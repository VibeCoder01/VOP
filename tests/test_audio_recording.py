"""Offline browser microphone contract. No device access, real voice or audible playback."""
import base64
from io import BytesIO
import json
import shutil
import subprocess
import wave

from bs4 import BeautifulSoup
import pytest
from starlette.testclient import TestClient

from test_phase3_release import app, HEADERS
from vop.audio_recording import SCRIPT


HARNESS = r"""
const assert = require('assert');
function element() {
 return {handlers:{},value:'',disabled:false,hidden:false,dataset:{},textContent:'',
  addEventListener(event,fn){this.handlers[event]=fn;}, setCustomValidity(value){this.validity=value;},
  pause(){},load(){},removeAttribute(key){delete this[key];}};
}
const names=['audio-upload','record-start','record-stop','record-cancel','audio-discard','audio-preview','audio-status'];
const el=Object.fromEntries(names.map(name=>[name,element()]));
const data=element(), save=element(), form=element();
form.querySelectorAll=()=>[save];
const editor=element(); editor.dataset.saved='yes'; editor.closest=()=>form;
editor.querySelector=selector=> selector==='[name=audio_data]' ? data : el[selector.slice(6,-1)];
const doc=element(); doc.hidden=false; doc.querySelector=()=>editor;
let duration=1, decodedSeconds=1, decodeError=false, permissionError=false, permissionDeferred=false;
let requests=0, stopped=0, recordings=[], permissionResolve, decodes=0, blobs=0, revoked=[];
doc.createElement=()=>{
 const probe=element();probe.duration=duration;
 Object.defineProperty(probe,'src',{set(value){if(value)queueMicrotask(()=>probe.onloadedmetadata?.());},configurable:true});
 return probe;
};
global.document=doc; global.window=globalThis;
const windowEvents={}; global.addEventListener=(event,fn)=>windowEvents[event]=fn;
Object.defineProperty(globalThis,'navigator',{value:{mediaDevices:{getUserMedia:async constraints=>{
 requests++;assert.equal(constraints.video,false);
 if(permissionError)throw Object.assign(new Error('denied'),{name:'NotAllowedError'});
 const stream={getTracks:()=>[{stop(){stopped++;}}]};
 if(permissionDeferred)return new Promise(resolve=>permissionResolve=()=>resolve(stream));
 return stream;
}}},configurable:true});
global.MediaRecorder=class {
 constructor(stream){this.state='inactive';this.mimeType='audio/webm';recordings.push(this);}
 start(){this.state='recording';}
 stop(){assert.notEqual(this.state,'inactive');this.state='inactive';
  this.ondataavailable?.({data:new Blob(['synthetic encoded audio'])});this.done=this.onstop?.();}
};
global.OfflineAudioContext=class {
 constructor(channels,length,rate){assert.equal(rate,16000);}
 async decodeAudioData(){decodes++;if(decodeError)throw new Error('codec');
  return {duration:decodedSeconds,length:Math.round(decodedSeconds*16000),numberOfChannels:1,
   getChannelData:()=>new Float32Array(Math.round(decodedSeconds*16000)).fill(0.25)};}
};
global.URL={createObjectURL(){return 'blob:local-'+(++blobs);},revokeObjectURL(url){revoked.push(url);}};
const timers=new Map();let timerId=0;
global.setTimeout=(fn,ms)=>{timers.set(++timerId,{fn,ms});return timerId;};
global.clearTimeout=id=>timers.delete(id);
global.setInterval=global.setTimeout;global.clearInterval=global.clearTimeout;
const settle=async()=>{for(let i=0;i<12;i++)await Promise.resolve();};
eval(SCRIPT);
"""


