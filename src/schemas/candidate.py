from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


# Fields where omission is valid and an explicit JSON null from an untrusted
# producer (model output, persisted prior shape) semantically means "absent",
# but the trusted internal schema declares a non-null default. Map null -> default
# at the validation boundary so strict internal invariants stay non-null.
_EXPLICIT_NULL_TO_DEFAULT = {
    "days_of_week": [],
    "validation_notes": [],
    "is_negated": False,
    "is_hypothetical": False,
    "is_reported_speech": False,
    "is_quoted": False,
    "is_sarcastic": False,
    "confidence": 1.0,
    "extractor_version": "rules-v2",
}


def _explicit_null_to_default(value: Any, field_name: str) -> Any:
    if value is not None:
        return value
    return _EXPLICIT_NULL_TO_DEFAULT[field_name]


class ExtractionCandidate(BaseModel):
    """
    Typed contract for candidate observations emitted by turn extractors
    before entering expectation shaping, outcome lifecycle, and Cortex context compilation.
    """
    candidate_key: str = Field(..., description="Deterministic hash or key unique to candidate within turn")
    source_start: Optional[int] = Field(default=None, description="Start character index in raw turn text")
    source_end: Optional[int] = Field(default=None, description="End character index in raw turn text")
    observation: str = Field(..., description="Extracted observation text snippet")
    actor_peer_id: Optional[str] = Field(default=None, description="Actor performing or initiating the action")
    subject_peer_id: Optional[str] = Field(default=None, description="Subject peer context e.g. mukesh")
    semantic_type: Optional[str] = Field(default=None, description="Internal semantic hint")
    expectation_type_hint: Optional[str] = Field(default=None, description="Hint for expectation classification")
    temporal_phrase: Optional[str] = Field(default=None, description="Extracted raw temporal phrase e.g. tonight")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Extraction confidence score")
    
    # Semantic Flags
    is_negated: bool = Field(default=False, description="True if statement contains negation e.g. not going to")
    is_hypothetical: bool = Field(default=False, description="True if statement is conditional e.g. if I had time")
    is_reported_speech: bool = Field(default=False, description="True if statement reports third-party speech")
    is_quoted: bool = Field(default=False, description="True if statement is within quotes")
    is_sarcastic: bool = Field(default=False, description="True when obvious sarcasm makes literal intent unsafe")

    # V4 Layer Hints
    open_loop_hint: Optional[str] = Field(default=None, description="Title for open loop if candidate implies unresolved thread")
    suppression_hint: Optional[Dict[str, Any]] = Field(default=None, description="Target, scope, until, and reason for suppression")
    clarification_hint: Optional[Dict[str, Any]] = Field(default=None, description="Clarification candidate payload for low-confidence or ambiguity")
    epistemic_provenance: Optional[str] = Field(default=None, description="Epistemic provenance classification e.g. attributed_belief")
    domain_tag: Optional[str] = Field(default=None, description="Domain tag e.g. work, relationship")
    category_tag: Optional[str] = Field(default=None, description="Category tag e.g. win, struggle, avoid_topic")
    resolution_hint: Optional[Dict[str, Any]] = Field(default=None, description="Resolution or correction target hint for outcome updates")
    epistemic_claim: Optional[Dict[str, Any]] = Field(default=None, description="Structured belief owner, target, claim, and optional nested belief")
    extractor_version: str = Field(default="rules-v2", description="Auditable extractor version")
    operational_kind: Optional[Literal[
        "expectation", "durable_objective", "recurring_intention", "progress",
        "completion", "cancellation", "suppression", "open_loop", "event",
        "semantic_only", "commitment_candidate",
    ]] = None
    # Commitment-candidate vocabulary (Phase 2). Evidence class is a semantic
    # category, not a numeric confidence; authority decides who may act.
    evidence_class: Optional[Literal[
        "explicit_command", "explicit_acceptance", "explicit_resolution",
        "explicit_modification", "implicit_self_commitment",
        "sophie_proposed_user_accepted", "sophie_proposed_soft_acceptance",
        "vague_self_talk",
    ]] = None
    authority: Optional[Literal["act", "ask"]] = None
    canonical_title: Optional[str] = None
    target_key: Optional[str] = None
    cadence: Optional[Literal["daily", "weekly", "interval"]] = None
    interval_days: Optional[int] = Field(default=None, ge=1, le=31)
    days_of_week: List[int] = Field(default_factory=list)
    preferred_window: Optional[str] = None
    target_amount: Optional[float] = None
    target_unit: Optional[str] = None
    progress_amount: Optional[float] = None
    progress_unit: Optional[str] = None
    expiry_phrase: Optional[str] = None
    raw_evidence: Optional[str] = None
    loose_observation_id: Optional[str] = None
    validation_notes: List[str] = Field(default_factory=list)

    @field_validator(*_EXPLICIT_NULL_TO_DEFAULT, mode="before")
    @classmethod
    def _normalize_explicit_null(cls, value: Any, info: Any) -> Any:
        return _explicit_null_to_default(value, info.field_name)


class LooseObservation(BaseModel):
    """Meaning-first proposal. Evidence is traceable but description need not be verbatim."""
    observation_id: str
    description: str = Field(min_length=3, max_length=500)
    evidence_text: str = Field(min_length=1, max_length=2000)
    source_start: Optional[int] = Field(default=None, ge=0)
    source_end: Optional[int] = Field(default=None, ge=0)
    confidence: float = Field(ge=0.0, le=1.0)
    actor_peer_id: Optional[str] = None
    subject_refs: List[str] = Field(default_factory=list, max_length=8)
    temporal_language: Optional[str] = None

    @field_validator("subject_refs", mode="before")
    @classmethod
    def _normalize_subject_refs_null(cls, value: Any) -> Any:
        return [] if value is None else value


class ExtractionResult(BaseModel):
    candidates: List[ExtractionCandidate] = Field(default_factory=list)
    observations: List[LooseObservation] = Field(default_factory=list)
    backend: str
    model: Optional[str] = None
    failure: Optional[str] = None
