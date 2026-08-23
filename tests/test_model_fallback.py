import hashlib

import pytest

from src.services import model_retry
from src.services.turn_extractor import LLMExtractorProvider
from src.services.model_retry import ModelCallError


# ── Failure classification ──────────────────────────────────────────────────

def test_classify_status_kinds():
    assert model_retry.classify_status(401) == model_retry.AUTH
    assert model_retry.classify_status(403) == model_retry.AUTH
    assert model_retry.classify_status(429) == model_retry.RATE_LIMIT
    assert model_retry.classify_status(408) == model_retry.TIMEOUT
    assert model_retry.classify_status(500) == model_retry.SERVER_ERROR
    assert model_retry.classify_status(503) == model_retry.SERVER_ERROR
    assert model_retry.classify_status(400) == model_retry.BAD_REQUEST
    assert model_retry.classify_status(404) == model_retry.INVALID_MODEL


def test_retryable_vs_permanent():
    assert model_retry.is_retryable(model_retry.TIMEOUT)
    assert model_retry.is_retryable(model_retry.RATE_LIMIT)
    assert model_retry.is_retryable(model_retry.SERVER_ERROR)
    assert model_retry.is_retryable(model_retry.MALFORMED_JSON)
    assert not model_retry.is_retryable(model_retry.AUTH)
    assert not model_retry.is_retryable(model_retry.INVALID_MODEL)
    assert model_retry.is_permanent(model_retry.AUTH)
    assert model_retry.is_permanent(model_retry.INVALID_MODEL)


def test_backoff_monotonic_capped():
    values = [model_retry.backoff_seconds(i, jitter=0) for i in range(8)]
    for previous, current in zip(values, values[1:]):
        assert current >= previous
    assert values[-1] <= model_retry.BACKOFF_CAP_SECONDS


# ── Provider orchestration (retry then fallback model) ─────────────────────

class _StubClient:
    """Scripted _call_model: primary raises a classified error, fallback works."""

    def __init__(self, primary_error: ModelCallError, stage_json):
        self.primary_error = primary_error
        self.stage_json = stage_json  # callable(prompt) -> json

    def __call__(self, provider, model, prompt):
        if model == provider.models[0]:
            raise self.primary_error
        return self.stage_json(prompt)


def _stub(provider, stub):
    provider._call_model = lambda model, prompt: stub(provider, model, prompt)


def _chat_payloads():
    loose = {
        "observations": [{
            "description": "Wants a daily walk",
            "evidence_text": "I want to walk every day",
            "confidence": 0.9,
            "actor_peer_id": "user",
            "subject_refs": [],
            "temporal_language": "every day",
        }]
    }
    shape = {
        "candidates": [{
            "loose_observation_id": "o_" + hashlib.sha1(b"i want to walk every day").hexdigest()[:10],
            "operational_kind": "recurring_intention",
            "observation": "Daily walk",
            "canonical_title": "Daily walk",
            "confidence": 0.9,
            "cadence": "daily",
            "days_of_week": None,
        }]
    }

    def stage_json(prompt):
        if "USER TURN" in prompt:
            return loose
        return shape

    return stage_json


def _provider():
    provider = LLMExtractorProvider(
        api_key="test-key", model="primary-model", models=["fallback-model"],
    )
    return provider


def test_primary_success_uses_primary(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(model_retry, "sleep_backoff", lambda attempt: 0)
    stage = _chat_payloads()
    _stub(provider, lambda p, model, prompt: stage(prompt))
    out = provider._chat_json("USER TURN: x")
    assert out == stage("USER TURN: x")
    assert provider.last_model_used == "primary-model"
    assert provider.last_fallback_count == 0


def test_timeout_on_primary_falls_back_to_second_model(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(model_retry, "sleep_backoff", lambda attempt: 0)
    stage = _chat_payloads()
    err = ModelCallError(model_retry.TIMEOUT, model="primary-model")
    _stub(provider, _StubClient(err, stage))
    out = provider._chat_json("USER TURN: x")
    assert out == stage("USER TURN: x")
    assert provider.last_model_used == "fallback-model"
    assert provider.last_fallback_count == 1


def test_malformed_json_on_primary_falls_back(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(model_retry, "sleep_backoff", lambda attempt: 0)
    stage = _chat_payloads()
    err = ModelCallError(model_retry.MALFORMED_JSON, model="primary-model")
    _stub(provider, _StubClient(err, stage))
    assert provider._chat_json("USER TURN: x") == stage("USER TURN: x")
    assert provider.last_model_used == "fallback-model"


def test_all_models_exhausted_raises_classified(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(model_retry, "sleep_backoff", lambda attempt: 0)

    def always_broken(provider_, model, prompt):
        raise ModelCallError(model_retry.SERVER_ERROR, model=model)

    _stub(provider, always_broken)
    with pytest.raises(ModelCallError):
        provider._chat_json("USER TURN: x")
    assert provider.last_failure_kind is None  # kind set in extract, not here


def test_permanent_auth_failure_does_not_burn_fallback(monkeypatch):
    provider = _provider()
    calls = []

    def raiser(provider_, model, prompt):
        calls.append(model)
        raise ModelCallError(model_retry.AUTH, model=model)

    _stub(provider, raiser)
    with pytest.raises(ModelCallError) as exc:
        provider._chat_json("USER TURN: x")
    assert exc.value.kind == model_retry.AUTH
    # AUTH is permanent: only the first model is attempted, no fallback burn.
    assert calls == ["primary-model"]


def test_full_extract_survives_fallback_and_reports_backend(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(model_retry, "sleep_backoff", lambda attempt: 0)
    stage = _chat_payloads()
    err = ModelCallError(model_retry.CONNECTIVITY, model="primary-model")
    _stub(provider, _StubClient(err, stage))
    candidates = provider.extract("I want to walk every day", peer_id="user")
    assert len(candidates) == 1
    assert candidates[0].operational_kind == "recurring_intention"
    assert provider.last_backend == "model"
    assert provider.last_failure is None
    assert provider.last_model_used == "fallback-model"
    assert provider.last_fallback_count == 1  # per-stage metric (both stages fell back)


def test_config_status_includes_fallback_models(monkeypatch):
    monkeypatch.setenv("SYNAPSE_EXTRACTOR_PROVIDER", "model")
    monkeypatch.setenv("OPENROUTER_API_KEY", "x")
    monkeypatch.setenv("SYNAPSE_EXTRACTOR_MODEL", "primary/m")
    monkeypatch.setenv("SYNAPSE_EXTRACTOR_FALLBACK_MODELS", " google/gemma-4-31b-it , google/gemma-3-27b-it ")
    from src.services.turn_extractor import extractor_config_status
    status = extractor_config_status()
    assert status["degraded"] is False
    assert status["model"] == "primary/m"
    assert status["fallback_models"] == [
        "google/gemma-4-31b-it",
        "google/gemma-3-27b-it",
    ]