"""A confirmed plan is still a plan; deictic recency words find what happened
in the window they name (the 2026-10-02 production continuity failure)."""
from datetime import datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

from src.services.matter_service import PrimitiveRef, derive_status, CONVERSATIONAL_CLOSURE_QUIET

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


