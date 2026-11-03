"""Explicit purge of a retired camera, using existing write/worker/vault guards."""
from contextlib import ExitStack
import json

from fasthtml.components import A, Button, Dialog, Form, H2, Input, P, Progress, Script, Section
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from vop.contracts import utcnow
from vop.dashboard import hidden
from vop.history_deletion import checkpoint
from vop.secret_cleanup import references, queue
from vop.storage import dumps


def counts(db, sid):
    result = {label:db.execute(f'SELECT count(*) FROM {table} WHERE source_id=?',(sid,)).fetchone()[0]
              for label,table in (('Answers','observations'),('Captures','runs'),('Episodes','events'),('Notifications','alerts'))}
    result['Action activity'] = db.execute("SELECT count(*) FROM action_jobs WHERE json_extract(context,'$.source_id')=?",(sid,)).fetchone()[0]
    result['Saved images'] = db.execute('SELECT count(*) FROM frames WHERE source_id=? AND evidence_png IS NOT NULL',(sid,)).fetchone()[0]
    for label,table in (('Automations','automations'),('Notification rules','rules')):
        result[label] = db.execute(f"SELECT count(*) FROM {table} WHERE json_extract(configuration,'$.source_id')=?",(sid,)).fetchone()[0]
    return result


def purge(app, sid):
    pipeline, store = app.state.pipeline, app.state.store
    with ExitStack() as stack:
        for guard in (pipeline.busy,app.state.reliable.lock,app.state.actions.lock):
            stack.enter_context(guard)
        source = pipeline.removed_sources.get(sid)
        if source is None or source.kind not in ('rtsp','usb') or not store.is_removed(sid):
            raise ValueError('Only a retired camera can be permanently deleted. Retire it first.')
        protected = references(source.settings)
        with store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN ('immutable_question_delete','immutable_rule_delete')").fetchall()
            for trigger in triggers: db.execute('DROP TRIGGER '+trigger['name'])
            db.execute('DELETE FROM deliveries WHERE alert_id IN (SELECT id FROM alerts WHERE source_id=?)',(sid,))
            for table in ('alerts','events','observations','runs','frames','mock_values','query_controls','query_policies','question_versions'):
                db.execute(f'DELETE FROM {table} WHERE source_id=?',(sid,))
            db.execute("DELETE FROM action_jobs WHERE json_extract(context,'$.source_id')=?",(sid,))
            for row in db.execute("SELECT id FROM automations WHERE json_extract(configuration,'$.source_id')=?",(sid,)).fetchall():
                db.execute("UPDATE action_jobs SET status='cancelled',detail='Automation deleted with retired camera.' WHERE automation_id=? AND status IN ('queued','retry','sending')",(row['id'],))
            db.execute("DELETE FROM automations WHERE json_extract(configuration,'$.source_id')=?",(sid,))
            for row in db.execute("SELECT id FROM rules WHERE json_extract(configuration,'$.source_id')=?",(sid,)).fetchall():
                db.execute("DELETE FROM rule_states WHERE substr(id,1,?)=?",(len(row['id'])+1,row['id']+':'))
            db.execute("DELETE FROM rules WHERE json_extract(configuration,'$.source_id')=?",(sid,))
            # A rule can have been moved to another camera. Remove only this
            # camera's old revision state, preserving the current camera's state.
            for row in db.execute("SELECT id,revision FROM rule_versions WHERE json_extract(configuration,'$.source_id')=?",(sid,)).fetchall():
                prefix=f"{row['id']}:{row['revision']}:"
                db.execute('DELETE FROM rule_states WHERE substr(id,1,?)=?',(len(prefix),prefix))
            db.execute("DELETE FROM rule_versions WHERE json_extract(configuration,'$.source_id')=?",(sid,))
            for row in db.execute('SELECT id,value_json FROM release_settings').fetchall():
                parts = row['id'].split(':')
                if len(parts)>1 and parts[1]==sid and parts[0] in ('camera_profile','camera_name','camera_privacy','camera_test','retained_source','monitor_interval','removed_question','deleted_question'):
                    protected.update(references(json.loads(row['value_json'])))
                    db.execute('DELETE FROM release_settings WHERE id=?',(row['id'],))
                elif row['id']=='workspace_config':
                    config=json.loads(row['value_json'])
                    config['sources']=[s for s in config['sources'] if s['id']!=sid]
                    db.execute('UPDATE release_settings SET value_json=? WHERE id=?',(dumps(config),row['id']))
            db.execute('DELETE FROM source_controls WHERE source_id=?',(sid,))
            db.execute('DELETE FROM sources WHERE id=?',(sid,))
            # Minimal reserved IDs prevent launcher templates or replacements from
            # resurrecting the old camera. No name, credential or question is retained.
            db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)',('removed_source:'+sid,'true'))
            db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)',('deleted_source:'+sid,'true'))
            for name in protected: queue(db,name)
            for trigger in triggers: db.execute(trigger['sql'])
            db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)',(utcnow().isoformat(),'camera_delete',sid))
        pipeline.removed_sources.pop(sid,None)
        pipeline.clear_preview(sid)
        with pipeline.preview_lock:
            samples=[s for s in pipeline.timing_samples if s['source_id']!=sid]
            pipeline.timing_samples.clear();pipeline.timing_samples.extend(samples)
        sampler=app.state.sampler
        with sampler.pending_lock:
            sampler.pending.discard(sid)
            sampler.camera_tests={key:value for key,value in sampler.camera_tests.items() if key[0]!=sid}
        for mapping in (sampler.deadlines,sampler.failures,sampler.source_errors):mapping.pop(sid,None)
    app.state.actions.clear_history_cache(sid)
    for _ in protected:
        app.state.actions.cleanup_secrets()
        if app.state.actions.cleanup_error: break
    checkpoint(store)
    with store.connection() as db:
        return any(db.execute('SELECT 1 FROM release_settings WHERE id=?',('pending_secret_delete:'+name,)).fetchone() for name in protected)


