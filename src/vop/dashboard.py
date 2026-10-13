"""Server-rendered browser workspace; native forms and SVG, no CDN or frontend build."""
from datetime import datetime, time, timedelta
import json
import secrets
from urllib.parse import urlencode
from zoneinfo import ZoneInfo

from fasthtml.components import (A, Aside, Body, Button, Details, Div, Form, H1, H2, Head,
                                Header, Html, Img, Input, Label, Link, Main, Meta, Nav, Option, P, Pre,
                                Section, Select, Small, Span, Summary, Table, Tbody, Td, Textarea, Th,
                                Thead, Title, Tr)
from fasthtml.svg import Svg, Polyline, Line, Rect, Circle, Text
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from vop.browser_auth import BrowserAuth
from vop.config import identifier
from vop.contracts import AnswerKind, QuestionSpec, utcnow
from vop.inference.mock import MockInferenceEngine
from vop.inputs.sources import capture_inline
from vop.measurements import QueryPolicy, utc, timezone_for

CSS = """
:root{font-family:Segoe UI,Arial,sans-serif;color:#24313e;background:#f4f6f8;font-size:15px;--accent:#157b78;--line:#dce2e7}
*{box-sizing:border-box}body{margin:0}a{color:inherit;text-decoration:none}button,input,select,textarea{font:inherit}
.shell{display:grid;grid-template-columns:218px minmax(0,1fr);min-height:100vh}.sidebar{padding:36px 24px;background:#172330;color:#bbc6d0;position:sticky;top:0;height:100vh}
.brand{font-size:32px;letter-spacing:-2px;font-weight:700;color:white}.subtitle{font-size:11px;letter-spacing:1.4px;text-transform:uppercase;margin-top:6px;line-height:1.7}
.navigation{display:grid;gap:5px;margin:38px -8px 0}.navigation a{padding:12px 14px;border-radius:5px;transition:background 120ms,color 120ms}
.navigation a:hover,.navigation a.current{background:#2a3947;color:#fff}.sidebar small{display:block;margin-top:34px;line-height:1.65}.sidebar small,.sidebar p{color:#aab9c8}.sidebar button.secondary{color:#d6e0e9;border-color:#8f9eaa}
.workspace{min-width:0}.sidebar a.button.secondary{display:inline-block;margin-top:12px;color:#d6e0e9;border-color:#8f9eaa}.filters .field{min-width:0;max-width:100%;flex:1 1 180px}
.workspace{padding:38px 46px 64px;max-width:1550px;width:100%;animation:appear 160ms ease-out}.top{display:flex;align-items:start;justify-content:space-between;gap:20px;margin-bottom:32px}
h1{font-size:30px;line-height:1.15;letter-spacing:-.9px;margin:0 0 10px}h2{font-size:18px;letter-spacing:-.3px;margin:0 0 18px}h3{font-size:15px;margin:22px 0 10px}
p{line-height:1.6;margin:8px 0;color:#667383}small,.muted{color:#637182;font-size:12px}section{margin:28px 0 38px}.divider{border:0;border-top:1px solid var(--line);margin:24px 0}
.status{font-size:11px;letter-spacing:.7px;font-weight:600;white-space:nowrap}.status.ACTIVE,.status.HEALTHY{color:var(--accent)}.status.UNKNOWN,.status.DISCONNECTED,.status.interrupted{color:#966025}
.status.PENDING,.status.RECOVERING{color:#657588}.tag{font-size:11px;letter-spacing:.6px;border:1px solid #cfdbdd;border-radius:3px;padding:5px 7px;color:#46676b;display:inline-block}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:24px;border-top:1px solid var(--line);border-bottom:1px solid var(--line);padding:22px 0 26px;margin:8px 0 36px}
.stat strong{font-size:34px;font-weight:500;letter-spacing:-1px;display:block;margin-top:8px}.stat small{font-size:12px}
table{border-collapse:collapse;width:100%;background:transparent;text-align:left}th{font-size:11px;letter-spacing:1.2px;text-transform:uppercase;color:#5c6b7b;font-weight:600;padding:11px 12px;border-bottom:1px solid var(--line)}
td{padding:17px 12px;border-bottom:1px solid #e3e8ec;vertical-align:top;font-size:13px}td strong{font-weight:600}td small{display:block;line-height:1.7;margin-top:3px}tr:hover td{background:#edf2f4}
.table-wrap{overflow:auto}.actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.button,button{background:var(--accent);border:1px solid var(--accent);color:white;padding:9px 14px;border-radius:4px;cursor:pointer;font-size:12px;font-weight:600;transition:background 130ms,transform 130ms}
.button:hover,button:hover{background:#116663}.button.secondary,button.secondary{color:#435362;background:transparent;border-color:#cbd5dc}.button.secondary:hover{background:#e9eff2}button:active,.button:active{transform:translateY(1px)}
a:focus-visible,button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible{outline:3px solid #64aaa7;outline-offset:3px}
form.inline{display:inline-flex;gap:8px;align-items:center}.filters{display:flex;gap:12px;align-items:end;flex-wrap:wrap;margin:0 0 24px}.field{display:grid;gap:7px;margin:0 0 18px}label{font-size:12px;font-weight:600;color:#40515f}
input,select,textarea{border:1px solid #cdd6dd;background:white;border-radius:4px;padding:10px 12px;color:#253340;max-width:100%;width:100%}textarea{min-height:86px;resize:vertical}input[type=checkbox]{width:auto}
.editor{max-width:760px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:20px}.notice{background:#e4f0ef;border-left:3px solid var(--accent);padding:12px 16px;font-size:13px;margin:18px 0}.error{background:#f4eae3;border-left:3px solid #a26c3b;padding:12px 16px}
pre{font:12px/1.6 Consolas,monospace;overflow:auto;background:#eaf0f3;padding:18px;white-space:pre-wrap;word-break:break-word}details{margin:14px 0}summary{cursor:pointer;font-size:13px;color:#526675;padding:9px 0}
.preview{max-width:100%;max-height:420px;background:#e3e8ec;border:1px solid var(--line);object-fit:contain}.evidence-box{display:inline-block;position:relative;max-width:100%}.evidence-box .preview{display:block}.roi-overlay{position:absolute;inset:0;width:100%;height:100%;pointer-events:none}.roi-overlay rect{fill:none;stroke:var(--accent);stroke-width:2;vector-effect:non-scaling-stroke}.login{max-width:440px;margin:12vh auto;padding:32px}.login h1{font-size:46px}.login .brand{color:#20313f}
.chart{width:100%;height:150px;display:block;max-width:700px}.chart line{stroke:#dfe6eb;stroke-width:1}.chart polyline{stroke:var(--accent);stroke-width:2;fill:none}.chart circle{fill:var(--accent)}.chart text{font-size:10px;fill:#637182}.section-heading{display:flex;align-items:center;justify-content:space-between;gap:20px;margin-bottom:16px}.section-heading h2{margin:0}
@keyframes appear{from{opacity:.6;transform:translateY(4px)}to{opacity:1;transform:none}}@media(prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media(max-width:800px){.shell{grid-template-columns:1fr}.sidebar{height:auto;position:static;padding:20px}.navigation{display:flex;flex-wrap:wrap;margin:16px 0 0}.sidebar small{display:none}.subtitle{display:none}.workspace{padding:28px 20px}.stats{grid-template-columns:1fr 1fr;gap:20px}.pair{grid-template-columns:1fr}.top{flex-direction:column}}
"""


