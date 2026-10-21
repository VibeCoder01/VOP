"""Native release forms reuse the dashboard's authentication, CSRF and layout."""
import json
import secrets
import os

from fasthtml.components import A, Button, Div, Form, H2, Input, Option, P, Pre, Section, Select, Td, Tr
from starlette.concurrency import run_in_threadpool
from starlette.responses import JSONResponse, RedirectResponse, Response

from vop.display import duration, duration_input
from vop.dashboard import field, hidden, badge
from vop.reliable import configuration, csv_export
from vop.storage import dumps


def install_release(app, settings, store, pipeline, reliable):
    def operator(request):
        return request.scope.get("auth_role") == "operator"

    @app.route("/api/v1/alerts", methods=["GET"])
    def api_alerts(request):
        params = request.query_params
        return JSONResponse({"alerts": reliable.alerts(source_id=params.get("source_id") or None, severity=params.get("severity") or None,
                                question_id=params.get("question_id") or None, start=params.get("start") or None, end=params.get("end") or None)})

    @app.route("/release", methods=["GET"])
    def release(request):
        csrf = request.scope["session"].setdefault("csrf", secrets.token_urlsafe(24))
        is_operator = operator(request)
        params = request.query_params
        rules = reliable.rules()
        alerts = reliable.alerts(source_id=params.get("source") or None, severity=params.get("severity") or None,
                                 question_id=params.get("question") or None, start=params.get("start") or None, end=params.get("end") or None)
        content = [P("Notifications describe sampled observations. MOCK alerts are demonstrations, not physical detections."),
                   Form(field("Filter source ID", "source", params.get("source", ""), id="filter-source"), field("Filter question ID", "question", params.get("question", ""), id="filter-question"),
                        field("Severity", "severity", params.get("severity", "")), field("From UTC (ISO 8601)", "start", params.get("start", "")),
                        field("Before UTC (ISO 8601)", "end", params.get("end", "")), Button("Filter alerts"), method="get", action="/release", cls="filters"),
                   Section(H2("Notifications"), app.state.table(["Created / rule", "Condition", "Severity / status", "Delivery", "Operator action"],
                    [Tr(Td(a["created_at_utc"], P(a["rule_id"] + f" · revision {a['rule_revision']}")),
                        Td(a["source_id"] + " / " + a["question_id"], P(a["kind"]), P("MOCK" if a["payload"]["synthetic"] else "Model observation")),
                        Td(badge(a["severity"]), P(badge(a["status"])), P(a["note"])),
                        Td(*(P(d['channel'] + ': ', badge(d['status']), f" · {d['attempts']} attempts") for d in a["deliveries"])),
                        Td(Form(hidden(csrf), field("Note", "note", a["note"], maxlength="4096", id="note-" + a["id"]),
                                Select(*(Option(v, value=v) for v in ("acknowledged", "resolved", "note")), name="action", aria_label="Alert action"),
                                Button("Save"), method="post", action=f"/release/alerts/{a['id']}") if is_operator else "Read only")) for a in alerts])),
                   P("Latest 1,000 matching alerts; use a time filter for older records."),
                   Section(H2("Rules"), Pre(dumps(rules)), P("Duration uses estimated, bounded sampled intervals; count uses confirmed episode starts. Acknowledgement does not imply the condition ended."))]
        if is_operator:
            content.append(Section(H2("Create or revise a rule"),
                P("A rule needs a current source and question ID. Restore or add them before saving.", cls="readiness warning") if not any(store.questions(sid) for sid in pipeline.sources) else None,
                Form(hidden(csrf), field("Rule ID", "id", required=True),
                     Select(*(Option(sid, value=sid) for sid in pipeline.sources), name="source_id", aria_label="Source"),
                     field("Rule question ID", "question_id", required=True),
                     Select(*(Option(label, value=k) for k, label in (("duration", "Active longer than (sampled duration)"), ("count", "Episode count greater than"), ("source_offline", "Source offline"), ("processing_degraded", "Processing degraded"))), name="kind", aria_label="Rule kind"),
                     field("Threshold (H:M:S for duration; number for counts)", "threshold", "0", required=True, placeholder="00:01:00 or 2"),
                     field("Count window (H:M:S)", "window_seconds", "01:00:00.0", required=True),
                     Select(*(Option(s, value=s) for s in ("info", "warning", "critical")), name="severity", aria_label="Severity"),
                     field("Enabled", "enabled", "on", type="checkbox", checked=True), field("Optional webhook (requires server environment configuration)", "webhook", "on", type="checkbox"),
                     P("Webhook delivery needs VOP_WEBHOOK_URL and VOP_WEBHOOK_ALLOWED_HOSTS in the server environment. They are not configured; dashboard notifications still work.", cls="readiness warning") if not os.environ.get('VOP_WEBHOOK_URL') or not os.environ.get('VOP_WEBHOOK_ALLOWED_HOSTS') else P("Webhook environment is present; endpoint authentication/reachability is checked at delivery.", cls="readiness info"),
                     Button("Save rule revision", disabled=not any(store.questions(sid) for sid in pipeline.sources)), method="post", action="/release/rules")))
        content.append(Section(H2("Export measured data"),
            Form(Select(*(Option(k, value=k) for k in ("events", "metrics", "alerts")), name="kind", aria_label="Dataset"),
                 Select(Option("JSON", value="json"), Option("CSV", value="csv"), name="format", aria_label="Format"),
                 field("Export source ID", "source", params.get("source", ""), id="export-source"), field("Export question ID", "question", params.get("question", ""), id="export-question"),
                 field("From UTC", "start", params.get("start", ""), id="export-start"), field("Before UTC", "end", params.get("end", ""), id="export-end"),
                 field("Timezone", "timezone", settings.timezone_name), Button("Download"), method="get", action="/release/export"),
            P("Includes timezone, question versions and provenance. Evidence pixels and credentials are excluded.")))
        if is_operator:
            content.extend([Section(H2("Configuration and backup"), A("Export current configuration", href="/release/config", cls="button secondary"),
                            P("Configuration includes local file references and environment variable names, never their secret values. Backup, restore and import run offline with tools/release.py; stop VOP first. Backups contain evidence when retained and need the same access protection as the live database.")),
                            Section(H2("Retention preview"), P("No automatic deletion until a policy is explicitly applied. Applied policies run hourly while VOP is running. Raw detail, evidence and audit have separate windows. Normalized history, events and metrics remain for replay. Backups are managed separately by the operator."),
                                    Form(hidden(csrf), *(field(label, k, duration((30 if k != "audit" else 365) * 86400), required=True) for k, label in (("evidence", "Evidence retention (H:M:S; whole days)"), ("raw", "Raw detail retention (H:M:S; whole days)"), ("audit", "Audit retention (H:M:S; whole days)"))),
                                         Button("Preview deletion"), method="post", action="/release/retention/preview")),
                            Section(H2("Audit history"), Pre(dumps(audit_rows(store))))])
        return app.state.page("Alerts and release tools", request, content, view="settings", notice=params.get("notice"))

    @app.route("/release/rules", methods=["POST"])
    async def rule_edit(request):
        form = await request.form()
        body = {k: str(form.get(k, "")) for k in ("id", "source_id", "question_id", "kind", "severity")}
        body.update(threshold=duration_input(form["threshold"]) if body["kind"] == "duration" else float(form["threshold"]), window_seconds=duration_input(form["window_seconds"]), enabled="enabled" in form, webhook="webhook" in form)
        await run_in_threadpool(reliable.save_rule, body)
        return RedirectResponse("/release?notice=Rule+revision+saved", status_code=303)

    @app.route("/release/alerts/{alert_id}", methods=["POST"])
    async def alert_edit(alert_id: str, request):
        form = await request.form()
        await run_in_threadpool(reliable.update_alert, alert_id, str(form.get("action", "")), str(form.get("note", "")))
        return RedirectResponse("/release?notice=Alert+updated", status_code=303)

    @app.route("/release/export", methods=["GET"])
    def export(request):
        params = request.query_params
        fmt = params.get("format", "json")
        if fmt not in ("json", "csv"):
            raise ValueError("Unsupported export format")
        body = reliable.export(params.get("kind", "events"), zone=params.get("timezone", settings.timezone_name),
                               source_id=params.get("source") or None, question_id=params.get("question") or None,
                               start=params.get("start") or None, end=params.get("end") or None, severity=params.get("severity") or None)
        return Response(csv_export(body) if fmt == "csv" else dumps(body), media_type="text/csv" if fmt == "csv" else "application/json",
                        headers={"Content-Disposition": f'attachment; filename="vop-export.{fmt}"'})

    @app.route("/release/config", methods=["GET"])
    def config_export(request):
        if not operator(request):
            return JSONResponse({"error": "operator_required"}, status_code=403)
        store.audit("configuration_export", "operator")
        return Response(dumps(configuration(settings, store, reliable)), media_type="application/json", headers={"Content-Disposition": 'attachment; filename="vop-configuration.json"'})

    @app.route("/release/retention/{mode}", methods=["POST"])
    async def retention(mode: str, request):
        if mode not in ("preview", "apply"):
            raise ValueError("Unknown maintenance action")
        form = await request.form()
        days = {}
        for k in ('evidence', 'raw', 'audit'):
            value = str(form[k])
            seconds = duration_input(value) if ':' in value else int(value) * 86400
            if seconds % 86400:
                raise ValueError('Retention must be a whole number of days, for example 24:00:00.')
            days[k] = int(seconds / 86400)
        result = await run_in_threadpool(reliable.retention, days, apply=mode == "apply")
        content = [Pre(dumps(result))]
        if mode == "preview":
            content.append(Form(hidden(request.scope["session"]["csrf"]), *(Input(type="hidden", name=k, value=v) for k, v in days.items()),
                                Button("Apply policy and delete eligible data", cls="danger"), method="post", action="/release/retention/apply"))
        content.append(A("Return to release tools", href="/release"))
        return app.state.page("Retention " + mode, request, content, view="settings")


def audit_rows(store):
    with store.connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY sequence DESC LIMIT 100")]
