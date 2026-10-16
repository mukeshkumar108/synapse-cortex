"""POST /v1/memory/*: the replacement understanding pipeline for Sophie.

- POST /consolidate: accept a COMPLETED session, run consolidation in the
  background, return 202 immediately (the Runtime never waits on it).
- GET /run/{run_id}: poll a consolidation's status + summary.
- GET /preparation: the latest cached perspective (pure read, no model).
- GET /state: notebook + ledger + arc for inspection/debugging.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import async_session_maker, get_async_session
from src.services import memory_pipeline

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/memory", tags=["memory"])


class ConsolidateRequest(BaseModel):
    workspace_id: str
    owner: str
    conversation_id: str
    session_id: str
    messages: List[Dict[str, Any]]          # full transcript, both sides: {id, speaker, text}
    companion_id: str = "sophie"


async def _run_consolidation(workspace_id: str, owner: str, conversation_id: str, session_id: str,
                             messages: List[Dict[str, Any]], companion_id: str) -> None:
    try:
        async with async_session_maker() as db:
            try:
                await memory_pipeline.consolidate(
                    db, workspace_id=workspace_id, owner=owner, conversation_id=conversation_id,
                    session_id=session_id, messages=messages, companion_id=companion_id)
            except Exception:
                logger.exception("memory consolidation failed for %s %s", owner, session_id)
                try:
                    await db.rollback()
                except Exception:
                    pass
    except Exception:
        logger.exception("memory consolidation session failed for %s %s", owner, session_id)


@router.post("/consolidate", status_code=202)
async def consolidate(req: ConsolidateRequest, db: AsyncSession = Depends(get_async_session)):
    if not req.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")
    for m in req.messages:
        if set(m) < {"id", "speaker", "text"}:
            raise HTTPException(status_code=422, detail="messages need id, speaker, text")
    try:
        run_id = await memory_pipeline.create_run(
            db, workspace_id=req.workspace_id, owner=req.owner, conversation_id=req.conversation_id,
            session_id=req.session_id, message_count=len(req.messages))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"run_create_failed:{type(exc).__name__}") from exc
    asyncio.create_task(_run_consolidation(
        req.workspace_id, req.owner, req.conversation_id, req.session_id,
        [dict(m) for m in req.messages], req.companion_id))
    return {"status": "accepted", "run_id": run_id}


@router.get("/run/{run_id}")
async def run_status(run_id: str, db: AsyncSession = Depends(get_async_session)):
    row = await memory_pipeline.get_run(db, run_id)
    if row is None:
        raise HTTPException(status_code=404, detail="run_not_found")
    try:
        bundle = json.loads(row.bundle_json or "{}")
    except Exception:
        bundle = {}
    out = {"run_id": str(row.id), "status": row.status,
           "conversation_id": row.conversation_id, "session_id": row.session_id,
           "covered_ids": json.loads(row.covered_ids_json or "[]"),
           "started_at": row.started_at.isoformat() if row.started_at else None,
           "finished_at": row.finished_at.isoformat() if row.finished_at else None}
    if row.status in ("consolidated", "replay_noop", "failed", "empty"):
        out["summary"] = {k: bundle.get(k) for k in (
            "message_count", "new_message_count", "findings", "arc_after",
            "ledger_added", "preparation_text", "ms_total") if k in bundle}
    return out


@router.get("/preparation")
async def preparation(workspace_id: str, owner: str, db: AsyncSession = Depends(get_async_session)):
    prep = await memory_pipeline.get_preparation(db, workspace_id=workspace_id, owner=owner)
    if prep is None:
        return {"found": False}
    return {"found": True, **prep}


class PrepareRequest(BaseModel):
    workspace_id: str
    owner: str


@router.post("/prepare")
async def prepare_now(req: PrepareRequest, db: AsyncSession = Depends(get_async_session)):
    """Compose a fresh preparation now (time or state moved on). Supersedes the
    cached one. Background-worthy; awaited here for operator use."""
    try:
        prep = await memory_pipeline.prepare(db, workspace_id=req.workspace_id, owner=req.owner)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"prepare_failed:{type(exc).__name__}") from exc
    if not prep.get("text"):
        raise HTTPException(status_code=503, detail="prepare_no_model")
    return {"found": True, "text": prep["text"], "id": prep.get("id"),
            "inputs_fingerprint": prep.get("inputs_fingerprint"), "model": prep.get("model")}


@router.get("/state")
async def state(workspace_id: str, owner: str, db: AsyncSession = Depends(get_async_session)):
    return await memory_pipeline.read_state(db, workspace_id=workspace_id, owner=owner)


class IndependentSittingRequest(BaseModel):
    workspace_id: str
    owner: str
    sitting_id: Optional[str] = None
    max_iterations: int = 8
    max_tool_calls: int = 10
    max_model_calls: int = 12


async def _run_solo(workspace_id: str, owner: str, sitting_id: str, budget: Dict[str, int]) -> None:
    try:
        async with async_session_maker() as db:
            try:
                from src.services import exploration
                from src.services.exploration import SoloBudget
                await exploration.run_independent_sitting(
                    db, workspace_id=workspace_id, owner=owner, sitting_id=sitting_id,
                    budget=SoloBudget(max_iterations=min(budget["max_iterations"], 12),
                                      max_tool_calls=min(budget["max_tool_calls"], 15),
                                      max_model_calls=min(budget["max_model_calls"], 20)))
            except Exception:
                logger.exception("independent sitting failed for %s %s", owner, sitting_id)
                try:
                    await db.rollback()
                except Exception:
                    pass
    except Exception:
        logger.exception("independent sitting session failed for %s %s", owner, sitting_id)


@router.post("/independent-sitting", status_code=202)
async def independent_sitting(req: IndependentSittingRequest, db: AsyncSession = Depends(get_async_session)):
    """Start one of Sophie's independent sittings (bounded, background). Her
    time is hers: she may explore, ask, read, make — or stop immediately."""
    import uuid as _uuid
    sitting_id = (req.sitting_id or f"solo-{_uuid.uuid4().hex[:8]}").strip() or f"solo-{_uuid.uuid4().hex[:8]}"
    asyncio.create_task(_run_solo(req.workspace_id, req.owner, sitting_id,
                                  {"max_iterations": req.max_iterations, "max_tool_calls": req.max_tool_calls,
                                   "max_model_calls": req.max_model_calls}))
    return {"status": "accepted", "sitting_id": sitting_id,
            "conversation_id": f"solo-{sitting_id}"}
