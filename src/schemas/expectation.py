from datetime import datetime
from typing import Literal, Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from src.models.expectation import ExpectationType, OutcomeState


class MaterializedAction(BaseModel):
    action: Literal["created", "updated", "completed", "cancelled"]
    source_system: Literal["app_task", "google_calendar"]
    object_id: str = Field(min_length=1, max_length=256)
    evidence_span: Optional[str] = Field(default=None, max_length=2000)


class TurnEventIngest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    workspace_id: str = Field(..., description="Honcho workspace ID")
    session_id: str = Field(..., description="Honcho session ID")
    honcho_message_id: str = Field(..., description="Canonical Honcho message ID")
    peer_id: str = Field(..., description="Sender peer ID e.g. mukesh")
    text: str = Field(..., description="Raw turn text")
    now: datetime = Field(..., description="Turn timestamp")
    timezone: str = Field(default="UTC", description="User timezone string e.g. Europe/London")
    # Fast→slow reconciliation: canonical actions the app already committed
    # synchronously from this exact turn (real-time interpreter). The watcher
    # deterministically suppresses conversation-derived candidates that would
    # duplicate them, so a canonical object is never shadowed by a second
    # derived representation of the same action.
    materialized_actions: list[MaterializedAction] = Field(default_factory=list, max_length=3)


class MaterializedAction(BaseModel):
    action: Literal["created", "updated", "completed", "cancelled"]
    source_system: Literal["app_task", "google_calendar"]
    object_id: str = Field(min_length=1, max_length=256)
    evidence_span: Optional[str] = Field(default=None, max_length=2000)


class ExpectationResponse(BaseModel):
    id: UUID
    honcho_workspace_id: str
    honcho_session_id: str
    honcho_message_id: str
    subject_peer_id: str
    expectation_type: ExpectationType
    title: str
    summary: str
    raw_temporal_phrase: Optional[str] = None
    expected_window_start: Optional[datetime] = None
    expected_window_end: Optional[datetime] = None
    hard_deadline_at: Optional[datetime] = None
    outcome_state: OutcomeState
    created_at: datetime
