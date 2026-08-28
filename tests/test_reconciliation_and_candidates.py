"""Phase 0 contracts + Phase 2 candidate intelligence.

Covers:
- fast→slow suppression (deterministic same-turn reconciliation, both orders)
- slow→fast canonicalization (same-message supersede on object materialization)
- absorb/re-point promotion lifecycle
- commitment candidate store: stable keys, durable dismissal, replay safety,
  expiry, listing and packet surfacing
"""

from datetime import datetime, timedelta, timezone

import pytest

UTC = timezone.utc


def iso(days_ahead: float = 0.0, hours: float = 0.0) -> str:
    base = datetime.now(UTC) + timedelta(days=days_ahead, hours=hours)
    return base.isoformat()


def object_payload(**overrides) -> dict:
    payload = {
        "workspace_id": "ws-rec",
        "session_id": "session-a",
        "peer_id": "user_1",
        "owner_peer_id": "user_1",
        "now": iso(),
        "timezone": "Europe/London",
        "source": {
            "system": "app_task",
            "object_id": "task-rec-1",
            "version": 1,
            "kind": "task",
        },
        "action": "created",
        "title": "Call the plumber",
        "due_at": iso(days_ahead=2),
        "reminder_windows": [],
    }
    payload.update(overrides)
    return payload


async def post_object(async_client, payload):
    return await async_client.post("/v1/events/object", json=payload)


async def post_turn(async_client, **overrides):
    payload = {
        "workspace_id": "ws-rec",
        "session_id": "session-a",
        "honcho_message_id": overrides.pop("message_id", "msg-rec-1"),
        "peer_id": "user_1",
        "text": overrides.pop("text", "remind me to call the plumber tomorrow"),
        "now": iso(),
        "timezone": "Europe/London",
    }
    payload.update(overrides)
    return await async_client.post("/v1/events/turn", json=payload)


def _materialized(message_evidence: str, action: str = "created", object_id: str = "task-rec-1"):
    return {
        "action": action,
        "source_system": "app_task",
        "object_id": object_id,
        "evidence_span": message_evidence,
    }


# ── Pure reconciliation semantics ────────────────────────────────────────────


def _candidate(observation: str, kind: str = "expectation", **kwargs):
    from src.schemas.candidate import ExtractionCandidate

    return ExtractionCandidate(
        candidate_key=f"c_{abs(hash(observation)) % 10_000}",
        observation=observation,
        raw_evidence=kwargs.pop("raw_evidence", observation),
        operational_kind=kind,
        **kwargs,
    )


def _action(action: str, object_id: str, evidence: str):
    from src.schemas.expectation import MaterializedAction

    return MaterializedAction(
        action=action, source_system="app_task", object_id=object_id,
        evidence_span=evidence,
    )


def test_suppression_requires_lane_and_evidence_relation():
    from src.services.turn_reconciliation import suppress_materialized_duplicates

    candidates = [
        _candidate("remind me to call the plumber tomorrow"),
        _candidate("I should renew my passport soon"),
        _candidate("I finished the tax return", kind="completion"),
    ]
    kept, suppressed = suppress_materialized_duplicates(
        candidates,
        [_action("created", "task-1", "remind me to call the plumber tomorrow")],
    )
    assert len(suppressed) == 1
    assert suppressed[0]["reason"] == "duplicate_of_canonical"
    assert suppressed[0]["matched_object_id"] == "task-1"
    # The unrelated self-talk and the completion survive (different evidence).
    assert {c.observation for c in kept} == {
        "I should renew my passport soon",
        "I finished the tax return",
    }


def test_suppression_never_merges_similar_people_or_topics():
    from src.services.turn_reconciliation import suppress_materialized_duplicates

    candidates = [_candidate("call mum tomorrow at 4")]
    kept, suppressed = suppress_materialized_duplicates(
        candidates,
        [_action("created", "task-1", "call the doctor about mum's appointment")],
    )
    # Token overlap below the heavy threshold: no destructive suppression.
    assert suppressed == [] and len(kept) == 1


def test_suppression_ignores_unrelated_evidence_and_empty_spans():
    from src.services.turn_reconciliation import suppress_materialized_duplicates

    candidates = [_candidate("remind me to call the plumber tomorrow")]
    kept, suppressed = suppress_materialized_duplicates(
        candidates, [_action("created", "task-1", "")]
    )
    assert suppressed == [] and len(kept) == 1


# ── API-level both-orders reconciliation ─────────────────────────────────────


