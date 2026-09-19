"""CurrentMeaning v1 — versioned live interpretation (semantic owner: Cortex).

One writable current interpretation per product scope. Stores ONLY:
  means / unresolved / provenance / version-supersession.
Per-turn foreground authority (active vs backgrounded vs unknown/omitted) is
ephemeral — returned by revise-sync / carried in the packet, never persisted
as a column here. An authority change alone creates zero rows.
"""

from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel
from sqlalchemy import UniqueConstraint, Index, text


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def canonical_owner_peer(owner_peer_id: Optional[str]) -> str:
    """Scope columns are NOT NULL with canonical defaults so the single-active
    invariant is DB-real (no NULL-coexistence loophole)."""
    value = (owner_peer_id or "").strip()
    return value if value else "shared"


def scope_key_for(workspace_id: str, product: str, session_id: str, owner_peer_id: Optional[str]) -> str:
    return "|".join([
        (workspace_id or "").strip(),
        (product or "sophie").strip().lower() or "sophie",
        (session_id or "").strip(),
        canonical_owner_peer(owner_peer_id),
    ])


class CurrentMeaning(SQLModel, table=True):
    __tablename__ = "current_meanings"
    __table_args__ = (
        # Idempotency: one committed revision per key per scope (live
        # `turn:<message_id>`, deep `consolidation:<digest>`). Separate from
        # provenance (source_message_ids, one or many).
        UniqueConstraint("scope_key", "revision_key", name="uq_current_meaning_scope_revision"),
        Index("ix_current_meaning_scope_active", "scope_key", "superseded_by_id"),
        Index("ix_current_meaning_scope_created", "scope_key", "created_at"),
        # Single-active backstop: at most one non-superseded row per scope.
        # (The concurrency algorithm is CAS + idempotency + scope lock; this
        # index is the invariant backstop, not the algorithm.)
        Index(
            "uq_current_meaning_scope_active",
            "scope_key",
            unique=True,
            postgresql_where=text("superseded_by_id IS NULL"),
            sqlite_where=text("superseded_by_id IS NULL"),
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)

    # Scope (all NOT NULL, canonicalised — see helpers above).
    honcho_workspace_id: str = Field(index=True, nullable=False)
    product: str = Field(default="sophie", index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(default="shared", index=True, nullable=False)
    scope_key: str = Field(index=True, nullable=False)

    # Content (v1 only — no lens taxonomy, no character model, no easing).
    means_json: str = Field(nullable=False)
    unresolved_json: str = Field(nullable=False)

    # Provenance (one or many source messages; never the idempotency identity).
    source_message_ids_json: str = Field(nullable=False)
    extractor_version: str = Field(default="fast-meaning-v1", nullable=False, index=True)
    lens_version: str = Field(default="sophie-meaning-v1", nullable=False)
    observed_at: datetime = Field(default_factory=utc_now, nullable=False)

    # Identity for idempotency (NOT provenance).
    revision_key: str = Field(index=True, nullable=False)

    # Revision chain (versioned-append + supersession; mirrors expectations).
    version: int = Field(default=1, nullable=False)
    superseded_by_id: Optional[UUID] = Field(default=None, index=True)

    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
