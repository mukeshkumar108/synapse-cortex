from datetime import datetime, timedelta, timezone
from typing import Dict, Any
from src.models.expectation import Expectation, TemporalState, OutcomeState


# A relative phrase ("in 5 mins", "now", "later") is only meaningful near the moment it was said. With no explicit window
# to anchor it, it used to read "not due" forever: a 40-day-old "on the bus, arriving in 5 minutes" stayed an active
# expectation. Past this age it is history (the window elapsed unobserved). Open-ended plans with NO time phrase (a decision
# to make, a goal) are not time-bound and stay open.
UNANCHORED_STALE_HOURS = 36


def derive_temporal_state(expectation: Expectation, now: datetime) -> TemporalState:
    """
    Pure deterministic function calculating temporal state relative to `now`.
    
    Rule:
    - If hard_deadline_at set and now > hard_deadline_at -> DEADLINE_PASSED
    - Else if hard_deadline_at set and now >= hard_deadline_at - 2 hours -> DEADLINE_APPROACHING
    - Else if expected_window_end set and now > expected_window_end -> WINDOW_ELAPSED
    - Else if expected_window_start set and expected_window_end set and start <= now <= end -> WINDOW_OPEN
    - Else if expected_window_start set and now < expected_window_start -> NOT_DUE
    - Else if ungrounded temporal phrase -> NOT_DUE (waiting for anchor)
    - Else -> WINDOW_OPEN
    """
    # Ensure naive UTC for comparison if now is naive UTC
    if now.tzinfo is not None:
        now_cmp = now.astimezone(timezone.utc).replace(tzinfo=None)
    else:
        now_cmp = now

    hard_deadline = expectation.hard_deadline_at
    if hard_deadline and hard_deadline.tzinfo is not None:
        hard_deadline = hard_deadline.astimezone(timezone.utc).replace(tzinfo=None)

    window_end = expectation.expected_window_end
    if window_end and window_end.tzinfo is not None:
        window_end = window_end.astimezone(timezone.utc).replace(tzinfo=None)

    window_start = expectation.expected_window_start
    if window_start and window_start.tzinfo is not None:
        window_start = window_start.astimezone(timezone.utc).replace(tzinfo=None)

    # 1. Hard deadline evaluation
    if hard_deadline:
        if now_cmp > hard_deadline:
            return TemporalState.DEADLINE_PASSED
        if hard_deadline - timedelta(hours=2) <= now_cmp <= hard_deadline:
            return TemporalState.DEADLINE_APPROACHING

    # 2. Window elapsed evaluation
    if window_end and now_cmp > window_end:
        return TemporalState.WINDOW_ELAPSED

    # 3. Window open evaluation
    if window_start and window_end and window_start <= now_cmp <= window_end:
        return TemporalState.WINDOW_OPEN

    # 4. Not due evaluation
    if window_start and now_cmp < window_start:
        return TemporalState.NOT_DUE

    # 5. Ungrounded relational phrase / open-ended plan: only live near the moment it was said.
    created = expectation.created_at
    if created is not None and created.tzinfo is not None:
        created = created.astimezone(timezone.utc).replace(tzinfo=None)
    stale = bool(created and expectation.raw_temporal_phrase and not window_start and not window_end and not hard_deadline
                 and (now_cmp - created) > timedelta(hours=UNANCHORED_STALE_HOURS))
    if stale:
        return TemporalState.WINDOW_ELAPSED
    if expectation.raw_temporal_phrase and not window_start and not hard_deadline:
        return TemporalState.NOT_DUE

    return TemporalState.WINDOW_OPEN


def is_followup_eligible(temporal_state: TemporalState, outcome_state: OutcomeState) -> bool:
    """
    Check follow-up eligibility based on dual-dimension state.
    Only eligible if temporal window elapsed or hard deadline passed AND outcome is still UNKNOWN.
    """
    return (
        temporal_state in (TemporalState.WINDOW_ELAPSED, TemporalState.DEADLINE_PASSED)
        and outcome_state == OutcomeState.UNKNOWN
    )


def derive_expectation_read_model(expectation: Expectation, now: datetime) -> Dict[str, Any]:
    """
    Computes complete read model representation for an expectation item.
    Does NOT mutate the database.
    """
    temporal_state = derive_temporal_state(expectation, now)
    eligible = is_followup_eligible(temporal_state, expectation.outcome_state)

    if expectation.outcome_state != OutcomeState.UNKNOWN:
        reason = f"outcome_{expectation.outcome_state.value}"
    elif temporal_state == TemporalState.DEADLINE_PASSED:
        reason = "hard_deadline_passed"
    elif temporal_state == TemporalState.WINDOW_ELAPSED:
        reason = "expected_window_elapsed"
    elif temporal_state == TemporalState.DEADLINE_APPROACHING:
        reason = "deadline_approaching"
    elif temporal_state == TemporalState.WINDOW_OPEN:
        reason = "window_currently_open"
    else:
        reason = "not_due_yet"

    # Human readable label formatting for expected window
    expected_window_label = expectation.raw_temporal_phrase or "recently"
    if temporal_state == TemporalState.WINDOW_ELAPSED:
        if expectation.raw_temporal_phrase in ("tonight", "today"):
            expected_window_label = "last night"
        elif expectation.raw_temporal_phrase == "tomorrow":
            expected_window_label = "yesterday"

    return {
        "id": expectation.id,
        "title": expectation.title,
        "summary": expectation.summary,
        "expected_window_label": expected_window_label,
        "temporal_state": temporal_state.value,
        "outcome_state": expectation.outcome_state.value,
        "followup_eligible": eligible,
        "reason": reason,
        "honcho_message_id": expectation.honcho_message_id,
        "expectation_type": expectation.expectation_type.value,
    }
