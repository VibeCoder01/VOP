"""Offline monitoring write contention and error remediation."""
import asyncio
import sqlite3
from threading import Event

import httpx2 as httpx
import pytest
from starlette.testclient import TestClient
from test_phase3_release import app, HEADERS, SID
from vop.monitoring import change_monitoring, retry_busy


def test_monitor_retries_only_failed_step_and_preserves_saved_interval(app,monkeypatch):
    store=app.state.store
    store.update_source(SID, enabled=True,retain_evidence=False,sample_interval_seconds=20)
    update=store.update_source
    calls={'update':0,'gap':0}
    def write(*a,**kw):
        calls['update']+=1
        if calls['update']<3:raise sqlite3.OperationalError('database is locked')
        return update(*a,**kw)
    def gap(*a):
        calls['gap']+=1
        if calls['gap']<2:raise sqlite3.OperationalError('database is locked')
    monkeypatch.setattr(store,'update_source',write)
    monkeypatch.setattr(app.state.pipeline,'record_gap',gap)
    assert change_monitoring(app,SID,False)
    assert calls=={'update':3,'gap':2}
    assert store.source_control(SID)['sample_interval_seconds']==0
    assert not change_monitoring(app,SID,True)
    assert store.source_control(SID)['sample_interval_seconds']==20


def test_busy_retry_is_bounded_and_other_storage_errors_are_not_retried():
    calls=[]
    def busy():calls.append(1);raise sqlite3.OperationalError('database is locked')
    with pytest.raises(sqlite3.OperationalError):retry_busy(busy)
    assert len(calls)==3
    calls.clear()
    def bad():calls.append(1);raise sqlite3.OperationalError('disk I/O error')
    with pytest.raises(sqlite3.OperationalError):retry_busy(bad)
    assert len(calls)==1


def test_readable_browser_error_and_api_error_keep_partial_pause_visible(app,monkeypatch):
    monkeypatch.setattr(app.state.pipeline,'record_gap',lambda *a: (_ for _ in ()).throw(sqlite3.OperationalError('database is locked')))
    client=TestClient(app,headers=HEADERS)
    response=client.post('/ui/sources/'+SID+'/monitor',data={'mode':'pause'},headers={'Accept':'text/html'})
    assert response.status_code==503
    assert 'busy saving other work' in response.text and 'may already have been saved' in response.text
    assert 'Return to workspace' in response.text
    assert app.state.store.source_control(SID)['sample_interval_seconds']==0
    response=client.post('/ui/sources/'+SID+'/monitor',data={'mode':'pause'})
    assert response.status_code==503 and response.json()['error']=='storage_unavailable'
    assert 'message' in response.json()


def test_monitor_wait_does_not_block_health_on_the_same_event_loop(app,monkeypatch):
    entered,release=Event(),Event()
    original=app.state.store.update_source
    def delayed(*a,**kw):
        entered.set()
        assert release.wait(5)
        return original(*a,**kw)
    monkeypatch.setattr(app.state.store,'update_source',delayed)
    monkeypatch.setattr(app.state.pipeline,'record_gap',lambda *a:None)
    monkeypatch.setattr(app.state.worker_session,'stop',lambda:None)
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',headers=HEADERS) as client:
            task=asyncio.create_task(client.post('/ui/sources/'+SID+'/monitor',data={'mode':'pause'}))
            try:
                assert await asyncio.to_thread(entered.wait,2)
                health=await asyncio.wait_for(client.get('/api/v1/health'),2)
                assert health.status_code==200
            finally:release.set()
            assert (await task).status_code==303
    asyncio.run(scenario())
