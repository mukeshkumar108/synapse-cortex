# Lane A (Companion Projection v1) canonical test.
#
# Offline, deterministic, no DB, no network, no models. Runs the frozen
# 12-day eval corpus (evals/companion_projection/corpus.json) through the
# deterministic builder and asserts the pre-registered bar from
# reports/companion_projection_lane_a_2026-09-28.md:
# full required-context recall, zero stale/closed leakage, full boundary
# preservation, zero hard/soft violations, full horizon correctness, clean
# relational/operational separation, complete provenance, zero behavioural
# commands, mundane caps, and baseline contrast.

import json
import os
import sys

HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "..", "evals", "companion_projection")
sys.path.insert(0, HERE)

from builder import build_projection  # noqa: E402
from score import (baseline_projection, load_day_events, score_baseline,  # noqa: E402
                   score_day)


def _run_all():
    corpus = json.load(open(os.path.join(HERE, "corpus.json")))
    out = []
    for day in corpus["days"]:
        events = load_day_events(day, corpus.get("fixture_version"))
        proj = build_projection(events, day["now"], day["session_id"],
                                corpus.get("fixture_version", "unknown"))
        res = score_day(day, proj)
        base = score_baseline(day, baseline_projection(events, day["now"]))
        out.append((day, res, base))
    return out


def test_projection_lane_a_bar():
    ran = _run_all()
    assert len(ran) == 12
    for day, r, _ in ran:
        assert r["recall"]["found"] == r["recall"]["total"], day["id"]
        assert r["stale"]["count"] == 0, (day["id"], r["stale"])
        assert r["boundary"]["found"] == r["boundary"]["total"], day["id"]
        assert r["hardsoft"]["violations"] == 0, (day["id"], r["hardsoft"])
        assert r["horizon"]["found"] == r["horizon"]["total"], day["id"]
        assert r["separation"]["relational_miss"] == [], day["id"]
        assert r["separation"]["op_violations"] == [], (day["id"], r["separation"])
        assert r["provenance"]["items_missing_sources"] == [], day["id"]
        assert r["provenance"]["meta_ok"] is True, day["id"]
        assert r["commands"]["passed"] is True, (day["id"], r["commands"])
        if "caps" in r:
            caps = day["caps"]
            assert r["caps"]["unresolved"] <= caps["max_unresolved"], day["id"]
            assert r["caps"]["opportunities"] <= caps["max_opportunities"], day["id"]
            assert r["caps"]["hard"] <= caps["max_hard"], day["id"]
            assert r["caps"]["relational"] <= caps["max_relational"], day["id"]


def test_projection_lane_a_baseline_contrast():
    # The naive flat imperative packet must fail exactly where the
    # projection earns its keep: hard constraints, provenance, commands.
    ran = _run_all()
    hard_required = sum(b["hard_total"] for _, _, b in ran)
    hard_got = sum(b["hard_boundary_items"] for _, _, b in ran)
    assert hard_required > 0
    assert hard_got == 0
    assert all(b["provenance_items"] == 0 for _, _, b in ran)
    assert all(b["command_phrases"] > 0 for _, _, b in ran)
    assert all(b["sections"] == 1 for _, _, b in ran)
