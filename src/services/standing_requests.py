"""Standing requests: what the person has asked of the companion about how to talk or behave ("don't call me babe", "fewer questions"), in their own
terms. A durable, owner-scoped, typed store with a lifecycle (active -> withdrawn), not prose inside a summary, so no length cap or rewrite can lose one.

SCOPE. A request is either `standing` (no time frame: "no diet advice", "don't call me babe": lives until withdrawn) or `sitting` (bound to the conversation it was
made in: "keep me focused this afternoon", "just listen for now"). The Runtime owns what a sitting is and hands Cortex an opaque `sitting_ref`; a sitting-scoped request is
visible only to that ref, so it ends with the sitting by construction (a read filter, no timer and no dependence on when the interpreter runs). Writers that supply no ref
(the interpreter runs after the sitting has ended) cannot create sitting-scoped requests: the instruction is over, so it is dropped rather than promoted.

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
    scope: str = Field(default="standing", nullable=False)                  # standing | sitting
    sitting_ref: Optional[str] = Field(default=None, index=True)            # the Runtime's sitting id; set only for scope == sitting


def _key(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(text).lower()).strip()


async def _active_rows(db: AsyncSession, workspace_id: str, owner: str) -> List[StandingRequest]:
    return list((await db.execute(select(StandingRequest).where(
        StandingRequest.honcho_workspace_id == workspace_id, StandingRequest.owner_peer_id == owner,
        StandingRequest.status == "active").order_by(StandingRequest.created_at))).scalars().all())


async def active(db: AsyncSession, workspace_id: str, owner: str) -> List[str]:
    """The durable (standing) requests only."""
    if not owner:
        return []
    return [r.text for r in await _active_rows(db, workspace_id, owner) if (r.scope or "standing") == "standing"]


async def active_sitting(db: AsyncSession, workspace_id: str, owner: str, sitting_ref: Optional[str]) -> List[str]:
    """Requests made for exactly this sitting (empty without a ref)."""
    if not owner or not sitting_ref:
        return []
    return [r.text for r in await _active_rows(db, workspace_id, owner) if r.scope == "sitting" and r.sitting_ref == sitting_ref]


async def visible(db: AsyncSession, workspace_id: str, owner: str, sitting_ref: Optional[str]) -> List[dict]:
    """What a pass in this sitting should see as already held: [{text, scope}]."""
    return ([{"text": t, "scope": "standing"} for t in await active(db, workspace_id, owner)]
            + [{"text": t, "scope": "sitting"} for t in await active_sitting(db, workspace_id, owner, sitting_ref)])


def _normalise(desired: list) -> List[tuple]:
    """Accepts plain strings (standing) or {text, scope} objects; returns [(text, scope)]."""
    out = []
    for item in desired or []:
        if isinstance(item, dict):
            text, scope = item.get("text"), str(item.get("scope") or "standing").lower()
        else:
            text, scope = item, "standing"
        if text:
            out.append((str(text), "sitting" if scope.startswith("sit") else "standing"))
    return out


async def sync(db: AsyncSession, workspace_id: str, owner: str, desired: List[str], *, source: str,
             revise: bool = False, now: Optional[datetime] = None, timezone_str: str = "UTC", sitting_ref: Optional[str] = None) -> dict:
    """Make the active set equal `desired`: new texts are created, active ones no longer listed are withdrawn (kept for history), a listed one that was
    withdrawn is reopened. Callers pass the full list only when they actually produced one (an omitted field means 'no change').

    With revise=True, record-first routing applies before storing: a candidate that is a dated
    correction of an open event/expectation revises that record (evidence attached) and is NOT
    stored as prose; genuine preferences and unmatchable texts store exactly as before. The
    receipt gains revised/already_current lists. Nothing is ever silently dropped."""
    if not owner:
        return {"created": 0, "withdrawn": 0}
    revised: list = []
    already: list = []
    pairs = _normalise(desired)
    scope_of = {" ".join(t.split())[:240]: sc for t, sc in pairs}
    texts = [t for t, _ in pairs]
    if revise and texts:
        from src.services import record_revision as _rr
        routed = await _rr.route_corrections(db, workspace_id, owner, texts, now=now or _now(), timezone_str=timezone_str)
        texts = routed["prose_kept"]
        revised, already = routed["revised"], routed["already_current"]
    wanted = {}
    for text in texts:
        text = " ".join(str(text).split())[:240]
        if not (text and _key(text)) or _key(text) in wanted:
            continue
        scope = scope_of.get(text, "standing")
        if scope == "sitting" and not sitting_ref:
            continue                 # the sitting this was for has ended (or has no identity): an expired instruction is dropped, never promoted to a standing one
        wanted[_key(text)] = (text, scope)
    wanted = dict(list(wanted.items())[:MAX_ACTIVE])
    rows = (await db.execute(select(StandingRequest).where(
        StandingRequest.honcho_workspace_id == workspace_id, StandingRequest.owner_peer_id == owner))).scalars().all()
    by_key = {r.key: r for r in rows}
    created = withdrawn = 0
    now = _now()
    for k, (text, scope) in wanted.items():
        ref = sitting_ref if scope == "sitting" else None
        row = by_key.get(k)
        if row is None:
            db.add(StandingRequest(honcho_workspace_id=workspace_id, owner_peer_id=owner, text=text, key=k, source=source, scope=scope, sitting_ref=ref))
            created += 1
        elif row.status != "active":
            row.status, row.withdrawn_at, row.updated_at, row.text, row.scope, row.sitting_ref = "active", None, now, text, scope, ref
            db.add(row)
            created += 1
        elif (row.scope or "standing") != scope or row.sitting_ref != ref:
            row.scope, row.sitting_ref, row.updated_at = scope, ref, now          # the same words restated in another scope (or in a later sitting) take that scope
            db.add(row)
    for k, row in by_key.items():
        if row.scope == "sitting" and row.sitting_ref != sitting_ref:
            continue                 # another sitting's request is not this writer's to withdraw (the read filter already hides it)
        if row.status == "active" and k not in wanted:
            row.status, row.withdrawn_at, row.updated_at = "withdrawn", now, now
            db.add(row)
            withdrawn += 1
    await db.commit()
    receipt: dict = {"created": created, "withdrawn": withdrawn}
    if revise:
        receipt["revised"] = revised
        receipt["already_current"] = already
    return receipt
