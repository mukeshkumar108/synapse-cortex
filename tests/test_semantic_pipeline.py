"""Semantic judge + reconciliation + roles tests.

Model judgement is exercised through a fake adapter (no network, no creds);
deterministic control (bounds, verbatim grounding, promotion) is real.
"""

import pytest

from src.services import semantic_judge
from src.services.semantic_judge import QUESTION_KINDS


class FakeAdapter:
    """Returns canned verdicts; evidence_span parsed verbatim from LATER."""

    def __init__(self, verdict="yes", confidence=0.8, span_chars=30):
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
                "evidence_span": span, "rationale": "test rationale"}


@pytest.mark.asyncio
async def test_judge_accepts_grounded_yes():
    j = await semantic_judge.judge(
        kind="resolves", earlier="Grandad letter",
        later="Found grandad original in the loft today",
        adapter=FakeAdapter())
    assert j is not None and j.accepted
    assert j.evidence_span in "Found grandad original in the loft today"


@pytest.mark.asyncio
async def test_judge_rejects_unknown_kind_no_adapter_low_conf():
    assert await semantic_judge.judge(
        kind="emotionally_should_revisit", earlier="a", later="b",
        adapter=FakeAdapter()) is None
    assert await semantic_judge.judge(
        kind="resolves", earlier="a", later="b", adapter=None) is None
    assert await semantic_judge.judge(
        kind="resolves", earlier="a", later="bbbbb",
        adapter=FakeAdapter(confidence=0.4)) is None


@pytest.mark.asyncio
async def test_judge_rejects_non_verbatim_span():
    class LyingAdapter(FakeAdapter):
        async def generate_structured(self, **kw):
            return {"verdict": "yes", "confidence": 0.9,
                    "evidence_span": "never appeared anywhere",
                    "rationale": "x"}

    assert await semantic_judge.judge(
        kind="resolves", earlier="a", later="some real turn text here",
        adapter=LyingAdapter()) is None


def test_question_kinds_bounded():
    assert set(QUESTION_KINDS) == {
        "resolves", "fulfils", "partially_fulfils", "factual_claim",
        "same_person", "accepts", "eased",
        "supersedes", "undertaking", "revisit_worthy"}


@pytest.mark.asyncio
async def test_reconciliation_closes_loop_and_promotes():
    from datetime import datetime, timezone

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.models.semantic import SemanticRelation
    from src.services.semantic_reconciliation import reconcile_turn

    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id="ws-rec", honcho_session_id="s1",
            honcho_message_id="m1", title="Grandad original letter",
            summary="Find grandad original for auntie"))
        await db.commit()
        out = await reconcile_turn(
            db, workspace_id="ws-rec", session_id="s1", message_id="m2",
            text="Found grandad original letter in the loft and sent auntie a photo",
            peer_id="kai", now=datetime.now(timezone.utc), closed_loop_ids=[],
            adapter=FakeAdapter())
        assert out["accepted"] >= 1 and out["promoted"] >= 1 and out["closed"] == 1
        loop = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == "ws-rec"))).scalar_one()
        assert loop.status == OpenLoopStatus.RESOLVED
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == "ws-rec"))).scalars().all()
        assert len(rels) == 1 and rels[0].rel_type == "resolves"
        # Replay of the same turn never re-judges (trace marker bound).
        out2 = await reconcile_turn(
            db, workspace_id="ws-rec", session_id="s1", message_id="m2",
            text="Found grandad original letter in the loft and sent auntie a photo",
            peer_id="kai", now=datetime.now(timezone.utc), closed_loop_ids=[],
            adapter=FakeAdapter())
        assert out2["judged"] == 0


