"""Independent sittings: bounded runner, tools, consolidation into exploring."""
import json

import pytest

from src.services import exploration, memory_pipeline
from src.services.exploration import SoloBudget, _safe_url, run_independent_sitting


@pytest.fixture(autouse=True)
def fakes(monkeypatch):
    async def chat(model, messages, max_tokens=800, title="solo"):
        last = messages[-1]["content"]
        if "DECIDING" in last or "deciding what to do" in last.lower() or "JSON object" in last:
            step = getattr(chat, "n", 0)
            chat.n = step + 1
            if step == 0:
                return {"text": '{"thought": "I keep wondering about octopus intelligence.", "action": {"type": "ask_model", "question": "What is remarkable about octopus cognition?"}}',
                        "model": model, "provider": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "ms": 1}
            if step == 1:
                return {"text": '{"thought": "That reply mentioned distributed nervous systems; let me look for more.", "action": {"type": "web_search", "query": "octopus distributed nervous system"}}',
                        "model": model, "provider": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "ms": 1}
            return {"text": '{"thought": "Enough for now; I have something to chew on.", "action": {"type": "done", "reason": "satisfied"}}',
                    "model": model, "provider": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 5}, "ms": 1}
        return {"text": "Octopuses have about 500 million neurons, two-thirds in their arms.",
                "model": model, "provider": "fake", "usage": {"prompt_tokens": 5, "completion_tokens": 8}, "ms": 1}

    async def search(query, count=5):
        return {"engine": "wikipedia", "query": query,
                "hits": [{"title": "Octopus", "snippet": "nervous system distributed", "url": "https://en.wikipedia.org/wiki/Octopus"}]}

    async def memfn(kind, prompt, max_tokens, models):
        if kind == "discovery":
            return {"text": "Sophie explored octopus cognition: asked a model, searched background material.", "model": "f", "provider": "f", "usage": {}, "ms": 1}
        if kind == "handoff":
            return {"text": "Solo sitting on octopus minds; still curious about arm autonomy.", "model": "f", "provider": "f", "usage": {}, "ms": 1}
        if kind.startswith("edit:"):
            page = kind.split(":", 1)[1]
            if page == "exploring":
                return {"text": "# Things I'm Exploring\n\n- Octopus cognition: 500M neurons, mostly in arms. Still open: how autonomous is each arm?", "model": "f", "provider": "f", "usage": {}, "ms": 1}
            return {"text": "# other\n\nUnchanged.\n", "model": "f", "provider": "f", "usage": {}, "ms": 1}
        if kind == "ledger":
            return {"text": "[]", "model": "f", "provider": "f", "usage": {}, "ms": 1}
        if kind == "preparation":
            return {"text": "", "model": "f", "provider": "f", "usage": {}, "ms": 1}
        raise AssertionError(kind)

    chat.n = 0
    exploration.set_chat_fn(chat)
    monkeypatch.setattr(exploration, "web_search", search)
    memory_pipeline.set_model_fn(memfn)
    yield
    exploration.set_chat_fn(None)
    memory_pipeline.set_model_fn(None)


def test_safe_url_blocks_private():
    assert _safe_url("https://en.wikipedia.org/wiki/Octopus")
    assert not _safe_url("http://localhost:8010/x")
    assert not _safe_url("http://127.0.0.1/y")
    assert not _safe_url("http://169.254.169.254/latest")
    assert not _safe_url("ftp://x/y")


@pytest.mark.asyncio
async def test_solo_sitting_explores_and_consolidates(async_client):
    from src.db import async_session_maker
    async with async_session_maker() as db:
        out = await run_independent_sitting(db, workspace_id="ws1", owner="u1", sitting_id="s1",
                                            budget=SoloBudget(max_iterations=5, max_tool_calls=5, max_model_calls=8))
    assert out["status"] == "consolidated"
    assert out["model_calls"] >= 3 and out["tool_calls"] >= 1

    async with async_session_maker() as db:
        state = await memory_pipeline.read_state(db, workspace_id="ws1", owner="u1")
    assert "Octopus" in state["notebook"]["exploring"]["text"]
    assert state["arc"]["version"] == 1  # shared arc untouched by solo sittings
    assert state["arc"]["text"].startswith("No conversations")
    # sitting log attached to the run bundle
    from sqlmodel import select
    async with async_session_maker() as db:
        rows = (await db.execute(select(memory_pipeline.MemoryRun))).scalars().all()
        bundles = [json.loads(r.bundle_json) for r in rows if r.bundle_json and "sitting_log" in r.bundle_json]
    assert bundles and any(e["kind"] == "ask_model" for e in bundles[0]["sitting_log"])
    assert any(e["kind"] == "web_search" for e in bundles[0]["sitting_log"])
    models = {e.get("model") for e in bundles[0]["sitting_log"] if e.get("model")}
    assert models  # model identity preserved


