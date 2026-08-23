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
    """Compact gap signal for a recurrence over the current week."""
    start = _week_start(user_day)
    completed = sum(
        1
        for o in occurrences
        if start <= o.user_day <= user_day and o.status == OccurrenceStatus.COMPLETED
    )
    expected = expected_days(recurrence, start, user_day)
    slipping = expected > 0 and completed < expected
    return {
        "expected_this_week": expected,
        "completed_this_week": completed,
        "slipping": slipping,
        "progress_line": f"{completed}/{expected} done this week" if expected else None,
    }