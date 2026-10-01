"""Actor direction: who holds a piece of state and which way it points.

Cortex models a shared world between a human and a system. State must not be
flattened into undirected expectations (docs/CORTEX_ARCHITECTURE.md §2.1):

  user_to_system  a request/expectation the user places on the system
  system_to_user  a commitment/owed follow-up/working prediction the system
                  holds toward the user (system-held, evidence-qualified)
  shared          unresolved human<->system repair, shared work, collaboration
  user_self       the user's own plan/intention (no system party)
  world           third-party / external dependency

Derivation is STRUCTURAL (row type, kind, class, owner, formation) — never
keyword matching on text. `direction_from_row` uses only the row itself (safe
to run at insert time); `effective_direction` additionally uses the scope's
user peer id to recognise system-held rows by ownership. System-held content
stays actor-owned: it is never world truth.
"""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy import event

USER_TO_SYSTEM = "user_to_system"
SYSTEM_TO_USER = "system_to_user"
SHARED = "shared"
USER_SELF = "user_self"
WORLD = "world"
DIRECTIONS = frozenset({USER_TO_SYSTEM, SYSTEM_TO_USER, SHARED, USER_SELF, WORLD})

# Relationship-axis directions (a human<->system party is involved).
RELATIONAL_DIRECTIONS = frozenset({USER_TO_SYSTEM, SYSTEM_TO_USER, SHARED})


def _s(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().lower()


def _is_external(owner: Optional[str]) -> bool:
    return (owner or "").strip().casefold().startswith("external:")


def direction_from_row(row: Any) -> Optional[str]:
    """Row-only derivation. Returns None when the row alone does not decide."""
    explicit = _s(getattr(row, "direction", None))
    if explicit in DIRECTIONS:
        return explicit
    table = getattr(row, "__tablename__", "")
    if table == "expectations":
        etype = _s(getattr(row, "expectation_type", None))
        if etype == "followup_invitation":
            return USER_TO_SYSTEM
        if etype == "external_dependency" or _is_external(getattr(row, "owner_peer_id", None)):
            return WORLD
        return USER_SELF
    if table == "open_loops":
        if getattr(row, "invited", False):
            return USER_TO_SYSTEM
        if _is_external(getattr(row, "owner_peer_id", None)):
            return WORLD
        return USER_SELF
    if table == "commitment_candidates":
        cls = _s(getattr(row, "evidence_class", None))
        if cls == "character_promise":
            return SYSTEM_TO_USER
        if _is_external(getattr(row, "owner_peer_id", None)):
            return WORLD
        return USER_SELF
    if table == "attention_candidates":
        return SYSTEM_TO_USER  # attention candidates are system-held carries
    if table == "work_items":
        return SYSTEM_TO_USER if _s(getattr(row, "owner", None)) in ("sophie", "system") else USER_SELF
    if table == "recurring_intentions":
        return USER_SELF
    if table == "model_entries":
        kind = _s(getattr(row, "model_kind", None))
        if kind == "relationship":
            return SHARED
        return None
    return None


def effective_direction(row: Any, *, user_peer_id: Optional[str] = None) -> Optional[str]:
    """Direction with scope knowledge: a row owned by a non-user, non-external
    peer is system-held. Never reclassifies an explicitly stamped row."""
    stamped = _s(getattr(row, "direction", None))
    if stamped in DIRECTIONS:
        return stamped
    derived = direction_from_row(row)
    owner = getattr(row, "owner_peer_id", None)
    table = getattr(row, "__tablename__", "")
    if (user_peer_id and owner and owner != user_peer_id and not _is_external(owner)
            and table in ("expectations", "open_loops", "commitment_candidates")
            and derived in (USER_SELF, None)):
        return SYSTEM_TO_USER
    return derived


def is_system_held(row: Any, *, user_peer_id: Optional[str] = None) -> bool:
    if _s(getattr(row, "holder_actor", None)) == "system":
        return True
    return effective_direction(row, user_peer_id=user_peer_id) == SYSTEM_TO_USER


def _stamp(_mapper: Any, _connection: Any, row: Any) -> None:
    if not _s(getattr(row, "direction", None)):
        derived = direction_from_row(row)
        if derived:
            row.direction = derived


def register_stamping() -> None:
    """Stamp `direction` on insert for the lifecycle primitives that carry the
    column. One choke point instead of edits in every writer; explicit values
    (e.g. a system-held prediction written by consolidation) always win."""
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.identity import ModelEntry
    from src.models.open_loop import OpenLoop
    for model in (Expectation, OpenLoop, CommitmentCandidate, ModelEntry):
        if not event.contains(model, "before_insert", _stamp):
            event.listen(model, "before_insert", _stamp)
