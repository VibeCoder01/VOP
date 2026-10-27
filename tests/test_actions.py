"""Offline action/automation acceptance. All device and message delivery is intercepted."""
import asyncio
import base64
from datetime import timedelta
from io import BytesIO
import json
from types import SimpleNamespace
from threading import Event
import wave

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_phase3_release import app, HEADERS, TOKEN, VIEWER, SID, QID, samples
from vop.actions import Actions, beep_wav, scale_wav, tapo, wav_bytes
from vop.contracts import utcnow


class Vault:
    def __init__(self): self.values = {}
    def get(self, key): return self.values[key]
    def set(self, key, value): self.values[key] = value


def sound(actions, aid='bell', location='browser'):
    return actions.save_action({'id': aid, 'kind': 'beep', 'name': 'Front door bell', 'location': location, 'volume': 50})


def automation(actions, **changes):
    body = {'id': 'front-door', 'name': 'Visitor at door', 'source_id': SID, 'question_id': QID,
            'trigger': 'start', 'actions': ['bell'], 'enabled': True, 'cooldown': 60}
    body.update(changes)
    actions.save_automation(body)
    return body


def summary(now, *, state='INACTIVE', value=False, events=()):
    return {'state': state, 'latest_value': value, 'events': list(events),
            'last_observation_id': None, 'last_sample_at_utc': now.isoformat()}


def event(now, eid='episode-1', **changes):
    return {'id': eid, 'started_at_utc': now.isoformat(), 'ended_at_utc': None, 'status': 'open',
            'estimated_observed_seconds': 0, **changes}


def test_episode_dedup_cooldown_pause_and_restart(app, monkeypatch):
    actions = app.state.actions
    sound(actions)
    automation(actions)
    now = utcnow() + timedelta(seconds=1)
    current = summary(now)
    monkeypatch.setattr(actions, 'summary', lambda *a, **kw: current)
    actions.evaluate(now)
    current.update(state='ACTIVE', latest_value=True, events=[event(now + timedelta(seconds=1))])
    actions.evaluate(now + timedelta(seconds=2))
    actions.evaluate(now + timedelta(seconds=3))
    assert len(actions.jobs()) == 1 and actions.jobs()[0]['status'] == 'queued'
    # Another episode within cooldown is recorded as suppressed, never deferred into a late action.
    current['events'].append(event(now + timedelta(seconds=4), 'episode-2'))
    actions.evaluate(now + timedelta(seconds=5))
    assert len(actions.jobs()) == 2 and actions.jobs()[0]['status'] == 'suppressed'
    actions.pause(True)
    assert actions.jobs()[1]['status'] == 'cancelled'
    actions.pause(False)
    actions.evaluate(now + timedelta(seconds=70))
    assert len(actions.jobs()) == 2  # Resume baselines; no old event replay.
    # Restart expires pending tests and marks interrupted sends uncertain.
    actions.test('bell')
    with actions.store.connection() as db:
        db.execute("UPDATE action_jobs SET status='sending' WHERE id LIKE 'test-%'")
    actions.stop_event.set()
    monkeypatch.setattr(actions, 'loop', lambda: None)
    actions.start()
    actions.stop()
    assert next(j for j in actions.jobs() if j['id'].startswith('test-'))['status'] == 'uncertain'
    fresh = Actions(actions.store, actions.pipeline)
    assert len(fresh.automations()) == 1 and len(fresh.definitions()) == 1


def test_unknown_not_end_duration_not_extrapolated_and_end_once(app, monkeypatch):
    actions = app.state.actions
    sound(actions)
    automation(actions, trigger='duration', seconds=10, cooldown=0)
    now = utcnow() + timedelta(seconds=1)
    e = event(now + timedelta(seconds=1), estimated_observed_seconds=0)
    current = summary(now)
    monkeypatch.setattr(actions, 'summary', lambda *a, **kw: current)
    actions.evaluate(now)
    current.update(state='ACTIVE', events=[e])
    actions.evaluate(now + timedelta(hours=1))
    assert actions.jobs() == []
    current['state'] = 'UNKNOWN'
    e['estimated_observed_seconds'] = 11
    actions.evaluate(now + timedelta(hours=1, seconds=1))
    assert actions.jobs() == []
    current['state'] = 'ACTIVE'
    actions.evaluate(now + timedelta(hours=1, seconds=2))
    assert len(actions.jobs()) == 1
    automation(actions, trigger='end', cooldown=0)
    actions.evaluate(now + timedelta(hours=2))
    current['state'] = 'UNKNOWN'
    e.update(status='interrupted', ended_at_utc=None)
    actions.evaluate(now + timedelta(hours=2, seconds=1))
    assert len(actions.jobs()) == 1
    current['state'] = 'INACTIVE'
    e.update(status='closed', ended_at_utc=(now + timedelta(hours=2, seconds=2)).isoformat())
    actions.evaluate(now + timedelta(hours=2, seconds=3))
    actions.evaluate(now + timedelta(hours=2, seconds=4))
    assert len(actions.jobs()) == 2


