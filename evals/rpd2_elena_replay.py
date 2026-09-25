"""RPD2 Elena real-transcript replay (115 turns, redacted fixture).

Posts every turn through the live ingest path (model extraction + semantic
reconciliation + T2 maintenance), then dumps durable state and runs
acceptance checks. Honest replay: redaction markers included as-is.

Usage:
    ./.venv/bin/python evals/rpd2_elena_replay.py [--out reports/rpd2_elena_replay.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

FIXTURE = Path("/Users/mukeshkumar/play/rpd2/fixtures/elena_5bb4821f.redacted.json")


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="reports/rpd2_elena_replay.json")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    os.environ["SYNAPSE_EXTRACTOR_PROVIDER"] = "model"
    db_path = "/tmp/rpd2_elena_replay.db"
    if os.path.exists(db_path):
        os.remove(db_path)
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"

    import dotenv
    dotenv.load_dotenv(REPO / ".env")

    from httpx import ASGITransport, AsyncClient
    from sqlmodel import SQLModel, select
    from src.main import app
    import src.db as dbmod
    from src.db import engine

    fixture = json.loads(FIXTURE.read_text())
    turns = fixture["turns"]
    if args.limit:
        turns = turns[: args.limit]

    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    ws, sess = "rpd2-elena", "elena-5bb4821f"
    base = datetime(2026, 9, 20, 20, 0, tzinfo=timezone.utc)
    transport = ASGITransport(app=app)
    errors = []
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for i, t in enumerate(turns):
            is_assistant = t["role"] == "assistant"
            payload = {
                "workspace_id": ws,
                "session_id": sess,
                "honcho_message_id": f"elena-t{i:03d}",
                "peer_id": "elena" if is_assistant else "kai",
                "text": t["content"],
                "now": (base + timedelta(seconds=180 * i)).isoformat(),
                "timezone": "Europe/London",
                "is_assistant_turn": is_assistant,
            }
            try:
                res = await client.post("/v1/events/turn", json=payload, timeout=180.0)
                if res.status_code not in (200, 202):
                    errors.append({"turn": i, "status": res.status_code,
                                   "body": res.text[:300]})
            except Exception as err:
                errors.append({"turn": i, "error": str(err)[:300]})
            if (i + 1) % 20 == 0:
                print(f"  {i + 1}/{len(turns)} turns, errors={len(errors)}", flush=True)

    from src.models.attention_candidate import AttentionCandidate
    from src.models.clarification import ClarificationCandidate
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.current_meaning import CurrentMeaning
    from src.models.expectation import Expectation
    from src.models.fact import Fact
    from src.models.identity import ModelEntry
    from src.models.open_loop import OpenLoop
    from src.models.semantic import SemanticClaim, SemanticRelation

    async with dbmod.async_session_maker() as db:
        async def all_of(model, cond=None):
            q = select(model).where(model.honcho_workspace_id == ws)
            if cond is not None:
                q = q.where(cond)
            return (await db.execute(q)).scalars().all()

        exps = await all_of(Expectation)
        comms = await all_of(CommitmentCandidate)
        loops = await all_of(OpenLoop)
        meanings = await all_of(CurrentMeaning)
        claims = await all_of(SemanticClaim)
        rels = await all_of(SemanticRelation)
        facts = await all_of(Fact)
        models = await all_of(ModelEntry)
        clars = await all_of(ClarificationCandidate)
        atts = await all_of(AttentionCandidate)

    def row_exp(e):
        return {"title": e.title[:120], "type": str(e.expectation_type),
                "state": str(e.outcome_state), "owner": e.owner_peer_id,
                "subject": e.subject_peer_id}

    report = {
        "turns": len(turns), "errors": errors,
        "counts": {
            "expectations": len(exps), "commitments": len(comms),
            "loops": len(loops), "meanings": len(meanings),
            "claims": len(claims), "relations": len(rels),
            "facts": len(facts), "model_entries": len(models),
            "clarifications": len(clars), "attention": len(atts),
        },
        "expectations": [row_exp(e) for e in exps],
        "commitments": [{"title": c.title[:120], "owner": c.owner_peer_id,
                         "authority": str(c.authority), "status": str(c.status)}
                        for c in comms],
        "loops": [{"title": (l.title or "")[:120], "status": str(l.status)} for l in loops],
        "meanings": [{"version": m.version, "means": m.means_json[:300],
                      "unresolved": m.unresolved_json[:300]} for m in meanings],
        "relations": [{"type": str(r.rel_type), "conf": r.confidence} for r in rels],
        "facts": [{"title": f.title[:120], "owner": f.owner_peer_id} for f in facts],
        "model_entries": [{"kind": m.model_kind, "claim": m.claim[:160]} for m in models],
    }
    dest = REPO / args.out
    dest.write_text(json.dumps(report, indent=1, default=str))
    print(f"wrote {dest} turns={len(turns)} errors={len(errors)}")
    print("counts:", report["counts"])
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
