"""Regression coverage for expectation agency/ownership coherence.

Companion commitments already had this boundary fixed
(test_counterparty_commitment_authority.py): an external sender's own
first-person promise cannot inherit user/companion action authority. The
same incoherence existed one layer up, in the expectation sink: a row could
be persisted with owner_peer_id="external:<sender>" (correct provenance)
while carrying ExpectationType.USER_INTENTION and title text asserting "the
user will..." (an extractor free-text hint, untouched by ownership). These
tests pin the fix: ownership authority (the ingest-adapter-supplied
"external:" prefix) overrides the extractor's self-reported type for the
two types that assert the user/companion as the acting party
(USER_INTENTION, USER_COMMITMENT), remapping them to the existing
EXTERNAL_DEPENDENCY type — never a new ontology, never a names/fixture
special case.
"""
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services.expectation_shaper import ExpectationShaper

shaper = ExpectationShaper()


def _expectation_candidate(*, sender: str, text: str, title: str,
                           hint: str = "user_intention") -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=f"c_{sender}",
        observation=text,
        raw_evidence=text,
        canonical_title=title,
        operational_kind="expectation",
        expectation_type_hint=hint,
        actor_peer_id=sender,
        subject_peer_id=sender,
        temporal_phrase="tomorrow",
        confidence=0.95,
        formation="explicit",
        extractor_version="agency-regression",
    )


async def _ingest_candidate(async_client, monkeypatch, *, workspace_id: str,
                            sender: str, candidate: ExtractionCandidate,
                            message_id: str = "message-1") -> Expectation:
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
            "honcho_message_id": message_id,
            "peer_id": sender,
            "text": candidate.observation,
            "now": "2026-09-28T12:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text
    async with async_session_maker() as db:
        return (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_message_id == message_id,
        ))).scalar_one()


# ── Case 1: external counterparty future action (unit) ──────────────────────

def test_external_first_person_promise_is_not_user_intention():
    """'I'll send the signature copy tomorrow.' authored by the external
    sender directly (not reported by the user) must not become
    USER_INTENTION merely because the extractor hinted it that way, and the
    derived title must attribute the action to the authoritative owner
    rather than leaving a bare, actor-less action phrase."""
    cand = _expectation_candidate(
        sender="external:studio_sam",
        text="I'll send the signature copy tomorrow.",
        title="Send the signature copy",
    )
    shaped = shaper.shape_expectation(
        cand, "external:studio_sam", owner_peer_id="external:studio_sam",
    )
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.EXTERNAL_DEPENDENCY
    assert shaped["subject_peer_id"] == "external:studio_sam"
    assert shaped["title"] == "Studio Sam will send the signature copy"


def test_external_counterparty_user_commitment_hint_also_remapped():
    cand = _expectation_candidate(
        sender="external:carlos",
        text="I'll pay you back tomorrow.",
        title="Pay you back",
        hint="user_commitment",
    )
    shaped = shaper.shape_expectation(
        cand, "external:carlos", owner_peer_id="external:carlos",
    )
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.EXTERNAL_DEPENDENCY
    assert shaped["title"] == "Carlos will pay you back"


# ── Case 2: genuine user intention (unit) — must be unaffected ─────────────

def test_genuine_user_intention_unaffected():
    cand = _expectation_candidate(
        sender="kai",
        text="I'll send the document tomorrow.",
        title="Send the document",
    )
    shaped = shaper.shape_expectation(cand, "kai", owner_peer_id="kai")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.USER_INTENTION
    assert shaped["subject_peer_id"] == "kai"


def test_owner_peer_id_omitted_preserves_prior_behavior():
    """Callers that do not pass owner_peer_id (existing call sites/tests)
    keep exactly the prior behavior: derived from actor/subject fallback,
    same as before this change."""
    cand = _expectation_candidate(
        sender="user-1", text="I'll do something tomorrow.", title="Do something",
    )
    shaped = shaper.shape_expectation(cand, "user-1")
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.USER_INTENTION


# ── Case D: ambiguous/unresolved actor — never fabricate an owner ──────────

def test_no_confident_external_owner_does_not_rewrite_title():
    """When ownership cannot be confidently resolved as external (no
    owner_peer_id, no actor_peer_id — falls back to a generic user-scoped
    subject), the type stays as hinted and the title is left exactly as
    extracted: no owner is fabricated onto a row we cannot attribute."""
    cand = _expectation_candidate(
        sender="user-1", text="I'll send the document tomorrow.",
        title="Send the document",
    ).model_copy(update={"actor_peer_id": None, "subject_peer_id": None})
    shaped = shaper.shape_expectation(cand, "user-1", owner_peer_id=None)
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.USER_INTENTION
    assert shaped["title"] == "Send the document"


def test_external_owner_without_recognizable_actor_phrasing_leaves_title_alone():
    """The extractor's free-text observation doesn't always take the
    recognized 'I'll .../the user will ...' shape. When we cannot
    deterministically isolate a bare action clause, we must not fabricate a
    reconstruction (STOP-clause behavior: leave title as extracted rather
    than guess)."""
    cand = _expectation_candidate(
        sender="external:studio_sam",
        text="Final signature copy pending tomorrow.",
        title="Final signature copy pending",
        hint="user_intention",
    )
    shaped = shaper.shape_expectation(
        cand, "external:studio_sam", owner_peer_id="external:studio_sam",
    )
    assert shaped is not None
    assert shaped["expectation_type"] == ExpectationType.EXTERNAL_DEPENDENCY
    # No actor-assertion prefix was present to strip, so no reconstruction:
    # the title is left as the cleaned observation (existing trailing-
    # temporal-phrase stripping still applies, unrelated to this fix).
    assert shaped["title"] == "Final signature copy pending"


