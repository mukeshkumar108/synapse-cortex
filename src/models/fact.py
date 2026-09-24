"""Durable user/character fact store (Step 3 Slice 2).

Health states, biographical facts, grief history, vocation and other settled
content are evidence and user/character-model material — never expectations.
Before this store, that content either became USER_INTENTION rows (take-2) or
was dropped entirely (take-5). Facts carry holder + provenance + formation so
later dreaming cognition can read and revise them like everything else.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Fact(SQLModel, table=True):
    """A durable, attributed fact about a participant. Holder-scoped
    (user or character peer); never a plan, promise or expectation."""

    __tablename__ = "facts"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    candidate_key: str = Field(default="primary", nullable=False)
    category: str = Field(default="general", nullable=False, index=True)
    title: str = Field(nullable=False)
    evidence_verbatim: str = Field(nullable=False)
    formation: str = Field(default="explicit", nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
