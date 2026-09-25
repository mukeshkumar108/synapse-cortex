"""B.1 proof: the durable graph answers reconciliation questions.

Builds an S1-shaped graph through the SAME deterministic writer production
uses, then asserts all seven read answers. Plus one prod-path integration
test (real hooks -> views). No foreground behaviour touched.
"""

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.semantic import SemanticClaim, SemanticRelation
from src.services import semantic_views as v
from src.services.semantic_promotion import promote_transition

WS = "ws-b1"


async def _seed_carlos(db):
    """S1-shaped: debt, partial, remainder-on-bank, florist, school money."""
    await promote_transition(
        db, workspace_id=WS, rel_type="partially_fulfils",
        from_text="Partial payment Q1500 received from Carlos",
        to_text="Amount owed by Carlos",
        source_key="honcho_message:e03#candidate:c1",
        evidence_refs=["honcho_message:e03#candidate:c1"],
        subjects_from=["carlos"], subjects_to=["carlos", "user"])
    await promote_transition(
        db, workspace_id=WS, rel_type="depends_on",
        from_text="Carlos will send remainder after bank release",
        to_text="Amount owed by Carlos",
        source_key="honcho_message:e03#candidate:c2",
        evidence_refs=["honcho_message:e03#candidate:c2"],
        subjects_from=["carlos"], subjects_to=["carlos", "user"])
    await promote_transition(
        db, workspace_id=WS, rel_type="resolves",
        from_text="Florist colours decided and sent",
        to_text="Florist follow-up pending",
        source_key="honcho_message:e09#candidate:c1",
        evidence_refs=["honcho_message:e09#candidate:c1"],
        subjects_from=["user"], subjects_to=["user", "florist"])
    await promote_transition(
        db, workspace_id=WS, rel_type="fulfils",
        from_text="School trip 18 paid",
        to_text="School trip money needed",
        source_key="honcho_message:e13#candidate:c1",
        evidence_refs=["honcho_message:e13#candidate:c1"],
        subjects_from=["user"], subjects_to=["user", "school"])
    claims = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == WS))).scalars().all()
    rels = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == WS))).scalars().all()
    return list(claims), list(rels)


@pytest.mark.asyncio
async def test_b1_seven_answers():
    async with async_session_maker() as db:
        claims, rels = await _seed_carlos(db)
        assert v.fulfilled_matters(claims, rels) == ["school trip money needed"]
        assert v.partially_fulfilled_matters(claims, rels) == ["amount owed by carlos"]
        assert v.resolved_matters(claims, rels) == ["florist follow-up pending"]
        waiting = v.waiting_on(claims, rels)
        assert waiting == ["carlos will send remainder after bank release"]
        assert v.dependencies_of("Carlos will send remainder after bank release",
                                 claims, rels) == ["amount owed by carlos"]
        assert v.dependencies_of("no such matter", claims, rels) == []
        bg = v.background_candidates(claims, rels)
        assert "florist follow-up pending" in bg
        assert "school trip money needed" in bg
        assert "amount owed by carlos" not in bg  # partial stays foreground
        third = v.third_party_open(claims, rels)
        assert "amount owed by carlos" in third
        assert "florist follow-up pending" not in third  # settled
        assert "school trip money needed" not in third  # settled


@pytest.mark.asyncio
async def test_b1_revision_chain():
    async with async_session_maker() as db:
        await promote_transition(
            db, workspace_id="ws-chain", rel_type="refines",
            from_text="Matias sports Thursday",
            to_text="matias school sports item friday?",
            source_key="m1", evidence_refs=["m1"])
        claims = (await db.execute(select(SemanticClaim).where(
            SemanticClaim.honcho_workspace_id == "ws-chain"))).scalars().all()
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == "ws-chain"))).scalars().all()
        assert v.revision_chain("Matias sports Thursday", list(claims), list(rels)) == [
            "matias school sports item friday?"]


@pytest.mark.asyncio
async def test_b1_prod_path_to_views():
    """Real hooks -> durable rows -> views. Fulfill + loop resolve, then read."""
    from datetime import datetime, timezone

    from src.models.expectation import Expectation, ExpectationType
    from src.models.open_loop import OpenLoop
    from src.schemas.candidate import ExtractionCandidate
    from src.services.lifecycle_service import LifecycleService

    ws = "ws-b1prod"
    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id=ws, honcho_session_id="s1",
            honcho_message_id="m1", subject_peer_id="kai",
            title="Pay Priya back", summary="Pay Priya back",
            expectation_type=ExpectationType.USER_INTENTION))
        db.add(OpenLoop(
            honcho_workspace_id=ws, honcho_session_id="s1",
            honcho_message_id="m1", title="Grandad original letter",
            summary="Find grandad original for auntie"))
        await db.commit()
        exp = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == ws))).scalar_one()
        svc = LifecycleService()
        await svc.handle_outcome_mutations(
            db, workspace_id=ws, session_id="s1", message_id="m2",
            candidate=ExtractionCandidate(
                candidate_key="c1", observation="Paid Priya back this morning",
                resolution_hint={"action": "fulfill", "target_id": str(exp.id)}),
            now=datetime.now(timezone.utc))
        closed = await svc.close_answered_loops(
            db, workspace_id=ws, session_id="s1", message_id="m3",
            text="Found grandad original in the loft and sent auntie a photo",
            now=datetime.now(timezone.utc))
        assert closed
        claims = (await db.execute(select(SemanticClaim).where(
            SemanticClaim.honcho_workspace_id == ws))).scalars().all()
        rels = (await db.execute(select(SemanticRelation).where(
            SemanticRelation.honcho_workspace_id == ws))).scalars().all()
        assert v.fulfilled_matters(list(claims), list(rels)) == ["pay priya back"]
        assert v.resolved_matters(list(claims), list(rels)) == [
            "grandad original letter find grandad original for auntie"]
        assert v.background_candidates(list(claims), list(rels)) == [
            "grandad original letter find grandad original for auntie",
            "pay priya back"]
