"""Server-rendered browser workspace; native forms and SVG, no CDN or frontend build."""
from datetime import datetime, time, timedelta
from importlib.metadata import version
import json
from dataclasses import asdict
from hashlib import sha256
import math
import secrets
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fasthtml.components import (A, Aside, Body, Button, Details, Div, Form, H1, H2, Head,
                                Header, Html, Img, Input, Label, Link, Main, Meta, Nav, Option, P, Pre,
                                Section, Select, Small, Span, Summary, Table, Tbody, Td, Textarea, Th,
                                Thead, Title, Tr, Ul, Li, Script, Noscript)
from fasthtml.common import to_xml
from fasthtml.components import Meter
from fasthtml.svg import Svg, Polyline, Line, Rect, Circle, Text, ft_svg
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from vop.browser_auth import BrowserAuth, configuring
from vop.display import duration, duration_input, answer_kind
from vop.config import identifier
from vop.contracts import AnswerKind, ProviderError, QuestionSpec, utcnow
from vop.inference.mock import MockInferenceEngine
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy, utc, timezone_for
from vop.ui_readiness import capture_dependencies
from vop.answer_images import answer_image_reference
from vop.episodes_ui import TITLE as EPISODES_TITLE, EPISODES_JS, episode_timeline

CSS = """
.image-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin:12px 0}.image-tile{min-width:0}.image-tile>strong{display:block;margin-bottom:8px;font-size:13px}.image-stage{height:200px;border-radius:8px;background:#e8e8ed}.observe-image .image-stage img{width:100%;height:100%;max-height:200px;object-fit:contain}.image-stage:focus-visible{outline:3px solid #72aaff;outline-offset:3px}.observe-image .image-stage:hover img:not([hidden]),.observe-image .image-stage:focus-visible img:not([hidden]){position:fixed;left:50%;top:50%;transform:translate(-50%,-50%);width:min(800px,calc(100vw - 48px));height:min(440px,calc(100vh - 48px));max-width:calc(100vw - 48px);max-height:440px;object-fit:contain;z-index:2000;background:#fff;box-shadow:0 10px 50px #0005;pointer-events:none}@media(max-width:600px){.image-pair{grid-template-columns:1fr}}
.source-selectors .button{gap:8px}.source-count{padding:2px 7px;border-radius:5px;background:#0001;font-size:11px;font-variant-numeric:tabular-nums}.episode-toolbar{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:16px 0}.episode-toolbar input[type=range]{width:180px;padding:0;min-height:32px;accent-color:var(--accent)}.episode-toolbar [data-zoom-value]{min-width:48px;font-size:13px;font-variant-numeric:tabular-nums}.episode-scroll{overflow:auto;max-height:560px;border:1px solid var(--line);border-radius:10px;background:#fff;overscroll-behavior:contain}.episode-scroll:focus-visible{outline:3px solid #72aaff;outline-offset:3px}.episode-scroll svg{display:block;max-width:none}.episode-span{fill:#1768c4}.episode-point{fill:#135aab}.episode-gap{stroke:#b77908;stroke-width:3;stroke-dasharray:5 4}.episode-row-line{stroke:#e4e8ee;stroke-width:1}.episode-axis-bg,.episode-label-bg{fill:#fff}.episode-label-bg{stroke:#e4e8ee;stroke-width:1}.episode-tick{fill:#626268;font-size:11px}.episode-camera,.episode-label-heading{fill:#273445;font-size:12px;font-weight:600}.episode-question{fill:#626268;font-size:11px}.episode-scroll a:hover .episode-span,.episode-scroll a:focus .episode-span{fill:#084d9b}.episode-legend-active{color:#1768c4}.episode-legend-gap{color:#956100}
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1d1d1f;background:#f5f5f7;font-size:15px;--accent:#0066cc;--line:#dcdce0;--muted:#626268}
*{box-sizing:border-box}body{margin:0}a{color:inherit;text-decoration:none}button,input,select,textarea{font:inherit}
.shell{display:grid;grid-template-columns:216px minmax(0,1fr);min-height:100vh}.sidebar{padding:32px 18px;background:#ececf0;position:sticky;top:0;height:100vh;border-right:1px solid var(--line);display:flex;flex-direction:column;overflow:auto}
.brand{font-size:28px;letter-spacing:-1.6px;font-weight:700;padding:0 12px;color:#1d1d1f}.sidebar .app-version{display:inline;margin:0 0 0 8px;font-size:12px;line-height:1}.subtitle{font-size:11px;color:var(--muted);padding:7px 12px;letter-spacing:.4px}
.mode-label{padding:12px;font-weight:600;color:#0055b3}.mode-switch{display:grid;gap:6px;padding:8px;margin:18px 10px 0;border:1px solid #c8cdd7;border-radius:12px;background:#e2e6ed}.mode-switch .mode-label{margin:0;padding:10px 12px;border-radius:8px;background:#dbeaff;text-align:center;font-size:13px}.sidebar .mode-switch form{margin:0}.mode-switch button{width:100%}.navigation{display:grid;gap:4px;margin:34px 0 auto}.navigation a{padding:11px 14px;border-radius:9px;font-weight:500;transition:background 150ms,color 150ms}.navigation a:hover{background:#e0e0e5}.navigation a.current{background:#dbeaff;color:#0055b3}.sidebar small{font-size:11px;line-height:1.7;margin:28px 12px 12px;color:var(--muted)}.sidebar small p{font-size:11px;margin:0}.sidebar form{margin:0 10px}
.sidebar .restart-control{margin:0 10px 10px}.workspace{padding:44px 5vw 72px;min-width:0;max-width:1450px;width:100%;animation:appear 180ms ease-out}.trends-workspace{animation:none}.top{display:flex;justify-content:space-between;align-items:start;gap:24px;margin-bottom:36px}.top p{margin:10px 0 0;max-width:600px}.title-line{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.app-version{font-size:12px;font-weight:400;color:var(--muted);letter-spacing:0;white-space:nowrap}
h1{font-size:34px;letter-spacing:-1.2px;line-height:1.15;margin:0;font-weight:650}h2{font-size:21px;letter-spacing:-.5px;margin:0 0 16px;line-height:1.3;font-weight:600}h3{font-size:16px;margin:22px 0 10px}p{line-height:1.6;margin:8px 0;color:var(--muted)}small,.muted{color:var(--muted);font-size:12px}section{margin:28px 0 36px}section[id]{scroll-margin-top:24px}
.deletion-progress{width:min(440px,calc(100vw - 40px));padding:28px;border:1px solid var(--line);border-radius:16px;box-shadow:0 18px 65px #0003;color:#1d1d1f;background:#fff}.deletion-progress::backdrop{background:#16203566}.deletion-progress progress{display:block;width:100%;height:14px;margin:22px 0;accent-color:var(--accent)}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.button,button{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:10px 18px;border:1px solid transparent;border-radius:9px;background:var(--accent);color:white;font-size:13px;font-weight:600;cursor:pointer;transition:background 150ms,box-shadow 150ms,transform 150ms;line-height:1.3}.button:hover,button:hover{background:#0055b3}.button:active,button:active{transform:scale(.98)}.button.secondary,button.secondary{background:white;color:#0055b3;border-color:#d3d3d9}.button.secondary:hover,button.secondary:hover{background:#f0f5ff;border-color:#a8bfdf}.button.danger,button.danger{background:white;color:#a1252c;border-color:#e4c4c7}.button.danger:hover,button.danger:hover{background:#fff0f1}button:disabled,button:disabled:hover{background:#e8e8ed;color:#6a6a70;border-color:#d8d8df;cursor:not-allowed;transform:none}button[aria-busy=true]{background:#455d78;cursor:progress}.text-link{color:#0055b3;font-size:13px;font-weight:600}.text-link:hover{text-decoration:underline}.back{display:inline-block;color:#0055b3;margin-bottom:24px;font-size:13px}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #72aaff;outline-offset:3px}
form.inline{display:inline-flex;gap:8px;align-items:center}.source-selectors{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:24px}.question-list th,.question-list td{padding:6px 10px}.question-list td small{margin-top:2px}.question-list .actions{gap:6px}.question-list .button,.question-list button{min-height:34px;padding:6px 12px}.question-list>p{margin:6px 0}.filters{display:flex;gap:14px;align-items:end;flex-wrap:wrap;margin:0 0 28px}.filters .field{margin-bottom:0;flex:1 1 180px;min-width:0;max-width:320px}.field{display:grid;gap:8px;margin:0 0 22px}label{font-size:13px;font-weight:600;color:#37373d}input,select,textarea{width:100%;max-width:100%;padding:12px 14px;border:1px solid #c8c8cf;border-radius:9px;background:#fff;color:#1d1d1f;min-height:44px}input[type=checkbox]{width:auto;min-height:0;accent-color:var(--accent)}textarea{min-height:100px;resize:vertical}.settings-tabs{display:flex;gap:6px;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:14px;margin-bottom:28px}.settings-tabs a{padding:10px 14px;border-radius:8px;font-weight:600;color:#48586a}.settings-tabs a[aria-current=page]{background:#dcecff;color:#0055b3}.form-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:18px;align-items:end}.form-grid .field{margin:0}.form-grid button{min-height:44px}.editor{max-width:680px}.camera-editor section{padding:18px 0;margin:0;border-bottom:1px solid var(--line)}.camera-editor section:first-of-type{padding-top:0}.camera-related{max-width:680px;margin-top:24px;padding-top:20px;border-top:1px solid var(--line)}.camera-related h2{margin:0 0 10px}.camera-editor section h2{margin:0 0 14px}.camera-editor .field{margin-bottom:12px}.camera-editor section>p{margin:8px 0}.camera-editor .pair{gap:16px}.editor .actions{margin-top:30px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.surface{background:white;border:1px solid #e0e0e5;border-radius:16px;padding:28px 30px}.object-list{margin-top:24px}.object-row{padding:26px 0;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:24px}.object-row:first-child{padding-top:0}.camera-list .object-row{padding:12px 0;gap:16px}.camera-list .object-row:first-child{padding-top:0}.camera-list .object-row p{margin:2px 0}.camera-list .actions{gap:8px}.camera-list .button{min-height:36px;padding:7px 12px}.object-row h2{margin:0 0 5px}.object-row p{margin:4px 0}.object-meta{font-size:13px}.object-copy{min-width:0;overflow-wrap:anywhere}.object-row .actions{flex-shrink:0}.empty{padding:48px 0;max-width:560px}.empty p{margin:12px 0 24px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:20px}.section-heading h2{margin:0}.capture-source{padding:24px 0;border-bottom:1px solid var(--line)}.capture-source .actions{margin-top:16px}.capture-source>small{display:block;margin:5px 0}.divider{border:0;border-top:1px solid var(--line);margin:24px 0}
table{border-collapse:collapse;width:100%;text-align:left}th{font-size:11px;color:var(--muted);font-weight:600;padding:12px 14px;border-bottom:1px solid var(--line);white-space:nowrap}td{padding:18px 14px;border-bottom:1px solid #e8e8ed;vertical-align:top;font-size:13px}td strong{font-weight:600}td small{display:block;line-height:1.6;margin-top:5px}tr:hover td{background:#eeeef3}.table-wrap{overflow:auto}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;margin:0 0 36px;padding:22px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.stat strong{display:block;font-size:32px;font-weight:600;letter-spacing:-1px;margin-top:10px}.stat small{font-size:12px}.status,.tag{display:inline-block;padding:5px 9px;border-radius:6px;background:#e8e8ed;color:#4f4f58;font-size:11px;font-weight:600;line-height:1.4;white-space:nowrap}.tag{color:#0055b3;background:#e5efff}.status.ACTIVE,.status.HEALTHY,.status.success,.status.closed,.status.OBSERVED,.status.delivered,.status.resolved{background:#e0f1e9;color:#206146}.status.UNKNOWN,.status.PENDING,.status.RECOVERING,.status.interrupted,.status.CONNECTING,.status.warning,.status.open{background:#fff0d7;color:#7e520c}.status.DISCONNECTED,.status.model_failure,.status.capture_failure,.status.timeout,.status.error,.status.critical,.status.failed{background:#fbe6e6;color:#a1252c}.status.info,.status.acknowledged{background:#e5efff;color:#205a94}
.readiness,.notice,.error{padding:14px 18px;border-radius:10px;margin:16px 0;font-size:13px;line-height:1.6;background:#eef1f5;color:#414854}.readiness p{color:inherit}.readiness ul{margin:5px 0;padding-left:18px}.readiness li{margin:4px 0}.readiness a{text-decoration:underline;text-underline-offset:3px}.readiness.success{background:#e5f2ec;color:#246147}.readiness.warning{background:#fff2df;color:#7a510e}.readiness.error,.error{background:#fbe9e9;color:#9a282f}.readiness.info,.notice{background:#e8f0fc;color:#285483}.readiness.success{padding:0;background:transparent}.readiness.success:before{content:'●';color:#26835b;margin-right:8px}
details{margin:22px 0;border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;font-size:13px;font-weight:600;color:#45454c;padding:10px 0}details[open]>summary{margin-bottom:12px}pre{font:12px/1.6 Consolas,monospace;overflow:auto;background:#ececf1;padding:18px;border-radius:9px;white-space:pre-wrap;word-break:break-word}.preview{max-width:100%;max-height:480px;object-fit:contain;border-radius:12px;background:#e8e8ed}.evidence-box{display:inline-block;position:relative;max-width:100%}.evidence-box .preview{display:block}.camera-test-result .evidence-box{display:block;width:fit-content;margin-bottom:24px}.camera-test-actions{margin-top:24px}.camera-test-actions .button{white-space:nowrap}.observe-image{border:4px solid #b77908;border-radius:16px;padding:8px;margin:18px 0;background:#fffaf0;max-width:800px}.observe-image.monitoring{border-color:#168153;background:#f0faf4}.observe-image img{max-width:100%;max-height:440px;object-fit:contain;border-radius:8px}.observe-image img:not([hidden]){display:block}.observe-image [data-monitoring-label]{font-weight:600}.observe-image p{margin:8px 0}.roi-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.roi-overlay rect{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}.answer-bar{display:grid;gap:5px;min-width:160px;margin-bottom:8px}.answer-bar span{font-size:12px}.answer-bar meter{width:100%;height:16px;accent-color:var(--accent)}.answer-bar meter::-webkit-meter-optimum-value{background:var(--accent)}.answer-bar meter::-moz-meter-bar{background:var(--accent)}.image-disclosure{border:0;padding:0;margin:8px 0 0}.image-disclosure>summary{display:inline-flex;padding:10px 18px;list-style:none}.image-disclosure>summary::-webkit-details-marker{display:none}.image-disclosure .hide-image{display:none}.image-disclosure[open] .hide-image{display:inline}.image-disclosure[open] .show-image{display:none}.observe-controls{display:flow-root;margin-top:16px}.capture-source .observe-controls>.actions{float:left;margin:0 10px 0 0}.camera-answers{border:0;padding:0;margin:0}.camera-answers>p,.camera-answers>[data-answer-content]{clear:both}.camera-answers>p{margin:6px 0}.camera-answers[open]>summary{margin-bottom:6px}.camera-answers th,.camera-answers td{padding:6px 10px}.camera-answers td small{margin-top:2px}.camera-answers .answer-bar{gap:2px;margin-bottom:3px}.camera-answers .answer-bar meter{height:12px}.camera-answers>summary{display:inline-flex;padding:10px 18px;color:#0055b3;list-style:none}.camera-answers>summary::-webkit-details-marker{display:none}.camera-answers .hide-answers{display:none}.camera-answers[open] .hide-answers{display:inline}.camera-answers[open] .show-answers{display:none}.login{max-width:440px;margin:12vh auto;padding:32px}.login .brand{padding:0}
.chart{width:100%;height:150px;display:block;max-width:700px}.chart line{stroke:#dcdce0;stroke-width:1}.chart polyline{stroke:var(--accent);stroke-width:2;fill:none}.chart circle{fill:var(--accent)}.chart text{font-size:10px;fill:#626268}.chart .unobserved{fill:#fff0d7;stroke:none}.chart-legend{font-size:12px;color:#7e520c;margin:6px 0 12px}.chart-legend span{display:inline-block;background:#fff0d7;border:1px solid #ae7925;width:14px;height:10px;margin-right:6px}[hidden]{display:none!important}
@keyframes appear{from{opacity:.6;transform:translateY(4px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media(max-width:1000px){.object-row{align-items:start;flex-direction:column;gap:14px}.workspace{padding:36px 30px}.stats{gap:14px}.stat strong{font-size:27px}}
@media(max-width:700px){.shell{grid-template-columns:1fr}.sidebar{height:auto;position:static;padding:18px;border-right:0;border-bottom:1px solid var(--line)}.navigation{display:flex;overflow:auto;gap:4px;margin:18px 0 0;padding-bottom:4px}.navigation a{white-space:nowrap}.sidebar small,.subtitle{display:none}.sidebar>form{align-self:end;margin-top:12px}.workspace{padding:28px 20px 48px}.top{margin-bottom:26px;flex-direction:column;gap:14px}h1{font-size:30px}.stats{grid-template-columns:1fr 1fr;gap:20px}.pair{grid-template-columns:1fr;gap:0}.surface{padding:22px 20px}.section-heading{align-items:start}.object-row .actions{flex-shrink:1}.filters .field{max-width:none}}
"""

