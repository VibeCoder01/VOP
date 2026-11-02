"""Selective workspace archives and offline, restart-boundary replacement.

SQLite schema is allow-listed against this installation before importing any rows.
Protected values stay OS-encrypted; archives never contain plaintext credentials.
"""
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sqlite3
from tempfile import TemporaryDirectory
from uuid import uuid4
from zipfile import ZipFile, ZIP_DEFLATED

from vop.config import load_config
from vop.contracts import utcnow
from importlib.metadata import version
from vop.secret_cleanup import references
from vop.secrets import reference
from vop.storage import dumps

MAX_ARCHIVE = 2 * 1024**3
DATA = ('deliveries', 'alerts', 'rule_states', 'action_jobs', 'events', 'observations', 'runs', 'frames', 'audit')
CONFIG = ('sources', 'question_versions', 'source_controls', 'query_controls', 'query_policies',
          'mock_values', 'rules', 'rule_versions', 'action_definitions', 'automations', 'action_audio', 'release_settings')
ALL = CONFIG + DATA
DESCRIPTORS = {'sources', 'question_versions', 'query_policies', 'rule_versions'}


@contextmanager
def connection(path, **kwargs):
    db = sqlite3.connect(path, **kwargs)
    try:
        with db:
            yield db
    finally:
        db.close()


def copy_database(source, destination):
    with connection(source) as old, connection(destination) as new:
        old.backup(new)


def schema(db):
    return db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' ORDER BY type,name").fetchall()


def validate_database(path, template):
    with connection(f'{Path(path).as_uri()}?mode=ro', uri=True) as db, connection(template) as expected:
        if schema(db) != schema(expected) or db.execute('PRAGMA user_version').fetchone()[0] != 3:
            raise ValueError('This backup has an incompatible database structure. Use the matching VOP version.')
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('The backup database is damaged. No settings were changed.')


@contextmanager
def mutable(db):
    db.execute('PRAGMA foreign_keys=OFF')
    triggers = db.execute("SELECT name,sql FROM sqlite_master WHERE type='trigger'").fetchall()
    with db:
        for name, _ in triggers:
            db.execute('DROP TRIGGER "' + name.replace('"', '""') + '"')
        yield
        for _, sql in triggers:
            db.execute(sql)
    db.execute('PRAGMA foreign_keys=ON')


def remove_history(db):
    for table in DATA:
        db.execute(f'DELETE FROM {table}')
    db.execute("DELETE FROM sqlite_sequence WHERE name IN ('observations','audit')")
    db.execute("UPDATE sources SET status='UNKNOWN',last_frame_utc=NULL")
    db.execute("UPDATE automations SET state='{}'")
    db.execute("DELETE FROM release_settings WHERE id LIKE 'camera_test:%' OR id LIKE 'action_device:%'")


def config_refs(db):
    found = set()
    for key, value in db.execute('SELECT id,value_json FROM release_settings'):
        value = json.loads(value)
        if key == 'workspace_config':
            value = {k: v for k, v in value.items() if k != 'engine'}
        found.update(references(value))
    for table, column in (('sources', 'configuration'), ('action_definitions', 'configuration')):
        for row in db.execute(f'SELECT {column} FROM {table}'):
            found.update(references(json.loads(row[0])))
    return {reference(name) for name in found} - {'dashboard-access-key'}


def encrypted_values(vault, names):
    values = {}
    for name in names:
        path = vault.root / (reference(name) + '.dpapi')
        if not path.exists() and getattr(vault, 'migrate_legacy', False):
            path = vault._legacy_path(name)
        if path is None or not path.exists():
            raise ValueError('A protected setting is unavailable. Repair it in camera, engine or action settings before backing up configuration. Protected backup currently requires Windows.')
        payload = path.read_bytes()
        vault._crypt(payload, True)  # Fail before labelling an unusable backup complete.
        values[name] = payload
    return values


