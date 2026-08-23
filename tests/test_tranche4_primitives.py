import hashlib
from datetime import datetime, timedelta, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.clarification import ClarificationCandidate, ClarificationStatus, ClarificationType
from src.models.operational_state import (OccurrenceStatus, OperationalStatus,
    RecurringIntention, RecurringOccurrence)
from src.models.suppression import Suppression, SuppressionStatus
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
        assert first is not None and "bed_time" in first
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
async def test_sleep_signal_in_packet_is_compact_without_confidence(async_client):
    from src.models.derived_signal import DerivedSignal, DerivedSignalKind, utc_now
    import json
    payload = {
        "bed_time": datetime(2026, 8, 22, 2, 56).isoformat(),
        "wake_time": datetime(2026, 8, 22, 9, 38).isoformat(),
        "hours": 6.7,
        "signal": "short_sleep_likely",
        "confidence": 0.8,
    }
    async with async_session_maker() as db:
        db.add(DerivedSignal(honcho_workspace_id="ws_sleep", honcho_session_id="s_sleep",
            kind=DerivedSignalKind.SLEEP_EPISODE, payload_json=json.dumps(payload),
            last_message_id="m1", created_at=utc_now(), updated_at=utc_now()))
        await db.commit()
    packet = await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_sleep", "session_id": "s_sleep",
        "now": "2026-08-22T09:45:00Z", "timezone": "Europe/London",
    })
    assert packet.json()["sleep"] == {"signal": "short_sleep_likely"}


# ── Recurrence gap + curiosity (distinct primitives) ────────────────────────