QUESTION_EDITOR_JS = """const form = document.querySelector('[data-question-editor]');
if (form) {
  const kind = form.querySelector('[name="kind"]');
  const update = () => {
    for (const group of form.querySelectorAll('[data-answer-kind]')) {
      const active = group.dataset.answerKind === kind.value;
      group.hidden = !active;
      for (const input of group.querySelectorAll('input, select, textarea')) input.disabled = !active;
    }
  };
  kind.addEventListener('change', update);
  update();
}
"""

WORKSPACE_JS = """document.addEventListener('submit', (event) => {
  const button = event.submitter;
  if (!button) return;
  button.setAttribute('aria-busy', 'true');
  button.textContent = 'Working…';
});"""


OBSERVE_IMAGES_JS = """const previews = document.querySelectorAll('[data-observe-preview]');
async function refreshPreview(card) {
  const image = card.querySelector('img');
  const empty = card.querySelector('[data-preview-empty]');
  const caption = card.querySelector('[data-preview-caption]');
  try {
    const response = await fetch(card.dataset.imageUrl, {method:'HEAD', cache:'no-store', signal:AbortSignal.timeout(5000)});
    if (!response.ok) {
      if (response.status === 401 || response.status === 403) { image.hidden = true; empty.hidden = false; }
      return;
    }
    const monitoring = response.headers.get('X-VOP-Monitoring') === 'true';
    const panel = card.querySelector('[data-image-panel]');
    if (card.dataset.monitoring !== String(monitoring)) panel.open = monitoring;
    card.dataset.monitoring = String(monitoring);
    const previewState = response.headers.get('X-VOP-Preview-State');
    card.classList.toggle('monitoring', monitoring);
    card.querySelector('[data-monitoring-label]').textContent = monitoring ? 'Monitoring' : 'Paused';
    // Keep checking monitoring status while hidden, but do not fetch image pixels
    // or renew the live decoder lease until the operator shows the image again.
    if (!panel.open) return;
    if (card.dataset.leaseUrl && Date.now() >= Number(card.dataset.renewAt || 0)) {
      const lease = await fetch(card.dataset.leaseUrl, {method:'POST', body:new URLSearchParams({csrf:card.dataset.csrf}), cache:'no-store', signal:AbortSignal.timeout(5000)});
      card.dataset.leaseFailed = lease.ok ? '' : 'true';
      card.dataset.renewAt = Date.now() + 5000;
    }
    if (response.status === 204) {
      image.hidden = true; image.removeAttribute('src'); empty.hidden = false;
      empty.textContent = card.dataset.leaseFailed ? 'Live preview could not start. Check this camera in Configure mode.' : response.headers.get('X-VOP-Preview-Error') === 'preview_capacity' ? 'Use the camera filter to show no more than four live previews.' : previewState === 'connecting' ? 'Connecting to camera…' : previewState === 'reconnecting' ? 'Reconnecting to camera. Check its saved details if this continues.' : 'No image available. Start monitoring or use Observe now.';
      card.dataset.frame = ''; caption.textContent = ''; return;
    }
    const frame = response.headers.get('X-VOP-Frame-Id');
    if (card.dataset.frame !== frame || image.hidden || !image.naturalWidth) {
      // Decode off-screen; keep the displayed pixels until the replacement is ready.
      const replacement = new Image();
      replacement.alt = image.alt;
      replacement.src = card.dataset.imageUrl + '?frame=' + encodeURIComponent(frame);
      await replacement.decode();
      if (!panel.open || document.hidden) return;
      image.replaceWith(replacement);
      empty.hidden = true;
      card.dataset.frame = frame;
    }
    const stamp = new Date(response.headers.get('X-VOP-Captured-At')).toLocaleString();
    const kind = response.headers.get('X-VOP-Preview-Kind');
    const state = response.headers.get('X-VOP-Preview-State');
    const note = response.headers.get('X-VOP-Preview-Error') === 'preview_capacity' ? 'Show fewer cameras for live previews. ' : card.dataset.leaseFailed ? 'Live preview unavailable; check camera setup. ' : state === 'connecting' ? 'Connecting. ' : state === 'reconnecting' ? 'Reconnecting. ' : '';
    caption.textContent = note + (kind === 'live' ? (state === 'live' ? 'Live preview: ' : 'Last preview: ') : kind === 'saved' ? 'Latest saved image: ' : 'Latest image: ') + stamp;
  } catch (_) { /* Keep the last received image during a temporary connection failure. */ }
}
async function refreshPreviews() {
  if (!document.hidden) for (const card of previews) {
    if (card.pending) continue;
    card.pending = true;
    refreshPreview(card).finally(() => { card.pending = false; });
  }
  setTimeout(refreshPreviews, 200);
}
refreshPreviews();
"""


OBSERVE_ANSWERS_JS = """async function updateProcessedImage(panel, response) {
  if (!panel.dataset.processedTarget) return;
  const tile = document.getElementById(panel.dataset.processedTarget);
  if (!tile) return;
  const image = tile.querySelector('img');
  const empty = tile.querySelector('[data-processed-empty]');
  const caption = tile.querySelector('[data-processed-caption]');
  if (response) {
    tile.dataset.wantedFrame = response.headers.get('X-VOP-Processed-frame') || '';
    for (const key of ['url','captured','message']) tile.dataset[key] = response.headers.get('X-VOP-Processed-' + key) || '';
  }
  function clear(message) {
    const shown = tile.querySelector('img');
    shown.hidden=true; shown.removeAttribute('src'); tile.dataset.frame='';
    empty.hidden=false; empty.textContent=message; caption.textContent='';
  }
  if (!tile.dataset.url) { clear(tile.dataset.message || 'Sign in to view the answer image.'); return; }
  const disclosure = tile.closest('[data-image-panel]');
  if (!disclosure.open || document.hidden) {
    if (tile.dataset.frame !== tile.dataset.wantedFrame) clear('Show images to load the latest answer frame.');
    return;
  }
  try {
    if (tile.dataset.frame !== tile.dataset.wantedFrame || image.hidden || !image.naturalWidth) {
      const replacement = new Image(); replacement.alt=image.alt; replacement.src=tile.dataset.url;
      let timer;
      try {
        await Promise.race([replacement.decode(),new Promise((_,reject)=>{
          timer=setTimeout(()=>reject(new Error('Image timed out')),5000);
        })]);
      } finally { clearTimeout(timer); }
      if (!disclosure.open || document.hidden) { clear('Show images to load the latest answer frame.'); return; }
      image.replaceWith(replacement); tile.dataset.frame=tile.dataset.wantedFrame; empty.hidden=true;
    }
    caption.textContent = tile.dataset.message + ' ' + new Date(tile.dataset.captured).toLocaleString(undefined,{timeZone:panel.dataset.zone || undefined});
  } catch (_) { clear('Answer image unavailable. Retrying…'); }
}
const panels = document.querySelectorAll('[data-answer-url]');
async function refreshAnswers(panel) {
  if (document.hidden || panel.pending) return;
  panel.pending = true;
  const showing = panel.open;
  try {
    const response = await fetch(panel.dataset.answerUrl + (showing ? '' : '&counts_only=1'), {cache:'no-store', signal:AbortSignal.timeout(5000),
      headers: panel.dataset.etag ? {'If-None-Match':panel.dataset.etag} : {}});
    if (response.status === 200) {
      const html = await response.text();
      await updateProcessedImage(panel,response);
      for (const kind of ['active', 'unknown']) {
        const count = response.headers.get('X-VOP-' + kind);
        if (count === null) continue;
        panel.dataset[kind] = count;
        const total = document.querySelector('[data-condition-count="' + kind + '"]');
        if (total) total.textContent = Array.from(panels).reduce((sum, item) => sum + Number(item.dataset[kind] || 0), 0);
      }
      panel.dataset.etag = response.headers.get('ETag') || '';
      if (showing && panel.open && !document.hidden) {
        panel.querySelector('[data-answer-content]').innerHTML = html;
      }
    } else if (response.status === 304) await updateProcessedImage(panel);
    else if (response.status === 401 || response.status === 403) await updateProcessedImage(panel,response);
  } catch (_) { /* Keep the last answers during a temporary connection failure. */ }
  finally { panel.pending = false; }
}
for (const panel of panels) {
  panel.addEventListener('toggle', () => { if (panel.open) refreshAnswers(panel); });
  async function poll() {
    await refreshAnswers(panel);
    setTimeout(poll, panel.open ? 200 : 1000);
  }
  poll();
}
"""


