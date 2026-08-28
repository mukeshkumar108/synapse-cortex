"""Commitment candidate lifecycle: derived, fallible, bounded.

The watcher proposes; this service stores the proposal as derived state; the
app (authority gate or the user via 'Sophie noticed') promotes or dismisses.
Deterministic guarantees:
- candidate_key is stable per (workspace, owner, message, observation) so
  redelivery/replay can never duplicate a candidate;
- canonical_key is the normalized-commitment identity, so a dismissal is
  durable against re-proposal of the same commitment;
- pending candidates expire (bounded intelligence, not a backlog).
"""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.commitment_candidate import (
    CommitmentCandidate,
    CommitmentCandidateAuthority,
    CommitmentCandidateStatus,
    utc_now,
)
from src.schemas.candidate import ExtractionCandidate

logger = logging.getLogger(__name__)

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "about", "after", "again", "also", "been", "could", "from", "have",
    "into", "just", "that", "their", "them", "then", "there", "they",
    "this", "what", "when", "where", "which", "with", "would", "your",
    "should", "need", "want", "maybe", "probably", "really", "actually",
    "soon", "someday", "sometime", "asap",
}


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


_SUFFIXES = ("ations", "ation", "ments", "ment", "ings", "ing", "edly", "ed", "ly", "es", "al", "s")


def _fold(word: str) -> str:
    """Tiny deterministic suffix folder so 'renew'/'renewal' and
    'book'/'booking' share a canonical identity. Deliberately conservative:
    it only ever merges near-identical content words."""
    for suffix in _SUFFIXES:
        if len(word) > len(suffix) + 2 and word.endswith(suffix):
            return word[: -len(suffix)]
    return word


def canonical_key_for(title: str) -> str:
    """Normalized-commitment identity: content tokens of the canonical title,
    order-independent, lightly stemmed. Deterministic across paraphrases that
    keep the same content words; different words yield different keys
    (deliberate: a wrong merge is worse than a duplicate proposal)."""
    words = _WORD_RE.findall(title.lower())
    content = sorted({_fold(w) for w in words if len(w) >= 3 and w not in _STOPWORDS})
    if not content:
        content = sorted({_fold(w) for w in _WORD_RE.findall(title.lower())}) or ["unknown"]
    return hashlib.sha1(":".join(content).encode()).hexdigest()