@pytest.mark.asyncio
async def test_slipping_recurrence_is_gap_attention_not_curiosity(async_client):
    now = datetime(2026, 8, 22, 12, tzinfo=timezone.utc)  # Saturday
    recurrence = RecurringIntention(
        honcho_workspace_id="ws_health", honcho_session_id="s_health", honcho_message_id="m1",
        candidate_key="r", canonical_key="morning-walk", title="Morning walk", cadence="daily",
        source_evidence="I walk each morning", status=OperationalStatus.ACTIVE,
        started_at=(now - timedelta(days=5)).replace(tzinfo=None),
        created_at=now.replace(tzinfo=None), updated_at=now.replace(tzinfo=None),
    )
    async with async_session_maker() as db:
        db.add(recurrence)
        await db.commit()
        await db.refresh(recurrence)

    body = (await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_health", "session_id": "s_health",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })).json()
    item = next(i for i in body["recurring_intentions"] if i["title"] == "Morning walk")
    assert item["slipping"] is True
    assert item["week_target"] == 7
    assert item["expected_so_far"] == 6  # Mon..Sat elapsed
    assert item["completed_so_far"] == 0
    assert item["progress_line"] == "0/6 done so far this week"
    # slippage is attention/gap, not curiosity
    assert any(g["type"] == "routine_gap" and g["topic"] == "Morning walk" for g in body["attention"])
    # started 5 days ago and never observed -> a genuine useful unknown
    assert any(c["type"] == "unobserved_routine" and c["topic"] == "Morning walk" for c in body["curiosity"])
    assert len(body["curiosity"]) <= 2


@pytest.mark.asyncio
async def test_fresh_completed_recurrence_no_gap_no_curiosity(async_client):
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
        start = now.date() - timedelta(days=now.date().weekday())
        for offset in range(6):
            db.add(RecurringOccurrence(recurring_intention_id=recurrence.id,
                honcho_workspace_id="ws_fresh", user_day=start + timedelta(days=offset),
                status=OccurrenceStatus.COMPLETED, evidence="done"))
        await db.commit()
    body = (await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_fresh", "session_id": "s_fresh",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })).json()
    item = next(i for i in body["recurring_intentions"] if i["title"] == "Morning walk")
    assert item["slipping"] is False
    assert item["completed_so_far"] == item["expected_so_far"] == 6
    assert body["attention"] == []
    assert body["curiosity"] == []  # started today, not an unobserved unknown


@pytest.mark.asyncio
async def test_pending_clarification_surfaces_as_curiosity(async_client):
    async with async_session_maker() as db:
        db.add(ClarificationCandidate(honcho_workspace_id="ws_clar", honcho_session_id="s_clar",
            honcho_message_id="m1", candidate_key="c",
            clarification_type=ClarificationType.UNCLEAR_TARGET,
            description="which follow-up did you mean?",
            status=ClarificationStatus.PENDING))
        await db.commit()
    body = (await async_client.get("/v1/cortex/attention-packet", params={
        "workspace_id": "ws_clar", "session_id": "s_clar",
        "now": "2026-08-22T12:00:00Z", "timezone": "Europe/London",
    })).json()
    assert any(c["type"] == "clarification" for c in body["curiosity"])


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
    assert hint is not None and hint["action"] == "reopen"
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


@pytest.mark.asyncio
async def test_durable_boundary_does_not_reopen_on_topic_mention():
    # A durable relational boundary ("don't ask about the divorce anymore") has
    # no reopen_condition. Mentioning the topic must NOT revoke it.
    async with async_session_maker() as db:
        service = LifecycleService()
        durable = Suppression(honcho_workspace_id="ws_du", honcho_session_id="s_du",
            honcho_message_id="m1", candidate_key="supp", target_type="topic",
            topic_or_entity="divorce", reason="user_explicit_suppression",
            reopen_condition=None, status=SuppressionStatus.ACTIVE)
        db.add(durable)
        await db.commit()
        reopened = await service.apply_reopen_conditions(
            db, workspace_id="ws_du", session_id="s_du",
            text="my divorce lawyer emailed me about the paperwork"
        )
        assert reopened == []
        row = (await db.execute(select(Suppression))).scalar_one()
        assert row.status == SuppressionStatus.ACTIVE


# ── Handshake: sitting owned by chronology, first_contact cortex-owned ──────

def _hs(now, chronology=None, last_interaction_time=None):
    return {
        "workspace_id": "ws_hs", "session_id": "s_hs", "now": now,
        "timezone": "Europe/London", "chronology": chronology,
        "last_interaction_time": last_interaction_time,
    }


@pytest.mark.asyncio
async def test_handshake_required_example_09_05_to_10_00_new_sitting_morning(async_client):
    # 09:05 morning contact, ~55 min away, 10:00 return -> new_sitting_same_day
    # + morning. Chronology (app-owned) declares it; cortex consumes it.
    payload = _hs(
        "2026-08-21T10:00:00Z",
        chronology={"temporalSession": "new", "gapMinutes": 55,
                    "firstContactUserDay": False},
        last_interaction_time="2026-08-21T09:05:00Z",
    )
    result = (await async_client.post("/v1/cortex/handshake", json=payload)).json()
    assert result["daypart"] == "morning"
    assert result["sitting"] == "new_sitting_same_day"
    assert result["first_contact_today"] is False


@pytest.mark.asyncio
async def test_handshake_first_contact_semantics_from_chronology(async_client):
    first = (await async_client.post("/v1/cortex/handshake", json=_hs(
        "2026-08-21T09:05:00Z",
        chronology={"temporalSession": "new", "gapMinutes": 900, "firstContactUserDay": True},
    ))).json()
    assert first["sitting"] == "first_contact_today"
    assert first["first_contact_today"] is True

    ongoing = (await async_client.post("/v1/cortex/handshake", json=_hs(
        "2026-08-21T09:40:00Z",
        chronology={"temporalSession": "same", "gapMinutes": 5, "firstContactUserDay": False},
        last_interaction_time="2026-08-21T09:32:00Z",
    ))).json()
    assert ongoing["sitting"] == "ongoing_sitting"
    assert ongoing["first_contact_today"] is False

    next_day = (await async_client.post("/v1/cortex/handshake", json=_hs(
        "2026-08-22T09:00:00Z",
        chronology={"temporalSession": "new", "gapMinutes": 720, "firstContactUserDay": True},
        last_interaction_time="2026-08-21T22:00:00Z",
    ))).json()
    assert next_day["sitting"] == "first_contact_today"
    assert next_day["first_contact_today"] is True


@pytest.mark.asyncio
async def test_handshake_without_chronology_only_owns_first_contact_fact(async_client):
    # No chronology -> cortex does NOT classify sitting (one owner), but may
    # still report the cortex-owned first_contact fact from known interaction.
    no_prior = (await async_client.post("/v1/cortex/handshake", json=_hs(
        "2026-08-21T09:05:00Z", last_interaction_time=None
    ))).json()
    assert no_prior["sitting"] is None
    assert no_prior["first_contact_today"] is True

    same_day = (await async_client.post("/v1/cortex/handshake", json=_hs(
        "2026-08-21T10:05:00Z", last_interaction_time="2026-08-21T09:30:00Z"
    ))).json()
    assert same_day["sitting"] is None
    assert same_day["first_contact_today"] is False
    assert same_day["daypart"] == "morning"