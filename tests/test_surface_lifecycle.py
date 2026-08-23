from datetime import datetime, timedelta, timezone

import pytest

from src.db import async_session_maker
from src.models.clarification import ClarificationCandidate, ClarificationStatus, ClarificationType
from src.models.operational_state import OperationalStatus, RecurringIntention
from src.services.surface_lifecycle import SurfaceRegistry


@pytest.mark.asyncio
async def test_surface_registry_cooldown_max_and_resolve():
    registry = SurfaceRegistry()
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        key = "curiosity:test"
        assert await registry.mark(db, workspace_id="w", session_id="s", message_id="m", key=key, now=now) == "allowed"
        assert await registry.mark(db, workspace_id="w", session_id="s", message_id="m", key=key, now=now) == "cooldown"
        later = now + timedelta(hours=2)
        assert await registry.mark(db, workspace_id="w", session_id="s", message_id="m", key=key, now=later) == "allowed"
        far = later + timedelta(hours=2)
        assert await registry.mark(db, workspace_id="w", session_id="s", message_id="m", key=key, now=far) == "allowed"
        exhausted = far + timedelta(hours=2)
        assert await registry.mark(db, workspace_id="w", session_id="s", message_id="m", key=key, now=exhausted) == "maxed"
        await registry.resolve(db, workspace_id="w", session_id="s", message_id="m", key=key, now=exhausted)
        again = exhausted + timedelta(hours=2)
        assert await registry.mark(db, workspace_id="w", session_id="s", message_id="m", key=key, now=again) == "allowed"


@pytest.mark.asyncio
async def test_curiosity_not_repeated_under_cooldown_and_extinguished_after_max(async_client):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    recurrence = RecurringIntention(
        honcho_workspace_id="ws_sc", honcho_session_id="s_sc", honcho_message_id="m1",
        candidate_key="r", canonical_key="morning-walk", title="Morning walk", cadence="daily",
        source_evidence="I walk each morning", status=OperationalStatus.ACTIVE,
        started_at=(now - timedelta(days=5)).replace(tzinfo=None),
        created_at=now.replace(tzinfo=None), updated_at=now.replace(tzinfo=None),
    )
    async with async_session_maker() as db:
        db.add(recurrence)
        await db.commit()

    params = {"workspace_id": "ws_sc", "session_id": "s_sc",
              "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London"}
    first = (await async_client.get("/v1/cortex/attention-packet", params=params)).json()
    assert any(c["type"] == "unobserved_routine" and c["topic"] == "Morning walk" for c in first["curiosity"])

    # Same instant again -> cooldown -> not repeated in this compile.
    second = (await async_client.get("/v1/cortex/attention-packet", params=params)).json()
    assert not any(c["type"] == "unobserved_routine" and c["topic"] == "Morning walk" for c in second["curiosity"])

    # A couple of hours later (past cooldown), remains available but budgeted.
    params2 = {**params, "now": "2026-08-22T14:00:00Z"}
    third = (await async_client.get("/v1/cortex/attention-packet", params=params2)).json()
    assert any(c["type"] == "unobserved_routine" and c["topic"] == "Morning walk" for c in third["curiosity"])


@pytest.mark.asyncio
async def test_stale_clarification_is_dismissed_and_not_surfaced(async_client):
    created = datetime(2026, 8, 10, 12, tzinfo=timezone.utc)  # 12 days before surface
    async with async_session_maker() as db:
        db.add(ClarificationCandidate(
            honcho_workspace_id="ws_stale", honcho_session_id="s_stale",
            honcho_message_id="m1", candidate_key="c",
            clarification_type=ClarificationType.UNCLEAR_TARGET,
            description="which follow-up did you mean?",
            status=ClarificationStatus.PENDING,
            created_at=created.replace(tzinfo=None),
            updated_at=created.replace(tzinfo=None),
        ))
        await db.commit()
    packet = (await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_stale", "session_id": "s_stale",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })).json()
    assert not any(c["type"] == "clarification" for c in packet["curiosity"])
    from sqlmodel import select
    async with async_session_maker() as db:
        row = (await db.execute(select(ClarificationCandidate))).scalar_one()
        assert row.status == ClarificationStatus.DISMISSED