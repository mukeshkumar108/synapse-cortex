"""Data models for the JIT longitudinal read path.

Reads are ephemeral by construction: RecruitedRead carries no persistence
method, no durability flag, and no promotion path. Anything that needs to
survive must go through Track P rules elsewhere; this module offers no such
door.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class ReadRequest:
    """Bounded question pulled by a specific current need."""

    question: str
    scope: str  # e.g. "matter:lucy_camera_payment" — never "the user"
    temporal_cutoff: str  # ISO timestamp; evidence after this is EXCLUDED structurally
    matter_refs: List[str] = field(default_factory=list)
    need: str = ""  # the live candidate/arbitration need pulling this question
    evidence_limit: int = 8


@dataclass(frozen=True)
class EvidenceItem:
    """One retrieved evidence fragment. Messages only — never stored conclusions."""

    event_id: str
    timestamp: str  # ISO
    sender: str
    role: str  # user | external | assistant
    source_type: str  # conversation | email | payment_feed | calendar | sms | message
    content: str
    provenance: str  # e.g. fixture:s1:s1_e03 | honcho:<workspace>:<session>:<id>
    matter_tags: List[str] = field(default_factory=list)
    entity_tags: List[str] = field(default_factory=list)


@dataclass(frozen=True)
class CortexJoin:
    """Authoritative Cortex-side state joined BEFORE synthesis (override channel)."""

    matter: str
    kind: str  # correction | lifecycle | closure | boundary | receipt | supersession
    statement: str
    source_event_id: str
    timestamp: str


@dataclass
class RecruitedRead:
    """The required recruited-read shape (§Mission: 11 fields). Ephemeral."""

    question_id: str
    verdict: str  # short machine-checkable verdict, e.g. "NO", "Q2100-OPEN", "ABSTAIN"
    current_reading: str
    supporting_evidence: List[str] = field(default_factory=list)
    counterexamples: List[str] = field(default_factory=list)
    corrections_applied: List[str] = field(default_factory=list)
    independence_accounting: str = ""
    scope_frame: str = ""
    observation_vs_interpretation: str = ""
    uncertainty: str = ""
    abstained: bool = False
    what_would_change: str = ""
    temporal_cutoff: str = ""
    excluded_after_cutoff: List[str] = field(default_factory=list)
    retrieval_backend: str = ""
    stored_conclusions_used: bool = False  # must ALWAYS be False; asserted in tests
    extra: Dict[str, Any] = field(default_factory=dict)

    def compact(self) -> str:
        """Compact rendering: what Runtime would receive without full corpus."""
        lines = [
            f"[{self.question_id}] {self.current_reading}",
            f"cutoff: {self.temporal_cutoff} | scope: {self.scope_frame}",
            f"support: {'; '.join(self.supporting_evidence) or '—'}",
            f"counter: {'; '.join(self.counterexamples) or '—'}",
        ]
        if self.corrections_applied:
            lines.append(f"corrections: {'; '.join(self.corrections_applied)}")
        if self.independence_accounting:
            lines.append(f"independence: {self.independence_accounting}")
        if self.abstained:
            lines.append("ABSTAIN")
        if self.uncertainty:
            lines.append(f"uncertainty: {self.uncertainty}")
        lines.append(f"would-change: {self.what_would_change}")
        return "\n".join(lines)
