"""Native release forms reuse the dashboard's authentication, CSRF and layout."""
import json
import secrets
import os
from datetime import datetime, timezone
from uuid import uuid4
from zoneinfo import available_timezones
from urllib.parse import urlencode

from fasthtml.components import A, Button, Div, Form, H2, Input, Label, Nav, Option, P, Pre, Section, Select, Td, Tr
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
                                question_id=params.get("question_id") or None, start=utc_value(params.get("start")), end=utc_value(params.get("end")))})

    def dropdown(label, name, options, selected='', *, empty=None, **kwargs):
        return Div(Label(label, _for=name), Select(
            Option(empty, value='', selected=not selected) if empty is not None else None,
            *(Option(text, value=value, selected=str(value) == str(selected)) for value, text in options),
            name=name, id=name, **kwargs), cls='field')

    def utc_value(value):
        if not value: return None
        stamp = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp.astimezone(timezone.utc)).isoformat()

    def dates(params):
        return [field(label, key, utc_value(params.get(key))[:19] if params.get(key) else '', type='datetime-local', step='1')
                for label, key in (('From (UTC)', 'start'), ('Before (UTC)', 'end'))]

    @app.route('/release', methods=['GET'])
    def release(request):
        csrf = request.scope['session'].setdefault('csrf', secrets.token_urlsafe(24))
        is_operator = operator(request)
        params = request.query_params
        tabs = [('notifications', 'Notifications'), ('rules', 'Rules'), ('export', 'Export'),
                ('configuration', 'Configuration and backup'), ('retention', 'Retention'), ('audit', 'Audit')]
        if not is_operator:
            tabs = [tab for tab in tabs if tab[0] in ('notifications', 'rules', 'export')]
        tab = params.get('tab', 'notifications')
        if tab not in dict(tabs):
            raise ValueError('Choose an available Settings tab.')
        with store.connection() as db:
            cameras = {r['id']: json.loads(r['configuration']).get('name', r['id']) for r in db.execute('SELECT id,configuration FROM sources')}
            historical_questions = list(db.execute('SELECT source_id,question_id,specification FROM question_versions ORDER BY version'))
        questions = {}
        for row in historical_questions:
            questions[row['question_id']] = json.loads(row['specification'])['text']
        def filters():
            return [dropdown('Camera', 'source', list(cameras.items()), params.get('source', ''), empty='All cameras'),
                    dropdown('Question', 'question', list(questions.items()), params.get('question', ''), empty='All questions')]
        navigation = Nav(*(A(label, href='/release?' + urlencode({'tab': key}), aria_current='page' if key == tab else None)
                           for key, label in tabs), cls='settings-tabs', aria_label='Settings sections')
        content = [navigation]
        if tab == 'notifications':
            alerts = reliable.alerts(source_id=params.get('source') or None, question_id=params.get('question') or None,
                start=utc_value(params.get('start')), end=utc_value(params.get('end')), severity=params.get('severity') or None)
            content += [Form(Input(type='hidden', name='tab', value=tab), *filters(),
                dropdown('Severity', 'severity', [(v, v.capitalize()) for v in ('info', 'warning', 'critical')], params.get('severity', ''), empty='All severities'),
                *dates(params), Button('Filter notifications'), method='get', action='/release', cls='filters'),
                Section(H2('Notifications'), app.state.table(['Created / rule', 'Condition', 'Severity / status', 'Delivery', 'Action'],
                    [Tr(Td(a['created_at_utc'], P(a['rule_id'])),
                        Td(cameras.get(a['source_id'], a['source_id']), P(questions.get(a['question_id'], a['question_id'])),
                           P('Synthetic test result') if a['payload'].get('synthetic') else None),
                        Td(badge(a['severity']), P(badge(a['status'])), P(a['note'])),
                        Td(*(P(d['channel'] + ': ', badge(d['status'])) for d in a['deliveries'])),
                        Td(Form(hidden(csrf), field('Note', 'note', a['note'], maxlength=4096, id='note-' + a['id']),
                            Select(*(Option(v.capitalize(), value=v) for v in ('acknowledged', 'resolved', 'note')), name='action', aria_label='Notification action'),
                            Button('Save'), method='post', action='/release/alerts/' + a['id'], cls='form-grid') if is_operator else 'Read only')) for a in alerts])),
                P('Latest 1,000 matching notifications. Use dates to find older records.', cls='muted')]
        elif tab == 'rules':
            rules = reliable.rules()
            chosen = next((r for r in rules if r['id'] == params.get('rule')), {})
            kinds = [('duration', 'Active longer than'), ('count', 'Episode count greater than'), ('source_offline', 'Camera offline'), ('processing_degraded', 'Processing degraded')]
            content += [Section(H2('Rules'), app.state.table(['Rule', 'Camera / question', 'Condition', 'Threshold', 'Status'],
                [Tr(Td(r['id']), Td(cameras.get(r['source_id'], r['source_id']), P(questions.get(r['question_id'], r['question_id']))),
                    Td(dict(kinds).get(r['kind'], r['kind'])), Td(duration(r['threshold']) if r['kind'] == 'duration' else f"{r['threshold']:.1f}"),
                    Td('Enabled' if r['enabled'] else 'Paused')) for r in rules]))]
            if is_operator:
                conditions = [(sid + '/' + r['spec'].question_id, source.name + ' — ' + r['spec'].text)
                              for sid, source in pipeline.sources.items() for r in store.questions(sid)]
                content += [Form(Input(type='hidden', name='tab', value='rules'),
                    dropdown('Edit rule', 'rule', [(r['id'], r['id']) for r in rules], params.get('rule', ''), empty='New rule'),
                    Button('Open rule'), method='get', action='/release', cls='filters'),
                    Section(H2('Edit rule' if chosen else 'New rule'),
                        P('Add a camera and question before creating a rule.', cls='notice') if not conditions else None,
                        Form(hidden(csrf), field('Rule ID (leave empty to create one)', 'id', chosen.get('id', ''), readonly=bool(chosen)),
                            dropdown('Camera and question', 'condition', conditions, chosen.get('source_id', '') + '/' + chosen.get('question_id', ''), required=True),
                            dropdown('Condition', 'kind', kinds, chosen.get('kind', 'duration')),
                            field('Threshold (H:M:S for duration; number for counts)', 'threshold', duration(chosen.get('threshold', 3600)) if chosen.get('kind', 'duration') == 'duration' else chosen.get('threshold', 0), required=True),
                            field('Count window (H:M:S)', 'window_seconds', duration(chosen.get('window_seconds', 3600)), required=True),
                            dropdown('Severity', 'severity', [(v, v.capitalize()) for v in ('info', 'warning', 'critical')], chosen.get('severity', 'warning')),
                            dropdown('Status', 'enabled', [('on', 'Enabled'), ('', 'Paused')], 'on' if chosen.get('enabled', True) else ''),
                            dropdown('Delivery', 'webhook', [('', 'Dashboard only'), ('on', 'Dashboard and webhook')], 'on' if chosen.get('webhook') else ''),
                            P('Webhook delivery requires server configuration. Dashboard notifications work without it.', cls='muted'),
                            Button('Save rule', disabled=not conditions), method='post', action='/release/rules', cls='form-grid'))]
        elif tab == 'export':
            zones = list(dict.fromkeys([settings.timezone_name, 'UTC', *sorted(available_timezones())]))
            content += [Section(H2('Export'), Form(
                dropdown('Data', 'kind', [('events', 'Episodes'), ('metrics', 'Trends'), ('alerts', 'Notifications')]),
                dropdown('File format', 'format', [('csv', 'CSV'), ('json', 'JSON')]), *filters(), *dates(params),
                dropdown('Timezone', 'timezone', [(z, z) for z in zones], settings.timezone_name), Button('Download'),
                method='get', action='/release/export', cls='form-grid'),
                P('Includes question versions and engine details. Images and credentials are excluded.', cls='muted'))]
        elif tab == 'configuration':
            content += [Section(H2('Configuration and backup'),
                A('Export configuration', href='/release/config', cls='button'),
                P('The export includes saved setup, without passwords or access keys.'),
                P('For a full backup or restore, stop VOP and use tools/release.py. A full backup can contain saved images. Keep it private.'),
                A('Workspace controls', href='/?view=settings', cls='button secondary'),
                A('Manage recorded data', href='/observations', cls='button secondary'))]
        elif tab == 'retention':
            options = [(duration(d * 86400), f'{duration(d * 86400)} ({d} days)') for d in (1, 7, 30, 90, 365)]
            content += [Section(H2('Retention'), P('Choose how long to keep images, engine details and audit records. Review the deletion preview before applying it. Answers and episodes remain.'),
                Form(hidden(csrf), *(dropdown(label, key, options, duration((365 if key == 'audit' else 30) * 86400))
                    for key, label in (('evidence', 'Images'), ('raw', 'Engine details'), ('audit', 'Audit records'))),
                    Button('Preview deletion'), method='post', action='/release/retention/preview', cls='form-grid'))]
        elif tab == 'audit':
            content += [Section(H2('Audit'), app.state.table(['Time (UTC)', 'Action', 'Result'],
                [Tr(Td(r['created_at_utc']), Td(r['action'].replace('_', ' ').capitalize()), Td(r['outcome'])) for r in audit_rows(store)]),
                P('Latest 100 recorded actions.', cls='muted'))]
        return app.state.page('Settings', request, content, view='settings', notice=params.get('notice'))

    @app.route("/release/rules", methods=["POST"])
    async def rule_edit(request):
        form = await request.form()
        body = {k: str(form.get(k, "")) for k in ("id", "source_id", "question_id", "kind", "severity")}
        if form.get('condition'):
            body['source_id'], body['question_id'] = str(form['condition']).split('/', 1)
        if not body['id']:
            body['id'] = 'rule-' + uuid4().hex[:12]
        body.update(threshold=duration_input(form["threshold"]) if body["kind"] == "duration" else float(form["threshold"]), window_seconds=duration_input(form["window_seconds"]), enabled=bool(form.get("enabled")), webhook=bool(form.get("webhook")))
        await run_in_threadpool(reliable.save_rule, body)
        return RedirectResponse("/release?tab=rules&notice=Rule+saved", status_code=303)

    @app.route("/release/alerts/{alert_id}", methods=["POST"])
    async def alert_edit(alert_id: str, request):
        form = await request.form()
        await run_in_threadpool(reliable.update_alert, alert_id, str(form.get("action", "")), str(form.get("note", "")))
        return RedirectResponse("/release?tab=notifications&notice=Notification+updated", status_code=303)

    @app.route("/release/export", methods=["GET"])
    def export(request):
        params = request.query_params
        fmt = params.get("format", "json")
        if fmt not in ("json", "csv"):
            raise ValueError("Unsupported export format")
        body = reliable.export(params.get("kind", "events"), zone=params.get("timezone", settings.timezone_name),
                               source_id=params.get("source") or None, question_id=params.get("question") or None,
                               start=utc_value(params.get("start")), end=utc_value(params.get("end")), severity=params.get("severity") or None)
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
        content.append(A("Return to Retention", href="/release?tab=retention"))
        return app.state.page("Retention " + mode, request, content, view="settings")


def audit_rows(store):
    with store.connection() as db:
        return [dict(r) for r in db.execute("SELECT * FROM audit ORDER BY sequence DESC LIMIT 100")]
