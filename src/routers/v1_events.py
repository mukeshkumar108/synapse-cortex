import logging
import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from src.db import get_async_session
from src.schemas.expectation import TurnEventIngest
from src.schemas.object_state import ObjectStateIngest
from src.services.turn_extractor import TurnExtractor
from src.services.expectation_shaper import ExpectationShaper
from src.services.temporal_grounding import TemporalGrounding
from src.models.operational_state import TurnStamp

from src.services.persistence import save_expectation_idempotent, save_fact_idempotent, save_model_entry
from src.services.ownership import resolve_owner
from src.services import entity_service
from src.services.lifecycle_service import LifecycleService
from src.services.object_lifecycle_service import ObjectLifecycleService
from src.services.operational_state_service import OperationalStateService
from src.services.turn_context import TurnContextAssembler
from src.services.sleep_signal import SleepSignalTracker
from src.services.turn_reconciliation import suppress_materialized_duplicates
from src.services.commitment_candidate_service import CommitmentCandidateService
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
commitment_candidate_service = CommitmentCandidateService()


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
            "owner_peer_id": payload.owner_peer_id,
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
            (sqlite_insert if db.bind.dialect.name == "sqlite" else insert)(AttentionCandidate)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["honcho_workspace_id", "source_message_id", "candidate_key"])
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


async def ingest_assistant_turn(db: AsyncSession, payload: TurnEventIngest) -> dict:
    """Narrow assistant/character-turn ingress: promises ONLY, speaker-owned.

    Hard boundaries (defense in depth across extractor + handler):
    - owner is ALWAYS the speaking peer; nothing here can mint user rows;
    - allowed kind: commitment_candidate — enforced here again even if the
      extractor misbehaves (event/open_loop trial sprawled in replay and was
      cut; character facts and loops flow via user-turn extraction instead);
    - create-only: no resolutions, suppressions, clarifications, expectations,
      sweeper arming, sleep tracking or user-active stamps. Lifecycle and
      revision of these rows belongs to later work, acting on both sides'
      evidence — never to ingestion.
    Idempotent per (workspace, message, candidate_key) via the same stores.
    """
    from src.services.turn_extractor import _SELF_OWNED_KINDS

    await operational_state_service.sweep(db, workspace_id=payload.workspace_id, now=payload.now)
    candidates = turn_extractor.extract_assistant_owned(payload.text, peer_id=payload.peer_id)
    mutations = []
    for cand in candidates:
        if cand.operational_kind not in _SELF_OWNED_KINDS:
            mutations.append({"mutation": "assistant_lane_rejected", "kind": cand.operational_kind})
            continue
        row = await commitment_candidate_service.upsert_from_candidate(
            db, workspace_id=payload.workspace_id, session_id=payload.session_id,
            owner_peer_id=payload.peer_id, message_id=payload.honcho_message_id,
            candidate=cand, now=payload.now,
        )
        mutations.append({"mutation": "commitment_candidate_upserted",
                          "candidate_key": row.candidate_key if row else None})
    return {"status": "accepted", "assistant_lane": True,
            "candidates_extracted": len(candidates), "mutations": mutations}


