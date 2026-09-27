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


async def _apply_accept(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    message_id: str,
    peer_id: str,
    text: str,
    now: datetime,
    kind: str,
    target: Any,
    matter: str,
    adjudication: Any,
    judgement: Any,
    recruit: Optional[Dict[str, Any]],
    result: Dict[str, int],
) -> None:
    """Shared deterministic apply for direct and recruited accepts.

    The model never writes: this commits the state change, the relation
    promotion, and the audit trace. Recruited accepts additionally record
    the query, hit provenance, and whether the grounding span came from the
    current turn or recruited history. Mutates result counts in place;
    never raises (fail-open via error trace).
    """
    from src.services import semantic_judge
    from src.services.semantic_promotion import promote_transition

    detail: Dict[str, Any] = {
        "kind": kind, "target_id": str(target.id),
        "verdict": adjudication.verdict,
        "confidence": judgement.confidence,
        "evidence_span": judgement.evidence_span,
        "rationale": judgement.rationale,
    }
    source_key = f"semantic_proposal:{message_id}#target:{target.id}"
    evidence_note = f"semantic_proposal:{message_id}#confidence:{judgement.confidence:.2f}"
    evidence_refs = [f"honcho_message:{message_id}#target:{target.id}"]
    trace_status = "accepted"
    item_key = f"{kind}:{target.id}:{message_id}"
    if recruit is not None:
        hits = recruit.get("hits") or []
        provenances = [h.provenance for h in hits]
        source_key += "#recruited"
        item_key += ":recruited"
        evidence_note = (
            f"semantic_proposal:{message_id}"
            f"#recruited:{(provenances[0] if provenances else '?')}"
            f"#confidence:{judgement.confidence:.2f}")
        evidence_refs = evidence_refs + [f"honcho_ref:{p}" for p in provenances]
        detail.update({
            "recruited_query": str(recruit.get("query") or "")[:500],
            "recruited_hits": provenances,
            "span_in_current": bool(recruit.get("span_in_current")),
        })
        trace_status = "accepted_via_recruitment"
    try:
        if kind == "resolves" and isinstance(target, OpenLoop):
            target.status = OpenLoopStatus.RESOLVED
            target.resolution_evidence = evidence_note
            target.updated_at = _naive_utc(now)
            db.add(target)
            await db.commit()
            result["closed"] += 1
        promoted = await promote_transition(
            db, workspace_id=workspace_id, rel_type=kind,
            from_text=text, to_text=matter,
            source_key=source_key,
            evidence_refs=evidence_refs,
            subjects_from=[peer_id] if peer_id else [],
            subjects_to=([target.owner_peer_id] if getattr(
                target, "owner_peer_id", None) else []),
            formation="inferred", confidence=judgement.confidence,
            effective_at=_naive_utc(now))
        if promoted is not None:
            result["promoted"] += 1
        result["accepted"] += 1
        await _mark(db, workspace_id=workspace_id, session_id=session_id,
                    message_id=message_id,
                    item_key=item_key,
                    status=trace_status,
                    detail=detail, model=semantic_judge.judge_model_id())
    except Exception as err:
        logger.warning("semantic reconciliation apply failed: %s", err)
        try:
            await db.rollback()
        except Exception:
            pass
        await _mark(db, workspace_id=workspace_id, session_id=session_id,
                    message_id=message_id,
                    item_key=item_key,
                    status="error",
                    detail={**detail, "error": str(err)[:200]},
                    model=semantic_judge.judge_model_id())


