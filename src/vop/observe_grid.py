"""Compact Observe layout; reuse authenticated previews and observation metadata."""
import math
from urllib.parse import urlencode

from fasthtml.components import A, Article, Div, H2, Img, Li, Nav, P, Small, Span, Ul

from vop.answer_images import answer_image_reference


def observe_url(layout='full', images='live', sources=(), anchor=''):
    return '/?' + urlencode([('layout',layout),('images',images),*(('source',s) for s in sorted(sources))]) + ('#camera-'+anchor if anchor else '')


def switch(layout, images, sources):
    return Nav(*(A(label,href=observe_url(value,images,sources),cls='button' if value==layout else 'button secondary',
                   aria_current='page' if value==layout else None) for value,label in (('full','Full view'),('grid','Grid view'))),
               cls='observe-view-switch',aria_label='Observe display')


def image_switch(images, sources):
    return Nav(*(A(label,href=observe_url('grid',value,sources),cls='button' if value==images else 'button secondary',
                   aria_current='page' if value==images else None) for value,label in (('live','Live images'),('captured','Last captured images'))),
               cls='observe-view-switch',aria_label='Grid image type')


def lights(answers, label):
    items=[]
    for answer in answers:
        spec,summary=answer['spec'],answer['summary']
        value=summary['latest_value']
        color,meaning='amber','Unknown or stale answer'
        if value is not None and answer['enabled'] and not summary.get('disabled') and not summary.get('stale'):
            if spec.kind=='binary' and type(value) is bool:
                color,meaning=('green','Yes') if value else ('red','No')
            elif spec.kind=='ordinal' and not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and 0<=value<len(spec.levels):
                fraction=value/max(1,len(spec.levels)-1)
                color='red' if fraction<1/3 else 'green' if fraction>=2/3 else 'amber'
                meaning='Low' if color=='red' else 'High' if color=='green' else 'Middle'
                meaning+=' position on this rating scale; not a judgement of good or bad'
            elif spec.kind=='choice' and value in dict(spec.choices):
                color,meaning='green','A category was returned; green does not rate this category'
        shown=label(value,spec.levels) if meaning!='Unknown or stale answer' else 'Unknown'
        description=f'{spec.text}: {shown}. {meaning}.'
        items.append(Li(Span(*(Span('',cls='grid-answer-lamp '+lamp+(' lit' if color==lamp else '')) for lamp in ('red','amber','green')),cls='grid-traffic-light',aria_hidden='true'),
                        Div(Span(spec.text,cls='grid-question'),Small(shown)),title=description,tabindex=0,
                        aria_label=description,cls='grid-question-answer',data_question=spec.question_id,data_answer_color=color))
    return Ul(*items,cls='grid-question-lights') if items else P('No questions configured.',cls='muted')


def captured_reference(store,pipeline,sid):
    # Intentional gaps (for example Pause) have no image. Keep the latest actual
    # observation capture, but never fall back to an older retained frame.
    with store.connection() as db:
        row=db.execute("SELECT o.id,o.status FROM observations o JOIN runs r ON r.id=o.run_id WHERE o.source_id=? AND (r.frame_id IS NOT NULL OR o.status='retention_gap') ORDER BY o.sequence DESC LIMIT 1",(sid,)).fetchone()
    if row and row['status']=='retention_gap':
        return {'frame':'','captured':'','url':'','message':'The last observation image was deleted. A new observation will show its image here.'}
    result=answer_image_reference(store,pipeline,sid,[row['id']] if row else [])
    return {**result,'message':result['message'] if not result['url'] else 'Last observation image, with camera privacy masks.'}


def card(source,answers,ref,*,mode,operator,csrf,zone,lease,label,caption):
    sid=source['source_id']
    monitoring=bool(source['enabled'] and source['sample_interval_seconds']>0)
    available=operator and bool(ref['url'])
    return Article(H2(source['name']),
        Div(Span('Monitoring' if monitoring else 'Paused',data_grid_monitoring_label='',cls='grid-monitoring-label'),
            Div(Div(Div(Img(src=ref['url'] if available else None,hidden=not available,
                            alt=('Live preview' if mode=='live' else 'Last observation image')+' from '+source['name']),
                        cls='grid-image-stage',tabindex=0,aria_label='Enlarge image from '+source['name']),
                    P(ref['message'] if operator else 'Operator access is required to view camera images.',hidden=available,data_grid_empty=''),
                    P(caption(ref['captured'],zone) if available and ref['captured'] else '',data_grid_caption='',cls='grid-caption')),
                Div(lights(answers,label),data_grid_lights=''),cls='grid-image-and-lights'),
            P('',data_grid_answer_status='',cls='grid-answer-status',role='status'),
            cls='grid-ring monitoring' if monitoring else 'grid-ring',data_grid_camera=sid,data_mode=mode,
            data_operator=str(operator).lower(),data_frame=ref['frame'] if available else '',data_url=ref['url'] if available else '',
            data_image_url='/ui/live-preview/'+sid,data_lease_url=('/ui/live-preview/'+sid+'/keepalive') if lease else '',
            data_answer_url='/ui/camera-answers/'+sid+'?'+urlencode({'zone':zone,'grid':'1'}),data_csrf=csrf,
            data_zone=zone,data_monitoring=str(monitoring).lower()),id='camera-'+sid,cls='grid-camera')


