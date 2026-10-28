"""The brief, prepared ahead and rebuilt on change.

The brief itself is a deterministic query (notes.brief). This module keeps the built page so it can be handed over as a document (to the Runtime, to a push at 08:00,
to the person to read) without being worked out again, and keeps it honest: a write to the person's notes or ledger marks their cached briefs stale IN THE SAME
TRANSACTION (a mapper event, so every writer is covered: the consolidation, an edit through the API, a tool, a background job), and anything stale is rebuilt on the next
read. A page also expires after a few hours, because time passing changes what is "still ahead" (the dentist at 15:30 is behind you at 16:00).
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional, Sequence

from sqlalchemy import event, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.brief import Brief
from src.models.note import Note
from src.models.world import LedgerItem, utc_now

EXPIRES_AFTER = timedelta(hours=3)


def _mark_stale(mapper, connection, target) -> None:
    ws, owner = getattr(target, "honcho_workspace_id", None), getattr(target, "owner_peer_id", None)
    if ws is None or owner is None:
        return
    connection.execute(update(Brief.__table__).where(Brief.honcho_workspace_id == ws, Brief.owner_peer_id == owner).values(dirty=True))


for _model in (Note, LedgerItem):
    for _name in ("after_insert", "after_update", "after_delete"):
        event.listen(_model, _name, _mark_stale)


def _payload(row: Brief, cached: bool) -> Dict[str, Any]:
    return {"part": row.part, "date": row.day, "text": row.text, "sections": json.loads(row.sections_json or "{}"), "version": row.version,
            "built_at": row.built_at.isoformat(), "reason": row.reason, "cached": cached}


async def get(db: AsyncSession, ws: str, owner: str, now: datetime, ledger_rows: Sequence[Any], part: Optional[str] = None, force: bool = False) -> Dict[str, Any]:
    """The current brief for this person and part of the day: the cached page when it is still good, otherwise rebuilt (and stored)."""
    from src.services import notes
    part = part if part in notes.PARTS else notes.day_part(now.hour)
    day = now.date().isoformat()
    row = (await db.execute(select(Brief).where(Brief.honcho_workspace_id == ws, Brief.owner_peer_id == owner, Brief.day == day, Brief.part == part))).scalars().first()
    if row is not None and not force and not row.dirty and (utc_now() - row.built_at) < EXPIRES_AFTER:
        return _payload(row, True)
    reason = "forced" if force else "first" if row is None else "changed" if row.dirty else "expired"
    built = await notes.brief(db, ws, owner, now, ledger_rows, part)
    if row is None:
        row = Brief(honcho_workspace_id=ws, owner_peer_id=owner, day=day, part=part)
        db.add(row)
    else:
        row.version += 1
    row.text, row.sections_json = built["text"], json.dumps(built["sections"])
    row.dirty, row.reason, row.built_at = False, reason, utc_now()
    await db.commit()
    return _payload(row, False)


async def prepare_day(db: AsyncSession, ws: str, owner: str, now: datetime, ledger_rows: Sequence[Any]) -> int:
    """Have all three parts of today ready (the end of a consolidation calls this, so the next read is a cache hit)."""
    from src.services import notes
    n = 0
    for part in notes.PARTS:
        out = await get(db, ws, owner, now, ledger_rows, part)
        n += 0 if out["cached"] else 1
    return n
