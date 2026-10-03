"""Bounded apply for V2 session reconstruction (feature-flagged).

Tier policy — what becomes durable state vs what stays visible-but-inert:

- AUTO (additive, reversible, provenance-linked): new_matter creation
  (through the EXISTING creation guards, never around them), same_as
  audit relations, attend/uncertainty attention rows, affirm/incidental
  no-ops. New uncertainty-kind matters need higher confidence, else they
  degrade to attention rather than rows.
- GUARDED (mutating, single-target, high-confidence only): resolve,
  partial, expectation revision — target must be live (OPEN/PENDING) in
  this workspace right now, confidence >= threshold, else deferred.
- DEFER (always shadow): suppressions (user-visible muting needs stronger
  warrant than one model call), discard/redundant marks, provisional
  supersede/redundant verdicts, anything below thresholds or ambiguous.

Idempotency: creation candidate_keys are stable hashes of
(workspace, session, op, target/title) — reruns hit unique constraints
and no-op. Mutations re-check liveness, so a second run defers as
already-applied. Nothing here invents consensus machinery: thresholds
are policy, documented, and every decision lands in the run ledger +
per-row evidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

logger = logging.getLogger(__name__)

APPLY_ENABLED_ENV = "SESSION_CONSOLIDATION_APPLY"

# Policy thresholds (documented, not tuned per scenario):
MUTATE_CONFIDENCE = 0.75   # resolve / partial / revise need this + liveness
CREATE_CONFIDENCE = 0.6    # additive creation at validation floor...
UNCERTAIN_CREATE_CONFIDENCE = 0.75  # ...except uncertainty-kind, which degrades
ATTENTION_CAP_PER_RUN = 5

EXTRACTOR_VERSION = "session-consolidation-v1"


APPLY_OWNER_PREFIXES_ENV = "SESSION_CONSOLIDATION_APPLY_OWNER_PREFIXES"


def apply_enabled(owner: Optional[str] = None) -> bool:
    """Global switch (SESSION_CONSOLIDATION_APPLY=1), or scoped enablement: apply for owners whose peer id starts with one of the
    comma-separated prefixes in SESSION_CONSOLIDATION_APPLY_OWNER_PREFIXES (for example `world:` = RPD2's per-chat worlds), leaving
    every other owner (a real person's world) untouched."""
    import os
    if os.getenv(APPLY_ENABLED_ENV, "0") == "1":
        return True
    prefixes = [p.strip() for p in os.getenv(APPLY_OWNER_PREFIXES_ENV, "").split(",") if p.strip()]
    return bool(owner and prefixes and any(str(owner).startswith(p) for p in prefixes))


def _stable_key(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


async def _fetch(db: Any, model: Any, workspace_id: str, mid: str) -> Any:
    from sqlmodel import select
    try:
        uuid = UUID(str(mid))
    except (TypeError, ValueError):
        return None
    try:
        return (await db.execute(select(model).where(
            model.id == uuid,
            model.honcho_workspace_id == workspace_id))).scalar_one_or_none()
    except Exception:
        return None


def _live_status(row: Any) -> bool:
    return str(getattr(row.status, "value", row.status or "")).upper() in ("OPEN", "PENDING")


async def apply_reconstruction(
    db: Any,
    *,
    workspace_id: str,
    session_id: str,
    result: Any,  # V2Result (accepted ops + discards + provisional_marks)
    user_peer_id: str = "user",
    now: Optional[datetime] = None,
    temporal_session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Apply the AUTO + GUARDED tiers; defer the rest. Returns
    {"applied": [...], "deferred": [...]}. Every applied mutation cites the
    session + message ids in row evidence; creations flow through existing
    creation guards. Never raises (per-op fail-open to deferred)."""
    from src.models.commitment_candidate import (
        CommitmentCandidate, CommitmentCandidateAuthority,
        CommitmentCandidateStatus,
    )
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.schemas.candidate import ExtractionCandidate
    from src.services.commitment_candidate_service import CommitmentCandidateService
    from src.services.lifecycle_service import (
        LifecycleService,
        record_ambiguity_attention,
    )
    from src.services.semantic_promotion import promote_transition

    now = now or datetime.now(timezone.utc)
    # Lane vs temporal: rows scope to the stable lane `session_id`; the
    # temporal boundary id travels only as provenance on message ids.
    message_id = f"consolidation:{temporal_session_id or session_id}"
    applied: List[Dict[str, Any]] = []
    deferred: List[Dict[str, Any]] = []
    attentions_used = 0
    lifecycle = LifecycleService()
    commitments = CommitmentCandidateService()

    def _defer(op: str, reason: str, data: Any = None) -> None:
        deferred.append({"op": op, "reason": reason,
                         "data": data if isinstance(data, dict) else {}})

    for op in list(getattr(result, "accepted", []) or []):
        try:
            outcome = await _apply_op(
                db, op, workspace_id=workspace_id, session_id=session_id,
                message_id=message_id, user_peer_id=user_peer_id, now=now,
                lifecycle=lifecycle, commitments=commitments,
                attentions_used=[attentions_used],
            )
        except Exception as err:
            logger.warning("consolidation apply op %s failed (deferred): %s",
                           getattr(op, "op", "?"), err)
            _defer(getattr(op, "op", "?"), "apply_error")
            continue
        if isinstance(outcome, dict) and outcome.get("attentions_used") is not None:
            attentions_used = int(outcome["attentions_used"])
            outcome = {k: v for k, v in outcome.items() if k != "attentions_used"}
        if outcome is None:
            continue
        if outcome.get("applied"):
            applied.append({k: v for k, v in outcome.items() if k != "applied"})
        else:
            _defer(outcome.get("op", "?"), outcome.get("reason", "deferred"),
                   outcome.get("data"))
    # Destruction-adjacent proposals never auto-apply: record visibly.
    for d in list(getattr(result, "discards", []) or []):
        _defer("discard", "destructive_needs_review", d)
    for mark in list(getattr(result, "provisional_marks", []) or []):
        _defer("provisional_review", "provisional_needs_review", mark)
    return {"applied": applied, "deferred": deferred}


async def _apply_op(db: Any, op: Any, *, workspace_id: str, session_id: str,
                    message_id: str, user_peer_id: str, now: datetime,
                    lifecycle: Any, commitments: Any,
                    attentions_used: List[int]) -> Optional[Dict[str, Any]]:
    from src.models.commitment_candidate import (
        CommitmentCandidate, CommitmentCandidateAuthority,
        CommitmentCandidateStatus,
    )
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.schemas.candidate import ExtractionCandidate
    from src.services.lifecycle_service import record_ambiguity_attention
    from src.services.semantic_promotion import promote_transition

    kind = getattr(op, "op", "?")
    data = getattr(op, "data", {}) or {}
    conf = float(getattr(op, "confidence", 0) or 0)
    from src.services.consolidation_world import WORLD_OPS, apply_world_op
    if kind in WORLD_OPS:
        # claims / directed expectations / known-unknowns: the epistemic and
        # direction-carrying write paths (never a second store).
        return await apply_world_op(
            db, op, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, user_peer_id=user_peer_id, now=now,
            create_conf=CREATE_CONFIDENCE)
    ev = data.get("evidence") or {}
    mids = [str(m) for m in (ev.get("message_ids") or [])]
    spans = ev.get("spans") or []
    span_texts = [str(s.get("span") or "") for s in spans if isinstance(s, dict)]

    if kind in ("affirm_matter", "incidental"):
        return {"op": kind, "applied": True, "mutation": "none",
                "data": data}
    if kind == "new_matter":
        title = str(data.get("title") or "")[:280]
        matter_kind = str(data.get("matter_kind") or "watch")
        owner = str(data.get("owner") or "user")
        subjects = [str(s) for s in (data.get("subjects") or [])[:4] if str(s).strip()]
        if not title or conf < CREATE_CONFIDENCE:
            return {"op": kind, "reason": "below_create_threshold", "data": data}
        key = _stable_key(workspace_id, session_id, "new", matter_kind, title)
        evidence_text = " ".join(span_texts)[:2000] or title
        owner_peer = user_peer_id if owner in ("user", "unknown") else owner
        if matter_kind == "uncertainty" and conf < UNCERTAIN_CREATE_CONFIDENCE:
            return await _hold_attention(
                db, workspace_id=workspace_id, session_id=session_id,
                message_id=message_id,
                key=_stable_key(workspace_id, session_id, "degraded", title),
                content=(f"Uncertain matter held from session: {title}"),
                conf=conf, attentions_used=attentions_used,
                op_name="new_matter(degraded_to_attention)", data=data)
        if matter_kind == "obligation":
            cand = ExtractionCandidate(
                candidate_key=key, observation=title, raw_evidence=evidence_text,
                canonical_title=title, operational_kind="commitment_candidate",
                evidence_class="implicit_self_commitment", authority="ask",
                subject_refs=subjects, confidence=min(1.0, conf),
                formation="inferred", extractor_version=EXTRACTOR_VERSION)
            # ASK authority: a proposal, never an actionable violation source.
            row = await commitments.upsert_from_candidate(
                db, workspace_id=workspace_id, session_id=session_id,
                owner_peer_id=owner_peer, message_id=message_id,
                candidate=cand, now=now)
            if row is None:
                return {"op": kind, "reason": "creation_guard_refused", "data": data}
            if subjects:
                # Parity with the turn-ingest router, which links commitment
                # subjects after upsert (upsert itself never links).
                try:
                    from src.services import entity_service
                    await entity_service.link_candidate_subjects(
                        db, workspace_id=workspace_id, session_id=session_id,
                        object_type="commitment", object_id=row.id,
                        refs=subjects, frame=None, message_id=message_id)
                except Exception as err:
                    logger.warning("consolidation subject linking failed: %s", err)
            if str(data.get("status") or "") == "partial":
                await _record_partial(
                    db, workspace_id=workspace_id, evidence_text=evidence_text,
                    matter_title=row.title, message_id=message_id,
                    owner_peer=owner_peer, confidence=conf,
                    remainder=str(data.get("remainder") or ""))
            return {"op": kind, "applied": True, "row_id": str(row.id),
                    "row_kind": "commitment", "data": data}
        cand = ExtractionCandidate(
            candidate_key=key, observation=title, raw_evidence=evidence_text,
            canonical_title=title, open_loop_hint=title,
            operational_kind="open_loop", subject_refs=subjects,
            confidence=min(1.0, conf), formation="inferred",
            extractor_version=EXTRACTOR_VERSION)
        row = await lifecycle.create_open_loop_if_needed(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, owner_peer_id=owner_peer,
            candidate=cand, expectation_id=None, now=now)
        if row is None:
            return {"op": kind, "reason": "creation_guard_held", "data": data}
        if str(data.get("status") or "") == "partial":
            await _record_partial(
                db, workspace_id=workspace_id, evidence_text=evidence_text,
                matter_title=f"{row.title or ''} {row.summary or ''}".strip(),
                message_id=message_id, owner_peer=owner_peer,
                confidence=conf, remainder=str(data.get("remainder") or ""))
        return {"op": kind, "applied": True, "row_id": str(row.id),
                "row_kind": "open_loop", "data": data}
    if kind == "resolve_matter":
        if conf < MUTATE_CONFIDENCE:
            return {"op": kind, "reason": "below_mutate_threshold", "data": data}
        mid = str(data.get("matter_id") or "")
        row = await _fetch(db, OpenLoop, workspace_id, mid)
        row_kind = "open_loop"
        if row is None:
            row = await _fetch(db, CommitmentCandidate, workspace_id, mid)
            row_kind = "commitment"
        if row is None:
            return {"op": kind, "reason": "target_missing", "data": data}
        if not _live_status(row):
            return {"op": kind, "reason": "target_not_live", "data": data}
        note = (f"consolidation:{session_id}#via:{data.get('via', 'completed')}"
                f"#evidence:{','.join(mids)}")
        if row_kind == "open_loop":
            row.status = OpenLoopStatus.RESOLVED
        else:
            row.status = CommitmentCandidateStatus.FULFILLED
        row.resolution_evidence = note[:500]
        row.updated_at = _naive_utc(now)
        db.add(row)
        await db.commit()
        return {"op": kind, "applied": True, "row_id": str(row.id),
                "row_kind": row_kind, "data": data}
    if kind == "partial_fulfilment":
        if conf < MUTATE_CONFIDENCE:
            return {"op": kind, "reason": "below_mutate_threshold", "data": data}
        mid = str(data.get("matter_id") or "")
        row = await _fetch(db, OpenLoop, workspace_id, mid) \
            or await _fetch(db, CommitmentCandidate, workspace_id, mid)
        if row is None:
            return {"op": kind, "reason": "target_missing", "data": data}
        if not _live_status(row):
            return {"op": kind, "reason": "target_not_live", "data": data}
        evidence_text = " ".join(span_texts)[:2000] or "(session evidence)"
        await _record_partial(
            db, workspace_id=workspace_id, evidence_text=evidence_text,
            matter_title=f"{getattr(row, 'title', '') or ''}",
            message_id=message_id,
            owner_peer=getattr(row, "owner_peer_id", None),
            confidence=conf, remainder=str(data.get("remainder") or ""))
        return {"op": kind, "applied": True, "row_id": str(row.id),
                "data": data}
    if kind == "revise_expectation":
        if conf < MUTATE_CONFIDENCE:
            return {"op": kind, "reason": "below_mutate_threshold", "data": data}
        row = await _fetch(db, Expectation, workspace_id,
                           str(data.get("expectation_id") or ""))
        if row is None:
            return {"op": kind, "reason": "target_missing", "data": data}
        from src.models.expectation import OutcomeState
        outcome = str(data.get("outcome") or "unknown")
        # "violated" is the model-facing word; the stored outcome is NOT_FULFILLED.
        mapping = {"fulfilled": OutcomeState.FULFILLED,
                   "violated": OutcomeState.NOT_FULFILLED,
                   "unknown": OutcomeState.UNKNOWN}
        if outcome not in mapping:
            return {"op": kind, "reason": "bad_outcome", "data": data}
        row.outcome_state = mapping[outcome]
        row.updated_at = _naive_utc(now)
        row.resolution_evidence = (
            f"consolidation:{session_id}#evidence:{','.join(mids)}"
            f"#note:{str(data.get('note') or '')[:200]}")[:500]
        db.add(row)
        await db.commit()
        return {"op": kind, "applied": True, "row_id": str(row.id),
                "data": data}
    if kind == "same_as":
        from src.models.open_loop import OpenLoop as _OL
        from src.models.commitment_candidate import CommitmentCandidate as _CC
        a = await _fetch(db, _OL, workspace_id, str(data.get("matter_id_a") or "")) \
            or await _fetch(db, _CC, workspace_id, str(data.get("matter_id_a") or ""))
        b = await _fetch(db, _OL, workspace_id, str(data.get("matter_id_b") or "")) \
            or await _fetch(db, _CC, workspace_id, str(data.get("matter_id_b") or ""))
        if a is None or b is None:
            return {"op": kind, "reason": "target_missing", "data": data}
        if conf < CREATE_CONFIDENCE:
            return {"op": kind, "reason": "below_create_threshold", "data": data}
        # Relation only: rows are never merged or deleted by this path.
        await promote_transition(
            db, workspace_id=workspace_id, rel_type="same_as",
            from_text=getattr(a, "title", "") or "",
            to_text=getattr(b, "title", "") or "",
            source_key=f"consolidation_same_as:{session_id}#{a.id}#{b.id}",
            evidence_refs=[f"honcho_message:{m}" for m in mids] or [f"honcho_message:{message_id}"],
            formation="inferred", confidence=conf,
            effective_at=_naive_utc(now))
        return {"op": kind, "applied": True,
                "data": {"matter_id_a": str(a.id), "matter_id_b": str(b.id)}}
    if kind in ("attend", "uncertainty"):
        return await _hold_attention(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id,
            key=_stable_key(workspace_id, session_id, kind,
                            str(data.get("content") or "")[:120]),
            content=str(data.get("content") or "")[:500],
            conf=conf, attentions_used=attentions_used,
            op_name=kind, data=data)
    if kind == "suppress":
        # User-visible muting from one model call is not auto-applied in
        # this tranche: the proposal stays visible/auditable instead.
        return {"op": kind, "reason": "suppression_needs_review", "data": data}
    return {"op": kind, "reason": "unknown_op", "data": data}


async def _hold_attention(db: Any, *, workspace_id: str, session_id: str,
                          message_id: str, key: str, content: str, conf: float,
                          attentions_used: List[int], op_name: str,
                          data: Dict[str, Any]) -> Dict[str, Any]:
    from src.services.lifecycle_service import record_ambiguity_attention

    if not content.strip() or conf < 0.6 - 1e-9:
        return {"op": op_name, "reason": "below_create_threshold", "data": data}
    if attentions_used[0] >= ATTENTION_CAP_PER_RUN:
        return {"op": op_name, "reason": "attention_cap_reached", "data": data}
    try:
        row = await record_ambiguity_attention(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, candidate_key=key, content=content,
            owner_peer_id=None, confidence=max(0.0, min(1.0, conf)))
    except Exception as err:
        logger.warning("consolidation attention hold failed: %s", err)
        return {"op": op_name, "reason": "attention_write_failed", "data": data}
    attentions_used[0] += 1
    return {"op": op_name, "applied": True,
            "row_id": str(row.id) if row is not None else None,
            "attentions_used": attentions_used[0], "data": data}


async def _record_partial(db: Any, *, workspace_id: str, evidence_text: str,
                          matter_title: str, message_id: str,
                          owner_peer: Any, confidence: float,
                          remainder: str) -> None:
    from src.services.semantic_promotion import promote_transition

    # Partial evidence accumulates WITHOUT touching resolution_evidence, so a
    # remainder can still violate/resolve later (Track D invariant).
    try:
        await promote_transition(
            db, workspace_id=workspace_id, rel_type="partially_fulfils",
            from_text=evidence_text, to_text=matter_title or "(matter)",
            source_key=f"consolidation_partial:{message_id}",
            evidence_refs=[f"honcho_message:{message_id}"],
            subjects_to=[owner_peer] if owner_peer else [],
            formation="inferred", confidence=confidence)
    except Exception as err:
        logger.warning("consolidation partial promotion failed: %s", err)
