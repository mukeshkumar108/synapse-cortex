"""Executive layer properties: wake-driven cognition (no model call without a reason or policy), autonomy by consequence/reversibility/authority,
untrusted ids are never applied, receipts are the only way an action becomes done."""
import json
import uuid
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
    catalogue = [{"tool": "calendar.cancel", "consequence": "moderate", "reversible": False}, {"tool": "calendar.create", "consequence": "low", "reversible": True}]
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": catalogue}})
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
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": [{"tool": "message.send", "consequence": "low", "reversible": True}]}})
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
async def test_speak_candidates_are_cheap_and_gated_and_the_outbound_text_is_recorded_on_the_exact_intent():
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
        assert await executive.record_outbound(db, WS, owner, item_id, "Hey, how did the portfolio go?", "dec-1") is True
        row = await db.get(WorkItem, __import__("uuid").UUID(item_id))
        assert json.loads(row.extra_json)["outbound_text"] == "Hey, how did the portfolio go?"
        assert await executive.record_outbound(db, WS, "someone_else", item_id, "x") is False                        # another world's intent id is never touched
        assert await executive.record_outbound(db, WS, owner, "not-a-uuid", "x") is False


@pytest.mark.asyncio
async def test_a_tool_must_be_in_the_product_catalogue_its_risk_is_the_products_not_the_models_and_authority_given_later_clears_it():
    owner = "user_exec8"
    cat = [{"tool": "task.create", "description": "create a task", "consequence": "low", "reversible": True}]
    first = Model({"intents": [
        {"op": "create", "kind": "act", "title": "Add 'call mum' as a task", "consequence": "none", "reversible": True, "authority_basis": "inferred", "action": {"tool": "task.create", "args": {"title": "call mum"}}},
        {"op": "create", "kind": "act", "title": "Wire money", "consequence": "none", "reversible": True, "authority_basis": "explicit_request", "action": {"tool": "bank.transfer", "args": {}}}]})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": cat}})
        res = await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=first)
        assert {d["reason"] for d in res["dropped"]} == {"unknown_tool"}                                         # a tool nobody declared never runs, whatever the model claims
        item = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "ask"))).scalars().one()
        assert json.loads(item.extra_json)["requires_confirmation"] and await executive.pending_actions_all(db, WS) == []     # inferred authority: a question, not an action
        second = Model({"intents": [{"op": "update", "id": str(item.id), "authority_basis": "explicit_request", "rationale": "user said yes"}]})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["user_replied"], adapter=second)
        pending = [p for p in await executive.pending_actions_all(db, WS) if p["owner"] == owner]
        assert len(pending) == 1 and pending[0]["tool"]["tool"] == "task.create"                                  # authority granted + product-declared low/reversible: cleared
        await executive.record_receipt(db, workspace_id=WS, owner=owner, work_item_id=pending[0]["work_item_id"], status="started", result_ref=None, detail=None)
        assert [p for p in await executive.pending_actions_all(db, WS) if p["owner"] == owner] == []              # claimed: cannot be executed twice
        await executive.record_receipt(db, workspace_id=WS, owner=owner, work_item_id=pending[0]["work_item_id"], status="succeeded", result_ref="task-1", detail=None)
        done = await db.get(WorkItem, __import__("uuid").UUID(pending[0]["work_item_id"]))
        assert done.status == "done" and json.loads(done.receipt_json)["result_ref"] == "task-1"


@pytest.mark.asyncio
async def test_the_executive_sees_its_own_completed_actions_and_an_identical_call_is_never_created_twice():
    owner = "user_exec9"
    cat = [{"tool": "task.create", "consequence": "low", "reversible": True}]
    act = {"op": "create", "kind": "act", "title": "Add walk task", "authority_basis": "explicit_request", "action": {"tool": "task.create", "args": {"title": "Evening walk"}}}
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": cat}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=Model({"intents": [act]}))
        item = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "act"))).scalars().one()
        await executive.record_receipt(db, workspace_id=WS, owner=owner, work_item_id=str(item.id), status="succeeded", result_ref="task-9", detail=None)
        again = Model({"intents": [act]})
        res = await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["receipt"], adapter=again)
        rows = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "act"))).scalars().all()
    ctx = json.loads(again.calls[0]["prompt"].split("CONTEXT (ids are real):\n")[1])
    assert ctx["recent_actions"][0]["receipt"]["result_ref"] == "task-9" and ctx["recent_actions"][0]["status"] == "done"          # it can see what it already did
    assert [d["reason"] for d in res["dropped"]] == ["duplicate_action"] and len(rows) == 1                                      # and a repeat is refused mechanically


