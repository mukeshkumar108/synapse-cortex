"""Companion-owned working space: lifecycle, provenance, isolation, policy, and the no-interpretation guarantee."""
import json

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.world import MemoryRun, NotebookPage, LedgerItem, SittingPreparation, ContinuingArc
from src.services import companion_work as work
from src.services import memory_pipeline


@pytest.fixture(autouse=True)
def policy(monkeypatch):
    monkeypatch.setenv("COMPANION_WORK_POLICY", json.dumps({
        "sophie": {"foreground": "write", "independent": "write"},
        "bloom": {"foreground": "read", "independent": "off"}}))
    async def boom(*a, **k):
        raise AssertionError("a model was called by the working space")
    memory_pipeline.set_model_fn(boom)
    yield
    memory_pipeline.set_model_fn(None)


S = ("ws1", "u1", "sophie")


@pytest.mark.asyncio
async def test_lifecycle_provenance_and_no_interpretation_side_effects():
    async with async_session_maker() as db:
        r = await work.run_tool(db, S, surface="foreground", tool="work_write", sitting_id="sit-1", conversation_id="chat-1",
                                args={"op": "create", "title": "The argument about ladders", "text": "Something about his claim doesn't convince me.", "kind": "doubt"})
        assert r["ok"], r
        iid = r["item_id"]
        r2 = await work.run_tool(db, S, surface="independent", tool="work_write", sitting_id="solo-9",
                                 args={"op": "continue", "id": iid[:8], "text": "Checked: the premise holds only for finite sets."},
                                 evidence=[{"ref": "a3", "kind": "model", "captured": "verbatim reply"}])
        assert r2["ok"] and r2["version"] == 2
        r3 = await work.run_tool(db, S, surface="independent", tool="work_write",
                                 args={"op": "revise", "id": iid, "text": "Revised: it holds only for finite sets.", "note": "earlier form was wrong"})
        assert r3["version"] == 3
        r4 = await work.run_tool(db, S, surface="foreground", tool="work_write", args={"op": "abandon", "id": iid, "note": "no longer interests me"})
        assert r4["status"] == "abandoned"
        r5 = await work.run_tool(db, S, surface="foreground", tool="work_write", args={"op": "continue", "id": iid, "text": "x"})
        assert not r5["ok"] and r5["code"] == "not_open"
        got = await work.get_with_events(db, S, iid)
        acts = [(e.action, e.surface, e.sitting_id, e.author) for e in got["events"]]
        assert acts == [("create", "foreground", "sit-1", "companion:sophie"), ("continue", "independent", "solo-9", "companion:sophie"),
                        ("revise", "independent", "", "companion:sophie"), ("abandon", "foreground", "", "companion:sophie")]
        assert json.loads(got["events"][1].evidence_json)[0]["captured"] == "verbatim reply"
        assert got["item"].text == "Revised: it holds only for finite sets."
        # nothing of the interpretation pipeline moved
        for model in (MemoryRun, NotebookPage, LedgerItem, SittingPreparation, ContinuingArc):
            assert (await db.execute(select(model))).scalars().all() == []


@pytest.mark.asyncio
async def test_isolation_between_companions_and_owners():
    async with async_session_maker() as db:
        r = await work.run_tool(db, S, surface="foreground", tool="work_write", args={"op": "create", "title": "mine", "text": "t"})
        iid = r["item_id"]
        for scope in (("ws1", "u2", "sophie"), ("ws1", "u1", "bloom"), ("ws2", "u1", "sophie")):
            assert (await work.list_items(db, scope)) == []
            out = await work.run_tool(db, scope, surface="foreground", tool="work_read", args={"id": iid})
            assert not out["ok"] and out["code"] in ("not_found", "policy_denied")
        out = await work.run_tool(db, ("ws1", "u2", "sophie"), surface="foreground", tool="work_write", args={"op": "abandon", "id": iid})
        assert not out["ok"] and out["code"] == "not_found"


@pytest.mark.asyncio
async def test_policy_enable_restrict_suppress():
    bloom = ("ws1", "u1", "bloom")
    async with async_session_maker() as db:
        denied = await work.run_tool(db, bloom, surface="foreground", tool="work_write", args={"op": "create", "title": "x"})
        assert not denied["ok"] and denied["code"] == "policy_denied"
        assert (await work.run_tool(db, bloom, surface="foreground", tool="work_read", args={}))["ok"]   # restricted to read
        assert not (await work.run_tool(db, bloom, surface="independent", tool="work_read", args={}))["ok"]  # suppressed
        assert not (await work.run_tool(db, ("ws1", "u1", "edgar"), surface="foreground", tool="work_read", args={}))["ok"]  # unlisted: off
        assert await work.context_block(db, bloom, "independent") == ""