TRENDS_REFRESH_JS = """const filters = document.querySelector('form.filters');
if (filters) {
  const saved = new URLSearchParams(new FormData(filters)).toString();
  setInterval(() => {
    if (document.hidden || filters.contains(document.activeElement)) return;
    if (new URLSearchParams(new FormData(filters)).toString() !== saved) return;
    location.reload();
  }, 10000);
}
"""


def badge(value):
    return Span(metric_label(str(value)), cls=f"status {value}")


def local_time(value, zone):
    return utc(value).astimezone(ZoneInfo(zone)).strftime("%d %b %H:%M:%S %Z %z") if value else "No observation"


def hidden(csrf):
    return Input(type="hidden", name="csrf", value=csrf)


def action(label, path, csrf, *, secondary=False):
    return Form(hidden(csrf), Button(label, type="submit", cls="secondary" if secondary else ""), method="post", action=path, cls="inline")


def restart_control(csrf):
    return Form(hidden(csrf), Button('Restart VOP', type='submit', cls='secondary'),
                P('Saved settings and monitoring will be restored.', cls='muted', role='status', hidden=True),
                method='post', action='/ui/restart', data_vop_restart='', cls='restart-control')


def dependency_panel(problems, *, ready="Local prerequisites met; connection is checked when you run the action."):
    return Div(StrongText("Needs attention" if problems else "Ready to try"),
               Ul(*(Li(A(message, href=href)) for message, href in problems)) if problems else P(ready),
               cls="readiness warning" if problems else "readiness success", role="status")


def field(label, name, value="", *, type="text", required=False, **kwargs):
    control_id = kwargs.pop("id", name)
    return Div(Label(label, _for=control_id), Input(id=control_id, name=name, value=value, type=type, required=required, **kwargs), cls="field")


METRIC_HELP = {
    "Configured sources": "Number of saved image inputs in this view, This does not mean that each input is connected or monitoring.",
    "Active conditions": "Number of confirmed active questions, including episodes awaiting end confirmation (RECOVERING). This counts questions, not people or cameras. Updates automatically for the selected cameras.",
    "Unknown conditions": "Number of questions whose current condition cannot be determined. Causes include missing, failed or stale answers, disabled questions, and disabled inputs. Unknown does not mean absent.",
    "Episodes recorded": "Number of confirmed episodes stored for the selected inputs, across question versions. Repeated positive samples in the same episode do not add to this count.",
    "Episodes": "Number of confirmed episodes that started in the selected range. An episode begins after the required positive confirmations; repeated positive samples do not create new episodes.",
    "Estimated active time": "Sum of covered intervals in confirmed episodes, including intervals while awaiting end confirmation. Unobserved gaps are excluded. This is an estimate from samples, not proof of continuous presence.",
    "Episode rate": "Confirmed episode starts per covered hour in the selected range. Unobserved gaps are excluded from the time used to calculate this rate.",
    "Unobserved time": "Time in the measured range that could not be covered by valid samples within the allowed gap. It includes failed intervals, long gaps and stale time. No active condition is assumed during this time.",
    "ACTIVE": "The condition has met the required positive confirmations. This is a sampled state, not proof of continuous presence.",
    "INACTIVE": "No episode is active. The required negative confirmations have ended any previous episode.",
    "PENDING": "A positive answer was received, but more positive confirmations are needed before an episode is confirmed.",
    "RECOVERING": "An episode is active, but negative answers are awaiting the required end confirmations.",
    "UNKNOWN": "There is no reliable current answer. Samples may be missing, failed or stale, or the input or question may be disabled. Unknown does not mean absent.",
    "OBSERVED": "A valid choice or ordinal answer was received. Yes/No episode confirmation states do not apply to this answer type.",
    "DISABLED": "This input is disabled. Enable it before requesting new observations.",
    "CONNECTING": "The input is enabled, but a successful frame has not yet confirmed its connection.",
    "HEALTHY": "The latest recorded capture succeeded. This is not a live guarantee that the camera is still connected.",
    "DISCONNECTED": "The latest capture failed. Check the camera connection and saved setup, then retry.",
    "Condition active": "Estimated share of covered time in confirmed active episodes. Episode confirmation rules apply. Higher means the condition was active more often; whether that is desirable depends on the question. Unobserved gaps are excluded. This is a sampled estimate, not proof of continuous presence.",
    "Observation coverage": "Share of the measured time supported by valid samples within the allowed gap. Higher means more complete timing evidence, not better model accuracy. No interval data means there is not enough timing evidence to calculate it.",
    "Covered time": "Time between consecutive valid samples that are no farther apart than the allowed gap. Failed samples and longer gaps are excluded. This is an estimate, not proof of continuous observation.",
    "Valid samples": "Number of successful answers with a usable value in the selected range. Failed, missing and temporally excluded answers are not counted.",
    "Unobserved gap": "Time within this episode for which VOP could not estimate the condition because samples failed or were too far apart. This time is excluded from estimated duration.",
    "Estimated duration": "Sum of covered intervals while the episode was active or awaiting confirmation that it ended. Unobserved gaps are excluded. This is an estimate from samples, not the full wall-clock span or proof of continuous presence.",
}


def metric_label(label):
    explanation = METRIC_HELP.get(label)
    return Span(label, title=explanation, tabindex="0", aria_label=label + ". " + explanation,
                style="cursor:help;text-decoration:underline dotted;text-underline-offset:4px") if explanation else label


def answer_label(value, levels=()):
    """Describe the expected ordinal position; never round it into a category."""
    if value is None:
        return "Unknown"
    if levels:
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= len(levels) - 1:
            return "Unknown"
        low, high = math.floor(value), math.ceil(value)
        return (levels[low] if low == high else f"Between {levels[low]} and {levels[high]}") + f" ({value:.1f})"
    return ("Yes" if value else "No") if type(value) is bool else (f"{value:.1f}" if isinstance(value, (int, float)) else str(value))


def chart(points, label):
    numeric = [p["value"] for p in points if isinstance(p["value"], (int, float))]
    if not numeric:
        return P("No numeric observations in this view.", cls="muted")
    maximum = max(1, max(numeric))
    segments, current, gaps, dots = [], [], [], []
    for i, point in enumerate(points):
        value = point["value"]
        x = 18 + i * 640 / max(1, len(points) - 1)
        stamp = point.get("local_label") or point.get("at_utc") or f"Sample {i + 1}"
        if i and (point.get("gap_before") or not isinstance(value, (int, float)) or not isinstance(points[i-1]['value'], (int, float))):
            previous_x = 18 + (i - 1) * 640 / max(1, len(points) - 1)
            previous_stamp = points[i-1].get('local_label') or points[i-1].get('at_utc') or f"Sample {i}"
            gaps.append(ft_svg('rect', Title(f"Unobserved interval: {previous_stamp} to {stamp}. No continuous observation is inferred."),
                             x=previous_x, y=14, width=x-previous_x, height=116, cls="unobserved"))
        if point.get("gap_before") and current:
            segments.append(current)
            current = []
        if not isinstance(value, (int, float)):
            if current:
                segments.append(current)
            current = []
        else:
            y = 125 - float(value) * 105 / maximum
            current.append((x, y))
            dots.append(ft_svg('circle', Title(f"{stamp} · value {answer_label(value)}"), cx=x, cy=y, r=2.5))
    if current:
        segments.append(current)
    return Div(Svg(*gaps, *(Line(x1=18, y1=y, x2=658, y2=y) for y in (20, 72, 125)),
               Text(f"{maximum:.1f}", x=2, y=20), Text("0.0", x=2, y=125),
               *(Polyline(points=" ".join(f"{x:.2f},{y:.2f}" for x, y in segment)) for segment in segments),
               *dots,
               viewBox="0 0 680 150", role="img", aria_label=label + "; amber bands mark unobserved gaps; gaps are not connected", cls="chart"),
               P(Span(aria_hidden="true") if gaps else None, "Amber shading: unobserved interval — points are intentionally not joined." if gaps else "Solid lines join successful samples within the allowed observation gap.", cls="chart-legend" if gaps else "muted"))


def evidence_image(url, label, rois=()):
    return Div(Img(src=url, alt=label, cls="preview"),
               Svg(*(Rect(x=roi[0], y=roi[1], width=roi[2], height=roi[3]) for roi in rois if roi),
                   viewBox="0 0 1 1", preserveAspectRatio="none", cls="roi-overlay", role="img", aria_label="Configured query regions") if any(rois) else None,
               cls="evidence-box")


