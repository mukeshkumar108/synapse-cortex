"""Deterministic object-state ingestion contract.

Canonical task/calendar objects live OUTSIDE Cortex (app Postgres owns tasks;
Google owns Calendar events). Cortex only derives lifecycle state from them via
this bounded, idempotent contract: stable source system + source object
identity + integer version, never embedded duplicate provider objects.

Every action is deterministic — no model calls, no candidate shaping, no
rebuilding of expectation extraction. This is a source-of-truth projection
path for app-owned and provider-owned objects only.
"""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

MAX_REMINDER_WINDOWS = 3
VALID_SOURCE_SYSTEMS = ("app_task", "google_calendar")


class SourceLink(BaseModel):
    system: Literal["app_task", "google_calendar"]
    object_id: str = Field(min_length=1, max_length=256)
    version: int = Field(default=1, ge=1, le=1_000_000)
    kind: Literal["task", "calendar_event"]

    @field_validator("object_id")
    @classmethod
    def _strip_object_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("object_id must not be empty")
        return cleaned


class ReminderWindow(BaseModel):
    """An explicit, user-facing reminder window ("Thursday afternoon",
    "30 minutes before"). Reminder timing is never inferred from a fixed
    approaching-deadline rule."""

    start: datetime
    end: Optional[datetime] = None
    label: Optional[str] = Field(default=None, max_length=120)

    @field_validator("start", "end")
    @classmethod
    def _require_explicit_offset(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("reminder window datetimes must carry an explicit UTC offset")
        return value


class ObjectOrigin(BaseModel):
    """Provenance of a real-time (fast-path) materialization: which user
    message produced this canonical action, so the background watcher can
    canonicalize (supersede) its own conversation-derived duplicate."""

    message_id: str = Field(min_length=1, max_length=256)
    evidence_span: Optional[str] = Field(default=None, max_length=2000)


class AbsorbRef(BaseModel):
    """A derived Cortex lifecycle object this canonical object absorbs.
    Promotion semantics: the expectation/open-loop is superseded or re-pointed
    so exactly one live representation remains."""

    kind: Literal["expectation", "open_loop"]
    id: str = Field(min_length=1, max_length=64)


class ObjectStateIngest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    session_id: str = Field(min_length=1, max_length=128)
    peer_id: Optional[str] = Field(default=None, max_length=64)
    owner_peer_id: Optional[str] = Field(default=None, max_length=64)
    now: datetime
    timezone: str = Field(default="UTC", max_length=64)
    source: SourceLink
    action: Literal["created", "updated", "completed", "cancelled"]
    title: str = Field(min_length=1, max_length=280)
    notes: Optional[str] = Field(default=None, max_length=2000)
    # Task timing (canonical due date for app-owned tasks).
    due_at: Optional[datetime] = None
    # Calendar event timing (canonical start/end for Google events).
    event_start: Optional[datetime] = None
    event_end: Optional[datetime] = None
    # Explicit reminder windows (tasks and events alike). Ordered, bounded.
    reminder_windows: list[ReminderWindow] = Field(default_factory=list, max_length=3)
    # Bounded post-event follow-up window in hours (calendar events only).
    followup_window_hours: Optional[int] = Field(default=None, ge=1, le=72)
    # Real-time provenance: the originating user message (canonicalization).
    origin: Optional[ObjectOrigin] = None
    # Promotion: derived Cortex objects absorbed into this canonical object.
    absorbs: list[AbsorbRef] = Field(default_factory=list, max_length=8)

    @field_validator("now", "due_at", "event_start", "event_end")
    @classmethod
    def _require_explicit_offset(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError("object-state datetimes must carry an explicit UTC offset")
        return value
