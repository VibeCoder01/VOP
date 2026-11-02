"""Operator-only backup, selective restore and explicit factory reset."""
from contextlib import ExitStack
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from time import monotonic
from uuid import uuid4

from fasthtml.components import A, Button, Form, H2, Input, Label, P, Script, Section, Td, Tr
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse, JSONResponse, Response

from vop.dashboard import hidden
from vop.contracts import utcnow
from vop.reliable import configuration
from vop.storage import dumps
from vop.workspace_backup import (ALL, MAX_ARCHIVE, copy_database, create_archive, inspect_archive,
                                  mutable, queue_operation, selected_restore, connection)


SCRIPT = r'''document.addEventListener('submit',async event=>{
 const form=event.target;
 if(!form.matches('[data-workspace-upload],[data-workspace-apply]'))return;
 event.preventDefault();const button=form.querySelector('button'),status=form.querySelector('[role=status]');
 button.disabled=true;status.hidden=false;status.textContent=form.hasAttribute('data-workspace-upload')?'Uploading and checking backup. No settings have changed…':'Waiting for current work to finish. Applying the operation and restarting VOP…';
 try{
  let response;
  if(form.hasAttribute('data-workspace-upload')){
   const file=form.elements.backup.files[0];if(!file)throw Error('Choose a backup file.');
   const query=new URLSearchParams();for(const key of ['configs','data'])if(form.elements[key].checked)query.set(key,'on');
   response=await fetch(form.action+'?'+query,{method:'POST',headers:{'Content-Type':'application/octet-stream','X-VOP-CSRF':form.elements.csrf.value,Accept:'application/json'},body:file});
  }else response=await fetch(form.action,{method:'POST',headers:{Accept:'application/json'},body:new URLSearchParams(new FormData(form))});
  const body=await response.json();if(!response.ok)throw Error(body.message||body.error||'The operation did not complete.');
  if(body.url){location.assign(body.url);return;}
  for(let n=0;n<180;n++){
   await new Promise(resolve=>setTimeout(resolve,1000));
   try{const check=await fetch('/api/v1/health',{signal:AbortSignal.timeout(3000)});const state=check.ok?await check.json():null;
    if(state?.instance_id&&state.instance_id!==body.instance_id){
     if(body.factory_reset)for(const name of ['sessionStorage','localStorage'])try{
      const storage=globalThis[name];for(let i=(storage?.length||0)-1;i>=0;i--){const key=storage.key(i);if(key?.startsWith('vop-'))storage.removeItem(key);}
     }catch(_){}
     location.replace('/release?tab=configuration&notice='+encodeURIComponent(body.complete_message||body.message));return;}
   }catch(_){}
  }
  throw Error('Open Start VOP to finish the operation.');
 }catch(error){status.textContent=error.message;button.disabled=false;}
});'''


def choices():
    return [Label(Input(type='checkbox', name='configs', checked=True), ' Configuration'),
            P('Cameras and protected connection details, questions and image areas, engines, actions and audio clips, automations, notification rules and other settings.'),
            Label(Input(type='checkbox', name='data', checked=True), ' Captured data'),
            P('Saved camera images, recorded answers, episodes, engine metadata, notification history, action activity and audit history. Unsaved live previews are not included. Historical camera/question descriptions needed to read the data are included; credentials are not.')]


def controls(csrf, *, managed=True):
    return [Section(H2('Back up'), P('Choose what to include. Keep the downloaded backup private. Protected credentials require the same Windows user profile on this computer when restored.'),
                    Form(hidden(csrf), *choices(), Button('Download backup'), method='post', action='/release/backup')),
            Section(H2('Restore'), P('Open VOP with Start VOP to enable restore and reset.',cls='notice') if not managed else None, P('Choose a .vop backup and what to restore. A preview appears before anything changes. Selected groups replace their current contents; unchecked groups are kept. Maximum backup size: 2 GB.'),
                    Form(hidden(csrf), Input(type='file', name='backup', accept='.vop', required=True), *choices(),
                         Button('Upload and review'), P('', role='status', hidden=True), method='post', action='/release/restore/preview', data_workspace_upload=''),
                    P('To keep setup and discard history: back up Configuration only, reset VOP, then restore Configuration only. Restored automations and notification rules are paused for review; queued messages and actions are not replayed.'),
                    P('JavaScript is required to upload and track a restore. Downloaded backups and files you exported outside VOP are not deleted by reset.')),
            Section(H2('Factory reset'), P('Permanently delete all workspace configuration, captured data, saved clips, notification history, retired records and protected camera/device/worker details. The application stays installed and local sign-in keeps working.'),
                    A('Review factory reset…', href='/release/factory-reset', cls='button danger')),
            Script(src='/ui/maintenance.js', defer=True)]


def counts(path):
    import sqlite3
    with connection(path) as db:
        result = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in
                ('sources','query_controls','action_definitions','automations','rules','observations','frames','events','alerts')}
        result['images']=db.execute('SELECT count(*) FROM frames WHERE evidence_png IS NOT NULL').fetchone()[0]
        return result


