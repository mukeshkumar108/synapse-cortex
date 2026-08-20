from datetime import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.schemas.followup_packet import FollowupItem, FollowupPacketResponse
from src.services.persistence import get_active_expectations_for_session
from src.services.expectation_engine import derive_expectation_read_model

router = APIRouter(prefix="/v1/context", tags=["context"])


@router.get("/followup-packet", response_model=FollowupPacketResponse)
async def get_followup_packet(
    workspace_id: str = Query(..., description="Honcho workspace ID"),
    session_id: str = Query(..., description="Honcho session ID"),
    now: datetime = Query(..., description="Current ISO timestamp"),
    timezone: str = Query("UTC", description="User timezone string"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Returns prose-free, deterministic follow-up context packet for the session.
    Calculates dynamic temporal/outcome states using zero LLM calls.
    """
    expectations = await get_active_expectations_for_session(db, workspace_id, session_id)
    
    followups = []
    for exp in expectations:
        read_model = derive_expectation_read_model(exp, now)
        if read_model["followup_eligible"]:
            followups.append(
                FollowupItem(
                    id=read_model["id"],
                    title=read_model["title"],
                    expected_window_label=read_model["expected_window_label"],
                    temporal_state=read_model["temporal_state"],
                    outcome_state=read_model["outcome_state"],
                    followup_eligible=read_model["followup_eligible"],
                    reason=read_model["reason"],
                    honcho_message_id=read_model["honcho_message_id"],
                )
            )

    return FollowupPacketResponse(followups=followups)
