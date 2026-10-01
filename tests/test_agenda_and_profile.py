"""Agenda: ONE ranked live attention artifact feeding AttentionState's
follow-through ledger (the handover that used to wrap it is retired), plus
product policy over generic Matter kinds."""

from src.services.agenda_service import (
    extract_candidates, fallback_rank,
)
from src.services.product_profile import get_profile


def _packet() -> dict:
    return {
        "hard_deadlines": [{"id": "d1", "title": "Visa form due Friday", "temporal_state": "deadline_approaching"}],
        "active_expectations": [{"id": "e1", "title": "Call the visa office", "temporal_state": "window_open"}],
        "recent_resolutions": [{"id": "r1", "title": "Mum visit did not happen because transport failed"}],
        "suppressed_targets": [{"id": "s1", "topic_or_entity": "staying at Mum's"}],
        "recurring_intentions": [],
        "window_elapsed_unknown": [],
        "window": {
            "daypart": "evening",
            "scopes": {"immediate": [], "today": [], "upcoming": [], "unresolved": [], "review_needed": []},
        },
        "sophie_attention": [{"id": "b1", "content": "Ask how the meeting prep went"}],
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


def test_product_profiles_weight_generic_matter_kinds_without_new_kinds():
    from src.models.matter import MATTER_KINDS
    for name in ("sophie", "bluum", "health", "productivity"):
        profile = get_profile(name)
        # policy only multiplies GENERIC kinds: no product-specific Matter kinds in Cortex
        assert set(profile.matter_kind_weights) <= MATTER_KINDS
        assert not hasattr(profile, "handover_limits")
    assert get_profile("health").matter_kind_weights["routine"] > 1.0
    assert get_profile("productivity").matter_kind_weights["project"] > get_profile("sophie").matter_kind_weights.get("project", 1.0)
    assert get_profile("health").priority("task") < get_profile("sophie").priority("task")
