"""Passive capture diagnostics and an explicit, bounded engine reconnect operation."""
import json
import secrets
from time import monotonic

from fasthtml.components import A, Button, Div, Form, H2, P, Section, Span, Td, Tr
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse

from vop.contracts import ProviderError, utcnow
from vop.dashboard import hidden, local_time
from vop.display import duration
from vop.inference.remote import RemoteInferenceEngine
from vop.measurements import utc
from vop.operator_workflow import recovery_message
from vop.ui_readiness import camera_dependencies, capture_dependencies


def signal(colour, label):
    return Div(Span(*(Span(cls='signal-lamp '+name+(' lit' if name==colour else '')) for name in ('red','amber','green')),
                    cls='signal-lights', aria_hidden='true'), Span(label),
               cls='diagnostic-signal '+colour, role='status', aria_label=colour.capitalize()+': '+label)


def snapshot(app):
    """Local state only: no DNS, SSH, health RPC, camera request or image retrieval."""
    pipeline, store, sampler = app.state.pipeline, app.state.store, app.state.sampler
    automatic = getattr(pipeline, 'auto_worker', None)
    failure = getattr(automatic, 'last_failure', None)
    health = getattr(pipeline.engine, 'last_health', None)
    code = failure.code if failure else (health or {}).get('error')
    code = code if isinstance(code, str) else None
    activity = pipeline.activity
    now, clock = utcnow(), monotonic()
    if activity:
        activity = {**activity, 'elapsed_seconds': max(0, (now - utc(activity['started_at_utc'])).total_seconds())}
    session = app.state.worker_session.status()
    cameras = []
    with store.connection() as db:
        for sid, source in list(pipeline.sources.items()):
            control = store.source_control(sid)
            latest = db.execute('''SELECT r.result_json FROM observations o JOIN runs r ON r.id=o.run_id
                WHERE o.source_id=? ORDER BY o.sequence DESC LIMIT 1''', (sid,)).fetchone()
            result = json.loads(latest[0]) if latest else {}
            acquisition = db.execute('SELECT last_frame_utc FROM sources WHERE id=?', (sid,)).fetchone()
            checked = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('camera_test:'+sid,)).fetchone()
            checked = json.loads(checked[0]) if checked else {}
            enabled_questions = len(store.questions(sid, active_only=True))
            saved_error = (result.get('error') or {}).get('code')
            runtime_error = sampler.source_errors.get(sid)
            error = runtime_error or saved_error
            waiting_engine = result.get('failure_stage') == 'engine' and (not runtime_error or runtime_error == saved_error) or error in (
                'worker_reconnect_failed', 'antec_name_unresolved', 'worker_auth', 'worker_unavailable',
                'worker_starting', 'gpu_capacity', 'model_load_failed', 'ssh_missing', 'worker_identity')
            problems = camera_dependencies(source)
            if not control['enabled']:
                status = 'Disabled'
            elif not enabled_questions:
                status = 'No enabled questions'
            elif control['sample_interval_seconds'] == 0 and not sampler.requested(sid):
                status = 'Monitoring paused'
            elif problems:
                status = 'Camera setup needs attention'
            elif activity and activity['source_id'] == sid:
                status = activity['stage']
            elif waiting_engine:
                status = 'Waiting for next observation' if (health or {}).get('ready') and not code else 'Waiting for engine; camera connection not checked'
            elif error:
                status = 'Last observation failed'
            elif result.get('status') == 'success':
                status = 'Monitoring' if control['sample_interval_seconds'] else 'Last observation succeeded'
            else:
                status = 'Waiting for first observation'
            light = 'amber'
            if control['enabled'] and enabled_questions and control['sample_interval_seconds']:
                if problems or error:
                    light = 'amber' if error in ('worker_starting','overloaded','recovery_busy') else 'red'
                elif result.get('status')=='success' and acquisition and acquisition[0]:
                    age=(now-utc(acquisition[0])).total_seconds()
                    light='green' if age <= max(60,control['sample_interval_seconds']*3) else 'amber'
                    if light=='amber': status='No recent observation image'
            cameras.append({'id': sid, 'name': source.name or sid, 'status': status,
                'light': light,
                'enabled': control['enabled'], 'interval': control['sample_interval_seconds'], 'questions': enabled_questions,
                'last_frame': acquisition[0] if acquisition else None, 'last_attempt': result.get('processed_at_utc'),
                'last_result': result.get('status'), 'error': error, 'failure_stage': 'engine' if waiting_engine else result.get('failure_stage'),
                'last_camera_test': {'status': checked.get('status'), 'at': checked.get('checked_at_utc') or checked.get('captured_at_utc')},
                'problems': [message for message, url in capture_dependencies(pipeline, sid)],
                'retry_seconds': max(0, sampler.deadlines.get(sid, clock) - clock),
                'failures': sampler.failures.get(sid, 0), 'observation_queued': sampler.requested(sid),
                'camera_test_queued': sampler.camera_test_requested(sid), 'camera': source.kind in ('rtsp', 'usb')})
    scheduler_running = bool(sampler.thread and sampler.thread.is_alive())
    engine_light = 'red' if code else 'green' if (health or {}).get('ready') or not isinstance(pipeline.engine,RemoteInferenceEngine) else 'amber'
    if code in ('worker_starting','overloaded','recovery_busy'): engine_light='amber'
    if engine_light=='green' and (health or {}).get('utc') and (now-utc(health['utc'])).total_seconds()>60: engine_light='amber'
    colours=[engine_light, 'amber' if pipeline.stopping else 'green' if scheduler_running else 'red', *(c['light'] for c in cameras)]
    rules_running=bool(app.state.reliable.thread and app.state.reliable.thread.is_alive())
    actions_running=bool(app.state.actions.thread and app.state.actions.thread.is_alive())
    actions_paused=app.state.actions.paused()
    colours += ['red' if app.state.reliable.last_error else 'green' if rules_running else 'amber',
                'red' if app.state.actions.last_error else 'green' if actions_running and not actions_paused else 'amber']
    if not cameras: colours.append('amber')
    overall='red' if 'red' in colours else 'amber' if 'amber' in colours else 'green'
    return {'checked_at': now.isoformat(), 'scheduler_running': scheduler_running, 'overall':overall,
        'stopping': pipeline.stopping, 'busy': pipeline.busy.locked(), 'activity': activity,
        'sampling_error': sampler.last_error, 'engine': {'name': pipeline.engine.engine_id,
            'ready_at_last_check': (health or {}).get('ready'), 'last_check': (health or {}).get('utc'),
        'error': code, 'light':engine_light, 'automatic_recovery': bool(automatic), 'session_active': session['active'],
            'session_expires': session['expires_at'].isoformat() if session.get('expires_at') else None,
            'connection_name': getattr(app.state.worker_session, 'connection_host', None)},
        'rules_error': app.state.reliable.last_error, 'actions_error': app.state.actions.last_error,
        'rules_running':rules_running,'actions_running':actions_running,'actions_paused':actions_paused,'cameras': cameras}


