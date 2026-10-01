#!/usr/bin/env python3
"""Backfill Matters, actor direction, knowledge coverage and the initial
WorldModel from existing primitives (docs/CORTEX_CUTOVER.md §8).

Idempotent and re-runnable; NEVER part of a migration. Seeds obvious
current/recent Matters through the same identity resolution
(`resolve_or_create_matter`) the live write path uses — it does not attempt a
perfect historical reconstruction. Ongoing consolidation improves it.

    python scripts/backfill_matters.py --workspace WS [--dry-run] [--tz Europe/London]
    python scripts/backfill_matters.py --all-workspaces

--dry-run runs everything inside one transaction and rolls it back, printing
exactly what would change.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import select  # noqa: E402

from src.db import async_session_maker, get_rollback_session  # noqa: E402


async def _stamp_directions(db, workspace_id: str) -> dict:
    """Stamp `direction` on rows that predate the column (structural derivation
    only — rows whose direction cannot be decided from the row stay null and
    are derived at read time with scope knowledge)."""
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop
    from src.services.actor_direction import direction_from_row
    out = {}
    for model in (Expectation, OpenLoop, CommitmentCandidate):
        rows = (await db.execute(select(model).where(
            model.honcho_workspace_id == workspace_id, model.direction.is_(None)))).scalars().all()
        n = 0
        for row in rows:
            d = direction_from_row(row)
            if d:
                row.direction = d
                db.add(row)
                n += 1
        out[model.__tablename__] = n
    await db.flush()
    return out


async def backfill_workspace(db, workspace_id: str, *, now: datetime, tz: str, allow_judge: bool) -> dict:
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop
    from src.models.operational_state import RecurringIntention
    from src.services import matter_service, world_model_service

    report: dict = {"workspace_id": workspace_id}
    report["directions_stamped"] = await _stamp_directions(db, workspace_id)
    adapter = None
    if allow_judge:
        from src.runtime_model import get_agenda_adapter
        adapter = get_agenda_adapter()
    report["matters"] = await matter_service.sync_workspace(
        db, workspace_id=workspace_id, now=now, allow_judge=allow_judge, adapter=adapter)
    owners = set()
    for model in (Expectation, OpenLoop, RecurringIntention, CommitmentCandidate):
        owners.update((await db.execute(select(model.owner_peer_id).where(
            model.honcho_workspace_id == workspace_id).distinct())).scalars().all())
    report["world_models"] = {}
    for owner in sorted(o for o in report["matters"] if o != "<none>"):
        wm = await world_model_service.compile_world_model(
            db, workspace_id=workspace_id, owner_peer_id=owner, now=now,
            timezone_str=tz, force=True, sync=False)
        report["world_models"][owner] = {
            "version": wm["meta"]["version"], "model_version": wm["meta"]["model_version"], "snapshot_id": wm["meta"]["snapshot_id"],
            "active_matters": wm["matters"]["active_total"],
            "coverage": wm["coverage"]["counts"]}
    return report


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--workspace", action="append", default=[])
    ap.add_argument("--all-workspaces", action="store_true")
    ap.add_argument("--tz", default="UTC")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--allow-judge", action="store_true",
                    help="use the bounded semantic judge for genuinely ambiguous Matter identity")
    args = ap.parse_args()
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    async def run(db) -> list:
        workspaces = list(args.workspace)
        if args.all_workspaces:
            from src.models.expectation import Expectation
            from src.models.open_loop import OpenLoop
            for model in (Expectation, OpenLoop):
                workspaces += (await db.execute(select(model.honcho_workspace_id).distinct())).scalars().all()
        workspaces = sorted(set(workspaces))
        return [await backfill_workspace(db, ws, now=now, tz=args.tz, allow_judge=args.allow_judge)
                for ws in workspaces]

    if args.dry_run:
        # Services commit internally; the rollback session keeps every effect
        # inside an outer transaction that is rolled back.
        from contextlib import aclosing
        async with aclosing(get_rollback_session()) as gen:   # always finalise (rollback + close)
            db = await gen.__anext__()
            reports = await run(db)
    else:
        async with async_session_maker() as db:
            reports = await run(db)
    if not reports:
        print("no workspaces (pass --workspace or --all-workspaces)", file=sys.stderr)
        return 2
    print(json.dumps({"dry_run": args.dry_run, "reports": reports}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