async def _recruit_after_rejection(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    message_id: str,
    peer_id: str,
    text: str,
    now: datetime,
    rejected: List[Dict[str, Any]],
    adapter: Any,
    history_provider: Any,
    result: Dict[str, int],
) -> None:
    """Adjacent self-resolution bridge (Canon 12-13).

    Fires only when plausible pairs existed, the judge ran, and nothing was
    accepted on current evidence alone. One bounded retrieval, re-judge of at
    most MAX_REJUDGE_PAIRS, mutation only on a single grounded winner;
    otherwise hold with an audit trace. Never raises; never clarifies.
    """
    from src.services import evidence_recruitment, semantic_judge

    try:
        outcome = await evidence_recruitment.recruit_and_rejudge(
            workspace_id=workspace_id, session_id=session_id, peer_id=peer_id,
            message_id=message_id, text=text, rejected=rejected,
            adapter=adapter, history_provider=history_provider)
    except Exception as err:
        logger.warning("evidence recruitment failed (fail-open): %s", err)
        return
    if not outcome.get("recruited"):
        return
    result["recruited"] = int(outcome.get("recruited") or 0)
    result["recruit_judged"] = int(outcome.get("recruit_judged") or 0)
    result["recruit_accepted"] = int(outcome.get("recruit_accepted") or 0)
    winner = outcome.get("winner")
    if winner is None:
        for pair in rejected[:evidence_recruitment.MAX_REJUDGE_PAIRS]:
            hold_key = f"{pair['kind']}:{pair['target'].id}:{message_id}:recruited"
            if await _marked(db, workspace_id, message_id, hold_key):
                continue
            await _mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, item_key=hold_key,
                        status="recruited_hold",
                        detail={"kind": pair["kind"],
                                "target_id": str(pair["target"].id),
                                "reasons": outcome.get("holds") or [],
                                "recruited": outcome.get("recruited")},
                        model=semantic_judge.judge_model_id())
        return
    pair = winner["pair"]
    await _apply_accept(
        db, workspace_id=workspace_id, session_id=session_id,
        message_id=message_id, peer_id=peer_id, text=text, now=now,
        kind=pair["kind"], target=pair["target"], matter=pair["matter"],
        adjudication=winner["judgement"],
        judgement=winner["judgement"], recruit=winner, result=result)


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
    history_provider: Any = None,
) -> Dict[str, int]:
    """Judge open matters against this turn's evidence. Returns counts.

    history_provider, when given, enables one bounded recruitment round if
    plausible pairs were judged but none accepted on current evidence alone
    (Canon 12-13: investigate privately before holding). None preserves
    today's behaviour exactly. Never mints clarifications.
    """
    from src.services import semantic_judge

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
    if closed and loops:
        # Same consumed-evidence guard as try_resolve_open_loop: structural
        # release already closed a sibling on this turn's text. Judging the
        # leftovers alone would crown a vocabulary neighbour sole winner by
        # elimination (payment closed -> form "wins"). Only loop closures
        # are suppressed; expectation refinement is a different lane.
        try:
            wanted = []
            for i in closed:
                try:
                    wanted.append(i if isinstance(i, UUID) else UUID(str(i)))
                except (TypeError, ValueError):
                    continue
            if not wanted:
                raise ValueError("no parseable closed ids")
            closed_rows = (await db.execute(select(OpenLoop).where(
                OpenLoop.honcho_workspace_id == workspace_id,
                OpenLoop.id.in_(wanted),
            ))).scalars().all()
            text_tokens = LifecycleService._significant_tokens(text)
            for crow in closed_rows:
                if text_tokens & LifecycleService._significant_tokens(
                        f"{crow.title or ''} {crow.summary or ''}"):
                    loops = []
                    break
        except Exception as err:
            logger.warning("closed-loop guard failed (fail-open): %s", err)
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

    rejected: List[Dict[str, Any]] = []
    resolves_accepts: List[Any] = []
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
            rejected.append(pair)
            continue
        if kind == "resolves":
            # Track D: closure needs a single grounded winner. Shared words
            # ("school trip payment" vs "school trip permission form") can
            # convince the judge twice; applying both would close a distinct
            # matter on vocabulary overlap. Collect first, apply below.
            resolves_accepts.append((pair, adjudication, judgement,
                                     item_key, base_detail))
            continue
        await _apply_accept(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, peer_id=peer_id, text=text, now=now,
            kind=kind, target=target, matter=pair["matter"],
            adjudication=adjudication, judgement=judgement,
            recruit=None, result=result)
    if len(resolves_accepts) == 1:
        pair, adjudication, judgement, item_key, base_detail = resolves_accepts[0]
        await _apply_accept(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, peer_id=peer_id, text=text, now=now,
            kind="resolves", target=pair["target"], matter=pair["matter"],
            adjudication=adjudication, judgement=judgement,
            recruit=None, result=result)
    elif len(resolves_accepts) > 1:
        # Ambiguous closure is worse than a missed one: hold everything and
        # leave an audit trace per matter. Never clarifies.
        for pair, adjudication, judgement, item_key, base_detail in resolves_accepts:
            await _mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, item_key=item_key,
                        status="ambiguous_hold",
                        detail={**base_detail,
                                "rationale": adjudication.rationale,
                                "evidence_span": adjudication.evidence_span,
                                "competitors": len(resolves_accepts)},
                        model=semantic_judge.judge_model_id())
    if result["accepted"] == 0 and rejected and history_provider is not None:
        await _recruit_after_rejection(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, peer_id=peer_id, text=text, now=now,
            rejected=rejected, adapter=adapter,
            history_provider=history_provider, result=result)
    return result


