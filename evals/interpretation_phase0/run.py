"""Validate and compare Phase-0 interpretation packets. Offline only."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ALLOWED_RELATIONS = {"supports", "qualifies", "contradicts"}
ALLOWED_CONFIDENCE = {"low", "medium", "high"}
ALLOWED_STATES = {"live", "contested", "superseded"}
ALLOWED_PERSISTENCE = {"turn", "session", "until_condition", "durable"}


def validate_case(case: dict) -> None:
    assert case["provenance"]["kind"] in {"historical", "synthetic"}
    evidence_ids = {item["id"] for item in case["evidence"]}
    assert len(evidence_ids) == len(case["evidence"])
    assert case["current_representation"]
    assert case["decision_task"]
    assert case["current_decision"] and case["sidecar_decision"]
    assert case["expected_decision"] == case["sidecar_decision"]

    matter = case["sidecar"]["matter"]
    assert matter["identity"] and matter["scope"]
    assert set(matter["evidence_refs"]) <= evidence_ids

    hypothesis_ids: set[str] = set()
    for hypothesis in case["sidecar"]["hypotheses"]:
        assert hypothesis["id"] not in hypothesis_ids
        hypothesis_ids.add(hypothesis["id"])
        assert hypothesis["scope"] in {case["product"], "shared"}
        assert hypothesis["confidence"] in ALLOWED_CONFIDENCE
        assert hypothesis["confidence_basis"]
        assert hypothesis["state"] in ALLOWED_STATES
        assert hypothesis["persistence"] in ALLOWED_PERSISTENCE
        assert hypothesis["recheck_when"]
        relations = hypothesis["evidence"]
        assert set(relations) == ALLOWED_RELATIONS
        refs = [ref for values in relations.values() for ref in values]
        assert set(refs) <= evidence_ids
        assert len(refs) == len(set(refs)), "one item cannot play two relations"
        implication = hypothesis["implication"]
        assert implication["decision"] and implication["guardrail"]


def main() -> None:
    packet = json.loads((ROOT / "cases.json").read_text())
    cases = packet["cases"]
    for case in cases:
        validate_case(case)

    improved = sum(c["current_decision"] != c["expected_decision"] for c in cases)
    print(f"validated={len(cases)}")
    print(f"sidecar_changes_bounded_decision={improved}/{len(cases)}")
    for case in cases:
        marker = "CHANGED" if case["current_decision"] != case["sidecar_decision"] else "SAME"
        print(f"{marker:7} {case['id']}: {case['sidecar_decision']}")


if __name__ == "__main__":
    main()

