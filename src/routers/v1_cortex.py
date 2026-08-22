import logging
from typing import Any, Dict, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.services.cortex_handshake_service import CortexHandshakeService
from src.services.cortex_packet_service import CortexPacketService
from src.services.cortex_router_service import CortexRouterService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cortex", tags=["cortex"])

handshake_service = CortexHandshakeService()
packet_service = CortexPacketService()
router_service = CortexRouterService()


class HandshakeRequest(BaseModel):
    workspace_id: str
    session_id: str
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
    )
