"""Knowledge coverage: hierarchical, generic, only useful gaps, never a value."""
import json
from datetime import timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.world_model import KnowledgeCoverage
from src.services import knowledge_coverage_service as kcs
from src.services.world_read import open_reader
from src.services.world_scope import resolve_scope
from tests.cortex_fixtures import (NOW, USER, WS, ago, build_longitudinal_world, naive, recurrence, save)


async def _refresh():
    async with async_session_maker() as db:
        from src.services import matter_service
        await matter_service.sync_primitives(db, workspace_id=WS, owner_peer_id=USER, now=NOW)
        reader = await open_reader(db, WS, USER, NOW, "Europe/London")
        await kcs.refresh(db, reader)
        return {r["subject_key"]: r for r in await kcs.read(db, reader.scope)}


@pytest.mark.asyncio
async def test_item_level_coverage_not_coarse_area_rows():
    await build_longitudinal_world()
    cov = await _refresh()
    assert cov["routines/walk_morning"]["status"] == "known"             # declared
    assert cov["routines/walk_morning/timing"]["status"] == "unknown"    # but when? never stated
    assert cov["routines/meditation_evening"]["status"] == "known"
    assert "routines/meditation_evening/timing" not in cov               # window known: no gap invented
    assert cov["routines/gym_weekdays"]["status"] == "partial"           # observed, never declared
    assert cov["routines"]["status"] == "partial"                        # parent summarises children
    # generic path mechanism: parent_key is the path prefix
    assert cov["routines/walk_morning/timing"]["parent_key"] == "routines/walk_morning"


@pytest.mark.asyncio
async def test_repeatedly_mentioned_person_with_unknown_role_is_a_useful_gap():
    await build_longitudinal_world()
    cov = await _refresh()
    assert cov["people/mati/relationship"]["status"] == "unknown"
    assert cov["people/mati/relationship"]["why_useful"]
    assert cov["people/ashley"]["status"] == "known"                     # a relationship edge exists
    assert "people/ashley/relationship" not in cov


@pytest.mark.asyncio
async def test_unknown_carries_no_value_and_no_evidence_claims():
    await build_longitudinal_world()
    cov = await _refresh()
    assert "value" not in KnowledgeCoverage.__table__.columns
    gap = cov["routines/walk_morning/timing"]
    assert gap["evidence_count"] == 0 and gap["evidence_refs"] == []
    for k, v in cov.items():
        assert set(v) >= {"status", "basis", "why_useful"}
        assert "value" not in v


@pytest.mark.asyncio
async def test_conflicting_and_stale_are_represented():
    await build_longitudinal_world()
    await save(recurrence("Weekly review", "weekly_review", created=ago(150)))
    cov = await _refresh()
    assert cov["routines/weekly_review"]["status"] == "stale"
    conflicts = [k for k, v in cov.items() if v["status"] == "conflicting"]
    assert conflicts and any(k.startswith("claims/") for k in conflicts)     # coffee: firm vs inferred


@pytest.mark.asyncio
async def test_registered_gaps_persist_until_evidence_and_are_bounded_by_key_shape():
    await build_longitudinal_world()
    async with async_session_maker() as db:
        scope = await resolve_scope(db, WS, USER)
        row = await kcs.register_gap(db, scope=scope, subject_key="routines/weekday_morning",
                                     why_useful="what a normal weekday morning looks like")
        assert row.status == "unknown" and row.source == "registered"
        for bad in ("", "Has Spaces", "a/b/c/d/e/f", "/"):
            with pytest.raises(ValueError):
                await kcs.register_gap(db, scope=scope, subject_key=bad, why_useful="x")
    cov = await _refresh()                       # derive again: the registered gap survives
    assert cov["routines/weekday_morning"]["status"] == "unknown"
    assert cov["routines/weekday_morning"]["source"] == "registered"
    # evidence arrives for that path -> it becomes derived knowledge, not an unknown
    await save(recurrence("Weekday morning", "weekday_morning", preferred_window="morning", created=ago(2)))
    cov = await _refresh()
    assert cov["routines/weekday_morning"]["status"] == "known" and cov["routines/weekday_morning"]["source"] == "derived"
    assert cov["routines/weekday_morning"]["why_useful"]                  # intent preserved


@pytest.mark.asyncio
async def test_gaps_ranked_for_natural_learning_and_marked_permission_not_instruction():
    await build_longitudinal_world()
    cov = await _refresh()
    gaps = kcs.gaps(list(cov.values()), limit=6)
    assert gaps and all(g["eligible_for_curiosity"] and "not an instruction" in g["note"] for g in gaps)
    assert gaps[0]["status"] == "conflicting"                              # most actionable first
    keys = [g["subject_key"] for g in gaps]
    assert keys.index("routines/walk_morning/timing") < keys.index("work_or_projects") if "work_or_projects" in keys else True


@pytest.mark.asyncio
async def test_cold_start_still_answers_what_we_do_not_know_without_inventing_content():
    async with async_session_maker() as db:
        reader = await open_reader(db, WS, "user_new", NOW, "UTC")
        await kcs.refresh(db, reader)
        rows = await kcs.read(db, reader.scope)
    assert {r["subject_key"] for r in rows} == set(kcs.FRAME)
    assert {r["status"] for r in rows} == {"unknown"}
    assert all(r["evidence_count"] == 0 for r in rows)


@pytest.mark.asyncio
async def test_refresh_is_idempotent_and_does_not_churn_updated_at():
    await build_longitudinal_world()
    await _refresh()
    async with async_session_maker() as db:
        before = {r.subject_key: r.updated_at for r in (await db.execute(select(KnowledgeCoverage))).scalars().all()}
    await _refresh()
    async with async_session_maker() as db:
        after = {r.subject_key: r.updated_at for r in (await db.execute(select(KnowledgeCoverage))).scalars().all()}
    assert before == after
