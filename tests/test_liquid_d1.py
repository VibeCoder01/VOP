from copy import deepcopy
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from vop.contracts import Status, infer
from vop.inference.liquid_d1 import (CHECKPOINT_REVISION, LiquidD1InferenceAdapter,
                                    normalise, provider_questions)


def native_response():
    return {"answers": {
        "red_square": {"type": "noul", "noul": 0.8, "extension": "keep me"},
        "background": {"type": "choice", "choice": "white", "confidence": 0.9,
                       "probabilities": {"white": 0.9, "black": 0.1}},
        "brightness": {"type": "score", "score": 1.7, "confidence": 0.8,
                       "probabilities": {"0": 0.1, "1": 0.1, "2": 0.8},
                       "legend": {"0": "Dark", "1": "Medium", "2": "Bright"}}},
        "usage": {"input_tokens": 42, "output_tokens": 0}, "extension": ["preserved"]}


def fake_engine(response):
    engine = LiquidD1InferenceAdapter()
    engine.model = SimpleNamespace(system_one=lambda *args, **kwargs: response)
    return engine


def test_official_schema_mapping_and_single_image_batch(request_frame):
    seen = []
    raw = native_response()
    engine = LiquidD1InferenceAdapter()
    def system_one(state, questions, *, images):
        seen.append((state, questions, len(images), images[0].size))
        return raw
    engine.model = SimpleNamespace(system_one=system_one)
    output = infer(engine, request_frame)
    assert output.status == Status.SUCCESS and not output.synthetic
    assert [a.value for a in output.answers] == [True, "white", 1.7]
    assert seen[0][0] is None and seen[0][2:] == (1, (384, 256))
    mapped = seen[0][1]
    assert [v["type"] for v in mapped.values()] == ["noul", "choice", "score"]
    assert mapped["background"]["criteria"] == {"white": "White background", "black": "Black background"}
    assert mapped["brightness"]["criteria"] == ["Dark", "Medium", "Bright"]
    assert output.provider_raw == raw and output.usage == raw["usage"]
    raw["extension"].append("mutation")
    assert output.provider_raw["extension"] == ["preserved"]
    assert not output.answers[0].calibrated and output.answers[0].threshold_used == 0.5


@pytest.mark.parametrize("raw", [None, {}, {"type": "noul"}, {"type": "choice", "noul": 0.1},
                                {"type": "noul", "noul": False}, {"type": "noul", "noul": float("nan")},
                                {"type": "noul", "noul": -0.1}, {"type": "noul", "noul": 1.2}])
def test_malformed_binary_never_negative(request_frame, raw):
    answer = normalise(request_frame.questions[0], raw)
    assert answer.status == Status.MODEL_FAILURE and answer.value is None


def test_valid_negative_requires_success(request_frame):
    answer = normalise(request_frame.questions[0], {"type": "noul", "noul": 0.1})
    assert answer.status == Status.SUCCESS and answer.value is False


@pytest.mark.parametrize("field,value", [("choice", "purple"), ("confidence", None),
                                         ("probabilities", {"white": 0.2, "black": 0.2})])
def test_malformed_choice(request_frame, field, value):
    raw = native_response()["answers"]["background"]
    raw[field] = value
    answer = normalise(request_frame.questions[1], raw)
    assert answer.status == Status.MODEL_FAILURE and answer.raw_provider_fields == raw


@pytest.mark.parametrize("field,value", [("score", 3), ("score", 1.2), ("legend", {}),
                                         ("confidence", 1.2), ("probabilities", {"0": 1})])
def test_malformed_ordinal(request_frame, field, value):
    raw = native_response()["answers"]["brightness"]
    raw[field] = value
    answer = normalise(request_frame.questions[2], raw)
    assert answer.status == Status.MODEL_FAILURE and answer.value is None


def test_explicit_unsupported(request_frame):
    answer = normalise(request_frame.questions[0], {"type": "unsupported", "reason": "cannot answer"})
    assert answer.status == Status.UNSUPPORTED and answer.value is None


@pytest.mark.parametrize("raw", [None, [], {}, {"answers": {}, "usage": {}},
                                {"answers": native_response()["answers"], "usage": {"input_tokens": 1, "output_tokens": 2}}])
def test_malformed_top_level_kept(request_frame, raw):
    output = infer(fake_engine(raw), request_frame)
    assert output.status == Status.MODEL_FAILURE
    assert output.provider_raw == raw and all(a.value is None for a in output.answers)


def test_optional_load_requires_both_consents():
    for kwargs in ({}, {"allow_model_download": True}, {"accept_model_risk": True}):
        with pytest.raises(Exception, match="consent_required"):
            LiquidD1InferenceAdapter().load(**kwargs)


def test_exact_snapshot_cpu_fp32_and_local_tokenizer_path(monkeypatch, tmp_path):
    calls = []
    snapshot = str(tmp_path / CHECKPOINT_REVISION)
    def download(model_id, **kwargs):
        calls.append(("download", model_id, kwargs))
        return snapshot
    class Model:
        def to(self, device):
            calls.append(("device", device))
            return self
        def eval(self):
            return self
    def load(path, **kwargs):
        calls.append(("load", path, kwargs))
        return Model()
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(float32="FP32"))
    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=download))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(AutoModel=SimpleNamespace(from_pretrained=load)))
    engine = LiquidD1InferenceAdapter()
    engine.load(allow_model_download=True, accept_model_risk=True, cache_dir=tmp_path)
    assert calls[0][1] == "LiquidAI/d1-3B" and calls[0][2]["revision"] == CHECKPOINT_REVISION
    assert calls[1][1] == snapshot
    assert calls[1][2] == {"revision": CHECKPOINT_REVISION, "code_revision": CHECKPOINT_REVISION,
                           "trust_remote_code": True, "local_files_only": True, "dtype": "FP32"}
    assert calls[2] == ("device", "cpu")
