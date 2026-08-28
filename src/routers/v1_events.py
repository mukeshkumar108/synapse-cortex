import logging
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from src.db import get_async_session
from src.schemas.expectation import TurnEventIngest
from src.schemas.object_state import ObjectStateIngest
from src.services.turn_extractor import TurnExtractor
from src.services.expectation_shaper import ExpectationShaper
from src.services.temporal_grounding import TemporalGrounding
from src.services.persistence import save_expectation_idempotent
from src.services.lifecycle_service import LifecycleService
from src.services.object_lifecycle_service import ObjectLifecycleService
from src.services.operational_state_service import OperationalStateService
from src.services.turn_context import TurnContextAssembler
from src.services.sleep_signal import SleepSignalTracker
from src.models.attention_candidate import (
    AttentionCandidate,
    AttentionCandidateStatus,
    utc_now as attention_utc_now,
)
from src.models.operational_state import ExtractionTrace
from src.schemas.candidate import ExtractionCandidate, ExtractionResult
from sqlmodel import select
from src.schemas.attention_candidate import AttentionCandidatesIngest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/events", tags=["events"])

turn_extractor = TurnExtractor()
expectation_shaper = ExpectationShaper()
temporal_grounder = TemporalGrounding()
lifecycle_service = LifecycleService()
operational_state_service = OperationalStateService()
turn_context_assembler = TurnContextAssembler()
sleep_tracker = SleepSignalTracker()
object_lifecycle_service = ObjectLifecycleService()


def _naive_utc(value: datetime | None) -> datetime | None:
    """Match PostgreSQL TIMESTAMP WITHOUT TIME ZONE columns at the API edge."""
    if value is None or value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


@router.post("/attention", status_code=status.HTTP_202_ACCEPTED)
async def ingest_attention_candidates(
    payload: AttentionCandidatesIngest,
    db: AsyncSession = Depends(get_async_session),
):
    """Persist bounded, provenance-linked Sophie-side attention candidates."""
    created = 0
    for candidate in payload.candidates:
        values = {
            "honcho_workspace_id": payload.workspace_id,
            "honcho_session_id": payload.session_id,
            "source_message_id": payload.source_message_id,
            "source_assistant_message_id": payload.source_assistant_message_id,
            "candidate_key": candidate.key,
            "kind": candidate.kind,
            "content": candidate.content,
            "salience": candidate.salience,
            "confidence": candidate.confidence,
            "not_before": _naive_utc(candidate.not_before),
            "expires_at": _naive_utc(candidate.expires_at),
            "status": AttentionCandidateStatus.ACTIVE,
            "surfaced_count": 0,
            "created_at": attention_utc_now(),
            "updated_at": attention_utc_now(),
        }
        result = await db.execute(
            insert(AttentionCandidate)
            .values(**values)
            .on_conflict_do_nothing(
                constraint="uq_attention_candidate_workspace_source_key"
            )
            .returning(AttentionCandidate.id)
        )
        if result.scalar_one_or_none() is not None:
            created += 1
    await db.commit()
    return {"status": "accepted", "candidates_created": created}


@router.post("/object", status_code=status.HTTP_202_ACCEPTED)
async def ingest_object_state(
    payload: ObjectStateIngest,
    db: AsyncSession = Depends(get_async_session),
):
    """Deterministic projection of canonical external objects (app-owned
    tasks, Google Calendar events) into Cortex lifecycle state.

    Canonical objects live outside Cortex; this endpoint never embeds provider
    objects and never runs extraction. Same-version re-delivery is an idempotent
    no-op; a bumped version supersedes prior state; completion/cancellation
    resolve lifecycle and invalidate stale attention.
    """
    result = await object_lifecycle_service.apply_object_state(db, payload)
    return result