def create_archive(store, config, vault, destination, *, configs, data):
    if not configs and not data:
        raise ValueError('Select Configuration, Captured data, or both.')
    with TemporaryDirectory(prefix='vop-backup-') as folder:
        path = Path(folder) / 'workspace.sqlite3'
        copy_database(store.path, path)
        with connection(path) as db:
            with mutable(db):
                db.execute("DELETE FROM release_settings WHERE id LIKE 'pending_secret_delete:%'")
                if configs:
                    db.execute("INSERT OR REPLACE INTO release_settings VALUES('workspace_config',?)", (dumps(config),))
                if not data:
                    remove_history(db)
                if not configs:
                    for table in CONFIG:
                        if table not in DESCRIPTORS:
                            db.execute(f'DELETE FROM {table}')
                values = encrypted_values(vault, config_refs(db)) if configs else {}
            db.execute('VACUUM')  # Removed captured bytes must not survive in free pages.
        config_bytes = dumps(config if configs else None).encode()
        if (len(values) > 1021 or len(config_bytes) > 8 * 1024**2
                or path.stat().st_size + len(config_bytes) + sum(map(len, values.values())) > MAX_ARCHIVE - 1024**2):
            raise ValueError('Backup exceeds the 2 GB limit. Choose Configuration only, or use the offline backup tools for a larger workspace.')
        manifest = {'version': 2, 'application_version':version('vop'), 'created_at_utc':utcnow().isoformat(), 'configuration': configs, 'data': data, 'files': {}}
        with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
            for name, payload in [('configuration.json', config_bytes),
                                  *((f'protected/{name}.dpapi', value) for name, value in values.items())]:
                archive.writestr(name, payload)
                manifest['files'][name] = sha256(payload).hexdigest()
            archive.write(path, 'workspace.sqlite3')
            manifest['files']['workspace.sqlite3'] = digest(path)
            archive.writestr('manifest.json', dumps(manifest))
    return manifest


def digest(path):
    from hashlib import file_digest
    with Path(path).open('rb') as stream:
        return file_digest(stream, 'sha256').hexdigest()


def inspect_archive(archive_path, destination, template, vault, *, decrypt_keys=True):
    destination = Path(destination)
    with ZipFile(archive_path) as archive:
        entries = archive.infolist()
        if len(entries) > 1024 or len({e.filename for e in entries}) != len(entries) or sum(e.file_size for e in entries) > MAX_ARCHIVE:
            raise ValueError('Backup is too large or has duplicate entries. Maximum unpacked size is 2 GB.')
        if archive.getinfo('configuration.json').file_size > 8 * 1024**2:
            raise ValueError('Backup configuration is too large.')
        if archive.getinfo('manifest.json').file_size > 1024**2:
            raise ValueError('Invalid backup manifest.')
        manifest = json.loads(archive.read('manifest.json'))
        if manifest.get('version') != 2 or type(manifest.get('configuration')) is not bool or type(manifest.get('data')) is not bool:
            raise ValueError('Choose a VOP selective workspace backup (.vop).')
        files = manifest.get('files', {})
        if set(files) | {'manifest.json'} != {e.filename for e in entries} or not {'workspace.sqlite3','configuration.json'} <= set(files):
            raise ValueError('Backup contents do not match its manifest.')
        for name, expected in files.items():
            if name not in ('workspace.sqlite3', 'configuration.json'):
                if not name.startswith('protected/') or not name.endswith('.dpapi'):
                    raise ValueError('Unexpected backup entry.')
                ref = reference(name[len('protected/'):-len('.dpapi')])
                if ref == 'dashboard-access-key':
                    raise ValueError('Backups cannot replace the local sign-in key.')
                if not manifest['configuration'] or archive.getinfo(name).file_size > 16384:
                    raise ValueError('Invalid protected backup entry.')
            target = destination / name  # Every permitted name is fixed or a validated reference.
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(name) as source, target.open('wb') as output:
                shutil.copyfileobj(source, output, 256 * 1024)
            if digest(target) != expected:
                raise ValueError('Backup checksum mismatch. No settings were changed.')
        validate_database(destination / 'workspace.sqlite3', template)
        config = json.loads((destination / 'configuration.json').read_text(encoding='utf-8'))
        if manifest['configuration']:
            # The destination database path is never taken from an uploaded file.
            config['database'] = str(Path(template).resolve())
            check = destination / 'validate.json'
            check.write_text(dumps(config), encoding='utf-8')
            load_config(check)
            check.unlink()
            if decrypt_keys:
                for path in (destination / 'protected').glob('*.dpapi') if (destination / 'protected').exists() else ():
                    vault._crypt(path.read_bytes(), True)  # Wrong Windows account fails before applying.
        return manifest, config