def test_value_and_unavailable_transitions_schedule_hour_limit(app, monkeypatch):
    actions = app.state.actions
    with actions.store.connection() as db:
        db.execute('UPDATE source_controls SET sample_interval_seconds=30 WHERE source_id=?', (SID,))
    sound(actions)
    automation(actions, trigger='value', value=True, cooldown=0, max_hour=1)
    now = utcnow() + timedelta(seconds=1)
    current = summary(now)
    current['last_observation_id'] = 'obs1'
    monkeypatch.setattr(actions, 'summary', lambda *a, **kw: current)
    monkeypatch.setattr(actions.store, 'observation', lambda *a: {'run': {'synthetic': False}})
    actions.evaluate(now)
    current.update(state='ACTIVE', latest_value=True)
    actions.evaluate(now + timedelta(seconds=1))
    current.update(state='UNKNOWN', latest_value=None)
    actions.evaluate(now + timedelta(seconds=2))
    current.update(state='ACTIVE', latest_value=True)
    actions.evaluate(now + timedelta(seconds=3))
    assert len(actions.jobs()) == 1  # Unknown does not re-arm a matching answer.
    current.update(state='INACTIVE', latest_value=False)
    actions.evaluate(now + timedelta(seconds=4))
    current.update(state='ACTIVE', latest_value=True, last_observation_id='obs2')
    actions.evaluate(now + timedelta(seconds=5))
    assert actions.jobs()[0]['detail'] == 'Hourly limit reached.'
    automation(actions, trigger='unavailable', cooldown=0)
    actions.evaluate(now + timedelta(seconds=6))
    current.update(state='UNKNOWN', latest_value=None)
    actions.evaluate(now + timedelta(seconds=7))
    assert len(actions.jobs()) == 3
    # Closed schedule suppresses rather than queues an obsolete event.
    local = (now + timedelta(seconds=10)).astimezone(__import__('zoneinfo').ZoneInfo(actions.zone))
    end = local.replace(hour=(local.hour + 2) % 24).strftime('%H:%M')
    start = local.replace(hour=(local.hour + 1) % 24).strftime('%H:%M')
    automation(actions, trigger='recovered', start=start, end=end)
    actions.evaluate(now + timedelta(seconds=8))
    current.update(state='ACTIVE', latest_value=True)
    actions.evaluate(now + timedelta(seconds=10))
    assert actions.jobs()[0]['detail'] == 'Outside the configured schedule.'


def test_sound_claim_once_and_does_not_block_other_actions(app):
    actions = app.state.actions
    sound(actions)
    sound(actions, 'computer-bell', 'computer')
    actions.test('bell')
    actions.test('computer-bell')
    delivered = []
    actions.sender = lambda config, context, key: (delivered.append(config['id']) or 'completed', 'Intercepted offline')
    actions.deliver()
    assert delivered == ['computer-bell']
    job = actions.claim_sound('tab1')
    assert job and actions.claim_sound('tab2') is None
    actions.acknowledge_sound(job['id'], 'tab2', True)
    assert next(j for j in actions.jobs() if j['id'] == job['id'])['status'] == 'sending'
    actions.acknowledge_sound(job['id'], 'tab1', True)
    assert all(j['status'] == 'completed' for j in actions.jobs())


