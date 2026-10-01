"""Epistemic envelope helpers over the existing ModelEntry store.

One epistemic system (docs/CORTEX_ARCHITECTURE.md §4): ModelEntry already has
formation, confidence, evidence and supersession. This module adds the shared
vocabulary and the invariants — never a second store:

* five formation classes: explicit(reported by the user), reported (relayed /
  attributed), source_linked (external system), observed, inferred, hypothesis
* a derived interpretation never silently becomes fact: inferred/hypothesis
  claims cannot supersede an explicit one (they sit beside it as `conflicting`)
* status: current | uncertain | conflicting | stale | superseded
* `explain()` answers "why does Cortex believe this?" from evidence/provenance
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

EXPLICIT = "explicit"
REPORTED = "reported"
SOURCE_LINKED = "source_linked"
OBSERVED = "observed"
INFERRED = "inferred"
HYPOTHESIS = "hypothesis"
FORMATION_CLASSES = (EXPLICIT, REPORTED, SOURCE_LINKED, OBSERVED, INFERRED, HYPOTHESIS)
# Higher = firmer. A lower-ranked claim may never replace a higher-ranked one.
FORMATION_RANK = {EXPLICIT: 5, SOURCE_LINKED: 4, REPORTED: 3, OBSERVED: 2, INFERRED: 1, HYPOTHESIS: 0}
FIRM_FORMATIONS = frozenset({EXPLICIT, REPORTED, SOURCE_LINKED})

_PROVENANCE_TO_FORMATION = {
    "direct_statement": EXPLICIT,
    "reported_statement": REPORTED,
    "attributed_belief": REPORTED,
    "observation": OBSERVED,
    "pattern": OBSERVED,
    "inference": INFERRED,
    "derived_state": INFERRED,
    "hypothesis": HYPOTHESIS,
    "external_source": SOURCE_LINKED,
}

STATUSES = ("current", "uncertain", "conflicting", "stale", "superseded")
CLAIM_KINDS = frozenset({
    "matter_summary", "pattern", "observation", "relationship_development",
    "repair", "perspective", "user_model", "correction", "decision",
})
STALE_AFTER_DAYS_FIRM = 365
STALE_AFTER_DAYS_SOFT = 120
UNCERTAIN_BELOW = 0.5


def formation_class(value: Any) -> str:
    """Map any stored formation/provenance string into the five-class
    vocabulary. Unknown values map to `inferred` — never upgraded to firm."""
    raw = str(getattr(value, "value", value) or "").strip().lower()
    if raw in FORMATION_RANK:
        return raw
    return _PROVENANCE_TO_FORMATION.get(raw, INFERRED)


def is_firm(value: Any) -> bool:
    return formation_class(value) in FIRM_FORMATIONS


def derive_status(entry: Any, now: datetime) -> str:
    """Status of a ModelEntry-shaped row as of `now`."""
    if getattr(entry, "superseded_by_id", None):
        return "superseded"
    stored = str(getattr(entry, "epistemic_status", "") or "current")
    if stored in ("conflicting", "uncertain", "stale"):
        return stored
    if float(getattr(entry, "confidence", 1.0) or 0.0) < UNCERTAIN_BELOW:
        return "uncertain"
    ref = getattr(entry, "effective_at", None) or getattr(entry, "updated_at", None) \
        or getattr(entry, "created_at", None)
    if ref is not None:
        limit = STALE_AFTER_DAYS_FIRM if is_firm(getattr(entry, "formation", "")) \
            else STALE_AFTER_DAYS_SOFT
        if now - ref > timedelta(days=limit):
            return "stale"
    return "current"


def _refs(entry: Any) -> List[str]:
    try:
        refs = json.loads(getattr(entry, "evidence_refs_json", "[]") or "[]")
    except (TypeError, ValueError):
        refs = []
    refs = [str(r) for r in refs if r]
    mid = getattr(entry, "honcho_message_id", None)
    if mid and mid not in refs:
        refs.append(str(mid))
    return refs


def entry_view(entry: Any, now: datetime) -> Dict[str, Any]:
    """Compact, provenance-carrying view of one ModelEntry."""
    return {
        "ref": {"type": "model_entry", "id": str(entry.id)},
        "claim": entry.claim,
        "claim_kind": getattr(entry, "claim_kind", None) or entry.model_kind,
        "model_kind": entry.model_kind,
        "formation": formation_class(entry.formation),
        "confidence": entry.confidence,
        "status": derive_status(entry, now),
        "holder_actor": getattr(entry, "holder_actor", None),
        "direction": getattr(entry, "direction", None),
        "subject_entity_id": str(entry.subject_entity_id) if entry.subject_entity_id else None,
        "subject_matter_id": str(entry.subject_matter_id) if getattr(entry, "subject_matter_id", None) else None,
        "evidence_refs": _refs(entry),
        "effective_at": entry.effective_at.isoformat() if entry.effective_at else None,
    }


async def write_claim(
    db: AsyncSession, *, workspace_id: str, session_id: str, message_id: str,
    owner_peer_id: Optional[str], model_kind: str, claim: str,
    evidence_verbatim: str, formation: str, confidence: float,
    claim_kind: Optional[str] = None, subject_entity_id: Optional[UUID] = None,
    subject_matter_id: Optional[UUID] = None, holder_actor: Optional[str] = None,
    direction: Optional[str] = None, evidence_refs: Optional[List[str]] = None,
    supersedes_id: Optional[UUID] = None, effective_at: Optional[datetime] = None,
) -> Any:
    """The one write path for epistemic claims.

    Enforces: formation normalisation; system-held claims are `perspective`
    kind and can never be `explicit`; an inferred/hypothesis claim cannot
    supersede a firm one (it is stored beside it and both are marked
    `conflicting`) — an interpretation never silently replaces what the user
    actually said."""
    from src.models.identity import ModelEntry
    fclass = formation_class(formation)
    holder = (holder_actor or "").strip() or None
    kind = claim_kind
    if holder == "system":
        kind = "perspective"
        if fclass in (EXPLICIT, REPORTED, SOURCE_LINKED):
            fclass = INFERRED  # the system's own thought is never user testimony
    if kind is not None and kind not in CLAIM_KINDS:
        raise ValueError(f"unknown claim_kind {kind!r}")
    # Idempotent per (workspace, message, claim text): re-applying the same
    # consolidation run never duplicates a claim.
    same_message = (await db.execute(select(ModelEntry).where(
        ModelEntry.honcho_workspace_id == workspace_id,
        ModelEntry.honcho_message_id == message_id,
        ModelEntry.superseded_by_id.is_(None)))).scalars().all()
    for row in same_message:
        if row.claim.strip().lower() == claim[:1000].strip().lower() and row.claim_kind == kind:
            return row
    entry = ModelEntry(
        honcho_workspace_id=workspace_id, honcho_session_id=session_id,
        honcho_message_id=message_id, owner_peer_id=owner_peer_id,
        subject_entity_id=subject_entity_id, model_kind=model_kind,
        claim=claim[:1000], evidence_verbatim=evidence_verbatim[:2000],
        formation=fclass, confidence=max(0.0, min(1.0, float(confidence))),
        effective_at=effective_at, claim_kind=kind,
        subject_matter_id=subject_matter_id, holder_actor=holder,
        direction=direction,
        evidence_refs_json=json.dumps(list(evidence_refs or [])),
    )
    prior = await db.get(ModelEntry, supersedes_id) if supersedes_id else None
    if prior is not None and prior.superseded_by_id is None:
        if FORMATION_RANK[fclass] < FORMATION_RANK[formation_class(prior.formation)] \
                and is_firm(prior.formation):
            entry.epistemic_status = "conflicting"
            prior.epistemic_status = "conflicting"
            db.add(prior)
            prior = None
    db.add(entry)
    await db.flush()
    if prior is not None and prior.superseded_by_id is None:
        prior.superseded_by_id = entry.id
        prior.epistemic_status = "superseded"
        db.add(prior)
    await db.commit()
    return entry


async def explain(db: AsyncSession, object_type: str, object_id: UUID,
                  now: Optional[datetime] = None) -> Dict[str, Any]:
    """Why does Cortex believe this? Evidence, formation, supersession chain,
    annotations and relations — read from the canonical rows."""
    from src.models.epistemic import EpistemicAnnotation
    from src.models.expectation import Expectation
    from src.models.fact import Fact
    from src.models.identity import ModelEntry
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.open_loop import OpenLoop
    from src.models.semantic import RelationStatus, SemanticClaim, SemanticRelation
    now = now or datetime.utcnow()
    registry = {"model_entry": ModelEntry, "expectation": Expectation, "fact": Fact,
                "commitment": CommitmentCandidate, "open_loop": OpenLoop}
    model = registry.get(object_type)
    row = await db.get(model, object_id) if model else None
    if row is None:
        return {"found": False, "ref": {"type": object_type, "id": str(object_id)}}
    out: Dict[str, Any] = {"found": True, "ref": {"type": object_type, "id": str(object_id)}}
    message_id = getattr(row, "honcho_message_id", None) or getattr(row, "source_message_id", None)
    if object_type == "model_entry":
        out.update(entry_view(row, now))
        out["evidence_verbatim"] = row.evidence_verbatim
        chain, cur, seen = [], row, set()
        while cur is not None and cur.superseded_by_id and cur.id not in seen:
            seen.add(cur.id)
            nxt = await db.get(ModelEntry, cur.superseded_by_id)
            if nxt is None:
                break
            chain.append({"id": str(nxt.id), "claim": nxt.claim, "formation": formation_class(nxt.formation)})
            cur = nxt
        out["superseded_by_chain"] = chain
        preds = (await db.execute(select(ModelEntry).where(
            ModelEntry.superseded_by_id == row.id))).scalars().all()
        out["supersedes"] = [{"id": str(p.id), "claim": p.claim} for p in preds]
    else:
        out["formation"] = formation_class(getattr(row, "formation", "explicit"))
        out["title"] = getattr(row, "title", None)
        out["evidence_verbatim"] = getattr(row, "evidence_verbatim", None) \
            or getattr(row, "resolution_evidence", None)
        out["evidence_refs"] = [message_id] if message_id else []
        out["confidence"] = getattr(row, "confidence", None) or getattr(row, "extraction_confidence", None)
    if message_id:
        anns = (await db.execute(select(EpistemicAnnotation).where(
            EpistemicAnnotation.honcho_workspace_id == row.honcho_workspace_id,
            EpistemicAnnotation.honcho_message_id == message_id))).scalars().all()
        out["annotations"] = [{
            "provenance_type": a.provenance_type.value if hasattr(a.provenance_type, "value") else str(a.provenance_type),
            "formation_class": formation_class(a.provenance_type),
            "perspective_peer_id": a.perspective_peer_id, "target_peer_id": a.target_peer_id,
            "claim_summary": a.claim_summary, "confidence": a.confidence,
        } for a in anns]
        claims = (await db.execute(select(SemanticClaim).where(
            SemanticClaim.honcho_workspace_id == row.honcho_workspace_id,
            SemanticClaim.source_key.like(f"honcho_message:{message_id}%")))).scalars().all()
        rels: List[Dict[str, Any]] = []
        for c in claims:
            for r in (await db.execute(select(SemanticRelation).where(
                    SemanticRelation.status == RelationStatus.ACTIVE,
                    (SemanticRelation.from_claim_id == c.id) | (SemanticRelation.to_claim_id == c.id)))).scalars().all():
                rels.append({"rel_type": r.rel_type.value if hasattr(r.rel_type, "value") else str(r.rel_type),
                             "formation": str(getattr(r.formation, "value", r.formation)),
                             "confidence": r.confidence})
        out["relations"] = rels[:10]
    return out
