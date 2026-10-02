"""A confirmed plan is still a plan; deictic recency words find what happened
in the window they name (the 2026-10-02 production continuity failure)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from src.services.matter_service import PrimitiveRef, derive_status, CONVERSATIONAL_CLOSURE_QUIET
from src.services.turn_working_set import TurnWorkingSetService, recency_window

NOW = datetime(2026, 10, 2, 13, 37)


def _loop(evidence, *, direction="user_to_system", terminal=True, age=timedelta(hours=1)):
    at = NOW - age
    row = SimpleNamespace(resolution_evidence=evidence, direction=direction, title="going into Cambridge")
    return PrimitiveRef("open_loop", uuid4(), row, "going into Cambridge", "", "open_loop",
                        live=not terminal, terminal=terminal, touched_at=at, created_at=at)


def _matter(last_touched):
    return SimpleNamespace(status="active", resolved_at=None, last_touched=last_touched)


def test_confirming_a_plan_does_not_resolve_the_matter():
    loop = _loop("semantic_proposal:abc#confidence:0.90")
    status, resolved_at = derive_status(_matter(loop.touched_at), [loop], NOW)
    assert status == "active" and resolved_at is None


def test_answered_thread_goes_dormant_not_resolved_after_the_quiet_window():
    loop = _loop("answered_in_turn:xyz", age=CONVERSATIONAL_CLOSURE_QUIET + timedelta(hours=1))
    status, _ = derive_status(_matter(loop.touched_at), [loop], NOW)
    assert status == "dormant"


def test_outcome_evidence_still_resolves():
    loop = _loop("resolved:completion:msg#candidate:k")
    status, resolved_at = derive_status(_matter(loop.touched_at), [loop], NOW)
    assert status == "resolved" and resolved_at is not None


def test_system_directed_loop_closure_is_not_treated_as_conversational():
    loop = _loop("answered_in_turn:xyz", direction="system_to_user")
    assert derive_status(_matter(loop.touched_at), [loop], NOW)[0] == "resolved"


def test_recency_window_is_the_user_day_and_morning_is_bounded():
    now = datetime(2026, 10, 2, 9, 43)  # 10:43 BST
    start, end = recency_window("don't you remember our call earlier?", now, "Europe/London")
    assert start == datetime(2026, 10, 2, 4, 0) and end == now
    assert recency_window("hey", now, "Europe/London") is None
    s2, e2 = recency_window("what did I say this morning", datetime(2026, 10, 2, 15, 0), "Europe/London")
    assert e2 == datetime(2026, 10, 2, 11, 0)  # noon BST in naive UTC


def test_earlier_finds_todays_plan_not_yesterdays_call():
    world = {"matters": {"active": [], "recently_resolved": []},
             "recent": {"today": {"occupied": [
                 {"matter_id": "plan", "title": "I'm going into Cambridge today and meeting a friend for lunch",
                  "touches": 1, "last_touched": "2026-10-02T08:10:27", "status": "active"}]}}}
    packet = {"window": {"scopes": {}}, "open_loops": [
        {"id": "old", "title": "Yeah we had a call earlier, now voice", "summary": "call earlier",
         "updated_at": "2026-10-01T21:16:53"}]}
    out = TurnWorkingSetService().compile_turn_working_set(
        packet, world_model=world, turn_text="don't you remember our call earlier?",
        now=datetime(2026, 10, 2, 9, 43, 51), timezone_name="Europe/London")
    warm = out["levels"]["warm"]
    assert warm[0]["matter_id"] == "plan"
    assert "Cambridge" in warm[0]["what"]
    old = [w for w in warm if w["kind"] == "open_loop"]
    assert old and old[0]["relevance"] < warm[0]["relevance"]