def run(scenario):
    if not shutil.which('node'):
        pytest.skip('Node is needed for the browser recording contract')
    result = subprocess.run(['node', '-e', 'const SCRIPT=' + json.dumps(SCRIPT) + ';\n' + HARNESS +
        '\n(async()=>{' + scenario + '})().catch(e=>{console.error(e);process.exitCode=1});'], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def test_record_stop_preview_and_existing_save_path(app):
    encoded = run(r"""
 assert.equal(requests,0); assert.equal(el['record-start'].disabled,false);
 await el['record-start'].handlers.click(); assert.equal(requests,1); assert(save.disabled);
 let prevented=false;form.handlers.submit({preventDefault(){prevented=true;}});assert(prevented);
 el['record-stop'].handlers.click();await recordings[0].done;
 assert.equal(stopped,1);assert.equal(save.disabled,false);assert(data.value);
 assert.equal(el['audio-preview'].hidden,false);assert(el['audio-preview'].src.startsWith('blob:'));
 assert(el['audio-status'].textContent.includes('Save action'));
 console.log(data.value);
 """)
    with wave.open(BytesIO(base64.b64decode(encoded)), 'rb') as audio:
        assert (audio.getnchannels(), audio.getsampwidth(), audio.getframerate(), audio.getnframes()) == (1, 2, 16000, 16000)
    client = TestClient(app)
    response = client.post('/actions/save', headers=HEADERS, data={'id':'recorded','kind':'audio','name':'Recorded alert','location':'browser','audio_data':encoded})
    assert response.status_code == 200
    assert app.state.actions.audio('recorded') == base64.b64decode(encoded)


def test_permission_cancel_failure_and_page_exit_release_microphone():
    run(r"""
 data.value='previous';permissionError=true;
 await el['record-start'].handlers.click();assert.equal(data.value,'previous');assert(!save.disabled);
 assert(el['audio-status'].textContent.includes('not allowed'));
 permissionError=false;permissionDeferred=true;
 const pending=el['record-start'].handlers.click();await settle();
 el['record-cancel'].handlers.click();permissionResolve();await pending;
 assert.equal(stopped,1);assert.equal(recordings.length,0);assert.equal(data.value,'previous');
 permissionDeferred=false;await el['record-start'].handlers.click();
 windowEvents.pagehide();await recordings[0].done;
 assert.equal(stopped,2);assert.equal(data.value,'previous');assert.equal(decodes,0);
 """)


def test_time_limit_hidden_page_and_decode_failure_preserve_previous_audio():
    run(r"""
 decodedSeconds=60.05;
 await el['record-start'].handlers.click();
 const timeout=[...timers.values()].find(t=>t.ms===60000);assert(timeout);timeout.fn();await recordings[0].done;
 const wav=Buffer.from(data.value,'base64');assert.equal(wav.readUInt32LE(40),60*16000*2);assert(wav.length<2*1024*1024);
 const previous=data.value;decodeError=true;
 await el['record-start'].handlers.click();doc.hidden=true;doc.handlers.visibilitychange();await recordings[1].done;
 assert.equal(stopped,2);assert.equal(data.value,previous);assert(!save.disabled);
 assert(el['audio-status'].textContent.includes('previous audio'));
 decodeError=false;await el['record-start'].handlers.click();el['record-cancel'].handlers.click();await recordings[2].done;
 assert.equal(data.value,previous);assert.equal(stopped,3);
 """)


def test_common_audio_import_long_clip_and_discard():
    run(r"""
 data.value='previous';duration=180;
 el['audio-upload'].files=[new Blob(['synthetic MP3'],{type:'audio/mpeg'})];
 await el['audio-upload'].handlers.change();assert.equal(decodes,0);assert.equal(data.value,'previous');
 assert(el['audio-status'].textContent.includes('00:01:00'));
 duration=1;await el['audio-upload'].handlers.change();assert.equal(decodes,1);
 assert(Buffer.from(data.value,'base64').toString('ascii',0,4)==='RIFF');
 el['audio-discard'].handlers.click();assert.equal(data.value,'');assert(revoked.length>=2);
 assert(el['audio-status'].textContent.includes('saved audio will be kept'));
 data.value='previous';el['audio-upload'].files=[{size:11*1024*1024}];
 await el['audio-upload'].handlers.change();assert.equal(decodes,1);assert.equal(data.value,'previous');
 assert(el['audio-status'].textContent.includes('10 MB'));
 """)


def test_unsupported_browser_keeps_file_import_available():
    script = HARNESS.replace('eval(SCRIPT);', 'delete global.MediaRecorder; eval(SCRIPT);')
    if not shutil.which('node'):
        pytest.skip('Node is needed for the browser recording contract')
    result = subprocess.run(['node','-e','const SCRIPT='+json.dumps(SCRIPT)+';\n'+script+
        "assert(el['record-start'].disabled);assert(!el['audio-upload'].disabled);assert.equal(requests,0);"], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr


def test_recording_controls_are_audio_only_and_preview_policy_is_local(app):
    client = TestClient(app)
    response = client.get('/actions/edit?kind=audio', headers=HEADERS)
    soup = BeautifulSoup(response.text,'html.parser')
    assert soup.select_one('[data-record-start][type=button]')
    assert soup.select_one('[data-record-stop][disabled]')
    assert soup.select_one('audio[controls][hidden]')
    assert 'audio/*' in soup.select_one('[data-audio-upload]')['accept']
    assert '/ui/audio-editor.js' in response.text
    assert "media-src 'self' blob:" in response.headers['content-security-policy']
    assert client.get('/ui/audio-editor.js', headers=HEADERS).status_code == 200
    assert 'data-record-start' not in client.get('/actions/edit?kind=beep', headers=HEADERS).text
