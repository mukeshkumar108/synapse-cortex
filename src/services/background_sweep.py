"""Background watcher: inspect views, detect change, decide.

Pattern: snapshot the eligible proactive set into a DerivedSignal row, diff
against the previous snapshot, and return newly-eligible items for the
proactive scheduler. No user query needed — this is how proactivity
originates ("what should I care about right now?") without compiling a life
into a prompt.

Prediction/action/outcome/evaluation stay separate rows; history is never
rewritten. Most of this never reaches foreground turns.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

WATCH_KIND = "background_watch"
MAX_WATCH_ITEMS = 8


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _eligible_set(views: Dict[str, List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    pool = []
    for section in ("reminder", "calendar", "follow_up", "waiting_on",
                    "conversation_opportunity"):
        for item in views.get(section, []) or []:
            if not isinstance(item, dict):
                continue
            signals = item.get("signals", {}) or {}
            if signals.get("urgent") or signals.get("actionable"):
                pool.append({
                    "section": section,
                    "kind": str(item.get("kind") or ""),
                    "id": str(item.get("id") or ""),
                    "title": str(item.get("title") or "")[:160],
                })
    seen, out = set(), []
    for item in pool:
        key = (item["section"], item["kind"], item["id"] or item["title"])
        if key in seen:
            continue
        seen.add(key)
        out.append({**item, "key": hashlib.sha1(
            "|".join(key).encode()).hexdigest()[:12]})
    return out[:MAX_WATCH_ITEMS * 2]


async def background_sweep(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    owner_peer_id: Optional[str],
    now: datetime,
    timezone_str: str = "UTC",
) -> Dict[str, Any]:
    """Diff current eligible set vs last snapshot. Returns newly eligible."""
    from src.models.derived_signal import DerivedSignal, DerivedSignalKind
    from src.services.state_views import compile_views

    views = await compile_views(
        db, workspace_id=workspace_id, session_id=session_id,
        owner_peer_id=owner_peer_id, now=now, timezone_str=timezone_str)
    current = _eligible_set(views)
    current_keys = {i["key"] for i in current}

    row = (await db.execute(select(DerivedSignal).where(
        DerivedSignal.honcho_workspace_id == workspace_id,
        DerivedSignal.honcho_session_id == session_id,
        DerivedSignal.kind == DerivedSignalKind.BACKGROUND_WATCH,
    ))).scalar_one_or_none()

    previous_keys: set = set()
    if row is not None:
        try:
            previous_keys = set(json.loads(row.payload_json or "{}").get("keys", []))
        except (ValueError, TypeError):
            previous_keys = set()

    new_items = [i for i in current if i["key"] not in previous_keys]
    snapshot = {"keys": sorted(current_keys),
                "at": _naive_utc(now).isoformat(),
                "count": len(current_keys)}
    try:
        if row is None:
            db.add(DerivedSignal(
                honcho_workspace_id=workspace_id,
                honcho_session_id=session_id,
                kind=DerivedSignalKind.BACKGROUND_WATCH,
                payload_json=json.dumps(snapshot),
                last_message_id=f"sweep:{_naive_utc(now).isoformat()}"))
        else:
            row.payload_json = json.dumps(snapshot)
            row.last_message_id = f"sweep:{_naive_utc(now).isoformat()}"
            row.updated_at = _naive_utc(now)
            db.add(row)
        await db.commit()
    except Exception as err:
        logger.warning("background sweep snapshot failed: %s", err)
        try:
            await db.rollback()
        except Exception:
            pass
    return {"new": new_items, "watched": len(current),
            "previous": len(previous_keys)}
