"""WorldModel, projections, knowledge coverage and Matter endpoints.

Everything here is derived from authoritative Cortex primitives. The WorldModel
is returned for Runtime inspection/caching and is never meant to be injected
wholesale into a prompt; Runtime asks projections for small fragments.
(docs/CORTEX_ARCHITECTURE.md §6-7)
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.db import get_async_session
from src.models.matter import Matter
from src.services import knowledge_coverage_service as kcs
from src.services import matter_service, world_model_service
from src.services.product_profile import get_profile
from src.services.projection_service import open_projections, why
from src.services.world_scope import resolve_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/cortex", tags=["world"])


class WorldRequest(BaseModel):
    workspace_id: str
    peer_id: Optional[str] = None
    session_id: Optional[str] = None
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"
    product: Optional[str] = None  # policy weights only; never changes stored truth


def _uuid(value: str, field: str) -> UUID:
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"invalid {field}") from exc


async def _proj(req: WorldRequest, db: AsyncSession):
    profile = get_profile(req.product) if req.product else None
    return await open_projections(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id, now=req.now,
        tz=req.timezone, session_id=req.session_id,
        weights=profile.matter_weights if profile else None,
        kind_weights=profile.matter_kind_weights if profile else None)


# ----------------------------------------------------------------- WorldModel
class WorldModelRequest(WorldRequest):
    force: bool = False


@router.post("/world-model")
async def get_world_model(req: WorldModelRequest, db: AsyncSession = Depends(get_async_session)):
    """Persisted, versioned WorldModel (derived; reconstructable). Cheap when
    fresh; stale sections are patched."""
    return await world_model_service.get_world_model(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id, now=req.now,
        timezone_str=req.timezone, session_id=req.session_id, force=req.force)


class SnapshotAtRequest(BaseModel):
    workspace_id: str
    peer_id: str
    version: int


@router.post("/world-model/at")
async def get_world_model_at(req: SnapshotAtRequest, db: AsyncSession = Depends(get_async_session)):
    """READ-ONLY. The exact materialisation of one past version (superseded snapshots are retained), so a turn's packet can be re-read as it was compiled. Never recomputes or writes."""
    from src.models.world_model import WorldModelSnapshot
    row = (await db.execute(select(WorldModelSnapshot).where(
        WorldModelSnapshot.honcho_workspace_id == req.workspace_id, WorldModelSnapshot.owner_peer_id == req.peer_id,
        WorldModelSnapshot.version == req.version))).scalars().first()
    if row is None:
        raise HTTPException(status_code=404, detail="no snapshot at that version")
    body = json.loads(row.snapshot_json)
    body["meta"] = {**body.get("meta", {}), "snapshot_id": str(row.id), "version": row.version, "compiled_at": row.compiled_at.isoformat() if row.compiled_at else None}      # the same meta the live read stamps
    return {"version": row.version, "compiled_at": row.compiled_at.isoformat() if row.compiled_at else None, "superseded_by_id": str(row.superseded_by_id) if row.superseded_by_id else None,
            "fingerprints": json.loads(row.fingerprints_json or "{}"), "snapshot": body}


class InvalidateRequest(BaseModel):
    workspace_id: str
    peer_id: Optional[str] = None
    sections: Optional[List[str]] = None


@router.post("/world-model/invalidate")
async def invalidate_world_model(req: InvalidateRequest, db: AsyncSession = Depends(get_async_session)):
    return await world_model_service.invalidate(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id, sections=req.sections)


# ---------------------------------------------------------------- Projections
class PersonRequest(WorldRequest):
    entity_id: Optional[str] = None  # None -> the user overview


@router.post("/projection/person")
async def projection_person(req: PersonRequest, db: AsyncSession = Depends(get_async_session)):
    p = await _proj(req, db)
    return p.person(_uuid(req.entity_id, "entity_id") if req.entity_id else None)


class MatterRequest(WorldRequest):
    matter_id: str


@router.post("/projection/matter")
async def projection_matter(req: MatterRequest, db: AsyncSession = Depends(get_async_session)):
    p = await _proj(req, db)
    return p.matter(_uuid(req.matter_id, "matter_id"))


class TimelineRequest(WorldRequest):
    subject_type: str = Field(pattern="^(matter|entity)$")
    subject_id: str
    start: Optional[datetime] = None
    end: Optional[datetime] = None


@router.post("/projection/timeline")
async def projection_timeline(req: TimelineRequest, db: AsyncSession = Depends(get_async_session)):
    p = await _proj(req, db)
    return p.timeline((req.subject_type, _uuid(req.subject_id, "subject_id")), req.start, req.end)


@router.post("/projection/today")
async def projection_today(req: WorldRequest, db: AsyncSession = Depends(get_async_session)):
    return (await _proj(req, db)).today()


@router.post("/projection/week")
async def projection_week(req: WorldRequest, db: AsyncSession = Depends(get_async_session)):
    return (await _proj(req, db)).week()


class PeriodRequest(WorldRequest):
    start: datetime
    end: datetime


@router.post("/projection/period")
async def projection_period(req: PeriodRequest, db: AsyncSession = Depends(get_async_session)):
    if req.end <= req.start:
        raise HTTPException(status_code=422, detail="end must be after start")
    return (await _proj(req, db)).period(req.start, req.end)


