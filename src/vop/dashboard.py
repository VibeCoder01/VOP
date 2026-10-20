"""Server-rendered browser workspace; native forms and SVG, no CDN or frontend build."""
from datetime import datetime, time, timedelta
from importlib.metadata import version
import json
import math
import secrets
import re
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fasthtml.components import (A, Aside, Body, Button, Details, Div, Form, H1, H2, Head,
                                Header, Html, Img, Input, Label, Link, Main, Meta, Nav, Option, P, Pre,
                                Section, Select, Small, Span, Summary, Table, Tbody, Td, Textarea, Th,
                                Thead, Title, Tr, Ul, Li, Script, Noscript)
from fasthtml.svg import Svg, Polyline, Line, Rect, Circle, Text, ft_svg
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from vop.browser_auth import BrowserAuth, configuring
from vop.config import identifier
from vop.contracts import AnswerKind, ProviderError, QuestionSpec, utcnow
from vop.inference.mock import MockInferenceEngine
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy, utc, timezone_for
from vop.ui_readiness import capture_dependencies

CSS = """
:root{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#1d1d1f;background:#f5f5f7;font-size:15px;--accent:#0066cc;--line:#dcdce0;--muted:#626268}
*{box-sizing:border-box}body{margin:0}a{color:inherit;text-decoration:none}button,input,select,textarea{font:inherit}
.shell{display:grid;grid-template-columns:216px minmax(0,1fr);min-height:100vh}.sidebar{padding:32px 18px;background:#ececf0;position:sticky;top:0;height:100vh;border-right:1px solid var(--line);display:flex;flex-direction:column;overflow:auto}
.brand{font-size:28px;letter-spacing:-1.6px;font-weight:700;padding:0 12px;color:#1d1d1f}.sidebar .app-version{display:inline;margin:0 0 0 8px;font-size:12px;line-height:1}.subtitle{font-size:11px;color:var(--muted);padding:7px 12px;letter-spacing:.4px}
.mode-label{padding:12px;font-weight:600;color:#0055b3}.navigation{display:grid;gap:4px;margin:34px 0 auto}.navigation a{padding:11px 14px;border-radius:9px;font-weight:500;transition:background 150ms,color 150ms}.navigation a:hover{background:#e0e0e5}.navigation a.current{background:#dbeaff;color:#0055b3}.sidebar small{font-size:11px;line-height:1.7;margin:28px 12px 12px;color:var(--muted)}.sidebar small p{font-size:11px;margin:0}.sidebar form{margin:0 10px}
.sidebar .restart-control{margin:0 10px 10px}.workspace{padding:44px 5vw 72px;min-width:0;max-width:1450px;width:100%;animation:appear 180ms ease-out}.top{display:flex;justify-content:space-between;align-items:start;gap:24px;margin-bottom:36px}.top p{margin:10px 0 0;max-width:600px}.title-line{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap}.app-version{font-size:12px;font-weight:400;color:var(--muted);letter-spacing:0;white-space:nowrap}
h1{font-size:34px;letter-spacing:-1.2px;line-height:1.15;margin:0;font-weight:650}h2{font-size:21px;letter-spacing:-.5px;margin:0 0 16px;line-height:1.3;font-weight:600}h3{font-size:16px;margin:22px 0 10px}p{line-height:1.6;margin:8px 0;color:var(--muted)}small,.muted{color:var(--muted);font-size:12px}section{margin:28px 0 36px}section[id]{scroll-margin-top:24px}
.actions{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.button,button{display:inline-flex;align-items:center;justify-content:center;min-height:40px;padding:10px 18px;border:1px solid transparent;border-radius:9px;background:var(--accent);color:white;font-size:13px;font-weight:600;cursor:pointer;transition:background 150ms,box-shadow 150ms,transform 150ms;line-height:1.3}.button:hover,button:hover{background:#0055b3}.button:active,button:active{transform:scale(.98)}.button.secondary,button.secondary{background:white;color:#0055b3;border-color:#d3d3d9}.button.secondary:hover,button.secondary:hover{background:#f0f5ff;border-color:#a8bfdf}.button.danger,button.danger{background:white;color:#a1252c;border-color:#e4c4c7}.button.danger:hover,button.danger:hover{background:#fff0f1}button:disabled,button:disabled:hover{background:#e8e8ed;color:#6a6a70;border-color:#d8d8df;cursor:not-allowed;transform:none}button[aria-busy=true]{background:#455d78;cursor:progress}.text-link{color:#0055b3;font-size:13px;font-weight:600}.text-link:hover{text-decoration:underline}.back{display:inline-block;color:#0055b3;margin-bottom:24px;font-size:13px}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #72aaff;outline-offset:3px}
form.inline{display:inline-flex;gap:8px;align-items:center}.filters{display:flex;gap:14px;align-items:end;flex-wrap:wrap;margin:0 0 28px}.filters .field{flex:1 1 180px;min-width:0;max-width:320px}.field{display:grid;gap:8px;margin:0 0 22px}label{font-size:13px;font-weight:600;color:#37373d}input,select,textarea{width:100%;max-width:100%;padding:12px 14px;border:1px solid #c8c8cf;border-radius:9px;background:#fff;color:#1d1d1f;min-height:44px}input[type=checkbox]{width:auto;min-height:0;accent-color:var(--accent)}textarea{min-height:100px;resize:vertical}.editor{max-width:680px}.editor .actions{margin-top:30px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.surface{background:white;border:1px solid #e0e0e5;border-radius:16px;padding:28px 30px}.object-list{margin-top:24px}.object-row{padding:26px 0;border-bottom:1px solid var(--line);display:flex;align-items:center;justify-content:space-between;gap:24px}.object-row:first-child{padding-top:0}.object-row h2{margin:0 0 5px}.object-row p{margin:4px 0}.object-meta{font-size:13px}.object-copy{min-width:0;overflow-wrap:anywhere}.object-row .actions{flex-shrink:0}.empty{padding:48px 0;max-width:560px}.empty p{margin:12px 0 24px}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:20px}.section-heading h2{margin:0}.capture-source{padding:24px 0;border-bottom:1px solid var(--line)}.capture-source .actions{margin-top:16px}.capture-source>small{display:block;margin:5px 0}.divider{border:0;border-top:1px solid var(--line);margin:24px 0}
table{border-collapse:collapse;width:100%;text-align:left}th{font-size:11px;color:var(--muted);font-weight:600;padding:12px 14px;border-bottom:1px solid var(--line);white-space:nowrap}td{padding:18px 14px;border-bottom:1px solid #e8e8ed;vertical-align:top;font-size:13px}td strong{font-weight:600}td small{display:block;line-height:1.6;margin-top:5px}tr:hover td{background:#eeeef3}.table-wrap{overflow:auto}
.stats{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:24px;margin:0 0 36px;padding:22px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.stat strong{display:block;font-size:32px;font-weight:600;letter-spacing:-1px;margin-top:10px}.stat small{font-size:12px}.status,.tag{display:inline-block;padding:5px 9px;border-radius:6px;background:#e8e8ed;color:#4f4f58;font-size:11px;font-weight:600;line-height:1.4;white-space:nowrap}.tag{color:#0055b3;background:#e5efff}.status.ACTIVE,.status.HEALTHY,.status.success,.status.closed,.status.OBSERVED,.status.delivered,.status.resolved{background:#e0f1e9;color:#206146}.status.UNKNOWN,.status.PENDING,.status.RECOVERING,.status.interrupted,.status.CONNECTING,.status.warning,.status.open{background:#fff0d7;color:#7e520c}.status.DISCONNECTED,.status.model_failure,.status.capture_failure,.status.timeout,.status.error,.status.critical,.status.failed{background:#fbe6e6;color:#a1252c}.status.info,.status.acknowledged{background:#e5efff;color:#205a94}
.readiness,.notice,.error{padding:14px 18px;border-radius:10px;margin:16px 0;font-size:13px;line-height:1.6;background:#eef1f5;color:#414854}.readiness p{color:inherit}.readiness ul{margin:5px 0;padding-left:18px}.readiness li{margin:4px 0}.readiness a{text-decoration:underline;text-underline-offset:3px}.readiness.success{background:#e5f2ec;color:#246147}.readiness.warning{background:#fff2df;color:#7a510e}.readiness.error,.error{background:#fbe9e9;color:#9a282f}.readiness.info,.notice{background:#e8f0fc;color:#285483}.readiness.success{padding:0;background:transparent}.readiness.success:before{content:'●';color:#26835b;margin-right:8px}
details{margin:22px 0;border-top:1px solid var(--line);padding-top:12px}summary{cursor:pointer;font-size:13px;font-weight:600;color:#45454c;padding:10px 0}details[open]>summary{margin-bottom:12px}pre{font:12px/1.6 Consolas,monospace;overflow:auto;background:#ececf1;padding:18px;border-radius:9px;white-space:pre-wrap;word-break:break-word}.preview{max-width:100%;max-height:480px;object-fit:contain;border-radius:12px;background:#e8e8ed}.evidence-box{display:inline-block;position:relative;max-width:100%}.evidence-box .preview{display:block}.roi-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.roi-overlay rect{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}.login{max-width:440px;margin:12vh auto;padding:32px}.login .brand{padding:0}
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
    "Configured sources": "Number of saved image inputs in this view, including demo inputs. This does not mean that each input is connected or monitoring.",
    "Active conditions": "Number of questions currently in the ACTIVE state after the required positive confirmations. This counts questions, not people or cameras. Conditions awaiting end confirmation are shown as RECOVERING instead.",
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
    "OBSERVED": "A valid choice or ordinal answer was received. Binary episode confirmation states do not apply to this answer type.",
    "DISABLED": "This input is disabled. Enable it before requesting new observations.",
    "CONNECTING": "The input is enabled, but a successful frame has not yet confirmed its connection.",
    "HEALTHY": "The latest recorded capture succeeded. This is not a live guarantee that the camera is still connected.",
    "DISCONNECTED": "The latest capture failed. Check the camera connection and saved setup, then retry.",
    "Daily episode counts / choice dwell": "Daily episode counts show how many confirmed episodes started on each date in the selected time zone. Choice dwell estimates the seconds spent in each named answer, using the previous answer between valid samples. Gaps are excluded.",
    "Occupancy": "Estimated active time divided by covered time, shown as a percentage. Applies to binary questions only. Unobserved gaps are excluded; this does not prove continuous presence.",
    "Coverage": "Covered time divided by covered time plus unobserved time in the measured range, shown as a percentage. No interval data means there is not enough timing evidence to calculate it.",
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
        return "Expected level: " + (levels[low] if low == high else f"Between {levels[low]} and {levels[high]}") + f" ({value})"
    return ("Yes" if value else "No") if type(value) is bool else str(value)


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
            dots.append(ft_svg('circle', Title(f"{stamp} · value {value}"), cx=x, cy=y, r=2.5))
    if current:
        segments.append(current)
    return Div(Svg(*gaps, *(Line(x1=18, y1=y, x2=658, y2=y) for y in (20, 72, 125)),
               Text(f"{maximum:g}", x=2, y=20), Text("0", x=2, y=125),
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
                      ("questions", "Questions", "/?view=questions"), ("observations", "Individual Observations", "/observations"), ("events", "Continuous Observations (Episodes)", "/?view=events"),
                      ("metrics", "Trends", "/?view=metrics"), ("settings", "Settings", "/?view=settings")]
        descriptions = {"overview": "Run an observation. Read the result.", "cameras": "Set up image inputs.",
                        "engines": "Set up and select the engine that answers questions.", "questions": "Choose what to ask about each image.",
                        "events": "Review episodes built from individual checks. These are sampled estimates, not continuous video.", "observations": "Review individual checks and their saved images, when available.", "metrics": "Review change over time.", "settings": "Manage this workspace."}
        return Html(Head(Title(f"{title} · VOP v{app_version}"), Meta(charset="utf-8"), Meta(name="viewport", content="width=device-width, initial-scale=1"), Link(rel="stylesheet", href="/ui/style.css")),
                    Body(Div(Aside(A("VOP", Small('v' + app_version, cls='app-version', aria_label='VOP version ' + app_version), href="/", cls="brand"), Div("Visual Observability", cls="subtitle"),
                                   Nav(*(A(label, href=url, cls="current" if key == view else "", aria_current="page" if key == view else None) for key, label, url in navigation
                                         if configure or key in ("overview", "observations", "events", "metrics")), cls="navigation", aria_label="Main"),
                                   P('Configure mode' if configure else 'View mode', cls='mode-label', role='status'),
                                   Form(hidden(csrf), Input(type='hidden', name='mode', value='view' if configure else 'configure'),
                                        Button('Switch to View' if configure else 'Configure workspace', cls='secondary'), method='post', action='/ui/mode') if role == 'operator' else None,
                                   Small("Local observation workspace", P("Viewer access" if role == "viewer" else "Operator access")),
                                   restart_control(csrf) if configure and app.state.shutdown_request else None,
                                   action("Sign out", "/logout", csrf, secondary=True), cls="sidebar"),
                             Main(Header(Div(H1(title), P(descriptions.get(view, ""))),
                                         A("Demo engine" if pipeline.engine.synthetic else pipeline.engine.engine_id, href="/engines", cls="tag") if view == "overview" and configure else None, cls="top"),
                                  Div(notice, cls="notice", role="status") if notice else None, *content, cls="workspace", id="workspace"), cls="shell"),
                         Script(src='/ui/workspace.js', defer=True) if getattr(pipeline, 'auto_worker', None) else None,
                         Script(src='/ui/restart.js', defer=True) if configure and app.state.shutdown_request else None,
                         Script(src='/ui/trends-refresh.js', defer=True) if view == 'metrics' else None))

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
                   A('Change image-saving setting', href='/ui/sources/' + source_id + '#image-saving', cls='button secondary') if operator and configure and source_id in pipeline.sources else
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
        for source_id in list(pipeline.sources):
            if source_filter and source_filter != source_id:
                continue
            for record in store.questions(source_id):
                q = record["spec"]
                summary = store.summary(source_id, q.question_id, q.version, kind=q.kind, as_of=utcnow(), timezone_name=zone or settings.timezone_name,
                                        range_start=range_start, range_end=range_end)
                if not record["enabled"] or not store.source_control(source_id)["enabled"]:
                    summary.update(state="UNKNOWN", latest_value=None, disabled=True)
                result.append({"source_id": source_id, **record, "summary": summary})
        return result

    def capture_controls(source, csrf, operator, configure):
        sid = source['source_id']
        problems = capture_dependencies(pipeline, sid) if operator else []
        automatic = bool(getattr(pipeline, 'auto_worker', None))
        monitoring = source['enabled'] and source['sample_interval_seconds'] > 0
        other_problems = [p for p in problems if p[1] != f'/ui/sources/{sid}']
        return Div(StrongText(source['name']), Small(" · " + source['kind'] + " · " + source['status']),
                   P('This input is disabled. Use Configure mode to enable it.', cls='notice') if not source['enabled'] and not configure else None,
                   dependency_panel(other_problems if automatic and not source['enabled'] else problems, ready="Ready to observe. The connection is checked when needed." if not pipeline.engine.synthetic else "Demo engine selected. Answers are synthetic.") if operator else P("Capture controls require operator access."),
                   Div(Form(hidden(csrf), Button("Enable and observe" if automatic and not source['enabled'] else "Observe now" if automatic else "Capture once",
                                                disabled=bool(other_problems if automatic and not source['enabled'] else problems)),
                            method="post", action=f"/ui/sources/{sid}/enable-observe" if automatic and not source['enabled'] else f"/ui/sources/{sid}/capture") if operator and (configure or source['enabled']) else None,
                       Form(hidden(csrf), Input(type='hidden', name='mode', value='pause' if monitoring else 'start'),
                            Button('Pause monitoring' if monitoring else 'Start monitoring', cls='secondary',
                                   disabled=not monitoring and bool(other_problems)),
                            method='post', action=f'/ui/sources/{sid}/monitor') if configure and automatic else None,
                       action("Run synthetic demo", f"/ui/sources/{sid}/demo", csrf, secondary=True) if configure and source['enabled'] and source['kind'] == 'synthetic' and isinstance(pipeline.engine, MockInferenceEngine) and store.questions(sid, active_only=True) else None,
                       cls="actions"), cls="capture-source")

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

    def filters(view, selected="", request=None):
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
            P('Use Configure mode to manage cameras, engines, questions, monitoring and saved data. View mode keeps your current monitoring running.'),
            Form(hidden(request.scope['session'].setdefault('csrf', secrets.token_urlsafe(24))), Input(type='hidden', name='mode', value='configure'),
                 Button('Switch to Configure mode'), method='post', action='/ui/mode') if request.scope.get('auth_role') == 'operator' else
            P('Configure mode requires operator access. Open Start VOP on this computer to sign in.')])

    @app.route("/logout", methods=["POST"])
    def logout(request):
        request.scope["session"].clear()
        return RedirectResponse("/login", status_code=303)

    @app.route("/", methods=["GET"])
    def overview(request):
        view = request.query_params.get("view", "overview")
        if view not in ("overview", "sources", "questions", "events", "metrics", "settings"):
            raise ValueError("Unknown view")
        selected = request.query_params.get("source", "")
        if selected and selected not in pipeline.sources:
            raise ValueError("Unknown source")
        csrf = request.scope["session"].setdefault("csrf", secrets.token_urlsafe(24))
        operator = request.scope.get("auth_role") == "operator"
        configure = configuring(request)
        zone = request.query_params.get("timezone", request.scope["session"].get("timezone", settings.timezone_name))
        timezone_for(zone)
        request.scope["session"]["timezone"] = zone
        range_start = datetime.combine(datetime.fromisoformat(request.query_params["from"]).date(), time(), tzinfo=ZoneInfo(zone)) if request.query_params.get("from") else None
        range_end = datetime.combine(datetime.fromisoformat(request.query_params["through"]).date() + timedelta(days=1), time(), tzinfo=ZoneInfo(zone)) if request.query_params.get("through") else None
        data = summaries(selected, zone=zone, range_start=range_start, range_end=range_end)
        sources = [s for s in store.sources(tuple(pipeline.sources)) if not selected or s["source_id"] == selected]
        content = [filters(view, selected, request)]
        if view == "overview":
            active = sum(d["summary"]["state"] == "ACTIVE" for d in data)
            unknown = sum(d["summary"]["state"] == "UNKNOWN" for d in data)
            count = store.event_count(selected or None)
            content += [Section(Div(H2("Choose an input"), A("Manage cameras", href="/cameras", cls="text-link") if configure else None, cls="section-heading"),
                                *(capture_controls(s, csrf, operator, configure) for s in sources)),
                        Div(*(Div(Small(metric_label(label)), StrongText(number), cls="stat")
                              for label, number in (("Configured sources", len(sources)), ("Active conditions", active), ("Unknown conditions", unknown), ("Episodes recorded", count))), cls="stats"),
                        Section(H2("Latest answers"), table(["Question", "Source", "State", "Last answer", "Observed"],
                        [Tr(Td(StrongText(d["spec"].text), Small("Version " + d["spec"].version)), Td(pipeline.sources[d["source_id"]].name, Small(d["source_id"])),
                            Td(badge(d["summary"]["state"])), Td(answer_label(d["summary"]["latest_value"], d["spec"].levels)),
                            Td(local_time(d["summary"]["last_observed_at_utc"], zone))) for d in data]))]
            content.append(P("Sampling: " + "; ".join(f"{s['source_id']} every {s['sample_interval_seconds']:g}s" if s["enabled"] and s["sample_interval_seconds"] else f"{s['source_id']} stopped" for s in sources),
                             " · ", A("Refresh view", href="/?" + urlencode({"view": view, "source": selected, "timezone": zone}), cls="button secondary"), cls="muted"))
        elif view == "sources":
            content += [Section(H2("Source health"), table(["Source", "Input", "Health", "Last frame", "Capture prerequisites", "Controls"],
                [Tr(Td(StrongText(s["name"]), Small(s["source_id"])), Td(s["kind"]), Td(badge(s["status"])),
                    Td(local_time(s["last_frame_utc"], zone)),
                    Td(dependency_panel(capture_dependencies(pipeline, s['source_id'])) if operator else "Operator setup required"),
                    Td(Div(A("Edit source", href=f"/ui/sources/{s['source_id']}", cls="button secondary"), A("Remove…", href=f"/ui/sources/{s['source_id']}/remove", cls="button danger"), cls="actions") if operator else "Read only")) for s in sources]))]
        elif view == "questions":
            content += [Section(H2("Questions"), table(["Question", "Kind", "Version", "Enabled", "Policy", "Edit"],
                [Tr(Td(StrongText(d["spec"].text), Small(d["source_id"] + " / " + d["spec"].question_id)), Td(d["spec"].kind), Td(d["spec"].version),
                    Td("Yes" if d["enabled"] else "No"), Td(f"{d['policy'].positive_confirmations} positive / {d['policy'].negative_confirmations} negative", Small(f"Gap: {d['policy'].max_gap_seconds:g}s · {d['policy'].unknown_gap_policy}")),
                    Td(Div(A("Edit", href=f"/ui/questions/{d['source_id']}/{d['spec'].question_id}", cls="button secondary"), A("Remove…", href=f"/ui/questions/{d['source_id']}/{d['spec'].question_id}/remove", cls="button danger"), cls="actions") if operator else "Read only")) for d in data])),
                Section(H2("Add a question"), *(A("New question · " + s["name"], href=f"/ui/questions/{s['source_id']}/new", cls="button secondary") for s in sources)) if operator else None]
        elif view == "events":
            event_rows = store.events(selected or None)
            content += [P('Episodes group individual observations after the required confirmations. ', A('Open Individual Observations to inspect results, saved images or delete recorded data.', href='/observations', cls='text-link')),
                Section(H2("Confirmed episodes"), table(["Question / source", "Started", "Ended", "Status", "Estimated duration", "Unobserved gap"],
                [Tr(Td(A(e["question_id"], href="/ui/observations/" + e["start_observation_id"]), Small(source_name(e["source_id"]) + " · version " + e["question_version"])),
                    Td(local_time(e["started_at_utc"], zone)), Td(local_time(e["ended_at_utc"], zone) if e["ended_at_utc"] else "Not confirmed ended"),
                    Td(badge(e["status"])), Td(f"{e['estimated_observed_seconds']:.1f} s"), Td(f"{e['unknown_seconds']:.1f} s")) for e in event_rows])),
                P("Latest 100 episodes. Durations estimate bounded sampled intervals; missing observations never close an episode.", cls="muted")]
        elif view == "metrics":
            content += [P('Auto refresh: every 10 seconds. ', A('Refresh now', href=str(request.url), cls='text-link')),
                        P('Updates recorded results; it does not start monitoring. Refresh pauses while you edit filters. Apply your changes to resume.', cls='muted'),
                        Noscript(P('Automatic refresh requires JavaScript. Use Refresh now to update the page.', cls='notice'))]
            for d in data:
                summary, q = d["summary"], d["spec"]
                occupancy = summary["occupancy_fraction"]
                content.append(Section(H2(q.text), P(f"{source_name(d['source_id'])} · version {q.version} · {q.kind}"),
                    Div(*(Div(Small(metric_label(label)), StrongText(value), cls="stat") for label, value in (
                        ("Episodes" if q.kind == "binary" else "Valid samples", ("No data" if summary["episode_count"] is None else str(summary["episode_count"])) if q.kind == "binary" else str(summary["valid_sample_count"])),
                        ("Estimated active time" if q.kind == "binary" else "Covered time", f"{summary['estimated_active_seconds'] if q.kind == 'binary' else summary['covered_seconds']:.3f}s" if summary["covered_seconds"] > 0 else "No interval data"),
                        ("Coverage", "No interval data" if summary["coverage_fraction"] is None else f"{summary['coverage_fraction']:.0%}"),
                        ("Occupancy", "No eligible data" if occupancy is None else f"{occupancy:.0%}"))), cls="stats"),
                    chart(summary["trend"][-60:], q.text),
                    P(metric_label("Episode rate"), ": " + (f"{summary['episodes_per_hour']:.3f} per covered hour" if summary["episodes_per_hour"] is not None else "No eligible interval"),
                      " · ", metric_label("Unobserved time"), f": {summary['unknown_seconds']:.1f}s", cls="muted") if q.kind == "binary" else None,
                    P("Rating levels: " + " · ".join(f"{i} {level}" for i, level in enumerate(q.levels)) + ". The score is an expected position and can fall between levels. It is not a physical unit or a selected category.", cls="muted") if q.kind == "ordinal" else None,
                    Details(Summary(metric_label("Daily episode counts / choice dwell")), Pre(json.dumps({"daily_counts": summary["daily_episode_counts"], "choice_dwell_seconds": summary["choice_dwell_seconds"]}, indent=2))),
                    Small(f"Latest 60 samples, equally spaced by sample order. Failed samples or gaps over {d['policy'].max_gap_seconds:g}s break the line. Hover over points for timestamps in " + zone)))
        else:
            content += [Section(H2("Processing and access"), P("One inference slot; no queued frames. Live capture and model loading require explicit operator setup."),
                                P("Current browser role: " + ("operator" if operator else "viewer")),
                                action("Rebuild events from stored observations", "/ui/replay", csrf, secondary=True) if operator else None,
                                P("Rebuilding preserves raw observations, immutable question versions and stable event IDs.", cls="muted")),
                        Section(H2('Restart VOP'), P('Finish the current observation, close the worker session and start VOP again. Saved settings and monitoring are restored.'),
                                restart_control(csrf) if app.state.shutdown_request and operator else P('Open Start VOP to enable restart controls.')) if operator else None,
                        Section(H2("Evidence policy"), P("Retention is off by default. Enable it per source; retained frames are privacy-masked and restricted to operators.")),
                        Section(H2("Setup"), Div(A("Cameras", href="/cameras", cls="button secondary"), A("Engines", href="/engines", cls="button secondary"),
                                                A("Other inputs", href="/?view=sources", cls="button secondary"), A("Alerts and release tools", href="/release", cls="button secondary"), cls="actions"))]
        if view in ("overview", "sources"):
            observations = store.observations(selected or None, limit=20)
            content.append(Section(Div(H2("Recent Individual Observations"), A('All Individual Observations', href='/observations', cls='text-link'), cls='section-heading'), table(["Question", "Result", "Captured", "Image", "Provenance"],
                [Tr(Td(o["question_id"], Small(source_name(o["source_id"]) + " · version " + o["question_version"])), Td(badge(o["status"]), Small(recorded_label(o["source_id"], o["answer"]))),
                    Td(local_time(o["captured_at_utc"], zone)), Td(recorded_image_status(o, operator)),
                    Td(A("Inspect native result", href="/ui/observations/" + o["id"]))) for o in reversed(observations)])))
        if operator and view in ("sources", "questions"):
            from vop.removal import removed_controls
            content.append(removed_controls(store, pipeline, csrf, view))
        return page({"overview": "Observe", "events": "Continuous Observations (Episodes)", "metrics": "Trends", "sources": "Inputs"}.get(view, view.title()), request, [c for c in content if c is not None], view=view, notice=request.query_params.get("notice"))

    @app.route('/observations', methods=['GET'])
    def observation_list(request):
        selected = request.query_params.get('source') or None
        before = int(request.query_params['before']) if request.query_params.get('before') else None
        if before is not None and before < 1: raise ValueError('Invalid observation page')
        with store.connection() as db:
            names = {r['id']: json.loads(r['configuration']).get('name', r['id']) for r in db.execute('SELECT id,configuration FROM sources')}
        if selected and selected not in names: raise ValueError('Unknown input')
        rows = store.observations(selected, newest=True, before=before, limit=100)
        operator = request.scope.get('auth_role') == 'operator'
        return page('Individual Observations', request, [
            P('Each row is one answer from a captured image. Open a result to see its saved image, if available. Several answers can share the same image.'),
            P('Image saving is off by default. A temporary capture preview is not a saved image. Images can also be deleted manually or by retention rules.', cls='muted'),
            Form(Div(Label('Input', _for='history-source'), Select(Option('All inputs', value=''), *(Option(name, value=sid, selected=sid == selected) for sid, name in names.items()), name='source', id='history-source'), cls='field'),
                 Button('Show', cls='secondary'), method='get', action='/observations', cls='filters'),
            image_settings(selected, operator, configuring(request)) if selected else P('Select an input above to see whether image saving is on or off. Use Configure mode to change it.' if operator else 'Select an input above to see its image-saving setting.', cls='notice'),
            Div(P('Newest answers first.'),
                A('Delete input history…', href='/ui/sources/' + selected + '/history/delete', cls='button danger') if selected and configuring(request) else P('Use Configure mode to delete recorded data.', cls='muted') if operator else None, cls='section-heading'),
            table(['Question / input', 'Result', 'Time', 'Image', 'Actions'], [Tr(
                Td(o['question_id'], Small(names.get(o['source_id']) or o['source_id'])), Td(badge(o['status']), Small(recorded_label(o['source_id'], o['answer']))),
                Td(local_time(o['captured_at_utc'] or o['processed_at_utc'], settings.timezone_name)),
                Td(recorded_image_status(o, operator)),
                Td(Div(A('Open', href='/ui/observations/' + o['id'], cls='button secondary'),
                       A('Delete capture…', href='/ui/observations/' + o['id'] + '/delete', cls='button danger') if configuring(request) else None, cls='actions'))) for o in rows]) if rows else P('No recorded observations.'),
            A('Older answers', href='/observations?' + urlencode({'source': selected or '', 'before': rows[-1]['sequence']}), cls='button secondary') if len(rows) == 100 else None
        ], view='observations', notice=request.query_params.get('notice'))

    @app.route("/ui/sources/{source_id}", methods=["GET"])
    def source_editor(source_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Operator permission required", status_code=403)
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        control = store.source_control(source_id)
        csrf = request.scope["session"]["csrf"]
        return page("Observation settings", request, [A("Back to camera", href="/cameras/" + source_id, cls="back") if pipeline.sources[source_id].kind in ("rtsp", "usb") else A("Back to inputs", href="/?view=sources", cls="back"), Form(hidden(csrf), H2(pipeline.sources[source_id].name),
            P("Set the sample interval and image-saving setting."),
            Label(Input(type="checkbox", name="enabled", checked=control["enabled"]), " Enabled"),
            Section(H2('Recorded images'),
                    Label(Input(type="checkbox", name="retain_evidence", checked=control["retain_evidence"]), " Save images for Individual Observations"),
                    P('Off by default. When on, VOP saves one privacy-masked still image per capture, shared by its answers. Open an Individual Observation to see its image.'),
                    P('Applies to future captures only. Turning this on cannot recover older unsaved or deleted images. Turning it off keeps images already saved. Retention rules or manual deletion can remove them.', cls='muted'), id='image-saving'),
            field("Sample interval in seconds (0 stops sampling)", "sample_interval_seconds", control["sample_interval_seconds"], type="number", min=0, max=3600, step=1),
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
                            sample_interval_seconds=float(form.get("sample_interval_seconds", "0")))
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
            Div(Label("Answer kind", _for="kind"), Select(*(Option(k.value, value=k.value, selected=k == selected_kind) for k in AnswerKind), name="kind", id="kind"), cls="field"),
            Noscript(P("With JavaScript off, choose a type before entering the question: ", *(A(k.value + " ", href=request.url.path + "?kind=" + k.value) for k in AnswerKind))),
            Div(Details(Summary('Advanced: detection and episode settings'), field("Binary threshold (uncalibrated)", "threshold", q.threshold, type="number", min=0, max=1, step="0.01", disabled=not binary),
                Div(field("Positive confirmations", "positive_confirmations", policy.positive_confirmations, type="number", min=1, max=100, disabled=not binary),
                    field("Negative confirmations", "negative_confirmations", policy.negative_confirmations, type="number", min=1, max=100, disabled=not binary), cls="pair"),
                Div(Label("After an unknown gap", _for="unknown_gap_policy"), Select(Option("Resume the episode after reconfirmation", value="resume", selected=policy.unknown_gap_policy == "resume"),
                Option("Split into an interrupted episode and a new episode", value="split", selected=policy.unknown_gap_policy == "split"),
                Option("Require operator review before continuing", value="manual_review", selected=policy.unknown_gap_policy == "manual_review"), id="unknown_gap_policy", name="unknown_gap_policy", disabled=not binary), cls="field"),
                ), data_answer_kind="binary", hidden=not binary),
            Div(Label("Choice options — one name | description per line", _for="choices"), Textarea("\n".join(f"{n}|{d}" for n, d in q.choices), name="choices", id="choices", disabled=selected_kind != AnswerKind.CHOICE),
                P("At least two options, each with a unique nonempty name and a description. Example: cat|A cat is visible", cls="muted"),
                data_answer_kind="choice", hidden=selected_kind != AnswerKind.CHOICE),
            Div(Label("Ordinal levels — one description per line, lowest first", _for="levels"), Textarea("\n".join(q.levels), name="levels", id="levels", disabled=selected_kind != AnswerKind.ORDINAL),
                P("Enter 2–10 nonempty levels in increasing order, for example: Low, Medium, High (on separate lines).", cls="muted"),
                data_answer_kind="ordinal", hidden=selected_kind != AnswerKind.ORDINAL),
            Details(Summary('Advanced: observation settings'), field("Maximum observation gap (seconds)", "max_gap_seconds", policy.max_gap_seconds, type="number", min=1, max=86400),
            field("ROI (optional: x, y, width, height in 0–1)", "roi", ",".join(str(v) for v in policy.roi) if policy.roi else ""),
            Label(Input(type="checkbox", name="enabled", checked=record["enabled"] if record else True), " Question enabled")),
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
        if not requested_id and question_id == 'new':
            base = re.sub(r'[^A-Za-z0-9_.-]+', '_', str(form['text']).lower()).strip('_.-')[:56] or 'question'
            if base == 'new': base = 'question_new'
            requested_id, number = base, 1
            ids = {r['spec'].question_id for r in store.questions(source_id, include_removed=True)}
            while requested_id in ids:
                number += 1
                requested_id = base + '_' + str(number)
        qid = identifier(requested_id)
        creating = question_id == "new" and not form.get("expected_version")
        if creating and qid == "new":
            raise ValueError("Question ID 'new' is reserved for the new-question form. Choose another ID.")
        if creating and any(r['spec'].question_id == qid for r in store.questions(source_id, include_removed=True)):
            raise ValueError("Question ID already exists for this source. Choose an unused ID, or edit/restore the existing question.")
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
                             float(form["max_gap_seconds"]), str(form.get("unknown_gap_policy", "resume")) if binary else "resume",
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

    @app.route("/ui/sources/{source_id}/capture", methods=["POST"])
    async def capture(source_id: str, request):
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        problems = capture_dependencies(pipeline, source_id)
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
        timing = (f"Inference time: {summary['elapsed_ms'] / 1000:.3f} seconds"
                  if summary['elapsed_ms'] is not None else "Inference was not run. No image was available.")
        content = [P(source_name(source_id)), P("Observation complete" if summary["status"] == "success" else "No valid answer", role="status", cls="readiness success" if summary['status'] == 'success' else "readiness error"),
                   *answers, P(guidance, role="alert") if guidance else None,
                   A("Open camera" if camera_error else "Open Engines", href=("/cameras/" + source_id if pipeline.sources[source_id].kind in ("rtsp", "usb") else "/ui/sources/" + source_id) if camera_error else "/engines", cls="button secondary") if error else None,
                   P(timing + f" · Engine: {summary['engine_id']}"),
                   Details(Summary("Technical details"), Pre(json.dumps(summary, indent=2))),
                   action("Observe again" if getattr(pipeline, 'auto_worker', None) else "Capture again", f"/ui/sources/{source_id}/capture", request.scope["session"]["csrf"]),
                   A("Back to Observe", href="/", cls="button secondary")]
        if pipeline.latest_preview and pipeline.latest_preview[:2] == (source_id, summary["frame_id"]):
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
            raise ValueError("Enable a binary question for the episode demo")
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

    @app.route("/ui/preview/{source_id}/{frame_id}", methods=["GET"])
    def preview(source_id: str, frame_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Evidence requires operator permission", status_code=403)
        if not pipeline.latest_preview or pipeline.latest_preview[:2] != (source_id, frame_id):
            return Response("Preview is no longer in memory", status_code=404)
        return Response(pipeline.latest_preview[2], media_type="image/png")

    @app.route("/ui/evidence/{source_id}/{frame_id}", methods=["GET"])
    def evidence(source_id: str, frame_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Evidence requires operator permission", status_code=403)
        payload = store.evidence(source_id, frame_id)
        return Response(payload, media_type="image/png") if payload else Response("No retained evidence", status_code=404)

    @app.route("/ui/evidence/{source_id}/{frame_id}/delete", methods=["POST"])
    def delete_evidence(source_id: str, frame_id: str, request):
        store.delete_evidence(source_id, frame_id)
        if pipeline.latest_preview and pipeline.latest_preview[:2] == (source_id, frame_id):
            pipeline.latest_preview = None
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


def StrongText(value):
    from fasthtml.components import Strong
    return Strong(str(value))
