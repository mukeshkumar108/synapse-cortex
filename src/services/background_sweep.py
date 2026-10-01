"""Background watcher: inspect AttentionState, detect change, decide.

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


def _eligible_set(state: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Newly-watchable items from AttentionState: due reminders/pending daily
    occurrences, planned events, and follow-up-eligible outcomes/clarifications.
    Deterministic from state provenance — never content inspection."""
    pool: List[Dict[str, Any]] = []

    def add(section: str, kind: str, item: Dict[str, Any], ident: Any = None) -> None:
        pool.append({"section": section, "kind": kind,
                     "id": str(ident if ident is not None else item.get("id") or ""),
                     "title": str(item.get("title") or item.get("topic") or "")[:160]})

    for item in state.get("commitments") or []:
        if item.get("state") in ("reminder_due", "overdue"):
            add("reminder", "reminder", item)
    for item in state.get("recurring_intentions") or []:
        if item.get("occurrence_status") == "pending" and item.get("occurrence_id"):
            add("reminder", "occurrence", {"title": f"recurring occurrence {item.get('user_day')}"},
                item["occurrence_id"])
    for item in state.get("events") or []:
        add("calendar", "event", item)
    for key in ("active_expectations", "elapsed_expectations"):
        for item in state.get(key) or []:
            if item.get("expectation_type") == "planned_event":
                add("calendar", "expectation", item)
    for key in ("followups", "window_elapsed_unknown"):
        for item in state.get(key) or []:
            add("follow_up", "expectation", item)
    for item in state.get("clarifications") or []:
        add("follow_up", "clarification", item)
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
    from src.services.attention_state_service import AttentionStateService

    state = await AttentionStateService().compile_attention_state(
        db=db, workspace_id=workspace_id, session_id=session_id, now=now,
        timezone_str=timezone_str, owner_peer_id=owner_peer_id)
    current = _eligible_set(state)
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
