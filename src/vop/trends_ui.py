"""Native time navigation: full selected samples, canvas rendering and local view state."""
from hashlib import sha256
from datetime import datetime, timezone
import json
import math

from fasthtml.components import Button, Canvas, Div, Input, Label, Noscript, P, Span
from fasthtml.svg import Svg

from vop.measurements import utc


def domain(series, start=None, end=None):
    # Temporal summaries are chronological; only endpoints are needed for a common axis.
    stamps = [utc(point['at_utc']).timestamp()*1000 for values in series if values for point in (values[0], values[-1])]
    if not stamps:
        right = utc(end).timestamp()*1000 if end else datetime.now(timezone.utc).timestamp()*1000
        left = utc(start).timestamp()*1000 if start else right-3600000
        return left, max(left+1000,right), right
    left = utc(start).timestamp()*1000 if start else min(stamps)
    right = utc(end).timestamp()*1000 if end else max(stamps)
    return (left, max(left+1000, right), max(stamps))


def graph(points, label, *, key, bounds, zone, fallback, numeric=True):
    if not numeric:
        return P('No numeric observations in this view.', cls='muted')
    data = []
    for point in points:
        value = point['value']
        value = float(value) if isinstance(value,(int,float)) and math.isfinite(value) else None
        data.append([int(utc(point['at_utc']).timestamp()*1000), value, int(bool(point.get('gap_before')))])
    identity = 'trend-zoom-' + sha256(key.encode()).hexdigest()[:12]
    return Div(
        Div(Button('Earlier', type='button', cls='secondary', data_trend_earlier='', disabled=True),
            Button('Later', type='button', cls='secondary', data_trend_later='', disabled=True),
            Label('Zoom', _for=identity), Button('−',type='button',cls='secondary',data_trend_out='',aria_label='Zoom out',disabled=True),
            Input(id=identity,type='range',min=0,max=10,step='.1',value=0,data_trend_zoom='',aria_label='Horizontal time zoom',disabled=True),
            Span('1.0 ×',data_trend_scale=''),Button('+',type='button',cls='secondary',data_trend_in='',aria_label='Zoom in',disabled=True),
            Button('Fit',type='button',cls='secondary',data_trend_fit='',disabled=True),
            Button('Latest',type='button',cls='secondary',data_trend_latest='',disabled=True),cls='trend-toolbar'),
        P('Full selected time range',data_trend_window='',cls='trend-window'),
        Div(Canvas(width=680,height=220,tabindex=0,hidden=True,data_trend_canvas='',role='img',
                   aria_label=label+'. Time graph. Arrow keys pan; plus and minus zoom; Home and End move to earliest and latest.'),
            Div(fallback(points[-200:],label),data_trend_fallback='',cls='trend-fallback'),cls='trend-plot'),
        Div(Svg(width=680,height=1,data_trend_track='',aria_hidden='true'),cls='trend-scroll',
            tabindex=0,role='region',aria_label='Horizontal time scroll for '+label,data_trend_scroll=''),
        P('Hover for the nearest recorded sample.',data_trend_readout='',cls='trend-readout'),
        P('Drag or scroll horizontally to move through time. Use zoom or Ctrl + wheel for detail. Amber marks unobserved time; gaps are not joined.',cls='muted'),
        Noscript(P('Interactive navigation requires JavaScript. The static preview shows up to 200 recent samples in sample order.',cls='notice')),
        data_trend=key,data_points=json.dumps(data,separators=(',',':')),data_start=bounds[0],data_end=bounds[1],data_latest=bounds[2],data_zone=zone,cls='trend-graph')


CSS = """
.trend-graph [hidden]{display:none!important}
.trend-refresh-status{min-height:40px;margin:8px 0;font-size:12px;color:var(--muted)}
.trend-toolbar{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin:20px 0 8px}.trend-toolbar input[type=range]{width:150px;padding:0;min-height:30px;accent-color:var(--accent)}.trend-toolbar [data-trend-scale]{display:inline-block;min-width:72px;font-size:12px;font-variant-numeric:tabular-nums}.trend-window{min-height:40px;font-size:12px;font-variant-numeric:tabular-nums;margin:8px 0}.trend-plot{position:relative;height:220px;width:100%}.trend-plot canvas{display:block;width:100%;height:220px;cursor:grab;touch-action:pan-y}.trend-plot canvas:active{cursor:grabbing}.trend-fallback{position:absolute;inset:0;overflow:hidden}.trend-scroll{overflow-x:auto;overflow-y:hidden;height:22px;border-bottom:1px solid #dcdce0;overscroll-behavior-x:contain}.trend-scroll svg{display:block;max-width:none}.trend-readout{min-height:24px;margin:8px 0;font-size:12px;font-variant-numeric:tabular-nums}.trend-lock{display:inline-flex;align-items:center;gap:8px;margin:12px 0 4px}.trend-graph{margin:16px 0 8px}
"""

