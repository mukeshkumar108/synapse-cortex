"""Standing requests: what the person has asked of the companion about how to talk or behave ("don't call me babe", "fewer questions"), in their own
terms. A durable, owner-scoped, typed store with a lifecycle (active -> withdrawn), not prose inside a summary, so no length cap or rewrite can lose one.

Writers (both use `sync`, full-list semantics): the fast scene pass (within an exchange or two) and the world interpreter (at its boundaries, seeing the
current list so it can keep, add or withdraw). Reader: the per-turn probe. Scope is the world owner, so nothing crosses a world."""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel, select
from sqlalchemy.ext.asyncio import AsyncSession

MAX_ACTIVE = 12


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class StandingRequest(SQLModel, table=True):
    __tablename__ = "standing_requests"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    text: str = Field(nullable=False)
    key: str = Field(index=True, nullable=False)                 # normalised text: the identity used to recognise the same request
    status: str = Field(default="active", index=True, nullable=False)       # active | withdrawn
    source: str = Field(default="scene_pass", nullable=False)               # scene_pass | interpreter
    created_at: datetime = Field(default_factory=_now, nullable=False)
    updated_at: datetime = Field(default_factory=_now, nullable=False)
    withdrawn_at: Optional[datetime] = Field(default=None)


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


async def active(db: AsyncSession, workspace_id: str, owner: str) -> List[str]:
    if not owner:
        return []
    rows = (await db.execute(select(StandingRequest).where(
        StandingRequest.honcho_workspace_id == workspace_id, StandingRequest.owner_peer_id == owner,
        StandingRequest.status == "active").order_by(StandingRequest.created_at))).scalars().all()
    return [r.text for r in rows]


async def sync(db: AsyncSession, workspace_id: str, owner: str, desired: List[str], *, source: str) -> dict:
    """Make the active set equal `desired`: new texts are created, active ones no longer listed are withdrawn (kept for history), a listed one that was
    withdrawn is reopened. Callers pass the full list only when they actually produced one (an omitted field means 'no change')."""
    if not owner:
        return {"created": 0, "withdrawn": 0}
    wanted = {}
    for text in desired:
        text = " ".join(str(text).split())[:240]
        if text and _key(text) and _key(text) not in wanted:
            wanted[_key(text)] = text
    wanted = dict(list(wanted.items())[:MAX_ACTIVE])
    rows = (await db.execute(select(StandingRequest).where(
        StandingRequest.honcho_workspace_id == workspace_id, StandingRequest.owner_peer_id == owner))).scalars().all()
    by_key = {r.key: r for r in rows}
    created = withdrawn = 0
    now = _now()
    for k, text in wanted.items():
        row = by_key.get(k)
        if row is None:
            db.add(StandingRequest(honcho_workspace_id=workspace_id, owner_peer_id=owner, text=text, key=k, source=source))
            created += 1
        elif row.status != "active":
            row.status, row.withdrawn_at, row.updated_at, row.text = "active", None, now, text
            db.add(row)
            created += 1
    for k, row in by_key.items():
        if row.status == "active" and k not in wanted:
            row.status, row.withdrawn_at, row.updated_at = "withdrawn", now, now
            db.add(row)
            withdrawn += 1
    await db.commit()
    return {"created": created, "withdrawn": withdrawn}
