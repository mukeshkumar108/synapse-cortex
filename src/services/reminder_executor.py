"""Reminder executor: the production firing path for persisted reminder
windows. Reminder intent is stored on expectations as
[{start, end, label}] (naive UTC). Nothing previously fired them. This scans
for due windows, marks them fired deterministically (so a reminder fires
exactly once), and returns the due items for delivery by the app/runtime.
State update and optional follow-up live with the caller; the executor owns
the schedule truth."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Dict, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.expectation import Expectation, OutcomeState


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


async def due_reminders(db: AsyncSession, *, workspace_id: str, owner_peer_id: str,
                        now: datetime) -> List[Dict[str, Any]]:
    """Scan the owner's active expectations for reminder windows that are due
    (start <= now, window still open or just closed within grace) and not yet
    fired. Marks fired windows deterministically and returns the due items."""
    now = _naive(now)
    rows = (await db.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.owner_peer_id == owner_peer_id,
        Expectation.outcome_state == OutcomeState.UNKNOWN,
        Expectation.reminder_windows_json.is_not(None),
    ))).scalars().all()

    due: List[Dict[str, Any]] = []
    grace_hours = 6.0
    for exp in rows:
        try:
            windows = json.loads(exp.reminder_windows_json or "[]")
        except (TypeError, ValueError):
            continue
        if not isinstance(windows, list):
            continue
        changed = False
        for w in windows:
            if not isinstance(w, dict) or w.get("fired"):
                continue
            start = w.get("start")
            if not start:
                continue
            try:
                start_dt = _naive(datetime.fromisoformat(str(start)))
            except ValueError:
                continue
            end = w.get("end")
            try:
                end_dt = _naive(datetime.fromisoformat(str(end))) if end else None
            except ValueError:
                end_dt = None
            is_due = start_dt <= now and (end_dt is None or now <= end_dt or (now - end_dt).total_seconds() <= grace_hours * 3600)
            if is_due:
                w["fired"] = True
                w["fired_at"] = now.isoformat()
                changed = True
                due.append({
                    "expectation_id": str(exp.id),
                    "title": exp.title[:200],
                    "summary": (exp.summary or "")[:200],
                    "window_label": w.get("label") or "",
                    "window_start": start,
                    "source_object_id": exp.source_object_id,
                    "source_system": exp.source_system,
                })
        if changed:
            exp.reminder_windows_json = json.dumps(windows)
            db.add(exp)
    if due:
        await db.commit()
    return due