def install_dashboard(app, settings, store, pipeline, engine, token, viewer_token=None):
    app_version = version('vop')

    def source_name(source_id):
        source = pipeline.sources.get(source_id) or pipeline.removed_sources.get(source_id)
        if source and source.name:
            return source.name
        with store.connection() as db:
            row = db.execute('SELECT configuration FROM sources WHERE id=?', (source_id,)).fetchone()
        return (json.loads(row[0]).get('name') if row else None) or source_id

    def page(title, request, content, *, view="overview", notice=None):
        session = request.scope["session"]
        csrf = session.setdefault("csrf", secrets.token_urlsafe(24))
        role = request.scope.get("auth_role") or session.get("role")
        configure = configuring(request)
        navigation = [("overview", "Observe", "/"), ("cameras", "Cameras", "/cameras"), ("engines", "Engines", "/engines"),
                      ("questions", "Questions", "/?view=questions"), ("observations", "Individual Observations", "/observations"), ("events", EPISODES_TITLE, "/?view=events"),
                      ("metrics", "Trends", "/?view=metrics"), ('activity', 'Activity', '/activity'),
                      ('actions', 'Actions', '/actions'), ('automations', 'Automations', '/automations'), ("settings", "Settings", "/release")]
        descriptions = {"overview": "Run an observation. Read the result.", "cameras": "Set up image inputs.",
                        "engines": "Set up and select the engine that answers questions.", "questions": "Choose what to ask about each image.",
                        "events": "Review episodes built from individual checks. These are sampled estimates, not continuous video.", "observations": "Review individual checks and their saved images, when available.", "metrics": "Review change over time.", "settings": "Manage this workspace."}
        return Html(Head(Title(f"{title} · VOP v{app_version}"), Meta(charset="utf-8"), Meta(name="viewport", content="width=device-width, initial-scale=1"), Link(rel="stylesheet", href="/ui/style.css")),
                    Body(Div(Aside(A("VOP", Small('v' + app_version, cls='app-version', aria_label='VOP version ' + app_version), href='/cameras' if configure else '/', cls="brand"), Div("Visual Observability", cls="subtitle"),
                                   Nav(*(A(label, href=url, cls="current" if key == view else "", aria_current="page" if key == view else None) for key, label, url in navigation
                                         if configure and key in ('cameras', 'engines', 'questions', 'actions', 'automations', 'settings') or not configure and key in ("overview", "observations", "events", "metrics", 'activity')), cls="navigation", aria_label="Main"),
                                   Div(P('Configure mode' if configure else 'View mode', cls='mode-label', role='status'),
                                   Form(hidden(csrf), Input(type='hidden', name='mode', value='view' if configure else 'configure'),
                                        Button('View mode' if configure else 'Configure mode', cls='secondary', aria_label='Switch to View mode' if configure else 'Switch to Configure mode'), method='post', action='/ui/mode') if role == 'operator' else None, cls='mode-switch', role='group', aria_label='Workspace mode'),
                                   Button('Enable sound', type='button', data_enable_sound='', data_csrf=csrf) if role == 'operator' else None,
                                   Small("Local observation workspace", P("Viewer access" if role == "viewer" else "Operator access")),
                                   restart_control(csrf) if configure and app.state.shutdown_request else None,
                                   action("Sign out", "/logout", csrf, secondary=True), cls="sidebar"),
                             Main(Header(Div(H1(title), P(descriptions.get(view, ""))),
                                         A("Demo engine" if pipeline.engine.synthetic else pipeline.engine.engine_id, href="/engines", cls="tag") if view == "overview" and configure else None, cls="top"),
                                  Div(notice, cls="notice", role="status") if notice else None, *content, cls="workspace trends-workspace" if view == "metrics" else "workspace", id="workspace"), cls="shell"),
                         Script(src='/ui/actions.js', defer=True) if role == 'operator' or view == 'activity' else None,
                         Script(src='/ui/workspace.js', defer=True) if getattr(pipeline, 'auto_worker', None) else None,
                         Script(src='/ui/restart.js', defer=True) if configure and app.state.shutdown_request else None,
                         Script(src='/ui/observe-images.js', defer=True) if view == 'overview' and not configure else None,
                         Script(src='/ui/observe-answers.js', defer=True) if view == 'overview' and not configure else None,
                         Script(src='/ui/trends-refresh.js', defer=True) if view == 'metrics' else None,
                         Script(src='/ui/episodes.js', defer=True) if view == 'events' else None,
                         Script(src='/ui/question-counts.js', defer=True) if view == 'questions' else None))

    def recorded_label(source_id, answer):
        if answer.get("status") != "success":
            return "Unknown"
        # Historical answers keep the level names from their immutable question version.
        with store.connection() as db:
            row = db.execute("SELECT specification FROM question_versions WHERE source_id=? AND question_id=? AND version=?",
                             (source_id, answer["question_id"], answer["question_version"])).fetchone()
        spec = json.loads(row[0]) if row else {}
        return answer_label(answer.get("value"), spec.get("levels", ()) if spec.get("kind") == "ordinal" else ())

    def image_settings(source_id, operator, configure=True):
        enabled = store.source_control(source_id)['retain_evidence']
        return Div(P('Image saving is ' + ('ON. Future captures will keep a privacy-masked still image.' if enabled else 'OFF. Future captures keep answers without saving an image.'), role='status'),
                   P('This setting affects future captures only. It does not restore unsaved or deleted images, or delete images already saved.', cls='muted'),
                   A('Change image-saving setting', href=('/cameras/' + source_id if source_id in pipeline.sources and pipeline.sources[source_id].kind in ('rtsp', 'usb') else '/ui/sources/' + source_id) + '#image-saving', cls='button secondary') if operator and configure and source_id in pipeline.sources else
                   P('Use Configure mode to change image saving.' if operator and not configure else 'Restore this input to change its settings.' if operator else 'An operator can change image saving.', cls='muted'), cls='readiness info')

    def recorded_image_status(observation, operator):
        frame_id = observation['provenance']['frame_id']
        if not frame_id:
            return 'No image captured'
        if not operator:
            return 'Operator access required'
        return A('View saved image', href='/ui/observations/' + observation['id'] + '#recorded-image', cls='text-link') if observation['image_saved'] else 'No image saved'

    app.state.image_settings = image_settings

    def summaries(source_filter=None, *, zone=None, range_start=None, range_end=None):
        result = []
        chosen = {source_filter} if isinstance(source_filter, str) else source_filter
        for source_id in list(pipeline.sources):
            if chosen and source_id not in chosen:
                continue
            for record in store.questions(source_id):
                q = record["spec"]
                summary = store.summary(source_id, q.question_id, q.version, kind=q.kind, as_of=utcnow(), timezone_name=zone or settings.timezone_name,
                                        range_start=range_start, range_end=range_end)
                if not record["enabled"] or not store.source_control(source_id)["enabled"]:
                    summary.update(state="UNKNOWN", latest_value=None, disabled=True)
                result.append({"source_id": source_id, **record, "summary": summary})
        return result

    def latest_image(source_id):
        live = pipeline.live_previews.image(source_id)
        cached = pipeline.previews.get(source_id)
        if live and (not cached or live[2] >= cached[2]):
            return live
        if cached:
            return (*cached, 'temporary', 'image/png')
        saved = store.latest_evidence(source_id)
        return (*saved, 'saved', 'image/png') if saved else None

    def observe_image(source, monitoring, csrf, answers):
        sid = source['source_id']
        image = latest_image(sid)
        url = '/ui/live-preview/' + sid
        ids = [d['summary']['last_observation_id'] for d in answers if d['enabled'] and not d['summary'].get('disabled')]
        processed = answer_image_reference(store,pipeline,sid,ids)
        return Div(Span('Monitoring' if monitoring else 'Paused', data_monitoring_label=''),
            Details(Summary(Span('Show images', cls='show-image'), Span('Hide images', cls='hide-image'), cls='button secondary'),
                Div(Div(StrongText('Live view' if source['kind'] in ('rtsp','usb') else 'Current image'),
                Div(Img(src=url if image and monitoring else None, alt='Latest privacy-masked image from ' + source['name'], hidden=not (image and monitoring)),
                    cls='image-stage',tabindex=0,aria_label='Enlarge live image from ' + source['name']),
                P('Loading image…' if image else 'No image available. Start monitoring or use Observe now.', hidden=bool(image and monitoring), data_preview_empty=''),
                Noscript(P(A('Open latest image', href=url, cls='text-link'))) if image and not monitoring else None,
                P(('Latest saved image: ' if image and image[3] == 'saved' else 'Latest image: ') + local_time(image[2], settings.timezone_name) if image else '',
                  data_preview_caption='', cls='muted'),cls='image-tile'),
                Div(StrongText('Last processed image'),
                    Div(Img(src=processed['url'] if processed['url'] and monitoring else None,
                            alt='Source frame used for latest answers from ' + source['name'],hidden=not (processed['url'] and monitoring)),
                        cls='image-stage',tabindex=0,aria_label='Enlarge processed image from ' + source['name']),
                    P(processed['message'],hidden=bool(processed['url'] and monitoring),data_processed_empty=''),
                    P(local_time(processed['captured'],settings.timezone_name) if processed['captured'] else '',data_processed_caption='',cls='muted'),
                    Noscript(P(A('Open processed image',href=processed['url'],cls='text-link'))) if processed['url'] else None,
                    id='processed-image-' + sid,cls='image-tile',data_processed_image='',data_frame=processed['frame'],
                    data_url=processed['url'],data_captured=processed['captured'],data_message=processed['message']),cls='image-pair'),
                Small('Hover over an image or focus it to enlarge.'),
                open=monitoring, data_image_panel='', cls='image-disclosure', aria_label='Images from ' + source['name']),
            cls='observe-image monitoring' if monitoring else 'observe-image', data_observe_preview=sid,
            data_monitoring=str(monitoring).lower(), data_image_url=url, data_frame=image[0] if image else '', data_csrf=csrf,
            data_lease_url=url + '/keepalive' if pipeline.live_previews.allowed and source['kind'] in ('rtsp', 'usb') else None)

    def answer_graph(spec, value, native):
        if value is None:
            return Small('No current value', cls='muted')

        def bar(label, amount, maximum, explanation):
            return Div(Span(label), Meter(value=amount, min=0, max=maximum,
                title=explanation, aria_label=label), cls='answer-bar')

        if spec.kind == 'ordinal':
            return bar(f'{float(value):.1f} / {len(spec.levels) - 1:.1f}', value, len(spec.levels) - 1,
                       'Returned rating on the configured level scale. Higher means a later level, not necessarily better.')
        if spec.kind == 'binary':
            score = native.get('score')
            if native.get('score_semantics') == 'Liquid noul: model score for yes' and isinstance(score, (int, float)) and not isinstance(score, bool) and math.isfinite(score) and 0 <= score <= 1:
                return bar(f'Yes score: {score * 100:.1f}%', score, 1,
                           'Model score for Yes. This is not a calibrated probability or a measure of accuracy.')
            return bar('Yes (1.0)' if value else 'No (0.0)', int(value), 1,
                       'Returned Yes/No answer: Yes fills the bar; No leaves it empty. No confidence score is implied.')
        raw = native.get('raw_provider_fields')
        probabilities = raw.get('probabilities', {}) if isinstance(raw, dict) else {}
        scored = isinstance(probabilities, dict) and set(probabilities) == set(dict(spec.choices)) and all(
            isinstance(n, (int, float)) and not isinstance(n, bool) and math.isfinite(n) and 0 <= n <= 1 for n in probabilities.values())
        return Div(*(bar(f'{name}: {probabilities[name] * 100:.1f}%' if scored else f'{name}: ' + ('Selected' if name == value else 'Not selected'),
                         probabilities[name] if scored else int(name == value), 1,
                         'Native model option score; not a calibrated probability.' if scored else 'Selected category only; no option score was returned.')
                     for name, _ in spec.choices), cls='answer-options')

    def camera_answer_content(answers, zone):
        rows = []
        ids = [d['summary']['last_observation_id'] for d in answers if d['summary']['last_observation_id']]
        native_answers = {}
        if ids:
            with store.connection() as db:
                native_answers = {row['id']: json.loads(row['answer_json']) for row in db.execute(
                    'SELECT id,answer_json FROM observations WHERE id IN (' + ','.join('?' for _ in ids) + ')', ids)}
        for d in answers:
            summary, spec = d['summary'], d['spec']
            native = native_answers.get(summary['last_observation_id'], {})
            rows.append(Tr(Td(StrongText(spec.text), Small('Version ' + spec.version)),
                Td(badge(summary['state'])), Td(answer_label(summary['latest_value'], spec.levels)),
                Td(answer_graph(spec, summary['latest_value'], native)),
                Td(local_time(summary['last_observed_at_utc'], zone))))
        return table(['Question', 'Episode State', 'Last answer', 'Value', 'Observed'], rows) if answers else P('No questions are configured for this camera.', cls='muted')

    def condition_counts(answers):
        return {'active': sum(d['summary']['state'] in ('ACTIVE', 'RECOVERING') for d in answers),
                'unknown': sum(d['summary']['state'] == 'UNKNOWN' for d in answers)}

    def camera_answers(source, answers, zone):
        return Details(Summary(Span('Show answers', cls='show-answers'), Span('Hide answers', cls='hide-answers'), cls='button secondary'),
            P('Answers update after each observation. Live images update separately.', cls='muted'),
            Div(camera_answer_content(answers, zone), data_answer_content=''),
            cls='camera-answers', aria_label='Latest answers for ' + source['name'],
            data_processed_target='processed-image-' + source['source_id'],data_zone=zone,
            data_active=condition_counts(answers)['active'], data_unknown=condition_counts(answers)['unknown'],
            data_answer_url='/ui/camera-answers/' + source['source_id'] + '?' + urlencode({'zone': zone}))

    @app.route('/ui/observe-answers.js', methods=['GET'])
    def observe_answers_script(request):
        return Response(OBSERVE_ANSWERS_JS, media_type='application/javascript')

    @app.route('/ui/camera-answers/{source_id}', methods=['GET'])
    def current_camera_answers(source_id: str, request):
        if source_id not in pipeline.sources:
            return Response(status_code=404)
        zone = request.query_params.get('zone', settings.timezone_name)
        timezone_for(zone)
        records = store.questions(source_id)
        # Cheap change checks avoid replaying the full history on every 0.2-second poll.
        counts_only = request.query_params.get('counts_only') == '1'
        control = store.source_control(source_id)
        revision = [app.state.instance_id, zone, counts_only, control, records]
        image_ids = []
        with store.connection() as db:
            revision.append(tuple(db.execute("SELECT count(*),max(sequence) FROM observations WHERE source_id=? AND status!='retention_gap'", (source_id,)).fetchone()))
            for record in records:
                spec = record['spec']
                last = db.execute('SELECT captured_at_utc,processed_at_utc,answer_json,id,status FROM observations WHERE source_id=? AND question_id=? AND question_version=? AND temporal_eligible=1 ORDER BY sequence DESC LIMIT 1',
                                  (source_id, spec.question_id, spec.version)).fetchone()
                revision.append(tuple(last) if last else None)
                revision.append(bool(last and (utcnow() - utc(last[0] or last[1])).total_seconds() > record['policy'].max_gap_seconds))
                if record['enabled'] and control['enabled']:
                    image_ids.append(last[3] if last and last[4] != 'retention_gap' else None)
        processed = answer_image_reference(store,pipeline,source_id,image_ids)
        revision.append(processed)
        etag = '"' + sha256(json.dumps(revision, default=lambda obj: asdict(obj), sort_keys=True).encode()).hexdigest() + '"'
        if request.headers.get('if-none-match') == etag:
            return Response(status_code=304, headers={'ETag': etag})
        answers = summaries(source_id, zone=zone)
        answer_ids = [d['summary']['last_observation_id'] for d in answers if d['enabled'] and not d['summary'].get('disabled')]
        if answer_ids != image_ids:
            # A capture committed during rendering: bind pixels to the actual answer rows.
            processed = answer_image_reference(store,pipeline,source_id,answer_ids)
            etag = ''  # Do not validate this newer representation with the earlier revision.
        headers = {**({'ETag':etag} if etag else {}), **{'X-VOP-' + key: str(value) for key, value in condition_counts(answers).items()}}
        headers.update({'X-VOP-Processed-' + key: value or '' for key,value in processed.items()})
        content = '' if counts_only else to_xml(camera_answer_content(answers, zone))
        return Response(content, media_type='text/html', headers=headers)

    def capture_controls(source, csrf, operator, configure, answers=(), zone=None):
        sid = source['source_id']
        problems = capture_dependencies(pipeline, sid) if operator else []
        automatic = bool(getattr(pipeline, 'auto_worker', None))
        monitoring = source['enabled'] and source['sample_interval_seconds'] > 0
        other_problems = [p for p in problems if p[1] != f'/ui/sources/{sid}']
        action_problems = other_problems if automatic and not source['enabled'] else problems
        return Div(StrongText(source['name']), Small(" · " + source['kind'] + " · " + source['status']),
                   P('This input is paused. Choose Start monitoring to begin repeated observations.' if operator and automatic else 'This input is disabled. Use Configure mode to enable it.', cls='notice') if not source['enabled'] and not configure else None,
                   Div(StrongText('Monitoring is running'), P('This camera takes repeated observations. Cameras take turns; monitoring stays on between samples. Pause monitoring to stop.'),
                       P('Demo engine selected. Answers are synthetic.') if pipeline.engine.synthetic else None, cls='readiness success', role='status') if operator and monitoring else None,
                   dependency_panel(action_problems, ready="Ready to observe. The connection is checked when needed." if not pipeline.engine.synthetic else "Demo engine selected. Answers are synthetic.") if operator and (action_problems or not monitoring) else P("Capture controls require operator access.") if not operator else None,
                   observe_image(source, monitoring, csrf, answers) if operator and not configure else None,
                   P('Observation scheduled. A fresh image will be captured on this camera’s turn.', cls='notice', role='status') if operator and app.state.sampler.requested(sid) else None,
                   Div(Div(Form(hidden(csrf), Button("Enable and observe" if automatic and not source['enabled'] else "Observe now" if automatic else "Capture once",
                                                disabled=bool(action_problems)),
                            method="post", action=f"/ui/sources/{sid}/enable-observe" if automatic and not source['enabled'] else f"/ui/sources/{sid}/capture") if operator and not monitoring and (configure or source['enabled']) else None,
                       Form(hidden(csrf), Input(type='hidden', name='mode', value='pause' if monitoring else 'start'),
                            Button('Pause monitoring' if monitoring else 'Start monitoring', cls='secondary',
                                   disabled=not monitoring and bool(other_problems)),
                            method='post', action=f'/ui/sources/{sid}/monitor') if operator and automatic else None,
                       action("Run synthetic demo", f"/ui/sources/{sid}/demo", csrf, secondary=True) if configure and source['enabled'] and source['kind'] == 'synthetic' and isinstance(pipeline.engine, MockInferenceEngine) and store.questions(sid, active_only=True) else None,
                       cls="actions"), camera_answers(source, answers, zone or settings.timezone_name), cls="observe-controls"), cls="capture-source")

    @app.route('/ui/sources/{source_id}/monitor', methods=['POST'])
    async def monitor(source_id: str, request):
        if source_id not in pipeline.sources:
            raise ValueError('Unknown source')
        form = await request.form()
        control = store.source_control(source_id)
        if form.get('mode') not in ('start', 'pause'):
            raise ValueError('Choose start or pause')
        with store.connection() as db:
            row = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('monitor_interval:' + source_id,)).fetchone()
            interval = control['sample_interval_seconds'] or (json.loads(row[0]) if row else 10)
            db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('monitor_interval:' + source_id, json.dumps(interval)))
        starting = form['mode'] == 'start'
        if starting and not store.questions(source_id, active_only=True):
            raise ValueError('Add or enable a question before starting monitoring')
        store.update_source(source_id, enabled=True if starting else control['enabled'], retain_evidence=control['retain_evidence'],
                            sample_interval_seconds=interval if starting else 0)
        if not starting:
            pipeline.record_gap(source_id)
            if not pipeline.busy.locked() and not any(c['enabled'] and c['sample_interval_seconds'] for c in store.sources(tuple(pipeline.sources))):
                await run_in_threadpool(app.state.worker_session.stop)
        return RedirectResponse('/?notice=Monitoring+' + ('started' if starting else 'paused'), status_code=303)

    @app.route('/ui/sources/{source_id}/enable-observe', methods=['POST'])
    async def enable_observe(source_id: str, request):
        if source_id not in pipeline.sources:
            raise ValueError('Unknown source')
        control = store.source_control(source_id)
        store.update_source(source_id, enabled=True, retain_evidence=control['retain_evidence'], sample_interval_seconds=0)
        return await capture(source_id, request)

    app.state.render_error = lambda request, message: page("Check the request", request,
        [Div(message, cls="error", role="alert"), A("Cameras", href="/cameras", cls="button secondary"), A("Engines", href="/engines", cls="button secondary"), A("Return to workspace", href="/", cls="button secondary")])

    def table(headers, rows):
        return Div(Table(Thead(Tr(*(Th(metric_label(h)) for h in headers))), Tbody(*rows)), cls="table-wrap")

    app.state.page, app.state.table = page, table

    def source_buttons(chosen, *, path='/', view=None, extra=(), counts=None):
        base = ([('view', view)] if view else []) + list(extra)
        def count(sid=None):
            value = sum(counts.values()) if sid is None else counts.get(sid, 0)
            return Span(str(value), cls='source-count', aria_label=f'{value} episodes')
        links = [A('All cameras', count() if counts is not None else None, href=path + ('?' + urlencode(base) if base else ''),
                   cls='button secondary' if chosen else 'button', role='button', aria_pressed=str(not chosen).lower())]
        for sid in list(pipeline.sources):
            toggled = chosen ^ {sid}
            links.append(A(source_name(sid), count(sid) if counts is not None else None, href=path + '?' + urlencode(base + [('source', s) for s in pipeline.sources if s in toggled]),
                           cls='button' if sid in chosen else 'button secondary', role='button', aria_pressed=str(sid in chosen).lower()))
        return Nav(*links, cls='source-selectors', aria_label='Choose cameras to show')

    def filters(view, selected="", request=None):
        if view in ('overview', 'events'):
            return source_buttons(set(request.query_params.getlist('source')) - {''}, view=view, counts=store.event_counts() if view == 'events' else None)
        if view == 'questions':
            return Nav(*(A(label, href='/?' + urlencode({'view': view, 'source': sid}),
                           cls='button' if sid == selected else 'button secondary',
                           aria_current='page' if sid == selected else None)
                         for sid, label in [('', 'All sources'), *((sid, source_name(sid)) for sid in list(pipeline.sources))]),
                       cls='source-selectors', aria_label='Filter questions by camera')
        if view == 'metrics':
            chosen = set(request.query_params.getlist('source')) - {''}
            dates = [(key, request.query_params[key]) for key in ('from', 'through') if request.query_params.get(key)]
            return Div(source_buttons(chosen, view=view, extra=dates),
                       Form(Input(type='hidden', name='view', value=view),
                            *(Input(type='hidden', name='source', value=sid) for sid in pipeline.sources if sid in chosen),
                            field('From date', 'from', request.query_params.get('from', ''), type='date'),
                            field('Through date', 'through', request.query_params.get('through', ''), type='date'),
                            Button('Apply dates', cls='secondary'), method='get', action='/', cls='filters'))
        selected_zone = request.scope["session"].get("timezone", settings.timezone_name) if request else settings.timezone_name
        return Form(Input(type="hidden", name="view", value=view),
                    Div(Label("Source", _for="source"), Select(Option("All sources", value=""),
                         *(Option(pipeline.sources[s].name + " · " + s, value=s, selected=s == selected) for s in pipeline.sources), name="source", id="source"), cls="field"),
                    Div(Label("Timezone", _for="timezone"), Select(*(Option(zone, value=zone, selected=zone == selected_zone) for zone in dict.fromkeys([settings.timezone_name, "UTC", "Europe/London"])), name="timezone", id="timezone"), cls="field"),
                    field("From date", "from", request.query_params.get("from", "") if request else "", type="date") if view == "metrics" else None,
                    field("Through date", "through", request.query_params.get("through", "") if request else "", type="date") if view == "metrics" else None,
                    Button("Apply filter", cls="secondary"), method="get", action="/", cls="filters")

    @app.route("/ui/style.css", methods=["GET"])
    def style():
        return Response(CSS, media_type="text/css")

    @app.route("/ui/question-editor.js", methods=["GET"])
    def question_editor_script():
        return Response(QUESTION_EDITOR_JS, media_type="application/javascript")

    @app.route('/ui/workspace.js', methods=['GET'])
    def workspace_script():
        return Response(WORKSPACE_JS, media_type='application/javascript')

    @app.route('/ui/trends-refresh.js', methods=['GET'])
    def trends_refresh_script():
        return Response(TRENDS_REFRESH_JS, media_type='application/javascript')

    @app.route("/favicon.ico", methods=["GET"])
    def favicon():
        return Response(status_code=204)

    @app.route("/login", methods=["GET"])
    def login_page(request):
        csrf = request.scope["session"].setdefault("csrf", secrets.token_urlsafe(24))
        return Html(Head(Title(f"Sign in · VOP v{app_version}"), Meta(charset="utf-8"), Meta(name="viewport", content="width=device-width, initial-scale=1"), Link(rel="stylesheet", href="/ui/style.css")),
                    Body(Main(Div(Div("VOP", cls="brand"), Small('v' + app_version, cls='app-version'), cls='title-line'), H2("Open your workspace"),
                              P("Open Start VOP on this computer. It signs you in automatically and reuses your saved cameras and connection."),
                              Details(Summary('Advanced: manual sign-in'), Form(hidden(csrf), Input(type="hidden", name="username", value="local-access", autocomplete="username"), field("Access key", "access_key", type="password", required=True, autocomplete="current-password"),
                                   Button("Open workspace", type="submit"), method="post", action="/login")), cls="login")))

    @app.route("/login", methods=["POST"])
    async def login(request):
        form = await request.form()
        supplied = str(form.get("access_key", "")).encode("utf-8")
        auth = BrowserAuth(None, token=token, store=store, pipeline=pipeline, viewer_token=viewer_token)
        role = auth.credential_role(supplied)
        if not role:
            await run_in_threadpool(store.audit, "browser_login", "denied")
            return Response("Access key was not accepted. Return to /login and try again.", status_code=401)
        request.scope["session"].clear()
        request.scope["session"].update(role=role, csrf=secrets.token_urlsafe(24))
        await run_in_threadpool(store.audit, "browser_login", "accepted")
        return RedirectResponse("/", status_code=303)

    @app.route('/ui/mode', methods=['POST'])
    async def set_mode(request):
        form = await request.form()
        if form.get('mode') not in ('view', 'configure'):
            raise ValueError('Choose View or Configure mode')
        request.scope['session']['mode'] = form['mode']
        return RedirectResponse('/cameras' if form['mode'] == 'configure' else '/', status_code=303)

    @app.route('/configure', methods=['GET'])
    def configure_required(request):
        return page('Configure this workspace', request, [
            P('No changes were saved. Switch to Configure mode, then reopen the form.', cls='notice') if request.query_params.get('stale') else None,
            P('Use Configure mode to manage cameras, engines, questions, monitoring intervals and saved data. Use Observe in View mode to start or pause monitoring.'),
            P('Use the mode switch in the sidebar to open Configure mode.') if request.scope.get('auth_role') == 'operator' else
            P('Configure mode requires operator access. Open Start VOP on this computer to sign in.')])

    @app.route("/logout", methods=["POST"])
    def logout(request):
        request.scope["session"].clear()
        return RedirectResponse("/login", status_code=303)

    @app.route("/", methods=["GET"])
    def overview(request):
        view = request.query_params.get("view", "overview")
        if view == 'overview' and configuring(request) and not request.headers.get('authorization'):
            return RedirectResponse('/cameras', status_code=303)
        if view not in ("overview", "sources", "questions", "events", "metrics", "settings"):
            raise ValueError("Unknown view")
        selected = request.query_params.get("source", "")
        selected_sources = set(request.query_params.getlist("source")) - {""} if view in ("overview", "events", "metrics") else ({selected} if selected else set())
        if selected_sources - pipeline.sources.keys():
            raise ValueError("Unknown source")
        csrf = request.scope["session"].setdefault("csrf", secrets.token_urlsafe(24))
        operator = request.scope.get("auth_role") == "operator"
        configure = configuring(request)
        zone = settings.timezone_name if view in ('questions', 'overview', 'events', 'metrics') else request.query_params.get("timezone", request.scope["session"].get("timezone", settings.timezone_name))
        timezone_for(zone)
        if view not in ('questions', 'overview', 'events', 'metrics'):
            request.scope["session"]["timezone"] = zone
        range_start = datetime.combine(datetime.fromisoformat(request.query_params["from"]).date(), time(), tzinfo=ZoneInfo(zone)) if view not in ("questions", "overview", "events") and request.query_params.get("from") else None
        range_end = datetime.combine(datetime.fromisoformat(request.query_params["through"]).date() + timedelta(days=1), time(), tzinfo=ZoneInfo(zone)) if view not in ("questions", "overview", "events") and request.query_params.get("through") else None
        data = ([] if view in ('questions', 'events') else
                summaries(selected_sources if view == "metrics" else None if view == "overview" else selected, zone=zone, range_start=range_start, range_end=range_end))
        if view == "overview" and selected_sources:
            data = [d for d in data if d["source_id"] in selected_sources]
        sources = [s for s in store.sources(tuple(pipeline.sources)) if not selected_sources or s["source_id"] in selected_sources]
        content = [filters(view, selected, request)]
        if view == "overview":
            counts = condition_counts(data)
            active, unknown = counts['active'], counts['unknown']
            count = sum(store.event_count(sid) for sid in selected_sources) if selected_sources else store.event_count()
            content += [Section(Div(H2("Choose an input"), A("Manage cameras", href="/cameras", cls="text-link") if configure else None, cls="section-heading"),
                                *(capture_controls(s, csrf, operator, configure,
                                    [d for d in data if d['source_id'] == s['source_id']], zone) for s in sources)),
                        Div(*(Div(Small(metric_label(label)), StrongText(number, data_condition_count="active" if label == "Active conditions" else "unknown" if label == "Unknown conditions" else None), cls="stat")
                              for label, number in (("Configured sources", len(sources)), ("Active conditions", active), ("Unknown conditions", unknown), ("Episodes recorded", count))), cls="stats")]
            content.append(P("Sampling: " + "; ".join(f"{s['source_id']} every {duration(s['sample_interval_seconds'])}" if s["enabled"] and s["sample_interval_seconds"] else f"{s['source_id']} stopped" for s in sources),
                             " · ", A("Refresh view", href="/?" + urlencode([("view", view), *(("source", s) for s in pipeline.sources if s in selected_sources)]), cls="button secondary"), cls="muted"))
        elif view == "sources":
            content += [Section(H2("Source health"), table(["Source", "Input", "Health", "Last frame", "Capture prerequisites", "Controls"],
                [Tr(Td(StrongText(s["name"]), Small(s["source_id"])), Td(s["kind"]), Td(badge(s["status"])),
                    Td(local_time(s["last_frame_utc"], zone)),
                    Td(dependency_panel(capture_dependencies(pipeline, s['source_id'])) if operator else "Operator setup required"),
                    Td(Div(A("Edit source", href=f"/ui/sources/{s['source_id']}", cls="button secondary"), A("Remove…", href=f"/ui/sources/{s['source_id']}/remove", cls="button danger"), cls="actions") if operator else "Read only")) for s in sources]))]
        elif view == "questions":
            from vop.removal import removed_controls
            content += [removed_controls(store, pipeline, csrf, view, source_filter=selected or None, editable=operator),
                Section(H2("Add a question"), *(A("New question · " + s["name"], href=f"/ui/questions/{s['source_id']}/new", cls="button secondary") for s in sources)) if operator else None]
        elif view == "events":
            timeline_rows = store.events(source_ids=tuple(sorted(selected_sources)), limit=1000)
            event_rows = timeline_rows[:100]
            names = {}
            keys = sorted({(e['source_id'],e['question_id'],e['question_version']) for e in timeline_rows})
            with store.connection() as db:
                for offset in range(0, len(keys), 300):
                    batch = keys[offset:offset+300]
                    values = ','.join('(?,?,?)' for key in batch)
                    rows = db.execute('SELECT q.source_id,q.question_id,q.version,q.specification FROM question_versions q JOIN (VALUES ' + values + ') wanted ON q.source_id=wanted.column1 AND q.question_id=wanted.column2 AND q.version=wanted.column3',
                                      tuple(value for key in batch for value in key))
                    for row in rows:
                        names[(row['source_id'],row['question_id'],row['version'])] = json.loads(row['specification'])['text']
            camera_names = {sid:source_name(sid) for sid in {e['source_id'] for e in timeline_rows}}
            content += [P('Episodes group individual observations after the required confirmations. ', A('Open Individual Observations to inspect results, saved images or delete recorded data.', href='/observations', cls='text-link')),
                P('Camera buttons count all recorded episodes. The timeline shows up to the latest 1,000 episodes for your selection.', cls='muted'),
                episode_timeline(timeline_rows, camera_names, names, zone),
                Section(H2("Confirmed episodes"), table(["Question / source", "Started", "Ended", "Status", "Estimated duration", "Unobserved gap"],
                [Tr(Td(A(e["question_id"], href="/ui/observations/" + e["start_observation_id"]), Small(source_name(e["source_id"]) + " · version " + e["question_version"])),
                    Td(local_time(e["started_at_utc"], zone)), Td(local_time(e["ended_at_utc"], zone) if e["ended_at_utc"] else "Not confirmed ended"),
                    Td(badge(e["status"])), Td(duration(e["estimated_observed_seconds"])), Td(duration(e["unknown_seconds"]))) for e in event_rows])),
                P("Latest 100 episodes. Durations estimate bounded sampled intervals; missing observations never close an episode.", cls="muted")]
        elif view == "metrics":
            content += [P('Auto refresh: every 00:00:10.0. ', A('Refresh now', href=str(request.url), cls='text-link')),
                        P('Updates recorded results; it does not start monitoring. Refresh pauses while you edit filters. Apply your changes to resume.', cls='muted'),
                        Noscript(P('Automatic refresh requires JavaScript. Use Refresh now to update the page.', cls='notice'))]
            for d in data:
                summary, q = d["summary"], d["spec"]
                occupancy = summary["occupancy_fraction"]
                content.append(Section(H2(q.text), P(f"{source_name(d['source_id'])} · version {q.version} · {answer_kind(q.kind)}"),
                    Div(*(Div(Small(metric_label(label)), StrongText(value), cls="stat") for label, value in (
                        ("Episodes" if q.kind == "binary" else "Valid samples", ("No data" if summary["episode_count"] is None else str(summary["episode_count"])) if q.kind == "binary" else str(summary["valid_sample_count"])),
                        ("Estimated active time" if q.kind == "binary" else "Covered time", duration(summary["estimated_active_seconds"] if q.kind == "binary" else summary["covered_seconds"]) if summary["covered_seconds"] > 0 else "No interval data"),
                        ("Observation coverage", "No interval data" if summary["coverage_fraction"] is None else f"{summary['coverage_fraction']:.1%}"),
                        ("Condition active", "No eligible data" if occupancy is None else f"{occupancy:.1%}"))), cls="stats"),
                    chart(summary["trend"][-60:], q.text),
                    P(metric_label("Episode rate"), ": " + (f"{summary['episodes_per_hour']:.1f} per covered hour" if summary["episodes_per_hour"] is not None else "No eligible interval"),
                      " · ", metric_label("Unobserved time"), f": {duration(summary['unknown_seconds'])}", cls="muted") if q.kind == "binary" else None,
                    P("Rating levels: " + " · ".join(f"{i} {level}" for i, level in enumerate(q.levels)) + ". The score is an expected position and can fall between levels. It is not a physical unit or a selected category.", cls="muted") if q.kind == "ordinal" else None,
                    Small(f"Latest 60 samples, equally spaced by sample order. Failed samples or gaps over {duration(d['policy'].max_gap_seconds)} break the line. Hover over points for timestamps in " + zone)))
        else:
            content += [Section(H2("Processing and access"), P("One inference slot; no queued frames. Live capture and model loading require explicit operator setup."),
                                P("Current browser role: " + ("operator" if operator else "viewer")),
                                action("Rebuild events from stored observations", "/ui/replay", csrf, secondary=True) if operator else None,
                                P("Rebuilding preserves raw observations, immutable question versions and stable event IDs.", cls="muted")),
                        Section(H2('Restart VOP'), P('Finish the current observation, close the worker session and start VOP again. Saved settings and monitoring are restored.'),
                                restart_control(csrf) if app.state.shutdown_request and operator else P('Open Start VOP to enable restart controls.')) if operator else None,
                        Section(H2("Evidence policy"), P("Retention is off by default. Enable it per source; retained frames are privacy-masked and restricted to operators.")),
                        Section(H2('Saved data'), P('Review or delete stored observations and images.'),
                                A('Manage saved data', href='/observations', cls='button secondary')),
                        Section(H2("Setup"), Div(A("Cameras", href="/cameras", cls="button secondary"), A("Engines", href="/engines", cls="button secondary"),
                                                A("Other inputs", href="/?view=sources", cls="button secondary"), A("Settings", href="/release", cls="button secondary"), cls="actions"))]
        if operator and view == "sources":
            from vop.removal import removed_controls
            content.append(removed_controls(store, pipeline, csrf, view, source_filter=selected or None))
        return page({"overview": "Observe", "events": EPISODES_TITLE, "metrics": "Trends", "sources": "Inputs"}.get(view, view.title()), request, [c for c in content if c is not None], view=view, notice=request.query_params.get("notice"))

    @app.route('/ui/episodes.js', methods=['GET'])
    def episodes_script():
        return Response(EPISODES_JS, media_type='application/javascript')

    @app.route('/observations', methods=['GET'])
    def observation_list(request):
        selected_sources = set(request.query_params.getlist('source')) - {''}
        before = int(request.query_params['before']) if request.query_params.get('before') else None
        if before is not None and before < 1: raise ValueError('Invalid observation page')
        with store.connection() as db:
            names = {r['id']: json.loads(r['configuration']).get('name', r['id']) for r in db.execute('SELECT id,configuration FROM sources')}
        if selected_sources - names.keys(): raise ValueError('Unknown input')
        rows = store.observations(newest=True, before=before, limit=100, source_ids=tuple(sorted(selected_sources)))
        operator = request.scope.get('auth_role') == 'operator'
        return page('Individual Observations', request, [
            P('Each row is one answer from a captured image. Open a result to see its saved image, if available. Several answers can share the same image.'),
            P('Image saving is off by default. A temporary capture preview is not a saved image. Images can also be deleted manually or by retention rules.', cls='muted'),
            source_buttons(selected_sources, path='/observations'),
            *(Section(H2(names[sid] or sid), image_settings(sid, operator, configuring(request)),
                      A('Delete input history…', href='/ui/sources/' + sid + '/history/delete', cls='button danger') if configuring(request) else None)
              for sid in sorted(selected_sources)),
            P('Select cameras above to see their image-saving settings.', cls='notice') if not selected_sources else None,
            Div(P('Newest answers first.'),
                P('Use Configure mode to delete recorded data.', cls='muted') if operator and not configuring(request) else None, cls='section-heading'),
            table(['Question / input', 'Result', 'Time', 'Image', 'Actions'], [Tr(
                Td(o['question_id'], Small(names.get(o['source_id']) or o['source_id'])), Td(badge(o['status']), Small(recorded_label(o['source_id'], o['answer']))),
                Td(local_time(o['captured_at_utc'] or o['processed_at_utc'], settings.timezone_name)),
                Td(recorded_image_status(o, operator)),
                Td(Div(A('Open', href='/ui/observations/' + o['id'], cls='button secondary'),
                       A('Delete capture…', href='/ui/observations/' + o['id'] + '/delete', cls='button danger') if configuring(request) else None, cls='actions'))) for o in rows]) if rows else P('No recorded observations.'),
            A('Older answers', href='/observations?' + urlencode([*(('source', sid) for sid in sorted(selected_sources)), ('before', rows[-1]['sequence'])]), cls='button secondary') if len(rows) == 100 else None
        ], view='observations', notice=request.query_params.get('notice'))

    @app.route("/ui/sources/{source_id}", methods=["GET"])
    def source_editor(source_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Operator permission required", status_code=403)
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        if pipeline.sources[source_id].kind in ("rtsp", "usb"):
            return RedirectResponse("/cameras/" + source_id + "#observations", status_code=303)
        control = store.source_control(source_id)
        csrf = request.scope["session"]["csrf"]
        return page("Observation settings", request, [A("Back to camera", href="/cameras/" + source_id, cls="back") if pipeline.sources[source_id].kind in ("rtsp", "usb") else A("Back to inputs", href="/?view=sources", cls="back"), Form(hidden(csrf), H2(pipeline.sources[source_id].name),
            P("Set the sample interval and image-saving setting."),
            Label(Input(type="checkbox", name="enabled", checked=control["enabled"]), " Enabled"),
            Section(H2('Recorded images'),
                    Label(Input(type="checkbox", name="retain_evidence", checked=control["retain_evidence"]), " Save images for Individual Observations"),
                    P('Off by default. When on, VOP saves one privacy-masked still image per capture, shared by its answers. Open an Individual Observation to see its image.'),
                    P('Applies to future captures only. Turning this on cannot recover older unsaved or deleted images. Turning it off keeps images already saved. Retention rules or manual deletion can remove them.', cls='muted'), id='image-saving'),
            field("Sample interval (H:M:S; 00:00:00 stops sampling; maximum 01:00:00)", "sample_interval_seconds", duration(control["sample_interval_seconds"]), required=True, aria_describedby='camera-interval-help'),
            P('Set the target time between observations for this camera and all its enabled questions. For example, 00:00:10.0 targets one observation every 00:00:10.0. Cameras take turns; capture/engine work and connection retries can make the actual interval longer. Set 00:00:00.0 to pause repeated observations.', id='camera-interval-help', cls='muted'),
            P("Saving a nonzero interval explicitly starts background sampling. Image saving is off by default.", cls="muted"), Button("Save settings"),
            method="post", action=f"/ui/sources/{source_id}", cls="editor")], view="sources")

    @app.route("/ui/sources/{source_id}", methods=["POST"])
    async def save_source(source_id: str, request):
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        form = await request.form()
        enabled = form.get("enabled") == "on"
        was_enabled = store.source_control(source_id)["enabled"]
        store.update_source(source_id, enabled=enabled, retain_evidence=form.get("retain_evidence") == "on",
                            sample_interval_seconds=duration_input(form.get("sample_interval_seconds", "0")))
        if was_enabled and not enabled:
            pipeline.record_gap(source_id)
        return RedirectResponse(("/cameras/" + source_id if pipeline.sources[source_id].kind in ("rtsp", "usb") else "/?view=sources") + ("?" if pipeline.sources[source_id].kind in ("rtsp", "usb") else "&") + "notice=Settings+saved", status_code=303)

    @app.route("/ui/questions/{source_id}/{question_id}", methods=["GET"])
    def question_editor(source_id: str, question_id: str, request):
        engine = pipeline.engine
        if request.scope.get("auth_role") != "operator":
            return Response("Operator permission required", status_code=403)
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        record = next((r for r in store.questions(source_id) if r["spec"].question_id == question_id), None)
        if record is None and question_id != "new":
            raise ValueError("Unknown question")
        q = record["spec"] if record else QuestionSpec("new_question", "1", "Is the condition visible?", AnswerKind.BINARY)
        policy = record["policy"] if record else QueryPolicy()
        selected_kind = AnswerKind(request.query_params.get("kind", q.kind.value))
        binary = selected_kind == AnswerKind.BINARY
        mock = str(engine.source_answers.get((source_id, q.question_id, q.version), engine.configured.get(q.question_id, ""))) if isinstance(engine, MockInferenceEngine) else ""
        csrf = request.scope["session"]["csrf"]
        return page("Edit question" if record else "New question", request, [Form(hidden(csrf),
            Input(type="hidden", name="expected_version", value=q.version if record else ""),
            Details(Summary('Advanced: question ID'), field("Question ID (optional for new questions)", "question_id", q.question_id if record else "", maxlength=64, pattern=r"[A-Za-z0-9_.\-]{1,64}",
                  title="1–64 ASCII letters, digits, dots, underscores or hyphens; no spaces", aria_describedby="question-id-help", placeholder="human_present", readonly=bool(record)),
            P("Leave blank for an automatic ID. If set, use 1–64 ASCII letters (A–Z, a–z), digits (0–9), dots (.), underscores (_) or hyphens (-). No spaces. Choose an unused ID for this source; 'new' is reserved for this form. The ID cannot change after saving.", id="question-id-help", cls="muted")),
            field("Question", "text", q.text if record else '', required=True, maxlength=4096, placeholder='Is there a human in the picture?'),
            Div(Label("Answer kind", _for="kind"), Select(*(Option(answer_kind(k.value), value=k.value, selected=k == selected_kind) for k in AnswerKind), name="kind", id="kind"), cls="field"),
            Noscript(P("With JavaScript off, choose a type before entering the question: ", *(A(answer_kind(k.value) + " ", href=request.url.path + "?kind=" + k.value) for k in AnswerKind))),
            Div(Details(Summary('Advanced: detection and episode settings'),
                P('These settings apply to this Yes/No question. They decide when answers start and end an episode.', cls='muted'),
                field("Yes/No threshold (uncalibrated)", "threshold", q.threshold, type="number", min=0, max=1, step="0.01", disabled=not binary, aria_describedby='threshold-help'),
                P('For engines that provide a Yes score, a score at or above this value counts as Yes. A higher threshold requires a stronger Yes score; a lower threshold accepts weaker scores. Treat the score as the engine’s own signal, not a guaranteed percentage chance.', id='threshold-help', cls='muted'),
                Div(field("Positive confirmations", "positive_confirmations", policy.positive_confirmations, type="number", min=1, max=100, disabled=not binary, aria_describedby="positive-help"),
                    field("Negative confirmations", "negative_confirmations", policy.negative_confirmations, type="number", min=1, max=100, disabled=not binary, aria_describedby="negative-help"), cls="pair"),
                P('Positive confirmations: consecutive valid Yes answers needed to start or resume an episode. Higher values reject brief detections but delay confirmation.', id='positive-help', cls='muted'),
                P('Negative confirmations: consecutive valid No answers needed to end an open episode. Higher values tolerate brief No answers but delay the end.', id='negative-help', cls='muted'),
                P('Confirmations count answers, not seconds. Failures and unknown gaps reset the counts. The camera observation interval also affects the delay.', cls='muted'),
                Div(Label("After an unknown gap", _for="unknown_gap_policy"), Select(Option("Resume the episode after reconfirmation", value="resume", selected=policy.unknown_gap_policy == "resume"),
                Option("Split into an interrupted episode and a new episode", value="split", selected=policy.unknown_gap_policy == "split"),
                Option("Require operator review before continuing", value="manual_review", selected=policy.unknown_gap_policy == "manual_review"), id="unknown_gap_policy", name="unknown_gap_policy", disabled=not binary, aria_describedby='gap-policy-help'), cls="field"),
                Div(P('After an unknown gap: choose what happens when observations fail or are too far apart.'),
                    Ul(Li('Resume: keep the episode open and resume after enough Yes answers. The gap is recorded as unobserved time.'),
                       Li('Split: mark the old episode interrupted. Enough new Yes answers start a new episode.'),
                       Li('Operator review: hold the state at Unknown for this question version after a gap. To resume automatic classification, choose Resume or Split and save a new version. This form has no separate approval action.')),
                    id='gap-policy-help', cls='muted'),
                ), data_answer_kind="binary", hidden=not binary),
            Div(Label("Choice options — one name | description per line", _for="choices"), Textarea("\n".join(f"{n}|{d}" for n, d in q.choices), name="choices", id="choices", disabled=selected_kind != AnswerKind.CHOICE),
                P("At least two options, each with a unique nonempty name and a description. Example: cat|A cat is visible", cls="muted"),
                data_answer_kind="choice", hidden=selected_kind != AnswerKind.CHOICE),
            Div(Label("Ordinal levels — one description per line, lowest first", _for="levels"), Textarea("\n".join(q.levels), name="levels", id="levels", disabled=selected_kind != AnswerKind.ORDINAL),
                P("Enter 2–10 nonempty levels in increasing order, for example: Low, Medium, High (on separate lines).", cls="muted"),
                data_answer_kind="ordinal", hidden=selected_kind != AnswerKind.ORDINAL),
            Details(Summary('Advanced: observation settings'),
            P('These settings apply to this question. Set how often images are captured in the camera observation settings: ',
              A('Open camera observation settings', href=f'/ui/sources/{source_id}', cls='text-link'), cls='muted'),
            field("Maximum observation gap (H:M:S; 00:00:01 to 24:00:00)", "max_gap_seconds", duration(policy.max_gap_seconds), required=True, aria_describedby='max-gap-help'),
            P('The longest interval between valid observations that VOP can count as observed time. Longer intervals are Unknown. Allow enough time for the camera interval and normal capture/engine delays. A larger value joins more widely spaced samples; a smaller value records more gaps. This does not set the observation frequency.', id='max-gap-help', cls='muted'),
            field("ROI (optional: x, y, width, height in 0–1)", "roi", ",".join(str(v) for v in policy.roi) if policy.roi else "", aria_describedby='roi-help'),
            P('Region of interest: ask this question about part of the image. Enter left position, top position, width and height as fractions from 0 to 1, measured from the top-left corner. Leave blank for the whole image. Example: 0, 0, 0.5, 1 uses the left half. The rectangle must stay inside the image. Camera privacy masks are applied before this crop.', id='roi-help', cls='muted'),
            Label(Input(type="checkbox", name="enabled", checked=record["enabled"] if record else True, aria_describedby='question-enabled-help'), " Question enabled"),
            P('When off, the camera skips this question. Existing recorded answers remain. Other enabled questions on the camera continue.', id='question-enabled-help', cls='muted')),
            *(Div(field(label, "mock_answer", mock if k == q.kind else "", id="mock-" + k.value, disabled=k != selected_kind, placeholder=example),
                  data_answer_kind=k.value, hidden=k != selected_kind) for k, label, example in (
                    (AnswerKind.BINARY, "Mock answer preset (true or false)", "true"),
                    (AnswerKind.CHOICE, "Mock answer preset (an option name)", "cat"),
                    (AnswerKind.ORDINAL, "Mock answer preset (zero-based level number)", "0"))) if isinstance(engine, MockInferenceEngine) else (),
            P("Each save creates an immutable version." + (" Mock presets are synthetic instructions, not image analysis." if isinstance(engine, MockInferenceEngine) else ""), cls="muted"),
            Button("Save changes" if record else "Add question"), method="post", action=f"/ui/questions/{source_id}/{question_id}", cls="editor", data_question_editor=""),
            Script(src="/ui/question-editor.js", defer=True)], view="questions")

    @app.route("/ui/questions/{source_id}/{question_id}", methods=["POST"])
    async def save_question(source_id: str, question_id: str, request):
        engine = pipeline.engine
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        form = await request.form()
        requested_id = str(form.get('question_id', '')).strip()
        with store.connection() as db:
            used_ids = {r[0] for r in db.execute('SELECT DISTINCT question_id FROM question_versions WHERE source_id=?', (source_id,))}
        if not requested_id and question_id == 'new':
            base = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(form['text']).lower()).strip('_.-')[:56] or 'question'
            if base == 'new': base = 'question_new'
            requested_id, number = base, 1
            while requested_id in used_ids:
                number += 1
                requested_id = base + '_' + str(number)
        qid = identifier(requested_id)
        creating = question_id == "new" and not form.get("expected_version")
        if creating and qid == "new":
            raise ValueError("Question ID 'new' is reserved for the new-question form. Choose another ID.")
        if creating and qid in used_ids:
            raise ValueError("Question ID was already used for this source. Choose an unused ID, or leave it blank for an automatic ID.")
        if not creating and qid != question_id:
            raise ValueError("Question ID cannot change")
        kind = AnswerKind(form["kind"])
        choices = tuple(tuple(line.split("|", 1)) for line in str(form.get("choices", "")).splitlines() if line.strip()) if kind == AnswerKind.CHOICE else ()
        levels = tuple(line.strip() for line in str(form.get("levels", "")).splitlines() if line.strip()) if kind == AnswerKind.ORDINAL else ()
        binary = kind == AnswerKind.BINARY
        q = QuestionSpec(qid, "1", str(form["text"]), kind, choices, levels, float(form.get("threshold", "0.5")) if binary else 0.5)
        if len(q.text) > 4096:
            raise ValueError("Question text exceeds 4096 characters")
        roi_text = str(form.get("roi", "")).strip()
        policy = QueryPolicy(int(form.get("positive_confirmations", "2")) if binary else 2, int(form.get("negative_confirmations", "2")) if binary else 2,
                             duration_input(form["max_gap_seconds"]), str(form.get("unknown_gap_policy", "resume")) if binary else "resume",
                             tuple(float(v) for v in roi_text.split(",")) if roi_text else None)
        mock = str(form.get("mock_answer", "")).strip()
        value = None
        if isinstance(engine, MockInferenceEngine) and mock:
            if kind == AnswerKind.BINARY:
                if mock.lower() not in ("true", "false"):
                    raise ValueError("Binary mock preset must be true or false")
                value = mock.lower() == "true"
            elif kind == AnswerKind.CHOICE:
                if mock not in dict(q.choices):
                    raise ValueError("Mock preset must name a configured choice")
                value = mock
            else:
                value = float(mock)
                if not 0 <= value <= len(q.levels) - 1:
                    raise ValueError("Mock ordinal preset is outside the levels")
        saved = store.edit_question(source_id, q, policy, enabled=form.get("enabled") == "on", expected_version=str(form.get("expected_version", "")) or None)
        if value is not None:
            store.set_mock_value(source_id, saved.question_id, saved.version, value)
            engine.configure_source_answer(source_id, saved.question_id, saved.version, value)
        return RedirectResponse("/?view=questions&notice=Immutable+question+version+saved", status_code=303)

    def schedule_observation(request, source_id):
        app.state.sampler.request(source_id)
        return page('Observation scheduled', request, [
            P('This camera will take a fresh image on its turn. Repeated clicks keep one pending observation for this camera.', cls='readiness info'),
            A('View Individual Observations', href='/observations?source=' + source_id, cls='button secondary'),
            A('Back to Observe', href='/', cls='button secondary')], view='overview')

    @app.route("/ui/sources/{source_id}/capture", methods=["POST"])
    async def capture(source_id: str, request):
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        problems = capture_dependencies(pipeline, source_id)
        if not problems and (request.scope.get('capture_schedule_only') or pipeline.busy.locked() or app.state.sampler.requested(source_id)):
            return schedule_observation(request, source_id)
        if not problems and not getattr(pipeline, 'auto_worker', None):
            from vop.inference.remote import RemoteInferenceEngine
            if isinstance(pipeline.engine, RemoteInferenceEngine):
                try:
                    health = await run_in_threadpool(pipeline.engine.health)
                    if not health.get('ready') or health.get('busy'):
                        problems.append(("Worker is not ready or is busy. Wait and test worker health again.", "/engines"))
                except ProviderError as exc:
                    pipeline.engine.last_health = {"ready": False, "error": exc.code}
                    problems.append(("Worker check failed (" + exc.code + "). Check its session, tunnel and protected key, then test worker health.", "/engines"))
                if not problems:
                    pipeline.engine.allow_remote = True
        if problems:
            return page("Cannot observe", request, [dependency_panel(problems), P("No camera image was acquired and no inference was requested."),
                        action('Enable camera and observe', f'/ui/sources/{source_id}/enable-observe', request.scope['session']['csrf']) if configuring(request) and not store.source_control(source_id)['enabled'] else None,
                        A("Back to Observe", href="/", cls="button secondary")], view="overview")
        try:
            result = await run_in_threadpool(pipeline.run, source_id)
        except ProviderError as exc:
            if exc.code == 'overloaded':
                return schedule_observation(request, source_id)
            from vop.operator_workflow import recovery_message
            return page("Could not observe yet", request, [P(recovery_message(exc.code), cls='readiness warning'),
                        action('Retry automatically', f'/ui/sources/{source_id}/capture', request.scope['session']['csrf']),
                        A('Open Engines', href='/engines', cls='button secondary'),
                        Details(Summary('Technical details'), Pre(exc.code))], view='overview')
        summary = result["result"]
        questions = {r["spec"].question_id: r["spec"].text for r in store.questions(source_id)}
        answers = []
        for answer in summary["answers"]:
            value = answer["value"]
            label = "Unknown — no valid answer"
            if answer["status"] == "success":
                if type(value) is bool:
                    human_question = questions.get(answer["question_id"]) == "Is there a human in the picture?"
                    label = ("Human present" if value else "No human detected") if human_question else ("Yes" if value else "No")
                else:
                    label = recorded_label(source_id, answer)
            answers.append(Section(H2(questions.get(answer["question_id"], answer["question_id"])), P(label, cls="readiness success" if answer['status'] == 'success' else "readiness error")))
        error = summary.get("error") or {}
        camera_error = error.get('code', '').startswith(('capture_', 'snapshot_', 'endpoint_', 'live_')) or error.get('code') == 'secret_unavailable'
        guidance = {"remote_consent_required": "Select an engine on Engines. Then run the observation again.",
                    "worker_unavailable": "The engine is not connected. Open Engines and check its connection.",
                    "worker_auth": "The worker access key was rejected. Check its protected setup.",
                    "capture_timeout": "The camera did not respond in time. Check its connection and address."}.get(error.get("code"))
        if error and not guidance:
            from vop.operator_workflow import recovery_message
            guidance = recovery_message(error.get('code'))
        timing = (f"Inference time: {duration(summary['elapsed_ms'] / 1000)}"
                  if summary['elapsed_ms'] is not None else "Inference was not run. No image was available.")
        content = [P(source_name(source_id)), P("Observation complete" if summary["status"] == "success" else "No valid answer", role="status", cls="readiness success" if summary['status'] == 'success' else "readiness error"),
                   *answers, P(guidance, role="alert") if guidance else None,
                   A("Open camera" if camera_error else "Open Engines", href=("/cameras/" + source_id if pipeline.sources[source_id].kind in ("rtsp", "usb") else "/ui/sources/" + source_id) if camera_error else "/engines", cls="button secondary") if error else None,
                   P(timing + f" · Engine: {summary['engine_id']}"),
                   Details(Summary("Technical details"), Pre(json.dumps(summary, indent=2))),
                   action("Observe again" if getattr(pipeline, 'auto_worker', None) else "Capture again", f"/ui/sources/{source_id}/capture", request.scope["session"]["csrf"]),
                   A("Back to Observe", href="/", cls="button secondary")]
        if pipeline.previews.get(source_id) and pipeline.previews[source_id][0] == summary["frame_id"]:
            content.insert(1, evidence_image(f"/ui/preview/{source_id}/{summary['frame_id']}", "Privacy-masked source frame; inspect recorded engine provenance",
                                             tuple(r["policy"].roi for r in store.questions(source_id))))
        with store.connection() as db:
            recorded = db.execute('SELECT id FROM observations WHERE run_id=? ORDER BY sequence LIMIT 1', (result['run_id'],)).fetchone()
        if recorded:
            saved = store.observation(recorded[0])
            if summary['frame_id']:
                content.append(P('An image was saved with this capture.' if saved['image_saved'] else
                                 'Temporary preview only. No image was saved with this capture.', cls='notice'))
                content.append(image_settings(source_id, True, configuring(request)))
            content.append(A('Open Individual Observation', href='/ui/observations/' + recorded[0], cls='button secondary'))
            if configuring(request):
                content.append(A('Delete capture…', href='/ui/observations/' + recorded[0] + '/delete', cls='button danger'))
        return page("Observation", request, content, view="overview")

    @app.route("/ui/sources/{source_id}/demo", methods=["POST"])
    async def demo(source_id: str, request):
        engine = pipeline.engine
        if source_id not in pipeline.sources or pipeline.sources[source_id].kind != "synthetic" or not isinstance(engine, MockInferenceEngine):
            raise ValueError("Demo is available only for synthetic mock sources")
        source = pipeline.source(source_id)
        if source.sample_interval_seconds > 0 or pipeline.busy.locked():
            raise ValueError("Stop background sampling before running the scripted demo")
        q = next((q for q in source.questions if q.kind == AnswerKind.BINARY), None)
        if q is None:
            raise ValueError("Enable a Yes/No question for the episode demo")
        key = (source_id, q.question_id, q.version)
        original = engine.source_answers.get(key)
        existed = key in engine.source_answers
        # Synthetic captures use their acquisition instants so repeated demos remain ordered.
        try:
            for index, value in enumerate((False, True, True, True, False, False)):
                engine.configure_source_answer(*key, value)
                frame = capture_inline(source)
                await run_in_threadpool(pipeline.run, source_id, frame)
        finally:
            if existed:
                engine.source_answers[key] = original
            else:
                engine.source_answers.pop(key, None)
        return RedirectResponse("/?view=events&notice=Synthetic+replay+demo+recorded", status_code=303)

    @app.route("/ui/replay", methods=["POST"])
    async def replay_history(request):
        if pipeline.busy.locked():
            raise ValueError("Stop active inference before rebuilding events")
        await run_in_threadpool(store.replay_all)
        return RedirectResponse("/?view=events&notice=Stored+observations+replayed", status_code=303)

    @app.route('/ui/observe-images.js', methods=['GET'])
    def observe_images_script():
        return Response(OBSERVE_IMAGES_JS, media_type='application/javascript')

    @app.route('/ui/live-preview/{source_id}/keepalive', methods=['POST'])
    async def preview_keepalive(source_id: str, request):
        if request.scope.get('auth_role') != 'operator':
            return Response('Images require operator permission', status_code=403)
        await run_in_threadpool(pipeline.live_previews.request, source_id)
        return Response(status_code=202)

    @app.route('/ui/live-preview/{source_id}', methods=['GET', 'HEAD'])
    def live_preview(source_id: str, request):
        if request.scope.get('auth_role') != 'operator':
            return Response('Images require operator permission', status_code=403)
        if source_id not in pipeline.sources:
            return Response('Camera not available', status_code=404)
        control = store.source_control(source_id)
        headers = {'X-VOP-Monitoring': str(bool(control['enabled'] and control['sample_interval_seconds'] > 0)).lower(),
                   'X-VOP-Preview-State': pipeline.live_previews.state(source_id),
                   'X-VOP-Preview-Error': pipeline.live_previews.error(source_id)}
        image = latest_image(source_id)
        if not image:
            return Response(status_code=204 if request.method == 'HEAD' else 404, headers=headers)
        frame_id, payload, captured_at, kind, content_type = image
        headers.update({'X-VOP-Frame-Id': frame_id, 'X-VOP-Captured-At': captured_at, 'X-VOP-Preview-Kind': kind})
        headers['Content-Length'] = str(len(payload))
        return Response(b'' if request.method == 'HEAD' else payload, media_type=content_type, headers=headers)

    @app.route('/ui/processed-image/{source_id}/{frame_id}', methods=['GET','HEAD'])
    def processed_image(source_id: str, frame_id: str, request):
        if request.scope.get('auth_role') != 'operator':
            return Response('Images require operator permission',status_code=403)
        if source_id not in pipeline.sources:
            return Response(status_code=404)
        cached = pipeline.processed_previews.get(source_id)
        payload = cached[1] if cached and cached[0] == frame_id else store.evidence(source_id,frame_id)
        if payload is None:
            return Response(status_code=404)
        return Response(b'' if request.method == 'HEAD' else payload,media_type='image/png',headers={'Content-Length':str(len(payload))})

    @app.route("/ui/preview/{source_id}/{frame_id}", methods=["GET"])
    def preview(source_id: str, frame_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Evidence requires operator permission", status_code=403)
        image = pipeline.previews.get(source_id)
        if not image or image[0] != frame_id:
            return Response("Preview is no longer in memory", status_code=404)
        return Response(image[1], media_type="image/png")

    @app.route("/ui/evidence/{source_id}/{frame_id}", methods=["GET"])
    def evidence(source_id: str, frame_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Evidence requires operator permission", status_code=403)
        payload = store.evidence(source_id, frame_id)
        return Response(payload, media_type="image/png") if payload else Response("No retained evidence", status_code=404)

    @app.route("/ui/evidence/{source_id}/{frame_id}/delete", methods=["POST"])
    def delete_evidence(source_id: str, frame_id: str, request):
        store.delete_evidence(source_id, frame_id)
        pipeline.clear_preview(source_id, frame_id)
        return RedirectResponse("/?notice=Evidence+deleted", status_code=303)

    @app.route("/ui/observations/{observation_id}", methods=["GET"])
    def inspection(observation_id: str, request):
        observation = store.observation(observation_id)
        if observation is None:
            return Response("Observation not found", status_code=404)
        content = [A('‹ Individual Observations', href='/observations?source=' + observation['source_id'], cls='back'),
                   P(source_name(observation["source_id"]) + " / " + observation["question_id"] + " · version " + observation["question_version"]),
                   P(recorded_label(observation["source_id"], observation["answer"])),
                   P("Captured: " + local_time(observation["captured_at_utc"], settings.timezone_name))]
        frame_id = observation["run"]["frame_id"]
        operator = request.scope.get('auth_role') == 'operator'
        if operator and frame_id and observation['image_saved']:
            url = f"/ui/evidence/{observation['source_id']}/{frame_id}"
            content.append(Section(H2('Recorded image'),
                evidence_image(url, "Retained privacy-masked evidence", (store.policy(observation["source_id"], observation["question_id"], observation["question_version"]).roi,)),
                P('This is the saved still image for this capture. It is shared by all answers from the same capture.', cls='muted'),
                action("Delete saved image", url + "/delete", request.scope["session"]["csrf"], secondary=True) if configuring(request) else None, id='recorded-image'))
        else:
            message = ('Recorded images require operator access. Sign in as an operator to view any saved image.' if not operator else
                       'No image was captured for this observation.' if not frame_id else
                       'No saved image is available. Image saving may have been off when this capture was taken, or its image may have been deleted manually or by a retention rule.')
            content.append(Section(H2('Recorded image'), P(message, cls='notice'), id='recorded-image'))
        content.append(image_settings(observation['source_id'], operator, configuring(request)))
        content.append(Details(Summary('Technical details'), Pre(json.dumps(observation['run'], indent=2))))
        if configuring(request):
            content.append(Section(H2('Delete this capture'), P('Review the answers and shared image that will be deleted.'),
                                   A('Delete capture…', href='/ui/observations/' + observation_id + '/delete', cls='button danger')))
        return page("Individual Observation", request, content, view="observations")


def StrongText(value, **attrs):
    from fasthtml.components import Strong
    return Strong(str(value), **attrs)
