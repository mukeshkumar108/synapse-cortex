"""CurrentMeaning reconstructibility diagnostic (3A closeout).

RPD2 proved durable state alone is not enough: an Account-style read must be
derivable from shared Cortex state. This module derives that read
deterministically from T0/T1 rows only — no model calls, no new state.
Anything requiring interpretation (posture, stance, trajectory meaning) is
listed as EVIDENCE with an explicit gap marker instead of invented.

Amended T2b contract (no durable Account table; replace-not-accumulate):
- as_of_turn, frame_scope, scene_or_session_ref, relationship/subject refs
- trajectory, dominant_current_meaning (generalized, not rupture-specific)
- active_interpretations[] (kind/scope, claim, evidence, since, confidence,
  formation) — tension/repair/grief/decision-pressure/disclosure/uncertainty
- easing_release[] (what changed + evidence)
- salient expectation/loop refs, previous-snapshot delta
  (activated/reframed/eased/released)
- confidence PER CLAIM, never blanket; posture implications are OUT —
  Control/Attention derives posture from this read, CurrentMeaning never
  choreographs behaviour.
Shape per checkpoint: trajectory, orientation, relevant expectations,
unresolved foreground-relevant matters, released/backgrounded matters,
posture-inputs (evidence only), confidence/evidence coverage, delta.
"""
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.clarification import ClarificationCandidate, ClarificationStatus
from src.models.commitment_candidate import CommitmentCandidate
from src.models.expectation import Expectation, OutcomeState
from src.models.fact import Fact
from src.models.identity import ModelEntry
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionStatus


def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def derive_diagnostic(
    db: AsyncSession, *, workspace_id: str,
    previous: Optional[Dict[str, Any]] = None,
    limit: int = 8,
) -> Dict[str, Any]:
    """Read-only structural rollup answering: can shared state reconstruct
    an Account-style current-meaning read? Returns sections + delta."""
    exps = (await db.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id))).scalars().all()
    comms = (await db.execute(select(CommitmentCandidate).where(
        CommitmentCandidate.honcho_workspace_id == workspace_id))).scalars().all()
    loops = (await db.execute(select(OpenLoop).where(
        OpenLoop.honcho_workspace_id == workspace_id))).scalars().all()
    facts = (await db.execute(select(Fact).where(
        Fact.honcho_workspace_id == workspace_id))).scalars().all()
    models = (await db.execute(select(ModelEntry).where(
        ModelEntry.honcho_workspace_id == workspace_id))).scalars().all()
    supps = (await db.execute(select(Suppression).where(
        Suppression.honcho_workspace_id == workspace_id))).scalars().all()
    clars = (await db.execute(select(ClarificationCandidate).where(
        ClarificationCandidate.honcho_workspace_id == workspace_id))).scalars().all()

    unknown_exps = [e for e in exps if e.outcome_state == OutcomeState.UNKNOWN]
    open_loops = [o for o in loops if o.status == OpenLoopStatus.OPEN]
    pending_clars = [c for c in clars if c.status == ClarificationStatus.PENDING]
    active_supps = [s for s in supps if s.status == SuppressionStatus.ACTIVE]
    released = [
        {"id": str(e.id), "title": e.title, "state": e.outcome_state.value,
         "evidence": e.resolution_evidence}
        for e in exps if e.outcome_state != OutcomeState.UNKNOWN
    ] + [
        {"id": str(o.id), "title": o.title, "state": o.status.value,
         "evidence": o.resolution_evidence}
        for o in loops if o.status != OpenLoopStatus.OPEN
    ]
    with_evidence = sum(
        1 for row in list(exps) + list(comms) + list(facts) + list(models)
        for text in [getattr(row, "resolution_evidence", None)
                     or getattr(row, "evidence_verbatim", None)]
        if text)
    total_rows = len(exps) + len(comms) + len(facts) + len(models)
    current_ids = {str(r.id) for r in list(exps) + list(comms) + list(loops)
                   + list(facts) + list(models)}
    prev_ids = set((previous or {}).get("ids", []))
    diagnostic = {
        "ids": sorted(current_ids),
        "counts": {
            "expectations": len(exps), "unknown_expectations": len(unknown_exps),
            "commitments": len(comms), "open_loops": len(loops),
            "open_loops_open": len(open_loops), "facts": len(facts),
            "model_entries": len(models), "active_suppressions": len(active_supps),
            "pending_clarifications": len(pending_clars),
        },
        "trajectory_structural": {
            "open_items": len(unknown_exps) + len(open_loops) + len(pending_clars),
            "released_items": len(released),
            "note": "counts only; direction of travel needs interpretation",
        },
        "relevant_expectations": [
            {"id": str(e.id), "title": e.title, "type": e.expectation_type.value,
             "formation": e.formation, "owner": e.owner_peer_id}
            for e in unknown_exps[:limit]
        ],
        "unresolved_foreground": (
            [{"kind": "open_loop", "id": str(o.id), "title": o.title} for o in open_loops[:limit]]
            + [{"kind": "clarification", "id": str(c.id), "title": c.description[:120]}
               for c in pending_clars[:limit]]
            + [{"kind": "commitment", "id": str(c.id), "title": c.title,
                 "owner": c.owner_peer_id} for c in comms[:limit]]
        ),
        "released_backgrounded": released[:limit],
        "model_state": [
            {"id": str(m.id), "kind": m.model_kind, "claim": m.claim[:160],
             "formation": m.formation} for m in models[:limit]
        ],
        "posture_inputs_evidence_only": {
            "suppressions": [{"topic": s.topic_or_entity, "reason": s.reason} for s in active_supps],
            "standing_commitments": len(comms),
            "gap": "stance/posture conclusions require an interpreter; inputs listed, no conclusion drawn",
        },
        "evidence_coverage": {
            "rows_with_evidence": with_evidence, "total_rows": total_rows,
        },
        "delta_ids": sorted(current_ids - prev_ids),
    }
    return diagnostic
