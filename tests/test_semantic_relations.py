"""Phase-B tiny persistence tests: claims/relations store + promotion.

Guardrails pinned here:
- bounded rel_type (unknown rejected, never persisted);
- idempotent promotion (no duplicate rows on replay);
- no salience/role/authority columns on either table;
- promotion is advisory: existing mutation outcomes byte-identical.
"""

import json

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.semantic import (
    RELATION_VOCAB,
    SemanticClaim,
    SemanticRelation,
)
from src.services.semantic_promotion import promote_transition


async def _counts(db, workspace_id):
    claims = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == workspace_id))).scalars().all()
    rels = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == workspace_id))).scalars().all()
    return claims, rels


@pytest.mark.asyncio
async def test_promote_fulfils_creates_claims_and_relation():
    async with async_session_maker() as db:
        row = await promote_transition(
            db, workspace_id="ws-sem", rel_type="fulfils",
            from_text="User cancelled Freepik after approval",
            to_text="Cancel Freepik Friday",
            source_key="honcho_message:m10#candidate:c1",
            evidence_refs=["honcho_message:m10#candidate:c1"],
            formation="inferred", confidence=0.9)
        assert row is not None
        assert row.rel_type == "fulfils"
        assert json.loads(row.evidence_refs_json) == ["honcho_message:m10#candidate:c1"]
        assert row.formation == "inferred"
        assert row.status == "active"
        assert row.discovered_at is not None
        claims, rels = await _counts(db, "ws-sem")
        assert len(claims) == 2 and len(rels) == 1


@pytest.mark.asyncio
async def test_promote_is_idempotent_and_appends_evidence():
    # Same transition replayed AND new corroborating evidence for the same
    # logical edge: one relation row, evidence unioned, occurrence rows kept.
    async with async_session_maker() as db:
        first = await promote_transition(
            db, workspace_id="ws-idem", rel_type="resolves",
            from_text="Found it in the loft", to_text="Grandad letter",
            source_key="honcho_message:m1#candidate:c1",
            evidence_refs=["honcho_message:m1#candidate:c1"])
        replay = await promote_transition(
            db, workspace_id="ws-idem", rel_type="resolves",
            from_text="Found it in the loft", to_text="Grandad letter",
            source_key="honcho_message:m1#candidate:c1",
            evidence_refs=["honcho_message:m1#candidate:c1"])
        assert replay.id == first.id
        second = await promote_transition(
            db, workspace_id="ws-idem", rel_type="resolves",
            from_text="Found it in the loft", to_text="Grandad letter",
            source_key="honcho_message:m2#candidate:c2",
            evidence_refs=["honcho_message:m2#candidate:c2"])
        assert second.id == first.id
        claims, rels = await _counts(db, "ws-idem")
        assert len(rels) == 1
        assert len(claims) == 4  # two occurrences x two endpoints, never merged
        assert sorted(json.loads(rels[0].evidence_refs_json)) == [
            "honcho_message:m1#candidate:c1", "honcho_message:m2#candidate:c2"]
        assert rels[0].last_corroborated_at is not None


@pytest.mark.asyncio
async def test_identical_wording_different_speakers_stays_separate():
    # ChatGPT's case: "I'll call you tomorrow" from Ashley vs Sophie.
    from src.services.semantic_promotion import ensure_claim
    async with async_session_maker() as db:
        a = await ensure_claim(
            db, workspace_id="ws-occ", content="I'll call you tomorrow",
            source_key="honcho_message:m_ashley#candidate:c1",
            evidence_refs=["honcho_message:m_ashley#candidate:c1"],
            subjects=["ashley"])
        b = await ensure_claim(
            db, workspace_id="ws-occ", content="I'll call you tomorrow",
            source_key="honcho_message:m_sophie#candidate:c1",
            evidence_refs=["honcho_message:m_sophie#candidate:c1"],
            subjects=["sophie"])
        assert a.id != b.id
        # Same wording, disjoint subjects: promotions must not merge edges.
        r1 = await promote_transition(
            db, workspace_id="ws-occ", rel_type="fulfils",
            from_text="Called you today", to_text="I'll call you tomorrow",
            source_key="honcho_message:m_ashley#candidate:c2",
            evidence_refs=["honcho_message:m_ashley#candidate:c2"],
            subjects_from=["ashley"], subjects_to=["user"])
        r2 = await promote_transition(
            db, workspace_id="ws-occ", rel_type="fulfils",
            from_text="Called you today", to_text="I'll call you tomorrow",
            source_key="honcho_message:m_sophie#candidate:c2",
            evidence_refs=["honcho_message:m_sophie#candidate:c2"],
            subjects_from=["sophie"], subjects_to=["user"])
        assert r1.id != r2.id


