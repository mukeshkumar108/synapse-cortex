"""Deterministic projection of canonical external objects into Cortex
lifecycle state.

Ownership boundaries preserved:
- App Postgres owns tasks; Google owns Calendar events. Cortex stores only
  derived lifecycle state, referenced by stable source identity + version.
- No model calls, no lane shaping, no expectation re-extraction: every action
  here is a deterministic, idempotent, bounded state transition.
- `updated` with a bumped source version supersedes the prior expectation
  (reschedule semantics). Same-version re-delivery is a no-op (duplicate-sync
  idempotency). `completed`/`cancelled` resolve state and invalidate stale
  attention (no stale callbacks after cancellation or rescheduling).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.attention_candidate import (
    AttentionCandidate,
    AttentionCandidateKind,
    AttentionCandidateStatus,
    utc_now as attention_utc_now,
)
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.schemas.object_state import ObjectStateIngest

logger = logging.getLogger(__name__)

DEFAULT_FOLLOWUP_WINDOW_HOURS = 6
EXTRACTOR_VERSION = "object_sync-v1"


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ObjectLifecycleService:
    async def apply_object_state(
        self, db: AsyncSession, payload: ObjectStateIngest
    ) -> Dict[str, Any]:
        owner_peer_id = payload.owner_peer_id or payload.peer_id or "user"
        current = await self._current_expectation(
            db,
            workspace_id=payload.workspace_id,
            source_system=payload.source.system,
            source_object_id=payload.source.object_id,
            owner_peer_id=owner_peer_id,
        )
        handler = {
            "created": self._apply_created_or_updated,
            "updated": self._apply_created_or_updated,
            "completed": self._apply_completed,
            "cancelled": self._apply_cancelled,
        }[payload.action]
        return await handler(db, payload, current, owner_peer_id)

    # ── lookups ──────────────────────────────────────────────────────────────

    async def _current_expectation(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        source_system: str,
        source_object_id: str,
        owner_peer_id: str,
    ) -> Optional[Expectation]:
        rows = (
            await db.execute(
                select(Expectation)
                .where(
                    Expectation.honcho_workspace_id == workspace_id,
                    Expectation.source_system == source_system,
                    Expectation.source_object_id == source_object_id,
                    # Owner scope: source identity is per-owner, so two users
                    # in a shared workspace can never project onto each other.
                    Expectation.owner_peer_id == owner_peer_id,
                    Expectation.superseded_by_id.is_(None),
                )
                .order_by(Expectation.created_at.desc())
            )
        ).scalars().all()
        return rows[0] if rows else None

    # ── created / updated (versioned upsert) ────────────────────────────────

    async def _apply_created_or_updated(
        self,
        db: AsyncSession,
        payload: ObjectStateIngest,
        current: Optional[Expectation],
        owner_peer_id: str,
    ) -> Dict[str, Any]:
        if current is not None and payload.source.version <= (current.source_version or 1):
            # Duplicate sync / stale delivery: same or older version is a no-op.
            return {
                "status": "accepted",
                "action_taken": "noop",
                "expectation_id": str(current.id),
                "reason": "stale_or_duplicate_version",
            }

        fields = self._expectation_fields(payload, owner_peer_id)

        if current is not None:
            current.outcome_state = OutcomeState.SUPERSEDED
            current.resolution_evidence = (
                f"source_object_updated:{payload.source.system}:"
                f"{payload.source.object_id}:v{current.source_version}->v{payload.source.version}"
            )
            db.add(current)

        expectation = Expectation(**fields)
        db.add(expectation)
        await db.flush()
        if current is not None:
            current.superseded_by_id = expectation.id
            db.add(current)
            # A rescheduled/changed calendar event invalidates stale follow-up
            # attention derived from its previous timing.
            if payload.source.system == "google_calendar":
                await self._cancel_source_attention(
                    db,
                    workspace_id=payload.workspace_id,
                    source_system=payload.source.system,
                    source_object_id=payload.source.object_id,
                )
        await db.commit()
        await db.refresh(expectation)
        return {
            "status": "accepted",
            "action_taken": "superseded" if current is not None else "created",
            "expectation_id": str(expectation.id),
            "superseded_id": str(current.id) if current is not None else None,
        }

    def _expectation_fields(
        self, payload: ObjectStateIngest, owner_peer_id: str
    ) -> Dict[str, Any]:
        system = payload.source.system
        windows = [
            {
                "start": _naive_utc(window.start).isoformat(),
                "end": _naive_utc(window.end).isoformat() if window.end else None,
                "label": window.label,
            }
            for window in payload.reminder_windows
        ]
        # Synthetic provenance ids are owner-scoped: source object ids are only
        # unique per owner, while the expectation idempotency constraint spans
        # the whole workspace.
        fields: Dict[str, Any] = {
            "honcho_workspace_id": payload.workspace_id,
            "honcho_session_id": payload.session_id,
            "honcho_message_id": (
                f"{system}:{owner_peer_id}:{payload.source.object_id}:v{payload.source.version}"
            ),
            "owner_peer_id": owner_peer_id,
            "subject_peer_id": owner_peer_id,
            "candidate_key": f"source:{system}:{owner_peer_id}:{payload.source.object_id}",
            "extractor_version": EXTRACTOR_VERSION,
            "version": 1,
            "title": payload.title,
            "summary": payload.notes or payload.title,
            "anchor_timezone": payload.timezone,
            "source_system": system,
            "source_object_id": payload.source.object_id,
            "source_version": payload.source.version,
            "reminder_windows_json": json.dumps(windows) if windows else None,
            "outcome_state": OutcomeState.UNKNOWN,
            "extraction_confidence": 1.0,
        }
        if payload.source.kind == "calendar_event":
            fields["expectation_type"] = ExpectationType.PLANNED_EVENT
            fields["expected_window_start"] = (
                _naive_utc(payload.event_start) if payload.event_start else None
            )
            fields["expected_window_end"] = (
                _naive_utc(payload.event_end) if payload.event_end else None
            )
            fields["hard_deadline_at"] = None
            fields["raw_temporal_phrase"] = None
        else:
            fields["expectation_type"] = ExpectationType.USER_COMMITMENT
            fields["hard_deadline_at"] = (
                _naive_utc(payload.due_at) if payload.due_at else None
            )
            fields["expected_window_start"] = None
            fields["expected_window_end"] = None
            fields["raw_temporal_phrase"] = (
                f"due {payload.due_at.isoformat()}" if payload.due_at else None
            )
        return fields

    # ── completed ────────────────────────────────────────────────────────────

    async def _apply_completed(
        self,
        db: AsyncSession,
        payload: ObjectStateIngest,
        current: Optional[Expectation],
        owner_peer_id: str = "user",
    ) -> Dict[str, Any]:
        action_taken = "resolved"
        if current is not None:
            current.outcome_state = OutcomeState.FULFILLED
            current.resolution_evidence = (
                f"source_object_completed:{payload.source.system}:{payload.source.object_id}"
            )
            current.updated_at = _now_naive()
            db.add(current)
        else:
            # Resolution tombstone for an object Cortex never saw created:
            # keeps recent_resolutions truthful without inventing live state.
            fields = self._expectation_fields(payload, owner_peer_id)
            fields["outcome_state"] = OutcomeState.FULFILLED
            fields["resolution_evidence"] = (
                f"source_object_completed:{payload.source.system}:{payload.source.object_id}"
            )
            db.add(Expectation(**fields))
            action_taken = "resolved_tombstone"

        callback_created = False
        if payload.source.kind == "calendar_event":
            callback_created = await self._create_followup_attention(
                db, payload, owner_peer_id
            )
        await db.commit()
        return {
            "status": "accepted",
            "action_taken": action_taken,
            "callback_attention_created": callback_created,
            "expectation_id": str(current.id) if current is not None else None,
        }

    async def _create_followup_attention(
        self,
        db: AsyncSession,
        payload: ObjectStateIngest,
        owner_peer_id: str = "user",
    ) -> bool:
        """Bounded post-event follow-up opportunity as source-linked attention.

        Uses the existing attention-candidate machinery (kind=callback) rather
        than inventing a new scheduler. The window is bounded by construction:
        not_before = event end, expires_at = end + followup_window_hours.
        """
        existing = (
            await db.execute(
                select(AttentionCandidate).where(
                    AttentionCandidate.honcho_workspace_id == payload.workspace_id,
                    AttentionCandidate.owner_peer_id == owner_peer_id,
                    AttentionCandidate.source_system == payload.source.system,
                    AttentionCandidate.source_object_id == payload.source.object_id,
                    AttentionCandidate.candidate_key
                    == f"calendar_followup:{owner_peer_id}:{payload.source.object_id}",
                    AttentionCandidate.status == AttentionCandidateStatus.ACTIVE,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return False

        window_hours = payload.followup_window_hours or DEFAULT_FOLLOWUP_WINDOW_HOURS
        event_end = _naive_utc(payload.event_end) if payload.event_end else _now_naive()
        db.add(
            AttentionCandidate(
                honcho_workspace_id=payload.workspace_id,
                honcho_session_id=payload.session_id,
                owner_peer_id=owner_peer_id,
                source_message_id=(
                    f"{payload.source.system}:{owner_peer_id}:{payload.source.object_id}"
                ),
                candidate_key=(
                    f"calendar_followup:{owner_peer_id}:{payload.source.object_id}"
                ),
                kind=AttentionCandidateKind.CALLBACK,
                content=f"Follow-up opportunity after '{payload.title}'",
                salience=0.6,
                confidence=1.0,
                status=AttentionCandidateStatus.ACTIVE,
                not_before=event_end,
                expires_at=event_end + timedelta(hours=window_hours),
                source_system=payload.source.system,
                source_object_id=payload.source.object_id,
                surfaced_count=0,
                created_at=attention_utc_now(),
                updated_at=attention_utc_now(),
            )
        )
        return True

    # ── cancelled ────────────────────────────────────────────────────────────

    async def _apply_cancelled(
        self,
        db: AsyncSession,
        payload: ObjectStateIngest,
        current: Optional[Expectation],
        owner_peer_id: str = "user",
    ) -> Dict[str, Any]:
        if current is not None:
            current.outcome_state = OutcomeState.CANCELLED
            current.resolution_evidence = (
                f"source_object_cancelled:{payload.source.system}:{payload.source.object_id}"
            )
            current.updated_at = _now_naive()
            db.add(current)
        cancelled_attention = await self._cancel_source_attention(
            db,
            workspace_id=payload.workspace_id,
            source_system=payload.source.system,
            source_object_id=payload.source.object_id,
        )
        await db.commit()
        return {
            "status": "accepted",
            "action_taken": "cancelled",
            "expectation_id": str(current.id) if current is not None else None,
            "attention_cancelled": cancelled_attention,
        }

    async def _cancel_source_attention(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        source_system: str,
        source_object_id: str,
    ) -> int:
        rows = (
            await db.execute(
                select(AttentionCandidate).where(
                    AttentionCandidate.honcho_workspace_id == workspace_id,
                    AttentionCandidate.source_system == source_system,
                    AttentionCandidate.source_object_id == source_object_id,
                    AttentionCandidate.status == AttentionCandidateStatus.ACTIVE,
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = AttentionCandidateStatus.DISMISSED
            row.updated_at = _now_naive()
            db.add(row)
        return len(rows)