@pytest.mark.asyncio
async def test_reconciliation_partial_keeps_outcome():
    from datetime import datetime, timezone

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.models.semantic import SemanticRelation
    from src.services.semantic_reconciliation import reconcile_turn

    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id="ws-part", honcho_session_id="s1",
            honcho_message_id="m1", subject_peer_id="carlos",
            title="Amount owed by Carlos for the event",
            summary="Carlos owes the event balance",
            expectation_type=ExpectationType.EXTERNAL_DEPENDENCY))
        await db.commit()
        out = await reconcile_turn(
            db, workspace_id="ws-part", session_id="s1", message_id="m2",
            text="Carlos paid something toward the event balance but not all of it yet",
            peer_id="ashley", now=datetime.now(timezone.utc), closed_loop_ids=[],
            adapter=FakeAdapter())
        assert out["promoted"] >= 1
        exp = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-part"))).scalar_one()
        # Partial fulfilment never changes outcome state.
        assert exp.outcome_state == OutcomeState.UNKNOWN
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == "ws-part"))).scalars().all()
        assert any(r.rel_type == "partially_fulfils" for r in rels)


@pytest.mark.asyncio
async def test_reconciliation_no_adapter_no_text_is_zero():
    from datetime import datetime, timezone
    from src.db import async_session_maker
    from src.services.semantic_reconciliation import reconcile_turn

    async with async_session_maker() as db:
        out = await reconcile_turn(
            db, workspace_id="ws-x", session_id="s1", message_id="m1",
            text="hi", peer_id="kai", now=datetime.now(timezone.utc),
            closed_loop_ids=[], adapter=None)
        assert out == {"pairs": 0, "judged": 0, "accepted": 0,
                       "promoted": 0, "closed": 0}


def test_roles_structural_zero_to_many():
    from src.services.state_roles import derive_roles

    class Row:
        def __init__(self, id, **kw):
            self.id = id
            self.__dict__.update(kw)

    roles = derive_roles(
        expectations=[Row("e1", outcome_state="unknown",
                          expected_window_start=None, expected_window_end=None,
                          hard_deadline_at=None, title="Do thing")],
        open_loops=[Row("l1", status="open", title="Thread")],
        commitments=[Row("c1", status="pending", authority="ask")],
        clarifications=[], attentions=[],
        relations=[], claims=[])
    assert set(roles["expectation:e1"]) == {"assertional", "obligation", "unresolved"}
    assert set(roles["open_loop:l1"]) == {"assertional", "attentional", "unresolved"}
    assert set(roles["commitment:c1"]) == {"attentional"}
    # Terminal rows shed to assertional.
    roles2 = derive_roles(
        expectations=[Row("e2", outcome_state="fulfilled", title="Done")],
        relations=[], claims=[])
    assert roles2["expectation:e2"] == ["assertional"]


@pytest.mark.asyncio
async def test_fulfill_grounding_blocks_disconnected_claim(monkeypatch):
    from datetime import datetime, timezone

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.schemas.candidate import ExtractionCandidate
    from src.services.lifecycle_service import LifecycleService

    counter = {"n": 0}

    async def run_case(adapter, observation):
        counter["n"] += 1
        ws = f"ws-g{counter['n']}"
        async with async_session_maker() as db:
            db.add(Expectation(
                honcho_workspace_id=ws, honcho_session_id="s1",
                honcho_message_id="m1", subject_peer_id="kai",
                title="Check on cousin Sam pickup", summary="Cousin Sam pickup",
                expectation_type=ExpectationType.USER_INTENTION))
            await db.commit()
            exp = (await db.execute(select(Expectation).where(
                Expectation.honcho_workspace_id == ws))).scalar_one()
            monkeypatch.setattr(
                "src.services.semantic_judge._adapter", lambda: adapter)
            cand = ExtractionCandidate(
                candidate_key="c1", observation=observation,
                resolution_hint={"action": "fulfill", "target_id": str(exp.id)})
            out = await LifecycleService().handle_outcome_mutations(
                db, workspace_id=ws, session_id="s1", message_id="m2",
                candidate=cand, now=datetime.now(timezone.utc))
            exp2 = await db.get(Expectation, exp.id)
            return out, exp2.outcome_state

    # Lexically disconnected evidence + rejecting judge -> stays UNKNOWN.
    out, state = await run_case(
        FakeAdapter(verdict="no", confidence=0.9),
        "Attached the revised contract clause document")
    assert out == [] and state == OutcomeState.UNKNOWN
    # Same pair with strong overlap proceeds without any model call.
    made = {"n": 0}

    class CountingAdapter(FakeAdapter):
        async def generate_structured(self, **kw):
            made["n"] += 1
            return await super().generate_structured(**kw)

    out2, state2 = await run_case(
        CountingAdapter(), "Cousin Sam pickup confirmed for Wednesday")
    assert out2 != [] and state2 == OutcomeState.FULFILLED
    assert made["n"] == 0



