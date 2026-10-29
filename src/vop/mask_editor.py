"""Camera-only editor grabs and reusable normalised rectangle controls."""
import json
from time import monotonic
from uuid import uuid4

from fasthtml.components import Button, Details, Div, Img, Input, Label, P, Section, H2, Summary, Ul, Noscript
from fasthtml.svg import Svg
from starlette.responses import JSONResponse, Response

from vop.measurements import regions
from vop.preprocessing import preprocess


def parse_regions(value):
    try:
        return regions(json.loads(value))
    except (TypeError, json.JSONDecodeError):
        raise ValueError('Mask areas must be a list of rectangles') from None


def editor(source_id, include=(), exclude=(), *, privacy=False):
    return Section(H2('Privacy mask' if privacy else 'Question mask'),
        P('Hide areas from all future previews, questions and saved images. Older recorded images stay unchanged.' if privacy else
          'Include areas to use only those parts of the image. Exclude areas to ignore them. No areas means the whole image.'),
        P('Existing privacy areas stay black in this grab. Save and grab again after removing a privacy area.' if privacy else
          'Camera privacy masks always apply first. A blue outline shows any advanced ROI crop, which also applies.', cls='muted'),
        P('Grabs use the saved camera connection. Save any connection changes first.', cls='muted') if privacy else None,
        Input(type='hidden', name='include_regions', value=json.dumps(include)) if not privacy else None,
        Input(type='hidden', name='privacy_masks' if privacy else 'exclude_regions', value=json.dumps(exclude)),
        Div(Button('Grab image', type='button', data_mask_grab='', cls='secondary'),
            Button('Include areas', type='button', data_mask_mode='include', aria_pressed='true', cls='secondary') if not privacy else None,
            Button('Hide areas' if privacy else 'Exclude areas', type='button', data_mask_mode='exclude', aria_pressed='true' if privacy else 'false', cls='secondary'),
            cls='actions mask-tools'),
        P('Grab an image, then drag to draw an area. Grabs wait for the next free camera slot; no inference or saved observation is requested.', data_mask_status='', role='status'),
        Div(Img(alt='Privacy-masked camera image for area selection'),
            Svg(viewBox='0 0 1 1', preserveAspectRatio='none', data_mask_canvas='', role='img', aria_label='Draw mask rectangles on the camera image'),
            cls='mask-stage', hidden=True, data_mask_stage=''),
        Ul(data_mask_list='', cls='mask-list'),
        Div(Button('Undo', type='button', data_mask_undo='', cls='secondary'),
            Button('Clear areas', type='button', data_mask_clear='', cls='secondary'), cls='actions mask-tools'),
        Details(Summary('Add area with coordinates'),
            Div(*(Div(Label(label, _for=f'mask-{source_id}-{key}'), Input(type='text', inputmode='decimal', value=value, id=f'mask-{source_id}-{key}',
                                           data_mask_coordinate=key, aria_label=label))
                  for key, label, value in (('x','Left',0),('y','Top',0),('w','Width',.5),('h','Height',.5))), cls='form-grid'),
            Button('Add area', type='button', data_mask_add='', cls='secondary'),
            P('Values are fractions from 0 to 1, measured from the top-left corner. Each area must stay inside the image. Up to 16 areas of each type.', cls='muted')),
        P('Save the form below to apply these areas.', cls='muted'),
        P('Saving a question creates a new version. Review its linked automations after changing areas.', cls='muted') if not privacy else None,
        P('Different question areas can make each observation take longer.', cls='muted') if not privacy else None,
        Noscript(P('Area editing requires JavaScript. Saving other settings keeps the existing areas.')),
        data_mask_editor=source_id, data_privacy=str(privacy).lower(), cls='mask-editor')


