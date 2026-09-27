"""Session lifecycle endpoints (Cortex side).

Identity contract (see session_reconstruction docstring):
- `session_id` is the STABLE durable lane (chat id). Every row this
  boundary reads or writes scopes to it, so reconstructed state lands in
  the exact namespace handover/attention/reconciliation read next time.
- `temporal_session_id` (optional) is this conversation's boundary id.
  Provenance only: traces, run ledger, created-row message ids. Never
  state scoping. Callers passing a temporal id as session_id fragment
  durable state into per-conversation namespaces — do not do that.

Snapshot ownership: Cortex captures the authoritative start snapshot
server-side on every call. A caller-supplied snapshot contributes people
hints only; its matters never suppress or replace authoritative rows.

Evidence: transcript (raw, authoritative) + receipts (factual, quotable)
+ checkpoints (navigation-only, never evidence). Long transcripts are
segmented into bounded raw windows (no cap increase, no summary-as-truth):
apply mode continues through applied rows; shadow mode carries prior
proposals as context. Coverage accounting is explicit.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.models.consolidation import ConsolidationRun
from src.services.session_apply import apply_enabled
from src.services.session_consolidation import (
    SessionTurn,
    StartSnapshot,
)
from src.services.session_reconstruction import (
    consolidate_long_session,
    reconstruct_session,
)

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


class EvidenceItem(BaseModel):
    kind: str = Field(default="note")
    label: str = Field(default="")
    text: str = Field(default="")


class ConsolidateRequest(BaseModel):
    workspace_id: str
    session_id: str
    transcript: List[TranscriptTurn] = Field(default_factory=list)
    start_snapshot: Optional[StartSnapshotIn] = None
    mode: str = Field(default="shadow")  # shadow | apply
    user_peer_id: str = Field(default="user")
    model_id: Optional[str] = None
    # Temporal boundary provenance (never state scoping — see contract).
    temporal_session_id: Optional[str] = None
    # Working-memory checkpoints: navigation only, never evidence.
    checkpoints: List[EvidenceItem] = Field(default_factory=list)
    # Action receipts: factual session evidence, quotable as receipt:N.
    receipts: List[EvidenceItem] = Field(default_factory=list)


def _to_snapshot(payload: ConsolidateRequest) -> Optional[StartSnapshot]:
    if payload.start_snapshot is None:
        return None
    from src.services.session_consolidation import SnapshotMatter
    return StartSnapshot(
        matters=[SnapshotMatter(
            id=m.id, kind=m.kind, title=m.title,
            status=m.status, owner=m.owner)
            for m in payload.start_snapshot.matters],
        attentions=list(payload.start_snapshot.attentions),
        suppressions=list(payload.start_snapshot.suppressions),
        people=list(payload.start_snapshot.people),
    )


@router.post("/consolidate", status_code=status.HTTP_200_OK)
async def consolidate(
    payload: ConsolidateRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Run V2 session reconstruction; optionally apply bounded tiers.

    Runtime contract: POST lane session_id + temporal_session_id +
    transcript [{message_id, speaker, text}] + user_peer_id (+ optional
    checkpoints/receipts; optional start_snapshot for people hints only).
    Response: validated proposal, would-apply, applied/deferred (apply
    mode with server flag), coverage for long sessions, run_id ledger key.
    Apply without the flag degrades to shadow and says so.
    """
    from src.services import semantic_judge
    from src.services.session_consolidation import capture_snapshot

    turns = [SessionTurn(message_id=t.message_id, speaker=t.speaker,
                         text=t.text) for t in payload.transcript]
    # Authoritative start snapshot is Cortex-owned: capture server-side.
    # A caller snapshot contributes people hints only — its matters can
    # never suppress authoritative rows (partial snapshots must not read
    # as "nothing else exists").
    authoritative = await capture_snapshot(
        db, workspace_id=payload.workspace_id, session_id=payload.session_id)
    snapshot_source = "authoritative"
    if payload.start_snapshot is not None:
        caller_people = [p for p in payload.start_snapshot.people if p]
        seen = {p.lower() for p in authoritative.people}
        merged = list(authoritative.people) + [
            p for p in caller_people if p.lower() not in seen][:12]
        if len(merged) != len(authoritative.people):
            authoritative = StartSnapshot(
                matters=list(authoritative.matters),
                attentions=list(authoritative.attentions),
                suppressions=list(authoritative.suppressions),
                people=merged)
            snapshot_source = "authoritative+caller-people"
    checkpoints = [{"label": c.label, "text": c.text} for c in payload.checkpoints]
    receipts = [{"kind": c.kind, "text": c.text} for c in payload.receipts]
    want_apply = payload.mode == "apply"
    aggregate = await consolidate_long_session(
        db, workspace_id=payload.workspace_id,
        session_id=payload.session_id,
        transcript=turns, start_snapshot=authoritative,
        model_id=payload.model_id,
        user_peer_id=payload.user_peer_id,
        temporal_session_id=payload.temporal_session_id,
        checkpoints=checkpoints, receipts=receipts,
        mode="apply" if want_apply else "shadow",
    )
    effective_mode = "shadow"
    apply_note = ""
    if want_apply and not aggregate.get("error"):
        if apply_enabled():
            effective_mode = "apply"
        else:
            apply_note = "apply_requested_but_disabled"
    run = ConsolidationRun(
        honcho_workspace_id=payload.workspace_id,
        honcho_session_id=payload.session_id,
        temporal_session_id=payload.temporal_session_id or "",
        mode=effective_mode,
        model=payload.model_id or semantic_judge.judge_model_id(),
        summary=" | ".join(aggregate.get("summaries", []))[:500],
        accepted_count=len(aggregate.get("accepted", [])),
        rejected_count=len(aggregate.get("rejected", [])),
        applied_count=len(aggregate.get("applied", [])),
        deferred_count=len(aggregate.get("deferred", [])),
        error=aggregate.get("error", ""),
        prompt_chars=aggregate.get("prompt_chars", 0),
        latency_s=aggregate.get("latency_s", 0.0),
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
        "summary": " | ".join(aggregate.get("summaries", []))[:500],
        "error": aggregate.get("error", ""),
        "prompt_chars": aggregate.get("prompt_chars", 0),
        "latency_s": aggregate.get("latency_s", 0.0),
        "apply_note": apply_note,
        "snapshot_source": snapshot_source,
        "coverage": aggregate.get("coverage", {}),
        "segments": aggregate.get("segment_reports", []),
        "accepted": aggregate.get("accepted", []),
        "rejected": aggregate.get("rejected", []),
        "discards": aggregate.get("discards", []),
        "provisional_marks": aggregate.get("provisional_marks", []),
        "would_apply": aggregate.get("would_apply", []),
        "applied": aggregate.get("applied", []),
        "deferred": aggregate.get("deferred", []),
    }
