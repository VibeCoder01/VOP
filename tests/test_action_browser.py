"""Browser sound queue contract, using a fake DOM/audio device and no playback."""
import json
import shutil
import subprocess

import pytest

from vop.actions_ui import SCRIPT


@pytest.mark.skipif(not shutil.which('node'), reason='Node is needed for the browser script contract')
def test_sound_enable_claim_play_ack_and_no_duplicate_poll():
    harness = r"""
const assert = require('assert');
const callbacks = [], timers = [], posts = [], store = new Map();
const button = {dataset:{csrf:'csrf'}, textContent:'Enable sound', addEventListener:(event,fn)=>callbacks.push(fn)};
global.document = {hidden:false,querySelector:s => s === '[data-enable-sound]' ? button : null};
Object.defineProperty(globalThis,'crypto',{value:{randomUUID:()=> 'browser-one'},configurable:true});
global.sessionStorage = {getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v),removeItem:k=>store.delete(k)};
global.setInterval = fn => timers.push(fn);
let finish, audioCount=0;
global.Audio = class {constructor(url){this.url=url; audioCount++;} play(){finish=this; return Promise.resolve();} pause(){} };
let available = true;
global.fetch = async (url,options) => {
 const fields = Object.fromEntries(options.body); posts.push({url,fields});
 return {ok:true,json:async()=> url.endsWith('claim') && available ? (available=false,{id:'job',config:{kind:'beep',id:'bell',volume:50}}) : {}};
};
eval(SCRIPT);
(async()=>{
 assert.equal(timers.length,1);
 await timers[0](); assert.equal(posts.length,0); // Disabled means no claims.
 await callbacks[0](); assert.equal(button.textContent,'Disable sound');
 const playing = timers[0]();
 for(let i=0;i<10;i++) await Promise.resolve();
 await timers[0](); assert.equal(posts.length,1); // In-flight playback blocks overlapping polls.
 assert.equal(finish.volume,0.5); finish.onended(); await playing;
 assert.equal(posts[1].url,'/actions/sound/ack');
 assert.equal(posts[1].fields.played,'yes');
 assert.equal(posts[1].fields.client,posts[0].fields.client);
 assert(posts[1].fields.client.length > 0);
 document.hidden=true; await timers[0](); assert.equal(posts.length,2);
 await callbacks[0](); assert.equal(button.textContent,'Enable sound');
 assert(!store.has('vop-sound'));
 document.hidden=false; await callbacks[0]();
 available=true;
 const before=audioCount;
 const cancelled=timers[0](); await callbacks[0](); await cancelled;
 assert.equal(audioCount,before); // Disabling during a claim must not start playback.
 assert.equal(posts.at(-1).fields.played,'no');
})().catch(e=>{console.error(e);process.exitCode=1});
"""
    result = subprocess.run(['node', '-e', 'const SCRIPT=' + json.dumps(SCRIPT) + ';\n' + harness], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