@pytest.mark.asyncio
async def test_budget_stops_the_sitting():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        out = await run_independent_sitting(db, workspace_id="ws1", owner="u2", sitting_id="s2",
                                            budget=SoloBudget(max_iterations=1, max_tool_calls=5, max_model_calls=5))
    assert out["model_calls"] <= 5


@pytest.mark.asyncio
async def test_independent_endpoint_accepts(async_client):
    r = await async_client.post("/v1/memory/independent-sitting",
                                json={"workspace_id": "ws1", "owner": "u9", "max_iterations": 1,
                                      "max_tool_calls": 0, "max_model_calls": 1})
    assert r.status_code == 202, r.text
    assert r.json()["sitting_id"]


@pytest.mark.asyncio
async def test_failed_ask_is_visible_to_sophie():
    """A failed model call must appear in her transcript, not vanish."""
    calls = {"n": 0}

    async def chat(model, messages, max_tokens=800, title="solo"):
        if "JSON object" in messages[-1]["content"]:
            calls["n"] += 1
            if calls["n"] == 1:
                return {"text": '{"thought": "Let me ask.", "action": {"type": "ask_model", "question": "Q?"}}',
                        "model": model, "provider": "fake", "usage": {}, "ms": 1}
            return {"text": '{"thought": "Nothing worked; stopping.", "action": {"type": "done", "reason": "blocked"}}',
                    "model": model, "provider": "fake", "usage": {}, "ms": 1}
        return {"error": "ConnectError: nano unreachable"}

    exploration.set_chat_fn(chat)
    try:
        from src.db import async_session_maker
        async with async_session_maker() as db:
            out = await run_independent_sitting(db, workspace_id="ws1", owner="u777", sitting_id="err1",
                                                budget=SoloBudget(max_iterations=3, max_tool_calls=3, max_model_calls=5))
        assert out["status"] == "declined"  # attempts failed: nothing substantive to consolidate
        async with async_session_maker() as db:
            state = await memory_pipeline.read_state(db, workspace_id="ws1", owner="u777")
        # the error must be recorded where she can see it (transcript label), not dropped
        from sqlmodel import select
        async with async_session_maker() as db:
            rows = (await db.execute(select(memory_pipeline.MemoryRun))).scalars().all()
            logs = [json.loads(r.bundle_json)["sitting_log"] for r in rows
                    if r.bundle_json and "sitting_log" in r.bundle_json and r.session_id == "solo:err1"]
        assert logs and any(e["kind"] == "ask_model_error" for e in logs[0])
    finally:
        exploration.set_chat_fn(None)


@pytest.mark.asyncio
async def test_truncated_reply_is_marked():
    seen = {}

    async def chat(model, messages, max_tokens=800, title="solo"):
        if "JSON object" in messages[-1]["content"]:
            return {"text": '{"thought": "Ask once.", "action": {"type": "ask_model", "question": "Q?"}}',
                    "model": model, "provider": "fake", "usage": {}, "ms": 1}
        seen["truncated"] = True
        return {"text": "Partial argument...", "model": model, "provider": "fake",
                "usage": {}, "ms": 1, "truncated": True}

    exploration.set_chat_fn(chat)
    try:
        from src.db import async_session_maker
        async with async_session_maker() as db:
            await run_independent_sitting(db, workspace_id="ws1", owner="u778", sitting_id="tr1",
                                          budget=SoloBudget(max_iterations=2, max_tool_calls=2, max_model_calls=4))
        from sqlmodel import select
        async with async_session_maker() as db:
            rows = (await db.execute(select(memory_pipeline.MemoryRun))).scalars().all()
            logs = [json.loads(r.bundle_json)["sitting_log"] for r in rows
                    if r.bundle_json and "sitting_log" in r.bundle_json and r.session_id == "solo:tr1"]
        asks = [e for e in logs[0] if e["kind"] == "ask_model"]
        assert seen.get("truncated") and asks and asks[0]["truncated"] is True
    finally:
        exploration.set_chat_fn(None)
