"""Matter identity, lifecycle, salience, relations, merge, and the
no-session-ownership / no-keyword-hack invariants."""
import json
from datetime import timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.domain_annotation import CategoryTag, DomainTag
from src.models.expectation import OutcomeState
from src.models.identity import EntityLink
from src.models.matter import Matter, MatterLink, MatterRelation
from src.models.open_loop import OpenLoopStatus
from src.services import matter_service as ms
from tests.cortex_fixtures import (
    NOW, USER, WS, ago, annotation, commitment, entity, exp, fact, link, loop, naive,
    recurrence, save, work_item,
)


async def sync(**kw):
    async with async_session_maker() as db:
        return await ms.sync_primitives(db, workspace_id=WS, owner_peer_id=USER, now=NOW, **kw)


async def matters():
    async with async_session_maker() as db:
        return list((await db.execute(select(Matter).order_by(Matter.created_at))).scalars().all())


async def links_of(matter_id):
    async with async_session_maker() as db:
        return [(l.object_type, l.object_id) for l in (await db.execute(
            select(MatterLink).where(MatterLink.matter_id == matter_id))).scalars().all()]


@pytest.mark.asyncio
async def test_one_real_world_matter_does_not_fragment_across_primitive_types():
    e = exp("Sort out Carlos payment", message="m1", summary="Carlos still owes the rest")
    lp = loop("Carlos payment follow-up", message="m2", expectation_id=e.id)
    wi = work_item("expectation", e.id, "Chase Carlos for the balance")
    await save(e, lp, wi)
    stats = await sync()
    ms_ = await matters()
    assert len(ms_) == 1, stats
    assert {t for t, _ in await links_of(ms_[0].id)} == {"expectation", "open_loop", "work_item"}
    assert stats["by"]["lineage"] == 2  # open loop via expectation_id, work item via parent


@pytest.mark.asyncio
async def test_same_entity_and_shared_content_joins_but_disjoint_content_stays_separate():
    carlos = entity("Carlos")
    l1 = loop("Carlos outstanding payment", message="m1", created=ago(5))
    l2 = loop("Any news on the payment from Carlos", message="m2", created=ago(2))
    l3 = loop("Venue details for Saturday", message="m3", created=ago(1))
    await save(carlos, l1, l2, l3)
    await save(link("open_loop", l1.id, carlos.id), link("open_loop", l2.id, carlos.id),
               link("open_loop", l3.id, carlos.id))
    await sync()
    ms_ = await matters()
    titles = sorted(m.title for m in ms_)
    assert len(ms_) == 2, titles
    payment = next(m for m in ms_ if "payment" in m.title.lower())
    assert len(await links_of(payment.id)) == 2
    async with async_session_maker() as db:
        rels = (await db.execute(select(MatterRelation))).scalars().all()
        assert [r.rel_type for r in rels] == ["related_to"]  # same actor, distinct matter
        el = (await db.execute(select(EntityLink).where(
            EntityLink.object_type == "matter", EntityLink.entity_id == carlos.id))).scalars().all()
        assert len(el) == 2  # entity <-> matter via EntityLink


@pytest.mark.asyncio
async def test_exact_canonical_key_unifies_recurrences_across_lanes():
    await save(recurrence("Walk every morning", "walk_morning", session="lane-1"),
               recurrence("Morning walk", "walk_morning", session="lane-2", slot="active"))
    await sync()
    ms_ = await matters()
    assert len(ms_) == 1 and ms_[0].kind == "routine"
    assert ms_[0].canonical_key == "routine:walk_morning"


@pytest.mark.asyncio
async def test_matter_is_never_session_owned():
    await save(exp("Finish the tax return", session="lane-1"))
    await sync()
    [m] = await matters()
    cols = {c.name for c in Matter.__table__.columns}
    assert "honcho_session_id" not in cols
    assert m.origin_session_id == "lane-1" and m.owner_peer_id == USER  # provenance only
    # a later primitive from a DIFFERENT lane about the same matter joins it
    await save(exp("Tax return - gather documents", session="lane-9",
                   key="k2"))
    # no shared entity/key -> remains separate (under-merge is the safe default)
    await sync()
    assert len(await matters()) == 2


