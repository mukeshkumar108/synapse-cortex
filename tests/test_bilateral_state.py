"""Step 3 Slice 2: bilateral ownership, fact store, relational commitments.

Acceptance anchors from the take-2/take-5 replays:
- msg 17 Elena promise must be ownable by Elena (owner=actor), never user state;
- user ratification must not overwrite the character side (owner-scoped dedupe);
- ghost/generic actors fall back to sender (no stranded rows, no laundering);
- event-kind content lands in facts, never expectations.
"""
import pytest

from src.schemas.candidate import ExtractionCandidate
from src.services.ownership import resolve_owner


def test_owner_defaults_to_sender():
    assert resolve_owner("kai", None, set()) == "kai"
    assert resolve_owner("kai", "", set()) == "kai"


def test_generic_role_words_fall_back_to_sender():
    for generic in ("user", "assistant", "User", "ASSISTANT", "unknown", "system"):
        assert resolve_owner("kai", generic, {"kai", "elena"}) == "kai", generic


def test_evidenced_character_peer_wins():
    assert resolve_owner("kai", "elena", {"kai", "elena"}) == "elena"


def test_ghost_peer_falls_back_to_sender():
    assert resolve_owner("kai", "mallory", {"kai", "elena"}) == "kai"
    assert resolve_owner("kai", "elena", set()) == "kai"


def test_character_promise_evidence_class_valid():
    cand = ExtractionCandidate(
        candidate_key="c_x", observation="I'll be here",
        raw_evidence="I'll be here", canonical_title="Be here",
        operational_kind="commitment_candidate", actor_peer_id="elena",
        evidence_class="character_promise", authority="act", confidence=0.9,
        extractor_version="test",
    )
    assert cand.evidence_class == "character_promise"


@pytest.mark.asyncio
async def test_commitment_upsert_is_owner_scoped():
    from src.db import async_session_maker
    from src.models.commitment_candidate import CommitmentCandidate, CommitmentCandidateStatus
    from src.services.commitment_candidate_service import CommitmentCandidateService
    from datetime import datetime, timezone
    cand = ExtractionCandidate(
        candidate_key="c_elena_space", observation="I'll give you space. I'll be here.",
        raw_evidence="I'll give you space. I'll be here.", canonical_title="Give space, be here",
        operational_kind="commitment_candidate", actor_peer_id="elena",
        evidence_class="character_promise", authority="act", confidence=0.95,
        extractor_version="test",
    )
    async with async_session_maker() as db:
        row = await CommitmentCandidateService().upsert_from_candidate(
            db, workspace_id="ws-bilat", session_id="s1", owner_peer_id="elena",
            message_id="m17", candidate=cand, now=datetime(2026, 9, 22, tzinfo=timezone.utc))
        assert row is not None
        assert row.owner_peer_id == "elena"
        assert row.status == CommitmentCandidateStatus.PENDING
        # A user-side row with the same title is a separate bilateral side.
        user_cand = ExtractionCandidate(
            candidate_key="c_kai_ok", observation="yes. very much so.",
            raw_evidence="yes. very much so.", canonical_title="Give space, be here",
            operational_kind="commitment_candidate", actor_peer_id="kai",
            evidence_class="explicit_acceptance", authority="ask", confidence=0.8,
            extractor_version="test",
        )
        user_row = await CommitmentCandidateService().upsert_from_candidate(
            db, workspace_id="ws-bilat", session_id="s1", owner_peer_id="kai",
            message_id="m18", candidate=user_cand, now=datetime(2026, 9, 22, tzinfo=timezone.utc))
        assert user_row is not None and user_row.id != row.id
        assert user_row.owner_peer_id == "kai"


