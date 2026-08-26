from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExpectationType(str, Enum):
    USER_INTENTION = "user_intention"
    USER_COMMITMENT = "user_commitment"
    EXTERNAL_DEPENDENCY = "external_dependency"
    PLANNED_EVENT = "planned_event"
    EXPECTED_OUTCOME = "expected_outcome"
    FOLLOWUP_INVITATION = "followup_invitation"


class TemporalState(str, Enum):
    NOT_DUE = "not_due"
    WINDOW_OPEN = "window_open"
    WINDOW_ELAPSED = "window_elapsed"
    DEADLINE_APPROACHING = "deadline_approaching"
    DEADLINE_PASSED = "deadline_passed"


class OutcomeState(str, Enum):
    UNKNOWN = "unknown"
    FULFILLED = "fulfilled"
    NOT_FULFILLED = "not_fulfilled"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class Expectation(SQLModel, table=True):
    __tablename__ = "expectations"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_message_id", "candidate_key",
            name="uq_expectation_workspace_message_candidate"
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Provenance Links (Mandatory)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    honcho_document_id: Optional[str] = Field(default=None, index=True)
    candidate_key: str = Field(default="primary", nullable=False)
    source_start: Optional[int] = Field(default=None)
    source_end: Optional[int] = Field(default=None)
    
    # Versioning & Supersession Policy
    version: int = Field(default=1, nullable=False)
    extractor_version: str = Field(default="rules-v1", nullable=False, index=True)
    superseded_by_id: Optional[UUID] = Field(default=None, index=True)
    
    # Metadata & Category
    subject_peer_id: str = Field(index=True, nullable=False)
    expectation_type: ExpectationType = Field(
        default=ExpectationType.USER_INTENTION,
        sa_column=Column(SAEnum(ExpectationType, native_enum=False), nullable=False),
    )
    title: str = Field(nullable=False)
    summary: str = Field(nullable=False)
    
    # Conservative Temporal Grounding
    raw_temporal_phrase: Optional[str] = Field(default=None)
    anchor_timezone: str = Field(default="UTC", nullable=False)
    
    expected_window_start: Optional[datetime] = Field(default=None, index=True)
    expected_window_end: Optional[datetime] = Field(default=None, index=True)
    hard_deadline_at: Optional[datetime] = Field(default=None, index=True)
    
    # Explicit Outcome State
    outcome_state: OutcomeState = Field(
        default=OutcomeState.UNKNOWN,
        sa_column=Column(SAEnum(OutcomeState, native_enum=False), nullable=False, index=True),
    )
    resolution_evidence: Optional[str] = Field(default=None)
    
    # Confidence & Audit Metadata
    extraction_confidence: float = Field(default=1.0, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