@pytest.mark.asyncio
async def test_sync_is_idempotent():
    await save(exp("Learn tabla", message="m1"), loop("Tabla teacher search", message="m2"))
    first = await sync()
    second = await sync()
    assert first["linked"] >= 2 and second["linked"] == 0 and second["created"] == 0


@pytest.mark.asyncio
async def test_lifecycle_follows_primitives_and_reopens_on_new_live_evidence():
    e = exp("Book dentist", message="m1", created=ago(3))
    await save(e)
    await sync()
    [m] = await matters()
    assert m.status == "active" and m.resolved_at is None
    async with async_session_maker() as db:
        row = await db.get(type(e), e.id)
        row.outcome_state = OutcomeState.FULFILLED
        row.updated_at = ago(1)
        db.add(row)
        await db.commit()
    await sync()
    [m] = await matters()
    assert m.status == "resolved" and m.resolved_at is not None
    # a new live loop in the same matter (lineage) reopens it
    lp = loop("Dentist booking confirmation", message="m5", expectation_id=e.id)
    await save(lp)
    await sync()
    [m] = await matters()
    assert m.status == "active" and m.resolved_at is None


@pytest.mark.asyncio
async def test_old_terminal_primitives_do_not_found_matters_but_recent_ones_do():
    await save(exp("Old errand", outcome=OutcomeState.FULFILLED, created=ago(200)),
               exp("Recent errand", outcome=OutcomeState.FULFILLED, created=ago(3)))
    await sync()
    ms_ = await matters()
    assert [m.title for m in ms_] == ["Recent errand"] and ms_[0].status == "resolved"


@pytest.mark.asyncio
async def test_kind_comes_from_structured_tags_not_keywords():
    # "worry" in text must not make a concern; a structured STRUGGLE tag must.
    worry_loop = loop("I worry about the bus timetable", message="m1")
    plain_loop = loop("Mum's hospital appointment outcome", message="m2")
    await save(worry_loop, plain_loop,
               annotation("m2", DomainTag.FAMILY, CategoryTag.STRUGGLE, "Mum's health is a struggle"))
    await sync()
    by_title = {m.title: m for m in await matters()}
    assert by_title["I worry about the bus timetable"].kind == "topic"
    assert by_title["Mum's hospital appointment outcome"].kind == "relationship_situation"


@pytest.mark.asyncio
async def test_facts_attach_but_never_found_matters():
    await save(fact("Dad retired in 2019"))
    await sync()
    assert await matters() == []


@pytest.mark.asyncio
async def test_salience_components_are_inspectable_and_not_one_opaque_score():
    e = exp("Submit proposal", message="m1", deadline=naive(NOW) + timedelta(hours=20),
            window_end=naive(NOW) + timedelta(hours=20), created=ago(0, 2))
    lp = loop("Proposal feedback pending", message="m2", expectation_id=e.id, created=ago(0, 1))
    await save(e, lp)
    await sync()
    [m] = await matters()
    comp = json.loads(m.salience_components_json)
    for k in ("recency", "frequency", "explicit_importance", "temporal_pressure",
              "unresolvedness", "repeated_user_initiation", "recent_activity"):
        assert 0.0 <= comp[k] <= 1.0
    assert comp["temporal_pressure"] > 0.6 and comp["unresolvedness"] > 0.5
    assert "salience" not in comp
    # transparent ranking with product-supplied weights
    assert ms.foreground_rank(comp, {"temporal_pressure": 4}) > ms.foreground_rank(comp)


@pytest.mark.asyncio
async def test_matter_relation_vocabulary_is_bounded_and_symmetric_related_to_dedupes():
    await save(exp("Plan the house move", message="m1"), exp("Pack the kitchen", message="m2"))
    await sync()
    a, b = await matters()
    async with async_session_maker() as db:
        with pytest.raises(ValueError):
            await ms.add_matter_relation(db, WS, a.id, b.id, "blocks")
        await ms.add_matter_relation(db, WS, a.id, b.id, "part_of")
        await ms.add_matter_relation(db, WS, a.id, b.id, "related_to")
        await ms.add_matter_relation(db, WS, b.id, a.id, "related_to")
        await db.commit()
        rels = (await db.execute(select(MatterRelation))).scalars().all()
        assert sorted(r.rel_type for r in rels) == ["part_of", "related_to"]


