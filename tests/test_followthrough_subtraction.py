from datetime import datetime, timedelta
from uuid import uuid4

from src.db import async_session_maker
from src.models.operational_state import TurnStamp
from src.services.followthrough_service import compute_admission
from src.services.agenda_service import extract_candidates


async def test_answered_ask_remains_durable_but_leaves_foreground():
    asked_at = datetime(2026, 9, 1, 17, 34, 34)
    occurrence_id = str(uuid4())
    async with async_session_maker() as db:
        db.add(TurnStamp(
            honcho_workspace_id="ws",
            owner_peer_id="user_1",
            honcho_message_id="reply-after-ask",
            turn_at=asked_at + timedelta(minutes=11),
        ))
        await db.commit()

        result = await compute_admission(
            db,
            workspace_id="ws",
            owner_peer_id="user_1",
            agenda_items=[{
                "what": "Two walks per day",
                "pressure": 0.75,
                "occurrence_id": occurrence_id,
                "next_move": "ask status",
            }],
            packet={
                "intelligence_brief": {"daypart": "evening", "user_day": "2026-09-01"},
                "recurring_intentions": [{
                    "occurrence_id": occurrence_id,
                    "ask_count": 1,
                    "asked_at": asked_at.isoformat(),
                }],
            },
            now=asked_at + timedelta(minutes=11),
            timezone_str="Europe/London",
        )

    assert result["owed"] == []
    assert result["optional"][0]["followup_state"] == "acknowledged_this_sitting"


def test_due_task_enters_agenda_but_future_task_does_not():
    candidates = extract_candidates({
        "commitments": [
            {"source_object_id": "tidy", "title": "Micro-tidying", "state": "reminder_due"},
            {"source_object_id": "walk", "title": "Morning walk", "state": "scheduled"},
        ],
    }, now=datetime(2026, 9, 1, 19, 0), timezone_str="Europe/London")
    assert [item["what"] for item in candidates] == ["Micro-tidying"]
    assert candidates[0]["pressure"] == 0.7


async def test_arrival_home_reactivates_event_suppressed_checkin():
    async with async_session_maker() as db:
        result = await compute_admission(
            db, workspace_id="ws", owner_peer_id="user_1",
            agenda_items=[{
                "what": "Micro-tidying", "pressure": 0.7,
                "status": "waiting_event", "next_move": "reactivate when I get home",
            }],
            packet={}, now=datetime(2026, 9, 1, 19, 15),
            timezone_str="Europe/London", current_turn="I'm home now — just through the door.",
        )
    assert result["owed"][0]["what"] == "Micro-tidying"
    assert result["owed"][0]["followup_state"] == "outstanding"


async def test_unanswered_ask_remains_foreground_eligible():
    asked_at = datetime(2026, 9, 1, 17, 34, 34)
    occurrence_id = str(uuid4())
    async with async_session_maker() as db:
        db.add(TurnStamp(
            honcho_workspace_id="ws",
            owner_peer_id="user_1",
            honcho_message_id="ask-triggering-turn",
            turn_at=asked_at - timedelta(seconds=1),
        ))
        await db.commit()

        result = await compute_admission(
            db,
            workspace_id="ws",
            owner_peer_id="user_1",
            agenda_items=[{
                "what": "Daily step goal",
                "pressure": 0.75,
                "occurrence_id": occurrence_id,
            }],
            packet={
                "intelligence_brief": {"daypart": "evening", "user_day": "2026-09-01"},
                "recurring_intentions": [{
                    "occurrence_id": occurrence_id,
                    "ask_count": 1,
                    "asked_at": asked_at,
                }],
            },
            now=asked_at,
            timezone_str="Europe/London",
        )

    assert result["owed"][0]["followup_state"] == "awaiting_answer"


async def test_supplied_progress_closes_ask_and_duplicate_pressure_collapses():
    asked_at = datetime(2026, 9, 1, 17, 34, 34)
    occurrence_id = str(uuid4())
    async with async_session_maker() as db:
        result = await compute_admission(
            db, workspace_id="ws", owner_peer_id="user_1",
            agenda_items=[
                {"what": "Daily 10k step goal", "pressure": 0.75, "occurrence_id": occurrence_id},
                {"what": "Daily 10k step goal", "pressure": 0.75, "occurrence_id": occurrence_id},
            ],
            packet={
                "recurring_intentions": [{"occurrence_id": occurrence_id, "ask_count": 1, "asked_at": asked_at.isoformat()}],
                "recent_progress": [{"title": "10k step goal", "amount": 4000, "unit": "steps", "evidence": "I've done about 4,000 steps and I'm walking now"}],
            },
            now=asked_at + timedelta(minutes=5), timezone_str="Europe/London",
        )
    assert result["owed"] == []
    assert len(result["optional"]) == 1
    assert result["optional"][0]["followup_state"] == "acknowledged_this_sitting"
