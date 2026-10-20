"""Reliability harness: run fixed fixtures repeatedly against a live Cortex and
compare the ledger after EVERY sitting to independently defined expectations
about the person's affairs (see reliability_fixtures.py).

Usage: CORTEX_URL=.. CORTEX_TOKEN=.. python scripts/eval_reliability.py [--reps 3] [--fixtures dentist-lifecycle] [--parallel 3]
Writes reports/reliability_<ts>.json and reports/reliability_<ts>.md (final states,
agent traces, every miss). Uses disposable owners (world:lab:rel-*); never touches real owners.

Checks collect EVERY failure (nothing overwrites a previous note), vacuous checks
do not exist (an expectation with no matching rows fails unless count allows 0),
and equivalent end states pass: the oracle accepts a set of correct outcomes.
"""
import argparse
import json
import os
import re
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reliability_fixtures import FIXTURES, TZ, sess

BASE = os.environ.get("CORTEX_URL", "http://127.0.0.1:8010").rstrip("/")
TOKEN = os.environ.get("CORTEX_TOKEN", "")
WS = os.environ.get("CORTEX_WORKSPACE", "llm-test-agent")


def api(path, body=None, method="POST"):
    H = {"Content-Type": "application/json"}
    if TOKEN:
        H["Authorization"] = "Bearer " + TOKEN
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None,
                                 headers=H, method=method)
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())


def _text(r):
    return " | ".join(str(r.get(k) or "") for k in ("title", "detail", "timing", "question", "waiting_on"))


def select_rows(ledger, sel):
    """Rows an expectation is about. `any`: needle anywhere in title|detail|timing; `title_any`: needle in the
    title only (a separate row that merely MENTIONS a matter in its detail is not that matter)."""
    if "title_any" in sel:
        needles = [n.lower() for n in sel["title_any"]]
        return [r for r in ledger if any(n in str(r.get("title") or "").lower() for n in needles)]
    needles = [n.lower() for n in sel.get("any", [])]
    return [r for r in ledger if any(n in _text(r).lower() for n in needles)]


def check_one(exp, ledger):
    """All failures are collected; returns (ok, notes)."""
    rows = select_rows(ledger, exp["select"])
    notes = []
    lo, hi = exp.get("count", (1, 99))
    if not lo <= len(rows) <= hi:
        notes.append(f"count {len(rows)} not in [{lo},{hi}]: {[r.get('title') for r in rows]}")
    if rows:
        if exp.get("status_in"):
            bad = [f"{r.get('title')!r} is {r.get('status')}" for r in rows if r.get("status") not in exp["status_in"]]
            if bad:
                notes.append(f"status not in {exp['status_in']}: " + "; ".join(bad))
        if exp.get("none_with_status"):
            bad = [f"{r.get('title')!r} is {r.get('status')}" for r in rows if r.get("status") in exp["none_with_status"]]
            if bad:
                notes.append(f"unexpected status {exp['none_with_status']}: " + "; ".join(bad))
        if exp.get("date_in"):
            bad = [f"{r.get('title')!r} date={r.get('expected_date')}" for r in rows if r.get("expected_date") not in exp["date_in"]]
            if bad:
                notes.append(f"expected_date not in {exp['date_in']}: " + "; ".join(bad))
        if exp.get("kind"):
            bad = [f"{r.get('title')!r} kind={r.get('kind')}" for r in rows if r.get("kind") != exp["kind"]]
            if bad:
                notes.append(f"kind != {exp['kind']}: " + "; ".join(bad))
        blob = " || ".join(_text(r) for r in rows)
        for rx in exp.get("mention", []):
            if not re.search(rx, blob, re.IGNORECASE):
                notes.append(f"nothing matches /{rx}/")
        if exp.get("mention_any") and not any(re.search(rx, blob, re.IGNORECASE) for rx in exp["mention_any"]):
            notes.append(f"none of {exp['mention_any']} matched")
    return (not notes), notes


def run_fixture(name, fix, rep):
    owner = f"world:lab:rel-{name}-{rep}-{int(time.time()) % 100000}"
    runs, snapshots = [], {}
    for sid, when, pairs in fix["sessions"]:
        body = {"workspace_id": WS, "owner": owner, "conversation_id": f"rel-{sid}",
                "session_id": f"rel-{sid}:{sid}", "messages": sess(pairs, sid), "companion_id": "sophie",
                "session_time": when, "time_zone": TZ}
        rid = api("/v1/memory/consolidate", body)["run_id"]
        st = {}
        for _ in range(90):
            time.sleep(4)
            st = api(f"/v1/memory/run/{rid}", method="GET")
            if st["status"] in ("consolidated", "replay_noop", "empty", "failed"):
                break
        summ = st.get("summary", {}) or {}
        agent = summ.get("ledger_agent") or {}
        runs.append({"sid": sid, "status": st["status"], "agent_status": agent.get("status"),
                     "accounting": agent.get("accounting"), "gate_failures": agent.get("gate_failures"),
                     "agent_summary": agent.get("summary"), "touched": agent.get("touched_keys"),
                     "witness": [{k: w.get(k) for k in ("title", "timing", "changed", "resolved", "ended", "status_hint", "waiting_on")}
                                 for w in (summ.get("ledger_witness_items") or [])],
                     "trace": [[t["name"] for t in (c.get("trace") or [])] for c in (summ.get("ledger_agent_trace") or [])],
                     "fallback": bool(summ.get("ledger_fallback")), "needs_review": summ.get("ledger_needs_review"),
                     "counts": summ.get("ledger_counts"), "ms": summ.get("ms_total")})
        state = api(f"/v1/memory/state?workspace_id={WS}&owner={owner}&include_closed=true", method="GET")
        snapshots[sid] = state.get("ledger", [])
    return {"owner": owner, "runs": runs, "snapshots": snapshots, "ledger": snapshots[fix["sessions"][-1][0]]}


