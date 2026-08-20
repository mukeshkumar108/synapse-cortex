from typing import List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class FollowupItem(BaseModel):
    id: UUID
    title: str
    expected_window_label: Optional[str] = None
    temporal_state: str  # e.g. "window_elapsed"
    outcome_state: str   # e.g. "unknown"
    followup_eligible: bool
    reason: str          # e.g. "expected_window_elapsed"
    honcho_message_id: str


class FollowupPacketResponse(BaseModel):
    followups: List[FollowupItem] = Field(default_factory=list)
