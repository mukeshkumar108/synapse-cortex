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


async def retract_memory(db: AsyncSession, *, workspace_id: str, owner: str, product: str, deleted: List[Dict[str, str]]) -> Dict[str, Any]:
    """The product-memory pipeline (story notes, arc, thread), for products that run it. A consolidation that read a discarded message, and every one after it (they were
    written with the ghost in the arc and the thread), is retracted: its notes go (what they superseded is current again), its thread checkpoint goes, the arc returns to what
    it was before the first of them, and the run stops counting as covered, so the surviving history is handed over again. Runs before the first are untouched.
    A rewind that no consolidation has read (a regenerated last reply, the usual case) changes nothing."""
    import json
    from src.models.note import Note
    from src.models.world import ContinuingArc, MemoryRun, ThreadCheckpoint
    from src.services.product_scope import SEP
    workspace_id = workspace_id if SEP in workspace_id else f"{product}{SEP}{workspace_id}"        # a product's memory lives in its own workspace (product_scope)
    ids = {str(d.get("id")) for d in deleted if d.get("id")}
    if not ids:
        return {"memory_runs_retracted": 0}
    runs = (await db.execute(select(MemoryRun).where(MemoryRun.honcho_workspace_id == workspace_id, MemoryRun.owner_peer_id == owner,
                                                     MemoryRun.status.in_(["consolidated", "replay_noop"])))).scalars().all()
    runs = sorted(runs, key=lambda r: (_made_at(r), str(r.id)))
    first = next((i for i, r in enumerate(runs) if ids & set(json.loads(r.covered_ids_json or "[]"))), None)
    if first is None:
        return {"memory_runs_retracted": 0}
    hit = runs[first:]
    hit_ids = [r.id for r in hit]
    try:
        arc_before = str((json.loads(hit[0].bundle_json or "{}")).get("arc_before") or "")
    except ValueError:
        arc_before = ""
    made = (await db.execute(select(Note).where(Note.honcho_workspace_id == workspace_id, Note.owner_peer_id == owner, Note.run_id.in_(hit_ids)))).scalars().all()
    gone = [n.id for n in made]
    notes_restored = 0
    if gone:
        restored = (await db.execute(select(Note).where(Note.replaced_by_id.in_(gone)))).scalars().all()
        for n in restored:
            n.status, n.replaced_by_id = "current", None
            db.add(n)
        notes_restored = len(restored)
        await db.execute(delete(Note).where(Note.id.in_(gone)))
    threads = (await db.execute(select(ThreadCheckpoint).where(ThreadCheckpoint.honcho_workspace_id == workspace_id, ThreadCheckpoint.owner_peer_id == owner,
                                                               ThreadCheckpoint.run_id.in_(hit_ids)))).scalars().all()
    for t in threads:
        await db.delete(t)
    arcs = (await db.execute(select(ContinuingArc).where(ContinuingArc.honcho_workspace_id == workspace_id, ContinuingArc.owner_peer_id == owner,
                                                         ContinuingArc.product == product))).scalars().all()
    for a in arcs:
        a.text, a.updated_at = arc_before, datetime.utcnow()
        db.add(a)
    for r in hit:
        r.status = "retracted"
        db.add(r)
    await db.commit()
    return {"memory_runs_retracted": len(hit), "notes_removed": len(gone), "notes_restored": notes_restored, "threads_removed": len(threads), "arc_restored_chars": len(arc_before)}


async def reset_live_scene(db: AsyncSession, *, workspace_id: str, owner: str, session_ids: List[str], since: datetime) -> Dict[str, Any]:
    """What the live scene was told at or after the rewind point (where they are, what they are doing, who is present) was said in a branch that is gone. A field written
    since then is dropped (the earlier value it overwrote is not kept, so the scene is simply re-read from the surviving story); fields set before it stay."""
    from src.models.scene import CurrentScene
    dropped = 0
    sessions = list(dict.fromkeys([s for s in session_ids if s] + [f"real_{owner}"]))
    for row in (await db.execute(select(CurrentScene).where(CurrentScene.honcho_workspace_id == workspace_id, CurrentScene.honcho_session_id.in_(sessions)))).scalars().all():
        try:
            fields = json.loads(row.fields_json or "{}")
        except ValueError:
            continue
        kept = {k: v for k, v in fields.items() if not (isinstance(v, dict) and (_naive_utc(v.get("updated_at")) or datetime.min) >= since)}
        if len(kept) != len(fields):
            dropped += len(fields) - len(kept)
            row.fields_json = json.dumps(kept, ensure_ascii=False)
            db.add(row)
    await db.commit()
    return {"scene_fields_dropped": dropped}


async def rewind(db: AsyncSession, *, workspace_id: str, owner: str, session_ids: List[str], since: datetime, deleted: List[Dict[str, str]], product: str = "") -> Dict[str, Any]:
    since_naive = _naive_utc(since) or datetime.utcnow()
    out = {**await retract_runs(db, workspace_id=workspace_id, owner=owner, deleted=deleted, since=since_naive),
           **await reset_sitting(db, workspace_id=workspace_id, session_ids=session_ids, since=since_naive)}
    if product:         # only products that run the memory pipeline say so; every other caller is exactly as before
        out.update(await retract_memory(db, workspace_id=workspace_id, owner=owner, product=product, deleted=deleted))
        out.update(await reset_live_scene(db, workspace_id=workspace_id, owner=owner, session_ids=session_ids, since=since_naive))
    return out
