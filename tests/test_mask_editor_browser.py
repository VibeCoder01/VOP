"""Native editor contract with a fake DOM: no browser, camera or imagery access."""
import json
import shutil
import subprocess

import pytest

from vop.mask_editor import SCRIPT


@pytest.mark.skipif(not shutil.which('node'),reason='Node required for editor contract')
@pytest.mark.parametrize('privacy',[False,True])
def test_draw_edit_undo_clear_keyboard_and_explicit_grab(privacy):
    harness=r"""
const assert=require('node:assert/strict');const privacy=PRIVACY;let events={},fetches=[],timers=new Map(),sequence=0;
class Element{
 constructor(){this.children=[];this.dataset={};this.listeners={};this.attrs={};this.value='';this.replaced=0;}
 append(...items){for(const item of items){item.parent=this;this.children.push(item);}}
 replaceChildren(...items){this.replaced++;this.children=[];this.append(...items);}
 setAttribute(k,v){this.attrs[k]=String(v);}
 addEventListener(k,fn){this.listeners[k]=fn;}
 remove(){if(this.parent)this.parent.children=this.parent.children.filter(item=>item!==this);}
 setPointerCapture(){}
 getBoundingClientRect(){return {left:0,top:0,width:200,height:100};}
}
const include=new Element(),exclude=new Element();include.value=exclude.value='[]';
const svg=new Element(),stage=new Element(),status=new Element(),list=new Element(),grab=new Element(),undo=new Element(),clear=new Element(),add=new Element();
const inc=new Element(),exc=new Element();inc.dataset.maskMode='include';exc.dataset.maskMode='exclude';
const coords=Object.fromEntries(['x','y','w','h'].map(k=>[k,new Element()]));
const form={querySelector:s=>s==='[name=csrf]'?{value:'fixture-csrf'}:null};
const box={dataset:{maskEditor:'fixture',privacy:String(privacy)},closest:()=>form,
 querySelector(selector){
  const items={'[name=include_regions]':privacy?null:include,'[name=exclude_regions]':exclude,'[name=privacy_masks]':exclude,
   '[data-mask-canvas]':svg,'[data-mask-stage]':stage,'[data-mask-status]':status,'[data-mask-list]':list,
   '[data-mask-grab]':grab,'[data-mask-undo]':undo,'[data-mask-clear]':clear,'[data-mask-add]':add};
  if(selector.startsWith('[data-mask-coordinate='))return coords[selector.slice(-2,-1)];return items[selector];
 },querySelectorAll:s=>s==='[data-mask-mode]'?(privacy?[exc]:[inc,exc]):Object.values(coords)};
global.document={hidden:false,querySelectorAll:()=>[box],createElement:()=>new Element(),createElementNS:()=>new Element()};
global.addEventListener=(name,fn)=>events[name]=fn;
global.setTimeout=(fn,delay)=>{const id=++sequence;timers.set(id,{fn,delay});return id;};
global.clearTimeout=id=>timers.delete(id);
global.Image=class{decode(){return Promise.resolve();}replaceWith(value){stage.image=value;}};
stage.image=new Image();stage.querySelector=()=>stage.image;
let responses=0;
global.fetch=async(url,options)=>{
 fetches.push({url,options});
 if(url.endsWith('/grab')){assert.equal(options.body.get('csrf'),'fixture-csrf');return {ok:true};}
 return {ok:true,json:async()=>++responses===1?{status:'waiting'}:{status:'ready',token:'fixture-token',captured:'2026-10-29T08:00:00+00:00'}};
};
eval(SOURCE);
(async()=>{
 assert.equal(fetches.length,0); // Merely opening the editor must not probe a camera.
 const event=(x,y)=>({button:0,clientX:x,clientY:y,pointerId:1,preventDefault(){}});
 const renders=list.replaced;
 svg.listeners.pointerdown(event(150,80));svg.listeners.pointermove(event(50,20));
 assert.equal(list.replaced,renders); // Pointer movement updates only the draft rectangle.
 svg.listeners.pointerup(event(50,20));
 assert.deepEqual(JSON.parse((privacy?exclude:include).value),[[.25,.2,.5,.6]]);
 exc.listeners.click();
 function values(x,y,w,h){for(const [k,v] of Object.entries({x,y,w,h}))coords[k].value=String(v);}
 values(.2,.2,.2,.3);add.listeners.click();
 let prior=JSON.parse(exclude.value).length;
 values(.9,0,.5,1);add.listeners.click();assert.equal(JSON.parse(exclude.value).length,prior);assert.match(status.textContent,/inside/);
 let prevented=false;values(.1,.1,.1,.1);coords.w.listeners.keydown({key:'Enter',preventDefault(){prevented=true;}});assert(prevented);
 assert.equal(JSON.parse(exclude.value).length,prior+1);
 const remove=list.children.at(-1).children[1];remove.listeners.click();assert.equal(JSON.parse(exclude.value).length,prior);
 undo.listeners.click();assert.equal(JSON.parse(exclude.value).length,prior+1);
 clear.listeners.click();assert.deepEqual(JSON.parse(exclude.value),[]);undo.listeners.click();assert.equal(JSON.parse(exclude.value).length,prior+1);
 await grab.listeners.click();await new Promise(setImmediate);
 assert(grab.disabled);assert.equal(fetches.length,2);
 const waiting=[...timers.values()].find(item=>item.delay===500);assert(waiting);await waiting.fn();await new Promise(setImmediate);
 assert.equal(stage.hidden,false);assert.equal(grab.disabled,false);assert.match(stage.image.src,/fixture-token/);
 assert.equal(fetches.length,3);assert.match(status.textContent,/Image grabbed/);
 const lastImage=stage.image;let finish;
 global.fetch=async url=>url.endsWith('/grab')?{ok:true}:new Promise(resolve=>{finish=resolve;});
 await grab.listeners.click();await new Promise(setImmediate);assert(grab.disabled);
 events.pagehide();assert.equal(grab.disabled,false);
 finish({ok:true,json:async()=>({status:'ready',token:'stale',captured:'2026-10-29T08:00:00+00:00'})});
 await new Promise(setImmediate);assert.equal(stage.image,lastImage);assert.match(status.textContent,/Grab again/);
})().catch(error=>{console.error(error);process.exitCode=1;});
""".replace('PRIVACY',json.dumps(privacy)).replace('SOURCE',json.dumps(SCRIPT))
    result=subprocess.run([shutil.which('node'),'-e',harness],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
