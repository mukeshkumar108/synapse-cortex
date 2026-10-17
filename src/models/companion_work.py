"""A companion's own working space: thoughts, questions, drafts, investigations and
provisional intentions that the COMPANION wrote. Not Cortex interpretation.

Two tables, both scoped by (workspace, owner, companion): the current state of each
item, and an append-only record of every companion act on it (who, when, from which
sitting, what evidence). No taxonomy: `kind` is the companion's own free label."""
from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from src.models.world import utc_now


class CompanionWork(SQLModel, table=True):
    __tablename__ = "companion_work"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    companion_id: str = Field(index=True, nullable=False)
    title: str = Field(nullable=False)
    text: str = Field(default="")                                   # current text, exactly as the companion last wrote it
    kind: str = Field(default="")                                   # the companion's own label, never validated
    status: str = Field(index=True, nullable=False, default="open")  # open | completed | abandoned
    version: int = Field(default=1, nullable=False)
    origin_sitting_id: str = Field(default="")
    origin_surface: str = Field(default="")                         # foreground | independent
    origin_conversation_id: str = Field(default="")
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
    closed_at: Optional[datetime] = Field(default=None)


class CompanionWorkEvent(SQLModel, table=True):
    __tablename__ = "companion_work_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    work_id: UUID = Field(index=True, nullable=False)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    companion_id: str = Field(index=True, nullable=False)
    version: int = Field(nullable=False)                            # item version after this act
    action: str = Field(nullable=False)                             # create | revise | continue | complete | abandon
    author: str = Field(nullable=False)                             # companion:<id>; nothing else writes here
    surface: str = Field(default="")                                # foreground | independent
    sitting_id: str = Field(default="")
    conversation_id: str = Field(default="")
    text: str = Field(default="")                                   # text written by this act (full text for create/revise, the addition for continue)
    note: str = Field(default="")                                   # companion's own reason, if given
    evidence_json: str = Field(default="[]")                        # what the act rests on; captured results are verbatim
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