@router.post("/turn", status_code=status.HTTP_202_ACCEPTED)
async def ingest_turn_event(
    payload: TurnEventIngest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Ingests shadow turn event from Sophie/Honcho.
    Executes V4 multi-pass extraction -> shaping -> temporal grounding -> lifecycle mutations -> idempotent persistence.
    """
    # 1. Multi-pass Turn Extraction
    await operational_state_service.sweep(db, workspace_id=payload.workspace_id, now=payload.now)
    await lifecycle_service.apply_reopen_conditions(
        db, workspace_id=payload.workspace_id, session_id=payload.session_id, text=payload.text,
    )
    await sleep_tracker.observe(
        db, workspace_id=payload.workspace_id, session_id=payload.session_id,
        message_id=payload.honcho_message_id, text=payload.text, now=payload.now,
        timezone_str=payload.timezone,
    )
    prior_shapes = (await db.execute(select(ExtractionTrace).where(
        ExtractionTrace.honcho_workspace_id == payload.workspace_id,
        ExtractionTrace.honcho_message_id == payload.honcho_message_id,
        ExtractionTrace.stage == "shape",
    ).order_by(ExtractionTrace.created_at.asc()))).scalars().all()
    if prior_shapes:
        candidates = [ExtractionCandidate(**json.loads(item.detail_json)) for item in prior_shapes]
        extraction_result = ExtractionResult(
            candidates=candidates, backend="trace_replay",
            model=prior_shapes[0].model,
        )
        turn_context: dict = {}
    else:
        turn_context = await turn_context_assembler.assemble(
            db, workspace_id=payload.workspace_id, session_id=payload.session_id,
            peer_id=payload.peer_id, now=payload.now,
            current_message_id=payload.honcho_message_id, current_text=payload.text,
            timezone_str=payload.timezone,
        )
        candidates = turn_extractor.extract_candidates(
            payload.text, peer_id=payload.peer_id, prior_state=turn_context or None,
        )
        extraction_result = turn_extractor.extraction_result(candidates)
    await operational_state_service.trace_result(
        db, workspace_id=payload.workspace_id, session_id=payload.session_id,
        message_id=payload.honcho_message_id, result=extraction_result,
    )
    if not candidates:
        logger.info("No state candidates extracted from turn msg_id=%s", payload.honcho_message_id)
        return {
            "status": "accepted",
            "expectation_created": False,
            "candidates_extracted": 0,
            "extraction_backend": extraction_result.backend,
            "extraction_failure": extraction_result.failure,
            "context": {
                "status": turn_context.get("status"),
                "honcho_status": turn_context.get("honcho_status"),
            } if turn_context else None,
        }

    expectations_created = []
    mutated_ids = []
    operational_mutations = []

    for cand in candidates:
        operational_result = await operational_state_service.apply(
            db, workspace_id=payload.workspace_id, session_id=payload.session_id,
            message_id=payload.honcho_message_id, peer_id=payload.peer_id,
            candidate=cand, now=payload.now, timezone_str=payload.timezone,
        )
        operational_mutations.append(operational_result)
        special_lifecycle = cand.operational_kind in ("recurring_intention", "progress") or str(
            operational_result.get("mutation", "")
        ).startswith(("recurrence_", "occurrence_", "open_loop_"))
        # A. Outcome mutations (fulfilled, cancelled, corrected)
        mutated = [] if special_lifecycle else await lifecycle_service.handle_outcome_mutations(
            db=db,
            workspace_id=payload.workspace_id,
            session_id=payload.session_id,
            message_id=payload.honcho_message_id,
            candidate=cand,
            now=payload.now,
        )
        mutated_ids.extend(mutated)

        # B. Suppressions
        await lifecycle_service.create_suppression_if_needed(
            db=db,
            workspace_id=payload.workspace_id,
            session_id=payload.session_id,
            message_id=payload.honcho_message_id,
            candidate=cand,
            now=payload.now,
            timezone_str=payload.timezone,
        )

        # C. Expectation Shaping & Persistence
        is_replacement_event = bool(
            cand.resolution_hint
            and cand.resolution_hint.get("action") in ("correct", "reschedule")
        )
        existing_objective = None
        if cand.operational_kind == "durable_objective":
            existing_objective = await operational_state_service.match_expectation(
                db, workspace_id=payload.workspace_id, session_id=payload.session_id,
                candidate=cand, peer_id=payload.peer_id,
            )
        shaped_data = None if (is_replacement_event or special_lifecycle or existing_objective) else expectation_shaper.shape_expectation(cand, payload.peer_id)
        expectation_record_id = existing_objective.id if existing_objective else None
        if shaped_data:
            raw_phrase = shaped_data.get("raw_temporal_phrase")
            win_start, win_end, hard_deadline = temporal_grounder.ground_expression(
                raw_phrase=raw_phrase, now=payload.now, timezone_str=payload.timezone
            )
            expectation_record = {
                "honcho_workspace_id": payload.workspace_id,
                "honcho_session_id": payload.session_id,
                "honcho_message_id": payload.honcho_message_id,
                "owner_peer_id": payload.peer_id,
                "candidate_key": f"{shaped_data['candidate_key']}@{cand.extractor_version}",
                "extractor_version": cand.extractor_version,
                "source_start": shaped_data["source_start"],
                "source_end": shaped_data["source_end"],
                "subject_peer_id": shaped_data["subject_peer_id"],
                "expectation_type": shaped_data["expectation_type"],
                "title": shaped_data["title"],
                "summary": shaped_data["summary"],
                "raw_temporal_phrase": raw_phrase,
                "anchor_timezone": payload.timezone,
                "expected_window_start": win_start,
                "expected_window_end": win_end,
                "hard_deadline_at": hard_deadline,
                "extraction_confidence": shaped_data["confidence"],
            }
            exp_model, created = await save_expectation_idempotent(db, expectation_record)
            if created:
                expectations_created.append(exp_model.id)
                expectation_record_id = exp_model.id

        # D. Open Loops
        await lifecycle_service.create_open_loop_if_needed(
            db=db,
            workspace_id=payload.workspace_id,
            session_id=payload.session_id,
            message_id=payload.honcho_message_id,
            owner_peer_id=payload.peer_id,
            candidate=cand,
            expectation_id=expectation_record_id,
            now=payload.now,
            timezone_str=payload.timezone,
        )

        # E. Epistemic & Domain Annotations
        await lifecycle_service.create_epistemic_annotation_if_needed(
            db=db,
            workspace_id=payload.workspace_id,
            session_id=payload.session_id,
            message_id=payload.honcho_message_id,
            candidate=cand,
            expectation_id=expectation_record_id,
        )
        await lifecycle_service.create_domain_annotation_if_needed(
            db=db,
            workspace_id=payload.workspace_id,
            session_id=payload.session_id,
            message_id=payload.honcho_message_id,
            candidate=cand,
        )

    return {
        "status": "accepted",
        "candidates_extracted": len(candidates),
        "expectation_created": len(expectations_created) > 0,
        "expectations_created_count": len(expectations_created),
        "expectation_ids": [str(eid) for eid in expectations_created],
        "mutated_expectation_ids": [str(mid) for mid in mutated_ids],
        "honcho_message_id": payload.honcho_message_id,
        "extraction_backend": extraction_result.backend,
        "operational_mutations": operational_mutations,
        "context": {
            "status": turn_context.get("status"),
            "honcho_status": turn_context.get("honcho_status"),
        } if turn_context else None,
    }
