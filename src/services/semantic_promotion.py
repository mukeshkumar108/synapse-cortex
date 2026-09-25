"""Phase-B deterministic promotion: lifecycle transitions -> relation rows.

Tiny by design:
- Only called AFTER the production mutation has committed. Promotion owns a
  separate commit, so a promotion failure can never roll back prod state.
- Total function: unknown rel_type or empty content returns None (quarantine
  path; shadow telemetry flags the schema gap). DB errors propagate loudly in
  tests; call sites treat promotion as advisory (fail-open write) so turns
  never break because of it.
- Idempotent: same (workspace, from, to, type) triple with status=active is
  one row; re-promotion unions evidence refs and stamps last_corroborated_at.
  Claims are (workspace, content_hash) idempotent with append-only evidence.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.semantic import (
    RELATION_VOCAB,
    RelationFormation,
    RelationStatus,
    RelationType,
    SemanticClaim,
    SemanticRelation,
    content_hash_for,
    normalize_claim_content,
)

logger = logging.getLogger(__name__)

MAX_CLAIM_CHARS = 500


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clip(text: str) -> str:
    text = normalize_claim_content(text)
    return text[:MAX_CLAIM_CHARS] if len(text) > MAX_CLAIM_CHARS else text


def _union(existing_json: str, new_refs: List[str]) -> str:
    try:
        current = json.loads(existing_json or "[]")
    except (ValueError, TypeError):
        current = []
    merged = list(dict.fromkeys([*(current if isinstance(current, list) else []), *new_refs]))
    return json.dumps(merged)


async def ensure_claim(
    db: AsyncSession,
    *,
    workspace_id: str,
    content: str,
    evidence_refs: List[str],
    formation: str = "inferred",
    confidence: float = 0.7,
    effective_at: Optional[datetime] = None,
    discovered_at: Optional[datetime] = None,
) -> Optional[SemanticClaim]:
    """Get-or-create a claim row. Empty content returns None (never a row)."""
    clipped = _clip(content)
    if not clipped:
        return None
    digest = content_hash_for(clipped)
    row = (await db.execute(select(SemanticClaim).where(
        SemanticClaim.honcho_workspace_id == workspace_id,
        SemanticClaim.content_hash == digest,
    ))).scalar_one_or_none()
    if row is not None:
        merged = _union(row.evidence_refs_json, evidence_refs)
        if merged != row.evidence_refs_json:
            row.evidence_refs_json = merged
            row.confidence = max(row.confidence, confidence)
            row.updated_at = _now_naive()
            db.add(row)
        return row
    row = SemanticClaim(
        honcho_workspace_id=workspace_id,
        content_hash=digest,
        content=clipped,
        evidence_refs_json=json.dumps(list(dict.fromkeys(evidence_refs))),
        formation=RelationFormation(formation) if formation in ("explicit", "inferred") else RelationFormation.INFERRED,
        confidence=confidence,
        effective_at=effective_at,
        discovered_at=discovered_at or _now_naive(),
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        row = (await db.execute(select(SemanticClaim).where(
            SemanticClaim.honcho_workspace_id == workspace_id,
            SemanticClaim.content_hash == digest,
        ))).scalar_one()
        merged = _union(row.evidence_refs_json, evidence_refs)
        if merged != row.evidence_refs_json:
            row.evidence_refs_json = merged
            row.updated_at = _now_naive()
            db.add(row)
    return row


async def promote_transition(
    db: AsyncSession,
    *,
    workspace_id: str,
    rel_type: str,
    from_text: str,
    to_text: str,
    evidence_refs: List[str],
    formation: str = "inferred",
    confidence: float = 0.9,
    effective_at: Optional[datetime] = None,
) -> Optional[SemanticRelation]:
    """Persist one deterministic lifecycle edge. Returns the row, or None when
    the input is outside the bounded vocabulary / empty (quarantine path)."""
    if rel_type not in RELATION_VOCAB:
        logger.warning("semantic promotion refused unknown rel_type=%r", rel_type)
        return None
    # Refuse before materializing anything: empty or identical endpoints
    # never create claim rows.
    if not _clip(from_text) or not _clip(to_text):
        return None
    if content_hash_for(from_text) == content_hash_for(to_text):
        logger.warning("semantic promotion refused self-edge")
        return None
    from_claim = await ensure_claim(
        db, workspace_id=workspace_id, content=from_text,
        evidence_refs=evidence_refs, formation=formation, confidence=confidence,
        effective_at=effective_at)
    to_claim = await ensure_claim(
        db, workspace_id=workspace_id, content=to_text,
        evidence_refs=evidence_refs, formation=formation, confidence=confidence,
        effective_at=effective_at)
    if from_claim is None or to_claim is None:
        return None
    existing = (await db.execute(select(SemanticRelation).where(
        SemanticRelation.honcho_workspace_id == workspace_id,
        SemanticRelation.rel_type == RelationType(rel_type),
        SemanticRelation.from_claim_id == from_claim.id,
        SemanticRelation.to_claim_id == to_claim.id,
        SemanticRelation.status == RelationStatus.ACTIVE,
    ))).scalar_one_or_none()
    now = _now_naive()
    if existing is not None:
        merged = _union(existing.evidence_refs_json, evidence_refs)
        if merged != existing.evidence_refs_json:
            existing.evidence_refs_json = merged
            existing.last_corroborated_at = now
            existing.confidence = max(existing.confidence, confidence)
            existing.updated_at = now
            db.add(existing)
            await db.commit()
        return existing
    row = SemanticRelation(
        honcho_workspace_id=workspace_id,
        rel_type=RelationType(rel_type),
        from_claim_id=from_claim.id,
        to_claim_id=to_claim.id,
        evidence_refs_json=json.dumps(list(dict.fromkeys(evidence_refs))),
        formation=RelationFormation(formation) if formation in ("explicit", "inferred") else RelationFormation.INFERRED,
        confidence=confidence,
        effective_at=effective_at,
        discovered_at=now,
        status=RelationStatus.ACTIVE,
    )
    db.add(row)
    await db.commit()
    return row
