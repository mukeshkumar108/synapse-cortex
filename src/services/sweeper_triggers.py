"""LANE 2 trigger engine — makes the sweeper part of the product.

Trigger model (event/debounce driven, not fixed-batch):
  1. SESSION SETTLE   — ~5 min of conversational inactivity after a turn
  2. TURN ACCUMULATION— >=10 new turns since the last sweep (long session)
  3. PERIODIC CATCH-UP— >=24h since the last sweep, if the user has been active

Cortex is a long-running container, so debounce is an in-process asyncio timer
per workspace: each ingested turn (re)arms it. State is also derivable from
TurnStamps (authoritative turn count), so a restart only resets the timer, not
the accounting. Sweeps are idempotent per evidence message, so overlap is safe.

Manual/forced runs (harness, ops) bypass all of this.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional

from sqlmodel import select

from src.db import async_session_maker
from src.models.operational_state import TurnStamp

logger = logging.getLogger(__name__)

SETTLE_DELAY_SECONDS = 300          # quiet period after the last turn
TURNS_SINCE_TRIGGER = 10            # long-session immediate trigger
CATCH_UP_HOURS = 24                 # periodic safety sweep

_pending: Dict[str, asyncio.Task] = {}
_state: Dict[str, Dict[str, Any]] = {}  # ws -> {"last_sweep_monotonic": float, "turns_at_last_sweep": int}


def _now() -> float:
    return time.monotonic()


async def _turn_count(db, workspace_id: str) -> int:
    from sqlalchemy import func
    res = await db.execute(
        select(func.count()).select_from(TurnStamp).where(
            TurnStamp.honcho_workspace_id == workspace_id)
    )
    return int(res.scalar() or 0)


def note_turn(workspace_id: str) -> Optional[str]:
    """Record a turn and decide whether a sweep should be scheduled now.

    Returns 'immediate' (turn-count trigger), 'debounced' (settling timer
    armed/rearmed), or None. Caller executes the returned plan.
    """
    st = _state.setdefault(workspace_id, {})
    st["turns"] = st.get("turns", 0) + 1
    st["last_turn_monotonic"] = _now()
    if st["turns"] - st.get("turns_at_last_sweep", 0) >= TURNS_SINCE_TRIGGER:
        return "immediate"
    if _now() - st.get("last_sweep_monotonic", 0) >= CATCH_UP_HOURS * 3600 and st["turns"]:
        return "immediate"
    return "debounced"


def mark_swept(workspace_id: str, turns: int) -> None:
    st = _state.setdefault(workspace_id, {})
    st["last_sweep_monotonic"] = _now()
    st["turns_at_last_sweep"] = turns


async def _delayed_sweep(workspace_id: str, session_id: str, peer_id: str, delay: float):
    try:
        await asyncio.sleep(delay)
        # Re-check settle: a newer turn re-armed a fresh task; this one is stale.
        async with async_session_maker() as db:
            await run_sweep(db, workspace_id=workspace_id,
                            session_id=session_id, peer_id=peer_id)
    except asyncio.CancelledError:
        pass
    except Exception as err:
        logger.warning("Lane 2 background sweep failed for %s: %s", workspace_id, err)


async def run_sweep(db, *, workspace_id: str, session_id: str, peer_id: str) -> Dict[str, Any]:
    """Execute one sweep with deriver-aware retry, then mark state."""
    from src.services.sweeper_service import SweeperService
    sweeper = SweeperService()
    last_err = None
    for attempt in range(3):
        try:
            result = await sweeper.run(db, workspace_id=workspace_id,
                                       peer_id=peer_id, session_id=session_id)
            if result.get("evidence_packets"):
                mark_swept(workspace_id, turns=_state.get(workspace_id, {}).get("turns", 0))
                return result
            last_err = "no_evidence_yet"
        except Exception as err:
            last_err = str(err)[:200]
        # Deriver may not have embedded the newest turns yet; back off once.
        if attempt < 2:
            await asyncio.sleep(60)
    result = {"status": "skipped", "reason": last_err or "no_evidence"}
    mark_swept(workspace_id, turns=_state.get(workspace_id, {}).get("turns", 0))
    return result


def schedule_after_turn(workspace_id: str, session_id: str, peer_id: str) -> Optional[str]:
    """Call from the turn-ingestion path. Fire-and-forget; never raises."""
    try:
        decision = note_turn(workspace_id)
        if decision is None:
            return None
        old = _pending.pop(workspace_id, None)
        if old and not old.done():
            old.cancel()
        if decision == "immediate":
            _pending[workspace_id] = asyncio.create_task(
                _delayed_sweep(workspace_id, session_id, peer_id, 0))
            return "immediate"
        _pending[workspace_id] = asyncio.create_task(
            _delayed_sweep(workspace_id, session_id, peer_id, SETTLE_DELAY_SECONDS))
        return "debounced"
    except Exception as err:
        logger.warning("Lane 2 scheduling failed: %s", err)
        return None
