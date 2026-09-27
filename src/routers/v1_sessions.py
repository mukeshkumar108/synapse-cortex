"""Session lifecycle endpoints (Cortex side).

Cortex owns NO session lifecycle: the app/runtime owns open/close and calls
this boundary with the completed transcript. Two modes:

- shadow (default): validated V2 reconstruction proposal + would-apply
  report. Never mutates interpreted state. Safe to call at session end,
  scene rollover, idle, or as a daily catch-up retry.
- apply: shadow proposal PLUS the bounded AUTO/GUARDED tiers applied
  (creation through existing guards, guarded resolutions, attention
  holds, audit relations). Requires SESSION_CONSOLIDATION_APPLY=1 or the
  call degrades to shadow with a flag in the response. Destructive or
  user-visible-muting proposals (discards, suppressions, low-confidence
  mutations) stay deferred in both modes.

Raw evidence stays canonical; every run writes one ConsolidationRun
ledger row so applied state can be revisited. A later pass can retry.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.models.consolidation import ConsolidationRun
from src.services.session_apply import apply_enabled, apply_reconstruction
from src.services.session_consolidation import (
    SessionTurn,
    StartSnapshot,
    SnapshotMatter,
)
from src.services.session_reconstruction import reconstruct_session

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/sessions", tags=["sessions"])


class TranscriptTurn(BaseModel):
    message_id: str
    speaker: str = "user"
    text: str = ""


class SnapshotMatterIn(BaseModel):
    id: str
    kind: str = "open_loop"
    title: str = ""
    status: str = ""
    owner: str = ""


class StartSnapshotIn(BaseModel):
    matters: List[SnapshotMatterIn] = Field(default_factory=list)
    attentions: List[str] = Field(default_factory=list)
    suppressions: List[str] = Field(default_factory=list)
    people: List[str] = Field(default_factory=list)


class ConsolidateRequest(BaseModel):
    workspace_id: str
    session_id: str
    transcript: List[TranscriptTurn] = Field(default_factory=list)
    start_snapshot: Optional[StartSnapshotIn] = None
    mode: str = Field(default="shadow")  # shadow | apply
    user_peer_id: str = Field(default="user")
    model_id: Optional[str] = None


@router.post("/consolidate", status_code=status.HTTP_200_OK)
async def consolidate(
    payload: ConsolidateRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Run V2 session reconstruction; optionally apply bounded tiers.

    Runtime contract: POST workspace_id + session_id + transcript
    [{message_id, speaker, text}] + user_peer_id (+ optional start_snapshot
    captured at session start; omitted = server captures current state and
    treats session-created rows as review lane). Response carries the
    validated proposal, would-apply report, applied/deferred lists, and the
    run_id ledger key. Apply mode without the server flag degrades to
    shadow and says so.
    """
    from src.services import semantic_judge

    snapshot: Optional[StartSnapshot] = None
    if payload.start_snapshot is not None:
        snapshot = StartSnapshot(
            matters=[SnapshotMatter(
                id=m.id, kind=m.kind, title=m.title,
                status=m.status, owner=m.owner)
                for m in payload.start_snapshot.matters],
            attentions=list(payload.start_snapshot.attentions),
            suppressions=list(payload.start_snapshot.suppressions),
            people=list(payload.start_snapshot.people),
        )
    result = await reconstruct_session(
        db, workspace_id=payload.workspace_id,
        session_id=payload.session_id,
        transcript=[SessionTurn(message_id=t.message_id, speaker=t.speaker,
                                text=t.text) for t in payload.transcript],
        start_snapshot=snapshot,
        model_id=payload.model_id,
        user_peer_id=payload.user_peer_id,
    )
    want_apply = payload.mode == "apply"
    applied: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    apply_note = ""
    effective_mode = "shadow"
    if want_apply and result.error == "":
        if apply_enabled():
            report = await apply_reconstruction(
                db, workspace_id=payload.workspace_id,
                session_id=payload.session_id, result=result,
                user_peer_id=payload.user_peer_id)
            applied = report["applied"]
            deferred = report["deferred"]
            effective_mode = "apply"
        else:
            apply_note = "apply_requested_but_disabled"
    run = ConsolidationRun(
        honcho_workspace_id=payload.workspace_id,
        honcho_session_id=payload.session_id,
        mode=effective_mode,
        model=payload.model_id or semantic_judge.judge_model_id(),
        summary=result.summary[:500],
        accepted_count=len(result.accepted),
        rejected_count=len(result.rejected),
        applied_count=len(applied),
        deferred_count=len(deferred),
        error=result.error,
        prompt_chars=result.prompt_chars,
        latency_s=result.latency_s,
        owner_peer_id=payload.user_peer_id,
    )
    db.add(run)
    try:
        await db.commit()
    except Exception as err:
        logger.warning("consolidation run ledger failed: %s", err)
        try:
            await db.rollback()
        except Exception:
            pass
    return {
        "status": effective_mode,
        "run_id": str(run.id),
        "summary": result.summary,
        "error": result.error,
        "prompt_chars": result.prompt_chars,
        "latency_s": result.latency_s,
        "apply_note": apply_note,
        "accepted": [{"op": o.op, "data": o.data, "confidence": o.confidence,
                      "rationale": o.rationale} for o in result.accepted],
        "rejected": result.rejected,
        "discards": result.discards,
        "provisional_marks": result.provisional_marks,
        "would_apply": result.would_apply,
        "applied": applied,
        "deferred": deferred,
    }
