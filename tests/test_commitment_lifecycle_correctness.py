"""Regression coverage for commitment-candidate lifecycle correctness:
completion recognition, third-party attribution, and cross-source
reconciliation.

Three verified benchmark failures shared underlying defects in this sink:
- PROBLEM A (chairs): CommitmentCandidate had NO terminal "done" state at
  all before this fix (only PENDING/MATERIALIZED/DISMISSED/EXPIRED/
  VIOLATED) and no consumer ever wired completion evidence to it, so a
  genuine self-commitment could only ever wait to VIOLATE regardless of
  what was said afterward.
- PROBLEM B (Studio Sam) / PROBLEM C (school money): `implicit_self_commitment`
  + `authority=act` was granted from evidence containing no first-person
  commitment language at all — a third party's reported promise ("Sam ...
  said he'd send...") or a third party's reported NEED ("Andree ... needs
  the school money") — because the extractor's own hint was trusted without
  a deterministic actor-attribution floor.
"""
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
)
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate

UTC = timezone.utc


def _commitment_candidate(*, key: str, text: str, title: str,
                         evidence_class: str = "implicit_self_commitment",
                         authority: str = "act") -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key,
        observation=text,
        raw_evidence=text,
        canonical_title=title,
        operational_kind="commitment_candidate",
        evidence_class=evidence_class,
        authority=authority,
        temporal_phrase="today",
        confidence=0.9,
        formation="explicit",
        extractor_version="lifecycle-correctness-regression",
    )


def _completion_candidate(*, key: str, text: str, title: str) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key,
        observation=text,
        raw_evidence=text,
        canonical_title=title,
        operational_kind="event",
        confidence=0.9,
        formation="explicit",
        extractor_version="lifecycle-correctness-regression",
        resolution_hint={"action": "fulfill", "target_kind": "commitment"},
    )


async def _send_turn(async_client, monkeypatch, *, workspace_id: str, sender: str,
                     message_id: str, candidate: ExtractionCandidate, text: str):
    monkeypatch.setattr(
        v1_events.turn_extractor, "extract_candidates",
        lambda *args, **kwargs: [candidate],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": workspace_id,
            "session_id": "session-1",
            "honcho_message_id": message_id,
            "peer_id": sender,
            "text": text,
            "now": "2026-09-28T10:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text


async def _commitments(workspace_id: str):
    async with async_session_maker() as db:
        return (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
        ).order_by(CommitmentCandidate.created_at))).scalars().all()


# ── PROBLEM A: explicit completion reconciles instead of later violating ───

@pytest.mark.asyncio
async def test_a1_explicit_completion_fulfils_existing_commitment(async_client, monkeypatch):
    ws = "ws-lifecycle-chairs"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I promised the venue I'd confirm chairs today.",
            title="confirm chairs with venue"),
        text="I promised the venue I'd confirm chairs today.",
    )
    rows = await _commitments(ws)
    assert len(rows) == 1
    assert rows[0].authority == CommitmentCandidateAuthority.ACT
    assert rows[0].status == CommitmentCandidateStatus.PENDING

    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_completion_candidate(
            key="c2", text="I told the venue yes, 120 chairs, so that's done.",
            title="confirm chairs with venue"),
        text="I told the venue yes, 120 chairs, so that's done.",
    )
    rows = await _commitments(ws)
    assert len(rows) == 1
    assert rows[0].status == CommitmentCandidateStatus.FULFILLED
    assert rows[0].resolution_evidence and rows[0].resolution_evidence.startswith("fulfilled:")


@pytest.mark.asyncio
async def test_a1b_fulfilled_commitment_never_violates(async_client, monkeypatch):
    """Same as A1, but proves evaluate_due leaves it alone even long after
    the due window (the actual observed failure: PENDING -> VIOLATED)."""
    ws = "ws-lifecycle-chairs-due"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I promised the venue I'd confirm chairs today.",
            title="confirm chairs with venue"),
        text="I promised the venue I'd confirm chairs today.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_completion_candidate(
            key="c2", text="I told the venue yes, 120 chairs, so that's done.",
            title="confirm chairs with venue"),
        text="I told the venue yes, 120 chairs, so that's done.",
    )
    from src.services.commitment_candidate_service import CommitmentCandidateService
    async with async_session_maker() as db:
        violated = await CommitmentCandidateService().evaluate_due(
            db, workspace_id=ws, now=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    assert violated == []
    rows = await _commitments(ws)
    assert rows[0].status == CommitmentCandidateStatus.FULFILLED


@pytest.mark.asyncio
async def test_a3_unresolved_control_still_violates(async_client, monkeypatch):
    """No completion evidence arrives: the pendulum check — fixing
    over-persistence must not cause premature/blanket closure either."""
    ws = "ws-lifecycle-chairs-unresolved"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I promised the venue I'd confirm chairs today.",
            title="confirm chairs with venue"),
        text="I promised the venue I'd confirm chairs today.",
    )
    from src.services.commitment_candidate_service import CommitmentCandidateService
    async with async_session_maker() as db:
        violated = await CommitmentCandidateService().evaluate_due(
            db, workspace_id=ws, now=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    rows = await _commitments(ws)
    assert violated == [rows[0].id]
    assert rows[0].status == CommitmentCandidateStatus.VIOLATED


# ── PROBLEM B: third-party reference must not become user ACT commitment ───

@pytest.mark.asyncio
async def test_b1_third_party_referenced_action_downgrades_to_ask(async_client, monkeypatch):
    ws = "ws-lifecycle-sam"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="Sam from the studio said he'd send the revised contract today.",
            title="send revised contract"),
        text="Sam from the studio said he'd send the revised contract today.",
    )
    rows = await _commitments(ws)
    assert len(rows) == 1
    assert rows[0].authority == CommitmentCandidateAuthority.ASK
    # Preserved as useful longitudinal evidence, not deleted/suppressed.
    assert rows[0].title == "send revised contract"

    from src.services.commitment_candidate_service import CommitmentCandidateService
    async with async_session_maker() as db:
        violated = await CommitmentCandidateService().evaluate_due(
            db, workspace_id=ws, now=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    assert violated == []


@pytest.mark.asyncio
async def test_b2_genuine_user_action_remains_act(async_client, monkeypatch):
    ws = "ws-lifecycle-genuine-user"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I'll send the document tomorrow.",
            title="send the document"),
        text="I'll send the document tomorrow.",
    )
    rows = await _commitments(ws)
    assert len(rows) == 1
    assert rows[0].authority == CommitmentCandidateAuthority.ACT


