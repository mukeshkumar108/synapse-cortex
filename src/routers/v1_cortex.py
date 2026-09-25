import logging
import time
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import and_, or_, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session, get_rollback_session
from src.models.commitment_candidate import CommitmentCandidateStatus
from src.services.commitment_candidate_service import CommitmentCandidateService
from src.services.cortex_handshake_service import CortexHandshakeService
from src.services.cortex_packet_service import CortexPacketService
from src.services.cortex_router_service import CortexRouterService
from src.services.working_set_service import WorkingSetService
from src.models.work_item import WorkItem  # noqa: F401  (register metadata for create_all)
from src.models.current_meaning import CurrentMeaning  # noqa: F401  (register metadata for create_all)
from src.runtime_model import get_agenda_adapter
from src.schemas.candidate import ExtractionCandidate
from src.models.expectation import Expectation
from src.models.open_loop import OpenLoop
from src.models.operational_state import (
    CandidateReceipt,
    OccurrenceStatus,
    OperationalStatus,
    RecurringIntention,
    RecurringOccurrence,
)
from sqlmodel import select

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cortex", tags=["cortex"])


handshake_service = CortexHandshakeService()
packet_service = CortexPacketService()
router_service = CortexRouterService()
candidate_service = CommitmentCandidateService()
working_set_service = WorkingSetService()


class WorkingSetRequest(BaseModel):
    workspace_id: str
    session_id: str
    peer_id: Optional[str] = None
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"
    turn_text: str = Field(default="", max_length=4000)
    current_message_id: Optional[str] = None
    posture: Optional[str] = None
    conversational_operation: Optional[str] = None
    director_hints: Optional[Dict[str, Any]] = None


class InitiativeCompletionRequest(BaseModel):
    workspace_id: str
    peer_id: str
    decision_id: str
    occurrence_id: Optional[str] = None
    delivered: bool
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    reason: Optional[str] = None


class CandidateQueryRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=200)
    owner_peer_id: str = Field(min_length=1, max_length=200)
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class CandidateReceiptItem(BaseModel):
    receipt_id: str = Field(min_length=1, max_length=200)
    decision_id: str = Field(min_length=1, max_length=200)
    turn_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=240)
    candidate_version: str = Field(min_length=1, max_length=100)
    stage: Literal["selected", "included_in_context", "generated", "persisted", "surfaced", "delivered", "visible", "user_responded", "resolved", "discarded", "failed"]
    channel: Literal["inbound", "proactive", "voice"]
    occurred_at: datetime
    assistant_message_id: Optional[str] = Field(default=None, max_length=200)
    effect: Optional[Literal["asked", "mentioned", "acted", "none"]] = None

    @model_validator(mode="after")
    def validate_delivery_evidence(self):
        if self.stage in ("generated", "persisted", "delivered", "visible") and not self.assistant_message_id:
            raise ValueError("delivered receipts require assistant_message_id")
        return self