def test_deletion_changed_question_and_expiry_cancel_waiting_actions(app, monkeypatch):
    actions = app.state.actions
    sound(actions)
    automation(actions)
    now = utcnow() + timedelta(seconds=1)
    current = summary(now)
    monkeypatch.setattr(actions, 'summary', lambda *a, **kw: current)
    actions.evaluate(now)
    current.update(state='ACTIVE', events=[event(now + timedelta(seconds=1))])
    actions.evaluate(now + timedelta(seconds=2))
    with pytest.raises(ValueError, match='Remove this action'):
        actions.delete('action', 'bell')
    with actions.store.connection() as db:
        db.execute('UPDATE query_controls SET enabled=0 WHERE source_id=? AND question_id=?', (SID,QID))
    assert actions.claim_sound('tab1') is None
    assert actions.jobs()[0]['status'] == 'cancelled'
    actions.delete('automation', 'front-door')
    actions.test('bell')
    actions.deliver(utcnow() + timedelta(minutes=3))
    assert next(j for j in actions.jobs() if j['id'].startswith('test-'))['status'] == 'expired'
    actions.delete('action', 'bell')
    assert actions.definitions() == []


def test_protected_configuration_audio_and_invalid_values(app):
    actions = app.state.actions
    actions.secrets = Vault()
    body = {'id': 'mail', 'name': 'Email me', 'kind': 'email', 'host': 'smtp.example.test', 'port': 465}
    protected = {'username': 'test@example.test', 'password': 'secret-do-not-export', 'from': 'vop@example.test', 'to': 'person@example.test'}
    actions.save_action(body, protected=protected)
    assert actions.dependency(actions.definitions()[0]) == ''
    with actions.store.connection() as db:
        assert 'secret-do-not-export' not in db.execute('SELECT configuration FROM action_definitions').fetchone()[0]
    actions.save_action(body)
    assert json.loads(actions.secrets.get('action-mail')) == protected
    with pytest.raises(ValueError): actions.save_action(body, protected={'password': 'partial'})
    encoded = base64.b64encode(beep_wav()).decode()
    actions.save_action({'id': 'audio', 'name': 'Doorbell', 'kind': 'audio', 'location': 'browser'}, audio=encoded)
    assert wav_bytes(encoded) == actions.audio('audio')
    with wave.open(BytesIO(scale_wav(beep_wav(), 0)), 'rb') as audio:
        assert set(audio.readframes(audio.getnframes())) == {0}
    for invalid in ('not base64', base64.b64encode(b'not a wave file').decode()):
        with pytest.raises(ValueError): wav_bytes(invalid)
    for changes in ({'volume': float('nan')}, {'volume': True}, {'location': 'antec'}):
        with pytest.raises(ValueError): actions.save_action({'kind':'beep','name':'No','location':'browser', **changes})


def test_actions_routes_csrf_modes_preview_and_real_test_is_only_queued(app):
    # No lifespan thread: inspect the queue before any delivery. No external systems contacted.
    client = TestClient(app)
    actions = app.state.actions
    actions.secrets = Vault()
    for kind in ('beep', 'audio', 'tapo', 'hub', 'email', 'sms'):
        response = client.get('/actions/edit?kind=' + kind, headers=HEADERS)
        assert response.status_code == 200
    response = client.post('/actions/save', headers=HEADERS, data={'id':'bell','kind':'beep','name':'Bell','location':'browser'})
    assert response.status_code == 200
    response = client.get('/automations/edit', headers=HEADERS)
    assert 'Episode starts' in response.text and 'Minimum time' in response.text
    form = {'condition': SID + '/' + QID, 'name':'Door bell', 'trigger':'start','actions':'bell','cooldown':'00:01:00','enabled':'yes'}
    response = client.post('/automations/preview', headers=HEADERS, data=form)
    assert 'Preview only' in response.text and actions.automations() == [] and actions.jobs() == []
    assert client.post('/automations/save', headers=HEADERS, data=form).status_code == 200
    assert client.post('/actions/bell/test', headers=HEADERS).status_code == 200
    assert actions.jobs()[0]['status'] == 'queued'
    assert client.get('/activity', headers={'Authorization':'Bearer ' + VIEWER}).status_code == 200
    assert client.get('/actions/edit?kind=sms', headers={'Authorization':'Bearer ' + VIEWER}).status_code == 403
    assert client.get('/actions/audio/private', headers={'Authorization':'Bearer ' + VIEWER}).status_code == 403
    assert client.post('/actions/bell/test', headers={'Authorization':'Bearer ' + VIEWER}).status_code == 403
    from test_phase2_browser_storage import login
    csrf = login(client, TOKEN)
    assert client.get('/actions', follow_redirects=False).headers['location'] == '/configure'
    assert client.post('/actions/sound/claim', data={'client':'x'}).status_code == 403
    response = client.post('/actions/sound/claim', data={'csrf':csrf,'client':'x'})
    assert response.status_code == 200 and response.json()['id']
    assert client.post('/automations/pause', data={'csrf':csrf,'paused':'yes'}).status_code == 200
    assert actions.paused()
    assert "media-src 'self'" in client.get('/').headers['content-security-policy']
    assert client.post('/ui/mode', data={'csrf':csrf,'mode':'configure'}).status_code == 200
    editor = BeautifulSoup(client.get('/actions/edit?kind=hub').text, 'html.parser')
    assert editor.select_one('select[name=volume]') and editor.select_one('select[name=sound]')
    assert not editor.select_one('input[name=message]')


