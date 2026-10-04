"""Executive layer properties: wake-driven cognition (no model call without a reason or policy), autonomy by consequence/reversibility/authority,
untrusted ids are never applied, receipts are the only way an action becomes done."""
import json
from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.work_item import WorkItem
from src.services import executive

WS, OWNER = "ws-exec", "user_exec1"


class Model:
    def __init__(self, raw): self.raw, self.calls, self.last_usage = raw, [], None
    async def generate_structured(self, **kw):
        self.calls.append(kw); return self.raw


def now(): return datetime.utcnow()


@pytest.mark.asyncio
async def test_the_tick_calls_no_model_when_nothing_is_due_or_the_world_has_not_opted_in():
    model = Model({"intents": []})
    async with async_session_maker() as db:
        await executive.add_wake(db, WS, OWNER, now() - timedelta(minutes=1), "world_interpreted")       # due, but this world's policy is off
        out = await executive.tick(db, adapter=model, now=now())
        assert model.calls == [] and out["skipped_disabled"] == 1
        await executive.set_policy(db, WS, OWNER, {"executive": {"enabled": True}})
        out = await executive.tick(db, adapter=model, now=now())                # a newly enabled world gets exactly one initial review
        assert len(model.calls) == 1 and out["ran"][0]["status"] == "applied"
        await executive.add_wake(db, WS, OWNER, now() + timedelta(hours=3), "next_review")                # a future wake is not a reason yet
        out = await executive.tick(db, adapter=model, now=now())
    assert len(model.calls) == 1 and out["ran"] == []


@pytest.mark.asyncio
async def test_a_due_wake_runs_one_pass_and_a_wait_outcome_costs_nothing_further():
    owner = "user_exec2"
    model = Model({"intents": [], "note": "nothing needs attention"})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.add_wake(db, WS, owner, now() - timedelta(seconds=1), "world_interpreted")
        first = await executive.tick(db, adapter=model, now=now())
        second = await executive.tick(db, adapter=model, now=now())          # the wake was consumed; no new reason exists
    assert len(model.calls) == 1 and first["ran"][0]["status"] == "applied" and second["ran"] == []
    assert "CONTEXT" in model.calls[0]["prompt"] and "woken_because" in model.calls[0]["prompt"]


@pytest.mark.asyncio
async def test_intents_are_validated_ids_never_trusted_and_consequential_actions_become_confirmation_requests():
    owner = "user_exec3"
    future = (now() + timedelta(hours=5)).isoformat() + "Z"
    raw = {"intents": [
        {"op": "create", "kind": "check_in", "title": "Ask how the Henderson portfolio went", "rationale": "window ended, outcome unknown", "about": {"type": "expectation", "id": "fabricated-id"},
         "importance": 0.8, "surface_now": True, "message_gist": "check in on the portfolio", "wake_at": future, "waiting_on": "the user's answer"},
        {"op": "create", "kind": "act", "title": "Cancel the dentist booking", "rationale": "user seems to be avoiding it", "consequence": "moderate", "reversible": False,
         "authority_basis": "inferred", "action": {"tool": "calendar.cancel", "args": {"event": "x"}}},
        {"op": "create", "kind": "act", "title": "Add the reminder to the calendar", "rationale": "user asked", "consequence": "low", "reversible": True,
         "authority_basis": "explicit_request", "action": {"tool": "calendar.create", "args": {}}},
        {"op": "update", "id": "not-an-intent-i-was-shown", "title": "x"},
        {"op": "create", "kind": "act", "title": "No tool named", "consequence": "low", "reversible": True, "authority_basis": "delegated"}],
        "next_review_at": future}
    model = Model(raw)
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        res = await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["test"], adapter=model)
        rows = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner))).scalars().all()
        agenda = await executive.surfaced_agenda(db, WS, owner)
    by_title = {r.action: r for r in rows}
    assert by_title["Ask how the Henderson portfolio went"].parent_type == "world"                               # the fabricated parent id was not trusted
    cancel = by_title["Cancel the dentist booking"]
    assert cancel.kind == "ask" and json.loads(cancel.extra_json)["requires_confirmation"] and cancel.status != "in_progress"
    assert by_title["Add the reminder to the calendar"].status == "in_progress"                                # low-risk, reversible, explicitly authorised
    assert {d["reason"] for d in res["dropped"]} == {"unknown_intent_id_or_op", "act_without_tool"}
    assert {a["what"] for a in agenda} == {"Ask how the Henderson portfolio went", "Cancel the dentist booking"}  # only what wants to reach the user
    assert any(w["reason"].startswith("intent:") for w in res["wakes"]) and any(w["reason"] == "next_review" for w in res["wakes"])


@pytest.mark.asyncio
async def test_only_a_receipt_completes_an_action_and_a_surfaced_intent_is_not_raised_twice():
    owner = "user_exec4"
    model = Model({"intents": [{"op": "create", "kind": "act", "title": "Send the reminder", "consequence": "none", "reversible": True,
                                "authority_basis": "explicit_request", "action": {"tool": "message.send", "args": {}}},
                               {"op": "create", "kind": "remind", "title": "Call mum", "importance": 0.9, "surface_now": True, "message_gist": "mum"}]})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=model)
        rows = {r.action: r for r in (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner))).scalars().all()}
        act = rows["Send the reminder"]
        assert act.status == "in_progress" and act.receipt_json is None                                          # approved, not done
        await executive.record_receipt(db, workspace_id=WS, owner=owner, work_item_id=str(act.id), status="succeeded", result_ref="msg-1", detail=None)
        await db.refresh(act)
        assert act.status == "done" and json.loads(act.receipt_json)["result_ref"] == "msg-1"
        item = (await executive.surfaced_agenda(db, WS, owner))[0]
        await executive.mark_surfaced(db, item["work_item_id"], now())
        assert await executive.surfaced_agenda(db, WS, owner) == []                                              # raised once; the executive decides if it deserves raising again
