"""WorldDelta: the typed interchange contract between producers (Runtime checkpoint, Honcho interpretation, narrow lane) and the Cortex
materialiser (docs/WORLD_CONTRACT.md). A delta carries CANDIDATES, not truth: every item cites evidence and states its formation; nothing in
a delta can claim ownership of the world (owner != actor)."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMATIONS = ("explicit", "reported", "source_linked", "observed", "inferred", "hypothesis")
ENTITY_TYPES = ("person", "character", "organisation", "team")
NARRATIVE_KINDS = ("relationship_shift", "trust_change", "disclosure", "concealment", "rupture", "reconciliation",
                   "emotional_state", "ambiguity", "perspective", "self_expression")
MATTER_KINDS_IN = ("project", "topic", "concern", "relationship_situation", "relationship_thread", "goal", "life_situation", "routine", "other")


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Message(_Item):
    id: str
    speaker: str                              # user | assistant (or a peer name)
    text: str


class CoveredThrough(_Item):
    message_id: str
    ordinal: int = 0


class DeltaSource(_Item):
    producer: str                             # runtime-checkpoint | honcho | narrow-lane | ...
    model: str = ""
    version: str = ""
    run_id: Optional[str] = None
    session_id: str
    messages: List[Message] = Field(default_factory=list)      # optional grounding material (verbatim text of the cited messages)
    covered_through: Optional[CoveredThrough] = None
    owner_actor: Optional[str] = None                          # ref of the actor that IS the owner's own character in this world
    speaker_actors: Dict[str, str] = Field(default_factory=dict)   # speaker -> actor ref (deterministic attribution repair)


class ActorC(_Item):
    ref: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    entity_type: Literal["person", "character", "organisation", "team"] = "person"
    relation_hint: Optional[str] = None
    explicit: bool = False
    confidence: float = 0.7
    evidence: List[str] = Field(default_factory=list)


class RelationshipC(_Item):
    ref: str
    actors: List[str]
    type: str
    formation: Literal["explicit", "reported", "source_linked", "observed", "inferred", "hypothesis"] = "inferred"
    confidence: float = 0.7
    evidence: List[str] = Field(default_factory=list)


class WhenC(_Item):
    start: Optional[str] = None
    end: Optional[str] = None
    precision: str = "unknown"
    phrase: Optional[str] = None


class EventC(_Item):
    ref: str
    label: str
    kind: str = "event"
    when: Optional[WhenC] = None
    where: Optional[str] = None
    participants: List[str] = Field(default_factory=list)
    holder: Optional[str] = None
    formation: Literal["explicit", "reported", "source_linked", "observed", "inferred", "hypothesis"] = "reported"
    confidence: float = 0.7
    evidence: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    conflicts_with: List[str] = Field(default_factory=list)


class ClaimC(_Item):
    ref: str
    subject: str                              # ref of an actor, event or relationship
    text: str
    predicate: Optional[str] = None
    holder: Optional[str] = "narrator"        # actor ref, "model" (the system's inference) or "narrator"
    formation: Literal["explicit", "reported", "source_linked", "observed", "inferred", "hypothesis"] = "reported"
    conflicts_with: List[str] = Field(default_factory=list)
    supersedes: List[str] = Field(default_factory=list)
    confidence: float = 0.7
    evidence: List[str] = Field(default_factory=list)
    span: Optional[str] = None                # verbatim span, grounded deterministically when messages are supplied


class NarrativeC(_Item):
    ref: str
    kind: Literal["relationship_shift", "trust_change", "disclosure", "concealment", "rupture", "reconciliation",
                  "emotional_state", "ambiguity", "perspective", "self_expression"]
    about: List[str] = Field(default_factory=list)
    holder: Optional[str] = "model"
    text: str
    formation: Literal["explicit", "reported", "source_linked", "observed", "inferred", "hypothesis"] = "inferred"
    confidence: float = 0.6
    evidence: List[str] = Field(default_factory=list)


class CommitmentC(_Item):
    ref: str
    committer: str
    to: Optional[str] = None
    text: str
    tentative: bool = False
    due: Optional[str] = None
    confidence: float = 0.7
    evidence: List[str] = Field(default_factory=list)


class MatterC(_Item):
    ref: str
    concept: str
    display_title: str
    kind: Literal["project", "topic", "concern", "relationship_situation", "relationship_thread", "goal", "life_situation", "routine", "other"] = "topic"
    actors: List[str] = Field(default_factory=list)
    members: List[str] = Field(default_factory=list)
    attach_to_hint: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)


class WorldDelta(_Item):
    contract_version: Literal["world-delta-v1"] = "world-delta-v1"
    workspace_id: str
    owner: str                                # the Cortex world scope (NOT an actor)
    source: DeltaSource
    actors: List[ActorC] = Field(default_factory=list)
    relationships: List[RelationshipC] = Field(default_factory=list)
    events: List[EventC] = Field(default_factory=list)
    claims: List[ClaimC] = Field(default_factory=list)
    narrative: List[NarrativeC] = Field(default_factory=list)
    commitments: List[CommitmentC] = Field(default_factory=list)
    matter_candidates: List[MatterC] = Field(default_factory=list)

    @model_validator(mode="after")
    def _structure(self) -> "WorldDelta":
        refs: List[str] = []
        for group in (self.actors, self.relationships, self.events, self.claims, self.narrative, self.commitments, self.matter_candidates):
            refs += [item.ref for item in group]
        if len(refs) != len(set(refs)):
            raise ValueError("refs must be unique within a delta")
        known = set(refs)
        actor_refs = {a.ref for a in self.actors}
        for rel in self.relationships:
            if len(rel.actors) != 2 or any(a not in actor_refs for a in rel.actors):
                raise ValueError(f"relationship {rel.ref}: needs exactly two actors declared in this delta")
        for ev in self.events:
            for p in ev.participants:
                if p not in actor_refs:
                    raise ValueError(f"event {ev.ref}: participant {p} is not an actor in this delta")
        for c in self.claims:
            if c.subject not in known:
                raise ValueError(f"claim {c.ref}: unknown subject {c.subject}")
            if c.holder not in (None, "model", "narrator") and c.holder not in actor_refs:
                raise ValueError(f"claim {c.ref}: holder {c.holder} is not an actor in this delta")
        for n in self.narrative:
            if any(a not in known for a in n.about):
                raise ValueError(f"narrative {n.ref}: unknown about-ref")
        for k in self.commitments:
            if k.committer not in actor_refs:
                raise ValueError(f"commitment {k.ref}: committer {k.committer} is not an actor in this delta")
        for item in (*self.actors, *self.relationships, *self.events, *self.claims, *self.narrative, *self.commitments, *self.matter_candidates):
            if not item.evidence:
                raise ValueError(f"{item.ref}: evidence is required (a candidate with no evidence is rejected)")
        for m in self.matter_candidates:
            if any(x not in known for x in (*m.members, *m.actors)):
                raise ValueError(f"matter candidate {m.ref}: unknown member/actor ref")
        return self