def test_tapo_l530_and_h100_adapter_contracts_without_network(monkeypatch):
    import sys
    calls = []
    alarm = SimpleNamespace(alarm_sounds=['Doorbell Ring 1'])
    async def play(**kw): calls.append(('play', kw))
    async def update(): calls.append('update')
    async def disconnect(): calls.append('disconnect')
    async def on(): calls.append('on')
    async def off(): calls.append('off')
    alarm.play = play
    device = SimpleNamespace(device_type='hub', model='H100', modules={'alarm':alarm}, update=update, disconnect=disconnect, turn_on=on, turn_off=off)
    async def discover(address, **kw):
        assert address == '192.168.1.2'
        return device
    monkeypatch.setitem(sys.modules, 'kasa', SimpleNamespace(Discover=SimpleNamespace(discover_single=discover),
        Module=SimpleNamespace(Alarm='alarm',Light='light'), DeviceType=SimpleNamespace(Hub='hub',Bulb='bulb',LightStrip='strip')))
    config = {'kind':'hub','address':'192.168.1.2','seconds':3,'volume':'low','sound':'Doorbell Ring 1'}
    asyncio.run(tapo(config, {'username':'test','password':'test'}, Event()))
    assert ('play', {'duration':3,'volume':'low','sound':'Doorbell Ring 1'}) in calls
    assert calls[-1] == 'disconnect'
    calls.clear()
    device.device_type = 'bulb'
    config.update(kind='tapo',operation='on')
    asyncio.run(tapo(config, {'username':'test','password':'test'}, Event()))
    assert calls == ['update','on','disconnect']
    config.update(operation='off')
    asyncio.run(tapo(config, {'username':'test','password':'test'}, Event()))
    assert calls[-2:] == ['off','disconnect']


def test_synthetic_observations_never_automatically_send(app):
    actions = app.state.actions
    sound(actions)
    automation(actions)
    now = utcnow() + timedelta(seconds=1)
    actions.evaluate(now)
    samples(app, now + timedelta(seconds=1), [True, True], step=1)
    actions.evaluate(now + timedelta(seconds=4))
    assert len(actions.jobs()) == 1
    assert actions.jobs()[0]['status'] == 'suppressed'
    assert actions.claim_sound('tab') is None