def evaluate(fix, res):
    last = fix["sessions"][-1][0]
    out = []
    for exp in fix["expected"]:
        at = exp.get("at", last)
        ok, notes = check_one(exp, res["snapshots"].get(at, []))
        out.append({"name": exp["name"], "at": at, "pass": ok, "notes": notes})
    return out


def one(args):
    name, rep = args
    fix = FIXTURES[name]
    try:
        res = run_fixture(name, fix, rep)
        res["checks"] = evaluate(fix, res)
    except Exception as e:  # a harness/infra failure is reported, never counted as a pass
        res = {"error": f"{type(e).__name__}: {str(e)[:300]}", "checks": [
            {"name": e_["name"], "at": e_.get("at"), "pass": False, "notes": ["harness error"]} for e_ in fix["expected"]]}
    res["fixture"], res["rep"] = name, rep
    return res


def render_md(out):
    lines = [f"# Reliability run {out['at']}  ({out['summary']})", ""]
    for name, reps in out["results"].items():
        lines.append(f"## {name}")
        for r in reps:
            lines.append(f"### rep {r['rep']}  owner `{r.get('owner', '?')}`" + (f"  ERROR {r['error']}" if r.get("error") else ""))
            for c in r["checks"]:
                lines.append(f"- {'PASS' if c['pass'] else '**MISS**'} [{c['at']}] {c['name']}" + ("" if c["pass"] else "  — " + " ; ".join(c["notes"])))
            lines.append("")
            lines.append("final ledger:")
            lines.append("")
            lines.append("| status | date | kind | title | timing | detail |")
            lines.append("|---|---|---|---|---|---|")
            for row in r.get("ledger", []):
                lines.append("| {} | {} | {} | {} | {} | {} |".format(
                    row.get("status"), row.get("expected_date") or "—", row.get("kind"), (row.get("title") or "")[:50],
                    (row.get("timing") or "")[:30], (row.get("detail") or "")[:90].replace("|", "/")))
            lines.append("")
            for run in r.get("runs", []):
                lines.append(f"- run {run['sid']}: {run['status']} agent={run['agent_status']} fallback={run['fallback']} "
                             f"touched={run['touched']} ops={run['trace']} ms={run['ms']}")
                if run.get("gate_failures"):
                    lines.append(f"  - gate failures: {run['gate_failures']}")
                lines.append(f"  - witness: {run['witness']}")
                lines.append(f"  - accounting: {run['accounting']}")
            lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--fixtures", nargs="*", default=list(FIXTURES))
    ap.add_argument("--parallel", type=int, default=3)
    args = ap.parse_args()
    jobs = [(n, rep) for n in args.fixtures for rep in range(args.reps)]
    with ThreadPoolExecutor(max_workers=max(1, args.parallel)) as ex:
        done = list(ex.map(one, jobs))
    results = {}
    for r in done:
        results.setdefault(r["fixture"], []).append(r)
    for v in results.values():
        v.sort(key=lambda r: r["rep"])
    npass = sum(1 for rs in results.values() for r in rs for c in r["checks"] if c["pass"])
    ntot = sum(1 for rs in results.values() for r in rs for c in r["checks"])
    reps_clean = sum(1 for rs in results.values() for r in rs if all(c["pass"] for c in r["checks"]))
    nreps = sum(len(rs) for rs in results.values())
    out = {"at": datetime.now(timezone.utc).isoformat(), "summary": f"checks {npass}/{ntot}, clean reps {reps_clean}/{nreps}",
           "results": results}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    os.makedirs("reports", exist_ok=True)
    json.dump(out, open(f"reports/reliability_{stamp}.json", "w"), indent=1)
    open(f"reports/reliability_{stamp}.md", "w").write(render_md(out))
    for name, rs in results.items():
        for r in rs:
            bad = [c for c in r["checks"] if not c["pass"]]
            print(f"{name} rep{r['rep']}: {'CLEAN' if not bad else str(len(bad)) + ' MISS'}")
            for c in bad:
                print(f"    MISS [{c['at']}] {c['name']}: {' ; '.join(c['notes'])}")
    print(f"{out['summary']} -> reports/reliability_{stamp}.md")
    return 0 if npass == ntot else 1


if __name__ == "__main__":
    raise SystemExit(main())
