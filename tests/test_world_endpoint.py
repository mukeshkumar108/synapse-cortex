"""GET /v1/memory/world and the exposure report: deterministic views over HTTP, flag-gated, product-isolated."""
import uuid
from datetime import datetime

import pytest
from sqlmodel import select

from src.config import settings
from src.db import async_session_maker
from src.models.known_world import CueExposure
from src.models.world import LedgerItem
from src.services import known_world as kw


@pytest.fixture(autouse=True)
def cfg(monkeypatch):
    monkeypatch.setattr(settings, "SYNAPSE_CORTEX_API_TOKEN", "legacy", raising=False)
    monkeypatch.setattr(settings, "SYNAPSE_PRODUCT_TOKENS", "sophie=ts,bloom=tb", raising=False)
    monkeypatch.setattr(settings, "CONNECTED_WORLD_ENABLED", True, raising=False)


def H(t): return {"Authorization": f"Bearer {t}"}


async def seed(ws, o, who):
    async with async_session_maker() as db:
        p = await kw.create(db, ws, o, name=who, kind="person", summary=f"{who} is an adviser", aliases=[f"{who} L"])
        b = await kw.create(db, ws, o, name=f"{who}'s project", kind="project", summary="A project")
        s = await kw.create(db, ws, o, name=f"{who}'s worry", kind="situation", summary="A developing worry", sensitive=True)
        await kw.link(db, ws, o, from_id=p.id, relation="adviser on", target_kind="entity", target_ref=str(b.id), basis="stated", evidence="q")
        db.add(LedgerItem(honcho_workspace_id=ws, owner_peer_id=o, kind="event", title=f"{who} meeting", status="open", situation_key=f"{who}-meeting",
                          expected_date=datetime(2026, 10, 22), expected_time="15:00", time_basis="stated", time_role="happens", time_zone="Europe/London"))
        await kw.link(db, ws, o, from_id=p.id, relation="involved in", target_kind="ledger", target_ref=f"{who}-meeting", basis="stated", evidence="q")
        await db.commit()
        return p.id, s.id


Q = {"now": "2026-10-20T14:00:00+01:00", "time_zone": "Europe/London"}


@pytest.mark.asyncio
async def test_disabled_deployments_answer_empty_and_enabled_ones_serve_the_views(async_client, monkeypatch):
    o = f"u-{uuid.uuid4().hex[:6]}"
    await seed("wsE", o, "Morgan")
    monkeypatch.setattr(settings, "CONNECTED_WORLD_ENABLED", False, raising=False)
    off = (await async_client.get("/v1/memory/world", params={"workspace_id": "wsE", "owner": o, "q": "Morgan", **Q}, headers=H("legacy"))).json()
    assert off["enabled"] is False and off["overview"] == "" and off["mentions"] == "" and off["shown"] == []
    monkeypatch.setattr(settings, "CONNECTED_WORLD_ENABLED", True, raising=False)
    p = (await async_client.get("/v1/memory/world", params={"workspace_id": "wsE", "owner": o, "q": "I spoke to Morgan today", **Q}, headers=H("legacy"))).json()
    assert p["enabled"] and "THEIR WORLD RIGHT NOW" in p["overview"] and "Morgan meeting: Thu 22 Oct, 3:00pm" in p["mentions"]
    ent = (await async_client.get("/v1/memory/world", params={"workspace_id": "wsE", "owner": o, "view": "entity", "q": "Morgan L", "depth": "deep", **Q}, headers=H("legacy"))).json()
    assert ent["found"] and "Supporting evidence" in ent["text"]
    nope = (await async_client.get("/v1/memory/world", params={"workspace_id": "wsE", "owner": o, "view": "entity", "q": "Zed", **Q}, headers=H("legacy"))).json()
    assert nope["found"] is False
    ins = (await async_client.get("/v1/memory/world", params={"workspace_id": "wsE", "owner": o, "view": "inspect"}, headers=H("legacy"))).json()
    assert {e["name"] for e in ins["entities"]} >= {"Morgan", "Morgan's project"} and any(l["basis"] == "stated" for l in ins["links"])
    for bad in ({"view": "nope"}, {"view": "entity", "q": "Morgan", "depth": "abyss"}, {"now": "tuesday"}):
        assert (await async_client.get("/v1/memory/world", params={"workspace_id": "wsE", "owner": o, **bad}, headers=H("legacy"))).status_code == 422


