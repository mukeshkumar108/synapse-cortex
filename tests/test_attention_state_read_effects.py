"""Lifecycle effects of an AttentionState read, and the evaluate arm's rollback.

Retained and re-targeted from the previous agent's reuse-parity research test:
the packet-reuse-by-handover-preview measurement was retired together with the
handover endpoint (docs/CORTEX_CUTOVER.md); what remains load-bearing is that
reading attention applies deterministic lifecycle transitions (expiry, stale
clarification dismissal, daily occurrence slot) and creates NO surface
receipts, while the evaluate endpoint rolls everything back.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlmodel import select

from src.db import async_session_maker
from src.models.clarification import (
    ClarificationCandidate,
    ClarificationStatus,
    ClarificationType,
)
from src.models.derived_signal import DerivedSignal
from src.models.operational_state import (
    AgendaSnapshot,
    OperationalStatus,
    RecurringIntention,
    RecurringOccurrence,
)
from src.models.suppression import Suppression, SuppressionStatus


async def _count(model) -> int:
    async with async_session_maker() as db:
        return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


async def test_attention_read_applies_lifecycle_transitions_and_evaluate_rolls_back(
    async_client,
):
    """The read endpoint commits lifecycle transitions; the evaluate endpoint
    runs the same compiler inside a rollback session and leaves no trace."""
    now = datetime(2026, 9, 26, 9, 0, tzinfo=timezone.utc)
    workspace_id = "ws-reuse"
    session_id = "session-reuse"
    peer_id = "peer-reuse"
    async with async_session_maker() as db:
        db.add(Suppression(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            owner_peer_id=peer_id,
            honcho_message_id="message-suppression",
            candidate_key="expired-topic",
            topic_or_entity="old topic",
            reason="temporary",
            suppressed_until=(now - timedelta(minutes=1)).replace(tzinfo=None),
            status=SuppressionStatus.ACTIVE,
        ))
        db.add(RecurringIntention(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            owner_peer_id=peer_id,
            honcho_message_id="message-routine",
            candidate_key="daily-walk",
            canonical_key="daily-walk",
            title="Daily walk",
            cadence="daily",
            source_evidence="I walk every day",
            status=OperationalStatus.ACTIVE,
            started_at=(now - timedelta(days=7)).replace(tzinfo=None),
            created_at=(now - timedelta(days=7)).replace(tzinfo=None),
            updated_at=now.replace(tzinfo=None),
        ))
        db.add(ClarificationCandidate(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            owner_peer_id=peer_id,
            honcho_message_id="message-clarification",
            candidate_key="stale-question",
            clarification_type=ClarificationType.UNCLEAR_TARGET,
            description="Which walk did you mean?",
            status=ClarificationStatus.PENDING,
            created_at=(now - timedelta(days=8)).replace(tzinfo=None),
            updated_at=(now - timedelta(days=8)).replace(tzinfo=None),
        ))
        await db.commit()

    params = {
        "workspace_id": workspace_id,
        "session_id": session_id,
        "peer_id": peer_id,
        "now": now.isoformat(),
        "timezone": "Europe/London",
    }
    # evaluate arm first: identical compilation, zero persisted effect
    evaluated = await async_client.get("/v1/cortex/attention-state/evaluate", params=params)
    assert evaluated.status_code == 200
    assert evaluated.json()["evaluation"]["effects_rolled_back"] is True
    async with async_session_maker() as db:
        assert (await db.execute(select(Suppression))).scalar_one().status == SuppressionStatus.ACTIVE
        assert (await db.execute(select(ClarificationCandidate))).scalar_one().status == ClarificationStatus.PENDING
    assert await _count(RecurringOccurrence) == 0

    attention_response = await async_client.get(
        "/v1/cortex/attention-state", params=params
    )
    assert attention_response.status_code == 200

    async with async_session_maker() as db:
        suppression = (await db.execute(select(Suppression))).scalar_one()
        clarification = (
            await db.execute(select(ClarificationCandidate))
        ).scalar_one()
        assert suppression.status == SuppressionStatus.EXPIRED
        assert clarification.status == ClarificationStatus.DISMISSED
    assert await _count(RecurringOccurrence) == 1
    # Eligibility checks do not consume a surface receipt during packet reads.
    assert await _count(DerivedSignal) == 0
    assert await _count(AgendaSnapshot) == 0