def install(app):
    pipeline = app.state.pipeline

    def allowed(request, sid=None):
        if request.scope.get('auth_role') != 'operator':
            return JSONResponse({'error':'operator_required'}, status_code=403)
        if sid is not None and sid not in pipeline.sources:
            return JSONResponse({'error':'source_not_found'}, status_code=404)

    def expire():
        with pipeline.preview_lock:
            for sid, item in list(pipeline.mask_grabs.items()):
                if item['expires'] < monotonic():
                    pipeline.mask_grabs.pop(sid, None)

    @app.route('/ui/mask-editor.js', methods=['GET'])
    def script(request):
        return Response(SCRIPT, media_type='application/javascript')

    @app.route('/ui/question-mask/{source_id}/grab', methods=['POST'])
    def grab(source_id: str, request):
        denied = allowed(request, source_id)
        if denied: return denied
        expire()
        with pipeline.preview_lock:
            current = pipeline.mask_grabs.get(source_id)
            if current and current['status'] == 'waiting':
                return JSONResponse({'status':'waiting'}, status_code=202)
            token = uuid4().hex
            pipeline.mask_grabs[source_id] = {'status':'waiting', 'token':token, 'expires':monotonic()+300}

        def capture():
            with pipeline.preview_lock:
                current = pipeline.mask_grabs.get(source_id, {})
                if current.get('token') != token or current.get('expires', 0) < monotonic():
                    return
            try:
                source = pipeline.sources[source_id]
                frame = pipeline.live_previews.capture(source, pipeline.capture_adapter.capture)
                if frame.source_id != source_id:
                    raise ValueError('Camera frame source mismatch')
                masked = preprocess(frame, source.settings.get('privacy_masks', ()), preview=True)
                item = {'status':'ready', 'payload':masked.payload, 'token':token,
                        'captured':frame.captured_at_utc.isoformat(), 'expires':monotonic()+300}
            except Exception:
                item = {'status':'failed', 'token':token, 'expires':monotonic()+300,
                        'message':'Could not grab an image. Check the camera connection, then try again.'}
            with pipeline.preview_lock:
                if pipeline.mask_grabs.get(source_id, {}).get('token') == token:
                    pipeline.mask_grabs[source_id] = item

        app.state.sampler.request_camera_test(source_id, capture, purpose='question-mask', replace_pending=True)
        return JSONResponse({'status':'waiting'}, status_code=202)

    @app.route('/ui/question-mask/{source_id}/image', methods=['GET'])
    def image(source_id: str, request):
        denied = allowed(request, source_id)
        if denied: return denied
        expire()
        with pipeline.preview_lock:
            item = pipeline.mask_grabs.get(source_id, {}).copy()
        if request.query_params.get('token'):
            if item.get('status') != 'ready' or item.get('token') != request.query_params['token']:
                return Response(status_code=404)
            return Response(item['payload'], media_type='image/png')
        return JSONResponse({key:value for key,value in item.items() if key not in ('payload','expires')} or {'status':'empty'})


