"""Executive layer endpoints: tick (cheap scan, model only for worlds with a due wake), wake (external events), policy, intents, action receipts."""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db import get_async_session
from src.models.work_item import WorkItem
from src.services import executive

router = APIRouter(prefix="/v1/executive", tags=["executive"])


class WorldRef(BaseModel):
    workspace_id: str
    owner: str


class PolicyRequest(WorldRef):
    policy: Dict[str, Any]


class SpeakCandidatesRequest(BaseModel):
    workspace_id: str


class OutboundRequest(WorldRef):
    intent_id: str
    text: str
    decision_id: Optional[str] = None
    message_id: Optional[str] = None            # the persisted app message that carried the intent out (exact causal link)


class WakeRequest(WorldRef):
    reason: str = "external_event"
    delay_seconds: int = 5
    detail: Optional[Dict[str, Any]] = None       # what happened (calendar change, tool result, product signal): shown to the executive


class ReceiptRequest(WorldRef):
    work_item_id: str
    status: str                          # succeeded | failed | partial
    result_ref: Optional[str] = None
    detail: Optional[str] = None


@router.post("/tick")
async def tick(db: AsyncSession = Depends(get_async_session)):
    from src.runtime_model import get_agenda_adapter
    adapter = get_agenda_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="no_model_credentials")
    return await executive.tick(db, adapter=adapter)


@router.post("/speak-candidates")
async def speak_candidates(req: SpeakCandidatesRequest, db: AsyncSession = Depends(get_async_session)):
    """Who has something the executive wants to raise right now (polled by the app's proactive scan; the initiative gate still decides at tick time)."""
    return await executive.speak_candidates(db, req.workspace_id)


@router.post("/outbound")
async def outbound(req: OutboundRequest, db: AsyncSession = Depends(get_async_session)):
    """The Runtime composed a message to carry out an intent: record what was actually said (exact link, called with the intent id the Runtime was given)."""
    return {"ok": await executive.record_outbound(db, req.workspace_id, req.owner, req.intent_id, req.text, req.decision_id, req.message_id)}


@router.post("/pending-actions-all")
async def pending_actions_all(req: SpeakCandidatesRequest, db: AsyncSession = Depends(get_async_session)):
    return await executive.pending_actions_all(db, req.workspace_id)


@router.post("/policy")
async def set_policy(req: PolicyRequest, db: AsyncSession = Depends(get_async_session)):
    return await executive.set_policy(db, req.workspace_id, req.owner, req.policy)


@router.get("/policy")
async def get_policy(workspace_id: str, owner: str, db: AsyncSession = Depends(get_async_session)):
    return await executive.get_policy(db, workspace_id, owner)


@router.post("/wake")
async def wake(req: WakeRequest, db: AsyncSession = Depends(get_async_session)):
    """An external reason to reconsider a world (calendar change, tool event, product signal). Recorded only if the world's policy enables the executive."""
    await executive.note_changed(db, req.workspace_id, req.owner, req.reason, delay_seconds=req.delay_seconds, detail=req.detail)
    return {"ok": True}


@router.get("/intents")
async def intents(workspace_id: str, owner: str, active_only: bool = True, db: AsyncSession = Depends(get_async_session)):
    stmt = select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner, WorkItem.source_agent == "executive", WorkItem.kind != "agenda")
    if active_only:
        stmt = stmt.where(WorkItem.status.in_(executive.ACTIVE_STATUSES))
    rows = (await db.execute(stmt.order_by(WorkItem.updated_at.desc()).limit(100))).scalars().all()
    return [{"id": str(r.id), "kind": r.kind, "title": r.action, "status": r.status, "importance": r.importance, "wake_at": r.wake_at.isoformat() if r.wake_at else None,
             "waiting_on": r.waiting_on, "tool": json.loads(r.tool_json) if r.tool_json else None, "receipt": json.loads(r.receipt_json) if r.receipt_json else None,
             "extra": json.loads(r.extra_json or "{}"), "run_id": r.run_id} for r in rows]


@router.get("/agenda")
async def agenda(workspace_id: str, owner: str, db: AsyncSession = Depends(get_async_session)):
    """What the companion is currently carrying across all concerns (its attention state), as last written by the executive."""
    row = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner, WorkItem.kind == "agenda"))).scalars().first()
    return (json.loads(row.extra_json or "{}").get("agenda") if row else None) or {"carrying": [], "sequence_note": None}


@router.get("/pending-actions")
async def pending_actions(workspace_id: str, owner: str, db: AsyncSession = Depends(get_async_session)):
    """Action intents cleared for execution by policy (the app / Runtime tool layer pulls these and reports a receipt)."""
    rows = (await db.execute(select(WorkItem).where(WorkItem.honcho_workspace_id == workspace_id, WorkItem.owner_peer_id == owner, WorkItem.source_agent == "executive",
                                                    WorkItem.kind == "act", WorkItem.status == "in_progress", WorkItem.receipt_json.is_(None)))).scalars().all()
    return [{"work_item_id": str(r.id), "title": r.action, "tool": json.loads(r.tool_json or "{}")} for r in rows]


@router.post("/receipt")
async def receipt(req: ReceiptRequest, background: BackgroundTasks, db: AsyncSession = Depends(get_async_session)):
    out = await executive.record_receipt(db, workspace_id=req.workspace_id, owner=req.owner, work_item_id=req.work_item_id, status=req.status,
                                         result_ref=req.result_ref, detail=req.detail, side_effects=False)
    if not out.get("ok"):
        raise HTTPException(status_code=404, detail=out.get("reason"))
    background.add_task(_after_receipt, req.workspace_id, req.owner, req.work_item_id, out["status"])
    return out


async def _after_receipt(workspace_id: str, owner: str, work_item_id: str, status: str) -> None:
    from src.db import async_session_maker
    async with async_session_maker() as db:
        await executive.after_receipt(db, workspace_id, owner, work_item_id, status)


class ApprovalRequest(WorldRef):
    work_item_id: str
    approved: bool


@router.post("/approve")
async def approve(req: ApprovalRequest, db: AsyncSession = Depends(get_async_session)):
    """The user's answer to a confirmation request: approval clears the pending action for execution; refusal cancels it."""
    import uuid
    row = await db.get(WorkItem, uuid.UUID(req.work_item_id))
    if row is None or row.honcho_workspace_id != req.workspace_id or row.owner_peer_id != req.owner:
        raise HTTPException(status_code=404, detail="unknown_work_item")
    extra = json.loads(row.extra_json or "{}")
    if req.approved and row.tool_json:
        row.kind, row.status = "act", "in_progress"
        extra["requires_confirmation"], extra["approved_by_user"] = False, True
    else:
        row.status = "cancelled"
    row.extra_json = json.dumps(extra)
    db.add(row)
    await db.commit()
    await executive.note_changed(db, req.workspace_id, req.owner, "approval", delay_seconds=5)
    return {"ok": True, "status": row.status}
