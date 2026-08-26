from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class OpenLoopStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"
    SUPPRESSED = "suppressed"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"


class OpenLoop(SQLModel, table=True):
    __tablename__ = "open_loops"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_message_id", "candidate_key",
            name="uq_open_loop_workspace_message_candidate",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    # Provenance Links
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    candidate_key: str = Field(default="primary", nullable=False)
    expectation_id: Optional[UUID] = Field(default=None, index=True)
    
    title: str = Field(nullable=False)
    summary: str = Field(nullable=False)
    status: OpenLoopStatus = Field(
        default=OpenLoopStatus.OPEN,
        sa_column=Column(SAEnum(OpenLoopStatus, native_enum=False), nullable=False, index=True),
    )
    resolution_evidence: Optional[str] = Field(default=None)
    expires_at: Optional[datetime] = Field(default=None, index=True)
    
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
