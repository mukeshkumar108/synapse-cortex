"""Cross-process lease for one world. A world's canonical state is mutated by at most one interpretation at a time, across every Cortex process.
Mechanics only: an atomic claim of a row that is free or expired; waiting is bounded polling; the holder releases on completion and the expiry
recovers a crashed holder."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.world import WorldLease

LEASE_TTL_SECONDS = 420          # longer than the interpreter timeout plus materialisation
POLL_SECONDS = 1.5


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def lease_key(workspace_id: str, owner: str) -> str:
    return f"{workspace_id}|{owner}"


async def try_acquire(db: AsyncSession, key: str, holder: str, *, ttl: int = LEASE_TTL_SECONDS) -> bool:
    now = _now()
    taken = await db.execute(update(WorldLease).where(WorldLease.key == key, WorldLease.expires_at < now).values(
        holder=holder, acquired_at=now, expires_at=now + timedelta(seconds=ttl)))
    if taken.rowcount:
        await db.commit()
        return True
    try:
        db.add(WorldLease(key=key, holder=holder, acquired_at=now, expires_at=now + timedelta(seconds=ttl)))
        await db.commit()
        return True
    except IntegrityError:
        await db.rollback()
        return False


async def acquire(db: AsyncSession, key: str, holder: str, *, wait_seconds: float = 30.0, ttl: int = LEASE_TTL_SECONDS) -> bool:
    deadline = _now() + timedelta(seconds=wait_seconds)
    while True:
        if await try_acquire(db, key, holder, ttl=ttl):
            return True
        if _now() >= deadline:
            return False
        await asyncio.sleep(POLL_SECONDS)


async def release(db: AsyncSession, key: str, holder: str) -> None:
    try:
        await db.rollback()
        await db.execute(delete(WorldLease).where(WorldLease.key == key, WorldLease.holder == holder))
        await db.commit()
    except Exception:            # the expiry recovers a lease we could not release
        await db.rollback()