@pytest.mark.asyncio
async def test_a_reply_is_linked_to_the_exact_intent_by_message_id_and_wakes_the_executive_with_it():
    owner = "user_exec10"
    model = Model({"intents": [{"op": "create", "kind": "check_in", "title": "Ask about the gym", "importance": 0.8, "surface_now": True, "message_gist": "gym"}]})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=model)
        item = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "check_in"))).scalars().one()
        await executive.mark_surfaced(db, str(item.id), now())
        await executive.record_outbound(db, WS, owner, str(item.id), "How's the gym going?", "dec-1", "msg-out-1")
        msgs = [{"id": "msg-out-1", "speaker": "assistant", "text": "How's the gym going?"}, {"id": "u-9", "speaker": "user", "text": "Skipped it again, honestly."}]
        index = await executive.outbound_index(db, WS, owner, [m["id"] for m in msgs])
        assert index == {"msg-out-1": {"intent_id": str(item.id), "title": "Ask about the gym"}}
        assert await executive.link_replies(db, WS, owner, msgs, index) == 1
        assert await executive.link_replies(db, WS, owner, msgs, index) == 0                                  # the same reply is never linked twice
        row = await db.get(WorkItem, item.id)
        assert json.loads(row.extra_json)["reply"] == {"message_id": "u-9", "text": "Skipped it again, honestly."}
        follow = Model({"intents": []})
        await executive.tick(db, adapter=follow, now=now() + timedelta(minutes=2))
    ctx = json.loads(follow.calls[0]["prompt"].split("CONTEXT (ids are real):\n")[1])
    assert ctx["external_events"][0]["user_reply"] == "Skipped it again, honestly." and "reply_to_intent" in ctx["woken_because"]
    assert ctx["recent_outcomes"][0]["what_was_said"] == "How's the gym going?" and ctx["recent_outcomes"][0]["user_reply"] == "Skipped it again, honestly."


@pytest.mark.asyncio
async def test_the_foreground_picture_shows_what_is_carried_waited_on_raised_done_and_set_aside_and_the_snapshot_version_moves():
    from src.services import world_model_service
    owner = "user_exec11"
    cat = [{"tool": "task.create", "consequence": "low", "reversible": True}]
    model = Model({"intents": [
        {"op": "create", "kind": "wait", "title": "James to confirm the viewing", "waiting_on": "James replying"},
        {"op": "create", "kind": "check_in", "title": "Ask about the portfolio", "surface_now": True, "message_gist": "portfolio"},
        {"op": "create", "kind": "act", "title": "Add walk task", "authority_basis": "explicit_request", "action": {"tool": "task.create", "args": {"title": "walk"}}}],
        "agenda": {"carrying": [{"title": "Ask about the portfolio", "horizon": "now", "stance": "pursue", "why": "deadline today"}], "sequence_note": "portfolio first"}})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": cat}})
        before = (await world_model_service.compile_world_model(db, workspace_id=WS, owner_peer_id=owner, now=now(), timezone_str="UTC", force=True))["meta"]["version"]
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=model)
        rows = {r.action: r for r in (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner))).scalars().all()}
        await executive.record_receipt(db, workspace_id=WS, owner=owner, work_item_id=str(rows["Add walk task"].id), status="succeeded", result_ref="t1", detail=None)
        await executive.mark_surfaced(db, str(rows["Ask about the portfolio"].id), now())
        layer = await executive.executive_layer(db, WS, owner)
        snap = await world_model_service.get_world_model(db, workspace_id=WS, owner_peer_id=owner, now=now(), timezone_str="UTC")
    assert layer["carrying"][0]["title"] == "Ask about the portfolio" and layer["sequence_note"] == "portfolio first"
    assert layer["waiting_on"][0]["waiting_on"] == "James replying" and layer["raised_recently"][0]["title"] == "Ask about the portfolio"
    assert layer["did_recently"] == [{"title": "Add walk task", "outcome": "succeeded"}]
    assert snap["meta"]["version"] > before and snap["executive"]["carrying"]                                  # the resident snapshot carries it and its version moved


