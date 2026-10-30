"""Named actions and episode automations. No acquisition or inference imports.

The queue owns deduplication, expiry and audit. Adapters never retry ambiguous sends.
"""
import asyncio
import base64
from datetime import timedelta
from email.message import EmailMessage
from hashlib import sha256
from io import BytesIO
import ipaddress
import json
import math
import os
import re
import smtplib
import ssl
from threading import Event, Lock, Thread
from time import monotonic
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, ProxyHandler
from uuid import uuid4
import wave

from vop.config import identifier
from vop.contracts import utcnow
from vop.inputs.sources import NoRedirect
from vop.measurements import utc, timezone_for
from vop.secrets import SecretStore
from vop.storage import dumps

KINDS = {'image': 'Save image', 'beep': 'Beep', 'audio': 'Play audio', 'tapo': 'Tapo light (L530)', 'hub': 'Tapo hub sound (H100)', 'email': 'Email', 'sms': 'Text message'}
TRIGGERS = {'start': 'Episode starts', 'duration': 'Episode stays active', 'end': 'Episode ends',
            'value': 'Answer becomes', 'unavailable': 'Observation becomes unavailable', 'recovered': 'Observation recovers'}
SCHEMA = """
CREATE TABLE IF NOT EXISTS action_definitions(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,configuration TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS automations(id TEXT PRIMARY KEY,revision INTEGER NOT NULL,configuration TEXT NOT NULL,state TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS automations_source ON automations(json_extract(configuration,'$.source_id'));
CREATE TABLE IF NOT EXISTS action_jobs(id TEXT PRIMARY KEY,automation_id TEXT,action_id TEXT NOT NULL,
 created TEXT NOT NULL,expires TEXT NOT NULL,due TEXT NOT NULL,status TEXT NOT NULL,attempts INTEGER NOT NULL,
 configuration TEXT NOT NULL,context TEXT NOT NULL,detail TEXT NOT NULL,claim TEXT);
CREATE INDEX IF NOT EXISTS action_jobs_due ON action_jobs(status,due);
CREATE INDEX IF NOT EXISTS action_jobs_limit ON action_jobs(automation_id,created);
CREATE TABLE IF NOT EXISTS action_audio(id TEXT PRIMARY KEY,payload BLOB NOT NULL);
"""


def text(value, label, limit=500):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'Enter {label} (up to {limit} characters).')
    return value.strip()


def number(value, low, high, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label} must be between {low} and {high}.')
    return value


def wav_bytes(encoded):
    try:
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > 2 * 1024 * 1024:
            raise ValueError()
        with wave.open(BytesIO(payload), 'rb') as audio:
            if audio.getcomptype() != 'NONE' or audio.getsampwidth() != 2 or audio.getnchannels() not in (1, 2) or not 8000 <= audio.getframerate() <= 48000 or not 0 < audio.getnframes() / audio.getframerate() <= 60:
                raise ValueError()
            if len(audio.readframes(audio.getnframes())) != audio.getnframes() * audio.getnchannels() * 2:
                raise ValueError()
        return payload
    except (ValueError, wave.Error, EOFError):
        raise ValueError('Choose a PCM WAV file: 16-bit, mono or stereo, 8–48 kHz, up to 00:01:00 and 2 MB.') from None


