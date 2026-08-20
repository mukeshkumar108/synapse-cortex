from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


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
