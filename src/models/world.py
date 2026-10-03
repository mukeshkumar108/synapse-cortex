"""World layer additions (docs/WORLD_CONTRACT.md): the one genuinely new primitive (Event), a generic link table, and producer provenance.

Additive tables only. Actors, relationships, claims and narrative state live in the EXISTING entities / relationship_edges / model_entries.
`producer_runs` + `row_provenance` record which producer/model/run made every materialised row, so a faulty interpretation can be traced
and retracted (the run is the unit of re-derivation)."""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ProducerRun(SQLModel, table=True):
    __tablename__ = "producer_runs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    producer: str = Field(default="unknown", index=True)          # runtime-checkpoint | honcho | narrow-lane | ...
    model: str = Field(default="")
    version: str = Field(default="")
    external_run_id: Optional[str] = Field(default=None, index=True)
    input_json: str = Field(default="{}")                        # session id + message id range
    covered_through_json: str = Field(default="{}")
    counts_json: str = Field(default="{}")
    status: str = Field(default="applied")                       # applied | retracted | rejected
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class RowProvenance(SQLModel, table=True):
    __tablename__ = "row_provenance"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    run_id: UUID = Field(index=True, nullable=False)
    row_type: str = Field(index=True, nullable=False)            # entity | edge | event | model_entry | matter
    row_id: UUID = Field(index=True, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class WorldEvent(SQLModel, table=True):
    """Something that happened. Time/place/participants may be partial. An Event does not need to remain an active Matter."""
    __tablename__ = "world_events"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    canonical_key: str = Field(default="", index=True)
    label: str = Field(nullable=False)
    kind: str = Field(default="event")
    when_start: Optional[datetime] = Field(default=None)
    when_end: Optional[datetime] = Field(default=None)
    when_phrase: Optional[str] = Field(default=None)
    when_precision: str = Field(default="unknown")
    place: Optional[str] = Field(default=None)
    holder_actor: Optional[str] = Field(default=None)
    formation: str = Field(default="reported")
    confidence: float = Field(default=0.7)
    status: str = Field(default="current")                       # current | conflicting | superseded
    superseded_by_id: Optional[UUID] = Field(default=None)
    evidence_refs_json: str = Field(default="[]")
    first_message_id: Optional[str] = Field(default=None)
    run_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class WorldLink(SQLModel, table=True):
    """Generic typed link between world rows (claim -> event, event -> matter, claim conflicts_with claim, narrative -> relationship...)."""
    __tablename__ = "world_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    from_type: str = Field(index=True, nullable=False)
    from_id: UUID = Field(index=True, nullable=False)
    to_type: str = Field(index=True, nullable=False)
    to_id: UUID = Field(index=True, nullable=False)
    role: str = Field(default="about", nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
