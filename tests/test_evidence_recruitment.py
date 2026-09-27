"""Evidence-recruitment fixtures: self-resolution before escalation.

Behavioural contract (Canon 12-13): when lifecycle reconciliation is
ambiguous on current evidence alone, Cortex may recruit targeted history,
re-judge with it, and reconcile only on a single grounded winner. Otherwise
it holds PENDING/OPEN. No fixture here mints a clarification; no keyword
list decides anything (overlap only retrieves).

All model judgement runs through stub adapters; all history through stub
providers (no network). Deterministic control is real.
"""

import pytest
from datetime import datetime, timezone

from sqlmodel import select

from src.db import async_session_maker
from src.models.clarification import ClarificationCandidate
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import ExtractionTrace
from src.models.semantic import SemanticClaim, SemanticRelation
from src.services.evidence_recruitment import HistoryHit
from src.services.semantic_reconciliation import reconcile_turn


class CannedAdapter:
    """Canned verdict; span taken verbatim from LATER (current text)."""

    def __init__(self, verdict="yes", confidence=0.85, span_chars=30):
        self.verdict = verdict
        self.confidence = confidence
        self.span_chars = span_chars
        self.calls = 0

    async def generate_structured(self, *, system, prompt, json_schema,
                                  model_id, **kw):
        self.calls += 1
        later = prompt.split("LATER:\n", 1)[1] if "LATER:\n" in prompt else ""
        for stop in ("\nCONTEXT:", "\nRules:", "\n\nRules:"):
            if stop in later:
                later = later.split(stop)[0]
                break
        span = later.strip()[: self.span_chars]
        return {"verdict": self.verdict, "confidence": self.confidence,
                "evidence_span": span, "rationale": "fixture rationale"}


class NeedsHistoryAdapter(CannedAdapter):
    """Unclear on current evidence alone; decides once recruited history
    carrying `marker` arrives as CONTEXT. Models the judge that cannot
    ground from the turn text but can with prior evidence."""

    def __init__(self, marker, **kw):
        super().__init__(**kw)
        self.marker = marker.lower()

    async def generate_structured(self, *, system, prompt, json_schema,
                                  model_id, **kw):
        self.calls += 1
        context = ""
        if "\nCONTEXT:\n" in prompt:
            context = prompt.split("\nCONTEXT:\n", 1)[1]
            for stop in ("\n\nRules:", "\nRules:"):
                if stop in context:
                    context = context.split(stop)[0]
                    break
        if self.marker in context.lower():
            later = prompt.split("LATER:\n", 1)[1] if "LATER:\n" in prompt else ""
            for stop in ("\nCONTEXT:", "\nRules:", "\n\nRules:"):
                if stop in later:
                    later = later.split(stop)[0]
                    break
            span = later.strip()[: self.span_chars]
            return {"verdict": "yes", "confidence": self.confidence,
                    "evidence_span": span, "rationale": "grounded via history"}
        return {"verdict": "unclear", "confidence": 0.5,
                "evidence_span": "", "rationale": "insufficient grounding"}


def stub_provider(hits, calls):
    async def provide(workspace_id, session_id, peer_id, query, limit):
        calls.append({"query": query, "limit": limit})
        return list(hits)
    return provide


async def clarifications_in(db, ws):
    return (await db.execute(select(ClarificationCandidate).where(
        ClarificationCandidate.honcho_workspace_id == ws))).scalars().all()


