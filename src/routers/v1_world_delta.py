"""POST /v1/world/delta: producers submit typed WorldDelta candidates; Cortex grounds, judges (ambiguous only, optional), materialises, and
returns a receipt (`covered_through`, ref -> id map, rejections) (docs/WORLD_CONTRACT.md)."""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.schemas.world_delta import WorldDelta
from src.services.world_materializer import materialize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/world", tags=["world-delta"])


@router.post("/delta")
async def submit_world_delta(delta: WorldDelta, db: AsyncSession = Depends(get_async_session)):
    try:
        return await materialize(db, delta)
    except Exception as exc:  # a bad delta must never corrupt canonical state or take the service down
        await db.rollback()
        logger.exception("world delta materialisation failed")
        raise HTTPException(status_code=500, detail=f"materialisation_failed:{type(exc).__name__}") from exc


class InterpretRequest(BaseModel):
    workspace_id: str
    owner: str
    session_id: str
    messages: List[Dict[str, str]]
    speakers: Dict[str, str] = {}
    policy: str = "grounded"
    constitution: Optional[Dict[str, str]] = None      # {actor, toward, text}: product-authored by the trusted caller, never extracted
    covered_ordinal: int = 0


@router.post("/interpret")
async def interpret_world(req: InterpretRequest, db: AsyncSession = Depends(get_async_session)):
    """One reasoning pass over new evidence + current world state; the result is materialised and a receipt (with the new snapshot version) returned."""
    from src.runtime_model import get_agenda_adapter
    from src.services import world_interpreter
    adapter = get_agenda_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="no_model_credentials")
    if len(req.messages) < 2 or any(set(m) < {"id", "speaker", "text"} for m in req.messages):
        raise HTTPException(status_code=422, detail="messages need id, speaker, text")
    try:
        receipt = await world_interpreter.interpret(
            db, workspace_id=req.workspace_id, owner=req.owner, session_id=req.session_id, messages=req.messages, speakers=req.speakers,
            policy=req.policy, constitution=req.constitution, adapter=adapter, covered_ordinal=req.covered_ordinal, matter_adapter=adapter)
        return receipt
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("world interpretation failed")
        raise HTTPException(status_code=500, detail=f"interpretation_failed:{type(exc).__name__}") from exc


@router.post("/version")
async def world_version(req: Dict[str, str], db: AsyncSession = Depends(get_async_session)):
    """Cheap freshness probe: the version of the current resident snapshot for a world, so the Runtime can refresh its cached packet exactly when
    Cortex has materialised something new (no polling interval, no recompilation)."""
    from sqlmodel import select
    from src.models.world_model import WorldModelSnapshot
    workspace_id, owner = req.get("workspace_id"), req.get("owner")
    if not workspace_id or not owner:
        raise HTTPException(status_code=422, detail="workspace_id and owner required")
    snap = (await db.execute(select(WorldModelSnapshot).where(
        WorldModelSnapshot.honcho_workspace_id == workspace_id, WorldModelSnapshot.owner_peer_id == owner,
        WorldModelSnapshot.superseded_by_id.is_(None)).order_by(WorldModelSnapshot.compiled_at.desc()).limit(1))).scalars().first()
    return {"version": snap.version if snap else None}