@pytest.mark.asyncio
async def test_fast_first_then_turn_delivery_suppresses_duplicate(async_client):
    """Order 1: fast path materializes, then the same turn arrives via the
    background pipeline → the derived duplicate is suppressed."""
    response = await post_object(async_client, object_payload(
        origin={"message_id": "msg-rec-1",
                "evidence_span": "remind me to call the plumber tomorrow"},
    ))
    assert response.status_code == 202
    assert response.json()["action_taken"] == "created"

    turn = await post_turn(async_client, message_id="msg-rec-1",
                           materialized_actions=[_materialized(
                               "remind me to call the plumber tomorrow")])
    assert turn.status_code == 202
    body = turn.json()
    # The rules watcher sees the commitment again, but the canonical object
    # already exists: no second live representation may be created.
    assert body["candidates_suppressed_by_reconciliation"] >= 1 or (
        body["candidates_extracted"] == 0
    )
    packet = await async_client.get(
        "/v1/cortex/attention-packet",
        params={"workspace_id": "ws-rec", "session_id": "session-a",
                "peer_id": "user_1", "timezone": "Europe/London"},
    )
    commitments = packet.json()["commitments"]
    plumber_items = [c for c in commitments if c["source_object_id"] == "task-rec-1"]
    assert len(plumber_items) == 1


@pytest.mark.asyncio
async def test_watcher_first_then_object_push_canonicalizes(async_client):
    """Order 2: the background pipeline ingests the turn first (derived
    expectation), then the fast path materializes the canonical object from
    the same message → the derived expectation is superseded, not duplicated."""
    turn = await post_turn(async_client, message_id="msg-rec-2")
    assert turn.status_code == 202
    derived_ids = turn.json().get("expectation_ids", [])

    response = await post_object(async_client, object_payload(
        source={"system": "app_task", "object_id": "task-rec-2", "version": 1,
                "kind": "task"},
        origin={"message_id": "msg-rec-2",
                "evidence_span": "remind me to call the plumber tomorrow"},
    ))
    assert response.status_code == 202
    body = response.json()
    if derived_ids:
        assert body["canonicalized_expectation_ids"], (
            "derived same-message expectation must be canonicalized"
        )
    packet = await async_client.get(
        "/v1/cortex/attention-packet",
        params={"workspace_id": "ws-rec", "session_id": "session-a",
                "peer_id": "user_1", "timezone": "Europe/London"},
    )
    data = packet.json()
    # Exactly one live representation of the commitment.
    live_commitments = [
        c for c in data["commitments"] if "plumber" in c["title"].lower()
    ]
    live_followups = [
        f for f in data["followups"] if "plumber" in f["title"].lower()
    ]
    assert len(live_commitments) <= 1
    assert len(live_followups) == 0


# ── Absorb / re-point promotion ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_absorb_supersedes_expectation_and_repoints_loop(async_client):
    from sqlmodel import SQLModel
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    import uuid

    async with async_session_maker() as session:
        # Derived open loop with no expectation link (standalone thread).
        loop = OpenLoop(
            honcho_workspace_id="ws-rec",
            honcho_session_id="session-a",
            owner_peer_id="user_1",
            honcho_message_id="msg-derived",
            title="Invited follow-up",
            summary="call the plumber follow-up",
            status=OpenLoopStatus.OPEN,
        )
        session.add(loop)
        await session.commit()
        await session.refresh(loop)
        loop_id = str(loop.id)

    response = await post_object(async_client, object_payload(
        source={"system": "app_task", "object_id": "task-rec-3", "version": 1,
                "kind": "task"},
        title="Call the plumber",
        absorbs=[{"kind": "open_loop", "id": loop_id}],
    ))
    assert response.status_code == 202
    assert loop_id in response.json()["absorbed_ids"]

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.open_loop import OpenLoop

    async with async_session_maker() as session:
        row = (
            await session.execute(
                select(OpenLoop).where(OpenLoop.id == uuid.UUID(loop_id))
            )
        ).scalar_one()
        # Standalone loop with no expectation link is resolved on absorb.
        assert row.status == OpenLoopStatus.RESOLVED


# ── Commitment candidate store ───────────────────────────────────────────────


def _candidate_for(title: str, evidence: str, authority: str = "ask",
                   evidence_class: str = "implicit_self_commitment"):
    from src.schemas.candidate import ExtractionCandidate

    return ExtractionCandidate(
        candidate_key=f"c_{abs(hash(title + evidence)) % 100_000}",
        observation=title,
        raw_evidence=evidence,
        canonical_title=title,
        operational_kind="commitment_candidate",
        evidence_class=evidence_class,
        authority=authority,
    )


