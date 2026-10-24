"""Recoverable configuration removal and confirmed question/data deletion."""
from dataclasses import asdict, replace
import json
from hashlib import sha256

from fasthtml.components import A, Button, Div, Form, H2, Input, Noscript, P, Section, Small, Table, Tbody, Td, Th, Thead, Tr
from starlette.responses import RedirectResponse, Response
from fasthtml.common import to_xml
from urllib.parse import urlencode
from starlette.concurrency import run_in_threadpool

from vop.contracts import ProviderError, utcnow
from vop.dashboard import action, hidden
from vop.display import answer_kind
from vop.storage import dumps
from vop.history_deletion import question_counts, question_selection, delete_question_data, checkpoint


def removed_controls(store, pipeline, csrf, view, *, source_kinds=None, heading=None, source_filter=None, editable=True):
    if view == 'sources':
        rows = [(s.name, f"/ui/sources/{sid}/restore") for sid, s in list(pipeline.removed_sources.items()) if source_kinds is None or s.kind in source_kinds]
        return Section(H2(heading or 'Removed sources'), P('Restore keeps monitoring disabled. History and protected camera details are retained.'),
                       *(Section(P(label), action('Restore', url, csrf, secondary=True)) for label, url in rows)) if rows else None
    rows = []
    for sid, source in list(pipeline.sources.items()):
        if source_filter and sid != source_filter:
            continue
        for record in store.questions(sid, include_removed=True):
            question = record['spec']
            url = f'/ui/questions/{sid}/{question.question_id}'
            rows.append(Tr(Td(Input(type='checkbox', name='selection', value=dumps([sid, question.question_id]),
                                   form='question-selection', aria_label=f'Select {question.text} on {source.name}') if editable else ''),
                Td(source.name or sid), Td(question.text, Small(question.question_id), Small(answer_kind(question.kind) + ' · version ' + question.version + (' · Enabled' if record['enabled'] else ' · Paused')), Small('Awaiting deletion', cls='status warning') if store.is_removed(sid, question.question_id) else None),
                *(Td('Loading…', data_count=key, data_source=sid, data_question=question.question_id)
                  for key in ('answers', 'images', 'episodes', 'alerts')),
                Td(Div(A('Edit', href=url, cls='button secondary') if not store.is_removed(sid, question.question_id) else None,
                       A('Delete question…', href=url + '/delete', cls='button danger'), cls='actions') if editable else 'Read only')))
    return Section(H2('Questions'),
        P('Delete question permanently deletes the question and all its recorded data. There is no Undo.'),
        P('Counts load separately and include all versions. Shared images can appear in several rows.', cls='muted'),
        P('Loading recorded data counts…', data_counts_status='', role='status', cls='muted'),
        Noscript(P('Counts require JavaScript here. Open Delete question to review its recorded data counts.')),
        Button('Retry counts', type='button', cls='secondary', hidden=True, data_retry_counts=''),
        Form(hidden(csrf), Button('Delete selected…', cls='danger'), id='question-selection',
             method='post', action='/ui/questions/delete') if editable else None,
        Div(Table(Thead(Tr(*(Th(label) for label in ('Select', 'Camera', 'Question', 'Answers', 'Images', 'Episodes', 'Alerts', 'Actions')))),
                  Tbody(*rows)), cls='table-wrap'), cls='question-list', data_counts_url='/ui/question-counts' + ('?' + urlencode({'source': source_filter}) if source_filter else '')) if rows else Section(H2('Questions'), P('No questions. Add a question to begin.'))


