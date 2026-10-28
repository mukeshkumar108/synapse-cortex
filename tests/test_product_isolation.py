"""PRODUCT ISOLATION INVARIANT: Cortex is shared technology, not shared personal memory.

Sophie, Bloom and any future product are independent products. Their users, conversations,
notebooks, arcs, operational records, attention actions and prepared context are isolated
by default — including when two products use the SAME user id and the SAME workspace name.

These tests attack the boundary from every side: a forged claim, a forged namespace, a
guessed run id, a route the product has no business calling, a background job pointed at
the wrong workspace, and identical identifiers in two products. No network; models scripted.
"""
import asyncio
import json
import uuid
from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from src.config import settings
from src.db import async_session_maker
from src.main import app
from src.models.world import (AttentionAction, AttentionEvent, ContinuingArc, LedgerItem, MemoryRun,
                              NotebookPage, SittingPreparation)
from src.services import attention_cycle, maintenance_agent as ma, memory_pipeline as mp, product_scope

LEGACY, TOK_SOPHIE, TOK_BLOOM = "legacy-internal-token", "tok-sophie", "tok-bloom"
W = "shared-workspace-name"       # the SAME workspace name and user id are used by both products on purpose


@pytest.fixture(autouse=True)
def tokens(monkeypatch):
    monkeypatch.setattr(settings, "SYNAPSE_CORTEX_API_TOKEN", LEGACY, raising=False)
    monkeypatch.setattr(settings, "SYNAPSE_PRODUCT_TOKENS", f"sophie={TOK_SOPHIE},bloom={TOK_BLOOM}", raising=False)
    yield
    mp.set_model_fn(None)
    ma.set_chat_fn(None)


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


def _tc(i, name, args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class Models:
    """Scripted pipeline model. The ledger witness reports ONE item whose title carries the product,
    so any leak between products is visible in the data itself."""

    def __init__(self, label):
        self.label = label

    async def __call__(self, kind, prompt, max_tokens, models):
        text = {"discovery": f"{self.label} findings: they talked about {self.label} things at length for the notes.",
                "handoff": f"{self.label} handoff.", "arc": f"{self.label} ARC text.",
                "preparation": f"{self.label} PREPARED NOTES.",
                "ledger": f"ITEM: {self.label} appointment\nKIND: event\nTIMING: Thursday\nDETAIL: {self.label} only\nEVIDENCE: \"hello there friend\"\n"}.get(kind)
        if kind.startswith("edit:"):
            text = f"# {kind.split(':', 1)[1]}\n\n{self.label} PAGE TEXT."
        return {"text": text, "model": "fake", "provider": "fake", "usage": {}, "ms": 1}


def _agent(label):
    key = f"{label.lower()}-appointment"
    steps = [[_tc(1, "list_open", {}), _tc(2, "create_item", {"title": f"{label} appointment", "kind": "event",
                                                                "expected_date": "2026-10-22", "status": "open"})],
             [_tc(3, "list_open", {})],
             [_tc(4, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "ok", "accounting": [{"obs": 1, "treatment": "applied", "key": key}]})]]
    st = {"n": 0}

    async def chat(model, messages):
        step = steps[min(st["n"], len(steps) - 1)]
        st["n"] += 1
        return {"content": "", "tool_calls": step, "finish_reason": "tool_calls", "model": model, "provider": "fake", "usage": {}}
    return chat


MSGS = [{"id": "m0", "speaker": "user", "text": "hello there friend"}, {"id": "m1", "speaker": "assistant", "text": "hi"}]


async def _run_via_http(client, tok, owner, label, conv, companion_id=None, workspace=W):
    mp.set_model_fn(Models(label))
    ma.set_chat_fn(_agent(label))
    body = {"workspace_id": workspace, "owner": owner, "conversation_id": conv, "session_id": f"{conv}:s",
            "messages": MSGS, "session_time": "2026-10-19T20:00:00+01:00", "time_zone": "Europe/London"}
    if companion_id:
        body["companion_id"] = companion_id
    r = await client.post("/v1/memory/consolidate", json=body, headers=H(tok))
    assert r.status_code == 202, r.text
    rid = r.json()["run_id"]
    for _ in range(80):
        st = (await client.get(f"/v1/memory/run/{rid}", headers=H(tok))).json()
        if st["status"] in ("consolidated", "replay_noop", "empty", "failed"):
            return rid, st
        await asyncio.sleep(0.1)
    raise AssertionError("run never finished")


