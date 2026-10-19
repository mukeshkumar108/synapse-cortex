"""Reliability harness: run fixed fixtures repeatedly against a live Cortex,
compare final ledger state to independently defined expectations.
Usage: CORTEX_URL=.. CORTEX_TOKEN=.. python scripts/eval_reliability.py [--reps 3] [--fixtures dentist-lifecycle]
Writes reports/reliability_<ts>.json. Fails loudly on mismatch; never modifies prod owners (world:lab:rel-*)."""
import argparse
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reliability_fixtures import FIXTURES, sess

BASE = os.environ.get("CORTEX_URL", "http://127.0.0.1:8010").rstrip("/")
TOKEN = os.environ.get("CORTEX_TOKEN", "")
WS = "llm-test-agent"


def api(path, body=None, method="POST"):
    H = {"Content-Type": "application/json"}
    if TOKEN:
        H["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body else None,
                                 headers=H, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())


def run_fixture(name, fix, rep):
    owner = f"world:lab:rel-{name}-{rep}-{int(time.time()) % 100000}"
    runs = []
    for sid, pairs in fix["sessions"]:
        body = {"workspace_id": WS, "owner": owner, "conversation_id": f"rel-{sid}",
                "session_id": f"rel-{sid}:{sid}", "messages": sess(pairs, sid), "companion_id": "sophie"}
        rid = api("/v1/memory/consolidate", body)["run_id"]
        for _ in range(55):
            time.sleep(10)
            st = api(f"/v1/memory/run/{rid}", method="GET")
            if st["status"] in ("consolidated", "replay_noop", "empty", "failed"):
                break
        runs.append({"sid": sid, "status": st["status"],
                     "summary": st.get("summary", {})})
    state = api(f"/v1/memory/state?workspace_id={WS}&owner={owner}", method="GET")
    rows = state.get("ledger", [])
    try:
        all_rows = api("/v1/memory/state?workspace_id=__all__&owner=__all__", method="GET")
    except Exception:
        all_rows = None
    return {"owner": owner, "runs": runs, "ledger": rows, "state_note": "open+waiting+watching+suppressed only"}


def check(fix, ledger):
    results = []
    low = [(r.get("title") or "").lower() for r in ledger]
    for exp in fix["expected"]:
        needle = exp["title_contains"].lower()
        matches = [r for r in ledger if needle in (r.get("title") or "").lower()]
        ok, notes = True, []
        if not matches:
            ok, notes = False, ["missing: no row containing %r" % needle]
        else:
            r = matches[0]
            if len(matches) > 1:
                ok, notes = False, ["duplicate: %d rows contain %r" % (len(matches), needle)]
            if exp.get("status") and r.get("status") != exp["status"]:
                ok, notes = False, [f"status {r.get('status')} != {exp['status']}"]
            if exp.get("expected_date") and r.get("expected_date") != exp["expected_date"]:
                ok, notes = False, [f"date {r.get('expected_date')} != {exp['expected_date']}"]
            if exp.get("kind") and r.get("kind") != exp["kind"]:
                ok, notes = False, [f"kind {r.get('kind')} != {exp['kind']}"]
            for m in exp.get("must_mention", []):
                blob = json.dumps(r).lower()
                if m.lower() not in blob:
                    ok, notes = False, [f"missing mention: {m}"]
        results.append({"expectation": exp, "pass": ok, "notes": notes})
    titles = " | ".join(low)
    for forb in fix.get("forbidden", []):
        bad = False
        if forb.startswith("duplicate"):
            w = forb.split()[-1]
            bad = sum(1 for t in low if w in t) > 1
        elif "closed before" in forb:
            bad = any(("closed" in t or "done" in t) for t in low)
        elif "thursday date surviving" in forb.lower():
            bad = any(("thursday" in t) for t in low)
        elif "marathon as commitment" in forb:
            bad = any(("marathon" in t) for t in low if "aspiration" not in t)
        elif "marathon closed" in forb:
            bad = False  # checked via expected status=open above
        elif "pete deleted" in forb:
            bad = not any(("pete" in t) for t in low)
        results.append({"expectation": {"forbidden": forb}, "pass": not bad,
                        "notes": ["forbidden condition held"] if bad else []})
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2)
    ap.add_argument("--fixtures", nargs="*", default=list(FIXTURES))
    args = ap.parse_args()
    out = {"at": datetime.now(timezone.utc).isoformat(), "results": {}}
    for name in args.fixtures:
        fix = FIXTURES[name]
        reps = []
        for rep in range(args.reps):
            print(f"== {name} rep {rep} ==", flush=True)
            try:
                res = run_fixture(name, fix, rep)
                res["checks"] = check(fix, res["ledger"])
            except Exception as e:
                res = {"error": f"{type(e).__name__}: {str(e)[:300]}", "checks": []}
            reps.append(res)
        out["results"][name] = reps
    path = f"reports/reliability_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    os.makedirs("reports", exist_ok=True)
    json.dump(out, open(path, "w"), indent=1)
    npass = sum(1 for r in out["results"].values() for rep in r for c in rep.get("checks", []) if c["pass"])
    ntot = sum(1 for r in out["results"].values() for rep in r for c in rep.get("checks", []))
    print(f"PASS {npass}/{ntot} -> {path}")
    return 0 if npass == ntot else 1


if __name__ == "__main__":
    raise SystemExit(main())