@router.post("/projection/unresolved")
async def projection_unresolved(req: WorldRequest, db: AsyncSession = Depends(get_async_session)):
    return (await _proj(req, db)).unresolved()


class ChangesRequest(WorldRequest):
    days: float = 7
    since: Optional[datetime] = None


@router.post("/projection/recent-changes")
async def projection_recent_changes(req: ChangesRequest, db: AsyncSession = Depends(get_async_session)):
    return (await _proj(req, db)).recent_changes(days=req.days, since=req.since)


@router.post("/projection/knowledge-gaps")
async def projection_knowledge_gaps(req: WorldRequest, db: AsyncSession = Depends(get_async_session)):
    return (await _proj(req, db)).knowledge_gaps()


@router.post("/projection/depth")
async def projection_depth(req: WorldRequest, db: AsyncSession = Depends(get_async_session)):
    return (await _proj(req, db)).depth()


class WhyRequest(BaseModel):
    object_type: str
    object_id: str
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


@router.post("/projection/why")
async def projection_why(req: WhyRequest, db: AsyncSession = Depends(get_async_session)):
    """Why does Cortex believe this? Evidence, formation, supersession."""
    return await why(db, req.object_type, _uuid(req.object_id, "object_id"),
                     req.now.replace(tzinfo=None) if req.now.tzinfo is None
                     else req.now.astimezone(timezone.utc).replace(tzinfo=None))


# ------------------------------------------------------------ Knowledge coverage
class CoverageRequest(WorldRequest):
    statuses: Optional[List[str]] = None
    prefix: Optional[str] = None


@router.post("/knowledge-coverage")
async def knowledge_coverage(req: CoverageRequest, db: AsyncSession = Depends(get_async_session)):
    p = await _proj(req, db)  # opens (and refreshes) coverage
    try:
        rows = await kcs.read(db, p.r.scope, statuses=req.statuses, prefix=req.prefix)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"coverage": rows, "gaps": kcs.gaps(rows)}


class GapRequest(WorldRequest):
    subject_key: str
    why_useful: str = Field(default="", max_length=240)


@router.post("/knowledge-coverage/gap")
async def register_gap(req: GapRequest, db: AsyncSession = Depends(get_async_session)):
    """Register a useful gap. Registers `unknown` only — never a value."""
    scope = await resolve_scope(db, req.workspace_id, req.peer_id, req.session_id)
    try:
        row = await kcs.register_gap(db, scope=scope, subject_key=req.subject_key,
                                     why_useful=req.why_useful)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return kcs.view(row)


# ------------------------------------------------------------------- Matters
class MatterListRequest(WorldRequest):
    status: Optional[str] = None
    kind: Optional[str] = None


@router.post("/matters/list")
async def list_matters(req: MatterListRequest, db: AsyncSession = Depends(get_async_session)):
    p = await _proj(req, db)
    ms = [m for m in p.r.matters.values()
          if (not req.status or m.status == req.status) and (not req.kind or m.kind == req.kind)]
    ms.sort(key=lambda m: (-p._matter_brief(m)["rank"], m.title))
    return {"matters": [p._matter_brief(m) for m in ms]}


class MatterSyncRequest(WorldRequest):
    allow_judge: bool = False


@router.post("/matters/sync")
async def sync_matters(req: MatterSyncRequest, db: AsyncSession = Depends(get_async_session)):
    """Idempotent: resolve unlinked primitives into Matters and refresh
    lifecycle/salience. The single write step shared with consolidation and
    the sweeper."""
    from src.runtime_model import get_agenda_adapter
    return await matter_service.sync_primitives(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id, session_id=req.session_id,
        now=req.now, allow_judge=req.allow_judge,
        adapter=get_agenda_adapter() if req.allow_judge else None)


class MergeRequest(BaseModel):
    keep_id: str
    drop_id: str


@router.post("/matters/merge")
async def merge_matters(req: MergeRequest, db: AsyncSession = Depends(get_async_session)):
    keep, drop = _uuid(req.keep_id, "keep_id"), _uuid(req.drop_id, "drop_id")
    for mid in (keep, drop):
        if (await db.execute(select(Matter.id).where(Matter.id == mid))).first() is None:
            raise HTTPException(status_code=404, detail=f"matter {mid} not found")
    m = await matter_service.merge_matters(db, keep, drop)
    return {"kept": str(m.id), "merged": str(drop)}


# ------------------------------------------------------------------- Episodes
class EpisodesRequest(BaseModel):
    workspace_id: str
    peer_id: Optional[str] = None
    session_id: Optional[str] = None
    limit: int = Field(default=10, ge=1, le=50)


@router.post("/episodes/list")
async def list_episodes(req: EpisodesRequest, db: AsyncSession = Depends(get_async_session)):
    """Provenance-linked session episodes (references to canonical writes)."""
    from src.models.world_model import SessionEpisode
    from src.services.session_episode_service import episode_view
    stmt = select(SessionEpisode).where(SessionEpisode.honcho_workspace_id == req.workspace_id)
    if req.peer_id:
        stmt = stmt.where(SessionEpisode.owner_peer_id == req.peer_id)
    if req.session_id:
        stmt = stmt.where(SessionEpisode.honcho_session_id == req.session_id)
    rows = (await db.execute(stmt.order_by(SessionEpisode.created_at.desc()).limit(req.limit))).scalars().all()
    return {"episodes": [episode_view(r) for r in rows]}
