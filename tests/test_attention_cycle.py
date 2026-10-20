"""Attention cycle acceptance: service behavior scripted end-to-end. No network."""
import pytest

from src.db import async_session_maker
from src.services import attention_cycle
from src.services import memory_pipeline


async def _seed_ledger():
    async with async_session_maker() as db:
        await memory_pipeline.apply_situations(
            db, workspace_id="ws1", owner="u1", run_id=None, session_id="s1",
            statements={"new": [
                {"key": "dentist", "title": "Dentist Thursday 2pm", "kind": "appointment",
                 "timing_text": "Thursday 2pm", "expected_date": "2026-10-22",
                 "evidence": ["dentist thursday"]},
                {"key": "invoice", "title": "Invoice from James", "kind": "situation",
                 "waiting_on": "James approval", "evidence": ["waiting james"]}],
                "update": [], "close": []})
        await db.commit()


@pytest.mark.asyncio
async def test_schedule_dedupe_and_transitions():
    await _seed_ledger()
    async with async_session_maker() as db:
        # 1. schedule without being asked (casual mention -> intention)
        r1 = await attention_cycle._tools(db, "ws1", "u1", "schedule_action",
                                          {"matter": "dentist", "intent": "Remind Thursday morning",
                                           "why": "appointment at 2pm", "kind": "reminder",
                                           "due_at": "2026-10-22T08:00"})
        assert r1["ok"] and r1["action"]["state"] == "pending"
        # duplicate refused
        r2 = await attention_cycle._tools(db, "ws1", "u1", "schedule_action",
                                          {"matter": "dentist", "intent": "Remind Thursday morning",
                                           "kind": "reminder"})
        assert "error" in r2 and "existing_id" in r2
        # 2. reschedule on move
        r3 = await attention_cycle._tools(db, "ws1", "u1", "update_action",
                                          {"id": r1["action"]["id"], "due_at": "2026-10-23T08:00"})
        assert r3["ok"] and r3["action"]["due_at"].startswith("2026-10-23")
        # 3. stop fussing -> suppress (matter stays open)
        r4 = await attention_cycle._tools(db, "ws1", "u1", "record_event",
                                          {"matter": "dentist", "event": "suppressed",
                                           "detail": "stop fussing, knows about it"})
        assert r4["ok"]
        pending = await attention_cycle.pending_attention(db, workspace_id="ws1", owner="u1")
        assert all(a.get("matter") != "dentist" for a in pending)
        items = await memory_pipeline.open_ledger(db, "ws1", "u1")
        assert any(i.situation_key == "dentist" for i in items)  # matter still open
        # lift suppression
        r5 = await attention_cycle._tools(db, "ws1", "u1", "record_event",
                                          {"matter": "dentist", "event": "unsuppressed",
                                           "detail": "asked about it again"})
        assert r5["ok"]
        pending = await attention_cycle.pending_attention(db, workspace_id="ws1", owner="u1")
        assert any(a.get("matter") == "dentist" for a in pending)
        # 4. delivered requires evidence; undelivered stays visible
        r6 = await attention_cycle._tools(db, "ws1", "u1", "update_action",
                                          {"id": r1["action"]["id"], "state": "delivered"})
        assert "error" in r6
        r7 = await attention_cycle._tools(db, "ws1", "u1", "update_action",
                                          {"id": r1["action"]["id"], "state": "delivered",
                                           "evidence": "push receipt abc"})
        assert r7["ok"]


@pytest.mark.asyncio
async def test_mark_due_and_held_and_replay_idempotent():
    await _seed_ledger()
    from datetime import datetime
    async with async_session_maker() as db:
        r = await attention_cycle._tools(db, "ws1", "u1", "schedule_action",
                                         {"matter": "invoice", "intent": "Chase James",
                                          "kind": "followup", "due_at": "2026-10-10T09:00"})
        assert r["ok"]
        due = await attention_cycle.mark_due(db, workspace_id="ws1", owner="u1",
                                             now=datetime(2026, 10, 19))
        assert len(due) == 1 and due[0]["state"] == "due"
        # replay: already due, not re-marked
        due2 = await attention_cycle.mark_due(db, workspace_id="ws1", owner="u1",
                                              now=datetime(2026, 10, 19))
        assert due2 == []
        # held survives gates
        await attention_cycle._tools(db, "ws1", "u1", "update_action",
                                     {"id": r["action"]["id"], "state": "held"})
        due3 = await attention_cycle.mark_due(db, workspace_id="ws1", owner="u1",
                                              now=datetime(2026, 10, 20))
        assert due3 == []


