"""Offline timer behaviour; no browser imagery or captures."""
import shutil
import subprocess
import pytest
from vop.image_magnify import SCRIPT


def test_one_second_hover_delay_cancellation_and_refresh_stability():
    node=shutil.which('node')
    if not node:pytest.skip('Node required')
    harness=r"""
const assert=require('node:assert/strict');
const timers=new Map(),listeners={},windowListeners={};let next=0;
const stages=[0,1].map(()=>({classes:new Set(),events:{},addEventListener(k,f){this.events[k]=f}}));
for(const stage of stages)stage.classList={add:k=>stage.classes.add(k),remove:k=>stage.classes.delete(k)};
global.document={hidden:false,querySelectorAll(){return stages},addEventListener(k,f){listeners[k]=f}};
global.window={addEventListener(k,f){windowListeners[k]=f}};
global.setTimeout=(f,ms)=>{assert.equal(ms,1000);timers.set(++next,f);return next};
global.clearTimeout=id=>timers.delete(id);
"""
    checks=r"""
for (const stage of stages) {
 stage.events.pointerenter({pointerType:'mouse'});assert.ok(!stage.classes.has('is-magnified'));
 stage.events.pointerleave();assert.equal(timers.size,0);
 stage.events.pointerenter({pointerType:'mouse'});const callback=[...timers.values()][0];timers.clear();callback();assert.ok(stage.classes.has('is-magnified'));
 // Image replacements do not replace this stable parent or restart its timer.
 stage.image={replacement:true};assert.ok(stage.classes.has('is-magnified'));
 stage.events.pointerleave();assert.ok(!stage.classes.has('is-magnified'));
 stage.events.pointerenter({pointerType:'touch'});assert.equal(timers.size,0);
 stage.events.pointerenter({pointerType:'mouse'});document.hidden=true;listeners.visibilitychange();assert.equal(timers.size,0);document.hidden=false;
}
windowListeners.pagehide();console.log('PASS');
"""
    result=subprocess.run([node,'-e',harness+'\n'+SCRIPT+'\n'+checks],capture_output=True,text=True,timeout=15)
    assert result.returncode==0,result.stderr
    assert 'PASS' in result.stdout
