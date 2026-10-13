from dataclasses import replace
from datetime import datetime, timedelta

import pytest

from vop.contracts import AnswerKind, InferenceRequest, QuestionAnswer, QuestionSpec, Status, utcnow


def test_request_has_bytes_no_required_path(request_frame):
    assert request_frame.frame.payload.startswith(b"\x89PNG")
    assert not hasattr(request_frame.frame, "path")
    assert request_frame.frame.source_id != "mock"
    assert request_frame.frame.captured_at_utc.utcoffset() == timedelta(0)


def test_duplicate_questions_rejected(request_frame):
    with pytest.raises(ValueError):
        InferenceRequest(request_frame.frame, (request_frame.questions[0],) * 2)


@pytest.mark.parametrize("kwargs", [
    {"text": " "}, {"version": ""}, {"threshold": float("nan")}, {"threshold": 2},
    {"kind": AnswerKind.CHOICE}, {"kind": AnswerKind.CHOICE, "choices": (("x", "X"), ("x", "Y"))},
    {"kind": AnswerKind.ORDINAL, "levels": ("one",)},
    {"kind": AnswerKind.ORDINAL, "levels": tuple("x" for _ in range(11))},
    {"kind": "unknown"},
])
def test_invalid_question(kwargs):
    spec = {"question_id": "q", "version": "1", "text": "Question?", "kind": AnswerKind.BINARY}
    spec.update(kwargs)
    with pytest.raises(ValueError):
        QuestionSpec(**spec)


def test_failed_answer_cannot_assert_negative():
    with pytest.raises(ValueError):
        QuestionAnswer("q", "1", AnswerKind.BINARY, Status.MODEL_FAILURE, False)


def test_naive_deadline_and_frame_rejected(request_frame):
    with pytest.raises(ValueError):
        replace(request_frame, deadline_utc=datetime(2026, 1, 1))
    with pytest.raises(ValueError):
        replace(request_frame.frame, captured_at_utc=datetime(2026, 1, 1))


def test_empty_request_rejected(request_frame):
    with pytest.raises(ValueError):
        replace(request_frame, questions=())
