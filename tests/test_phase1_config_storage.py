from dataclasses import replace
import json
from pathlib import Path
import sqlite3

import pytest

from vop.config import load_config
from vop.contracts import QuestionSpec
from vop.storage import Store


@pytest.fixture
def settings(tmp_path):
    data = json.loads((Path(__file__).resolve().parents[1] / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    data["database"] = "observations.sqlite3"
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_config(path)


@pytest.mark.parametrize("field,value", [("schema_version", 2), ("schema_version", True),
                                         ("capture_timeout_seconds", -1), ("inference_timeout_seconds", True),
                                         ("password", "secret")])
def test_reject_invalid_config(tmp_path, field, value):
    data = json.loads((Path(__file__).resolve().parents[1] / "sample-config" / "phase1.json").read_text(encoding="utf-8"))
    data[field] = value
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(path)


def test_relative_database_resolution_and_immutable_versions(settings):
    store = Store(settings.database)
    store.configure(settings)
    store.configure(settings)  # restart/bootstrap is idempotent
    source = settings.sources[0]
    changed = replace(source.questions[0], text="Changed question")
    with pytest.raises(ValueError, match="increment version"):
        store.configure(replace(settings, sources=(replace(source, questions=(changed, *source.questions[1:])),)))
    updated = replace(changed, version="2")
    store.configure(replace(settings, sources=(replace(source, questions=(updated, *source.questions[1:])),)))
    with store.connection() as connection:
        assert connection.execute("SELECT count(*) FROM question_versions").fetchone()[0] == 4
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            connection.execute("UPDATE question_versions SET specification='{}'")
    assert Store(settings.database).health()["database_schema"] == 1


def test_newer_or_foreign_database_not_silently_modified(tmp_path):
    for name, statement in (("future.sqlite3", "PRAGMA user_version=2"),
                            ("other.sqlite3", "CREATE TABLE unrelated(id INTEGER)")):
        path = tmp_path / name
        with sqlite3.connect(path) as connection:
            connection.execute(statement)
        with pytest.raises(ValueError):
            Store(path)


def test_configure_transaction_rolls_back_partial_source_changes(settings):
    store = Store(settings.database)
    store.configure(settings)
    source = settings.sources[0]
    invalid = replace(source, name="Should roll back", questions=(replace(source.questions[0], text="Illegal edit"),))
    with pytest.raises(ValueError):
        store.configure(replace(settings, sources=(invalid,)))
    assert store.sources((source.source_id,))[0]["name"] == source.name


def test_disable_then_reenable_status(settings):
    store = Store(settings.database)
    source = settings.sources[0]
    store.configure(replace(settings, sources=(replace(source, enabled=False),)))
    assert store.sources((source.source_id,))[0]["status"] == "DISABLED"
    store.configure(settings)
    assert store.sources((source.source_id,))[0]["status"] == "CONNECTING"


def test_missing_config_fields_fail_cleanly(tmp_path):
    path = tmp_path / "invalid.json"
    path.write_text('{"schema_version":1}', encoding="utf-8")
    with pytest.raises(ValueError, match="configuration field"):
        load_config(path)
