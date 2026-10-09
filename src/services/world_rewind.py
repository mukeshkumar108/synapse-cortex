"""A rewound conversation: the person edited, retried or regenerated, so some messages no longer belong to the active timeline.

What Cortex derived from those messages loses its authority. The interpreter's ledger is its applied runs, and "the run is the unit of re-derivation": every run
whose evidence includes a discarded message (by id, or by the hash of a synthetic copy of that exchange) is retracted: the rows it created are deleted, anything it
had superseded is restored, and its messages become uncovered again so the next pass re-derives the surviving history. The sitting's anchors and picture are
reset to what predates the rewind. Nothing here touches durable identities (actors, relationships): a name that appeared is still a name."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.identity import ModelEntry
from src.models.world import ContinuationBrief, ProducerRun, RelationshipDimension, RowProvenance, TrajectoryNote, WorldEvent, WorldLink, WorldObjective

logger = logging.getLogger(__name__)

# row_type recorded in row_provenance -> table
TABLES = {"event": WorldEvent, "model_entry": ModelEntry, "objective": WorldObjective, "dimension": RelationshipDimension,
          "trajectory_note": TrajectoryNote, "continuation_brief": ContinuationBrief}


def _naive_utc(value: Any) -> Optional[datetime]:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _made_at(row: Any) -> datetime:
    for name in ("created_at", "discovered_at", "updated_at"):
        stamp = _naive_utc(getattr(row, name, None))
        if stamp is not None:
            return stamp
    return datetime.min


async def retract_runs(db: AsyncSession, *, workspace_id: str, owner: str, deleted: List[Dict[str, str]], since: Optional[datetime] = None) -> Dict[str, int]:
    """Retract every interpreter run that read a discarded message AND every run after the first of them: a later run read the world with the ghost in it (the brief, the
    dimensions, the trajectory it wrote are conclusions drawn from it), so its conclusions are re-derived from the surviving history rather than trusted. Rows a run created are
    deleted (events, claims, objectives, dimensions, trajectory notes, briefs, and the actors and relationships nothing else uses); what it superseded is current again."""
    from src.models.identity import Entity, EntityAlias, EntityLink, RelationshipEdge
    from src.models.world import WorldIdentity
    from src.services.standing_requests import StandingRequest
    from src.services.world_interpreter import message_hash
    ids = {str(d.get("id")) for d in deleted if d.get("id")}
    hashes = {message_hash(d.get("speaker") or "user", d.get("text") or "") for d in deleted if (d.get("text") or "").strip()}
    runs = (await db.execute(select(ProducerRun).where(ProducerRun.honcho_workspace_id == workspace_id, ProducerRun.owner_peer_id == owner,
                                                       ProducerRun.producer == "world-interpreter", ProducerRun.status == "applied"))).scalars().all()
    first_hit: Optional[datetime] = None
    for run in runs:
        try:
            data = json.loads(run.input_json or "{}")
        except ValueError:
            continue
        if ids & set(data.get("message_ids") or []) or hashes & set(data.get("synthetic_hashes") or []):
            first_hit = min(first_hit, _made_at(run)) if first_hit else _made_at(run)
    standing = {"standing_removed": 0, "standing_reopened": 0}
    if since is not None:         # everything after the rewind point is gone, so a request made (or withdrawn) there is not the active timeline's
        for r in (await db.execute(select(StandingRequest).where(StandingRequest.honcho_workspace_id == workspace_id, StandingRequest.owner_peer_id == owner))).scalars().all():
            if (_naive_utc(r.created_at) or datetime.min) >= since:
                await db.delete(r)
                standing["standing_removed"] += 1
            elif r.status == "withdrawn" and (_naive_utc(r.withdrawn_at) or datetime.min) >= since:
                r.status, r.withdrawn_at = "active", None
                db.add(r)
                standing["standing_reopened"] += 1
    if first_hit is None:
        await db.commit()
        return {"runs_retracted": 0, "rows_removed": 0, "actors_removed": 0, **standing}
    hit = sorted([r for r in runs if _made_at(r) >= first_hit], key=_made_at, reverse=True)       # newest first, so what each superseded is restored in order
    hit_ids = {r.id for r in hit}
    pinned = {w.entity_id for w in (await db.execute(select(WorldIdentity).where(WorldIdentity.honcho_workspace_id == workspace_id, WorldIdentity.owner_peer_id == owner))).scalars().all()}
    removed = actors = 0
    for run in hit:
        prov = (await db.execute(select(RowProvenance).where(RowProvenance.run_id == run.id))).scalars().all()
        for row_type, table in TABLES.items():
            row_ids = [p.row_id for p in prov if p.row_type == row_type]
            if not row_ids:
                continue
            made = [r for r in (await db.execute(select(table).where(table.id.in_(row_ids)))).scalars().all() if _made_at(r) >= _made_at(run)]        # only what this run CREATED
            gone = [r.id for r in made]
            if not gone:
                continue
            if hasattr(table, "superseded_by_id"):
                await db.execute(update(table).where(table.superseded_by_id.in_(gone)).values(superseded_by_id=None))
            await db.execute(delete(WorldLink).where(WorldLink.honcho_workspace_id == workspace_id, (WorldLink.from_id.in_(gone)) | (WorldLink.to_id.in_(gone))))
            await db.execute(delete(table).where(table.id.in_(gone)))
            removed += len(gone)
        run.status = "retracted"
        db.add(run)
    await db.commit()
    # Actors and relationships a retracted run introduced stay only if a surviving run (or the pinned identities) also touched them.
    survivors = {p.row_id for p in (await db.execute(select(RowProvenance).where(RowProvenance.honcho_workspace_id == workspace_id, RowProvenance.run_id.not_in(hit_ids)))).scalars().all()} if hit_ids else set()
    for run in hit:
        prov = (await db.execute(select(RowProvenance).where(RowProvenance.run_id == run.id))).scalars().all()
        edge_ids = [p.row_id for p in prov if p.row_type == "edge" and p.row_id not in survivors]
        ent_ids = [p.row_id for p in prov if p.row_type == "entity" and p.row_id not in survivors and p.row_id not in pinned]
        if edge_ids:
            await db.execute(delete(RelationshipEdge).where(RelationshipEdge.id.in_(edge_ids), RelationshipEdge.created_at >= _made_at(run)))
        if ent_ids:
            fresh = [e.id for e in (await db.execute(select(Entity).where(Entity.id.in_(ent_ids)))).scalars().all() if _made_at(e) >= _made_at(run)]
            if fresh:
                await db.execute(delete(RelationshipEdge).where(RelationshipEdge.from_entity_id.in_(fresh) | RelationshipEdge.to_entity_id.in_(fresh)))
                await db.execute(delete(EntityAlias).where(EntityAlias.entity_id.in_(fresh)))
                await db.execute(delete(EntityLink).where(EntityLink.entity_id.in_(fresh)))
                await db.execute(delete(Entity).where(Entity.id.in_(fresh)))
                actors += len(fresh)
    await db.commit()
    from src.services import world_model_service
    try:
        await world_model_service.invalidate(db, workspace_id=workspace_id, owner_peer_id=owner)
    except Exception as exc:        # the retraction stands; the snapshot refreshes on its own schedule
        logger.warning("snapshot invalidation after rewind failed: %s", exc)
    return {"runs_retracted": len(hit), "rows_removed": removed, "actors_removed": actors, **standing}


async def reset_sitting(db: AsyncSession, *, workspace_id: str, session_ids: List[str], since: datetime) -> Dict[str, Any]:
    """Anchors established before the rewind point stay; everything at or after it goes, and so does the prose picture (it cannot be un-written) and the
    buffered exchanges: the next pass rebuilds the picture from the surviving messages with the surviving anchors in hand."""
    from src.models.scene import SceneNarrative
    from src.services.scene_narrative import load_anchors
    dropped = kept = 0
    for sid in dict.fromkeys(s for s in session_ids if s):
        row = (await db.execute(select(SceneNarrative).where(SceneNarrative.honcho_workspace_id == workspace_id, SceneNarrative.honcho_session_id == sid))).scalars().first()
        if row is None:
            continue
        anchors = load_anchors(row)
        survivors = [a for a in anchors if (_naive_utc(a.get("at")) or datetime.min) < since]
        dropped += len(anchors) - len(survivors)
        kept += len(survivors)
        row.anchors_json = json.dumps(survivors, ensure_ascii=False)
        row.text, row.pending_json, row.through_message_id = "", "[]", None
        db.add(row)
    await db.commit()
    return {"anchors_dropped": dropped, "anchors_kept": kept}


async def rewind(db: AsyncSession, *, workspace_id: str, owner: str, session_ids: List[str], since: datetime, deleted: List[Dict[str, str]]) -> Dict[str, Any]:
    since_naive = _naive_utc(since) or datetime.utcnow()
    return {**await retract_runs(db, workspace_id=workspace_id, owner=owner, deleted=deleted, since=since_naive),
            **await reset_sitting(db, workspace_id=workspace_id, session_ids=session_ids, since=since_naive)}