@pytest.mark.asyncio
async def test_merge_repairs_fragmentation_without_deleting_history():
    await save(exp("Plan the house move", message="m1"), exp("Packing boxes", message="m2"))
    await sync()
    a, b = await matters()
    async with async_session_maker() as db:
        keep = await ms.merge_matters(db, a.id, b.id)
    ms_ = await matters()
    assert len(await links_of(keep.id)) == 2
    dropped = next(m for m in ms_ if m.id == b.id)
    assert dropped.status == "archived" and dropped.merged_into_id == a.id
    async with async_session_maker() as db:
        assert (await ms.get_matter(db, b.id)).id == a.id  # reads follow the merge


class _Adapter:
    """Judge stub: answers `yes` only when the EARLIER text contains `accept`."""

    def __init__(self, accept):
        self.accept, self.calls = accept, 0

    async def generate_structured(self, **kwargs):
        self.calls += 1
        earlier = kwargs["prompt"].split("EARLIER:\n", 1)[1].split("\n", 1)[0]
        later = kwargs["prompt"].split("LATER:\n", 1)[1].split("\n", 1)[0]
        yes = self.accept and self.accept in earlier
        return {"verdict": "yes" if yes else "no", "confidence": 0.9,
                "evidence_span": later[:20] if yes else "", "rationale": "stub"}


async def _two_carlos_matters():
    carlos = entity("Carlos")
    pay = exp("Carlos payment balance", message="m1", created=ago(6))
    form = exp("Carlos form submission", message="m2", created=ago(5))
    await save(carlos, pay, form, link("expectation", pay.id, carlos.id),
               link("expectation", form.id, carlos.id))
    await sync()
    assert len(await matters()) == 2
    new = loop("Payment form for Carlos", message="m3", created=ago(0, 1))
    await save(new, link("open_loop", new.id, carlos.id))
    return new


@pytest.mark.asyncio
async def test_genuinely_ambiguous_identity_stays_separate_by_default():
    await _two_carlos_matters()
    await sync()  # no judge: ambiguity must NOT guess
    ms_ = await matters()
    assert len(ms_) == 3
    async with async_session_maker() as db:
        rels = (await db.execute(select(MatterRelation))).scalars().all()
    new_matter = next(m for m in ms_ if m.title == "Payment form for Carlos")
    assert {r.rel_type for r in rels if new_matter.id in (r.from_matter_id, r.to_matter_id)} == {"related_to"}
    assert sum(1 for r in rels if new_matter.id in (r.from_matter_id, r.to_matter_id)) == 2


@pytest.mark.asyncio
async def test_bounded_semantic_judge_resolves_ambiguity_only_when_exactly_one_accepted():
    await _two_carlos_matters()
    adapter = _Adapter(accept="form submission")
    await sync(allow_judge=True, adapter=adapter)
    ms_ = await matters()
    assert len(ms_) == 2 and adapter.calls >= 2  # joined the form matter; no third matter


@pytest.mark.asyncio
async def test_judge_accepting_both_or_neither_keeps_matters_separate():
    await _two_carlos_matters()
    adapter = _Adapter(accept="Carlos")  # yes to both -> still ambiguous
    await sync(allow_judge=True, adapter=adapter)
    assert len(await matters()) == 3


@pytest.mark.asyncio
async def test_existing_semantic_relation_unifies_matters_without_shared_entity():
    from src.services.semantic_promotion import promote_transition
    a = exp("Sort out visa renewal", message="m1", created=ago(8))
    await save(a)
    await sync()
    b = exp("Immigration appointment booked", message="m2", created=ago(1))
    await save(b)
    async with async_session_maker() as db:
        await promote_transition(
            db, workspace_id=WS, rel_type="same_as", from_text=b.title, to_text=a.title,
            source_key="test:rel", evidence_refs=["honcho_message:m2"],
            formation="explicit", confidence=0.9)
    await sync()
    assert len(await matters()) == 1
