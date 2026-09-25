"""Attention/surfacing controller tests: working sets, selection, report-back.

Selection policy is pure (no DB): user-first, budgets, arbitration,
protective override, suppressions, temporal gates, postures. Report-back and
sweep touch only existing durable machinery.
"""

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.services.turn_selection import (
    effective_clock,
    pressure_of,
    select_for_turn,
    window_gate,
)


def _ws(sections, budgets=None, mandatory=()):
    return {"version": "session-working-set-v1", "composition": "session",
            "budgets": {"max_foreground_items": 3, "proactive_remaining": 2,
                        **(budgets or {})},
            "mandatory_kinds": list(mandatory), "sections": sections}


def _item(title, kind="expectation", signals=None, **kw):
    base = {"protective": False, "urgent": False, "actionable": False}
    base.update(signals or {})
    return {"kind": kind, "id": f"id-{title[:8]}", "title": title,
            "signals": base, **kw}


def test_pressure_tiers_structural():
    assert pressure_of(_item("x", signals={"urgent": True, "actionable": True},
                              kind="reminder")) == "must_resolve"
    assert pressure_of(_item("x", signals={"protective": True})) == "priority"
    assert pressure_of(_item("x", kind="open_loop",
                              signals={"actionable": True})) == "opportunistic"
    assert pressure_of(_item("x")) == "background"


def test_user_first_no_hijack():
    ws = _ws({"todo": [_item("Carlos payment debt", signals={"actionable": True}),
                        _item("Florist colours", signals={"actionable": True})]})
    out = select_for_turn(ws, turn_text="What is the capital of France?",
                          initiated_by="user")
    assert out["posture"] == "FOLLOW"
    assert out["include"] == []
    assert len(out["held"]) == 2


def test_turn_relevant_included_and_capped():
    ws = _ws({"todo": [_item(f"matter {i}", signals={"actionable": True})
                        for i in range(6)],
              "reminder": [_item("chairs reminder",
                                  signals={"urgent": True, "actionable": True})]})
    out = select_for_turn(
        ws, turn_text="remind me about the chairs reminder matter today",
        initiated_by="user")
    assert out["posture"] == "FOLLOW"
    assert len(out["include"]) <= 3
    assert any(i["title"] == "chairs reminder" for i in out["include"])


def test_protective_override_bounded():
    ws = _ws({"worry": [_item("health concern a", signals={"protective": True}),
                        _item("health concern b", signals={"protective": True})]})
    out = select_for_turn(ws, turn_text="what time is it?", initiated_by="user")
    assert out["reasons"]["protective_override_used"] is True
    assert len(out["include"]) == 1  # bounded: max 1 override


def test_proactive_budget_and_silence():
    ws = _ws({"conversation_opportunity": [_item("callback x")]},
             budgets={"proactive_remaining": 0})
    out = select_for_turn(ws, turn_text="", initiated_by="scheduler")
    assert out["include"] == []  # silence is valid
    assert out["posture"] == "HOLD"
    ws2 = _ws({"reminder": [_item("due now", kind="reminder",
                                      signals={"urgent": True, "actionable": True})]},
              budgets={"proactive_remaining": 0})
    out2 = select_for_turn(ws2, turn_text="", initiated_by="scheduler")
    assert out2["posture"] == "LEAD"  # duty bypasses spent budget


def test_suppression_and_repetition():
    ws = _ws({"todo": [_item("cake vendor", signals={"actionable": True})]},
             )
    out = select_for_turn(
        ws, turn_text="cake vendor status", initiated_by="user",
        local_state={"surfaced_topics": ["cake vendor"]})
    assert out["include"] == []
    assert out["held"][0]["hold_reason"] == "recently_surfaced"


def test_window_gate_scene_clock():
    from datetime import datetime, timezone
    item = {"title": "Mum Friday visit", "window": {"until": "2026-10-02T00:00:00"}}
    assert window_gate(item, effective_clock(None, "2026-10-05T12:00:00")) == \
        "held:window_passed"
    assert window_gate(item, effective_clock(None, "2026-09-30T12:00:00")) is None
    # Scene jump wakes latent items without touching canonical state.
    item2 = {"title": "Marko text", "not_before": "2026-10-03T00:00:00"}
    assert window_gate(item2, effective_clock(None, "2026-10-01T12:00:00")) == \
        "held:not_yet_due"
    assert window_gate(item2, effective_clock(None, "2026-10-04T12:00:00")) is None
    assert window_gate({"title": "x"}, effective_clock(None, None)) is None


def test_no_response_gesture_flag():
    ws = _ws({"conversation_opportunity": [_item("thinking of you",
                                                 kind="attention")]})
    out = select_for_turn(ws, turn_text="", initiated_by="scheduler")
    assert out["include"][0]["expects_response"] is False