@pytest.mark.asyncio
async def test_a_plan_groups_its_steps_refs_resolve_inside_one_response_and_a_cleared_dependency_wakes_the_executive():
    owner = "user_exec12"
    first = Model({"intents": [
        {"op": "create", "ref": "p1", "kind": "plan", "title": "Get the flat viewing sorted", "rationale": "goal"},
        {"op": "create", "ref": "s1", "kind": "wait", "title": "James confirms the viewing", "about": {"type": "plan", "id": "ref:p1"}, "waiting_on": "James"},
        {"op": "create", "ref": "s2", "kind": "check_in", "title": "Arrange the Saturday morning around it", "about": {"type": "plan", "id": "ref:p1"}, "depends_on": ["ref:s1", "ref:ghost"]}]})
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=first)
        rows = {r.action: r for r in (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind != "agenda"))).scalars().all()}
        plan, step1, step2 = rows["Get the flat viewing sorted"], rows["James confirms the viewing"], rows["Arrange the Saturday morning around it"]
        assert step1.parent_type == "plan" and step1.parent_id == str(plan.id) and step2.parent_id == str(plan.id)              # steps hang under the plan created in the same response
        deps = json.loads(step2.extra_json)["depends_on_ids"]
        assert deps == [str(step1.id)] and step2.status == "waiting"                                                            # the ghost ref was not trusted
        layer = await executive.executive_layer(db, WS, owner)
        assert layer["plans"][0]["goal"] == "Get the flat viewing sorted" and len(layer["plans"][0]["steps"]) == 2
        second = Model({"intents": [{"op": "done", "id": str(step1.id)}]})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["reply"], adapter=second)
        follow = Model({"intents": []})
        await executive.tick(db, adapter=follow, now=now() + timedelta(minutes=2))
    ctx = json.loads(follow.calls[0]["prompt"].split("CONTEXT (ids are real):\n")[1])
    event = next(e for e in ctx["external_events"] if e["reason"] == "dependency_cleared")
    assert event["cleared"] == "James confirms the viewing" and event["unblocked"] == ["Arrange the Saturday morning around it"]       # the executive is told what was unblocked


@pytest.mark.asyncio
async def test_an_interrupted_pass_and_a_claimed_but_unreported_action_are_recovered_not_lost_or_repeated():
    from src.models.world import ProducerRun
    owner = "user_exec13"
    old = now() - timedelta(minutes=40)
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": [{"tool": "task.create", "consequence": "low", "reversible": True}]}})
        db.add(ProducerRun(honcho_workspace_id=WS, owner_peer_id=owner, producer="executive", status="running", created_at=old, input_json=json.dumps({"reasons": ["world_interpreted"]})))
        await db.commit()
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=Model({"intents": [
            {"op": "create", "kind": "act", "title": "Add task", "authority_basis": "explicit_request", "action": {"tool": "task.create", "args": {"title": "x"}}}]}))
        act = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "act"))).scalars().one()
        act.receipt_json = json.dumps({"status": "started", "at": old.isoformat()})            # claimed by the app, then the app died
        db.add(act)
        await db.commit()
        model = Model({"intents": []})
        await executive.tick(db, adapter=model, now=now())
        runs = (await db.execute(select(ProducerRun).where(ProducerRun.owner_peer_id == owner, ProducerRun.producer == "executive"))).scalars().all()
        await db.refresh(act)
        assert [r.status for r in runs].count("failed") == 1 and act.status == "failed"                              # nothing hangs forever
        assert await executive.pending_actions_all(db, WS) == [] or all(p["owner"] != owner for p in await executive.pending_actions_all(db, WS))   # and it is NOT re-executed automatically
        await executive.tick(db, adapter=model, now=now() + timedelta(minutes=1))
    reasons = " ".join(" ".join(c["prompt"].split("woken_because")[1][:200].split()) for c in model.calls)
    assert "recovered" in reasons or "action_stalled" in reasons                                                    # the executive was woken to deal with both


