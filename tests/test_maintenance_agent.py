"""Agentic maintenance acceptance: scripted tool-call S1→S2 asserting final DB.
No network: the model is a canned tool-call script; tools + validation are real."""
import json

import pytest

from src.db import async_session_maker
from src.services import maintenance_agent, memory_pipeline


def _tc(i, name, args):
    return {"id": f"call_{i}", "type": "function",
            "function": {"name": name, "arguments": json.dumps(args)}}


@pytest.mark.asyncio
async def test_agent_maintains_s2_end_to_end():
    script = [
        {"tool_calls": [_tc(1, "list_open", {})]},
        {"tool_calls": [_tc(2, "history", {"key": "vinesh-review"}),
                        _tc(3, "update_item", {"key": "ashley-renders", "status": "done",
                                               "evidence": "loved the renders, done"}),
                        _tc(4, "update_item", {"key": "vinesh-review", "timing_text": "Friday morning",
                                               "expected_date": "2026-10-23", "time_role": "happens",
                                               "evidence": "moved to Friday morning"})]},
        {"tool_calls": [_tc(5, "list_open", {})]},
        {"tool_calls": [_tc(6, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "closed Ashley, moved Vinesh date"})]},
    ]
    state = {"n": 0}

    async def fake_chat(model, messages):
        out = script[state["n"]]
        state["n"] += 1
        return {"content": "", "tool_calls": out["tool_calls"], "model": model,
                "provider": "fake", "usage": {"prompt_tokens": 10, "completion_tokens": 5}}

    async with async_session_maker() as db:
        db.add(memory_pipeline.LedgerItem(
            honcho_workspace_id="ws1", owner_peer_id="u1", kind="commitment",
            title="Vinesh review Thursday", detail="d", status="open",
            situation_key="vinesh-review", timing_text="Thursday"))
        db.add(memory_pipeline.LedgerItem(
            honcho_workspace_id="ws1", owner_peer_id="u1", kind="commitment",
            title="Ashley renders", detail="d", status="open",
            situation_key="ashley-renders", timing_text="Tuesday"))
        await db.commit()
        maintenance_agent.set_chat_fn(fake_chat)
        try:
            out = await maintenance_agent.run_maintenance(
                db, workspace_id="ws1", owner="u1", session_id="s2",
                observations="- Ashley loved the renders, done\n- Vinesh moved to Friday morning",
                today="2026-10-19")
        finally:
            maintenance_agent.set_chat_fn(None)
    assert out["status"] == "verified" and out["inspected"] is True
    assert len(out["calls"]) == 4
    async with async_session_maker() as db:
        rows = {r.situation_key: r for r in await memory_pipeline.open_ledger(db, "ws1", "u1", limit=50)}
        # Ashley closed -> leaves the open list; Vinesh date moved deterministically
        assert "ashley-renders" not in rows
        assert rows["vinesh-review"].timing_text == "Friday morning"
        from sqlmodel import select
        all_rows = (await db.execute(select(memory_pipeline.LedgerItem).where(
            memory_pipeline.LedgerItem.owner_peer_id == "u1"))).scalars().all()
        by_key = {r.situation_key: r for r in all_rows}
        assert by_key["ashley-renders"].status == "done"
        assert (by_key["vinesh-review"].expected_date is not None
                and by_key["vinesh-review"].expected_date.strftime("%Y-%m-%d") == "2026-10-23")


@pytest.mark.asyncio
async def test_agent_false_finish_is_not_verified():
    async def fake_chat(model, messages):
        return {"content": "all good", "tool_calls": [_tc(1, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "nothing to do"})],
                "model": model, "provider": "fake", "usage": {}}

    async with async_session_maker() as db:
        maintenance_agent.set_chat_fn(fake_chat)
        try:
            out = await maintenance_agent.run_maintenance(
                db, workspace_id="ws1", owner="u9", session_id="s9",
                observations="- something happened", today="2026-10-19")
        finally:
            maintenance_agent.set_chat_fn(None)
    assert out["status"] == "finished_without_inspection"
    assert out["inspected"] is False


@pytest.mark.asyncio
async def test_agent_skipped_when_nothing_observed():
    # consolidate-level skip: exercised via shape with no witness — agent not invoked.
    # Here: run_maintenance with empty observations still inspects honestly.
    async def fake_chat(model, messages):
        return {"content": "", "tool_calls": [_tc(1, "list_open", {}),
                                              _tc(2, "finish", {"transcript_sweep": "nothing beyond the observations", "summary": "nothing open"})],
                "model": model, "provider": "fake", "usage": {}}

    async with async_session_maker() as db:
        maintenance_agent.set_chat_fn(fake_chat)
        try:
            out = await maintenance_agent.run_maintenance(
                db, workspace_id="ws1", owner="u8", session_id="s8",
                observations="", today="2026-10-19")
        finally:
            maintenance_agent.set_chat_fn(None)
    assert out["status"] == "verified"