@pytest.mark.asyncio
async def test_factual_rescue_persists_stranded_disclosure():
    from datetime import datetime, timezone

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.fact import Fact
    from src.services.semantic_reconciliation import rescue_zero_yield_turn

    class Cand:
        operational_kind = "semantic_only"
        confidence = 0.9
        observation = "Kai sat with her dad daily for three months while he was dying"
        raw_evidence = "You sat with my dad when he was dying, Kai. Three months."
        candidate_key = "c_dad"
        domain_tag = "family"

    async with async_session_maker() as db:
        # Yielding turns never trigger rescue.
        out = await rescue_zero_yield_turn(
            db, workspace_id="ws-rescue", session_id="s", message_id="m",
            peer_id="isa", now=datetime.now(timezone.utc),
            candidates=[Cand()], had_durable_yield=True,
            adapter=FakeAdapter())
        assert out["rescued"] == 0
        # Zero-yield + accepting judge persists one fact via idempotent writer.
        out2 = await rescue_zero_yield_turn(
            db, workspace_id="ws-rescue", session_id="s", message_id="m",
            peer_id="isa", now=datetime.now(timezone.utc),
            candidates=[Cand()], had_durable_yield=False,
            adapter=FakeAdapter())
        assert out2["rescued"] == 1
        facts = (await db.execute(select(Fact).where(
            Fact.honcho_workspace_id == "ws-rescue"))).scalars().all()
        assert len(facts) == 1
        assert facts[0].owner_peer_id == "isa"
        assert "dad" in facts[0].title.lower()
        # Replay is idempotent: same message never re-judges.
        out3 = await rescue_zero_yield_turn(
            db, workspace_id="ws-rescue", session_id="s", message_id="m",
            peer_id="isa", now=datetime.now(timezone.utc),
            candidates=[Cand()], had_durable_yield=False,
            adapter=FakeAdapter())
        assert out3["rescued"] == 0


@pytest.mark.asyncio
async def test_factual_rescue_rejects_non_facts():
    from datetime import datetime, timezone

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.fact import Fact
    from src.services.semantic_reconciliation import rescue_zero_yield_turn

    class Cand:
        operational_kind = "semantic_only"
        confidence = 0.9
        observation = "I will call you tomorrow maybe"
        raw_evidence = "I will call you tomorrow maybe"
        candidate_key = "c_maybe"
        domain_tag = None

    async with async_session_maker() as db:
        out = await rescue_zero_yield_turn(
            db, workspace_id="ws-rescue2", session_id="s", message_id="m",
            peer_id="kai", now=datetime.now(timezone.utc),
            candidates=[Cand()], had_durable_yield=False,
            adapter=FakeAdapter(verdict="no", confidence=0.9))
        assert out["rescued"] == 0
        facts = (await db.execute(select(Fact).where(
            Fact.honcho_workspace_id == "ws-rescue2"))).scalars().all()
        assert facts == []


@pytest.mark.asyncio
async def test_factual_rescue_uses_raw_evidence_and_recurring_kind():
    from datetime import datetime, timezone

    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.fact import Fact
    from src.services.semantic_reconciliation import rescue_zero_yield_turn

    class Cand:
        operational_kind = "recurring_intention"
        confidence = 0.9
        observation = "Acknowledges consistent presence over three months"
        raw_evidence = "You sat with my dad when he was dying, Kai"
        candidate_key = "c_past"
        domain_tag = "family"

    async with async_session_maker() as db:
        out = await rescue_zero_yield_turn(
            db, workspace_id="ws-rescue3", session_id="s", message_id="m",
            peer_id="isa", now=datetime.now(timezone.utc),
            candidates=[Cand()], had_durable_yield=False,
            adapter=FakeAdapter())
        assert out["rescued"] == 1
        facts = (await db.execute(select(Fact).where(
            Fact.honcho_workspace_id == "ws-rescue3"))).scalars().all()
        assert len(facts) == 1
        assert "dad" in facts[0].evidence_verbatim.lower()
