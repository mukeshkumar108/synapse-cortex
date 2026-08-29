from datetime import datetime, timedelta, timezone

from src.models.expectation import Expectation, ExpectationType
from src.services.cortex_packet_service import CortexPacketService


def expectation(now: datetime, *, hours_ago: int = 0) -> Expectation:
    end = now - timedelta(hours=hours_ago)
    return Expectation(
        honcho_workspace_id="ws",
        honcho_session_id="session",
        honcho_message_id=f"message-{hours_ago}",
        subject_peer_id="user",
        expectation_type=ExpectationType.USER_INTENTION,
        title=f"Expectation {hours_ago}",
        summary="Grounded expectation",
        raw_temporal_phrase="today",
        expected_window_start=end - timedelta(hours=1),
        expected_window_end=end,
    )


def test_stale_unknown_expectation_is_reviewable_not_foreground():
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    stale = expectation(now, hours_ago=72)
    packet = {
        "active_expectations": [{
            "id": str(stale.id),
            "temporal_state": "window_elapsed",
        }],
        "commitments": [], "events": [], "recurring_intentions": [],
        "commitment_candidates": [], "open_loops": [], "sophie_attention": [],
    }
    brief = CortexPacketService._compile_intelligence_brief(
        packet, expectations=[stale], now=now, timezone_str="Europe/London"
    )
    assert brief["horizons"]["unresolved"] == []
    assert brief["horizons"]["review_needed"][0]["id"] == str(stale.id)


def test_recent_unknown_expectation_preserves_uncertainty_for_a_natural_check():
    now = datetime(2026, 8, 29, 12, tzinfo=timezone.utc)
    recent = expectation(now, hours_ago=3)
    packet = {
        "active_expectations": [{
            "id": str(recent.id),
            "temporal_state": "window_elapsed",
        }],
        "commitments": [], "events": [], "recurring_intentions": [],
        "commitment_candidates": [], "open_loops": [], "sophie_attention": [],
    }
    brief = CortexPacketService._compile_intelligence_brief(
        packet, expectations=[recent], now=now, timezone_str="Europe/London"
    )
    item = brief["horizons"]["unresolved"][0]
    assert item["suggested_move"] == "ask_outcome_if_natural"
    assert "unknown" in item["uncertainty"].lower()


def test_recurring_window_moves_from_now_to_uncertain_after_window():
    packet = {
        "active_expectations": [], "commitments": [], "events": [],
        "commitment_candidates": [], "open_loops": [], "sophie_attention": [],
        "recurring_intentions": [{
            "id": "walk", "title": "Morning walk", "preferred_window": "morning",
            "occurrence_status": "pending", "user_day": "2026-08-29",
        }],
    }
    morning = CortexPacketService._compile_intelligence_brief(
        packet, expectations=[],
        now=datetime(2026, 8, 29, 8, tzinfo=timezone.utc),
        timezone_str="Europe/London",
    )
    evening = CortexPacketService._compile_intelligence_brief(
        packet, expectations=[],
        now=datetime(2026, 8, 29, 18, tzinfo=timezone.utc),
        timezone_str="Europe/London",
    )
    assert morning["horizons"]["now"][0]["id"] == "walk"
    assert evening["horizons"]["unresolved"][0]["id"] == "walk"
    assert "not proof" in evening["horizons"]["unresolved"][0]["uncertainty"]
