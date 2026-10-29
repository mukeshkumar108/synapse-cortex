"""One running account per chat, kept by the existing handoff call (no extra pass), served when the chat is reopened.

A thread is not a subject: a chat can hold several, and a subject can span chats. The account is a view of the chat (dated, who said what); notes, ledger and arc stay the truth."""
import asyncio
import json

import pytest

from src.services import memory_pipeline as mp

SEEN = []


def model(kind, prompt, max_tokens, models):
    if kind == "handoff":
        SEEN.append((prompt, max_tokens))
        day = "29 Oct" if "Thu 29 Oct" in prompt else "later"
        prior = prompt.split("--- this chat so far ---", 1)[1].split("--- transcript ---", 1)[0].strip() if "--- this chat so far ---" in prompt else ""
        account = (prior + "\n\n" if prior and not prior.startswith("(nothing yet") else "") + f"Pricing: discussed on {day}; Mukesh decided to test two price points; open: which market first."
        return {"text": f"They worked on pricing.\n===THREAD===\n{account}", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "discovery":
        return {"text": "He is working out pricing.", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind.startswith("edit:"):
        return {"text": f"# {kind.split(':', 1)[1]}\n\nx", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    if kind == "ledger":
        return {"text": '{"new": [], "update": [], "close": []}', "model": "fake", "provider": "fake", "usage": {}, "ms": 1}
    return {"text": "ok", "model": "fake", "provider": "fake", "usage": {}, "ms": 1}


@pytest.fixture(autouse=True)
def fake_model():
    SEEN.clear()
    mp.set_model_fn(model)
    yield
    mp.set_model_fn(None)


def msgs(prefix, n=8):
    return [{"id": f"{prefix}{i}", "speaker": "user" if i % 2 == 0 else "assistant", "text": f"{prefix} line {i} about pricing and the first market"} for i in range(n)]


async def wait(client, rid):
    for _ in range(80):
        r = (await client.get(f"/v1/memory/run/{rid}")).json()
        if r["status"] in ("consolidated", "replay_noop", "empty", "failed"):
            return r
        await asyncio.sleep(0.1)
    raise AssertionError("never finished")


async def sitting(client, chat, session, prefix, when="2026-10-29T09:00:00+00:00"):
    r = await client.post("/v1/memory/consolidate", json={"workspace_id": "ws1", "owner": "user_t", "conversation_id": chat, "session_id": session, "messages": msgs(prefix), "session_time": when, "time_zone": "Europe/London"})
    assert r.status_code == 202, r.text
    return await wait(client, r.json()["run_id"])


async def thread(client, chat):
    return (await client.get("/v1/memory/thread", params={"workspace_id": "ws1", "owner": "user_t", "conversation_id": chat})).json()


def test_the_calls_answer_is_split_into_the_sitting_summary_and_the_chats_account():
    assert mp.split_thread("Two sentences.\n===THREAD===\nPricing: decided X.") == ("Two sentences.", "Pricing: decided X.")
    assert mp.split_thread("Only a summary.") == ("Only a summary.", "")


def test_without_a_usable_account_the_sitting_is_folded_in_dated_and_the_oldest_paragraph_goes_first():
    one = mp.fold_into_thread("", "They talked pricing.", "Thu 29 Oct 2026")
    assert one == "Thu 29 Oct 2026: They talked pricing."
    long = "\n\n".join(f"Day {i}: " + "x" * 400 for i in range(12))
    out = mp.fold_into_thread(long, "Latest.", "Fri 30 Oct 2026")
    assert out.endswith("Fri 30 Oct 2026: Latest.") and len(out) <= mp.THREAD_FALLBACK_CHARS and "Day 0:" not in out


@pytest.mark.asyncio
async def test_a_chat_keeps_one_account_across_sittings_and_other_chats_do_not_touch_it(async_client):
    run = await sitting(async_client, "chat-product", "s1", "a")
    assert run["status"] == "consolidated"
    first = await thread(async_client, "chat-product")
    assert first["found"] and first["sittings"] == 1 and "test two price points" in first["text"]
    assert "--- this chat so far ---\n(nothing yet" in SEEN[0][0] and SEEN[0][1] >= 1000, "the same handoff call, handed the account so far (none yet), with room to answer"

    await sitting(async_client, "chat-fitness", "s2", "b")                                   # an unrelated chat in between
    await sitting(async_client, "chat-product", "s3", "c", when="2026-11-05T09:00:00+00:00")
    again = await thread(async_client, "chat-product")
    assert again["sittings"] == 2 and again["version"] == 2
    assert again["text"].count("Pricing:") == 2, "the first sitting's account is kept and the second added"
    assert "Pricing: discussed on 29 Oct" in SEEN[2][0] or "Pricing:" in SEEN[2][0], "the third call was handed this chat's account, not the fitness chat's"
    other = await thread(async_client, "chat-fitness")
    assert other["sittings"] == 1 and other["text"].count("Pricing:") == 1
    assert not (await thread(async_client, "chat-never-used"))["found"]


@pytest.mark.asyncio
async def test_a_replayed_sitting_is_not_merged_twice(async_client):
    await sitting(async_client, "chat-replay", "s-same", "a")
    await sitting(async_client, "chat-replay", "s-same", "z")           # same session id offered again with other messages (a failed run being replayed)
    assert (await thread(async_client, "chat-replay"))["sittings"] == 1


@pytest.mark.asyncio
async def test_a_call_that_forgets_the_account_still_leaves_the_chat_a_dated_one(async_client):
    mp.set_model_fn(lambda kind, p, mt, m: ({"text": "They talked pricing.", "model": "f", "provider": "f", "usage": {}, "ms": 1} if kind == "handoff" else model(kind, p, mt, m)))
    run = await sitting(async_client, "chat-fallback", "s9", "f")
    assert run["status"] == "consolidated"
    t = await thread(async_client, "chat-fallback")
    assert t["found"] and t["text"].endswith("They talked pricing.") and "Thu" in t["text"]


@pytest.mark.asyncio
async def test_it_can_be_switched_off(async_client, monkeypatch):
    monkeypatch.setenv("MEMORY_THREAD_CHECKPOINT", "0")
    await sitting(async_client, "chat-off", "s5", "o")
    assert not (await thread(async_client, "chat-off"))["found"]
    assert "===THREAD===" not in SEEN[-1][0]
