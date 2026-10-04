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


def test_standing_delegated_authority_lets_a_scoped_action_proceed_without_a_fresh_confirmation():
    act = {"kind": "act", "consequence": "low", "reversible": True, "authority_basis": "inferred", "action": {"tool": "calendar.create", "args": {}}}
    assert executive.permission(act)["mode"] == "needs_confirmation"                                              # inferred authority alone is not enough
    grant = [{"tool": "calendar.", "max_consequence": "low"}]
    assert executive.permission(act, grant) == {"mode": "autonomous", "basis": "delegation"}
    assert executive.permission({**act, "consequence": "moderate"}, grant)["mode"] == "needs_confirmation"      # outside the delegated scope
    assert executive.permission({**act, "action": {"tool": "email.send"}}, grant)["mode"] == "needs_confirmation"


@pytest.mark.asyncio
async def test_the_agenda_persists_what_is_being_carried_and_a_set_aside_concern_is_remembered_not_reconsidered():
    owner = "user_exec5"
    first = Model({"intents": [{"op": "create", "kind": "check_in", "title": "Ask about the gym", "horizon": "this_week", "stance": "pursue"}],
                   "agenda": {"carrying": [{"title": "Ask about the gym", "horizon": "this_week", "stance": "pursue", "why": "weekly goal"}], "sequence_note": "gym after the deadline"}})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=first)
        item = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "check_in"))).scalars().one()
        second = Model({"intents": [{"op": "cancel", "id": str(item.id), "reason": "user said the gym is off this month"}], "agenda": {"carrying": [], "sequence_note": "nothing carried"}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t2"], adapter=second)
        third = Model({"intents": []})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t3"], adapter=third)
    ctx2 = json.loads(second.calls[0]["prompt"].split("CONTEXT (ids are real):\n")[1])
    ctx3 = json.loads(third.calls[0]["prompt"].split("CONTEXT (ids are real):\n")[1])
    assert ctx2["agenda"]["carrying"][0]["title"] == "Ask about the gym"                                          # the last agenda is handed back to the executive
    assert ctx3["set_aside"] == [{"id": str(item.id), "title": "Ask about the gym", "reason": "user said the gym is off this month"}]
    assert ctx3["agenda"]["sequence_note"] == "nothing carried" and ctx3["intents"] == []                         # agenda bookkeeping never shows up as an intent


@pytest.mark.asyncio
async def test_an_external_event_reaches_the_executive_and_outreach_is_followed_by_raw_outcome_facts():
    owner = "user_exec6"
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.note_changed(db, WS, owner, "calendar_changed", delay_seconds=0, detail={"event": "3pm meeting moved to 5pm"})
    model = Model({"intents": []})
    async with async_session_maker() as db:
        await executive.tick(db, adapter=model, now=now() + timedelta(seconds=5))
    ctx = json.loads(model.calls[0]["prompt"].split("CONTEXT (ids are real):\n")[1])
    assert ctx["external_events"][0]["event"] == "3pm meeting moved to 5pm" and "calendar_changed" in ctx["woken_because"]


@pytest.mark.asyncio
async def test_a_world_whose_operational_semantics_belong_to_the_interpreter_is_only_stamped_by_the_turn_endpoint(async_client, monkeypatch):
    from src.models.expectation import Expectation
    from src.models.operational_state import TurnStamp
    from src.routers import v1_events
    called = []
    monkeypatch.setattr(v1_events.turn_extractor, "extract_candidates", lambda *a, **kw: called.append(1) or [])
    payload = {"workspace_id": "ws-own", "session_id": "s", "honcho_message_id": "m-own", "peer_id": "user_own", "text": "Remind me to call mum at 5pm.",
               "now": "2026-10-04T12:00:00+01:00", "timezone": "Europe/London"}
    async with async_session_maker() as db:
        await executive.set_policy(db, "ws-own", "user_own", {"operational": {"owner": "interpreter"}})
    r = await async_client.post("/v1/events/turn", json=payload)
    assert r.status_code == 202 and r.json()["interpreter_owns_meaning"] is True and called == []                   # no legacy reader ran
    async with async_session_maker() as db:
        assert (await db.execute(select(TurnStamp).where(TurnStamp.honcho_workspace_id == "ws-own"))).scalars().one().honcho_message_id == "m-own"
        assert (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == "ws-own"))).scalars().all() == []


@pytest.mark.asyncio
async def test_speak_candidates_are_cheap_and_gated_and_the_outbound_message_is_linked_to_exactly_one_raised_intent():
    from src.models.operational_state import ProactiveLog
    owner = "user_exec7"
    model = Model({"intents": [{"op": "create", "kind": "check_in", "title": "Ask about the portfolio", "importance": 0.9, "surface_now": True, "message_gist": "portfolio"},
                               {"op": "create", "kind": "remind", "title": "Passport", "importance": 0.4, "surface_now": False}]})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=model)
        cands = await executive.speak_candidates(db, WS)
        mine = [c for c in cands if c["owner"] == owner]
        assert len(mine) == 1 and mine[0]["title"] == "Ask about the portfolio" and mine[0]["count"] == 1           # only what wants to be raised; no model call
        db.add(ProactiveLog(honcho_workspace_id=WS, owner_peer_id=owner, at=now(), item_key="x", reason="quiet hours", decision="withheld:quiet_hours"))
        await db.commit()
        assert [c for c in await executive.speak_candidates(db, WS) if c["owner"] == owner] == []                   # recently held back by the gate: not asked again every minute
        item_id = mine[0]["intent_id"]
        await executive.mark_surfaced(db, item_id, now())
        assert await executive.attach_outbound(db, WS, owner, "msg-77", "Hey, how did the portfolio go?", now()) is True
        row = await db.get(WorkItem, __import__("uuid").UUID(item_id))
        assert json.loads(row.extra_json)["outbound_message_id"] == "msg-77"
        assert await executive.attach_outbound(db, WS, owner, "msg-78", "another", now()) is False                  # nothing outstanding: no guess
