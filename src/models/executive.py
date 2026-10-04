"""Executive layer storage: when a world should be reconsidered, and the per-world product policy that enables/limits it."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ExecutiveWake(SQLModel, table=True):
    """A reason to reconsider a world at a time. Cheap to scan; the model is only invoked for worlds with a due, unconsumed wake."""
    __tablename__ = "executive_wakes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    due_at: datetime = Field(index=True, nullable=False)
    reason: str = Field(default="")
    attempts: int = Field(default=0)
    detail_json: Optional[str] = Field(default=None)       # an external event's content (calendar change, tool result, product signal), shown to the executive
    consumed_at: Optional[datetime] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class WorldPolicy(SQLModel, table=True):
    """Product-supplied policy for one world: whether the executive runs, and the limits on proactive delivery. Not meaning, only product config."""
    __tablename__ = "world_policies"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    policy_json: str = Field(default="{}", nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
