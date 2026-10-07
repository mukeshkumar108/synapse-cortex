"""POST /v1/world/delta: producers submit typed WorldDelta candidates; Cortex grounds, judges (ambiguous only, optional), materialises, and
returns a receipt (`covered_through`, ref -> id map, rejections) (docs/WORLD_CONTRACT.md)."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.schemas.world_delta import WorldDelta
from src.services.world_materializer import materialize

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/world", tags=["world-delta"])


@router.post("/delta")
async def submit_world_delta(delta: WorldDelta, db: AsyncSession = Depends(get_async_session)):
    try:
        return await materialize(db, delta)
    except Exception as exc:  # a bad delta must never corrupt canonical state or take the service down
        await db.rollback()
        logger.exception("world delta materialisation failed")
        raise HTTPException(status_code=500, detail=f"materialisation_failed:{type(exc).__name__}") from exc


class InterpretRequest(BaseModel):
    workspace_id: str
    owner: str
    session_id: str
    messages: List[Dict[str, str]]
    speakers: Dict[str, str] = {}
    policy: str = "grounded"
    constitution: Optional[Dict[str, str]] = None      # {actor, toward, text}: product-authored by the trusted caller, never extracted
    covered_ordinal: int = 0
    user_actor: Optional[str] = None            # product-supplied identity of the human's actor in this world (never inferred from prose)
    companion_actor: Optional[str] = None       # product-supplied identity of the companion's actor
    timezone: str = "UTC"                       # the user's timezone, used to ground time phrases of operational items
    overrides: Optional[Dict[str, Any]] = None  # LAB ONLY (owner must be world:lab:*): {system_replace:[[old,new]], system_append, model}
    agency: bool = False                        # product policy (Runtime registry): after this pass the character reflects (heart) and the story may move (pressure), in the background


@router.post("/interpret")
async def interpret_world(req: InterpretRequest, db: AsyncSession = Depends(get_async_session)):
    """One reasoning pass over new evidence + current world state; the result is materialised and a receipt (with the new snapshot version) returned."""
    from src.runtime_model import get_agenda_adapter
    from src.services import world_interpreter
    adapter = get_agenda_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="no_model_credentials")
    if req.overrides and not req.owner.startswith("world:lab:"):
        raise HTTPException(status_code=403, detail="interpreter_overrides_are_lab_only")
    if len(req.messages) < 2 or any(set(m) < {"id", "speaker", "text"} for m in req.messages):
        raise HTTPException(status_code=422, detail="messages need id, speaker, text")
    try:
        receipt = await world_interpreter.interpret(
            db, workspace_id=req.workspace_id, owner=req.owner, session_id=req.session_id, messages=req.messages, speakers=req.speakers,
            policy=req.policy, constitution=req.constitution, adapter=adapter, covered_ordinal=req.covered_ordinal, matter_adapter=adapter,
            user_actor=req.user_actor, companion_actor=req.companion_actor, timezone=req.timezone, overrides=req.overrides)
        if req.agency and receipt.get("status") == "applied":
            import asyncio
            from src.services import character_agency
            asyncio.create_task(character_agency.run_background(
                workspace_id=req.workspace_id, owner=req.owner, session_id=req.session_id, constitution=req.constitution,
                user_actor=req.user_actor, companion_actor=req.companion_actor))
        return receipt
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=f"bad_interpreter_override:{exc}") from exc
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        logger.exception("world interpretation failed")
        raise HTTPException(status_code=500, detail=f"interpretation_failed:{type(exc).__name__}") from exc


class NarrateRequest(BaseModel):
    workspace_id: str
    session_id: str
    messages: List[Dict[str, str]]          # last exchanges, oldest first: {id?, speaker: user|assistant, text}
    names: Dict[str, str] = {}              # {user, assistant} display names (product-supplied)
    force: bool = False                     # a significant moment: rewrite now instead of batching
    owner: Optional[str] = None             # the world owner: standing requests are stored against it, not against the conversation
    model: Optional[str] = None             # LAB ONLY (session must be a lab chat)


@router.post("/narrate")
async def narrate_scene(req: NarrateRequest, db: AsyncSession = Depends(get_async_session)):
    """The fast scene pass: rewrite the conversation's running picture (a few plain sentences) from the last messages. Fail-open for the caller."""
    from src.runtime_model import get_agenda_adapter
    from src.services import scene_narrative
    adapter = get_agenda_adapter()
    if adapter is None:
        raise HTTPException(status_code=503, detail="no_model_credentials")
    try:
        return await scene_narrative.narrate(db, adapter=adapter, workspace_id=req.workspace_id, session_id=req.session_id, messages=req.messages,
                                             names=req.names, model=req.model if req.session_id.startswith("chat-lab") else None, force=req.force, owner=req.owner)
    except Exception as exc:
        await db.rollback()
        logger.exception("scene narrative failed")
        raise HTTPException(status_code=500, detail=f"narrate_failed:{type(exc).__name__}") from exc


