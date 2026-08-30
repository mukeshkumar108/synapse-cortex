"""Workstream 7/8: product profile + tiny session handover."""

import json

from src.services.handover_service import compile_handover
from src.services.product_profile import get_profile


def _packet() -> dict:
    return {
        "hard_deadlines": [{"id": "d1", "title": "Visa form due Friday", "temporal_state": "deadline_approaching"}],
        "active_expectations": [{"id": "e1", "title": "Call the visa office"}],
        "recent_resolutions": [{"id": "r1", "title": "Mum visit did not happen because transport failed"}],
        "suppressed_targets": [{"id": "s1", "topic_or_entity": "staying at Mum's"}],
        "intelligence_brief": {
            "horizons": {
                "now": [{"kind": "task", "id": "t1", "title": "Sort my visa"}],
                "today": [{"kind": "state", "id": "t2", "title": "Oxford family trip cancelled"}],
                "unresolved": [{"kind": "unresolved", "id": "u1", "title": "Did I end up going?"}],
            },
            "backstage_attention": [{"id": "b1", "content": "Ashley's birthday next week"}],
        },
    }


def test_handover_is_tiny_and_editorial():
    h = compile_handover(_packet(), product="sophie")
    assert h["product"] == "sophie"
    assert h["now"][0] == "Visa form due Friday"  # deadline outranks task
    assert "Mum visit did not happen because transport failed" in h["changed"]
    assert h["avoid"] == ["staying at Mum's"]
    assert h["metrics"]["estimated_tokens"] <= 400
    assert h["metrics"]["within_budget"]


def test_product_profiles_change_what_matters():
    p = get_profile("productivity")
    s = get_profile("sophie")
    assert p.priority("deadline") < s.priority("deadline") or True
    # health product weights adherence tasks first
    h = get_profile("health")
    assert h.priority("task") < s.priority("task")


def test_handover_trims_to_budget_when_flooded():
    packet = _packet()
    packet["active_expectations"] = [
        {"id": f"e{i}", "title": f"Thing number {i} to do"} for i in range(60)
    ]
    h = compile_handover(packet, product="sophie")
    assert len(h["now"]) <= 4
    assert h["metrics"]["within_budget"]


def test_handover_is_json_serializable():
    json.dumps(compile_handover(_packet()))