@pytest.mark.asyncio
async def test_same_matter_different_wording_resolves_via_history():
    """'Carlos still owes me' + 'The transfer never arrived' share only
    {transfer, still}: too poor to ground, enough to retrieve. History
    bridges the vocabulary gap; the matter resolves with provenance."""
    from src.services import evidence_recruitment

    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id="ws-recruit-1", honcho_session_id="s1",
            honcho_message_id="m1", title="Carlos still owes me",
            summary="Carlos owes the dinner balance, transfer expected Friday"))
        await db.commit()
        hits = [HistoryHit(
            text="Carlos said he would transfer the dinner balance on Friday",
            provenance="honcho_peer:carlos:msg-9@s0",
            source="peer_search")]
        calls: list = []
        out = await reconcile_turn(
            db, workspace_id="ws-recruit-1", session_id="s1", message_id="m2",
            text="The transfer never arrived in my account, still waiting on it.",
            peer_id="ashley", now=datetime.now(timezone.utc), closed_loop_ids=[],
            adapter=NeedsHistoryAdapter("carlos"),
            history_provider=stub_provider(hits, calls))
        # One retrieval, one re-judge: bounded cost, then a single winner.
        assert len(calls) == 1
        assert len(calls[0]["query"]) <= 500
        assert "carlos" in calls[0]["query"].lower()
        assert out.get("recruited") == 1
        assert out.get("recruit_accepted") == 1
        assert out["closed"] == 1
        loop = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == "ws-recruit-1"))).scalar_one()
        assert loop.status == OpenLoopStatus.RESOLVED
        assert "#recruited:honcho_peer:carlos:msg-9@s0" in (
            loop.resolution_evidence or "")
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == "ws-recruit-1")
        )).scalars().all()
        assert len(rels) == 1 and rels[0].rel_type == "resolves"
        assert "honcho_ref:honcho_peer:carlos:msg-9@s0" in (
            rels[0].evidence_refs_json or "")
        claims = (await db.execute(select(SemanticClaim).where(
            SemanticClaim.honcho_workspace_id == "ws-recruit-1")
        )).scalars().all()
        assert any("#recruited" in (c.source_key or "") for c in claims)
        # No interrogation: uncertainty was resolved privately.
        assert await clarifications_in(db, "ws-recruit-1") == []
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == "ws-recruit-1",
            ExtractionTrace.stage == "semantic_proposal",
        ))).scalars().all()
        assert any(t.status == "accepted_via_recruitment" for t in traces)


@pytest.mark.asyncio
async def test_similar_wording_different_matter_holds():
    """Two live payment matters + 'The payment arrived': history confirms
    both vocabularies, so there is no single winner. Hold everything."""
    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id="ws-recruit-2", honcho_session_id="s1",
            honcho_message_id="m1", title="Carlos payment",
            summary="Carlos invoice payment expected"))
        db.add(OpenLoop(
            honcho_workspace_id="ws-recruit-2", honcho_session_id="s1",
            honcho_message_id="m1b", title="Studio Sam payment",
            summary="Studio Sam contract payment expected"))
        await db.commit()
        hits = [
            HistoryHit(text="Carlos confirmed the invoice payment of 300",
                       provenance="honcho_peer:carlos:h1@s0",
                       source="peer_search"),
            HistoryHit(text="Studio Sam sent the contract payment of 450",
                       provenance="honcho_peer:studio_sam:h2@s0",
                       source="peer_search"),
        ]
        calls: list = []
        out = await reconcile_turn(
            db, workspace_id="ws-recruit-2", session_id="s1", message_id="m2",
            text="The payment finally arrived in the account this morning, all sorted now.",
            peer_id="ashley", now=datetime.now(timezone.utc), closed_loop_ids=[],
            adapter=NeedsHistoryAdapter("payment"),
            history_provider=stub_provider(hits, calls))
        assert len(calls) == 1
        assert out.get("recruited") == 2
        assert out.get("recruit_accepted") == 2
        assert out["closed"] == 0 and out["promoted"] == 0
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == "ws-recruit-2"))).scalars().all()
        assert all(lp.status == OpenLoopStatus.OPEN for lp in loops)
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == "ws-recruit-2")
        )).scalars().all()
        assert rels == []
        assert await clarifications_in(db, "ws-recruit-2") == []
        traces = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == "ws-recruit-2",
            ExtractionTrace.stage == "semantic_proposal",
        ))).scalars().all()
        assert any(t.status == "recruited_hold" for t in traces)


@pytest.mark.asyncio
async def test_partial_external_evidence_never_fulfils():
    """Carlos owes 2100; bank shows 1900. History raises confidence that it
    is the same debt and supports partially_fulfils — but the row must stay
    UNKNOWN with the discrepancy preserved, never closed."""
    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id="ws-recruit-3", honcho_session_id="s1",
            honcho_message_id="m1", subject_peer_id="carlos",
            owner_peer_id="ashley",
            title="Carlos owes 2100 for the event",
            summary="Carlos will send the full 2100 balance",
            expectation_type=ExpectationType.EXTERNAL_DEPENDENCY))
        await db.commit()
        hits = [HistoryHit(
            text="Carlos said he would send 2100 for the event next week",
            provenance="honcho_peer:carlos:h3@s0",
            source="peer_search")]
        calls: list = []
        out = await reconcile_turn(
            db, workspace_id="ws-recruit-3", session_id="s1", message_id="m2",
            text="Bank feed shows 1900 received from Carlos this morning, not the full amount.",
            peer_id="ashley", now=datetime.now(timezone.utc), closed_loop_ids=[],
            adapter=NeedsHistoryAdapter("2100"),
            history_provider=stub_provider(hits, calls))
        assert len(calls) == 1
        assert out.get("recruit_accepted") == 1
        assert out["promoted"] == 1
        exp = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-recruit-3"))).scalar_one()
        # Partial support refines; it never closes or fulfils.
        assert exp.outcome_state == OutcomeState.UNKNOWN
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == "ws-recruit-3")
        )).scalars().all()
        assert any(r.rel_type == "partially_fulfils"
                   and "honcho_ref:honcho_peer:carlos:h3@s0" in (
                       r.evidence_refs_json or "") for r in rels)
        assert not any(r.rel_type in ("fulfils", "resolves") for r in rels)
        assert await clarifications_in(db, "ws-recruit-3") == []


