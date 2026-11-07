"""Monitoring controls run off the event loop, with bounded busy retries."""
import json
import sqlite3
from time import sleep


def storage_busy(error):
    code = getattr(error, 'sqlite_errorcode', None)
    return (code & 255) in (sqlite3.SQLITE_BUSY, sqlite3.SQLITE_LOCKED) if code is not None else str(error) in ('database is locked', 'database table is locked')


def retry_busy(operation):
    for attempt in range(3):
        try:
            return operation()
        except sqlite3.OperationalError as error:
            if not storage_busy(error) or attempt == 2:
                raise
            sleep(.1)


def change_monitoring(app, source_id, starting):
    pipeline, store = app.state.pipeline, app.state.store
    if source_id not in pipeline.sources:
        raise ValueError('Unknown source')
    control = retry_busy(lambda: store.source_control(source_id))
    if starting and not store.questions(source_id, active_only=True):
        raise ValueError('Add or enable a question before starting monitoring')

    def save_interval():
        with store.connection() as db:
            row = db.execute('SELECT value_json FROM release_settings WHERE id=?', ('monitor_interval:' + source_id,)).fetchone()
            interval = control['sample_interval_seconds'] or (json.loads(row[0]) if row else 10)
            db.execute('INSERT OR REPLACE INTO release_settings VALUES(?,?)', ('monitor_interval:' + source_id, json.dumps(interval)))
        return interval
    interval = retry_busy(save_interval)
    retry_busy(lambda: store.update_source(source_id, enabled=True if starting else control['enabled'],
        retain_evidence=control['retain_evidence'], sample_interval_seconds=interval if starting else 0))
    if not starting:
        # Retry just the atomic gap write, not already committed control changes.
        retry_busy(lambda: pipeline.record_gap(source_id))
        return not pipeline.busy.locked() and not any(c['enabled'] and c['sample_interval_seconds'] for c in store.sources(tuple(pipeline.sources)))
    return False
