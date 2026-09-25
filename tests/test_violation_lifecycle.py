"""3B2 violation/self-accounting + release/closure tests (deterministic).

- ASK-only rows can never violate (113-row lesson).
- ACT + elapsed due + no fulfilment -> VIOLATED with evidence, never silent.
- Corroboration promotes ASK -> ACT (explicit authority/acceptance only).
- Later evidence closes loops; suppressions carry review notes.
"""
from datetime import datetime, timezone

import pytest

from src.schemas.candidate import ExtractionCandidate
from src.services.commitment_candidate_service import (
    CommitmentCandidateService,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
)

WS = "ws-violation"
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc)


def _promise_cand(**kw):
    base = dict(
        candidate_key="c_friend", observation="I'll ask how your friend is tomorrow",
        raw_evidence="I'll ask how your friend is tomorrow",
        canonical_title="Ask how friend is", operational_kind="commitment_candidate",
        actor_peer_id="elena", evidence_class="character_promise",
        authority="act", temporal_phrase="tomorrow",
        confidence=0.95, formation="explicit", extractor_version="test")
    base.update(kw)
    return ExtractionCandidate(**base)


@pytest.mark.asyncio
async def test_unmet_companion_promise_becomes_violation(async_client, monkeypatch):
    """Mandated synthetic: 'I'll ask how your friend is tomorrow', due passes
    with no fulfilment -> VIOLATED + repair-eligible, never fulfilled/discarded."""
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.commitment_candidate import CommitmentCandidate
    from src.routers import v1_events
    monkeypatch.setattr(v1_events.turn_extractor, "extract_assistant_owned",
                        lambda *a, **kw: [_promise_cand()])
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": WS, "session_id": "s1", "honcho_message_id": "m1",
        "peer_id": "elena", "text": "I'll ask how your friend is tomorrow",
        "now": "2026-09-22T10:00:00+01:00", "timezone": "Europe/London",
        "is_assistant_turn": True})
    assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == WS))).scalars().all()
        assert len(rows) == 1 and rows[0].owner_peer_id == "elena"
        row_id = rows[0].id
        # Due condition (tomorrow window) passes with no fulfilment evidence.
        violated = await CommitmentCandidateService().evaluate_due(
            db, workspace_id=WS, now=datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc))
        assert violated == [row_id]
        refreshed = await db.get(CommitmentCandidate, row_id)
        assert refreshed.status == CommitmentCandidateStatus.VIOLATED
        assert refreshed.resolution_evidence is not None
        assert "tomorrow" in refreshed.title.lower() or "friend" in refreshed.title.lower()


@pytest.mark.asyncio
async def test_ask_only_rows_never_violate():
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.commitment_candidate import CommitmentCandidate
    async with async_session_maker() as db:
        cand = _promise_cand(candidate_key="c_ask", authority="ask")
        row = await CommitmentCandidateService().upsert_from_candidate(
            db, workspace_id=WS, session_id="s1", owner_peer_id="elena",
            message_id="m1", candidate=cand, now=NOW)
        assert row.authority == CommitmentCandidateAuthority.ASK
        violated = await CommitmentCandidateService().evaluate_due(
            db, workspace_id=WS, now=datetime(2026, 10, 1, tzinfo=timezone.utc))
        assert violated == []
        await db.refresh(row)
        assert row.status == CommitmentCandidateStatus.PENDING


@pytest.mark.asyncio
async def test_corroboration_promotes_ask_to_act():
    from src.db import async_session_maker
    from src.models.commitment_candidate import CommitmentCandidate
    async with async_session_maker() as db:
        svc = CommitmentCandidateService()
        first = _promise_cand(candidate_key="c_p1", authority="ask")
        row = await svc.upsert_from_candidate(
            db, workspace_id=WS, session_id="s1", owner_peer_id="elena",
            message_id="m1", candidate=first, now=NOW)
        assert row.authority == CommitmentCandidateAuthority.ASK
        # Mere repetition does NOT promote.
        again = _promise_cand(candidate_key="c_p2", authority="ask")
        row = await svc.upsert_from_candidate(
            db, workspace_id=WS, session_id="s1", owner_peer_id="elena",
            message_id="m2", candidate=again, now=NOW)
        assert row.authority == CommitmentCandidateAuthority.ASK
        # Explicit acceptance corroborates -> ACT with evidence.
        ratified = _promise_cand(candidate_key="c_p3", authority="ask",
                                 evidence_class="explicit_acceptance")
        row = await svc.upsert_from_candidate(
            db, workspace_id=WS, session_id="s1", owner_peer_id="elena",
            message_id="m3", candidate=ratified, now=NOW)
        assert row.authority == CommitmentCandidateAuthority.ACT
        assert row.resolution_evidence is not None and "corroborated" in row.resolution_evidence


@pytest.mark.asyncio
async def test_later_evidence_closes_loop_without_completion_object(async_client, monkeypatch):
    """Release channel: a later turn taking up the loop's matter resolves it,
    even though no turn emitted a completion candidate."""
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.routers import v1_events
    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id=WS, honcho_session_id="s1", honcho_message_id="m1",
            owner_peer_id="kai", title="dentist appointment timing",
            summary="When is the dentist appointment", status=OpenLoopStatus.OPEN))
        await db.commit()
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: [])
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": WS, "session_id": "s1", "honcho_message_id": "m2",
        "peer_id": "kai", "text": "the dentist appointment is Thursday at two, all set",
        "now": "2026-09-22T10:00:00+01:00", "timezone": "Europe/London"})
    assert r.status_code == 202, r.text
    assert r.json()["closed_loop_ids"], "later evidence should close the loop"
    async with async_session_maker() as db:
        rows = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == WS))).scalars().all()
        assert rows[0].status == OpenLoopStatus.RESOLVED
        assert "answered_in_turn" in (rows[0].resolution_evidence or "")


@pytest.mark.asyncio
async def test_suppression_review_note_survives_as_worklist_signal(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.suppression import Suppression, SuppressionStatus
    from src.routers import v1_events
    cand = ExtractionCandidate(
        candidate_key="c_rev", observation="do not talk about money",
        raw_evidence="do not talk about money", canonical_title="money",
        operational_kind="suppression", confidence=0.9, extractor_version="test",
        suppression_hint={"target_type": "topic", "topic_or_entity": "money",
                          "reason": "user said so", "direction": "refuse",
                          "surface_scope": "all_surfaces",
                          "review_note": "possible_direction_conflict: turn also invites openness"})
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: [cand])
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": WS, "session_id": "s1", "honcho_message_id": "m9",
        "peer_id": "kai", "text": "do not talk about money",
        "now": "2026-09-22T10:00:00+01:00", "timezone": "Europe/London"})
    assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        rows = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == WS))).scalars().all()
        assert len(rows) == 1 and rows[0].status == SuppressionStatus.ACTIVE
        assert rows[0].review_note is not None and "direction_conflict" in rows[0].review_note