@pytest.mark.asyncio
async def test_review_schedules_and_verifies():
    await _seed_ledger()
    script = [
        {"tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "list_matters", "arguments": "{}"}}]},
        {"tool_calls": [{"id": "c2", "type": "function",
                         "function": {"name": "schedule_action", "arguments":
                                      '{"matter": "dentist", "intent": "Remind Thursday morning", "why": "2pm appointment", "kind": "reminder", "due_at": "2026-10-22T08:00"}'}},
                        {"id": "c3", "type": "function",
                         "function": {"name": "attention_history", "arguments": "{}"}}]},
        {"tool_calls": [{"id": "c4", "type": "function",
                         "function": {"name": "finish", "arguments": '{"summary": "dentist reminder set; invoice already watched"}'}}]},
    ]
    state = {"n": 0}

    async def fake(model, messages):
        out = script[state["n"]]
        state["n"] += 1
        return {"content": "", "tool_calls": out["tool_calls"], "model": model,
                "provider": "fake", "usage": {"prompt_tokens": 5, "completion_tokens": 5}}

    async with async_session_maker() as db:
        attention_cycle.set_chat_fn(fake)
        try:
            out = await attention_cycle.run_attention_review(
                db, workspace_id="ws1", owner="u1", today_utc="2026-10-19",
                reason="test")
        finally:
            attention_cycle.set_chat_fn(None)
    assert out["status"] == "verified" and out["inspected"] is True
    assert len(out["calls"]) == 3
    async with async_session_maker() as db:
        pending = await attention_cycle.pending_attention(db, workspace_id="ws1", owner="u1")
        assert any(a["matter"] == "dentist" and a["due_at"].startswith("2026-10-22") for a in pending)


@pytest.mark.asyncio
async def test_tick_marks_due_and_skips_fresh_review():
    await _seed_ledger()
    async with async_session_maker() as db:
        await attention_cycle._tools(db, "ws1", "u1", "schedule_action",
                                     {"matter": "dentist", "intent": "Remind",
                                      "kind": "reminder", "due_at": "2026-10-10T09:00"})
        from datetime import datetime
        due = await attention_cycle.mark_due(db, workspace_id="ws1", owner="u1",
                                             now=datetime(2026, 10, 19))
        assert len(due) == 1
        cfg = attention_cycle.tick_config()
        assert cfg["tick_seconds"] >= 60 and cfg["review_stale_hours"] >= 1


@pytest.mark.asyncio
async def test_describe_states_three_facts():
    await _seed_ledger()
    async with async_session_maker() as db:
        await attention_cycle._tools(db, "ws1", "u1", "schedule_action",
                                     {"matter": "dentist", "intent": "Remind him Thursday morning",
                                      "kind": "reminder", "due_at": "2026-10-22T08:00"})
        lines = await attention_cycle.describe_attention(db, workspace_id="ws1", owner="u1")
        assert len(lines) == 1
        assert "Remind Sophie" not in lines[0]
        assert "not yet delivered" in lines[0]


@pytest.mark.asyncio
async def test_review_records_surfaced_from_findings():
    await _seed_ledger()
    script = [
        {"tool_calls": [{"id": "c1", "type": "function",
                         "function": {"name": "list_matters", "arguments": "{}"}}]},
        {"tool_calls": [{"id": "c2", "type": "function",
                         "function": {"name": "record_event", "arguments":
                                      '{"matter": "dentist", "event": "surfaced", "detail": "asked what time Thursday"}'}}]},
        {"tool_calls": [{"id": "c3", "type": "function",
                         "function": {"name": "finish", "arguments": '{"summary": "surfaced dentist question"}'}}]},
    ]
    state = {"n": 0}

    async def fake(model, messages):
        assert any("asked about a tracked unknown" in str(m.get("content") or "") for m in messages), \
            "findings must reach the review prompt"
        out = script[state["n"]]
        state["n"] += 1
        return {"content": "", "tool_calls": out["tool_calls"], "model": model,
                "provider": "fake", "usage": {}}

    async with async_session_maker() as db:
        attention_cycle.set_chat_fn(fake)
        try:
            out = await attention_cycle.run_attention_review(
                db, workspace_id="ws1", owner="u1", today_utc="2026-10-19",
                reason="end-of-sitting",
                findings="Sophie asked what time the dentist appointment is on Thursday.")
        finally:
            attention_cycle.set_chat_fn(None)
    assert out["status"] == "verified"
    async with async_session_maker() as db:
        lines = await attention_cycle.describe_attention(db, workspace_id="ws1", owner="u1")
        assert any("already asked" in l for l in lines), lines


@pytest.mark.asyncio
async def test_follow_ups_must_reference_a_live_matter_and_a_future_time():
    from datetime import datetime, timezone
    from src.models.world import LedgerItem
    from src.services import attention_cycle as ac
    async with async_session_maker() as db:
        db.add(LedgerItem(honcho_workspace_id="wsA", owner_peer_id="uA", kind="commitment", title="Open thing", status="open", situation_key="open-thing"))
        db.add(LedgerItem(honcho_workspace_id="wsA", owner_peer_id="uA", kind="commitment", title="Done thing", status="done", situation_key="done-thing"))
        await db.commit()
        tz_t = ac._TZ_CTX.set("Europe/London")
        now_t = ac._NOW_CTX.set(datetime(2026, 10, 19, 19, 0))               # 20:00 BST on the person's Monday
        try:
            assert "unknown matter key" in (await ac._tools(db, "wsA", "uA", "schedule_action", {"intent": "x", "matter": "invoice-approval"}))["error"]
            assert "nothing left to follow up" in (await ac._tools(db, "wsA", "uA", "schedule_action", {"intent": "x", "matter": "done-thing"}))["error"]
            assert "in the past" in (await ac._tools(db, "wsA", "uA", "schedule_action", {"intent": "x", "matter": "open-thing", "due_at": "2026-10-19T09:00"}))["error"]
            ok = await ac._tools(db, "wsA", "uA", "schedule_action", {"intent": "Remind him", "matter": "open-thing", "due_at": "2026-10-20T08:00"})
            assert ok["ok"] and ok["action"]["due_at"] == "2026-10-20T07:00:00+00:00"       # 08:00 BST stored as UTC, emitted with its offset
        finally:
            ac._TZ_CTX.reset(tz_t)
            ac._NOW_CTX.reset(now_t)


@pytest.mark.asyncio
async def test_closing_a_matter_supersedes_its_pending_follow_ups():
    from src.models.world import AttentionAction, LedgerItem
    from src.services import maintenance_agent as ma
    from sqlmodel import select
    async with async_session_maker() as db:
        db.add(LedgerItem(honcho_workspace_id="wsA", owner_peer_id="uB", kind="commitment", title="Invoice", status="open", situation_key="invoice"))
        await db.commit()
        await ac_tools(db, "uB")
        tok = ma._TRANSCRIPT_CTX.set("James approved the invoice this morning.")
        try:
            res = await ma._tools(db, "wsA", "uB", "update_item", {"key": "invoice", "status": "done", "evidence": "James approved the invoice this morning."})
        finally:
            ma._TRANSCRIPT_CTX.reset(tok)
        assert res["ok"] and res["follow_ups_superseded"] == 1
        (a,) = (await db.execute(select(AttentionAction).where(AttentionAction.owner_peer_id == "uB"))).scalars().all()
        assert a.state == "superseded"


async def ac_tools(db, owner):
    from src.services import attention_cycle as ac
    r = await ac._tools(db, "wsA", owner, "schedule_action", {"intent": "Check in on the invoice", "matter": "invoice"})
    assert r["ok"]