# ── Integration: persisted rows via /v1/events/turn ─────────────────────────

@pytest.mark.asyncio
async def test_case1_external_promise_persists_as_external_dependency(
    async_client, monkeypatch,
):
    row = await _ingest_candidate(
        async_client, monkeypatch,
        workspace_id="ws-expectation-external-sam",
        sender="external:studio_sam",
        candidate=_expectation_candidate(
            sender="external:studio_sam",
            text="I'll send the signature copy tomorrow.",
            title="Send the signature copy",
        ),
    )
    assert row.owner_peer_id == "external:studio_sam"
    assert row.subject_peer_id == "external:studio_sam"
    assert row.expectation_type == ExpectationType.EXTERNAL_DEPENDENCY
    assert row.title == "Studio Sam will send the signature copy"
    assert row.summary.startswith("Expected from another: Studio Sam will send")
    assert row.outcome_state == OutcomeState.UNKNOWN


@pytest.mark.asyncio
async def test_case2_genuine_user_intention_persists_unchanged(
    async_client, monkeypatch,
):
    row = await _ingest_candidate(
        async_client, monkeypatch,
        workspace_id="ws-expectation-genuine-user",
        sender="kai",
        candidate=_expectation_candidate(
            sender="kai",
            text="I'll send the document tomorrow.",
            title="Send the document",
        ),
    )
    assert row.owner_peer_id == "kai"
    assert row.subject_peer_id == "kai"
    assert row.expectation_type == ExpectationType.USER_INTENTION
    assert row.title == "Send the document"


@pytest.mark.asyncio
async def test_case3_external_promise_later_fulfilled_by_evidence(
    async_client, monkeypatch,
):
    """Counterparty promise exists (Case 1), then later evidence shows they
    did the thing. Lifecycle transition uses existing type-agnostic
    reconciliation (handle_outcome_mutations / _resolve_targets by
    target_id) — no user-agency rewriting, no lingering false obligation."""
    row = await _ingest_candidate(
        async_client, monkeypatch,
        workspace_id="ws-expectation-external-fulfilled",
        sender="external:studio_sam",
        candidate=_expectation_candidate(
            sender="external:studio_sam",
            text="I'll send the signature copy tomorrow.",
            title="Send the signature copy",
        ),
        message_id="message-1",
    )
    assert row.expectation_type == ExpectationType.EXTERNAL_DEPENDENCY
    assert row.title == "Studio Sam will send the signature copy"
    assert row.outcome_state == OutcomeState.UNKNOWN

    fulfilling = ExtractionCandidate(
        candidate_key="c_fulfil",
        observation="Final copy attached for signature.",
        raw_evidence="Apologies for the delay. Final copy attached for signature.",
        operational_kind="event",
        actor_peer_id="external:studio_sam",
        confidence=0.95,
        formation="explicit",
        extractor_version="agency-regression",
        resolution_hint={"target_id": str(row.id), "action": "fulfill",
                         "target_kind": "expectation"},
    )
    monkeypatch.setattr(
        v1_events.turn_extractor,
        "extract_candidates",
        lambda *args, **kwargs: [fulfilling],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws-expectation-external-fulfilled",
            "session_id": "session-1",
            "honcho_message_id": "message-2",
            "peer_id": "external:studio_sam",
            "text": fulfilling.observation,
            "now": "2026-09-30T07:15:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text

    async with async_session_maker() as db:
        refreshed = await db.get(Expectation, row.id)
        assert refreshed.outcome_state == OutcomeState.FULFILLED
        # Fulfilment evidence closes the row; ownership is not rewritten
        # onto the user or companion by the act of closing it.
        assert refreshed.owner_peer_id == "external:studio_sam"
        assert refreshed.expectation_type == ExpectationType.EXTERNAL_DEPENDENCY
        assert refreshed.title == "Studio Sam will send the signature copy"


@pytest.mark.asyncio
async def test_case4_no_definitive_evidence_stays_open_not_prematurely_closed(
    async_client, monkeypatch,
):
    """No fulfilment evidence arrives: the counterparty matter must remain
    longitudinally available (UNKNOWN), never silently closed."""
    row = await _ingest_candidate(
        async_client, monkeypatch,
        workspace_id="ws-expectation-external-pending",
        sender="external:carlos",
        candidate=_expectation_candidate(
            sender="external:carlos",
            text="I'll pay you back tomorrow.",
            title="Pay you back",
        ),
    )
    assert row.expectation_type == ExpectationType.EXTERNAL_DEPENDENCY
    assert row.outcome_state == OutcomeState.UNKNOWN

    # An unrelated later turn from the same sender must not incidentally
    # close the pending counterparty matter.
    unrelated = ExtractionCandidate(
        candidate_key="c_unrelated",
        observation="Hope you're having a good week.",
        operational_kind="semantic_only",
        actor_peer_id="external:carlos",
        confidence=0.9,
        extractor_version="agency-regression",
    )
    monkeypatch.setattr(
        v1_events.turn_extractor,
        "extract_candidates",
        lambda *args, **kwargs: [unrelated],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": "ws-expectation-external-pending",
            "session_id": "session-1",
            "honcho_message_id": "message-2",
            "peer_id": "external:carlos",
            "text": unrelated.observation,
            "now": "2026-09-29T09:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text

    async with async_session_maker() as db:
        refreshed = await db.get(Expectation, row.id)
        assert refreshed.outcome_state == OutcomeState.UNKNOWN
        assert refreshed.owner_peer_id == "external:carlos"
