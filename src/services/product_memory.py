"""Per-product memory configuration.

The person is shared; a product's relationship, perspective and experience are
product-specific. This module holds only the *configuration* that differs by
product: which notebook pages exist, what they cover, the prompts that frame
listening/editing/preparation, and which Cortex capabilities the product uses.
Notebook pages, the continuing arc and the prepared perspective are scoped by
`product`; the operational ledger stays with the person.

Deliberately small and typed. It is configuration, not a framework and not a
taxonomy: a new product supplies a ProductMemory and registers it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional, Tuple


@dataclass(frozen=True)
class ProductMemory:
    name: str                       # also the `product` scope value stored on pages/arc/preparation
    companion_name: str             # how the companion is named in transcripts and prompts
    user_label: str                 # transcript label for the person
    pages: Tuple[str, ...]
    page_titles: Dict[str, str]
    page_scopes: Dict[str, str]
    listening_prompt: str
    handoff_prompt: str
    editor_prompt: str
    arc_prompt: str
    preparation_prompt: str
    arc_seed: str = "No conversations recorded yet."
    page_subjects: Dict[str, str] = field(default_factory=dict)
    independent_listening_prompt: Optional[str] = None   # None: the product has no independent sittings
    independent_rule: str = ""
    ledger_enabled: bool = True     # operational commitments extracted from sessions
    attention_enabled: bool = True  # persisted intentions / follow-through review after consolidation
    preparation_label: str = "PREPARED PERSPECTIVE"
    world_enabled: bool = True      # this product uses the connect pass (entities, situations, links) when the deployment flag is on
    default_time_zone: str = "UTC"  # used only when the caller supplies no timezone

    def seed(self, key: str) -> str:
        return f"# {self.page_titles[key]}\n\nNothing established yet.\n"


_REGISTRY: Dict[str, ProductMemory] = {}


def register(cfg: ProductMemory) -> None:
    _REGISTRY[cfg.name] = cfg


def get(companion_id: Optional[str]) -> ProductMemory:
    """The memory product for a companion. Unknown companions are an error, never
    silently Sophie: a product must not inherit another product's identity."""
    key = str(companion_id or "sophie").strip().lower()
    cfg = _REGISTRY.get(key)
    if cfg is None:
        raise KeyError(f"unknown_memory_product:{key}")
    return cfg


def known() -> Tuple[str, ...]:
    return tuple(sorted(_REGISTRY))