def quiesce(app):
    pipeline = app.state.pipeline
    pipeline.stopping = True
    for worker in (app.state.sampler, app.state.reliable, app.state.actions):
        worker.stop_event.set()
    for worker in (app.state.sampler, app.state.reliable, app.state.actions):
        if worker.thread:
            worker.thread.join()
    with pipeline.busy:
        pipeline.persistent_cameras.stop()
        pipeline.live_previews.stop()
        app.state.worker_session.stop()


def install(app):
    previews, lock = {}, Lock()
    store, pipeline = app.state.store, app.state.pipeline

    def cleanup_uploads():
        with lock:
            for item in previews.values(): item['temp'].cleanup()
            previews.clear()
    app.state.workspace_cleanup_uploads = cleanup_uploads

    def prune():
        for key, item in list(previews.items()):
            if item['expires'] < monotonic():
                previews.pop(key)['temp'].cleanup()

    @app.route('/ui/maintenance.js', methods=['GET'])
    def javascript():
        return Response(SCRIPT, media_type='application/javascript')

    @app.route('/release/backup', methods=['POST'])
    async def backup(request):
        form = await request.form()
        configs, data = form.get('configs') == 'on', form.get('data') == 'on'
        temp = TemporaryDirectory(prefix='vop-download-')
        path = Path(temp.name) / 'workspace.vop'
        def make():
            with ExitStack() as stack:
                for guard in (pipeline.busy, app.state.reliable.lock, app.state.actions.lock):
                    stack.enter_context(guard)
                config = configuration(pipeline.settings, store, app.state.reliable)['config']
                return create_archive(store, config, app.state.secrets, path, configs=configs, data=data)
        try:
            await run_in_threadpool(make)
        except Exception:
            temp.cleanup()
            raise
        label='configuration-and-data' if configs and data else 'configuration' if configs else 'captured-data'
        filename='vop-'+label+'-'+utcnow().strftime('%Y%m%d-%H%M%S-UTC')+'.vop'
        return FileResponse(path, filename=filename, media_type='application/octet-stream', background=BackgroundTask(temp.cleanup))

    @app.route('/release/restore/preview', methods=['POST'])
    async def upload(request):
        configs = request.query_params.get('configs') == 'on'
        data = request.query_params.get('data') == 'on'
        if not configs and not data:
            raise ValueError('Select Configuration, Captured data, or both.')
        temp = TemporaryDirectory(prefix='vop-restore-')
        folder = Path(temp.name); archive = folder / 'upload.vop'
        try:
            size = 0
            with archive.open('wb') as output:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_ARCHIVE:
                        raise ValueError('Backup exceeds the 2 GB upload limit.')
                    await run_in_threadpool(output.write, chunk)
            manifest, config = await run_in_threadpool(inspect_archive, archive, folder / 'checked', store.path, app.state.secrets, decrypt_keys=configs)
            configs, data = configs and manifest['configuration'], data and manifest['data']
            if not configs and not data:
                raise ValueError('The backup does not contain a selected group. Select Configuration for a configuration-only backup, or Captured data for a data-only backup.')
            with lock:
                prune(); key = uuid4().hex
                previews[key] = dict(temp=temp, folder=folder/'checked', manifest=manifest, config=config,
                                     configs=configs, data=data, expires=monotonic()+900)
            return JSONResponse({'url':'/release/restore/'+key})
        except (ValueError, KeyError, OSError) as exc:
            temp.cleanup()
            raise ValueError(str(exc) if isinstance(exc, ValueError) else 'The backup could not be read. No settings were changed.') from None
        except Exception:
            temp.cleanup()
            raise ValueError('The backup could not be validated. No settings were changed.') from None

    @app.route('/release/restore/{key}', methods=['GET'])
    def review(key: str, request):
        with lock:
            prune(); item = previews.get(key)
            if not item:
                raise ValueError('This restore preview expired. Upload the backup again.')
            summary = counts(item['folder']/'workspace.sqlite3')
        return app.state.page('Review restore', request, [
            P('Backup: VOP '+str(item['manifest'].get('application_version','unknown'))+' · '+str(item['manifest'].get('created_at_utc','time not recorded'))),
            P('Replace: '+', '.join(label for selected,label in ((item['configs'],'Configuration'),(item['data'],'Captured data')) if selected)),
            P('Any group not selected or not included in the backup is kept. Old selected contents, including anything recorded since the backup, will be replaced.'),
            app.state.table(['Backup contents','Count'], [Tr(Td(label),Td(str(summary[key]))) for key,label in
                (('sources','Cameras / inputs, including retired'),('query_controls','Questions'),('action_definitions','Actions'),('automations','Automations'),('rules','Notification rules'),('observations','Answers'),('frames','Captured frames (metadata)'),('images','Saved images'),('events','Episodes'),('alerts','Notification history'))]), P('Automations and notification rules will be paused. Review them before resuming. Pending actions and messages will not be replayed.'),
            P('Open VOP with Start VOP before applying a restore.',cls='notice') if not app.state.shutdown_request else None,
            Form(hidden(request.scope['session']['csrf']), Button('Restore selected groups and restart',disabled=not app.state.shutdown_request), P('', role='status', hidden=True),
                 method='post', action='/release/restore/'+key+'/apply', data_workspace_apply=''),
            Form(hidden(request.scope['session']['csrf']), Button('Cancel', cls='secondary'), method='post', action='/release/restore/'+key+'/cancel'),
            Script(src='/ui/maintenance.js', defer=True)], view='settings')

    @app.route('/release/restore/{key}/cancel', methods=['POST'])
    def cancel(key: str):
        from starlette.responses import RedirectResponse
        with lock:
            item = previews.pop(key, None)
        if item: item['temp'].cleanup()
        return RedirectResponse('/release?tab=configuration', status_code=303)

    @app.route('/release/factory-reset', methods=['GET'])
    def reset_review(request):
        return app.state.page('Factory reset', request, [
            H2('Delete all VOP workspace data and settings'),
            P('This includes cameras, questions, image areas, engines, actions, clips, automations, notification rules and history, answers, images, episodes, audit records, retired records and protected connection details. There is no Undo.'),
            P('Download and verify a backup first if you want to restore your setup. The application, model files, local sign-in key, external backups and already-sent messages are not deleted.'),
            P('Open VOP with Start VOP before applying a reset.',cls='notice') if not app.state.shutdown_request else None,
            Form(hidden(request.scope['session']['csrf']), Label('Type RESET to confirm', Input(name='confirmation', required=True, pattern='RESET', autocomplete='off')),
                 Button('Delete all data and settings, then restart', cls='danger',disabled=not app.state.shutdown_request), P('', role='status', hidden=True), method='post', action='/release/factory-reset/apply', data_workspace_apply=''),
            A('Cancel',href='/release?tab=configuration',cls='button secondary'), Script(src='/ui/maintenance.js',defer=True)], view='settings')

    async def apply(request, key=None):
        if not app.state.shutdown_request:
            return JSONResponse({'message':'Open VOP with Start VOP to enable restart-boundary maintenance.'}, status_code=409)
        item = None
        if key is not None:
            with lock:
                prune(); item = previews.pop(key, None)
            if not item: raise ValueError('This restore preview expired. Upload the backup again.')
        else:
            form = await request.form()
            if form.get('confirmation') != 'RESET':
                raise ValueError('Type RESET exactly to confirm. No settings were changed.')
        def stage():
            with pipeline.workspace_condition:
                pipeline.workspace_maintenance = True
                while pipeline.workspace_writes > 1:  # Exclude this maintenance request.
                    pipeline.workspace_condition.wait()
            quiesce(app)
            with TemporaryDirectory(prefix='vop-apply-') as folder:
                path = Path(folder)/'workspace.sqlite3'
                if item:
                    selected_restore(store.path, item['folder']/'workspace.sqlite3', path, configs=item['configs'], data=item['data'])
                    config = item['config'] if item['configs'] else configuration(pipeline.settings,store,app.state.reliable)['config']
                    protected = {p.stem:p.read_bytes() for p in (item['folder']/'protected').glob('*.dpapi')} if item['configs'] else {}
                else:
                    copy_database(store.path,path)
                    import sqlite3
                    with connection(path) as db:
                        with mutable(db):
                            for table in ALL: db.execute(f'DELETE FROM {table}')
                            db.execute('DELETE FROM sqlite_sequence')
                        db.execute('VACUUM')
                    from vop.inference.liquid_d1 import CHECKPOINT_REVISION
                    default_engine = {'kind':'worker','id':'liquid-d1-3b','version':CHECKPOINT_REVISION,'worker_id':'antec-d1','url':'http://127.0.0.1:8878','transport':'ssh','secret_ref':'antec-worker','synthetic':False}
                    config = {'schema_version':1,'database':str(store.path),'timezone':'UTC','engine':default_engine,'sources':[],
                              'capture_timeout_seconds':10,'inference_timeout_seconds':30}
                    protected = {}
                queue_operation(store,path,config,protected,reset=item is None,replace_configs=bool(item and item['configs']))
        try:
            await run_in_threadpool(stage)
        except Exception as exc:
            # Database is untouched until the launcher applies the validated stage.
            # Restart is still needed to resume workers stopped for maintenance.
            message = str(exc) if isinstance(exc,ValueError) else 'VOP could not prepare the change.'
            return JSONResponse({'error':'operation_not_applied','message':message+' The previous workspace is kept. VOP will restart; upload again if needed.'},
                                status_code=400,background=BackgroundTask(app.state.shutdown_request,'restart'))
        finally:
            if item: item['temp'].cleanup()
        return JSONResponse({'status':'operation_queued','factory_reset':item is None,'instance_id':app.state.instance_id,'message':'The operation is queued. VOP will restart.',
                            'complete_message':'Factory reset complete.' if item is None else 'Restore complete. Automations and notification rules are paused; review them before resuming.'},
                            status_code=202, background=BackgroundTask(app.state.shutdown_request,'restart'))

    @app.route('/release/factory-reset/apply', methods=['POST'])
    async def reset_apply(request): return await apply(request)

    @app.route('/release/restore/{key}/apply', methods=['POST'])
    async def restore_apply(key: str, request): return await apply(request,key)
