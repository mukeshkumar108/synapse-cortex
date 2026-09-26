"""Regression coverage for counterparty promises crossing the commitment sink.

External senders remain useful longitudinal evidence, but their first-person
promises are not commitments owned by the user or companion.
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
from src.services.commitment_candidate_service import CommitmentCandidateService


def _commitment_candidate(*, sender: str, text: str, title: str) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=f"c_{sender}",
        observation=text,
        raw_evidence=text,
        canonical_title=title,
        operational_kind="commitment_candidate",
        actor_peer_id=sender,
        subject_peer_id=sender,
        evidence_class="character_promise",
        authority="act",
        temporal_phrase="tomorrow",
        confidence=0.95,
        formation="explicit",
        extractor_version="counterparty-regression",
    )


async def _ingest_candidate(async_client, monkeypatch, *, workspace_id: str,
                            sender: str, text: str, title: str,
                            evidence_class: str = "character_promise") -> CommitmentCandidate:
    candidate = _commitment_candidate(
        sender=sender, text=text, title=title
    ).model_copy(update={"evidence_class": evidence_class})
    monkeypatch.setattr(
        v1_events.turn_extractor,
        "extract_candidates",
        lambda *args, **kwargs: [candidate],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": workspace_id,
            "session_id": "session-1",
            "honcho_message_id": "message-1",
            "peer_id": sender,
            "text": text,
            "now": "2026-09-22T10:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text
    async with async_session_maker() as db:
        rows = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id
        ))).scalars().all()
        assert len(rows) == 1
        return rows[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("workspace_id", "sender", "text", "title"),
    [
        (
            "ws-external-payment",
            "external:carlos",
            "I'll send the payment tomorrow.",
            "Send the payment tomorrow",
        ),
        (
            "ws-external-signature",
            "external:studio_sam",
            "I'll send the signature copy tomorrow.",
            "Send the signature copy tomorrow",
        ),
    ],
)
async def test_external_promise_stays_non_actionable_longitudinal_evidence(
    async_client, monkeypatch, workspace_id, sender, text, title
):
    row = await _ingest_candidate(
        async_client,
        monkeypatch,
        workspace_id=workspace_id,
        sender=sender,
        text=text,
        title=title,
    )
    assert row.owner_peer_id == sender
    assert row.title == title
    assert row.evidence_verbatim == text
    assert row.evidence_class == "counterparty_promise"
    assert row.authority == CommitmentCandidateAuthority.ASK
    assert row.status == CommitmentCandidateStatus.PENDING

    async with async_session_maker() as db:
        corroborated = _commitment_candidate(
            sender=sender,
            text=text,
            title=title,
        ).model_copy(update={
            "candidate_key": f"c_{sender}_corroborated",
            "evidence_class": "explicit_acceptance",
            "authority": "act",
        })
        refreshed = await CommitmentCandidateService().upsert_from_candidate(
            db,
            workspace_id=workspace_id,
            session_id="session-1",
            owner_peer_id=sender,
            message_id="message-2",
            candidate=corroborated,
            now=datetime(2026, 9, 23, 12, 0, tzinfo=timezone.utc),
        )
        assert refreshed.authority == CommitmentCandidateAuthority.ASK
        assert refreshed.evidence_class == "counterparty_promise"
        violated = await CommitmentCandidateService().evaluate_due(
            db,
            workspace_id=workspace_id,
            now=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
        )
        assert violated == []
        after_due = await db.get(CommitmentCandidate, row.id)
        assert after_due.status == CommitmentCandidateStatus.PENDING


@pytest.mark.asyncio
async def test_user_owned_actionable_commitment_keeps_existing_lifecycle(
    async_client, monkeypatch
):
    row = await _ingest_candidate(
        async_client,
        monkeypatch,
        workspace_id="ws-user-commitment",
        sender="kai",
        text="I'll confirm the chairs tomorrow.",
        title="Confirm the chairs tomorrow",
        evidence_class="implicit_self_commitment",
    )
    assert row.owner_peer_id == "kai"
    assert row.evidence_class == "implicit_self_commitment"
    assert row.authority == CommitmentCandidateAuthority.ACT
    assert row.status == CommitmentCandidateStatus.PENDING

    async with async_session_maker() as db:
        violated = await CommitmentCandidateService().evaluate_due(
            db,
            workspace_id="ws-user-commitment",
            now=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
        )
        assert violated == [row.id]
        refreshed = await db.get(CommitmentCandidate, row.id)
        assert refreshed.status == CommitmentCandidateStatus.VIOLATED


@pytest.mark.asyncio
async def test_user_reported_third_party_promise_does_not_inherit_user_authority(
    async_client, monkeypatch
):
    """Scenario-3 shape: unknown actor attribution falls back to the sender,
    but the reported promise must still not become the sender's obligation."""
    text = "Sam from the studio said he'd send the revised contract today."
    candidate = _commitment_candidate(
        sender="studio_sam",
        text=text,
        title="Send revised contract",
    ).model_copy(update={
        "actor_peer_id": "studio_sam",
        "evidence_class": "implicit_self_commitment",
        "temporal_phrase": "today",
    })
    monkeypatch.setattr(
        v1_events.turn_extractor,
        "extract_candidates",
        lambda *args, **kwargs: [candidate],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws-reported-counterparty",
            "session_id": "session-1",
            "honcho_message_id": "message-1",
            "peer_id": "kai",
            "text": text,
            "now": "2026-09-22T10:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text

    async with async_session_maker() as db:
        row = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == "ws-reported-counterparty"
        ))).scalar_one()
        # Ghost actors still fall back safely; semantic authority does not.
        assert row.owner_peer_id == "kai"
        assert row.evidence_class == "counterparty_promise"
        assert row.authority == CommitmentCandidateAuthority.ASK
        violated = await CommitmentCandidateService().evaluate_due(
            db,
            workspace_id="ws-reported-counterparty",
            now=datetime(2026, 9, 25, 12, 0, tzinfo=timezone.utc),
        )
        assert violated == []