def install_diagnostics(app):
    pipeline, store = app.state.pipeline, app.state.store

    @app.route('/api/v1/diagnostics', methods=['GET'])
    def diagnostics_api():
        return JSONResponse(snapshot(app))

    @app.route('/diagnostics', methods=['GET'])
    def diagnostics_page(request):
        data = snapshot(app)
        csrf = request.scope['session'].setdefault('csrf', secrets.token_urlsafe(24))
        operator = request.scope.get('auth_role') == 'operator'
        engine = data['engine']
        content = [Div(signal(data['overall'], {'green':'Monitoring is working','amber':'Some monitoring is paused, waiting or unverified','red':'Needs attention — see the red indicators below'}[data['overall']]),cls='diagnostic-summary'),
            P('Green: recent success or a running service. Amber: paused, waiting or unverified. Red: a reported failure. Lights describe the checks below, not detection accuracy.', cls='muted'),
            P('These are saved settings and recent results. Opening this page does not connect to cameras or start the engine.', cls='muted'),
            Div(A('Refresh diagnostics', href='/diagnostics', cls='button secondary'),
                Form(hidden(csrf), Button('Check and reconnect engine'), method='post', action='/diagnostics/reconnect') if operator else None,
                cls='actions'), P('Reconnecting can take up to a minute while the engine loads. Refresh diagnostics to read newer results.', cls='muted'),
            P('Updated: ' + local_time(data['checked_at'], app.state.pipeline.settings.timezone_name), cls='muted'),
            Section(H2('Observation scheduler'), signal('amber' if data['stopping'] else 'green' if data['scheduler_running'] else 'red','Restarting' if data['stopping'] else 'Running' if data['scheduler_running'] else 'Stopped'),
                P('VOP is stopping or restarting.' if data['stopping'] else 'The scheduler is running.' if data['scheduler_running'] else 'The scheduler is stopped. Restart VOP to restore monitoring.'),
                P((data['activity']['stage'] + ' · ' + next((c['name'] for c in data['cameras'] if c['id']==data['activity']['source_id']), 'Camera') +
                  ' · elapsed observation time ' + duration(data['activity']['elapsed_seconds'])) if data['activity'] else 'A camera test or maintenance operation is running.' if data['busy'] else 'No observation is running at this moment. Scheduled monitoring can still be active.'),
                P(recovery_message(data['sampling_error']), cls='notice') if data['sampling_error'] else None,
                A('Open Observe', href='/', cls='button secondary')),
            Section(H2('Engine connection'), signal(engine['light'], 'Connection needs attention' if engine['light']=='red' else 'Last check or local engine ready' if engine['light']=='green' else 'Waiting or not recently checked'), P(engine['name']),
                P(recovery_message(engine['error']), cls='notice') if engine['error'] else
                P('The engine was ready at its last check.' if engine['ready_at_last_check'] else 'The engine was not ready at its last check.' if engine['last_check'] else 'The engine has not been checked in this process.'),
                P('Last check: ' + local_time(engine['last_check'], pipeline.settings.timezone_name)) if engine['last_check'] else None,
                P('Automatic reconnection is enabled.' if engine['automatic_recovery'] else 'Automatic reconnection is not enabled for this engine.'),
                P('Antec session is active.' if engine['session_active'] else 'No VOP-managed Antec session is active.'),
                P('Session ends: ' + local_time(engine['session_expires'], pipeline.settings.timezone_name)) if engine['session_expires'] else None,
                P('Connection name: ' + engine['connection_name']) if engine['connection_name'] else None,
                P('Reconnect uses the existing timed Antec session policy and can temporarily pause its other GPU workload. It does not change camera setup or request a camera frame.', cls='muted') if operator else None),
            Section(H2('Cameras'), app.state.table(['Camera / state', 'Monitoring', 'Recent activity', 'Help'], [Tr(
                Td(c['name'], signal(c['light'],c['status'])),
                Td('Enabled' if c['enabled'] else 'Disabled', P('Target interval: '+duration(c['interval']) if c['interval'] else 'Monitoring paused'),
                   P(str(c['questions'])+' enabled questions'), P('Retry in '+duration(c['retry_seconds'])) if c['failures'] else None,
                   P('Camera test queued') if c['camera_test_queued'] else P('Observation queued') if c['observation_queued'] else None),
                Td('Last observation image: '+local_time(c['last_frame'], pipeline.settings.timezone_name) if c['last_frame'] else 'No observation image acquired yet',
                   P('Last attempt: '+local_time(c['last_attempt'], pipeline.settings.timezone_name)) if c['last_attempt'] else None,
                   P('Last camera-only test: ' + ('succeeded' if c['last_camera_test']['status']=='capture_success' else 'not successful') +
                     (' · ' + local_time(c['last_camera_test']['at'], pipeline.settings.timezone_name) if c['last_camera_test']['at'] else ' · time not recorded')) if c['last_camera_test']['status'] else None,
                   P(recovery_message(c['error'])) if c['error'] else None),
                Td(*(P(message) for message in c['problems']),
                   Div(A('Camera settings', href='/cameras/'+c['id'], cls='button secondary'),
                       Form(hidden(csrf), Button('Test camera connection'), method='post', action='/integration/cameras/'+c['id']+'/test') if c['camera'] else None,
                       cls='actions') if operator else None)) for c in data['cameras']])),
            Section(H2('Other services'), signal('red' if data['rules_error'] else 'green' if data['rules_running'] else 'amber','Notification rules need attention' if data['rules_error'] else 'Notification service running' if data['rules_running'] else 'Notification service is stopped'),
                    A('Notification settings',href='/release?tab=rules',cls='button secondary') if operator and data['rules_error'] else None,
                    signal('red' if data['actions_error'] else 'green' if data['actions_running'] and not data['actions_paused'] else 'amber','Actions need attention' if data['actions_error'] else 'Automations paused' if data['actions_paused'] else 'Action service running' if data['actions_running'] else 'Action service is stopped'),
                    A('Action settings',href='/actions',cls='button secondary') if operator and data['actions_error'] else None)]
        return app.state.page('Diagnostics', request, content, view='diagnostics', notice=request.query_params.get('notice'))

    @app.route('/diagnostics/reconnect', methods=['POST'])
    async def reconnect(request):
        def check():
            with pipeline.busy:
                automatic = getattr(pipeline, 'auto_worker', None)
                if automatic:
                    automatic.ensure_ready()
                if isinstance(pipeline.engine, RemoteInferenceEngine):
                    return pipeline.engine.health().get('ready', False)
                return True
        ready = False
        try:
            ready = await run_in_threadpool(check)
            message = 'Engine ready. Scheduled monitoring will resume automatically.' if ready else 'The engine is not ready. Check the details below.'
            if ready:
                app.state.sampler.deadlines.clear()
                app.state.sampler.last_error = None
        except ProviderError as error:
            message = recovery_message(error.code)
        store.audit('diagnostics_reconnect', 'ready' if ready else 'needs_attention')
        from urllib.parse import urlencode
        return RedirectResponse('/diagnostics?' + urlencode({'notice': message}), status_code=303)
