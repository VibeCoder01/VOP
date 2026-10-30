"""Actions, sentence-style automations and read-only activity using native forms."""
import json
import secrets

from fasthtml.components import A, Button, Details, Div, Form, H2, H3, Input, Label, Option, P, Pre, Select, Summary, Td, Tr
from fasthtml.core import to_xml
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from vop.actions import KINDS, TRIGGERS, beep_wav
from vop.audio_recording import audio_editor, SCRIPT as AUDIO_SCRIPT
from vop.dashboard import badge, field, hidden, local_time
from vop.display import duration, duration_input


SCRIPT = r"""(() => {
  const activity = document.querySelector('[data-action-activity]');
  let activityBusy = false, lastActivity = '';
  if (activity) setInterval(async () => {
    if (activityBusy || document.hidden) return;
    activityBusy = true;
    try {
      const response = await fetch('/activity/rows', {signal:AbortSignal.timeout(5000)});
      if (!response.ok || response.redirected) return;
      const html = await response.text();
      if (html !== lastActivity) { activity.innerHTML = html; lastActivity = html; }
    } catch (_) {} finally { activityBusy = false; }
  }, 1000);
  const enable = document.querySelector('[data-enable-sound]');
  if (!enable) return;
  const csrf = enable.dataset.csrf;
  let active = false, busy = false, current;
  const client = crypto.randomUUID();
  const post = (url, fields) => fetch(url, {method:'POST', credentials:'same-origin', signal:AbortSignal.timeout(5000),
    headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:new URLSearchParams({csrf, ...fields})});
  enable.addEventListener('click', async () => {
    if (active) { active = false; sessionStorage.removeItem('vop-sound'); if (current) current.pause(); enable.textContent = 'Enable sound'; return; }
    try {
      // The deliberate click unlocks browser audio; metadata polling never changes this choice.
      current = new Audio('/actions/beep.wav'); current.volume = 0.3;
      await current.play();
      active = true; sessionStorage.setItem('vop-sound','on'); enable.textContent = 'Disable sound';
    } catch (_) { enable.textContent = 'Enable sound — check browser audio'; }
  });
  if (sessionStorage.getItem('vop-sound') === 'on') {
    current = new Audio('/actions/beep.wav'); current.volume = 0;
    current.play().then(() => {active = true; enable.textContent = 'Disable sound';}).catch(() => {});
  }
  setInterval(async () => {
    if (!active || busy || document.hidden) return;
    busy = true;
    try {
      const response = await post('/actions/sound/claim', {client});
      if (!response.ok) { active = false; enable.textContent = 'Enable sound'; return; }
      const job = await response.json();
      if (!job.id) return;
      if (!active) { await post('/actions/sound/ack', {client, id:job.id, played:'no'}); return; }
      let played = false;
      try {
        const url = job.config.kind === 'beep' ? '/actions/beep.wav' : '/actions/audio/' + encodeURIComponent(job.config.id) + '?digest=' + encodeURIComponent(job.config.audio_digest);
        current = new Audio(url); current.volume = job.config.volume / 100;
        await current.play();
        played = await new Promise(resolve => {
          const timeout = setTimeout(() => { current.pause(); resolve(false); }, 65000);
          current.onended = () => { clearTimeout(timeout); resolve(true); };
          current.onerror = () => { clearTimeout(timeout); resolve(false); };
        });
      } catch (_) {}
      await post('/actions/sound/ack', {client, id:job.id, played:played ? 'yes' : 'no'});
    } catch (_) { /* Keep audio enabled; a later poll can reconnect. */ }
    finally { busy = false; }
  }, 500);
})();"""


