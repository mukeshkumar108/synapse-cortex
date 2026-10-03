"""Session lifecycle endpoints (Cortex side).

Identity contract (see session_reconstruction docstring):
- `session_id` is the STABLE durable lane (chat id). Every row this
  boundary reads or writes scopes to it, so reconstructed state lands in
  the exact namespace attention/reconciliation read next time.
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

import json
import logging
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.models.consolidation import ConsolidationRun
from src.services.session_apply import apply_enabled
from src.services.session_consolidation import (
    SessionTurn,
    StartSnapshot,
)
from src.services.session_reconstruction import consolidate_long_session

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


class RetryRequest(BaseModel):
    """Re-run ONLY the failed windows of a prior partial/failed run.

    Transcript must contain exactly the same turn ids as the original call
    (else 400 transcript_changed — boundaries must not drift under a
    retry). Converges via stable idempotency keys + liveness guards; a new
    run row chains to the prior via prior_run_id. Merged accepted ops from
    the prior run are returned alongside the new ones.
    """

    workspace_id: str
    session_id: str
    run_id: str
    transcript: List[TranscriptTurn] = Field(default_factory=list)
    temporal_session_id: Optional[str] = None
    user_peer_id: str = Field(default="user")
    model_id: Optional[str] = None
    checkpoints: List[EvidenceItem] = Field(default_factory=list)
    receipts: List[EvidenceItem] = Field(default_factory=list)


async def _write_run(db: AsyncSession, *, workspace_id: str, session_id: str,
                     temporal: str, mode: str, model: str,
                     aggregate: Dict[str, Any], user_peer_id: str,
                     prior_run_id: Optional[UUID] = None) -> ConsolidationRun:
    coverage = aggregate.get("coverage", {}) or {}
    semantic = coverage.get("semantic", {}) or {}
    failed = semantic.get("windows_failed", []) or []
    ok = int(semantic.get("windows_ok", 0) or 0)
    skipped = int(semantic.get("windows_skipped_covered", 0) or 0)
    if coverage.get("complete"):
        completion = "complete"
    elif ok > 0 or skipped > 0:
        completion = "partial"
    else:
        completion = "failed"
    segment_map = []
    for rep in aggregate.get("segment_reports", []) or []:
        segment_map.append({
            "segment": rep.get("segment"),
            "message_ids": rep.get("message_ids", []),
            "status": rep.get("status", "failed" if rep.get("error") else "ok"),
            "error": rep.get("error", ""),
        })
    run = ConsolidationRun(
        honcho_workspace_id=workspace_id,
        honcho_session_id=session_id,
        temporal_session_id=temporal or "",
        mode=mode,
        model=model,
        summary=" | ".join(aggregate.get("summaries", []))[:500],
        accepted_count=len(aggregate.get("accepted", [])),
        rejected_count=len(aggregate.get("rejected", [])),
        applied_count=len(aggregate.get("applied", [])),
        deferred_count=len(aggregate.get("deferred", [])),
        error=aggregate.get("error", ""),
        prompt_chars=aggregate.get("prompt_chars", 0),
        latency_s=aggregate.get("latency_s", 0.0),
        owner_peer_id=user_peer_id,
        completion=completion,
        segment_map_json=json.dumps(segment_map, default=str),
        accepted_json=json.dumps(aggregate.get("accepted", []), default=str),
        prior_run_id=prior_run_id,
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
    return run


async def _record_episode(db: AsyncSession, *, run: ConsolidationRun, aggregate: Dict[str, Any],
                          payload: Any, effective_mode: str):
    """Applied runs leave a provenance-linked SessionEpisode that REFERENCES
    the canonical writes (never a second store). Fail-open: the run ledger and
    canonical writes already committed."""
    if effective_mode != "apply":
        return None
    try:
        from datetime import datetime, timezone
        from src.services.session_episode_service import record_episode
        return await record_episode(
            db, workspace_id=payload.workspace_id, session_id=payload.session_id,
            temporal_session_id=payload.temporal_session_id or "", run=run, aggregate=aggregate,
            user_peer_id=payload.user_peer_id, now=datetime.now(timezone.utc).replace(tzinfo=None))
    except Exception as err:
        logger.warning("session episode failed (fail-open): %s", err)
        try:
            await db.rollback()
        except Exception:
            pass
        return None


def _response(run: ConsolidationRun, aggregate: Dict[str, Any],
              *, snapshot_source: str = "authoritative",
              apply_note: str = "", retried_from: str = "",
              merged_accepted: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    coverage = aggregate.get("coverage", {}) or {}
    semantic = coverage.get("semantic", {}) or {}
    return {
        "status": run.mode,
        "run_id": str(run.id),
        "completion": run.completion,
        "summary": " | ".join(aggregate.get("summaries", []))[:500],
        "error": aggregate.get("error", ""),
        "prompt_chars": aggregate.get("prompt_chars", 0),
        "latency_s": aggregate.get("latency_s", 0.0),
        "apply_note": apply_note,
        "snapshot_source": snapshot_source,
        "coverage": coverage,
        "failed_segments": semantic.get("windows_failed", []),
        "segments": aggregate.get("segment_reports", []),
        "accepted": merged_accepted if merged_accepted is not None
        else aggregate.get("accepted", []),
        "rejected": aggregate.get("rejected", []),
        "discards": aggregate.get("discards", []),
        "provisional_marks": aggregate.get("provisional_marks", []),
        "would_apply": aggregate.get("would_apply", []),
        "applied": aggregate.get("applied", []),
        "deferred": aggregate.get("deferred", []),
        "retried_from": retried_from,
    }


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
                people=merged, claims=list(authoritative.claims))
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
    # Mode records what the orchestrator was authorized to do, not whether
    # every window succeeded: per-segment results apply independently, and
    # partial completion is reported via completion + failed_segments, never
    # by relabeling applied state as shadow.
    if want_apply:
        if apply_enabled(payload.user_peer_id):
            effective_mode = "apply"
        else:
            apply_note = "apply_requested_but_disabled"
    run = await _write_run(
        db, workspace_id=payload.workspace_id,
        session_id=payload.session_id,
        temporal=payload.temporal_session_id or "",
        mode=effective_mode,
        model=payload.model_id or semantic_judge.judge_model_id(),
        aggregate=aggregate, user_peer_id=payload.user_peer_id)
    episode = await _record_episode(db, run=run, aggregate=aggregate, payload=payload,
                                    effective_mode=effective_mode)
    response = _response(run, aggregate, snapshot_source=snapshot_source,
                         apply_note=apply_note)
    if episode is not None:
        response["episode_id"] = str(episode.id)
    return response


@router.post("/consolidate/retry", status_code=status.HTTP_200_OK)
async def retry_consolidate(
    payload: RetryRequest,
    db: AsyncSession = Depends(get_async_session),
) -> Dict[str, Any]:
    """Retry only the failed windows of a partial/failed run.

    Loads the prior run's segment map, verifies the transcript is
    unchanged (same turn ids — boundaries must not drift under retry),
    re-runs exactly the failed windows, and chains a new run row. Already
    covered windows cost no model calls; convergence without duplicates
    comes from stable idempotency keys + liveness guards. A retry of a
    complete run returns already_complete with the prior accepted ops.
    """
    from src.services import semantic_judge
    from src.services.session_reconstruction import retry_long_session, RetryError

    turns = [SessionTurn(message_id=t.message_id, speaker=t.speaker,
                         text=t.text) for t in payload.transcript]
    checkpoints = [{"label": c.label, "text": c.text} for c in payload.checkpoints]
    receipts = [{"kind": c.kind, "text": c.text} for c in payload.receipts]
    try:
        outcome = await retry_long_session(
            db, workspace_id=payload.workspace_id,
            session_id=payload.session_id, run_id=payload.run_id,
            transcript=turns, user_peer_id=payload.user_peer_id,
            model_id=payload.model_id,
            temporal_session_id=payload.temporal_session_id,
            checkpoints=checkpoints, receipts=receipts)
    except RetryError as err:
        if err.code == "already_complete":
            prior = err.payload.get("prior", {})
            return {
                "status": prior.get("mode", "shadow"),
                "run_id": prior.get("id", ""),
                "completion": "complete", "retried_from": "",
                "already_complete": True,
                "accepted": err.payload.get("accepted", []),
                "failed_segments": [],
                "coverage": {"complete": True},
                "applied": [], "deferred": [], "error": "",
            }
        status_map = {"bad_run_id": 400, "run_not_found": 404,
                      "run_scope_mismatch": 400, "transcript_changed": 400,
                      "nothing_retryable": 400}
        raise HTTPException(status_code=status_map.get(err.code, 400),
                            detail=err.code)
    aggregate = outcome["aggregate"]
    merged = outcome["merged"]
    episode_id = ""
    if outcome["effective_mode"] == "apply":
        try:
            run_row = await db.get(ConsolidationRun, UUID(str(outcome["run_id"])))
        except ValueError:
            run_row = None
        if run_row is not None:
            episode = await _record_episode(db, run=run_row, aggregate=aggregate,
                                            payload=payload, effective_mode="apply")
            episode_id = str(episode.id) if episode is not None else ""
    return {
        "episode_id": episode_id,
        "status": outcome["effective_mode"],
        "run_id": outcome["run_id"],
        "completion": outcome["completion"],
        "summary": " | ".join(aggregate.get("summaries", []))[:500],
        "error": aggregate.get("error", ""),
        "prompt_chars": aggregate.get("prompt_chars", 0),
        "latency_s": aggregate.get("latency_s", 0.0),
        "apply_note": "",
        "snapshot_source": "authoritative",
        "coverage": aggregate.get("coverage", {}),
        "failed_segments": (aggregate.get("coverage", {}) or {}).get(
            "semantic", {}).get("windows_failed", []),
        "segments": aggregate.get("segment_reports", []),
        "accepted": merged,
        "rejected": aggregate.get("rejected", []),
        "discards": aggregate.get("discards", []),
        "provisional_marks": aggregate.get("provisional_marks", []),
        "would_apply": aggregate.get("would_apply", []),
        "applied": aggregate.get("applied", []),
        "deferred": aggregate.get("deferred", []),
        "retried_from": outcome["prior"]["id"],
    }
