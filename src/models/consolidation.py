from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConsolidationRun(SQLModel, table=True):
    """Durable audit ledger for session-consolidation runs (shadow + apply).

    One row per endpoint/service invocation that reached a model call (or a
    recorded failure). Interpreted-state mutations applied by a run cite
    `consolidation:<session_id>:<run_id_short>` in their evidence fields, so
    any applied change traces back here and can be revisited or corrected.
    Raw evidence remains canonical; this ledger is the revisit index.
    """

    __tablename__ = "consolidation_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    # Stable lane vs temporal boundary: honcho_session_id is ALWAYS the
    # durable lane id (state namespace). The temporal conversation boundary
    # id lives here — provenance only, never state scoping.
    temporal_session_id: str = Field(default="", nullable=False)
    mode: str = Field(default="shadow", nullable=False)  # shadow | apply
    model: str = Field(default="", nullable=False)
    summary: str = Field(default="", nullable=False)
    accepted_count: int = Field(default=0, nullable=False)
    rejected_count: int = Field(default=0, nullable=False)
    applied_count: int = Field(default=0, nullable=False)
    deferred_count: int = Field(default=0, nullable=False)
    error: str = Field(default="", nullable=False)
    prompt_chars: int = Field(default=0, nullable=False)
    latency_s: float = Field(default=0.0, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
