"""Phase-B tiny persistence: reified semantic claims + relations.

Deliberate non-goals (the five-trap guardrails are structural, not comments):
- No role/family column: state roles stay zero-to-many derived views.
- No salience/surface/actionability columns: remembered != salient !=
  user-facing. Surfacing reads via the existing attention machinery.
- No authority/operation columns: whether a relation may become a task,
  reminder, or calendar event is decided by existing gates
  (list_actionable, SurfaceRegistry), never by this store.
- Bounded rel_type: writers outside RELATION_VOCAB are rejected, never
  persisted. Unknown semantics are preserved as shadow telemetry
  (UNREPRESENTED_SCHEMA_GAP), never as invented predicates.
"""

import hashlib
import re
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Column
from sqlalchemy import Enum as SAEnum
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_claim_content(text: str) -> str:
    """Stable identity basis: lowercase, whitespace-collapsed, NFKD-folded."""
    import unicodedata
    folded = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", folded.strip().lower())


def content_hash_for(text: str) -> str:
    return hashlib.sha1(normalize_claim_content(text).encode()).hexdigest()


class RelationType(str, Enum):
    SAME_AS = "same_as"
    REFINES = "refines"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DEPENDS_ON = "depends_on"
    PART_OF = "part_of"
    CONDITIONED_ON = "conditioned_on"
    FULFILS = "fulfils"
    PARTIALLY_FULFILS = "partially_fulfils"
    RESOLVES = "resolves"
    REOPENS = "reopens"
    ENABLES = "enables"
    BLOCKS = "blocks"


RELATION_VOCAB = frozenset(t.value for t in RelationType)


class RelationFormation(str, Enum):
    EXPLICIT = "explicit"
    INFERRED = "inferred"


class RelationStatus(str, Enum):
    ACTIVE = "active"
    SUPERSEDED = "superseded"
    RETRACTED = "retracted"


class SemanticClaim(SQLModel, table=True):
    """One permissive semantic node: open-ended content, stable identity.

    Identity is (workspace, content_hash): the same claim re-evidenced is one
    row with growing evidence refs (append-only), never a duplicate.
    """

    __tablename__ = "semantic_claims"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    honcho_workspace_id: str = Field(index=True, nullable=False)
    content_hash: str = Field(index=True, nullable=False)
    content: str = Field(nullable=False)
    subjects_json: str = Field(default="[]", nullable=False)
    evidence_refs_json: str = Field(default="[]", nullable=False)
    formation: RelationFormation = Field(
        default=RelationFormation.INFERRED,
        sa_column=Column(SAEnum(RelationFormation, native_enum=False, values_callable=lambda e: [m.value for m in e]), nullable=False),
    )
    confidence: float = Field(default=0.7, nullable=False)
    effective_at: Optional[datetime] = Field(default=None)
    discovered_at: Optional[datetime] = Field(default=None)

    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class SemanticRelation(SQLModel, table=True):
    """One reified relation with its own provenance.

    The relation knows why it exists (evidence_refs), how (formation),
    how strongly (confidence), and when (effective/discovered/corroborated).
    Revision is append-only: new rows + status transitions, never in-place
    rewrites of why something was believed. The single exception is evidence
    growth on the same active triple (union of refs + last_corroborated_at),
    which records corroboration without altering the original belief.
    """

    __tablename__ = "semantic_relations"
    __table_args__ = (
        CheckConstraint(
            "rel_type IN ('same_as','refines','contradicts','supersedes',"
            "'depends_on','part_of','conditioned_on','fulfils',"
            "'partially_fulfils','resolves','reopens','enables','blocks')",
            name="ck_semantic_relation_type_bounded",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    honcho_workspace_id: str = Field(index=True, nullable=False)
    rel_type: RelationType = Field(
        sa_column=Column(SAEnum(RelationType, native_enum=False, values_callable=lambda e: [m.value for m in e]), nullable=False, index=True),
    )
    from_claim_id: UUID = Field(foreign_key="semantic_claims.id", index=True, nullable=False)
    to_claim_id: UUID = Field(foreign_key="semantic_claims.id", index=True, nullable=False)
    evidence_refs_json: str = Field(default="[]", nullable=False)
    formation: RelationFormation = Field(
        default=RelationFormation.INFERRED,
        sa_column=Column(SAEnum(RelationFormation, native_enum=False, values_callable=lambda e: [m.value for m in e]), nullable=False),
    )
    confidence: float = Field(default=0.7, nullable=False)
    effective_at: Optional[datetime] = Field(default=None)
    discovered_at: Optional[datetime] = Field(default=None)
    last_corroborated_at: Optional[datetime] = Field(default=None)
    status: RelationStatus = Field(
        default=RelationStatus.ACTIVE,
        sa_column=Column(SAEnum(RelationStatus, native_enum=False, values_callable=lambda e: [m.value for m in e]), nullable=False, index=True),
    )
    superseded_by_id: Optional[UUID] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
