"""WorldDelta: the typed interchange contract between producers (Runtime checkpoint, Honcho interpretation, narrow lane) and the Cortex
materialiser (docs/WORLD_CONTRACT.md). A delta carries CANDIDATES, not truth: every item cites evidence and states its formation; nothing in
a delta can claim ownership of the world (owner != actor)."""
from __future__ import annotations

from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

FORMATIONS = ("explicit", "reported", "source_linked", "observed", "inferred", "hypothesis")
ENTITY_TYPES = ("person", "character", "organisation", "team")
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
    policy: Literal["grounded", "generative"] = "generative"        # product epistemics: grounded = facts the companion merely asserts are not world truth
    owner_actor: Optional[str] = None                          # ref of the actor that IS the owner's own character in this world
    speaker_actors: Dict[str, str] = Field(default_factory=dict)   # speaker -> actor ref (deterministic attribution repair)


class ActorC(_Item):
    ref: str
    name: str
    aliases: List[str] = Field(default_factory=list)
    entity_type: Literal["person", "character", "organisation", "team"] = "person"
    relation_hint: Optional[str] = None
    existing_id: Optional[str] = None          # the interpreter recognised a known actor (id from the world state it was shown)
    explicit: bool = False
    confidence: float = 0.7
    evidence: List[str] = Field(default_factory=list)


class RelationshipC(_Item):
    ref: str
    actors: List[str]
    type: str                                 # open vocabulary
    directional: bool = False                 # the interpreter decides whether A->B differs from B->A for this kind of relationship
    existing_id: Optional[str] = None
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
    same_as: Optional[str] = None             # the interpreter judged this the SAME occurrence as a known event (id or ref): merge
    possibly_same_as: Optional[str] = None    # ...or possibly the same: keep both, link, never merge destructively


class ClaimC(_Item):
    ref: str
    subject: str                              # ref of an actor, event or relationship
    text: str
    kind: str = "assertion"                   # assertion (about an occurrence/relationship) | attribute (a stable property of an actor)
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
    kind: str                                 # open vocabulary (rupture, concealment, resentment, ...); `self_expression` marks rhetoric/performance
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
    continuity_required: bool = False         # the interpreter's judgement: does FUTURE behaviour depend on this unresolved state?
    continuity_reason: Optional[str] = None
    attach_to_existing_matter_id: Optional[str] = None
    evidence: List[str] = Field(default_factory=list)


OBJECTIVE_STATES = ("on_track", "drifting", "at_risk", "failing", "resolved", "unknown")


class ObjectiveC(_Item):
    ref: str
    op: Literal["create", "update", "resolve"] = "create"
    existing_id: Optional[str] = None         # update/resolve target: a known objective id from the world state the interpreter was shown
    actor: str                                # whose objective it is (actor ref)
    text: str
    scope: Literal["enduring", "active", "immediate"] = "active"
    toward: Optional[str] = None              # actor ref the objective is directed at
    strength: float = 0.6
    cause: Optional[str] = None               # why the actor wants it (hurt, fear, shame, desire...)
    state: Literal["on_track", "drifting", "at_risk", "failing", "resolved", "unknown"] = "unknown"
    conflicts_with: Optional[List[str]] = None                    # other objective refs/ids, or "constitution"; None = leave the recorded conflicts unchanged
    durability: Literal["acute", "provisional", "durable", "unknown"] = "unknown"   # the interpreter's judgement: a moment, unconfirmed, or sustained
    formation: Literal["explicit", "reported", "source_linked", "observed", "inferred", "hypothesis"] = "inferred"
    confidence: float = 0.6
    evidence: List[str] = Field(default_factory=list)


class DimensionC(_Item):
    ref: str
    relationship: str                         # relationship ref (the shared identity this facet hangs under)
    from_actor: str
    to_actor: str
    dimension: str                            # open vocabulary: affection, trust, resentment, dependency, respect, awareness-of-X ...
    value: str
    about: Optional[str] = None               # event ref (awareness_of / disclosure_of)
    durability: Literal["acute", "provisional", "durable", "unknown"] = "unknown"
    supersedes: Optional[str] = None          # id of a known facet this one REPLACES (the interpreter's judgement that the state changed)
    formation: Literal["explicit", "reported", "source_linked", "observed", "inferred", "hypothesis"] = "inferred"
    confidence: float = 0.6
    evidence: List[str] = Field(default_factory=list)


class TrajectoryC(_Item):
    """The interpreter's assessment of how one actor's current behaviour relates to its long-term orientation, with a plausible way the situation
    could move. An INTERPRETATION: expiring, evidence-linked, never a fact and never a script."""
    ref: str
    actor: str
    state: Literal["on_track", "drifting", "at_risk", "failing", "unknown"] = "unknown"
    note: str
    objectives: List[str] = Field(default_factory=list)       # objective refs/ids the assessment concerns
    evidence: List[str] = Field(default_factory=list)


class BriefLineC(_Item):
    text: str
    refs: List[str] = Field(default_factory=list)             # delta refs or known ids the line derives from


class BriefC(_Item):
    """The interpreter's compact, neutral rendering of the current situation for the foreground. A projection of the structured state, stored
    versioned; it carries no independent truth."""
    text: str
    lines: List[BriefLineC] = Field(default_factory=list)


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
    objectives: List[ObjectiveC] = Field(default_factory=list)
    dimensions: List[DimensionC] = Field(default_factory=list)
    trajectory: List[TrajectoryC] = Field(default_factory=list)
    brief: Optional[BriefC] = None

    @model_validator(mode="after")
    def _structure(self) -> "WorldDelta":
        refs: List[str] = []
        for group in (self.actors, self.relationships, self.events, self.claims, self.narrative, self.commitments, self.matter_candidates, self.objectives, self.dimensions, self.trajectory):
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
        for item in (*self.actors, *self.relationships, *self.events, *self.claims, *self.narrative, *self.commitments, *self.matter_candidates, *self.objectives, *self.dimensions, *self.trajectory):
            if not item.evidence:
                raise ValueError(f"{item.ref}: evidence is required (a candidate with no evidence is rejected)")
        objective_refs = {o.ref for o in self.objectives}
        for o in self.objectives:
            if o.actor not in actor_refs or (o.toward and o.toward not in actor_refs):
                raise ValueError(f"objective {o.ref}: actor/toward must be actors in this delta")
            if o.op == "create" and o.existing_id:
                raise ValueError(f"objective {o.ref}: create cannot name an existing id")
        relationship_refs = {r.ref for r in self.relationships}
        for d in self.dimensions:
            if d.relationship not in relationship_refs or d.from_actor not in actor_refs or d.to_actor not in actor_refs:
                raise ValueError(f"dimension {d.ref}: relationship/actors must be declared in this delta")
            if d.about and d.about not in known:
                raise ValueError(f"dimension {d.ref}: unknown about-ref")
        for t in self.trajectory:
            if t.actor not in actor_refs:
                raise ValueError(f"trajectory {t.ref}: actor must be an actor in this delta")
        for m in self.matter_candidates:
            if any(x not in known for x in (*m.members, *m.actors)):
                raise ValueError(f"matter candidate {m.ref}: unknown member/actor ref")
        return self
