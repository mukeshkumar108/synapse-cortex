"""POST /v1/memory/*: the replacement understanding pipeline for Sophie.

- POST /consolidate: accept a COMPLETED session, run consolidation in the
  background, return 202 immediately (the Runtime never waits on it).
- GET /run/{run_id}: poll a consolidation's status + summary.
- GET /preparation: the latest cached perspective (pure read, no model).
- GET /state: notebook + ledger + arc for inspection/debugging.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import async_session_maker, get_async_session
from src.services import memory_pipeline, product_scope

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/memory", tags=["memory"])


class ConsolidateRequest(BaseModel):
    workspace_id: str
    owner: str
    conversation_id: str
    session_id: str
    messages: List[Dict[str, Any]]          # full transcript, both sides: {id, speaker, text}
    companion_id: str = "sophie"
    session_time: Optional[str] = None      # ISO time the sitting happened (with offset); relative dates resolve against it
    time_zone: Optional[str] = None         # IANA zone the person was in


def _scope(request: Request, workspace_id: str, companion_id: Optional[str]) -> product_scope.Scope:
    """The product boundary for this request: trusted product + namespaced workspace, computed once, here."""
    return product_scope.resolve_scope(request, workspace_id, companion_id)


async def _run_consolidation(workspace_id: str, owner: str, conversation_id: str, session_id: str,
                             messages: List[Dict[str, Any]], companion_id: str,
                             session_time: Optional[str] = None, time_zone: Optional[str] = None) -> None:
    try:
        async with async_session_maker() as db:
            try:
                await memory_pipeline.consolidate(
                    db, workspace_id=workspace_id, owner=owner, conversation_id=conversation_id,
                    session_id=session_id, messages=messages, companion_id=companion_id,
                    session_time=session_time, time_zone=time_zone)
            except Exception:
                logger.exception("memory consolidation failed for %s %s", owner, session_id)
                try:
                    await db.rollback()
                except Exception:
                    pass
    except Exception:
        logger.exception("memory consolidation session failed for %s %s", owner, session_id)


@router.post("/consolidate", status_code=202)
async def consolidate(req: ConsolidateRequest, request: Request, db: AsyncSession = Depends(get_async_session)):
    if not req.messages:
        raise HTTPException(status_code=422, detail="messages must not be empty")
    scope = _scope(request, req.workspace_id, req.companion_id if "companion_id" in req.model_fields_set else None)
    for m in req.messages:
        if set(m) < {"id", "speaker", "text"}:
            raise HTTPException(status_code=422, detail="messages need id, speaker, text")
    try:
        run_id = await memory_pipeline.create_run(
            db, workspace_id=scope.workspace, owner=req.owner, conversation_id=req.conversation_id,
            session_id=req.session_id, message_count=len(req.messages))
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"run_create_failed:{type(exc).__name__}") from exc
    asyncio.create_task(_run_consolidation(
        scope.workspace, req.owner, req.conversation_id, req.session_id,
        [dict(m) for m in req.messages], scope.product, req.session_time, req.time_zone))
    return {"status": "accepted", "run_id": run_id}


@router.get("/run/{run_id}")
async def run_status(run_id: str, request: Request, db: AsyncSession = Depends(get_async_session)):
    row = await memory_pipeline.get_run(db, run_id)
    authed = getattr(request.state, "product", None)
    if row is None or (authed and product_scope.product_of_workspace(row.honcho_workspace_id) != authed):
        raise HTTPException(status_code=404, detail="run_not_found")      # another product's run is indistinguishable from no run
    try:
        bundle = json.loads(row.bundle_json or "{}")
    except Exception:
        bundle = {}
    out = {"run_id": str(row.id), "status": row.status,
           "conversation_id": row.conversation_id, "session_id": row.session_id,
           "covered_ids": [c for c in json.loads(row.covered_ids_json or "[]") if not str(c).startswith("mfp:")],
           "started_at": row.started_at.isoformat() if row.started_at else None,
           "finished_at": row.finished_at.isoformat() if row.finished_at else None}
    if row.status in ("consolidated", "replay_noop", "failed", "empty"):
        out["summary"] = {k: bundle.get(k) for k in (
            "message_count", "new_message_count", "findings", "arc_after",
            "ledger_added", "ledger_counts", "preparation_text", "ms_total", "product", "clock",
            "ledger_witness_items", "ledger_observations", "ledger_agent", "ledger_needs_review", "ledger_fallback", "world_agent", "stage_ms") if k in bundle}
        if "ledger_agent_calls" in bundle:
            out["summary"]["ledger_agent_trace"] = [
                {"finish_reason": c.get("finish_reason"), "trace": c.get("trace")} for c in bundle["ledger_agent_calls"]]
        if "world_agent_calls" in bundle:
            out["summary"]["world_agent_trace"] = [
                {"finish_reason": c.get("finish_reason"), "trace": c.get("trace")} for c in bundle["world_agent_calls"]]
    return out


@router.get("/preparation")
async def preparation(request: Request, workspace_id: str, owner: str, companion_id: Optional[str] = None,
                      db: AsyncSession = Depends(get_async_session)):
    scope = _scope(request, workspace_id, companion_id)
    prep = await memory_pipeline.get_preparation(db, workspace_id=scope.workspace, owner=owner, companion_id=scope.product)
    if prep is None:
        return {"found": False}
    return {"found": True, **prep}


class PrepareRequest(BaseModel):
    workspace_id: str
    owner: str
    companion_id: Optional[str] = None
    time_zone: Optional[str] = None

@router.post("/prepare")
async def prepare_now(req: PrepareRequest, request: Request, db: AsyncSession = Depends(get_async_session)):
    """Compose a fresh preparation now (time or state moved on). Supersedes the
    cached one. Background-worthy; awaited here for operator use."""
    try:
        scope = _scope(request, req.workspace_id, req.companion_id)
        prep = await memory_pipeline.prepare(db, workspace_id=scope.workspace, owner=req.owner,
                                             companion_id=scope.product, time_zone=req.time_zone)
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"prepare_failed:{type(exc).__name__}") from exc
    if not prep.get("text"):
        raise HTTPException(status_code=503, detail="prepare_no_model")
    return {"found": True, "text": prep["text"], "id": prep.get("id"),
            "inputs_fingerprint": prep.get("inputs_fingerprint"), "model": prep.get("model")}


@router.get("/state")
async def state(request: Request, workspace_id: str, owner: str, include_closed: bool = False, companion_id: Optional[str] = None,
                db: AsyncSession = Depends(get_async_session)):
    scope = _scope(request, workspace_id, companion_id)
    return await memory_pipeline.read_state(db, workspace_id=scope.workspace, owner=owner,
                                            include_closed=include_closed, companion_id=scope.product)


@router.get("/ledger")
async def ledger_view(request: Request, workspace_id: str, owner: str, companion_id: Optional[str] = None,
                      view: str = "awareness", period: Optional[str] = None, date_from: Optional[str] = None,
                      date_to: Optional[str] = None, now: Optional[str] = None, time_zone: Optional[str] = None,
                      include_closed: bool = False, db: AsyncSession = Depends(get_async_session)):
    """Deterministic, time-aware views over the maintained ledger. No model, no transcript: interpretation
    happened when the records were written. `view`: awareness (the foreground picture), range (a schedule for a
    period or date span), needs_detail (open matters with an unanswered question). `now` and `time_zone` are the
    caller's authoritative clock; absent, the last zone this person's sittings reported is used."""
    from datetime import datetime as _dt, timedelta as _td, timezone as _tz
    from sqlmodel import select as _select
    from src.models.world import LedgerItem as _L
    from src.services import attention_cycle as _ac, ledger_views as _lv, product_memory as _pm
    scope = _scope(request, workspace_id, companion_id)
    cfg = _pm.get(scope.product)
    tz = time_zone or await _ac.owner_time_zone(db, workspace_id=scope.workspace, owner=owner, default=None) or cfg.default_time_zone
    try:
        clock_now = _dt.fromisoformat(now.replace("Z", "+00:00")) if now else _dt.now(_tz.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="now must be an ISO timestamp")
    rows = (await db.execute(_select(_L).where(_L.honcho_workspace_id == scope.workspace, _L.owner_peer_id == owner)
                             .order_by(_L.created_at.desc()).limit(500))).scalars().all()
    data = [{"key": i.situation_key, "kind": i.kind, "title": i.title, "status": i.status,
             "expected_date": i.expected_date.strftime("%Y-%m-%d") if i.expected_date else None,
             "expected_time": i.expected_time, "time_basis": i.time_basis, "time_zone": i.time_zone, "time_role": i.time_role, "importance": i.importance,
             "waiting_on": i.waiting_on, "question": i.question_text, "detail": i.detail,
             "updated_at": i.updated_at.isoformat() if i.updated_at else None,
             "created_at": i.created_at.isoformat() if i.created_at else None} for i in rows]
    v = _lv.compute(data, clock_now, tz, cfg.default_time_zone)
    base = {"product": scope.product, "now": v["now"].isoformat(), "time_zone": v["zone"].key,
            "pending_consolidations": await memory_pipeline.pending_runs(db, scope.workspace, owner)}
    if view == "awareness":
        return {**base, "text": _lv.render(v), "cues": _lv.cues(v)}
    if view == "needs_detail":
        flagged = [c for c in _lv.cues(v) if c["band"] not in ("older",)]
        by_key = {d["key"]: d for d in data}
        out = [c for c in flagged if by_key.get(c["key"], {}).get("question")
               or (by_key.get(c["key"], {}).get("time_role") == "happens" and by_key[c["key"]].get("expected_date") and not by_key[c["key"]].get("expected_time"))]
        return {**base, "cues": out, "text": "\n".join(f"- {c['line']}" for c in out)}
    if view == "range":
        try:
            if date_from or date_to:
                start = _dt.strptime((date_from or date_to)[:10], "%Y-%m-%d").date()
                end = _dt.strptime((date_to or date_from)[:10], "%Y-%m-%d").date()
            else:
                start, end = _lv.resolve_range(period or "week", v["today"])
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
        if end < start or (end - start).days > 366:
            raise HTTPException(status_code=422, detail="range must be ordered and at most a year")
        out = _lv.render_range(data, start, end, clock_now, tz, include_closed=include_closed, default_zone=cfg.default_time_zone)
        return {**base, "from": start.isoformat(), "to": end.isoformat(), **out}
    raise HTTPException(status_code=422, detail="view must be awareness, range or needs_detail")


def _world_ctx_args(now: Optional[str]):
    from datetime import datetime as _dt, timezone as _tz
    try:
        return _dt.fromisoformat(now.replace("Z", "+00:00")) if now else _dt.now(_tz.utc)
    except ValueError:
        raise HTTPException(status_code=422, detail="now must be an ISO timestamp")


@router.get("/world")
async def world_view(request: Request, workspace_id: str, owner: str, companion_id: Optional[str] = None, view: str = "packet",
                     q: Optional[str] = None, depth: str = "connected", now: Optional[str] = None, time_zone: Optional[str] = None,
                     db: AsyncSession = Depends(get_async_session)):
    """The connected world, read deterministically from maintained records (no model). view: packet (the foreground's overview +
    snapshots of whoever/whatever `q` mentions), overview, entity (q = a name; depth snapshot|connected|deep), inspect (everything,
    with provenance). Disabled deployments answer enabled=false with empty text, so callers can simply inject nothing."""
    from src.config import settings as _s
    from src.services import attention_cycle as _ac, known_world as _kw, product_memory as _pm
    scope = _scope(request, workspace_id, companion_id)
    if not _s.CONNECTED_WORLD_ENABLED:
        return {"enabled": False, "product": scope.product, "overview": "", "mentions": "", "text": "", "shown": []}
    cfg = _pm.get(scope.product)
    if not cfg.world_enabled:
        return {"enabled": False, "product": scope.product, "overview": "", "mentions": "", "text": "", "shown": []}
    pending = await memory_pipeline.pending_runs(db, scope.workspace, owner)
    tz = time_zone or await _ac.owner_time_zone(db, workspace_id=scope.workspace, owner=owner, default=None) or cfg.default_time_zone
    ctx = _kw.Ctx(_world_ctx_args(now), tz, cfg.default_time_zone)
    base = {"enabled": True, "product": scope.product, "now": ctx.now.isoformat(), "time_zone": ctx.tz, "pending_consolidations": pending}
    if view == "packet":
        return {**base, **(await _kw.packet(db, scope.workspace, owner, q or "", ctx, cfg.world_sensitive))}
    if view == "overview":
        text, shown = await _kw.overview_text(db, scope.workspace, owner, ctx, cfg.world_sensitive)
        return {**base, "text": text, "shown": [{"source": a, "ref": b} for a, b in shown]}
    if view == "entity":
        if depth not in ("snapshot", "connected", "deep"):
            raise HTTPException(status_code=422, detail="depth must be snapshot, connected or deep")
        return {**base, **(await _kw.entity_view(db, scope.workspace, owner, q or "", ctx, depth))}
    if view == "inspect":
        return {**base, **(await _kw.inspect(db, scope.workspace, owner))}
    raise HTTPException(status_code=422, detail="view must be packet, overview, entity or inspect")


@router.get("/export")
async def export_owner(request: Request, workspace_id: str, owner: str, companion_id: Optional[str] = None, db: AsyncSession = Depends(get_async_session)):
    """Everything this product holds about this person (memory pipeline + connected understanding), as JSON. See owner_data.NOT_COVERED."""
    from src.services import owner_data
    scope = _scope(request, workspace_id, companion_id)
    owner_data.check_owner_for_product(scope.product, owner)
    return await owner_data.export_owner(db, scope.workspace, owner)


class DeleteRequest(BaseModel):
    workspace_id: str
    owner: str
    companion_id: Optional[str] = None
    confirm: str                    # must equal the owner id: deletion is permanent


@router.post("/delete")
async def delete_owner(req: DeleteRequest, request: Request, db: AsyncSession = Depends(get_async_session)):
    """Permanently delete this product's memory of this person. Requires confirm == owner. Nothing else is touched (other products, other owners)."""
    from src.services import owner_data
    if req.confirm != req.owner:
        raise HTTPException(status_code=422, detail="confirm must equal owner; deletion is permanent")
    scope = _scope(request, req.workspace_id, req.companion_id)
    owner_data.check_owner_for_product(scope.product, req.owner)
    from src.services.memory_pipeline import ConsolidationBusy, owner_lock
    try:
        # Wait out any consolidation in flight for this person, or it would write its results back after the delete.
        async with owner_lock(scope.workspace, req.owner, timeout=120):
            counts = await owner_data.delete_owner(db, scope.workspace, req.owner)
            await db.commit()
    except ConsolidationBusy:
        raise HTTPException(status_code=409, detail="a consolidation for this person is still running; try again shortly")
    async with async_session_maker() as vdb:
        left = await owner_data.residue(vdb, scope.workspace, req.owner)
    return {"deleted": counts, "remaining": left, "not_covered": owner_data.NOT_COVERED,
            "note": "Conversations queued for consolidation before this call can still write new records when they run; the Runtime's own stores and Honcho evidence are separate."}