SCRIPT = r"""(() => {
const roots=Array.from(document.querySelectorAll('[data-trend]'));
const lock=document.querySelector('[data-trend-lock]');if(!lock)return;
const filters=document.querySelector('form.filters');
const scope=location.pathname+'?'+(filters?new URLSearchParams(new FormData(filters)).toString():location.search);
let stored={};try{const value=JSON.parse(sessionStorage.getItem('vop-trend-view')||'{}');if(value.scope===scope)stored=value;}catch(_){}
let dragging=false,interactingUntil=0,syncing=false,leader=null;
const touch=()=>{interactingUntil=Date.now()+1500;};
const charts=[];
function save(){try{sessionStorage.setItem('vop-trend-view',JSON.stringify({scope,locked:lock.checked,views:Object.fromEntries(charts.map(c=>[c.key,c.state()]))}));}catch(_){} }
window.vopTrends={busy:()=>dragging||Date.now()<interactingUntil,save};
function sync(source){
  leader=source;if(!lock.checked||syncing)return;syncing=true;
  const view=source.state();for(const other of charts)if(other!==source)other.apply(view,false);
  syncing=false;
}
for(const root of roots){
 let samples,begin,end,range,latest,maximum,hasNumeric;
 function read(data){samples=JSON.parse(data.points);begin=Number(data.start);end=Number(data.end);range=end-begin;
   latest=Math.max(begin,Math.min(end,Number(data.latest)));maximum=1;hasNumeric=false;for(const sample of samples)if(sample[1]!==null){maximum=Math.max(maximum,sample[1]);hasNumeric=true;}}
 read(root.dataset);
 const canvas=root.querySelector('[data-trend-canvas]'),ctx=canvas.getContext('2d');if(!ctx)continue;
 const scroll=root.querySelector('[data-trend-scroll]'),track=root.querySelector('[data-trend-track]'),zoom=root.querySelector('[data-trend-zoom]');
 const readout=root.querySelector('[data-trend-readout]'),windowLabel=root.querySelector('[data-trend-window]');
 const date=new Intl.DateTimeFormat(undefined,{timeZone:root.dataset.zone,day:'2-digit',month:'short',year:'numeric'});
 const time=new Intl.DateTimeFormat(undefined,{timeZone:root.dataset.zone,hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
 const stamp=value=>date.format(new Date(value))+' '+time.format(new Date(value));
 let scale=1,width=680,span=range,from=begin,follow=true,fit=true,pending=false,drag=null,appliedScroll=null;
 const left=48,right=16,top=16,bottom=165,height=220;
 function lower(value){let a=0,b=samples.length;while(a<b){const m=(a+b)>>1;if(samples[m][0]<value)a=m+1;else b=m;}return a;}
 function state(){return {start:from,span,follow,fit};}
 function draw(){
   width=Math.max(160,Math.round(canvas.getBoundingClientRect().width||680));
   const dpr=window.devicePixelRatio||1;canvas.width=Math.round(width*dpr);canvas.height=height*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);
   const plot=width-left-right,x=t=>left+(t-from)/span*plot,y=v=>bottom-v/maximum*(bottom-top);
   ctx.clearRect(0,0,width,height);ctx.font='11px system-ui';ctx.lineWidth=1;
   for(let i=0;i<3;i++){const value=maximum*i/2,py=y(value);ctx.strokeStyle='#dcdce0';ctx.beginPath();ctx.moveTo(left,py);ctx.lineTo(width-right,py);ctx.stroke();ctx.fillStyle='#626268';ctx.textAlign='right';ctx.fillText(value.toFixed(1),left-8,py+4);}
   const first=Math.max(0,lower(from)-1),last=Math.min(samples.length,lower(from+span)+1);
   const gaps=[];
   function gap(a,b){a=Math.max(left,x(a));b=Math.min(width-right,x(b));if(b<=a)return;const previous=gaps.at(-1);if(previous&&a<=previous[1])previous[1]=Math.max(previous[1],b);else gaps.push([a,b]);}
   if(samples.length&&from<samples[0][0])gap(from,samples[0][0]);
   for(let i=first+1;i<last;i++)if(samples[i][2]||samples[i][1]===null||samples[i-1][1]===null)gap(samples[i-1][0],samples[i][0]);
   if(samples.length&&from+span>samples.at(-1)[0])gap(samples.at(-1)[0],from+span);
   ctx.fillStyle='#fff0d7';for(const [a,b] of gaps)ctx.fillRect(a,top,b-a,bottom-top);
   ctx.save();ctx.beginPath();ctx.rect(left,top,plot,bottom-top+3);ctx.clip();ctx.beginPath();ctx.strokeStyle='#0066cc';ctx.lineWidth=2;
   let connected=false;
   for(let i=first;i<last;i++){const [t,v,gapBefore]=samples[i];if(v===null){connected=false;continue;}if(!connected||gapBefore)ctx.moveTo(x(t),y(v));else ctx.lineTo(x(t),y(v));connected=true;}
   ctx.stroke();ctx.fillStyle='#0066cc';
   if(last-first<=1000)for(let i=first;i<last;i++){const [t,v]=samples[i];if(v!==null){ctx.beginPath();ctx.arc(x(t),y(v),2.5,0,Math.PI*2);ctx.fill();}}
   ctx.restore();ctx.fillStyle='#626268';
   if(!hasNumeric){ctx.textAlign='center';ctx.fillText('No numeric observations in this view.',left+plot/2,90);}
   const ticks=Math.max(1,Math.floor(plot/160));
   for(let i=0;i<=ticks;i++){const t=from+span*i/ticks,px=left+plot*i/ticks;ctx.textAlign=i===0?'left':i===ticks?'right':'center';ctx.fillText(date.format(new Date(t)),px,190);ctx.fillText(time.format(new Date(t)),px,207);}
   windowLabel.textContent=stamp(from)+' — '+stamp(from+span)+' · '+root.dataset.zone+(follow?' · Following latest':'');
   root.querySelector('[data-trend-scale]').textContent=scale.toFixed(1)+' ×';zoom.value=String(Math.log2(scale));zoom.setAttribute('aria-valuetext',scale.toFixed(1)+' times');
   root.querySelector('[data-trend-earlier]').disabled=from<=begin+.1;
   root.querySelector('[data-trend-later]').disabled=from+span>=end-.1;
 }
 function apply(value,notify=true){
   const next=Number(value.span);span=Number.isFinite(next)&&next>0?Math.max(range/1024,Math.min(range,next)):range;
   scale=range/span;fit=!!value.fit||scale<=1.000001;if(fit){span=range;scale=1;}
   follow=!!value.follow||fit;
   const requested=follow&&!fit?latest-span:Number(value.start);from=fit?begin:Math.max(begin,Math.min(end-span,Number.isFinite(requested)?requested:begin));
   const viewport=Math.max(1,scroll.clientWidth||canvas.getBoundingClientRect().width||680);track.setAttribute('width',Math.ceil(viewport*scale));
   scroll.scrollLeft=(from-begin)/range*viewport*scale;appliedScroll=scroll.scrollLeft;draw();if(notify){touch();sync(api);save();}
 }
 function zoomAt(next,fraction=.5){const anchor=from+span*fraction;const nextSpan=range/Math.max(1,Math.min(1024,next));apply({start:anchor-nextSpan*fraction,span:nextSpan,follow:false,fit:next<=1});}
 function pan(fraction){apply({start:from+span*fraction,span,follow:false,fit:false});}
 const api={key:root.dataset.trend,state,apply,update(data){const view=state();read(data);apply(view,false);}};charts.push(api);
 root.querySelector('[data-trend-fallback]').hidden=true;canvas.hidden=false;
 for(const input of root.querySelectorAll('button,input'))input.disabled=false;
 zoom.addEventListener('input',()=>zoomAt(2**Number(zoom.value)));
 root.querySelector('[data-trend-in]').addEventListener('click',()=>zoomAt(scale*2));
 root.querySelector('[data-trend-out]').addEventListener('click',()=>zoomAt(scale/2));
 root.querySelector('[data-trend-fit]').addEventListener('click',()=>apply({span:range,fit:true,follow:true}));
 root.querySelector('[data-trend-latest]').addEventListener('click',()=>apply({span,fit,follow:true}));
 root.querySelector('[data-trend-earlier]').addEventListener('click',()=>pan(-.5));root.querySelector('[data-trend-later]').addEventListener('click',()=>pan(.5));
 scroll.addEventListener('scroll',()=>{if(pending)return;pending=true;requestAnimationFrame(()=>{
   pending=false;if(appliedScroll!==null&&Math.abs(scroll.scrollLeft-appliedScroll)<.1)return;appliedScroll=null;
   const viewport=Math.max(1,scroll.clientWidth||680),next=begin+scroll.scrollLeft/(viewport*scale)*range;
   if(Math.abs(next-from)<.5)return;from=Math.max(begin,Math.min(end-span,next));follow=Math.abs(from+span-latest)<=Math.max(1,span*.001);fit=scale<=1.000001;
   draw();touch();sync(api);save();
 });});
 canvas.addEventListener('pointerdown',event=>{if(event.button!==0)return;drag={x:event.clientX,left:scroll.scrollLeft};dragging=true;canvas.setPointerCapture(event.pointerId);touch();});
 canvas.addEventListener('pointermove',event=>{
   if(drag){scroll.scrollLeft=drag.left+drag.x-event.clientX;touch();return;}
   const rect=canvas.getBoundingClientRect(),fraction=Math.max(0,Math.min(1,(event.clientX-rect.left-left)/(width-left-right))),t=from+span*fraction;
   let i=lower(t);if(i>=samples.length)i=samples.length-1;else if(i>0&&t-samples[i-1][0]<samples[i][0]-t)i--;
   if(i>=0){const point=samples[i];readout.textContent='Nearest recorded sample: '+stamp(point[0])+' · '+(point[1]===null?'Unknown':'Value '+point[1].toFixed(1));}
 });
 const release=()=>{if(drag){drag=null;dragging=false;touch();}};
 canvas.addEventListener('pointerup',release);canvas.addEventListener('pointercancel',release);canvas.addEventListener('lostpointercapture',release);
 canvas.addEventListener('wheel',event=>{
   if(event.ctrlKey){event.preventDefault();zoomAt(scale*(event.deltaY<0?1.25:.8),Math.max(0,Math.min(1,(event.clientX-canvas.getBoundingClientRect().left-left)/(width-left-right))));}
   else if(event.shiftKey||Math.abs(event.deltaX)>Math.abs(event.deltaY)){event.preventDefault();scroll.scrollLeft+=event.deltaX||event.deltaY;touch();}
 },{passive:false});
 canvas.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight','+','=','-','Home','End'].includes(event.key))return;event.preventDefault();
   if(event.key==='ArrowLeft')pan(-.25);else if(event.key==='ArrowRight')pan(.25);else if(event.key==='Home')apply({start:begin,span,follow:false,fit:false});
   else if(event.key==='End')apply({span,follow:true,fit});else zoomAt(event.key==='-'?scale/2:scale*2);
 });
 window.addEventListener('resize',()=>apply(state(),false));
 apply(stored.views?.[api.key]||{span:range,fit:true,follow:true},false);
}
lock.disabled=!charts.length;lock.checked=!!stored.locked;
lock.addEventListener('change',()=>{touch();if(lock.checked&&charts.length)sync(leader||charts.find(c=>stored.views?.[c.key])||charts[0]);save();});
if(lock.checked&&charts.length)sync(charts.find(c=>stored.views?.[c.key])||charts[0]);
addEventListener('pagehide',save);
window.vopTrends.update=doc=>{
 const incoming=new Map(Array.from(doc.querySelectorAll('[data-trend]'),r=>[r.dataset.trend,r.dataset]));
 const sections=Array.from(document.querySelectorAll('[data-trend-section]'));
 const nextSections=new Map(Array.from(doc.querySelectorAll('[data-trend-section]'),s=>[s.dataset.trendSection,s]));
 if(incoming.size!==charts.length||charts.some(c=>!incoming.has(c.key))||nextSections.size!==sections.length||sections.some(s=>!nextSections.has(s.dataset.trendSection)))return false;
 for(const chart of charts)chart.update(incoming.get(chart.key));
 for(const section of sections){const next=nextSections.get(section.dataset.trendSection);
   const values=section.querySelectorAll('[data-trend-value]'),nextValues=next.querySelectorAll('[data-trend-value]');
   values.forEach((value,i)=>{value.style.minHeight=value.getBoundingClientRect().height+'px';value.textContent=nextValues[i].textContent;});
   const summary=section.querySelector('[data-trend-summary]'),nextSummary=next.querySelector('[data-trend-summary]');
   if(summary&&nextSummary&&!summary.contains(document.activeElement))summary.replaceChildren(...nextSummary.childNodes);
 }
 if(lock.checked&&charts.length)sync(leader||charts[0]);save();return true;
};
})();"""
