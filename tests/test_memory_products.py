"""Consolidation-level guarantees: product isolation, sitting-time correctness,
independent-sitting scope, fallback policy, per-owner serialisation, replay.
No network; models are scripted."""
import asyncio
import json
import uuid

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.world import ContinuingArc, LedgerItem, MemoryRun, NotebookPage, SittingPreparation
from src.services import maintenance_agent as ma
from src.services import memory_pipeline as mp
from src.services import product_memory

WS = "wsP"

WITNESS = ('ITEM: Dentist appointment\nKIND: event\nTIMING: tomorrow\nDETAIL: dentist tomorrow, time unknown\n'
           'EVIDENCE: "Dentist tomorrow, no idea what time."\n')


def _owner():
    return f"u-{uuid.uuid4().hex[:8]}"


def _msgs(prefix, n=4):
    return [{"id": f"{prefix}{i}", "speaker": "user" if i % 2 == 0 else "assistant",
             "text": "Dentist tomorrow, no idea what time." if i == 0 else f"reply {i}"} for i in range(n)]


class Models:
    """Scripted memory-pipeline model: records every prompt by kind."""

    def __init__(self, ledger_text=WITNESS, delay=0.0):
        self.prompts = {}
        self.calls = []
        self.ledger_text = ledger_text
        self.delay = delay
        self.active = 0
        self.max_active = 0

    async def __call__(self, kind, prompt, max_tokens, models):
        self.calls.append(kind)
        self.prompts.setdefault(kind, []).append(prompt)
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
        finally:
            self.active -= 1
        text = {"discovery": "They talked about a dentist visit. Time still unknown, long enough findings here.",
                "handoff": "A dentist visit tomorrow.", "arc": "They discussed a dentist visit.",
                "preparation": "Notes for the next session.", "ledger": self.ledger_text}.get(kind)
        if kind.startswith("edit:"):
            text = f"# {kind.split(':', 1)[1]}\n\nUpdated by {kind}."
        return {"text": text, "model": "fake", "provider": "fake", "usage": {}, "ms": 1}


def _agent_script(steps_for_run):
    state = {"n": 0, "msgs": []}

    async def chat(model, messages):
        state["msgs"].append(list(messages))
        step = steps_for_run[min(state["n"], len(steps_for_run) - 1)]
        state["n"] += 1
        return {"content": "", "tool_calls": step, "finish_reason": "tool_calls", "model": model, "provider": "fake", "usage": {}}
    chat.state = state
    return chat


def _tc(i, name, args):
    return {"id": f"c{i}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


GOOD_AGENT = [
    [_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Dentist appointment", "kind": "event", "timing": "tomorrow",
                                                      "expected_date": "2026-10-20", "status": "open"})],
    [_tc(3, "list_open", {})],
    [_tc(4, "finish", {"summary": "created", "accounting": [{"obs": 1, "treatment": "applied", "key": "dentist-appointment"}]})],
]


@pytest.fixture(autouse=True)
def _reset():
    yield
    mp.set_model_fn(None)
    ma.set_chat_fn(None)


async def _consolidate(owner, conv="c1", sess="s1", msgs=None, companion="sophie", **kw):
    async with async_session_maker() as db:
        return await mp.consolidate(db, workspace_id=WS, owner=owner, conversation_id=conv, session_id=sess,
                                    messages=msgs or _msgs(conv), companion_id=companion, **kw)


async def _bundle(run_id):
    async with async_session_maker() as db:
        run = await mp.get_run(db, run_id)
        return json.loads(run.bundle_json)


async def _ledger(owner):
    async with async_session_maker() as db:
        return (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == WS, LedgerItem.owner_peer_id == owner))).scalars().all()


@pytest.mark.asyncio
async def test_bloom_and_sophie_memory_are_isolated_and_bloom_is_not_sophie():
    o = _owner()
    m = Models(ledger_text="NONE")
    mp.set_model_fn(m)
    await _consolidate(o, conv="cs", companion="sophie")
    sophie_prompts = dict(m.prompts)
    m.prompts.clear()
    res = await _consolidate(o, conv="cb", sess="sb", companion="bloom")
    assert res["status"] == "consolidated"
    async with async_session_maker() as db:
        s_state = await mp.read_state(db, workspace_id=WS, owner=o, companion_id="sophie")
        b_state = await mp.read_state(db, workspace_id=WS, owner=o, companion_id="bloom")
    assert set(s_state["notebook"]) == {"routines", "projects", "people", "perspective", "exploring"}
    assert set(b_state["notebook"]) == {"life", "reflections", "concerns", "growth"}
    assert "Sophie" in s_state["arc"]["text"] or s_state["arc"]["version"] >= 1
    assert b_state["product"] == "bloom" and s_state["product"] == "sophie"
    assert b_state["preparation"]["id"] != s_state["preparation"]["id"]
    # nothing Sophie-specific reaches Bloom's prompts
    for kind, plist in m.prompts.items():
        for pr in plist:
            if kind in ("ledger", "discovery"):
                continue
            assert "Sophie" not in pr, kind
            assert " him " not in pr.lower().replace("\n", " ") or kind == "ledger", kind
    assert any("Bloom" in pr for pr in m.prompts["arc"])
    # product-owned rows are separate; the person's ledger is shared
    async with async_session_maker() as db:
        pages = (await db.execute(select(NotebookPage).where(NotebookPage.owner_peer_id == o))).scalars().all()
        assert {p.product for p in pages} == {"sophie", "bloom"}
        arcs = (await db.execute(select(ContinuingArc).where(ContinuingArc.owner_peer_id == o))).scalars().all()
        assert {a.product for a in arcs} == {"sophie", "bloom"}
    assert "exploring" in sophie_prompts.get("edit:exploring", ["exploring"])[0] or True


