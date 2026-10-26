"""Synthetic regression checks for repeated work in hot loops."""
from collections import Counter
from contextlib import contextmanager
from datetime import timedelta
import json
import pytest

from starlette.testclient import TestClient

from test_phase3_release import app, samples, rule, SID, QID, HEADERS
from vop.contracts import utcnow
from vop.storage import Store


def traced(store, monkeypatch):
    statements = []
    original = store.connection
    @contextmanager
    def connection():
        with original() as db:
            db.set_trace_callback(statements.append)
            try:
                yield db
            finally:
                db.set_trace_callback(None)
    monkeypatch.setattr(store, 'connection', connection)
    return statements


def test_alert_cycle_reuses_question_replay_and_only_loads_provenance_for_new_alerts(app, monkeypatch):
    store, reliable = app.state.store, app.state.reliable
    now = utcnow()
    samples(app, now - timedelta(seconds=30), [True, True, True], step=10)
    for i in range(8):
        reliable.save_rule(rule(id=f'loop-rule-{i}', threshold=0))
    calls = Counter()
    for name in ('questions','summary','source_control','observation'):
        original = getattr(store, name)
        def counted(*args, _name=name, _original=original, **kwargs):
            calls[_name] += 1
            return _original(*args, **kwargs)
        monkeypatch.setattr(store, name, counted)
    reliable.evaluate(now)
    assert calls == {'questions':1,'summary':1,'source_control':1,'observation':1}
    assert len(reliable.alerts()) == 8
    calls.clear()
    reliable.evaluate(now)
    assert calls == {'questions':1,'summary':1,'source_control':1}
    # Cycle-local reuse must not hide a new disabled state or a new question version.
    record = store.questions(SID)[0]
    store.edit_question(SID, record['spec'], record['policy'], enabled=False)
    calls.clear()
    reliable.evaluate(now)
    assert calls['summary'] == 1
    with store.connection() as db:
        assert not db.execute('SELECT 1 FROM rule_states WHERE id LIKE ? AND active=1', ('%:2:%',)).fetchone()
    assert len(reliable.alerts()) == 8


def test_retention_does_not_rewrite_already_cleared_history(app, monkeypatch):
    store, reliable = app.state.store, app.state.reliable
    now = utcnow()
    samples(app, now - timedelta(days=3), [True, True, True], step=10)
    days = {'evidence':1,'raw':1,'audit':30}
    first = reliable.retention(days, apply=True, now=now + timedelta(days=4))
    assert first['counts']['raw'] == 3
    sql = traced(store, monkeypatch)
    second = reliable.retention(days, apply=True, now=now + timedelta(days=4))
    assert second['counts']['raw'] == 0
    assert not any(statement.startswith(('UPDATE runs SET result_json=', 'UPDATE observations SET answer_json=')) for statement in sql)
    assert store.health()['observation_count'] == 9