@router.get("/interpreter-config")
async def interpreter_config():
    """The authoritative description of the world interpreter AS DEPLOYED (never a copy): the exact system prompt, model, and where its output goes."""
    from src.services import world_interpreter as wi
    return {"version": "wi-2", "model": wi.INTERPRETER_MODEL, "system_prompt": wi.SYSTEM,
            "input_sections": ["PRODUCT POLICY", "IDENTITIES (product-supplied)", "CHARACTER CONSTITUTIONAL ORIENTATION", "CURRENT WORLD STATE (ids are real)",
                               "HONCHO CONTEXT (long-term store, when available)", "EARLIER MESSAGES (already interpreted, context only)", "NEW EVIDENCE"],
            "scene_fields": {"brief.text": "durable story so far", "brief.now": "what is happening in the most recent exchange", "brief.unresolved": "genuinely open",
                             "brief.transient": "observed reactions not to be promoted unless sustained", "brief.changed": "what materially changed this stretch",
                             "brief.spent": "already asked/told/joked/promised/settled", "brief.raw_turns": "0-3 raw turns the interpreter thinks still matter", "brief.raw_reason": "why"},
            "not_extracted_as_fields": ["participants/location of the current scene (the Runtime's own current_scene extractor owns the physical scene)"],
            "storage": "continuation_briefs (text, lines_json, scene_json), versioned; superseded rows kept",
            "projection": "world_model_service.build_world_layer -> continuation.brief.scene -> Runtime render_continuation -> [WHAT IS HAPPENING NOW] block",
            "cadence": "Runtime hands evidence over every CORTEX_CHECKPOINT_EVERY_TURNS user turns (3), at session end, and immediately for time-bound / awaiting-reply turns; "
                       "each pass interprets only message ids not yet covered"}


@router.post("/version")
async def world_version(req: Dict[str, str], db: AsyncSession = Depends(get_async_session)):
    """Cheap freshness probe: the version of the current resident snapshot for a world, so the Runtime can refresh its cached packet exactly when
    Cortex has materialised something new (no polling interval, no recompilation)."""
    from sqlmodel import select
    from src.models.world_model import WorldModelSnapshot
    workspace_id, owner = req.get("workspace_id"), req.get("owner")
    if not workspace_id or not owner:
        raise HTTPException(status_code=422, detail="workspace_id and owner required")
    snap = (await db.execute(select(WorldModelSnapshot).where(
        WorldModelSnapshot.honcho_workspace_id == workspace_id, WorldModelSnapshot.owner_peer_id == owner,
        WorldModelSnapshot.superseded_by_id.is_(None)).order_by(WorldModelSnapshot.compiled_at.desc()).limit(1))).scalars().first()
    from src.services import executive, scene_state
    import json as _json

    async def layer(session: Optional[str]) -> Optional[Dict[str, Any]]:
        if not session:
            return None
        row = await scene_state.get_active_scene(db, workspace_id, session)
        return {"fields": _json.loads(row.fields_json or "{}"), "updated_at": row.updated_at.isoformat()} if row is not None else None
    real_owner = req.get("real_owner")
    from src.services import scene_narrative
    narrative_session = req.get("narrative_session_id") or req.get("session_id")      # a person-scoped product keeps ONE running picture across chats and voice
    nar = await scene_narrative.current(db, workspace_id, narrative_session) if narrative_session else None
    from src.services import standing_requests as _sr, character_agency as _ca
    return {"developments": await _ca.pending_arrivals(db, workspace_id, owner), "narrative": ({"text": nar.text, "updated_at": nar.updated_at.isoformat()} if nar else None), "standing_requests": await _sr.active(db, workspace_id, owner), "version": snap.version if snap else None, "awaiting_reply": await executive.awaiting_reply(db, workspace_id, owner),
            # The canonical live scene, two layers: this conversation's story, and the person's real-world situation (shared across chats/devices).
            "scene": {"story": await layer(req.get("session_id")), "real": await layer(f"real_{real_owner}" if real_owner else None)}}