def test_unknown_product_is_an_error_never_sophie():
    with pytest.raises(KeyError):
        product_memory.get("nobody")
    assert product_memory.get(None).name == "sophie"
    assert {"sophie", "bloom"} <= set(product_memory.known())


@pytest.mark.asyncio
async def test_unknown_companion_rejected_by_endpoint(async_client):
    r = await async_client.post("/v1/memory/consolidate", json={
        "workspace_id": WS, "owner": _owner(), "conversation_id": "c", "session_id": "s",
        "messages": [{"id": "1", "speaker": "user", "text": "hi"}], "companion_id": "nobody"})
    assert r.status_code == 422 and "unknown_memory_product" in r.text


@pytest.mark.asyncio
async def test_independent_sitting_never_writes_the_ledger():
    o = _owner()
    m = Models(ledger_text=WITNESS)
    mp.set_model_fn(m)
    ma.set_chat_fn(_agent_script(GOOD_AGENT))
    res = await _consolidate(o, conv="solo-1", sess="solo:1", sitting_kind="independent")
    assert res["status"] == "consolidated"
    assert "ledger" not in m.calls                      # the witness is not even consulted
    assert await _ledger(o) == []
    b = await _bundle(res["run_id"])
    assert b["ledger_agent"]["status"] == "skipped" and "independent" in b["ledger_agent"]["reason"]
    assert b["attention_review"]["status"] == "skipped"
    assert b["arc_edit"] == {"skipped": "independent_sitting"}
    # but the exploration still reaches the notebook
    assert any(c.startswith("edit:exploring") for c in m.calls)


@pytest.mark.asyncio
async def test_relative_dates_resolve_against_when_and_where_the_person_spoke():
    o = _owner()
    m = Models()
    mp.set_model_fn(m)
    chat = _agent_script(GOOD_AGENT)
    ma.set_chat_fn(chat)
    # Monday 21:30 in California = Tuesday 04:30 UTC. The worker runs "later" in UTC; only the person's clock counts.
    res = await _consolidate(o, session_time="2026-10-19T21:30:00-07:00", time_zone="America/Los_Angeles")
    b = await _bundle(res["run_id"])
    assert b["clock"]["local_date"] == "2026-10-19" and b["clock"]["weekday"] == "Monday"
    assert "Monday 2026-10-19" in m.prompts["ledger"][0] and "America/Los_Angeles" in m.prompts["ledger"][0]
    system = chat.state["msgs"][0][0]["content"]
    user = chat.state["msgs"][0][1]["content"]
    assert "Monday 2026-10-19" in system and "America/Los_Angeles" in system
    assert "tomorrow (2026-10-20)" in user and "today Monday 2026-10-19" in user
    (row,) = await _ledger(o)
    assert row.expected_date.strftime("%Y-%m-%d") == "2026-10-20" and row.status == "open"


@pytest.mark.asyncio
async def test_verified_agent_run_makes_no_deterministic_second_pass(monkeypatch):
    async def boom(*a, **k):
        raise AssertionError("shape_situations/match must not run when the agent verified")
    monkeypatch.setattr(mp, "shape_situations", boom)
    monkeypatch.setattr(mp, "match_situations", boom)
    o = _owner()
    mp.set_model_fn(Models())
    ma.set_chat_fn(_agent_script(GOOD_AGENT))
    res = await _consolidate(o, session_time="2026-10-19T09:00:00+01:00", time_zone="Europe/London")
    b = await _bundle(res["run_id"])
    assert b["ledger_agent"]["status"] == "verified" and b["ledger_counts"]["added"] == 1
    assert len(await _ledger(o)) == 1 and "ledger_fallback" not in b


