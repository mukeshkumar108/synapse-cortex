from datetime import date, datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OperationalStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class OccurrenceStatus(str, Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    PARTIAL = "partial"
    MISSED = "missed"
    UNKNOWN = "unknown"


class RecurrenceSemanticType(str, Enum):
    """What a recurrence fundamentally IS, preserved even when later projected
    into a common actionable Tasks surface. Model may propose; deterministic
    code validates and owns durable state."""

    RECURRING_ACTION = "recurring_action"      # "I want to walk every morning"
    RECURRING_RITUAL = "recurring_ritual"      # "morning and evening prayers every day"
    ADHERENCE_ACTION = "adherence_action"      # take medication / physio exercises
    MEASURABLE_GOAL = "measurable_goal"        # "at least 10k steps per day" (floor, not checkbox)
    OBSERVED_PATTERN = "observed_pattern"      # "we talk everyday obviously" / "I try to walk most mornings"


class RecurringIntention(SQLModel, table=True):
    __tablename__ = "recurring_intentions"
    __table_args__ = (
        UniqueConstraint("honcho_workspace_id", "honcho_session_id", "canonical_key", "active_slot", name="uq_recurring_active_key"),
        UniqueConstraint("honcho_workspace_id", "honcho_message_id", "candidate_key", name="uq_recurring_source_candidate"),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    candidate_key: str = Field(nullable=False)
    canonical_key: str = Field(index=True, nullable=False)
    active_slot: Optional[str] = Field(default="active", index=True)
    title: str = Field(nullable=False)
    cadence: str = Field(nullable=False)
    semantic_type: Optional[str] = Field(default=None, index=True)
    interval_days: Optional[int] = None
    days_of_week_json: str = Field(default="[]", nullable=False)
    timezone: str = Field(default="UTC", nullable=False)
    preferred_window: Optional[str] = None
    target_amount: Optional[float] = None
    target_unit: Optional[str] = None
    status: OperationalStatus = Field(default=OperationalStatus.ACTIVE, sa_column=Column(SAEnum(OperationalStatus, native_enum=False), nullable=False, index=True))
    source_evidence: str = Field(nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    started_at: datetime = Field(default_factory=utc_now, nullable=False)
    paused_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    superseded_by_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class RecurringOccurrence(SQLModel, table=True):
    __tablename__ = "recurring_occurrences"
    __table_args__ = (UniqueConstraint("recurring_intention_id", "user_day", name="uq_recurring_occurrence_day"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    recurring_intention_id: UUID = Field(index=True, nullable=False)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    user_day: date = Field(index=True, nullable=False)
    status: OccurrenceStatus = Field(default=OccurrenceStatus.PENDING, sa_column=Column(SAEnum(OccurrenceStatus, native_enum=False), nullable=False, index=True))
    progress_amount: Optional[float] = None
    progress_unit: Optional[str] = None
    source_message_id: Optional[str] = Field(default=None, index=True)
    evidence: Optional[str] = None
    # Deterministic follow-up accounting: when the handover surfaced this
    # objective to the foreground (an ask opportunity was granted). Code owns
    # this state so asking is a computed duty, never model discretion.
    asked_at: Optional[datetime] = None
    ask_count: int = Field(default=0, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class ObjectiveProgress(SQLModel, table=True):
    __tablename__ = "objective_progress"
    __table_args__ = (UniqueConstraint("honcho_workspace_id", "honcho_message_id", "candidate_key", name="uq_progress_source_candidate"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    candidate_key: str = Field(nullable=False)
    expectation_id: Optional[UUID] = Field(default=None, index=True)
    title: str = Field(nullable=False)
    amount: Optional[float] = None
    unit: Optional[str] = None
    user_day: date = Field(index=True, nullable=False)
    evidence: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class ExtractionTrace(SQLModel, table=True):
    __tablename__ = "extraction_traces"
    __table_args__ = (UniqueConstraint("honcho_workspace_id", "honcho_message_id", "stage", "item_key", name="uq_extraction_trace_stage_item"),)

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    stage: str = Field(index=True, nullable=False)
    item_key: str = Field(nullable=False)
    status: str = Field(index=True, nullable=False)
    detail_json: str = Field(nullable=False)
    model: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
