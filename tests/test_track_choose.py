"""track->choose: the agenda's ranked judgement must reach AttentionState's
follow-through ledger (optional list keeps rank order + why/next_move), and
proactive eligibility must speak the agenda's status vocabulary."""
import pytest

from src.db import async_session_maker
from src.services.followthrough_service import compute_admission
from src.services.initiative_service import _high_pressure_items
from tests.cortex_fixtures import NOW, USER, WS


@pytest.mark.asyncio
async def test_optional_follows_agenda_rank_and_keeps_judgement():
    agenda = [
        {"what": "Update on Matt's condition", "pressure": 0.45, "status": "unresolved",
         "why": "unresolved 42h", "next_move": "check back naturally",
         "item_key": "loop:loop-matt", "candidate_id": "open_loop:loop-matt",
         "candidate_version": "v2", "horizon": "day"},
        {"what": "Low value thread", "pressure": 0.27, "status": "unresolved",
         "why": "open thread", "next_move": "return naturally",
         "item_key": "loop:loop-low", "candidate_id": "open_loop:loop-low",
         "candidate_version": "v1", "horizon": "day"},
    ]
    packet = {"window": {"daypart": "morning", "user_day": "2026-09-28"}, "recurring_intentions": [],
              "recent_progress": []}
    async with async_session_maker() as db:
        admission = await compute_admission(
            db, workspace_id=WS, owner_peer_id=USER, agenda_items=agenda, packet=packet,
            now=NOW, timezone_str="Europe/London")
    optional = admission["optional"]
    assert [o["what"] for o in optional] == ["Update on Matt's condition", "Low value thread"]
    first = optional[0]
    assert first["why"] == "unresolved 42h" and first["next_move"] == "check back naturally"
    assert first["candidate_id"] == "open_loop:loop-matt" and first["candidate_version"] == "v2"
    assert admission["scene"]["time_of_day"] == "morning"


def test_initiative_sees_live_agenda_statuses():
    items = [
        {"what": "overdue task", "pressure": 0.85, "status": "outstanding"},
        {"what": "waiting thread", "pressure": 0.7, "status": "waiting_event"},
        {"what": "plain thread", "pressure": 0.7, "status": "unresolved"},
        {"what": "settled", "pressure": 0.9, "status": "resolved"},
        {"what": "later", "pressure": 0.9, "status": "scheduled_for_later"},
    ]
    got = _high_pressure_items(items, 0.6)
    assert {i["what"] for i in got} == {"overdue task", "waiting thread", "plain thread"}
