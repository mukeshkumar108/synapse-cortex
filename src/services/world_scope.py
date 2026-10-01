"""Scope of "this person's shared world".

State rows are owner-scoped (`owner_peer_id`). The shared world is the user's
rows PLUS the rows the system holds toward that user — assistant-turn promises
are owned by the speaking (character/system) peer, in the same durable lanes
(sessions) as the user's rows. A Matter or WorldModel for the user must see
both, so scope resolves the user's lanes and the non-user, non-external peers
co-present in them. `external:<sender>` peers are third-party feeds, never the
system.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, FrozenSet, Optional

from sqlalchemy import and_, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select


@dataclass(frozen=True)
class Scope:
    workspace_id: str
    owner_peer_id: Optional[str]
    session_id: Optional[str] = None
    lane_ids: FrozenSet[str] = field(default_factory=frozenset)
    system_peers: FrozenSet[str] = field(default_factory=frozenset)

    def is_system(self, peer: Optional[str]) -> bool:
        return bool(peer) and peer in self.system_peers

    def clause(self, model: Any):
        """SQL filter selecting `model` rows inside this scope. `model` must
        have honcho_workspace_id (always applied by callers) and may have
        owner_peer_id / honcho_session_id."""
        has_owner = hasattr(model, "owner_peer_id")
        has_session = hasattr(model, "honcho_session_id")
        lanes = set(self.lane_ids)
        if self.session_id:
            lanes.add(self.session_id)
        if not self.owner_peer_id:
            if has_session and self.session_id:
                return model.honcho_session_id == self.session_id
            return model.honcho_workspace_id == self.workspace_id
        parts = []
        if has_owner:
            parts.append(model.owner_peer_id == self.owner_peer_id)
            if has_session and lanes:
                if self.system_peers:
                    parts.append(and_(model.owner_peer_id.in_(list(self.system_peers)),
                                      model.honcho_session_id.in_(list(lanes))))
                parts.append(and_(model.owner_peer_id.is_(None),
                                  model.honcho_session_id.in_(list(lanes))))
        elif has_session and lanes:
            parts.append(model.honcho_session_id.in_(list(lanes)))
        else:
            return model.honcho_workspace_id == self.workspace_id
        return or_(*parts)


async def resolve_scope(db: AsyncSession, workspace_id: str,
                        owner_peer_id: Optional[str],
                        session_id: Optional[str] = None) -> Scope:
    """Discover the user's lanes and the system peers co-present in them."""
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop
    from src.models.operational_state import RecurringIntention

    lanes: set = set()
    if owner_peer_id:
        for model in (Expectation, OpenLoop, CommitmentCandidate, RecurringIntention):
            lanes.update((await db.execute(
                select(model.honcho_session_id).where(
                    model.honcho_workspace_id == workspace_id,
                    model.owner_peer_id == owner_peer_id).distinct())).scalars().all())
    if session_id:
        lanes.add(session_id)
    lanes.discard(None)
    lanes.discard("")
    system: set = set()
    if owner_peer_id and lanes:
        for model in (Expectation, OpenLoop, CommitmentCandidate):
            system.update((await db.execute(
                select(model.owner_peer_id).where(
                    model.honcho_workspace_id == workspace_id,
                    model.honcho_session_id.in_(list(lanes)),
                    model.owner_peer_id.is_not(None),
                    model.owner_peer_id != owner_peer_id).distinct())).scalars().all())
        system = {p for p in system if p and not p.strip().casefold().startswith("external:")}
    return Scope(workspace_id=workspace_id, owner_peer_id=owner_peer_id,
                 session_id=session_id, lane_ids=frozenset(lanes),
                 system_peers=frozenset(system))
