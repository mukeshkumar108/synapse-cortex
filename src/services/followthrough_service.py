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
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.operational_state import RecurringOccurrence, TurnStamp


_FOREGROUND_TERMINAL = {
    "acknowledged_this_sitting",
    "scheduled_for_later",
    "resolved",
    "suppressed_until_event",
}


def _naive(dt):
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _as_naive_datetime(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return _naive(value)
    if isinstance(value, str):
        try:
            return _naive(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None


def _pressure(item: Dict[str, Any]) -> float:
    p = item.get("pressure")
    if isinstance(p, str):
        return {"high": 0.8, "medium": 0.5, "low": 0.2}.get(p, 0.2)
    return float(p or 0.2)


def _obligation_terms(value: Any) -> set[str]:
    stop = {"the", "a", "an", "daily", "today", "tomorrow", "goal", "objective", "my", "to", "per", "of"}
    return {
        token for token in re.findall(r"[a-z0-9]+", str(value or "").lower())
        if token not in stop and len(token) > 2
    }


def _same_obligation(left: Any, right: Any) -> bool:
    a, b = _obligation_terms(left), _obligation_terms(right)
    if not a or not b:
        return False
    return len(a & b) / min(len(a), len(b)) >= 0.6


async def compute_admission(
    db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
    agenda_items: List[Dict[str, Any]], packet: Dict[str, Any],
    now: datetime, timezone_str: str, current_turn: str = "",
) -> Dict[str, Any]:
    """Classify agenda items into OWED (admitted) vs OPTIONAL (held back),
    and attach follow-through ledger state to each owed item."""
    now = _naive(now)
    brief = packet.get("intelligence_brief") or {}
    daypart = str(brief.get("daypart") or "").lower()
    last_turn = (await db.execute(select(TurnStamp.turn_at).where(
        TurnStamp.honcho_workspace_id == workspace_id,
        *([TurnStamp.owner_peer_id == owner_peer_id] if owner_peer_id else []),
    ).order_by(TurnStamp.turn_at.desc()).limit(1))).scalar()

    occ_by_id = {}
    for item in (packet.get("recurring_intentions") or []):
        if item.get("occurrence_id"):
            occ_by_id[str(item.get("occurrence_id"))] = item

    owed: List[Dict[str, Any]] = []
    optional: List[Dict[str, Any]] = []
    seen_obligations: set[str] = set()
    recent_progress = packet.get("recent_progress") or []

    for item in (agenda_items or []):
        what = str(item.get("what") or "").strip()
        if not what:
            continue
        obligation_key = (
            f"occurrence:{item.get('occurrence_id')}"
            if item.get("occurrence_id")
            else "topic:" + " ".join(sorted(_obligation_terms(what)))
        )
        # Multiple source representations remain auditable in their canonical
        # tables, but only one representation may consume foreground pressure.
        if obligation_key in seen_obligations:
            continue
        seen_obligations.add(obligation_key)
        pressure = _pressure(item)
        occ_id = item.get("occurrence_id")
        occ = occ_by_id.get(str(occ_id)) if occ_id else None
        asks = int(occ.get("ask_count") if isinstance(occ, dict) else (occ.ask_count if occ else 0) or 0)
        status = "outstanding"
        asked_at = None
        if isinstance(occ, dict):
            asked_at = occ.get("asked_at")
        elif occ is not None:
            asked_at = occ.asked_at
        asked_at = _as_naive_datetime(asked_at)
        if asks > 0:
            status = "awaiting_answer"
            # The ask ledger records that foreground airtime was already spent.
            # Once the user has subsequently spoken, the item remains durable
            # but must leave the current conversational window. A later daily
            # occurrence or explicit recovery policy may admit it again; this
            # handover must not keep repeating the same ask in one sitting.
            if asked_at and last_turn and last_turn > asked_at:
                status = "acknowledged_this_sitting"
        if any(
            _same_obligation(what, progress.get("title"))
            or _same_obligation(what, progress.get("evidence"))
            for progress in recent_progress
            if isinstance(progress, dict)
        ):
            # Concrete supplied progress answers the conversational ask even
            # though the underlying daily objective is not complete.
            status = "acknowledged_this_sitting"
        if item.get("status") in ("resolved", "confirmed"):
            status = "resolved"
        elif item.get("status") in ("scheduled", "deferred"):
            status = "scheduled_for_later"
        elif item.get("status") in ("suppressed", "waiting_event"):
            status = "suppressed_until_event"
            trigger = str(item.get("next_move") or "").lower()
            turn = current_turn.lower()
            arrival_trigger = any(word in trigger for word in ("home", "get back", "through the door", "arriv"))
            arrival_evidence = bool(re.search(
                r"\b(?:i(?:'m| am) home|just got home|back home|through the door|i(?:'ve| have) arrived)\b",
                turn,
            ))
            if arrival_trigger and arrival_evidence:
                status = "outstanding"

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
        if pressure >= 0.5 and status not in _FOREGROUND_TERMINAL:
            owed.append(entry)
        else:
            optional.append({
                "what": what[:80],
                "pressure": round(pressure, 2),
                "followup_state": (
                    status if status in _FOREGROUND_TERMINAL else "optional_background"
                ),
            })

    owed.sort(key=lambda x: (-x["pressure"], -x["surface_count"] * -0.0))
    owed = owed[:3]

    # LIVE SCENE: only what helps the foreground understand the current world.
    elapsed_min = int((now - last_turn).total_seconds() / 60) if last_turn else None
    scene = {
        "time_of_day": daypart or "unknown",
        "minutes_since_last_user_turn": elapsed_min,
        "local_date": str(brief.get("user_day") or ""),
    }

    return {"owed": owed, "optional": optional, "scene": scene}
