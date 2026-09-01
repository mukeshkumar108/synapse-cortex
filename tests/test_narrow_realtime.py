"""Deterministic validation tests for the narrow real-time contract (no model)."""
from datetime import datetime, timezone

import pytest

from src.services.narrow_realtime import NarrowRealtimeExtractor, NarrowDecision

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
TZ = "Europe/London"
TEXT = "going to bed now. tomorrow i want you to remind me to go out for a walk during the day"


@pytest.fixture
def extractor():
    ex = NarrowRealtimeExtractor.__new__(NarrowRealtimeExtractor)  # no model provider
    from src.services.temporal_grounding import TemporalGrounding
    ex.grounder = TemporalGrounding()
    return ex


def test_valid_reminder_create_grounds(extractor):
    d = extractor.validate(
        {
            "decision": "create",
            "kind": "reminder",
            "title": "Daytime walk",
            "temporal_phrase": "tomorrow",
            "evidence_text": "tomorrow i want you to remind me to go out for a walk",
            "confidence": 0.9,
        },
        TEXT,
        now=NOW,
        timezone_str=TZ,
    )
    assert d.valid and d.decision == "create" and d.kind == "reminder"


def test_invalid_evidence_rejected(extractor):
    d = extractor.validate(
        {
            "decision": "create",
            "kind": "reminder",
            "title": "Daytime walk",
            "temporal_phrase": "tomorrow",
            "evidence_text": "please remind me about the walk sometime soon",
            "confidence": 0.9,
        },
        TEXT,
        now=NOW,
        timezone_str=TZ,
    )
    assert not d.valid and d.decision == "none"
    assert any("verbatim" in n for n in d.validation_notes)


def test_event_without_grounding_rejected(extractor):
    d = extractor.validate(
        {
            "decision": "create",
            "kind": "event",
            "title": "Something vague",
            "temporal_phrase": "someday eventually",
            "evidence_text": "going to bed now",
            "confidence": 0.9,
        },
        TEXT,
        now=NOW,
        timezone_str=TZ,
    )
    assert not d.valid and d.decision == "none"


def test_event_with_grounding_valid(extractor):
    text = "We're going to Oxford on Sunday morning"
    d = extractor.validate(
        {
            "decision": "create",
            "kind": "event",
            "title": "Trip to Oxford",
            "temporal_phrase": "Sunday morning",
            "evidence_text": "going to Oxford on Sunday morning",
            "confidence": 0.9,
        },
        text,
        now=NOW,
        timezone_str=TZ,
    )
    assert d.valid and d.decision == "create" and d.kind == "event"


def test_transition_requires_target(extractor):
    d = extractor.validate(
        {
            "decision": "complete",
            "evidence_text": "I did my walk today",
            "confidence": 0.9,
        },
        "I did my walk today",
        now=NOW,
        timezone_str=TZ,
    )
    assert not d.valid and d.decision == "none"
    assert any("target_key" in n for n in d.validation_notes)


def test_valid_completion_with_target(extractor):
    d = extractor.validate(
        {
            "decision": "complete",
            "target_key": "walk",
            "canonical_title": "Daily walk",
            "evidence_text": "I did my walk today",
            "confidence": 0.9,
        },
        "I did my walk today",
        now=NOW,
        timezone_str=TZ,
    )
    assert d.valid and d.decision == "complete"


def test_unknown_decision_rejected(extractor):
    d = extractor.validate({"decision": "discover_goals", "evidence_text": "x"}, TEXT)
    assert not d.valid and d.decision == "none"


def test_reschedule_requires_new_phrase(extractor):
    d = extractor.validate(
        {
            "decision": "reschedule",
            "target_key": "dentist",
            "evidence_text": "move my dentist appointment",
            "confidence": 0.9,
        },
        "can you move my dentist appointment",
        now=NOW,
        timezone_str=TZ,
    )
    assert not d.valid


def test_none_passthrough(extractor):
    d = extractor.validate({"decision": "none", "confidence": 0.5}, TEXT)
    assert d.valid and d.decision == "none"


def test_to_candidate_maps_to_existing_lanes(extractor):
    d = extractor.validate(
        {
            "decision": "create",
            "kind": "reminder",
            "title": "Daytime walk",
            "temporal_phrase": "tomorrow",
            "evidence_text": "remind me to go out for a walk",
            "confidence": 0.9,
        },
        TEXT,
        now=NOW,
        timezone_str=TZ,
    )
    cand = extractor.to_candidate(d)
    assert cand is not None
    assert cand.expectation_type_hint == "user_commitment"
    assert cand.reminder_request is True
    assert cand.extractor_version == "narrow-realtime-v1"

    d2 = extractor.validate(
        {
            "decision": "cancel",
            "target_key": "oxford",
            "canonical_title": "Trip to Oxford",
            "evidence_text": "I have to give it a miss",
            "confidence": 0.9,
        },
        "Yeah, I have to give it a miss",
        now=NOW,
        timezone_str=TZ,
    )
    cand2 = extractor.to_candidate(d2)
    assert cand2 is not None
    assert cand2.resolution_hint["action"] == "cancelled"
    assert cand2.target_key == "oxford" or cand2.resolution_hint["target_key"] == "oxford"