SCRIPT = r"""(() => {
for (const box of document.querySelectorAll('[data-mask-editor]')) {
  const form=box.closest('form'), privacy=box.dataset.privacy==='true';
  const inputs={include:box.querySelector('[name=include_regions]'),exclude:box.querySelector(privacy?'[name=privacy_masks]':'[name=exclude_regions]')};
  const areas={include:inputs.include?JSON.parse(inputs.include.value):[],exclude:JSON.parse(inputs.exclude.value)};
  const svg=box.querySelector('[data-mask-canvas]'),stage=box.querySelector('[data-mask-stage]'),status=box.querySelector('[data-mask-status]');
  const list=box.querySelector('[data-mask-list]'),grab=box.querySelector('[data-mask-grab]'),undo=box.querySelector('[data-mask-undo]');
  const roi=form.querySelector('[name=roi]');
  const history=[]; let mode=privacy?'exclude':'include',start=null,drawing=null,polling=false,generation=0;
  const ns='http://www.w3.org/2000/svg';
  function node(name,attrs={}) {const item=document.createElementNS(ns,name); for(const [k,v] of Object.entries(attrs))item.setAttribute(k,v);return item;}
  function remember(){history.push(JSON.stringify(areas));if(history.length>64)history.shift();}
  function render(){
    svg.replaceChildren();list.replaceChildren();
    if(areas.include.length){
      const id='outside-'+box.dataset.maskEditor,mask=node('mask',{id});mask.append(node('rect',{width:1,height:1,fill:'white'}));
      for(const [x,y,w,h] of areas.include)mask.append(node('rect',{x,y,width:w,height:h,fill:'black'}));
      const defs=node('defs');defs.append(mask);svg.append(defs,node('rect',{width:1,height:1,fill:'black',opacity:.65,mask:'url(#'+id+')'}));
    }
    for(const kind of ['include','exclude']){
      if(inputs[kind])inputs[kind].value=JSON.stringify(areas[kind]);
      areas[kind].forEach((rect,index)=>{
        const [x,y,w,h]=rect;svg.append(node('rect',{x,y,width:w,height:h,class:'mask-'+kind}));
        const row=document.createElement('li'),label=document.createElement('span'),remove=document.createElement('button');
        label.textContent=(kind==='include'?'Include':'Hide')+' area '+(index+1)+' · '+rect.map(n=>n.toFixed(2)).join(', ');
        remove.type='button';remove.className='secondary';remove.textContent='Remove';remove.setAttribute('aria-label','Remove '+label.textContent);
        remove.addEventListener('click',()=>{remember();areas[kind].splice(index,1);render();});row.append(label,remove);list.append(row);
      });
    }
    if(roi&&roi.value.trim()){
      const rect=roi.value.split(',').map(Number);
      if(rect.length===4&&rect.every(Number.isFinite)){const [x,y,w,h]=rect;svg.append(node('rect',{x,y,width:w,height:h,class:'mask-roi'}));}
    }
    undo.disabled=!history.length;
  }
  function add(rect){
    if(rect.some(n=>!Number.isFinite(n))||rect[0]<0||rect[1]<0||rect[2]<=0||rect[3]<=0||rect[0]+rect[2]>1.000001||rect[1]+rect[3]>1.000001){status.textContent='Keep the area inside the image, with a positive width and height.';return;}
    if(areas[mode].length>=16){status.textContent='Use no more than 16 areas of this type.';return;}
    const rounded=rect.map(n=>Math.round(n*1000000)/1000000);rounded[2]=Math.min(rounded[2],1-rounded[0]);rounded[3]=Math.min(rounded[3],1-rounded[1]);
    if(rounded[2]<=0||rounded[3]<=0){status.textContent='This area is too small.';return;}
    remember();areas[mode].push(rounded);render();status.textContent='Area added. Save the form to apply it.';
  }
  const point=e=>{const r=svg.getBoundingClientRect();return [Math.max(0,Math.min(1,(e.clientX-r.left)/r.width)),Math.max(0,Math.min(1,(e.clientY-r.top)/r.height))];};
  const rectangle=(a,b)=>[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.abs(a[0]-b[0]),Math.abs(a[1]-b[1])];
  svg.addEventListener('pointerdown',e=>{if(e.button!==0)return;start=point(e);svg.setPointerCapture(e.pointerId);e.preventDefault();});
  svg.addEventListener('pointermove',e=>{if(!start)return;
    if(!drawing){drawing=node('rect',{class:'mask-'+mode});svg.append(drawing);}
    const [x,y,w,h]=rectangle(start,point(e));for(const [k,v] of Object.entries({x,y,width:w,height:h}))drawing.setAttribute(k,v);
  });
  function endDrawing(){start=null;if(drawing)drawing.remove();drawing=null;}
  svg.addEventListener('pointerup',e=>{if(!start)return;const rect=rectangle(start,point(e));endDrawing();if(rect[2]>.002&&rect[3]>.002)add(rect);});
  svg.addEventListener('pointercancel',endDrawing);
  for(const button of box.querySelectorAll('[data-mask-mode]'))button.addEventListener('click',()=>{
    mode=button.dataset.maskMode;for(const other of box.querySelectorAll('[data-mask-mode]'))other.setAttribute('aria-pressed',String(other===button));
  });
  undo.addEventListener('click',()=>{if(history.length)Object.assign(areas,JSON.parse(history.pop()));render();});
  box.querySelector('[data-mask-clear]').addEventListener('click',()=>{remember();areas.include=[];areas.exclude=[];render();});
  const addCoordinates=()=>add(['x','y','w','h'].map(k=>Number(box.querySelector('[data-mask-coordinate='+k+']').value)));
  box.querySelector('[data-mask-add]').addEventListener('click',addCoordinates);
  for(const input of box.querySelectorAll('[data-mask-coordinate]'))input.addEventListener('keydown',event=>{if(event.key==='Enter'){event.preventDefault();addCoordinates();}});
  const root='/ui/question-mask/'+encodeURIComponent(box.dataset.maskEditor);
  if(roi)roi.addEventListener('input',()=>render());
  async function wait(ticket){
    if(!polling||ticket!==generation)return;if(document.hidden){setTimeout(()=>wait(ticket),1000);return;}
    try{
      const response=await fetch(root+'/image',{cache:'no-store',signal:AbortSignal.timeout(5000)});
      if(!polling||ticket!==generation)return;
      if(response.redirected)throw new Error('Open this editor in Configure mode, then grab again.');
      if(!response.ok)throw new Error('Image unavailable. Check sign-in, then grab again.');const info=await response.json();
      if(!polling||ticket!==generation)return;
      if(info.status==='waiting'){setTimeout(()=>wait(ticket),500);return;}
      if(info.status!=='ready')throw new Error(info.message||'Grab expired or was cleared. Grab a new image.');
      const replacement=new Image();replacement.alt='Privacy-masked camera image for area selection';replacement.src=root+'/image?token='+encodeURIComponent(info.token);
      let timer;try{await Promise.race([replacement.decode(),new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Image load timed out. Grab again.')),5000);})]);}finally{clearTimeout(timer);}
      if(!polling||ticket!==generation)return;
      stage.querySelector('img').replaceWith(replacement);stage.hidden=false;
      status.textContent='Image grabbed. Drag to draw areas, or use coordinates. '+new Date(info.captured).toLocaleString();
    }catch(error){if(ticket!==generation)return;status.textContent=error.name==='Error'?error.message:'Could not load the image. Grab again, or check the camera connection.';}
    polling=false;grab.disabled=false;
  }
  grab.addEventListener('click',async()=>{
    if(polling)return;polling=true;grab.disabled=true;status.textContent='Image scheduled. Waiting for a free camera slot…';
    const ticket=++generation;
    try{const response=await fetch(root+'/grab',{method:'POST',body:new URLSearchParams({csrf:form.querySelector('[name=csrf]').value}),signal:AbortSignal.timeout(5000)});if(!response.ok)throw new Error('Could not schedule an image. Check sign-in and camera setup.');wait(ticket);}
    catch(error){if(ticket!==generation)return;polling=false;grab.disabled=false;status.textContent=error.name==='Error'?error.message:'Could not schedule an image. Try again in Configure mode.';}
  });
  addEventListener('pagehide',()=>{if(polling)status.textContent='Grab again to refresh the image.';polling=false;generation++;grab.disabled=false;endDrawing();});render();
}
})();"""