CSS='''
.observe-view-switch{display:flex;gap:8px;flex-wrap:wrap;margin:0 0 18px}.observe-camera-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,360px),1fr));gap:22px;margin-top:20px}.grid-camera{min-width:0}.grid-camera h2{font-size:19px;margin:0 0 10px}.grid-ring{border:4px solid #b77908;border-radius:16px;background:#fffaf0;padding:10px 10px 6px;margin-bottom:0}.grid-ring.monitoring{border-color:#168153;background:#f0faf4}.grid-monitoring-label{display:block;font-size:12px;font-weight:650;margin-bottom:10px}.grid-image-and-lights{display:grid;grid-template-columns:minmax(0,1fr) minmax(110px,.45fr);gap:12px;align-items:start}.grid-image-stage{height:180px;background:#e8e8ed;border-radius:8px}.grid-image-stage img:not([hidden]){display:block;width:100%;height:180px;object-fit:contain;border-radius:8px}.grid-image-stage:hover img:not([hidden]),.grid-image-stage:focus-visible img:not([hidden]){position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:min(800px,calc(100vw - 48px));height:min(440px,calc(100vh - 48px));max-height:440px;z-index:2000;background:white;box-shadow:0 10px 50px #0005;pointer-events:none}.grid-caption{font-size:11px;min-height:26px;margin:6px 0 0;font-variant-numeric:tabular-nums}.grid-answer-status{font-size:11px;margin:6px 0 0}.grid-answer-status:empty{display:none}.grid-caption:empty{display:none}.grid-question-lights{list-style:none;padding:0;margin:0;max-height:244px;overflow:auto}.grid-question-answer{display:flex;align-items:center;gap:8px;margin:0 0 12px;font-size:12px}.grid-question-answer>div{min-width:0}.grid-question-answer small{display:block;font-size:11px;margin-top:3px}.grid-question{overflow-wrap:anywhere}.grid-answer-lamp{display:block;border-radius:50%}.grid-answer-lamp.green{background:#168153}.grid-answer-lamp.red{background:#d52b35}.grid-answer-lamp.amber{background:#b77908}.grid-view-link{float:right;margin-left:10px}.grid-ring [data-grid-empty]{font-size:12px}.grid-question-answer:last-child{margin-bottom:0}
.grid-traffic-light{display:inline-flex;gap:3px;padding:5px;background:#172a3a;border-radius:14px;flex:0 0 auto}.grid-traffic-light .grid-answer-lamp{flex:0 0 11px;width:11px;height:11px;border:0;box-shadow:none;opacity:.23}.grid-traffic-light .grid-answer-lamp.lit{opacity:1;box-shadow:0 0 0 1px #ffffff60}.answers-offline .grid-traffic-light .grid-answer-lamp{opacity:.23}.answers-offline .grid-traffic-light .grid-answer-lamp.amber{opacity:1}
'''


