"""Pressure dynamics: growth, fatigue, boost, bypass. Pure functions."""
from datetime import datetime, timedelta, timezone

from src.services.pressure_service import adjust_candidate, apply_pressure_dynamics

NOW = datetime(2026, 9, 28, 12, 0)


def test_due_items_untouched():
    for p in (0.6, 0.7, 0.85):
        out = adjust_candidate({"pressure": p, "age_hours": 100.0,
                                "semantic_type": "commitment"}, now=NOW)
        assert out["pressure"] == p


def test_contractual_types_untouched():
    out = adjust_candidate({"pressure": 0.55, "age_hours": 100.0,
                            "semantic_type": "recurring_action"}, now=NOW)
    assert out["pressure"] == 0.55
    out = adjust_candidate({"pressure": 0.3, "age_hours": 100.0,
                            "semantic_type": "deadline"}, now=NOW)
    assert out["pressure"] == 0.3


def test_resolved_never_grows():
    out = adjust_candidate({"pressure": 0.15, "age_hours": 100.0,
                            "semantic_type": "transition",
                            "status": "resolved"}, now=NOW)
    assert out["pressure"] == 0.15


def test_age_growth_bounded():
    fresh = adjust_candidate({"pressure": 0.25, "age_hours": 6.0,
                              "semantic_type": "open_loop"}, now=NOW)
    old = adjust_candidate({"pressure": 0.25, "age_hours": 72.0,
                            "semantic_type": "open_loop"}, now=NOW)
    ancient = adjust_candidate({"pressure": 0.25, "age_hours": 720.0,
                                "semantic_type": "open_loop"}, now=NOW)
    assert fresh["pressure"] == 0.27
    assert old["pressure"] == 0.45
    assert ancient["pressure"] == 0.45  # capped at +0.20
    assert "unresolved" in old["why"]


def test_recent_surfacing_fatigue():
    recent = (NOW - timedelta(hours=5)).isoformat()
    out = adjust_candidate({"pressure": 0.4, "age_hours": 72.0,
                            "semantic_type": "open_loop",
                            "last_surfaced_at": recent,
                            "updated_at": (NOW - timedelta(days=4)).isoformat()},
                           now=NOW)
    # growth would give 0.6; fatigue x0.5 applies
    assert out["pressure"] == 0.3
    assert "24h" in out["why"]


def test_old_surfacing_partial_fatigue():
    old = (NOW - timedelta(hours=50)).isoformat()
    out = adjust_candidate({"pressure": 0.4, "age_hours": 72.0,
                            "semantic_type": "open_loop",
                            "last_surfaced_at": old,
                            "updated_at": (NOW - timedelta(days=4)).isoformat()},
                           now=NOW)
    assert out["pressure"] == round(0.6 * 0.75, 3)


def test_new_evidence_skips_fatigue():
    out = adjust_candidate({"pressure": 0.4, "age_hours": 72.0,
                            "semantic_type": "open_loop",
                            "last_surfaced_at": (NOW - timedelta(hours=5)).isoformat(),
                            "updated_at": NOW.isoformat()}, now=NOW)
    assert out["pressure"] == 0.6
    assert "no fatigue" in out["why"]


def test_repeated_asks_cap():
    out = adjust_candidate({"pressure": 0.5, "age_hours": 200.0,
                            "semantic_type": "open_loop", "ask_count": 4,
                            "last_surfaced_at": (NOW - timedelta(days=10)).isoformat(),
                            "updated_at": (NOW - timedelta(days=10)).isoformat()},
                           now=NOW)
    assert out["pressure"] == 0.35


def test_missing_fields_fail_open():
    out = adjust_candidate({"pressure": 0.25, "semantic_type": "open_loop"}, now=NOW)
    assert out["pressure"] == 0.25
    out = adjust_candidate({"semantic_type": "open_loop"}, now=NOW)
    assert out["pressure"] == 0.0


def test_batch_never_raises():
    out = apply_pressure_dynamics(
        [{"pressure": 0.3, "age_hours": 24.0, "semantic_type": "open_loop"},
         {"pressure": "bogus"}, None, {}], now=NOW)
    assert out[0]["pressure"] == 0.38
    assert out[1]["pressure"] == "bogus"
