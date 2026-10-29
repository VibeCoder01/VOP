"""Operator-owned engine profiles and protected camera setup. No credentials in SQLite."""
from dataclasses import replace
import ipaddress
from hashlib import sha256
import json
import re
import secrets as random_secrets
from urllib.parse import urlsplit

from fasthtml.components import A, Button, Details, Div, Form, H2, Input, Label, Option, P, Pre, Section, Select, Small, Span, Summary, Script
from starlette.concurrency import run_in_threadpool
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
from fasthtml.common import to_xml
from vop.display import duration, duration_input

from vop.config import SourceSpec, identifier
from vop.contracts import AnswerKind, ProviderError, QuestionSpec, utcnow
from vop.dashboard import field, hidden, evidence_image, dependency_panel, action
from vop.inference.liquid_d1 import CHECKPOINT_REVISION
from vop.inference.mock import MockInferenceEngine
from vop.inference.remote import RemoteInferenceEngine, profile
from vop.inputs.sources import SourceAdapters
from vop.preprocessing import preprocess
from vop.secrets import SecretStore, reference
from vop.mask_editor import editor as mask_editor, parse_regions
from vop.storage import dumps
from vop.ui_readiness import camera_dependencies, worker_dependencies


def antec_profile(engine):
    return (isinstance(engine, RemoteInferenceEngine) and engine.config["worker_id"] == "antec-d1"
            and engine.config["transport"] == "ssh" and engine.config["url"] == "http://127.0.0.1:8878"
            and engine.engine_id == "liquid-d1-3b" and engine.engine_version == CHECKPOINT_REVISION and not engine.synthetic)


def worker_health_content(health):
    from vop.operator_workflow import recovery_message
    error = health.get('error') or ''
    code = error.get('code', '') if isinstance(error, dict) else str(error)
    return [P('Last check: connected.' if health.get('ready') else 'Last check: not connected.',
              role='status', cls='readiness success' if health.get('ready') else 'readiness warning'),
            P(recovery_message(code)) if not health.get('ready') else None,
            P('The engine is busy. Wait, then try again.') if health.get('busy') else None,
            Details(Summary('Connection details'), Pre(dumps(health)))]


def camera_source(record):
    model = record["model"]
    if model not in ("C200", "C210", "C510W"):
        raise ValueError("Unsupported pilot camera model")
    sid = identifier(record["source_id"])
    options = {"endpoint_secret_ref": reference(record["endpoint_ref"]), "secret_ref": reference(record["credentials_ref"]), "allowed_hosts": record["allowed_hosts"]}
    if record.get("privacy_masks"):
        options["privacy_masks"] = record["privacy_masks"]
    return SourceSpec(sid, "Tapo " + model, "rtsp", options,
                      (QuestionSpec("human_present", "1", "Is there a human in the picture?", AnswerKind.BINARY),), enabled=False)


def restore_cameras(store, settings, pipeline):
    with store.connection() as db:
        rows = db.execute("SELECT value_json FROM release_settings WHERE id LIKE 'camera_profile:%'").fetchall()
        names = {row[0].removeprefix('camera_name:'): json.loads(row[1]) for row in
                 db.execute("SELECT id,value_json FROM release_settings WHERE id LIKE 'camera_name:%'")}
        privacy = {row[0].removeprefix('camera_privacy:'): json.loads(row[1]) for row in
                   db.execute("SELECT id,value_json FROM release_settings WHERE id LIKE 'camera_privacy:%'")}
    for row in rows:
        source = camera_source(json.loads(row[0]))
        source = replace(source, name=names.get(source.source_id, source.name))
        store.configure(replace(settings, sources=(source,)))
        target = pipeline.removed_sources if store.is_removed(source.source_id) else pipeline.sources
        target[source.source_id] = source
    for sources in (pipeline.sources, pipeline.removed_sources):
        for sid, source in list(sources.items()):
            if source.kind in ('rtsp', 'usb') and (sid in names or sid in privacy):
                sources[sid] = replace(source, name=names.get(sid,source.name),
                                       settings={**source.settings, 'privacy_masks':privacy.get(sid,source.settings.get('privacy_masks', []))})
                store.configure(replace(settings, sources=(sources[sid],)))


