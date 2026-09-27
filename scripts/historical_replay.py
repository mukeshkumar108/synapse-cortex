#!/usr/bin/env python3
"""Export read-only history and replay it into a fresh isolated Cortex DB.

Examples are documented in ``docs/HISTORICAL_REPLAY.md``.  Raw corpus and
reports may contain private conversation text and are gitignored.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.replay.historical import (  # noqa: E402
    export_rpd2, export_sophie, lexical_future_references, load_corpus,
    parse_env_file,
)


def parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)
    ex = sub.add_parser("export", help="read a historical DB and write corpus JSON")
    ex.add_argument("--source", choices=("sophie", "rpd2"), required=True)
    ex.add_argument("--env-file", type=Path, required=True)
    ex.add_argument("--url-key", default="DATABASE_URL")
    ex.add_argument("--out", type=Path, required=True)
    ex.add_argument("--user-id"); ex.add_argument("--persona-id")
    ex.add_argument("--chat-id"); ex.add_argument("--limit", type=int, default=8)
    ex.add_argument("--min-messages", type=int, default=2)
    ex.add_argument("--idle-minutes", type=int, default=30)
    run = sub.add_parser("run", help="replay corpus through current consolidation")
    run.add_argument("--input", type=Path, required=True)
    run.add_argument("--out", type=Path, required=True)
    run.add_argument("--db", type=Path, required=True)
    run.add_argument("--model-id")
    run.add_argument("--max-sessions", type=int, default=0)
    return ap


async def do_export(args: argparse.Namespace) -> None:
    values = parse_env_file(args.env_file)
    url = values.get(args.url_key)
    if not url:
        raise SystemExit(f"{args.url_key} missing from {args.env_file}")
    if args.source == "sophie":
        if not args.user_id or not args.persona_id:
            raise SystemExit("Sophie export requires --user-id and --persona-id")
        corpus = await export_sophie(
            url, user_id=args.user_id, persona_id=args.persona_id,
            min_messages=args.min_messages, limit=args.limit)
    else:
        if not args.chat_id:
            raise SystemExit("RPD2 export requires --chat-id")
        corpus = await export_rpd2(url, chat_id=args.chat_id,
                                   idle_minutes=args.idle_minutes)
    corpus.dump(args.out)
    print(json.dumps({"out": str(args.out), "source": corpus.source,
                      "sessions": len(corpus.sessions),
                      "messages": sum(len(s.turns) for s in corpus.sessions)}))


def _matter_dict(m: Any) -> dict[str, Any]:
    return {"id": m.id, "kind": m.kind, "title": m.title,
            "status": m.status, "owner": m.owner}


def _snapshot_dict(s: Any) -> dict[str, Any]:
    return {"matters": [_matter_dict(m) for m in s.matters],
            "attentions": list(s.attentions), "suppressions": list(s.suppressions),
            "people": list(s.people)}


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    b = {m["id"]: m for m in before["matters"]}; a = {m["id"]: m for m in after["matters"]}
    return {"added": [a[k] for k in a.keys() - b.keys()],
            "removed": [b[k] for k in b.keys() - a.keys()],
            "changed": [{"before": b[k], "after": a[k]} for k in a.keys() & b.keys()
                        if a[k] != b[k]],
            "attention_added": sorted(set(after["attentions"]) - set(before["attentions"])),
            "suppression_added": sorted(set(after["suppressions"]) - set(before["suppressions"]))}


async def do_run(args: argparse.Namespace) -> None:
    # Must happen before src.db is imported: replay cannot point at normal Cortex.
    db_path = args.db.resolve()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        raise SystemExit(f"refusing to overwrite replay DB: {db_path}")
    os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{db_path}"
    os.environ["ENV"] = "test"
    os.environ["SESSION_CONSOLIDATION_ENABLED"] = "1"
    os.environ["SESSION_CONSOLIDATION_APPLY"] = "1"
    # Load model credentials/config without allowing .env's DATABASE_URL to
    # replace the isolated path set above.
    try:
        from dotenv import load_dotenv
        load_dotenv(REPO / ".env", override=False)
    except ImportError:
        pass

    from sqlmodel import SQLModel
    import src.main  # noqa: F401 -- imports every table model into metadata
    import src.db as dbmod
    from src.services.session_consolidation import SessionTurn, capture_snapshot
    from src.services.session_reconstruction import consolidate_long_session

    corpus = load_corpus(args.input)
    sessions = corpus.sessions[:args.max_sessions or None]
    workspace_id = f"replay:{corpus.source}:{corpus.subject_id}"
    # Cortex's current durable rows are session-scoped. A stable lane id is
    # intentional: source session provenance remains on every report item,
    # while state can carry across historical boundaries.
    lane_session_id = f"historical-lane:{corpus.subject_id}:{corpus.companion_id}"
    async with dbmod.engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    records = []
    async with dbmod.async_session_maker() as db:
        for i, session in enumerate(sessions):
            before_obj = await capture_snapshot(
                db, workspace_id=workspace_id, session_id=lane_session_id)
            before = _snapshot_dict(before_obj)
            turns = [SessionTurn(t.message_id, "assistant" if t.role == "assistant" else "user", t.text)
                     for t in session.turns]
            # Segmented orchestration: long sessions split into bounded raw
            # windows (apply-continue), short ones take the single path.
            aggregate = await consolidate_long_session(
                db, workspace_id=workspace_id, session_id=lane_session_id,
                transcript=turns, start_snapshot=before_obj,
                temporal_session_id=session.source_session_id,
                model_id=args.model_id, user_peer_id=corpus.subject_id,
                mode="apply")
            await db.commit()
            after_obj = await capture_snapshot(
                db, workspace_id=workspace_id, session_id=lane_session_id)
            after = _snapshot_dict(after_obj)
            future_text = "\n".join(t.text for s in sessions[i + 1:] for t in s.turns)
            records.append({
                "source_session_id": session.source_session_id,
                "boundary": session.boundary, "started_at": session.started_at,
                "ended_at": session.ended_at, "message_count": len(session.turns),
                "transcript": [asdict(t) for t in session.turns],
                "consolidation": {"summaries": aggregate.get("summaries", []),
                    "error": aggregate.get("error", ""),
                    "prompt_chars": aggregate.get("prompt_chars", 0),
                    "latency_s": aggregate.get("latency_s", 0.0),
                    "accepted": aggregate.get("accepted", []),
                    "rejected": aggregate.get("rejected", []),
                    "discards": aggregate.get("discards", []),
                    "provisional_marks": aggregate.get("provisional_marks", []),
                    "would_apply": aggregate.get("would_apply", []),
                    "applied": aggregate.get("applied", []),
                    "deferred": aggregate.get("deferred", []),
                    "segments": aggregate.get("segment_reports", []),
                    "coverage": aggregate.get("coverage", {})},
                "snapshot_after": after, "diff_from_prior": _diff(before, after),
                "future_lexical_references": lexical_future_references(
                    (m["title"] for m in after["matters"]), future_text),
                "coverage": aggregate.get("coverage", {}),
            })
            print(f"{i + 1}/{len(sessions)} {session.source_session_id}: "
                  f"{len(aggregate.get('accepted', []))} accepted, "
                  f"{len(aggregate.get('applied', []))} applied, "
                  f"segments={len(aggregate.get('segment_reports', []))}, "
                  f"error={aggregate.get('error') or '-'}", flush=True)
    report = {"schema_version": 1, "source": corpus.source,
              "source_locator": corpus.source_locator,
              "subject_id": corpus.subject_id, "companion_id": corpus.companion_id,
              "workspace_id": workspace_id, "isolated_db": str(db_path),
              "source_provenance": corpus.provenance, "sessions": records}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str))
    print(json.dumps({"out": str(args.out), "db": str(db_path),
                      "sessions": len(records)}))


async def main() -> None:
    args = parser().parse_args()
    await (do_export(args) if args.command == "export" else do_run(args))


if __name__ == "__main__":
    asyncio.run(main())
