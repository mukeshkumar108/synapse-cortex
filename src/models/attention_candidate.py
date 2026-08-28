from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AttentionCandidateKind(str, Enum):
    PENDING_QUESTION = "pending_question"
    UNFINISHED_THOUGHT = "unfinished_thought"
    CALLBACK = "callback"
    PROMISE = "promise"
    REENTRY = "reentry"


class AttentionCandidateStatus(str, Enum):
    ACTIVE = "active"
    SURFACED = "surfaced"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class AttentionCandidate(SQLModel, table=True):
    """A grounded thing Sophie may still carry, never prewritten dialogue."""

    __tablename__ = "attention_candidates"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "source_message_id", "candidate_key",
            name="uq_attention_candidate_workspace_source_key",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    source_message_id: str = Field(index=True, nullable=False)
    source_assistant_message_id: Optional[str] = Field(default=None, index=True)
    candidate_key: str = Field(nullable=False)
    # Stable source-link contract for deterministically derived attention
    # (e.g. bounded post-event follow-up opportunities from Google Calendar).
    source_system: Optional[str] = Field(default=None, index=True)
    source_object_id: Optional[str] = Field(default=None, index=True)
    kind: AttentionCandidateKind = Field(
        sa_column=Column(SAEnum(AttentionCandidateKind, native_enum=False), nullable=False, index=True)
    )
    content: str = Field(nullable=False)
    salience: float = Field(default=0.5, ge=0.0, le=1.0)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    status: AttentionCandidateStatus = Field(
        default=AttentionCandidateStatus.ACTIVE,
        sa_column=Column(SAEnum(AttentionCandidateStatus, native_enum=False), nullable=False, index=True),
    )
    not_before: Optional[datetime] = Field(default=None, index=True)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    surfaced_count: int = Field(default=0, nullable=False)
    last_surfaced_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
