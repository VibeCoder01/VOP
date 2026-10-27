"""Sampled episode timeline: native SVG, local scrolling and bounded zoom."""
from datetime import datetime, timezone
from fasthtml.components import Button, Div, H2, Input, Label, P, Section, Span
from fasthtml.svg import Svg, Rect, Line, Text, ft_svg
from vop.display import duration
from vop.measurements import utc, timezone_for

TITLE = 'Episodes (Contiguous active observations)'
LABEL_WIDTH = 180
ROW_HEIGHT = 46


def intervals(values):
    """Combine adjacent recorded intervals; never fill an unknown gap."""
    result = []
    for item in values:
        start, end = utc(item['from']).timestamp() * 1000, utc(item['to']).timestamp() * 1000
        if end <= start:
            continue
        if result and start <= result[-1][1]:
            result[-1] = (result[-1][0], max(result[-1][1], end))
        else:
            result.append((start, end))
    return result


def episode_timeline(events, camera_names, question_names, zone):
    if not events:
        return Section(H2('Episode timeline'), P('No episodes recorded for these cameras.', cls='notice'))
    prepared, bounds, lanes = [], [], set()
    for event in events:
        key = (event['source_id'], event['question_id'], event['question_version'])
        start = utc(event['started_at_utc']).timestamp() * 1000
        active, gaps = intervals(event.get('segments', [])), intervals(event.get('unknown_intervals', []))
        ends = [start, *(b for a, b in active), *(b for a, b in gaps)]
        for field in ('ended_at_utc', 'interrupted_at_utc'):
            if event.get(field):
                ends.append(utc(event[field]).timestamp() * 1000)
        bounds.extend((start, max(ends)))
        prepared.append((event, key, start, active, gaps))
        lanes.add(key)
    start, end = min(bounds), max(bounds)
    end = max(start + 1000, end)
    keys = sorted(lanes, key=lambda k:(camera_names.get(k[0],k[0]).casefold(), question_names.get(k,k[1]), k[2]))
    positions = {key: 44 + i * ROW_HEIGHT for i, key in enumerate(keys)}
    height, width = 44 + len(keys) * ROW_HEIGHT, 1200
    local_zone = timezone_for(zone)

    def x(stamp):
        return LABEL_WIDTH + (stamp - start) / (end - start) * (width - LABEL_WIDTH - 20)

    axis = [Rect(x=0, y=0, width=width, height=44, cls='episode-axis-bg')]
    for i in range(7):
        stamp = start + (end - start) * i / 6
        label = datetime.fromtimestamp(stamp / 1000, timezone.utc).astimezone(local_zone).strftime('%d %b %H:%M:%S')
        axis.append(Text(label, x=x(stamp), y=26, cls='episode-tick',text_anchor='end' if i == 6 else 'start'))
    marks = []
    labels = [Rect(x=0,y=0,width=LABEL_WIDTH,height=height,cls='episode-label-bg')]
    for key in keys:
        y = positions[key]
        camera, question = camera_names.get(key[0],key[0]), question_names.get(key,key[1])
        labels.extend((Text(camera[:24], ft_svg('title',camera), x=12,y=y+17,cls='episode-camera'),
                       Text(question[:22] + ' · v' + key[2], ft_svg('title',question),x=12,y=y+34,cls='episode-question')))
        marks.append(Line(x1=LABEL_WIDTH,y1=y+ROW_HEIGHT,x2=width,y2=y+ROW_HEIGHT,cls='episode-row-line',data_row_line=''))
    for event,key,stamp,active,gaps in prepared:
        y = positions[key] + 23
        label = camera_names.get(key[0],key[0]) + ' · ' + question_names.get(key,key[1]) + ' · ' + event['status']
        label += ' · Estimated duration ' + duration(event['estimated_observed_seconds'])
        label += ' · Started ' + utc(event['started_at_utc']).astimezone(local_zone).strftime('%d %b %Y %H:%M:%S %Z')
        shapes = [ft_svg('circle',ft_svg('title',label),cx=x(stamp),cy=y,r=3,cls='episode-point',data_point=stamp)]
        for a,b in gaps:
            shapes.append(ft_svg('line',ft_svg('title','Unobserved gap · ' + label),x1=x(a),x2=x(b),y1=y,y2=y,cls='episode-gap',data_from=a,data_to=b))
        for a,b in active:
            shapes.append(ft_svg('rect',ft_svg('title',label),x=x(a),y=y-8,width=max(1,x(b)-x(a)),height=16,rx=4,cls='episode-span',data_from=a,data_to=b))
        marks.append(ft_svg('a',*shapes,href='/ui/observations/' + event['start_observation_id'],aria_label=label,tabindex=0))
    corner = ft_svg('g',Rect(x=0,y=0,width=LABEL_WIDTH,height=44,cls='episode-label-bg'),Text('Camera / question',x=12,y=26,cls='episode-label-heading'),data_episode_corner='')
    graphic = Svg(ft_svg('g',*marks),ft_svg('g',*axis,data_episode_axis=''),ft_svg('g',*labels,data_episode_labels=''),corner,
                  width=width,height=height,viewBox=f'0 0 {width} {height}',role='group',aria_label='Episode timeline by camera and question',data_episode_svg='')
    return Section(H2('Episode timeline'),
        Div(Label('Zoom',_for='episode-zoom'),Button('−',type='button',cls='secondary',data_zoom_out='',aria_label='Zoom out'),
            Input(id='episode-zoom',type='range',min=1,max=64,step=1,value=1,aria_label='Timeline zoom'),
            Span('1.0 ×',data_zoom_value=''),Button('+',type='button',cls='secondary',data_zoom_in='',aria_label='Zoom in'),
            Button('Fit',type='button',cls='secondary',data_zoom_fit=''),cls='episode-toolbar'),
        P('Scroll to move through time. Select an episode to inspect its first observation. Times: ' + zone + '.',cls='muted'),
        P(Span('Active intervals',cls='episode-legend-active'),' · ',Span('Unobserved gaps',cls='episode-legend-gap'),' · Dots mark confirmed starts. No time is inferred after the last sample.',cls='muted'),
        Div(graphic,cls='episode-scroll',tabindex=0,role='region',aria_label='Scrollable episode timeline'),
        cls='episode-timeline',data_episode_timeline='',data_start=start,data_end=end,data_zone=zone)


