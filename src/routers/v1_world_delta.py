"""POST /v1/world/delta: producers submit typed WorldDelta candidates; Cortex grounds, judges (ambiguous only, optional), materialises, and
returns a receipt (`covered_through`, ref -> id map, rejections) (docs/WORLD_CONTRACT.md)."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
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