@pytest.mark.asyncio
async def test_fact_writer_dedupes_and_never_touches_expectations():
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.expectation import Expectation
    from src.models.fact import Fact
    from src.services.persistence import save_fact_idempotent
    record = dict(honcho_workspace_id="ws-fact", honcho_session_id="s1",
                  honcho_message_id="m134", owner_peer_id="kai",
                  candidate_key="c_neck@test", category="health",
                  title="Recurring neck ache", evidence_verbatim="recurring neck ache",
                  formation="explicit", confidence=0.9)
    async with async_session_maker() as db:
        first, created = await save_fact_idempotent(db, record)
        assert created is True
        second, created2 = await save_fact_idempotent(db, record)
        assert created2 is False and second.id == first.id
        rows = (await db.execute(select(Fact).where(Fact.honcho_workspace_id == "ws-fact"))).scalars().all()
        assert len(rows) == 1 and rows[0].category == "health"
        assert (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-fact"))).scalars().all() == []


@pytest.mark.asyncio
async def test_event_turn_writes_fact_not_expectation(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.expectation import Expectation
    from src.models.fact import Fact
    from src.routers import v1_events
    cand = ExtractionCandidate(
        candidate_key="c_grief", observation="Father died less than a year after diagnosis",
        raw_evidence="he was diagnosed. and then less than a year later he was gone.",
        canonical_title="Father death", operational_kind="event",
        actor_peer_id="kai", confidence=0.9, extractor_version="test")
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: [cand])
    payload = {"workspace_id": "ws-event", "session_id": "s1", "honcho_message_id": "m198",
               "peer_id": "kai", "text": cand.raw_evidence,
               "now": "2026-09-22T11:23:21+01:00", "timezone": "Europe/London"}
    r = await async_client.post("/v1/events/turn", json=payload)
    assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        facts = (await db.execute(select(Fact).where(Fact.honcho_workspace_id == "ws-event"))).scalars().all()
        assert len(facts) == 1
        assert facts[0].owner_peer_id == "kai"
        assert "death" in facts[0].title.lower() or "father" in facts[0].title.lower()
        exps = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-event"))).scalars().all()
        assert exps == []


def _promise_cand(**kw):
    base = dict(
        candidate_key="c_promise", observation="I'll give you space. I'll be here.",
        raw_evidence="I'll give you space. I'll be here.", canonical_title="Give space, be here",
        operational_kind="commitment_candidate", actor_peer_id="elena",
        subject_peer_id="elena", evidence_class="character_promise", authority="act",
        confidence=0.95, formation="explicit", extractor_version="test")
    base.update(kw)
    return ExtractionCandidate(**base)


def _assistant_payload(**kw):
    base = dict(workspace_id="ws-asst", session_id="s1", honcho_message_id="m-elena-17",
                peer_id="elena", text="I'll give you space. I'll be here.",
                now="2026-09-22T02:21:19+01:00", timezone="Europe/London",
                is_assistant_turn=True)
    base.update(kw)
    return base


@pytest.mark.asyncio
async def test_assistant_promise_becomes_speaker_owned_commitment(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.suppression import Suppression
    from src.models.clarification import ClarificationCandidate
    from src.routers import v1_events
    monkeypatch.setattr(v1_events.turn_extractor, "extract_assistant_owned",
                        lambda *a, **kw: [_promise_cand()])
    r = await async_client.post("/v1/events/turn", json=_assistant_payload())
    assert r.status_code == 202, r.text
    assert r.json()["assistant_lane"] is True
    async with async_session_maker() as db:
        rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == "ws-asst"))).scalars().all()
        assert len(rows) == 1
        assert rows[0].owner_peer_id == "elena"
        assert rows[0].evidence_class == "character_promise"
        # Hard ban: no user-authority or lifecycle rows from this path.
        assert (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-asst"))).scalars().all() == []
        assert (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == "ws-asst"))).scalars().all() == []
        assert (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == "ws-asst"))).scalars().all() == []


@pytest.mark.asyncio
async def test_assistant_lane_rejects_expectation_kind(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.expectation import Expectation
    from src.routers import v1_events
    bad = _promise_cand(operational_kind="expectation", expectation_type_hint="user_intention")
    monkeypatch.setattr(v1_events.turn_extractor, "extract_assistant_owned",
                        lambda *a, **kw: [bad])
    r = await async_client.post("/v1/events/turn", json=_assistant_payload())
    assert r.status_code == 202, r.text
    assert r.json()["mutations"] == [
        {"mutation": "assistant_lane_rejected", "kind": "expectation"}]
    async with async_session_maker() as db:
        assert (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-asst"))).scalars().all() == []


@pytest.mark.asyncio
async def test_assistant_turn_is_replay_idempotent(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.commitment_candidate import CommitmentCandidate
    from src.routers import v1_events
    monkeypatch.setattr(v1_events.turn_extractor, "extract_assistant_owned",
                        lambda *a, **kw: [_promise_cand()])
    for _ in range(2):
        r = await async_client.post("/v1/events/turn", json=_assistant_payload())
        assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == "ws-asst"))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_assistant_turn_leaves_user_rows_untouched(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.routers import v1_events
    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id="ws-asst", honcho_session_id="s1", honcho_message_id="m-user-1",
            owner_peer_id="kai", subject_peer_id="kai",
            expectation_type=ExpectationType.USER_INTENTION,
            title="User plan", summary="User intends: plan"))
        await db.commit()
    monkeypatch.setattr(v1_events.turn_extractor, "extract_assistant_owned",
                        lambda *a, **kw: [_promise_cand()])
    r = await async_client.post("/v1/events/turn", json=_assistant_payload())
    assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        rows = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-asst"))).scalars().all()
        assert len(rows) == 1 and rows[0].outcome_state == OutcomeState.UNKNOWN
        assert rows[0].title == "User plan"
