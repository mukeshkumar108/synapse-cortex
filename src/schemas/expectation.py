from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field
from src.models.expectation import ExpectationType, OutcomeState


class TurnEventIngest(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=True)
    workspace_id: str = Field(..., description="Honcho workspace ID")
    session_id: str = Field(..., description="Honcho session ID")
    honcho_message_id: str = Field(..., description="Canonical Honcho message ID")
    peer_id: str = Field(..., description="Sender peer ID e.g. mukesh")
    text: str = Field(..., description="Raw turn text")
    now: datetime = Field(..., description="Turn timestamp")
    timezone: str = Field(default="UTC", description="User timezone string e.g. Europe/London")


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