# ── PROBLEM C: school-trip duplicate authority + bank reconciliation ───────

@pytest.mark.asyncio
async def test_c_school_trip_only_genuine_self_commitment_gets_act(async_client, monkeypatch):
    ws = "ws-lifecycle-school"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1",
            text="Andree just told me he needs the school money today or he can't go on the trip",
            title="pay school money"),
        text="Andree just told me he needs the school money today or he can't go on the trip.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="I'll pay it when I get home from sports day.",
            title="pay for school trip"),
        text="I'll pay it when I get home from sports day.",
    )
    rows = await _commitments(ws)
    assert len(rows) == 2
    by_title = {r.title: r for r in rows}
    assert by_title["pay school money"].authority == CommitmentCandidateAuthority.ASK
    assert by_title["pay for school trip"].authority == CommitmentCandidateAuthority.ACT

    # Only the genuine ACT commitment can ever violate.
    from src.services.commitment_candidate_service import CommitmentCandidateService
    async with async_session_maker() as db:
        violated = await CommitmentCandidateService().evaluate_due(
            db, workspace_id=ws, now=datetime(2026, 10, 5, 12, 0, tzinfo=UTC))
    assert violated == [by_title["pay for school trip"].id]


@pytest.mark.asyncio
async def test_c3_bank_feed_fulfils_commitment_across_owner(async_client, monkeypatch):
    """The realistic shape: bank-feed evidence arrives with a DIFFERENT
    sender identity than the commitment's owner (external:bank_feed vs
    ashley) — fulfilment matching must not be owner-scoped, matching the
    already-established, owner-agnostic Expectation pattern."""
    ws = "ws-lifecycle-school-bank"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I'll pay for the school trip when I get home.",
            title="pay for school trip"),
        text="I'll pay for the school trip when I get home.",
    )
    rows = await _commitments(ws)
    assert rows[0].authority == CommitmentCandidateAuthority.ACT

    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="external:bank_feed", message_id="m2",
        candidate=_completion_candidate(
            key="c2", text="Outgoing payment: School Trips Ltd — £18.",
            title="pay for school trip"),
        text="Outgoing payment: School Trips Ltd — £18.",
    )
    rows = await _commitments(ws)
    assert rows[0].status == CommitmentCandidateStatus.FULFILLED


@pytest.mark.asyncio
async def test_c4_superficially_similar_unrelated_evidence_does_not_close(async_client, monkeypatch):
    """Pendulum check: must NOT close merely because words/amounts happen to
    overlap. Weak, single-token overlap with no judge available must leave
    the commitment PENDING rather than guess."""
    ws = "ws-lifecycle-unrelated-evidence"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I'll pay for the school trip when I get home.",
            title="pay for school trip"),
        text="I'll pay for the school trip when I get home.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="external:bank_feed", message_id="m2",
        candidate=_completion_candidate(
            key="c2", text="Incoming payment: refund from Trip Advisor — £18.",
            title="unrelated refund"),
        text="Incoming payment: refund from Trip Advisor — £18.",
    )
    rows = await _commitments(ws)
    assert rows[0].status == CommitmentCandidateStatus.PENDING


@pytest.mark.asyncio
async def test_ambiguous_two_equally_strong_matches_stays_pending(async_client, monkeypatch):
    """Two commitments both strongly overlap the same completion evidence:
    do not guess which one it means."""
    ws = "ws-lifecycle-ambiguous"
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I'll pay the school trip deposit today.",
            title="pay the school trip deposit"),
        text="I'll pay the school trip deposit today.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="I'll pay the school trip balance today.",
            title="pay the school trip balance"),
        text="I'll pay the school trip balance today.",
    )
    await _send_turn(
        async_client, monkeypatch, workspace_id=ws, sender="external:bank_feed", message_id="m3",
        candidate=_completion_candidate(
            key="c3", text="Outgoing payment: School Trips Ltd — school trip payment made.",
            title="school trip payment"),
        text="Outgoing payment: School Trips Ltd — school trip payment made.",
    )
    rows = await _commitments(ws)
    assert {r.status for r in rows} == {CommitmentCandidateStatus.PENDING}
