"""Explicit, durable cleanup candidates; never sweep unknown OS-vault values."""
import json

from vop.secrets import reference
from vop.storage import dumps

PREFIX = 'pending_secret_delete:'
FIELDS = {'secret', 'secret_ref', 'endpoint_ref', 'credentials_ref', 'endpoint_secret_ref'}


def references(value):
    found = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in FIELDS and isinstance(item, str):
                found.add(item)
            else:
                found.update(references(item))
    elif isinstance(value, (list, tuple)):
        for item in value:
            found.update(references(item))
    return found


def queue(db, name):
    if name:
        name = reference(name)
        db.execute('INSERT OR IGNORE INTO release_settings VALUES(?,?)', (PREFIX + name, dumps(name)))


def used_references(db, pipeline):
    used = {'dashboard-access-key'} | references(pipeline.settings.engine) | references(getattr(pipeline.engine, 'config', {}))
    for row in db.execute('SELECT configuration FROM sources'):
        used.update(references(json.loads(row[0])))
    for row in db.execute("SELECT value_json FROM release_settings WHERE id NOT LIKE 'pending_secret_delete:%'"):
        used.update(references(json.loads(row[0])))
    if db.execute("SELECT 1 FROM sqlite_master WHERE name='action_definitions'").fetchone():
        for row in db.execute('SELECT configuration FROM action_definitions'):
            used.update(references(json.loads(row[0])))
    return used


def clean(store, vault, pipeline):
    """Caller serializes action edits; pipeline lock excludes engine/credential edits."""
    with store.connection() as db:
        rows = db.execute("SELECT id,value_json FROM release_settings WHERE id LIKE 'pending_secret_delete:%' ORDER BY rowid LIMIT 1").fetchall()
        if not rows:
            return None
        used = used_references(db, pipeline)
        sending = set()
        for row in db.execute("SELECT configuration FROM action_jobs WHERE status='sending'"):
            sending.update(references(json.loads(row[0])))
    # Never hold a database writer transaction while calling an OS vault. Caller
    # locks serialize configuration edits; a crash before acknowledgement retries.
    key, value = rows[0]
    name = reference(json.loads(value))
    pending = key != PREFIX + name or name in sending and name not in used
    failed = key != PREFIX + name
    if not pending and name not in used:
        try:
            vault.delete(name)
        except Exception:
            pending = True
            failed = True
    with store.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('DELETE FROM release_settings WHERE id=? AND value_json=?', (key, value))
        if pending:
            # Move this retry to the tail so a locked file cannot starve others.
            db.execute('INSERT OR IGNORE INTO release_settings VALUES(?,?)', (key, value))
    return 'Protected-setting cleanup is pending. It will retry when the OS vault is available.' if failed else None