SCRIPT=r'''(() => {
const cards=document.querySelectorAll('[data-grid-camera]');let stopped=false;
const available=()=>!stopped&&!document.hidden&&!window.vopSessionExpired;
addEventListener('pagehide',()=>{stopped=true;});
function monitoring(card,response){
 const value=response.headers.get('X-VOP-Monitoring');if(value===null)return;
 card.dataset.monitoring=value;card.classList.toggle('monitoring',value==='true');
 card.querySelector('[data-grid-monitoring-label]').textContent=value==='true'?'Monitoring':'Paused';
}
function clear(card,message){const image=card.querySelector('img');image.hidden=true;image.removeAttribute('src');
 card.dataset.frame='';card.dataset.url='';const empty=card.querySelector('[data-grid-empty]');empty.hidden=false;empty.textContent=message;
 card.querySelector('[data-grid-caption]').textContent='';}
async function paint(card,ref){
 if(!available()||card.dataset.operator!=='true')return;
 if(!ref.url){clear(card,ref.message||'No observation image available.');return;}
 const image=card.querySelector('img');
 if(card.dataset.frame!==ref.frame||image.hidden||!image.naturalWidth){
  const replacement=new Image();replacement.alt=image.alt;replacement.src=ref.url;
  let timer;
  try{await Promise.race([replacement.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(Error('Image timeout')),5000);})]);}
  finally{clearTimeout(timer);}
  if(!available())return;
  image.replaceWith(replacement);card.dataset.frame=ref.frame;card.dataset.url=ref.url;card.querySelector('[data-grid-empty]').hidden=true;
 }
 card.querySelector('[data-grid-caption]').textContent=ref.message+' '+(ref.captured?new Date(ref.captured).toLocaleString(undefined,{timeZone:card.dataset.zone}):'');
}
async function answers(card){
 if(!available()||card.answerPending)return;card.answerPending=true;
 try{
  const response=await fetch(card.dataset.answerUrl,{cache:'no-store',signal:AbortSignal.timeout(5000),headers:card.dataset.etag?{'If-None-Match':card.dataset.etag}:{}});
  if(response.status===401||response.status===403){card.classList.add('answers-offline');clear(card,'Sign in as an operator to view camera images.');return;}
  if(!available())return;
  if(response.status===304){card.classList.remove('answers-offline');card.querySelector('[data-grid-answer-status]').textContent='';
   if(card.dataset.mode==='captured'&&card.ref)await paint(card,card.ref);return;}
  if(response.status===404){card.classList.remove('monitoring');card.querySelector('[data-grid-monitoring-label]').textContent='Unavailable';clear(card,'Camera no longer available. Refresh the page.');}
  if(!response.ok||response.redirected)throw Error('Answers unavailable');
  const html=await response.text();if(!available())return;monitoring(card,response);
  if(card.dataset.mode==='captured'){
   card.ref={};for(const key of ['frame','url','captured','message'])card.ref[key]=response.headers.get('X-VOP-Processed-'+key)||'';
   try{await paint(card,card.ref);}catch(_){clear(card,'Last-captured image unavailable. Retrying…');}
  }
  if(!available())return;
  card.querySelector('[data-grid-lights]').innerHTML=html;card.dataset.etag=response.headers.get('ETag')||'';
  card.classList.remove('answers-offline');card.querySelector('[data-grid-answer-status]').textContent='';
 }catch(_){if(available()){card.classList.add('answers-offline');card.querySelector('[data-grid-answer-status]').textContent='Answers could not update. Showing last received values; retrying…';}}
 finally{card.answerPending=false;}
}
async function live(card){
 if(!available()||card.dataset.mode!=='live'||card.dataset.operator!=='true'||card.imagePending)return;
 card.imagePending=true;
 try{
  const response=await fetch(card.dataset.imageUrl,{method:'HEAD',cache:'no-store',signal:AbortSignal.timeout(5000)});
  if(response.status===401||response.status===403){card.classList.add('answers-offline');clear(card,'Sign in as an operator to view camera images.');return;}
  if(!available())return;
  if(response.status===404){card.classList.remove('monitoring');card.querySelector('[data-grid-monitoring-label]').textContent='Unavailable';clear(card,'Camera no longer available. Refresh the page.');return;}
  if(!response.ok)throw Error('Preview unavailable');monitoring(card,response);
  let leaseFailed=false;
  if(card.dataset.monitoring==='true'&&card.dataset.leaseUrl&&Date.now()>=Number(card.dataset.renewAt||0)){
   const lease=await fetch(card.dataset.leaseUrl,{method:'POST',body:new URLSearchParams({csrf:card.dataset.csrf}),cache:'no-store',signal:AbortSignal.timeout(5000)});
   leaseFailed=!lease.ok;card.dataset.renewAt=Date.now()+5000;
  }
  if(!available())return;
  if(response.status===204){
   clear(card,response.headers.get('X-VOP-Preview-Error')==='preview_capacity'?'Live limit reached. Filter to four cameras or choose Last captured.':leaseFailed?'Live preview could not start. Open Diagnostics.':response.headers.get('X-VOP-Preview-State')==='reconnecting'?'Reconnecting to camera. Open Diagnostics if this continues.':card.dataset.monitoring==='true'?'Connecting to camera…':'No preview available. Camera monitoring is paused.');return;
  }
  const kind=response.headers.get('X-VOP-Preview-Kind'),state=response.headers.get('X-VOP-Preview-State');
  const isLive=kind==='live'&&state==='live'&&card.dataset.monitoring==='true';
  await paint(card,{frame:response.headers.get('X-VOP-Frame-Id'),url:card.dataset.imageUrl+'?frame='+encodeURIComponent(response.headers.get('X-VOP-Frame-Id')),
   captured:response.headers.get('X-VOP-Captured-At'),message:isLive?'Live preview:':'Last available preview (not live):'});
 }catch(_){if(available())card.querySelector('[data-grid-caption]').textContent='Preview interrupted. Showing the last received image; retrying…';}
 finally{card.imagePending=false;}
}
for(const card of cards){
 async function answerPoll(){await answers(card);if(!stopped)setTimeout(answerPoll,1000);}
 async function imagePoll(){await live(card);if(!stopped&&card.dataset.mode==='live'&&card.dataset.operator==='true')setTimeout(imagePoll,200);}
 answerPoll();imagePoll();
}
})();'''
