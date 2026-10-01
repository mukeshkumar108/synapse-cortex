"""Product policy profiles (Workstream 7).

Cortex stays broadly product-neutral current understanding. This small typed
configuration is the product POLICY layer: how a product weights Cortex's
product-neutral state (operational kind priority, generic Matter kinds,
Matter salience components). It never changes stored truth and never adds
product-specific Matter kinds or ontology to Cortex. Deliberately NOT a
generic policy framework — a small typed config is enough today.
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
    # Multipliers over GENERIC Matter kinds (project|topic|concern|
    # relationship_situation|goal|life_situation|routine|other). Missing = 1.0.
    matter_kind_weights: Dict[str, float] = field(default_factory=dict)
    # Weights over the inspectable Matter salience components
    # (recency, frequency, explicit_importance, temporal_pressure,
    # unresolvedness, repeated_user_initiation, recent_activity). Missing = 1.0.
    matter_weights: Dict[str, float] = field(default_factory=dict)

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
        matter_kind_weights={"relationship_situation": 1.25, "concern": 1.15, "life_situation": 1.15},
        matter_weights={"repeated_user_initiation": 1.5, "temporal_pressure": 1.25},
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
        matter_kind_weights={"concern": 1.4, "routine": 1.25, "relationship_situation": 1.25},
        matter_weights={"recency": 1.25, "recent_activity": 1.25},
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
        matter_kind_weights={"routine": 1.4, "goal": 1.2},
        matter_weights={"temporal_pressure": 1.5, "unresolvedness": 1.25},
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
        matter_kind_weights={"project": 1.4, "goal": 1.25},
        matter_weights={"temporal_pressure": 1.5, "explicit_importance": 1.25},
    ),
}

DEFAULT_PROFILE = "sophie"


def get_profile(name: Optional[str]) -> ProductProfile:
    return _PROFILES.get((name or DEFAULT_PROFILE).lower(), _PROFILES[DEFAULT_PROFILE])


def profile_names() -> List[str]:
    return sorted(_PROFILES)
