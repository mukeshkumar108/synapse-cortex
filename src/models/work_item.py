"""Actionable work items — the executable projection of canonical state.

Semantic state (objectives, commitments, expectations, open loops) explains WHY.
Work items explain WHAT HAPPENS NEXT, split by owner:

  owner="user"    things the user needs to do
  owner="sophie"  things Sophie must do / prepare / follow up on

Created only via deterministic validation of agent/llm PROPOSALS (model
proposes, code commits). Always linked to their parent semantic object by
(parent_type, parent_id) + provenance. No claimed execution without a tool
record. This is NOT a duplicate of the app's canonical Tasks: Cortex owns the
semantic->work projection; the app may materialize user-owned tasks into its
own canonical store via commitment-candidate flow.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, SQLModel
from sqlalchemy import SAEnum

import enum


class WorkOwner(str, enum.Enum):
    USER = "user"
    SOPHIE = "sophie"


class WorkStatus(str, enum.Enum):
    PROPOSED = "proposed"
    SURFACED = "surfaced"
    IN_PROGRESS = "in_progress"
    DONE = "done"
    CANCELLED = "cancelled"
    SUPERSEDED = "superseded"


class WorkItem(SQLModel, table=True):
    __tablename__ = "work_items"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    honcho_session_id: Optional[str] = None

    # parent linkage
    parent_type: str = Field(index=True, nullable=False)   # objective|commitment|expectation|open_loop|recurrence|event
    parent_id: str = Field(index=True, nullable=False)
    parent_title: Optional[str] = None

    owner: str = Field(sa_column=Column(SAEnum(WorkOwner, native_enum=False), nullable=False, index=True))
    action: str = Field(nullable=False)                    # the concrete next action
    status: str = Field(
        default=WorkStatus.PROPOSED.value,
        sa_column=Column(SAEnum(WorkStatus, native_enum=False), nullable=False, index=True),
    )

    importance: float = Field(default=0.5)                 # 0..1
    authority: Optional[str] = None                        # act|ask|prepare
    due_window_start: Optional[datetime] = None
    due_window_end: Optional[datetime] = None
    completion_condition: Optional[str] = None             # what "done" means
    blocker: Optional[str] = None                          # dependency/blocker if known
    sophie_executable: bool = Field(default=False)         # can she do it with existing tools?

    # provenance + accounting
    source_agent: str = Field(default="planner")           # planner|pa_task|lane2|app
    evidence_text: Optional[str] = None
    provenance_json: str = Field(default="{}", nullable=False)
    surfaced_count: int = Field(default=0)
    last_surfaced_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    extra_json: str = Field(default="{}", nullable=False)