QUESTION_COUNTS_JS = """const list = document.querySelector('[data-counts-url]');
if (list) {
  const status = list.querySelector('[data-counts-status]');
  const retry = list.querySelector('[data-retry-counts]');
  async function load() {
    retry.hidden = true;
    status.textContent = 'Loading recorded data counts…';
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    try {
      const response = await fetch(list.dataset.countsUrl, {signal: controller.signal, headers: {Accept: 'text/html'}});
      if (!response.ok || response.redirected) throw new Error('counts unavailable');
      const doc = new DOMParser().parseFromString(await response.text(), 'text/html');
      const cells = new Map(Array.from(doc.querySelectorAll('[data-count]'), cell =>
        [JSON.stringify([cell.dataset.source, cell.dataset.question, cell.dataset.count]), cell]));
      const targets = Array.from(list.querySelectorAll('[data-count]'));
      if (targets.some(cell => !cells.has(JSON.stringify([cell.dataset.source, cell.dataset.question, cell.dataset.count]))))
        throw new Error('questions changed');
      for (const cell of targets) {
        const value = cells.get(JSON.stringify([cell.dataset.source, cell.dataset.question, cell.dataset.count]));
        cell.replaceChildren(...value.childNodes);
      }
      status.textContent = 'Recorded data counts loaded. Counts can change while monitoring runs.';
    } catch (_) {
      status.textContent = 'Counts could not load. Try again. You can still edit questions or review deletion counts.';
      retry.hidden = false;
    } finally { clearTimeout(timer); }
  }
  retry.addEventListener('click', load);
  load();
}
"""


