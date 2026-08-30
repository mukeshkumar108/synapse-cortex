"""Workstream 1: recurrence semantic semantics — deterministic guard.

Realistic messy-language regression cases covering: recurring action,
recurring ritual, adherence action, durable measurable goal, observed
pattern, problem-frequency one-off objectives, and hedged habits.
"""

from src.services.turn_extractor import RecurrenceSemantics


def _apply(text: str, evidence: str | None = None, raw: dict | None = None) -> dict:
    raw = dict(raw or {})
    raw.setdefault("operational_kind", "recurring_intention")
    raw.setdefault("cadence", "daily")
    notes = RecurrenceSemantics.apply(raw, "recurring_intention", text, (evidence or text).lower())
    return {"raw": raw, "notes": notes}


# --- one-off objective wrongly shaped as recurrence (founder case) ---------

def test_audio_bug_problem_frequency_is_demoted_to_objective():
    # Real founder evidence: "it's been happening every single day" describes
    # the BUG, not a user practice.
    text = ("yes, I need to fix this audio transcription bug because it's been "
            "happening every single day, so you need to remind me keep top of me")
    out = _apply(text)
    assert out["raw"]["operational_kind"] == "durable_objective"
    assert out["raw"]["cadence"] is None
    assert "demoted_problem_frequency_recurrence_to_objective" in out["notes"]


def test_keeps_happening_is_demoted():
    out = _apply("the sync error keeps happening every day, I must fix it")
    assert out["raw"]["operational_kind"] == "durable_objective"


# --- observed patterns are not commitments --------------------------------

def test_mutual_talk_pattern_is_observed_pattern():
    # Real founder evidence: "we talk everyday obviously..."
    out = _apply("we talk everyday obviously")
    assert out["raw"]["operational_kind"] == "recurring_intention"
    assert out["raw"]["recurrence_semantic_type"] == "observed_pattern"


def test_hedged_most_mornings_is_observed_pattern_not_commitment():
    out = _apply("I try to walk most mornings before work")
    assert out["raw"]["recurrence_semantic_type"] == "observed_pattern"
    assert out["raw"]["confidence"] <= 0.75


# --- clean semantic types ---------------------------------------------------

def test_explicit_want_every_morning_is_recurring_action():
    out = _apply("I want to walk every morning")
    assert out["raw"]["recurrence_semantic_type"] == "recurring_action"


def test_prayers_every_day_is_recurring_ritual():
    out = _apply("I want to do morning and evening prayers every day")
    assert out["raw"]["recurrence_semantic_type"] == "recurring_ritual"


def test_medication_is_adherence_action():
    out = _apply("I take my medication every morning")
    assert out["raw"]["recurrence_semantic_type"] == "adherence_action"


def test_step_goal_target_is_measurable_goal():
    out = _apply("my goal is at least 10k steps per day",
                 raw={"target_amount": 10000.0, "target_unit": "steps"})
    assert out["raw"]["recurrence_semantic_type"] == "measurable_goal"


# --- model proposals are validated, not trusted -----------------------------

def test_model_proposed_type_is_accepted_when_valid():
    out = _apply("I meditate every day", raw={"recurrence_semantic_type": "recurring_ritual"})
    assert out["raw"]["recurrence_semantic_type"] == "recurring_ritual"


def test_invalid_model_proposal_falls_back_deterministically():
    out = _apply("I run every morning", raw={"recurrence_semantic_type": "lifestyle_thing"})
    assert "discarded_invalid_recurrence_semantic_type" in out["notes"]
    assert out["raw"]["recurrence_semantic_type"] == "recurring_action"


def test_problem_frequency_wins_over_model_proposal():
    out = _apply("the build keeps breaking every single day and I need to sort it",
                 raw={"recurrence_semantic_type": "recurring_action"})
    assert out["raw"]["operational_kind"] == "durable_objective"
    assert out["raw"]["recurrence_semantic_type"] is None


def test_non_recurrence_kinds_are_untouched():
    raw = {"operational_kind": "durable_objective", "cadence": "daily"}
    notes = RecurrenceSemantics.apply(raw, "durable_objective", "we talk everyday", "we talk everyday")
    assert notes == []
    assert "recurrence_semantic_type" not in raw
