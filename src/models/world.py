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


class WorldObjective(SQLModel, table=True):
    """What an actor is trying to achieve. Actor-owned, directional (`toward`), many per actor and allowed to conflict (that tension is the drama).
    scope: constitutional (product-authored, never superseded by an extractor) | enduring | active | immediate. Trajectory `state` is judged
    PER objective; any character-level summary is derived."""
    __tablename__ = "world_objectives"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    actor_entity_id: UUID = Field(index=True, nullable=False)
    toward_entity_id: Optional[UUID] = Field(default=None)
    canonical_key: str = Field(default="", index=True)
    text: str = Field(nullable=False)
    scope: str = Field(default="active", index=True)
    strength: float = Field(default=0.6)
    cause: Optional[str] = Field(default=None)
    state: str = Field(default="unknown")                        # on_track | drifting | at_risk | failing | resolved | unknown
    durability: str = Field(default="unknown")                   # acute | provisional | durable | unknown (the interpreter's judgement)
    conflicts_json: str = Field(default="[]")                    # objective ids, or the literal "constitution"
    formation: str = Field(default="inferred")
    confidence: float = Field(default=0.6)
    status: str = Field(default="current")                       # current | resolved | superseded
    evidence_refs_json: str = Field(default="[]")
    run_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class RelationshipDimension(SQLModel, table=True):
    """One directional facet of a shared relationship (Audrey->Kai trust, Kai->Audrey awareness of event E). The relationship edge stays one
    canonical identity; perspective lives here, never flattened into a single relationship state."""
    __tablename__ = "relationship_dimensions"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    edge_id: UUID = Field(index=True, nullable=False)
    from_entity_id: UUID = Field(nullable=False)
    to_entity_id: UUID = Field(nullable=False)
    dimension: str = Field(index=True, nullable=False)
    value: str = Field(nullable=False)
    durability: str = Field(default="unknown")                   # acute | provisional | durable | unknown (the interpreter's judgement)
    about_event_id: Optional[UUID] = Field(default=None)
    formation: str = Field(default="inferred")
    confidence: float = Field(default=0.6)
    superseded_by_id: Optional[UUID] = Field(default=None)
    evidence_refs_json: str = Field(default="[]")
    run_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class TrajectoryNote(SQLModel, table=True):
    """Reconciler output: an INTERPRETATION (never a fact, never a script) of how a character's current behaviour relates to its constitutional
    objective, plus a plausible way back. Labelled, evidence-linked, expiring."""
    __tablename__ = "trajectory_notes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    actor_entity_id: UUID = Field(index=True, nullable=False)
    objective_id: Optional[UUID] = Field(default=None)
    state: str = Field(default="at_risk")
    note: str = Field(nullable=False)
    basis_json: str = Field(default="{}")                        # objective / entry / dimension ids the note was derived from
    producer: str = Field(default="trajectory-reconciler")
    run_id: Optional[UUID] = Field(default=None, index=True)
    superseded_by_id: Optional[UUID] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    expires_at: Optional[datetime] = Field(default=None)


class ContinuationBrief(SQLModel, table=True):
    """The interpreter's compact rendering of the current situation for the foreground. Versioned; a PROJECTION of structured state (lines cite
    the rows they derive from), never a source of truth."""
    __tablename__ = "continuation_briefs"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    text: str = Field(nullable=False)
    lines_json: str = Field(default="[]")
    producer: str = Field(default="interpreter")
    run_id: Optional[UUID] = Field(default=None, index=True)
    superseded_by_id: Optional[UUID] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