async def rescue_zero_yield_turn(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    message_id: str,
    peer_id: str,
    now: datetime,
    candidates: List[Any],
    had_durable_yield: bool,
    adapter: Any = ...,
) -> Dict[str, int]:
    """End-of-ingest factual rescue; see _rescue_factual_claim. Called with
    the turn's candidates once yield is known. Bounded: top-1 candidate,
    one judge call, only on zero-yield turns."""
    from src.services import semantic_judge
    if adapter is ...:
        adapter = semantic_judge._adapter()
    if adapter is None:
        return {"rescued": 0, "reason": "no_adapter"}
    rescued = await _rescue_factual_claim(
        db, workspace_id=workspace_id, session_id=session_id,
        message_id=message_id, peer_id=peer_id, now=now,
        candidates=candidates or [], had_durable_yield=had_durable_yield,
        adapter=adapter)
    return {"rescued": rescued}


async def _rescue_factual_claim(
    db: AsyncSession, *, workspace_id: str, session_id: str, message_id: str,
    peer_id: str, now: datetime, candidates: List[Any],
    had_durable_yield: bool, adapter: Any,
) -> int:
    """Bounded rescue for zero-yield turns: biographical disclosures the
    extractor left as semantic_only would otherwise vanish despite high
    confidence + verbatim evidence. At most ONE judge call, only when the
    turn produced no durable rows. Accepted verdicts persist via the
    existing idempotent fact writer — the model never writes directly."""
    from src.services import semantic_judge
    from src.services.persistence import save_fact_idempotent

    if had_durable_yield:
        return 0
    # Stranded disclosures: semantic_only rows, plus recurring_intention rows
    # (past-habitual "every day for three months" is biography, not a future
    # recurrence — and when nothing durable was created, nothing was lost by
    # asking). Judged over RAW evidence: factuality is a property of what was
    # said, not of the extractor's gratitude framing.
    stranded = [c for c in candidates
                if getattr(c, "operational_kind", "") in (
                    "semantic_only", "recurring_intention")
                and float(getattr(c, "confidence", 0) or 0) >= 0.8
                and ((getattr(c, "raw_evidence", "") or "").strip()
                     or (getattr(c, "observation", "") or "").strip())]
    if not stranded:
        return 0
    stranded.sort(key=lambda c: float(getattr(c, "confidence", 0) or 0),
                  reverse=True)
    rescued = 0
    for cand in stranded[:2]:
        text = (getattr(cand, "raw_evidence", "") or "").strip() \
            or (getattr(cand, "observation", "") or "").strip()
        item_key = f"factual:{getattr(cand, 'candidate_key', '?')}:{message_id}"
        if await _marked(db, workspace_id, message_id, item_key):
            continue
        adjudication = await semantic_judge.adjudicate(
            kind="factual_claim", earlier="candidate biographical disclosure",
            later=text, adapter=adapter)
        if not adjudication.accepted or not adjudication.evidence_span.strip() \
                or adjudication.evidence_span.strip() not in text:
            await _mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, item_key=item_key, status="rejected",
                        detail={"kind": "factual_claim",
                                "verdict": adjudication.verdict,
                                "confidence": adjudication.confidence,
                                "note": adjudication.note},
                        model=semantic_judge.judge_model_id())
            continue
        try:
            row, created = await save_fact_idempotent(db, {
                "honcho_workspace_id": workspace_id,
                "honcho_session_id": session_id,
                "honcho_message_id": message_id,
                "owner_peer_id": peer_id,
                "candidate_key": f"{getattr(cand, 'candidate_key', 'rescued')}@semantic-rescue-v1",
                "category": getattr(cand, "domain_tag", None) or "general",
                "title": text[:280],
                "evidence_verbatim": text[:2000],
                "formation": "inferred",
                "confidence": adjudication.confidence,
            })
        except Exception as err:
            logger.warning("factual rescue persist failed: %s", err)
            continue
        await _mark(db, workspace_id=workspace_id, session_id=session_id,
                    message_id=message_id, item_key=item_key, status="accepted",
                    detail={"kind": "factual_claim", "fact_id": str(row.id),
                            "created": created,
                            "confidence": adjudication.confidence,
                            "evidence_span": adjudication.evidence_span},
                    model=semantic_judge.judge_model_id())
        if created:
            rescued += 1
    return rescued
