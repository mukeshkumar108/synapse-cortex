"""One-off repair of the three founder recurrences (Workstream 1 audit).

Audit verdict (2026-08-30), against original evidence:
  1. "daily talk with Ashley"  — evidence "we talk everyday obviously..." —
     REAL cadence words, but they describe mutual observed behaviour, not a
     commitment. -> semantic_type=observed_pattern (kept as recurrence).
  2. "Fix audio transcription bug" — evidence "it's been happening every
     single day" — cadence words attach to the PROBLEM, not a practice. NOT
     a recurrence at all. -> status=CANCELLED with provenance note (the
     durable objective already lives in expectations).
  3. "daily step goal" — evidence "10 K is the base is the floor" — no
     cadence evidence in the verbatim span; a durable measurable goal with a
     floor target. -> semantic_type=measurable_goal (kept, cadence daily is
     the everyday unit of the target).

Run with --apply to mutate; default is a dry run. Provenance is appended to
source_evidence so the supersede/delete invariant is preserved.
"""

import asyncio
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.db import engine  # noqa: E402


REPAIRS = {
    "fix-audio-transcription-bug": {"cancel": True,
        "note": "repair 2026-08-30: problem-frequency cadence (bug happening daily) is not a user practice; demoted to one-off durable objective"},
    "talk-with-ashley": {"semantic_type": "observed_pattern",
        "note": "repair 2026-08-30: mutual observed pattern ('we talk everyday'), not a commitment"},
    "step-goal": {"semantic_type": "measurable_goal",
        "note": "repair 2026-08-30: durable measurable goal with floor target (10k steps/day), not a simple checkbox"},
}


async def main(apply: bool) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker
    maker = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with maker() as db:
        rows = (await db.execute(text(
            "select id, canonical_key, title, status, semantic_type, source_evidence "
            "from recurring_intentions where status = 'ACTIVE'"
        ))).mappings().all()
        for row in rows:
            repair = REPAIRS.get(row["canonical_key"])
            if not repair:
                print(f"SKIP {row['canonical_key']!r} (no repair defined)")
                continue
            print(f"{'APPLY' if apply else 'DRY '} {row['canonical_key']!r}: {repair}")
            if not apply:
                continue
            if repair.get("cancel"):
                await db.execute(text(
                    "update recurring_intentions set status='CANCELLED', active_slot=NULL, "
                    "ended_at=now(), updated_at=now(), source_evidence=source_evidence || :note "
                    "where id=:id"
                ), {"id": row["id"], "note": f" [{repair['note']}]"})
            else:
                await db.execute(text(
                    "update recurring_intentions set semantic_type=:st, updated_at=now(), "
                    "source_evidence=source_evidence || :note where id=:id"
                ), {"id": row["id"], "st": repair["semantic_type"], "note": f" [{repair['note']}]"})
        if apply:
            await db.commit()
            print("committed")


if __name__ == "__main__":
    asyncio.run(main(apply="--apply" in sys.argv))
