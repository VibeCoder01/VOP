"""Read-only question-area overlays; no image fetches or acquisition."""
SCRIPT = r"""(() => {
  let active = null, overlay = null, legend = null, stage = null;
  const ns = 'http://www.w3.org/2000/svg';
  function clear() {
    overlay?.remove(); legend?.remove();
    overlay = legend = stage = null; active = null;
  }
  function draw(row) {
    clear();
    if (!row) return;
    const panel = row.closest('[data-processed-target]');
    if (!panel?.open) return;
    const tile = document.getElementById(panel.dataset.processedTarget);
    const image = tile?.querySelector('img');
    const box = tile?.querySelector('.image-stage');
    if (!image || image.hidden || !image.naturalWidth || !box || !box.clientWidth || !box.clientHeight) return;
    let areas;
    try { areas = JSON.parse(row.dataset.questionAreas); } catch (_) { return; }
    if (!areas.include.length && !areas.exclude.length) return;
    active = row; stage = box;
    const w = box.clientWidth, h = box.clientHeight;
    const scale = Math.min(w / image.naturalWidth, h / image.naturalHeight);
    const iw = image.naturalWidth * scale, ih = image.naturalHeight * scale;
    const left = (w - iw) / 2, top = (h - ih) / 2;
    overlay = document.createElementNS(ns, 'svg');
    overlay.setAttribute('class', 'question-area-overlay');
    overlay.setAttribute('viewBox', `0 0 ${w} ${h}`);
    overlay.setAttribute('aria-hidden', 'true');
    for (const kind of ['include','exclude']) for (const [x,y,rw,rh] of areas[kind]) {
      const rect = document.createElementNS(ns, 'rect');
      for (const [name, value] of Object.entries({x:left+x*iw,y:top+y*ih,width:rw*iw,height:rh*ih,class:kind})) rect.setAttribute(name, String(value));
      overlay.append(rect);
    }
    box.append(overlay);
    legend = document.createElement('p'); legend.className = 'question-area-legend';
    legend.textContent = row.dataset.questionLabel + ' — Green: include. Red dashed: exclude (takes priority). Current configured areas.';
    tile.append(legend);
  }
  document.addEventListener('mouseover', event => {
    const row = event.target.closest('[data-question-areas]');
    if (row && row !== active) draw(row);
  });
  document.addEventListener('mouseout', event => {
    const row = event.target.closest('[data-question-areas]');
    if (row && !row.contains(event.relatedTarget)) clear();
  });
  document.addEventListener('focusin', event => draw(event.target.closest('[data-question-areas]')));
  document.addEventListener('focusout', event => {
    if (active && !active.contains(event.relatedTarget)) clear();
  });
  document.addEventListener('visibilitychange', () => { if (document.hidden) clear(); });
  document.addEventListener('toggle', () => { if (active) draw(active); }, true);
  document.addEventListener('load', event => { if (active && event.target.closest('[data-processed-image]')) draw(active); }, true);
  window.addEventListener('resize', () => { if (active) draw(active); });
  window.addEventListener('pagehide', clear);
  // Answer polling replaces rows. Resolve the current hover/focus, never keep old areas.
  for (const content of document.querySelectorAll('[data-answer-content]')) {
    new MutationObserver(() => {
      if (active && !active.isConnected) draw(content.querySelector('[data-question-areas]:hover, [data-question-areas]:focus-within'));
    }).observe(content, {childList:true, subtree:true});
  }
})();"""
