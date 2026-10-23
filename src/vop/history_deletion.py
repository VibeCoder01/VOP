"""Confirmed retention deletion. Configuration is kept; retained history is replayed."""
from hashlib import sha256
import json
import logging
import sqlite3
from uuid import uuid4

from fasthtml.components import A, Button, Form, H2, Input, P, Section
from starlette.concurrency import run_in_threadpool
from starlette.responses import RedirectResponse, Response

from vop.contracts import ProviderError, utcnow
from vop.dashboard import hidden
from vop.storage import dumps


def selection(db, *, source_id=None, observation_id=None):
    if observation_id:
        row = db.execute("SELECT source_id,run_id FROM observations WHERE id=? AND status!='retention_gap'", (observation_id,)).fetchone()
        if row is None:
            raise ProviderError('source_not_found', 'This observation no longer exists')
        source_id, run_id = row
        runs = db.execute('SELECT id,source_id,frame_id FROM runs WHERE id=?', (run_id,)).fetchall()
        answers = db.execute('SELECT sequence,source_id,question_id,question_version,captured_at_utc,processed_at_utc,temporal_eligible FROM observations WHERE run_id=? ORDER BY sequence', (run_id,)).fetchall()
        keys = sorted({(r['source_id'], r['question_id'], r['question_version']) for r in answers})
    else:
        if not db.execute('SELECT 1 FROM sources WHERE id=?', (source_id,)).fetchone():
            raise ValueError('This input does not exist')
        runs = db.execute("SELECT id,source_id,frame_id FROM runs WHERE source_id=? AND id IN (SELECT run_id FROM observations WHERE status!='retention_gap') ORDER BY id", (source_id,)).fetchall()
        answers = db.execute("SELECT sequence,source_id,question_id,question_version,captured_at_utc,processed_at_utc,temporal_eligible FROM observations WHERE source_id=? AND status!='retention_gap' ORDER BY sequence", (source_id,)).fetchall()
        keys = [tuple(r) for r in db.execute('SELECT source_id,question_id,version FROM question_versions WHERE source_id=?', (source_id,))]
    alerts, events = [], []
    for key in keys:
        alerts.extend(r[0] for r in db.execute('SELECT id FROM alerts WHERE source_id=? AND question_id=? AND question_version=?', key))
        events.extend(r[0] for r in db.execute('SELECT id FROM events WHERE source_id=? AND question_id=? AND question_version=?', key))
    pairs = {(k[0], k[1]) for k in keys}
    rules = [dict(r) for r in db.execute('SELECT * FROM rules') if (json.loads(r['configuration'])['source_id'], json.loads(r['configuration'])['question_id']) in pairs]
    evidence = sum(bool(db.execute('SELECT 1 FROM frames WHERE source_id=? AND frame_id=? AND evidence_png IS NOT NULL', (r['source_id'], r['frame_id'])).fetchone()) for r in runs)
    counts = {'captures': len(runs), 'answers': len(answers), 'images': evidence, 'episodes': len(events), 'alerts': len(alerts),
              'rules': sum(json.loads(r['configuration'])['enabled'] for r in rules),
              'gap_markers': 0 if observation_id else db.execute("SELECT count(*) FROM observations WHERE source_id=? AND status='retention_gap'", (source_id,)).fetchone()[0]}
    fingerprint = sha256(dumps({'source_id': source_id, 'capture': bool(observation_id), 'counts': counts, 'runs': sorted(r['id'] for r in runs), 'alerts': sorted(alerts), 'events': sorted(events), 'rules': rules}).encode()).hexdigest()
    return dict(source_id=source_id, runs=runs, answers=answers, keys=keys, alerts=alerts, rules=rules, counts=counts, fingerprint=fingerprint)


def delete_related_alerts(db, chosen):
    for aid in chosen['alerts']:
        db.execute('DELETE FROM deliveries WHERE alert_id=?', (aid,))
        db.execute('DELETE FROM alerts WHERE id=?', (aid,))
    for rule in chosen['rules']:
        config = json.loads(rule['configuration'])
        if config['enabled']:
            config['enabled'] = False
            revision = rule['revision'] + 1
            db.execute('UPDATE rules SET revision=?,configuration=? WHERE id=?', (revision, dumps(config), rule['id']))
            db.execute('INSERT INTO rule_versions VALUES(?,?,?)', (rule['id'], revision, dumps(config)))
        db.execute('DELETE FROM rule_states WHERE substr(id,1,?)=?', (len(rule['id']) + 1, rule['id'] + ':'))


