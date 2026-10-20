"""Connected understanding: the smallest connective structure over what Cortex already maintains.

Design (see docs/CONNECTED_UNDERSTANDING.md and docs/DECISIONS.md):
- An ENTITY is a durable thing the person's world is about: a person, project, organisation, place, topic, or a
  SITUATION (a developing matter that is not an operational task: a worry, a health observation, an unresolved
  decision, a curiosity). It carries only a compact identity/state summary. It never copies dates, commitments or
  other facts that live elsewhere.
- A LINK connects an entity to another entity or to a record in its authoritative home (ledger item, attention
  intention, notebook page, exploration). The relation is free text ("adviser on", "pilot for"); the BASIS says
  whether the person stated it (with a verified quote) or it is an inference. Views read the target at query time,
  so a changed deadline or a closed obligation is reflected immediately and nothing is stored twice.
- Scoping: every row is keyed by the (product-namespaced) workspace and owner, like the rest of the memory
  pipeline, so product isolation is inherited. These tables replace nothing: the legacy `entities` / `matters`
  tables are workspace-global or fiction-mixed and are deliberately not reused (docs/DECISIONS.md D-W1).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from src.models.world import utc_now


class KnownEntity(SQLModel, table=True):
    __tablename__ = "known_entities"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    kind: str = Field(default="person", index=True, nullable=False)       # person | project | organisation | place | topic | situation | ... (model-chosen, display only)
    name: str = Field(nullable=False)
    name_key: str = Field(default="", index=True, nullable=False)          # normalised, for deterministic matching
    summary: str = Field(default="")                                        # compact identity / current state, <= ~500 chars; never dates or commitments
    status: str = Field(default="active", index=True, nullable=False)      # active | dormant | resolved | merged
    sensitive: bool = Field(default=False)                                  # emotional / health / family: handled with extra care by product policy
    suppressed: bool = Field(default=False)                                 # the person asked not to be prompted about it: never raised unprompted (memory is kept)
    basis: str = Field(default="stated")                                    # stated | inferred: how we know this entity (and its identity) exists
    source_refs_json: str = Field(default="[]")                             # provenance: [{session, quote}], capped
    merged_into_id: Optional[UUID] = Field(default=None, index=True)
    # What KIND OF RECORD this is, structurally (the model sets it; code only uses it to decide how to render and when to surface):
    # "" = a thing (person, project, organisation, place, topic); situation = a developing matter; happening = something that
    # occurred (an incident or experience, interpretation not required); disposition = a like, interest, hope, fear, value;
    # pattern = a provisional, revisable reading across several happenings.
    form: str = Field(default="", index=True)
    tags: str = Field(default="")                                           # comma-separated, lower-case: "relationships/romantic", "culture/literature", "sleep" (soft relevance signals, not boundaries)
    occurred_on: Optional[datetime] = Field(default=None)                   # happenings: the day it happened (person's local date)
    significance: int = Field(default=2)                                    # 1 minor, 2 ordinary, 3 consequential (model-set)
    run_id: Optional[UUID] = Field(default=None, index=True)
    first_seen_at: datetime = Field(default_factory=utc_now, nullable=False)
    last_touched_at: datetime = Field(default_factory=utc_now, nullable=False, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class KnownEntityAlias(SQLModel, table=True):
    __tablename__ = "known_entity_aliases"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    entity_id: UUID = Field(index=True, nullable=False)
    alias: str = Field(nullable=False)
    alias_key: str = Field(index=True, nullable=False)
    basis: str = Field(default="stated")
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class KnownLink(SQLModel, table=True):
    __tablename__ = "known_links"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    from_entity_id: UUID = Field(index=True, nullable=False)
    relation: str = Field(nullable=False)                                   # free text, the nature of the connection ("adviser on", "potential pilot for", "blocks")
    target_kind: str = Field(default="entity", index=True, nullable=False)  # entity | ledger | attention | page | arc | exploration
    target_ref: str = Field(default="", index=True, nullable=False)         # entity id | ledger situation_key | attention action id | page key | ...
    basis: str = Field(default="inferred", nullable=False)                  # stated (needs a verified quote) | inferred
    evidence: str = Field(default="")                                       # the verified quote behind a stated link
    status: str = Field(default="current", index=True, nullable=False)      # current | superseded
    note: str = Field(default="")                                           # why it was superseded / corrected
    superseded_by_id: Optional[UUID] = Field(default=None)
    session_id: str = Field(default="")
    run_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)


class CueExposure(SQLModel, table=True):
    """Exposure management, kept apart from engagement: how often a candidate occupied the foreground (reported by the
    Runtime from what it actually composed) and whether the companion/person engaged with it (recorded when the attention
    review sees it raised or answered). Shown is not raised; raised is not resolved."""
    __tablename__ = "cue_exposure"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    source: str = Field(index=True, nullable=False)                         # entity | ledger
    ref: str = Field(index=True, nullable=False)
    shown_count: int = Field(default=0, nullable=False)
    first_shown_at: Optional[datetime] = Field(default=None)
    last_shown_at: Optional[datetime] = Field(default=None)
    engaged_at: Optional[datetime] = Field(default=None)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