@pytest.mark.parametrize('alert_count', [12, 905])
def test_alert_list_batches_deliveries_instead_of_querying_each_alert(app, monkeypatch, alert_count):
    reliable, store = app.state.reliable, app.state.store
    now = utcnow()
    samples(app, now - timedelta(seconds=30), [True, True, True], step=10)
    reliable.save_rule(rule(threshold=0))
    reliable.evaluate(now)
    with store.connection() as db:
        template = dict(db.execute('SELECT * FROM alerts LIMIT 1').fetchone())
        for i in range(alert_count - 1):
            row = {**template, 'id':f'listed-alert-{i}'}
            payload = json.loads(row['payload_json']); payload['id'] = row['id']
            row['payload_json'] = json.dumps(payload)
            db.execute('INSERT INTO alerts VALUES(' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            db.execute('INSERT INTO deliveries SELECT ?,channel,status,attempts,next_attempt_utc FROM deliveries WHERE alert_id=?', (row['id'], template['id']))
    sql = traced(store, monkeypatch)
    alerts = reliable.alerts()
    assert len(alerts) == alert_count and all(len(a['deliveries']) == 1 for a in alerts)
    assert len([q for q in sql if q.startswith('SELECT')]) == (2 if alert_count <= 900 else 3)


def test_history_and_latest_image_lookups_use_matching_indexes_after_reopen(app):
    store = Store(app.state.store.path)
    with store.connection() as db:
        history = db.execute('EXPLAIN QUERY PLAN SELECT * FROM observations WHERE source_id=? AND question_id=? AND question_version=? ORDER BY sequence', (SID,QID,'1')).fetchall()
        latest = db.execute('EXPLAIN QUERY PLAN SELECT frame_id,evidence_png,captured_at_utc FROM frames WHERE source_id=? AND evidence_png IS NOT NULL ORDER BY captured_at_utc DESC LIMIT 1', (SID,)).fetchall()
        assert any('observations_question' in row[3] and 'SEARCH' in row[3] for row in history)
        assert any('frames_latest_evidence' in row[3] and 'SEARCH' in row[3] for row in latest)
        assert not any('TEMP B-TREE' in row[3] for row in (*history,*latest))


def test_camera_answer_rows_use_one_native_answer_query(app, monkeypatch):
    now = utcnow()
    samples(app, now - timedelta(seconds=30), [True, True, True], step=10)
    monkeypatch.setattr(app.state.sampler, 'start', lambda: None)
    monkeypatch.setattr(app.state.reliable, 'start', lambda: None)
    with TestClient(app) as client:
        sql = traced(app.state.store, monkeypatch)
        response = client.get('/ui/camera-answers/' + SID, headers=HEADERS)
        assert response.status_code == 200 and 'Episode State' in response.text
        assert len([q for q in sql if q.startswith('SELECT id,answer_json FROM observations WHERE id IN')]) == 1
        assert not any(q.startswith('SELECT answer_json FROM observations WHERE id=') for q in sql)


def test_history_preview_counts_saved_images_with_one_aggregate(app, monkeypatch):
    from vop.history_deletion import selection
    now = utcnow()
    store = app.state.store
    store.update_source(SID, enabled=True, retain_evidence=True, sample_interval_seconds=0)
    frames = samples(app, now - timedelta(seconds=100), [True] * 8, step=10)
    sql = traced(store, monkeypatch)
    with store.connection() as db:
        chosen = selection(db, source_id=SID)
        assert chosen['counts']['images'] == len(frames)
        assert len([q for q in sql if q.startswith('SELECT count(*) FROM runs r JOIN frames')]) == 1
        assert not any(q.startswith('SELECT 1 FROM frames WHERE') for q in sql)


def test_backup_and_restore_hash_without_loading_database_into_memory(app, tmp_path, monkeypatch):
    from pathlib import Path
    from vop.reliable import backup, configuration, restore
    reliable, store = app.state.reliable, app.state.store
    def forbidden(*args, **kwargs):
        raise AssertionError('Backup/restore must stream hashes, never read an entire database into RAM')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    bundle = configuration(reliable.settings, store, reliable)
    saved = backup(store, bundle, tmp_path / 'streamed-backup')
    restored = restore(saved, tmp_path / 'streamed-restore')
    assert restored.is_file()


def test_streaming_hash_uses_bounded_buffers(tmp_path, monkeypatch):
    from pathlib import Path
    from hashlib import sha256
    from vop.reliable import file_sha256
    target = tmp_path / 'synthetic-large-file'
    chunk = b'synthetic-hash-data' * 4096
    expected = sha256()
    with target.open('wb') as stream:
        for _ in range(48):
            stream.write(chunk); expected.update(chunk)
    original = Path.open
    reads = []
    class GuardedFile:
        def __enter__(self):
            self.stream = original(target, 'rb'); return self
        def __exit__(self, *args):
            self.stream.close()
        def readable(self):
            return True
        def readinto(self, buffer):
            reads.append(len(buffer))
            assert len(buffer) <= 256 * 1024
            return self.stream.readinto(buffer)
    monkeypatch.setattr(Path, 'open', lambda *args, **kwargs: GuardedFile())
    assert file_sha256(target) == expected.hexdigest()
    assert len(reads) > 1