def test_message_adapters_acceptance_rejection_and_ambiguous_send(app, monkeypatch):
    import smtplib
    from urllib.error import HTTPError
    from vop import actions as module
    actions = app.state.actions
    actions.secrets = Vault()
    protected = {'username':'u@example.test','password':'not-a-real-secret','from':'vop@example.test','to':'test@example.test'}
    actions.save_action({'id':'mail','kind':'email','name':'Mail','host':'smtp.example.test','port':465,
                         'subject':'{camera}','message':'{question}: {trigger}'}, protected=protected)
    recorded = []
    class SMTP:
        def __init__(self, host, port, **kwargs):
            assert host == 'smtp.example.test' and port == 465 and kwargs['timeout'] == 8
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def login(self, username, password): assert username == protected['username'] and password == protected['password']
        def send_message(self, mail): recorded.append(mail)
    monkeypatch.setattr(module.smtplib, 'SMTP_SSL', SMTP)
    config = actions.definitions()[0]
    status, _ = actions.send(config, {'camera':'Door','question':'Person','trigger':'Episode starts'}, 'key')
    assert status == 'accepted' and recorded[0]['Subject'] == 'Door' and 'Person: Episode starts' in recorded[0].get_content()
    def reject(*args, **kw): raise smtplib.SMTPAuthenticationError(535, b'No')
    monkeypatch.setattr(SMTP, 'login', reject)
    assert actions.send(config, {}, 'key')[0] == 'blocked'
    sms = {'account':'AC'+'1'*32, 'username':'SK'+'2'*32, 'password':'test-secret','from':'+441234567890','to':'+441234567891'}
    actions.save_action({'id':'sms','kind':'sms','name':'Text'}, protected=sms)
    config = next(a for a in actions.definitions() if a['id'] == 'sms')
    class Opener:
        def open(self, request, timeout):
            assert request.full_url == 'https://api.twilio.com/2010-04-01/Accounts/' + sms['account'] + '/Messages.json'
            assert b'To=%2B441234567891' in request.data
            return self
        def __enter__(self): return self
        def __exit__(self, *args): pass
        status = 201
    monkeypatch.setattr(module, 'build_opener', lambda *args: Opener())
    assert actions.send(config, {'camera':'Door'}, 'sms-key')[0] == 'accepted'
    def busy(*args, **kw): raise HTTPError('https://api.twilio.com',429,'Busy',{},None)
    monkeypatch.setattr(Opener, 'open', busy)
    assert actions.send(config, {}, 'key')[0] == 'retry'
    # A network timeout is ambiguous: queue records it once, without automatic resending.
    def timeout(*args): raise TimeoutError()
    actions.sender = timeout
    actions.test('sms')
    actions.deliver()
    actions.deliver()
    assert actions.jobs()[0]['status'] == 'uncertain' and actions.jobs()[0]['attempts'] == 1


def test_summary_cache_invalidates_samples_policy_and_history_deletion(app, monkeypatch):
    actions = app.state.actions
    record = actions.store.questions(SID)[0]
    now = utcnow()
    samples(app, now, [False, False], step=1)
    calls = []
    original = actions.store.summary
    def counted(*args, **kwargs):
        calls.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(actions.store, 'summary', counted)
    q, policy = record['spec'], record['policy']
    assert actions.summary(SID, q, policy, now + timedelta(seconds=2))['state'] == 'INACTIVE'
    assert actions.summary(SID, q, policy, now + timedelta(hours=1))['state'] == 'UNKNOWN'
    assert len(calls) == 1
    samples(app, now + timedelta(seconds=3), [True], step=1)
    actions.summary(SID, q, policy, now + timedelta(seconds=4))
    assert len(calls) == 2
    with actions.store.connection() as db:
        db.execute('DELETE FROM observations WHERE sequence=(SELECT MIN(sequence) FROM observations WHERE source_id=? AND question_id=?)', (SID,QID))
    actions.summary(SID, q, policy, now + timedelta(seconds=4))
    assert len(calls) == 3
    from dataclasses import replace
    actions.summary(SID, q, replace(policy, max_gap_seconds=2), now + timedelta(seconds=4))
    assert len(calls) == 4


def test_question_data_deletion_erases_action_history_and_pauses_automation(app, monkeypatch):
    from vop.history_deletion import question_selection, delete_question_data
    actions = app.state.actions
    sound(actions)
    automation(actions)
    now = utcnow() + timedelta(seconds=1)
    current = summary(now)
    monkeypatch.setattr(actions, 'summary', lambda *a: current)
    actions.evaluate(now)
    current.update(events=[event(now + timedelta(seconds=1))], state='ACTIVE')
    actions.evaluate(now + timedelta(seconds=2))
    assert actions.jobs()
    with actions.store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        delete_question_data(db, question_selection(db, SID, QID))
    assert actions.jobs() == [] and not actions.automations()[0]['enabled']


def test_ordinal_and_choice_forms_only_offer_valid_named_values(app):
    actions = app.state.actions
    sound(actions)
    client = TestClient(app)
    for qid, expected in (('background','white'), ('brightness','(0)')):
        response = client.get('/automations/edit?condition=' + SID + '/' + qid + '&trigger=value', headers=HEADERS)
        soup = BeautifulSoup(response.text, 'html.parser')
        assert soup.select_one('select[name=value]')
        assert expected in soup.select_one('select[name=value]').text
        assert 'Episode starts' not in soup.select_one('select[name=trigger]').text
        assert not soup.select_one('input[name=seconds]')


