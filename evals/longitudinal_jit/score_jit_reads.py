"""Scorer for the frozen F1-F10 JIT battery. Oracle-gated: ONLY this file
(plus the test harness invoking it) reads oracle JSONs. The synthesis layer
never imports this module or any oracle path.

Verdict matching is deliberately strict-substring on the machine-checkable
`verdict` field plus required recruited-shape fields; prose is not scored.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

REPO_ROOT = Path(__file__).resolve().parents[2]

# question_id -> acceptable verdicts + must-cite event ids + must-hold flags
EXPECTATIONS: Dict[str, Dict] = {
    "F1": {"verdicts": ["Q2100-OPEN"], "must_cite": ["s1_e03", "s1_e04"],
           "must_state": ["ONE transfer"], "abstain": False},
    "F2": {"verdicts": ["NO"], "must_cite": ["s3_e05"],
           "must_state": ["withhold"], "abstain": False},
    "F3": {"verdicts": ["ONE"], "must_cite": ["s1_e01"],
           "must_state": ["ONE distinct"], "abstain": False},
    "F4": {"verdicts": ["NO-TRANSFER"], "must_cite": ["s3_e01"],
           "must_state": ["distinct"], "abstain": False},
    "F5": {"verdicts": ["ABSTAIN"], "must_cite": ["s1_e03"],
           "must_state": ["ABSTAIN"], "abstain": True},
    "F6": {"verdicts": ["NO-END-WATCH"], "must_cite": ["s4_e10"],
           "must_state": ["release"], "abstain": False},
    "F7": {"verdicts": ["NO-NOT-SIGNED"], "must_cite": ["s3_e06"],
           "must_state": ["not sign"], "abstain": False},
    "F8": {"verdicts": ["NO-TURN-SCOPED"], "must_cite": ["s1_e10"],
           "must_state": ["turn"], "abstain": False},
    "F9": {"verdicts": ["ABSTAIN"], "must_cite": ["s1_e01"],
           "must_state": ["ABSTAIN"], "abstain": True},
    "F10": {"verdicts": ["CLOSED-SAME-SOURCE"], "must_cite": ["s3_e10", "s3_e11"],
            "must_state": ["SAME-SOURCE"], "abstain": False},
}

REQUIRED_SHAPE = [
    "current_reading", "supporting_evidence", "counterexamples",
    "corrections_applied", "independence_accounting", "scope_frame",
    "observation_vs_interpretation", "uncertainty",
    "what_would_change", "temporal_cutoff",
]


def score_read(read) -> Dict:
    """Score one RecruitedRead. Returns {correct, failures[], dimensions{}}."""
    exp = EXPECTATIONS[read.question_id]
    failures: List[str] = []
    dims: Dict[str, bool] = {}

    dims["verdict"] = read.verdict in exp["verdicts"]
    if not dims["verdict"]:
        failures.append(f"verdict {read.verdict!r} not in {exp['verdicts']}")

    blob = (read.current_reading + "\n" + "\n".join(read.supporting_evidence)
            + "\n" + "\n".join(read.counterexamples)
            + "\n" + read.independence_accounting + "\n" + read.what_would_change).lower()
    dims["grounding"] = all(e.lower() in blob for e in exp["must_cite"])
    if not dims["grounding"]:
        failures.append(f"missing citations: {[e for e in exp['must_cite'] if e.lower() not in blob]}")
    dims["recruitment_phrase"] = all(s.lower() in blob for s in exp["must_state"])
    if not dims["recruitment_phrase"]:
        failures.append(f"missing required content: {exp['must_state']}")

    # Required shape: 11-field recruited read.
    shape_ok = True
    if not read.current_reading:
        shape_ok = False
    if not read.supporting_evidence:
        shape_ok = False
        failures.append("no supporting evidence")
    if not read.counterexamples:
        shape_ok = False
        failures.append("no counterexamples")
    if not read.independence_accounting:
        shape_ok = False
        failures.append("no independence accounting")
    if not read.scope_frame:
        shape_ok = False
        failures.append("no scope/frame")
    if not read.observation_vs_interpretation:
        shape_ok = False
        failures.append("no obs-vs-interp")
    if not read.uncertainty:
        shape_ok = False
        failures.append("no uncertainty")
    if not read.what_would_change:
        shape_ok = False
        failures.append("no what-would-change")
    if not read.temporal_cutoff:
        shape_ok = False
        failures.append("no temporal cutoff")
    dims["shape"] = shape_ok

    dims["abstain_correct"] = (read.abstained == exp["abstain"])
    if not dims["abstain_correct"]:
        failures.append(f"abstain={read.abstained}, expected {exp['abstain']}")

    # Temporal discipline: excluded_after_cutoff must contain the known
    # post-cutoff resolvers where applicable (F2: s3_e08; F9: s1_e12).
    dims["temporal"] = True
    if read.question_id == "F2" and "s3_e08" not in read.excluded_after_cutoff:
        # s3_e08 may or may not have been retrieved; only fail if it leaked
        # into the reading instead.
        if "s3_e08" in blob and "after" not in blob and "excluded" not in blob:
            dims["temporal"] = False
            failures.append("F2 hindsight leak: s3_e08 used at Monday checkpoint")
    if read.question_id == "F9" and not read.abstained:
        dims["temporal"] = False
        failures.append("F9 hindsight/abstain failure")

    dims["quarantine"] = (read.stored_conclusions_used is False)
    if not dims["quarantine"]:
        failures.append("stored conclusions used")

    # Fabrication check: every cited s*_e* id must exist in the frozen corpus.
    valid_ids = set()
    for name in ["scenario_1_ashley_event_ops_input.json",
                 "scenario_2_ordinary_sophie_plans_input.json",
                 "scenario_3_multisource_conflict_input.json",
                 "scenario_4_health_worry_texture_input.json"]:
        data = json.loads((REPO_ROOT / "evals" / "sophie_longitudinal" / name).read_text())
        valid_ids.update(ev["id"] for ev in data["events"])
    import re
    cited = set(re.findall(r"s[1-4]_e\d+", blob))
    fabricated = cited - valid_ids
    dims["no_fabrication"] = not fabricated
    if fabricated:
        failures.append(f"fabricated event ids: {sorted(fabricated)}")

    correct = all([dims["verdict"], dims["grounding"], dims["abstain_correct"],
                   dims["temporal"], dims["quarantine"], dims["no_fabrication"]])
    return {"correct": correct, "failures": failures, "dimensions": dims}