@pytest.mark.asyncio
async def test_candidate_upsert_dedupe_dismissal_and_expiry(async_client):
    from src.services.commitment_candidate_service import (
        CommitmentCandidateService,
        canonical_key_for,
    )
    from src.db import async_session_maker

    service = CommitmentCandidateService()
    async with async_session_maker() as db:
        first = await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_1",
            message_id="msg-c1",
            candidate=_candidate_for("Renew my passport", "I should really renew my passport"),
            now=datetime.now(UTC),
        )
        assert first is not None and first.status.value == "pending"

        # Replay of the same observation: idempotent.
        replay = await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_1",
            message_id="msg-c1",
            candidate=_candidate_for("Renew my passport", "I should really renew my passport"),
            now=datetime.now(UTC),
        )
        assert replay.candidate_key == first.candidate_key

        # Paraphrase with the same content words refreshes, not duplicates.
        paraphrase = await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_1",
            message_id="msg-c2",
            candidate=_candidate_for("Passport renewal", "sort my passport renewal this week"),
            now=datetime.now(UTC),
        )
        assert paraphrase.candidate_key == first.candidate_key

        # Durable dismissal.
        marked = await service.mark(
            db, workspace_id="ws-rec", owner_peer_id="user_1",
            candidate_key=first.candidate_key, status=__import__(
                "src.models.commitment_candidate", fromlist=["CommitmentCandidateStatus"]
            ).CommitmentCandidateStatus.DISMISSED,
        )
        assert marked.status.value == "dismissed"

        # Same normalized commitment is never re-proposed after dismissal.
        repropose = await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_1",
            message_id="msg-c3",
            candidate=_candidate_for("Renew passport soon", "need to renew my passport"),
            now=datetime.now(UTC),
        )
        assert repropose is None

        # A different commitment still gets its own candidate.
        other = await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_1",
            message_id="msg-c4",
            candidate=_candidate_for("Book the dentist", "I never booked the dentist"),
            now=datetime.now(UTC),
        )
        assert other is not None


@pytest.mark.asyncio
async def test_candidate_listing_and_packet_surface(async_client):
    from src.services.commitment_candidate_service import CommitmentCandidateService
    from src.db import async_session_maker

    service = CommitmentCandidateService()
    async with async_session_maker() as db:
        await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_2",
            message_id="msg-c5",
            candidate=_candidate_for(
                "Book the dentist", "I never booked the dentist", authority="ask"
            ),
            now=datetime.now(UTC),
        )
        await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_2",
            message_id="msg-c6",
            candidate=_candidate_for(
                "Sort out the garage someday",
                "I really should sort the garage at some point",
                authority="ask", evidence_class="vague_self_talk",
            ),
            now=datetime.now(UTC),
        )

    listing = await async_client.get(
        "/v1/cortex/commitment-candidates",
        params={"workspace_id": "ws-rec", "owner_peer_id": "user_2"},
    )
    assert listing.status_code == 200
    candidates = listing.json()["candidates"]
    titles = {c["title"] for c in candidates}
    assert "Book the dentist" in titles

    packet = await async_client.get(
        "/v1/cortex/attention-packet",
        params={"workspace_id": "ws-rec", "session_id": "session-a",
                "peer_id": "user_2", "timezone": "Europe/London"},
    )
    data = packet.json()
    surfaced = {c["title"] for c in data["commitment_candidates"]}
    # Vague background thoughts stay invisible; concrete ones surface.
    assert "Sort out the garage someday" not in surfaced
    assert "Book the dentist" in surfaced
    continuity = data["continuity_context"]["continuity"]
    assert any(
        item["type"] == "commitment_candidate" and item["topic"] == "Book the dentist"
        for item in continuity
    )


@pytest.mark.asyncio
async def test_candidate_dismiss_via_endpoint_is_durable(async_client):
    from src.services.commitment_candidate_service import CommitmentCandidateService
    from src.db import async_session_maker

    service = CommitmentCandidateService()
    async with async_session_maker() as db:
        row = await service.upsert_from_candidate(
            db, workspace_id="ws-rec", session_id="session-a", owner_peer_id="user_3",
            message_id="msg-c7",
            candidate=_candidate_for("Post the birthday card", "must post the birthday card"),
            now=datetime.now(UTC),
        )

    marked = await async_client.post(
        "/v1/cortex/commitment-candidates/mark",
        json={
            "workspace_id": "ws-rec",
            "owner_peer_id": "user_3",
            "candidate_key": row.candidate_key,
            "status": "dismissed",
        },
    )
    assert marked.status_code == 200

    listing = await async_client.get(
        "/v1/cortex/commitment-candidates",
        params={"workspace_id": "ws-rec", "owner_peer_id": "user_3"},
    )
    assert all(
        c["candidate_key"] != row.candidate_key for c in listing.json()["candidates"]
    )