def test_hub_device_check_reads_sound_choices_without_playing(app, monkeypatch):
    import sys
    actions = app.state.actions
    actions.secrets = Vault()
    actions.save_action({'id':'hub','kind':'hub','name':'Hub bell','address':'192.168.1.2','volume':'low','seconds':3},
                        protected={'username':'u@example.test','password':'test'})
    calls = []
    async def update(): calls.append('read')
    async def disconnect(): calls.append('disconnect')
    device = SimpleNamespace(model='H100', update=update, disconnect=disconnect,
                             modules={'alarm':SimpleNamespace(alarm_sounds=['Doorbell Ring 1','Alarm 1'])})
    async def discover(*args, **kwargs): return device
    monkeypatch.setitem(sys.modules, 'kasa', SimpleNamespace(Discover=SimpleNamespace(discover_single=discover), Module=SimpleNamespace(Alarm='alarm')))
    monkeypatch.setattr(actions, 'dependency', lambda config: '')
    assert actions.check_device('hub')['model'] == 'H100'
    assert calls == ['read','disconnect'] and actions.hub_sounds('hub') == ['Doorbell Ring 1','Alarm 1']
    assert actions.jobs() == []


def test_ordinal_matching_uses_numeric_thresholds():
    from vop.actions import matches
    assert matches(1.6, {'value':1,'comparison':'at_least'})
    assert not matches(0.9, {'value':1,'comparison':'at_least'})
    assert matches(0.9, {'value':1,'comparison':'at_most'})
    assert not matches(None, {'value':1,'comparison':'at_most'})
    assert not matches(True, {'value':1,'comparison':'at_least'})


def test_mixed_synthetic_episode_does_not_trigger_external_action(app, monkeypatch):
    actions = app.state.actions
    sound(actions)
    automation(actions, trigger='duration', seconds=1)
    now = utcnow() + timedelta(seconds=1)
    current = summary(now)
    monkeypatch.setattr(actions, 'summary', lambda *a: current)
    monkeypatch.setattr(actions.store, 'observation', lambda oid: {'run':{'synthetic':oid=='synthetic-start'}})
    actions.evaluate(now)
    current.update(state='ACTIVE', last_observation_id='real-latest', events=[event(now + timedelta(seconds=1),
                   start_observation_id='synthetic-start', estimated_observed_seconds=10)])
    actions.evaluate(now + timedelta(seconds=2))
    assert actions.jobs()[0]['status'] == 'suppressed'


def test_replaced_audio_is_not_substituted_into_an_already_claimed_job(app):
    actions = app.state.actions
    body = {'id':'audio','kind':'audio','name':'Bell','location':'browser'}
    actions.save_action(body, audio=base64.b64encode(beep_wav(50)).decode())
    actions.test('audio')
    job = actions.claim_sound('tab')
    digest = job['config']['audio_digest']
    assert actions.audio('audio', digest) is not None
    actions.save_action(body, audio=base64.b64encode(beep_wav(10)).decode())
    assert actions.audio('audio', digest) is None
    assert actions.audio('audio', next(a for a in actions.definitions() if a['id']=='audio')['audio_digest']) is not None


def test_full_backup_preserves_actions_audio_and_json_import_explains_limit(app, tmp_path):
    import importlib.util
    from pathlib import Path
    from vop.reliable import configuration, backup, restore
    from vop.config import load_config
    from vop.service import create_app
    actions = app.state.actions
    actions.save_action({'id':'audio','kind':'audio','name':'Bell','location':'browser'},
                        audio=base64.b64encode(beep_wav()).decode())
    package = configuration(app.state.reliable.settings, actions.store, app.state.reliable)
    assert package['actions'][0]['kind'] == 'audio'
    folder = backup(actions.store, package, tmp_path / 'backup')
    config = restore(folder, tmp_path / 'restored')
    fresh = create_app(load_config(config), token=TOKEN)
    assert fresh.state.actions.audio('audio') == actions.audio('audio')
    assert fresh.state.actions.definitions() == actions.definitions()
    spec = importlib.util.spec_from_file_location('action_release_tool', Path(__file__).resolve().parents[1] / 'tools/release.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match='Use full backup'):
        module.import_configuration(folder / 'configuration.json', tmp_path / 'imported')
    assert not (tmp_path / 'imported').exists()
