"""Export and delete one person's memory in one product: every Cortex table that stores data about an owner.

Scope: DISCOVERED from the schema, not listed by hand: every table with an `owner_peer_id` column (the memory pipeline, connected understanding, and the older
interpretation/expectation/world tables that predate them: a real account had rows in ~33 of them, and a hand-written list had covered 13). Within a table a row is
this person's if `owner_peer_id` matches and, where the table has a `honcho_workspace_id`, the product workspace matches too. The product workspace comes from the caller's
credential, so one product can neither export nor delete another's data. Older tables without a workspace column are guarded by the owner-id convention (Runtime
qualifies every non-default product's owner: `bloom-<id>` / `user_bloom-<id>`), so a Sophie credential cannot name a Bloom owner.

NOT covered here: the Runtime's own stores and Honcho, which live in other systems; `companion-runtime` `erase_user` removes them and then calls this. See docs/DATA_LIFECYCLE.md.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, List
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import SQLModel

import src.models  # noqa: F401  (registers every table)
from src.services import product_memory, product_scope

NOT_COVERED = ["Honcho conversation evidence and derived conclusions", "Runtime turn logs, sitting state, mirrored messages", "database backups"]
EXPORT_ROW_CAP = 5000


def owner_tables():
    return [t for t in SQLModel.metadata.sorted_tables if "owner_peer_id" in t.c]


def _plain(v: Any) -> Any:
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, UUID):
        return str(v)
    if isinstance(v, (bytes, bytearray)):
        return None
    return v


def check_owner_for_product(product: str, owner: str) -> None:
    """Tables without a workspace column are keyed by owner alone, so the owner id must belong to the caller's product."""
    o = owner[5:] if owner.startswith("user_") else owner
    others = [p for p in product_memory.known() if p != product_scope.DEFAULT_PRODUCT]
    if product == product_scope.DEFAULT_PRODUCT:
        if any(o.startswith(p + "-") for p in others):
            raise HTTPException(status_code=403, detail="this owner belongs to another product")
    elif not o.startswith(product + "-"):
        raise HTTPException(status_code=403, detail=f"owner is not a {product} owner")


def _where(t, ws: str, owner: str):
    cond = [t.c.owner_peer_id == owner]
    if "honcho_workspace_id" in t.c:
        cond.append(t.c.honcho_workspace_id == ws)
    return cond


async def export_owner(db: AsyncSession, ws: str, owner: str) -> Dict[str, Any]:
    out: Dict[str, Any] = {"workspace": ws, "owner": owner, "exported_at": datetime.utcnow().isoformat(), "not_covered": NOT_COVERED, "tables": {}, "truncated": []}
    for t in owner_tables():
        rows = (await db.execute(select(t).where(*_where(t, ws, owner)).limit(EXPORT_ROW_CAP + 1))).mappings().all()
        if len(rows) > EXPORT_ROW_CAP:
            out["truncated"].append(t.name)
            rows = rows[:EXPORT_ROW_CAP]
        if rows:
            out["tables"][t.name] = [{k: _plain(v) for k, v in r.items()} for r in rows]
    return out


async def delete_owner(db: AsyncSession, ws: str, owner: str) -> Dict[str, int]:
    """Hard delete. Returns rows removed per table (only tables that had rows). Caller must have verified the confirmation and the owner/product match."""
    counts: Dict[str, int] = {}
    for t in owner_tables():
        res = await db.execute(delete(t).where(*_where(t, ws, owner)))
        if res.rowcount:
            counts[t.name] = int(res.rowcount)
    return counts


async def residue(db: AsyncSession, ws: str, owner: str) -> Dict[str, int]:
    """Rows still held for this person (for verifying an erasure)."""
    from sqlalchemy import func
    left: Dict[str, int] = {}
    for t in owner_tables():
        n = (await db.execute(select(func.count()).select_from(t).where(*_where(t, ws, owner)))).scalar() or 0
        if n:
            left[t.name] = int(n)
    return left
