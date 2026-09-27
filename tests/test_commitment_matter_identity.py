"""Regression coverage for commitment same-matter identity: one real-world
obligation accumulating evidence rather than multiplying active
representations of itself (school-trip: "pay school money" / "pay for
school trip").

Generalises the OpenLoop matter-identity principle (entity identity gates
before any semantic step; lexical overlap is never sole authority) rather
than copying its implementation: commitment semantics differ (a DISMISSED/
FULFILLED/VIOLATED/MATERIALIZED row must never silently absorb new evidence,
so only PENDING rows are eligible), and confirmation uses the new
`same_matter` semantic-judge question rather than a lexical threshold, so
poor lexical overlap (paraphrase, cross-language) does not defeat it and
same-actor-different-topic does not falsely trigger it.
"""
from datetime import datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.commitment_candidate import CommitmentCandidate, CommitmentCandidateAuthority
from src.routers import v1_events
from src.schemas.candidate import ExtractionCandidate
from src.services import semantic_judge

UTC = timezone.utc


class _ScriptedMatterAdapter:
    def __init__(self, verdict_for):
        self.verdict_for = verdict_for
        self.calls = []

    async def generate_structured(self, *, system, prompt, model_id, **kw):
        earlier = prompt.split("EARLIER:\n", 1)[1].split("\n\nLATER:")[0] if "EARLIER:\n" in prompt else ""
        later = prompt.split("LATER:\n", 1)[1] if "LATER:\n" in prompt else ""
        for stop in ("\nCONTEXT:", "\nRules:"):
            if stop in later:
                later = later.split(stop)[0]
                break
        later = later.strip()
        self.calls.append((earlier.strip(), later))
        verdict = self.verdict_for(earlier.strip(), later)
        span = later[:40] if verdict == "yes" else ""
        return {"verdict": verdict, "confidence": 0.85 if verdict == "yes" else 0.8,
                "evidence_span": span, "rationale": "test"}


def _commitment_candidate(*, key: str, text: str, title: str, refs: list) -> ExtractionCandidate:
    return ExtractionCandidate(
        candidate_key=key,
        observation=text,
        raw_evidence=text,
        canonical_title=title,
        operational_kind="commitment_candidate",
        evidence_class="implicit_self_commitment",
        authority="act",
        subject_refs=refs,
        temporal_phrase="tomorrow",
        confidence=0.9,
        formation="explicit",
        extractor_version="matter-identity-regression",
    )


async def _send(async_client, monkeypatch, *, workspace_id: str, sender: str,
                message_id: str, candidate: ExtractionCandidate, adapter=None):
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
            "honcho_message_id": message_id, "peer_id": sender,
            "text": candidate.observation, "now": "2026-09-28T10:00:00+01:00",
            "timezone": "Europe/London",
        },
    )
    assert response.status_code == 202, response.text


async def _commitments(workspace_id: str):
    async with async_session_maker() as db:
        return (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
        ).order_by(CommitmentCandidate.created_at))).scalars().all()


# ── A1: same obligation, different wording ──────────────────────────────────

@pytest.mark.asyncio
async def test_a1_paraphrased_same_obligation_accumulates_on_one_row(async_client, monkeypatch):
    ws = "ws-matter-school-a1"
    adapter = _ScriptedMatterAdapter(lambda earlier, later: "yes")
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's school money tomorrow.",
            title="pay Andree's school money", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="Pay for school trip.",
            title="pay for school trip", refs=["Andree"]),
        adapter=adapter,
    )
    rows = await _commitments(ws)
    assert len(rows) == 1, [r.title for r in rows]
    assert rows[0].source_message_id == "m2"
    assert "school trip" in rows[0].evidence_verbatim.lower()
    assert "andree" in rows[0].evidence_verbatim.lower() or "school money" in rows[0].evidence_verbatim.lower()
    # A same_matter judge call happened (earlier=the existing row's title);
    # a second call for self_undertaking is expected too since "Pay for
    # school trip." carries no first-person marker — that is Problem B's
    # mechanism confirming the same evidence, not a flaw in this test.
    assert ("pay Andree's school money", "pay for school trip") in adapter.calls


# ── A2: same obligation across messages accumulates, no proliferation ──────

@pytest.mark.asyncio
async def test_a2_later_urgency_evidence_accumulates_no_sibling(async_client, monkeypatch):
    ws = "ws-matter-school-a2"
    adapter = _ScriptedMatterAdapter(lambda earlier, later: "yes")
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's school money tomorrow.",
            title="pay Andree's school money", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="Don't let me forget the school trip money.",
            title="school trip money", refs=["Andree"]),
        adapter=adapter,
    )
    rows = await _commitments(ws)
    assert len(rows) == 1, [r.title for r in rows]