@pytest.mark.asyncio
async def test_context_block_lists_possibilities_with_origin():
    async with async_session_maker() as db:
        await work.run_tool(db, S, surface="foreground", tool="work_write", conversation_id="c1",
                            args={"op": "create", "title": "Look into the 5am thing", "text": "He mentioned waking at 5 twice."})
        block = await work.context_block(db, S, "independent")
    assert "Look into the 5am thing" in block and "while talking with them" in block and "He mentioned waking" in block


@pytest.mark.asyncio
async def test_http_routes(async_client):
    body = {"workspace_id": "wsh", "owner": "uh", "companion_id": "sophie", "surface": "foreground"}
    r = await async_client.post("/v1/work/tool", json={**body, "tool": "work_write", "args": {"op": "create", "title": "hi", "text": "t"}, "sitting_id": "s"})
    assert r.status_code == 200 and r.json()["ok"], r.text
    ctx = await async_client.get("/v1/work/context", params={k: body[k] for k in ("workspace_id", "owner", "companion_id", "surface")})
    assert "hi" in ctx.json()["text"]
    items = await async_client.get("/v1/work/items", params={k: body[k] for k in ("workspace_id", "owner", "companion_id")})
    iid = items.json()["items"][0]["id"]
    detail = await async_client.get(f"/v1/work/items/{iid}", params={k: body[k] for k in ("workspace_id", "owner", "companion_id")})
    assert detail.json()["events"][0]["author"] == "companion:sophie"


def _scripted(steps):
    state = {"n": 0, "prompts": []}

    async def chat(model, messages, max_tokens=800, title="solo"):
        last = messages[-1]["content"]
        if "JSON object" in last:
            state["prompts"].append(last)
            step = steps[min(state["n"], len(steps) - 1)]
            state["n"] += 1
            return {"text": json.dumps(step), "model": model, "provider": "fake", "usage": {"prompt_tokens": 3, "completion_tokens": 2}, "ms": 1}
        return {"text": "Finite sets only: the premise fails for infinite ones.", "model": model, "provider": "fake",
                "usage": {"prompt_tokens": 3, "completion_tokens": 4}, "ms": 1}
    return chat, state


@pytest.mark.asyncio
async def test_independent_sitting_sees_own_work_acts_on_it_with_cited_evidence_and_does_not_consolidate_it():
    from src.services import exploration
    from src.services.exploration import SoloBudget, run_independent_sitting
    async with async_session_maker() as db:
        r = await work.run_tool(db, ("wsx", "ux", "sophie"), surface="foreground", tool="work_write", conversation_id="chat-A",
                                args={"op": "create", "title": "Is his ladder argument sound?", "text": "Doesn't convince me; check infinite case."})
        iid = r["item_id"][:8]
    chat, state = _scripted([
        {"thought": "I wrote that earlier; let me test it.", "action": {"type": "ask_model", "question": "Does the ladder argument survive infinite sets?"}},
        {"thought": "Revising.", "action": {"type": "work_write", "op": "revise", "id": iid, "text": "Sound only for finite sets.", "cites": ["a1", "zz9"], "note": "evidence"}},
        {"thought": "Done.", "action": {"type": "done", "reason": "enough"}}])
    exploration.set_chat_fn(chat)
    try:
        async with async_session_maker() as db:
            out = await run_independent_sitting(db, workspace_id="wsx", owner="ux", sitting_id="solo-t1",
                                                budget=SoloBudget(max_iterations=5, max_tool_calls=5, max_model_calls=8))
    finally:
        exploration.set_chat_fn(None)
    assert "Is his ladder argument sound?" in state["prompts"][0] and "never obligations" in state["prompts"][0]
    assert out["work_writes"] == 1
    async with async_session_maker() as db:
        got = await work.get_with_events(db, ("wsx", "ux", "sophie"), iid)
    rev = got["events"][-1]
    assert rev.action == "revise" and rev.surface == "independent" and rev.sitting_id == "solo-t1"
    ev = json.loads(rev.evidence_json)
    assert ev[0]["ref"] == "a1" and "Finite sets only" in ev[0]["captured"]      # captured verbatim from the actual model reply
    assert ev[1] == {"ref": "zz9", "unresolved": True}


