import logging
from typing import Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db import get_async_session
from src.models.expectation import Expectation
from src.models.open_loop import OpenLoop
from src.models.suppression import Suppression
from src.models.epistemic import EpistemicAnnotation
from src.models.domain_annotation import DomainAnnotation
from src.models.clarification import ClarificationCandidate
from src.models.operational_state import (ExtractionTrace, RecurringIntention,
    RecurringOccurrence, ObjectiveProgress)
from src.models.attention_candidate import AttentionCandidate
from src.models.commitment_candidate import CommitmentCandidate
from src.services.expectation_engine import derive_expectation_read_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/debug", tags=["debug"])


@router.get("/owner-state")
async def get_owner_state(
    workspace_id: str = Query(...),
    owner_peer_id: str = Query(..., min_length=1),
    limit: int = Query(100, ge=1, le=250),
    db: AsyncSession = Depends(get_async_session),
):
    """Owner-scoped continuity inspection for authenticated app tooling.

    The service-token boundary authenticates the app; this endpoint then
    requires the app's stable owner peer id and never falls back to a
    workspace-wide or session-wide read. It is intentionally a read model,
    not a mutation surface.
    """
    now = datetime.now(timezone.utc)

    expectations = (await db.execute(
        select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.owner_peer_id == owner_peer_id,
        ).order_by(Expectation.created_at.desc()).limit(limit)
    )).scalars().all()
    open_loops = (await db.execute(
        select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.owner_peer_id == owner_peer_id,
        ).order_by(OpenLoop.created_at.desc()).limit(limit)
    )).scalars().all()
    recurrences = (await db.execute(
        select(RecurringIntention).where(
            RecurringIntention.honcho_workspace_id == workspace_id,
            RecurringIntention.owner_peer_id == owner_peer_id,
        ).order_by(RecurringIntention.updated_at.desc()).limit(limit)
    )).scalars().all()
    recurrence_ids = [item.id for item in recurrences]
    occurrences = []
    if recurrence_ids:
        occurrences = (await db.execute(
            select(RecurringOccurrence).where(
                RecurringOccurrence.recurring_intention_id.in_(recurrence_ids)
            ).order_by(RecurringOccurrence.user_day.desc()).limit(limit)
        )).scalars().all()
    progress = (await db.execute(
        select(ObjectiveProgress).where(
            ObjectiveProgress.honcho_workspace_id == workspace_id,
            ObjectiveProgress.owner_peer_id == owner_peer_id,
        ).order_by(ObjectiveProgress.created_at.desc()).limit(limit)
    )).scalars().all()
    attention = (await db.execute(
        select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == workspace_id,
            AttentionCandidate.owner_peer_id == owner_peer_id,
        ).order_by(AttentionCandidate.created_at.desc()).limit(limit)
    )).scalars().all()
    commitments = (await db.execute(
        select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.owner_peer_id == owner_peer_id,
        ).order_by(CommitmentCandidate.created_at.desc()).limit(limit)
    )).scalars().all()

    return {
        "generated_at": now.isoformat(),
        "counts": {
            "expectations": len(expectations),
            "open_loops": len(open_loops),
            "recurring_intentions": len(recurrences),
            "recurring_occurrences": len(occurrences),
            "objective_progress": len(progress),
            "attention_candidates": len(attention),
            "commitment_candidates": len(commitments),
        },
        "expectations": [
            {
                "id": str(item.id),
                "session_id": item.honcho_session_id,
                "source_message_id": item.honcho_message_id,
                "candidate_key": item.candidate_key,
                "title": item.title,
                "summary": item.summary,
                "expectation_type": item.expectation_type.value,
                "confidence": item.extraction_confidence,
                "raw_temporal_phrase": item.raw_temporal_phrase,
                "expected_window_start": item.expected_window_start.isoformat()
                if item.expected_window_start else None,
                "expected_window_end": item.expected_window_end.isoformat()
                if item.expected_window_end else None,
                "hard_deadline_at": item.hard_deadline_at.isoformat()
                if item.hard_deadline_at else None,
                "temporal_state": derive_expectation_read_model(item, now)["temporal_state"],
                "outcome_state": item.outcome_state.value,
                "followup_eligible": derive_expectation_read_model(item, now)["followup_eligible"],
                "superseded_by_id": str(item.superseded_by_id)
                if item.superseded_by_id else None,
                "resolution_evidence": item.resolution_evidence,
                "source_system": item.source_system,
                "source_object_id": item.source_object_id,
                "source_version": item.source_version,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in expectations
        ],
        "open_loops": [
            {
                "id": str(item.id),
                "session_id": item.honcho_session_id,
                "source_message_id": item.honcho_message_id,
                "candidate_key": item.candidate_key,
                "expectation_id": str(item.expectation_id)
                if item.expectation_id else None,
                "title": item.title,
                "summary": item.summary,
                "status": item.status.value,
                "resolution_evidence": item.resolution_evidence,
                "expires_at": item.expires_at.isoformat()
                if item.expires_at else None,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in open_loops
        ],
        "recurring_intentions": [
            {
                "id": str(item.id),
                "session_id": item.honcho_session_id,
                "source_message_id": item.honcho_message_id,
                "candidate_key": item.candidate_key,
                "canonical_key": item.canonical_key,
                "title": item.title,
                "cadence": item.cadence,
                "interval_days": item.interval_days,
                "days_of_week_json": item.days_of_week_json,
                "timezone": item.timezone,
                "preferred_window": item.preferred_window,
                "target_amount": item.target_amount,
                "target_unit": item.target_unit,
                "status": item.status.value,
                "source_evidence": item.source_evidence,
                "confidence": item.confidence,
                "superseded_by_id": str(item.superseded_by_id)
                if item.superseded_by_id else None,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in recurrences
        ],
        "recurring_occurrences": [
            {
                "id": str(item.id),
                "recurring_intention_id": str(item.recurring_intention_id),
                "user_day": item.user_day.isoformat(),
                "status": item.status.value,
                "progress_amount": item.progress_amount,
                "progress_unit": item.progress_unit,
                "source_message_id": item.source_message_id,
                "evidence": item.evidence,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in occurrences
        ],
        "objective_progress": [
            {
                "id": str(item.id),
                "source_message_id": item.honcho_message_id,
                "expectation_id": str(item.expectation_id)
                if item.expectation_id else None,
                "title": item.title,
                "amount": item.amount,
                "unit": item.unit,
                "user_day": item.user_day.isoformat(),
                "evidence": item.evidence,
                "created_at": item.created_at.isoformat(),
            }
            for item in progress
        ],
        "attention_candidates": [
            {
                "id": str(item.id),
                "session_id": item.honcho_session_id,
                "source_message_id": item.source_message_id,
                "source_assistant_message_id": item.source_assistant_message_id,
                "candidate_key": item.candidate_key,
                "kind": item.kind.value,
                "content": item.content,
                "salience": item.salience,
                "confidence": item.confidence,
                "status": item.status.value,
                "not_before": item.not_before.isoformat()
                if item.not_before else None,
                "expires_at": item.expires_at.isoformat()
                if item.expires_at else None,
                "surfaced_count": item.surfaced_count,
                "last_surfaced_at": item.last_surfaced_at.isoformat()
                if item.last_surfaced_at else None,
                "source_system": item.source_system,
                "source_object_id": item.source_object_id,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in attention
        ],
        "commitment_candidates": [
            {
                "id": str(item.id),
                "session_id": item.honcho_session_id,
                "source_message_id": item.source_message_id,
                "candidate_key": item.candidate_key,
                "canonical_key": item.canonical_key,
                "title": item.title,
                "notes": item.notes,
                "evidence_verbatim": item.evidence_verbatim,
                "evidence_class": item.evidence_class,
                "authority": item.authority.value,
                "status": item.status.value,
                "materialized_source_object_id": item.materialized_source_object_id,
                "raw_temporal_phrase": item.raw_temporal_phrase,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in commitments
        ],
    }


@router.get("/decisions")
async def get_recent_decisions(
    workspace_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    message_id: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Developer debug endpoint returning recent extraction & V4 state decisions.
    Answers: "Why did Synapse think this turn created an expectation, loop, or suppression?"
    """
    now = datetime.now(timezone.utc)

    # 1. Expectations
    stmt_exp = select(Expectation)
    if workspace_id:
        stmt_exp = stmt_exp.where(Expectation.honcho_workspace_id == workspace_id)
    if session_id:
        stmt_exp = stmt_exp.where(Expectation.honcho_session_id == session_id)
    if message_id is not None:
        stmt_exp = stmt_exp.where(Expectation.honcho_message_id == message_id)
    stmt_exp = stmt_exp.order_by(Expectation.created_at.desc()).limit(limit)
    res_exp = await db.execute(stmt_exp)
    expectations = res_exp.scalars().all()

    decisions = []
    for exp in expectations:
        read_model = derive_expectation_read_model(exp, now)
        decisions.append({
            "id": str(exp.id),
            "honcho_workspace_id": exp.honcho_workspace_id,
            "honcho_session_id": exp.honcho_session_id,
            "honcho_message_id": exp.honcho_message_id,
            "candidate_key": exp.candidate_key,
            "source_start": exp.source_start,
            "source_end": exp.source_end,
            "subject_peer_id": exp.subject_peer_id,
            "expectation_type": exp.expectation_type.value,
            "title": exp.title,
            "summary": exp.summary,
            "raw_temporal_phrase": exp.raw_temporal_phrase,
            "expected_window_start": exp.expected_window_start.isoformat() if exp.expected_window_start else None,
            "expected_window_end": exp.expected_window_end.isoformat() if exp.expected_window_end else None,
            "hard_deadline_at": exp.hard_deadline_at.isoformat() if exp.hard_deadline_at else None,
            "temporal_state": read_model["temporal_state"],
            "outcome_state": exp.outcome_state.value,
            "resolution_evidence": exp.resolution_evidence,
            "followup_eligible": read_model["followup_eligible"],
            "confidence": exp.extraction_confidence,
            "created_at": exp.created_at.isoformat(),
        })

    # 2. Open Loops
    stmt_loop = select(OpenLoop)
    if workspace_id:
        stmt_loop = stmt_loop.where(OpenLoop.honcho_workspace_id == workspace_id)
    if session_id:
        stmt_loop = stmt_loop.where(OpenLoop.honcho_session_id == session_id)
    if message_id is not None:
        stmt_loop = stmt_loop.where(OpenLoop.honcho_message_id == message_id)
    res_loop = await db.execute(stmt_loop)
    open_loops = res_loop.scalars().all()

    # 3. Suppressions
    stmt_supp = select(Suppression)
    if workspace_id:
        stmt_supp = stmt_supp.where(Suppression.honcho_workspace_id == workspace_id)
    if session_id:
        stmt_supp = stmt_supp.where(Suppression.honcho_session_id == session_id)
    if message_id is not None:
        stmt_supp = stmt_supp.where(Suppression.honcho_message_id == message_id)
    res_supp = await db.execute(stmt_supp)
    suppressions = res_supp.scalars().all()

    # 4. Epistemic Annotations
    stmt_ep = select(EpistemicAnnotation)
    if workspace_id:
        stmt_ep = stmt_ep.where(EpistemicAnnotation.honcho_workspace_id == workspace_id)
    if session_id:
        stmt_ep = stmt_ep.where(EpistemicAnnotation.honcho_session_id == session_id)
    if message_id is not None:
        stmt_ep = stmt_ep.where(EpistemicAnnotation.honcho_message_id == message_id)
    res_ep = await db.execute(stmt_ep)
    epistemics = res_ep.scalars().all()

    stmt_clar = select(ClarificationCandidate)
    if workspace_id:
        stmt_clar = stmt_clar.where(ClarificationCandidate.honcho_workspace_id == workspace_id)
    if session_id:
        stmt_clar = stmt_clar.where(ClarificationCandidate.honcho_session_id == session_id)
    if message_id is not None:
        stmt_clar = stmt_clar.where(ClarificationCandidate.honcho_message_id == message_id)
    clarifications = (await db.execute(stmt_clar)).scalars().all()

    trace_stmt = select(ExtractionTrace)
    recurrence_stmt = select(RecurringIntention)
    occurrence_stmt = select(RecurringOccurrence)
    progress_stmt = select(ObjectiveProgress)
    if workspace_id:
        trace_stmt = trace_stmt.where(ExtractionTrace.honcho_workspace_id == workspace_id)
        recurrence_stmt = recurrence_stmt.where(RecurringIntention.honcho_workspace_id == workspace_id)
        occurrence_stmt = occurrence_stmt.where(RecurringOccurrence.honcho_workspace_id == workspace_id)
        progress_stmt = progress_stmt.where(ObjectiveProgress.honcho_workspace_id == workspace_id)
    if session_id:
        trace_stmt = trace_stmt.where(ExtractionTrace.honcho_session_id == session_id)
        recurrence_stmt = recurrence_stmt.where(RecurringIntention.honcho_session_id == session_id)
        progress_stmt = progress_stmt.where(ObjectiveProgress.honcho_session_id == session_id)
    if message_id is not None:
        trace_stmt = trace_stmt.where(ExtractionTrace.honcho_message_id == message_id)
        recurrence_stmt = recurrence_stmt.where(RecurringIntention.honcho_message_id == message_id)
        progress_stmt = progress_stmt.where(ObjectiveProgress.honcho_message_id == message_id)
    traces = (await db.execute(trace_stmt.order_by(ExtractionTrace.created_at.desc()).limit(limit))).scalars().all()
    recurrences = (await db.execute(recurrence_stmt)).scalars().all()
    occurrences = (await db.execute(occurrence_stmt)).scalars().all()
    if workspace_id or session_id:
        recurrence_ids = {item.id for item in recurrences}
        occurrences = [item for item in occurrences if item.recurring_intention_id in recurrence_ids]
    progress = (await db.execute(progress_stmt)).scalars().all()

    return {
        "count": len(decisions),
        "decisions": decisions,
        "open_loops": [
            {
                "id": str(l.id),
                "title": l.title,
                "summary": l.summary,
                "status": l.status.value,
                "resolution_evidence": l.resolution_evidence,
            }
            for l in open_loops
        ],
        "suppressions": [
            {
                "id": str(s.id),
                "target_type": s.target_type.value,
                "topic_or_entity": s.topic_or_entity,
                "reason": s.reason,
                "surface_scope": s.surface_scope,
                "suppressed_until": s.suppressed_until.isoformat() if s.suppressed_until else None,
                "status": s.status.value,
            }
            for s in suppressions
        ],
        "epistemic_annotations": [
            {
                "id": str(ep.id),
                "perspective_peer_id": ep.perspective_peer_id,
                "target_peer_id": ep.target_peer_id,
                "provenance_type": ep.provenance_type.value,
                "claim_summary": ep.claim_summary,
            }
            for ep in epistemics
        ],
        "clarifications": [
            {
                "id": str(item.id),
                "clarification_type": item.clarification_type.value,
                "description": item.description,
                "candidates_json": item.candidates_json,
                "status": item.status.value,
            }
            for item in clarifications
        ],
        "extraction_traces": [{"stage": t.stage, "item_key": t.item_key, "status": t.status,
            "detail": t.detail_json, "model": t.model} for t in traces],
        "recurring_intentions": [{"id": str(r.id), "title": r.title, "cadence": r.cadence,
            "status": r.status.value, "source_message_id": r.honcho_message_id} for r in recurrences],
        "recurring_occurrences": [{"id": str(o.id), "recurring_intention_id": str(o.recurring_intention_id),
            "user_day": o.user_day.isoformat(), "status": o.status.value} for o in occurrences],
        "objective_progress": [{"id": str(p.id), "title": p.title, "amount": p.amount,
            "unit": p.unit, "expectation_id": str(p.expectation_id) if p.expectation_id else None} for p in progress],
    }
