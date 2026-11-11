"""Synthetic, differently coloured frames and intercepted SMTP only."""
from dataclasses import replace
from hashlib import sha256
from io import BytesIO

from PIL import Image
import pytest
from starlette.testclient import TestClient
from bs4 import BeautifulSoup
from test_phase3_release import app, HEADERS, SID, QID
from test_actions import Vault
from vop.contracts import utcnow
from vop.inputs.sources import capture_inline


def frame(app, colour):
    f = capture_inline(app.state.pipeline.sources[SID])
    out = BytesIO()
    Image.new('RGB', (f.width, f.height), colour).save(out, format='PNG')
    f = replace(f, payload=out.getvalue(), sha256=sha256(out.getvalue()).hexdigest())
    app.state.pipeline.run(SID, f)
    with app.state.store.connection() as db:
        oid = db.execute('SELECT id FROM observations WHERE source_id=? ORDER BY sequence DESC LIMIT 1',(SID,)).fetchone()[0]
    return f, {'source_id':SID,'observation_id':oid,'camera':'Synthetic camera','question':'Test <question>','trigger':'Answer becomes Yes'}


@pytest.fixture
def mail(app, monkeypatch):
    actions = app.state.actions
    actions.secrets = Vault()
    actions.save_action({'id':'mail','kind':'email','name':'Image email','host':'smtp.example.test','port':465,
        'message':'Before <script>\n{image}\n{trigger}\n{image}'}, protected={'username':'test','password':'test','from':'a@example.test','to':'b@example.test'})
    sent = []
    class SMTP:
        def __init__(self,*a,**kw): pass
        def __enter__(self): return self
        def __exit__(self,*a): pass
        def login(self,*a): pass
        def send_message(self,m): sent.append(m)
    monkeypatch.setattr('vop.actions.smtplib.SMTP_SSL',SMTP)
    return actions.definitions()[0], sent


def test_exact_trigger_image_is_pinned_and_emailed_after_new_frames(app,mail):
    config,sent = mail
    app.state.pipeline.sources[SID] = replace(app.state.pipeline.sources[SID], settings={**app.state.pipeline.sources[SID].settings,'privacy_masks':[[0,0,.5,1]]})
    frame(app,'red')
    trigger,context = frame(app,'green')
    expected = app.state.pipeline.processed_previews[SID][1]
    with app.state.store.connection() as db:
        app.state.actions.enqueue(db,'image-email',None,config,context,utcnow())
    assert app.state.actions.jobs()[0]['status'] == 'queued'
    assert app.state.store.evidence(SID,trigger.frame_id) == expected
    frame(app,'blue')
    assert app.state.actions.send(config,context,'image-email')[0] == 'accepted'
    images = [p for p in sent[0].walk() if p.get_content_type() == 'image/png']
    assert len(images) == 1 and images[0].get_payload(decode=True) == expected
    img = Image.open(BytesIO(expected))
    assert img.width == trigger.width - int(trigger.width*.5) - 1
    assert img.getpixel((0,0)) == (0,128,0)  # Private outer border removed; exact green trigger retained.
    assert img.getpixel((img.width-1,img.height-1)) == (0,128,0)
    html = sent[0].get_body(preferencelist=('html',)).get_content()
    assert html.count('cid:') == 2 and '&lt;script&gt;' in html and '<script>' not in html
    assert '{image}' not in sent[0].get_body(preferencelist=('plain',)).get_content()
    # Deleted evidence is never restored from a queued copy or a newer preview.
    app.state.store.delete_evidence(SID,trigger.frame_id)
    assert app.state.actions.send(config,context,'deleted')[0] == 'blocked'
    assert len(sent) == 1


def test_missing_old_frame_blocks_email_without_substitution(app,mail):
    config,sent = mail
    old,context = frame(app,'red')
    new,_ = frame(app,'blue')
    with app.state.store.connection() as db:
        app.state.actions.enqueue(db,'missing-email',None,config,context,utcnow())
    assert app.state.actions.jobs()[0]['status'] == 'blocked'
    assert app.state.actions.send(config,context,'missing-email')[0] == 'blocked'
    assert not sent
    assert app.state.store.evidence(SID,old.frame_id) is None
    assert app.state.store.evidence(SID,new.frame_id) is None


def test_image_email_manual_test_uses_camera_observation_without_capture(app,mail,monkeypatch):
    _,sent = mail
    f,_ = frame(app,'green')
    monkeypatch.setattr(app.state.pipeline.capture_adapter,'capture',lambda *a:pytest.fail('No extra capture'))
    client = TestClient(app,headers=HEADERS)
    soup = BeautifulSoup(client.get('/actions').text,'html.parser')
    assert soup.select_one('form[action="/actions/mail/test"] select[name=source_id][required]')
    assert client.post('/actions/mail/test').status_code == 400
    assert client.post('/actions/mail/test',data={'source_id':SID}).status_code == 200
    assert app.state.store.evidence(SID,f.frame_id)
    assert not sent


def test_suppressed_or_rolled_back_email_does_not_retain_image(app,mail):
    config,_ = mail
    f,context = frame(app,'green')
    with app.state.store.connection() as db:
        app.state.actions.enqueue(db,'suppressed',None,config,context,utcnow(),'Cooldown')
    assert app.state.actions.jobs()[0]['status'] == 'suppressed'
    assert app.state.store.evidence(SID,f.frame_id) is None
    with pytest.raises(RuntimeError):
        with app.state.store.connection() as db:
            app.state.actions.enqueue(db,'rollback',None,config,context,utcnow())
            raise RuntimeError('rollback')
    assert app.state.store.evidence(SID,f.frame_id) is None
    assert len(app.state.actions.jobs()) == 1