@pytest.mark.asyncio
async def test_report_back_lifecycle():
    from datetime import datetime, timezone

    from src.models.clarification import ClarificationCandidate, ClarificationStatus
    from src.services.surfacing import report_back

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        db.add(ClarificationCandidate(
            honcho_workspace_id="ws-surf", honcho_session_id="s1",
            honcho_message_id="m1", description="Which day?"))
        await db.commit()
        clar = (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == "ws-surf"))).scalar_one()
        out = await report_back(
            db, workspace_id="ws-surf", session_id="s1", owner_peer_id="kai",
            events=[
                {"matter_kind": "clarification", "matter_id": str(clar.id),
                 "outcome": "answered", "move_key": "q1"},
                {"matter_kind": "open_loop", "matter_id": "nope",
                 "outcome": "bogus", "move_key": "q2"},
                {"matter_kind": "attention", "matter_id": "a1",
                 "outcome": "dismissed", "move_key": "q3"},
                {"matter_kind": "attention", "matter_id": "a2",
                 "outcome": "ignored", "move_key": "q4"},
            ],
            now=now, message_id="m9")
        assert out["ok"] == 3
        clar2 = await db.get(ClarificationCandidate, clar.id)
        assert clar2.status == ClarificationStatus.RESOLVED
        from src.models.suppression import Suppression
        supps = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == "ws-surf"))).scalars().all()
        # dismissed -> strong suppression; ignored -> none.
        assert len(supps) == 1 and supps[0].surface_scope == "all_surfaces"


@pytest.mark.asyncio
async def test_working_set_compile_and_refresh():
    from datetime import datetime, timezone

    from src.models.expectation import Expectation, ExpectationType
    from src.services.session_workingset import (
        compile_session_working_set, needs_refresh,
    )

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        db.add(Expectation(
            honcho_workspace_id="ws-ws", honcho_session_id="s1",
            honcho_message_id="m1", subject_peer_id="kai",
            title="Pay Priya back", summary="Pay Priya back",
            expectation_type=ExpectationType.USER_INTENTION))
        await db.commit()
        ws = await compile_session_working_set(
            db, workspace_id="ws-ws", session_id="s1", owner_peer_id="kai",
            now=now, product="sophie")
        assert ws["composition"] == "session"
        assert ws["source_version"]
        assert any(ws["sections"]["todos"])
        assert ws["sections"]["suppressions_deferrals"] == []
        scene = await compile_session_working_set(
            db, workspace_id="ws-ws", session_id="s1", owner_peer_id="kai",
            now=now, product="rpd2",
            scene={"time": "Friday morning", "place": "kitchen",
                   "characters": ["kai", "isa"]})
        assert scene["composition"] == "scene"
        assert scene["sections"]["scene_anchor"]["place"] == "kitchen"
        assert "character_undertakings" in scene["sections"]
        fresh = await needs_refresh(
            db, workspace_id="ws-ws", session_id="s1",
            cached_source_version=ws["source_version"])
        assert fresh["stale"] is False
        db.add(Expectation(
            honcho_workspace_id="ws-ws", honcho_session_id="s1",
            honcho_message_id="m2", subject_peer_id="kai",
            title="Second matter", summary="Second matter",
            expectation_type=ExpectationType.USER_INTENTION))
        await db.commit()
        stale = await needs_refresh(
            db, workspace_id="ws-ws", session_id="s1",
            cached_source_version=ws["source_version"])
        assert stale["stale"] is True


@pytest.mark.asyncio
async def test_background_sweep_detects_new():
    from datetime import datetime, timezone

    from src.models.clarification import ClarificationCandidate
    from src.services.background_sweep import background_sweep

    now = datetime.now(timezone.utc)
    async with async_session_maker() as db:
        first = await background_sweep(
            db, workspace_id="ws-bg", session_id="s1", owner_peer_id="kai",
            now=now)
        assert first["new"] == []
        db.add(ClarificationCandidate(
            honcho_workspace_id="ws-bg", honcho_session_id="s1",
            honcho_message_id="m1", description="Which dentist day?"))
        await db.commit()
        second = await background_sweep(
            db, workspace_id="ws-bg", session_id="s1", owner_peer_id="kai",
            now=now)
        assert any("dentist" in i["title"].lower() for i in second["new"])
        third = await background_sweep(
            db, workspace_id="ws-bg", session_id="s1", owner_peer_id="kai",
            now=now)
        assert third["new"] == []  # already seen: no repeat nag


