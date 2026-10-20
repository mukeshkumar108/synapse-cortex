"""Export and delete one person's memory in one product (the controls a person is owed over what is kept about them).

Scope: exactly the tables the memory pipeline and connected-understanding layer write, keyed by (product workspace, owner). The product
workspace is derived from the caller's credential at the request boundary, so one product can neither export nor delete another's data.

NOT covered (stated, not hidden): raw conversation evidence mirrored to Honcho, the Runtime's own stores (turn logs, sitting state), and the
legacy tables in this database that predate the memory pipeline. A complete erasure also needs those removed; see docs/IMPLEMENTATION_STATUS.md.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Dict, List, Type
from uuid import UUID

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.known_world import CueExposure, KnownEntity, KnownEntityAlias, KnownLink
from src.models.world import AttentionAction, AttentionEvent, ContinuingArc, LedgerItem, MemoryRun, NotebookPage, SittingPreparation
from src.models.companion_work import CompanionWork, CompanionWorkEvent

TABLES: List[Type] = [LedgerItem, NotebookPage, ContinuingArc, SittingPreparation, AttentionAction, AttentionEvent, MemoryRun,
                      KnownEntity, KnownEntityAlias, KnownLink, CueExposure, CompanionWork, CompanionWorkEvent]
NOT_COVERED = ["Honcho raw conversation evidence", "Runtime turn logs and sitting state", "legacy pre-pipeline tables"]


def _plain(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    return v


def _where(model: Type, ws: str, owner: str):
    return (model.honcho_workspace_id == ws, model.owner_peer_id == owner)


async def export_owner(db: AsyncSession, ws: str, owner: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"workspace": ws, "owner": owner, "exported_at": datetime.utcnow().isoformat(), "not_covered": NOT_COVERED, "tables": {}}
    for m in TABLES:
        rows = (await db.execute(select(m).where(*_where(m, ws, owner)))).scalars().all()
        out["tables"][m.__tablename__] = [{k: _plain(v) for k, v in r.model_dump().items()} for r in rows]
    return out


async def delete_owner(db: AsyncSession, ws: str, owner: str) -> Dict[str, int]:
    """Hard delete. Returns rows removed per table. Caller must have verified the confirmation."""
    counts: Dict[str, int] = {}
    for m in TABLES:
        res = await db.execute(delete(m).where(*_where(m, ws, owner)))
        counts[m.__tablename__] = int(res.rowcount or 0)
    return counts
