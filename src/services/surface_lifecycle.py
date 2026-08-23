"""Surface lifecycle for packet-emitted candidates.

Every packet-emitted surface item (curiosity, clarifications, routine gaps)
needs a bounded delivery lifecycle: eligible -> promoted -> surfaced -> cooldown
-> eligible again / resolved / expired. Without a report-back event today, the
packet compiler records an approximation: each time an item is admitted into a
compiled packet it is marked surfaced; the store enforces a per-key cooldown
and a max surface count, so a candidate can never nag indefinitely. When a
candidate reaches its max it signals the caller to resolve/dismiss the source
(for ClarificationCandidates that is a real DB state transition).

Stored in derived_signals.kind = surface_cooldown (payload is a key -> state map),
reusing the existing kind-scoped derived-signals substrate (additive; no new table).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.derived_signal import DerivedSignal, DerivedSignalKind

logger = logging.getLogger(__name__)


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


class SurfaceRegistry:
    """Per-session surface bookkeeping with cooldown + max-count semantics."""

    async def _load(self, db, workspace_id: str, session_id: str) -> Optional[DerivedSignal]:
        return (
            await db.execute(
                select(DerivedSignal).where(
                    DerivedSignal.honcho_workspace_id == workspace_id,
                    DerivedSignal.honcho_session_id == session_id,
                    DerivedSignal.kind == DerivedSignalKind.SURFACE_COOLDOWN,
                )
            )
        ).scalar_one_or_none()

    async def _upsert(
        self,
        db,
        workspace_id: str,
        session_id: str,
        message_id: str,
        payload: Dict[str, Any],
        now: datetime,
    ) -> None:
        row = await self._load(db, workspace_id, session_id)
        target = row or DerivedSignal(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            kind=DerivedSignalKind.SURFACE_COOLDOWN,
            payload_json="{}",
            last_message_id=message_id,
        )
        target.payload_json = json.dumps(payload)
        target.last_message_id = message_id
        target.updated_at = _utc(now)
        db.add(target)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await self._load(db, workspace_id, session_id)
            if existing:
                existing.payload_json = target.payload_json
                existing.last_message_id = message_id
                existing.updated_at = _utc(now)
                db.add(existing)
                await db.commit()

    async def mark(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        message_id: str,
        key: str,
        now: datetime,
        cooldown_seconds: int = 3600,
        max_count: int = 3,
    ) -> str:
        """Record one surfacing.

        Returns:
          allowed - admitted to the packet (and counted).
          cooldown - last surfacing too recent; suppressed this time.
          maxed - surface budget exhausted; caller should resolve/dismiss.
        """
        now_utc = _utc(now)
        row = await self._load(db, workspace_id, session_id)
        payload = json.loads(row.payload_json) if row else {}
        entry = payload.get(key)
        current = 0
        last_at: datetime | None = None
        if isinstance(entry, dict):
            current = int(entry.get("count", 0))
            if entry.get("last"):
                try:
                    last_at = datetime.fromisoformat(entry["last"])
                except (TypeError, ValueError):
                    last_at = None
        if current >= max_count:
            return "maxed"
        if last_at is not None and (now_utc - last_at).total_seconds() < cooldown_seconds:
            return "cooldown"
        payload[key] = {
            "count": current + 1,
            "last": now_utc.isoformat(),
        }
        await self._upsert(db, workspace_id, session_id, message_id, payload, now)
        return "allowed"

    async def resolve(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        message_id: str,
        key: str,
        now: datetime,
    ) -> None:
        row = await self._load(db, workspace_id, session_id)
        if not row:
            return
        payload = json.loads(row.payload_json)
        if key in payload:
            payload.pop(key, None)
            await self._upsert(db, workspace_id, session_id, message_id, payload, now)