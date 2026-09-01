#!/usr/bin/env python3
"""Narrow real-time contract shadow comparison (Item 2).

Runs the CURRENT per-turn extractor and the NARROW real-time classifier
side-by-side over representative real production turns, then reports:

  - per case: current operational_kinds vs narrow (decision, kind, valid, notes)
  - agreement class: MATCH / NARROW_NARROWER (current emits non-operational
    discovery the narrow contract defers to Lane 2) / DISAGREE (both emit
    different operational actions) / NARROW_MISSED (narrow says none where the
    current path found a genuine operational action)
  - writes evals/results/narrow_contract_compare.json

Usage:
  python3 evals/narrow_contract_compare.py [--cases FILE] [--limit N] [--id CASE_ID]

Requires model credentials in env (OPENAI_API_KEY / OPENROUTER_API_KEY) and
optionally SYNAPSE_EXTRACTOR_MODEL. Read-only: never mutates any state.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.turn_extractor import TurnExtractor  # noqa: E402
from src.services.narrow_realtime import NarrowRealtimeExtractor  # noqa: E402

VALID_DECISIONS = {"none", "create", "progress", "complete", "cancel",
                   "reschedule", "correct", "suppress", "reopen"}


def classify_agreement(current_kinds, narrow_dec):
    """Agreement taxonomy for the capability-delta report."""
    narrow_op = narrow_dec.decision if narrow_dec.valid else "none"
    current_op = {k for k in current_kinds if k not in (None, "semantic_only")}
    if narrow_op == "none":
        if not current_op:
            return "MATCH"
        # Current found *something*; was it genuinely operational (would mutate
        # state) or discovery/memory work the narrow contract defers to Lane 2?
        discovery = {"durable_objective", "recurring_intention", "open_loop",
                     "commitment_candidate", "event"}
        if current_op <= discovery:
            return "NARROW_DEFERS_TO_LANE2"
        return "NARROW_MISSED"
    if current_op & {"completion", "cancellation", "progress", "suppression",
                     "expectation", "event", "commitment_candidate"}:
        return "MATCH" if narrow_op != "none" else "DISAGREE"
    if not current_op:
        return "NARROW_ONLY"
    return "DISAGREE"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cases", default=os.path.join(os.path.dirname(__file__), "narrow_contract_cases.json"))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--id", dest="case_id", default=None)
    args = parser.parse_args()

    with open(args.cases) as fh:
        doc = json.load(fh)
    cases = doc["cases"]
    if args.case_id:
        cases = [c for c in cases if c["id"] == args.case_id]
    if args.limit:
        cases = cases[: args.limit]

    current = TurnExtractor()
    narrow = NarrowRealtimeExtractor()
    now = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)

    results = []
    for case in cases:
        text = case["text"]
        prior = case.get("prior_state")
        cur_candidates = current.extract_candidates(text, peer_id="user", prior_state=prior)
        cur_kinds = [c.operational_kind for c in cur_candidates]
        cur_failure = getattr(current.provider, "last_failure", None)
        cur_detail = [
            {
                "kind": c.operational_kind,
                "title": (c.canonical_title or c.observation or "")[:60],
                "temporal_phrase": c.temporal_phrase,
                "reminder_request": c.reminder_request,
                "evidence_class": c.evidence_class,
            }
            for c in cur_candidates
        ]
        nd = narrow.classify(text, peer_id="user", prior_state=prior, now=now, timezone_str="Europe/London")
        agreement = classify_agreement(cur_kinds, nd)
        expected = case.get("expected_narrow", "none")
        ok = (nd.decision if nd.valid else "none") == expected
        if expected in ("create",) and nd.valid and nd.decision == "create":
            ok = nd.kind == case.get("expected_kind", nd.kind)
        rec = {
            "id": case["id"],
            "provenance": case.get("provenance"),
            "current_kinds": cur_kinds,
            "current_detail": cur_detail,
            "current_failure": str(cur_failure)[:200] if cur_failure else None,
            "narrow": nd.summary(),
            "expected_narrow": expected,
            "expected_match": ok,
            "agreement_class": agreement,
        }
        results.append(rec)
        print(f"--- {case['id']} [{agreement}] expected={expected} "
              f"narrow={nd.decision}{('/' + str(nd.kind)) if nd.kind else ''} "
              f"valid={nd.valid} match={ok}")
        print(f"    current: {cur_detail}")
        if nd.validation_notes:
            print(f"    narrow notes: {nd.validation_notes}")
        if nd.decision != "none" and nd.valid:
            print(f"    narrow: title={nd.title!r} temporal={nd.temporal_phrase!r} "
                  f"target={nd.target_key or nd.canonical_title!r}")

    os.makedirs("evals/results", exist_ok=True)
    out = "evals/results/narrow_contract_compare.json"
    with open(out, "w") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "model": os.getenv("SYNAPSE_EXTRACTOR_MODEL", "gpt-4o-mini"),
                   "results": results}, fh, indent=2, default=str)

    from collections import Counter
    print("\n=== AGGREGATE ===")
    print("agreement classes:", dict(Counter(r["agreement_class"] for r in results)))
    print("expected match:", sum(1 for r in results if r["expected_match"]), "/", len(results))
    print(f"written: {out}")


if __name__ == "__main__":
    main()
