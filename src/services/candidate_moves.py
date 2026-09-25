"""Unified CandidateMove derivation — read-side over existing machinery.

Moves are recomputed per call from durable rows (attention, clarification,
commitment candidates, open loops, occurrences, graph reads). Nothing here is
a durable row: expiry/ineligibility can never resolve the underlying matter
because matter state is always re-read live.

System-attention-first: QUESTION/FOLLOW_UP candidates are checked against
internal resolution (semantic relations, existing settled state) before they
may become user-facing. Answered-internally matters emit no move.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

MOVE_KINDS = ("QUESTION", "FOLLOW_UP", "WATCH", "REMIND", "ACT", "PROPOSE",
              "DIGEST", "CALLBACK", "SHARE")


@dataclass(frozen=True)
class Move:
    move_id: str
    kind: str
    reason: str
    matter_kind: str
    matter_id: str
    source_refs: List[str] = field(default_factory=list)
    support: float = 0.5
    salience: float = 0.5
    eligibility: str = "eligible"
    window: Optional[str] = None
    lifecycle: str = "eligible"
    owner: str = "sophie"
    user_facing: bool = False
    telemetry: str = "MOVE_ELIGIBLE"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


async def _surface_hold(db: AsyncSession, *, workspace_id: str, session_id: str,
                        key: str, now: datetime) -> Optional[str]:
    """SurfaceRegistry cooldown check without recording. Returns hold reason
    or None when eligible."""
    from src.services.surface_lifecycle import SurfaceRegistry
    try:
        outcome = await SurfaceRegistry().eligibility(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=f"moves:{int(_naive_utc(now).timestamp())}",
            key=key, now=now)
    except Exception as err:
        logger.warning("surface eligibility check failed: %s", err)
        return None
    if outcome == "allowed":
        return None
    return f"held:{outcome}"


async def _internally_answered(db: AsyncSession, workspace_id: str,
                               matter_title: str) -> Optional[str]:
    """System attention: can existing settled state answer this matter?
    Returns the answering evidence or None. Deterministic, structural."""
    from src.models.expectation import Expectation, OutcomeState
    from src.models.semantic import SemanticClaim, SemanticRelation, normalize_claim_content
    from src.services.semantic_views import resolved_matters

    norm = normalize_claim_content(matter_title or "")
    if not norm:
        return None
    settled = (await db.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.outcome_state.in_([OutcomeState.FULFILLED, OutcomeState.CANCELLED]),
    ).limit(200))).scalars().all()
    for exp in settled:
        if normalize_claim_content(exp.title or "") == norm:
            return f"settled expectation {exp.id} ({exp.outcome_state})"
    claims = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == workspace_id))).scalars().all()
    rels = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == workspace_id))).scalars().all()
    by_content = {c.content: str(c.id) for c in claims}
    match = by_content.get(norm)
    if match is None:
        for content, cid in by_content.items():
            if norm and (norm in content or content in norm):
                match = cid
                break
    if match is not None:
        for r in rels:
            if (str(getattr(r, "status", "active")) == "active"
                    and str(getattr(r, "to_claim_id", "")) == match
                    and str(getattr(r, "rel_type", "")) in ("resolves", "fulfils")):
                return f"graph {r.rel_type} edge {r.id}"
    resolved = resolved_matters(list(claims), list(rels))
    if norm in [normalize_claim_content(t) for t in resolved]:
        return "graph-resolved matter"
    return None


async def derive_moves(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    owner_peer_id: Optional[str],
    now: datetime,
) -> Dict[str, Any]:
    """Derive the unified move set. Read-only apart from surface bookkeeping
    reads (no surfacing is recorded here)."""
    from src.models.attention_candidate import (
        AttentionCandidate, AttentionCandidateStatus,
    )
    from src.models.clarification import ClarificationCandidate, ClarificationStatus
    from src.models.commitment_candidate import (
        CommitmentCandidate, CommitmentCandidateStatus,
    )
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.models.operational_state import RecurringIntention, RecurringOccurrence
    from src.services import semantic_views as graph
    from src.models.semantic import SemanticClaim, SemanticRelation

    moves: List[Move] = []
    telemetry: Dict[str, int] = {}
    internally_resolved = 0

    def emit(move: Move) -> None:
        moves.append(move)
        telemetry[move.telemetry] = telemetry.get(move.telemetry, 0) + 1

    atts = (await db.execute(select(AttentionCandidate).where(
        AttentionCandidate.honcho_workspace_id == workspace_id,
        AttentionCandidate.honcho_session_id == session_id,
        AttentionCandidate.status.in_([AttentionCandidateStatus.ACTIVE,
                                       AttentionCandidateStatus.SURFACED]),
    ).limit(20))).scalars().all()
    _ATTN_MAP = {
        "pending_question": ("QUESTION", "CLARIFY", True),
        "unfinished_thought": ("FOLLOW_UP", "CHECK_BACK", True),
        "callback": ("CALLBACK", "CHECK_BACK", True),
        "promise": ("ACT", "FULFIL_OWN_PROMISE", False),
        "reentry": ("FOLLOW_UP", "CHECK_BACK", True),
    }
    for att in atts:
        kind_key = str(getattr(att.kind, "value", att.kind) or "").lower()
        mapped = _ATTN_MAP.get(kind_key)
        if mapped is None:
            telemetry["UNREPRESENTED_SCHEMA_GAP"] = telemetry.get(
                "UNREPRESENTED_SCHEMA_GAP", 0) + 1
            continue
        kind, reason, maybe_user = mapped
        title = att.content or "attention matter"
        answered = None
        if maybe_user:
            answered = await _internally_answered(db, workspace_id, title)
        if answered is not None:
            internally_resolved += 1
            telemetry["NO_MOVE_WARRANTED"] = telemetry.get("NO_MOVE_WARRANTED", 0) + 1
            continue
        hold = await _surface_hold(
            db, workspace_id=workspace_id, session_id=session_id,
            key=f"attention:{att.id}", now=now)
        window = None
        try:
            if att.not_before or att.expires_at:
                window = f"{att.not_before}/{att.expires_at}"
        except Exception:
            pass
        emit(Move(
            move_id=f"{kind}:attention:{att.id}", kind=kind, reason=reason,
            matter_kind="attention", matter_id=str(att.id),
            source_refs=[r for r in [att.source_message_id] if r],
            support=float(att.confidence or 0.5),
            salience=float(att.salience or 0.5),
            eligibility="eligible" if hold is None else hold,
            window=window,
            lifecycle="held" if hold else "eligible",
            owner=str(att.owner_peer_id or "sophie"),
            user_facing=maybe_user and hold is None,
            telemetry="MOVE_ELIGIBLE" if hold is None else "MOVE_HELD"))

    clars = (await db.execute(select(ClarificationCandidate).where(
        ClarificationCandidate.honcho_workspace_id == workspace_id,
        ClarificationCandidate.honcho_session_id == session_id,
        ClarificationCandidate.status == ClarificationStatus.PENDING,
    ).limit(10))).scalars().all()
    for clar in clars:
        title = clar.description or "clarification"
        if await _internally_answered(db, workspace_id, title) is not None:
            internally_resolved += 1
            telemetry["NO_MOVE_WARRANTED"] = telemetry.get("NO_MOVE_WARRANTED", 0) + 1
            continue
        hold = await _surface_hold(
            db, workspace_id=workspace_id, session_id=session_id,
            key=f"clarification:{clar.id}", now=now)
        emit(Move(
            move_id=f"QUESTION:clarification:{clar.id}", kind="QUESTION",
            reason="CLARIFY", matter_kind="clarification", matter_id=str(clar.id),
            source_refs=[clar.honcho_message_id] if clar.honcho_message_id else [],
            support=0.6, salience=0.6,
            eligibility="eligible" if hold is None else hold,
            lifecycle="held" if hold else "eligible",
            user_facing=hold is None,
            telemetry="MOVE_ELIGIBLE" if hold is None else "MOVE_HELD"))

    cands = (await db.execute(select(CommitmentCandidate).where(
        CommitmentCandidate.honcho_workspace_id == workspace_id,
        CommitmentCandidate.honcho_session_id == session_id,
        CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
    ).limit(10))).scalars().all()
    for cand in cands:
        authority = str(getattr(cand.authority, "value", cand.authority) or "")
        if authority == "ask":
            # ASK is proposal-only: surfaced as PROPOSE, never promoted to ACT.
            emit(Move(
                move_id=f"PROPOSE:commitment:{cand.id}", kind="PROPOSE",
                reason="OPPORTUNITY", matter_kind="commitment",
                matter_id=str(cand.id),
                source_refs=[cand.source_message_id] if cand.source_message_id else [],
                support=0.5, salience=0.5, eligibility="eligible",
                lifecycle="eligible", owner=str(cand.owner_peer_id or "sophie"),
                user_facing=False, telemetry="MOVE_ELIGIBLE"))
        else:
            emit(Move(
                move_id=f"ACT:commitment:{cand.id}", kind="ACT",
                reason="FULFIL_OWN_PROMISE", matter_kind="commitment",
                matter_id=str(cand.id),
                source_refs=[cand.source_message_id] if cand.source_message_id else [],
                support=0.7, salience=0.7, eligibility="eligible",
                lifecycle="eligible", owner=str(cand.owner_peer_id or "sophie"),
                user_facing=False, telemetry="MOVE_ELIGIBLE"))

    loops = (await db.execute(select(OpenLoop).where(
        OpenLoop.honcho_workspace_id == workspace_id,
        OpenLoop.honcho_session_id == session_id,
        OpenLoop.status == OpenLoopStatus.OPEN,
    ).limit(10))).scalars().all()
    for loop in loops:
        title = f"{loop.title or ''} {loop.summary or ''}".strip()
        if await _internally_answered(db, workspace_id, title) is not None:
            internally_resolved += 1
            telemetry["NO_MOVE_WARRANTED"] = telemetry.get("NO_MOVE_WARRANTED", 0) + 1
            continue
        hold = await _surface_hold(
            db, workspace_id=workspace_id, session_id=session_id,
            key=f"open_loop:{loop.id}", now=now)
        emit(Move(
            move_id=f"FOLLOW_UP:open_loop:{loop.id}", kind="FOLLOW_UP",
            reason="CHECK_BACK", matter_kind="open_loop", matter_id=str(loop.id),
            source_refs=[loop.honcho_message_id] if loop.honcho_message_id else [],
            support=0.6, salience=0.6,
            eligibility="eligible" if hold is None else hold,
            lifecycle="held" if hold else "eligible",
            user_facing=hold is None,
            telemetry="MOVE_ELIGIBLE" if hold is None else "MOVE_HELD"))

    occs = (await db.execute(select(RecurringOccurrence).where(
        RecurringOccurrence.honcho_workspace_id == workspace_id,
    ).order_by(RecurringOccurrence.created_at.desc()).limit(10))).scalars().all()
    for occ in occs:
        status = str(getattr(occ.status, "value", occ.status) or "")
        if status != "pending":
            continue
        emit(Move(
            move_id=f"REMIND:occurrence:{occ.id}", kind="REMIND", reason="DUE",
            matter_kind="occurrence", matter_id=str(occ.id),
            source_refs=[], support=0.6, salience=0.6, eligibility="eligible",
            lifecycle="eligible", user_facing=False, telemetry="MOVE_HELD"))

    claims = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == workspace_id).limit(200))).scalars().all()
    rels = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == workspace_id).limit(200))).scalars().all()
    for title in graph.waiting_on(list(claims), list(rels)):
        emit(Move(
            move_id=f"WATCH:graph:{abs(hash(title)) % 10**8}", kind="WATCH",
            reason="MONITOR", matter_kind="graph", matter_id=title,
            source_refs=[], support=0.6, salience=0.5, eligibility="eligible",
            lifecycle="eligible", user_facing=False, telemetry="MOVE_ELIGIBLE"))
    for title in graph.third_party_open(list(claims), list(rels)):
        emit(Move(
            move_id=f"WATCH:thirdparty:{abs(hash(title)) % 10**8}", kind="WATCH",
            reason="MONITOR", matter_kind="graph", matter_id=title,
            source_refs=[], support=0.6, salience=0.5, eligibility="eligible",
            lifecycle="eligible", user_facing=False, telemetry="MOVE_ELIGIBLE"))

    moves.sort(key=lambda m: m.move_id)
    return {"moves": [m.to_dict() for m in moves], "telemetry": telemetry,
            "internally_resolved": internally_resolved}
