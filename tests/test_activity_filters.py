"""Offline Activity filtering; no actions are delivered."""
from datetime import datetime, timezone, timedelta

import pytest
from starlette.testclient import TestClient
from bs4 import BeautifulSoup
from test_phase3_release import app, HEADERS
from vop.storage import dumps


def test_filters_apply_before_limit_and_refresh_keeps_query(app):
    actions = app.state.actions
    with app.state.store.connection() as db:
        for i in range(105):
            stamp = datetime(2026, 11, 4, tzinfo=timezone.utc) + timedelta(minutes=i)
            db.execute("INSERT INTO action_jobs(id,automation_id,action_id,created,expires,due,status,attempts,configuration,context,detail) VALUES(?,?,?,?,?,?,?,0,?,?,?)",
                (str(i), 'old-rule' if i == 0 else 'new-rule', 'old-action' if i == 0 else 'new-action',
                 stamp.isoformat(), stamp.isoformat(), stamp.isoformat(), 'uncertain' if i == 0 else 'completed',
                 dumps({'kind':'beep','name':'Old bell' if i == 0 else 'New bell'}),
                 dumps({'automation':'Old automation' if i == 0 else 'New automation'}), 'Recorded result'))
    assert len(actions.jobs()) == 100
    filters = {'action':'old-action','automation':'old-rule','result':'uncertain','from':'2026-11-04','to':'2026-11-04'}
    assert [j['id'] for j in actions.jobs(filters)] == ['0']
    assert len(actions.jobs({'details':'recorded RESULT'})) == 100
    assert not actions.jobs({'details':'unmatched'})
    assert not actions.jobs({'details':'%'})
    assert not actions.jobs({'from':'2026-11-05'})
    assert not actions.jobs({'to':'2026-11-03'})
    assert not actions.jobs({'action':"' OR 1=1 --"})
    with pytest.raises(ValueError):
        actions.jobs({'from':'invalid'})
    with pytest.raises(ValueError):
        actions.jobs({'from':'2026-11-05','to':'2026-11-04'})
    # No lifespan is started: sampling and physical delivery stay stopped.
    client = TestClient(app, headers=HEADERS)
    response = client.get('/activity', params=filters)
    assert response.status_code == 200
    soup = BeautifulSoup(response.text, 'html.parser')
    pause = soup.select_one('form.activity-pause')
    assert pause and not pause.has_attr('style')
    assert len(soup.select('thead tr.activity-column-filters td')) == 4
    assert soup.select_one('thead input[name=details]')
    assert not soup.select_one('[data-action-activity] input')
    assert soup.select_one('select[name=action] option[selected]')['value'] == 'old-action'
    table = soup.select_one('[data-action-activity]')
    assert 'Queued at' in soup.select_one('thead').text and 'Old bell' in table.text and 'New bell' not in table.text
    rows = client.get('/activity/rows', params=filters)
    assert 'Old bell' in rows.text and 'New bell' not in rows.text
    assert 'Choose valid dates' in client.get('/activity/rows?from=invalid').text
    assert "location.search" in client.get('/ui/actions.js').text
