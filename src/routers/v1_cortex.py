import logging
from typing import Any, Dict, Literal, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.models.commitment_candidate import CommitmentCandidateStatus
from src.services.commitment_candidate_service import CommitmentCandidateService
from src.services.cortex_handshake_service import CortexHandshakeService
from src.services.cortex_packet_service import CortexPacketService
from src.services.cortex_router_service import CortexRouterService
from src.schemas.candidate import ExtractionCandidate

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cortex", tags=["cortex"])

handshake_service = CortexHandshakeService()
packet_service = CortexPacketService()
router_service = CortexRouterService()
candidate_service = CommitmentCandidateService()


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
