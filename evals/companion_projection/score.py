# Lane A evaluation: frozen corpus + deterministic scorer + naive baseline.
#
# Usage: python3 score.py [--out results.json]
# Loads evals/sophie_longitudinal scenario fixtures (pinned version asserted)
# plus inline synthetic days from corpus.json, builds projections with
# builder.build_projection, and scores nine dimensions with exact matching.
# No models, no randomness.

import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from builder import build_projection, _label_cluster  # noqa: E402

SCEN_DIR = os.path.join(HERE, "..", "sophie_longitudinal")


def load_day_events(day, corpus_version):
    events = []
    for src in day.get("sources", []):
        path = os.path.join(SCEN_DIR, src["scenario"] + "_input.json")
        scen = json.load(open(path))
        assert scen.get("fixture_version") == "1.0.0", path
        events += [e for e in scen["events"] if e["id"] <= src["upto"]]
    events += day.get("synthetic", [])
    events.sort(key=lambda e: e.get("timestamp", ""))
    return events


def _normq(s):
    return (s or "").replace("’", "'").replace("“", '"').replace("”", '"').lower()


def _slug_tokens(topic):
    return set(topic.lower().split("-"))


def _item_tokens(item):
    toks = set(_slug_tokens(item.get("topic", "")))
    for s in (item.get("stems") or []):
        toks.add(str(s).lower())
    return toks


def _match_tokens(item, tokens):
    it = _item_tokens(item)
    text = (item.get("topic", "") + " " + " ".join(
        str(s) for s in (item.get("stems") or []))).lower()
    return any(t.lower() in text or t.lower() in it for t in tokens)


def _all_items(proj):
    out = []
    for section, val in proj.items():
        if section in ("meta", "horizons"):
            continue
        if isinstance(val, list):
            out += [v for v in val if isinstance(v, dict)]
        elif isinstance(val, dict):
            for v in val.values():
                if isinstance(v, list):
                    out += [x for x in v if isinstance(x, dict)]
                elif isinstance(v, dict) and "id" in v:
                    out.append(v)
    return out


def lifecycle_rows(proj):
    return proj["current_world"]["task_lifecycle"]


def hard_items(proj):
    h = proj["hard_constraints"]
    return h["boundaries"] + h["deferrals"] + h["required_reminders"] + \
        h["verified_closures"] + h["revalidation_requirements"]


def score_day(day, proj):
    res = {"id": day["id"]}
    details = {}

    # 1. required-context recall
    req = day.get("required", [])
    found = 0
    for r in req:
        toks = r["tokens"]
        if r.get("kind") == "possible_goal":
            pool = proj["soft_candidates"]["active_goals"]
        elif r.get("kind") == "recent_accomplishment":
            pool = proj["soft_candidates"]["recent_significant_events"]
        else:
            pool = lifecycle_rows(proj)
        ok = any(_match_tokens(i, toks) and
                 (r.get("status") is None or i.get("status") == r["status"])
                 for i in pool)
        found += 1 if ok else 0
        details.setdefault("recall_miss", []).append(
            {"tokens": toks, "ok": ok} if not ok else None) if not ok else None
    res["recall"] = {"found": found, "total": len(req)}

    # 2. irrelevant-context inclusion (open lifecycle rows w/o any anchor)
    anchor_toks = set()
    for r in req:
        anchor_toks.update(t.lower() for t in r["tokens"])
    anchor_toks.update(t.lower() for t in day.get("allowed_extra", []))
    anchor_toks.update(t.lower() for h in day.get("required_hard", []) for t in h["tokens"])
    extras = []
    for row in lifecycle_rows(proj):
        if row.get("status") != "open":
            continue
        it = _item_tokens(row)
        if not (it & anchor_toks) and not any(
                t in row.get("topic", "") for t in anchor_toks):
            extras.append(row["topic"])
    res["irrelevant"] = {"count": len(extras), "topics": extras}

    # 3. stale/closed leakage
    leaks = []
    for f in day.get("forbidden_open", []):
        for row in lifecycle_rows(proj):
            if row.get("status") == "open" and f.lower() in (
                    row.get("topic", "") + " " + " ".join(
                        str(s) for s in (row.get("stems") or []))).lower():
                leaks.append({"token": f, "topic": row["topic"]})
    res["stale"] = {"count": len(leaks), "leaks": leaks}

    # 4. explicit-boundary preservation
    hb = day.get("required_hard", [])
    hfound = 0
    for h in hb:
        ok = any(_match_tokens(i, h["tokens"]) and
                 (_normq(h.get("quote", "")) in _normq(i.get("quote"))) and
                 (h.get("scope") is None or i.get("scope") == h["scope"])
                 for i in hard_items(proj))
        hfound += 1 if ok else 0
    res["boundary"] = {"found": hfound, "total": len(hb)}

    # 5. hard/soft distinction (required-soft tokens must not surface in hard)
    hs_viol = []
    for t in day.get("required_soft_absent_from_hard", []):
        for i in hard_items(proj):
            blob = (i.get("topic", "") + " " + (i.get("quote") or "")).lower()
            if t.lower() in blob:
                hs_viol.append({"token": t, "item": i["id"]})
    res["hardsoft"] = {"violations": len(hs_viol), "detail": hs_viol}

    # 6. horizon correctness
    hh = day.get("required_horizons", [])
    hrok = 0
    for h in hh:
        ok = any(_match_tokens(i, h["tokens"]) and i.get("horizon") == h["horizon"]
                 for i in _all_items(proj))
        hrok += 1 if ok else 0
    res["horizon"] = {"found": hrok, "total": len(hh)}

    # 7. relational-vs-operational separation
    rel = day.get("required_relational", [])
    relmiss = [k for k in rel if not any(
        k.lower() in (i.get("quote") or "").lower() or k.lower() in i.get("topic", "").lower()
        for i in proj["relational_context"])]
    opviol = []
    op_pool = (proj["soft_candidates"]["unresolved_topics"]
               + proj["soft_candidates"]["active_goals"]
               + proj["soft_candidates"]["opportunities"]
               + proj["current_world"]["active_commitments"])
    for k in day.get("forbidden_operational", []):
        for i in op_pool:
            blob = (i.get("topic", "") + " " + " ".join(
                str(s) for s in (i.get("stems") or []))).lower()
            if k.lower() in blob:
                opviol.append({"token": k, "item": i["id"]})
    res["separation"] = {"relational_miss": relmiss, "op_violations": opviol}

    # 8. provenance / invalidation availability
    prov_bad = [i.get("id", "?") for i in _all_items(proj) if not i.get("sources")]
    meta = proj.get("meta", {})
    meta_ok = all([meta.get("built_at"), meta.get("session_id"),
                   meta.get("rebuild_on"), meta.get("source_event_ids") is not None])
    res["provenance"] = {"items_missing_sources": prov_bad, "meta_ok": meta_ok}

    # 9. behavioural-command leakage (builder self-audit)
    audit = meta.get("command_audit", {})
    res["commands"] = {"violations": audit.get("violations", []),
                       "passed": audit.get("passed", False)}

    # mundane caps
    caps = day.get("caps")
    if caps:
        res["caps"] = {
            "unresolved": len(proj["soft_candidates"]["unresolved_topics"]),
            "opportunities": len(proj["soft_candidates"]["opportunities"]),
            "hard": len(hard_items(proj)),
            "relational": len(proj["relational_context"]),
        }
    if day.get("required_opportunities"):
        res["opportunities"] = len(proj["soft_candidates"]["opportunities"])
    return res


