"""Recoverable configuration removal; immutable observations remain available."""
from dataclasses import asdict, replace
import json

from fasthtml.components import A, Button, Form, H2, P, Section
from starlette.responses import RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

from vop.contracts import ProviderError, utcnow
from vop.dashboard import action, hidden
from vop.storage import dumps


def removed_controls(store, pipeline, csrf, view):
    if view == "sources":
        rows = [(s.name, f"/ui/sources/{sid}/restore") for sid, s in list(pipeline.removed_sources.items())]
    else:
        rows = [(f"{sid} · {r['spec'].text}", f"/ui/questions/{sid}/{r['spec'].question_id}/restore")
                for sid in list(pipeline.sources) for r in store.questions(sid, include_removed=True)
                if store.is_removed(sid, r['spec'].question_id)]
    return Section(H2("Removed " + view), P("Restore keeps monitoring disabled. History and protected camera details are retained."),
                   *(Section(P(label), action("Restore", url, csrf, secondary=True)) for label, url in rows)) if rows else None


def install_removal(app, store, pipeline, reliable):
    def checked(source_id, question_id=None, *, removed=False):
        sources = pipeline.removed_sources if removed and question_id is None else pipeline.sources
        if source_id not in sources:
            raise ValueError("Unknown source")
        if question_id is not None:
            record = next((r for r in store.questions(source_id, include_removed=True) if r['spec'].question_id == question_id), None)
            if record is None or store.is_removed(source_id, question_id) != removed:
                raise ValueError("Unknown question")
            return record

    def change(source_id, question_id=None, *, restore=False):
        if not pipeline.busy.acquire(blocking=False):
            raise ProviderError("overloaded", "A capture is running; retry removal when it finishes")
        try:
            if not reliable.lock.acquire(blocking=False):
                raise ProviderError("overloaded", "Alert processing is running; retry shortly")
            try:
                record = checked(source_id, question_id, removed=restore)
                if restore:
                    if question_id is None and len(pipeline.sources) >= 32 or question_id is not None and len(store.questions(source_id)) >= 32:
                        raise ValueError("Restore would exceed the limit of 32 items")
                elif store.source_control(source_id)['enabled']:
                    if question_id is None:
                        pipeline.record_gap(source_id)
                    elif record['enabled']:
                        source = replace(pipeline.sources[source_id], questions=(record['spec'],))
                        pipeline.save_capture_error(source, ProviderError("question_removed", "Question is no longer monitored"))
                with store.connection() as db:
                    db.execute("BEGIN IMMEDIATE")
                    key = store.removal_key(source_id, question_id)
                    if restore:
                        db.execute("DELETE FROM release_settings WHERE id=?", (key,))
                    else:
                        db.execute("INSERT INTO release_settings VALUES(?,?)", (key, dumps({"removed_at_utc": utcnow().isoformat()})))
                        for row in db.execute("SELECT * FROM rules").fetchall():
                            rule = json.loads(row['configuration'])
                            if rule['source_id'] != source_id or question_id is not None and rule['question_id'] != question_id:
                                continue
                            if rule['enabled']:
                                rule['enabled'] = False
                                revision = row['revision'] + 1
                                db.execute("UPDATE rules SET revision=?,configuration=? WHERE id=?", (revision, dumps(rule), row['id']))
                                db.execute("INSERT INTO rule_versions VALUES(?,?,?)", (row['id'], revision, dumps(rule)))
                            db.execute("UPDATE deliveries SET status='cancelled' WHERE status IN ('pending','retry') AND alert_id IN (SELECT id FROM alerts WHERE rule_id=?)", (row['id'],))
                    if question_id is None:
                        db.execute("UPDATE source_controls SET enabled=0,evidence_enabled=0,sample_interval_seconds=0 WHERE source_id=?", (source_id,))
                        db.execute("UPDATE sources SET status='DISABLED' WHERE id=?", (source_id,))
                        if not restore:
                            # Keep a reconstruction record for backup restore and configuration changes.
                            db.execute("INSERT OR REPLACE INTO release_settings VALUES(?,?)", (f"retained_source:{source_id}", dumps(asdict(pipeline.sources[source_id]))))
                    else:
                        db.execute("UPDATE query_controls SET enabled=0 WHERE source_id=? AND question_id=?", (source_id, question_id))
                    db.execute("INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)", (utcnow().isoformat(), "configuration_restore" if restore else "configuration_remove", dumps({"source_id": source_id, "question_id": question_id})))
                if question_id is None:
                    source, target = (pipeline.removed_sources, pipeline.sources) if restore else (pipeline.sources, pipeline.removed_sources)
                    target[source_id] = source.pop(source_id)
                pipeline.latest_preview = None
            finally:
                reliable.lock.release()
        finally:
            pipeline.busy.release()

    async def remove(request, source_id, question_id=None):
        if request.scope['auth_role'] != 'operator':
            return Response("Operator required", status_code=403)
        checked(source_id, question_id)
        view = "questions" if question_id is not None else "sources"
        if request.method == 'POST':
            await run_in_threadpool(change, source_id, question_id)
            return RedirectResponse(f"/?view={view}&notice=Removed.+History+retained", status_code=303)
        label = question_id if question_id is not None else pipeline.sources[source_id].name
        return app.state.page("Remove " + label, request, [
            P("This removes the item from active configuration and disables its alert rules. Pending webhook deliveries are cancelled. Recorded observations, events, evidence and immutable versions remain."),
            P("Protected camera details are retained. Restore is available on the listing; monitoring and alert rules must be enabled explicitly afterwards."),
            Form(hidden(request.scope['session']['csrf']), Button("Remove " + label), method="post", action=request.url.path),
            A("Cancel", href=f"/?view={view}", cls="button secondary")], view=view)

    @app.route('/ui/sources/{source_id}/remove', methods=['GET', 'POST'])
    async def remove_source(request, source_id: str):
        return await remove(request, source_id)

    @app.route('/ui/questions/{source_id}/{question_id}/remove', methods=['GET', 'POST'])
    async def remove_question(request, source_id: str, question_id: str):
        return await remove(request, source_id, question_id)

    @app.route('/ui/sources/{source_id}/restore', methods=['POST'])
    def restore_source(source_id: str):
        change(source_id, restore=True)
        return RedirectResponse('/?view=sources&notice=Restored.+Monitoring+disabled', status_code=303)

    @app.route('/ui/questions/{source_id}/{question_id}/restore', methods=['POST'])
    def restore_question(source_id: str, question_id: str):
        change(source_id, question_id, restore=True)
        return RedirectResponse('/?view=questions&notice=Restored.+Question+disabled', status_code=303)
