#!/usr/bin/env python3
"""Small-model bakeoff for the NARROW real-time lane (frozen contract).

Baseline (prod): deepseek/deepseek-v4-flash. Candidates: cheap fast models.
Every model runs through the SAME narrow prompt + the SAME deterministic
validator. No per-model special casing (invariant: model proposes, code commits).

Scored per model:
  - schema_gate   : validator pass rate WITHOUT fail-safe coercion
                    (parseable JSON, valid decision/kind, verbatim evidence,
                     grounded temporal phrase, target present for transitions)
  - operation_acc : decision (+kind for create) equals expected
  - none_precision: correct `none` on non-operational turns
  - target_acc    : correct target object on transition decisions
  - paraphrase_ok : same decision on paraphrased variants
  - p50/p95 latency, error rate (model call failures)

Usage: python3 narrow_model_bakeoff.py [--models m1,m2,...] [--repeat N]
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.services.turn_extractor import LLMExtractorProvider  # noqa: E402
from src.services.narrow_realtime import NarrowRealtimeExtractor  # noqa: E402

BASELINE = "deepseek/deepseek-v4-flash"
DEFAULT_CANDIDATES = [
    BASELINE,
    "openai/gpt-4o-mini",
    "cohere/command-r7b-12-2024",
    "ibm-granite/granite-4.1-8b",
    "ibm-granite/granite-4.0-h-micro",
]

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=timezone.utc)
TZ = "Europe/London"

OXFORD_PRIOR = {"objectives": [
    {"title": "Trip to Oxford for Raksha Bandhan (Sunday)", "target_key": "oxford_raksha_bandhan",
     "canonical_title": "Trip to Oxford for Raksha Bandhan", "expectation_type": "planned_event", "status": "active"},
    {"title": "Visit mum tonight (Bedford)", "target_key": "mum_visit_bedford",
     "canonical_title": "Visit mum tonight", "expectation_type": "planned_event", "status": "active"},
]}

# Paraphrase invariance probes: same operational meaning, different wording.
PARAPHRASE_PAIRS = [
    {"pair": "reminder", "expected": ("create", "reminder"), "variants": [
        {"text": "haha ok. i was just standing outside watching the stars. going to bed now. tomorrow i want you to encourage and remind me to go out for a walk during the day not just an early evening walk!! please"},
        {"text": "heading up to bed! tomorrow can you nudge me to get out for a walk in the daytime, not just the evening one please"}]},
    {"pair": "event", "expected": ("create", "event"), "variants": [
        {"text": "So Sunday morning we're traveling early. We're going to Oxford to see my uncle and my cousins. It's an event called Raksha Bandhan."},
        {"text": "we head off to Oxford first thing Sunday morning for Raksha Bandhan with my uncle and cousins"}]},
    {"pair": "none-narration", "expected": ("none", None), "variants": [
        {"text": "Same old loop, I'm on it right now. Burwell Fen is basically my everyday walk and it takes some variance. it's beautiful, it's not hot, it's not cold, it's just lovely"},
        {"text": "the moon looks unreal tonight, huge and white over the trees"}]},
    {"pair": "cancel", "expected": ("cancel", None), "prior_state": OXFORD_PRIOR, "variants": [
        {"text": "Yeah, I've got no way of getting there. So unfortunately, I have to give it a miss. Still don't have a car at the moment."},
        {"text": "not going to make it to Oxford after all, there's no way for me to get there"}]},
]



def score_model(model, cases, repeat):
    provider = LLMExtractorProvider(model=model, models=[model])
    extractor = NarrowRealtimeExtractor(provider=provider)
    rows = []
    for rep in range(repeat):
        for case in cases:
            text = case["text"]
            prior = case.get("prior_state")
            t0 = time.perf_counter()
            nd = extractor.classify(text, peer_id="user", prior_state=prior,
                                    now=NOW, timezone_str=TZ)
            latency = time.perf_counter() - t0
            exp_dec, exp_kind = expected_for(case)
            call_failed = any(n.startswith("model_call_failed") for n in nd.validation_notes)
            schema_ok = nd.valid and not call_failed
            got_dec = nd.decision if (nd.valid and not call_failed) else None
            got_kind = nd.kind if got_dec == "create" else None
            op_ok = (got_dec == exp_dec) and (exp_kind is None or got_kind == exp_kind)
            target_ok = None
            if exp_dec in ("progress", "complete", "cancel", "reschedule", "correct") and got_dec == exp_dec:
                want = case.get("expected_target_keys") or [
                    o.get("target_key") for o in (case.get("prior_state", {}).get("objectives") or [])
                ]
                got_t = str(nd.target_key or nd.canonical_title or "")
                target_ok = bool(got_t) and any(w and (w in got_t or got_t in w) for w in want)
            rows.append({"case": case["id"], "repeat": rep, "latency": latency,
                         "schema_ok": schema_ok, "call_failed": call_failed,
                         "got": got_dec, "got_kind": got_kind, "expected": exp_dec,
                         "op_ok": op_ok, "target_ok": target_ok, "notes": nd.validation_notes})
    lat = sorted(r["latency"] for r in rows if not r["call_failed"])
    def pct(p):
        if not lat:
            return None
        return round(lat[min(len(lat) - 1, max(0, round(p / 100 * len(lat)) - 1))], 2)
    n = len(rows)
    summary = {
        "model": model, "n": n,
        "schema_gate": round(sum(1 for r in rows if r["schema_ok"]) / n, 3),
        "error_rate": round(sum(1 for r in rows if r["call_failed"]) / n, 3),
        "operation_acc": round(sum(1 for r in rows if r["op_ok"]) / n, 3),
        "none_precision": round(sum(1 for r in rows if r["expected"] == "none" and r["got"] == "none")
                                / max(1, sum(1 for r in rows if r["expected"] == "none")), 3),
        "target_acc": _ratio([r for r in rows if r["target_ok"] is not None], "target_ok"),
        "latency_p50": pct(50), "latency_p95": pct(95),
    }
    return summary, rows


def _ratio(subset, key):
    if not subset:
        return None
    return round(sum(1 for r in subset if r[key]) / len(subset), 3)

def load_cases(path):
    with open(path) as fh:
        return json.load(fh)["cases"]


def expected_for(case):
    return (case.get("expected_narrow", "none"), case.get("expected_kind"))


def score_paraphrase(model, repeat=1):
    """Invariance: both variants of each pair must yield the same valid decision."""
    provider = LLMExtractorProvider(model=model, models=[model])
    extractor = NarrowRealtimeExtractor(provider=provider)
    ok = 0
    total = 0
    details = []
    for rep in range(repeat):
        for pair in PARAPHRASE_PAIRS:
            outs = []
            for var in pair["variants"]:
                nd = extractor.classify(var["text"], peer_id="user",
                                        prior_state=pair.get("prior_state"),
                                        now=NOW, timezone_str=TZ)
                failed = any(n.startswith("model_call_failed") for n in nd.validation_notes)
                outs.append(None if failed else (nd.decision, nd.kind if nd.valid else None))
            total += 1
            # Compare DECISIONS only; kind is contract-relevant for create.
            # (Models often fill kind on transitions with non-contract values.)
            def norm(o):
                if o is None:
                    return None
                return (o[0], o[1] if o[0] == "create" else None)
            inv = norm(outs[0]) is not None and norm(outs[0]) == norm(outs[1]) and norm(outs[0]) == pair["expected"]
            ok += 1 if inv else 0
            details.append({"pair": pair["pair"], "outs": outs, "expected": pair["expected"], "invariant": inv})
    return {"model": model, "paraphrase_invariance": round(ok / total, 3), "details": details}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=None, help="comma-separated override")
    ap.add_argument("--cases", default=os.path.join(os.path.dirname(__file__), "narrow_contract_cases.json"))
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--skip-paraphrase", action="store_true")
    args = ap.parse_args()

    models = args.models.split(",") if args.models else DEFAULT_CANDIDATES
    cases = load_cases(args.cases)

    summaries, all_rows = [], []
    for m in models:
        print(f"=== scoring {m} ...", flush=True)
        try:
            s, rows = score_model(m, cases, args.repeat)
            summaries.append(s)
            all_rows.extend(rows)
            print(json.dumps(s), flush=True)
        except Exception as e:
            print(f"  FAILED: {e}", flush=True)
            summaries.append({"model": m, "error": str(e)[:300]})

    para = []
    if not args.skip_paraphrase:
        for m in models:
            print(f"=== paraphrase {m} ...", flush=True)
            try:
                s = score_paraphrase(m)
                para.append(s)
                print(f"  invariance: {s['paraphrase_invariance']}", flush=True)
            except Exception as e:
                print(f"  FAILED: {e}", flush=True)

    os.makedirs("evals/results", exist_ok=True)
    out = "evals/results/narrow_model_bakeoff.json"
    with open(out, "w") as fh:
        json.dump({"generated_at": datetime.now(timezone.utc).isoformat(),
                   "summaries": summaries, "paraphrase": para, "rows": all_rows},
                  fh, indent=2, default=str)
    print("\n=== LEADERBOARD (schema_gate=1.0 required, then operation_acc, then latency) ===")
    for s in sorted(summaries, key=lambda x: (x.get("schema_gate", 0) < 1.0, -x.get("operation_acc", 0), x.get("latency_p50") or 9e9)):
        print(json.dumps(s))
    print(f"written: {out}")


if __name__ == "__main__":
    main()

def expected_for(case):
    return (case.get("expected_narrow", "none"), case.get("expected_kind"))
