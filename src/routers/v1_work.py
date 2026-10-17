"""POST/GET /v1/work/*: the companion-owned working space (see services/companion_work.py).

No model call, no memory run, no consolidation or preparation side effect on any route here.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.services import companion_work as work

router = APIRouter(prefix="/v1/work", tags=["work"])


class ToolRequest(BaseModel):
    workspace_id: str
    owner: str
    companion_id: str
    surface: str
    tool: str
    args: Dict[str, Any] = {}
    sitting_id: str = ""
    conversation_id: str = ""


@router.post("/tool")
async def tool(req: ToolRequest, db: AsyncSession = Depends(get_async_session)):
    """What the companion's own work_read / work_write call executes. `text` is exactly what the model is shown."""
    try:
        return await work.run_tool(db, (req.workspace_id, req.owner, req.companion_id), surface=req.surface, tool=req.tool,
                                   args=req.args, sitting_id=req.sitting_id, conversation_id=req.conversation_id)
    except Exception as exc:
        await db.rollback()
        return {"ok": False, "code": "error", "text": f"Not done: the working space is unavailable ({type(exc).__name__})."}


@router.get("/context")
async def context(workspace_id: str, owner: str, companion_id: str, surface: str = "foreground",
                  db: AsyncSession = Depends(get_async_session)):
    lv = work.level(companion_id, surface)
    text = await work.context_block(db, (workspace_id, owner, companion_id), surface) if lv != "off" else ""
    return {"level": lv, "text": text}


def _item(i) -> Dict[str, Any]:
    return {"id": str(i.id), "title": i.title, "kind": i.kind, "status": i.status, "version": i.version, "text": i.text,
            "origin_surface": i.origin_surface, "origin_sitting_id": i.origin_sitting_id,
            "origin_conversation_id": i.origin_conversation_id,
            "created_at": i.created_at.isoformat(), "updated_at": i.updated_at.isoformat(),
            "closed_at": i.closed_at.isoformat() if i.closed_at else None}


@router.get("/items")
async def items(workspace_id: str, owner: str, companion_id: str, status: Optional[str] = None, limit: int = 50,
                db: AsyncSession = Depends(get_async_session)):
    """Operator/inspection read (not policy-gated: the owner's evidence). Companion-facing reads go through /tool."""
    rows = await work.list_items(db, (workspace_id, owner, companion_id), status=status or None, limit=max(1, min(limit, 200)))
    return {"items": [_item(i) for i in rows]}


@router.get("/items/{ref}")
async def item(ref: str, workspace_id: str, owner: str, companion_id: str, db: AsyncSession = Depends(get_async_session)):
    try:
        got = await work.get_with_events(db, (workspace_id, owner, companion_id), ref)
    except work.WorkError as exc:
        raise HTTPException(status_code=404, detail=exc.code) from exc
    return {**_item(got["item"]), "events": [
        {"version": e.version, "action": e.action, "author": e.author, "surface": e.surface, "sitting_id": e.sitting_id,
         "conversation_id": e.conversation_id, "text": e.text, "note": e.note,
         "evidence": json.loads(e.evidence_json or "[]"), "created_at": e.created_at.isoformat()} for e in got["events"]]}