def selected_restore(current, incoming, output, *, configs, data):
    """Replace selected groups; untouched groups must have compatible descriptors."""
    if not configs and not data:
        raise ValueError('Select at least one restore group.')
    copy_database(incoming if configs else current, output)
    if configs and data:
        return
    with connection(output) as target, connection(current if configs else incoming) as history:
        # Restoring configuration alone keeps current captured data; data alone keeps
        # current configuration. Require immutable history descriptors to match.
        for table, keys in (('sources', ('id',)), ('question_versions', ('source_id','question_id','version')),
                            ('rule_versions', ('id','revision'))):
            for row in history.execute(f'SELECT * FROM {table}'):
                columns = [r[1] for r in history.execute(f'PRAGMA table_info({table})')]
                key_values = tuple(row[columns.index(k)] for k in keys)
                found = target.execute(f'SELECT * FROM {table} WHERE ' + ' AND '.join(k+'=?' for k in keys), key_values).fetchone()
                if found is None or (table != 'sources' and tuple(found) != tuple(row)):
                    # Empty history needs no corresponding descriptors.
                    if history.execute('SELECT 1 FROM observations LIMIT 1').fetchone() or history.execute('SELECT 1 FROM alerts LIMIT 1').fetchone():
                        raise ValueError('Selected data and configuration do not match. Restore both groups together, or reset before restoring configuration only.')
        with mutable(target):
            for table in DATA:
                target.execute(f'DELETE FROM {table}')
                rows = history.execute(f'SELECT * FROM {table}')
                columns = [r[1] for r in history.execute(f'PRAGMA table_info({table})')]
                target.executemany(f'INSERT INTO {table} VALUES('+','.join('?' for _ in columns)+')', rows)
            target.execute('UPDATE sources SET last_frame_utc=(SELECT MAX(captured_at_utc) FROM frames WHERE source_id=sources.id)')
        if target.execute('PRAGMA foreign_key_check').fetchone():
            raise ValueError('Restore would leave missing history references. Restore both groups together.')


def authoritative_settings(settings, store):
    with store.connection() as db:
        row = db.execute("SELECT value_json FROM release_settings WHERE id='workspace_config'").fetchone()
    if not row:
        return settings, False
    config = json.loads(row[0]); config['database'] = str(store.path.resolve())
    # The saved bootstrap supplies source adapter settings, not stale controls or
    # questions. Edits/deletions made AFTER restore must survive the next restart.
    sources = []
    with store.connection() as db:
        profile = db.execute("SELECT value_json FROM release_settings WHERE id='engine_profile'").fetchone()
        if profile:
            config['engine'] = json.loads(profile[0])
        for source in config['sources']:
            sid = source['id']
            public = db.execute('SELECT configuration FROM sources WHERE id=?',(sid,)).fetchone()
            if public is None or store.is_removed(sid):
                continue
            value = dict(source)
            value.update(name=json.loads(public[0])['name'], **store.source_control(sid))
            value['questions'] = []
            for record in store.questions(sid):
                spec = asdict(record['spec']); spec['id'] = spec.pop('question_id')
                value['questions'].append(spec)
            sources.append(value)
    config['sources'] = sources
    with TemporaryDirectory(prefix='vop-settings-') as folder:
        path = Path(folder) / 'config.json'; path.write_text(dumps(config), encoding='utf-8')
        return load_config(path), True


def queue_operation(store, staged, config, protected, *, reset=False, replace_configs=False):
    root = store.path.parent / '.vop-maintenance'
    if not root.resolve().is_relative_to(store.path.parent.resolve()):
        raise ValueError('Workspace staging must stay inside the VOP data folder.')
    root.mkdir(exist_ok=True)
    folder = root / uuid4().hex; folder.mkdir()
    try:
        copy_database(staged, folder / 'workspace.sqlite3')
        with connection(folder / 'workspace.sqlite3') as db:
            db.execute("INSERT OR REPLACE INTO release_settings VALUES('workspace_config',?)", (dumps(config),))
            db.execute("INSERT OR REPLACE INTO release_settings VALUES('actions_paused',?)",('false' if reset else 'true',))
            db.execute("INSERT OR REPLACE INTO release_settings VALUES('notification_rules_paused',?)",('false' if reset else 'true',))
            db.execute("DELETE FROM rule_states WHERE NOT EXISTS(SELECT 1 FROM rules r WHERE substr(rule_states.id,1,length(r.id)+1)=r.id||':')")
            db.execute("UPDATE action_jobs SET status='cancelled',detail='Not replayed after restore',claim=NULL WHERE status IN ('queued','retry','sending','awaiting_browser')")
            db.execute("UPDATE deliveries SET status='cancelled' WHERE status IN ('pending','retry','sending')")
            from vop.deletion_audit import audit
            if any(audit(db)['issues'].values()):
                raise ValueError('Configuration and captured data have unmatched references. Restore both groups from the same backup, or reset before restoring configuration only.')
        for name, value in protected.items():
            (folder / (reference(name) + '.dpapi')).write_bytes(value)
        body = {'folder': folder.name, 'reset': reset, 'replace_configs': replace_configs, 'keys': sorted(protected), 'sha256': digest(folder / 'workspace.sqlite3')}
        pending = store.path.with_name(store.path.name + '.maintenance.json')
        if pending.exists():
            raise ValueError('A workspace operation is already waiting for restart.')
        temporary = folder / 'pending.json'
        temporary.write_text(dumps(body), encoding='utf-8')
        temporary.replace(pending)
    except Exception:
        shutil.rmtree(folder)
        raise