@pytest.mark.asyncio
async def test_work_only_sitting_is_not_consolidated_and_second_companion_uses_same_code(monkeypatch):
    from src.services import exploration
    from src.services.exploration import SoloBudget, run_independent_sitting
    # bloom's independent surface is off in this policy: the capability is suppressed, nothing shown or written
    chat, state = _scripted([{"thought": "x", "action": {"type": "work_write", "op": "create", "title": "t", "text": "b"}},
                             {"thought": "y", "action": {"type": "done", "reason": "r"}}])
    exploration.set_chat_fn(chat)
    try:
        async with async_session_maker() as db:
            out = await run_independent_sitting(db, workspace_id="wsy", owner="uy", sitting_id="b1", companion_id="bloom",
                                                constitution="You are Bluum. Warm, grounded.",
                                                budget=SoloBudget(max_iterations=3, max_tool_calls=3, max_model_calls=5))
        assert out["work_writes"] == 0 and out["status"] == "declined"
    finally:
        exploration.set_chat_fn(None)
    monkeypatch.setenv("COMPANION_WORK_POLICY", json.dumps({"bloom": {"foreground": "write", "independent": "write"}}))
    chat, state = _scripted([{"thought": "x", "action": {"type": "work_write", "op": "create", "title": "A gratitude pattern", "text": "People who make him laugh."}},
                             {"thought": "y", "action": {"type": "done", "reason": "r"}}])
    exploration.set_chat_fn(chat)
    try:
        async with async_session_maker() as db:
            out = await run_independent_sitting(db, workspace_id="wsy", owner="uy", sitting_id="b2", companion_id="bloom",
                                                constitution="You are Bluum. Warm, grounded.",
                                                budget=SoloBudget(max_iterations=3, max_tool_calls=3, max_model_calls=5))
        assert out["status"] == "worked" and out["work_writes"] == 1      # no consolidation (memory_pipeline model_fn would have raised)
        async with async_session_maker() as db:
            assert [i.title for i in await work.list_items(db, ("wsy", "uy", "bloom"))] == ["A gratitude pattern"]
            assert await work.list_items(db, ("wsy", "uy", "sophie")) == []
    finally:
        exploration.set_chat_fn(None)


@pytest.mark.asyncio
async def test_an_action_without_a_type_is_told_to_her_not_treated_as_stopping():
    from src.services import exploration
    from src.services.exploration import SoloBudget, run_independent_sitting
    chat, state = _scripted([{"thought": "revise", "action": {"op": "revise", "id": "zzzz", "text": "x"}},
                             {"thought": "ok", "action": {"type": "work_write", "op": "create", "title": "second try", "text": "kept"}},
                             {"thought": "done", "action": {"type": "done", "reason": "r"}}])
    exploration.set_chat_fn(chat)
    try:
        async with async_session_maker() as db:
            out = await run_independent_sitting(db, workspace_id="wsm", owner="um", sitting_id="m1",
                                                budget=SoloBudget(max_iterations=5, max_tool_calls=3, max_model_calls=8))
    finally:
        exploration.set_chat_fn(None)
    assert out["work_writes"] == 1 and out["status"] == "worked"
    assert "had no \"type\"" in state["prompts"][1]


@pytest.mark.asyncio
async def test_what_she_just_wrote_is_in_front_of_her_on_the_next_iteration():
    from src.services import exploration
    from src.services.exploration import SoloBudget, run_independent_sitting
    async with async_session_maker() as db:
        r = await work.run_tool(db, ("wsr", "ur", "sophie"), surface="foreground", tool="work_write", args={"op": "create", "title": "Seed", "text": "first line"})
    iid = r["item_id"][:8]
    chat, state = _scripted([{"thought": "add", "action": {"type": "work_write", "op": "continue", "id": iid, "text": "SECOND-LINE-MARKER"}},
                             {"thought": "close", "action": {"type": "work_write", "op": "complete", "id": iid, "text": "closing words"}},
                             {"thought": "done", "action": {"type": "done", "reason": "r"}}])
    exploration.set_chat_fn(chat)
    try:
        async with async_session_maker() as db:
            await run_independent_sitting(db, workspace_id="wsr", owner="ur", sitting_id="r1", budget=SoloBudget(max_iterations=5, max_tool_calls=3, max_model_calls=8))
    finally:
        exploration.set_chat_fn(None)
    assert "SECOND-LINE-MARKER" not in state["prompts"][0] and "SECOND-LINE-MARKER" in state["prompts"][1]
    async with async_session_maker() as db:
        got = await work.get_with_events(db, ("wsr", "ur", "sophie"), iid)
    assert got["item"].status == "completed" and got["item"].text.endswith("closing words") and got["events"][-1].text == "closing words"
