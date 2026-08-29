"""Behavioural tests for the controlled historical repair pass (CP2).

Known live pollution shapes: stale shower/life-admin expectations, narration
promoted to expectation, one-off work turned into a daily recurrence.
Evidence is never deleted; only derived state is repaired."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.models.operational_state import (
    RecurringIntention, RecurringOccurrence, OperationalStatus,
)
from src.services.historical_repair import HistoricalRepairService

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=timezone.utc)
WS = "ws-repair"


async def seed(session):
    stale_shower = Expectation(
        honcho_workspace_id=WS, honcho_session_id="s1",
        honcho_message_id="m-1", subject_peer_id="user-1",
        expectation_type=ExpectationType.USER_INTENTION,
        title="Take a shower now", summary="take a shower now",
        raw_temporal_phrase="now",
        expected_window_start=NOW - timedelta(hours=50),
        expected_window_end=NOW - timedelta(hours=49),
    )
    narration = Expectation(
        honcho_workspace_id=WS, honcho_session_id="s1",
        honcho_message_id="m-2", subject_peer_id="user-1",
        expectation_type=ExpectationType.USER_INTENTION,
        title="Ordered a flat white", summary="ordered a flat white",
        raw_temporal_phrase=None,
    )
    dup_a = Expectation(
        honcho_workspace_id=WS, honcho_session_id="s1",
        honcho_message_id="m-3", subject_peer_id="user-1",
        expectation_type=ExpectationType.USER_INTENTION,
        title="Fix audio transcription bug",
        summary="fix the audio transcription bug",
        raw_temporal_phrase="today",
    )
    dup_b = Expectation(
        honcho_workspace_id=WS, honcho_session_id="s1",
        honcho_message_id="m-4", subject_peer_id="user-1",
        expectation_type=ExpectationType.USER_INTENTION,
        title="fix audio transcription bug",
        summary="fix the audio transcription bug",
        raw_temporal_phrase="today",
    )
    recurrence = RecurringIntention(
        honcho_workspace_id=WS, honcho_session_id="s1",
        honcho_message_id="m-3", title="Fix audio transcription bug",
        cadence="daily", status=OperationalStatus.ACTIVE,
        candidate_key="c_recur_test", canonical_key="fix-audio-transcription-bug",
        source_evidence="I really need to fix the audio transcription bug every day",
    )
    session.add_all([stale_shower, narration, dup_a, dup_b, recurrence])
    await session.commit()
    return stale_shower, narration, dup_a, dup_b, recurrence


@pytest.mark.asyncio
async def test_repair_classifies_without_deleting_and_applies_derived_state():
    async with async_session_maker() as session:
        stale_shower, narration, dup_a, dup_b, recurrence = await seed(session)

        service = HistoricalRepairService()
        report = await service.classify_and_repair(
            session, workspace_id=WS, now=NOW, apply=True,
        )

        classifications = {a.target_id: a.classification for a in report.actions}
        # Narration was flagged, not deleted.
        assert classifications[str(narration.id)] == "incorrectly_typed"
        # Duplicate flagged; the earliest copy stays canonical.
        assert classifications[str(dup_b.id)] == "duplicate"
        assert classifications[str(dup_a.id)] != "duplicate"
        # Shower: narration promoted to expectation -> re-extraction candidate
        # (narration classification takes precedence over staleness).
        assert classifications[str(stale_shower.id)] == "incorrectly_typed"
        # One-off turned daily recurrence flagged for cadence verification.
        assert classifications[str(recurrence.id)] == "reextract_candidate"

        await session.refresh(dup_b)
        assert dup_b.superseded_by_id == dup_a.id
        assert dup_b.outcome_state == OutcomeState.SUPERSEDED
        # Evidence rows still exist.
        rows = (await session.execute(
            select(Expectation).where(
                Expectation.honcho_workspace_id == WS)
        )).scalars().all()
        assert len(rows) == 4

        # Dry-run after repair: duplicate is gone, nothing else mutates.
        report2 = await service.classify_and_repair(
            session, workspace_id=WS, now=NOW, apply=False,
        )
        assert all(
            a.action != "supersede" for a in report2.actions
        )