def apply_pending(settings, vault):
    """Called by the launcher only after all old VOP processes have stopped."""
    database = settings.database
    pending = database.with_name(database.name + '.maintenance.json')
    if not pending.exists():
        return
    body = json.loads(pending.read_text(encoding='utf-8'))
    if (not {'folder','reset','replace_configs','keys','sha256'} <= set(body)
            or set(body) - {'folder','reset','replace_configs','keys','sha256','completed'}
            or type(body['reset']) is not bool or type(body['replace_configs']) is not bool
            or not isinstance(body['keys'],list) or type(body.get('completed',False)) is not bool):
        raise ValueError('Invalid pending workspace operation.')
    name = body['folder']
    if len(name) != 32 or any(c not in '0123456789abcdef' for c in name):
        raise ValueError('Invalid pending workspace operation.')
    folder = database.parent / '.vop-maintenance' / name
    if folder.is_symlink() or not folder.resolve().is_relative_to(database.parent.resolve()):
        raise ValueError('Workspace staging must stay inside the VOP data folder.')
    def complete():
        if body['reset']:
            for suffix in ('.v1-backup.sqlite3', '.v2-backup.sqlite3'):
                database.with_name(database.name + suffix).unlink(missing_ok=True)
        if folder.exists():
            shutil.rmtree(folder)
        pending.unlink()
    if body.get('completed'):
        complete()
        return
    stage = folder / 'workspace.sqlite3'
    if digest(stage) != body['sha256']:
        raise ValueError('Pending workspace checksum failed; original workspace was not changed.')
    validate_database(stage, database)
    keys = {reference(k): (folder / (reference(k)+'.dpapi')).read_bytes() for k in body['keys']}
    for payload in keys.values():
        vault._crypt(payload, True)
    names = set(keys)
    if body['reset'] or body.get('replace_configs'):
        names |= {p.stem for p in vault.root.glob('*.dpapi') if p.stem != 'dashboard-access-key'}
        if getattr(vault, 'migrate_legacy', False):
            for path in vault._legacy_paths('workspace-probe'):
                names |= {p.stem for p in path.parent.glob('*.dpapi') if p.stem != 'dashboard-access-key'}
    names.discard('dashboard-access-key')
    # Persist rollback BEFORE changing either store. A crash during application can
    # be rolled back at the next launch rather than backing up partially applied state.
    rollback = folder / 'rollback'
    def recover():
        copy_database(rollback / 'workspace.sqlite3', database)
        original_names = json.loads((rollback / 'keys.json').read_text(encoding='utf-8'))
        for name in original_names:
            name = reference(name)
            original = rollback / (name+'.dpapi')
            if original.exists():
                vault._write_blob(vault.root / (name+'.dpapi'), original.read_bytes())
            else:
                (vault.root / (name+'.dpapi')).unlink(missing_ok=True)
        return set(original_names)
    if (rollback / 'ready').exists():
        names |= recover()
    else:
        rollback.mkdir(exist_ok=True)
        copy_database(database, rollback / 'workspace.sqlite3')
        for name in names:
            original = vault.root / (name+'.dpapi')
            if not original.exists() and getattr(vault, 'migrate_legacy', False):
                original = vault._legacy_path(name)
            if original is not None and original.exists():
                (rollback / (name+'.dpapi')).write_bytes(original.read_bytes())
        (rollback / 'keys.json').write_text(dumps(sorted(names)),encoding='utf-8')
        (rollback / 'ready').touch()
    try:
        for name in names:
            if name == 'dashboard-access-key':
                raise ValueError('Backups cannot replace the local sign-in key.')
            if body['reset'] or name not in keys:
                vault.delete(name)
            else:
                vault._write_blob(vault.root / (name+'.dpapi'), keys[name])
        copy_database(stage, database)
        with connection(database) as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
            db.execute('VACUUM')
    except Exception:
        recover()
        raise
    body['completed'] = True
    temporary = folder / 'complete.json'
    temporary.write_text(dumps(body),encoding='utf-8')
    temporary.replace(pending)
    complete()
