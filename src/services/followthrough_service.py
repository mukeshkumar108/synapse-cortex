"""Foreground admission control + follow-through ledger (Parts 3/4/6/7).

The backend holds everything; the foreground receives only what is admitted.

A. OWED / contractual: explicit accountability objectives (daily 10k, morning
   walk), adherence, Sophie-promised follow-ups. These cannot silently die:
   states are outstanding -> surfaced -> awaiting_answer -> resolved, with
   defer/suppress/recovery_due. Deferral never deletes; the ledger tracks
   last_surfaced, surface_count and next recovery window.
B. OPTIONAL / available: low-pressure relational threads, trips, patterns.
   They do not consume foreground bandwidth while owed work is unresolved.

Deterministic code computes states from occurrence ledger + agenda pressure.
No model involved in the admission decision.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.operational_state import RecurringOccurrence, TurnStamp


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _pressure(item: Dict[str, Any]) -> float:
    p = item.get("pressure")
    if isinstance(p, str):
        return {"high": 0.8, "medium": 0.5, "low": 0.2}.get(p, 0.2)
    return float(p or 0.2)


async def compute_admission(
    db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
    agenda_items: List[Dict[str, Any]], packet: Dict[str, Any],
    now: datetime, timezone_str: str,
) -> Dict[str, Any]:
    """Classify agenda items into OWED (admitted) vs OPTIONAL (held back),
    and attach follow-through ledger state to each owed item."""
    now = _naive(now)
    brief = packet.get("intelligence_brief") or {}
    daypart = str(brief.get("daypart") or "").lower()
    occ_by_id = {}
    for item in (packet.get("recurring_intentions") or []):
        if item.get("occurrence_id"):
            occ_by_id[str(item.get("occurrence_id"))] = item

    owed: List[Dict[str, Any]] = []
    optional: List[Dict[str, Any]] = []

    for item in (agenda_items or []):
        what = str(item.get("what") or "").strip()
        if not what:
            continue
        pressure = _pressure(item)
        occ_id = item.get("occurrence_id")
        occ = occ_by_id.get(str(occ_id)) if occ_id else None
        asks = int(occ.get("ask_count") if isinstance(occ, dict) else (occ.ask_count if occ else 0) or 0)
        status = "outstanding"
        if asks > 0:
            status = "awaiting_answer"
        if item.get("status") in ("resolved", "confirmed"):
            status = "resolved"

        entry = {
            "what": what,
            "occurrence_id": str(occ_id) if occ_id else None,
            "owner": item.get("owner", "user"),
            "semantic_type": item.get("semantic_type", "objective"),
            "followup_state": status,
            "surface_count": asks,
            "pressure": pressure,
            "next_move": str(item.get("next_move") or "")[:120],
        }
        # ADMISSION GATE: owed = contractual accountability objectives with
        # real pressure; everything else is optional capacity.
        if pressure >= 0.5 and status != "resolved":
            owed.append(entry)
        else:
            optional.append({"what": what[:80], "pressure": round(pressure, 2)})

    owed.sort(key=lambda x: (-x["pressure"], -x["surface_count"] * -0.0))
    owed = owed[:3]

    # LIVE SCENE: only what helps the foreground understand the current world.
    last_turn = (await db.execute(select(TurnStamp.turn_at).where(
        TurnStamp.honcho_workspace_id == workspace_id,
    ).order_by(TurnStamp.turn_at.desc()).limit(1))).scalar()
    elapsed_min = int((now - last_turn).total_seconds() / 60) if last_turn else None
    scene = {
        "time_of_day": daypart or "unknown",
        "minutes_since_last_user_turn": elapsed_min,
        "local_date": str(brief.get("user_day") or ""),
    }

    return {"owed": owed, "optional": optional, "scene": scene}
