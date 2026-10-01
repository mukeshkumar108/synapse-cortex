"""Derived, reconstructable Cortex state: WorldModel snapshots, knowledge
coverage and session episodes.

None of these is authoritative truth. Snapshots and episode prose can be
deleted and rebuilt from the primitives; coverage rows are derived or are
explicit *gap registrations* that carry no value (an unknown never holds a
guess). See docs/CORTEX_ARCHITECTURE.md §5, §6, §11, §12.
"""
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

COVERAGE_STATUSES = frozenset({"known", "partial", "unknown", "stale", "conflicting"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class WorldModelSnapshot(SQLModel, table=True):
    __tablename__ = "world_model_snapshots"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    version: int = Field(default=1, nullable=False)
    compiled_at: datetime = Field(default_factory=utc_now, nullable=False)
    snapshot_json: str = Field(nullable=False)
    # {section_name: source-fingerprint} so stale sections are patched, not
    # the whole model rebuilt.
    fingerprints_json: str = Field(default="{}", nullable=False)
    superseded_by_id: Optional[UUID] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class KnowledgeCoverage(SQLModel, table=True):
    __tablename__ = "knowledge_coverage"
    __table_args__ = (
        UniqueConstraint("honcho_workspace_id", "owner_peer_id", "subject_key",
                         name="uq_knowledge_coverage_subject"),
        CheckConstraint(
            "status IN ('known','partial','unknown','stale','conflicting')",
            name="ck_knowledge_coverage_status",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    # Generic hierarchical path, e.g. "routines/daily", "routines/weekday_morning".
    subject_key: str = Field(nullable=False, index=True)
    parent_key: Optional[str] = Field(default=None, index=True)
    status: str = Field(nullable=False, index=True)
    # derived | registered (a gap registered by consolidation/other writers)
    source: str = Field(default="derived", nullable=False)
    basis: str = Field(default="", nullable=False)
    evidence_count: int = Field(default=0, nullable=False)
    evidence_refs_json: str = Field(default="[]", nullable=False)
    last_evidence_at: Optional[datetime] = Field(default=None)
    why_useful: str = Field(default="", nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)


class SessionEpisode(SQLModel, table=True):
    """Provenance-linked record of what a consolidation run detected/wrote.

    Holds prose + REFERENCES only. Decisions, repair state, expectations and
    relationship truth live in the canonical primitives/ModelEntries named by
    `writes_json`; the episode never becomes a second store of them.
    """

    __tablename__ = "session_episodes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    # Stable lane id (state namespace); temporal id is provenance only.
    honcho_session_id: str = Field(index=True, nullable=False)
    temporal_session_id: str = Field(default="", nullable=False)
    consolidation_run_id: Optional[UUID] = Field(default=None, index=True)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    summary: str = Field(default="", nullable=False)
    # [{"role": "decision|resolution|correction|repair|system_expectation|...",
    #   "object_type": "...", "object_id": "...", "evidence_refs": [...]}]
    writes_json: str = Field(default="[]", nullable=False)
    detected_json: str = Field(default="[]", nullable=False)
    matters_touched_json: str = Field(default="[]", nullable=False)
    entities_touched_json: str = Field(default="[]", nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
