"""Unattended independent-sitting opportunities for Sophie.

The scheduler offers an opportunity; Sophie decides whether and how to use it
— including stopping immediately with nothing to show. A scheduled sitting is
autonomous execution, not autonomous initiative: the distinction is preserved
by never nudging her toward activity (no topic weighting, no minimum output).

Eligibility per tick: scheduler enabled, owner allowlisted, daily cap unmet,
outside quiet hours, no sitting/consolidation currently running, user not
active recently. Everything is env-configurable; defaults do nothing.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, time, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import async_session_maker
from src.models.operational_state import TurnStamp
from src.models.world import MemoryRun
from src.services import exploration
from src.services.exploration import SoloBudget

logger = logging.getLogger(__name__)


def _int(env: str, default: int) -> int:
    try:
        return int(os.getenv(env, str(default)))
    except ValueError:
        return default


def config() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("SOPHIE_SOLO_SCHEDULER", "false").strip().lower() in ("1", "true", "yes", "on"),
        "workspace_id": os.getenv("SOPHIE_SOLO_WORKSPACE", "llm-test-agent"),
        "owners": [o.strip() for o in os.getenv("SOPHIE_SOLO_OWNERS", "").split(",") if o.strip()],
        "max_per_day": _int("SOPHIE_SOLO_MAX_PER_DAY", 2),
        "tick_seconds": _int("SOPHIE_SOLO_TICK_SECONDS", 900),
        "quiet_start": _int("SOPHIE_SOLO_QUIET_START_H", 23),
        "quiet_end": _int("SOPHIE_SOLO_QUIET_END_H", 7),
        "user_active_minutes": _int("SOPHIE_SOLO_USER_ACTIVE_MIN", 30),
    }


async def sittings_today(db: AsyncSession, workspace_id: str, owner: str, now: datetime) -> int:
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    rows = (await db.execute(select(MemoryRun).where(
        MemoryRun.honcho_workspace_id == workspace_id,
        MemoryRun.owner_peer_id == owner,
        MemoryRun.session_id.like("solo:%"),
        MemoryRun.created_at >= day_start))).scalars().all()
    return len(rows)


async def anything_running(db: AsyncSession, workspace_id: str, owner: str) -> Optional[str]:
    row = (await db.execute(select(MemoryRun).where(
        MemoryRun.honcho_workspace_id == workspace_id,
        MemoryRun.owner_peer_id == owner,
        MemoryRun.status == "running").order_by(MemoryRun.created_at.desc()).limit(1))).scalars().first()
    return row.session_id if row is not None else None


async def last_user_turn(db: AsyncSession, workspace_id: str, owner: str) -> Optional[datetime]:
    return (await db.execute(select(TurnStamp.turn_at).where(
        TurnStamp.honcho_workspace_id == workspace_id,
        TurnStamp.owner_peer_id == owner).order_by(TurnStamp.turn_at.desc()).limit(1))).scalar()


def in_quiet_hours(now: datetime, start_h: int, end_h: int) -> bool:
    h = now.hour
    return (h >= start_h or h < end_h) if start_h > end_h else (start_h <= h < end_h)


async def eligibility(db: AsyncSession, *, workspace_id: str, owner: str, now: Optional[datetime] = None) -> Tuple[bool, str, Dict[str, Any]]:
    """Would an opportunity be offered right now? Returns (eligible, reason, facts)."""
    cfg = config()
    now = now or datetime.now(timezone.utc)
    facts: Dict[str, Any] = {"now": now.isoformat(), "owner": owner}
    if not cfg["enabled"]:
        return False, "scheduler_disabled", facts
    if owner not in cfg["owners"]:
        return False, "owner_not_allowlisted", facts
    if in_quiet_hours(now, cfg["quiet_start"], cfg["quiet_end"]):
        return False, f"quiet_hours_{cfg['quiet_start']}-{cfg['quiet_end']}utc", facts
    running = await anything_running(db, workspace_id, owner)
    facts["running"] = running
    if running:
        return False, f"already_running:{running}", facts
    n = await sittings_today(db, workspace_id, owner, now)
    facts["sittings_today"] = n
    if n >= cfg["max_per_day"]:
        return False, f"daily_cap_{n}/{cfg['max_per_day']}", facts
    last = await last_user_turn(db, workspace_id, owner)
    facts["last_user_turn"] = last.isoformat() if last else None
    if last is not None:
        age_min = (now.replace(tzinfo=None) - last).total_seconds() / 60.0
        facts["user_idle_minutes"] = round(age_min, 1)
        if age_min < cfg["user_active_minutes"]:
            return False, f"user_active_{round(age_min, 1)}min_ago", facts
    return True, "eligible", facts


async def offer_once(*, workspace_id: str, owner: str, sitting_id: Optional[str] = None) -> Dict[str, Any]:
    """Run one bounded opportunity inline (operator/scheduler use). Consolidates
    only substantive sittings; a stop-immediately sitting is recorded declined."""
    import uuid as _uuid
    sitting_id = (sitting_id or f"solo-{_uuid.uuid4().hex[:8]}").strip()
    async with async_session_maker() as db:
        try:
            return await exploration.run_independent_sitting(
                db, workspace_id=workspace_id, owner=owner, sitting_id=sitting_id,
                budget=SoloBudget(
                    max_iterations=_int("SOPHIE_SOLO_ITERATIONS", 8),
                    max_tool_calls=_int("SOPHIE_SOLO_TOOL_CALLS", 10),
                    max_model_calls=_int("SOPHIE_SOLO_MODEL_CALLS", 12)))
        except Exception as exc:
            logger.exception("scheduled solo opportunity failed for %s", owner)
            try:
                await db.rollback()
            except Exception:
                pass
            return {"sitting_id": sitting_id, "status": "failed", "error": type(exc).__name__}


async def tick() -> List[Dict[str, Any]]:
    """One scheduler pass over all allowlisted owners. Returns per-owner outcomes."""
    cfg = config()
    if not cfg["enabled"]:
        return []
    outcomes = []
    for owner in cfg["owners"]:
        try:
            async with async_session_maker() as db:
                ok, reason, facts = await eligibility(db, workspace_id=cfg["workspace_id"], owner=owner)
        except Exception as exc:
            logger.warning("solo tick eligibility failed open for %s: %s", owner, exc)
            continue
        if not ok:
            outcomes.append({"owner": owner, "offered": False, "reason": reason, "facts": facts})
            continue
        import uuid as _uuid
        sitting_id = f"solo-{_uuid.uuid4().hex[:8]}"
        logger.info("[solo-scheduler] offering %s to %s", sitting_id, owner)
        result = await offer_once(workspace_id=cfg["workspace_id"], owner=owner, sitting_id=sitting_id)
        outcomes.append({"owner": owner, "offered": True, "reason": "eligible", "facts": facts, "result": result})
    return outcomes


async def run_forever() -> None:
    import asyncio
    while True:
        try:
            await tick()
        except Exception:
            logger.exception("solo scheduler tick failed (next tick retries)")
        await asyncio.sleep(max(60, config()["tick_seconds"]))