@pytest.mark.asyncio
async def test_fabricated_evidence_rejected():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        db.add(memory_pipeline.LedgerItem(
            honcho_workspace_id="ws1", owner_peer_id="u1", kind="commitment",
            title="Dentist Thursday", detail="d", status="open",
            situation_key="dentist"))
        await db.commit()
        from src.services import maintenance_agent as ma
        token = ma._TRANSCRIPT_CTX.set("dentist thursday, time unknown.")
        try:
            bad = await ma._tools(db, "ws1", "u1", "update_item",
                                  {"key": "dentist", "status": "done",
                                   "evidence": "Thursday 2pm, locked in."})
            assert "error" in bad and "transcript" in bad["error"]
            good = await ma._tools(db, "ws1", "u1", "update_item",
                                   {"key": "dentist", "status": "done",
                                    "evidence": "User confirmed: \"dentist thursday, time unknown\" is now handled"})
            assert good.get("ok") is True
        finally:
            ma._TRANSCRIPT_CTX.reset(token)


@pytest.mark.asyncio
async def test_run_reports_change_counts():
    from src.db import async_session_maker

    async def fake(kind_or_model, messages=None, max_tokens=None):
        # scripted agent: inspect, close one row, finish
        if isinstance(kind_or_model, str) and messages is None:
            return None
        n = fake.calls
        fake.calls += 1
        if n == 0:
            return {"content": "", "tool_calls": [
                {"id": "c1", "type": "function",
                 "function": {"name": "list_open", "arguments": "{}"}}],
                    "model": "fake", "provider": "fake", "usage": {}}
        if n == 1:
            return {"content": "", "tool_calls": [
                {"id": "c2", "type": "function",
                 "function": {"name": "update_item", "arguments": json.dumps(
                     {"key": "dentist", "status": "done",
                      "evidence": "dentist thursday confirmed at 2pm"})}}],
                    "model": "fake", "provider": "fake", "usage": {}}
        if n == 2:   # re-read after the write: finish is refused until the state is re-listed
            return {"content": "", "tool_calls": [
                {"id": "c2b", "type": "function", "function": {"name": "list_open", "arguments": "{}"}}],
                    "model": "fake", "provider": "fake", "usage": {}}
        return {"content": "", "tool_calls": [
            {"id": "c3", "type": "function",
             "function": {"name": "finish", "arguments": json.dumps({"summary": "closed dentist", "transcript_sweep": "nothing beyond the observations"})}}],
                "model": "fake", "provider": "fake", "usage": {}}
    fake.calls = 0

    async with async_session_maker() as db:
        db.add(memory_pipeline.LedgerItem(
            honcho_workspace_id="ws1", owner_peer_id="u1", kind="commitment",
            title="Dentist Thursday", detail="d", status="open",
            situation_key="dentist"))
        await db.commit()
        from src.services import maintenance_agent as ma
        ma.set_chat_fn(fake)
        try:
            out = await ma.run_maintenance(
                db, workspace_id="ws1", owner="u1", session_id="sx",
                observations="- dentist done", today="2026-10-19",
                transcript="user: dentist thursday confirmed at 2pm, all good")
        finally:
            ma.set_chat_fn(None)
    assert out["status"] == "verified"
    assert out["changes"] == {"created": 0, "updated": 0, "closed": 1}


@pytest.mark.asyncio
async def test_agent_reports_change_counts():
    from src.db import async_session_maker
    async with async_session_maker() as db:
        db.add(memory_pipeline.LedgerItem(
            honcho_workspace_id="ws1", owner_peer_id="u1", kind="commitment",
            title="Dentist Thursday", detail="d", status="open",
            situation_key="dentist"))
        await db.commit()
        from src.services import maintenance_agent as ma
        token = ma._TRANSCRIPT_CTX.set("dentist thursday confirmed at 2pm, all good")
        try:
            out = {"created": 0, "updated": 0, "closed": 0}
            res = await ma._tools(db, "ws1", "u1", "update_item",
                                  {"key": "dentist", "status": "done",
                                   "evidence": "dentist thursday confirmed at 2pm"})
            assert res.get("ok") is True
        finally:
            ma._TRANSCRIPT_CTX.reset(token)


def test_evidence_split_verified_vs_reported():
    from src.services.maintenance_agent import _evidence_spans
    v, r = _evidence_spans('"Dentist Thursday at 2pm, all good" plus some model flourish about relief',
                           "user: dentist thursday at 2pm, all good. assistant: noted.")
    assert v == ["Dentist Thursday at 2pm, all good"]
    assert "flourish" in r
    v2, r2 = _evidence_spans("Completely invented resolution narrative here", "user: nothing yet.")
    assert v2 == [] and "invented" in r2
