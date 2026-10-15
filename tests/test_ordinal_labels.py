from dataclasses import replace

import pytest
from starlette.testclient import TestClient

from test_phase2_browser_storage import settings, login, OWNER
from vop.dashboard import answer_label
from vop.measurements import QueryPolicy
from vop.service import create_app


@pytest.mark.parametrize("value,expected", [
    (0, "Expected level: Low"), (1.0, "Expected level: Medium"),
    (2, "Expected level: High"), (0.25, "Expected level: Between Low and Medium"),
    (1.8, "Expected level: Between Medium and High"),
    (None, "Unknown"), (float("nan"), "Unknown"), (3, "Unknown"),
])
def test_expected_ordinal_position_is_named_without_rounding(value, expected):
    assert answer_label(value, ("Low", "Medium", "High")) == expected


def test_ordinal_labels_in_capture_overview_history_and_old_version(settings):
    app = create_app(settings, token=OWNER)
    store, pipeline = app.state.store, app.state.pipeline
    old = store.questions("synthetic-scene")[0]["spec"]
    question = store.edit_question("synthetic-scene", replace(old, kind="ordinal", levels=("Low <level>", "Medium", "High")),
                                   QueryPolicy(), expected_version=old.version)
    pipeline.engine.configure_source_answer("synthetic-scene", question.question_id, question.version, 0.25)
    with TestClient(app) as client:
        csrf = login(client)
        response = client.post("/ui/sources/synthetic-scene/capture", data={"csrf": csrf})
        assert response.status_code == 200
        label = "Expected level: Between Low &lt;level&gt; and Medium"
        assert label in response.text
        observation = store.observations()[0]
        assert observation["answer"]["value"] == 0.25
        for path in ("/", "/observations", "/ui/observations/" + observation["id"]):
            assert label in client.get(path).text
        store.edit_question("synthetic-scene", replace(question, levels=("New low", "New medium", "New high")),
                            QueryPolicy(), expected_version=question.version)
        assert label in client.get("/observations").text
        assert label in client.get("/ui/observations/" + observation["id"]).text
