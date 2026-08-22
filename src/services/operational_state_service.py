import json
import re
from datetime import datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.expectation import Expectation, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import (
    ExtractionTrace, ObjectiveProgress, OccurrenceStatus, OperationalStatus,
    RecurringIntention, RecurringOccurrence,
)
from src.schemas.candidate import ExtractionCandidate, ExtractionResult
from src.services.temporal_grounding import TemporalGrounding


def _utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def canonical_key(value: str) -> str:
    stop = {"a", "an", "the", "to", "for", "my", "proper", "every", "daily", "weekly", "today",
            "user", "need", "needs", "still", "keep", "send", "sent", "larger", "objective",
            "unresolved", "active", "continue", "continuing", "has", "but", "remains",
            "routine", "habit", "establish", "established", "start", "again"}
    normalize = {"jobs": "job", "applications": "application", "applying": "application",
                 "applied": "application", "apply": "application", "walking": "walk", "walks": "walk"}
    words = [normalize.get(w, w) for w in re.findall(r"[a-z0-9]+", value.lower()) if w not in stop]
    return "-".join(words[:8]) or "untitled"


def _overlap(left: str, right: str) -> float:
    a, b = set(canonical_key(left).split("-")), set(canonical_key(right).split("-"))
    return len(a & b) / max(1, min(len(a), len(b)))