@pytest.mark.asyncio
async def test_exposure_is_recorded_once_per_sitting_through_the_api(async_client):
    o = f"u-{uuid.uuid4().hex[:6]}"
    pid, sid = await seed("wsE", o, "Morgan")
    body = {"workspace_id": "wsE", "owner": o, "refs": [{"source": "entity", "ref": str(sid)}], "now": "2026-10-20T10:00:00+00:00"}
    for minutes in (0, 5, 20):
        r = await async_client.post("/v1/memory/world/exposure", json={**body, "now": f"2026-10-20T10:{minutes:02d}:00+00:00"}, headers=H("legacy"))
        assert r.status_code == 200
    r = await async_client.post("/v1/memory/world/exposure", json={**body, "now": "2026-10-20T15:00:00+00:00"}, headers=H("legacy"))
    async with async_session_maker() as db:
        x = (await db.execute(select(CueExposure).where(CueExposure.owner_peer_id == o))).scalars().one()
    assert x.shown_count == 2


@pytest.mark.asyncio
async def test_two_products_with_the_same_ids_share_no_entities_links_or_exposure(async_client):
    o = f"u-{uuid.uuid4().hex[:6]}"                                    # THE SAME user id and workspace name in both products
    spid, ssid = await seed("wsI", o, "SophieMorgan")
    bpid, bsid = await seed("bloom::wsI", o, "BloomMorgan")
    q = {"workspace_id": "wsI", "owner": o, **Q}
    s = (await async_client.get("/v1/memory/world", params={**q, "q": "SophieMorgan and BloomMorgan"}, headers=H("ts"))).json()
    b = (await async_client.get("/v1/memory/world", params={**q, "q": "SophieMorgan and BloomMorgan"}, headers=H("tb"))).json()
    assert "SophieMorgan" in s["mentions"] and "BloomMorgan" not in (s["mentions"] + s["overview"])
    assert "BloomMorgan" in b["mentions"] and "SophieMorgan" not in (b["mentions"] + b["overview"])
    for tok, mine, theirs in (("ts", "SophieMorgan", "BloomMorgan"), ("tb", "BloomMorgan", "SophieMorgan")):
        ent = (await async_client.get("/v1/memory/world", params={**q, "view": "entity", "q": theirs}, headers=H(tok))).json()
        assert ent["found"] is False                                    # the other product's person simply does not exist here
        ins = (await async_client.get("/v1/memory/world", params={**q, "view": "inspect"}, headers=H(tok))).json()
        assert all(theirs not in e["name"] for e in ins["entities"]) and all(theirs not in l["from"] for l in ins["links"])
    await async_client.post("/v1/memory/world/exposure", json={"workspace_id": "wsI", "owner": o, "refs": [{"source": "entity", "ref": str(ssid)}]}, headers=H("ts"))
    ins_b = (await async_client.get("/v1/memory/world", params={**q, "view": "inspect"}, headers=H("tb"))).json()
    assert ins_b["exposure"] == []                                      # Sophie's exposure is invisible to Bloom
    assert (await async_client.get("/v1/memory/world", params={**q, "companion_id": "sophie"}, headers=H("tb"))).status_code == 403
    assert (await async_client.get("/v1/memory/world", params={**q, "workspace_id": "bloom::wsI"}, headers=H("tb"))).status_code == 422