EPISODES_JS = """const timeline = document.querySelector('[data-episode-timeline]');
if (timeline) {
  const viewport = timeline.querySelector('.episode-scroll');
  const svg = timeline.querySelector('[data-episode-svg]');
  const zoom = timeline.querySelector('#episode-zoom');
  const axis = timeline.querySelector('[data-episode-axis]');
  const labels = timeline.querySelector('[data-episode-labels]');
  const corner = timeline.querySelector('[data-episode-corner]');
  const start = Number(timeline.dataset.start), end = Number(timeline.dataset.end);
  const format = new Intl.DateTimeFormat(undefined,{timeZone:timeline.dataset.zone,day:'2-digit',month:'short',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false});
  const left = 180, height = Number(svg.getAttribute('height'));
  let plot = 1000, scale = 1, framePending = false;
  const x = stamp => left + (Number(stamp)-start)/(end-start)*plot;
  function element(tag,attrs,text) {
    const node = document.createElementNS('http://www.w3.org/2000/svg',tag);
    for (const [name,value] of Object.entries(attrs)) node.setAttribute(name,value);
    if (text) node.textContent=text;
    return node;
  }
  function scroll() {
    labels.setAttribute('transform',`translate(${viewport.scrollLeft},0)`);
    axis.setAttribute('transform',`translate(0,${viewport.scrollTop})`);
    corner.setAttribute('transform',`translate(${viewport.scrollLeft},${viewport.scrollTop})`);
    const nodes = [element('rect',{x:viewport.scrollLeft,y:0,width:viewport.clientWidth,height:44,class:'episode-axis-bg'})];
    const first = Math.max(left,Math.ceil((viewport.scrollLeft+left)/180)*180);
    for (let px=first; px<=Math.min(left+plot,viewport.scrollLeft+viewport.clientWidth-150); px+=180) {
      nodes.push(element('text',{x:px,y:26,class:'episode-tick'},format.format(new Date(start+(px-left)/plot*(end-start)))));
    }
    axis.replaceChildren(...nodes);
  }
  function resize(next=scale,reset=false) {
    const centre=(viewport.scrollLeft+(viewport.clientWidth-left)/2)/plot;
    scale=Math.max(1,Math.min(64,Math.round(Number(next)||1))); zoom.value=String(scale);
    plot=Math.max(780,viewport.clientWidth-left-20)*scale;
    const width=left+plot+20;
    svg.setAttribute('width',width); svg.setAttribute('viewBox',`0 0 ${width} ${height}`);
    for (const mark of svg.querySelectorAll('[data-from]')) {
      const a=x(mark.dataset.from), b=x(mark.dataset.to);
      if (mark.tagName.toLowerCase()==='line') { mark.setAttribute('x1',a); mark.setAttribute('x2',b); }
      else { mark.setAttribute('x',a); mark.setAttribute('width',Math.max(1,b-a)); }
    }
    for (const point of svg.querySelectorAll('[data-point]')) point.setAttribute('cx',x(point.dataset.point));
    for (const line of svg.querySelectorAll('[data-row-line]')) line.setAttribute('x2',width);
    timeline.querySelector('[data-zoom-value]').textContent=scale.toFixed(1)+' ×';
    zoom.setAttribute('aria-valuetext',scale.toFixed(1)+' times');
    viewport.scrollLeft=reset ? 0 : Math.max(0,centre*plot-(viewport.clientWidth-left)/2);
    scroll();
  }
  zoom.addEventListener('input',()=>resize(zoom.value));
  timeline.querySelector('[data-zoom-in]').addEventListener('click',()=>resize(scale*2));
  timeline.querySelector('[data-zoom-out]').addEventListener('click',()=>resize(scale/2));
  timeline.querySelector('[data-zoom-fit]').addEventListener('click',()=>resize(1,true));
  viewport.addEventListener('scroll',()=>{
    if (!framePending) { framePending=true; requestAnimationFrame(()=>{framePending=false;scroll();}); }
  });
  window.addEventListener('resize',()=>resize());
  resize(1,true);
}
"""
