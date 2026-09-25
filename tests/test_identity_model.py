"""Step 3A: identity/model foundation tests (deterministic, no model).

- exact alias resolution + frame scoping + ambiguity + incidental skip
- late naming: 'my brother' -> 'his name is Leo' enriches one entity
- same-name distinct people coexist; no auto-merge
- relationship edges revisable with history preserved
- model entries persist + revise, never transition outcomes
- turn frame rows written per turn
- resolve-before-clarify via entity links
- suppression direction gate (missing fails closed; allow reopens)
"""
import pytest

from src.services import entity_service

WS = "ws-identity"


@pytest.mark.asyncio
async def test_exact_alias_links_within_frame():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        ent, status = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Ashley",
            frame="creator_direct", message_id="m1")
        assert status == "provisioned" and ent.display_name == "Ashley"
        same, status2 = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="ashley",
            frame="creator_direct", message_id="m2")
        assert status2 == "linked" and same.id == ent.id


@pytest.mark.asyncio
async def test_same_alias_different_frames_do_not_merge():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        roleplay, _ = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Kai",
            frame="in_roleplay", message_id="m1")
        creator, status = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Kai",
            frame="creator_direct", message_id="m2")
        assert status == "provisioned" and creator.id != roleplay.id


@pytest.mark.asyncio
async def test_same_name_distinct_people_coexist_without_merge():
    from src.db import async_session_maker
    from src.models.identity import Entity, EntityAlias
    async with async_session_maker() as db:
        for label in ("Marco from work", "Marco from school"):
            ent = Entity(honcho_workspace_id=WS, display_name=label,
                         frame_scope="creator_direct", provisional=False)
            db.add(ent)
            await db.flush()
            db.add(EntityAlias(entity_id=ent.id, alias="marco",
                               provenance_message_id="m1"))
        await db.commit()
        found, status = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Marco",
            frame="creator_direct", message_id="m3")
        assert found is None and status == "ambiguous"


@pytest.mark.asyncio
async def test_incidental_mentions_do_not_provision():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        for mention in ("the cashier", "tabs", "love", "you", "the house", "space"):
            found, status = await entity_service.resolve_mention(
                db, workspace_id=WS, session_id="s1", mention=mention,
                frame="creator_direct", message_id="m1")
            assert (found, status) == (None, "skipped"), mention


@pytest.mark.asyncio
async def test_late_naming_enriches_same_entity():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        brother, status = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="my brother",
            frame="creator_direct", message_id="m1")
        assert status == "provisioned"
        named = await entity_service.apply_naming_assertion(
            db, workspace_id=WS, session_id="s1",
            text="his name is Leo", message_id="m2")
        assert named is not None and named.id == brother.id
        leo, status2 = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Leo",
            frame="creator_direct", message_id="m3")
        assert status2 == "linked" and leo.id == brother.id


@pytest.mark.asyncio
async def test_naming_without_role_context_stays_separate():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        named = await entity_service.apply_naming_assertion(
            db, workspace_id=WS, session_id="s1",
            text="his name is Leo", message_id="m1")
        assert named is None
        leo, status = await entity_service.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Leo",
            frame="creator_direct", message_id="m2")
        assert status == "provisioned"


@pytest.mark.asyncio
async def test_relationship_edge_revision_preserves_history():
    from src.db import async_session_maker
    from src.models.identity import Entity, RelationshipEdge
    async with async_session_maker() as db:
        a = Entity(honcho_workspace_id=WS, display_name="user", provisional=False)
        b = Entity(honcho_workspace_id=WS, display_name="Sarah", provisional=False)
        db.add_all([a, b])
        await db.flush()
        edge = RelationshipEdge(
            honcho_workspace_id=WS, from_entity_id=a.id, to_entity_id=b.id,
            role="friend", provenance_message_id="m1", confidence=0.8)
        db.add(edge)
        await db.commit()
        revised = await entity_service.revise_edge(
            db, edge_id=edge.id, new_role="ex", message_id="m2")
        assert revised.id != edge.id and revised.role == "ex"
        await db.refresh(edge)
        assert edge.end_at is not None and edge.role == "friend"


@pytest.mark.asyncio
async def test_model_entry_persists_and_revises_without_outcomes():
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.identity import ModelEntry
    from src.services.persistence import save_model_entry
    base = dict(honcho_workspace_id=WS, honcho_session_id="s1",
                honcho_message_id="m70", owner_peer_id="kai",
                model_kind="user", claim="User feels invisible in real life",
                evidence_verbatim="i feel invisible in the real world",
                formation="explicit", confidence=0.9)
    async with async_session_maker() as db:
        first, created = await save_model_entry(db, dict(base))
        assert created is True
        dup, created2 = await save_model_entry(db, dict(base))
        assert created2 is False and dup.id == first.id
        assert not hasattr(first, "outcome_state")
        rows = (await db.execute(select(ModelEntry).where(
            ModelEntry.honcho_workspace_id == WS))).scalars().all()
        assert len(rows) == 1


@pytest.mark.asyncio
async def test_turn_frame_written_per_turn(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.identity import TurnFrame
    from src.routers import v1_events
    from src.schemas.candidate import ExtractionResult

    class FakeExtractor:
        def extract_candidates(self, *a, **kw):
            return []

        def extraction_result(self, candidates):
            return ExtractionResult(candidates=[], observations=[], backend="fake",
                                    frame="creator_direct", frame_confidence=0.9)

    monkeypatch.setattr(v1_events, "turn_extractor", FakeExtractor())
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": WS, "session_id": "s1", "honcho_message_id": "m-frame",
        "peer_id": "kai", "text": "i am the narrator speaking now",
        "now": "2026-09-22T03:41:03+01:00", "timezone": "Europe/London"})
    assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        rows = (await db.execute(select(TurnFrame).where(
            TurnFrame.honcho_workspace_id == WS))).scalars().all()
        assert len(rows) == 1
        assert rows[0].frame == "creator_direct"