class ExposureRequest(BaseModel):
    workspace_id: str
    owner: str
    companion_id: Optional[str] = None
    refs: List[Dict[str, str]]
    now: Optional[str] = None


@router.post("/world/exposure")
async def world_exposure(req: ExposureRequest, request: Request, db: AsyncSession = Depends(get_async_session)):
    """The Runtime reports what it actually composed into a packet (exposure, counted once per sitting). Engagement is recorded
    separately by the attention review when the companion raised something or the person answered."""
    from src.config import settings as _s
    from src.services import known_world as _kw
    scope = _scope(request, req.workspace_id, req.companion_id)
    if not _s.CONNECTED_WORLD_ENABLED:
        return {"enabled": False, "recorded": 0}
    n = await _kw.record_exposure(db, scope.workspace, req.owner, req.refs[:50], now=_world_ctx_args(req.now).replace(tzinfo=None))
    await db.commit()
    return {"enabled": True, "recorded": n}


class SoloTickRequest(BaseModel):
    workspace_id: str = "llm-test-agent"
    owner: str = ""
    dry_run: bool = True


@router.post("/solo-tick")
async def solo_tick(req: SoloTickRequest, db: AsyncSession = Depends(get_async_session)):
    """Operator tick: check opportunity eligibility (dry_run), or run one live
    opportunity inline when dry_run=false (bounded, minutes)."""
    from src.services import solo_scheduler
    if not req.owner:
        owners = [o for o in solo_scheduler.config()["owners"]]
        if not owners:
            return {"tick": "no_allowlisted_owners"}
        req = req.model_copy(update={"owner": owners[0]})
    product_scope.clean_workspace(req.workspace_id)       # Sophie-only job: it can never be pointed at another product's namespace
    ok, reason, facts = await solo_scheduler.eligibility(db, workspace_id=req.workspace_id, owner=req.owner)
    out: Dict[str, Any] = {"eligible": ok, "reason": reason, "facts": facts}
    if ok and not req.dry_run:
        out["result"] = await solo_scheduler.offer_once(workspace_id=req.workspace_id, owner=req.owner)
    return out


