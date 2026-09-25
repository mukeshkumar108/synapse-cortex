"""Step 3A identity substrate + Model primitive store.

Entities are identity, not knowledge: stable referents (people, characters,
places, projects) that primitive rows link to. Relationship edges carry
structure (who is connected how); model_entries carry interpretation (what
the relationship/person is like right now). turn_frames records per-turn
speaking stance for resolution scoping.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Entity(SQLModel, table=True):
    __tablename__ = "entities"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    entity_type: str = Field(default="person", nullable=False)
    display_name: str = Field(nullable=False)
    frame_scope: Optional[str] = Field(default=None)
    first_seen_message_id: Optional[str] = Field(default=None)
    confidence: float = Field(default=1.0, nullable=False)
    provisional: bool = Field(default=True, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class EntityAlias(SQLModel, table=True):
    __tablename__ = "entity_aliases"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    entity_id: UUID = Field(index=True, nullable=False)
    alias: str = Field(index=True, nullable=False)
    provenance_message_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class RelationshipEdge(SQLModel, table=True):
    __tablename__ = "relationship_edges"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    from_entity_id: UUID = Field(nullable=False)
    to_entity_id: UUID = Field(nullable=False)
    role: str = Field(nullable=False)
    provenance_message_id: Optional[str] = Field(default=None)
    confidence: float = Field(default=1.0, nullable=False)
    effective_at: Optional[datetime] = Field(default=None)
    end_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class ModelEntry(SQLModel, table=True):
    """A durable User/Character/Relationship Model claim. Interpretive state
    with evidence trail and revision: superseded, never fulfilled/violated."""

    __tablename__ = "model_entries"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    subject_entity_id: Optional[UUID] = Field(default=None, index=True)
    model_kind: str = Field(nullable=False, index=True)
    claim: str = Field(nullable=False)
    evidence_verbatim: str = Field(nullable=False)
    formation: str = Field(default="explicit", nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    effective_at: Optional[datetime] = Field(default=None)
    discovered_at: datetime = Field(default_factory=utc_now, nullable=False)
    superseded_by_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class EntityLink(SQLModel, table=True):
    """One primitive row's reference to an entity in a given role."""

    __tablename__ = "entity_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    object_type: str = Field(nullable=False, index=True)
    object_id: UUID = Field(nullable=False, index=True)
    role: str = Field(nullable=False)
    entity_id: UUID = Field(index=True, nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    provenance_message_id: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class TurnFrame(SQLModel, table=True):
    """Per-turn speaking stance. Lightweight metadata only: in_roleplay,
    creator_direct, or ambiguous. Exists to scope entity resolution and feed
    later scene work — not a scene engine."""

    __tablename__ = "turn_frames"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    frame: str = Field(nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