# ------------------------------------------------------------- credentials ----

@pytest.mark.asyncio
async def test_unknown_or_missing_credential_is_rejected(async_client):
    for headers in ({}, H("nope"), {"Authorization": "Bearer "}):
        r = await async_client.get("/v1/memory/state", params={"workspace_id": W, "owner": "u"}, headers=headers)
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_a_product_credential_cannot_claim_another_product(async_client):
    base = {"workspace_id": W, "owner": "u1"}
    r = await async_client.get("/v1/memory/state", params={**base, "companion_id": "sophie"}, headers=H(TOK_BLOOM))
    assert r.status_code == 403 and "product_mismatch" in r.text
    r = await async_client.get("/v1/memory/preparation", params={**base, "companion_id": "bloom"}, headers=H(TOK_SOPHIE))
    assert r.status_code == 403
    r = await async_client.post("/v1/memory/consolidate", headers=H(TOK_BLOOM), json={
        **base, "conversation_id": "c", "session_id": "s", "messages": MSGS, "companion_id": "sophie"})
    assert r.status_code == 403
    # with no claim at all, the credential decides
    ok = await async_client.get("/v1/memory/state", params=base, headers=H(TOK_BLOOM))
    assert ok.status_code == 200 and ok.json()["product"] == "bloom"
    assert (await async_client.get("/v1/memory/state", params=base, headers=H(TOK_SOPHIE))).json()["product"] == "sophie"


@pytest.mark.asyncio
async def test_the_internal_credential_still_names_its_product_and_unknown_products_fail(async_client):
    base = {"workspace_id": W, "owner": "u1"}
    assert (await async_client.get("/v1/memory/state", params={**base, "companion_id": "bloom"}, headers=H(LEGACY))).json()["product"] == "bloom"
    assert (await async_client.get("/v1/memory/state", params=base, headers=H(LEGACY))).json()["product"] == "sophie"    # compat default
    r = await async_client.get("/v1/memory/state", params={**base, "companion_id": "edgar"}, headers=H(LEGACY))
    assert r.status_code == 422 and "unknown_memory_product" in r.text


@pytest.mark.asyncio
async def test_a_namespace_cannot_be_forged_by_any_caller(async_client):
    for tok in (TOK_SOPHIE, TOK_BLOOM, LEGACY):
        for ws in ("bloom::" + W, "sophie::" + W, "x::y"):
            r = await async_client.get("/v1/memory/state", params={"workspace_id": ws, "owner": "u1"}, headers=H(tok))
            assert r.status_code == 422, (tok, ws, r.text)
            r = await async_client.post("/v1/memory/consolidate", headers=H(tok), json={
                "workspace_id": ws, "owner": "u1", "conversation_id": "c", "session_id": "s", "messages": MSGS})
            assert r.status_code == 422


# ------------------------------------------------------------------ routes ----

def _all_routes():
    """Every (path, methods) the app serves, including routers mounted via include_router."""
    def walk(routes):
        for x in routes:
            if getattr(x, "path", None) is not None and getattr(x, "methods", None):
                yield x.path, set(x.methods)
            else:
                sub = getattr(x, "original_router", None) or getattr(x, "router", None)
                if sub is not None:
                    yield from walk(sub.routes)
    return list(walk(app.routes))


def _concrete(path):
    import re
    return re.sub(r"\{[^}]+\}", "x", path)


@pytest.mark.asyncio
async def test_every_route_outside_the_product_list_is_denied_to_product_credentials(async_client):
    """Route inventory: enumerate the real app. A product credential must be refused (403) on every
    route that is not on the explicit product list, before any handler runs."""
    denied, allowed = [], []
    for path, methods in _all_routes():
        if path in ("/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/health"):
            continue
        for m in sorted(methods - {"HEAD", "OPTIONS"}):
            url = _concrete(path)
            if product_scope.route_allowed_for_product(m, url):
                allowed.append((m, path))
                continue
            for tok in (TOK_BLOOM, TOK_SOPHIE):
                r = await async_client.request(m, url, headers=H(tok), json={} if m in ("POST", "PUT", "PATCH") else None)
                assert r.status_code == 403, f"{m} {path} reachable with a product credential ({r.status_code})"
            denied.append((m, path))
    served = {p for p, _ in _all_routes()}
    assert len(denied) > 80 and set(app.openapi()["paths"]) <= served      # the inventory covers the whole documented surface
    assert sorted(allowed) == sorted([("POST", "/v1/memory/consolidate"), ("GET", "/v1/memory/run/{run_id}"),
                                      ("GET", "/v1/memory/preparation"), ("POST", "/v1/memory/prepare"), ("GET", "/v1/memory/state"),
                                      ("GET", "/v1/memory/ledger"), ("GET", "/v1/memory/world"), ("GET", "/v1/memory/notes"), ("POST", "/v1/memory/world/exposure"), ("GET", "/v1/memory/export"), ("POST", "/v1/memory/delete")])