@pytest.mark.asyncio
async def test_session_working_set_routes(async_client):
    from datetime import datetime, timezone

    base = {"workspace_id": "ws-routes", "session_id": "s1", "peer_id": "kai",
            "now": datetime.now(timezone.utc).isoformat()}
    r = await async_client.post("/v1/cortex/session-working-set", json=base)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["composition"] == "session"
    assert body["source_version"]
    r2 = await async_client.post("/v1/cortex/session-working-set", json={
        **base, "product": "rpd2",
        "scene": {"time": "Friday morning", "place": "kitchen",
                  "characters": ["kai", "isa"]}})
    assert r2.status_code == 200, r2.text
    assert r2.json()["composition"] == "scene"
    assert r2.json()["sections"]["scene_anchor"]["place"] == "kitchen"
    fresh = await async_client.post("/v1/cortex/session-working-set/refresh", json={
        "workspace_id": "ws-routes", "session_id": "s1",
        "cached_source_version": body["source_version"]})
    assert fresh.status_code == 200 and fresh.json()["stale"] is False
    stale = await async_client.post("/v1/cortex/session-working-set/refresh", json={
        "workspace_id": "ws-routes", "session_id": "s1",
        "cached_source_version": "deadbeef"})
    assert stale.json()["stale"] is True


@pytest.mark.asyncio
async def test_surfacing_report_route(async_client):
    from datetime import datetime, timezone

    r = await async_client.post("/v1/cortex/surfacing/report", json={
        "workspace_id": "ws-rroute", "session_id": "s1", "peer_id": "kai",
        "message_id": "m9",
        "now": datetime.now(timezone.utc).isoformat(),
        "events": [
            {"matter_kind": "attention", "matter_id": "a1",
             "outcome": "ignored", "move_key": "q1"},
            {"matter_kind": "attention", "matter_id": "a2",
             "outcome": "bogus", "move_key": "q2"},
        ]})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] == 1
    assert body["applied"][1]["applied"] is False


@pytest.mark.asyncio
async def test_background_sweep_route(async_client):
    from datetime import datetime, timezone

    r = await async_client.post("/v1/cortex/background-sweep", json={
        "workspace_id": "ws-bgr", "session_id": "s1", "peer_id": "kai",
        "now": datetime.now(timezone.utc).isoformat()})
    assert r.status_code == 200, r.text
    assert r.json()["new"] == []


def test_jev_flags_default_posture_with_local_fallback():
    from src.services.turn_selection import select_for_turn
    ws = {"sections": {"todo": [
        {"kind": "expectation", "id": "e1", "title": "plain matter",
         "signals": {"protective": False, "urgent": False, "actionable": True}}]},
        "budgets": {"max_foreground_items": 3, "proactive_remaining": 2},
        "mandatory_kinds": []}
    local = select_for_turn(ws, turn_text="", initiated_by="scheduler")
    assert local["posture"] == "LEAD"
    assert local["reasons"]["posture_source"] == "local_derivation"
    assert local["compiler_flags"]["gear"] is None
    empty = select_for_turn(
        {"sections": {}, "budgets": {}, "mandatory_kinds": []},
        turn_text="", initiated_by="scheduler")
    assert empty["posture"] == "HOLD"
    flagged = select_for_turn(
        ws, turn_text="", initiated_by="scheduler",
        jev_flags={"gear": "repair", "initiative": "none",
                   "reasoning_need": "deep", "domains": ["repair_presence"]})
    assert flagged["posture"] == "REPAIR"
    assert flagged["reasons"]["posture_source"] == "jev_flags"
    assert flagged["compiler_flags"]["reasoning_need"] == "deep"
    # Unknown gear values never override: local derivation stands.
    weird = select_for_turn(ws, turn_text="", initiated_by="scheduler",
                            jev_flags={"gear": "turbo"})
    assert weird["posture"] == "LEAD"
    assert weird["reasons"]["posture_source"] == "local_derivation"


def test_semantic_reactivation_reopens_suppressed():
    from src.services.turn_selection import select_for_turn
    item = {"kind": "expectation", "id": "e9", "title": "Carlos debt thread",
            "signals": {"protective": False, "urgent": False, "actionable": True}}
    supp = [{"target_id": "e9", "topic_or_entity": "Carlos debt",
             "reopen_condition": "new payment evidence", "reactivated": False}]
    ws = {"sections": {"todo": [item], "suppressions_deferrals": supp},
          "budgets": {"max_foreground_items": 3, "proactive_remaining": 2},
          "mandatory_kinds": []}
    out = select_for_turn(ws, turn_text="something else entirely",
                          initiated_by="scheduler")
    assert out["include"] == []
    assert out["suppressed"][0]["suppress_reason"] == "suppressed:target"
    supp[0]["reactivated"] = True
    out2 = select_for_turn(ws, turn_text="something else entirely",
                           initiated_by="scheduler")
    assert len(out2["include"]) == 1
    assert out2["include"][0]["select_reason"] == "reactivated_by_new_evidence"