class Actions:
    def __init__(self, store, pipeline, zone='UTC', *, secrets=None, sender=None):
        self.store, self.pipeline, self.zone = store, pipeline, zone
        self.secrets = secrets or SecretStore()
        self.sender = sender or self.send
        self.stop_event, self.lock = Event(), Lock()
        self.thread = None
        self.last_error = None
        self.cleanup_error = None
        self.cleanup_retry_after = 0
        self.summary_cache = {}
        with store.connection() as db:
            db.executescript(SCHEMA)
            row = db.execute("SELECT value_json FROM release_settings WHERE id='actions_schema'").fetchone()
            if row and json.loads(row[0]) != 1:
                raise ValueError('Actions storage is newer than this application.')
            db.execute("INSERT OR IGNORE INTO release_settings VALUES('actions_schema','1')")

    def definitions(self):
        with self.store.connection() as db:
            return [{**json.loads(r['configuration']), 'revision': r['revision']} for r in db.execute('SELECT * FROM action_definitions ORDER BY id')]

    def automations(self):
        with self.store.connection() as db:
            return [{**json.loads(r['configuration']), 'revision': r['revision']} for r in db.execute('SELECT * FROM automations ORDER BY id')]

    def paused(self):
        with self.store.connection() as db:
            r = db.execute("SELECT value_json FROM release_settings WHERE id='actions_paused'").fetchone()
            return bool(json.loads(r[0])) if r else False

    def pause(self, paused):
        with self.lock, self.store.connection() as db:
            db.execute("INSERT OR REPLACE INTO release_settings VALUES('actions_paused',?)", (dumps(bool(paused)),))
            db.execute("UPDATE action_jobs SET status='cancelled',detail='Automations paused.' WHERE automation_id IS NOT NULL AND status IN ('queued','retry')")
            # Resume from the current state, without replaying events from the pause.
            db.execute("UPDATE automations SET state='{}'")
        self.store.audit('automations_pause', str(bool(paused)))

    def save_action(self, body, *, protected=None, audio=None):
        body = dict(body)
        aid = identifier(body.get('id') or 'action-' + uuid4().hex[:12])
        kind = body.get('kind')
        if kind not in KINDS:
            raise ValueError('Choose an action type.')
        config = {'id': aid, 'name': text(body.get('name'), 'an action name', 100), 'kind': kind}
        if kind in ('beep', 'audio'):
            if body.get('location') not in ('browser', 'computer'):
                raise ValueError('Choose where the sound plays.')
            config.update(location=body['location'], volume=number(body.get('volume', 60), 0, 100, 'Volume'))
        if kind in ('tapo', 'hub'):
            try:
                address = ipaddress.ip_address(body.get('address', ''))
                if not address.is_private or address.is_loopback or address.is_multicast or address.is_unspecified or address.version != 4:
                    raise ValueError()
            except ValueError:
                raise ValueError('Enter the device’s private LAN IPv4 address.') from None
            config['address'] = str(address)
        if kind == 'tapo':
            if body.get('operation') not in ('on', 'off', 'flash'):
                raise ValueError('Choose turn on, turn off or flash.')
            config.update(address=str(address), operation=body['operation'],
                          seconds=number(body.get('seconds', 6), 2, 20, 'Flash duration'),
                          brightness=number(body.get('brightness', 0), 0, 100, 'Brightness'))
            colour = body.get('colour', '')
            if colour and not re.fullmatch(r'#[0-9a-fA-F]{6}', colour):
                raise ValueError('Choose a colour or leave it empty to keep the current colour.')
            config['colour'] = colour
        if kind == 'hub':
            if body.get('volume', 'low') not in ('low', 'normal', 'high'):
                raise ValueError('Choose low, normal or high hub volume.')
            config.update(seconds=int(number(body.get('seconds', 3), 1, 30, 'Hub sound duration')),
                          volume=body.get('volume', 'low'), sound=body.get('sound', ''))
            if config['sound']:
                text(config['sound'], 'a hub sound', 100)
        if kind == 'email':
            config.update(host=text(body.get('host'), 'the SMTP server', 253), port=int(number(body.get('port', 465), 1, 65535, 'SMTP port')),
                          subject=text(body.get('subject', 'VOP: {camera} — {question}'), 'a subject', 200))
            if any(c in config['host'] for c in '/:@\r\n') or '\n' in config['subject'] or '\r' in config['subject']:
                raise ValueError('Enter a server hostname and a single-line subject.')
        if kind in ('email', 'sms'):
            config['message'] = text(body.get('message', '{camera}: {question} — {trigger}'), 'a message', 1000)
        with self.lock:
            old = next((a for a in self.definitions() if a['id'] == aid), None)
            if old and old['kind'] != kind:
                raise ValueError('Create a new action to change its type.')
            if kind in ('tapo', 'hub', 'email', 'sms'):
                # The whole account/recipient bundle is protected; secrets never enter SQLite.
                secret = 'action-' + aid
                if len(secret) > 64:
                    secret = 'action-' + sha256(aid.encode()).hexdigest()[:40]
                if protected:
                    self.validate_protected(kind, protected)
                    self.secrets.set(secret, dumps(protected))
                config['secret'] = secret
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if audio is not None:
                    db.execute('INSERT OR REPLACE INTO action_audio VALUES(?,?)', (aid, wav_bytes(audio)))
                if kind == 'audio' and not db.execute('SELECT 1 FROM action_audio WHERE id=?', (aid,)).fetchone():
                    raise ValueError('Record a clip or choose an audio file for this action.')
                if kind == 'audio':
                    config['audio_digest'] = sha256(bytes(db.execute('SELECT payload FROM action_audio WHERE id=?', (aid,)).fetchone()[0])).hexdigest()
                db.execute('INSERT OR REPLACE INTO action_definitions VALUES(?,?,?)', (aid, (old['revision'] if old else 0) + 1, dumps(config)))
                db.execute("UPDATE action_jobs SET status='cancelled',detail='Action settings changed.' WHERE action_id=? AND status IN ('queued','retry')", (aid,))
        self.store.audit('action_saved', aid)
        return aid

    @staticmethod
    def validate_protected(kind, values):
        required = {'tapo': ('username', 'password'), 'hub': ('username', 'password'), 'email': ('username', 'password', 'from', 'to'),
                    'sms': ('account', 'username', 'password', 'from', 'to')}[kind]
        if set(values) != set(required):
            raise ValueError('Complete all protected connection fields, or leave them all blank to keep the saved values.')
        for key in required:
            text(values[key], key, 256)
            if '\r' in values[key] or '\n' in values[key]:
                raise ValueError('Connection fields must be single-line values.')
        if kind == 'email' and any(not re.fullmatch(r'[^\s<>@,;]+@[^\s<>@,;]+\.[^\s<>@,;]+', values[k]) for k in ('from', 'to')):
            raise ValueError('Enter one sender and one recipient email address.')
        if kind == 'sms' and (not re.fullmatch(r'AC[0-9a-fA-F]{32}', values['account']) or
                not re.fullmatch(r'SK[0-9a-fA-F]{32}', values['username']) or
                any(not re.fullmatch(r'\+[1-9][0-9]{7,14}', values[k]) for k in ('from', 'to'))):
            raise ValueError('Use a Twilio Account SID (AC…), API key SID (SK…), secret and international phone numbers (+country code).')

    def dependency(self, config):
        if config['kind'] in ('email', 'sms', 'tapo', 'hub'):
            try:
                self.validate_protected(config['kind'], json.loads(self.secrets.get(config['secret'])))
            except Exception:
                return 'Enter the protected account and recipient details in Edit action.'
        if config['kind'] in ('tapo', 'hub'):
            from importlib.util import find_spec
            if find_spec('kasa') is None:
                return 'Install the optional Tapo support on the VOP computer. See the Actions runbook.'
        if config.get('location') == 'computer' and os.name != 'nt':
            return 'Computer sound currently requires Windows. Choose this browser instead.'
        if config.get('location') == 'browser':
            return 'Sound needs an open VOP page with Enable sound selected.'
        return ''

    def hub_sounds(self, aid):
        with self.store.connection() as db:
            row = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('action_device:' + aid,)).fetchone()
        action = next((a for a in self.definitions() if a['id'] == aid), None)
        info = json.loads(row[0]) if row else {}
        return info.get('sounds', []) if action and action.get('address') == info.get('address') else []

    def check_device(self, aid):
        config = next((a for a in self.definitions() if a['id'] == aid), None)
        if not config or config['kind'] not in ('tapo', 'hub'):
            raise ValueError('Choose a saved Tapo light or hub action.')
        dependency = self.dependency(config)
        if dependency:
            raise ValueError(dependency)
        try:
            info = asyncio.run(asyncio.wait_for(tapo_info(config, json.loads(self.secrets.get(config['secret']))), timeout=12))
        except Exception:
            raise ValueError('VOP could not check the device. Check its LAN address, power and Tapo account in Edit action. No light or sound was requested.') from None
        with self.store.connection() as db:
            db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('action_device:' + aid, dumps(info)))
        self.store.audit('action_device_checked', aid)
        return info

    def validate_automation(self, body):
        body = dict(body)
        mid = identifier(body.get('id') or 'automation-' + uuid4().hex[:12])
        sid, qid = body.get('source_id'), body.get('question_id')
        if sid not in self.pipeline.sources:
            raise ValueError('Choose an available camera.')
        question = next((q for q in self.store.questions(sid, active_only=True) if q['spec'].question_id == qid), None)
        if not question:
            raise ValueError('Choose an enabled question.')
        trigger = body.get('trigger')
        if trigger not in TRIGGERS or trigger in ('start', 'duration', 'end') and question['spec'].kind != 'binary':
            raise ValueError('Episode triggers require a Yes/No question. Use Answer becomes for other answer types.')
        selected = body.get('actions')
        if not isinstance(selected, list) or not selected or len(selected) > 10 or len(set(selected)) != len(selected) or set(selected) - {a['id'] for a in self.definitions()}:
            raise ValueError('Choose between one and ten different actions.')
        value = body.get('value')
        q = question['spec']
        comparison = body.get('comparison', 'at_least' if q.kind == 'ordinal' else 'equals')
        if comparison not in (('at_least', 'at_most') if q.kind == 'ordinal' else ('equals',)):
            raise ValueError('Choose how to compare the answer.')
        if trigger == 'value':
            if q.kind == 'binary' and type(value) is not bool or q.kind == 'choice' and value not in [name for name, description in q.choices] or q.kind == 'ordinal' and (type(value) is not int or not 0 <= value < len(q.levels)):
                raise ValueError('Choose an answer value from this question.')
        start, end = body.get('start', ''), body.get('end', '')
        if bool(start) != bool(end) or any(v and not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', v) for v in (start, end)):
            raise ValueError('Set both schedule times (HH:MM), or leave both empty.')
        if type(body.get('enabled', False)) is not bool:
            raise ValueError('Choose Enabled or Paused.')
        config = {'id': mid, 'name': text(body.get('name'), 'an automation name', 100), 'source_id': sid, 'question_id': qid,
                  'question_version': q.version, 'trigger': trigger, 'value': value, 'actions': selected,
                  'comparison': comparison,
                  'seconds': number(body.get('seconds', 30), 0, 31536000, 'Active duration'),
                  'cooldown': number(body.get('cooldown', 60), 0, 86400, 'Cooldown'),
                  'max_hour': int(number(body.get('max_hour', 10), 1, 100, 'Hourly limit')),
                  'start': start, 'end': end, 'enabled': body.get('enabled', False), 'armed': utcnow().isoformat()}
        return config

    def save_automation(self, body):
        config = self.validate_automation(body)
        mid = config['id']
        with self.lock, self.store.connection() as db:
            old = db.execute('SELECT revision FROM automations WHERE id=?', (mid,)).fetchone()
            db.execute('INSERT OR REPLACE INTO automations VALUES(?,?,?,?)', (mid, old[0] + 1 if old else 1, dumps(config), '{}'))
            db.execute("UPDATE action_jobs SET status='cancelled',detail='Automation settings changed.' WHERE automation_id=? AND status IN ('queued','retry')", (mid,))
        self.store.audit('automation_saved', mid)
        return mid

    def automation_dependencies(self, config):
        sid = config['source_id']
        if sid not in self.pipeline.sources:
            return ['The camera is retired or unavailable. Edit this automation.']
        record = next((r for r in self.store.questions(sid) if r['spec'].question_id == config['question_id']), None)
        if not record or not record['enabled']:
            return ['The question is deleted or paused. Choose an enabled question.']
        if record['spec'].version != config['question_version']:
            return ['The question changed. Review and save this automation for the current version.']
        if not self.store.source_control(sid)['enabled']:
            return ['The camera is disabled. Enable it in Cameras.']
        if self.store.source_control(sid)['sample_interval_seconds'] == 0:
            return ['Monitoring is paused. Start monitoring in Observe, or run a manual observation.']
        return []

    def delete(self, kind, key):
        identifier(key)
        if kind not in ('action', 'automation'):
            raise ValueError('Unknown item.')
        with self.lock, self.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            if kind == 'action':
                if any(key in m['actions'] for m in self.automations()):
                    raise ValueError('Remove this action from its automations first. Open Automations to edit them.')
                from vop.secret_cleanup import queue
                row = db.execute('SELECT configuration FROM action_definitions WHERE id=?', (key,)).fetchone()
                if row:
                    queue(db, json.loads(row[0]).get('secret'))
                db.execute('DELETE FROM action_definitions WHERE id=?', (key,))
                db.execute('DELETE FROM action_audio WHERE id=?', (key,))
            else:
                db.execute('DELETE FROM automations WHERE id=?', (key,))
            column = 'action_id' if kind == 'action' else 'automation_id'
            db.execute(f"UPDATE action_jobs SET status='cancelled',detail='Configuration deleted.' WHERE {column}=? AND status IN ('queued','retry')", (key,))
            self.summary_cache.clear()
        self.store.audit(kind + '_deleted', key)
        self.cleanup_secrets()

    def cleanup_secrets(self):
        from vop.secret_cleanup import clean
        if monotonic() < self.cleanup_retry_after:
            return
        with self.store.connection() as db:
            if not db.execute("SELECT 1 FROM release_settings WHERE id LIKE 'pending_secret_delete:%' LIMIT 1").fetchone():
                return
        if not self.pipeline.busy.acquire(blocking=False):
            return
        try:
            with self.lock:
                self.cleanup_error = clean(self.store, self.secrets, self.pipeline)
                self.last_error = self.cleanup_error
                self.cleanup_retry_after = monotonic() + 30 if self.cleanup_error else 0
        finally:
            self.pipeline.busy.release()

    def clear_history_cache(self, source_id):
        with self.lock:
            for key in list(self.summary_cache):
                if key[0] == source_id:
                    self.summary_cache.pop(key)

    def evaluate(self, now=None):
        now = utc(now) if now else utcnow()
        if self.paused():
            return
        summaries, questions, controls, observations = {}, {}, {}, {}
        for m in self.automations():
            if not m['enabled'] or m['source_id'] not in self.pipeline.sources:
                continue
            sid, qid = m['source_id'], m['question_id']
            if sid not in questions:
                questions[sid] = {r['spec'].question_id: r for r in self.store.questions(sid, active_only=True)}
                controls[sid] = self.store.source_control(sid)
            record = questions[sid].get(qid)
            if not record or not controls[sid]['enabled'] or record['spec'].version != m['question_version']:
                continue
            if m['trigger'] in ('unavailable', 'recovered') and controls[sid]['sample_interval_seconds'] == 0:
                continue  # An intentional monitoring pause is not a device failure.
            q = record['spec']
            sk = (sid, qid, q.version)
            if sk not in summaries:
                summaries[sk] = self.summary(sid, q, record['policy'], now)
            summary = summaries[sk]
            unavailable = summary['state'] == 'UNKNOWN'
            with self.store.connection() as db:
                row = db.execute('SELECT state FROM automations WHERE id=? AND revision=?', (m['id'], m['revision'])).fetchone()
            if not row:
                continue
            state = json.loads(row[0])
            # Initial state is a baseline, including after a restart or pause. Never act on history.
            if not state:
                state = {'baseline': now.isoformat(), 'unavailable': unavailable, 'match': matches(summary['latest_value'], m) if not unavailable else False}
                candidates = []
            else:
                candidates = []
                boundary = max(utc(m['armed']), utc(state['baseline']))
                for event in summary['events'] if m['trigger'] in ('start', 'end', 'duration') else ():
                    stamp = event['ended_at_utc'] if m['trigger'] == 'end' else event['started_at_utc']
                    if stamp is None or not boundary <= utc(stamp) <= now:
                        continue
                    if m['trigger'] == 'end' and event['status'] == 'closed' or m['trigger'] == 'start' or m['trigger'] == 'duration' and not unavailable and event['status'] == 'open' and event['estimated_observed_seconds'] >= m['seconds']:
                        candidates.append(event['id'])
                match = not unavailable and matches(summary['latest_value'], m)
                if m['trigger'] == 'value' and match and not state.get('match'):
                    candidates.append(summary['last_observation_id'])
                if m['trigger'] == 'unavailable' and unavailable and not state.get('unavailable') or m['trigger'] == 'recovered' and not unavailable and state.get('unavailable'):
                    candidates.append(summary['last_sample_at_utc'] or now.isoformat())
                if not unavailable:
                    state['match'] = match
                state['unavailable'] = unavailable
            local = now.astimezone(timezone_for(self.zone)).strftime('%H:%M')
            scheduled = not m['start'] or (m['start'] <= local < m['end'] if m['start'] < m['end'] else local >= m['start'] or local < m['end'])
            # Read-only idle cycles: do not take SQLite's writer lock every polling tick.
            with self.store.connection() as db:
                candidates = [eid for eid in candidates if not db.execute('SELECT 1 FROM action_jobs WHERE id=?',
                    (sha256(f"{m['id']}:{m['revision']}:{eid}".encode()).hexdigest() + ':' + m['actions'][0],)).fetchone()]
            if not candidates and dumps(state) == row[0]:
                continue
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if not db.execute('SELECT 1 FROM automations WHERE id=? AND revision=?', (m['id'], m['revision'])).fetchone():
                    continue
                db.execute('UPDATE automations SET state=? WHERE id=?', (dumps(state), m['id']))
                for event_id in candidates:
                    key = sha256(f"{m['id']}:{m['revision']}:{event_id}".encode()).hexdigest()
                    if db.execute('SELECT 1 FROM action_jobs WHERE id=?', (key + ':' + m['actions'][0],)).fetchone():
                        continue
                    last = db.execute('SELECT MAX(created) FROM action_jobs WHERE automation_id=? AND status NOT IN (\'suppressed\',\'cancelled\')', (m['id'],)).fetchone()[0]
                    recent = db.execute("SELECT COUNT(DISTINCT substr(id,1,64)) FROM action_jobs WHERE automation_id=? AND created>=? AND status NOT IN ('suppressed','cancelled')", (m['id'], (now - timedelta(hours=1)).isoformat())).fetchone()[0]
                    reason = 'Outside the configured schedule.' if not scheduled else 'Cooldown is active.' if last and (now - utc(last)).total_seconds() < m['cooldown'] else 'Hourly limit reached.' if recent >= m['max_hour'] else ''
                    observation_ids = [summary['last_observation_id']]
                    related_event = next((e for e in summary['events'] if e['id'] == event_id), None)
                    if related_event:
                        observation_ids += [related_event.get('start_observation_id'), related_event.get('end_observation_id')]
                    for oid in observation_ids:
                        if oid and oid not in observations:
                            observations[oid] = self.store.observation(oid)
                    synthetic = any(observations[oid]['run'].get('synthetic') for oid in observation_ids if oid and observations.get(oid))
                    if synthetic:
                        reason = 'Synthetic observations do not run automatic actions. Use an explicit action test.'
                    context = {'camera': self.pipeline.sources[sid].name or sid, 'question': q.text, 'trigger': TRIGGERS[m['trigger']],
                               'automation': m['name'], 'source_id': sid, 'question_id': qid, 'question_version': q.version, 'event_id': event_id,
                               'observation_id': summary['last_observation_id']}
                    for aid in m['actions']:
                        action = db.execute('SELECT configuration FROM action_definitions WHERE id=?', (aid,)).fetchone()
                        if action:
                            self.enqueue(db, key + ':' + aid, m['id'], json.loads(action[0]), context, now, reason)

    def summary(self, sid, question, policy, now):
        """Reuse temporal replay until samples or policy change; age UNKNOWN separately."""
        key = (sid, question.question_id, question.version)
        with self.store.connection() as db:
            signature = tuple(db.execute('SELECT COUNT(*),MAX(sequence) FROM observations WHERE source_id=? AND question_id=? AND question_version=?', key).fetchone()) + (policy,)
        cached = self.summary_cache.get(key)
        if not cached or cached[0] != signature:
            value = self.store.summary(*key, kind=question.kind)
            if value.get('disabled'):
                self.summary_cache.pop(key, None)
                return value
            # Bounded by the supported 32 cameras × 32 questions; evict obsolete versions.
            if len(self.summary_cache) >= 1024:
                self.summary_cache.clear()
            self.summary_cache[key] = (signature, value)
        else:
            value = cached[1]
        if value['last_sample_at_utc'] and (now - utc(value['last_sample_at_utc'])).total_seconds() > policy.max_gap_seconds:
            return {**value, 'state': 'UNKNOWN', 'stale': True, 'latest_value': None}
        return value

    def enqueue(self, db, jid, mid, config, context, now, reason=''):
        if db.execute('SELECT 1 FROM action_jobs WHERE id=?', (jid,)).fetchone():
            return
        status, detail = ('suppressed', reason) if reason else ('queued', '')
        if not reason and config['kind'] == 'image':
            # This local DB action and its Activity receipt commit together. No queued
            # image copies, external I/O or later retry can restore deleted evidence.
            status, detail = self.save_image(db, context, now)
        db.execute('INSERT OR IGNORE INTO action_jobs VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',
                   (jid, mid, config['id'], now.isoformat(), (now + timedelta(minutes=2)).isoformat(), now.isoformat(),
                    status, int(config['kind']=='image' and not reason), dumps(config), dumps(context), detail, None))
        if config['kind'] == 'image' and not reason:
            db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)',
                       (now.isoformat(),'action_result',dumps({'id':jid,'status':status})))

    def save_image(self, db, context, now):
        row = db.execute("SELECT r.source_id,r.frame_id,f.evidence_png IS NOT NULL AS saved FROM observations o JOIN runs r ON r.id=o.run_id JOIN frames f ON f.source_id=r.source_id AND f.frame_id=r.frame_id WHERE o.id=? AND o.status!='retention_gap' AND r.source_id=?",
                         (context.get('observation_id'), context.get('source_id'))).fetchone()
        if not row:
            return 'blocked', 'No observation image is available. Run an observation before testing Save image.'
        if row['saved']:
            return 'completed', 'The observation image is already saved in Individual Observations.'
        with self.pipeline.preview_lock:
            candidates = (self.pipeline.processed_previews.get(row['source_id']), self.pipeline.previews.get(row['source_id']))
            image = next((p[1] for p in candidates if p and p[0] == row['frame_id']), None)
        if not image:
            return 'blocked', 'The triggering image is no longer available. No newer image was substituted.'
        db.execute('UPDATE frames SET evidence_png=? WHERE source_id=? AND frame_id=?', (image, row['source_id'], row['frame_id']))
        db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)', (now.isoformat(),'evidence','retained_by_action'))
        return 'completed', 'Saved the observation image in Individual Observations.'

    def test(self, aid, source_id=None):
        with self.lock:
            config = next((a for a in self.definitions() if a['id'] == aid), None)
            if not config:
                raise ValueError('This action no longer exists.')
            context = {'camera': 'Test camera', 'question': 'Action test', 'trigger': 'Manual test', 'automation': 'Manual test'}
            if config['kind'] == 'image':
                if source_id not in self.pipeline.sources:
                    raise ValueError('Choose a camera for the Save image test.')
                context.update(source_id=source_id, camera=self.pipeline.sources[source_id].name or source_id)
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                if config['kind'] == 'image':
                    row = db.execute("SELECT o.id FROM observations o JOIN runs r ON r.id=o.run_id WHERE o.source_id=? AND r.frame_id IS NOT NULL AND o.status!='retention_gap' ORDER BY o.sequence DESC LIMIT 1", (source_id,)).fetchone()
                    context['observation_id'] = row['id'] if row else None
                if db.execute("SELECT 1 FROM action_jobs WHERE action_id=? AND automation_id IS NULL AND created>?", (aid, (utcnow() - timedelta(seconds=5)).isoformat())).fetchone():
                    raise ValueError('Wait 00:00:05 between action tests.')
                self.enqueue(db, 'test-' + uuid4().hex, None, config,
                             context, utcnow())
        self.store.audit('action_test', aid)

    def jobs(self):
        with self.store.connection() as db:
            return [{**dict(r), 'configuration': json.loads(r['configuration']), 'context': json.loads(r['context'])}
                    for r in db.execute('SELECT * FROM action_jobs ORDER BY created DESC,rowid DESC LIMIT 100')]

    def deliver(self, now=None):
        now = utc(now) if now else utcnow()
        with self.lock, self.store.connection() as db:
            if not db.execute("SELECT 1 FROM action_jobs WHERE status IN ('queued','retry') OR (status='sending' AND claim IS NOT NULL AND expires<=?) LIMIT 1", (now.isoformat(),)).fetchone():
                return
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE action_jobs SET status='expired',detail='The action was too old to run.' WHERE status IN ('queued','retry') AND expires<=?", (now.isoformat(),))
            db.execute("UPDATE action_jobs SET status='uncertain',detail='The browser did not confirm playback.' WHERE status='sending' AND claim IS NOT NULL AND expires<=?", (now.isoformat(),))
            row = db.execute("SELECT * FROM action_jobs WHERE status IN ('queued','retry') AND due<=? AND COALESCE(json_extract(configuration,'$.location'),'')!='browser' ORDER BY created,rowid LIMIT 1", (now.isoformat(),)).fetchone()
            if not row:
                return
            config = json.loads(row['configuration'])
            if not self.job_eligible(db, row):
                return
            db.execute("UPDATE action_jobs SET status='sending',attempts=attempts+1 WHERE id=?", (row['id'],))
        try:
            status, detail = self.sender(config, json.loads(row['context']), row['id'])
        except Exception:
            status, detail = 'uncertain', 'The result is unknown. Check the destination before testing again.'
        if status not in ('completed', 'accepted', 'blocked', 'uncertain', 'retry'):
            status, detail = 'blocked', 'The action returned an invalid result.'
        if status == 'retry' and row['attempts'] >= 2:
            status = 'blocked'
        with self.store.connection() as db:
            db.execute('UPDATE action_jobs SET status=?,detail=?,due=? WHERE id=?', (status, detail,
                       (now + timedelta(seconds=10)).isoformat(), row['id']))
        self.store.audit('action_result', dumps({'id': row['id'], 'status': status}))

    def claim_sound(self, client):
        now = utcnow()
        with self.lock, self.store.connection() as db:
            if not db.execute("SELECT 1 FROM action_jobs WHERE status='queued' AND json_extract(configuration,'$.location')='browser' LIMIT 1").fetchone():
                return None
            db.execute('BEGIN IMMEDIATE')
            db.execute("UPDATE action_jobs SET status='expired',detail='No enabled browser played this sound in time.' WHERE status='queued' AND expires<=?", (now.isoformat(),))
            row = db.execute("SELECT * FROM action_jobs WHERE status='queued' AND expires>? AND json_extract(configuration,'$.location')='browser' ORDER BY created,rowid LIMIT 1", (now.isoformat(),)).fetchone()
            if not row:
                return None
            if not self.job_eligible(db, row):
                return None
            db.execute("UPDATE action_jobs SET status='sending',attempts=attempts+1,claim=? WHERE id=?", (client, row['id']))
            return {'id': row['id'], 'config': json.loads(row['configuration'])}

    def job_eligible(self, db, row):
        if not row['automation_id']:
            return True  # Explicit manual test, including synthetic workspaces.
        context = json.loads(row['context'])
        m = db.execute('SELECT configuration FROM automations WHERE id=?', (row['automation_id'],)).fetchone()
        q = db.execute('SELECT enabled,current_version FROM query_controls WHERE source_id=? AND question_id=?',
                       (context['source_id'], context['question_id'])).fetchone()
        control = db.execute('SELECT enabled FROM source_controls WHERE source_id=?', (context['source_id'],)).fetchone()
        paused = db.execute("SELECT value_json FROM release_settings WHERE id='actions_paused'").fetchone()
        reason = ''
        if not m or not json.loads(m[0])['enabled'] or paused and json.loads(paused[0]):
            reason = 'Automation is paused or deleted.'
        elif not q or not q['enabled'] or q['current_version'] != context['question_version'] or not control or not control[0] or context['source_id'] not in self.pipeline.sources:
            reason = 'The camera or question changed. Review the automation.'
        if reason:
            db.execute("UPDATE action_jobs SET status='cancelled',detail=? WHERE id=?", (reason, row['id']))
            return False
        return True

    def acknowledge_sound(self, jid, client, played):
        with self.store.connection() as db:
            db.execute("UPDATE action_jobs SET status=?,detail=? WHERE id=? AND claim=? AND status IN ('sending','uncertain')",
                       ('completed' if played else 'blocked', 'Browser played the sound.' if played else 'Enable sound and check this browser’s audio output.', jid, client))

    def audio(self, aid, digest=None):
        with self.store.connection() as db:
            row = db.execute('SELECT payload FROM action_audio WHERE id=?', (aid,)).fetchone()
            payload = bytes(row[0]) if row else None
            return payload if payload and (digest is None or sha256(payload).hexdigest() == digest) else None

    def send(self, config, context, key):
        kind = config['kind']
        dependency = self.dependency(config)
        if dependency:
            return 'blocked', dependency
        if kind == 'image':
            with self.store.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                return self.save_image(db,context,utcnow())
        if kind in ('beep', 'audio'):
            import winsound
            # Windows wave playback respects the WAV's samples. Beep uses system volume.
            payload = self.audio(config['id'], config.get('audio_digest')) if kind == 'audio' else beep_wav(config['volume'])
            if not payload:
                return 'blocked', 'Choose an audio file in Edit action.'
            if kind == 'audio':
                payload = scale_wav(payload, config['volume'])
            winsound.PlaySound(payload, winsound.SND_MEMORY | winsound.SND_NODEFAULT)
            return 'completed', 'Played on the VOP computer.'
        protected = json.loads(self.secrets.get(config['secret']))
        message = render(config.get('message', ''), context)
        if kind == 'email':
            mail = EmailMessage()
            mail['From'], mail['To'] = protected['from'], protected['to']
            mail['Subject'] = render(config['subject'], context).replace('\n', ' ').replace('\r', ' ')
            mail['Message-ID'] = '<' + sha256(key.encode()).hexdigest() + '@vop.local>'
            mail.set_content(message)
            try:
                with smtplib.SMTP_SSL(config['host'], config['port'], timeout=8, context=ssl.create_default_context()) as smtp:
                    smtp.login(protected['username'], protected['password'])
                    smtp.send_message(mail)
            except (smtplib.SMTPAuthenticationError, smtplib.SMTPRecipientsRefused, smtplib.SMTPSenderRefused):
                return 'blocked', 'Check the SMTP account, sender and recipient in Edit action.'
            return 'accepted', 'The mail server accepted the message. Inbox delivery is not confirmed.'
        if kind == 'sms':
            auth = base64.b64encode((protected['username'] + ':' + protected['password']).encode()).decode()
            url = 'https://api.twilio.com/2010-04-01/Accounts/' + protected['account'] + '/Messages.json'
            request = Request(url, data=urlencode({'From': protected['from'], 'To': protected['to'], 'Body': message}).encode(),
                              headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/x-www-form-urlencoded'})
            try:
                with build_opener(NoRedirect(), ProxyHandler({})).open(request, timeout=8) as response:
                    if response.status == 201:
                        return 'accepted', 'Twilio accepted the text. Handset delivery is not confirmed.'
                    return 'uncertain', 'Check the Twilio delivery log before trying again.'
            except HTTPError as exc:
                if exc.code == 429:
                    return 'retry', 'Twilio is busy; retry scheduled.'
                if exc.code >= 500:
                    return 'uncertain', 'Twilio returned a server error. Check its delivery log before trying again.'
                return 'blocked', 'Check the Twilio account, sender and recipient in Edit action.'
        if kind in ('tapo', 'hub'):
            try:
                asyncio.run(asyncio.wait_for(tapo(config, protected, self.stop_event), timeout=35))
            except Exception:
                return 'uncertain', ('The device did not confirm the result. Check the light or hub before retrying. '
                                     'In Edit action, use Check device. If that fails, check power, LAN address and TP-Link account access.')
            return 'completed', 'The device acknowledged the command.'
        return 'blocked', 'Choose a supported action type.'

    def start(self):
        with self.store.connection() as db:
            db.execute("UPDATE action_jobs SET status='uncertain',detail='VOP restarted before the result was confirmed. Check the destination.' WHERE status='sending'")
            db.execute("UPDATE action_jobs SET status='expired',detail='VOP restarted; old actions were not replayed.' WHERE status IN ('queued','retry')")
            db.execute("UPDATE automations SET state='{}'")
        self.stop_event.clear()
        self.thread = Thread(target=self.loop, name='vop-actions', daemon=True)
        self.thread.start()

    def loop(self):
        while not self.stop_event.is_set():
            try:
                with self.lock:
                    self.evaluate()
                self.deliver()
                self.last_error = self.cleanup_error
                self.cleanup_secrets()
            except Exception:
                self.last_error = 'Actions need attention. Check Activity and the saved automation settings.'
            self.stop_event.wait(0.5)

    def stop(self):
        self.stop_event.set()
        if self.thread:
            self.thread.join(timeout=40)


def render(template, context):
    # Only named literal substitutions, never format expressions or executable templates.
    for name in ('camera', 'question', 'trigger', 'automation'):
        template = template.replace('{' + name + '}', str(context.get(name, '')))
    return template


def matches(value, config):
    if value is None:
        return False
    comparison = config.get('comparison', 'equals')
    if comparison in ('at_least', 'at_most'):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or config.get('value') is None:
            return False
        return value >= config['value'] if comparison == 'at_least' else value <= config['value']
    return value == config['value']


def beep_wav(volume=60):
    import struct
    stream = BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        audio.writeframes(b''.join(struct.pack('<h', int(16000 * volume / 100 * math.sin(2 * math.pi * 880 * n / 16000))) for n in range(4000)))
    return stream.getvalue()


def scale_wav(payload, volume):
    from array import array
    import sys
    with wave.open(BytesIO(payload), 'rb') as audio:
        params = audio.getparams()
        samples = array('h', audio.readframes(audio.getnframes()))
    if sys.byteorder != 'little':
        samples.byteswap()
    for i, value in enumerate(samples):
        samples[i] = int(value * volume / 100)
    if sys.byteorder != 'little':
        samples.byteswap()
    stream = BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setparams(params)
        audio.writeframes(samples.tobytes())
    return stream.getvalue()


def detach_question(db, sid, qid=None, *, erase=False):
    """Called inside existing removal transactions; compatible with pre-actions stores."""
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='automations'").fetchone():
        return
    for row in db.execute('SELECT id,configuration,revision FROM automations').fetchall():
        config = json.loads(row['configuration'])
        if config['source_id'] == sid and (qid is None or config['question_id'] == qid):
            config['enabled'] = False
            db.execute("UPDATE automations SET configuration=?,revision=?,state='{}' WHERE id=?", (dumps(config), row['revision'] + 1, row['id']))
    where = "json_extract(context,'$.source_id')=?" + (" AND json_extract(context,'$.question_id')=?" if qid is not None else '')
    params = (sid, qid) if qid is not None else (sid,)
    if erase:
        db.execute('DELETE FROM action_jobs WHERE ' + where, params)
    else:
        db.execute("UPDATE action_jobs SET status='cancelled',detail='Camera or question removed.' WHERE status IN ('queued','retry') AND " + where, params)


async def tapo(config, protected, stopped):
    from kasa import Discover
    device = await Discover.discover_single(config['address'], username=protected['username'], password=protected['password'], timeout=4)
    if device is None:
        raise ValueError('Light not found.')
    try:
        await device.update()
        # Do not switch arbitrary plugs; require a device that identifies as a light.
        from kasa import DeviceType, Module
        if config['kind'] == 'hub':
            if device.device_type != DeviceType.Hub or Module.Alarm not in device.modules:
                raise ValueError('This device has no supported hub alarm.')
            alarm = device.modules[Module.Alarm]
            sound = config.get('sound') or None
            if sound and sound not in alarm.alarm_sounds:
                raise ValueError('Check the available sounds for this hub.')
            await alarm.play(duration=int(config['seconds']), volume=config['volume'], sound=sound)
            return
        if device.device_type not in (DeviceType.Bulb, DeviceType.LightStrip):
            raise ValueError('This device is not a supported light.')
        if config['operation'] != 'off' and (config.get('brightness') or config.get('colour')):
            light = device.modules[Module.Light]
            if config.get('colour'):
                from colorsys import rgb_to_hsv
                colour = config['colour'].lstrip('#')
                h, s, v = rgb_to_hsv(*(int(colour[i:i + 2], 16) / 255 for i in (0, 2, 4)))
                await light.set_hsv(int(h * 360), int(s * 100), int(config['brightness']) if config.get('brightness') else None)
            elif config.get('brightness'):
                await light.set_brightness(int(config['brightness']))
        if config['operation'] == 'on':
            await device.turn_on()
        elif config['operation'] == 'off':
            await device.turn_off()
        else:
            # Bounded on/off pulses, finishing OFF; never restore an old user state.
            needs_off = False
            try:
                for _ in range(int(config['seconds'] / 2)):
                    if stopped.is_set():
                        break
                    needs_off = True
                    await device.turn_on()
                    await asyncio.sleep(1)
                    await device.turn_off()
                    needs_off = False
                    await asyncio.sleep(1)
            finally:
                if needs_off:
                    await device.turn_off()
    finally:
        await device.disconnect()


async def tapo_info(config, protected):
    from kasa import Discover, Module
    device = await Discover.discover_single(config['address'], username=protected['username'], password=protected['password'], timeout=4)
    if device is None:
        raise ValueError('Device not found.')
    try:
        await device.update()
        expected = 'H100' if config['kind'] == 'hub' else 'L530'
        if not device.model.startswith(expected):
            raise ValueError('This action requires ' + expected)
        return {'address': config['address'], 'model': device.model,
                'sounds': list(device.modules[Module.Alarm].alarm_sounds) if config['kind'] == 'hub' else []}
    finally:
        await device.disconnect()
