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
from src.services.expectation_engine import derive_expectation_read_model

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/debug", tags=["debug"])


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
    }
