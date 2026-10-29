"""Deletion/resource lifecycle contracts use disposable metadata and fake vaults."""
import json
import sqlite3

import pytest

from test_phase4_worker import app
from test_history_deletion import captures, SID
from vop.actions import Actions
from vop.deletion_audit import audit
from vop.history_deletion import selection, delete_selected, question_selection, delete_question_data
from vop.secret_cleanup import PREFIX, queue
from vop.storage import dumps


class Vault:
    def __init__(self): self.values, self.fail = {}, False
    def set(self, key, value): self.values[key] = value
    def get(self, key): return self.values[key]
    def delete(self, key):
        if self.fail: raise OSError('fixture locked vault')
        self.values.pop(key, None)


def account(app):
    actions = app.state.actions
    actions.secrets = Vault()
    actions.save_action({'id':'mail','kind':'email','name':'Mail','host':'smtp.example.test','port':465},
                        protected={'username':'fixture','password':'fixture','from':'a@example.test','to':'b@example.test'})
    return actions


def pending(store):
    with store.connection() as db:
        return db.execute("SELECT count(*) FROM release_settings WHERE id LIKE 'pending_secret_delete:%'").fetchone()[0]


def test_action_deletion_cleans_protected_account_but_keeps_cancelled_snapshot(app, monkeypatch):
    actions = account(app)
    monkeypatch.setattr(actions, 'dependency', lambda _: '')
    actions.test('mail')
    actions.delete('action', 'mail')
    assert not actions.definitions() and not actions.secrets.values and pending(actions.store) == 0
    assert actions.jobs()[0]['status'] == 'cancelled'
    assert actions.jobs()[0]['configuration']['name'] == 'Mail'


def test_shared_protected_value_survives_until_last_owner_is_deleted(app):
    actions = account(app)
    with actions.store.connection() as db:
        db.execute('INSERT INTO release_settings VALUES(?,?)', ('saved_engine:shared', dumps({'profile':{'secret_ref':'action-mail'}})))
    actions.delete('action', 'mail')
    assert 'action-mail' in actions.secrets.values
    with actions.store.connection() as db:
        db.execute("DELETE FROM release_settings WHERE id='saved_engine:shared'")
        queue(db, 'action-mail')
    actions.cleanup_secrets()
    assert not actions.secrets.values and pending(actions.store) == 0


def test_inflight_action_keeps_its_key_until_delivery_finishes(app, monkeypatch):
    actions = account(app)
    monkeypatch.setattr(actions, 'dependency', lambda _: '')
    actions.test('mail')
    with actions.store.connection() as db: db.execute("UPDATE action_jobs SET status='sending'")
    actions.delete('action', 'mail')
    assert pending(actions.store) == 1 and 'action-mail' in actions.secrets.values
    with actions.store.connection() as db: db.execute("UPDATE action_jobs SET status='completed'")
    actions.cleanup_secrets()
    assert not actions.secrets.values and pending(actions.store) == 0


def test_vault_failure_cleanup_survives_restart_and_does_not_replay_action(app):
    actions = account(app)
    actions.secrets.fail = True
    actions.delete('action', 'mail')
    assert not actions.definitions() and pending(actions.store) == 1
    assert actions.cleanup_error
    fresh = Actions(actions.store, actions.pipeline, secrets=actions.secrets)
    actions.secrets.fail = False
    fresh.cleanup_secrets()
    assert not fresh.secrets.values and pending(actions.store) == 0
    assert not fresh.jobs() and fresh.cleanup_error is None


def test_failed_entity_transaction_never_deletes_its_key(app):
    actions = account(app)
    with actions.store.connection() as db:
        db.execute("CREATE TRIGGER fixture_fail BEFORE DELETE ON action_definitions BEGIN SELECT RAISE(ABORT,'fixture rollback'); END")
    with pytest.raises(sqlite3.IntegrityError): actions.delete('action', 'mail')
    assert actions.definitions() and 'action-mail' in actions.secrets.values and pending(actions.store) == 0


def test_os_vault_cleanup_does_not_hold_database_writer_lock(app):
    actions = account(app)
    original = actions.secrets.delete
    def remove(key):
        with actions.store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.rollback()
        original(key)
    actions.secrets.delete = remove
    actions.delete('action', 'mail')
    assert not actions.secrets.values and pending(actions.store) == 0


def test_dashboard_key_is_never_removed_by_entity_cleanup(app):
    actions = account(app)
    actions.secrets.set('dashboard-access-key', 'fixture')
    with actions.store.connection() as db: queue(db, 'dashboard-access-key')
    actions.cleanup_secrets()
    assert actions.secrets.get('dashboard-access-key') == 'fixture'


def test_no_pending_cleanup_never_reserves_capture_worker(app, monkeypatch):
    def fail(*args, **kwargs): pytest.fail('No cleanup work must not reserve capture')
    monkeypatch.setattr(app.state.pipeline, 'busy', type('Busy', (), {'acquire': fail})())
    app.state.actions.cleanup_secrets()


def test_whole_history_deletion_includes_empty_runs_and_unreferenced_images(app):
    runs = captures(app, 2)
    store = app.state.store
    with store.connection() as db:
        for run, _ in runs: db.execute('DELETE FROM observations WHERE run_id=?', (run,))
        db.execute('DELETE FROM runs WHERE id=?', (runs[1][0],))
        assert audit(db)['issues']['unreferenced_frames'] == 1
        chosen = selection(db, source_id=SID)
        assert chosen['counts']['captures'] == 1 and chosen['counts']['images'] == 2
        delete_selected(db, chosen, whole_source=True)
        for key in chosen['keys']: store._rebuild(db, *key)
        for table in ('runs', 'observations', 'frames', 'events'):
            assert db.execute(f'SELECT count(*) FROM {table} WHERE source_id=?', (SID,)).fetchone()[0] == 0
        assert audit(db)['result'] == 'PASS'


def test_question_data_delete_also_erases_configured_test_answer(app):
    captures(app, 1)
    with app.state.store.connection() as db:
        db.execute('INSERT OR REPLACE INTO mock_values VALUES(?,?,?,?)', (SID,'red_square','1','true'))
        delete_question_data(db, question_selection(db, SID, 'red_square'))
        assert not db.execute('SELECT 1 FROM mock_values WHERE source_id=? AND question_id=?', (SID,'red_square')).fetchone()
        assert db.execute('SELECT 1 FROM observations WHERE source_id=? AND question_id!=?', (SID,'red_square')).fetchone()
        assert audit(db)['result'] == 'PASS'


def test_audit_is_read_only_and_detects_missing_audio(app):
    with app.state.store.connection() as db:
        db.execute('INSERT INTO action_audio VALUES(?,?)', ('missing-definition', b'fixture'))
    with app.state.store.connection() as db:
        db.execute('PRAGMA query_only=ON')
        result = audit(db)
        assert result['result'] == 'NEEDS_ATTENTION' and result['issues']['audio_without_action'] == 1