def install_removal(app, store, pipeline, reliable):
    @app.route('/ui/question-counts.js', methods=['GET'])
    def counts_script():
        return Response(QUESTION_COUNTS_JS, media_type='application/javascript')

    def count_cells(source_filter):
        cells = []
        with store.connection() as db:
            db.execute('BEGIN')
            for sid in list(pipeline.sources):
                if source_filter and source_filter != sid:
                    continue
                for record in store.questions(sid, include_removed=True):
                    qid = record['spec'].question_id
                    counts = question_counts(db, sid, qid)
                    cells.extend(Div(str(counts[key]), Small(f"{counts['shared_images']} shared") if key == 'images' and counts['shared_images'] else None,
                                     data_count=key, data_source=sid, data_question=qid)
                                 for key in ('answers', 'images', 'episodes', 'alerts'))
        return to_xml(Div(*cells))

    @app.route('/ui/question-counts', methods=['GET'])
    async def counts_fragment(request):
        selected = request.query_params.get('source', '')
        if selected and selected not in pipeline.sources:
            raise ValueError('Unknown source')
        return Response(await run_in_threadpool(count_cells, selected), media_type='text/html')

    def checked(source_id, question_id=None, *, removed=False):
        sources = pipeline.removed_sources if removed and question_id is None else pipeline.sources
        if source_id not in sources:
            raise ValueError("Unknown source")
        if question_id is not None:
            record = next((r for r in store.questions(source_id, include_removed=True) if r['spec'].question_id == question_id), None)
            if record is None or (removed is not None and store.is_removed(source_id, question_id) != removed):
                raise ValueError("Unknown question")
            return record

    def change(source_id, question_id=None, *, restore=False):
        pipeline.busy.acquire()
        try:
            reliable.lock.acquire()
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
                pipeline.clear_preview(source_id)
            finally:
                reliable.lock.release()
        finally:
            pipeline.busy.release()

    async def remove(request, source_id, question_id=None):
        if request.scope['auth_role'] != 'operator':
            return Response("Operator required", status_code=403)
        checked(source_id, question_id)
        view = "questions" if question_id is not None else "sources"
        camera = question_id is None and pipeline.sources[source_id].kind in ('rtsp', 'usb')
        destination = '/cameras' if camera else f'/?view={view}'
        if request.method == 'POST':
            await run_in_threadpool(change, source_id, question_id)
            return RedirectResponse(destination + ('?' if camera else '&') + 'notice=Removed.+History+retained', status_code=303)
        label = question_id if question_id is not None else pipeline.sources[source_id].name
        return app.state.page("Remove " + label, request, [
            P("Removal waits for the current observation to finish. Keep this page open while it works."),
            P("This removes the item from active configuration and disables its alert rules. Pending webhook deliveries are cancelled. Recorded observations, events, evidence and immutable versions remain."),
            P("Protected camera details are retained. Restore is available on the listing; monitoring and alert rules must be enabled explicitly afterwards."),
            Form(hidden(request.scope['session']['csrf']), Button("Remove " + label, cls="danger"), method="post", action=request.url.path),
            A("Cancel", href=destination, cls="button secondary")], view='cameras' if camera else view)

    @app.route('/ui/sources/{source_id}/remove', methods=['GET', 'POST'])
    async def remove_source(request, source_id: str):
        return await remove(request, source_id)

    @app.route('/ui/questions/{source_id}/{question_id}/remove', methods=['GET', 'POST'])
    async def remove_question(request, source_id: str, question_id: str):
        checked(source_id, question_id, removed=None)
        return RedirectResponse(f'/ui/questions/{source_id}/{question_id}/delete', status_code=303)

    @app.route('/ui/sources/{source_id}/restore', methods=['POST'])
    async def restore_source(source_id: str):
        await run_in_threadpool(change, source_id, restore=True)
        if pipeline.sources[source_id].kind in ('rtsp', 'usb'):
            return RedirectResponse('/cameras?notice=Camera+restored.+Monitoring+is+paused.', status_code=303)
        return RedirectResponse('/?view=sources&notice=Restored.+Monitoring+disabled', status_code=303)

    @app.route('/ui/questions/{source_id}/{question_id}/restore', methods=['POST'])
    async def restore_question(source_id: str, question_id: str):
        checked(source_id, question_id, removed=None)
        return RedirectResponse(f'/ui/questions/{source_id}/{question_id}/delete', status_code=303)

    def question_snapshot(db, pairs):
        items = [(sid, qid, checked(sid, qid, removed=None), question_selection(db, sid, qid)) for sid, qid in pairs]
        fingerprint = sha256(dumps([(sid, qid, record['spec'].version, chosen['fingerprint'])
                                    for sid, qid, record, chosen in items]).encode()).hexdigest()
        return items, fingerprint

    def delete_questions(pairs, expected_data, expected_version=None):
        # Called in a worker thread: wait without blocking the dashboard event loop.
        pipeline.busy.acquire()
        try:
            reliable.lock.acquire()
            try:
                with store.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    items, fingerprint = question_snapshot(db, pairs)
                    if expected_version is not None and expected_version != items[0][2]['spec'].version:
                        raise ValueError('Question changed. Reopen the deletion page before confirming')
                    if expected_data != fingerprint:
                        return False
                    # Validate the whole preview first. Re-read shared runs after each purge
                    # so a later selected question cannot restore an earlier deleted answer.
                    for sid, qid, _, _ in items:
                        delete_question_data(db, question_selection(db, sid, qid))
                        db.execute('UPDATE query_controls SET enabled=0 WHERE source_id=? AND question_id=?', (sid, qid))
                        db.execute('DELETE FROM release_settings WHERE id=?', (store.removal_key(sid, qid),))
                        db.execute('INSERT INTO release_settings VALUES(?,?)',
                                   (f'deleted_question:{sid}:{qid}', dumps({'deleted_at_utc': utcnow().isoformat()})))
                        db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)',
                                   (utcnow().isoformat(), 'question_delete', dumps({'source_id': sid, 'question_id': qid})))
                for sid in {sid for sid, _ in pairs}:
                    pipeline.clear_preview(sid)
                checkpoint(store)
                return True
            finally:
                reliable.lock.release()
        finally:
            pipeline.busy.release()

    def deletion_page(request, pairs, *, changed=False, bulk=False):
        with store.connection() as db:
            db.execute('BEGIN')
            items, fingerprint = question_snapshot(db, pairs)
        rows = []
        warnings = []
        for sid, qid, record, chosen in items:
            counts = chosen['counts']
            rows.append(Tr(Td(pipeline.sources[sid].name or sid), Td(record['spec'].text),
                           *(Td(str(counts[key])) for key in ('answers', 'images', 'episodes', 'alerts'))))
            if counts['shared_images'] and (not bulk or not warnings):
                warnings.append(P('Some selected questions share saved images. Those images will disappear from other questions’ results too.' if bulk else
                    f"{counts['shared_images']} saved " + ('image is' if counts['shared_images'] == 1 else 'images are') +
                    ' shared with other questions. Those images will disappear from their results too.'))
        return app.state.page('Delete questions' if bulk else 'Delete question', request, [
            H2(f'{len(items)} selected questions' if bulk else items[0][2]['spec'].text),
            P('Recorded data changed. Review the updated counts and confirm again.', cls='notice', role='status') if changed else None,
            P('This permanently deletes the selected questions and their recorded data. They cannot be restored from the app.' if bulk else 'This permanently deletes the question and its recorded data. It cannot be restored from the app.'),
            P('Deletes answers across all versions, associated saved images, raw engine data, episodes, alerts and delivery records. Timestamp-only deletion gaps for these questions are also removed.'),
            P('Other questions’ normalised answers are kept, but shared images and raw engine details are cleared. Related alert rules are disabled.'),
            P('Deletion waits for the current observation to finish. Keep this page open while the request is working.'),
            P('The question IDs stay reserved. Leave the ID blank when adding a replacement question.'),
            Form(hidden(request.scope['session']['csrf']), Input(type='hidden', name='expected_data', value=fingerprint),
                 Input(type='hidden', name='confirm', value='yes'),
                 *(([Input(type='hidden', name='selection', value=dumps(pair)) for pair in pairs]) if bulk else
                    [Input(type='hidden', name='expected_version', value=items[0][2]['spec'].version)]),
                 Section(H2('Recorded data'), app.state.table(['Camera', 'Question', 'Answers', 'Images', 'Episodes', 'Alerts'], rows),
                         P('Counts are per question. Shared images may appear in more than one row; each image is deleted once.', cls='muted'),
                         *warnings,
                         P('Question definitions and audit records remain. There is no Undo. Existing backups, exports and messages already sent are not changed.', cls='readiness warning')),
                 Button('Delete question and data' if not bulk else 'Delete selected questions and data', cls='danger'), method='post', action=request.url.path),
            A('Cancel', href='/?view=questions', cls='button secondary')], view='questions')

    @app.route('/ui/questions/{source_id}/{question_id}/delete', methods=['GET', 'POST'])
    async def delete_question(request, source_id: str, question_id: str):
        if request.scope.get('auth_role') != 'operator':
            return Response('Operator required', status_code=403)
        checked(source_id, question_id, removed=None)
        changed = False
        if request.method == 'POST':
            form = await request.form()
            if await run_in_threadpool(delete_questions, [(source_id, question_id)],
                                      str(form.get('expected_data', '')), str(form.get('expected_version', ''))):
                return RedirectResponse('/?view=questions&notice=Question+deleted.+Recorded+data+deleted.', status_code=303)
            changed = True
        return deletion_page(request, [(source_id, question_id)], changed=changed)

    @app.route('/ui/removed-questions/delete', methods=['POST'])
    async def legacy_bulk_delete():
        return RedirectResponse('/ui/questions/delete', status_code=307)

    @app.route('/ui/questions/delete', methods=['POST'])
    async def delete_selected_questions(request):
        if request.scope.get('auth_role') != 'operator':
            return Response('Operator required', status_code=403)
        form = await request.form()
        try:
            values = [json.loads(value) for value in form.getlist('selection')]
            if not values or len(values) > 1024 or any(not isinstance(value, list) or len(value) != 2 or not all(isinstance(part, str) for part in value) for value in values):
                raise ValueError()
            pairs = sorted({tuple(value) for value in values})
        except (ValueError, TypeError):
            raise ValueError('Select one or more questions before deleting.') from None
        changed = False
        if form.get('confirm') == 'yes':
            if await run_in_threadpool(delete_questions, pairs, str(form.get('expected_data', ''))):
                return RedirectResponse('/?view=questions&notice=Selected+questions+and+their+recorded+data+deleted.', status_code=303)
            changed = True
        return deletion_page(request, pairs, changed=changed, bulk=True)
