"""Regression coverage for semantic actor attribution on commitment
candidates: "who undertakes this action?" beyond a first-person-pronoun
regex.

The deterministic `_FIRST_PERSON_COMMITMENT_RE` floor (previous tranche) is
a cheap hard-boundary guard for the common, unambiguous case only — it is
explicitly NOT semantic authority (Spark audit). It cannot recognise
indirect self-commitment ("leave it with me"), named-self reference
("Mukesh will sort it" when Mukesh is the sender), non-English phrasing, or
a literal first-person marker sitting inside a quotation (which is NOT the
sender's own commitment). Those are resolved by the new `self_undertaking`
semantic-judge question, using owner identity as structured context rather
than a name special-case. The marker only ever SKIPS that model call when it
already agrees (cheap-signal-first, per the pendulum check); it never
overrides a judge verdict.
"""
from datetime import datetime, timezone

import pytest

from src.db import async_session_maker
from sqlmodel import select

from src.models.commitment_candidate import CommitmentCandidate, CommitmentCandidateAuthority
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services import semantic_judge

UTC = timezone.utc


class _ScriptedActorAdapter:
    """Verdict decided by a caller-supplied predicate over the LATER text —
    stands in for a real semantic judge's meaning-based verdict, the same
    pattern as tests/test_semantic_pipeline.py's FakeAdapter."""

    def __init__(self, verdict_for):
        self.verdict_for = verdict_for
        self.calls = []

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        later = prompt.split("LATER:\n", 1)[1] if "LATER:\n" in prompt else ""
        for stop in ("\nCONTEXT:", "\nRules:"):
            if stop in later:
                later = later.split(stop)[0]
                break
        later = later.strip()
        self.calls.append(later)
        verdict = self.verdict_for(later, prompt)
        span = later[:40] if verdict == "yes" else ""
        return {"verdict": verdict, "confidence": 0.85 if verdict == "yes" else 0.8,
                "evidence_span": span, "rationale": "test"}


def _commitment_candidate(*, key: str, text: str, title: str,
                         is_quoted: bool = False, is_reported_speech: bool = False,
                         actor_peer_id=None) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key,
        observation=text,
        raw_evidence=text,
        canonical_title=title,
        operational_kind="commitment_candidate",
        evidence_class="implicit_self_commitment",
        authority="act",
        temporal_phrase="tomorrow",
        confidence=0.9,
        formation="explicit",
        extractor_version="actor-attribution-regression",
        is_quoted=is_quoted,
        is_reported_speech=is_reported_speech,
        actor_peer_id=actor_peer_id,
    )


async def _ingest(async_client, monkeypatch, *, workspace_id: str, sender: str,
                  candidate: ExtractionCandidate, adapter=None) -> CommitmentCandidate:
    if adapter is not None:
        monkeypatch.setattr(semantic_judge, "_adapter", lambda: adapter)
    monkeypatch.setattr(
        v1_events.turn_extractor, "extract_candidates",
        lambda *args, **kwargs: [candidate],
    )
    response = await async_client.post(
        "/v1/events/turn",
        json={
            "workspace_id": workspace_id, "session_id": "session-1",
            "honcho_message_id": "message-1", "peer_id": sender,
            "text": candidate.observation, "now": "2026-09-28T10:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text
    async with async_session_maker() as db:
        return (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
        ))).scalar_one()


# ── B1: genuine direct user commitment — cheap marker, no judge call ───────

@pytest.mark.asyncio
async def test_b1_direct_first_person_stays_act_without_judge_call(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "no")  # would be WRONG if called
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b1", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="I'll send the document tomorrow.", title="send the document"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ACT
    assert adapter.calls == []  # cheap marker resolved it; no model call spent


# ── B2: indirect user commitment — needs the judge ─────────────────────────

@pytest.mark.asyncio
async def test_b2_indirect_self_commitment_confirmed_by_judge(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "yes")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b2", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="Leave the invoice with me.", title="handle the invoice"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ACT
    assert len(adapter.calls) == 1


# ── B3: named-self formulation — owner identity as context, no name special-case ─

@pytest.mark.asyncio
async def test_b3_named_self_reference_confirmed_via_owner_context(async_client, monkeypatch):
    def verdict(later, prompt):
        # A real judge would use the CONTEXT block naming the sender; this
        # stand-in checks the mechanism actually PASSES that context through.
        return "yes" if "mukesh" in prompt.lower() else "no"
    adapter = _ScriptedActorAdapter(verdict)
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b3", sender="mukesh",
        candidate=_commitment_candidate(
            key="c1", text="Mukesh will sort it tomorrow.", title="sort it"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ACT


# ── B4: third-party action — must not become user ACT ──────────────────────

@pytest.mark.asyncio
async def test_b4_third_party_action_stays_ask(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "no")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b4", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="Sam said he'd send the revised contract.",
            title="send the revised contract"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ASK


# ── B5: third-party need/reference — nobody committed ───────────────────────

@pytest.mark.asyncio
async def test_b5_third_party_need_stays_ask(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "no")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b5", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="Sam needs to send the revised contract.",
            title="send the revised contract"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ASK


# ── B6: quotation defeats the literal marker ────────────────────────────────

@pytest.mark.asyncio
async def test_b6_quoted_first_person_does_not_imply_user_actor(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "no")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b6", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="She literally said, 'I'll send it tomorrow.'",
            title="send it", is_quoted=True),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ASK
    assert len(adapter.calls) == 1  # the marker's literal "I'll" did NOT short-circuit


@pytest.mark.asyncio
async def test_b6b_reported_speech_flag_defeats_marker_even_without_quotes(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "no")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b6b", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="She said I'll send it tomorrow, apparently.",
            title="send it", is_reported_speech=True),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ASK
    assert len(adapter.calls) == 1


# ── B7: ambiguous actor — do not fabricate ownership ────────────────────────

@pytest.mark.asyncio
async def test_b7_ambiguous_actor_stays_ask_not_fabricated(async_client, monkeypatch):
    adapter = _ScriptedActorAdapter(lambda later, prompt: "unclear")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b7", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="Should get that sent tomorrow.", title="get that sent"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ASK


# ── B8: paraphrase/multilingual/noisy — not lexically dependent ────────────

@pytest.mark.asyncio
async def test_b8_non_english_indirect_commitment_confirmed_by_judge(async_client, monkeypatch):
    """No English first-person token appears anywhere in the evidence; the
    marker regex cannot fire, so this must route to the judge and succeed
    on meaning, proving the mechanism is not merely English-token
    recognition."""
    adapter = _ScriptedActorAdapter(lambda later, prompt: "yes")
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-b8", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="Voy a hacerlo mañana.", title="hacerlo"),
        adapter=adapter,
    )
    assert row.authority == CommitmentCandidateAuthority.ACT
    assert len(adapter.calls) == 1


@pytest.mark.asyncio
async def test_no_adapter_fails_closed_to_ask(async_client, monkeypatch):
    """Documented limitation: without a configured judge adapter, indirect/
    non-English self-commitments cannot be recognised and fail closed to
    ASK rather than guessing ACT."""
    row = await _ingest(
        async_client, monkeypatch, workspace_id="ws-actor-no-adapter", sender="ashley",
        candidate=_commitment_candidate(
            key="c1", text="Leave the invoice with me.", title="handle the invoice"),
    )
    assert row.authority == CommitmentCandidateAuthority.ASK