@pytest.mark.asyncio
async def test_unknown_rel_type_and_empty_content_rejected():
    async with async_session_maker() as db:
        assert await promote_transition(
            db, workspace_id="ws-reject", rel_type="emotionally_should_revisit",
            from_text="a", to_text="b", source_key="m1",
            evidence_refs=["m1"]) is None
        assert await promote_transition(
            db, workspace_id="ws-reject", rel_type="fulfils",
            from_text="   ", to_text="b", source_key="m1",
            evidence_refs=["m1"]) is None
        assert await promote_transition(
            db, workspace_id="ws-reject", rel_type="fulfils",
            from_text="same", to_text="  SAME  ", source_key="m1",
            evidence_refs=["m1"]) is None
        claims, rels = await _counts(db, "ws-reject")
        assert claims == [] and rels == []


def test_vocab_matches_shadow_and_has_no_attention_columns():
    assert set(RELATION_VOCAB) == {
        "same_as", "refines", "contradicts", "supersedes", "depends_on",
        "part_of", "conditioned_on", "fulfils", "partially_fulfils",
        "resolves", "reopens", "enables", "blocks"}
    claim_cols = set(SemanticClaim.model_fields)
    rel_cols = set(SemanticRelation.model_fields)
    for banned in ("salience", "surfaced_count", "role", "lifecycle",
                   "authority", "actionable", "pressure", "surface_scope"):
        assert banned not in claim_cols, banned
        assert banned not in rel_cols, banned


@pytest.mark.asyncio
async def test_same_title_supersession_promotes_nothing():
    # Versioning supersession keeps identical titles, so there is no distinct
    # edge to promote (self-edges are refused). Prod mutation still happens.
    from src.models.expectation import ExpectationType, OutcomeState
    from src.services.persistence import save_expectation_idempotent

    async with async_session_maker() as db:
        base = dict(honcho_workspace_id="ws-sup", honcho_session_id="s1",
                    honcho_message_id="m1",
                    subject_peer_id="kai", title="Cancel Freepik Friday",
                    summary="User intends: cancel Freepik Friday",
                    expectation_type=ExpectationType.USER_INTENTION)
        first, created = await save_expectation_idempotent(
            db, {**base, "candidate_key": "a"})
        assert created is True
        second, created2 = await save_expectation_idempotent(
            db, {**base, "candidate_key": "b"})
        assert created2 is True
        assert first.outcome_state == OutcomeState.SUPERSEDED
        claims, rels = await _counts(db, "ws-sup")
        assert rels == []


@pytest.mark.asyncio
async def test_supersedes_with_distinct_content_promotes():
    async with async_session_maker() as db:
        row = await promote_transition(
            db, workspace_id="ws-sup2", rel_type="supersedes",
            from_text="Cancel Freepik Saturday",
            to_text="Cancel Freepik Friday",
            source_key="honcho_message:m9#candidate:c1",
            evidence_refs=["honcho_message:m9#candidate:c1"])
        assert row is not None and row.rel_type == "supersedes"


@pytest.mark.asyncio
async def test_outcome_fulfill_promotes_edge():
    from datetime import datetime, timezone

    from src.models.expectation import Expectation, ExpectationType
    from src.schemas.candidate import ExtractionCandidate
    from src.services.lifecycle_service import LifecycleService

    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id="ws-ful", honcho_session_id="s1",
            honcho_message_id="m1", subject_peer_id="kai",
            title="Renew parking permit", summary="Renew parking permit",
            expectation_type=ExpectationType.USER_INTENTION))
        await db.commit()
        exp = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == "ws-ful"))).scalar_one()
        cand = ExtractionCandidate(
            candidate_key="c1", observation="Renewed the parking permit today",
            resolution_hint={"action": "fulfill", "target_id": str(exp.id)})
        modified = await LifecycleService().handle_outcome_mutations(
            db, workspace_id="ws-ful", session_id="s1", message_id="m2",
            candidate=cand, now=datetime.now(timezone.utc))
        assert modified == [exp.id]
        _, rels = await _counts(db, "ws-ful")
        assert len(rels) == 1
        assert rels[0].rel_type == "fulfils"


@pytest.mark.asyncio
async def test_close_answered_loops_promotes_resolves():
    from datetime import datetime, timezone

    from src.models.open_loop import OpenLoop
    from src.services.lifecycle_service import LifecycleService

    async with async_session_maker() as db:
        db.add(OpenLoop(
            honcho_workspace_id="ws-loop", honcho_session_id="s1",
            honcho_message_id="m1", title="Grandad original letter",
            summary="Find grandad original for auntie"))
        await db.commit()
        svc = LifecycleService()
        closed = await svc.close_answered_loops(
            db, workspace_id="ws-loop", session_id="s1", message_id="m2",
            text="Found grandad original letter in the loft and sent auntie a photo",
            now=datetime.now(timezone.utc))
        assert closed, "fixture text should close the loop"
        _, rels = await _counts(db, "ws-loop")
        assert len(rels) == 1
        assert rels[0].rel_type == "resolves"
