from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import (ObjectiveProgress, OccurrenceStatus,
    OperationalStatus, RecurringIntention, RecurringOccurrence)
from src.schemas.candidate import ExtractionCandidate
from src.services.operational_state_service import OperationalStateService
from src.services.turn_extractor import LLMExtractorProvider


class StubTwoStageProvider(LLMExtractorProvider):
    def __init__(self, responses):
        super().__init__(api_key="test-key", model="test-fast-model")
        self.responses = iter(responses)

    def _chat_json(self, prompt):
        return next(self.responses)


def test_loose_semantic_observation_does_not_require_verbatim_description():
    text = "I want to get a proper walk in every day, ideally about an hour."
    provider = StubTwoStageProvider([
        {"observations": [{"description": "User wants a daily walking routine lasting about one hour",
            "evidence_text": text, "confidence": .94, "actor_peer_id": "user",
            "subject_refs": [], "temporal_language": "every day"}]},
        {"candidates": [{"loose_observation_id": "o_" + __import__("hashlib").sha1(text.lower().encode()).hexdigest()[:10],
            "operational_kind": "recurring_intention", "observation": "Daily one-hour walk",
            "canonical_title": "Walk", "actor_peer_id": "user", "subject_peer_id": "user",
            "confidence": .93, "cadence": "daily", "days_of_week": [],
            "target_amount": 1, "target_unit": "hour"}]},
    ])
    candidates = provider.extract(text, peer_id="user")
    assert len(candidates) == 1
    assert candidates[0].observation == "Daily one-hour walk"
    assert candidates[0].raw_evidence == text
    assert candidates[0].cadence == "daily"
    assert provider.last_backend == "model"


def test_model_failure_is_observable_and_does_not_silently_use_rules():
    provider = LLMExtractorProvider(api_key="", fallback_on_error=False)
    assert provider.extract("I need to call the dentist tomorrow") == []
    assert provider.last_backend == "failed"
    assert provider.last_failure == "credentials_unavailable"


@pytest.mark.asyncio
async def test_recurrence_completion_progress_and_expiry_are_lifecycle_safe():
    service = OperationalStateService()
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        recurrence = ExtractionCandidate(candidate_key="walk-create", observation="Daily walk",
            raw_evidence="I want to walk every day", confidence=.95,
            operational_kind="recurring_intention", canonical_title="Walk",
            cadence="daily", target_amount=1, target_unit="hour")
        created = await service.apply(db, workspace_id="ws", session_id="s", message_id="m1",
            peer_id="u", candidate=recurrence, now=now, timezone_str="Europe/London")
        assert created["mutation"] == "recurrence_created"

        completed = ExtractionCandidate(candidate_key="walk-done", observation="Completed walk",
            raw_evidence="I did my walk today btw", confidence=.96,
            operational_kind="completion", canonical_title="Walk", target_key="walk")
        result = await service.apply(db, workspace_id="ws", session_id="s", message_id="m2",
            peer_id="u", candidate=completed, now=now, timezone_str="Europe/London")
        assert result["mutation"] == "occurrence_completed"
        routine = (await db.execute(select(RecurringIntention))).scalar_one()
        occurrence = (await db.execute(select(RecurringOccurrence))).scalar_one()
        assert routine.status == OperationalStatus.ACTIVE
        assert occurrence.status == OccurrenceStatus.COMPLETED

        objective = Expectation(honcho_workspace_id="ws", honcho_session_id="s",
            honcho_message_id="objective", candidate_key="jobs", subject_peer_id="u",
            expectation_type=ExpectationType.USER_COMMITMENT, title="Apply for jobs",
            summary="Keep applying for jobs", outcome_state=OutcomeState.UNKNOWN)
        db.add(objective); await db.commit(); await db.refresh(objective)
        progress = ExtractionCandidate(candidate_key="jobs-progress", observation="Sent three applications",
            raw_evidence="I sent three job applications today but I still need to keep applying",
            confidence=.97, operational_kind="progress", canonical_title="Apply for jobs",
            target_key="apply jobs", progress_amount=3, progress_unit="applications")
        await service.apply(db, workspace_id="ws", session_id="s", message_id="m3",
            peer_id="u", candidate=progress, now=now, timezone_str="Europe/London")
        await db.refresh(objective)
        assert objective.outcome_state == OutcomeState.UNKNOWN
        assert (await db.execute(select(ObjectiveProgress))).scalar_one().expectation_id == objective.id

        loop = OpenLoop(honcho_workspace_id="ws", honcho_session_id="s", honcho_message_id="m4",
            candidate_key="ashley", title="Check how Ashley's event went", summary="Temporary follow-up",
            expires_at=now.replace(tzinfo=None) - timedelta(minutes=1))
        db.add(loop); await db.commit()
        assert await service.sweep(db, workspace_id="ws", now=now) == 1
        await db.refresh(loop)
        assert loop.status == OpenLoopStatus.EXPIRED
