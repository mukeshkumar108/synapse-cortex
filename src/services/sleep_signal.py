"""Backstage sleep derived-state.

Evidence is the user's own words (bed announcement, wake/late appearance) with
timestamps. We only derive a bounded inference (short_sleep_likely /
normal_cycle_likely) when we actually have both bookends; an unsupported
inference is never stored. Honcho/cortex never demands biometric certainty —
an explicit "going to bed at 02:56" plus a first appearance at 09:38 already
bounds the sleep window.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.derived_signal import DerivedSignal, DerivedSignalKind

logger = logging.getLogger(__name__)

_BED_PATTERNS = [
    r"\b(going to bed|headed to bed|heading to bed|off to (?:bed|sleep)|getting into bed|"
    r"i'm (?:going|headed) to bed|hitting the hay|turning in|for tonight)\b",
    r"\bgoodnight\b",
]
_WAKE_PATTERNS = [
    r"\b(?:just )?woke up\b",
    r"\b(?:just )?(?:i'm|i am|finally) up\b",
    r"\bup and at (?:'em|him)\b",
    r"\bawake (?:now|already)\b",
]

SHORT_SLEEP_HOURS = 7.0
CONFIDENCE_GROUNDED = 0.8
CONFIDENCE_SOFT = 0.6


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _now_value(now: datetime) -> datetime:
    return _utc(now) if now else datetime.now(timezone.utc).replace(tzinfo=None)


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
            changed = True
        if wake_hit:
            wake_at = _now_value(now)
            if payload.get("bed_time") and not payload.get("wake_time"):
                payload["wake_time"] = wake_at.isoformat()
                bed = datetime.fromisoformat(payload["bed_time"])
                hours = (wake_at - bed).total_seconds() / 3600.0
                payload["hours"] = round(hours, 1)
                explicit_bed = bool(payload.get("bed_announced_at"))
                if hours < SHORT_SLEEP_HOURS:
                    payload["signal"] = "short_sleep_likely"
                elif bed.hour >= 1:
                    payload["signal"] = "unusually_late_night_likely"
                else:
                    payload["signal"] = "normal_cycle_likely"
                payload["confidence"] = CONFIDENCE_GROUNDED if explicit_bed else CONFIDENCE_SOFT
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
    ) -> Optional[Dict[str, Any]]:
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
        return json.loads(row.payload_json)