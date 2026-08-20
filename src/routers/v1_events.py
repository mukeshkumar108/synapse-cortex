import logging
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session
from src.schemas.expectation import TurnEventIngest
from src.services.turn_extractor import TurnExtractor
from src.services.expectation_shaper import ExpectationShaper
from src.services.temporal_grounding import TemporalGrounding
from src.services.persistence import save_expectation_idempotent
from src.services.lifecycle_service import LifecycleService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/events", tags=["events"])

turn_extractor = TurnExtractor()
expectation_shaper = ExpectationShaper()
temporal_grounder = TemporalGrounding()
lifecycle_service = LifecycleService()


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
    candidates = turn_extractor.extract_candidates(payload.text, peer_id=payload.peer_id)
    if not candidates:
        logger.info("No state candidates extracted from turn msg_id=%s", payload.honcho_message_id)
        return {
            "status": "accepted",
            "expectation_created": False,
            "candidates_extracted": 0,
        }

    expectations_created = []
    mutated_ids = []

    for cand in candidates:
        # A. Outcome mutations (fulfilled, cancelled, corrected)
        mutated = await lifecycle_service.handle_outcome_mutations(
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
        shaped_data = None if is_replacement_event else expectation_shaper.shape_expectation(cand, payload.peer_id)
        expectation_record_id = None
        if shaped_data:
            raw_phrase = shaped_data.get("raw_temporal_phrase")
            win_start, win_end, hard_deadline = temporal_grounder.ground_expression(
                raw_phrase=raw_phrase, now=payload.now, timezone_str=payload.timezone
            )
            expectation_record = {
                "honcho_workspace_id": payload.workspace_id,
                "honcho_session_id": payload.session_id,
                "honcho_message_id": payload.honcho_message_id,
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
            candidate=cand,
            expectation_id=expectation_record_id,
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
    }
