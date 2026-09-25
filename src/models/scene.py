"""Authoritative live scene/situation state + epoch log.

CurrentScene is volatile truth ("what is actually true right now"), persisted
until evidence changes it — never a prompt, never choreography. Truth,
steering (overlays), and rendering policy (density) stay separate objects.

Epoch semantics: closing an epoch synchronously writes only the closed/new
epoch identity, a final-scene snapshot reference, and carried-forward matter
IDs. Everything richer (summaries, T2 reinterpretation, consolidation) is
async and must never block the next epoch opening.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# Authority ranks: higher always wins; equal rank → newer wins.
AUTHORITY_RANK = {
    "user_explicit": 3,
    "external_event": 2,
    "entry_context": 2,
    "model_inferred": 1,
    "default": 0,
}


class CurrentScene(SQLModel, table=True):
    """One active row per workspace+session. fields_json maps
    field -> {value, source, authority, confidence, updated_at}."""

    __tablename__ = "current_scenes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    epoch_id: int = Field(default=1, nullable=False, index=True)
    fields_json: str = Field(default="{}", nullable=False)
    carried_matter_ids_json: str = Field(default="[]", nullable=False)

    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class SceneEpoch(SQLModel, table=True):
    """Closed-epoch log: snapshot reference + carried matters. Async
    consolidation reads these; foreground never waits for it."""

    __tablename__ = "scene_epochs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    epoch_id: int = Field(index=True, nullable=False)
    opened_at: datetime = Field(default_factory=utc_now, nullable=False)
    closed_at: Optional[datetime] = Field(default=None)
    close_reason: Optional[str] = Field(default=None)
    final_snapshot_json: str = Field(default="{}", nullable=False)
    carried_matter_ids_json: str = Field(default="[]", nullable=False)

    created_at: datetime = Field(default_factory=utc_now, nullable=False)
