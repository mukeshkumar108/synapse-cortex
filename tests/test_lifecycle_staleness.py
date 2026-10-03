"""Cortex must not emit impossible lifecycle state (real shapes from a 2026-10-03 account audit):
a 40-day-old "on the bus, arriving in 5 minutes" expectation read 'not due'; an elapsed 'take a shower now'
stayed an active goal; an app task a month overdue stayed 'overdue' forever."""
from datetime import datetime, timedelta
from uuid import uuid4

import pytest

from src.models.expectation import Expectation, ExpectationType, OutcomeState, TemporalState
from src.services.expectation_engine import derive_temporal_state
from src.services.matter_service import describe

NOW = datetime(2026, 10, 3, 17, 0, 0)


def exp(*, phrase=None, created_hours_ago=1.0, start=None, end=None, deadline=None, outcome=OutcomeState.UNKNOWN):
    created = NOW - timedelta(hours=created_hours_ago)
    return Expectation(id=uuid4(), honcho_workspace_id="w", honcho_session_id="s", honcho_message_id="m", subject_peer_id="u",
                       expectation_type=ExpectationType.USER_INTENTION, title="t", summary="s", raw_temporal_phrase=phrase,
                       anchor_timezone="Europe/London", expected_window_start=start, expected_window_end=end, hard_deadline_at=deadline,
                       outcome_state=outcome, created_at=created, updated_at=created)


def test_a_relative_phrase_with_no_anchor_is_live_only_near_the_moment_it_was_said():
    assert derive_temporal_state(exp(phrase="in about 5 mins", created_hours_ago=0.2), NOW) == TemporalState.NOT_DUE
    assert derive_temporal_state(exp(phrase="in about 5 mins", created_hours_ago=960), NOW) == TemporalState.WINDOW_ELAPSED


def test_an_open_ended_plan_with_no_time_phrase_is_not_time_bound_and_stays_open():
    assert derive_temporal_state(exp(created_hours_ago=2), NOW) == TemporalState.WINDOW_OPEN
    assert derive_temporal_state(exp(created_hours_ago=893), NOW) == TemporalState.WINDOW_OPEN      # "decide which flat to rent"


def test_explicit_windows_and_deadlines_are_unaffected_by_the_staleness_rule():
    future = exp(phrase="tomorrow", created_hours_ago=100, start=NOW + timedelta(hours=5), end=NOW + timedelta(hours=9))
    assert derive_temporal_state(future, NOW) == TemporalState.NOT_DUE
    assert derive_temporal_state(exp(deadline=NOW - timedelta(hours=1), created_hours_ago=100), NOW) == TemporalState.DEADLINE_PASSED


def test_a_lapsed_expectation_no_longer_keeps_its_matter_live():
    stale = describe("expectation", exp(phrase="now", created_hours_ago=893), NOW)
    fresh = describe("expectation", exp(phrase="now", created_hours_ago=2), NOW)
    assert stale is not None and stale.live is False and stale.terminal is False       # rests as dormant, never claimed fulfilled
    assert fresh is not None and fresh.live is True


def test_a_recently_elapsed_window_still_counts_as_live_until_the_grace_passes():
    just_elapsed = exp(phrase="tonight", created_hours_ago=20, start=NOW - timedelta(hours=18), end=NOW - timedelta(hours=10))
    assert describe("expectation", just_elapsed, NOW).live is True                      # an unresolved plan from last night is still a thing to follow up


@pytest.mark.asyncio
async def test_an_app_task_a_month_overdue_is_lapsed_not_overdue(async_client):
    from tests.test_object_state import get_packet, iso, object_payload, post_object
    await post_object(async_client, object_payload(due_at=iso(days_ahead=-31), reminder_windows=[]))
    late = await get_packet(async_client, now=iso(days_ahead=0))
    commitments = late.json()["commitments"]
    assert commitments and commitments[0]["state"] == "lapsed"
    assert not any(item.get("type") == "task_due" and item.get("status") == "overdue" for item in late.json()["eligible"])