def badge(value):
    return Span(str(value), cls=f"status {value}")


def local_time(value, zone):
    return utc(value).astimezone(ZoneInfo(zone)).strftime("%d %b %H:%M:%S %Z %z") if value else "No observation"


def hidden(csrf):
    return Input(type="hidden", name="csrf", value=csrf)


def action(label, path, csrf, *, secondary=False):
    return Form(hidden(csrf), Button(label, type="submit", cls="secondary" if secondary else ""), method="post", action=path, cls="inline")


def field(label, name, value="", *, type="text", required=False, **kwargs):
    control_id = kwargs.pop("id", name)
    return Div(Label(label, _for=control_id), Input(id=control_id, name=name, value=value, type=type, required=required, **kwargs), cls="field")


def chart(points, label):
    numeric = [p["value"] for p in points if isinstance(p["value"], (int, float))]
    if not numeric:
        return P("No numeric observations in this view.", cls="muted")
    maximum = max(1, max(numeric))
    segments, current = [], []
    for i, point in enumerate(points):
        value = point["value"]
        if point.get("gap_before") and current:
            segments.append(current)
            current = []
        if not isinstance(value, (int, float)):
            if current:
                segments.append(current)
            current = []
        else:
            current.append((18 + i * 640 / max(1, len(points) - 1), 125 - float(value) * 105 / maximum))
    if current:
        segments.append(current)
    return Svg(*(Line(x1=18, y1=y, x2=658, y2=y) for y in (20, 72, 125)),
               Text(f"{maximum:g}", x=2, y=20), Text("0", x=2, y=125),
               *(Polyline(points=" ".join(f"{x:.2f},{y:.2f}" for x, y in segment)) for segment in segments),
               *(Circle(cx=x, cy=y, r=2.5) for segment in segments for x, y in segment),
               viewBox="0 0 680 150", role="img", aria_label=label + "; gaps are not connected", cls="chart")