def delete_selected(db, chosen, *, whole_source=False):
    delete_related_alerts(db, chosen)
    for run in chosen['runs']:
        db.execute('DELETE FROM observations WHERE run_id=?', (run['id'],))
        db.execute('DELETE FROM runs WHERE id=?', (run['id'],))
        if run['frame_id']:
            db.execute('DELETE FROM frames WHERE source_id=? AND frame_id=?', (run['source_id'], run['frame_id']))
    sid = chosen['source_id']
    if whole_source:
        db.execute("DELETE FROM observations WHERE source_id=? AND status='retention_gap'", (sid,))
        db.execute('DELETE FROM runs WHERE source_id=? AND id NOT IN (SELECT run_id FROM observations)', (sid,))
    else:
        eligible = [row for row in chosen['answers'] if row['temporal_eligible']]
        if eligible:
            # Keep timestamp-only, explicitly labelled gaps at the original positions.
            # Older replay code also treats non-success rows as Unknown, not coverage.
            gap_run = 'deleted-' + str(uuid4())
            stamp = eligible[0]['processed_at_utc']
            marker = {'status': 'retention_gap', 'source_id': sid, 'frame_id': None,
                      'captured_at_utc': eligible[0]['captured_at_utc'], 'processed_at_utc': stamp,
                      'engine_id': 'retention-gap', 'engine_version': '1', 'synthetic': True,
                      'elapsed_ms': None, 'usage': None, 'provider_raw': None, 'raw_retained': False, 'answers': [],
                      'error': {'code': 'retention_gap', 'message': 'Capture deleted; no image or model answer retained'}}
            db.execute('INSERT INTO runs VALUES(?,?,?,?,?)', (gap_run, sid, None, stamp, dumps(marker)))
            for row in eligible:
                db.execute('INSERT INTO observations(sequence,id,run_id,source_id,question_id,question_version,captured_at_utc,processed_at_utc,status,normalised_state,answer_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)',
                           (row['sequence'], 'deleted-' + str(uuid4()), gap_run, sid, row['question_id'], row['question_version'], row['captured_at_utc'], row['processed_at_utc'], 'retention_gap', 'unknown', dumps({'value': None})))
    last = db.execute('SELECT MAX(captured_at_utc) FROM frames WHERE source_id=?', (sid,)).fetchone()[0]
    enabled = db.execute('SELECT enabled FROM source_controls WHERE source_id=?', (sid,)).fetchone()[0]
    db.execute('UPDATE sources SET last_frame_utc=?,status=? WHERE id=?', (last, 'UNKNOWN' if enabled else 'DISABLED', sid))
    db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)', (utcnow().isoformat(), 'history_delete', dumps(chosen['counts'])))


def question_counts(db, source_id, question_id):
    """List counts without loading results/images or querying once per capture."""
    params = (source_id, question_id)
    answers, gaps = db.execute("SELECT COALESCE(SUM(status!='retention_gap'),0), COALESCE(SUM(status='retention_gap'),0) FROM observations WHERE source_id=? AND question_id=?", params).fetchone()
    images, shared, others = db.execute("""
        WITH selected AS (
            SELECT DISTINCT run_id FROM observations WHERE source_id=? AND question_id=?
        ), other AS (
            SELECT run_id, count(*) AS n FROM observations
            WHERE source_id=? AND question_id!=? AND status!='retention_gap' GROUP BY run_id
        )
        SELECT COALESCE(SUM(f.evidence_png IS NOT NULL),0),
               COALESCE(SUM(f.evidence_png IS NOT NULL AND other.n>0),0),
               COALESCE(SUM(other.n),0)
        FROM selected JOIN runs r ON r.id=selected.run_id
        LEFT JOIN frames f ON f.source_id=r.source_id AND f.frame_id=r.frame_id
        LEFT JOIN other ON other.run_id=r.id
        """, params + params).fetchone()
    episodes = db.execute('SELECT count(*) FROM events WHERE source_id=? AND question_id=?', params).fetchone()[0]
    alerts = db.execute('SELECT count(*) FROM alerts WHERE source_id=? AND question_id=?', params).fetchone()[0]
    return dict(answers=answers, gap_markers=gaps, images=images, shared_images=shared,
                other_answers=others, episodes=episodes, alerts=alerts)


