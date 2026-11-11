"""Recurrence classification: the model states it, the guard only validates the model's own fields.

Nothing here reads the person's words. Whether "it's been happening every single day" is a problem's
frequency rather than a routine, or "we talk everyday" an observed pattern, is the model's judgement under
the extraction prompt (checked against the live model in scripts/check_recurrence_live.py, not in unit tests).
"""

from src.services.turn_extractor import RecurrenceSemantics


def _apply(raw: dict | None = None, kind: str = "recurring_intention") -> dict:
    raw = dict(raw or {})
    raw.setdefault("operational_kind", kind)
    raw.setdefault("cadence", "daily")
    notes = RecurrenceSemantics.apply(raw, kind, "", "")
    return {"raw": raw, "notes": notes}


def test_a_valid_model_classification_is_kept():
    for kind in ("recurring_action", "recurring_ritual", "adherence_action", "measurable_goal", "observed_pattern"):
        out = _apply({"recurrence_semantic_type": kind})
        assert out["raw"]["recurrence_semantic_type"] == kind
        assert out["notes"] == []


def test_an_invalid_classification_is_discarded_and_noted():
    out = _apply({"recurrence_semantic_type": "lifestyle_thing"})
    assert "discarded_invalid_recurrence_semantic_type" in out["notes"]
    assert out["raw"]["recurrence_semantic_type"] == "recurring_action"


def test_structured_targets_make_a_measurable_goal_when_the_model_gave_no_type():
    out = _apply({"target_amount": 10000.0, "target_unit": "steps"})
    assert out["raw"]["recurrence_semantic_type"] == "measurable_goal"


def test_a_missing_type_is_flagged_not_silently_invented():
    out = _apply({})
    assert "recurrence_type_not_stated_defaulted_to_action" in out["notes"]


def test_the_model_classification_is_never_overridden_by_the_wording():
    # The same evidence that used to trigger keyword demotion ("keeps happening", "we talk") must not change what the model said.
    out = _apply({"recurrence_semantic_type": "recurring_action", "cadence_evidence_text": "the build keeps breaking every single day"})
    assert out["raw"]["operational_kind"] == "recurring_intention"
    assert out["raw"]["recurrence_semantic_type"] == "recurring_action"


def test_non_recurrence_kinds_are_untouched():
    raw = {"operational_kind": "durable_objective", "cadence": "daily"}
    assert RecurrenceSemantics.apply(raw, "durable_objective") == []
    assert "recurrence_semantic_type" not in raw
