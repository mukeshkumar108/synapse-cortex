"""Product policy profiles (Workstream 7).

Cortex stays broadly product-neutral current understanding. This small typed
configuration decides, per product, what matters for foreground attention and
handover: priority ordering of operational kinds and how much of each may
appear in the tiny session handover. Deliberately NOT a generic policy
framework — a small typed config is enough today.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class ProductProfile:
    name: str
    purpose: str
    # Operational-kind priority for foreground editorial selection.
    # Lower = more important. Kinds not listed are treated as background.
    kind_priority: Dict[str, int]
    # Max lines per section in the tiny handover.
    handover_limits: Dict[str, int] = field(default_factory=lambda: {
        "agenda": 4, "patterns": 2, "avoid": 2,
    })
    # Characters the whole handover should stay under (~400 tokens ≈ 1600 chars).
    handover_char_budget: int = 1600

    def priority(self, kind: str) -> int:
        return self.kind_priority.get(kind, 99)


_PROFILES: Dict[str, ProductProfile] = {
    "sophie": ProductProfile(
        name="sophie",
        purpose=(
            "Relationship continuity + meaningful life events + commitments "
            "+ curiosity; broad human weighting."
        ),
        kind_priority={
            "deadline": 0,
            "task": 1,
            "event": 2,
            "state": 3,
            "open_loop": 4,
            "unresolved": 5,
            "backstage_attention": 8,
        },
    ),
    "bluum": ProductProfile(
        name="bluum",
        purpose=(
            "Emotional state + ritual continuity + meaningful disclosures "
            "+ wellbeing signals."
        ),
        kind_priority={
            "state": 0,
            "event": 1,
            "open_loop": 2,
            "task": 4,
            "deadline": 5,
            "unresolved": 3,
            "backstage_attention": 7,
        },
    ),
    "health": ProductProfile(
        name="health",
        purpose="Adherence + symptoms + appointments + escalation signals.",
        kind_priority={
            "task": 0,       # adherence actions
            "deadline": 0,
            "event": 1,      # appointments
            "state": 2,      # symptoms/context
            "unresolved": 4,
            "open_loop": 5,
            "backstage_attention": 9,
        },
    ),
    "productivity": ProductProfile(
        name="productivity",
        purpose="Deadlines + blockers + commitments + prepared work.",
        kind_priority={
            "deadline": 0,
            "task": 1,
            "open_loop": 2,
            "unresolved": 3,
            "event": 4,
            "state": 6,
            "backstage_attention": 9,
        },
    ),
}

DEFAULT_PROFILE = "sophie"


def get_profile(name: Optional[str]) -> ProductProfile:
    return _PROFILES.get((name or DEFAULT_PROFILE).lower(), _PROFILES[DEFAULT_PROFILE])


def profile_names() -> List[str]:
    return sorted(_PROFILES)
