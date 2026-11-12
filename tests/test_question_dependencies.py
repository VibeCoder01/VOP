"""Offline dependency preview and transactional deletion; never deliver actions."""
import json
import pytest
from starlette.testclient import TestClient
from test_question_data_deletion import app, login, SID, QID, URL, fields
from test_actions import sound, automation
from vop.history_deletion import question_selection, delete_question_data
from vop.storage import dumps


def setup(app):
    actions=app.state.actions
    sound(actions)
    automation(actions,id='target-auto',name='Target automation')
    automation(actions,id='other-auto',name='Other automation',question_id='background',trigger='value',value='white')
    app.state.reliable.save_rule({'id':'target-rule','source_id':SID,'question_id':QID,'kind':'duration'})
    app.state.reliable.save_rule({'id':'other-rule','source_id':SID,'question_id':'background','kind':'source_offline'})


def test_preview_lists_dependencies_and_confirmation_rechecks_new_automations(app):
    setup(app)
    client=TestClient(app);csrf=login(client)
    preview=client.get(URL)
    assert 'Automation: Target automation' in preview.text and 'Notification rule: target-rule' in preview.text
    assert 'Other automation' not in preview.text
    old=fields(preview)
    automation(app.state.actions,id='new-auto',name='Added after preview')
    changed=client.post(URL,data=old)
    assert 'automations or notification rules changed' in changed.text
    assert len(app.state.actions.automations())==3
    assert client.post(URL,data=fields(changed)).status_code==200
    assert [m['id'] for m in app.state.actions.automations()]==['other-auto']
    assert [r['id'] for r in app.state.reliable.rules()]==['other-rule']
    assert app.state.actions.definitions()[0]['id']=='bell'
    with app.state.store.connection() as db:
        assert not db.execute("SELECT 1 FROM rule_versions WHERE json_extract(configuration,'$.question_id')=?",(QID,)).fetchone()
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='immutable_rule_delete'").fetchone()


def test_dependency_purge_rolls_back_and_preserves_moved_rule(app):
    setup(app)
    # Old revision references the deleted question; current rule belongs elsewhere.
    app.state.reliable.save_rule({'id':'moved','source_id':SID,'question_id':QID,'kind':'duration'})
    app.state.reliable.save_rule({'id':'moved','source_id':SID,'question_id':'background','kind':'source_offline'})
    store=app.state.store
    with store.connection() as db:
        db.execute('INSERT INTO rule_states VALUES(?,?,?)',('moved:1:sample',0,1))
        db.execute('INSERT INTO rule_states VALUES(?,?,?)',('moved:2:sample',1,2))
    with pytest.raises(RuntimeError):
        with store.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            delete_question_data(db,question_selection(db,SID,QID))
            raise RuntimeError('rollback')
    assert len(app.state.actions.automations())==2
    assert len(app.state.reliable.rules())==3
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        delete_question_data(db,question_selection(db,SID,QID))
    assert {r['id'] for r in app.state.reliable.rules()}=={'other-rule','moved'}
    with store.connection() as db:
        assert db.execute("SELECT revision FROM rule_versions WHERE id='moved'").fetchall()[0][0]==2
        assert not db.execute("SELECT 1 FROM rule_states WHERE id='moved:1:sample'").fetchone()
        assert db.execute("SELECT 1 FROM rule_states WHERE id='moved:2:sample'").fetchone()


def test_deletion_erases_target_jobs_but_keeps_unrelated_history_and_actions(app):
    setup(app)
    actions,store=app.state.actions,app.state.store
    config=actions.definitions()[0]
    from vop.contracts import utcnow
    with store.connection() as db:
        for jid,mid,qid in [('target-job','target-auto',QID),('old-history','target-auto','background'),('old-queued','target-auto','background'),('other-job','other-auto','background')]:
            actions.enqueue(db,jid,mid,config,{'source_id':SID,'question_id':qid},utcnow())
        db.execute("UPDATE action_jobs SET status='completed' WHERE id='old-history'")
        delete_question_data(db,question_selection(db,SID,QID))
    jobs={j['id']:j['status'] for j in actions.jobs()}
    assert 'target-job' not in jobs
    assert jobs=={'old-history':'completed','old-queued':'cancelled','other-job':'queued'}
    assert [m['id'] for m in actions.automations()]==['other-auto']
    assert actions.definitions()[0]['id']=='bell'
