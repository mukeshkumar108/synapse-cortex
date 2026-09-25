"""Phase-A shadow runner — reads fixtures, runs shadow pipeline, writes output.

Usage:
    ./.venv/bin/python scripts/run_shadow_phase_a.py [--out reports/shadow_phase_a_output.json]

- Never imports src.models/src.services/src.routers/src.db.
- Never writes production state. Output JSON is disposable/inspectable.
- Also prints a compact acceptance table to stdout.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))

from shadow_a.cases import build_cases  # noqa: E402
from shadow_a.pipeline import _sid, run_case  # noqa: E402
from shadow_a.schema import ShadowClaim  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/shadow_phase_a_output.json")
    args = ap.parse_args()

    out: dict = {"cases": [], "table": []}
    for spec in build_cases():
        res = run_case(spec["case_id"], spec["events"],
                       spec.get("observed_sources", []),
                       spec.get("user_tracking_ok", True),
                       spec.get("absence_probes"))
        # Inject extra evidence-backed claims for reconstructed probes (stand-in
        # for a fuller semantic extractor; claims carry refs, not conclusions).
        for extra in spec.get("extra_claims", []):
            cid = "term" + _sid(spec["case_id"], extra["content"]) if "pact term" in extra["content"] or "open matter" in extra["content"] else _sid(spec["case_id"], extra["content"])
            if cid not in {c.claim_id for c in res.claims}:
                res.claims.append(ShadowClaim(
                    claim_id=cid, content=extra["content"], subjects=["user", "isa"],
                    evidence_refs=list(extra["refs"]), modality="promised",
                    formation="explicit", confidence=0.8))
        # Re-run relational/role layers if extras were added.
        if spec.get("extra_claims"):
            from shadow_a.pipeline import (assign_roles, build_obligations, build_views, derive_moves,
                                           propose_relations, propose_t2)
            res.relations = propose_relations(res.case_id, res.claims, spec["events"])
            res.roles = assign_roles(res.claims, res.relations)
            res.obligations = build_obligations(res.case_id, res.claims, res.roles)
            res.t2 = propose_t2(res.case_id, spec["events"], res.claims, res.roles)
            res.views = build_views(res.claims, res.roles, res.obligations)
            res.moves, res.assessments = derive_moves(
                res.case_id, res.claims, res.roles, res.relations,
                res.obligations, res.t2, spec.get("observed_sources", []),
                spec.get("user_tracking_ok", True))

        d = res.to_dict()
        d["title"] = spec["title"]
        out["cases"].append(d)
        tel = {}
        for a in res.assessments:
            tel[a.telemetry] = tel.get(a.telemetry, 0) + 1
        out["table"].append({
            "case": res.case_id, "title": spec["title"],
            "claims": len(res.claims), "relations": len(res.relations),
            "moves": len(res.moves),
            "user_facing": sum(1 for m in res.moves if m.user_facing),
            "telemetry": tel,
            "expected_but_missing": len(res.expected_but_missing),
            "unknowns": len(res.unknowns),
        })

    dest = REPO / args.out
    dest.write_text(json.dumps(out, indent=1))
    print(f"wrote {dest}")
    for row in out["table"]:
        print(f"{row['case']:20s} claims={row['claims']:2d} rels={row['relations']} "
              f"moves={row['moves']} user_facing={row['user_facing']} tel={row['telemetry']} "
              f"ebm={row['expected_but_missing']} unk={row['unknowns']}")

    # A.5 sequential replays + revision diffs (shadow only, disposable).
    from shadow_a.pipeline import diff_snapshots, replay_sequential  # noqa: E402
    seq_out: dict = {"replays": []}
    for spec in build_cases():
        if not spec.get("sequential"):
            continue
        snaps = replay_sequential(spec["case_id"], spec["events"],
                                  spec.get("observed_sources", []),
                                  spec.get("user_tracking_ok", True))
        diffs = []
        for i in range(1, len(snaps)):
            d = diff_snapshots(snaps[i - 1], snaps[i])
            d["step"] = f"t{i:02d}->{i + 1:02d}"
            d["event"] = spec["events"][i]["id"]
            # keep diffs readable: only steps that changed something
            if d["new_claims"] or d["new_relations"] or d["evidence_grown"] or d["role_changes"]:
                diffs.append(d)
        final = snaps[-1].to_dict()
        seq_out["replays"].append({
            "case": spec["case_id"], "title": spec["title"],
            "n_events": len(spec["events"]),
            "final_table": {
                "claims": len(snaps[-1].claims), "relations": len(snaps[-1].relations),
                "moves": len(snaps[-1].moves),
                "user_facing": sum(1 for m in snaps[-1].moves if m.user_facing),
                "telemetry": _tel(snaps[-1]),
            },
            "final": final,
            "diffs": diffs,
        })
        print(f"sequential {spec['case_id']}: {len(snaps)} snapshots, "
              f"{len(diffs)} changing steps")
    seq_dest = dest.parent / "shadow_phase_a5_sequential.json"
    seq_dest.write_text(json.dumps(seq_out, indent=1))
    print(f"wrote {seq_dest}")
    return 0


def _tel(res) -> dict:
    tel: dict = {}
    for a in res.assessments:
        tel[a.telemetry] = tel.get(a.telemetry, 0) + 1
    return tel


if __name__ == "__main__":
    raise SystemExit(main())
