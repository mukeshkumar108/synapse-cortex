"""Handover v4 + agenda: ONE ranked live attention artifact.
Sections are retired; the agenda is the center of behavioral attention."""

import json

from src.services.agenda_service import (
    extract_candidates, fallback_rank,
)
from src.services.handover_service import compile_handover
from src.services.product_profile import get_profile


def _packet() -> dict:
    return {
        "hard_deadlines": [{"id": "d1", "title": "Visa form due Friday", "temporal_state": "deadline_approaching"}],
        "active_expectations": [{"id": "e1", "title": "Call the visa office", "temporal_state": "window_open"}],
        "recent_resolutions": [{"id": "r1", "title": "Mum visit did not happen because transport failed"}],
        "suppressed_targets": [{"id": "s1", "topic_or_entity": "staying at Mum's"}],
        "recurring_intentions": [],
        "window_elapsed_unknown": [],
        "intelligence_brief": {
            "daypart": "evening",
            "horizons": {"now": [], "today": [], "unresolved": [], "review_needed": []},
            "backstage_attention": [{"id": "b1", "content": "Ask how the meeting prep went"}],
        },
    }


def _agenda():
    return extract_candidates(_packet(), now=__import__("datetime").datetime(2026, 8, 31, 18, 15), timezone_str="Europe/London")


def test_candidates_extract_objectives_deadlines_and_intentions():
    packet = _packet()
    packet["recurring_intentions"] = [{
        "id": "r1", "title": "daily step goal", "semantic_type": "measurable_goal",
        "occurrence_status": "pending", "occurrence_id": "occ-1", "ask_count": 0,
        "target_amount": 10000, "target_unit": "steps",
    }]
    c = extract_candidates(packet, now=__import__("datetime").datetime(2026, 8, 31, 18, 15), timezone_str="Europe/London")
    kinds = {x["item_key"].split(":")[0] for x in c}
    assert {"obj", "exp", "si"} <= kinds
    obj = next(x for x in c if x["item_key"] == "obj:r1")
    assert obj["urgency"] >= 0.6  # evening + unconfirmed
    assert obj["occurrence_id"] == "occ-1"


def test_observed_patterns_and_stale_items_never_become_candidates():
    packet = _packet()
    packet["recurring_intentions"] = [{
        "id": "r2", "title": "daily talk with Ashley",
        "semantic_type": "observed_pattern", "occurrence_status": "pending",
    }]
    packet["active_expectations"] = [{
        "id": "e1", "title": "coffee shop visit days ago",
        "temporal_state": "window_open", "age_hours": 96,
    }]
    c = extract_candidates(packet, now=__import__("datetime").datetime(2026, 8, 31, 18, 15), timezone_str="Europe/London")
    assert not any("Ashley" in x["what"] for x in c)
    assert not any("coffee shop" in x["what"] for x in c)


def test_fallback_rank_orders_by_salience_and_caps_items():
    packet = _packet()
    packet["recurring_intentions"] = [
        {"id": f"r{i}", "title": f"objective {i}", "semantic_type": "recurring_action",
         "occurrence_status": "pending", "ask_count": 0} for i in range(10)
    ]
    c = extract_candidates(packet, now=__import__("datetime").datetime(2026, 8, 31, 18, 15), timezone_str="Europe/London")
    top = fallback_rank(c, daypart="evening")
    assert 0 < len(top) <= 4
    assert top == sorted(top, key=lambda x: -x["score"])


def test_handover_avoids_suppressed_and_ids():
    packet = _packet()
    packet["suppressed_targets"] = [
        {"id": "s1", "topic_or_entity": "user_5377a025-b876-4d1f-bd62-59352da44146"},
        {"id": "s2", "topic_or_entity": "mother's pressure to stay longer"},
    ]
    h = compile_handover(packet, product="sophie", admission={})
    assert h["avoid"] == ["mother's pressure to stay longer"]


def test_handover_patterns_are_context_only():
    packet = _packet()
    packet["recurring_intentions"] = [{
        "id": "r2", "title": "daily talk with Ashley",
        "semantic_type": "observed_pattern", "occurrence_status": "pending",
    }]
    h = compile_handover(packet, product="sophie", admission={})
    assert any("observed pattern" in l for l in h["patterns"])
    assert not any("Ashley" in o["what"] for o in h.get("owed", []))


def test_handover_budget_trims_agenda_last():
    packet = _packet()
    packet["suppressed_targets"] = [
        {"id": f"s{i}", "topic_or_entity": f"topic number {i} that is suppressed"} for i in range(10)
    ]
    admission = {"owed": [{"what": f"item {i}", "followup_state": "outstanding", "pressure": 0.7} for i in range(6)],
                 "optional": [], "scene": {}}
    h = compile_handover(packet, product="sophie", admission=admission)
    assert h["metrics"]["within_budget"]
    assert h["owed"], "owed survives trimming"


def test_handover_is_json_serializable():
    json.dumps(compile_handover(_packet(), product="sophie", admission={}))


def test_product_profiles_change_handover_limits():
    assert get_profile("sophie").handover_limits["agenda"] >= 2  # agenda cap reused for owed
    assert get_profile("health").priority("task") < get_profile("sophie").priority("task")