# ------------------------------------------------- identical ids, two products ----

@pytest.mark.asyncio
async def test_identical_user_and_workspace_in_two_products_share_nothing(async_client):
    U = f"user-{uuid.uuid4().hex[:8]}"                         # THE SAME user id in both products
    s_rid, s_run = await _run_via_http(async_client, TOK_SOPHIE, U, "SOPHIE", "conv-s")
    b_rid, b_run = await _run_via_http(async_client, TOK_BLOOM, U, "BLOOM", "conv-b")
    assert s_run["status"] == "consolidated" and b_run["status"] == "consolidated"

    q = {"workspace_id": W, "owner": U, "include_closed": "true"}
    s_state = (await async_client.get("/v1/memory/state", params=q, headers=H(TOK_SOPHIE))).json()
    b_state = (await async_client.get("/v1/memory/state", params=q, headers=H(TOK_BLOOM))).json()
    s_blob, b_blob = json.dumps(s_state), json.dumps(b_state)
    assert "SOPHIE" in s_blob and "BLOOM" not in s_blob
    assert "BLOOM" in b_blob and "SOPHIE" not in b_blob
    assert [r["title"] for r in s_state["ledger"]] == ["SOPHIE appointment"]
    assert [r["title"] for r in b_state["ledger"]] == ["BLOOM appointment"]
    assert set(s_state["notebook"]) != set(b_state["notebook"])
    assert s_state["arc"]["text"] != b_state["arc"]["text"]
    # prepared context, both read paths
    for tok, mine, theirs in ((TOK_SOPHIE, "SOPHIE", "BLOOM"), (TOK_BLOOM, "BLOOM", "SOPHIE")):
        prep = (await async_client.get("/v1/memory/preparation", params={"workspace_id": W, "owner": U}, headers=H(tok))).json()
        assert prep["found"] and mine in prep["text"] and theirs not in prep["text"]
    # run records: a product cannot read the other's run, even knowing the id
    assert (await async_client.get(f"/v1/memory/run/{b_rid}", headers=H(TOK_SOPHIE))).status_code == 404
    assert (await async_client.get(f"/v1/memory/run/{s_rid}", headers=H(TOK_BLOOM))).status_code == 404
    assert (await async_client.get(f"/v1/memory/run/{b_rid}", headers=H(TOK_BLOOM))).status_code == 200


@pytest.mark.asyncio
async def test_every_stored_row_lives_in_exactly_one_product_namespace(async_client):
    U = f"user-{uuid.uuid4().hex[:8]}"
    await _run_via_http(async_client, TOK_SOPHIE, U, "SOPHIE", "conv-s")
    await _run_via_http(async_client, TOK_BLOOM, U, "BLOOM", "conv-b")
    async with async_session_maker() as db:
        for model in (LedgerItem, NotebookPage, ContinuingArc, SittingPreparation, MemoryRun, AttentionAction, AttentionEvent):
            rows = (await db.execute(select(model).where(model.owner_peer_id == U))).scalars().all()
            for r in rows:
                ws = r.honcho_workspace_id
                assert ws in (W, "bloom::" + W), (model.__name__, ws)
                prod = getattr(r, "product", None)
                if prod is not None:                          # relationship-owned rows also carry their product
                    assert prod == product_scope.product_of_workspace(ws), (model.__name__, prod, ws)
                if model is LedgerItem:
                    assert (ws == W) == ("SOPHIE" in r.title) and (ws != W) == ("BLOOM" in r.title)
        assert (await db.execute(select(LedgerItem).where(LedgerItem.owner_peer_id == U, LedgerItem.honcho_workspace_id == W))).scalars().all()
        assert (await db.execute(select(LedgerItem).where(LedgerItem.owner_peer_id == U, LedgerItem.honcho_workspace_id == "bloom::" + W))).scalars().all()
        # Bloom does not use attention in this release: it must have created none, anywhere
        assert (await db.execute(select(AttentionAction).where(AttentionAction.owner_peer_id == U,
                                                               AttentionAction.honcho_workspace_id == "bloom::" + W))).scalars().all() == []