@pytest.mark.asyncio
async def test_export_and_delete_are_confirmed_product_scoped_and_complete_for_the_owners_rows(monkeypatch):
    from httpx import ASGITransport, AsyncClient
    from src.main import app
    o1, o2 = f"u-{uuid.uuid4().hex[:6]}", f"u-{uuid.uuid4().hex[:6]}"
    await seed("sophie-ws", o1, "Morgan")
    ob = "bloom-" + o1
    await seed("bloom::bloom-ws", ob, "Quentin")          # the same person-id in another product (Runtime qualifies owners per product)
    await seed("sophie-ws", o2, "Nadia")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
        ex = (await c.get(f"/v1/memory/export?workspace_id=sophie-ws&owner={o1}&companion_id=sophie", headers=H("ts"))).json()
        assert {e["name"] for e in ex["tables"]["known_entities"]} == {"Morgan", "Morgan's project", "Morgan's worry"} and ex["tables"]["ledger_items"] and ex["not_covered"]
        no = await c.post("/v1/memory/delete", headers=H("ts"), json={"workspace_id": "sophie-ws", "owner": o1, "companion_id": "sophie", "confirm": "yes"})
        assert no.status_code == 422                                              # permanent: must be confirmed with the owner id
        ok = await c.post("/v1/memory/delete", headers=H("ts"), json={"workspace_id": "sophie-ws", "owner": o1, "companion_id": "sophie", "confirm": o1})
        assert ok.json()["deleted"]["known_entities"] == 3 and ok.json()["deleted"]["ledger_items"] == 1 and ok.json()["remaining"] == {}
        after = (await c.get(f"/v1/memory/export?workspace_id=sophie-ws&owner={o1}&companion_id=sophie", headers=H("ts"))).json()
        assert not any(after["tables"].values())
        other_product = (await c.get(f"/v1/memory/export?workspace_id=bloom-ws&owner={ob}&companion_id=bloom", headers=H("tb"))).json()
        assert {e["name"] for e in other_product["tables"]["known_entities"]} == {"Quentin", "Quentin's project", "Quentin's worry"}   # untouched
        wrong_owner = await c.get(f"/v1/memory/export?workspace_id=sophie-ws&owner=bloom-someone&companion_id=sophie", headers=H("ts"))
        assert wrong_owner.status_code == 403                                      # a Sophie credential cannot name a Bloom owner (tables keyed by owner alone)
        same_ws_other_owner = (await c.get(f"/v1/memory/export?workspace_id=sophie-ws&owner={o2}&companion_id=sophie", headers=H("ts"))).json()
        assert same_ws_other_owner["tables"]["known_entities"]
        cross = await c.post("/v1/memory/delete", headers=H("ts"), json={"workspace_id": "bloom-ws", "owner": ob, "companion_id": "bloom", "confirm": ob})
        assert cross.status_code in (403, 404, 422) or cross.json()["deleted"]["known_entities"] == 0      # Sophie's credential cannot delete Bloom's data


@pytest.mark.asyncio
async def test_callers_are_told_when_a_consolidation_for_this_person_is_still_running(async_client):
    from datetime import datetime as _dt, timedelta as _td
    from src.models.world import MemoryRun
    o = f"u-{uuid.uuid4().hex[:6]}"
    await seed("wsP2", o, "Morgan")
    params = {"workspace_id": "wsP2", "owner": o, **Q}
    assert (await async_client.get("/v1/memory/world", params=params, headers=H("legacy"))).json()["pending_consolidations"] == 0
    async with async_session_maker() as db:
        db.add(MemoryRun(honcho_workspace_id="wsP2", owner_peer_id=o, conversation_id="c", session_id="s", status="running", started_at=_dt.utcnow() - _td(minutes=2)))
        db.add(MemoryRun(honcho_workspace_id="wsP2", owner_peer_id=o, conversation_id="c", session_id="old", status="running", started_at=_dt.utcnow() - _td(hours=3)))   # an orphan is not "pending"
        await db.commit()
    assert (await async_client.get("/v1/memory/world", params=params, headers=H("legacy"))).json()["pending_consolidations"] == 1
    assert (await async_client.get("/v1/memory/ledger", params=params, headers=H("legacy"))).json()["pending_consolidations"] == 1
