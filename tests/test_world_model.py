"""WorldModel: persisted, versioned, reconstructable, derived — and never a prompt payload."""
import json
from datetime import timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.expectation import Expectation
from src.models.world_model import WorldModelSnapshot
from src.services import world_model_service as wm
from tests.cortex_fixtures import (NOW, USER, WS, ago, build_longitudinal_world, exp, loop, naive, save, settle)

TZ = "Europe/London"


async def compile_(now=NOW, **kw):
    async with async_session_maker() as db:
        return await wm.get_world_model(db, workspace_id=WS, owner_peer_id=USER, now=now,
                                        timezone_str=TZ, **kw)


async def snapshots():
    async with async_session_maker() as db:
        return list((await db.execute(select(WorldModelSnapshot).order_by(WorldModelSnapshot.version))).scalars().all())


@pytest.mark.asyncio
async def test_all_agreed_sections_exist_and_model_declares_it_is_not_truth():
    await build_longitudinal_world()
    model = await compile_()
    for section in ("person", "relationship_with_system", "recent", "matters", "people",
                    "routines_patterns", "forward", "unresolved", "uncertainty", "coverage",
                    "system_perspective", "depth_index"):
        assert section in model, section
    assert set(model["recent"]) == {"today", "yesterday", "recent_days", "significant_changes"}
    assert set(model["forward"]) >= {"today", "this_week", "later"}
    assert set(model["matters"]["by_kind"]) >= {"routine", "life_situation"}
    assert model["meta"]["authoritative"] is False
    assert "never insert the whole model into a prompt" in " ".join(model["meta"]["contract"])
    assert model["meta"]["freshness"] == "compiled" and model["meta"]["model_version"] == "world-model-v1"


@pytest.mark.asyncio
async def test_snapshot_is_compact_not_a_mega_packet():
    await build_longitudinal_world()
    model = await compile_()
    size = len(json.dumps(model, default=str))
    assert size < 30_000, size
    assert len(model["matters"]["active"]) <= 12
    # raw evidence text and database-row dumps are not carried
    blob = json.dumps(model, default=str)
    assert "evidence_verbatim" not in blob and "salience_components_json" not in blob


@pytest.mark.asyncio
async def test_second_read_is_fresh_and_costs_no_recompile():
    await build_longitudinal_world()
    first = await compile_()
    second = await compile_()
    assert second["meta"]["freshness"] == "fresh" and second["meta"]["snapshot_id"] == first["meta"]["snapshot_id"]
    assert len(await snapshots()) == 1


@pytest.mark.asyncio
async def test_targeted_patch_recompiles_only_stale_sections_and_versions_up():
    await build_longitudinal_world()
    first = await compile_()
    await save(loop("Landlord deposit still not returned", message="l-dep", created=ago(0, 1)))
    await settle()                                  # the mutation boundary (sweeper/consolidation) reconciles
    second = await compile_(now=NOW + timedelta(minutes=5))
    assert second["meta"]["freshness"] == "patched"
    patched = set(second["meta"]["patched_sections"])
    assert {"matters", "unresolved"} <= patched
    assert not patched & {"routines_patterns", "forward", "system_perspective", "uncertainty"}  # untouched sources reused
    assert second["routines_patterns"] == first["routines_patterns"]
    assert any("deposit" in m["title"].lower() for m in second["matters"]["active"])
    snaps = await snapshots()
    assert [s.version for s in snaps] == [1, 2] and snaps[0].superseded_by_id == snaps[1].id   # recoverable history


@pytest.mark.asyncio
async def test_user_day_rollover_refreshes_day_dependent_sections():
    await build_longitudinal_world()
    await compile_()
    nxt = await compile_(now=NOW + timedelta(days=1))   # age also exceeds TTL
    assert nxt["meta"]["user_day"] == "2026-10-02"
    assert nxt["meta"]["freshness"] in ("compiled", "patched")


@pytest.mark.asyncio
async def test_invalidate_marks_sections_and_next_read_recompiles_exactly_those():
    await build_longitudinal_world()
    await compile_()
    async with async_session_maker() as db:
        res = await wm.invalidate(db, workspace_id=WS, owner_peer_id=USER, sections=["forward"])
    assert res["invalidated"] == ["forward"]
    again = await compile_()
    assert again["meta"]["patched_sections"] == ["forward"]


@pytest.mark.asyncio
async def test_world_model_is_disposable_and_reconstructable_from_primitives():
    await build_longitudinal_world()
    first = await compile_()
    async with async_session_maker() as db:      # throw the derived model away
        for s in (await db.execute(select(WorldModelSnapshot))).scalars().all():
            await db.delete(s)
        await db.commit()
        n_exp = len((await db.execute(select(Expectation))).scalars().all())
    assert n_exp > 0                              # authoritative state untouched
    rebuilt = await compile_()
    strip = lambda m: {k: v for k, v in m.items() if k != "meta"}
    assert strip(rebuilt) == strip(first)         # same content, rebuilt from authoritative rows


@pytest.mark.asyncio
async def test_world_model_is_product_neutral_and_matters_are_not_session_owned():
    await build_longitudinal_world()
    model = await compile_()
    def keys(node):
        if isinstance(node, dict):
            for k, v in node.items():
                yield str(k).lower()
                yield from keys(v)
        elif isinstance(node, list):
            for v in node:
                yield from keys(v)
    for product in ("sophie", "bloom", "rpd2", "bluum", "health", "companion"):
        assert not any(product in k for k in keys(model)), product
    kinds = set(model["matters"]["by_kind"])
    from src.models.matter import MATTER_KINDS
    assert kinds <= MATTER_KINDS


@pytest.mark.asyncio
async def test_new_person_has_a_valid_empty_model_and_cold_start_coverage():
    async with async_session_maker() as db:
        model = await wm.get_world_model(db, workspace_id=WS, owner_peer_id="user_new", now=NOW, timezone_str=TZ)
    assert model["matters"]["active"] == [] and model["unresolved"]["by_matter"] == []
    assert set(model["coverage"]["frame"]) == {"person", "routines", "people", "work_or_projects",
                                                "preferences_and_boundaries", "relationship_with_system"}
    assert set(model["coverage"]["frame"].values()) == {"unknown"}


@pytest.mark.asyncio
async def test_reading_the_world_model_never_mutates_canonical_state():
    """Reads rebuild only disposable derived state; Matter reconciliation belongs to mutation boundaries."""
    from src.models.matter import Matter, MatterLink
    await build_longitudinal_world()
    await save(loop("Brand new unreconciled thread", message="l-new", created=ago(0, 1)))
    async with async_session_maker() as db:
        before = (len((await db.execute(select(Matter))).scalars().all()),
                  len((await db.execute(select(MatterLink))).scalars().all()))
    await compile_(now=NOW + timedelta(minutes=5))
    await compile_(now=NOW + timedelta(minutes=6), force=True)
    async with async_session_maker() as db:
        after = (len((await db.execute(select(Matter))).scalars().all()),
                 len((await db.execute(select(MatterLink))).scalars().all()))
    assert before == after
    await settle()
    async with async_session_maker() as db:
        assert len((await db.execute(select(Matter))).scalars().all()) == before[0] + 1