class IndependentSittingRequest(BaseModel):
    workspace_id: str
    owner: str
    sitting_id: Optional[str] = None
    max_iterations: int = 8
    max_tool_calls: int = 10
    max_model_calls: int = 12
    companion_id: str = "sophie"
    identity: Optional[str] = None      # the companion's own constitution text, supplied by the product/Runtime registry


async def _run_solo(workspace_id: str, owner: str, sitting_id: str, budget: Dict[str, int],
                    companion_id: str = "sophie", identity: Optional[str] = None) -> None:
    try:
        async with async_session_maker() as db:
            try:
                from src.services import exploration
                from src.services.exploration import SoloBudget
                await exploration.run_independent_sitting(
                    db, workspace_id=workspace_id, owner=owner, sitting_id=sitting_id,
                    budget=SoloBudget(max_iterations=min(budget["max_iterations"], 12),
                                      max_tool_calls=min(budget["max_tool_calls"], 15),
                                      max_model_calls=min(budget["max_model_calls"], 20)),
                    companion_id=companion_id, constitution=identity)
            except Exception:
                logger.exception("independent sitting failed for %s %s", owner, sitting_id)
                try:
                    await db.rollback()
                except Exception:
                    pass
    except Exception:
        logger.exception("independent sitting session failed for %s %s", owner, sitting_id)


