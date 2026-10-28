"""The prepared brief: one cached page per person, day and part of the day (morning, afternoon, evening), built from the dated notes and the ledger.

Prepared ahead and cached, but never trusted past a change: any write to the person's notes or ledger marks their briefs stale in the same transaction
(see services/brief_cache.py), and the next read, or the end of the next consolidation, rebuilds it."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from src.models.world import utc_now


class Brief(SQLModel, table=True):
    __tablename__ = "briefs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    day: str = Field(index=True, nullable=False)                 # the person's local date, YYYY-MM-DD
    part: str = Field(index=True, nullable=False)                # morning | afternoon | evening
    text: str = Field(default="")
    sections_json: str = Field(default="{}")
    version: int = Field(default=1, nullable=False)              # +1 on every rebuild, so a reader can tell whether it already has this one
    dirty: bool = Field(default=False, nullable=False)           # a note or ledger row changed since it was built
    reason: str = Field(default="")                              # why it was last rebuilt: first | changed | expired | forced
    built_at: datetime = Field(default_factory=utc_now, nullable=False)
