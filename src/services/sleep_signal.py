"""Backstage sleep derived-state.

Evidence is the user's own words (bed announcement, wake/late appearance) with
timestamps. We only derive a bounded inference (short_sleep_likely /
unusually_late_night_likely) when we actually have both bookends AND the window
plausibly covers the user's main overnight sleep — a daytime nap is never an
overnight signal. Signals are session-lifetime with a kind-specific TTL: a
stale episode from a previous waking/day episode stops surfacing.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.derived_signal import DerivedSignal, DerivedSignalKind

logger = logging.getLogger(__name__)

_BED_PATTERNS = [
    r"\b(going to bed|headed to bed|heading to bed|off to (?:bed|sleep)|getting into bed|"
    r"i'm (?:going|headed) to bed|hitting the hay|turning in)\b",
    r"\bgoodnight\b",
]
_WAKE_PATTERNS = [
    r"\b(?:just )?woke up\b",
    r"\b(?:just )?(?:i'm|i am|finally) up\b",
    r"\bup and at (?:'em|him)\b",
    r"\bawake (?:now|already)\b",
]

SHORT_SLEEP_HOURS = 7.0
SLEEP_SIGNAL_TTL_HOURS = 20.0
# Overnight bedtimes fall in the evening->early-AM range (19:00..05:59 local).
OVERNIGHT_BED_START_HOUR = 19
OVERNIGHT_BED_END_HOUR = 5
LATE_NIGHT_START_HOUR = 1
LATE_NIGHT_END_HOUR = 5
MIN_OVERNIGHT_HOURS = 4.0

CONFIDENCE_GROUNDED = 0.8
CONFIDENCE_SOFT = 0.6


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _now_value(now: datetime) -> datetime:
    return _utc(now) if now else datetime.now(timezone.utc).replace(tzinfo=None)


def _as_naive_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return _utc(parsed) if parsed.tzinfo else parsed


def _local_hour(value: datetime, timezone_str: str) -> int:
    try:
        tz = ZoneInfo(timezone_str)
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(tz).hour
    except Exception:
        return value.hour


def _is_overnight(bed_time: datetime, wake_at: datetime, timezone_str: str) -> bool:
    """True when the window plausibly covers the user's main overnight sleep.

    Requires an evening-to-early-AM bedtime and enough elapsed time to be a
    night of sleep (>= MIN_OVERNIGHT_HOURS). A daytime nap (e.g. 14:00-16:30)
    fails the bedtime window and is never an overnight signal.
    """
    bed_hour = _local_hour(bed_time, timezone_str)
    hours = (wake_at - bed_time).total_seconds() / 3600.0
    overnight_window = (
        bed_hour >= OVERNIGHT_BED_START_HOUR or bed_hour <= OVERNIGHT_BED_END_HOUR
    )
    return overnight_window and hours >= MIN_OVERNIGHT_HOURS


def _bed_is_late(bed_time: datetime, timezone_str: str) -> bool:
    hour = _local_hour(bed_time, timezone_str)
    return LATE_NIGHT_START_HOUR <= hour <= LATE_NIGHT_END_HOUR


class SleepSignalTracker:
    """Upserts the single current sleep episode per session from evidence."""

    async def observe(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        message_id: str,
        text: str,
        now: datetime,
        timezone_str: str = "UTC",
    ) -> Optional[Dict[str, Any]]:
        lower = text.lower()
        bed_hit = any(re.search(p, lower) for p in _BED_PATTERNS)
        wake_hit = any(re.search(p, lower) for p in _WAKE_PATTERNS)
        if not bed_hit and not wake_hit:
            return None

        current = (
            await db.execute(
                select(DerivedSignal).where(
                    DerivedSignal.honcho_workspace_id == workspace_id,
                    DerivedSignal.honcho_session_id == session_id,
                    DerivedSignal.kind == DerivedSignalKind.SLEEP_EPISODE,
                )
            )
        ).scalar_one_or_none()
        payload = json.loads(current.payload_json) if current else {}

        changed = False
        if bed_hit and (not payload.get("bed_time") or payload.get("wake_time")):
            payload = {}
            payload["bed_time"] = _now_value(now).isoformat()
            payload["bed_announced_at"] = _now_value(now).isoformat()
            payload["anchor_timezone"] = timezone_str
            changed = True
        if wake_hit:
            wake_at = _now_value(now)
            if payload.get("bed_time") and not payload.get("wake_time"):
                payload["wake_time"] = wake_at.isoformat()
                bed = _as_naive_utc(payload["bed_time"])
                hours = (wake_at - bed).total_seconds() / 3600.0
                payload["hours"] = round(hours, 1)
                tz = payload.get("anchor_timezone") or timezone_str
                explicit_bed = bool(payload.get("bed_announced_at"))
                payload["confidence"] = (
                    CONFIDENCE_GROUNDED if explicit_bed else CONFIDENCE_SOFT
                )
                # Only main overnight sleep produces a bedtime-window signal.
                # Daytime naps are observed backstage (hours) but never promoted.
                if _is_overnight(bed, wake_at, tz):
                    if hours < SHORT_SLEEP_HOURS:
                        payload["signal"] = "short_sleep_likely"
                    elif _bed_is_late(bed, tz):
                        payload["signal"] = "unusually_late_night_likely"
                    else:
                        payload["signal"] = "sleep_windows_observed"
                else:
                    payload.pop("signal", None)
                changed = True

        if not changed:
            return None

        row = current or DerivedSignal(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            kind=DerivedSignalKind.SLEEP_EPISODE,
            payload_json="{}",
            last_message_id=message_id,
        )
        row.payload_json = json.dumps(payload)
        row.last_message_id = message_id
        row.updated_at = _utc(now)
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = (
                await db.execute(
                    select(DerivedSignal).where(
                        DerivedSignal.honcho_workspace_id == workspace_id,
                        DerivedSignal.honcho_session_id == session_id,
                        DerivedSignal.kind == DerivedSignalKind.SLEEP_EPISODE,
                    )
                )
            ).scalar_one_or_none()
            if existing:
                existing.payload_json = row.payload_json
                existing.last_message_id = message_id
                existing.updated_at = _utc(now)
                db.add(existing)
                await db.commit()
                return json.loads(existing.payload_json)
            return None
        await db.refresh(row)
        return payload

    async def read(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        now: Optional[datetime] = None,
        max_age_hours: float = SLEEP_SIGNAL_TTL_HOURS,
    ) -> Optional[Dict[str, Any]]:
        """Current episode with kind-TTL staleness. An episode older than
        max_age_hours no longer describes the present waking/day episode and is
        treated as absent.
        """
        row = (
            await db.execute(
                select(DerivedSignal).where(
                    DerivedSignal.honcho_workspace_id == workspace_id,
                    DerivedSignal.honcho_session_id == session_id,
                    DerivedSignal.kind == DerivedSignalKind.SLEEP_EPISODE,
                )
            )
        ).scalar_one_or_none()
        if not row:
            return None
        payload = json.loads(row.payload_json)
        reference = payload.get("wake_time") or payload.get("bed_time")
        if not reference:
            return None
        age = (_now_value(now) - _as_naive_utc(reference)).total_seconds() / 3600.0
        if age > max_age_hours:
            return None
        return payload