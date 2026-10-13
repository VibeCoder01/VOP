from copy import deepcopy
from typing import Mapping

from vop.contracts import (AnswerKind, InferenceRequest, InferenceResult, ProviderError,
                           QuestionAnswer, Status, result)


class MockInferenceEngine:
    """SYNTHETIC: returns configured values and never examines image pixels."""
    engine_version = "deterministic-mock-v1"
    synthetic = True

    def __init__(self, answers: Mapping[str, bool | str | float], engine_id: str = "mock",
                 supported: tuple[AnswerKind, ...] = tuple(AnswerKind)):
        self.engine_id = engine_id
        self.configured = dict(answers)
        self.supported = supported
        self.source_answers = {}

    def configure_source_answer(self, source_id, question_id, version, value):
        self.source_answers[(source_id, question_id, version)] = value

    def capabilities(self) -> tuple[AnswerKind, ...]:
        return self.supported

    def infer(self, request: InferenceRequest) -> InferenceResult:
        answers = []
        for q in request.questions:
            error = None
            source_key = (request.frame.source_id, q.question_id, q.version)
            value = self.source_answers.get(source_key, self.configured.get(q.question_id))
            if q.kind not in self.supported:
                error = ProviderError("unsupported_kind", "Mock capability unavailable", Status.UNSUPPORTED)
            elif q.question_id not in self.configured and source_key not in self.source_answers:
                error = ProviderError("mock_unconfigured", "No synthetic answer configured", Status.UNSUPPORTED)
            elif not (q.kind == AnswerKind.BINARY and isinstance(value, bool)
                      or q.kind == AnswerKind.CHOICE and value in dict(q.choices)
                      or q.kind == AnswerKind.ORDINAL and isinstance(value, (int, float))
                      and not isinstance(value, bool) and 0 <= value <= len(q.levels) - 1):
                error = ProviderError("mock_invalid", "Configured answer violates question contract")
            answers.append(QuestionAnswer(q.question_id, q.version, q.kind,
                                           error.status if error else Status.SUCCESS,
                                           None if error else value,
                                           {"synthetic": True, "configured": deepcopy(value)}, error=error))
        return result(request, self, tuple(answers), 0, {"synthetic": True, "label": "MOCK — no vision"})