class CommitmentCandidateService:
    async def upsert_from_candidate(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        owner_peer_id: str,
        message_id: str,
        candidate: ExtractionCandidate,
        now: datetime,
    ) -> Optional[CommitmentCandidate]:
        title = (candidate.canonical_title or candidate.observation or "").strip()
        if not title:
            return None
        candidate_key = hashlib.sha1(
            f"{workspace_id}:{owner_peer_id}:{message_id}:{candidate.candidate_key}".encode()
        ).hexdigest()
        canonical_key = canonical_key_for(title)
        evidence = (
            candidate.raw_evidence
            or candidate.observation
            or ""
        ).strip()[:2000]

        existing_canonical = (
            await db.execute(
                select(CommitmentCandidate).where(
                    CommitmentCandidate.honcho_workspace_id == workspace_id,
                    CommitmentCandidate.owner_peer_id == owner_peer_id,
                    CommitmentCandidate.canonical_key == canonical_key,
                    CommitmentCandidate.status.in_([
                        CommitmentCandidateStatus.PENDING,
                        CommitmentCandidateStatus.MATERIALIZED,
                        CommitmentCandidateStatus.DISMISSED,
                    ]),
                )
            )
        ).scalars().first()

        if existing_canonical is not None:
            # Durable dismissal: the same normalized commitment is never
            # re-proposed after the user dismissed it.
            if existing_canonical.status == CommitmentCandidateStatus.DISMISSED:
                return None
            # Replay/redelivery of the same observation: idempotent no-op.
            if existing_canonical.candidate_key == candidate_key:
                return existing_canonical
            if existing_canonical.status == CommitmentCandidateStatus.MATERIALIZED:
                return None
            # A later, fresh observation of the same commitment refreshes the
            # pending candidate's evidence rather than duplicating it.
            existing_canonical.evidence_verbatim = evidence or existing_canonical.evidence_verbatim
            existing_canonical.source_message_id = message_id
            existing_canonical.updated_at = _now_naive()
            db.add(existing_canonical)
            await db.commit()
            return existing_canonical

        row = CommitmentCandidate(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            owner_peer_id=owner_peer_id,
            candidate_key=candidate_key,
            canonical_key=canonical_key,
            title=title[:280],
            notes=(candidate.observation or None) if candidate.observation != title else None,
            evidence_verbatim=evidence or title,
            evidence_class=(candidate.evidence_class or "implicit_self_commitment"),
            authority=(
                CommitmentCandidateAuthority(candidate.authority)
                if candidate.authority in ("act", "ask")
                else CommitmentCandidateAuthority.ASK
            ),
            status=CommitmentCandidateStatus.PENDING,
            source_message_id=message_id,
            raw_temporal_phrase=candidate.temporal_phrase,
        )
        db.add(row)
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            return (
                await db.execute(
                    select(CommitmentCandidate).where(
                        CommitmentCandidate.honcho_workspace_id == workspace_id,
                        CommitmentCandidate.owner_peer_id == owner_peer_id,
                        CommitmentCandidate.candidate_key == candidate_key,
                    )
                )
            ).scalar_one_or_none()
        return row

    async def expire_stale(
        self, db: AsyncSession, *, workspace_id: str, owner_peer_id: str, now: datetime
    ) -> None:
        cutoff = _now_naive() - timedelta(
            days=CommitmentCandidate.CANDIDATE_MAX_AGE_DAYS
        )
        rows = (
            await db.execute(
                select(CommitmentCandidate).where(
                    CommitmentCandidate.honcho_workspace_id == workspace_id,
                    CommitmentCandidate.owner_peer_id == owner_peer_id,
                    CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
                    CommitmentCandidate.updated_at < cutoff,
                )
            )
        ).scalars().all()
        for row in rows:
            row.status = CommitmentCandidateStatus.EXPIRED
            row.updated_at = _now_naive()
            db.add(row)
        if rows:
            await db.commit()

    async def list_pending(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        owner_peer_id: str,
        authority: Optional[CommitmentCandidateAuthority] = None,
        limit: int = 20,
    ) -> List[CommitmentCandidate]:
        await self.expire_stale(
            db, workspace_id=workspace_id, owner_peer_id=owner_peer_id, now=_now_naive()
        )
        conditions = [
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.owner_peer_id == owner_peer_id,
            CommitmentCandidate.status == CommitmentCandidateStatus.PENDING,
        ]
        if authority is not None:
            conditions.append(CommitmentCandidate.authority == authority)
        rows = (
            await db.execute(
                select(CommitmentCandidate)
                .where(*conditions)
                .order_by(CommitmentCandidate.created_at.desc())
                .limit(max(1, min(limit, 50)))
            )
        ).scalars().all()
        return list(rows)

    async def mark(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        owner_peer_id: str,
        candidate_key: str,
        status: CommitmentCandidateStatus,
        source_object_id: Optional[str] = None,
    ) -> Optional[CommitmentCandidate]:
        row = (
            await db.execute(
                select(CommitmentCandidate).where(
                    CommitmentCandidate.honcho_workspace_id == workspace_id,
                    CommitmentCandidate.owner_peer_id == owner_peer_id,
                    CommitmentCandidate.candidate_key == candidate_key,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            return None
        if row.status == CommitmentCandidateStatus.DISMISSED:
            return row  # dismissal is durable; materialization cannot resurrect
        row.status = status
        if source_object_id:
            row.materialized_source_object_id = source_object_id
        row.updated_at = _now_naive()
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row
