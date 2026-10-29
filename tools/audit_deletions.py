"""Audit metadata only; never repair, migrate, decrypt secrets or connect to hardware."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
from types import SimpleNamespace

from vop.config import load_config
from vop.deletion_audit import audit
from vop.secret_cleanup import used_references
from vop.secrets import SecretStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('config', nargs='?', type=Path, default=Path(__file__).resolve().parents[1] / 'sample-config/phase1.json')
    parser.add_argument('--check-vault', action='store_true', help='Count unreferenced canonical Windows vault filenames; do not read their contents')
    args = parser.parse_args()
    settings = load_config(args.config)
    with sqlite3.connect(settings.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.execute('PRAGMA query_only=ON')
        result = audit(db)
        if args.check_vault and os.name == 'nt':
            pipeline = SimpleNamespace(settings=settings, engine=SimpleNamespace(config={}))
            used = used_references(db, pipeline)
            # In-flight jobs may still need a deleted action's account.
            from vop.secret_cleanup import references
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='action_jobs'").fetchone():
                for row in db.execute("SELECT configuration FROM action_jobs WHERE status='sending'"):
                    used.update(references(json.loads(row[0])))
            vault = SecretStore()
            result['unreferenced_canonical_vault_files_to_review'] = sum(p.stem not in used for p in vault.root.glob('*.dpapi'))
            if vault.migrate_legacy:
                result['unreferenced_legacy_vault_files_to_review'] = sum(p.stem not in used for root in vault._legacy_roots() for p in root.glob('*.dpapi'))
            if result['result'] == 'PASS' and any(value for key, value in result.items() if key.endswith('_files_to_review')):
                result['result'] = 'REVIEW_VAULT_REFERENCES'
        elif args.check_vault:
            result['vault_check_skipped'] = 'This optional filename check is for Windows DPAPI vaults, not Linux Secret Service.'
    print(json.dumps(result, sort_keys=True))
    return 0 if result['result'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
