"""Action projection (Workstream 2): underlying meaning -> actionable surface.

Many things may PROJECT into Tasks; not everything fundamentally IS a Task.
Cortex preserves the underlying semantic type; a bounded, provenance-rich
commitment candidate lets the product (Sophie Noticed -> user acceptance ->
canonical Task in the app) decide what becomes actionable. Deterministic,
idempotent, and authority-gated: the projection is always a fallible ASK
candidate, never canonical Task state.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.models.operational_state import RecurringIntention
from src.schemas.candidate import ExtractionCandidate
from src.services.commitment_candidate_service import (
    CommitmentCandidateService,
    canonical_key_for,
)

# Semantic types that are genuinely actionable and therefore project.
# observed_pattern (ordinary repeated behaviour) deliberately does NOT project:
# narrated life patterns must not become Tasks without an explicit user ask.
ACTIONABLE_SEMANTIC_TYPES = {
    "recurring_action",
    "recurring_ritual",
    "adherence_action",
    "measurable_goal",
}

_candidate_service = CommitmentCandidateService()


async def project_recurrence_to_candidate(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    message_id: str,
    peer_id: str,
    recurrence: RecurringIntention,
    candidate: Optional[ExtractionCandidate] = None,
    now: datetime,
) -> Optional[Dict[str, Any]]:
    """Project an actionable recurring intention into the bounded candidate
    store so the product can surface it ("Sophie noticed") and the user can
    promote it to a canonical Task. Idempotent via the projection candidate
    key and canonical dedupe in CommitmentCandidateService."""
    semantic_type = recurrence.semantic_type or (
        candidate.recurrence_semantic_type if candidate else None
    )
    if semantic_type not in ACTIONABLE_SEMANTIC_TYPES:
        return None

    title = recurrence.title
    projection_key = f"recproj:{canonical_key_for(title)}"
    notes = (
        f"Projected from recurring_intention {recurrence.id} "
        f"(semantic_type={semantic_type}, cadence={recurrence.cadence})"
    )
    payload = ExtractionCandidate(
        candidate_key=projection_key,
        observation=title,
        canonical_title=title,
        operational_kind="commitment_candidate",
        evidence_class="implicit_self_commitment",
        authority="ask",
        raw_evidence=recurrence.source_evidence,
        confidence=min(0.85, float(recurrence.confidence or 0.8)),
        recurrence_semantic_type=semantic_type,  # type: ignore[arg-type]
        cadence=recurrence.cadence,  # type: ignore[arg-type]
        target_amount=recurrence.target_amount,
        target_unit=recurrence.target_unit,
        validation_notes=["recurrence_action_projection"],
    )
    row = await _candidate_service.upsert_from_candidate(
        db, workspace_id=workspace_id, session_id=session_id,
        owner_peer_id=peer_id, message_id=message_id,
        candidate=payload, now=now,
    )
    if row is None:
        return None
    return {
        "candidate_id": str(row.id),
        "canonical_key": row.canonical_key,
        "semantic_type": semantic_type,
        "authority": row.authority.value,
        "note": notes,
    }