@router.get("/trace")
async def world_trace(workspace_id: str, owner: str, run_id: Optional[str] = None, limit: int = 10, db: AsyncSession = Depends(get_async_session)):
    """The one diagnostic surface for a world: its recent interpretation runs (lifecycle, evidence range, honcho use, candidates kept / dropped /
    rejected with reasons, supersessions, state reviews, snapshot revision before/after), the current resident snapshot revision with its coverage
    frontier, and whether a run currently holds the world."""
    import json
    from sqlmodel import select
    from src.models.world import ProducerRun, WorldLease
    from src.models.world_model import WorldModelSnapshot
    from src.services.world_lease import lease_key
    stmt = select(ProducerRun).where(ProducerRun.honcho_workspace_id == workspace_id, ProducerRun.owner_peer_id == owner)
    if run_id:
        stmt = stmt.where(ProducerRun.id == run_id)
    runs = (await db.execute(stmt.order_by(ProducerRun.created_at.desc()).limit(max(1, min(limit, 50))))).scalars().all()
    snap = (await db.execute(select(WorldModelSnapshot).where(
        WorldModelSnapshot.honcho_workspace_id == workspace_id, WorldModelSnapshot.owner_peer_id == owner,
        WorldModelSnapshot.superseded_by_id.is_(None)).order_by(WorldModelSnapshot.compiled_at.desc()).limit(1))).scalars().first()
    lease = await db.get(WorldLease, lease_key(workspace_id, owner))
    snapshot = None
    if snap is not None:
        try:
            body = json.loads(snap.snapshot_json or "{}")
        except ValueError:
            body = {}

        def find(node, key):          # the frontier lives in the resident manifest; locate it structurally
            if isinstance(node, dict):
                if key in node:
                    return node[key]
                for v in node.values():
                    hit = find(v, key)
                    if hit is not None:
                        return hit
            return None
        snapshot = {"version": snap.version, "compiled_at": snap.compiled_at.isoformat(), "covered_through": find(body, "covered_through")}
    def load(blob):
        try:
            return json.loads(blob or "{}")
        except ValueError:
            return {}
    return {"workspace_id": workspace_id, "owner": owner, "snapshot": snapshot,
            "lease": {"held_by": lease.holder, "expires_at": lease.expires_at.isoformat()} if lease else None,
            "runs": [{"run_id": str(r.id), "status": r.status, "producer": r.producer, "model": r.model, "created_at": r.created_at.isoformat(),
                      "started_at": r.started_at.isoformat() if r.started_at else None, "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                      "input": load(r.input_json), "covered_through": load(r.covered_through_json), "counts": load(r.counts_json), "detail": load(r.detail_json)}
                     for r in runs]}


class DevelopmentsRequest(BaseModel):
    workspace_id: str
    owner: str
    new_sitting: bool = False
    told_ids: List[str] = []


@router.post("/developments/advance")
async def advance_developments(req: DevelopmentsRequest, db: AsyncSession = Depends(get_async_session)):
    """pending -> arrived when the user arrives at a new sitting; arrived -> told once the foreground has had its turn with them."""
    from src.services import character_agency
    return await character_agency.advance_arrivals(db, req.workspace_id, req.owner, new_sitting=req.new_sitting, told_ids=req.told_ids)


class AgencyLabRequest(BaseModel):
    workspace_id: str
    owner: str
    session_id: Optional[str] = None
    constitution: Optional[Dict[str, str]] = None
    user_actor: Optional[str] = None
    companion_actor: Optional[str] = None
    models: Optional[List[str]] = None
    which: str = "both"             # heart | pressure | both


@router.post("/agency/lab-pass")
async def agency_lab_pass(req: AgencyLabRequest, db: AsyncSession = Depends(get_async_session)):
    """LAB ONLY dry run (owner must be world:lab:*): what the character would carry and whether the story would move, persisting nothing."""
    from src.services import character_agency
    if not req.owner.startswith("world:lab:"):
        raise HTTPException(status_code=403, detail="lab_only")
    kw = dict(workspace_id=req.workspace_id, owner=req.owner, session_id=req.session_id, constitution=req.constitution, user_actor=req.user_actor,
              companion_actor=req.companion_actor, dry_run=True, models=req.models)
    out: Dict[str, Any] = {}
    if req.which in ("heart", "both"):
        out["heart"] = await character_agency.run_heart(db, **kw)
    if req.which in ("pressure", "both"):
        out["pressure"] = await character_agency.run_pressure(db, **kw)
    return out