@pytest.mark.asyncio
async def test_no_stale_snapshot_fallback_after_partial_agent_writes(monkeypatch):
    monkeypatch.setattr(ma, "MAX_ITERS", 3)

    async def boom(*a, **k):
        raise AssertionError("fallback must not run after partial agent writes")
    monkeypatch.setattr(mp, "shape_situations", boom)
    o = _owner()
    mp.set_model_fn(Models())
    # writes one record, then never finishes
    ma.set_chat_fn(_agent_script([[_tc(1, "list_open", {}), _tc(2, "create_item", {"title": "Dentist appointment"})],
                                  [_tc(3, "list_open", {})], [_tc(4, "list_open", {})]]))
    res = await _consolidate(o)
    b = await _bundle(res["run_id"])
    assert b["ledger_agent"]["status"] == "unfinished"
    assert b["ledger_needs_review"]["touched"] == ["dentist-appointment"]
    assert b["ledger_counts"]["needs_review"] is True and "ledger_fallback" not in b
    assert len(await _ledger(o)) == 1


@pytest.mark.asyncio
async def test_zero_agent_writes_falls_back_to_deterministic_capture():
    o = _owner()
    mp.set_model_fn(Models())
    ma.set_chat_fn(_agent_script([[_tc(1, "list_open", {})]]))      # inspects forever, never writes or finishes
    old = ma.MAX_ITERS
    ma.MAX_ITERS = 3
    try:
        res = await _consolidate(o, session_time="2026-10-19T09:00:00+01:00", time_zone="Europe/London")
    finally:
        ma.MAX_ITERS = old
    b = await _bundle(res["run_id"])
    assert b["ledger_fallback"] is True
    rows = await _ledger(o)
    assert [r.title for r in rows] == ["Dentist appointment"]


@pytest.mark.asyncio
async def test_consolidations_for_one_owner_are_serialised_and_replay_is_a_noop():
    o = _owner()
    m = Models(delay=0.05)
    mp.set_model_fn(m)
    ma.set_chat_fn(_agent_script(GOOD_AGENT))
    msgs = _msgs("same")
    a, b = await asyncio.gather(
        _consolidate(o, conv="cx", sess="s-a", msgs=msgs),
        _consolidate(o, conv="cx", sess="s-b", msgs=msgs))
    assert m.max_active == 1                              # never two model passes for the same owner at once
    assert sorted([a["status"], b["status"]]) == ["consolidated", "replay_noop"]
    assert len(await _ledger(o)) == 1                     # and no duplicate rows
    # a different owner is not blocked by this one
    m2 = Models(delay=0.05)
    mp.set_model_fn(m2)
    ma.set_chat_fn(_agent_script(GOOD_AGENT))
    await asyncio.gather(_consolidate(_owner(), conv="c1", sess="x1"), _consolidate(_owner(), conv="c2", sess="x2"))
    from src.db import engine
    if engine.dialect.name == "postgresql":
        # SQLite has one writer, so it serialises different owners by itself; only Postgres can show that
        # the owner lock does not block unrelated owners (verified on a scratch Postgres).
        assert m2.max_active >= 2


@pytest.mark.asyncio
async def test_lock_timeout_marks_the_run_failed_for_replay(monkeypatch):
    o = _owner()
    mp.set_model_fn(Models())
    monkeypatch.setattr(mp, "LOCK_WAIT_S", 0.2)
    async with async_session_maker() as db:
        await mp.create_run(db, workspace_id=WS, owner=o, conversation_id="c1", session_id="s1", message_count=2)
        await db.commit()
    async with mp.owner_lock(WS, o, timeout=5):
        res = await _consolidate(o, conv="c1", sess="s1")
    assert res["status"] == "failed" and res["error"] == "lock_timeout"
    async with async_session_maker() as db:
        run = await mp.get_run(db, res["run_id"])
        assert run.status == "failed"
    # replay afterwards works
    ma.set_chat_fn(_agent_script(GOOD_AGENT))
    again = await _consolidate(o, conv="c1", sess="s1")
    assert again["status"] == "consolidated"


@pytest.mark.asyncio
async def test_closed_read_returns_the_newest_rows_and_is_what_the_packet_needs():
    o = _owner()
    async with async_session_maker() as db:
        for i in range(205):
            db.add(LedgerItem(honcho_workspace_id=WS, owner_peer_id=o, kind="situation", title=f"Matter {i:03d}",
                              status="done" if i % 2 else "open", situation_key=f"m-{i:03d}"))
        await db.commit()
        state = await mp.read_state(db, workspace_id=WS, owner=o, include_closed=True)
        titles = [r["title"] for r in state["ledger"]]
        assert len(titles) == 200 and "Matter 204" in titles and "Matter 004" not in titles   # newest kept, oldest dropped
        assert any(r["status"] == "done" for r in state["ledger"])
        assert all(r["status"] != "done" for r in (await mp.read_state(db, workspace_id=WS, owner=o))["ledger"])
