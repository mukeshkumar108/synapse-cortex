"""Evaluation endpoints run real cognition but roll persistent effects back."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlmodel import select

from src.db import async_session_maker
from src.models.current_meaning import CurrentMeaning
from src.models.operational_state import (
    AgendaSnapshot,
    OperationalStatus,
    RecurringIntention,
    RecurringOccurrence,
)
from src.services import current_meaning_service as cm


async def _count(model) -> int:
    async with async_session_maker() as db:
        return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


async def test_evaluation_handover_rolls_back_agenda_and_occurrence_writes(async_client):
    now = datetime(2026, 9, 21, 9, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        db.add(RecurringIntention(
            honcho_workspace_id="ws-eval",
            honcho_session_id="session-eval",
            owner_peer_id="user-eval",
            honcho_message_id="message-1",
            candidate_key="daily-walk",
            canonical_key="daily-walk",
            title="Daily walk",
            cadence="daily",
            source_evidence="I take a walk every day",
            status=OperationalStatus.ACTIVE,
            started_at=(now - timedelta(days=7)).replace(tzinfo=None),
            created_at=now.replace(tzinfo=None),
            updated_at=now.replace(tzinfo=None),
        ))
        await db.commit()

    response = await async_client.post(
        "/v1/cortex/handover/evaluate",
        json={
            "workspace_id": "ws-eval",
            "session_id": "session-eval",
            "peer_id": "user-eval",
            "now": now.isoformat(),
            "timezone": "Europe/London",
            "turn_text": "morning",
        },
    )
    assert response.status_code == 200
    assert response.json()["evaluation"]["effects_rolled_back"] is True
    assert await _count(AgendaSnapshot) == 0
    assert await _count(RecurringOccurrence) == 0


async def test_evaluation_revise_returns_hypothesis_without_committing(async_client, monkeypatch):
    async def fake_interpreter(**_kwargs):
        return {
            "means": ["the cancelled walk still matters"],
            "unresolved": ["whether to reschedule"],
            "foreground_authority": "active",
            "evidence_span": "cancelled walk",
            "confidence": 0.9,
            "no_change": False,
        }

    monkeypatch.setattr(cm, "run_interpreter", fake_interpreter)
    response = await async_client.post(
        "/v1/cortex/current-meaning/revise-sync/evaluate",
        json={
            "workspace_id": "ws-eval",
            "session_id": "session-eval",
            "peer_id": "user-eval",
            "message_id": "message-eval-1",
            "turn_text": "the cancelled walk still matters",
            "recent_conversation": [],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["meaning_revision"] == "revised"
    assert body["trace"]["evaluation"] is True
    assert body["trace"]["effects_rolled_back"] is True
    assert body["trace"]["would_write_revision"] is True
    assert await _count(CurrentMeaning) == 0