def install_integration(app, settings, store, pipeline):
    secrets = SecretStore()
    app.state.secrets = secrets
    def operator(request):
        return request.scope.get("auth_role") == "operator"
    def busy():
        if not pipeline.busy.acquire(False):
            raise ProviderError("overloaded", "Stop or wait for the current capture/inference before changing profiles")

    def csrf(request):
        return request.scope['session'].setdefault('csrf', random_secrets.token_urlsafe(24))

    def denied(request):
        if not operator(request):
            return JSONResponse({'error': 'operator_required'}, status_code=403)

    def saved_engines():
        with store.connection() as db:
            rows = db.execute("SELECT id,value_json FROM release_settings WHERE id LIKE 'saved_engine:%' ORDER BY id").fetchall()
        return {row[0].split(':', 1)[1]: json.loads(row[1]) for row in rows}

    def save_engine_record(eid, name, value):
        with store.connection() as db:
            db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('saved_engine:' + eid, dumps({'name': name, 'profile': value})))

    if not saved_engines():
        save_engine_record('current', 'Antec AI' if antec_profile(pipeline.engine) else 'Demo' if pipeline.engine.synthetic else pipeline.engine.engine_id, pipeline.engine_profile)

    with store.connection() as db:
        if not db.execute("SELECT 1 FROM release_settings WHERE id='active_engine_profile_id'").fetchone():
            selected_id = next((eid for eid, record in saved_engines().items() if record['profile'] == pipeline.engine_profile), None)
            db.execute("INSERT INTO release_settings VALUES('active_engine_profile_id',?)", (dumps(selected_id),))

    def active_engine_id():
        with store.connection() as db:
            return json.loads(db.execute("SELECT value_json FROM release_settings WHERE id='active_engine_profile_id'").fetchone()[0])

    def engine_record(eid):
        if eid not in saved_engines():
            raise ValueError('This engine does not exist. Open Engines and select a saved engine.')
        return saved_engines()[eid]

    def camera_record(sid):
        source = pipeline.sources.get(sid)
        if source is None or source.kind not in ('rtsp', 'usb'):
            raise ValueError('This camera does not exist. Open Cameras and select a saved camera.')
        return source

    @app.route('/integration', methods=['GET'])
    def integration(request):
        if denied(request): return denied(request)
        if request.query_params.get('camera'):
            return camera_editor(request.query_params['camera'], request)
        if 'new_camera' in request.query_params:
            return camera_editor('new', request)
        return app.state.page('Setup', request, [
            Section(H2('Cameras'), P('Add a camera or change its connection.'), A('Open Cameras', href='/cameras', cls='button')),
            Section(H2('Engines'), P('Save an engine profile. Select an engine for observations.'), A('Open Engines', href='/engines', cls='button'))
        ], view='settings')

    @app.route('/cameras', methods=['GET'])
    def cameras(request):
        if denied(request): return denied(request)
        rows = [source for source in pipeline.sources.values() if source.kind in ('rtsp', 'usb')]
        content = [Div(P(str(len(rows)) + (' camera' if len(rows) == 1 else ' cameras')),
                       A('Add camera', href='/cameras/new', cls='button'), cls='section-heading')]
        content.append(Div(*(Div(Div(H2(A(source.name, href='/cameras/' + source.source_id)),
                                    P(source.source_id, cls='object-meta'),
                                    P('Monitoring' if store.source_control(source.source_id)['sample_interval_seconds'] and store.source_control(source.source_id)['enabled'] else 'Monitoring paused', cls='object-meta'), cls='object-copy'),
                                 Div(A('Manage camera', href='/cameras/' + source.source_id, cls='button secondary'), cls='actions'), cls='object-row') for source in rows), cls='object-list camera-list')
                       if rows else Div(H2('Add your first camera'), P('Enter its network address and camera account. The engine is set up on the Engines page.'),
                                        A('Add camera', href='/cameras/new', cls='button'), cls='empty'))
        from vop.removal import removed_controls
        content.append(removed_controls(store, pipeline, csrf(request), 'sources', source_kinds=('rtsp', 'usb'), heading='Retired Cameras'))
        return app.state.page('Cameras', request, content, view='cameras', notice=request.query_params.get('notice'))

    def camera_editor(source_id, request):
        if denied(request): return denied(request)
        selected = camera_record(source_id) if source_id != 'new' else None
        usb = selected is not None and selected.kind == 'usb'
        control = store.source_control(source_id) if selected else {'enabled':False, 'retain_evidence':False, 'sample_interval_seconds':0}
        endpoint, username, warning = '', '', None
        missing = []
        if selected and not usb:
            try:
                endpoint = secrets.get(selected.settings['endpoint_secret_ref'])
            except ProviderError:
                missing.append('camera address')
            try:
                username = secrets.camera(selected.settings['secret_ref'])['username']
            except ProviderError:
                missing.append('camera account')
            if missing:
                warning = P('Saved ' + ' and '.join(missing) + ' could not be read. Check those fields and save the corrected details. Any readable saved details are kept.', cls='readiness warning')
        model = 'C200'
        if selected and not usb:
            with store.connection() as db:
                row = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('camera_profile:' + source_id,)).fetchone()
            model = json.loads(row[0])['model'] if row else selected.name.removeprefix('Tapo ')
        last_test = None
        if selected:
            with store.connection() as db:
                row = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('camera_test:' + source_id,)).fetchone()
                last_test = json.loads(row[0]) if row else None
        return app.state.page(selected.name if selected else 'Add camera', request, [
            A('‹ Cameras', href='/cameras', cls='back'), warning,
            P('Monitoring' if control['enabled'] and control['sample_interval_seconds'] else 'Monitoring paused' if control['enabled'] else 'Camera disabled',
              cls='status success' if control['enabled'] and control['sample_interval_seconds'] else 'status warning') if selected else None,
            Form(hidden(csrf(request)), Input(type='hidden', name='source_id', value=source_id if selected else ''),
                 Input(type='hidden', name='observation_settings', value='1'),
                 Section(H2('Camera'), field('Camera name', 'name', selected.name if selected else '',
                         placeholder='For example, Front door', maxlength=128),
                         P('Choose a name you recognise.', cls='muted')),
                 Section(H2('Connection'),
                     P('USB camera · device ' + str(selected.settings.get('device', 0)), cls='muted') if usb else
                     Div(Div(Label('Camera model', _for='camera-model'), Select(*(Option(m, value=m, selected=m == model) for m in ('C200', 'C210', 'C510W')), name='model', id='camera-model'), cls='field'),
                         field('Camera address', 'endpoint', endpoint, placeholder='rtsp://CAMERA-IP:554/stream1', required=True),
                         P('Use the LAN address with /stream1 for full size or /stream2 for a smaller image.', cls='muted'),
                         Div(field('Camera username', 'username', username, autocomplete='username', required=not selected),
                             field('Camera password', 'password', type='password', autocomplete='new-password', required=not selected), cls='pair'),
                         P('Leave the password empty to keep the saved password.', cls='muted') if selected else None),
                     dependency_panel(camera_dependencies(selected), ready='Connection details are saved.') if selected else None,
                     P('Camera test scheduled. ', A('Open test result', href='/integration/cameras/' + source_id + '/test'), cls='notice') if selected and app.state.sampler.camera_test_requested(source_id) else None,
                     P('Last test: image received.' if last_test.get('status') == 'capture_success' else 'Last test failed. Check the connection details and test again.', cls='muted') if last_test else None,
                     P('Save and test connection below saves this form, then receives one image. The connection test does not run inference or keep an image.', cls='muted') if selected and not usb else None),
                 Section(H2('Observations'),
                     Label(Input(type='checkbox', name='enabled', checked=control['enabled']), ' Camera enabled'),
                     P('When off, this camera does not take observations. Its saved questions and history remain.', cls='muted'),
                     field('Sample interval (H:M:S)', 'sample_interval_seconds', duration(control['sample_interval_seconds']), required=True,
                           aria_describedby='camera-interval-help'),
                     P('Applies to all enabled questions on this camera. Use 00:00:00.0 to pause monitoring, or 00:00:01.0 to 01:00:00.0 for repeated observations. Cameras take turns, so processing and connection delays can make the actual interval longer.', id='camera-interval-help', cls='muted'),
                     P('Saving a nonzero interval starts monitoring when Camera enabled is on.', cls='muted'), id='observations'),
                 Section(H2('Recorded images'),
                     Label(Input(type='checkbox', name='retain_evidence', checked=control['retain_evidence']), ' Save images with observations'),
                     P('Off by default. When on, future observations keep a privacy-masked still image for Individual Observations. Questions from the same capture share one image.', cls='muted'),
                     P('Turning this off keeps images already saved. It cannot recover earlier unsaved or deleted images.', cls='muted'), id='image-saving'),
                 mask_editor(source_id, exclude=selected.settings.get('privacy_masks', ()), privacy=True) if selected else
                 P('Save the camera before adding a privacy mask.', cls='muted'),
                 P('Save waits for the current observation. Changes apply to the next one.', cls='muted'),
                 Div(Button('Save settings' if selected else 'Add camera'),
                     Button('Save and test connection', name='connect', value='1', cls='secondary') if selected and not usb else None,
                     A('Cancel', href='/cameras', cls='button secondary'), cls='actions'),
                 method='post', action='/cameras/save', cls='editor camera-editor'),
            Script(src='/ui/mask-editor.js', defer=True) if selected else None,
            Section(H2('Questions'), P('Choose what this camera observes.'),
                    A('Manage questions', href='/?view=questions&source=' + source_id, cls='button secondary'), cls='camera-related') if selected else None,
            Section(H2('Remove camera'), P('Stop using this camera. Its history and protected details remain. You can restore it.'),
                    A('Remove camera…', href='/ui/sources/' + source_id + '/remove', cls='button danger'), cls='camera-related') if selected else None
        ], view='cameras', notice=request.query_params.get('notice'))

    @app.route('/cameras/new', methods=['GET'])
    def new_camera(request):
        return camera_editor('new', request)

    @app.route('/cameras/{source_id}/edit', methods=['GET'])
    def edit_camera(source_id: str, request):
        return RedirectResponse('/cameras/' + source_id, status_code=303)

    @app.route('/cameras/{source_id}/rename', methods=['GET'])
    def rename_camera_editor(source_id: str, request):
        if denied(request): return denied(request)
        source = camera_record(source_id)
        return RedirectResponse('/cameras/' + source_id, status_code=303)

    @app.route('/cameras/{source_id}/rename', methods=['POST'])
    async def rename_camera(source_id: str, request):
        source = camera_record(source_id)
        name = str((await request.form()).get('name', '')).strip()
        if not name or len(name) > 128 or any(ord(c) < 32 for c in name):
            raise ValueError('Enter a camera name with 1 to 128 characters.')
        source = replace(source, name=name)
        busy()
        try:
            with store.connection() as db:
                configuration = json.loads(db.execute('SELECT configuration FROM sources WHERE id=?', (source_id,)).fetchone()[0])
                configuration['name'] = name
                db.execute('UPDATE sources SET configuration=? WHERE id=?', (dumps(configuration), source_id))
                db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('camera_name:' + source_id, dumps(name)))
            pipeline.sources[source_id] = source
            store.audit('camera_name', 'saved')
        finally:
            pipeline.busy.release()
        return RedirectResponse('/cameras/' + source_id + '?notice=Camera+name+saved.', status_code=303)

    @app.route('/cameras/{source_id}', methods=['GET'])
    def camera_detail(source_id: str, request):
        return camera_editor(source_id, request)

    @app.route('/engines', methods=['GET'])
    def engines(request):
        if denied(request): return denied(request)
        entries = saved_engines()
        selected_id = active_engine_id()
        return app.state.page('Engines', request, [
            Div(P('Use one engine for all observations.'), A('Add engine', href='/engines/new', cls='button'), cls='section-heading'),
            Div(*(Div(Div(H2(A(record['name'], href='/engines/' + eid)),
                          P('Demo · synthetic answers' if record['profile']['kind'] == 'mock' else record['profile']['id'], cls='object-meta'),
                          Span('Selected', cls='status info') if eid == selected_id and record['profile'] == pipeline.engine_profile else
                          Span('Saved changes', cls='status warning') if eid == selected_id else None, cls='object-copy'),
                      Div(A('Open engine', href='/engines/' + eid, cls='button secondary'), A('Edit', href='/engines/' + eid + '/edit', cls='text-link'),
                          A('Delete…', href='/engines/' + eid + '/delete', cls='button danger'), cls='actions'), cls='object-row')
                  for eid, record in entries.items()), cls='object-list')
        ], view='engines', notice=request.query_params.get('notice'))

    def engine_editor(eid, request):
        if denied(request): return denied(request)
        record = engine_record(eid) if eid != 'new' else None
        value = record['profile'] if record else {
            'kind': 'worker', 'id': 'liquid-d1-3b', 'version': CHECKPOINT_REVISION,
            'worker_id': 'antec-d1', 'url': 'http://127.0.0.1:8878', 'transport': 'ssh', 'secret_ref': 'antec-worker', 'synthetic': False}
        kind = value['kind'] if record else request.query_params.get('kind', 'worker')
        if getattr(pipeline, 'live_workspace', False) and kind != 'worker': raise ValueError('Choose an AI worker.')
        if kind not in ('mock', 'worker'): raise ValueError('Choose a worker or demo engine.')
        return app.state.page('Edit engine' if record else 'Add engine', request, [
            A('‹ Engines', href='/engines', cls='back'),
            Div(A('AI worker', href='/engines/new?kind=worker', cls='button' if kind == 'worker' else 'button secondary'),
                A('Demo', href='/engines/new?kind=mock', cls='button' if kind == 'mock' else 'button secondary'), cls='actions') if not record and not getattr(pipeline, 'live_workspace', False) else None,
            Form(hidden(csrf(request)), Input(type='hidden', name='kind', value=kind),
                 Div(H2('Engine profile'), field('Name', 'name', record['name'] if record else 'Antec AI' if kind == 'worker' else 'Demo', required=True, maxlength=80),
                     P('The Antec settings are filled in. Open Connection settings only to change them.') if kind == 'worker' and not record else None,
                     Details(Summary('Connection settings'),
                         field('Engine ID', 'engine_id', value.get('id', 'liquid-d1-3b'), required=True),
                         field('Model revision', 'version', value.get('version', CHECKPOINT_REVISION), required=True),
                         field('Worker ID', 'worker_id', value.get('worker_id', 'antec-d1'), required=True),
                         field('Local connection address', 'url', value.get('url', 'http://127.0.0.1:8878'), required=True),
                         P('Use a loopback address. A remote worker is reached through an SSH tunnel.', cls='muted'),
                         Div(Label('Connection type', _for='worker-transport'), Select(Option('SSH tunnel', value='ssh', selected=value.get('transport') == 'ssh'), Option('Local worker', value='local', selected=value.get('transport') == 'local'), name='transport', id='worker-transport'), cls='field'),
                         field('Worker access key', 'worker_token', type='password', autocomplete='new-password'),
                         P('Leave empty to keep the saved key. VOP can recover the Antec key.', cls='muted'),
                         field('Synthetic worker (test only)', 'synthetic', 'on', type='checkbox', checked=value.get('synthetic', False)) if not getattr(pipeline, 'live_workspace', False) else None) if kind == 'worker' else P('Demo answers are synthetic. This engine does not analyse images.', cls='readiness warning'), cls='surface'),
                 P('Save stores this profile. Use engine selects it for observations.', cls='muted'),
                 Div(Button('Save engine'), A('Cancel', href='/engines/' + eid if record else '/engines', cls='button secondary'), cls='actions'),
                 method='post', action='/engines/' + eid + '/save', cls='editor')
        ], view='engines')

    @app.route('/engines/new', methods=['GET'])
    def new_engine(request): return engine_editor('new', request)

    @app.route('/engines/{engine_id}/edit', methods=['GET'])
    def edit_engine(engine_id: str, request): return engine_editor(engine_id, request)

    @app.route('/engines/{engine_id}/save', methods=['POST'])
    async def save_engine(engine_id: str, request):
        form = await request.form()
        record = engine_record(engine_id) if engine_id != 'new' else None
        name = str(form.get('name', '')).strip()
        if not name or len(name) > 80: raise ValueError('Enter an engine name with 1 to 80 characters.')
        eid = engine_id
        if not record:
            entries = saved_engines()
            if len(entries) >= 32: raise ValueError('You can save up to 32 engines.')
            base = re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')[:50] or 'engine'
            eid, number = base, 1
            while eid in entries or eid == 'new':
                number += 1
                eid = base + '-' + str(number)
        if getattr(pipeline, 'live_workspace', False) and (form['kind'] != 'worker' or 'synthetic' in form): raise ValueError('Choose a real AI worker.')
        if form['kind'] == 'mock':
            value = record['profile'] if record and record['profile']['kind'] == 'mock' else {'kind': 'mock', 'id': 'synthetic-mock', 'answers': {**settings.mock_answers, 'human_present': False}}
        elif form['kind'] == 'worker':
            secret_ref = record['profile'].get('secret_ref', 'antec-worker') if record else 'antec-worker'
            key = str(form.get('worker_token', ''))
            if key:
                if not 32 <= len(key) <= 256 or not key.isascii() or any(c.isspace() for c in key):
                    raise ValueError('The worker key must contain 32 to 256 ASCII characters without spaces.')
                secret_ref = 'engine-key-' + random_secrets.token_hex(12)
            value = profile({'kind': 'worker', 'id': str(form['engine_id']), 'version': str(form['version']),
                             'worker_id': str(form['worker_id']), 'url': str(form['url']), 'transport': str(form['transport']),
                             'secret_ref': secret_ref, 'synthetic': 'synthetic' in form})
            if key: await run_in_threadpool(secrets.set, secret_ref, key)
        else: raise ValueError('Choose a worker or demo engine.')
        save_engine_record(eid, name, value)
        store.audit('engine_profile', 'saved')
        return RedirectResponse('/engines/' + eid + '?notice=Engine+saved.+Select+Use+engine+to+apply+it.', status_code=303)

    async def select_engine(eid, value):
        busy()
        try:
            if value != pipeline.engine_profile:
                await run_in_threadpool(app.state.worker_session.stop)
            engine = RemoteInferenceEngine(value, allow_remote=True, secrets=secrets) if value['kind'] == 'worker' else MockInferenceEngine(value['answers'], value['id'])
            if isinstance(engine, MockInferenceEngine):
                for sid, qid, version, preset in store.mock_values(): engine.configure_source_answer(sid, qid, version, preset)
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES('engine_profile',?)", (dumps(value),))
                db.execute("INSERT OR REPLACE INTO release_settings VALUES('active_engine_profile_id',?)", (dumps(eid),))
            pipeline.engine, pipeline.engine_profile = engine, value
            if pipeline.auto_worker:
                pipeline.auto_worker.retry_after, pipeline.auto_worker.last_failure = 0, None
            store.audit('engine_selection', 'saved_profile')
        finally: pipeline.busy.release()

    @app.route('/engines/{engine_id}/use', methods=['POST'])
    async def use_engine(engine_id: str, request):
        await select_engine(engine_id, engine_record(engine_id)['profile'])
        return RedirectResponse('/engines/' + engine_id + '?notice=Engine+in+use.', status_code=303)

    @app.route('/engines/{engine_id}/delete', methods=['GET', 'POST'])
    async def delete_engine(engine_id: str, request):
        if denied(request): return denied(request)
        record = engine_record(engine_id)
        expected = sha256(dumps(record).encode()).hexdigest()
        selected = engine_id == active_engine_id()
        changed = False
        if request.method == 'POST' and not selected:
            form = await request.form()
            if str(form.get('expected', '')) == expected:
                busy()
                try:
                    with store.connection() as db:
                        from vop.secret_cleanup import queue
                        db.execute('BEGIN IMMEDIATE')
                        queue(db, record['profile'].get('secret_ref'))
                        db.execute('DELETE FROM release_settings WHERE id=?', ('saved_engine:' + engine_id,))
                    store.audit('engine_profile', 'deleted')
                finally: pipeline.busy.release()
                app.state.actions.cleanup_secrets()
                return RedirectResponse('/engines?notice=Engine+profile+deleted.', status_code=303)
            changed = True
        return app.state.page('Delete engine profile', request, [
            P(record['name']), P('The profile changed. Review it before you confirm.', cls='readiness warning') if changed else None,
            P('Select another engine before you delete this one.', cls='readiness warning') if selected else None,
            A('Choose another engine', href='/engines', cls='button') if selected else None,
            P('This deletes the saved profile and its unused protected key. Keys shared with another configuration stay. Recorded observations and shared model files remain.'),
            P('This cannot be undone in VOP.'),
            Form(hidden(csrf(request)), Input(type='hidden', name='expected', value=expected), Button('Delete profile', cls='danger', disabled=selected), method='post', action=request.url.path),
            A('Cancel', href='/engines/' + engine_id, cls='button secondary')
        ], view='engines')

    @app.route('/engines/{engine_id}', methods=['GET'])
    def engine_detail(engine_id: str, request):
        if denied(request): return denied(request)
        record = engine_record(engine_id)
        value, active = record['profile'], engine_id == active_engine_id() and record['profile'] == pipeline.engine_profile
        session = app.state.worker_session.status()
        return app.state.page(record['name'], request, [
            A('‹ Engines', href='/engines', cls='back'),
            Div(Span('Selected' if active else 'Saved', cls='status info' if active else 'status'),
                A('Edit engine', href='/engines/' + engine_id + '/edit', cls='button secondary'), cls='section-heading'),
            Section(H2('Use this engine'), P('This engine will answer questions for all cameras.'),
                    P('The previous settings are still selected. Use engine applies the saved changes.', cls='readiness info') if engine_id == active_engine_id() and not active else None,
                    P('Demo answers are synthetic. They do not describe the camera image.', cls='readiness warning') if value['kind'] == 'mock' else None,
                    action('Use engine', '/engines/' + engine_id + '/use', csrf(request)) if not active else P('This engine is selected. The connection is checked when you observe.', cls='muted'),
                    P('Switch to View mode to run observations.') if active else None),
            Section(H2('Connection'), P('VOP connects to Antec when you run an observation.') if active and antec_profile(pipeline.engine) else P('Check the selected engine without sending a camera image.'),
                    P('The check can start a 15-minute Antec session.', cls='muted') if active and antec_profile(pipeline.engine) and pipeline.auto_worker else None,
                    action('Check connection', '/integration/health', csrf(request)) if active else P('Select Use engine before you check its connection.', cls='muted'),
                    *(worker_health_content(pipeline.engine.last_health) if active and getattr(pipeline.engine, 'last_health', None) else [])),
            Details(Summary('Session controls'), P('Antec sessions pause the other GPU workload. The workload returns when the session ends.'),
                    P('A VOP session is active.' if session['active'] else 'No VOP session is active.'),
                    Form(hidden(csrf(request)), Select(*(Option(duration(m * 60), value=str(m)) for m in (15, 30, 60)), name='minutes', aria_label='Session length'),
                         Button('Start session', disabled=session['active']), method='post', action='/integration/session/start'),
                    action('Stop session', '/integration/session/stop', csrf(request), secondary=True) if session['active'] else None) if active and antec_profile(pipeline.engine) else None,
            Details(Summary('Engine details'), Pre(dumps({k: v for k, v in value.items() if k not in ('secret_ref', 'answers')}))),
            Section(H2('Delete profile'), P('Delete this saved profile. Model files and observations remain.'),
                    A('Delete engine profile…', href='/engines/' + engine_id + '/delete', cls='button danger'))
        ], view='engines', notice=request.query_params.get('notice'))

    @app.route('/integration/engine/antec', methods=['POST'])
    async def antec_preset():
        value = profile({'kind': 'worker', 'id': 'liquid-d1-3b', 'version': CHECKPOINT_REVISION, 'worker_id': 'antec-d1',
                         'url': 'http://127.0.0.1:8878', 'transport': 'ssh', 'secret_ref': 'antec-worker', 'synthetic': False})
        save_engine_record('legacy-current', 'Antec AI', value)
        await select_engine('legacy-current', value)
        return RedirectResponse('/engines/legacy-current?notice=Engine+in+use.', status_code=303)

    @app.route("/integration/session/start", methods=["POST"])
    async def session_start(request):
        form = await request.form()
        engine = pipeline.engine
        if not antec_profile(engine):
            raise ValueError("Select the real antec-d1 SSH backend at http://127.0.0.1:8878 before starting its session")
        if worker_dependencies(engine):
            raise ValueError("Save a readable worker access key in backend setup before starting antec")
        await run_in_threadpool(app.state.worker_session.start, int(form.get("minutes", "15")))
        store.audit("worker_session", "start_requested")
        return RedirectResponse('/engines?notice=Session+starting.+Open+the+engine+to+check+its+connection.', status_code=303)

    @app.route("/integration/session/stop", methods=["POST"])
    async def session_stop(request):
        await run_in_threadpool(app.state.worker_session.stop)
        store.audit("worker_session", "stop_requested")
        return RedirectResponse('/engines?notice=Session+stopped.+Workload+restoration+requested.', status_code=303)

    @app.route("/integration/consent", methods=["POST"])
    async def image_consent(request):
        if not isinstance(pipeline.engine, RemoteInferenceEngine):
            raise ValueError("Select an authenticated worker before enabling image transmission")
        form = await request.form()
        busy()
        try:
            pipeline.engine.allow_remote = "allow" in form
            store.audit("remote_consent", "enabled" if pipeline.engine.allow_remote else "disabled")
        finally:
            pipeline.busy.release()
        return RedirectResponse("/integration?notice=Image+permission+updated", status_code=303)

    @app.route("/integration/engine", methods=["POST"])
    async def engine_edit(request):
        form = await request.form()
        if getattr(pipeline, "live_workspace", False) and (form.get("kind") != "worker" or "synthetic" in form): raise ValueError("Choose a real AI worker.")
        if form.get("kind") == "mock":
            value = {"kind": "mock", "id": "synthetic-mock", "answers": {**settings.mock_answers, "human_present": False}}
        elif form.get("kind") == "worker":
            value = profile({"kind": "worker", "id": str(form["engine_id"]), "version": str(form["version"]), "worker_id": str(form["worker_id"]), "url": str(form["url"]), "secret_ref": str(form["secret_ref"]), "transport": str(form["transport"]), "synthetic": "synthetic" in form})
            key = str(form.get("worker_token", ""))
            if key:
                if not 32 <= len(key) <= 256 or not key.isascii() or any(c.isspace() for c in key):
                    raise ValueError("Worker key must be 32–256 ASCII characters without whitespace")
                await run_in_threadpool(secrets.set, value["secret_ref"], key)
        else:
            raise ValueError("Unknown engine kind")
        save_engine_record('legacy-current', 'Demo' if value['kind'] == 'mock' else value['id'], value)
        await select_engine('legacy-current', value)
        return RedirectResponse('/engines/legacy-current?notice=Engine+in+use.', status_code=303)

    @app.route("/integration/health", methods=["POST"])
    async def engine_health(request):
        if isinstance(pipeline.engine, RemoteInferenceEngine):
            try:
                if getattr(pipeline, 'auto_worker', None):
                    await run_in_threadpool(pipeline.auto_worker.ensure_ready)
                health = await run_in_threadpool(pipeline.engine.health)
            except ProviderError as exc:
                health = {"ready": False, "error": exc.code, "message": exc.message}
                pipeline.engine.last_health = health
        else:
            health = {"ready": True, "device": "mock", "synthetic": True, "engine_id": pipeline.engine.engine_id}
        store.audit("engine_health", "ready" if health.get("ready") else "unavailable")
        return app.state.page("Engine connection", request, [*worker_health_content(health),
            Div(action('Check again', '/integration/health', csrf(request)),
                A("Back to Engines", href="/engines", cls='button secondary'), cls='actions')], view="engines")

    @app.route("/integration/camera", methods=["POST"])
    async def camera_edit(request):
        form = await request.form()
        requested_id = str(form.get('source_id', '')).strip()
        if not requested_id:
            base = 'tapo-' + str(form['model']).lower()
            requested_id, number = base, 1
            while requested_id in pipeline.sources or requested_id in pipeline.removed_sources:
                number += 1
                requested_id = base + '-' + str(number)
        sid = identifier(requested_id)
        is_new = sid not in pipeline.sources
        previous_masks = pipeline.sources[sid].settings.get('privacy_masks', ()) if not is_new else ()
        privacy_masks = parse_regions(str(form.get('privacy_masks', dumps(previous_masks))))
        controls = None
        if form.get('observation_settings') == '1':
            interval = duration_input(form.get('sample_interval_seconds', ''))
            if interval != 0 and not 1 <= interval <= 3600:
                raise ValueError('Use 00:00:00.0 to pause, or an interval from 00:00:01.0 to 01:00:00.0.')
            controls = {'enabled':form.get('enabled') == 'on', 'retain_evidence':form.get('retain_evidence') == 'on',
                        'sample_interval_seconds':interval}
        if not is_new and pipeline.sources[sid].kind == 'usb':
            source = pipeline.sources[sid]
            name = str(form.get('name', source.name)).strip()
            if not name or len(name) > 128 or any(ord(c) < 32 for c in name):
                raise ValueError('Enter a camera name with 1 to 128 characters.')
            await run_in_threadpool(pipeline.busy.acquire)
            try:
                source = replace(source, name=name, settings={**source.settings, 'privacy_masks':privacy_masks})
                store.configure(replace(settings, sources=(source,)))
                with store.connection() as db:
                    db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('camera_name:' + sid, dumps(name)))
                    db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('camera_privacy:' + sid, dumps(privacy_masks)))
                pipeline.sources[sid] = source
                if controls is not None:
                    previous = store.source_control(sid)
                    store.update_source(sid, **controls)
                    if (previous['enabled'] and not controls['enabled']) or (previous['sample_interval_seconds'] and not controls['sample_interval_seconds']):
                        pipeline.record_gap(sid)
                pipeline.clear_preview(sid)
                store.audit('camera_setup', 'saved')
            finally:
                pipeline.busy.release()
            return RedirectResponse('/cameras/' + sid + '?notice=Camera+settings+saved.', status_code=303)
        parsed = urlsplit(str(form["endpoint"]))
        try:
            address = ipaddress.ip_address(parsed.hostname or "")
            if parsed.scheme not in ("rtsp", "rtsps") or not address.is_private or address.is_loopback or address.is_link_local or address.is_multicast or address.is_unspecified or parsed.username is not None or parsed.password is not None or parsed.fragment or parsed.query or parsed.path not in ("/stream1", "/stream2") or parsed.port not in (None, 554):
                raise ValueError()
        except ValueError:
            raise ValueError("Use a literal private LAN camera IP, RTSP port 554, /stream1 or /stream2, without credentials") from None
        record = {"source_id": sid, "model": str(form["model"]), "endpoint_ref": sid + "-endpoint", "credentials_ref": sid + "-credentials", "allowed_hosts": [parsed.hostname]}
        source = camera_source(record)
        name = str(form.get('name', pipeline.sources[sid].name if not is_new else '')).strip() or source.name
        if len(name) > 128 or any(ord(c) < 32 for c in name):
            raise ValueError('Enter a camera name with 1 to 128 characters.')
        source = replace(source, name=name)
        if store.is_removed(sid):
            raise ValueError("Restore this source on Sources before editing its camera setup")
        if sid in pipeline.sources and pipeline.sources[sid].kind != "rtsp":
            raise ValueError("Source ID already belongs to another input")
        if sid not in pipeline.sources and len(pipeline.sources) >= 32:
            raise ValueError("At most 32 sources")
        record['privacy_masks'] = privacy_masks
        source = replace(source, settings={**source.settings, 'privacy_masks':privacy_masks})
        username, password = str(form.get("username", "")), str(form.get("password", ""))
        if username and (len(username) > 128 or any(ord(c) < 32 for c in username)):
            raise ValueError('Invalid camera account username')
        if password:
            if not 1 <= len(username) <= 128 or not 1 <= len(password) <= 128 or any(ord(c) < 32 for c in username + password):
                raise ValueError("Invalid camera account credentials")
        # Serialize setup with acquisition before changing protected connection details.
        # Wait off the event loop so monitoring and the rest of the UI stay responsive.
        await run_in_threadpool(pipeline.busy.acquire)
        try:
            if password:
                await run_in_threadpool(secrets.set, record["credentials_ref"], json.dumps({"username": username, "password": password}))
            else:
                saved = await run_in_threadpool(secrets.camera, record["credentials_ref"])
                if username and username != saved['username']:
                    await run_in_threadpool(secrets.set, record["credentials_ref"], json.dumps({'username':username, 'password':saved['password']}))
            await run_in_threadpool(secrets.set, record["endpoint_ref"], str(form["endpoint"]))
            store.configure(replace(settings, sources=(source,)))
            with store.connection() as db:
                db.execute("INSERT OR REPLACE INTO release_settings VALUES(?,?)", ("camera_profile:" + sid, dumps(record)))
                db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('camera_name:' + sid, dumps(name)))
                db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('camera_privacy:' + sid, dumps(privacy_masks)))
            pipeline.sources[sid] = source
            pipeline.clear_preview(sid)
            if controls is not None:
                previous = store.source_control(sid)
                store.update_source(sid, **controls)
                if (previous['enabled'] and not controls['enabled']) or (previous['sample_interval_seconds'] and not controls['sample_interval_seconds']):
                    pipeline.record_gap(sid)
            elif is_new and form.get('connect') == '1':
                store.update_source(sid, enabled=True, retain_evidence=False, sample_interval_seconds=0)
            store.audit("camera_setup", "saved_protected_references")
        finally:
            pipeline.busy.release()
        if form.get('connect') == '1':
            return await camera_test(sid, request)
        return RedirectResponse('/cameras/' + sid + '?notice=Camera+saved.+Test+the+connection+when+ready.', status_code=303) if request.url.path == '/cameras/save' else RedirectResponse("/integration?camera=" + sid + "&notice=Camera+setup+saved", status_code=303)

    @app.route('/cameras/save', methods=['POST'])
    async def camera_save(request):
        return await camera_edit(request)

    def run_camera_test(source_id):
        source = pipeline.sources[source_id]
        try:
            frame = SourceAdapters(allow_live_sources=True, timeout_seconds=settings.capture_timeout_seconds).capture(source)
            masked = preprocess(frame, source.settings.get("privacy_masks", []), preview=True)
            pipeline.remember_preview(source_id, frame.frame_id, masked.payload, frame.captured_at_utc)
            diagnostic = {"source_id": source_id, "status": "capture_success", "width": frame.width,
                          "height": frame.height, "frame_id": frame.frame_id, "captured_at_utc": frame.captured_at_utc.isoformat()}
        except ProviderError as exc:
            diagnostic = {"source_id": source_id, "status": exc.code}
        except Exception:
            diagnostic = {"source_id": source_id, "status": "capture_failed"}
        diagnostic['checked_at_utc'] = utcnow().isoformat()
        store.audit("camera_connection_test", dumps(diagnostic))
        with store.connection() as db:
            db.execute("INSERT OR REPLACE INTO release_settings VALUES(?,?)", ("camera_test:" + source_id, dumps(diagnostic)))

    @app.route("/integration/cameras/{source_id}/test", methods=["GET"])
    def camera_test_result(source_id: str, request):
        if denied(request): return denied(request)
        camera_record(source_id)
        pending = app.state.sampler.camera_test_requested(source_id)
        content = []
        if pending:
            content = [P('Camera test scheduled. It will start as soon as the current observation finishes.', cls='notice', role='status'),
                       P('This page updates automatically. No inference is requested and evidence is not retained.')]
        else:
            with store.connection() as db:
                row = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('camera_test:' + source_id,)).fetchone()
            diagnostic = json.loads(row[0]) if row else {}
            if diagnostic.get('status') == 'capture_success':
                content = [P(f"Capture succeeded: {diagnostic['width']} × {diagnostic['height']}. No inference was requested; evidence was not retained.", cls='readiness success')]
                preview = pipeline.previews.get(source_id)
                if preview and preview[0] == diagnostic.get('frame_id'):
                    content.append(evidence_image(f'/ui/preview/{source_id}/{preview[0]}', 'Privacy-masked connection preview'))
                else:
                    content.append(P('The temporary preview has expired. Test again for a new image.', cls='muted'))
            elif diagnostic:
                from vop.operator_workflow import recovery_message
                content = [P('The camera could not connect yet.', cls='readiness warning'), P(recovery_message(diagnostic['status'])),
                           A('Correct camera details', href='/cameras/' + source_id, cls='button secondary'),
                           Details(Summary('Technical details'), Pre(diagnostic['status']))]
            else:
                content = [P('This camera has not been tested yet.')]
        footer = Div(action('Test camera again', f'/integration/cameras/{source_id}/test', csrf(request)) if not pending else None,
                     A('Back to camera', href='/cameras/' + source_id, cls='button secondary'), cls='actions camera-test-actions')
        result = app.state.page('Camera connection test', request, [Div(*content, cls='camera-test-result'), footer], view='cameras')
        return HTMLResponse(to_xml(result), headers={'Refresh': '1'} if pending else {})

    @app.route("/integration/cameras/{source_id}/test", methods=["POST"])
    async def camera_test(source_id: str, request):
        if denied(request): return denied(request)
        if source_id not in pipeline.sources or pipeline.sources[source_id].kind != 'rtsp':
            raise ValueError('Choose a saved camera before testing its connection')
        if app.state.sampler.camera_test_requested(source_id) or not pipeline.busy.acquire(False):
            app.state.sampler.request_camera_test(source_id, lambda: run_camera_test(source_id))
        else:
            try:
                await run_in_threadpool(run_camera_test, source_id)
            finally:
                pipeline.busy.release()
        return RedirectResponse(f'/integration/cameras/{source_id}/test', status_code=303)
