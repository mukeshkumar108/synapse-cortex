"""Event-driven semantic reconciliation: later evidence vs open state.

Runs post-ingest (even on empty turns). Deterministic code selects a BOUNDED
set of candidate pairs by token overlap; the semantic judge answers meaning;
deterministic promotion/control applies the outcome. The model never writes.

Per-turn bounds: text floor, adapter required, overlap prefilter, max 3 judge
calls, per-(kind,target,message) trace markers so replays never re-judge.
Fail-open: any failure returns counts, never breaks ingest.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.expectation import Expectation, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.services.lifecycle_service import LifecycleService

logger = logging.getLogger(__name__)

MIN_TEXT_CHARS = 40
MAX_OPEN_TARGETS = 4
MAX_JUDGE_CALLS_PER_TURN = 3


def _overlap(a: str, b: str) -> int:
    ta = LifecycleService._significant_tokens(a or "")
    tb = LifecycleService._significant_tokens(b or "")
    return len(ta & tb)


async def _marked(db: AsyncSession, workspace_id: str, message_id: str,
                 item_key: str) -> bool:
    from src.models.operational_state import ExtractionTrace
    row = (await db.execute(select(ExtractionTrace).where(
        ExtractionTrace.honcho_workspace_id == workspace_id,
        ExtractionTrace.honcho_message_id == message_id,
        ExtractionTrace.stage == "semantic_proposal",
        ExtractionTrace.item_key == item_key,
    ))).scalar_one_or_none()
    return row is not None


async def _mark(db: AsyncSession, *, workspace_id: str, session_id: str,
               message_id: str, item_key: str, status: str,
               detail: Dict[str, Any], model: str) -> None:
    from src.models.operational_state import ExtractionTrace
    try:
        db.add(ExtractionTrace(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            stage="semantic_proposal",
            item_key=item_key,
            status=status,
            model=model,
            detail_json=json.dumps(detail, default=str)[:4000],
        ))
        await db.commit()
    except Exception as err:
        logger.warning("semantic proposal trace failed: %s", err)
        try:
            await db.rollback()
        except Exception:
            pass


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


async def reconcile_turn(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    message_id: str,
    text: str,
    peer_id: str,
    now: datetime,
    closed_loop_ids: Optional[List[Any]] = None,
    adapter: Any = ...,
) -> Dict[str, int]:
    """Judge open matters against this turn's evidence. Returns counts."""
    from src.services import semantic_judge
    from src.services.semantic_promotion import promote_transition

    result = {"pairs": 0, "judged": 0, "accepted": 0, "promoted": 0, "closed": 0}
    text = (text or "").strip()
    if len(text) < MIN_TEXT_CHARS:
        return result
    if adapter is ...:
        adapter = semantic_judge._adapter()
    if adapter is None:
        return result
    closed = {str(i) for i in (closed_loop_ids or [])}

    loops = (await db.execute(select(OpenLoop).where(
        OpenLoop.honcho_workspace_id == workspace_id,
        OpenLoop.honcho_session_id == session_id,
        OpenLoop.status == OpenLoopStatus.OPEN,
        OpenLoop.honcho_message_id != message_id,
    ).order_by(OpenLoop.created_at.desc()).limit(MAX_OPEN_TARGETS))).scalars().all()
    loops = [lp for lp in loops if str(lp.id) not in closed]
    exps = (await db.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.honcho_session_id == session_id,
        Expectation.outcome_state == OutcomeState.UNKNOWN,
        Expectation.superseded_by_id.is_(None),
    ).order_by(Expectation.created_at.desc()).limit(MAX_OPEN_TARGETS))).scalars().all()

    pairs: List[Dict[str, Any]] = []
    for lp in loops:
        matter = f"{lp.title or ''} {lp.summary or ''}".strip() or "open loop"
        if _overlap(matter, text) >= 1:
            pairs.append({"kind": "resolves", "target": lp, "matter": matter})
    for exp in exps:
        matter = f"{exp.title or ''} {exp.summary or ''}".strip() or "expectation"
        if _overlap(matter, text) >= 2:
            pairs.append({"kind": "partially_fulfils", "target": exp, "matter": matter})
    # Loops first (closure beats refinement), then expectations.
    pairs.sort(key=lambda p: 0 if p["kind"] == "resolves" else 1)
    result["pairs"] = len(pairs)

    for pair in pairs[:MAX_JUDGE_CALLS_PER_TURN]:
        kind = pair["kind"]
        target = pair["target"]
        item_key = f"{kind}:{target.id}:{message_id}"
        if await _marked(db, workspace_id, message_id, item_key):
            continue
        adjudication = await semantic_judge.adjudicate(
            kind=kind, earlier=pair["matter"], later=text, adapter=adapter)
        result["judged"] += 1
        base_detail = {"kind": kind, "target_id": str(target.id),
                       "verdict": adjudication.verdict,
                       "confidence": adjudication.confidence,
                       "note": adjudication.note}
        judgement = None
        if adjudication.accepted and adjudication.evidence_span.strip() \
                and adjudication.evidence_span.strip() in text:
            judgement = adjudication
        if judgement is None:
            await _mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, item_key=item_key, status="rejected",
                        detail={**base_detail,
                                "rationale": adjudication.rationale,
                                "evidence_span": adjudication.evidence_span},
                        model=semantic_judge.judge_model_id())
            continue
        result["accepted"] += 1
        detail = {"kind": kind, "target_id": str(target.id),
                  "verdict": adjudication.verdict,
                  "confidence": judgement.confidence,
                  "evidence_span": judgement.evidence_span,
                  "rationale": judgement.rationale}
        try:
            if kind == "resolves" and isinstance(target, OpenLoop):
                target.status = OpenLoopStatus.RESOLVED
                target.resolution_evidence = (
                    f"semantic_proposal:{message_id}#confidence:{judgement.confidence:.2f}")
                target.updated_at = _naive_utc(now)
                db.add(target)
                await db.commit()
                result["closed"] += 1
            promoted = await promote_transition(
                db, workspace_id=workspace_id, rel_type=kind,
                from_text=text, to_text=pair["matter"],
                source_key=f"semantic_proposal:{message_id}#target:{target.id}",
                evidence_refs=[f"honcho_message:{message_id}#target:{target.id}"],
                subjects_from=[peer_id] if peer_id else [],
                subjects_to=([target.owner_peer_id] if getattr(
                    target, "owner_peer_id", None) else []),
                formation="inferred", confidence=judgement.confidence,
                effective_at=_naive_utc(now))
            if promoted is not None:
                result["promoted"] += 1
            await _mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, item_key=item_key, status="accepted",
                        detail=detail, model=semantic_judge.judge_model_id())
        except Exception as err:
            logger.warning("semantic reconciliation apply failed: %s", err)
            try:
                await db.rollback()
            except Exception:
                pass
            await _mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, item_key=item_key, status="error",
                        detail={**detail, "error": str(err)[:200]},
                        model=semantic_judge.judge_model_id())
    return result
