"""Single source of truth for daypart derivation.

Both the handshake (event orientation) and the continuity compiler (state
lighting) previously re-derived daypart from the same hour; one canonical
helper avoids drift between the two paths.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def resolve_daypart(
    now: datetime,
    timezone_str: str = "Europe/London",
) -> str:
    """Return morning/afternoon/evening/night for `now` in the user's zone."""
    try:
        local_now = (
            now.astimezone(ZoneInfo(timezone_str))
            if now.tzinfo
            else now.replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo(timezone_str))
        )
    except Exception:
        local_now = now
    hour = local_now.hour
    if 5 <= hour < 12:
        return "morning"
    if 12 <= hour < 17:
        return "afternoon"
    if 17 <= hour < 22:
        return "evening"
    return "night"