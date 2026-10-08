"""Agency between turns: the Heart stores wants/intentions as objectives; Pressure stores paced off-screen developments with an arrival lifecycle. Models propose, code bounds."""
import json
from datetime import timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.world import WorldEvent, WorldIdentity, WorldObjective
from src.services import character_agency as ca
from src.services import nano_adapter
from tests.cortex_fixtures import NOW, WS

import uuid


def test_json_is_found_inside_fences_reasoning_and_prose():
    assert nano_adapter.extract_json('```json\n{"items": []}\n```') == {"items": []}
    assert nano_adapter.extract_json('<think>hm {not json}</think>Sure! {"a": {"b": 1}} hope that helps') == {"a": {"b": 1}}
    assert nano_adapter.extract_json("no json here") is None and nano_adapter.extract_json("") is None


async def world(owner):
    async with async_session_maker() as db:
        for role in ("companion_actor", "user_actor"):
            db.add(WorldIdentity(honcho_workspace_id=WS, owner_peer_id=owner, role=role, entity_id=uuid.uuid4()))
        await db.commit()


@pytest.mark.asyncio
async def test_heart_creates_updates_closes_dedupes_and_bounds_what_she_carries():
    owner = "world:heart-1"
    await world(owner)
    async with async_session_maker() as db:
        out = await ca._apply_heart(db, WS, owner, [
            {"op": "create", "kind": "unsaid", "text": "I haven't told him I read the message.", "next_move": "raise it if he mentions his brother", "ready_when": "once things are warm", "basis": "explicit", "strength": 0.8},
            {"op": "create", "kind": "curious", "text": "I want to know what he felt when he said he'd be fine.", "basis": "inferred"},
            {"op": "create", "kind": "unsaid", "text": "I haven't told him I read the message."},                 # duplicate: ignored
        ], [])
        assert out["created"] == 2
        live = await ca.live_heart_items(db, WS, owner)
        by_kind = {o.kind: o for o in live}
        assert by_kind["unsaid"].next_move.startswith("raise it") and by_kind["unsaid"].formation == "explicit" and by_kind["curious"].formation == "inferred"
        assert all(o.source == "heart" and o.toward_entity_id for o in live)
        again = await ca._apply_heart(db, WS, owner, [
            {"op": "update", "id": str(by_kind["unsaid"].id), "kind": "unsaid", "text": "I still haven't told him I read the message.", "ready_when": "if he asks"},
            {"op": "done", "id": str(by_kind["curious"].id)},
            {"op": "update", "id": "not-mine", "text": "ignored"}], live)
        assert again == {"created": 0, "updated": 1, "closed": 1}
        live = await ca.live_heart_items(db, WS, owner)
        assert [o.text for o in live] == ["I still haven't told him I read the message."]
        many = [{"op": "create", "kind": "want", "text": f"I want thing number {i} between us", "strength": i / 20} for i in range(12)]
        await ca._apply_heart(db, WS, owner, many, live)
        assert len(await ca.live_heart_items(db, WS, owner)) <= ca.MAX_LIVE_HEART


@pytest.mark.asyncio
async def test_heart_without_a_pinned_character_changes_nothing():
    async with async_session_maker() as db:
        assert (await ca._apply_heart(db, WS, "world:unpinned", [{"op": "create", "text": "I want x"}], []))["reason"] == "no_pinned_character"


@pytest.mark.asyncio
async def test_pressure_is_paced_and_walks_pending_arrived_told():
    owner = "world:pressure-1"
    async with async_session_maker() as db:
        assert await ca._pressure_gate(db, WS, owner) is None
        db.add(WorldEvent(honcho_workspace_id=WS, owner_peer_id=owner, label="Liam's message arrives", kind="development", origin="story_pressure", arrival="pending",
                          detail=json.dumps({"what_happens": "Liam messages Elena.", "bears_on": "it reopens the question"})))
        await db.commit()
        assert await ca._pressure_gate(db, WS, owner) == "one_already_waiting"              # at most one waiting at a time
        assert await ca.pending_arrivals(db, WS, owner) == []                                  # pending is invisible to the foreground
        assert (await ca.advance_arrivals(db, WS, owner, new_sitting=False))["arrived"] == 0   # nothing arrives mid-sitting
        assert (await ca.advance_arrivals(db, WS, owner, new_sitting=True))["arrived"] == 1    # the person returns: it arrives
        shown = await ca.pending_arrivals(db, WS, owner)
        assert shown[0]["what_happens"] == "Liam messages Elena." and shown[0]["bears_on"] == "it reopens the question"
        assert (await ca.advance_arrivals(db, WS, owner, new_sitting=False, told_ids=[shown[0]["id"]]))["told"] == 1
        assert await ca.pending_arrivals(db, WS, owner) == []                                  # shown once
        assert await ca._pressure_gate(db, WS, owner) == "too_soon"                            # and the next one waits


@pytest.mark.asyncio
async def test_pressure_daily_cap(monkeypatch):
    owner = "world:pressure-cap"
    async with async_session_maker() as db:
        monkeypatch.setattr(ca, "PRESSURE_MIN_GAP", timedelta(seconds=0))
        for i in range(ca.PRESSURE_MAX_PER_DAY):
            db.add(WorldEvent(honcho_workspace_id=WS, owner_peer_id=owner, label=f"d{i}", kind="development", origin="story_pressure", arrival="told", detail="{}"))
        await db.commit()
        assert await ca._pressure_gate(db, WS, owner) == "daily_cap"