class CandidateReceiptRequest(BaseModel):
    contract_version: Literal["candidate-receipts-v1"] = "candidate-receipts-v1"
    workspace_id: str = Field(min_length=1, max_length=200)
    owner_peer_id: str = Field(min_length=1, max_length=200)
    receipts: List[CandidateReceiptItem] = Field(min_length=1, max_length=50)


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.post("/candidates/query")
async def query_neutral_candidates(
    req: CandidateQueryRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Pure, neutral candidate read. No admission, prompt or ledger writes."""
    rows = (await db.execute(
        select(RecurringOccurrence, RecurringIntention)
        .join(
            RecurringIntention,
            RecurringIntention.id == RecurringOccurrence.recurring_intention_id,
        )
        .where(
            RecurringOccurrence.honcho_workspace_id == req.workspace_id,
            RecurringIntention.honcho_workspace_id == req.workspace_id,
            RecurringIntention.owner_peer_id == req.owner_peer_id,
            RecurringIntention.status == OperationalStatus.ACTIVE,
            RecurringOccurrence.status == OccurrenceStatus.PENDING,
            RecurringOccurrence.asked_at.is_(None),
            RecurringOccurrence.user_day <= req.now.date(),
        )
        .order_by(RecurringOccurrence.user_day, RecurringOccurrence.id)
        .limit(20)
    )).all()
    candidates = []
    for occurrence, intention in rows:
        candidates.append({
            "candidate_id": f"recurring_occurrence:{occurrence.id}",
            "candidate_version": occurrence.updated_at.isoformat(),
            "kind": "unresolved_occurrence",
            "state": occurrence.status.value,
            "eligible": True,
            "not_before": None,
            "expires_at": None,
            "due_at": occurrence.user_day.isoformat(),
            "urgency": 0.7,
            "importance": 0.8,
            "confidence": float(intention.confidence),
            "facts": {
                "title": intention.title,
                "outcome_known": False,
            },
            "provenance": [{
                "source_type": "honcho_message",
                "source_id": occurrence.source_message_id or intention.honcho_message_id,
            }],
        })
    return {
        "contract_version": "candidate-set-v1",
        "generated_at": req.now.isoformat(),
        "candidates": candidates,
    }


@router.post("/candidate-receipts")
async def record_candidate_receipts(
    req: CandidateReceiptRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Append idempotent candidate lifecycle evidence scoped to its owner."""
    accepted = 0
    duplicates = 0
    for item in req.receipts:
        prefix, separator, raw_id = item.candidate_id.partition(":")
        from src.models.attention_candidate import AttentionCandidate, AttentionCandidateStatus
        from src.models.open_loop import OpenLoop
        from src.models.clarification import ClarificationCandidate
        if separator != ":" or prefix not in {"recurring_occurrence", "attention", "open_loop", "clarification"}:
            raise HTTPException(status_code=422, detail="unsupported candidate_id")
        try:
            occurrence_id = __import__("uuid").UUID(raw_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid candidate_id") from exc
        if prefix == "recurring_occurrence":
            owned = (await db.execute(select(RecurringOccurrence).join(RecurringIntention,
                RecurringIntention.id == RecurringOccurrence.recurring_intention_id).where(
                RecurringOccurrence.id == occurrence_id,
                RecurringOccurrence.honcho_workspace_id == req.workspace_id,
                RecurringIntention.honcho_workspace_id == req.workspace_id,
                RecurringIntention.owner_peer_id == req.owner_peer_id,
            ))).scalar_one_or_none()
        else:
            model = {"attention": AttentionCandidate, "open_loop": OpenLoop, "clarification": ClarificationCandidate}[prefix]
            owned = (await db.execute(select(model).where(model.id == occurrence_id,
                model.honcho_workspace_id == req.workspace_id,
                model.owner_peer_id == req.owner_peer_id))).scalar_one_or_none()
        if owned is None:
            raise HTTPException(status_code=404, detail="candidate not found for owner")
        existing_rows = (await db.execute(select(CandidateReceipt).where(or_(
            CandidateReceipt.receipt_id == item.receipt_id,
            and_(
                CandidateReceipt.decision_id == item.decision_id,
                CandidateReceipt.candidate_id == item.candidate_id,
                CandidateReceipt.stage == item.stage,
            ),
        )))).scalars().all()

        def exact_match(existing: CandidateReceipt) -> bool:
            return (
                existing.receipt_id == item.receipt_id
                and existing.decision_id == item.decision_id
                and existing.turn_id == item.turn_id
                and existing.candidate_id == item.candidate_id
                and existing.candidate_version == item.candidate_version
                and existing.honcho_workspace_id == req.workspace_id
                and existing.owner_peer_id == req.owner_peer_id
                and existing.stage == item.stage
                and existing.channel == item.channel
                and existing.occurred_at == _naive_utc(item.occurred_at)
                and existing.assistant_message_id == item.assistant_message_id
                and existing.effect == item.effect
            )

        if existing_rows:
            if any(exact_match(existing) for existing in existing_rows):
                duplicates += 1
                continue
            raise HTTPException(status_code=409, detail="conflicting candidate receipt replay")

        if item.candidate_version != owned.updated_at.isoformat():
            raise HTTPException(status_code=409, detail="stale candidate_version")
        row = CandidateReceipt(
            receipt_id=item.receipt_id,
            decision_id=item.decision_id,
            turn_id=item.turn_id,
            candidate_id=item.candidate_id,
            candidate_version=item.candidate_version,
            honcho_workspace_id=req.workspace_id,
            owner_peer_id=req.owner_peer_id,
            stage=item.stage,
            channel=item.channel,
            occurred_at=_naive_utc(item.occurred_at),
            assistant_message_id=item.assistant_message_id,
            effect=item.effect,
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
            accepted += 1
        except IntegrityError:
            concurrent_rows = (await db.execute(select(CandidateReceipt).where(or_(
                CandidateReceipt.receipt_id == item.receipt_id,
                and_(
                    CandidateReceipt.decision_id == item.decision_id,
                    CandidateReceipt.candidate_id == item.candidate_id,
                    CandidateReceipt.stage == item.stage,
                ),
            )))).scalars().all()
            if any(exact_match(existing) for existing in concurrent_rows):
                duplicates += 1
                continue
            raise HTTPException(status_code=409, detail="conflicting candidate receipt replay")
        if prefix == "attention" and item.stage in ("generated", "delivered") and item.effect == "asked":
            # Asked/generated is NOT a claim of delivery, visibility or response.
            await db.execute(update(AttentionCandidate).where(
                AttentionCandidate.id == owned.id, AttentionCandidate.surfaced_count == 0,
            ).values(surfaced_count=1, last_surfaced_at=_naive_utc(item.occurred_at)))
        if prefix == "clarification" and item.stage in ("generated", "delivered") and item.effect == "asked":
            from src.services.surface_lifecycle import SurfaceRegistry
            await SurfaceRegistry().mark(db, workspace_id=req.workspace_id,
                session_id=owned.honcho_session_id, message_id=item.assistant_message_id,
                key=f"clarification:{owned.id}", now=item.occurred_at)
        if prefix == "recurring_occurrence" and item.stage == "delivered" and item.effect == "asked":
            await db.execute(
                update(RecurringOccurrence)
                .where(
                    RecurringOccurrence.id == occurrence_id,
                    RecurringOccurrence.asked_at.is_(None),
                )
                .values(
                    asked_at=_naive_utc(item.occurred_at),
                    ask_count=RecurringOccurrence.ask_count + 1,
                    updated_at=_naive_utc(item.occurred_at),
                )
            )
    await db.commit()
    return {
        "contract_version": "candidate-receipts-v1",
        "accepted": accepted,
        "duplicates": duplicates,
    }


@router.post("/working-set")
async def get_cortex_working_set(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Bounded per-turn working set (L0 HOT / L1 WARM / L2 COLD refs).

    Consumes the same attention packet / intelligence brief used by the
    proactive path and Inspector; it never builds a second interpretation."""
    started = time.perf_counter()
    packet = await packet_service.compile_attention_packet(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        owner_peer_id=req.peer_id,
    )
    working_set = working_set_service.compile_working_set(
        packet,
        turn_text=req.turn_text,
        current_message_id=req.current_message_id,
        posture=req.posture,
        conversational_operation=req.conversational_operation,
        director_hints=req.director_hints,
    )
    # WS10: per-hop evidence — Cortex-side cost of this foreground fetch,
    # so the runtime/app can attribute waterfall time correctly.
    working_set["metrics"]["cortex_ms"] = round((time.perf_counter() - started) * 1000, 1)
    return working_set


class SessionWorkingSetRequest(BaseModel):
    workspace_id: str
    session_id: str
    peer_id: Optional[str] = None
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"
    product: str = "sophie"
    scene: Optional[Dict[str, Any]] = None


class SessionWorkingSetRefreshRequest(BaseModel):
    workspace_id: str
    session_id: str
    cached_source_version: str


class SurfacingEvent(BaseModel):
    matter_kind: str
    matter_id: str
    outcome: str
    move_key: Optional[str] = None


class SurfacingReportRequest(BaseModel):
    workspace_id: str
    session_id: str
    peer_id: str
    message_id: str
    channel: str = "chat"
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    events: List[SurfacingEvent] = Field(min_length=1, max_length=25)


@router.post("/session-working-set")
async def get_session_working_set(
    req: SessionWorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Disposable session/scene working set compiled from independent views
    (never the foreground packet). Runtime caches it and selects locally per
    turn; recompile only on material change (see refresh). Canonical truth
    stays in Cortex — a stale/corrupt set is discarded, never repaired."""
    from src.services.session_workingset import compile_session_working_set
    started = time.perf_counter()
    artifact = await compile_session_working_set(
        db, workspace_id=req.workspace_id, session_id=req.session_id,
        owner_peer_id=req.peer_id, now=req.now, timezone_str=req.timezone,
        product=req.product, scene=req.scene)
    artifact["metrics"] = {
        "cortex_ms": round((time.perf_counter() - started) * 1000, 1)}
    return artifact


@router.post("/session-working-set/refresh")
async def session_working_set_refresh(
    req: SessionWorkingSetRefreshRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Cheap staleness answer without recompiling."""
    from src.services.session_workingset import needs_refresh
    return await needs_refresh(
        db, workspace_id=req.workspace_id, session_id=req.session_id,
        cached_source_version=req.cached_source_version)


@router.post("/surfacing/report")
async def report_surfacing_outcomes(
    req: SurfacingReportRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Runtime reconciles local surfacing state back in bounded batches:
    surfaced/deferred/dismissed/answered/still-open. Ignored never resolves;
    explicit dismissal outranks silence."""
    from src.services.surfacing import report_back
    return await report_back(
        db, workspace_id=req.workspace_id, session_id=req.session_id,
        owner_peer_id=req.peer_id,
        events=[ev.model_dump() for ev in req.events],
        now=req.now, message_id=req.message_id, channel=req.channel)


@router.post("/background-sweep")
async def run_background_sweep(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Inspect eligible views, diff vs last snapshot, return newly-eligible
    items for the proactive scheduler. No user query needed."""
    from src.services.background_sweep import background_sweep
    return await background_sweep(
        db, workspace_id=req.workspace_id, session_id=req.session_id,
        owner_peer_id=req.peer_id, now=req.now, timezone_str=req.timezone)


async def _compile_session_handover(
    req: WorkingSetRequest,
    db: AsyncSession,
    *,
    evaluation: bool,
):
    """Tiny product-edited session handover (~200-400 tokens).

    One compact foreground object compiled from the same attention packet as
    the working set: what matters for THIS product/person now, what changed,
    what is unresolved, what to avoid. Replaceable derived projection, not
    canonical state; JIT detail stays available via /evidence."""
    from src.services.handover_service import compile_handover

    started = time.perf_counter()
    packet = await packet_service.compile_attention_packet(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        owner_peer_id=req.peer_id,
    )
    # THE LIVE AGENDA: one ranked mixed-semantic artifact compiled from the
    # packet (deterministic facts + cheap async model ranking + deterministic
    # fallback). Read-or-compile: fresh snapshots return instantly; the model
    # refresh never blocks the foreground.
    from src.services.agenda_service import compile_agenda

    agenda_result = await compile_agenda(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id,
        packet=packet, now=req.now, timezone_str=req.timezone,
        adapter=get_agenda_adapter(),
        force=False,  # compile_agenda reconciles cached rank against current eligibility
        schedule_background=not evaluation,
    )
    # FOREGROUND ADMISSION CONTROL: the backend decides what deserves
    # foreground bandwidth. Owed/contractual items are admitted with
    # follow-through ledger state; optional items are held back as capacity.
    from src.services.followthrough_service import compute_admission
    admission = await compute_admission(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id,
        agenda_items=agenda_result.get("items") or [],
        packet=packet, now=req.now, timezone_str=req.timezone,
        current_turn=req.turn_text,
    )
    result = compile_handover(
        packet, product=(req.director_hints or {}).get("product"), now=req.now,
        agenda=agenda_result.get("items"), admission=admission,
        compiled_by=agenda_result.get("compiled_by", "fallback"),
    )
    # Compiling context is not an ask. Only explicit effect receipts update ledgers.
    result["metrics"]["cortex_ms"] = round((time.perf_counter() - started) * 1000, 1)
    if evaluation:
        result["evaluation"] = {
            "mode": "evaluation",
            "effects_rolled_back": True,
            "would_record_asks": [],
        }
    return result


@router.post("/handover")
async def get_session_handover(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    return await _compile_session_handover(req, db, evaluation=False)


@router.post("/handover/evaluate")
async def evaluate_session_handover(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_rollback_session),
):
    """Run the complete handover compiler while rolling DB effects back."""
    return await _compile_session_handover(req, db, evaluation=True)


@router.post("/handover/preview")
async def preview_session_handover(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_rollback_session),
):
    """Live-turn projection with the complete handover logic and zero writes.

    The legacy `/handover` endpoint is preserved for compatibility. Runtime
    uses this preview endpoint so reading context cannot count as asking.
    """
    result = await _compile_session_handover(req, db, evaluation=True)
    result.pop("evaluation", None)
    return result


@router.post("/initiative/tick")
async def initiative_tick(req: WorkingSetRequest, db: AsyncSession = Depends(get_async_session)):
    """PRODUCTION INITIATIVE ENGINE: should Sophie appear unprompted right now?

    Deterministic policy over the live agenda (pressure threshold, quiet
    hours, cadence gap, daily spam budget, ledger). Driven by the app's
    scheduler/cron and by the scenario harness. 'Nothing worth pushing' is a
    first-class outcome."""
    from src.services.initiative_service import evaluate_initiative
    from src.services.handover_service import compile_handover
    from src.services.agenda_service import compile_agenda

    packet = await packet_service.compile_attention_packet(
        db=db, workspace_id=req.workspace_id, session_id=req.session_id,
        now=req.now, timezone_str=req.timezone, owner_peer_id=req.peer_id,
    )
    agenda_result = await compile_agenda(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id,
        packet=packet, now=req.now, timezone_str=req.timezone,
        adapter=get_agenda_adapter(),
    )
    decision = await evaluate_initiative(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id or "",
        agenda=agenda_result.get("items") or [], now=req.now, timezone_str=req.timezone,
    )
    return decision


@router.post("/initiative/complete")
async def initiative_complete(
    req: InitiativeCompletionRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Finalize a reservation after the external delivery outcome is known."""
    from uuid import UUID
    from src.models.operational_state import ProactiveLog, RecurringOccurrence

    try:
        decision_id = UUID(req.decision_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="invalid decision_id") from exc
    row = (await db.execute(select(ProactiveLog).where(
        ProactiveLog.id == decision_id,
        ProactiveLog.honcho_workspace_id == req.workspace_id,
        ProactiveLog.owner_peer_id == req.peer_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="initiative decision not found")
    if row.decision == "reserved":
        row.decision = "appeared" if req.delivered else "failed:delivery"
        if req.reason:
            row.reason = req.reason[:200]
        db.add(row)
    if req.delivered and req.occurrence_id:
        try:
            occurrence_id = UUID(req.occurrence_id)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail="invalid occurrence_id") from exc
        occurrence = (await db.execute(select(RecurringOccurrence).where(
            RecurringOccurrence.id == occurrence_id,
            RecurringOccurrence.honcho_workspace_id == req.workspace_id,
        ))).scalar_one_or_none()
        if occurrence is not None and occurrence.asked_at is None:
            occurrence.asked_at = req.now.astimezone(timezone.utc).replace(tzinfo=None)
            occurrence.ask_count += 1
            db.add(occurrence)
    await db.commit()
    return {"status": row.decision, "decision_id": req.decision_id}


@router.post("/reminders/due")
async def reminders_due(req: WorkingSetRequest, db: AsyncSession = Depends(get_async_session)):
    """PRODUCTION REMINDER EXECUTOR: fire due reminder windows exactly once,
    mark them fired deterministically, and return the due items for delivery.
    Delivery (notification/proactive Sophie message) belongs to the caller."""
    from src.services.reminder_executor import due_reminders
    items = await due_reminders(
        db, workspace_id=req.workspace_id, owner_peer_id=req.peer_id or "", now=req.now,
    )
    return {"due": items, "count": len(items), "now": req.now.isoformat()}


@router.get("/evidence")
async def get_cortex_evidence(
    workspace_id: str = Query(...),
    ref: str = Query(...),
    ref_type: Optional[str] = Query(None),
    peer_id: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_async_session),
):
    """JIT retrieval: resolve a compact working-set reference into its deeper
    stored detail. Bounded, provenance-preserving; raw Honcho message bodies
    stay in Honcho and are resolved by the runtime that owns that client."""
    try:
        row_uuid = __import__("uuid").UUID(ref)
    except ValueError:
        row_uuid = None

    def scoped(model):
        # Mirror packet owner_scope: owner rows are workspace/owner-visible;
        # NULL-owner rows are session-scoped legacy state.
        cond = [model.honcho_workspace_id == workspace_id]
        if peer_id and hasattr(model, "owner_peer_id"):
            from sqlalchemy import or_, and_
            session_cond = (
                model.honcho_session_id == session_id if session_id else None
            )
            cond.append(or_(
                model.owner_peer_id == peer_id,
                and_(model.owner_peer_id.is_(None), session_cond)
                if session_cond is not None else model.owner_peer_id.is_(None),
            ))
        return cond

    found = None
    if row_uuid is not None:
        row = (await db.execute(
            select(Expectation).where(Expectation.id == row_uuid,
                                      *scoped(Expectation))
        )).scalar_one_or_none()
        if row:
            found = {
                "type": "expectation", "id": str(row.id),
                "title": row.title, "summary": row.summary,
                "outcome_state": row.outcome_state.value,
                "expectation_type": row.expectation_type.value,
                "raw_temporal_phrase": row.raw_temporal_phrase,
                "evidence": row.resolution_evidence,
                "honcho_message_id": row.honcho_message_id,
            }
        if found is None:
            row = (await db.execute(
                select(OpenLoop).where(OpenLoop.id == row_uuid,
                                       *scoped(OpenLoop))
            )).scalar_one_or_none()
            if row:
                found = {
                    "type": "open_loop", "id": str(row.id),
                    "title": getattr(row, "title", None),
                    "summary": getattr(row, "summary", None),
                    "status": str(getattr(row, "status", "")),
                    "honcho_message_id": getattr(row, "honcho_message_id", None),
                }
        if found is None:
            row = (await db.execute(
                select(RecurringIntention).where(
                    RecurringIntention.id == row_uuid,
                    *scoped(RecurringIntention))
            )).scalar_one_or_none()
            if row:
                found = {
                    "type": "recurring_intention", "id": str(row.id),
                    "title": row.title, "cadence": row.cadence,
                    "preferred_window": row.preferred_window,
                    "honcho_message_id": row.honcho_message_id,
                }
    if found is None and not ref.startswith("message-"):
        from src.models.commitment_candidate import CommitmentCandidate
        row = (await db.execute(
            select(CommitmentCandidate).where(
                CommitmentCandidate.honcho_workspace_id == workspace_id,
                CommitmentCandidate.candidate_key == ref,
            )
        )).scalar_one_or_none()
        if row is not None:
            found = {
                "type": "commitment_candidate", "id": row.candidate_key,
                "title": row.title, "notes": row.notes,
                "raw_evidence": row.evidence_verbatim,
                "evidence_class": row.evidence_class,
                "status": str(row.status),
            }
    if found is None:
        raise HTTPException(status_code=404, detail="reference not resolvable")
    return found


class HandshakeRequest(BaseModel):
    workspace_id: str
    session_id: str
    peer_id: Optional[str] = None
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"
    last_interaction_time: Optional[datetime] = None
    chronology: Optional[Dict[str, Any]] = None


class RouteRequest(BaseModel):
    query: str


@router.post("/handshake")
async def get_cortex_handshake(
    req: HandshakeRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Compiles deterministic Cortex Handshake.
    Answers: "How should Sophie enter this interaction?"
    """
    return await handshake_service.compile_handshake(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        last_interaction_time=req.last_interaction_time,
        chronology=req.chronology,
        owner_peer_id=req.peer_id,
    )


@router.post("/handshake/evaluate")
async def evaluate_cortex_handshake(
    req: HandshakeRequest,
    db: AsyncSession = Depends(get_rollback_session),
):
    result = await handshake_service.compile_handshake(
        db=db,
        workspace_id=req.workspace_id,
        session_id=req.session_id,
        now=req.now,
        timezone_str=req.timezone,
        last_interaction_time=req.last_interaction_time,
        chronology=req.chronology,
        owner_peer_id=req.peer_id,
    )
    result["evaluation"] = {"mode": "evaluation", "effects_rolled_back": True}
    return result


@router.post("/route")
async def route_cortex_query(req: RouteRequest):
    """
    Routes query to information source (HONCHO_MEMORY, SYNAPSE_STATE, BOTH, CURRENT_SESSION, NO_RETRIEVAL).
    """
    return router_service.route_query(req.query)


@router.get("/attention-packet")
async def get_cortex_attention_packet(
    workspace_id: str = Query(...),
    session_id: str = Query(...),
    peer_id: Optional[str] = Query(None),
    now: Optional[datetime] = Query(None),
    timezone_str: str = Query("UTC", alias="timezone"),
    db: AsyncSession = Depends(get_async_session),
):
    """
    Compiles dynamic, prose-free Attention & Continuity Packet.
    """
    eval_now = now or datetime.now(timezone.utc)
    return await packet_service.compile_attention_packet(
        db=db,
        workspace_id=workspace_id,
        session_id=session_id,
        now=eval_now,
        timezone_str=timezone_str,
        owner_peer_id=peer_id,
    )


@router.get("/attention-packet/evaluate")
async def evaluate_cortex_attention_packet(
    workspace_id: str = Query(...),
    session_id: str = Query(...),
    peer_id: Optional[str] = Query(None),
    now: Optional[datetime] = Query(None),
    timezone_str: str = Query("UTC", alias="timezone"),
    db: AsyncSession = Depends(get_rollback_session),
):
    result = await packet_service.compile_attention_packet(
        db=db,
        workspace_id=workspace_id,
        session_id=session_id,
        now=now or datetime.now(timezone.utc),
        timezone_str=timezone_str,
        owner_peer_id=peer_id,
    )
    result["evaluation"] = {"mode": "evaluation", "effects_rolled_back": True}
    return result


@router.get("/commitment-candidates")
async def list_commitment_candidates(
    workspace_id: str = Query(...),
    owner_peer_id: str = Query(...),
    limit: int = Query(20, ge=1, le=50),
    db: AsyncSession = Depends(get_async_session),
):
    """Bounded listing of derived commitment candidates (Sophie noticed)."""
    rows = await candidate_service.list_pending(
        db, workspace_id=workspace_id, owner_peer_id=owner_peer_id, limit=limit
    )
    return {
        "candidates": [
            {
                "candidate_key": row.candidate_key,
                "canonical_key": row.canonical_key,
                "title": row.title,
                "notes": row.notes,
                "evidence_verbatim": row.evidence_verbatim,
                "evidence_class": row.evidence_class,
                "authority": row.authority.value,
                "source_message_id": row.source_message_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows
        ]
    }


class CurrentMeaningReviseRequest(BaseModel):
    """Live revise-sync. Runtime supplies ONLY: turn + bounded local
    conversation + scope/product (+ optional expected lens version + expected
    prior). Cortex loads prior row + bounded Cortex state itself. Runtime
    never sends lens text or Cortex-owned state."""
    workspace_id: str
    session_id: str
    peer_id: Optional[str] = None
    product: Optional[str] = "sophie"
    expected_lens_version: Optional[str] = None
    message_id: str = Field(min_length=1, max_length=200)
    turn_text: str = Field(default="", max_length=4000)
    recent_conversation: List[Dict[str, str]] = Field(default_factory=list, max_length=6)
    expected_prior_id: Optional[str] = None
    expected_prior_version: Optional[int] = None
    revision_key: Optional[str] = None  # default turn:<message_id>; deep callers pass consolidation:<digest>
    now: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    timezone: str = "Europe/London"


@router.post("/current-meaning/revise-sync")
async def revise_current_meaning_sync(
    req: CurrentMeaningReviseRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Every-turn semantic fast interpretation (Cortex-owned).

    Returns the ephemeral per-turn result; persists a new version ONLY when
    meaning genuinely revised. Fail-closed: any failure → retain prior,
    authority unknown/omitted, render nothing.
    """
    import json as _json
    from src.models.current_meaning import scope_key_for, canonical_owner_peer
    from src.services import current_meaning_service as _cm
    from src.services.meaning_lens import resolve_lens

    product = (req.product or "sophie").lower()
    owner = canonical_owner_peer(req.peer_id)
    scope = {
        "workspace_id": req.workspace_id,
        "product": product,
        "session_id": req.session_id,
        "owner_peer_id": owner,
    }
    scope_key = scope_key_for(req.workspace_id, product, req.session_id, req.peer_id)
    revision_key = req.revision_key or f"turn:{req.message_id}"
    lens = resolve_lens(product)
    lens_mismatch = bool(req.expected_lens_version and req.expected_lens_version != lens.version)

    prior = await _cm.get_active(db, scope_key=scope_key)
    prior_dict = _cm.row_to_dict(prior) if prior else None

    def unchanged_outcome(authority: str, trace_extra: Dict[str, Any]) -> Dict[str, Any]:
        trace = {"lens_version": lens.version, "lens_mismatch": lens_mismatch, **trace_extra}
        return {
            "meaning_revision": "unchanged",
            "foreground_authority": authority,
            "active": prior_dict,
            "revision": None,
            "trace": trace,
        }

    evidence = await _cm.load_cortex_evidence(
        db, workspace_id=req.workspace_id, session_id=req.session_id,
        owner_peer_id=owner, now=req.now,
    )
    history: List[Dict[str, str]] = []
    for item in (req.recent_conversation or [])[-6:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "user")[:20]
        content = str(item.get("content") or "")[:700]
        if content.strip():
            history.append({"role": role, "content": content})

    adapter = get_agenda_adapter()
    started = time.perf_counter()
    raw = await _cm.run_interpreter(
        adapter=adapter,
        system=lens.system,
        prompt=_cm.build_interpreter_prompt(
            lens_system=lens.system, turn_text=req.turn_text, prior=prior_dict,
            history=history, cortex_evidence=evidence,
        ),
    )
    latency_ms = round((time.perf_counter() - started) * 1000, 1)
    if raw is None:
        return unchanged_outcome(
            "unknown_omitted_due_to_interpretation_failure",
            {"reason": "interpreter_unavailable", "latency_ms": latency_ms},
        )
    raw_authority = str(raw.get("foreground_authority") or "").lower()
    if raw_authority not in {"active", "backgrounded"}:
        raw_authority = "active" if raw.get("no_change") is True else "active"
    if raw.get("no_change") is True:
        return unchanged_outcome(raw_authority, {"reason": "interpreter_no_change", "latency_ms": latency_ms})

    proposal = _cm.validate_proposal(raw=raw, turn_text=req.turn_text, prior=prior)
    if proposal is None:
        # Invalid (incl. non-verbatim evidence) or identical → carry, but the
        # interpreter DID answer, so its authority stands (not a failure).
        return unchanged_outcome(raw_authority, {"reason": "validation_carry", "latency_ms": latency_ms})

    result = await _cm.commit_revision(
        db, scope=scope, scope_key=scope_key, revision_key=revision_key,
        source_message_ids=[req.message_id], proposal=proposal,
        lens_version=lens.version, now=req.now,
        expected_prior_id=req.expected_prior_id,
        expected_prior_version=req.expected_prior_version,
    )
    if result["outcome"] == "stale_prior":
        # Authored against the wrong state: discard, never rebase. v1
        # abstains rather than paying for a second call → omit.
        return {
            "meaning_revision": "unchanged",
            "foreground_authority": "unknown_omitted_due_to_interpretation_failure",
            "active": result.get("active"),
            "revision": None,
            "trace": {
                "lens_version": lens.version, "reason": "stale_prior_discarded",
                "latency_ms": latency_ms,
            },
        }
    row = result["row"]
    return {
        "meaning_revision": "revised" if result["outcome"] == "committed" else "unchanged",
        "foreground_authority": proposal["foreground_authority"],
        "active": row,
        "revision": row if result["outcome"] == "committed" else None,
        "trace": {
            "lens_version": lens.version, "reason": result["outcome"],
            "latency_ms": latency_ms, "lens_mismatch": lens_mismatch,
        },
    }


@router.post("/current-meaning/revise-sync/evaluate")
async def evaluate_current_meaning_sync(
    req: CurrentMeaningReviseRequest,
    db: AsyncSession = Depends(get_rollback_session),
):
    """Run the real interpreter and commit path inside a rolled-back txn."""
    result = await revise_current_meaning_sync(req, db)
    trace = result.setdefault("trace", {})
    trace["evaluation"] = True
    trace["effects_rolled_back"] = True
    trace["would_write_revision"] = bool(result.get("revision"))
    return result


@router.get("/current-meaning/active")
async def get_current_meaning_active(
    workspace_id: str = Query(...),
    session_id: str = Query(...),
    peer_id: Optional[str] = Query(None),
    product: str = Query("sophie"),
    db: AsyncSession = Depends(get_async_session),
):
    """Read the retained active row. Authority is per-turn (revise-sync /
    packet), never stored — this endpoint reports belief, not bandwidth."""
    from src.models.current_meaning import scope_key_for
    from src.services import current_meaning_service as _cm

    scope_key = scope_key_for(workspace_id, product, session_id, peer_id)
    row = await _cm.get_active(db, scope_key=scope_key)
    return {"active": _cm.row_to_dict(row) if row else None, "scope_key": scope_key}


class CandidateMarkRequest(BaseModel):
    workspace_id: str
    owner_peer_id: str
    candidate_key: str
    status: Literal["materialized", "dismissed"]
    source_object_id: Optional[str] = None


class CandidateProposal(BaseModel):
    key: str = Field(min_length=1, max_length=160)
    title: str = Field(min_length=1, max_length=280)
    notes: Optional[str] = Field(default=None, max_length=2000)
    evidence_verbatim: str = Field(min_length=1, max_length=2000)
    evidence_class: Literal[
        "implicit_self_commitment", "sophie_proposed_user_accepted",
        "sophie_proposed_soft_acceptance", "vague_self_talk",
    ] = "implicit_self_commitment"
    authority: Literal["act", "ask"] = "ask"
    temporal_phrase: Optional[str] = Field(default=None, max_length=160)


class CandidateProposalRequest(BaseModel):
    workspace_id: str
    session_id: str
    owner_peer_id: str
    source_message_id: str
    candidates: list[CandidateProposal] = Field(max_length=12)


@router.post("/commitment-candidates/propose")
async def propose_commitment_candidates(
    req: CandidateProposalRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Trusted chief-of-staff/editorial proposals. This endpoint only creates
    derived candidates; it never mutates a canonical Task."""
    accepted = []
    for item in req.candidates:
        candidate = ExtractionCandidate(
            candidate_key=item.key,
            observation=item.notes or item.title,
            raw_evidence=item.evidence_verbatim,
            canonical_title=item.title,
            operational_kind="commitment_candidate",
            evidence_class=item.evidence_class,
            authority=item.authority,
            temporal_phrase=item.temporal_phrase,
            actor_peer_id=req.owner_peer_id,
            subject_peer_id=req.owner_peer_id,
            confidence=1.0,
            extractor_version="chief-of-staff-v1",
        )
        row = await candidate_service.upsert_from_candidate(
            db,
            workspace_id=req.workspace_id,
            session_id=req.session_id,
            owner_peer_id=req.owner_peer_id,
            message_id=req.source_message_id,
            candidate=candidate,
            now=datetime.now(timezone.utc),
        )
        if row is not None:
            accepted.append(row.candidate_key)
    return {"status": "accepted", "candidate_keys": accepted}


@router.post("/commitment-candidates/mark")
async def mark_commitment_candidate(
    req: CandidateMarkRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """Durable candidate state transition: materialized (promoted to a
    canonical Task) or dismissed (never re-proposed for the same commitment)."""
    row = await candidate_service.mark(
        db,
        workspace_id=req.workspace_id,
        owner_peer_id=req.owner_peer_id,
        candidate_key=req.candidate_key,
        status=CommitmentCandidateStatus(req.status),
        source_object_id=req.source_object_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="candidate_not_found")
    return {
        "status": "ok",
        "candidate_key": row.candidate_key,
        "candidate_status": row.status.value,
    }


@router.post("/sweeper/run")
async def run_sweeper(
    req: WorkingSetRequest,
    db: AsyncSession = Depends(get_async_session),
):
    """LANE 2 — Honcho-backed discovery sweeper.

    Async, trigger-driven (session settled / turn accumulation / promise
    detected / periodic catch-up). Asks object-shaped semantic questions over
    accumulated Honcho history and promotes evidence-backed durable findings
    through the same deterministic persistence as the real-time lane.
    Idempotent per evidence message. Fail-open: errors are reported, never
    thrown into the caller's turn path.
    """
    from src.services.sweeper_service import SweeperService

    sweeper = SweeperService()
    try:
        result = await sweeper.run(
            db, workspace_id=req.workspace_id, peer_id=req.peer_id,
            session_id=req.session_id, now=req.now,
        )
        return result
    except Exception as err:
        logger.exception("Sweeper run failed")
        return {"status": "error", "detail": str(err)[:300]}


# --- WORK ITEMS: the executable projection of canonical state ---------------


class WorkItemProposal(BaseModel):
    owner: Literal["user", "sophie"]
    action: str = Field(min_length=3, max_length=300)
    importance: float = Field(default=0.5, ge=0.0, le=1.0)
    authority: Optional[Literal["act", "ask", "prepare"]] = None
    due_window_start: Optional[datetime] = None
    due_window_end: Optional[datetime] = None
    completion_condition: Optional[str] = Field(default=None, max_length=300)
    blocker: Optional[str] = Field(default=None, max_length=300)
    sophie_executable: bool = False
    evidence_text: Optional[str] = Field(default=None, max_length=1000)


class WorkItemsPropose(BaseModel):
    workspace_id: str
    session_id: Optional[str] = None
    peer_id: Optional[str] = None
    parent_type: Literal["objective", "commitment", "expectation", "open_loop", "recurrence", "event"]
    parent_id: str = Field(min_length=1, max_length=128)
    parent_title: Optional[str] = Field(default=None, max_length=200)
    source_agent: Literal["planner", "pa_task", "lane2", "app"] = "planner"
    items: list[WorkItemProposal] = Field(min_length=1, max_length=10)


_VALID_PARENT_TYPES = {
    "objective", "commitment", "expectation", "open_loop", "recurrence", "event",
}


@router.post("/work-items/propose")
async def propose_work_items(req: WorkItemsPropose, db: AsyncSession = Depends(get_async_session)):
    """Deterministic commit for agent-proposed actionable work (model proposes,
    code commits). Idempotent per (workspace, parent, owner, normalized action).
    Rejected items are returned with reasons; nothing silently dropped."""
    import re as _re
    from src.models.work_item import WorkItem, WorkOwner, WorkStatus
    from datetime import timedelta

    if req.parent_type not in _VALID_PARENT_TYPES:
        raise HTTPException(status_code=422, detail=f"invalid parent_type {req.parent_type}")

    created, rejected = [], []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for item in req.items:
        notes = []
        action = _re.sub(r"\s+", " ", (item.action or "")).strip()
        if len(action) < 3:
            notes.append("action too short or empty")
        if item.due_window_start and item.due_window_end and item.due_window_end < item.due_window_start:
            notes.append("due window end before start")
        if item.owner == "sophie" and item.sophie_executable and item.authority != "act":
            notes.append("sophie_executable requires authority=act (no claimed execution)")
        due_start = item.due_window_start.replace(tzinfo=None) if item.due_window_start else None
        due_end = item.due_window_end.replace(tzinfo=None) if item.due_window_end else None
        norm_action = action.lower()
        if not notes:
            dup = (await db.execute(text(
                "select id from work_items where honcho_workspace_id = :ws "
                "and parent_id = :pid and owner = :owner and status in ('proposed','surfaced','in_progress') "
                "and lower(action) = :action limit 1"
            ), {"ws": req.workspace_id, "pid": req.parent_id, "owner": item.owner, "action": norm_action})).scalar()
            if dup:
                rejected.append({"action": action, "notes": ["duplicate_of_existing"]})
                continue
        if notes:
            rejected.append({"action": action, "notes": notes})
            continue
        row = WorkItem(
            honcho_workspace_id=req.workspace_id,
            owner_peer_id=req.peer_id or "user",
            honcho_session_id=req.session_id,
            parent_type=req.parent_type,
            parent_id=req.parent_id,
            parent_title=req.parent_title,
            owner=WorkOwner(item.owner),
            action=action,
            status=WorkStatus.PROPOSED.value,
            importance=item.importance,
            authority=item.authority,
            due_window_start=due_start,
            due_window_end=due_end,
            completion_condition=item.completion_condition,
            blocker=item.blocker,
            sophie_executable=item.sophie_executable,
            source_agent=req.source_agent,
            evidence_text=item.evidence_text,
            created_at=now, updated_at=now,
        )
        db.add(row)
        await db.flush()
        created.append({"id": str(row.id), "owner": item.owner, "action": action})
    try:
        await db.commit()
    except Exception as err:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(err)[:200])
    return {"status": "ok", "created": created, "rejected": rejected}


class WorkItemListRequest(BaseModel):
    workspace_id: str
    peer_id: Optional[str] = None
    statuses: Optional[list[Literal["proposed", "surfaced", "in_progress", "done", "cancelled", "superseded"]]] = None
    parent_id: Optional[str] = None


@router.post("/work-items/list")
async def list_work_items(req: WorkItemListRequest, db: AsyncSession = Depends(get_async_session)):
    """Typed read-packet: actionable work by owner, for PA/Task agent and Synapse."""
    from src.models.work_item import WorkItem, WorkStatus
    conds = [WorkItem.honcho_workspace_id == req.workspace_id]
    if req.peer_id:
        conds.append(WorkItem.owner_peer_id == req.peer_id)
    if req.statuses:
        conds.append(WorkItem.status.in_([s for s in req.statuses]))
    if req.parent_id:
        conds.append(WorkItem.parent_id == req.parent_id)
    rows = (await db.execute(select(WorkItem).where(*conds).order_by(WorkItem.importance.desc()))).scalars().all()
    return {
        "items": [
            {
                "id": str(r.id), "parent_type": r.parent_type, "parent_id": r.parent_id,
                "parent_title": r.parent_title, "owner": r.owner, "action": r.action,
                "status": r.status, "importance": r.importance, "authority": r.authority,
                "due_window_start": str(r.due_window_start) if r.due_window_start else None,
                "due_window_end": str(r.due_window_end) if r.due_window_end else None,
                "completion_condition": r.completion_condition, "blocker": r.blocker,
                "sophie_executable": r.sophie_executable, "source_agent": r.source_agent,
            } for r in rows
        ]
    }