def evidence_image(url, label, rois=()):
    return Div(Img(src=url, alt=label, cls="preview"),
               Svg(*(Rect(x=roi[0], y=roi[1], width=roi[2], height=roi[3]) for roi in rois if roi),
                   viewBox="0 0 1 1", preserveAspectRatio="none", cls="roi-overlay", role="img", aria_label="Configured query regions") if any(rois) else None,
               cls="evidence-box")


def install_dashboard(app, settings, store, pipeline, engine, token, viewer_token=None):
    def page(title, request, content, *, view="overview", notice=None):
        session = request.scope["session"]
        csrf = session.setdefault("csrf", secrets.token_urlsafe(24))
        role = request.scope.get("auth_role") or session.get("role")
        navigation = [("overview", "Overview"), ("sources", "Sources"), ("questions", "Questions"), ("events", "Events"), ("metrics", "Metrics"), ("settings", "Settings")]
        return Html(Head(Title(f"{title} · VOP"), Meta(charset="utf-8"), Meta(name="viewport", content="width=device-width, initial-scale=1"), Link(rel="stylesheet", href="/ui/style.css")),
                    Body(Div(Aside(A("VOP", href="/", cls="brand"), Div("Visual Observability", cls="subtitle"),
                                   Nav(*(A(label, href="/?" + urlencode({"view": key}), cls="current" if key == view else "") for key, label in navigation), cls="navigation"),
                                   A("Alerts and release tools", href="/release", cls="button secondary"),
                                   Small("Local observation workspace", P("Viewer access" if role == "viewer" else "Operator access")),
                                   action("Sign out", "/logout", csrf, secondary=True), cls="sidebar"),
                             Main(Header(Div(H1(title), P("Review sampled conditions and their evidence.")),
                                         Span("MOCK · NO VISION" if engine.synthetic else engine.engine_id, cls="tag"), cls="top"),
                                  Div(notice, cls="notice", role="status") if notice else None, *content, cls="workspace", id="workspace"), cls="shell")))

    def summaries(source_filter=None, *, zone=None, range_start=None, range_end=None):
        result = []
        for source_id in pipeline.sources:
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

    app.state.render_error = lambda request, message: page("Check the request", request,
        [Div(message, cls="error", role="alert"), A("Return to workspace", href="/", cls="button secondary")])

    def table(headers, rows):
        return Div(Table(Thead(Tr(*(Th(h) for h in headers))), Tbody(*rows)), cls="table-wrap")

    app.state.page, app.state.table = page, table

    def filters(view, selected="", request=None):
        selected_zone = request.scope["session"].get("timezone", settings.timezone_name) if request else settings.timezone_name
        return Form(Input(type="hidden", name="view", value=view),
                    Div(Label("Source", _for="source"), Select(Option("All sources", value=""),
                         *(Option(s, value=s, selected=s == selected) for s in pipeline.sources), name="source", id="source"), cls="field"),
                    Div(Label("Timezone", _for="timezone"), Select(*(Option(zone, value=zone, selected=zone == selected_zone) for zone in dict.fromkeys([settings.timezone_name, "UTC", "Europe/London"])), name="timezone", id="timezone"), cls="field"),
                    field("From date", "from", request.query_params.get("from", "") if request else "", type="date") if view == "metrics" else None,
                    field("Through date", "through", request.query_params.get("through", "") if request else "", type="date") if view == "metrics" else None,
                    Button("Apply filter", cls="secondary"), method="get", action="/", cls="filters")

    @app.route("/ui/style.css", methods=["GET"])
    def style():
        return Response(CSS, media_type="text/css")

    @app.route("/favicon.ico", methods=["GET"])
    def favicon():
        return Response(status_code=204)

    @app.route("/login", methods=["GET"])
    def login_page(request):
        csrf = request.scope["session"].setdefault("csrf", secrets.token_urlsafe(24))
        return Html(Head(Title("Sign in · VOP"), Meta(charset="utf-8"), Meta(name="viewport", content="width=device-width, initial-scale=1"), Link(rel="stylesheet", href="/ui/style.css")),
                    Body(Main(Div("VOP", cls="brand"), P("Local observation workspace"), H2("Sign in"),
                              Form(hidden(csrf), Input(type="hidden", name="username", value="local-access", autocomplete="username"), field("Access key", "access_key", type="password", required=True, autocomplete="current-password"),
                                   Button("Open workspace", type="submit"), method="post", action="/login"),
                              P("Use the operator or viewer key set when the service started.", cls="muted"), cls="login")))

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
            content += [Div(*(Div(Small(label), StrongText(number), cls="stat")
                              for label, number in (("Configured sources", len(sources)), ("Active conditions", active), ("Unknown conditions", unknown), ("Episodes recorded", count))), cls="stats"),
                        Section(H2("Latest conditions"), table(["Question", "Source", "State", "Last answer", "Observed"],
                        [Tr(Td(StrongText(d["spec"].text), Small("Version " + d["spec"].version)), Td(d["source_id"]),
                            Td(badge(d["summary"]["state"])), Td(str(d["summary"]["latest_value"]) if d["summary"]["latest_value"] is not None else "Unknown"),
                            Td(local_time(d["summary"]["last_observed_at_utc"], zone))) for d in data])),
                        Section(Div(H2("Capture controls"), cls="section-heading"),
                                *(Div(StrongText(s["name"]), Small(" · " + s["kind"] + " · " + s["status"]),
                                      action("Capture once", f"/ui/sources/{s['source_id']}/capture", csrf) if operator and s["enabled"] else None,
                                      action("Run synthetic demo", f"/ui/sources/{s['source_id']}/demo", csrf, secondary=True) if operator and s["kind"] == "synthetic" and engine.synthetic else None,
                                      cls="actions") for s in sources))]
            content.append(P("Sampling: " + "; ".join(f"{s['source_id']} every {s['sample_interval_seconds']:g}s" if s["enabled"] and s["sample_interval_seconds"] else f"{s['source_id']} stopped" for s in sources),
                             " · ", A("Refresh view", href="/?" + urlencode({"view": view, "source": selected, "timezone": zone}), cls="button secondary"), cls="muted"))
        elif view == "sources":
            content += [Section(H2("Source health"), table(["Source", "Input", "Health", "Last frame", "Controls"],
                [Tr(Td(StrongText(s["name"]), Small(s["source_id"])), Td(s["kind"]), Td(badge(s["status"])),
                    Td(local_time(s["last_frame_utc"], zone)),
                    Td(A("Edit source", href=f"/ui/sources/{s['source_id']}", cls="button secondary") if operator else "Read only")) for s in sources]))]
        elif view == "questions":
            content += [Section(H2("Question versions"), table(["Question", "Kind", "Version", "Enabled", "Policy", "Edit"],
                [Tr(Td(StrongText(d["spec"].text), Small(d["source_id"] + " / " + d["spec"].question_id)), Td(d["spec"].kind), Td(d["spec"].version),
                    Td("Yes" if d["enabled"] else "No"), Td(f"{d['policy'].positive_confirmations} positive / {d['policy'].negative_confirmations} negative", Small(f"Gap: {d['policy'].max_gap_seconds:g}s · {d['policy'].unknown_gap_policy}")),
                    Td(A("Edit", href=f"/ui/questions/{d['source_id']}/{d['spec'].question_id}", cls="button secondary") if operator else "Read only")) for d in data])),
                Section(H2("Add a question"), *(A("New question · " + s["name"], href=f"/ui/questions/{s['source_id']}/new", cls="button secondary") for s in sources)) if operator else None]
        elif view == "events":
            event_rows = store.events(selected or None)
            content += [Section(H2("Confirmed episodes"), table(["Question / source", "Started", "Ended", "Status", "Estimated duration", "Unobserved gap"],
                [Tr(Td(A(e["question_id"], href="/ui/observations/" + e["start_observation_id"]), Small(e["source_id"] + " · version " + e["question_version"])),
                    Td(local_time(e["started_at_utc"], zone)), Td(local_time(e["ended_at_utc"], zone) if e["ended_at_utc"] else "Not confirmed ended"),
                    Td(badge(e["status"])), Td(f"{e['estimated_observed_seconds']:.1f} s"), Td(f"{e['unknown_seconds']:.1f} s")) for e in event_rows])),
                P("Latest 100 episodes. Durations estimate bounded sampled intervals; missing observations never close an episode.", cls="muted")]
        elif view == "metrics":
            for d in data:
                summary, q = d["summary"], d["spec"]
                occupancy = summary["occupancy_fraction"]
                content.append(Section(H2(q.text), P(f"{d['source_id']} · version {q.version} · {q.kind}"),
                    Div(*(Div(Small(label), StrongText(value), cls="stat") for label, value in (
                        ("Episodes" if q.kind == "binary" else "Valid samples", ("No data" if summary["episode_count"] is None else str(summary["episode_count"])) if q.kind == "binary" else str(summary["valid_sample_count"])),
                        ("Estimated active time" if q.kind == "binary" else "Covered time", f"{summary['estimated_active_seconds'] if q.kind == 'binary' else summary['covered_seconds']:.3f}s" if summary["covered_seconds"] > 0 else "No interval data"),
                        ("Coverage", "No interval data" if summary["coverage_fraction"] is None else f"{summary['coverage_fraction']:.0%}"),
                        ("Occupancy", "No eligible data" if occupancy is None else f"{occupancy:.0%}"))), cls="stats"),
                    chart(summary["trend"][-60:], q.text),
                    P("Episode rate: " + (f"{summary['episodes_per_hour']:.3f} per covered hour" if summary["episodes_per_hour"] is not None else "No eligible interval") + f" · Unobserved time: {summary['unknown_seconds']:.1f}s", cls="muted") if q.kind == "binary" else None,
                    P("Rating levels: " + " · ".join(f"{i} {level}" for i, level in enumerate(q.levels)) + ". Values are ordered levels, not physical units.", cls="muted") if q.kind == "ordinal" else None,
                    Details(Summary("Daily episode counts / choice dwell"), Pre(json.dumps({"daily_counts": summary["daily_episode_counts"], "choice_dwell_seconds": summary["choice_dwell_seconds"]}, indent=2))),
                    Small("Chart: latest 60 samples; unknown intervals break the line. Times shown in " + zone)))
        else:
            content += [Section(H2("Processing and access"), P("One inference slot; no queued frames. Live capture and model loading require explicit operator setup."),
                                P("Current browser role: " + ("operator" if operator else "viewer")),
                                action("Rebuild events from stored observations", "/ui/replay", csrf, secondary=True) if operator else None,
                                P("Rebuilding preserves raw observations, immutable question versions and stable event IDs.", cls="muted")),
                        Section(H2("Evidence policy"), P("Retention is off by default. Enable it per source; retained frames are privacy-masked and restricted to operators.")),
                        Section(H2("Source and engine placement"), P("Capture and inference use independent contracts. This build runs locally; remote workers and GPU configuration remain separate later work."))]
        if view in ("overview", "sources"):
            observations = store.observations(selected or None, limit=20)
            content.append(Section(H2("Recent observations"), table(["Question", "Result", "Captured", "Provenance"],
                [Tr(Td(o["question_id"], Small(o["source_id"] + " · version " + o["question_version"])), Td(badge(o["status"]), Small(str(o["answer"].get("value")))),
                    Td(local_time(o["captured_at_utc"], zone)),
                    Td(A("Inspect native result", href="/ui/observations/" + o["id"]))) for o in reversed(observations)])))
        return page(view.title(), request, [c for c in content if c is not None], view=view, notice=request.query_params.get("notice"))

    @app.route("/ui/sources/{source_id}", methods=["GET"])
    def source_editor(source_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Operator permission required", status_code=403)
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        control = store.source_control(source_id)
        csrf = request.scope["session"]["csrf"]
        return page("Source controls", request, [Form(hidden(csrf), H2(pipeline.sources[source_id].name),
            P("Capture stays on this machine; engine selection is independent."),
            Label(Input(type="checkbox", name="enabled", checked=control["enabled"]), " Enabled"),
            Div(Label(Input(type="checkbox", name="retain_evidence", checked=control["retain_evidence"]), " Retain privacy-masked evidence"), cls="field"),
            field("Sample interval in seconds (0 stops sampling)", "sample_interval_seconds", control["sample_interval_seconds"], type="number", min=0, max=3600, step=1),
            P("Saving a nonzero interval explicitly starts background sampling. Evidence is off by default.", cls="muted"), Button("Save controls"),
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
        return RedirectResponse("/?view=sources&notice=Source+controls+saved", status_code=303)

    @app.route("/ui/questions/{source_id}/{question_id}", methods=["GET"])
    def question_editor(source_id: str, question_id: str, request):
        if request.scope.get("auth_role") != "operator":
            return Response("Operator permission required", status_code=403)
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        record = next((r for r in store.questions(source_id) if r["spec"].question_id == question_id), None)
        if record is None and question_id != "new":
            raise ValueError("Unknown question")
        q = record["spec"] if record else QuestionSpec("new_question", "1", "Is the condition visible?", AnswerKind.BINARY)
        policy = record["policy"] if record else QueryPolicy()
        csrf = request.scope["session"]["csrf"]
        return page("Edit question" if record else "New question", request, [Form(hidden(csrf),
            Input(type="hidden", name="expected_version", value=q.version if record else ""),
            field("Question ID", "question_id", q.question_id if record else "", required=True, maxlength=64, readonly=bool(record)),
            field("Question", "text", q.text, required=True, maxlength=4096),
            Div(Label("Answer kind", _for="kind"), Select(*(Option(k.value, value=k.value, selected=k == q.kind) for k in AnswerKind), name="kind", id="kind"), cls="field"),
            Div(Label("Choice options — one name | description per line", _for="choices"), Textarea("\n".join(f"{n}|{d}" for n, d in q.choices), name="choices", id="choices"), cls="field"),
            Div(Label("Ordinal levels — one description per line, lowest first", _for="levels"), Textarea("\n".join(q.levels), name="levels", id="levels"), cls="field"),
            Div(field("Binary threshold (uncalibrated)", "threshold", q.threshold, type="number", min=0, max=1, step="0.01"),
                field("Maximum observation gap (seconds)", "max_gap_seconds", policy.max_gap_seconds, type="number", min=1, max=86400), cls="pair"),
            Div(field("Positive confirmations", "positive_confirmations", policy.positive_confirmations, type="number", min=1, max=100),
                field("Negative confirmations", "negative_confirmations", policy.negative_confirmations, type="number", min=1, max=100), cls="pair"),
            Div(Label("After an unknown gap", _for="unknown_gap_policy"), Select(Option("Resume the episode after reconfirmation", value="resume", selected=policy.unknown_gap_policy == "resume"),
                Option("Split into an interrupted episode and a new episode", value="split", selected=policy.unknown_gap_policy == "split"),
                Option("Require operator review before continuing", value="manual_review", selected=policy.unknown_gap_policy == "manual_review"), id="unknown_gap_policy", name="unknown_gap_policy"), cls="field"),
            field("ROI (optional: x, y, width, height in 0–1)", "roi", ",".join(str(v) for v in policy.roi) if policy.roi else ""),
            Label(Input(type="checkbox", name="enabled", checked=record["enabled"] if record else True), " Question enabled"),
            field("Mock answer preset (true/false, option name, or level number)", "mock_answer", str(engine.source_answers.get((source_id, q.question_id, q.version), engine.configured.get(q.question_id, ""))) if isinstance(engine, MockInferenceEngine) else "") if engine.synthetic else None,
            P("Each save creates an immutable version. Mock presets are synthetic instructions, not image analysis.", cls="muted"),
            P("For a manual-review gap, review the history and save a new version to start fresh confirmations.", cls="muted"),
            Button("Save new version"), method="post", action=f"/ui/questions/{source_id}/{question_id}", cls="editor")], view="questions")

    @app.route("/ui/questions/{source_id}/{question_id}", methods=["POST"])
    async def save_question(source_id: str, question_id: str, request):
        if source_id not in pipeline.sources:
            raise ValueError("Unknown source")
        form = await request.form()
        qid = identifier(str(form["question_id"]))
        if question_id != "new" and qid != question_id:
            raise ValueError("Question ID cannot change")
        kind = AnswerKind(form["kind"])
        choices = tuple(tuple(line.split("|", 1)) for line in str(form.get("choices", "")).splitlines() if line.strip()) if kind == AnswerKind.CHOICE else ()
        levels = tuple(line.strip() for line in str(form.get("levels", "")).splitlines() if line.strip()) if kind == AnswerKind.ORDINAL else ()
        q = QuestionSpec(qid, "1", str(form["text"]), kind, choices, levels, float(form["threshold"]))
        if len(q.text) > 4096:
            raise ValueError("Question text exceeds 4096 characters")
        roi_text = str(form.get("roi", "")).strip()
        policy = QueryPolicy(int(form["positive_confirmations"]), int(form["negative_confirmations"]), float(form["max_gap_seconds"]), str(form["unknown_gap_policy"]),
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
        saved = store.edit_question(source_id, q, policy, enabled=form.get("enabled") == "on", expected_version=str(form.get("expected_version")) or None)
        if value is not None:
            store.set_mock_value(source_id, saved.question_id, saved.version, value)
            engine.configure_source_answer(source_id, saved.question_id, saved.version, value)
        return RedirectResponse("/?view=questions&notice=Immutable+question+version+saved", status_code=303)

    @app.route("/ui/sources/{source_id}/capture", methods=["POST"])
    async def capture(source_id: str, request):
        result = await run_in_threadpool(pipeline.run, source_id)
        summary = result["result"]
        content = [P("Capture result: " + summary["status"]), Pre(json.dumps(summary, indent=2)),
                   A("Return to overview", href="/", cls="button secondary")]
        if pipeline.latest_preview and pipeline.latest_preview[:2] == (source_id, summary["frame_id"]):
            content.insert(1, evidence_image(f"/ui/preview/{source_id}/{summary['frame_id']}", "Privacy-masked source frame; mock answers are not computer vision",
                                             tuple(r["policy"].roi for r in store.questions(source_id))))
        return page("Capture inspection", request, content, view="sources")

    @app.route("/ui/sources/{source_id}/demo", methods=["POST"])
    async def demo(source_id: str, request):
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
        content = [P(observation["source_id"] + " / " + observation["question_id"] + " · version " + observation["question_version"]),
                   P("Captured: " + local_time(observation["captured_at_utc"], settings.timezone_name)),
                   Pre(json.dumps(observation["run"], indent=2))]
        frame_id = observation["run"]["frame_id"]
        if request.scope.get("auth_role") == "operator" and frame_id and store.evidence(observation["source_id"], frame_id):
            url = f"/ui/evidence/{observation['source_id']}/{frame_id}"
            content.insert(2, evidence_image(url, "Retained privacy-masked evidence", (store.policy(observation["source_id"], observation["question_id"], observation["question_version"]).roi,)))
            content.append(action("Delete retained evidence", url + "/delete", request.scope["session"]["csrf"], secondary=True))
        else:
            content.append(P("No accessible retained evidence.", cls="muted"))
        return page("Observation detail", request, content, view="events")


def StrongText(value):
    from fasthtml.components import Strong
    return Strong(str(value))