def install_actions(app, actions):
    store, pipeline = actions.store, actions.pipeline

    def csrf(request):
        return request.scope['session'].setdefault('csrf', secrets.token_urlsafe(24))

    def choose(label, name, options, selected='', **kwargs):
        return Div(Label(label, _for=name), Select(*(Option(label, value=value, selected=str(selected) == str(value))
                   for value, label in options), name=name, id=name, **kwargs), cls='field')

    def back(label, url):
        return A(label, href=url, cls='button secondary')

    def page(title, request, content, view):
        return app.state.page(title, request, content, view=view, notice=request.query_params.get('notice'))

    @app.route('/ui/actions.js', methods=['GET'])
    def script():
        return Response(SCRIPT, media_type='application/javascript')

    @app.route('/ui/audio-editor.js', methods=['GET'])
    def audio_script():
        return Response(AUDIO_SCRIPT, media_type='application/javascript')

    @app.route('/actions', methods=['GET'])
    def listing(request):
        token = csrf(request)
        rows = []
        for action in actions.definitions():
            rows.append(Tr(Td(action['name']), Td(KINDS[action['kind']]), Td(actions.dependency(action) or 'Ready to test'),
                Td(Div(back('Edit action', '/actions/edit?id=' + action['id']),
                    Form(hidden(token),
                         Label('Camera for image test',Select(Option('Choose a camera',value=''),*(Option(s.name or sid,value=sid) for sid,s in pipeline.sources.items()),name='source_id',required=True)) if action['kind']=='image' else None,
                         Button('Test action'), method='post', action='/actions/' + action['id'] + '/test'),
                    back('Delete…', '/actions/' + action['id'] + '/delete'), cls='actions'))))
        return page('Actions', request, [P('Create an action here. Connect it to a camera and question in Automations.'),
            Div(back('Add action', '/actions/edit'), back('Automations', '/automations'), back('Setup help', '/actions/help'), cls='actions'),
            app.state.table(['Name', 'Type', 'Setup', 'Controls'], rows) if rows else P('No actions yet. Add a beep to start.'),
            P('Test action performs the real action. Save image keeps the chosen camera’s latest observation image; it does not take a new capture. Saving settings and simulation do not contact devices or send messages.', cls='muted')], 'actions')

    @app.route('/actions/help', methods=['GET'])
    def help_page(request):
        return page('Action setup', request, [H2('Sound'), P('Choose This browser or The VOP computer. Select Enable sound once in each browser tab that should play queued sounds. The choice is remembered as you navigate in that tab; your browser may require another click after a reload.'),
            H2('Tapo L530 and H100'), P('Use the device’s LAN address and your Tapo account. This is separate from the camera RTSP account. Save, then Check device. Checking only reads device information.'),
            P('If Tapo support is missing, run this from the VOP folder on the computer running the dashboard, then restart VOP:'),
            Pre('.\\.venv\\Scripts\\python.exe -m pip install ".[tapo]"'),
            H2('Save image'), P('Connect this action to a question in Automations. It saves the privacy-masked source image for the observation that caused the action, in Individual Observations, even when automatic image saving is off. It uses the same image format, retention and deletion rules. It does not save a separate per-question crop or turn on automatic saving.'),
            P('The matching image must still be in the temporary preview or already saved. Activity reports a missing image; it never substitutes another frame. Manual tests need a camera and an existing observation.'),
            H2('Email'), P('Email is text only: images are not attached, including when a Save image action is linked to the same automation. Use your provider’s SMTP SSL server, normally port 465, and an app password if required. VOP does not support STARTTLS-only servers in this release.'),
            H2('Text messages'), P('Create a Twilio SMS sender and API key. Enter its Account SID, API key SID and secret, sender and recipient in the protected fields. Trial accounts may require recipient verification. Provider charges apply.'),
            H2('If an action fails'), P('Open Activity, read the result, then Edit action or Check device. A blocked action needs corrected setup. An uncertain action may already have happened: check the destination before using Test action. Old actions are not replayed.'),
            back('Back to Actions', '/actions')], 'actions')

    @app.route('/actions/edit', methods=['GET'])
    def editor(request):
        aid = request.query_params.get('id', '')
        existing = next((a for a in actions.definitions() if a['id'] == aid), {})
        if aid and not existing:
            raise ValueError('This action no longer exists. Return to Actions.')
        kind = existing.get('kind', request.query_params.get('kind', 'beep'))
        if kind not in KINDS:
            raise ValueError('Choose an action type.')
        content = [Form(choose('Action type', 'kind', list(KINDS.items()), kind), Button('Choose type'), method='get', action='/actions/edit', cls='filters')] if not existing else []
        fields = [hidden(csrf(request)), Input(type='hidden', name='id', value=aid), Input(type='hidden', name='kind', value=kind),
                  field('Name', 'name', existing.get('name', ''), required=True, maxlength=100)]
        if kind in ('beep', 'audio'):
            fields += [choose('Play sound on', 'location', [('browser', 'This browser'), ('computer', 'The VOP computer')], existing.get('location', 'browser')),
                P('Browser sound needs an open VOP page and Enable sound. Computer sound plays on the machine running the dashboard, independently of the inference engine.', cls='muted'),
                field('Volume (0–100)', 'volume', existing.get('volume', 60), type='number', min=0, max=100, required=True)]
        if kind == 'audio':
            fields += [audio_editor(saved=bool(existing))]
        if kind == 'image':
            fields += [P('Save the triggering observation’s privacy-masked source image in Individual Observations. Camera and question are chosen in the automation.'),
                       P('Works when automatic image saving is off. No new camera capture is taken. The image follows normal retention and deletion rules. If it is no longer available, Activity explains why nothing was saved.',cls='muted'),
                       P('This action does not attach images to email. Email actions currently send text only.',cls='muted')]
        if kind == 'tapo':
            fields += [field('Light LAN address', 'address', existing.get('address', ''), required=True),
                       choose('Operation', 'operation', [('on', 'Turn on'), ('off', 'Turn off'), ('flash', 'Flash, then turn off')], existing.get('operation', 'on')),
                       field('Flash duration (H:M:S, 00:00:02–00:00:20)', 'seconds', duration(existing.get('seconds', 6)), required=True),
                       field('Brightness (1–100; 0 keeps the current setting)', 'brightness', existing.get('brightness', 0), type='number', min=0, max=100),
                       field('Colour (#RRGGBB; blank keeps the current colour)', 'colour', existing.get('colour', ''), pattern='#[0-9a-fA-F]{6}'),
                       P('Flash uses one-second on/off pulses and finishes off. It does not restore a previous light setting. Requires optional python-kasa support and a compatible light; see docs/actions.md.', cls='muted')]
        if kind == 'hub':
            fields += [field('Hub LAN address', 'address', existing.get('address', ''), required=True),
                       choose('Volume', 'volume', [('low', 'Low'), ('normal', 'Normal'), ('high', 'High')], existing.get('volume', 'low')),
                       field('Sound duration (H:M:S, 00:00:01–00:00:30)', 'seconds', duration(existing.get('seconds', 3)), required=True),
                       choose('Sound', 'sound', [('', 'Use the hub’s current sound')] + [(v, v) for v in actions.hub_sounds(aid)], existing.get('sound', '')),
                       P('Save the address and protected account first, then Check device to load its available sounds. Checking does not play a sound. Test action does.', cls='muted')]
        if kind == 'email':
            fields += [field('SMTP server (encrypted connection)', 'host', existing.get('host', ''), required=True),
                       field('SMTP SSL port', 'port', existing.get('port', 465), type='number', min=1, max=65535, required=True),
                       field('Subject', 'subject', existing.get('subject', 'VOP: {camera} — {question}'), required=True)]
        if kind in ('email', 'sms'):
            fields += [field('Message', 'message', existing.get('message', '{camera}: {question} — {trigger}'), required=True, maxlength=1000),
                       P('Use {camera}, {question}, {trigger} and {automation}. Messages contain text only, with no image attachments.', cls='muted')]
        protected = {'tapo': [('username', 'Tapo account email'), ('password', 'Tapo account password')],
                     'email': [('username', 'SMTP username'), ('password', 'SMTP password or app password'), ('from', 'Sender email'), ('to', 'Recipient email')],
                     'sms': [('account', 'Twilio Account SID (AC…)'), ('username', 'Twilio API key SID (SK…)'), ('password', 'Twilio API key secret'), ('from', 'Sender number (+country code)'), ('to', 'Recipient number (+country code)')]}
        protected['hub'] = protected['tapo']
        if kind in protected:
            fields += [H3('Protected connection details'), P('Enter all fields to replace these details. Leave all fields blank to keep saved details. Values are protected by the operating system and are not displayed.'),
                       *(field(label, 'protected_' + key, type='password' if key == 'password' else 'text', autocomplete='new-password' if key == 'password' else 'off') for key, label in protected[kind])]
        if kind == 'sms':
            fields += [P('Twilio requires a configured SMS sender and may restrict trial recipients. Messages can incur charges. Accepted means received by the provider, not confirmed on the phone.', cls='notice')]
        fields += [Div(Button('Save action'), back('Cancel', '/actions'), cls='actions')]
        if existing and kind in ('hub', 'tapo'):
            content += [Form(hidden(csrf(request)), Button('Check device'), method='post', action='/actions/' + aid + '/check')]
        content += [H2(KINDS[kind]), Form(*fields, action='/actions/save', method='post', cls='editor')]
        return page('Edit action' if existing else 'Add action', request, content, 'actions')

    @app.route('/actions/save', methods=['POST'])
    async def save(request):
        form = await request.form()
        body = {k: str(form.get(k, '')) for k in ('id', 'kind', 'name', 'location', 'address', 'operation', 'host', 'subject', 'message', 'colour', 'sound')}
        body.update(volume=str(form.get('volume', 'low')) if body['kind'] == 'hub' else float(form.get('volume', 60)),
                    brightness=float(form.get('brightness', 0)), seconds=duration_input(str(form.get('seconds', '00:00:06'))), port=int(form.get('port', 465)))
        protected = {k.removeprefix('protected_'): str(v) for k, v in form.items() if k.startswith('protected_') and str(v)}
        await run_in_threadpool(actions.save_action, body, protected=protected or None, audio=str(form.get('audio_data')) if form.get('audio_data') else None)
        return RedirectResponse('/actions?notice=Action+saved', status_code=303)

    @app.route('/actions/{aid}/test', methods=['POST'])
    async def test(aid: str, request):
        form = await request.form()
        await run_in_threadpool(actions.test, aid, str(form.get('source_id','')) or None)
        return RedirectResponse('/activity?notice=Action+test+requested', status_code=303)

    @app.route('/actions/{aid}/check', methods=['POST'])
    async def check(aid: str, request):
        await run_in_threadpool(actions.check_device, aid)
        return RedirectResponse('/actions/edit?id=' + aid + '&notice=Device+checked.+No+sound+or+light+change+was+requested.', status_code=303)

    @app.route('/automations', methods=['GET'])
    def automation_list(request):
        names = {a['id']: a['name'] for a in actions.definitions()}
        rows = [Tr(Td(m['name']), Td(pipeline.sources[m['source_id']].name if m['source_id'] in pipeline.sources else m['source_id'],
                    P(TRIGGERS[m['trigger']])), Td(', '.join(names.get(a, 'Deleted action') for a in m['actions'])),
                    Td('Enabled' if m['enabled'] else 'Paused', *(P(issue, cls='muted') for issue in actions.automation_dependencies(m))), Td(Div(back('Edit', '/automations/edit?id=' + m['id']),
                    back('Delete…', '/automations/' + m['id'] + '/delete'), cls='actions'))) for m in actions.automations()]
        return page('Automations', request, [P('Connect confirmed episodes and answer changes to named actions.'),
            Div(back('Add automation', '/automations/edit'), back('Actions', '/actions'), cls='actions'),
            app.state.table(['Name', 'When', 'Then', 'Status', 'Controls'], rows) if rows else P('No automations yet.'),
            P('Automations are paused globally.' if actions.paused() else 'Automations are running. Individual paused automations stay paused.', cls='notice'),
            Form(hidden(csrf(request)), Input(type='hidden', name='paused', value='no' if actions.paused() else 'yes'),
                 Button('Resume automations' if actions.paused() else 'Pause automations'), method='post', action='/automations/pause')], 'automations')

    @app.route('/automations/edit', methods=['GET'])
    def automation_editor(request):
        mid = request.query_params.get('id', '')
        m = next((m for m in actions.automations() if m['id'] == mid), {})
        if mid and not m:
            raise ValueError('This automation no longer exists.')
        conditions = [(sid + '/' + r['spec'].question_id, source.name + ' — ' + r['spec'].text, r['spec'])
                      for sid, source in pipeline.sources.items() for r in store.questions(sid, active_only=True)]
        selected = request.query_params.get('condition', m.get('source_id', '') + '/' + m.get('question_id', ''))
        current = next((c for c in conditions if c[0] == selected), conditions[0] if conditions else None)
        choices = actions.definitions()
        if not current or not choices:
            return page('Add automation', request, [P('Add an enabled camera question and at least one action first.', cls='notice'),
                        Div(back('Actions', '/actions'), back('Questions', '/?view=questions'), cls='actions')], 'automations')
        q = current[2]
        options = list(TRIGGERS.items()) if q.kind == 'binary' else [(k,v) for k,v in TRIGGERS.items() if k not in ('start', 'end', 'duration')]
        values = [('true', 'Yes'), ('false', 'No')] if q.kind == 'binary' else [(json.dumps(name), name + ' — ' + description) for name, description in q.choices] if q.kind == 'choice' else [(str(i), f'{label} ({i})') for i, label in enumerate(q.levels)]
        trigger = request.query_params.get('trigger', m.get('trigger', options[0][0]))
        if trigger not in dict(options):
            trigger = options[0][0]
        chooser = Form(Input(type='hidden', name='id', value=mid), choose('Camera and question', 'condition', [(c[0],c[1]) for c in conditions], current[0]),
                       choose('When', 'trigger', options, trigger), Button('Choose trigger'), method='get', action='/automations/edit', cls='filters')
        fields = [hidden(csrf(request)), Input(type='hidden', name='id', value=mid), Input(type='hidden', name='condition', value=current[0]),
                  Input(type='hidden', name='trigger', value=trigger), field('Name', 'name', m.get('name', ''), required=True, maxlength=100),
                  H2('When'), P(current[1] + ' — ' + TRIGGERS[trigger])]
        if trigger == 'value':
            fields += [choose('Answer', 'value', values, json.dumps(m.get('value', True if q.kind == 'binary' else q.choices[0][0] if q.kind == 'choice' else 0)))]
            if q.kind == 'ordinal':
                fields += [choose('Position compared with this level', 'comparison', [('at_least', 'At or above'), ('at_most', 'At or below')], m.get('comparison', 'at_least')),
                           P('Ordinal answers can fall between levels. This compares the returned number with the selected level’s number.', cls='muted')]
        if trigger == 'duration':
            fields += [field('Confirmed active duration (H:M:S)', 'seconds', duration(m.get('seconds', 30)), required=True)]
        fields += [H2('Then'), Div(*(Label(Input(type='checkbox', name='actions', value=a['id'], checked=a['id'] in m.get('actions', [])), ' ', a['name']) for a in choices), cls='source-selectors'),
                   P('Actions run independently in the background. Their results appear in Activity.', cls='muted'),
                   H2('Limits'), field('Minimum time between activations (H:M:S)', 'cooldown', duration(m.get('cooldown', 60)), required=True),
                   field('Maximum activations per hour', 'max_hour', m.get('max_hour', 10), type='number', min=1, max=100, required=True),
                   Details(Summary('Daily schedule'), P('Leave both times empty to run at any time. Uses workspace timezone: ' + actions.zone),
                           field('From', 'start', m.get('start', ''), type='time'), field('Until', 'end', m.get('end', ''), type='time')),
                   choose('Status', 'enabled', [('', 'Paused'), ('yes', 'Enabled')], 'yes' if m.get('enabled') else ''),
                   P('Only new transitions run actions. Saving, resuming and restarting do not replay old episodes. Missing observations do not mean an episode ended.', cls='muted'),
                   Div(Button('Save automation'), Button('Preview automation', formaction='/automations/preview'), back('Cancel', '/automations'), cls='actions')]
        return page('Edit automation' if m else 'Add automation', request, [P('The original camera or question is unavailable. Choose its replacement before saving.', cls='notice') if m and current[0] != selected else None,
                    chooser, Form(*fields, method='post', action='/automations/save', cls='editor')], 'automations')

    def automation_body(form):
        sid, qid = str(form.get('condition', '')).split('/', 1)
        return {'id': str(form.get('id', '')), 'name': str(form.get('name', '')), 'source_id': sid, 'question_id': qid,
                'trigger': str(form.get('trigger')), 'value': json.loads(str(form.get('value', 'null'))), 'actions': list(form.getlist('actions')),
                'seconds': duration_input(str(form.get('seconds', '00:00:30'))), 'cooldown': duration_input(str(form.get('cooldown', '00:01:00'))),
                'max_hour': int(form.get('max_hour', 10)), 'enabled': form.get('enabled') == 'yes',
                'start': str(form.get('start', '')), 'end': str(form.get('end', '')),
                **({'comparison': str(form['comparison'])} if form.get('comparison') else {})}

    @app.route('/automations/save', methods=['POST'])
    async def save_automation(request):
        await run_in_threadpool(actions.save_automation, automation_body(await request.form()))
        return RedirectResponse('/automations?notice=Automation+saved', status_code=303)

    @app.route('/automations/preview', methods=['POST'])
    async def preview(request):
        form = await request.form()
        body = await run_in_threadpool(actions.validate_automation, automation_body(form))
        names = {a['id']: a['name'] for a in actions.definitions()}
        source = pipeline.sources.get(body['source_id'])
        question = next((r['spec'] for r in store.questions(body['source_id']) if r['spec'].question_id == body['question_id']), None)
        if not source or not question or body['trigger'] not in TRIGGERS or not body['actions'] or set(body['actions']) - set(names):
            raise ValueError('Choose an available camera, question, trigger and actions.')
        summary = f"When {source.name} — {question.text}: {TRIGGERS[body['trigger']]}, run " + ', '.join(names[a] for a in body['actions']) + '.'
        if body['trigger'] == 'value':
            value = body['value']
            label = question.levels[value] + f' ({value})' if question.kind == 'ordinal' and type(value) is int and 0 <= value < len(question.levels) else 'Yes' if value is True else 'No' if value is False else str(value)
            summary += ' Answer: ' + ('at or above ' if body.get('comparison') == 'at_least' else 'at or below ' if body.get('comparison') == 'at_most' else '') + label + '.'
        if body['trigger'] == 'duration':
            summary += ' Confirmed active duration: ' + duration(body['seconds']) + '.'
        details = [P(summary), P('Cooldown: ' + duration(body['cooldown']) + f". Maximum {body['max_hour']} activations per hour."),
                   P('Schedule: ' + (body['start'] + '–' + body['end'] + ' (' + actions.zone + ')' if body['start'] else 'Any time.')),
                   P('Preview only. No action has run and nothing has been saved.', cls='notice')]
        for aid in body['actions']:
            config = next(a for a in actions.definitions() if a['id'] == aid)
            details.append(P(config['name'] + ': ' + (actions.dependency(config) or 'Ready to test; the connection has not been checked.')))
        details += [Form(*(Input(type='hidden', name=k, value=str(v)) for k, v in form.multi_items()), Button('Save automation'), method='post', action='/automations/save'),
                    back('Cancel', '/automations')]
        return page('Preview automation', request, details, 'automations')

    @app.route('/automations/pause', methods=['POST'])
    async def pause(request):
        await run_in_threadpool(actions.pause, (await request.form()).get('paused') == 'yes')
        return RedirectResponse('/activity?notice=Automation+status+updated', status_code=303)

    def deletion(request, kind, key):
        definitions = actions.definitions() if kind == 'action' else actions.automations()
        item = next((a for a in definitions if a['id'] == key), None)
        if not item:
            raise ValueError('This item no longer exists.')
        url = '/actions/' if kind == 'action' else '/automations/'
        return page('Delete ' + kind, request, [H2(item['name']), P('Delete this configuration and cancel its waiting actions. Activity records are kept.'),
                    Form(hidden(csrf(request)), Button('Delete permanently', cls='danger'), method='post', action=url + key + '/delete'),
                    back('Cancel', '/actions' if kind == 'action' else '/automations')], 'actions' if kind == 'action' else 'automations')

    @app.route('/actions/{aid}/delete', methods=['GET'])
    def action_delete(aid: str, request):
        return deletion(request, 'action', aid)

    @app.route('/automations/{mid}/delete', methods=['GET'])
    def automation_delete(mid: str, request):
        return deletion(request, 'automation', mid)

    @app.route('/actions/{aid}/delete', methods=['POST'])
    async def action_delete_post(aid: str, request):
        await run_in_threadpool(actions.delete, 'action', aid)
        return RedirectResponse('/actions?notice=Action+deleted', status_code=303)

    @app.route('/automations/{mid}/delete', methods=['POST'])
    async def automation_delete_post(mid: str, request):
        await run_in_threadpool(actions.delete, 'automation', mid)
        return RedirectResponse('/automations?notice=Automation+deleted', status_code=303)

    def activity_rows(request):
        current_actions = {a['id'] for a in actions.definitions()}
        return app.state.table(['Time', 'Automation / action', 'Result', 'Details'], [Tr(Td(local_time(j['created'], actions.zone)),
            Td(j['context'].get('automation', ''), P(j['configuration']['name'])), Td(badge(j['status'])),
            Td(j['detail'] or 'Waiting to run.', P(A('Edit action', href='/actions/edit?id=' + j['action_id']) if j['action_id'] in current_actions else 'Action deleted') if request.scope.get('auth_role') == 'operator' else None)) for j in actions.jobs()])

    @app.route('/activity/rows', methods=['GET'])
    def rows(request):
        return Response(to_xml(activity_rows(request)), media_type='text/html')

    @app.route('/activity', methods=['GET'])
    def activity(request):
        return page('Activity', request, [P('Automations paused.' if actions.paused() else 'Automations running.', cls='notice'),
            P(actions.last_error, cls='notice') if actions.last_error else None,
            Form(hidden(csrf(request)), Input(type='hidden', name='paused', value='no' if actions.paused() else 'yes'),
                 Button('Resume automations' if actions.paused() else 'Pause automations'), method='post', action='/automations/pause') if request.scope.get('auth_role') == 'operator' else None,
            Div(back('Refresh activity', '/activity'), cls='actions'),
            Div(activity_rows(request), data_action_activity='', aria_live='polite'),
            P('Latest 100 actions. Accepted means the provider accepted the message; final delivery is not confirmed. Uncertain actions are not resent automatically.', cls='muted')], 'activity')

    @app.route('/actions/beep.wav', methods=['GET'])
    def beep():
        return Response(beep_wav(100), media_type='audio/wav')

    @app.route('/actions/audio/{aid}', methods=['GET'])
    def audio(aid: str, request):
        payload = actions.audio(aid, request.query_params.get('digest'))
        return Response(payload or b'', media_type='audio/wav', status_code=200 if payload else 404)

    @app.route('/actions/sound/claim', methods=['POST'])
    async def claim(request):
        client = str((await request.form()).get('client', ''))
        if not client or len(client) > 64:
            raise ValueError('Reload the page and enable sound.')
        return JSONResponse(await run_in_threadpool(actions.claim_sound, client) or {})

    @app.route('/actions/sound/ack', methods=['POST'])
    async def ack(request):
        form = await request.form()
        await run_in_threadpool(actions.acknowledge_sound, str(form.get('id', '')), str(form.get('client', '')), form.get('played') == 'yes')
        return JSONResponse({'ok': True})