@pytest.mark.asyncio
async def test_self_resolution_without_asking_and_no_rewander():
    """Ambiguity resolves via one recruitment; replay performs no second
    retrieval (per-message idempotency holds for the bridge too)."""
    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id="ws-recruit-4", honcho_session_id="s1",
            honcho_message_id="m1", title="Chase Carlos for the balance",
            summary="Carlos still owes the remaining dinner balance"))
        await db.commit()
        hits = [HistoryHit(
            text="Carlos promised the remaining dinner balance by Friday",
            provenance="honcho_peer:carlos:h4@s0",
            source="peer_search")]
        calls: list = []
        text = "Nobody has sent the remaining balance yet and Friday is nearly here."
        out = await reconcile_turn(
            db, workspace_id="ws-recruit-4", session_id="s1", message_id="m2",
            text=text, peer_id="ashley", now=datetime.now(timezone.utc),
            closed_loop_ids=[],
            adapter=NeedsHistoryAdapter("carlos"),
            history_provider=stub_provider(hits, calls))
        assert out["closed"] == 1
        assert await clarifications_in(db, "ws-recruit-4") == []
        out2 = await reconcile_turn(
            db, workspace_id="ws-recruit-4", session_id="s1", message_id="m2",
            text=text, peer_id="ashley", now=datetime.now(timezone.utc),
            closed_loop_ids=[],
            adapter=NeedsHistoryAdapter("carlos"),
            history_provider=stub_provider(hits, calls))
        assert out2["judged"] == 0
        assert "recruited" not in out2
        assert len(calls) == 1


@pytest.mark.asyncio
async def test_honcho_unavailable_preserves_hold():
    """Same ambiguous event with a failing provider — and with no provider
    at all: exactly today's safe behaviour, no mutation, no question."""
    text = "The transfer never arrived in my account, still waiting on it."

    async def make_loop(ws):
        async with async_session_maker() as db:
            db.add(OpenLoop(
                honcho_workspace_id=ws, honcho_session_id="s1",
                honcho_message_id="m1", title="Carlos still owes me",
                summary="Carlos owes the dinner balance, transfer expected"))
            await db.commit()

    async def failing_provider(workspace_id, session_id, peer_id, query, limit):
        raise TimeoutError("honcho unreachable")

    await make_loop("ws-recruit-5a")
    async with async_session_maker() as db:
        out = await reconcile_turn(
            db, workspace_id="ws-recruit-5a", session_id="s1", message_id="m2",
            text=text, peer_id="ashley", now=datetime.now(timezone.utc),
            closed_loop_ids=[],
            adapter=NeedsHistoryAdapter("carlos"),
            history_provider=failing_provider)
        assert "recruited" not in out
        assert out["closed"] == 0 and out["promoted"] == 0
        loop = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == "ws-recruit-5a"))).scalar_one()
        assert loop.status == OpenLoopStatus.OPEN
        assert await clarifications_in(db, "ws-recruit-5a") == []

    # No provider at all: byte-shape of today's result is preserved.
    await make_loop("ws-recruit-5b")
    async with async_session_maker() as db:
        out = await reconcile_turn(
            db, workspace_id="ws-recruit-5b", session_id="s1", message_id="m2",
            text=text, peer_id="ashley", now=datetime.now(timezone.utc),
            closed_loop_ids=[],
            adapter=CannedAdapter(verdict="unclear", confidence=0.5),
            history_provider=None)
        assert out == {"pairs": 1, "judged": 1, "accepted": 0,
                       "promoted": 0, "closed": 0}
        loop = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == "ws-recruit-5b"))).scalar_one()
        assert loop.status == OpenLoopStatus.OPEN