@router.post("/independent-sitting", status_code=202)
async def independent_sitting(req: IndependentSittingRequest, db: AsyncSession = Depends(get_async_session)):
    """Start one of Sophie's independent sittings (bounded, background). Her
    time is hers: she may explore, ask, read, make — or stop immediately."""
    import uuid as _uuid
    from src.services import companion_work
    product_scope.clean_workspace(req.workspace_id)
    if companion_work.level(req.companion_id, "independent") == "off":
        raise HTTPException(status_code=403, detail=f"independent_sittings_off_for_{req.companion_id}")
    sitting_id = (req.sitting_id or f"solo-{_uuid.uuid4().hex[:8]}").strip() or f"solo-{_uuid.uuid4().hex[:8]}"
    asyncio.create_task(_run_solo(req.workspace_id, req.owner, sitting_id,
                                  {"max_iterations": req.max_iterations, "max_tool_calls": req.max_tool_calls,
                                   "max_model_calls": req.max_model_calls}, req.companion_id, req.identity))
    return {"status": "accepted", "sitting_id": sitting_id,
            "conversation_id": f"solo-{sitting_id}"}


class ReviewRequest(BaseModel):
    workspace_id: str
    owner: str
    lookback_runs: int = 6


@router.post("/review")
async def review_situations(req: ReviewRequest, db: AsyncSession = Depends(get_async_session)):
    """Longitudinal noticing: one model call over open situations + recent
    session findings. Updates, never closes (closes need session evidence)."""
    product_scope.clean_workspace(req.workspace_id)
    try:
        return await memory_pipeline.review(db, workspace_id=req.workspace_id, owner=req.owner,
                                            lookback_runs=max(1, min(req.lookback_runs, 12)))
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"review_failed:{type(exc).__name__}") from exc


