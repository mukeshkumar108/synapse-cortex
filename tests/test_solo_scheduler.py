"""Scheduler eligibility, declined opportunities, operator tick. No network."""
from datetime import datetime, timedelta, timezone

import pytest

from src.db import async_session_maker
from src.services import exploration, memory_pipeline, solo_scheduler
from src.services.exploration import SoloBudget, run_independent_sitting


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("SOPHIE_SOLO_SCHEDULER", "true")
    monkeypatch.setenv("SOPHIE_SOLO_WORKSPACE", "ws1")
    monkeypatch.setenv("SOPHIE_SOLO_OWNERS", "u1")
    monkeypatch.setenv("SOPHIE_SOLO_MAX_PER_DAY", "2")
    monkeypatch.setenv("SOPHIE_SOLO_QUIET_START_H", "23")
    monkeypatch.setenv("SOPHIE_SOLO_QUIET_END_H", "7")
    monkeypatch.setenv("SOPHIE_SOLO_USER_ACTIVE_MIN", "30")


def _midday():
    from datetime import datetime as _d
    return _d.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)


@pytest.mark.asyncio
async def test_eligible_when_idle():
    async with async_session_maker() as db:
        ok, reason, facts = await solo_scheduler.eligibility(db, workspace_id="ws1", owner="u1", now=_midday())
    assert ok and reason == "eligible", facts


@pytest.mark.asyncio
async def test_quiet_hours_and_cap_and_overlap():
    async with async_session_maker() as db:
        ok, reason, _ = await solo_scheduler.eligibility(
            db, workspace_id="ws1", owner="u1",
            now=datetime.now(timezone.utc).replace(hour=2, minute=0, second=0, microsecond=0))
        assert not ok and reason.startswith("quiet_hours")
        ok, reason, _ = await solo_scheduler.eligibility(db, workspace_id="ws1", owner="stranger", now=_midday())
        assert not ok and reason == "owner_not_allowlisted"
        # running overlap
        from src.models.world import MemoryRun
        db.add(MemoryRun(honcho_workspace_id="ws1", owner_peer_id="u1", conversation_id="solo-x",
                         session_id="solo:x", status="running"))
        await db.commit()
        ok, reason, _ = await solo_scheduler.eligibility(db, workspace_id="ws1", owner="u1", now=_midday())
        assert not ok and reason.startswith("already_running")


@pytest.mark.asyncio
async def test_daily_cap_counts_solo_runs():
    from src.models.world import MemoryRun
    async with async_session_maker() as db:
        for i in range(2):
            db.add(MemoryRun(honcho_workspace_id="ws1", owner_peer_id="u1", conversation_id=f"solo-{i}",
                             session_id=f"solo:{i}", status="consolidated"))
        await db.commit()
        ok, reason, facts = await solo_scheduler.eligibility(db, workspace_id="ws1", owner="u1", now=_midday())
    assert not ok and reason.startswith("daily_cap") and facts["sittings_today"] == 2


@pytest.mark.asyncio
async def test_recent_user_turn_defers(monkeypatch):
    from datetime import datetime as _d
    from src.models.operational_state import TurnStamp
    now = _d.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
    async with async_session_maker() as db:
        db.add(TurnStamp(honcho_workspace_id="ws1", owner_peer_id="u1", honcho_message_id="m1",
                         turn_at=now.replace(tzinfo=None)))
        await db.commit()
        ok, reason, _ = await solo_scheduler.eligibility(db, workspace_id="ws1", owner="u1", now=now)
    assert not ok and reason.startswith("user_active")


@pytest.mark.asyncio
async def test_immediate_stop_is_declined_not_consolidated():
    async def chat(model, messages, max_tokens=800, title="solo"):
        return {"text": '{"thought": "Nothing pulls me right now.", "action": {"type": "done", "reason": "not curious"}}',
                "model": model, "provider": "fake", "usage": {"prompt_tokens": 5, "completion_tokens": 5}, "ms": 1}

    async def memfn(kind, prompt, max_tokens, models):
        raise AssertionError("consolidation must not run for a declined sitting")

    exploration.set_chat_fn(chat)
    memory_pipeline.set_model_fn(memfn)
    try:
        async with async_session_maker() as db:
            out = await run_independent_sitting(db, workspace_id="ws1", owner="u1", sitting_id="dec1",
                                                budget=SoloBudget(max_iterations=3, max_tool_calls=3, max_model_calls=3))
        assert out["status"] == "declined"
        async with async_session_maker() as db:
            state = await memory_pipeline.read_state(db, workspace_id="ws1", owner="u1")
        assert state["notebook"]["exploring"]["version"] == 1  # no state change
        assert state["arc"]["version"] == 1
    finally:
        exploration.set_chat_fn(None)
        memory_pipeline.set_model_fn(None)


@pytest.mark.asyncio
async def test_solo_tick_dry_run(async_client, monkeypatch):
    monkeypatch.setenv("SOPHIE_SOLO_QUIET_START_H", "0")  # never quiet regardless of wall clock
    monkeypatch.setenv("SOPHIE_SOLO_QUIET_END_H", "0")
    r = await async_client.post("/v1/memory/solo-tick",
                                json={"workspace_id": "ws1", "owner": "u1", "dry_run": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["eligible"] is True and body["reason"] == "eligible"
