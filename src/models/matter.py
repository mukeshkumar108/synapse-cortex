"""Matter: something in the shared world with enough continuity to maintain.

A Matter is a generic coherence layer over the specialised primitives; it owns
only lifecycle + inspectable foreground components. It is NEVER session-owned:
it is scoped to workspace + the person whose world it is, and a session or
message may appear only as optional provenance. The summary is a reference to
the authoritative ModelEntry (or a reconstructable cache) — never a second
canonical narrative. See docs/CORTEX_ARCHITECTURE.md §3.
"""
from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, Index, UniqueConstraint
from sqlalchemy import text as sa_text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MatterKind(str, Enum):
    PROJECT = "project"
    TOPIC = "topic"
    CONCERN = "concern"
    RELATIONSHIP_SITUATION = "relationship_situation"
    GOAL = "goal"
    LIFE_SITUATION = "life_situation"
    ROUTINE = "routine"
    OTHER = "other"


class MatterStatus(str, Enum):
    ACTIVE = "active"
    DORMANT = "dormant"
    RESOLVED = "resolved"
    ARCHIVED = "archived"


MATTER_KINDS = frozenset(k.value for k in MatterKind)
MATTER_STATUSES = frozenset(s.value for s in MatterStatus)
# Deliberately small. Do not grow speculatively (docs/CORTEX_ARCHITECTURE.md §3).
MATTER_RELATIONS = frozenset({"related_to", "part_of", "depends_on"})


class Matter(SQLModel, table=True):
    __tablename__ = "matters"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    # Whose world this is. Nullable only for legacy rows that never carried an
    # owner (those are reachable through their provenance session).
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(default="other", nullable=False, index=True)
    title: str = Field(nullable=False)
    canonical_key: str = Field(default="", nullable=False, index=True)
    status: str = Field(default="active", nullable=False, index=True)
    first_seen: datetime = Field(default_factory=utc_now, nullable=False)
    active_since: datetime = Field(default_factory=utc_now, nullable=False)
    last_touched: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    resolved_at: Optional[datetime] = Field(default=None)
    merged_into_id: Optional[UUID] = Field(default=None, index=True)
    # Reference to the authoritative current-summary ModelEntry. Any summary
    # text surfaced with a Matter is read through this reference.
    summary_entry_id: Optional[UUID] = Field(default=None)
    confidence: float = Field(default=0.7, nullable=False)
    formation: str = Field(default="inferred", nullable=False)
    # Optional provenance only — a session never owns a Matter.
    origin_session_id: Optional[str] = Field(default=None)
    origin_message_id: Optional[str] = Field(default=None)
    last_touched_session_id: Optional[str] = Field(default=None)
    # Derived cache of inspectable components (recency, frequency, ...).
    salience_components_json: str = Field(default="{}", nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class MatterLink(SQLModel, table=True):
    """Matter ↔ primitive row (many-to-many, role-qualified)."""

    __tablename__ = "matter_links"
    __table_args__ = (
        UniqueConstraint("matter_id", "object_type", "object_id",
                         name="uq_matter_link_object"),
        # A primitive is the SUBJECT of at most one Matter. Concurrent
        # reconcilers that race to found a Matter for the same primitive
        # cannot both win: the loser's transaction rolls back (sync handles it).
        Index("uq_matter_link_subject", "object_type", "object_id", unique=True,
              postgresql_where=sa_text("role = 'subject'"),
              sqlite_where=sa_text("role = 'subject'")),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    matter_id: UUID = Field(index=True, nullable=False)
    object_type: str = Field(nullable=False, index=True)
    object_id: UUID = Field(nullable=False, index=True)
    role: str = Field(default="subject", nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    provenance_message_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class MatterRelation(SQLModel, table=True):
    __tablename__ = "matter_relations"
    __table_args__ = (
        CheckConstraint(
            "rel_type IN ('related_to','part_of','depends_on')",
            name="ck_matter_relation_type_bounded",
        ),
        Index(
            "uq_matter_relation_edge", "honcho_workspace_id", "from_matter_id",
            "to_matter_id", "rel_type", unique=True,
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    from_matter_id: UUID = Field(index=True, nullable=False)
    to_matter_id: UUID = Field(index=True, nullable=False)
    rel_type: str = Field(nullable=False)
    evidence_refs_json: str = Field(default="[]", nullable=False)
    formation: str = Field(default="inferred", nullable=False)
    confidence: float = Field(default=0.7, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