@router.post("/turn", status_code=status.HTTP_202_ACCEPTED)
async def ingest_turn_event(
    payload: TurnEventIngest,
    db: AsyncSession = Depends(get_async_session),
):
    """
    Ingests shadow turn event from Sophie/Honcho.
    Executes V4 multi-pass extraction -> shaping -> temporal grounding -> lifecycle mutations -> idempotent persistence.
    """
    if payload.is_assistant_turn:
        return await ingest_assistant_turn(db=db, payload=payload)
    # Turn stamp: the turn's own timestamp (injectable clock), consumed by
    # the initiative engine's user-recently-active guard.
    stamp_values = {
        "honcho_workspace_id": payload.workspace_id,
        "owner_peer_id": payload.peer_id,
        "honcho_message_id": payload.honcho_message_id,
        "turn_at": _naive_utc(payload.now),
    }
    dialect_name = db.get_bind().dialect.name
    stamp_insert = sqlite_insert if dialect_name == "sqlite" else insert
    await db.execute(
        stamp_insert(TurnStamp).values(**stamp_values).on_conflict_do_nothing(
            index_elements=["honcho_workspace_id", "honcho_message_id"]
        )
    )
    await db.commit()
    # LANE 2 trigger: (re)arm the sweeper debounce/turn-count for this workspace.
    try:
        from src.services.sweeper_triggers import schedule_after_turn
        schedule_after_turn(payload.workspace_id, payload.session_id, payload.peer_id)
    except Exception as err:
        logger.warning("Lane 2 trigger scheduling failed: %s", err)
    # 1. Multi-pass Turn Extraction
    await operational_state_service.sweep(db, workspace_id=payload.workspace_id, now=payload.now)
    await lifecycle_service.apply_reopen_conditions(
        db, workspace_id=payload.workspace_id, session_id=payload.session_id, text=payload.text, owner_peer_id=payload.peer_id,
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
        from src.services.narrow_realtime import NarrowRealtimeExtractor, narrow_mode
        mode = narrow_mode()
        narrow_extractor = None
        if mode in ("shadow", "on"):
            narrow_extractor = getattr(ingest_turn_event, "_narrow_extractor", None)
            if narrow_extractor is None:
                narrow_extractor = NarrowRealtimeExtractor()
                setattr(ingest_turn_event, "_narrow_extractor", narrow_extractor)
        if mode == "on":
            # NARROW REAL-TIME LANE IS PRIMARY: one narrow decision per turn,
            # projected into the EXISTING deterministic commit machinery
            # (shaping, grounding, lifecycle, admission). Open-ended per-turn
            # ontology discovery is retired from the real-time lane; discovery
            # belongs to the async Honcho-backed sweeper (Lane 2).
            narrow_decision = narrow_extractor.classify(
                payload.text, peer_id=payload.peer_id, prior_state=turn_context or None,
                now=payload.now, timezone_str=payload.timezone,
            )
            narrow_candidate = narrow_extractor.to_candidate(narrow_decision)
            candidates = [narrow_candidate] if narrow_candidate is not None else []
            extraction_result = ExtractionResult(
                candidates=candidates,
                observations=[],
                backend="narrow",
                model=narrow_extractor.last_model_used,
                failure=None if narrow_decision.valid else (
                    ";".join(narrow_decision.validation_notes)[:300] or "narrow_decision_invalid"
                ),
            )
            await db.execute(stamp_insert(ExtractionTrace).values(
                honcho_workspace_id=payload.workspace_id,
                honcho_session_id=payload.session_id,
                honcho_message_id=payload.honcho_message_id,
                stage="narrow",
                item_key="narrow",
                status="ok" if narrow_decision.valid else "rejected",
                model=narrow_extractor.last_model_used,
                detail_json=json.dumps(narrow_decision.model_dump(), default=str),
            ))
            await db.commit()
            narrow_shadow_summary = narrow_decision.summary()
        else:
            candidates = turn_extractor.extract_candidates(
                payload.text, peer_id=payload.peer_id, prior_state=turn_context or None,
            )
            extraction_result = turn_extractor.extraction_result(candidates)
    await operational_state_service.trace_result(
        db, workspace_id=payload.workspace_id, session_id=payload.session_id,
        message_id=payload.honcho_message_id, result=extraction_result,
    )
    # Turn speaking stance for identity scoping (Step 3A). One row per turn;
    # replays are idempotent. Scene assembly (3D) consumes these later.
    if extraction_result.frame:
        from src.models.identity import TurnFrame
        existing_frame = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == payload.workspace_id,
            ExtractionTrace.honcho_message_id == payload.honcho_message_id,
            ExtractionTrace.stage == "frame",
        ))).scalar_one_or_none()
        if existing_frame is None:
            db.add(TurnFrame(
                honcho_workspace_id=payload.workspace_id,
                honcho_session_id=payload.session_id,
                honcho_message_id=payload.honcho_message_id,
                frame=extraction_result.frame,
                confidence=extraction_result.frame_confidence,
            ))
            await db.execute(stamp_insert(ExtractionTrace).values(
                honcho_workspace_id=payload.workspace_id,
                honcho_session_id=payload.session_id,
                honcho_message_id=payload.honcho_message_id,
                stage="frame",
                item_key="frame",
                status="ok",
                model=extraction_result.model,
                detail_json=json.dumps({"frame": extraction_result.frame,
                                        "confidence": extraction_result.frame_confidence}),
            ))
            await db.commit()
    # NARROW REAL-TIME CONTRACT (shadow mode). Non-destructive: runs the narrow
    # classifier alongside the current extractor, validates deterministically,
    # and traces the result. It NEVER mutates state or alters the existing
    # pipeline. Cutover is gated on the comparison harness results.
    narrow_shadow_summary: dict | None = None
    from src.services.narrow_realtime import NarrowRealtimeExtractor, narrow_mode
    if narrow_mode() == "shadow":
        try:
            narrow_extractor = getattr(ingest_turn_event, "_narrow_extractor", None)
            if narrow_extractor is None:
                narrow_extractor = NarrowRealtimeExtractor()
                setattr(ingest_turn_event, "_narrow_extractor", narrow_extractor)
            narrow_decision = narrow_extractor.classify(
                payload.text, peer_id=payload.peer_id, prior_state=turn_context or None,
                now=payload.now, timezone_str=payload.timezone,
            )
            await db.execute(stamp_insert(ExtractionTrace).values(
                honcho_workspace_id=payload.workspace_id,
                honcho_session_id=payload.session_id,
                honcho_message_id=payload.honcho_message_id,
                stage="narrow_shadow",
                item_key="narrow",
                status="ok" if narrow_decision.valid else "rejected",
                model=narrow_extractor.last_model_used,
                detail_json=json.dumps(narrow_decision.model_dump(), default=str),
            ))
            await db.commit()
            narrow_shadow_summary = narrow_decision.summary()
        except Exception as err:  # fail-open: shadow never breaks the real path
            logger.warning("Narrow shadow extraction failed: %s", err)
            narrow_shadow_summary = {"error": str(err)[:300]}
    # Fast→slow reconciliation: deterministic suppression of conversation-derived
    # candidates that would duplicate canonical actions already committed from
    # this exact turn by the real-time interpreter. Applied after tracing (so
    # replay re-applies identically) and before any lifecycle mutation.
    candidates, suppressed = suppress_materialized_duplicates(
        candidates, payload.materialized_actions
    )
    # Structural release + due evaluation (deterministic maintenance). Runs
    # even when this turn extracted nothing: later evidence closes loops
    # and passes due conditions regardless of what the current turn says.
    closed_loop_ids: list = []
    violated_ids: list = []
    try:
        closed_loop_ids = await lifecycle_service.close_answered_loops(
            db, workspace_id=payload.workspace_id, session_id=payload.session_id,
            message_id=payload.honcho_message_id, text=payload.text, now=payload.now)
    except Exception as err:
        logger.warning("Loop release failed: %s", err)
    try:
        violated_ids = await commitment_candidate_service.evaluate_due(
            db, workspace_id=payload.workspace_id, now=payload.now)
    except Exception as err:
        logger.warning("Due evaluation failed: %s", err)
    if not candidates:
        logger.info("No state candidates extracted from turn msg_id=%s", payload.honcho_message_id)
        return {
            "status": "accepted",
            "expectation_created": False,
            "candidates_extracted": 0,
            "candidates_suppressed_by_reconciliation": len(suppressed),
            "extraction_backend": extraction_result.backend,
            "extraction_failure": extraction_result.failure,
            "closed_loop_ids": [str(lid) for lid in closed_loop_ids],
            "violated_commitment_ids": [str(vid) for vid in violated_ids],
            "narrow_shadow": narrow_shadow_summary,
            "context": {
                "status": turn_context.get("status"),
                "honcho_status": turn_context.get("honcho_status"),
            } if turn_context else None,
        }

    expectations_created = []
    mutated_ids = []
    operational_mutations = []

    # Bilateral ownership: rows about character-owned content are ownable by
    # the character peer when the extractor attributes to an explicit peer id
    # evidenced in this turn's context. Everything else stays sender-owned.
    evidence_peer_ids = {payload.peer_id}
    for item in (turn_context.get("recent_evidence") or []):
        peer = item.get("peer_id") if isinstance(item, dict) else None
        if peer:
            evidence_peer_ids.add(peer)

    # Naming assertions attach before per-row resolution ("his name is Leo"):
    # the name becomes an alias of the recent role entity.
    turn_frame = extraction_result.frame
    try:
        await entity_service.apply_naming_assertion(
            db, workspace_id=payload.workspace_id, session_id=payload.session_id,
            text=payload.text, message_id=payload.honcho_message_id)
    except Exception as err:
        logger.warning("Naming assertion failed: %s", err)

    for cand in candidates:
        row_owner = resolve_owner(payload.peer_id, cand.actor_peer_id, evidence_peer_ids)

    async def _link_subjects(object_type: str, object_id) -> None:
        try:
            await entity_service.link_candidate_subjects(
                db, workspace_id=payload.workspace_id, session_id=payload.session_id,
                object_type=object_type, object_id=object_id,
                refs=getattr(cand, "subject_refs", None),
                frame=turn_frame, message_id=payload.honcho_message_id)
        except Exception as err:
            logger.warning("Subject linking failed: %s", err)

    for cand in candidates:
        row_owner = resolve_owner(payload.peer_id, cand.actor_peer_id, evidence_peer_ids)
        if cand.clarification_hint:
            # Preserve the existing extractor's uncertainty; no guessed change.
            hint = cand.clarification_hint
            await lifecycle_service._create_clarification(
                db, payload.workspace_id, payload.session_id, payload.honcho_message_id,
                cand, str(hint.get("question") or hint.get("description") or "What did you mean?")[:280],
                [], owner_peer_id=payload.peer_id)
            continue
        # Commitment candidates are derived, fallible proposals: they persist
        # only into the bounded candidate store and never enter the hard lanes.
        if cand.operational_kind == "commitment_candidate":
            candidate_row = await commitment_candidate_service.upsert_from_candidate(
                db, workspace_id=payload.workspace_id, session_id=payload.session_id,
                owner_peer_id=row_owner, message_id=payload.honcho_message_id,
                candidate=cand, now=payload.now,
            )
            operational_mutations.append({
                "mutation": "commitment_candidate_upserted",
                "candidate_key": candidate_row.candidate_key if candidate_row else None,
                "authority": candidate_row.authority.value if candidate_row else None,
                "canonical_key": candidate_row.canonical_key if candidate_row else None,
            })
            if candidate_row is not None:
                await _link_subjects("commitment", candidate_row.id)
            continue

        if (cand.resolution_hint or {}).get("target_kind") in ("attention", "open_loop", "clarification"):
            # One semantic proposal, one lifecycle writer. Do not also create
            # an operational objective from the same resolution evidence.
            mutated_ids.extend(await lifecycle_service.handle_outcome_mutations(
                db=db, workspace_id=payload.workspace_id, session_id=payload.session_id,
                message_id=payload.honcho_message_id, candidate=cand, now=payload.now,
                owner_peer_id=payload.peer_id))
            continue

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
            owner_peer_id=payload.peer_id,
        )
        if special_lifecycle:
            # Progress/completion lanes skip generic outcome mutations (they
            # have their own objective handling) but explicit completions
            # must still resolve the open expectation they complete.
            mutated = await lifecycle_service.resolve_explicit_completions(
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
            owner_peer_id=payload.peer_id,
        )

        # C. Expectation Shaping & Persistence. Settled event content is
        # holder-scoped fact material, never an expectation (shaper rejects
        # the event kind outright); persist it to the fact store instead.
        is_replacement_event = bool(
            cand.resolution_hint
            and cand.resolution_hint.get("action") in ("correct", "reschedule")
        )
        if cand.operational_kind == "event":
            fact_record = {
                "honcho_workspace_id": payload.workspace_id,
                "honcho_session_id": payload.session_id,
                "honcho_message_id": payload.honcho_message_id,
                "owner_peer_id": row_owner,
                "candidate_key": f"{cand.candidate_key}@{cand.extractor_version}",
                "category": cand.domain_tag or "general",
                "title": (cand.canonical_title or cand.observation or "")[:280],
                "evidence_verbatim": (cand.raw_evidence or cand.observation or "")[:2000],
                "formation": cand.formation or "explicit",
                "confidence": cand.confidence,
            }
            if fact_record["title"]:
                fact_row, fact_created = await save_fact_idempotent(db, fact_record)
                operational_mutations.append({
                    "mutation": "fact_recorded" if fact_created else "fact_duplicate",
                    "id": str(fact_row.id),
                })
                await _link_subjects("fact", fact_row.id)
            shaped_data = None
            existing_objective = None
            expectation_record_id = None
        elif cand.operational_kind == "model_claim":
            # User/Character/Relationship Model primitive: durable interpretive
            # belief with evidence trail. Revised by supersession, never
            # fulfilled or violated — no outcome routing touches these rows.
            model_subject_id = None
            if cand.model_kind in ("user", "character", "relationship"):
                for ref in (getattr(cand, "subject_refs", None) or [])[:8]:
                    if not isinstance(ref, str) or not ref.strip():
                        continue
                    ent, status = await entity_service.resolve_mention(
                        db, workspace_id=payload.workspace_id, session_id=payload.session_id,
                        mention=ref, frame=turn_frame, message_id=payload.honcho_message_id)
                    if ent is not None and status in ("linked", "provisioned"):
                        model_subject_id = ent.id
                        break
                entry, entry_created = await save_model_entry(db, {
                    "honcho_workspace_id": payload.workspace_id,
                    "honcho_session_id": payload.session_id,
                    "honcho_message_id": payload.honcho_message_id,
                    "owner_peer_id": row_owner,
                    "subject_entity_id": model_subject_id,
                    "model_kind": cand.model_kind,
                    "claim": (cand.observation or "")[:2000],
                    "evidence_verbatim": (cand.raw_evidence or cand.observation or "")[:2000],
                    "formation": cand.formation or "explicit",
                    "confidence": cand.confidence,
                })
                operational_mutations.append({
                    "mutation": "model_entry_recorded" if entry_created else "model_entry_duplicate",
                    "id": str(entry.id),
                })
                await _link_subjects("model_entry", entry.id)
            shaped_data = None
            existing_objective = None
            expectation_record_id = None
        else:
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
                "owner_peer_id": row_owner,
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
                "formation": shaped_data.get("formation") or "explicit",
                "effective_at": win_start or _naive_utc(payload.now),
                # Semantic reminder proposal from the interpreter (validated
                # downstream against a grounded window); never raw-text regex.
                "reminder_requested": cand.reminder_request,  # None = model omitted: deterministic default applies at persistence
            }
            exp_model, created = await save_expectation_idempotent(
                db, expectation_record, grounding_now=payload.now
            )
            if created:
                expectations_created.append(exp_model.id)
                expectation_record_id = exp_model.id
                await _link_subjects("expectation", exp_model.id)
                # Belief reconciliation: the new expectation is the current
                # belief about its plan; stale sibling UNKNOWN rows describing
                # the same plan are superseded onto it (preserved as evidence).
                await lifecycle_service.reconcile_new_expectation(
                    db, expectation=exp_model, now=payload.now,
                )

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

    # Structural release + due evaluation ran earlier (before the empty
    # extraction early-return) so later evidence always gets its turn.
    return {
        "status": "accepted",
        "candidates_extracted": len(candidates),
        "candidates_suppressed_by_reconciliation": len(suppressed),
        "expectation_created": len(expectations_created) > 0,
        "expectations_created_count": len(expectations_created),
        "expectation_ids": [str(eid) for eid in expectations_created],
        "mutated_expectation_ids": [str(mid) for mid in mutated_ids],
        "closed_loop_ids": [str(lid) for lid in closed_loop_ids],
        "violated_commitment_ids": [str(vid) for vid in violated_ids],
        "honcho_message_id": payload.honcho_message_id,
        "extraction_backend": extraction_result.backend,
        "operational_mutations": operational_mutations,
        "narrow_shadow": narrow_shadow_summary,
        "context": {
            "status": turn_context.get("status"),
            "honcho_status": turn_context.get("honcho_status"),
        } if turn_context else None,
    }
