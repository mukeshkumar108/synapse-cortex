"""Shadow-A proposal schema — in-memory only, never persisted to prod tables.

Covers build items 1-9:
 1. semantic claim proposals
 2. reified relation proposals (bounded vocab, own provenance)
 3. state roles (0..n, time-varying)
 4. directed obligation frame
 5. shadow T2/context proposal (not written to current_meanings)
 6. derived read views
 7. CandidateMove
 8. system-attention-before-user-attention record
 9. telemetry per matter
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

# Build item 2 — bounded initial relation vocabulary (closed set for Phase A).
RELATION_VOCAB = (
    "same_as",
    "refines",
    "contradicts",
    "supersedes",
    "depends_on",
    "part_of",
    "conditioned_on",
    "fulfils",
    "partially_fulfils",
    "resolves",
    "reopens",
    "enables",
    "blocks",
)

# Build item 3 — state roles are labels, never a partition.
ROLE_VOCAB = ("assertional", "obligation", "unresolved", "predictive", "attentional")

# Build item 7 — CandidateMove kinds + lifecycle (shadow tracks to eligible;
# surfaced/satisfied etc. would belong to a foreground scheduler, out of scope).
MOVE_KINDS = ("QUESTION", "FOLLOW_UP", "WATCH", "REMIND", "ACT", "PROPOSE", "DIGEST")
MOVE_LIFECYCLE = (
    "created",
    "held",
    "eligible",
    "surfaced",
    "satisfied",
    "deferred",
    "suppressed",
    "expired",
)

# Build item 9 — telemetry per evaluated matter (closed set).
TELEMETRY = (
    "NO_MOVE_WARRANTED",
    "MOVE_HELD",
    "MOVE_ELIGIBLE",
    "UNRESOLVED_SEMANTICS",
    "UNREPRESENTED_SCHEMA_GAP",
)


@dataclass(frozen=True)
class ShadowClaim:
    """Build item 1 — one permissive semantic proposal."""

    claim_id: str  # stable shadow id: sha1(case:idx:normalized)[:12]
    content: str
    subjects: List[str] = field(default_factory=list)
    evidence_refs: List[str] = field(default_factory=list)
    modality: str = "stated"  # stated | intended | promised | conditional | reported | inferred
    condition: Optional[str] = None  # e.g. "if client approves", "after bank releases"
    formation: str = "explicit"  # explicit | inferred
    confidence: float = 0.7
    effective_at: Optional[str] = None
    discovered_at: Optional[str] = None


@dataclass(frozen=True)
class ShadowRelation:
    """Build item 2 — reified relation with its own provenance."""

    relation_id: str
    rel_type: str  # must be in RELATION_VOCAB
    from_id: str  # claim_id
    to_id: str  # claim_id
    evidence_refs: List[str] = field(default_factory=list)
    formation: str = "explicit"  # explicit | inferred
    confidence: float = 0.7
    effective_at: Optional[str] = None
    discovered_at: Optional[str] = None
    status: str = "active"  # active | superseded | retracted


@dataclass(frozen=True)
class ObligationFrame:
    """Build item 4 — directed obligation. obligor != self-accounting by default."""

    frame_id: str
    claim_id: str
    obligor: str  # who owes: ashley/carlos/studio_sam/cousin_sam/user/sophie/...
    beneficiary: Optional[str] = None  # who is owed
    action: str = ""
    condition: Optional[str] = None
    due: Optional[str] = None
    authority: str = "reported_statement"  # explicit_command | reported_statement | inference | ...
    strength: str = "normal"  # weak | normal | strong
    modality: str = "stated"  # promised | intended | conditional | ...


@dataclass(frozen=True)
class T2Proposal:
    """Build item 5 — shadow context proposal. Never persisted.

    context_labels are inferred from evidence counts/affect language, never
    hardcoded per case (amendment 4). context_weight dampens routine nudges
    when load/distress signals dominate.
    """

    means: List[str] = field(default_factory=list)
    unresolved: List[str] = field(default_factory=list)
    trajectory: str = "steady"  # easing | steady | intensifying | unclear
    easing: List[str] = field(default_factory=list)
    tensions: List[str] = field(default_factory=list)
    context_labels: List[str] = field(default_factory=list)
    context_weight: float = 0.0  # 0..1 attenuation of routine moves
    evidence_refs: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class ReadViews:
    """Build item 6 — derived read views (pure projections of claims+roles)."""

    todo: List[str] = field(default_factory=list)
    reminder: List[str] = field(default_factory=list)
    open_matter: List[str] = field(default_factory=list)
    worry: List[str] = field(default_factory=list)
    follow_up: List[str] = field(default_factory=list)
    companion_obligation: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CandidateMove:
    """Build item 7 — proposed control object with matter link."""

    move_id: str
    kind: str  # MOVE_KINDS
    reason: str  # CLARIFY | RESOLVE_CONFLICT | CHECK_BACK | DUE | FULFIL_OWN_PROMISE | CURIOSITY | OPPORTUNITY | MONITOR | ...
    matter_id: str  # underlying claim_id (expiry/ineligibility never resolves matter)
    source_refs: List[str] = field(default_factory=list)
    support_strength: float = 0.5
    salience: float = 0.5
    eligibility: str = "eligible"  # eligible | held:* | ineligible:*
    validity_window: Optional[str] = None
    lifecycle: str = "created"  # MOVE_LIFECYCLE
    owner: str = "sophie"  # derivation owner, distinct from obligor
    user_facing: bool = False


@dataclass(frozen=True)
class ResolutionAttempt:
    """Build item 8 — one internal-resolution attempt before user attention."""

    matter_id: str
    strategy: str  # search_state | search_honcho | reconcile_sources | wait_window | verify_feed | ...
    sources_checked: List[str] = field(default_factory=list)
    outcome: str = "unresolved"  # resolved | partial | unresolved
    detail: str = ""


@dataclass(frozen=True)
class MatterAssessment:
    """Build item 9 — per-matter telemetry + linked artefacts."""

    matter_id: str
    roles: List[str] = field(default_factory=list)
    telemetry: str = "NO_MOVE_WARRANTED"
    moves: List[CandidateMove] = field(default_factory=list)
    resolution_attempts: List[ResolutionAttempt] = field(default_factory=list)
    note: str = ""


@dataclass(frozen=True)
class Observability:
    """Amendment 1 — a source/window capable of observing the expected event."""

    source: str  # e.g. bank_feed, inbox, calendar
    window: str = ""
    observed: bool = False  # True only if source actually covered the window
    last_observed_at: Optional[str] = None


@dataclass
class ShadowResult:
    case_id: str
    claims: List[ShadowClaim] = field(default_factory=list)
    relations: List[ShadowRelation] = field(default_factory=list)
    roles: Dict[str, List[str]] = field(default_factory=dict)  # claim_id -> roles
    obligations: List[ObligationFrame] = field(default_factory=list)
    t2: Optional[T2Proposal] = None
    views: Optional[ReadViews] = None
    moves: List[CandidateMove] = field(default_factory=list)
    assessments: List[MatterAssessment] = field(default_factory=list)
    expected_but_missing: List[Dict[str, Any]] = field(default_factory=list)
    unknowns: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        from dataclasses import asdict

        return asdict(self)
