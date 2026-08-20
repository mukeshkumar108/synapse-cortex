from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ClarificationType(str, Enum):
    LOW_CONFIDENCE = "low_confidence"
    AMBIGUOUS_ACTOR = "ambiguous_actor"
    AMBIGUOUS_TEMPORAL = "ambiguous_temporal"
    CONTRADICTION = "contradiction"
    UNCLEAR_TARGET = "unclear_target"


class ClarificationStatus(str, Enum):
    PENDING = "pending"
    RESOLVED = "resolved"
    DISMISSED = "dismissed"
    SUPERSEDED = "superseded"


class ClarificationCandidate(SQLModel, table=True):
    __tablename__ = "clarification_candidates"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_message_id", "candidate_key",
            "clarification_type", name="uq_clarification_event_candidate_type",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    candidate_key: str = Field(default="primary", nullable=False)
    
    clarification_type: ClarificationType = Field(
        default=ClarificationType.LOW_CONFIDENCE,
        sa_column=Column(SAEnum(ClarificationType, native_enum=False), nullable=False),
    )
    description: str = Field(nullable=False)
    candidates_json: Optional[str] = Field(default=None)
    status: ClarificationStatus = Field(
        default=ClarificationStatus.PENDING,
        sa_column=Column(SAEnum(ClarificationStatus, native_enum=False), nullable=False, index=True),
    )
    
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