class OperationalStateService:
    """Deterministic commit/reconcile/lifecycle layer for model proposals."""

    def __init__(self):
        self.temporal = TemporalGrounding()

    async def trace_result(self, db: AsyncSession, *, workspace_id: str, session_id: str,
                           message_id: str, result: ExtractionResult) -> None:
        items = [("extractor", "result", result.backend, {"failure": result.failure})]
        items += [("loose", o.observation_id, "proposed", o.model_dump(mode="json")) for o in result.observations]
        items += [("shape", c.candidate_key, "proposed", c.model_dump(mode="json")) for c in result.candidates]
        for stage, key, status, detail in items:
            exists = (await db.execute(select(ExtractionTrace).where(
                ExtractionTrace.honcho_workspace_id == workspace_id,
                ExtractionTrace.honcho_message_id == message_id,
                ExtractionTrace.stage == stage, ExtractionTrace.item_key == key,
            ))).scalar_one_or_none()
            if not exists:
                db.add(ExtractionTrace(honcho_workspace_id=workspace_id, honcho_session_id=session_id,
                    honcho_message_id=message_id, stage=stage, item_key=key, status=status,
                    detail_json=json.dumps(detail, default=str), model=result.model))
                try:
                    await db.commit()
                except IntegrityError:
                    await db.rollback()

    async def apply(self, db: AsyncSession, *, workspace_id: str, session_id: str,
                    message_id: str, peer_id: str, candidate: ExtractionCandidate,
                    now: datetime, timezone_str: str) -> dict:
        kind = candidate.operational_kind
        if kind == "semantic_only":
            return {"rejected": "semantic_memory_only"}
        if kind == "recurring_intention":
            return await self._upsert_recurrence(db, workspace_id, session_id, message_id, candidate, now, timezone_str)
        if kind in ("completion", "cancellation"):
            recurrence = await self._match_recurrence(db, workspace_id, session_id, candidate)
            if recurrence:
                if kind == "cancellation":
                    recurrence.status = OperationalStatus.CANCELLED
                    recurrence.active_slot = None
                    recurrence.ended_at = _utc(now)
                    recurrence.updated_at = _utc(now)
                    db.add(recurrence)
                    await db.commit()
                    return {"mutation": "recurrence_cancelled", "id": str(recurrence.id)}
                occurrence = await self._occurrence(db, recurrence, now, timezone_str)
                occurrence.status = OccurrenceStatus.COMPLETED
                occurrence.source_message_id = message_id
                occurrence.evidence = candidate.raw_evidence or candidate.observation
                occurrence.updated_at = _utc(now)
                db.add(occurrence)
                await db.commit()
                return {"mutation": "occurrence_completed", "id": str(occurrence.id)}
            loop = await self._match_open_loop(db, workspace_id, session_id, candidate)
            if loop:
                loop.status = OpenLoopStatus.RESOLVED if kind == "completion" else OpenLoopStatus.ABANDONED
                loop.resolution_evidence = candidate.raw_evidence or candidate.observation
                loop.updated_at = _utc(now)
                db.add(loop); await db.commit()
                return {"mutation": "open_loop_resolved", "id": str(loop.id)}
        if kind == "progress":
            return await self._record_progress(db, workspace_id, session_id, message_id, candidate, now, timezone_str)
        return {"mutation": "delegated_existing_lifecycle"}

    async def match_expectation(self, db: AsyncSession, *, workspace_id: str,
                                session_id: str, candidate: ExtractionCandidate) -> Optional[Expectation]:
        rows = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_session_id == session_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
            Expectation.superseded_by_id.is_(None),
        ))).scalars().all()
        target = candidate.target_key or candidate.canonical_title or candidate.observation
        matches = sorted(rows, key=lambda item: _overlap(target, item.title), reverse=True)
        return matches[0] if matches and _overlap(target, matches[0].title) >= .34 else None

    async def _match_open_loop(self, db, workspace_id, session_id, candidate):
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_session_id == session_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        ))).scalars().all()
        target = candidate.target_key or candidate.canonical_title or candidate.observation
        matches = sorted(loops, key=lambda item: _overlap(target, f"{item.title} {item.summary}"), reverse=True)
        return matches[0] if matches and _overlap(target, f"{matches[0].title} {matches[0].summary}") >= .34 else None

    async def _match_recurrence(self, db: AsyncSession, workspace_id: str, session_id: str, candidate: ExtractionCandidate) -> Optional[RecurringIntention]:
        active = (await db.execute(select(RecurringIntention).where(
            RecurringIntention.honcho_workspace_id == workspace_id,
            RecurringIntention.honcho_session_id == session_id,
            RecurringIntention.status == OperationalStatus.ACTIVE,
        ))).scalars().all()
        target = candidate.target_key or candidate.canonical_title or candidate.observation
        matches = sorted(active, key=lambda item: _overlap(target, item.title), reverse=True)
        return matches[0] if matches and _overlap(target, matches[0].title) >= 0.34 else None

    async def _upsert_recurrence(self, db, workspace_id, session_id, message_id, candidate, now, timezone_str):
        if not candidate.cadence or candidate.confidence < 0.65:
            return {"rejected": "invalid_or_low_confidence_recurrence"}
        title = candidate.canonical_title or candidate.observation
        existing = await self._match_recurrence(db, workspace_id, session_id, candidate)
        new_key = canonical_key(title)
        if existing:
            changed = (existing.cadence != candidate.cadence or
                       existing.days_of_week_json != json.dumps(candidate.days_of_week))
            if not changed:
                return {"mutation": "recurrence_deduped", "id": str(existing.id)}
            existing.status = OperationalStatus.SUPERSEDED
            existing.active_slot = None
            existing.ended_at = _utc(now)
            existing.updated_at = _utc(now)
            db.add(existing)
        row = RecurringIntention(
            honcho_workspace_id=workspace_id, honcho_session_id=session_id,
            honcho_message_id=message_id, candidate_key=candidate.candidate_key,
            canonical_key=new_key, title=title, cadence=candidate.cadence,
            interval_days=candidate.interval_days, days_of_week_json=json.dumps(candidate.days_of_week),
            timezone=timezone_str, preferred_window=candidate.preferred_window,
            target_amount=candidate.target_amount, target_unit=candidate.target_unit,
            source_evidence=candidate.raw_evidence or candidate.observation,
            confidence=candidate.confidence, started_at=_utc(now),
        )
        db.add(row)
        await db.commit(); await db.refresh(row)
        if existing:
            existing.superseded_by_id = row.id; db.add(existing); await db.commit()
        await self._occurrence(db, row, now, timezone_str)
        return {"mutation": "recurrence_created" if not existing else "recurrence_superseded", "id": str(row.id)}

    async def _occurrence(self, db, recurrence, now, timezone_str):
        try: user_day = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now).astimezone(ZoneInfo(timezone_str)).date()
        except Exception: user_day = _utc(now).date()
        found = (await db.execute(select(RecurringOccurrence).where(
            RecurringOccurrence.recurring_intention_id == recurrence.id,
            RecurringOccurrence.user_day == user_day,
        ))).scalar_one_or_none()
        if found: return found
        row = RecurringOccurrence(recurring_intention_id=recurrence.id,
            honcho_workspace_id=recurrence.honcho_workspace_id, user_day=user_day)
        db.add(row); await db.commit(); await db.refresh(row); return row

    async def _record_progress(self, db, workspace_id, session_id, message_id, candidate, now, timezone_str):
        existing = (await db.execute(select(ObjectiveProgress).where(
            ObjectiveProgress.honcho_workspace_id == workspace_id,
            ObjectiveProgress.honcho_message_id == message_id,
            ObjectiveProgress.candidate_key == candidate.candidate_key,
        ))).scalar_one_or_none()
        if existing: return {"mutation": "progress_deduped", "id": str(existing.id)}
        parent = await self.match_expectation(
            db, workspace_id=workspace_id, session_id=session_id, candidate=candidate
        )
        try: user_day = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now).astimezone(ZoneInfo(timezone_str)).date()
        except Exception: user_day = _utc(now).date()
        row = ObjectiveProgress(honcho_workspace_id=workspace_id, honcho_session_id=session_id,
            honcho_message_id=message_id, candidate_key=candidate.candidate_key,
            expectation_id=parent.id if parent else None, title=candidate.canonical_title or candidate.observation,
            amount=candidate.progress_amount, unit=candidate.progress_unit, user_day=user_day,
            evidence=candidate.raw_evidence or candidate.observation)
        db.add(row); await db.commit(); await db.refresh(row)
        return {"mutation": "progress_recorded", "id": str(row.id), "parent_id": str(parent.id) if parent else None}

    async def sweep(self, db: AsyncSession, *, workspace_id: str, now: datetime) -> int:
        now_utc = _utc(now)
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id, OpenLoop.status == OpenLoopStatus.OPEN,
            OpenLoop.expires_at.is_not(None), OpenLoop.expires_at < now_utc,
        ))).scalars().all()
        for loop in loops:
            loop.status = OpenLoopStatus.EXPIRED
            loop.resolution_evidence = "deterministic_expiry:window_elapsed_without_resolution"
            loop.updated_at = now_utc; db.add(loop)
        if loops: await db.commit()
        return len(loops)
