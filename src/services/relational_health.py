"""Relational learning derivation: intention (recurrence) → attempt (occurrence)
→ outcome (completed) → gap (slipping).

Deterministic and bounded. The foreground gets one compact line, not the
occurrence ledger.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import List

from src.models.operational_state import OccurrenceStatus, RecurringIntention, RecurringOccurrence


def _week_start(user_day: date) -> date:
    return user_day - timedelta(days=user_day.weekday())


def week_target(recurrence: RecurringIntention) -> int:
    """Full-week expected occurrence count (daily=7, weekly=len(weekdays))."""
    if recurrence.cadence == "daily":
        return 7
    if recurrence.cadence == "weekly":
        try:
            raw = json.loads(recurrence.days_of_week_json or "[]")
            return len({int(d) for d in raw if isinstance(d, (int, float))})
        except (TypeError, ValueError):
            return 0
    return 0


def expected_days(
    recurrence: RecurringIntention,
    week_start: date,
    user_day: date,
) -> int:
    """Number of cadence-aligned days in [week_start, user_day] inclusive.

    Interval cadence has no clean weekly expectation and is excluded from the
    gap signal; daily/weekly carry the expected count.
    """
    if recurrence.cadence == "interval":
        return 0
    if recurrence.cadence == "weekly":
        try:
            raw = json.loads(recurrence.days_of_week_json or "[]")
            days = {int(d) for d in raw if isinstance(d, (int, float))}
        except (TypeError, ValueError):
            return 0
        total = 0
        cursor = week_start
        while cursor <= user_day:
            if cursor.weekday() in days:
                total += 1
            cursor += timedelta(days=1)
        return total
    # daily
    return (user_day - week_start).days + 1


def recurrence_week_health(
    recurrence: RecurringIntention,
    occurrences: List[RecurringOccurrence],
    user_day: date,
) -> dict:
    """Compact gap signal per recurrence. Field names are elapsed-to-date, not a
    weekly target, so downstream gap intelligence cannot misfire on intent.
    """
    start = _week_start(user_day)
    completed = sum(
        1
        for o in occurrences
        if start <= o.user_day <= user_day and o.status == OccurrenceStatus.COMPLETED
    )
    expected = expected_days(recurrence, start, user_day)
    target = week_target(recurrence)
    slipping = expected > 0 and completed < expected
    return {
        "week_target": target,
        "expected_so_far": expected,
        "completed_so_far": completed,
        "slipping": slipping,
        "progress_line": f"{completed}/{expected} done so far this week" if expected else None,
    }