class AttentionTickRequest(BaseModel):
    workspace_id: str = "llm-test-agent"
    owner: str = ""
    dry_run: bool = True


@router.post("/attention-tick")
async def attention_tick(req: AttentionTickRequest, db: AsyncSession = Depends(get_async_session)):
    """Operator tick: due-scan + stale review for one owner (dry_run reports
    what would run). The scheduler loop calls the same path unattended."""
    from src.services import attention_cycle
    product_scope.clean_workspace(req.workspace_id)
    if not req.owner:
        owners = [o for o in attention_cycle.tick_config()["owners"]]
        if not owners:
            return {"tick": "no_allowlisted_owners"}
        req = req.model_copy(update={"owner": owners[0]})
    if req.dry_run:
        from datetime import datetime as _dt, timezone as _tz
        from sqlmodel import select as _select
        from src.models.world import AttentionAction as _AA
        rows = (await db.execute(_select(_AA).where(
            _AA.honcho_workspace_id == req.workspace_id, _AA.owner_peer_id == req.owner,
            _AA.state == "pending", _AA.due_at.is_not(None),
            _AA.due_at <= _dt.now(_tz.utc).replace(tzinfo=None)))).scalars().all()
        pending = await attention_cycle.pending_attention(db, workspace_id=req.workspace_id, owner=req.owner)
        last = await attention_cycle.last_review_at(db, workspace_id=req.workspace_id, owner=req.owner)
        return {"dry_run": True, "would_mark_due": [str(r.id) for r in rows],
                "pending": len(pending), "last_review_at": last.isoformat() if last else None}
    return await attention_cycle.tick_once(workspace_id=req.workspace_id, owner=req.owner)


@router.post("/recover")
async def recover_runs(db: AsyncSession = Depends(get_async_session)):
    """Operator recovery: mark orphaned running rows failed (audited). Replay
    sessions normally afterwards — coverage + title-identity make it idempotent."""
    from src.services import memory_pipeline
    try:
        return {"recovered": await memory_pipeline.recover_orphaned_runs(db)}
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"recover_failed:{type(exc).__name__}") from exc
