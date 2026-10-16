"""Memory pipeline: Cortex-owned consolidation, preparation, replay-safety, and the
legacy-interpret retirement gate. No network: the model is an injected fake."""
import asyncio
import json

import pytest

from src.services import memory_pipeline
from src.services.memory_pipeline import LISTENING_PROMPT, HANDOFF_PROMPT


def _fake_model(kind, prompt, max_tokens, models):
    if kind == "discovery":
        return {"text": "He walks about five miles most evenings. A morning walk is an aspiration, not a routine.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "handoff":
        return {"text": "They talked walking. The morning walk stays an open idea.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind.startswith("edit:"):
        page = kind.split(":", 1)[1]
        return {"text": f"# {page}\n\nEvening walk ~5 miles established. Morning walk is an aspiration, not a routine.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "ledger":
        return {"text": '[{"title": "Deliver the render by Thursday", "kind": "commitment", "date": "unknown", "status": "open"}]',
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "arc":
        return {"text": "They talked walking; the morning walk remains an open idea.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "preparation":
        return {"text": "I wonder if he got his evening walk in. The morning walk is still just an idea.",
                "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    raise AssertionError(kind)


@pytest.fixture(autouse=True)
def fake_models():
    memory_pipeline.set_model_fn(_fake_model)
    yield
    memory_pipeline.set_model_fn(None)


def _msgs(n, prefix="m"):
    return [{"id": f"{prefix}{i}", "speaker": "user" if i % 2 == 0 else "assistant",
             "text": f"message {i}"} for i in range(n)]


BASE = {"workspace_id": "ws1", "owner": "user_1", "conversation_id": "c1"}


async def _wait_run(client, run_id, tries=50):
    for _ in range(tries):
        r = await client.get(f"/v1/memory/run/{run_id}")
        assert r.status_code == 200, r.text
        if r.json()["status"] in ("consolidated", "replay_noop", "empty", "failed"):
            return r.json()
        await asyncio.sleep(0.1)
    raise AssertionError("run never finished")


@pytest.mark.asyncio
async def test_baseline_prompts_verbatim():
    assert "Only keep what genuinely matters. Write it as short, plain, standalone sentences." in LISTENING_PROMPT
    assert "Deliver no more than 2-3 sentences at most." in HANDOFF_PROMPT
    assert "Structure" not in LISTENING_PROMPT
    blob = (memory_pipeline.NOTEBOOK_EDITOR_PROMPT + memory_pipeline.ARC_UPDATE_PROMPT
            + memory_pipeline.LEDGER_EXTRACT_PROMPT + memory_pipeline.PREPARATION_PROMPT)
    for guard in ("Do not carry the mood", "never turn one difficult exchange into a lasting verdict",
                  "an aspiration is not a task", "honest about what you don't know"):
        assert guard in blob


@pytest.mark.asyncio
async def test_consolidate_preparation_state_roundtrip(async_client):
    r = await async_client.post("/v1/memory/consolidate",
                                json={**BASE, "session_id": "s1", "messages": _msgs(10)})
    assert r.status_code == 202, r.text
    run = await _wait_run(async_client, r.json()["run_id"])
    assert run["status"] == "consolidated"
    assert run["summary"]["new_message_count"] if "new_message_count" in run["summary"] else True

    prep = (await async_client.get("/v1/memory/preparation", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    assert prep["found"] and "evening walk" in prep["text"]

    state = (await async_client.get("/v1/memory/state", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    assert "aspiration, not a routine" in state["notebook"]["routines"]["text"]
    assert state["notebook"]["routines"]["version"] == 2
    assert any(i["title"] == "Deliver the render by Thursday" for i in state["ledger"])
    assert "open idea" in state["arc"]["text"]
    # page scopes hold: routines page carries no infrastructure material
    assert "database" not in state["notebook"]["routines"]["text"].lower()


@pytest.mark.asyncio
async def test_replay_is_noop_without_duplicates(async_client):
    r1 = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "s1", "messages": _msgs(6)})
    assert (await _wait_run(async_client, r1.json()["run_id"]))["status"] == "consolidated"
    before = (await async_client.get("/v1/memory/state", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    r2 = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "s1b", "messages": _msgs(6)})
    run2 = await _wait_run(async_client, r2.json()["run_id"])
    assert run2["status"] == "replay_noop"
    after = (await async_client.get("/v1/memory/state", params={"workspace_id": "ws1", "owner": "user_1"})).json()
    assert after["notebook"] == before["notebook"] and after["arc"] == before["arc"]
    titles = [i["title"] for i in after["ledger"]]
    assert len(titles) == len(set(titles))


@pytest.mark.asyncio
async def test_full_fifty_message_coverage(async_client):
    r = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "long", "messages": _msgs(50)})
    run = await _wait_run(async_client, r.json()["run_id"])
    assert run["status"] == "consolidated" and len(run["covered_ids"]) == 50


@pytest.mark.asyncio
async def test_legacy_interpret_retired_for_sophie(async_client):
    r = await async_client.post("/v1/world/interpret", json={
        "workspace_id": "ws1", "owner": "user_1", "session_id": "c1",
        "messages": [{"id": "a", "speaker": "user", "text": "hi"}, {"id": "b", "speaker": "assistant", "text": "hey"}],
        "policy": "grounded", "companion_id": "sophie", "agency": True})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "superseded_by_memory_pipeline"


@pytest.mark.asyncio
async def test_empty_transcript_rejected(async_client):
    r = await async_client.post("/v1/memory/consolidate", json={**BASE, "session_id": "s0", "messages": []})
    assert r.status_code == 422
