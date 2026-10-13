from dataclasses import replace
from datetime import timedelta

import pytest

from vop.contracts import Status, infer, utcnow
from vop.inference.liquid_d1 import LiquidD1InferenceAdapter
from vop.inference.mock import MockInferenceEngine


@pytest.mark.parametrize("exception,status", [(RuntimeError("boom"), Status.MODEL_FAILURE),
                                             (MemoryError("OOM"), Status.MODEL_FAILURE),
                                             (TimeoutError("late"), Status.TIMEOUT)])
def test_provider_exception_never_negative(request_frame, exception, status):
    class Broken(MockInferenceEngine):
        def infer(self, request):
            raise exception
    output = infer(Broken({}), request_frame)
    assert output.status == status
    assert all(a.value is None and a.error for a in output.answers)


def test_expired_request_does_not_invoke_provider(request_frame):
    class Forbidden(MockInferenceEngine):
        def infer(self, request):
            raise AssertionError("Expired request must never reach provider")
    output = infer(Forbidden({}), replace(request_frame, deadline_utc=utcnow() - timedelta(seconds=1)))
    assert output.status == Status.TIMEOUT and output.error.code == "deadline"


def test_missing_model_no_negative(request_frame):
    output = infer(LiquidD1InferenceAdapter(), request_frame)
    assert output.status == Status.MODEL_FAILURE
    assert output.error.code == "model_not_loaded" and all(a.value is None for a in output.answers)