def question_selection(db, source_id, question_id):
    """Preview all versions of one question, without loading retained image bytes."""
    params = (source_id, question_id)
    answers = db.execute('SELECT sequence,status FROM observations WHERE source_id=? AND question_id=? ORDER BY sequence', params).fetchall()
    runs = db.execute('SELECT id,frame_id,result_json FROM runs WHERE id IN (SELECT run_id FROM observations WHERE source_id=? AND question_id=?) ORDER BY id', params).fetchall()
    alerts = [r[0] for r in db.execute('SELECT id FROM alerts WHERE source_id=? AND question_id=? ORDER BY id', params)]
    events = [r[0] for r in db.execute('SELECT id FROM events WHERE source_id=? AND question_id=? ORDER BY id', params)]
    rules = [dict(r) for r in db.execute('SELECT * FROM rules ORDER BY id') if (json.loads(r['configuration'])['source_id'], json.loads(r['configuration'])['question_id']) == params]
    counts = question_counts(db, source_id, question_id)
    fingerprint = sha256(dumps({'source_id': source_id, 'question_id': question_id, 'counts': counts, 'answers': [r['sequence'] for r in answers],
                               'runs': [(r['id'], sha256(r['result_json'].encode()).hexdigest()) for r in runs], 'alerts': alerts, 'events': events, 'rules': rules}).encode()).hexdigest()
    return dict(source_id=source_id, question_id=question_id, runs=runs, alerts=alerts, rules=rules, counts=counts, fingerprint=fingerprint)


def delete_question_data(db, chosen):
    """Purge one question; preserve other normalised answers from shared captures."""
    sid, qid = chosen['source_id'], chosen['question_id']
    delete_related_alerts(db, chosen)
    db.execute('DELETE FROM observations WHERE source_id=? AND question_id=?', (sid, qid))
    db.execute('DELETE FROM events WHERE source_id=? AND question_id=?', (sid, qid))
    for run in chosen['runs']:
        if not db.execute('SELECT 1 FROM observations WHERE run_id=?', (run['id'],)).fetchone():
            db.execute('DELETE FROM runs WHERE id=?', (run['id'],))
            if run['frame_id']:
                db.execute('DELETE FROM frames WHERE source_id=? AND frame_id=?', (sid, run['frame_id']))
            continue
        body = json.loads(run['result_json'])
        body['answers'] = [a for a in body['answers'] if a['question_id'] != qid]
        # Opaque shared payloads can contain any answer. Keep typed answers and
        # provenance, following the existing raw-retention policy for provider data.
        body.update(raw_retained=False, provider_raw=None, usage=None, error=None)
        for answer in body['answers']:
            answer['raw_provider_fields'] = None
            answer['usage'] = None
        db.execute('UPDATE runs SET result_json=? WHERE id=?', (dumps(body), run['id']))
        for row in db.execute('SELECT id,answer_json FROM observations WHERE run_id=?', (run['id'],)).fetchall():
            answer = json.loads(row['answer_json'])
            answer.update(raw_provider_fields=None, usage=None)
            db.execute('UPDATE observations SET answer_json=? WHERE id=?', (dumps(answer), row['id']))
        db.execute('UPDATE frames SET evidence_png=NULL WHERE source_id=? AND frame_id=?', (sid, run['frame_id']))
    last = db.execute('SELECT MAX(captured_at_utc) FROM frames WHERE source_id=?', (sid,)).fetchone()[0]
    db.execute('UPDATE sources SET last_frame_utc=? WHERE id=?', (last, sid))
    db.execute('INSERT INTO audit(created_at_utc,action,outcome) VALUES(?,?,?)', (utcnow().isoformat(), 'question_data_delete', dumps({'source_id': sid, 'question_id': qid, **chosen['counts']})))


