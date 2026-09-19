"""Canonical product-scoped interpretation lenses (Cortex-owned).

Runtime identifies the product (and may state an expected lens version for
observability); Cortex resolves the canonical lens itself. Runtime never
supplies free-form interpretation doctrine.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class MeaningLens:
    product: str
    version: str
    system: str


_SOPHIE_MEANING_V1 = MeaningLens(
    product="sophie",
    version="sophie-meaning-v1",
    system=(
        "You are the live interpreter for a companion's current meaning. "
        "Given the current user turn, the prior current meaning, and bounded "
        "Cortex evidence, output the CURRENT interpretation with replace "
        "semantics: what the past now makes true (means, 1-3 short lines) and "
        "what is still open (unresolved, 0-3 short items). "
        "Rules: output the present interpretation, never an addition to it; "
        "surface demands are evidence of state, not state itself; feeling is "
        "authoritative at any volume while literal enduring intent under high "
        "activation is uncertain; quote evidence_span VERBATIM from the "
        "current turn; if nothing changed, return no_change=true and echo the "
        "prior meaning exactly; never invent persons, motives, commitments, "
        "or coordinates; keep every line under 140 chars. "
        "Also decide foreground authority for THIS turn only: active when the "
        "meaning deserves foreground bandwidth now, backgrounded when it "
        "should be retained but omitted. Authority never creates meaning."
    ),
)

_LENSES = {"sophie": _SOPHIE_MEANING_V1}


def resolve_lens(product: str | None) -> MeaningLens:
    return _LENSES.get((product or "sophie").lower(), _LENSES["sophie"])
