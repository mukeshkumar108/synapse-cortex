"""Replay a real RPD2 transcript (a text dump of '#n [role] time' blocks) through the rpd2 notes writer with a live model, then ask what the character would be told.

  NANO_API_KEY=... python -m pytest evals/replay_rpd2_isa.py -s --transcript <file> --upto 107
Not collected by the normal suite (no test_ prefix); it spends real model calls."""
import os
import re
import uuid
from datetime import datetime

import pytest

from src.db import async_session_maker
from src.services import memory_pipeline, notes, rpd2_memory

pytestmark = pytest.mark.skipif(not os.getenv("REPLAY_TRANSCRIPT"), reason="set REPLAY_TRANSCRIPT")

DIRECTIVE = re.compile(r"^You are continuing the roleplay", re.I)


def load(path, upto):
    blocks = re.split(r"\n(?=#\d+ \[(?:user|assistant)\])", open(path).read().strip())
    msgs = []
    for b in blocks:
        head, _, body = b.partition("\n")
        m = re.match(r"#(\d+) \[(user|assistant)\] (\S+)", head)
        if not m or int(m.group(1)) > upto:
            continue
        body = body.strip()
        if m.group(2) == "user" and DIRECTIVE.match(body):
            continue
        if len(set(body)) < 6 and len(body) > 200:      # degenerate output
            continue
        msgs.append(("Player" if m.group(2) == "user" else "Character", body))
    return msgs


@pytest.mark.asyncio
async def test_replay():
    msgs = load(os.environ["REPLAY_TRANSCRIPT"], int(os.getenv("REPLAY_UPTO", "107")))
    transcript = "\n".join(f"{who}: {text}" for who, text in msgs)
    o = f"world:rpd2:replay:{uuid.uuid4().hex[:6]}"
    async with async_session_maker() as db:
        out = await notes.write(db, workspace_id="rpd2::replay", owner=o, product="rpd2", session_id="replay", run_id=None, transcript=transcript, person_label="Player",
                                companion_name="Character", session_day=datetime(2026, 11, 2), weekday="Monday", profile=rpd2_memory.PROFILE)
    print("\nWRITE:", {k: v for k, v in out.items() if k != "usage"})
    async with async_session_maker() as db:
        rows = await notes._current(db, "rpd2::replay", o)
        print(f"\n{len(rows)} NOTES")
        for r in rows:
            print(f" [{r.area}/{r.certainty}] {r.subject}: {r.text}")
        for q in ("what did you do with marcus? how does he know where you live?", "where did you meet him", "why did you take the ring off"):
            text, named = await notes.mentions_text(db, "rpd2::replay", o, q)
            print(f"\nQ: {q}\nNAMED: {named}\n{text}")



@pytest.mark.asyncio
async def test_replay_through_the_real_consolidation_route(async_client):
    """Two sittings through POST /v1/memory/consolidate as the Runtime sends them, then what the Runtime would read back."""
    import asyncio
    path = os.environ["REPLAY_TRANSCRIPT"]
    night_len = len(load(path, 107))
    every = load(path, int(os.getenv("REPLAY_UPTO", "115")))      # only what had happened by then: later replies are the failure under study, not input
    owner_id = f"world:rpd2:replay:{uuid.uuid4().hex[:6]}"
    base = {"workspace_id": "llm-test-agent", "owner": owner_id, "conversation_id": "chat-1", "companion_id": "rpd2", "time_zone": "Europe/London"}

    async def run(msgs, session_id, when):
        payload = [{"id": f"{session_id}-{i}", "speaker": "user" if who == "Player" else "assistant", "text": t} for i, (who, t) in enumerate(msgs)]
        r = await async_client.post("/v1/memory/consolidate", json={**base, "session_id": session_id, "session_time": when, "messages": payload})
        assert r.status_code == 202, r.text
        for _ in range(900):
            st = (await async_client.get(f"/v1/memory/run/{r.json()['run_id']}", params={"companion_id": "rpd2"})).json()
            if st["status"] in ("consolidated", "replay_noop", "empty", "failed"):
                return st
            await asyncio.sleep(0.5)
        raise AssertionError("did not finish")

    print("\nRUN 1:", (await run(every[:night_len], "night", "2026-11-02T02:10:00+00:00"))["status"])
    print("RUN 2:", (await run(every[night_len:], "midday", "2026-11-02T12:55:00+00:00"))["status"])
    st = (await async_client.get("/v1/memory/state", params={"workspace_id": "llm-test-agent", "owner": owner_id, "companion_id": "rpd2"})).json()
    print("\nARC:\n", (st.get("arc") or {}).get("text"))
    for q in ("what did you do with marcus? how does he know where you live?", "where did you meet him, marcus"):
        w = (await async_client.get("/v1/memory/world", params={"workspace_id": "llm-test-agent", "owner": owner_id, "companion_id": "rpd2", "view": "packet", "q": q})).json()
        print(f"\nQ: {q}\nNAMED: {w.get('named_now')}\n{w.get('mentions')}")
