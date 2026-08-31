"""Initiative engine: decides whether Sophie should appear unprompted.

This is a PRODUCTION capability (driven by cron/scheduler in the app, and by
the scenario harness). Deterministic policy owns the decision:
  - the live agenda's top item must carry real pressure (>= high threshold)
  - quiet hours are respected (unless the item is acute)
  - a spam budget caps proactive appearances per local day
  - a minimum cadence gap applies between proactive appearances
  - suppressions were already excluded from the agenda upstream
Every decision (appeared or withheld, with reason) is written to the
proactive ledger. "Nothing worth pushing right now" is a first-class outcome.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from zoneinfo import ZoneInfo

from src.models.operational_state import ProactiveLog


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


DEFAULT_POLICY = {
    "quiet_hours": [22, 8],          # local hours [start, end) where proactive is off
    "min_gap_hours": 4.0,            # minimum cadence between proactive appearances
    "max_per_day": 2,                # spam budget per local day
    "pressure_threshold": 0.6,       # agenda item pressure needed to appear
}


def _high_pressure_items(agenda: List[Dict[str, Any]], threshold: float) -> List[Dict[str, Any]]:
    out = []
    for item in agenda or []:
        pressure = item.get("pressure")
        if isinstance(pressure, str):
            pressure = {"high": 0.8, "medium": 0.45, "low": 0.2}.get(pressure, 0.2)
        if float(pressure or 0) >= threshold and item.get("status") == "unresolved":
            out.append(item)
    return out


async def evaluate_initiative(
    db: AsyncSession, *, workspace_id: str, owner_peer_id: str,
    agenda: List[Dict[str, Any]], now: datetime, timezone_str: str,
    policy: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Product decision: should Sophie appear unprompted right now, and with
    what? Deterministic, ledgered, and boring by design."""
    now = _naive(now)
    policy = {**DEFAULT_POLICY, **(policy or {})}
    try:
        local_hour = now.astimezone(ZoneInfo(timezone_str)).hour
        local_day = now.astimezone(ZoneInfo(timezone_str)).date().isoformat()
    except Exception:
        local_hour, local_day = now.hour, now.date().isoformat()

    def ledger(decision: str, item_key: Optional[str] = None, reason: str = "") -> Dict[str, Any]:
        db.add(ProactiveLog(honcho_workspace_id=workspace_id, owner_peer_id=owner_peer_id,
                            at=now, item_key=item_key, reason=reason[:200], decision=decision))
        return {"should_appear": decision == "appeared", "reason": reason,
                "item": None, "local_hour": local_hour}

    high = _high_pressure_items(agenda, float(policy["pressure_threshold"]))
    if not high:
        return ledger("withheld:no_pressing_item", reason="no agenda item carries enough pressure right now")
    if policy["quiet_hours"][0] <= local_hour or local_hour < policy["quiet_hours"][1]:
        if high[0].get("severity") != "acute":
            return ledger("withheld:quiet_hours", item_key=high[0].get("what", "")[:80],
                          reason=f"local hour {local_hour} is inside quiet hours")
    since = now - timedelta(hours=float(policy["min_gap_hours"]))
    recent = (await db.execute(select(ProactiveLog).where(
        ProactiveLog.honcho_workspace_id == workspace_id,
        ProactiveLog.owner_peer_id == owner_peer_id,
        ProactiveLog.at >= since,
        ProactiveLog.decision == "appeared",
    ))).scalars().all()
    if recent:
        return ledger("withheld:cadence_gap", item_key=high[0].get("what", "")[:80],
                      reason="proactive appearance inside minimum cadence gap")
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    todays = (await db.execute(select(ProactiveLog).where(
        ProactiveLog.honcho_workspace_id == workspace_id,
        ProactiveLog.owner_peer_id == owner_peer_id,
        ProactiveLog.at >= day_start,
        ProactiveLog.decision == "appeared",
    ))).scalars().all()
    if len(todays) >= int(policy["max_per_day"]):
        return ledger("withheld:daily_budget", reason="daily proactive budget exhausted")

    item = high[0]
    result = ledger("appeared", item_key=str(item.get("what", ""))[:80],
                    reason="high-pressure agenda item due for follow-up")
    result["item"] = item
    return result