@pytest.mark.asyncio
async def test_replay_and_serialisation_hold_inside_each_namespace(async_client):
    U = f"user-{uuid.uuid4().hex[:8]}"
    _, first = await _run_via_http(async_client, TOK_BLOOM, U, "BLOOM", "conv-b")
    _, replay = await _run_via_http(async_client, TOK_BLOOM, U, "BLOOM", "conv-b")        # same messages: no-op
    assert first["status"] == "consolidated" and replay["status"] == "replay_noop"
    # the other product's identical conversation id and message ids are NOT covered by Bloom's run
    _, s_first = await _run_via_http(async_client, TOK_SOPHIE, U, "SOPHIE", "conv-b")
    assert s_first["status"] == "consolidated"
    async with async_session_maker() as db:
        assert len((await db.execute(select(LedgerItem).where(LedgerItem.owner_peer_id == U))).scalars().all()) == 2
    # the two products' locks are independent
    assert mp.owner_lock(W, U).key != mp.owner_lock("bloom::" + W, U).key


# ----------------------------------------------- pipeline-level and background ----

@pytest.mark.asyncio
async def test_the_pipeline_refuses_a_workspace_from_another_product():
    async with async_session_maker() as db:
        with pytest.raises(ValueError):
            await mp.read_state(db, workspace_id=W, owner="u", companion_id="bloom")
        with pytest.raises(ValueError):
            await mp.get_preparation(db, workspace_id="bloom::" + W, owner="u", companion_id="sophie")
        with pytest.raises(ValueError):
            await mp.consolidate(db, workspace_id=W, owner="u", conversation_id="c", session_id="s", messages=MSGS, companion_id="bloom")


@pytest.mark.asyncio
async def test_background_jobs_for_one_product_never_touch_another():
    """A due follow-up in Bloom's namespace must be invisible to, and unchanged by, Sophie's scheduled passes."""
    U = f"user-{uuid.uuid4().hex[:8]}"
    past = datetime.utcnow() - timedelta(hours=1)
    async with async_session_maker() as db:
        db.add(AttentionAction(honcho_workspace_id="bloom::" + W, owner_peer_id=U, intent="BLOOM follow-up", kind="followup",
                               state="pending", due_at=past))
        db.add(LedgerItem(honcho_workspace_id="bloom::" + W, owner_peer_id=U, kind="event", title="BLOOM thing", status="open", situation_key="bloom-thing"))
        await db.commit()
    attention_cycle_cfg = attention_cycle.tick_config()
    assert all("::" not in str(attention_cycle_cfg.get("workspace_id", "")) for _ in [0])
    async with async_session_maker() as db:
        became_due = await attention_cycle.mark_due(db, workspace_id=W, owner=U)             # Sophie's due-scan, same owner id
        assert became_due == []
        assert await attention_cycle.pending_attention(db, workspace_id=W, owner=U) == []
        assert [a["intent"] for a in await attention_cycle.pending_attention(db, workspace_id="bloom::" + W, owner=U)] == ["BLOOM follow-up"]
        assert await mp.open_ledger(db, W, U) == []
        out = await attention_cycle.tick_once(workspace_id=W, owner=U)                         # Sophie's scheduled tick
        assert out.get("became_due") == [] and out.get("review", {}).get("status") in (None, "skipped")
        row = (await db.execute(select(AttentionAction).where(AttentionAction.owner_peer_id == U))).scalars().one()
        assert row.state == "pending"                                                           # untouched by Sophie's jobs
    # orphan recovery changes status only; it never exposes or moves another product's data
    async with async_session_maker() as db:
        recovered = await mp.recover_orphaned_runs(db)
        assert all(set(r) <= {"run_id", "session_id", "owner"} for r in recovered)


def test_the_sophie_workspace_is_unchanged_so_no_existing_row_is_migrated():
    assert product_scope.scoped_workspace("sophie", "llm-test-agent") == "llm-test-agent"
    assert product_scope.scoped_workspace("bloom", "llm-test-agent") == "bloom::llm-test-agent"
    assert product_scope.product_of_workspace("llm-test-agent") == "sophie"
    assert product_scope.product_of_workspace("bloom::llm-test-agent") == "bloom"