# ── A3: genuine distinct obligations, same actor, must stay distinct ───────

@pytest.mark.asyncio
async def test_a3_distinct_obligations_same_actor_stay_separate(async_client, monkeypatch):
    ws = "ws-matter-school-a3"
    # Judge correctly distinguishes: same person, different obligation.
    adapter = _ScriptedMatterAdapter(lambda earlier, later: "no")
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's school trip money tomorrow.",
            title="pay Andree's school trip money", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="I need to sign Andree's permission form tomorrow.",
            title="sign Andree's permission form", refs=["Andree"]),
        adapter=adapter,
    )
    rows = await _commitments(ws)
    assert len(rows) == 2, [r.title for r in rows]


# ── A4: poor lexical overlap / non-English — not lexically dependent ───────

@pytest.mark.asyncio
async def test_a4_poor_lexical_overlap_still_recognised_via_judge(async_client, monkeypatch):
    """No shared English content words at all between the two observations
    beyond the entity name; only the judge (standing in for genuine semantic
    understanding, including cross-language) can recognise sameness."""
    ws = "ws-matter-school-a4"
    adapter = _ScriptedMatterAdapter(lambda earlier, later: "yes")
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's school money tomorrow.",
            title="pay Andree's school money", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="Necesito pagar la excursión de Andree mañana.",
            title="pagar la excursión de Andree", refs=["Andree"]),
        adapter=adapter,
    )
    rows = await _commitments(ws)
    assert len(rows) == 1, [r.title for r in rows]


# ── A5: ambiguous identity — do not guess ───────────────────────────────────

@pytest.mark.asyncio
async def test_a5_ambiguous_identity_stays_distinct_not_merged(async_client, monkeypatch):
    """Two entity-linked PENDING candidates both plausibly match: the judge
    confirms more than one, so nothing is merged — ambiguity is preserved,
    not guessed."""
    ws = "ws-matter-school-a5"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's trip deposit tomorrow.",
            title="pay Andree's trip deposit", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="I need to pay Andree's trip balance tomorrow.",
            title="pay Andree's trip balance", refs=["Andree"]),
    )
    adapter = _ScriptedMatterAdapter(lambda earlier, later: "yes")  # confirms BOTH -> ambiguous
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m3",
        candidate=_commitment_candidate(
            key="c3", text="I need to pay for Andree's trip tomorrow.",
            title="pay for Andree's trip", refs=["Andree"]),
        adapter=adapter,
    )
    rows = await _commitments(ws)
    assert len(rows) == 3, [r.title for r in rows]


@pytest.mark.asyncio
async def test_no_adapter_creates_distinct_row_never_guesses(async_client, monkeypatch):
    """Documented limitation: without a configured judge adapter, entity
    identity alone is not sufficient to merge — the safe default is a new,
    distinct row."""
    ws = "ws-matter-school-no-adapter"
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's school money tomorrow.",
            title="pay Andree's school money", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="Pay for school trip.",
            title="pay for school trip", refs=["Andree"]),
    )
    rows = await _commitments(ws)
    assert len(rows) == 2, [r.title for r in rows]


@pytest.mark.asyncio
async def test_no_shared_entity_never_merges_on_content_alone(async_client, monkeypatch):
    """No resolvable subject_refs on the second candidate: identity check is
    skipped entirely (safe default), even with a judge configured that
    would say yes if asked — the entity gate is REQUIRED, not optional."""
    ws = "ws-matter-school-no-entity"
    adapter = _ScriptedMatterAdapter(lambda earlier, later: "yes")
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m1",
        candidate=_commitment_candidate(
            key="c1", text="I need to pay Andree's school money tomorrow.",
            title="pay Andree's school money", refs=["Andree"]),
    )
    await _send(
        async_client, monkeypatch, workspace_id=ws, sender="ashley", message_id="m2",
        candidate=_commitment_candidate(
            key="c2", text="Pay for school trip.",
            title="pay for school trip", refs=[]),
        adapter=adapter,
    )
    rows = await _commitments(ws)
    assert len(rows) == 2, [r.title for r in rows]
    # No same_matter call was made (earlier=the existing row's title never
    # appears): the entity gate short-circuited before any judge call for
    # matter identity, regardless of an adapter being configured. A
    # self_undertaking call is separately expected (Problem B, unrelated
    # to this test's concern) since "Pay for school trip." has no
    # first-person marker.
    assert not any(call[0] == "pay Andree's school money" for call in adapter.calls)
