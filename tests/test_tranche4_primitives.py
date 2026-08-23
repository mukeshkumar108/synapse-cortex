import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import (AttentionCandidate, AttentionCandidateKind,
    AttentionCandidateStatus)
from src.models.operational_state import (OccurrenceStatus, OperationalStatus,
    RecurringIntention, RecurringOccurrence)
from src.models.suppression import Suppression, SuppressionStatus
from src.services.cortex_packet_service import CortexPacketService
from src.services.lifecycle_service import LifecycleService
from src.services.sleep_signal import SleepSignalTracker
from src.services.turn_extractor import LLMExtractorProvider


class StubTwoStage(LLMExtractorProvider):
    def __init__(self, responses):
        super().__init__(api_key="test-key", model="test-model")
        self.responses = iter(responses)

    def _chat_json(self, prompt):
        return next(self.responses)


def _obs_id(evidence: str) -> str:
    return f"o_{hashlib.sha1(evidence.lower().encode()).hexdigest()[:10]}"


# ── Sleep derived-state ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sleep_tracker_bed_then_wake_short_sleep():
    tracker = SleepSignalTracker()
    now = datetime(2026, 8, 22, 2, 56, tzinfo=timezone.utc)
    async with async_session_maker() as db:
        first = await tracker.observe(db, workspace_id="ws", session_id="s", message_id="m1",
            text="I'm heading to bed now, goodnight", now=now)
        assert first is not None
        assert "bed_time" in first
        wake = datetime(2026, 8, 22, 9, 38, tzinfo=timezone.utc)
        second = await tracker.observe(db, workspace_id="ws", session_id="s", message_id="m2",
            text="just woke up", now=wake)
        assert second is not None
        assert second["signal"] == "short_sleep_likely"
        assert second["hours"] < 7
        read = await tracker.read(db, workspace_id="ws", session_id="s")
        assert read["signal"] == "short_sleep_likely"
        assert read["confidence"] >= 0.7


@pytest.mark.asyncio
async def test_sleep_tracker_ignores_non_sleep_text():
    tracker = SleepSignalTracker()
    async with async_session_maker() as db:
        result = await tracker.observe(db, workspace_id="ws", session_id="s", message_id="m1",
            text="I need to get back into exercise", now=datetime(2026, 8, 22, 12, tzinfo=timezone.utc))
        assert result is None
        assert await tracker.read(db, workspace_id="ws", session_id="s") is None


@pytest.mark.asyncio
async def test_sleep_signal_in_packet_when_available(async_client):
    from src.models.derived_signal import DerivedSignal, DerivedSignalKind
    payload = {
        "bed_time": datetime(2026, 8, 22, 2, 56).isoformat(),
        "wake_time": datetime(2026, 8, 22, 9, 38).isoformat(),
        "hours": 6.7,
        "signal": "short_sleep_likely",
        "confidence": 0.8,
    }
    import json
    from src.models.derived_signal import utc_now
    async with async_session_maker() as db:
        db.add(DerivedSignal(honcho_workspace_id="ws_sleep", honcho_session_id="s_sleep",
            kind=DerivedSignalKind.SLEEP_EPISODE, payload_json=json.dumps(payload),
            last_message_id="m1", created_at=utc_now(), updated_at=utc_now()))
        await db.commit()
    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_sleep", "session_id": "s_sleep",
        "now": "2026-08-22T09:45:00Z", "timezone": "Europe/London",
    })
    assert packet.json()["sleep"]["signal"] == "short_sleep_likely"
    assert set(packet.json()["sleep"].keys()) == {"signal", "confidence"}


# ── Recurrence health + curiosity ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_recurrence_health_and_curiosity_in_packet(async_client):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)  # Saturday 2026-08-22
    recurrence = RecurringIntention(
        honcho_workspace_id="ws_health", honcho_session_id="s_health", honcho_message_id="m1",
        candidate_key="r", canonical_key="morning-walk", title="Morning walk", cadence="daily",
        source_evidence="I walk each morning", status=OperationalStatus.ACTIVE,
        created_at=now.replace(tzinfo=None), updated_at=now.replace(tzinfo=None),
    )
    async with async_session_maker() as db:
        db.add(recurrence)
        await db.commit()
        await db.refresh(recurrence)

    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_health", "session_id": "s_health",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })
    body = packet.json()
    item = next(i for i in body["recurring_intentions"] if i["title"] == "Morning walk")
    assert item["slipping"] is True
    assert item["expected_this_week"] >= 1
    assert item["completed_this_week"] == 0
    assert item["progress_line"] == f"0/{item['expected_this_week']} done this week"
    curiosity = body["curiosity"]
    assert any(c["topic"] == "Morning walk" for c in curiosity)
    assert len(curiosity) <= 2


@pytest.mark.asyncio
async def test_completed_recurrence_is_not_slipping_and_no_curiosity(async_client):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    recurrence = RecurringIntention(
        honcho_workspace_id="ws_fresh", honcho_session_id="s_fresh", honcho_message_id="m1",
        candidate_key="r", canonical_key="morning-walk", title="Morning walk", cadence="daily",
        source_evidence="I walk each morning", status=OperationalStatus.ACTIVE,
        created_at=now.replace(tzinfo=None), updated_at=now.replace(tzinfo=None),
    )
    async with async_session_maker() as db:
        db.add(recurrence)
        await db.commit()
        await db.refresh(recurrence)
        # Full week completed: Mon..Sat (today) each completed -> not slipping.
        start = now.date() - timedelta(days=now.date().weekday())
        for offset in range(6):
            db.add(RecurringOccurrence(recurring_intention_id=recurrence.id,
                honcho_workspace_id="ws_fresh", user_day=start + timedelta(days=offset),
                status=OccurrenceStatus.COMPLETED, evidence="done"))
        await db.commit()
    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_fresh", "session_id": "s_fresh",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })
    body = packet.json()
    item = next(i for i in body["recurring_intentions"] if i["title"] == "Morning walk")
    assert item["slipping"] is False
    assert item["completed_this_week"] == item["expected_this_week"]
    assert body["curiosity"] == []


