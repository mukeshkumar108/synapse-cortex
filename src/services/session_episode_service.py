"""SessionEpisode: provenance-linked record of what a consolidation run wrote.

The episode is NOT a store of decisions, repair state, expectations or
relationship truth. Those are written by consolidation into the canonical
primitives/ModelEntries (session_apply + consolidation_world); the episode
holds prose plus REFERENCES to those writes with a role label, what was
detected but deliberately not applied, and the Matters/entities the run
touched (docs/CORTEX_ARCHITECTURE.md §12).

`reconcile_after_writes` is the one post-write step shared by consolidation
and the Lane-2 sweeper: resolve new primitives into Matters, link the claims
a run wrote to their Matter/subject, refresh lifecycle + salience.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.matter import MatterLink
from src.models.world_model import SessionEpisode

logger = logging.getLogger(__name__)

CLAIM_ROLE = {
    "decision": "decision", "correction": "correction", "repair": "repair",
    "relationship_development": "relationship_development", "pattern": "pattern",
    "observation": "pattern", "perspective": "system_perspective",
}
OBJECT_TYPE_OF_ROW_KIND = {"open_loop": "open_loop", "commitment": "commitment",
                           "expectation": "expectation", "model_entry": "model_entry",
                           "knowledge_coverage": "knowledge_coverage"}


def _writes_from_applied(applied: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    writes: List[Dict[str, Any]] = []
    for a in applied or []:
        op = a.get("op")
        row_id, row_kind = a.get("row_id"), a.get("row_kind")
        evidence = (a.get("data") or {}).get("evidence") or {}
        refs = [str(m) for m in (evidence.get("message_ids") or [])]
        role: Optional[str] = None
        otype = OBJECT_TYPE_OF_ROW_KIND.get(row_kind or "")
        if op == "new_matter":
            role = "matter_created"
        elif op == "resolve_matter":
            role = "resolution"
        elif op == "partial_fulfilment":
            role = "partial_resolution"
        elif op == "revise_expectation":
            role, otype = "outcome_revised", "expectation"
        elif op == "same_as":
            data = a.get("data") or {}
            writes.append({"role": "identity_link", "object_type": None, "object_id": None,
                           "related": [data.get("matter_id_a"), data.get("matter_id_b")],
                           "evidence_refs": refs})
            continue
        elif op in ("attend", "uncertainty"):
            role, otype = "attention_held", "attention"
        elif op == "claim":
            role = CLAIM_ROLE.get(a.get("claim_kind") or "", "claim")
        elif op == "directed_expectation":
            role = f"{a.get('direction')}_expectation"
        elif op == "knowledge_gap":
            role = "knowledge_gap"
        if role is None or not row_id:
            continue
        writes.append({"role": role, "object_type": otype, "object_id": str(row_id),
                       "op": op, "evidence_refs": refs})
    return writes


async def _link_claims(db: AsyncSession, workspace_id: str, applied: List[Dict[str, Any]]) -> None:
    """Attach written claims to the Matter of the primitive they relate to and
    to their subject entity (exact alias match only — never provisioned or
    guessed here)."""
    from src.models.identity import ModelEntry
    from src.services import entity_service
    for a in applied or []:
        if a.get("op") != "claim" or not a.get("row_id"):
            continue
        try:
            entry = await db.get(ModelEntry, UUID(str(a["row_id"])))
        except ValueError:
            continue
        if entry is None:
            continue
        changed = False
        if entry.subject_matter_id is None:
            for rid in a.get("related") or []:
                try:
                    uid = UUID(str(rid))
                except ValueError:
                    continue
                mid = (await db.execute(select(MatterLink.matter_id).where(
                    MatterLink.object_id == uid))).scalars().first()
                if mid:
                    entry.subject_matter_id, changed = mid, True
                    break
        if entry.subject_entity_id is None:
            for name in a.get("subjects") or []:
                found = await entity_service.find_entities(db, workspace_id=workspace_id, alias=name)
                if len(found) == 1:
                    entry.subject_entity_id, changed = found[0].id, True
                    break
        if changed:
            db.add(entry)
    await db.commit()


async def reconcile_after_writes(db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
                                 session_id: Optional[str], now: datetime,
                                 allow_judge: bool = False, adapter: Any = None) -> Dict[str, Any]:
    """The single post-write step: primitives -> Matters (+lifecycle/salience)."""
    from src.services import matter_service
    return await matter_service.sync_primitives(
        db, workspace_id=workspace_id, owner_peer_id=owner_peer_id, session_id=session_id,
        now=now, allow_judge=allow_judge, adapter=adapter)


async def record_episode(db: AsyncSession, *, workspace_id: str, session_id: str,
                         temporal_session_id: str, run: Any, aggregate: Dict[str, Any],
                         user_peer_id: Optional[str], now: datetime,
                         allow_judge: bool = True) -> Optional[SessionEpisode]:
    """Write the episode for an APPLIED consolidation run (idempotent per run)."""
    run_id = getattr(run, "id", None)
    if run_id is not None:
        existing = (await db.execute(select(SessionEpisode).where(
            SessionEpisode.consolidation_run_id == run_id))).scalars().first()
        if existing is not None:
            return existing
    applied = aggregate.get("applied") or []
    deferred = aggregate.get("deferred") or []
    adapter = None
    if allow_judge:
        try:
            from src.services import semantic_judge
            adapter = semantic_judge._adapter()
        except Exception:
            adapter = None
    sync_stats = await reconcile_after_writes(
        db, workspace_id=workspace_id, owner_peer_id=user_peer_id, session_id=session_id,
        now=now, allow_judge=bool(adapter), adapter=adapter)
    await _link_claims(db, workspace_id, applied)
    writes = _writes_from_applied(applied)

    # Matters / entities touched, resolved from the canonical links of the writes.
    object_ids = []
    for w in writes:
        for key in ("object_id",):
            if w.get(key):
                try:
                    object_ids.append(UUID(w[key]))
                except ValueError:
                    pass
        for rid in w.get("related") or []:
            try:
                object_ids.append(UUID(str(rid)))
            except (ValueError, TypeError):
                pass
    matter_ids: List[str] = []
    entity_ids: List[str] = []
    if object_ids:
        from src.models.identity import EntityLink, ModelEntry
        mids = {l.matter_id for l in (await db.execute(select(MatterLink).where(
            MatterLink.object_id.in_(object_ids)))).scalars().all()}
        for e in (await db.execute(select(ModelEntry).where(ModelEntry.id.in_(object_ids)))).scalars().all():
            if e.subject_matter_id:
                mids.add(e.subject_matter_id)
        matter_ids = sorted(str(m) for m in mids)
        eids = {l.entity_id for l in (await db.execute(select(EntityLink).where(
            EntityLink.object_id.in_(object_ids + list(mids))))).scalars().all()}
        entity_ids = sorted(str(e) for e in eids)
    for w in writes:  # annotate each write with the Matter it landed in
        if w.get("object_id"):
            try:
                mid = (await db.execute(select(MatterLink.matter_id).where(
                    MatterLink.object_id == UUID(w["object_id"])))).scalars().first()
            except ValueError:
                mid = None
            if mid:
                w["matter_id"] = str(mid)

    detected = [{"op": d.get("op"), "reason": d.get("reason"), "applied": False} for d in deferred]
    episode = SessionEpisode(
        honcho_workspace_id=workspace_id, honcho_session_id=session_id,
        temporal_session_id=temporal_session_id or "", consolidation_run_id=run_id,
        owner_peer_id=user_peer_id,
        summary=(getattr(run, "summary", "") or " | ".join(aggregate.get("summaries", [])))[:1000],
        writes_json=json.dumps(writes, default=str),
        detected_json=json.dumps(detected + [{"op": "matter_sync", "stats": sync_stats}], default=str),
        matters_touched_json=json.dumps(matter_ids),
        entities_touched_json=json.dumps(entity_ids))
    db.add(episode)
    await db.commit()
    return episode


def episode_view(ep: SessionEpisode) -> Dict[str, Any]:
    return {
        "id": str(ep.id), "session_id": ep.honcho_session_id, "temporal_session_id": ep.temporal_session_id,
        "consolidation_run_id": str(ep.consolidation_run_id) if ep.consolidation_run_id else None,
        "summary": ep.summary, "writes": json.loads(ep.writes_json or "[]"),
        "detected": json.loads(ep.detected_json or "[]"),
        "matters_touched": json.loads(ep.matters_touched_json or "[]"),
        "entities_touched": json.loads(ep.entities_touched_json or "[]"),
        "created_at": ep.created_at.isoformat(),
        "note": "references canonical writes; not a store of decisions/repair/expectations/truth",
    }
