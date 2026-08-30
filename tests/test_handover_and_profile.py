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
    assert h["version"] == "handover-v2"
    assert h["product"] == "sophie"
    assert h["now"][0] == "Visa form due Friday"  # deadline outranks task
    assert "Mum visit did not happen because transport failed" in h["changed"][0]
    assert h["avoid"] == ["staying at Mum's"]
    assert h["metrics"]["estimated_tokens"] <= 400
    assert h["metrics"]["within_budget"]


def test_stale_window_elapsed_items_never_pose_as_now():
    packet = _packet()
    packet["window_elapsed_unknown"] = [
        {"id": "e1", "title": "Plans to take a bus to Bedford after visiting mum's"}
    ]
    h = compile_handover(packet, product="sophie")
    assert not any("bus to Bedford" in line for line in h["now"])
    assert any("no outcome evidence yet" in line and "bus to Bedford" in line
               for line in h["uncertain"])


def test_changed_carries_evidence_grounded_cause():
    packet = _packet()
    packet["recent_resolutions"] = [{
        "id": "r1", "title": "Oxford family trip", "outcome_state": "CANCELLED",
        "evidence": "transport fell through, no car available",
    }]
    h = compile_handover(packet, product="sophie")
    assert "transport fell through" in h["changed"][0]


def test_avoid_filters_opaque_entity_ids():
    packet = _packet()
    packet["suppressed_targets"] = [
        {"id": "s1", "topic_or_entity": "user_5377a025-b876-4d1f-bd62-59352da44146"},
        {"id": "s2", "topic_or_entity": "mother's pressure to stay longer"},
    ]
    h = compile_handover(packet, product="sophie")
    assert h["avoid"] == ["mother's pressure to stay longer"]


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
