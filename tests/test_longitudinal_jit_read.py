"""Regression: owned JIT longitudinal read path over frozen F1-F10.

Blindness: tests load ONLY F_BATTERY.json (inputs) + synthesis. Oracle
expectations live in evals/longitudinal_jit/score_jit_reads.py (gated
scorer); fixture oracle JSONs are never opened here.

Freeze: battery config sha is recorded; any change to battery, synthesis,
or scorer after the scored run must re-run and re-record.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from evals.longitudinal_jit.score_jit_reads import EXPECTATIONS, score_read
from src.longitudinal_read import retrieval
from src.longitudinal_read.interface import ask_longitudinal
from src.longitudinal_read.query_discipline import QueryRejected

REPO_ROOT = Path(__file__).resolve().parents[1]
BATTERY = REPO_ROOT / "evals" / "longitudinal_jit" / "F_BATTERY.json"


def _battery():
    return json.loads(BATTERY.read_text())["questions"]


def test_battery_config_frozen_shape():
    qs = _battery()
    assert [q["id"] for q in qs] == [f"F{i}" for i in range(1, 11)]
    for q in qs:
        assert q["question"] and q["scope"] and q["temporal_cutoff"]
        assert q["matter_refs"] and q["need"]


def test_open_ended_scans_refused():
    import pytest
    for bad in ["analyse the user", "what matters in their life?",
                "find important patterns", "what should the companion know?"]:
        with pytest.raises(QueryRejected):
            ask_longitudinal(question=bad, scope="matter:x",
                             temporal_cutoff="2026-10-01T00:00:00+01:00",
                             matter_refs=["x"], need="test")
    with pytest.raises(QueryRejected):  # profile API shape refused
        ask_longitudinal(question="tell me about the user", scope="user",
                         temporal_cutoff="2026-10-01T00:00:00+01:00",
                         matter_refs=[], need="test")


def test_stored_conclusions_quarantined():
    assert retrieval.CONCLUSIONS_TOUCHED is False
    import inspect
    import src.longitudinal_read.retrieval as r
    # Scored path is pure-local: no HTTP client usage at all.
    assert "httpx" not in inspect.getsource(r.fixture_search)
    assert "http" not in inspect.getsource(r.fixture_search).lower()
    # The only network adapter (live, off the scored path) posts to message
    # search; no request-building line may address the conclusions endpoints.
    live_src = inspect.getsource(r.honcho_live_search)
    assert "/search" in live_src
    request_lines = [ln for ln in live_src.splitlines()
                     if any(k in ln for k in (".post", ".get", "_request", "base_url"))]
    assert request_lines, "live adapter must build its request visibly"
    assert all("conclusions" not in ln for ln in request_lines)


def test_f1_f10_regression():
    raw_results = {}
    for q in _battery():
        read = ask_longitudinal(
            question=q["question"], scope=q["scope"],
            temporal_cutoff=q["temporal_cutoff"],
            matter_refs=q["matter_refs"], need=q["need"],
            question_id=q["id"],
        )
        assert read.stored_conclusions_used is False
        assert read.temporal_cutoff == q["temporal_cutoff"]
        scored = score_read(read)
        raw_results[q["id"]] = {
            "verdict": read.verdict,
            "correct": scored["correct"],
            "failures": scored["failures"],
            "compact": read.compact(),
        }
    out_dir = REPO_ROOT / "evals" / "longitudinal_jit" / "raw_outputs"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "jit_reads_f1_f10.json").write_text(json.dumps(raw_results, indent=2))
    n_correct = sum(1 for v in raw_results.values() if v["correct"])
    assert n_correct >= 7, f"only {n_correct}/10 correct: {raw_results}"
    # Zero-tolerance gates: corrections, abstains, leaks, fabrication.
    for qid in ["F2", "F5", "F9"]:
        assert raw_results[qid]["correct"], f"{qid} critical failure: {raw_results[qid]}"
    assert all(v["correct"] for v in raw_results.values()), f"failures: {raw_results}"