def install(app):
    @app.route('/ui/sources/{source_id}/delete',methods=['GET','POST'])
    async def delete_camera(source_id: str,request):
        if request.scope.get('auth_role')!='operator':return Response('Operator required',status_code=403)
        pipeline,store=app.state.pipeline,app.state.store
        source=pipeline.removed_sources.get(source_id)
        if source is None or source.kind not in ('rtsp','usb'):
            raise ValueError('This retired camera is unavailable. Open Cameras to review it.')
        if request.method=='POST':
            form=await request.form()
            if form.get('confirmation')!='DELETE':raise ValueError('Type DELETE to permanently delete this retired camera and its data.')
            pending = await run_in_threadpool(purge,app,source_id)
            from urllib.parse import urlencode
            notice = 'Retired camera and its data permanently deleted.' + (' Protected-setting cleanup is pending; VOP will retry automatically.' if pending else '')
            return RedirectResponse('/cameras?'+urlencode({'notice':notice}),status_code=303)
        with store.connection() as db: summary=counts(db,source_id)
        return app.state.page('Permanently delete retired camera',request,[
            H2(source.name),P('Delete this retired camera, all its questions and recorded data, its automations and notification rules, and unused protected connection details. This cannot be restored from VOP.'),
            *(P(label+': '+str(value)) for label,value in summary.items()),
            P('Reusable actions and their audio clips remain. Shared credentials used elsewhere are kept. A reserved camera ID and audit history remain; external backups and already-sent messages are unchanged.'),
            P('Deletion waits for current work to finish. Counts are a preview; all data for this camera will be removed.'),
            Form(hidden(request.scope['session']['csrf']),P('Type DELETE to confirm'),Input(name='confirmation',pattern='DELETE',required=True,autocomplete='off'),
                 Button('Delete camera and all its data',cls='danger'),method='post',action=request.url.path,data_question_delete=''),
            A('Cancel',href='/cameras',cls='button secondary'),
            Dialog(Section(H2('Deleting retired camera'),P('Keep this page open. The result will appear when deletion finishes.'),Progress('Deletion in progress')),data_question_delete_progress=''),
            Script(src='/ui/question-delete.js',defer=True)],view='cameras')
