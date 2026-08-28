from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import ClassVar, Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class CommitmentCandidateStatus(str, Enum):
    PENDING = "pending"
    MATERIALIZED = "materialized"
    DISMISSED = "dismissed"
    EXPIRED = "expired"


class CommitmentCandidateAuthority(str, Enum):
    ACT = "act"
    ASK = "ask"


class CommitmentCandidate(SQLModel, table=True):
    """A derived, fallible commitment hypothesis from the background watcher
    (implicit self-commitments, Sophie-proposed + user-accepted proposals).

    Never canonical Task state: candidates live here until the authority gate
    or the user (via 'Sophie noticed') promotes or dismisses them. Dismissal
    is keyed on canonical_key so the same normalized commitment is never
    re-proposed; genuinely different commitments produce different keys."""

    __tablename__ = "commitment_candidates"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "owner_peer_id", "candidate_key",
            name="uq_commitment_candidate_workspace_owner_key",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    owner_peer_id: str = Field(index=True, nullable=False)
    # Stable per-candidate identity (hash of message + observation) — replay-safe.
    candidate_key: str = Field(nullable=False)
    # Normalized-commitment identity (hash of canonical title tokens) —
    # cross-message dedupe and durable dismissal key.
    canonical_key: str = Field(index=True, nullable=False)
    title: str = Field(nullable=False)
    notes: Optional[str] = Field(default=None)
    evidence_verbatim: str = Field(nullable=False)
    evidence_class: str = Field(nullable=False, default="implicit_self_commitment")
    authority: CommitmentCandidateAuthority = Field(
        default=CommitmentCandidateAuthority.ASK,
        sa_column=Column(SAEnum(CommitmentCandidateAuthority, native_enum=False), nullable=False),
    )
    status: CommitmentCandidateStatus = Field(
        default=CommitmentCandidateStatus.PENDING,
        sa_column=Column(SAEnum(CommitmentCandidateStatus, native_enum=False), nullable=False, index=True),
    )
    source_message_id: str = Field(index=True, nullable=False)
    materialized_source_object_id: Optional[str] = Field(default=None, index=True)
    raw_temporal_phrase: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)

    CANDIDATE_MAX_AGE_DAYS: ClassVar[int] = 21

    @classmethod
    def expiry(cls, now: datetime) -> datetime:
        return now + timedelta(days=cls.CANDIDATE_MAX_AGE_DAYS)