@pytest.mark.asyncio
async def test_curiosity_respects_already_asked_attention_bookkeeping(async_client):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)
    recurrence = RecurringIntention(
        honcho_workspace_id="ws_nag", honcho_session_id="s_nag", honcho_message_id="m1",
        candidate_key="r", canonical_key="morning-walk", title="Morning walk", cadence="daily",
        source_evidence="I walk each morning", status=OperationalStatus.ACTIVE,
        created_at=now.replace(tzinfo=None), updated_at=now.replace(tzinfo=None),
    )
    async with async_session_maker() as db:
        db.add(recurrence)
        await db.commit()
        await db.refresh(recurrence)
        db.add(AttentionCandidate(honcho_workspace_id="ws_nag", honcho_session_id="s_nag",
            source_message_id="m0", candidate_key="q", kind=AttentionCandidateKind.PENDING_QUESTION,
            content="How is your morning walk routine going?", salience=.6, confidence=.6,
            status=AttentionCandidateStatus.ACTIVE, surfaced_count=3))
        await db.commit()
    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_nag", "session_id": "s_nag",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })
    assert packet.json()["curiosity"] == []


# ── Suppression reopen ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_explicit_reopen_from_model_shape_stage():
    text = "we can talk about Ashley now"
    evidence = "we can talk about Ashley now"
    provider = StubTwoStage([
        {"observations": [{"description": "Ashley topic reopened", "evidence_text": evidence,
            "confidence": .9, "actor_peer_id": "user", "subject_refs": [], "temporal_language": None}]},
        {"candidates": [{"loose_observation_id": _obs_id(evidence),
            "operational_kind": "suppression", "observation": "Reopen Ashley topic",
            "canonical_title": "Ashley", "confidence": .9, "suppression_hint": None}]},
    ])
    candidates = provider.extract(text, peer_id="user")
    assert len(candidates) == 1
    hint = candidates[0].suppression_hint
    assert hint is not None
    assert hint["action"] == "reopen"
    assert "ashley" in (hint.get("topic_or_entity") or "").lower()
    assert any("normalized_reopen_language" in note for note in candidates[0].validation_notes)


@pytest.mark.asyncio
async def test_condition_based_reopen_consumes_user_mention():
    async with async_session_maker() as db:
        service = LifecycleService()
        suppression = Suppression(honcho_workspace_id="ws_re", honcho_session_id="s_re",
            honcho_message_id="m1", candidate_key="supp", target_type="topic",
            topic_or_entity="ashley", reason="user_explicit_suppression",
            reopen_condition="user_mentions_topic", status=SuppressionStatus.ACTIVE)
        db.add(suppression)
        await db.commit()

        reopened = await service.apply_reopen_conditions(
            db, workspace_id="ws_re", session_id="s_re", text="I fixed the printer today"
        )
        assert reopened == []
        row = (await db.execute(select(Suppression))).scalar_one()
        assert row.status == SuppressionStatus.ACTIVE

        reopened = await service.apply_reopen_conditions(
            db, workspace_id="ws_re", session_id="s_re", text="Ashley and I talked today"
        )
        assert len(reopened) == 1
        row = (await db.execute(select(Suppression))).scalar_one()
        assert row.status == SuppressionStatus.REOPENED


# ── Handshake first-contact ─────────────────────────────────────────────────

def _handshake_payload(now, last_interaction_time=None):
    return {
        "workspace_id": "ws_hs", "session_id": "s_hs", "now": now,
        "timezone": "Europe/London",
        "last_interaction_time": last_interaction_time,
    }


@pytest.mark.asyncio
async def test_handshake_first_contact_lifecycle(async_client):
    day1_0930 = "2026-08-21T09:30:00Z"
    first = (await async_client.post("/v1/cortex/handshake", json=_handshake_payload(day1_0930))).json()
    assert first["first_contact_today"] is True
    assert first["sitting"] == "first_contact_today"

    same_day_0940 = "2026-08-21T09:40:00Z"
    ongoing = (await async_client.post("/v1/cortex/handshake", json=_handshake_payload(
        same_day_0940, last_interaction_time="2026-08-21T09:32:00Z"))).json()
    assert ongoing["first_contact_today"] is False
    assert ongoing["sitting"] == "ongoing_sitting"

    same_day_1130 = "2026-08-21T11:30:00Z"
    later = (await async_client.post("/v1/cortex/handshake", json=_handshake_payload(
        same_day_1130, last_interaction_time="2026-08-21T09:40:00Z"))).json()
    assert later["first_contact_today"] is False
    assert later["sitting"] == "new_sitting_same_day"

    day2_0900 = "2026-08-22T09:00:00Z"
    next_day = (await async_client.post("/v1/cortex/handshake", json=_handshake_payload(
        day2_0900, last_interaction_time="2026-08-21T22:00:00Z"))).json()
    assert next_day["first_contact_today"] is True
    assert next_day["sitting"] == "first_contact_today"


@pytest.mark.asyncio
async def test_handshake_sleep_and_first_contact_distinct(async_client):
    # A morning re-entry the same day keeps first_contact false but daypart morning.
    payload = _handshake_payload(
        "2026-08-21T10:05:00Z", last_interaction_time="2026-08-21T09:30:00Z"
    )
    result = (await async_client.post("/v1/cortex/handshake", json=payload)).json()
    assert result["daypart"] == "morning"
    assert result["first_contact_today"] is False