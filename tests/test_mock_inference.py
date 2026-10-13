from vop.contracts import AnswerKind, Status, infer
from vop.examples import MOCK_ANSWERS
from vop.inference.mock import MockInferenceEngine


def test_interchangeable_engines_same_caller_and_frame(request_frame):
    providers = [MockInferenceEngine(MOCK_ANSWERS, "mock-cpu"),
                 MockInferenceEngine({**MOCK_ANSWERS, "red_square": False}, "mock-alternate")]
    outcomes = [infer(engine, request_frame) for engine in providers]
    assert all(o.status == Status.SUCCESS and o.synthetic for o in outcomes)
    assert all(o.frame_id == request_frame.frame.frame_id and len(o.answers) == 3 for o in outcomes)
    assert [o.answers[0].value for o in outcomes] == [True, False]
    assert [o.engine_id for o in outcomes] == ["mock-cpu", "mock-alternate"]
    # Windows clock resolution can give an instant mock call identical timestamps.
    assert all(o.captured_at_utc == request_frame.frame.captured_at_utc <= o.processed_at_utc for o in outcomes)
    assert all(a.question_version == "1" for o in outcomes for a in o.answers)


def test_deterministic_answers_and_clear_label(request_frame):
    engine = MockInferenceEngine(MOCK_ANSWERS)
    first, second = infer(engine, request_frame), infer(engine, request_frame)
    assert first.answers == second.answers
    assert first.provider_raw["label"] == "MOCK — no vision"


def test_unsupported_and_unconfigured_not_negative(request_frame):
    outcome = infer(MockInferenceEngine({}, supported=(AnswerKind.BINARY,)), request_frame)
    assert outcome.status == Status.UNSUPPORTED
    assert all(a.value is None for a in outcome.answers)


def test_invalid_configured_value_not_negative(request_frame):
    outcome = infer(MockInferenceEngine({**MOCK_ANSWERS, "red_square": "no"}), request_frame)
    assert outcome.status == Status.MODEL_FAILURE
    assert outcome.answers[0].value is None
