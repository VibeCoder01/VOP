"""Remove test records when opening the explicitly selected live workspace."""
from dataclasses import replace
import json

from vop.contracts import utcnow
from vop.storage import dumps


def real_profile(value):
    return value.get('kind') == 'worker' and not value.get('synthetic', False)


def prepare(store, settings):
    from vop.inference.liquid_d1 import CHECKPOINT_REVISION
    fallback = {'kind': 'worker', 'id': 'liquid-d1-3b', 'version': CHECKPOINT_REVISION,
                'worker_id': 'antec-d1', 'url': 'http://127.0.0.1:8878', 'transport': 'ssh',
                'secret_ref': 'antec-worker', 'synthetic': False}
    counts = {'inputs': 0, 'captures': 0, 'alerts': 0, 'rules': 0, 'engines': 0, 'audit': 0}
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        test_sources = {r['id'] for r in db.execute('SELECT * FROM sources') if json.loads(r['configuration'])['kind'] == 'synthetic'}
        counts['inputs'] = len(test_sources)
        affected_sources = set()
        # Only deletion triggers are suspended, within this transaction, for test-only
        # configuration. Real immutable versions are never changed or deleted.
        triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger' AND name IN ('immutable_question_delete','immutable_rule_delete')").fetchall()
        for trigger in triggers:
            db.execute('DROP TRIGGER ' + trigger['name'])
        for row in db.execute('SELECT * FROM runs').fetchall():
            result = json.loads(row['result_json'])
            if row['source_id'] not in test_sources and (not result.get('synthetic') or result.get('status') == 'retention_gap'):
                continue
            counts['captures'] += 1
            affected_sources.add(row['source_id'])
            if row['source_id'] in test_sources:
                db.execute('DELETE FROM observations WHERE run_id=?', (row['id'],))
                db.execute('DELETE FROM runs WHERE id=?', (row['id'],))
            else:
                # Timestamp-only gaps keep real history from joining across removed tests.
                marker = {'status': 'retention_gap', 'source_id': row['source_id'], 'frame_id': None,
                          'engine_id': 'retention-gap', 'engine_version': '1', 'synthetic': False,
                          'elapsed_ms': None, 'usage': None, 'provider_raw': None, 'answers': []}
                db.execute('UPDATE runs SET frame_id=NULL,result_json=? WHERE id=?', (dumps(marker), row['id']))
                db.execute("UPDATE observations SET status='retention_gap',normalised_state='unknown',answer_json=? WHERE run_id=?", (dumps({'value': None}), row['id']))
            if row['frame_id']:
                db.execute('DELETE FROM frames WHERE source_id=? AND frame_id=?', (row['source_id'], row['frame_id']))
        for row in db.execute('SELECT * FROM alerts').fetchall():
            if row['source_id'] in test_sources or json.loads(row['payload_json']).get('synthetic'):
                db.execute('DELETE FROM deliveries WHERE alert_id=?', (row['id'],))
                db.execute('DELETE FROM alerts WHERE id=?', (row['id'],))
                counts['alerts'] += 1
        for row in db.execute('SELECT * FROM rules').fetchall():
            if json.loads(row['configuration'])['source_id'] in test_sources:
                db.execute('DELETE FROM rule_states WHERE substr(id,1,?)=?', (len(row['id']) + 1, row['id'] + ':'))
                db.execute('DELETE FROM rule_versions WHERE id=?', (row['id'],))
                db.execute('DELETE FROM rules WHERE id=?', (row['id'],))
                counts['rules'] += 1
        db.execute('DELETE FROM mock_values')
        for row in db.execute('SELECT sequence,outcome FROM audit').fetchall():
            try:
                outcome = json.loads(row['outcome'])
            except ValueError:
                continue
            if isinstance(outcome, dict) and outcome.get('source_id') in test_sources:
                db.execute('DELETE FROM audit WHERE sequence=?', (row['sequence'],))
                counts['audit'] += 1
        for sid in test_sources:
            for table in ('events', 'query_controls', 'query_policies', 'question_versions', 'source_controls'):
                db.execute(f'DELETE FROM {table} WHERE source_id=?', (sid,))
            db.execute('DELETE FROM frames WHERE source_id=?', (sid,))
            db.execute('DELETE FROM sources WHERE id=?', (sid,))
            for row in db.execute('SELECT id,value_json FROM release_settings').fetchall():
                if row['id'].split(':')[1:2] == [sid]:
                    db.execute('DELETE FROM release_settings WHERE id=?', (row['id'],))
        for sid in affected_sources - test_sources:
            db.execute('UPDATE sources SET last_frame_utc=(SELECT MAX(captured_at_utc) FROM frames WHERE source_id=?) WHERE id=?', (sid, sid))
        for row in db.execute("SELECT id,value_json FROM release_settings WHERE id LIKE 'saved_engine:%'").fetchall():
            if not real_profile(json.loads(row['value_json'])['profile']):
                db.execute('DELETE FROM release_settings WHERE id=?', (row['id'],))
                counts['engines'] += 1
        row = db.execute("SELECT value_json FROM release_settings WHERE id='engine_profile'").fetchone()
        profile = json.loads(row[0]) if row else settings.engine or {}
        if not real_profile(profile):
            profile = fallback
            db.execute("INSERT OR REPLACE INTO release_settings VALUES('engine_profile',?)", (dumps(profile),))
            db.execute("DELETE FROM release_settings WHERE id='active_engine_profile_id'")
        for trigger in triggers:
            db.execute(trigger['sql'])
        if any(counts.values()):
            db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)', (utcnow().isoformat(), 'workspace_cleanup', dumps(counts)))
    return replace(settings, sources=tuple(s for s in settings.sources if s.kind != 'synthetic'),
                   engine=profile, engine_id=profile['id'], mock_answers={}), counts
