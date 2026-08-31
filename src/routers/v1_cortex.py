import logging
import time
from typing import Any, Dict, Literal, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.models.commitment_candidate import CommitmentCandidateStatus
from src.services.commitment_candidate_service import CommitmentCandidateService
from src.services.cortex_handshake_service import CortexHandshakeService
from src.services.cortex_packet_service import CortexPacketService
from src.services.cortex_router_service import CortexRouterService
from src.services.working_set_service import WorkingSetService
from src.schemas.candidate import ExtractionCandidate
from src.models.expectation import Expectation
from src.models.open_loop import OpenLoop
from src.models.operational_state import RecurringIntention
from sqlmodel import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cortex", tags=["cortex"])

handshake_service = CortexHandshakeService()
packet_service = CortexPacketService()
router_service = CortexRouterService()
candidate_service = CommitmentCandidateService()
working_set_service = WorkingSetService()


class WorkingSetRequest(BaseModel):
    workspace_id: str
    session_id: str
    peer_id: Optional[str] = None
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"
    turn_text: str = Field(default="", max_length=4000)
    current_message_id: Optional[str] = None
    posture: Optional[str] = None
    conversational_operation: Optional[str] = None
    director_hints: Optional[Dict[str, Any]] = None


@router.post("/working-set")
async def get_cortex_working_set(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Bounded per-turn working set (L0 HOT / L1 WARM / L2 COLD refs).

    Consumes the same attention packet / intelligence brief used by the
    proactive path and Inspector; it never builds a second interpretation."""
    started = time.perf_counter()
    packet = await packet_service.compile_attention_packet(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        owner_peer_id=req.peer_id,
    )
    working_set = working_set_service.compile_working_set(
        packet,
        turn_text=req.turn_text,
        current_message_id=req.current_message_id,
        posture=req.posture,
        conversational_operation=req.conversational_operation,
        director_hints=req.director_hints,
    )
    # WS10: per-hop evidence — Cortex-side cost of this foreground fetch,
    # so the runtime/app can attribute waterfall time correctly.
    working_set["metrics"]["cortex_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return working_set


@router.post("/handover")
async def get_session_handover(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Tiny product-edited session handover (~200-400 tokens).

    One compact foreground object compiled from the same attention packet as
    the working set: what matters for THIS product/person now, what changed,
    what is unresolved, what to avoid. Replaceable derived projection, not
    canonical state; JIT detail stays available via /evidence."""
    from src.services.handover_service import compile_handover

    started = time.perf_counter()
    packet = await packet_service.compile_attention_packet(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        owner_peer_id=req.peer_id,
    )
    result = compile_handover(packet, product=(req.director_hints or {}).get("product"), now=req.now)
    # Deterministic follow-up accounting: surfacing an ask_now objective in
    # the handover records the ask opportunity against today's occurrence so
    # the duty cannot repeat endlessly nor silently vanish (code owns it).
    try:
        for obj in (result.get("current_window") or {}).get("objectives") or []:
            occ_id = obj.get("ask_now") and obj.get("occurrence_id")
            if occ_id:
                await db.execute(text(
                    "update recurring_occurrences set asked_at = :now, "
                    "ask_count = ask_count + 1 where id = :id"
                ), {"now": (req.now or datetime.now(timezone.utc)).replace(tzinfo=None), "id": occ_id})
        await db.commit()
    except Exception:
        await db.rollback()
    result["metrics"]["cortex_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return result


@router.get("/evidence")
async def get_cortex_evidence(
    workspace_id: str = Query(...),
    ref: str = Query(...),
    ref_type: Optional[str] = Query(None),
    peer_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    """JIT retrieval: resolve a compact working-set reference into its deeper
    stored detail. Bounded, provenance-preserving; raw Honcho message bodies
    stay in Honcho and are resolved by the runtime that owns that client."""
    try:
        row_uuid = __import__("uuid").UUID(ref)
    except ValueError:
        row_uuid = None

    def scoped(model):
        # Mirror packet owner_scope: owner rows are workspace/owner-visible;
        # NULL-owner rows are session-scoped legacy state.
        cond = [model.honcho_workspace_id == workspace_id]
        if peer_id and hasattr(model, "owner_peer_id"):
            from sqlalchemy import or_, and_
            session_cond = (
                model.honcho_session_id == session_id if session_id else None
            )
            cond.append(or_(
                model.owner_peer_id == peer_id,
                and_(model.owner_peer_id.is_(None), session_cond)
                if session_cond is not None else model.owner_peer_id.is_(None),
            ))
        return cond

    found = None
    if row_uuid is not None:
        row = (await db.execute(
            select(Expectation).where(Expectation.id == row_uuid,
                                      *scoped(Expectation))
        )).scalar_one_or_none()
        if row:
            found = {
                "type": "expectation", "id": str(row.id),
                "title": row.title, "summary": row.summary,
                "outcome_state": row.outcome_state.value,
                "expectation_type": row.expectation_type.value,
                "raw_temporal_phrase": row.raw_temporal_phrase,
                "evidence": row.resolution_evidence,
                "honcho_message_id": row.honcho_message_id,
            }
        if found is None:
            row = (await db.execute(
                select(OpenLoop).where(OpenLoop.id == row_uuid,
                                       *scoped(OpenLoop))
            )).scalar_one_or_none()
            if row:
                found = {
                    "type": "open_loop", "id": str(row.id),
                    "title": getattr(row, "title", None),
                    "summary": getattr(row, "summary", None),
                    "status": str(getattr(row, "status", "")),
                    "honcho_message_id": getattr(row, "honcho_message_id", None),
                }
        if found is None:
            row = (await db.execute(
                select(RecurringIntention).where(
                    RecurringIntention.id == row_uuid,
                    *scoped(RecurringIntention))
            )).scalar_one_or_none()
            if row:
                found = {
                    "type": "recurring_intention", "id": str(row.id),
                    "title": row.title, "cadence": row.cadence,
                    "preferred_window": row.preferred_window,
                    "honcho_message_id": row.honcho_message_id,
                }
    if found is None and not ref.startswith("message-"):
        from src.models.commitment_candidate import CommitmentCandidate
        row = (await db.execute(
            select(CommitmentCandidate).where(
                CommitmentCandidate.honcho_workspace_id == workspace_id,
                CommitmentCandidate.candidate_key == ref,
            )
        )).scalar_one_or_none()
        if row is not None:
            found = {
                "type": "commitment_candidate", "id": row.candidate_key,
                "title": row.title, "notes": row.notes,
                "raw_evidence": row.evidence_verbatim,
                "evidence_class": row.evidence_class,
                "status": str(row.status),
            }
    if found is None:
        raise HTTPException(status_code=404, detail="reference not resolvable")
    return found


class HandshakeRequest(BaseModel):
    workspace_id: str
    session_id: str
    peer_id: Optional[str] = None
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"
    last_interaction_time: Optional[datetime] = None
    chronology: Optional[Dict[str, Any]] = None


class RouteRequest(BaseModel):
    query: str


@router.post("/handshake")
async def get_cortex_handshake(
    req: HandshakeRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Compiles deterministic Cortex Handshake.
    Answers: "How should Sophie enter this interaction?"
    """
    return await handshake_service.compile_handshake(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        last_interaction_time=req.last_interaction_time,
        chronology=req.chronology,
        owner_peer_id=req.peer_id,
    )


@router.post("/route")
async def route_cortex_query(req: RouteRequest):
    """
    Routes query to information source (HONCHO_MEMORY, SYNAPSE_STATE, BOTH, CURRENT_SESSION, NO_RETRIEVAL).
    """
    return router_service.route_query(req.query)


@router.get("/attention-packet")
async def get_cortex_attention_packet(
    workspace_id: str = Query(...),
    session_id: str = Query(...),
    peer_id: Optional[str] = Query(None),
    now: Optional[datetime] = Query(None),
    timezone_str: str = Query("UTC", alias="timezone"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Compiles dynamic, prose-free Attention & Continuity Packet.
    """
    eval_now = now or datetime.now(timezone.utc)
    return await packet_service.compile_attention_packet(
        db=db,
        workspace_id=workspace_id,
        session_id=session_id,
        now=eval_now,
        timezone_str=timezone_str,
        owner_peer_id=peer_id,
    )


@router.get("/commitment-candidates")
async def list_commitment_candidates(
    workspace_id: str = Query(...),
    owner_peer_id: str = Query(...),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_session),
):
    """Bounded listing of derived commitment candidates (Sophie noticed)."""
    rows = await candidate_service.list_pending(
        db, workspace_id=workspace_id, owner_peer_id=owner_peer_id, limit=limit
    )
    return {
        "candidates": [
            {
                "candidate_key": row.candidate_key,
                "canonical_key": row.canonical_key,
                "title": row.title,
                "notes": row.notes,
                "evidence_verbatim": row.evidence_verbatim,
                "evidence_class": row.evidence_class,
                "authority": row.authority.value,
                "source_message_id": row.source_message_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


class CandidateMarkRequest(BaseModel):
    workspace_id: str
    owner_peer_id: str
    candidate_key: str
    status: Literal["materialized", "dismissed"]
    source_object_id: Optional[str] = None


class CandidateProposal(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=280)
    notes: Optional[str] = Field(default=None, max_length=2000)
    evidence_verbatim: str = Field(min_length=1, max_length=2000)
    evidence_class: Literal[
        "implicit_self_commitment", "sophie_proposed_user_accepted",
        "sophie_proposed_soft_acceptance", "vague_self_talk",
    ] = "implicit_self_commitment"
    authority: Literal["act", "ask"] = "ask"
    temporal_phrase: Optional[str] = Field(default=None, max_length=160)


class CandidateProposalRequest(BaseModel):
    workspace_id: str
    session_id: str
    owner_peer_id: str
    source_message_id: str
    candidates: list[CandidateProposal] = Field(max_length=12)


@router.post("/commitment-candidates/propose")
async def propose_commitment_candidates(
    req: CandidateProposalRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Trusted chief-of-staff/editorial proposals. This endpoint only creates
    derived candidates; it never mutates a canonical Task."""
    accepted = []
    for item in req.candidates:
        candidate = ExtractionCandidate(
            candidate_key=item.key,
            observation=item.notes or item.title,
            raw_evidence=item.evidence_verbatim,
            canonical_title=item.title,
            operational_kind="commitment_candidate",
            evidence_class=item.evidence_class,
            authority=item.authority,
            temporal_phrase=item.temporal_phrase,
            actor_peer_id=req.owner_peer_id,
            subject_peer_id=req.owner_peer_id,
            confidence=1.0,
            extractor_version="chief-of-staff-v1",
        )
        row = await candidate_service.upsert_from_candidate(
            db,
            workspace_id=req.workspace_id,
            session_id=req.session_id,
            owner_peer_id=req.owner_peer_id,
            message_id=req.source_message_id,
            candidate=candidate,
            now=datetime.now(timezone.utc),
        )
        if row is not None:
            accepted.append(row.candidate_key)
    return {"status": "accepted", "candidate_keys": accepted}


@router.post("/commitment-candidates/mark")
async def mark_commitment_candidate(
    req: CandidateMarkRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Durable candidate state transition: materialized (promoted to a
    canonical Task) or dismissed (never re-proposed for the same commitment)."""
    row = await candidate_service.mark(
        db,
        workspace_id=req.workspace_id,
        owner_peer_id=req.owner_peer_id,
        candidate_key=req.candidate_key,
        status=CommitmentCandidateStatus(req.status),
        source_object_id=req.source_object_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    return {
        "status": "ok",
        "candidate_key": row.candidate_key,
        "candidate_status": row.status.value,
    }
