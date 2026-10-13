"""Offline release maintenance; restore/import always create a new directory."""
import argparse
import json
from pathlib import Path

from vop.config import load_config
from vop.pipeline import Pipeline
from vop.inference.mock import MockInferenceEngine
from vop.storage import Store, dumps
from vop.reliable import Reliable, backup, configuration, restore, validate_rule
from vop.measurements import QueryPolicy


def import_configuration(source, destination):
    package = json.loads(Path(source).read_text(encoding="utf-8"))
    if not isinstance(package, dict) or set(package) != {"schema_version", "config", "policies", "mock_values", "rules"} or package["schema_version"] != 1:
        raise ValueError("Unsupported configuration package")
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError("Import requires a new destination directory")
    # Build privately and validate all controls before publishing any destination.
    import tempfile
    import shutil
    with tempfile.TemporaryDirectory(prefix="vop-config-import-") as folder:
        stage = Path(folder).resolve()
        path = stage / "config.json"
        path.write_text(dumps(package["config"]), encoding="utf-8")
        settings = load_config(path)
        if settings.database != (stage / "data" / "vop.sqlite3").resolve():
            raise ValueError("Configuration package must use data/vop.sqlite3")
        store = Store(settings.database)
        store.configure(settings)
        pipeline = Pipeline(settings, MockInferenceEngine(settings.mock_answers), store, None)
        reliable = Reliable(store, settings, pipeline)
        expected = {(s.source_id, q.question_id, q.version) for s in settings.sources for q in s.questions}
        seen = set()
        with store.connection() as db:
            for record in package["policies"]:
                if set(record) != {"source_id", "question_id", "version", "enabled", "policy"} or type(record["enabled"]) is not bool:
                    raise ValueError("Invalid query control record")
                key = (record["source_id"], record["question_id"], record["version"])
                if key not in expected or key in seen:
                    raise ValueError("Unknown or duplicate policy")
                seen.add(key)
                policy = QueryPolicy(**record["policy"])
                db.execute("DELETE FROM query_policies WHERE source_id=? AND question_id=? AND version=?", key)
                db.execute("INSERT INTO query_policies VALUES(?,?,?,?)", (*key, dumps(policy)))
                db.execute("UPDATE query_controls SET enabled=? WHERE source_id=? AND question_id=?", (record["enabled"], *key[:2]))
            if seen != expected:
                raise ValueError("Missing query policies")
        for sid, qid, version, value in package["mock_values"]:
            if (sid, qid, version) not in expected:
                raise ValueError("Unknown mock question")
            pipeline.engine.configure_source_answer(sid, qid, version, value)
            store.set_mock_value(sid, qid, version, value)
        for body in package["rules"]:
            reliable.save_rule(body)
        store.audit("configuration_import", "validated")
        # Copy exact allow-listed files; never an archive extraction or path supplied by the package.
        destination.mkdir(parents=True)
        (destination / "data").mkdir()
        shutil.copyfile(path, destination / "config.json")
        with store.connection() as old:
            import sqlite3
            with sqlite3.connect(destination / "data" / "vop.sqlite3") as new:
                old.backup(new)
    return destination / "config.json"


def main():
    parser = argparse.ArgumentParser(description="VOP maintenance: stop the dashboard first")
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("backup", "export-config"):
        p = sub.add_parser(name)
        p.add_argument("--config", required=True, type=Path)
        p.add_argument("--output", required=True, type=Path)
    for name in ("restore", "import-config"):
        p = sub.add_parser(name)
        p.add_argument("--input", required=True, type=Path)
        p.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.command in ("restore", "import-config"):
        output = restore(args.input, args.output) if args.command == "restore" else import_configuration(args.input, args.output)
    else:
        settings = load_config(args.config)
        store = Store(settings.database)
        store.configure(settings)
        pipeline = Pipeline(settings, MockInferenceEngine(settings.mock_answers), store, None)
        package = configuration(settings, store, Reliable(store, settings, pipeline))
        if args.command == "backup":
            output = backup(store, package, args.output)
        else:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(dumps(package))
            output = args.output
    print(json.dumps({"result": "PASS", "command": args.command, "output": str(output)}))


if __name__ == "__main__":
    main()