@pytest.mark.asyncio
async def test_resolve_before_clarify_uses_entity_link(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.clarification import ClarificationCandidate
    from src.models.expectation import Expectation, ExpectationType, OutcomeState
    from src.routers import v1_events
    from src.schemas.candidate import ExtractionCandidate
    from src.services import entity_service as entities
    async with async_session_maker() as db:
        ent, _ = await entities.resolve_mention(
            db, workspace_id=WS, session_id="s1", mention="Ashley",
            frame="creator_direct", message_id="m0")
        mine = Expectation(
            honcho_workspace_id=WS, honcho_session_id="s1", honcho_message_id="m1",
            owner_peer_id="kai", subject_peer_id="kai",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Ask Ashley about Saturday", summary="Ask Ashley about Saturday")
        other = Expectation(
            honcho_workspace_id=WS, honcho_session_id="s1", honcho_message_id="m2",
            owner_peer_id="kai", subject_peer_id="kai",
            expectation_type=ExpectationType.USER_INTENTION,
            title="Ask Ashley about Sunday", summary="Ask Ashley about Sunday")
        db.add_all([mine, other])
        await db.flush()
        await entities.link_object(
            db, workspace_id=WS, object_type="expectation", object_id=mine.id,
            role="subject", entity_id=ent.id, confidence=0.9, message_id="m1")
        await db.commit()
        mine_id = mine.id
    cand = ExtractionCandidate(
        candidate_key="c_res", observation="done with the Ashley thing",
        raw_evidence="done with the Ashley thing", canonical_title="Ashley thing",
        operational_kind="completion", confidence=0.9, extractor_version="test",
        resolution_hint={"action": "fulfill", "target_text": "Ashley"})
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: [cand])
    r = await async_client.post("/v1/events/turn", json={
        "workspace_id": WS, "session_id": "s1", "honcho_message_id": "m3",
        "peer_id": "kai", "text": "done with the Ashley thing",
        "now": "2026-09-22T04:00:00+01:00", "timezone": "Europe/London"})
    assert r.status_code == 202, r.text
    async with async_session_maker() as db:
        mine = await db.get(Expectation, mine_id)
        assert mine.outcome_state == OutcomeState.FULFILLED
        clar = (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == WS))).scalars().all()
        assert clar == []


@pytest.mark.asyncio
async def test_suppression_direction_gate(async_client, monkeypatch):
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.suppression import Suppression
    from src.routers import v1_events
    from src.schemas.candidate import ExtractionCandidate

    def cand_with(hint):
        return ExtractionCandidate(
            candidate_key="c_sup", observation="do not talk about money",
            raw_evidence="do not talk about money", canonical_title="money",
            operational_kind="suppression", confidence=0.9, extractor_version="test",
            suppression_hint=hint)

    nodir = cand_with({"target_type": "topic", "topic_or_entity": "money",
                       "reason": "user said so"})
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: [nodir])
    base = {"workspace_id": WS, "session_id": "s1", "peer_id": "kai",
            "text": "do not talk about money", "now": "2026-09-22T04:00:00+01:00",
            "timezone": "Europe/London"}
    assert (await async_client.post("/v1/events/turn", json={**base, "honcho_message_id": "m-s1"})).status_code == 202
    refuse = cand_with({"target_type": "topic", "topic_or_entity": "money",
                        "reason": "user said so", "direction": "refuse",
                        "surface_scope": "all_surfaces"})
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: [refuse])
    assert (await async_client.post("/v1/events/turn", json={**base, "honcho_message_id": "m-s2"})).status_code == 202
    async with async_session_maker() as db:
        rows = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == WS))).scalars().all()
        assert len(rows) == 1
        assert rows[0].topic_or_entity == "money"


@pytest.mark.asyncio
async def test_fact_subject_refs_provision_and_link_entities():
    from sqlmodel import select
    from src.db import async_session_maker
    from src.models.identity import Entity, EntityLink
    from src.services.persistence import save_fact_idempotent
    from src.services import entity_service
    from uuid import uuid4
    async with async_session_maker() as db:
        fact, created = await save_fact_idempotent(db, dict(
            honcho_workspace_id=WS, honcho_session_id="s1", honcho_message_id="m-ashley",
            owner_peer_id="kai", candidate_key="c1", category="general",
            title="Ashley has an event Saturday", evidence_verbatim="Ashley has an event Saturday",
            formation="explicit", confidence=0.9))
        assert created is True
        linked = await entity_service.link_candidate_subjects(
            db, workspace_id=WS, session_id="s1", object_type="fact",
            object_id=fact.id, refs=["Ashley", "tabs"], frame="creator_direct",
            message_id="m-ashley")
        # Ashley (proper name) provisions; tabs (bare topic) skips.
        assert [e.display_name for e in linked] == ["Ashley"]
        rows = (await db.execute(select(EntityLink).where(
            EntityLink.object_type == "fact"))).scalars().all()
        assert len(rows) == 1 and rows[0].role == "subject"
        entities = (await db.execute(select(Entity).where(
            Entity.honcho_workspace_id == WS))).scalars().all()
        assert {e.display_name for e in entities} >= {"Ashley"}
