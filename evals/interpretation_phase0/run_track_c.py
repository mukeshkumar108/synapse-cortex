"""Validate and summarise Track C (Bloom/wellbeing) interpretation fixtures.

Offline only. Reuses the Phase 0 packet-shape validator; does not modify or
depend on cases.json (the frozen Phase 0 baseline).
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def _load_validator():
    spec = importlib.util.spec_from_file_location("phase0_run", ROOT / "run.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def main() -> None:
    validator = _load_validator()
    packet = json.loads((ROOT / "track_c_bloom_cases.json").read_text())
    cases = packet["cases"]
    for case in cases:
        validator.validate_case(case)

    changed = sum(c["current_decision"] != c["sidecar_decision"] for c in cases)
    print(f"validated={len(cases)}")
    print(f"sidecar_changes_bounded_decision={changed}/{len(cases)}")
    for case in cases:
        marker = "CHANGED" if case["current_decision"] != case["sidecar_decision"] else "SAME"
        n_hyp = len(case["sidecar"]["hypotheses"])
        print(f"{marker:7} [{case['control_type']:26}] {case['id']}: {n_hyp} hypotheses -> {case['sidecar_decision']}")


if __name__ == "__main__":
    main()
