import hashlib

import pytest

from src.schemas.candidate import ExtractionCandidate, LooseObservation
from src.services.turn_extractor import LLMExtractorProvider

BASE = dict(candidate_key="c", observation="obs", source_start=0, source_end=2)


# ── ExtractionCandidate schema boundary ─────────────────────────────────────

def test_explicit_days_of_week_null_normalized_to_empty_list():
    cand = ExtractionCandidate(**{**BASE, "days_of_week": None})
    assert cand.days_of_week == []


def test_omitted_days_of_week_remains_empty_list():
    cand = ExtractionCandidate(**BASE)
    assert cand.days_of_week == []


def test_valid_days_of_week_unchanged():
    cand = ExtractionCandidate(**{**BASE, "days_of_week": [0, 2, 4]})
    assert cand.days_of_week == [0, 2, 4]


@pytest.mark.parametrize("bad", ["daily", {"monday": 0}, 42, 3.5])
def test_malformed_days_of_week_still_rejected(bad):
    with pytest.raises(Exception):
        ExtractionCandidate(**{**BASE, "days_of_week": bad})


def test_explicit_validation_notes_null_normalized_to_empty_list():
    cand = ExtractionCandidate(**{**BASE, "validation_notes": None})
    assert cand.validation_notes == []


def test_boolean_flags_null_normalized_to_false():
    cand = ExtractionCandidate(
        **{**BASE, "is_negated": None, "is_hypothetical": None, "is_reported_speech": None,
           "is_quoted": None, "is_sarcastic": None}
    )
    assert cand.is_negated is False
    assert cand.is_hypothetical is False
    assert cand.is_reported_speech is False
    assert cand.is_quoted is False
    assert cand.is_sarcastic is False


def test_boolean_flags_omitted_default_false():
    cand = ExtractionCandidate(**BASE)
    assert cand.is_negated is False
    assert cand.is_sarcastic is False


def test_extractor_version_null_normalized_to_default():
    cand = ExtractionCandidate(**{**BASE, "extractor_version": None})
    assert cand.extractor_version == "rules-v2"


def test_confidence_null_normalized_to_schema_default():
    cand = ExtractionCandidate(**{**BASE, "confidence": None})
    assert cand.confidence == 1.0


# ── LooseObservation schema boundary ────────────────────────────────────────

def test_loose_observation_subject_refs_null_normalized():
    obs = LooseObservation(
        observation_id="o1",
        description="some description text here",
        evidence_text="evidence",
        confidence=0.5,
        subject_refs=None,
    )
    assert obs.subject_refs == []


def test_loose_observation_subject_refs_omitted_default_global_empty():
    obs = LooseObservation(
        observation_id="o1",
        description="some description text here",
        evidence_text="evidence",
        confidence=0.5,
    )
    assert obs.subject_refs == []


def test_loose_observation_subject_refs_valid_unchanged():
    obs = LooseObservation(
        observation_id="o1",
        description="some description text here",
        evidence_text="evidence",
        confidence=0.5,
        subject_refs=["ashley", "morgan"],
    )
    assert obs.subject_refs == ["ashley", "morgan"]


def test_loose_observation_subject_refs_malformed_rejected():
    with pytest.raises(Exception):
        LooseObservation(
            observation_id="o1",
            description="some description text here",
            evidence_text="evidence",
            confidence=0.5,
            subject_refs="ashley",
        )


# ── Parsing path: model output dict -> typed candidate ─────────────────────

def _monkeypatch_llm(monkeypatch, loose_payload, shaped_payload):
    provider = LLMExtractorProvider(api_url="http://unused.local", api_key="unused", model="unused-model")
    calls = []

    def fake_chat_json(prompt):
        calls.append(prompt)
        if len(calls) == 1:
            return loose_payload
        return shaped_payload

    monkeypatch.setattr(provider, "_chat_json", fake_chat_json)
    return provider, calls


def test_model_explicit_null_days_of_week_survives_parsing(monkeypatch):
    text = "I want to get a proper walk in every day, ideally about an hour."
    evidence = "I want to get a proper walk in every day"
    obs_id = f"o_{hashlib.sha1(evidence.lower().encode()).hexdigest()[:10]}"
    loose = {
        "observations": [{
            "observation_id": obs_id,
            "description": "Wants a proper daily walk of about an hour",
            "evidence_text": evidence,
            "source_start": 0,
            "source_end": len(evidence),
            "confidence": 0.9,
            "actor_peer_id": "user",
            "subject_refs": [],
            "temporal_language": "every day",
        }]
    }
    shaped = {
        "candidates": [{
            "loose_observation_id": obs_id,
            "operational_kind": "recurring_intention",
            "canonical_title": "Daily walk",
            "observation": "Wants a daily walk",
            "raw_evidence": evidence,
            "confidence": 0.9,
            "actor_peer_id": "user",
            "subject_peer_id": "user",
            "temporal_phrase": "every day",
            "expectation_type_hint": None,
            "cadence": "daily",
            "interval_days": None,
            "days_of_week": None,
            "preferred_window": None,
            "target_amount": None,
            "target_unit": None,
            "progress_amount": None,
            "progress_unit": None,
            "expiry_phrase": None,
            "open_loop_hint": None,
            "suppression_hint": None,
            "resolution_hint": None,
        }]
    }
    provider, _ = _monkeypatch_llm(monkeypatch, loose, shaped)
    candidates = provider.extract(text, peer_id="user")
    assert len(candidates) == 1
    assert candidates[0].operational_kind == "recurring_intention"
    assert candidates[0].days_of_week == []
    assert provider.last_backend == "model"


def test_model_null_subject_refs_in_loose_stage_survives_parsing(monkeypatch):
    text = "I sent three applications today but I still need to keep applying."
    evidence = "I still need to keep applying"
    obs_id = f"o_{hashlib.sha1(evidence.lower().encode()).hexdigest()[:10]}"
    loose = {
        "observations": [{
            "observation_id": obs_id,
            "description": "Still needs to keep applying for jobs",
            "evidence_text": evidence,
            "source_start": text.index(evidence),
            "source_end": text.index(evidence) + len(evidence),
            "confidence": 0.9,
            "actor_peer_id": "user",
            "subject_refs": None,
            "temporal_language": None,
        }]
    }
    shaped = {
        "candidates": [{
            "loose_observation_id": obs_id,
            "operational_kind": "durable_objective",
            "canonical_title": "Keep applying for jobs",
            "observation": "Keep applying for jobs",
            "raw_evidence": evidence,
            "confidence": 0.9,
            "actor_peer_id": "user",
            "subject_peer_id": "user",
            "temporal_phrase": None,
            "expectation_type_hint": None,
            "cadence": None,
            "interval_days": None,
            "days_of_week": None,
            "preferred_window": None,
            "target_amount": None,
            "target_unit": None,
            "progress_amount": None,
            "progress_unit": None,
            "expiry_phrase": None,
            "open_loop_hint": None,
            "suppression_hint": None,
            "resolution_hint": None,
        }]
    }
    provider, _ = _monkeypatch_llm(monkeypatch, loose, shaped)
    candidates = provider.extract(text, peer_id="user")
    assert len(candidates) == 1
    assert candidates[0].operational_kind == "durable_objective"
    assert candidates[0].days_of_week == []
    assert provider.last_backend == "model"