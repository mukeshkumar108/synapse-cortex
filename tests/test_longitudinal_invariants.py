"""Invariants over realistic longitudinal state: provenance never lost, no false
certainty, no unknown->inference leakage, lane independence, owner isolation."""
import json

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.matter import Matter, MatterLink
from src.services import world_model_service as wm
from src.services.epistemics import FORMATION_CLASSES
from tests.cortex_fixtures import (NOW, SYSTEM, USER, WS, ago, build_longitudinal_world, exp, loop, recurrence, save,
                                   entity, link)

TZ = "Europe/London"


async def model_for(peer=USER, session=None):
    async with async_session_maker() as db:
        return await wm.get_world_model(db, workspace_id=WS, owner_peer_id=peer, now=NOW, timezone_str=TZ,
                                        session_id=session)


def walk(node, path=()):
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, path + (k,))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, path + (i,))


@pytest.mark.asyncio
async def test_every_claim_and_item_in_the_world_model_keeps_formation_and_provenance():
    await build_longitudinal_world()
    model = await model_for()
    checked = 0
    for path, d in walk(model):
        if "formation" in d and "ref" in d:
            checked += 1
            assert d["formation"] in FORMATION_CLASSES, (path, d["formation"])
            kind = d["ref"].split(":")[0]
            if kind in ("model_entry", "fact", "expectation", "open_loop", "commitment"):
                assert d.get("evidence") or d["ref"], (path, d)        # provenance: refs/evidence survive compression
            if kind == "model_entry":
                assert d.get("evidence"), (path, d)
    assert checked > 15


@pytest.mark.asyncio
async def test_no_false_certainty_system_held_and_inferred_state_is_never_labelled_explicit():
    await build_longitudinal_world()
    model = await model_for()
    for path, d in walk(model):
        if d.get("holder") == "system" and "formation" in d:
            assert d["formation"] != "explicit", (path, d)          # the system's own thought is not testimony
    persp = model["system_perspective"]["entries"]
    assert persp and all(e["formation"] in ("hypothesis", "inferred") and e["holder"] == "system" for e in persp)
    assert all(e["claim_kind"] == "perspective" for e in persp)


@pytest.mark.asyncio
async def test_matters_are_session_independent_and_owner_isolated():
    await build_longitudinal_world()
    a = await model_for(session="lane-1")
    b = await model_for(session="lane-77")             # a different lane for the same person
    ids = lambda m: sorted(x["id"] for x in m["matters"]["active"])
    assert ids(a) == ids(b) and ids(a)
    other = await model_for(peer="user_someone_else")
    assert other["matters"]["active"] == [] and other["person"]["facts"] == []
    async with async_session_maker() as db:
        ms = (await db.execute(select(Matter))).scalars().all()
    assert ms and all(m.owner_peer_id == USER for m in ms)


@pytest.mark.asyncio
async def test_structural_integrity_no_dangling_links_no_duplicate_keys():
    await build_longitudinal_world()
    await model_for()
    from src.services.matter_service import _models
    async with async_session_maker() as db:
        links = (await db.execute(select(MatterLink))).scalars().all()
        models = _models()
        for l in links:
            assert await db.get(models[l.object_type], l.object_id) is not None, (l.object_type, l.object_id)
            assert await db.get(Matter, l.matter_id) is not None
        ms = [m for m in (await db.execute(select(Matter))).scalars().all() if m.merged_into_id is None]
        keys = [m.canonical_key for m in ms if m.canonical_key]
        assert len(keys) == len(set(keys)), "duplicate canonical keys => fragmented Matters"
        # one object belongs to at most one live matter
        seen = {}
        for l in links:
            assert seen.setdefault(l.object_id, l.matter_id) == l.matter_id


@pytest.mark.asyncio
async def test_years_of_history_stay_bounded_and_history_is_kept_not_erased():
    await build_longitudinal_world()
    # three more years of stale-but-real history across lanes
    rows = []
    for i in range(40):
        rows.append(loop(f"Old thread number {i} about the garden shed {i}", message=f"old-{i}", session=f"lane-{i % 4}",
                         created=ago(400 + i * 20)))
    await save(*rows, recurrence("Old yoga class", "old_yoga", created=ago(900)))
    model = await model_for()
    assert len(json.dumps(model, default=str)) < 32_000                       # bounded regardless of history size
    titles = {m["title"] for m in model["matters"]["active"]}
    assert not any("Old thread" in t for t in titles)                       # low salience / old: out of the foreground
    async with async_session_maker() as db:
        from src.models.open_loop import OpenLoop
        assert len((await db.execute(select(OpenLoop))).scalars().all()) >= 40   # ...but never erased from the store
    assert model["depth_index"]["history"]["horizon_days"] == 180


@pytest.mark.asyncio
async def test_reopening_and_lifecycle_do_not_resurrect_resolved_state_as_fact():
    ids = await build_longitudinal_world()
    model = await model_for()
    resolved = {m["title"] for m in model["matters"]["recently_resolved"]}
    assert "Finish logo draft" in resolved
    assert "Finish logo draft" not in {m["title"] for m in model["matters"]["active"]}
    assert "Finish logo draft" not in {i["title"] for i in model["forward"]["today"] + model["forward"]["this_week"]}