@pytest.mark.asyncio
async def test_a_consequential_action_needs_the_users_linked_reply_and_then_runs_without_ever_lowering_the_products_declared_risk():
    owner = "user_exec14"
    cat = [{"tool": "task.cancel", "consequence": "moderate", "reversible": False}]
    ask = {"op": "create", "kind": "act", "title": "Remove the passport task", "authority_basis": "explicit_request", "surface_now": True, "message_gist": "confirm removal",
           "action": {"tool": "task.cancel", "args": {"task_id": "t-1"}}}
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": cat}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=Model({"intents": [ask]}))
        item = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "ask"))).scalars().one()
        assert json.loads(item.extra_json)["requires_confirmation"]                                             # even an explicit request does not clear an irreversible tool
        claim = {"intents": [{"op": "update", "id": str(item.id), "authority_basis": "confirmed_by_user"}]}
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t2"], adapter=Model(claim))
        assert [p for p in await executive.pending_actions_all(db, WS) if p["owner"] == owner] == []             # claiming confirmation WITHOUT a linked reply does nothing
        await executive.mark_surfaced(db, str(item.id), now())
        await executive.record_outbound(db, WS, owner, str(item.id), "Remove the passport task for good?", "d", "out-5")
        await executive.link_replies(db, WS, owner, [{"id": "out-5", "speaker": "assistant", "text": "x"}, {"id": "u-5", "speaker": "user", "text": "yes, remove it"}],
                                     {"out-5": {"intent_id": str(item.id), "title": "Remove the passport task"}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["reply"], adapter=Model(claim))
        pending = [p for p in await executive.pending_actions_all(db, WS) if p["owner"] == owner]
    assert len(pending) == 1 and pending[0]["tool"]["tool"] == "task.cancel"                                      # linked reply + confirmation: cleared


@pytest.mark.asyncio
async def test_an_ask_that_carries_a_tool_is_a_confirmation_request_and_a_linked_yes_releases_it():
    owner = "user_exec15"
    cat = [{"tool": "task.cancel", "consequence": "moderate", "reversible": False}]
    plain_ask = {"op": "create", "kind": "ask", "title": "Delete the duplicate task?", "surface_now": True, "message_gist": "offer",
                 "action": {"tool": "task.cancel", "args": {"task_id": "dup-1"}}}
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}, "capabilities": {"tools": cat}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["t"], adapter=Model({"intents": [plain_ask, {**plain_ask, "title": "Ghost", "action": {"tool": "nope.tool", "args": {}}}]}))
        item = (await db.execute(select(WorkItem).where(WorkItem.owner_peer_id == owner, WorkItem.kind == "ask"))).scalars().one()          # the ghost-tool ask was dropped
        assert json.loads(item.extra_json)["requires_confirmation"] is True
        await executive.mark_surfaced(db, str(item.id), now())
        await executive.record_outbound(db, WS, owner, str(item.id), "Delete the duplicate?", "d", "out-7")
        await executive.link_replies(db, WS, owner, [{"id": "out-7", "speaker": "assistant", "text": "x"}, {"id": "u-7", "speaker": "user", "text": "yes"}], {"out-7": {"intent_id": str(item.id), "title": "t"}})
        await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["reply"], adapter=Model({"intents": [{"op": "update", "id": str(item.id), "authority_basis": "confirmed_by_user"}]}))
        assert [p["tool"]["args"] for p in await executive.pending_actions_all(db, WS) if p["owner"] == owner] == [{"task_id": "dup-1"}]


def test_a_lab_pass_layer_is_derived_from_the_raw_response_without_persisting_anything():
    from src.services.executive import layer_from_raw
    raw = {"intents": [
        {"op": "create", "kind": "plan", "title": "Make the cabin Friday feel special", "ref": "p1", "rationale": "x"},
        {"op": "create", "kind": "prepare", "title": "Pack the good blanket", "about": {"type": "plan", "id": "p1"}, "waiting_on": None},
        {"op": "create", "kind": "check_in", "title": "Ask how the supervisor lunch went", "waiting_on": "his answer"},
        {"op": "cancel", "kind": "remind", "title": "Remind him about the ladder", "reason": "already settled"}],
        "agenda": {"carrying": [{"title": "Cabin trip", "horizon": "this_week", "stance": "pursue", "why": "she is looking forward to it"}], "sequence_note": "pack first"}}
    layer = layer_from_raw(raw)
    assert layer["carrying"][0]["title"] == "Cabin trip" and layer["plans"][0]["goal"].startswith("Make the cabin") and layer["plans"][0]["steps"][0]["title"] == "Pack the good blanket"
    assert layer["waiting_on"] == [{"title": "Ask how the supervisor lunch went", "waiting_on": "his answer"}] and layer["set_aside"][0]["reason"] == "already settled"
    assert layer_from_raw(None)["carrying"] == []


@pytest.mark.asyncio
async def test_a_self_scheduled_review_is_floored_so_the_executive_does_not_poll():
    owner = f"floor-{uuid.uuid4().hex[:6]}"
    soon = (now() + timedelta(minutes=45)).isoformat()
    async with async_session_maker() as db:
        await executive.set_policy(db, WS, owner, {"executive": {"enabled": True}})
        res = await executive.run_pass(db, workspace_id=WS, owner=owner, reasons=["test"], adapter=Model({"intents": [], "next_review_at": soon}))
    review = next(w for w in res["wakes"] if w["reason"] == "next_review")
    assert datetime.fromisoformat(review["due"]) >= now() + timedelta(hours=executive.MIN_REVIEW_INTERVAL_HOURS) - timedelta(minutes=1)
