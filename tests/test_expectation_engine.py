from datetime import datetime, timedelta, timezone
from uuid import uuid4
from src.models.expectation import Expectation, ExpectationType, OutcomeState, TemporalState
from src.services.expectation_engine import (
    derive_temporal_state,
    is_followup_eligible,
    derive_expectation_read_model,
)


def test_elapsed_window_unknown_outcome_is_window_elapsed_not_violated():
    exp = Expectation(
        id=uuid4(),
        honcho_workspace_id="ws_1",
        honcho_session_id="sess_1",
        honcho_message_id=101,
        subject_peer_id="mukesh",
        expectation_type=ExpectationType.USER_INTENTION,
        title="Test Sophie initiative changes",
        summary="User plans to test tonight",
        raw_temporal_phrase="tonight",
        anchor_timezone="Europe/London",
        expected_window_start=datetime(2026, 8, 11, 17, 0, 0),
        expected_window_end=datetime(2026, 8, 11, 22, 59, 59),
        outcome_state=OutcomeState.UNKNOWN,
    )

    # Next morning 09:00 AM UTC
    now_next_morning = datetime(2026, 8, 12, 8, 0, 0)

    t_state = derive_temporal_state(exp, now_next_morning)
    assert t_state == TemporalState.WINDOW_ELAPSED
    assert t_state != "violated"  # CRITICAL SPEC RULE

    read_model = derive_expectation_read_model(exp, now_next_morning)
    assert read_model["temporal_state"] == "window_elapsed"
    assert read_model["outcome_state"] == "unknown"
    assert read_model["followup_eligible"] is True
    assert read_model["expected_window_label"] == "last night"


def test_fulfilled_expectation_ineligible_for_followup():
    exp = Expectation(
        id=uuid4(),
        honcho_workspace_id="ws_1",
        honcho_session_id="sess_1",
        honcho_message_id=102,
        subject_peer_id="mukesh",
        expectation_type=ExpectationType.USER_INTENTION,
        title="Test Sophie initiative changes",
        summary="User plans to test tonight",
        expected_window_end=datetime(2026, 8, 11, 22, 59, 59),
        outcome_state=OutcomeState.FULFILLED,
    )

    now = datetime(2026, 8, 12, 8, 0, 0)
    read_model = derive_expectation_read_model(exp, now)
    assert read_model["temporal_state"] == "window_elapsed"
    assert read_model["outcome_state"] == "fulfilled"
    assert read_model["followup_eligible"] is False


def test_hard_deadline_passed():
    exp = Expectation(
        id=uuid4(),
        honcho_workspace_id="ws_1",
        honcho_session_id="sess_1",
        honcho_message_id=103,
        subject_peer_id="mukesh",
        expectation_type=ExpectationType.USER_COMMITMENT,
        title="Submit architecture report",
        summary="Submit by 5pm Friday",
        hard_deadline_at=datetime(2026, 8, 14, 16, 0, 0),
        outcome_state=OutcomeState.UNKNOWN,
    )

    # After 5pm Friday
    now = datetime(2026, 8, 14, 18, 0, 0)
    read_model = derive_expectation_read_model(exp, now)
    assert read_model["temporal_state"] == "deadline_passed"
    assert read_model["outcome_state"] == "unknown"
    assert read_model["followup_eligible"] is True


def test_aware_now_is_converted_to_utc_before_comparison():
    exp = Expectation(
        honcho_workspace_id="ws_1",
        honcho_session_id="sess_1",
        honcho_message_id=104,
        subject_peer_id="mukesh",
        title="Call James",
        summary="Call James this afternoon",
        expected_window_start=datetime(2026, 8, 11, 14, 0),
        expected_window_end=datetime(2026, 8, 11, 16, 0),
    )

    now = datetime(2026, 8, 11, 16, 30, tzinfo=timezone(timedelta(hours=1)))
    assert derive_temporal_state(exp, now) == TemporalState.WINDOW_OPEN