CSS = """
.mask-stage rect.mask-roi{fill:none;stroke:#1768c4;stroke-width:2;stroke-dasharray:5 4;vector-effect:non-scaling-stroke}
.editor .mask-tools{margin:12px 0;gap:8px}.mask-tools [aria-pressed=true]{background:#dcecff;color:#0055b3;border-color:#94b7dd}.mask-tools [data-mask-mode=include][aria-pressed=true]{background:#def3e6;color:#15623a;border-color:#6bb58a}.mask-tools [data-mask-mode=exclude][aria-pressed=true]{background:#fbe5e5;color:#9b2525;border-color:#d88c8c}.mask-stage{position:relative;width:100%;max-width:680px;border:1px solid #bac5cf;border-radius:8px;overflow:hidden;background:#152330}.mask-stage img{display:block;width:100%;height:auto}.mask-stage svg{position:absolute;inset:0;width:100%;height:100%;touch-action:none;cursor:crosshair}.mask-stage rect.mask-include{fill:#249c4e22;stroke:#168143;stroke-width:2;vector-effect:non-scaling-stroke}.mask-stage rect.mask-exclude{fill:#a61f3655;stroke:#c33042;stroke-width:2;vector-effect:non-scaling-stroke}.mask-list{list-style:none;margin:10px 0;padding:0}.mask-list li{display:flex;gap:12px;align-items:center;justify-content:space-between;padding:6px 0;border-bottom:1px solid #e2e6ec;font-size:12px}.mask-list button{min-height:30px;padding:5px 10px}.mask-editor details{margin:12px 0}.mask-editor details button{margin-top:12px}.mask-editor .form-grid{grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}
"""