def checkpoint(store):
    try:
        with store.connection() as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
    except sqlite3.OperationalError:
        logging.getLogger(__name__).warning('History deletion committed; database checkpoint deferred')


def install_history_deletion(app, store, pipeline, reliable):
    def change(expected, *, source_id=None, observation_id=None):
        if not pipeline.busy.acquire(False):
            raise ProviderError('overloaded', 'An observation is running. Wait, then review deletion again')
        try:
            if not reliable.lock.acquire(False):
                raise ProviderError('overloaded', 'Alert processing is running. Wait, then review deletion again')
            try:
                with store.connection() as db:
                    db.execute('BEGIN IMMEDIATE')
                    chosen = selection(db, source_id=source_id, observation_id=observation_id)
                    control = store.source_control(chosen['source_id'])
                    if not observation_id and control['enabled'] and control['sample_interval_seconds']:
                        raise ValueError('Pause monitoring before you delete input history')
                    if expected != chosen['fingerprint']:
                        return False
                    delete_selected(db, chosen, whole_source=not observation_id)
                    for key in chosen['keys']:
                        store._rebuild(db, *key)
                pipeline.clear_preview(chosen['source_id'])
                checkpoint(store)
                return chosen['source_id']
            finally:
                reliable.lock.release()
        finally:
            pipeline.busy.release()

    async def confirm(request, *, source_id=None, observation_id=None):
        if request.scope.get('auth_role') != 'operator':
            return Response('Operator required', status_code=403)
        changed = False
        if request.method == 'POST':
            form = await request.form()
            deleted_source = await run_in_threadpool(change, str(form.get('expected', '')), source_id=source_id, observation_id=observation_id)
            if deleted_source:
                return RedirectResponse('/observations?source=' + deleted_source + '&notice=History+deleted.+Affected+alert+rules+are+paused.', status_code=303)
            changed = True
        with store.connection() as db:
            chosen = selection(db, source_id=source_id, observation_id=observation_id)
        sid, counts = chosen['source_id'], chosen['counts']
        control = store.source_control(sid)
        paused = not control['enabled'] or not control['sample_interval_seconds']
        return app.state.page('Delete capture' if observation_id else 'Delete input history', request, [
            P('History changed. Review these updated counts before you confirm.', cls='readiness warning') if changed else None,
            P('Input: ' + sid), Section(H2('What will be deleted'),
                P(f"{counts['captures']} captures · {counts['answers']} answers · {counts['images']} retained images"),
                P(f"{counts['alerts']} related alerts will be deleted. {counts['episodes']} episodes will be rebuilt from the remaining history."),
                P(f"{counts['rules']} affected alert rules will be paused. Review them before enabling them again.")),
            P('All answers from this capture share one raw result and image. They are deleted together. A timestamp-only gap remains so charts do not join across deleted data.') if observation_id else P('This deletes all recorded captures for this input. Camera setup, questions and engine profiles remain.'),
            P(f"{counts['gap_markers']} timestamp-only gap markers will also be deleted.") if not observation_id else None,
            P('There is no Undo. Setup and audit records remain. Backups and messages already sent are not changed.', cls='readiness warning'),
            P('Pause monitoring in View mode before deleting history. Use the sidebar mode switch.', cls='readiness warning') if not observation_id and not paused else None,
            Form(hidden(request.scope['session']['csrf']),
                 Input(type='hidden', name='expected', value=chosen['fingerprint']),
                 Button('Delete capture' if observation_id else 'Delete history', cls='danger', disabled=not observation_id and not paused), method='post', action=request.url.path),
            A('Cancel', href='/observations?source=' + sid, cls='button secondary')
        ], view='observations')

    @app.route('/ui/observations/{observation_id}/delete', methods=['GET', 'POST'])
    async def delete_capture(observation_id: str, request):
        return await confirm(request, observation_id=observation_id)

    @app.route('/ui/sources/{source_id}/history/delete', methods=['GET', 'POST'])
    async def delete_source_history(source_id: str, request):
        return await confirm(request, source_id=source_id)