# ----------------------------------------------------------------------------
# Naive baseline: flat recency-ranked imperative packet (no channels, no
# lifecycle, no provenance). Shows what the projection earns over "helpful".
# ----------------------------------------------------------------------------

def baseline_projection(events, now_iso):
    from builder import cluster_events, _parse_ts
    now = _parse_ts(now_iso)
    evs = sorted([e for e in events
                  if (_parse_ts(e.get("timestamp", "")) or now) <= now],
                 key=lambda e: e.get("timestamp", ""))
    by_id = {e["id"]: e for e in evs}
    clusters, _ = cluster_events(evs)
    lines = []
    for i, c in enumerate(sorted(
            clusters, key=lambda c: by_id[c["event_ids"][-1]].get("timestamp", ""),
            reverse=True)):
        label, _ = _label_cluster(c, by_id)
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or c["key"]
        lines.append("Priority %d: Ask about '%s' (last: %s). Mention this "
                     "to the user and remind the user to act on it." % (
                         i + 1, slug, c["event_ids"][-1]))
    return {"priorities": lines, "topics": [
        re.sub(r"[^a-z0-9]+", "-", _label_cluster(c, by_id)[0].lower()).strip("-")
        or c["key"] for c in clusters]}


def score_baseline(day, base):
    topics = base["topics"]
    req = day.get("required", [])
    found = sum(1 for r in req if any(
        t.lower() in topic for topic in topics for t in r["tokens"]))
    hb = day.get("required_hard", [])
    text = " ".join(base["priorities"]).lower()
    import re as _re
    cmd_hits = sum(1 for p in
                   [r"\bask about\b", r"\bmention\b", r"\bremind the user\b",
                    r"\bpriority\b"]
                   if _re.search(p, text))
    return {"recall": {"found": found, "total": len(req)},
            "hard_boundary_items": 0, "hard_total": len(hb),
            "command_phrases": cmd_hits,
            "sections": 1, "provenance_items": 0}


def main():
    corpus = json.load(open(os.path.join(HERE, "corpus.json")))
    out_path = None
    if "--out" in sys.argv:
        out_path = sys.argv[sys.argv.index("--out") + 1]
    results = {"version": corpus["version"], "days": [], "baseline": []}
    for day in corpus["days"]:
        events = load_day_events(day, corpus.get("fixture_version"))
        proj = build_projection(events, day["now"], day["session_id"],
                                corpus.get("fixture_version", "unknown"))
        results["days"].append(score_day(day, proj))
        base = baseline_projection(events, day["now"])
        b = score_baseline(day, base)
        b["id"] = day["id"]
        results["baseline"].append(b)

    # report table
    print("day | recall | irrel | stale | bound | hardsoft | horiz | sep(rel,op) | prov | cmd")
    for r in results["days"]:
        print("%s | %d/%d | %d | %d | %d/%d | viol %d | %d/%d | relmiss %d opviol %d | bad %d meta %s | %s" % (
            r["id"], r["recall"]["found"], r["recall"]["total"],
            r["irrelevant"]["count"], r["stale"]["count"],
            r["boundary"]["found"], r["boundary"]["total"],
            r["hardsoft"]["violations"],
            r["horizon"]["found"], r["horizon"]["total"],
            len(r["separation"]["relational_miss"]), len(r["separation"]["op_violations"]),
            len(r["provenance"]["items_missing_sources"]),
            r["provenance"]["meta_ok"], r["commands"]["passed"]))
    print("--- baseline (flat imperative packet) ---")
    for b in results["baseline"]:
        print("%s | recall %d/%d | hard %d/%d | cmd_phrases %d | sections %d | provenance %d" % (
            b["id"], b["recall"]["found"], b["recall"]["total"],
            b["hard_boundary_items"], b["hard_total"],
            b["command_phrases"], b["sections"], b["provenance_items"]))
    if out_path:
        json.dump(results, open(out_path, "w"), indent=1)
        print("wrote", out_path)


if __name__ == "__main__":
    main()
