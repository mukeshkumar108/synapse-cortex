from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class AttentionCandidateIn(BaseModel):
    key: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_-]+$")
    kind: Literal["pending_question", "unfinished_thought", "callback", "promise", "reentry"]
    content: str = Field(min_length=1, max_length=500)
    salience: float = Field(ge=0.0, le=1.0)
    confidence: float = Field(ge=0.0, le=1.0)
    not_before: Optional[datetime] = None
    expires_at: Optional[datetime] = None


class AttentionCandidatesIngest(BaseModel):
    workspace_id: str
    session_id: str
    source_message_id: str
    source_assistant_message_id: Optional[str] = None
    candidates: list[AttentionCandidateIn] = Field(default_factory=list, max_length=3)
