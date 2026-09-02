import logging
import json
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from sqlmodel import select
from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.expectation import Expectation, OutcomeState, ExpectationType
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionStatus
from src.models.attention_candidate import AttentionCandidate, AttentionCandidateStatus
from src.models.clarification import ClarificationCandidate, ClarificationStatus
from src.models.operational_state import (RecurringIntention, RecurringOccurrence,
    ObjectiveProgress, OperationalStatus)
from src.services.expectation_engine import derive_expectation_read_model, derive_temporal_state
from src.services.daypart import resolve_daypart
from src.services.sleep_signal import SleepSignalTracker
from src.services.relational_health import recurrence_week_health, _week_start
from src.services.surface_lifecycle import SurfaceRegistry
from src.services.commitment_candidate_service import CommitmentCandidateService
from src.models.commitment_candidate import CommitmentCandidateAuthority

CURIOSITY_COOLDOWN_SECONDS = 3600
CURIOSITY_MAX_SURFACES = 3
CLARIFICATION_MAX_AGE_HOURS = 168  # 7 days
# Source-linked objects (app tasks, Google Calendar events) surface from
# explicit reminder windows, never from a fixed approaching-deadline rule.
TASK_EVENT_HORIZON_HOURS = 48
EVENT_IMMINENT_MINUTES = 60
REMINDER_SURFACE_MAX = 1
# Ordinary conversational expectations are useful shortly after their window,
# not forever. Historical rows remain inspectable; this only bounds foreground
# and proactive eligibility.
ELAPSED_EXPECTATION_FOREGROUND_HOURS = 36
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
commitment_candidate_service = CommitmentCandidateService()


class CortexPacketService:
    """
    Compiles deterministic, prose-free Attention & Continuity Packets.
    Evaluates dynamic Synapse state (expectations, open loops, suppressions) against `now`.
    Requires 0 LLM calls.
    """

    async def compile_attention_packet(
        self,
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        now: datetime,
        timezone_str: str = "UTC",
        owner_peer_id: str | None = None,
    ) -> Dict[str, Any]:
        def owner_scope(model):
            if not owner_peer_id:
                return model.honcho_session_id == session_id
            return or_(
                model.owner_peer_id == owner_peer_id,
                and_(
                    model.owner_peer_id.is_(None),
                    model.honcho_session_id == session_id,
                ),
            )
        # 1. Fetch active Suppressions
        stmt_supp = select(Suppression).where(
            Suppression.honcho_workspace_id == workspace_id,
            Suppression.honcho_session_id == session_id,
            Suppression.status == SuppressionStatus.ACTIVE,
        )
        res_supp = await db.execute(stmt_supp)
        suppressions = res_supp.scalars().all()

        now_utc = (
            now.astimezone(timezone.utc).replace(tzinfo=None)
            if now.tzinfo else now
        )
        active_suppressions = []
        suppressed_topics: set[str] = set()
        for supp in suppressions:
            if supp.suppressed_until and supp.suppressed_until < now_utc:
                supp.status = SuppressionStatus.EXPIRED
                db.add(supp)
            else:
                active_suppressions.append(supp)
                if supp.topic_or_entity:
                    suppressed_topics.add(supp.topic_or_entity.lower())

        if suppressions != active_suppressions:
            await db.commit()

        # 2. Fetch Expectations
        stmt_exp = select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            owner_scope(Expectation),
            Expectation.superseded_by_id.is_(None),
        ).order_by(Expectation.created_at.desc())
        res_exp = await db.execute(stmt_exp)
        expectations = res_exp.scalars().all()

        followups = []
        window_elapsed_unknown = []
        hard_deadlines = []
        waiting_on = []
        active_expectations = []
        elapsed_expectations = []
        recent_resolutions = []
        source_expectations = []
        suppressed_expectation_ids: set[str] = set()
        suppressed_message_ids: set[str] = set()

        for exp in expectations:
            read_model = derive_expectation_read_model(exp, now)
            # Stale open-ended plans: an UNKNOWN expectation whose window
            # opened >36h ago is days-old narration, not current reality.
            # Open-ended windows never "elapse" on their own, so without this
            # they leak into 'now' and greetings forever (the coffee-shop bug).
            _stale_open = (
                exp.outcome_state == OutcomeState.UNKNOWN
                and read_model["temporal_state"] == "window_open"
                and (now_utc - (exp.expected_window_start or exp.created_at)).total_seconds() > 36 * 3600
            )
            if _stale_open:
                read_model = {**read_model, "temporal_state": "window_elapsed"}

            # Check suppression match
            exp_text = f"{exp.title} {exp.summary}".lower()
            is_suppressed = any(
                supp.surface_scope in ("all_surfaces", "followup_prompt") and (
                (supp.target_type.value == "expectation" and supp.target_id == str(exp.id))
                or (
                    supp.topic_or_entity
                    and any(
                        token in exp_text
                        for token in supp.topic_or_entity.lower().split()
                        if len(token) >= 4
                    )
                ))
                for supp in active_suppressions
            )

            if is_suppressed:
                suppressed_expectation_ids.add(str(exp.id))
                suppressed_message_ids.add(exp.honcho_message_id)
                continue

            # Source-linked objects (app tasks, calendar events) carry their
            # own canonical state; only their resolutions flow through the
            # generic sections. Live state is compiled in dedicated sections.
            if exp.source_system:
                if exp.outcome_state in (OutcomeState.FULFILLED, OutcomeState.CANCELLED):
                    if exp.updated_at >= now_utc - timedelta(hours=72):
                        recent_resolutions.append({
                            "id": str(exp.id),
                            "title": exp.title,
                            "outcome_state": exp.outcome_state.value,
                            "evidence": exp.resolution_evidence,
                        })
                    continue
                if exp.outcome_state == OutcomeState.SUPERSEDED:
                    continue
                source_expectations.append(exp)
                continue

            if exp.outcome_state in (OutcomeState.FULFILLED, OutcomeState.CANCELLED, OutcomeState.SUPERSEDED):
                if exp.updated_at >= now_utc - timedelta(hours=72):
                    recent_resolutions.append({
                        "id": str(exp.id),
                        "title": exp.title,
                        "outcome_state": exp.outcome_state.value,
                        "evidence": exp.resolution_evidence,
                    })
                continue

            if read_model["followup_eligible"]:
                followups.append({
                    "id": str(exp.id),
                    "honcho_message_id": exp.honcho_message_id,
                    "title": exp.title,
                    "summary": exp.summary,
                    "expectation_type": exp.expectation_type.value,
                    "temporal_state": read_model["temporal_state"],
                    "outcome_state": read_model["outcome_state"],
                    "reason": read_model["reason"],
                    "expected_window_label": read_model["expected_window_label"],
                })

            if read_model["temporal_state"] == "window_elapsed":
                window_elapsed_unknown.append({
                    "id": str(exp.id),
                    "title": exp.title,
                    "summary": exp.summary,
                    "raw_temporal_phrase": exp.raw_temporal_phrase,
                    "age_hours": round((now_utc - (exp.expected_window_start or exp.created_at)).total_seconds() / 3600, 1),
                })

            if exp.hard_deadline_at:
                hard_deadlines.append({
                    "id": str(exp.id),
                    "honcho_message_id": exp.honcho_message_id,
                    "title": exp.title,
                    "hard_deadline_at": exp.hard_deadline_at.isoformat(),
                    "temporal_state": read_model["temporal_state"],
                })

            if exp.expectation_type == ExpectationType.EXTERNAL_DEPENDENCY:
                waiting_on.append({
                    "id": str(exp.id),
                    "actor": exp.subject_peer_id,
                    "title": exp.title,
                    "summary": exp.summary,
                })

            if exp.raw_temporal_phrase or exp.hard_deadline_at:
                item_dict = {
                    "id": str(exp.id),
                    "honcho_message_id": exp.honcho_message_id,
                    "title": exp.title,
                    "summary": exp.summary,
                    "expectation_type": exp.expectation_type.value,
                    "temporal_state": read_model["temporal_state"],
                    "outcome_state": read_model["outcome_state"],
                    "reason": read_model["reason"],
                    "expected_window_label": read_model["expected_window_label"],
                    "raw_temporal_phrase": exp.raw_temporal_phrase,
                    "age_hours": round((now_utc - exp.created_at).total_seconds() / 3600, 1),
                }
                if read_model["temporal_state"] in (
                    "window_elapsed", "deadline_passed"
                ):
                    elapsed_expectations.append(item_dict)
                else:
                    active_expectations.append(item_dict)

        # 3. Fetch Open Loops
        stmt_loop = select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            owner_scope(OpenLoop),
            OpenLoop.status == OpenLoopStatus.OPEN,
        )
        res_loop = await db.execute(stmt_loop)
        loops = list(res_loop.scalars().all())
        loops.sort(key=lambda loop: loop.created_at, reverse=True)

        open_loops_list = []
        expectations_by_id = {exp.id: exp for exp in expectations}
        for loop in loops:
            age = now_utc - loop.created_at
            explicitly_invited = loop.title == "Invited follow-up"
            linked_active = any(
                exp.id == loop.expectation_id and exp.outcome_state == OutcomeState.UNKNOWN
                for exp in expectations
            )
            # Age changes surfacing eligibility, never historical status.
            if age > timedelta(days=30) or (
                age > timedelta(days=7) and not explicitly_invited and not linked_active
            ):
                continue
            is_suppressed = any(
                supp.surface_scope in ("all_surfaces", "followup_prompt") and (
                (supp.target_type.value == "open_loop" and supp.target_id == str(loop.id))
                or (
                    supp.topic_or_entity
                    and (
                        supp.topic_or_entity.lower() in loop.title.lower()
                        or supp.topic_or_entity.lower() in loop.summary.lower()
                    )
                ))
                for supp in active_suppressions
            ) or (loop.expectation_id is not None and str(loop.expectation_id) in suppressed_expectation_ids) \
                or loop.honcho_message_id in suppressed_message_ids
            if not is_suppressed:
                linked_expectation = expectations_by_id.get(loop.expectation_id)
                open_loops_list.append({
                    "id": str(loop.id),
                    "honcho_message_id": loop.honcho_message_id,
                    "title": (
                        (linked_expectation.title if linked_expectation else loop.summary)
                        if loop.title == "Invited follow-up"
                        else loop.title
                    ),
                    "summary": (
                        linked_expectation.summary
                        if linked_expectation and loop.summary.startswith("honcho_message:")
                        else loop.summary
                    ),
                    "expectation_id": str(loop.expectation_id) if loop.expectation_id else None,
                    "explicitly_invited": explicitly_invited,
                })

        # 4. Fetch grounded Sophie-side attention. Candidates are permission to
        # carry something, never an instruction to say it now. Source-linked
        # attention (e.g. bounded post-event follow-up opportunities) is
        # owner-scoped and remains visible across that owner's chats.
        attention_session_scope = AttentionCandidate.honcho_session_id == session_id
        if owner_peer_id:
            attention_session_scope = or_(
                attention_session_scope,
                and_(
                    AttentionCandidate.owner_peer_id.is_not(None),
                    AttentionCandidate.owner_peer_id == owner_peer_id,
                ),
            )
        stmt_attention = select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == workspace_id,
            attention_session_scope,
            AttentionCandidate.status == AttentionCandidateStatus.ACTIVE,
        )
        res_attention = await db.execute(stmt_attention)
        attention_rows = list(res_attention.scalars().all())
        active_attention = []
        for candidate in attention_rows:
            if candidate.expires_at and candidate.expires_at < now_utc:
                candidate.status = AttentionCandidateStatus.EXPIRED
                candidate.updated_at = now_utc
                db.add(candidate)
                continue
            if candidate.not_before and candidate.not_before > now_utc:
                continue
            active_attention.append(candidate)
        if len(active_attention) != len(attention_rows):
            await db.commit()
        active_attention.sort(
            key=lambda item: (-item.salience, -item.confidence, item.created_at)
        )
        sophie_attention = [
            {
                "id": str(item.id),
                "type": item.kind.value,
                "content": item.content,
                "salience": item.salience,
                "confidence": item.confidence,
                "evidence_refs": [
                    ref for ref in (
                        item.source_message_id,
                        item.source_assistant_message_id,
                    ) if ref
                ],
                "surfaced_count": item.surfaced_count,
                **(
                    {
                        "source_system": item.source_system,
                        "source_object_id": item.source_object_id,
                    }
                    if item.source_system
                    else {}
                ),
            }
            for item in active_attention[:5]
        ]

        temporal_priority = {
            "deadline_passed": 0,
            "window_elapsed": 1,
            "deadline_approaching": 2,
            "window_open": 3,
            "not_due": 4,
        }
        # Stale/elapsed items must not crowd current and future state out of
        # the capped foreground lists. Elapsed unknowns are reported through
        # `window_elapsed_unknown` and the brief's unresolved/review horizons;
        # followups and active_expectations carry only live temporal state.
        followups = [
            item for item in followups
            if item.get("temporal_state")
            not in ("window_elapsed", "deadline_passed")
        ]
        followups.sort(
            key=lambda item: (
                temporal_priority.get(item.get("temporal_state", ""), 9),
                item.get("title", ""),
            )
        )
        hard_deadlines.sort(
            key=lambda item: (
                temporal_priority.get(item.get("temporal_state", ""), 9),
                item.get("hard_deadline_at", ""),
            )
        )
        active_expectations.sort(
            key=lambda item: (
                temporal_priority.get(item.get("temporal_state", ""), 9),
                item.get("title", ""),
            )
        )
        elapsed_expectations.sort(
            key=lambda item: (
                temporal_priority.get(item.get("temporal_state", ""), 9),
                item.get("title", ""),
            )
        )

        try:
            from zoneinfo import ZoneInfo
            user_day = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now).astimezone(ZoneInfo(timezone_str)).date()
        except Exception:
            user_day = now_utc.date()
        recurrences = (await db.execute(select(RecurringIntention).where(
            RecurringIntention.honcho_workspace_id == workspace_id,
            owner_scope(RecurringIntention),
            RecurringIntention.status == OperationalStatus.ACTIVE,
        ).order_by(RecurringIntention.updated_at.desc()))).scalars().all()
        week_start = _week_start(user_day)
        week_occurrences = (await db.execute(select(RecurringOccurrence).where(
            RecurringOccurrence.recurring_intention_id.in_([r.id for r in recurrences[:8]]),
            RecurringOccurrence.user_day >= week_start,
            RecurringOccurrence.user_day <= user_day,
        ))).scalars().all()
        occurrences_by_intention: dict = {}
        for occurrence in week_occurrences:
            occurrences_by_intention.setdefault(str(occurrence.recurring_intention_id), []).append(occurrence)
        recurring_items = []
        for recurrence in recurrences[:8]:
            occurrence = (await db.execute(select(RecurringOccurrence).where(
                RecurringOccurrence.recurring_intention_id == recurrence.id,
                RecurringOccurrence.user_day == user_day,
            ))).scalar_one_or_none()
            if occurrence is None and recurrence.status == OperationalStatus.ACTIVE and recurrence.semantic_type != "observed_pattern":
                # Deterministic daily occurrence: every active actionable
                # recurrence owes today a row. Concurrent handover requests can
                # race here; the loser re-reads instead of failing.
                occurrence = RecurringOccurrence(
                    recurring_intention_id=recurrence.id,
                    honcho_workspace_id=recurrence.honcho_workspace_id,
                    user_day=user_day,
                )
                db.add(occurrence)
                try:
                    await db.flush()
                except Exception:
                    await db.rollback()
                    occurrence = (await db.execute(select(RecurringOccurrence).where(
                        RecurringOccurrence.recurring_intention_id == recurrence.id,
                        RecurringOccurrence.user_day == user_day,
                    ))).scalars().first()
            health = recurrence_week_health(
                recurrence, occurrences_by_intention.get(str(recurrence.id), []), user_day
            )
            recurring_items.append({
                "id": str(recurrence.id), "title": recurrence.title,
                "cadence": recurrence.cadence, "preferred_window": recurrence.preferred_window,
                "semantic_type": recurrence.semantic_type,
                "target_amount": recurrence.target_amount, "target_unit": recurrence.target_unit,
                "user_day": user_day.isoformat(),
                "occurrence_status": occurrence.status.value if occurrence else "pending",
                "occurrence_id": str(occurrence.id) if occurrence else None,
                "ask_count": occurrence.ask_count if occurrence else 0,
                "asked_at": occurrence.asked_at.isoformat() if occurrence and occurrence.asked_at else None,
                "evidence_ref": recurrence.honcho_message_id,
                **health,
            })
        progress_rows = (await db.execute(select(ObjectiveProgress).where(
            ObjectiveProgress.honcho_workspace_id == workspace_id,
            owner_scope(ObjectiveProgress),
        ).order_by(ObjectiveProgress.created_at.desc()).limit(3))).scalars().all()

        packet = {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "timestamp": now.isoformat(),
            "followups": followups[:8],
            "open_loops": open_loops_list[:5],
            "active_expectations": active_expectations[:12],
            "elapsed_expectations": elapsed_expectations[:12],
            "window_elapsed_unknown": window_elapsed_unknown[:6],
            "hard_deadlines": hard_deadlines[:4],
            "waiting_on": waiting_on[:3],
            "recent_resolutions": recent_resolutions[:3],
            "suppressed_targets": [
                {
                    "id": str(s.id),
                    "target_type": s.target_type.value,
                    "topic_or_entity": s.topic_or_entity,
                    "reason": s.reason,
                    "surface_scope": s.surface_scope,
                    "suppressed_until": s.suppressed_until.isoformat() if s.suppressed_until else None,
                }
                for s in active_suppressions[:5]
            ],
            "important_but_can_wait": [],
            "sophie_attention": sophie_attention,
            "recurring_intentions": recurring_items[:4],
            "recent_progress": [{
                "id": str(item.id), "expectation_id": str(item.expectation_id) if item.expectation_id else None,
                "title": item.title, "amount": item.amount, "unit": item.unit,
                "user_day": item.user_day.isoformat(), "evidence_ref": item.honcho_message_id,
            } for item in progress_rows],
            "relevant_honcho_message_ids": sorted({
                item["honcho_message_id"] for item in followups[:5]
            } | {
                item["honcho_message_id"] for item in open_loops_list[:5]
            }),
        }
        packet["commitments"] = await self._compile_commitments(
            db, workspace_id, session_id, source_expectations, now=now
        )
        packet["events"] = self._compile_events(source_expectations, now=now)
        packet["commitment_candidates"] = await self._compile_commitment_candidates(
            db, workspace_id, owner_peer_id or "", now=now
        )
        packet["intelligence_brief"] = self._compile_intelligence_brief(
            packet, expectations=expectations, now=now,
            timezone_str=timezone_str,
        )
        packet["continuity_context"] = self._compile_continuity_context(
            packet, now=now, timezone_str=timezone_str
        )
        packet["sleep"] = await self._compile_sleep_signal(
            db, workspace_id, session_id, now=now, timezone_str=timezone_str
        )
        packet["attention"] = self._compile_gap_signals(recurring_items)
        packet["curiosity"] = await self._compile_curiosity(
            db, workspace_id, session_id, recurrences[:8], user_day, now
        )
        return packet

    @staticmethod
    def _compile_intelligence_brief(
        packet: Dict[str, Any], *, expectations: List[Expectation],
        now: datetime, timezone_str: str,
    ) -> Dict[str, Any]:
        """Typed, deterministic chief-of-staff read model.

        This is an editorial input, never an instruction to speak or mutate a
        Task. It separates temporal relevance from durable storage so stale
        unknown outcomes remain auditable without occupying every turn.
        """
        try:
            local_now = now.astimezone(ZoneInfo(timezone_str))
        except Exception:
            local_now = now
        now_utc = (
            now.astimezone(timezone.utc).replace(tzinfo=None)
            if now.tzinfo else now
        )
        daypart = resolve_daypart(now, timezone_str)
        horizons: Dict[str, List[Dict[str, Any]]] = {
            "now": [], "today": [], "tomorrow": [], "later": [],
            "unresolved": [], "review_needed": [],
        }
        expectation_by_id = {str(item.id): item for item in expectations}

        def add(bucket: str, item: Dict[str, Any]) -> None:
            if len(horizons[bucket]) < 12:
                horizons[bucket].append(item)

        for item in packet.get("active_expectations", []) + packet.get(
            "elapsed_expectations", []
        ):
            exp = expectation_by_id.get(str(item.get("id")))
            if exp is None:
                continue
            state = str(item.get("temporal_state") or "unknown")
            start = exp.expected_window_start or exp.hard_deadline_at
            end = exp.expected_window_end or exp.hard_deadline_at
            target = start or end
            base = {
                "kind": "expectation",
                "id": str(exp.id),
                "title": exp.title,
                "expectation_type": exp.expectation_type.value,
                "temporal_state": state,
                "outcome_state": exp.outcome_state.value,
                "confidence": exp.extraction_confidence,
                "expected_start": start.isoformat() if start else None,
                "expected_end": end.isoformat() if end else None,
                "evidence_refs": [exp.honcho_message_id],
            }
            if state in ("window_open", "deadline_approaching"):
                add("now", {**base, "suggested_move": "consider"})
            elif state in ("window_elapsed", "deadline_passed"):
                elapsed_from = end or start or exp.updated_at
                if elapsed_from.tzinfo is not None:
                    elapsed_from = elapsed_from.astimezone(timezone.utc).replace(
                        tzinfo=None
                    )
                age = now_utc - elapsed_from
                if state == "deadline_passed" or age <= timedelta(
                    hours=ELAPSED_EXPECTATION_FOREGROUND_HOURS
                ):
                    add("unresolved", {
                        **base,
                        "suggested_move": "ask_outcome_if_natural",
                        "uncertainty": "Outcome is unknown; do not claim failure.",
                    })
                else:
                    add("review_needed", {
                        **base,
                        "suggested_move": "backstage_review",
                        "uncertainty": "Stale unknown outcome; keep out of ordinary foreground context.",
                    })
            elif target:
                try:
                    target_local = target.replace(tzinfo=timezone.utc).astimezone(
                        ZoneInfo(timezone_str)
                    ) if target.tzinfo is None else target.astimezone(ZoneInfo(timezone_str))
                    delta_days = (target_local.date() - local_now.date()).days
                except Exception:
                    delta_days = 2
                add("today" if delta_days == 0 else "tomorrow" if delta_days == 1 else "later", base)

        for item in packet.get("commitments", []):
            state = str(item.get("state") or "open")
            base = {"kind": "task", **item}
            if state in ("overdue", "reminder_due"):
                add("now", base)
            else:
                due_at = item.get("due_at")
                try:
                    due = datetime.fromisoformat(str(due_at))
                    due_local = due.replace(tzinfo=timezone.utc).astimezone(
                        ZoneInfo(timezone_str)
                    ) if due.tzinfo is None else due.astimezone(ZoneInfo(timezone_str))
                    delta_days = (due_local.date() - local_now.date()).days
                except Exception:
                    delta_days = 2
                add("today" if delta_days == 0 else "tomorrow" if delta_days == 1 else "later", base)

        for item in packet.get("events", []):
            state = str(item.get("state") or "upcoming")
            if state in ("imminent", "ongoing"):
                bucket = "now"
            else:
                try:
                    start = datetime.fromisoformat(str(item.get("start_at")))
                    start_local = start.replace(tzinfo=timezone.utc).astimezone(
                        ZoneInfo(timezone_str)
                    ) if start.tzinfo is None else start.astimezone(ZoneInfo(timezone_str))
                    delta_days = (start_local.date() - local_now.date()).days
                except Exception:
                    delta_days = 2
                bucket = "today" if delta_days == 0 else "tomorrow" if delta_days == 1 else "later"
            add(bucket, {"kind": "event", **item})

        for item in packet.get("recurring_intentions", []):
            if item.get("occurrence_status") != "pending":
                continue
            preferred = str(item.get("preferred_window") or "").lower()
            window_matches = not preferred or daypart in preferred
            base = {
                "kind": "recurring_intention", **item,
                "uncertainty": "Pending means no completion evidence, not proof it was missed.",
            }
            if window_matches:
                add("now", {**base, "suggested_move": "consider"})
            elif preferred and daypart in ("afternoon", "evening") and "morning" in preferred:
                add("unresolved", {**base, "suggested_move": "ask_outcome_if_natural"})
            else:
                add("today", base)

        return {
            "version": "continuity-brief-v1",
            "generated_at": now.isoformat(),
            "user_day": local_now.date().isoformat(),
            "daypart": daypart,
            "horizons": horizons,
            "task_candidates": packet.get("commitment_candidates", [])[:8],
            "open_threads": packet.get("open_loops", [])[:8],
            # Non-source Sophie attention remains backstage. It may inform an
            # active user-led conversation but cannot independently trigger
            # proactive outreach or a daily brief.
            "backstage_attention": packet.get("sophie_attention", [])[:8],
            "constraints": {
                "unknown_is_not_failed": True,
                "brief_is_permission_not_instruction": True,
                "canonical_tasks_require_authority": True,
            },
        }

    @staticmethod
    @staticmethod
    def _parse_reminder_windows(exp: Expectation) -> List[Dict[str, Any]]:
        if not exp.reminder_windows_json:
            return []
        try:
            windows = json.loads(exp.reminder_windows_json)
        except (TypeError, ValueError):
            return []
        if not isinstance(windows, list):
            return []
        return [window for window in windows if isinstance(window, dict)]

    @staticmethod
    async def _compile_commitments(
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        source_expectations: List[Expectation],
        *,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        """App-owned task commitments, evaluated against explicit reminder
        windows and the canonical due date. States:
        reminder_due > overdue > upcoming. Reminder surfacing is bounded by
        the surface registry (one surfacing per reminder window per session).
        """
        now_utc = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
        registry = SurfaceRegistry()
        message_id = f"packet:{int(now_utc.timestamp())}"
        items: List[Dict[str, Any]] = []
        for exp in source_expectations:
            if exp.source_system != "app_task":
                continue
            windows = CortexPacketService._parse_reminder_windows(exp)
            active_window = None
            next_window = None
            for window in windows:
                try:
                    start = datetime.fromisoformat(window["start"])
                except (KeyError, TypeError, ValueError):
                    continue
                end = (
                    datetime.fromisoformat(window["end"])
                    if window.get("end")
                    else None
                )
                if start <= now_utc and (end is None or end >= now_utc):
                    active_window = {**window, "start": start, "end": end}
                elif start > now_utc and (
                    next_window is None or start < next_window["start"]
                ):
                    next_window = {**window, "start": start, "end": end}
            due_at = exp.hard_deadline_at
            overdue = bool(due_at and now_utc > due_at)
            # Overdue outranks an open reminder window: past the due date the
            # honest state is 'overdue', not 'reminder_due'.
            if overdue:
                state = "overdue"
            elif active_window is not None:
                state = "reminder_due"
            else:
                state = "upcoming"
            reminder_surfaced = False
            if active_window is not None:
                window_key = f"task_reminder:{exp.source_object_id}:{active_window['start'].isoformat()}"
                window_end = active_window.get("end")
                cooldown = (
                    max(60, int((window_end - active_window["start"]).total_seconds()))
                    if window_end
                    else 86_400
                )
                outcome = await registry.mark(
                    db,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    message_id=message_id,
                    key=window_key,
                    now=now,
                    cooldown_seconds=cooldown,
                    max_count=REMINDER_SURFACE_MAX,
                )
                # 'allowed' = first surfacing of this window; 'cooldown'/'maxed'
                # keep the task visible without re-nagging the reminder line.
                reminder_surfaced = outcome != "allowed"
            items.append({
                "id": str(exp.id),
                "source_system": exp.source_system,
                "source_object_id": exp.source_object_id,
                "source_version": exp.source_version,
                "title": exp.title,
                "due_at": due_at.isoformat() if due_at else None,
                "state": state,
                "active_reminder": (
                    {
                        "start": active_window["start"].isoformat(),
                        "end": active_window["end"].isoformat() if active_window.get("end") else None,
                        "label": active_window.get("label"),
                    }
                    if active_window
                    else None
                ),
                "next_reminder": (
                    {
                        "start": next_window["start"].isoformat(),
                        "end": next_window["end"].isoformat() if next_window.get("end") else None,
                        "label": next_window.get("label"),
                    }
                    if next_window
                    else None
                ),
                "reminder_surfaced": reminder_surfaced,
                "created_at": exp.created_at.isoformat(),
            })
        priority = {"reminder_due": 0, "overdue": 1, "upcoming": 2}
        items.sort(
            key=lambda item: (
                priority.get(item["state"], 9),
                item.get("due_at") or "9999",
            )
        )
        return items[:6]

    @staticmethod
    def _compile_events(
        source_expectations: List[Expectation], *, now: datetime
    ) -> List[Dict[str, Any]]:
        """Google Calendar events referenced by identity. States:
        imminent > ongoing > upcoming. Past events are not listed; bounded
        post-event follow-up flows through source-linked callback attention.
        """
        now_utc = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
        items: List[Dict[str, Any]] = []
        horizon = timedelta(hours=TASK_EVENT_HORIZON_HOURS)
        for exp in source_expectations:
            if exp.source_system != "google_calendar":
                continue
            start = exp.expected_window_start
            end = exp.expected_window_end
            if start is None:
                continue
            if start > now_utc + horizon:
                continue
            if end is not None and end < now_utc - timedelta(hours=24):
                continue
            if start <= now_utc and (end is None or end >= now_utc):
                state = "ongoing"
            elif start > now_utc and (start - now_utc) <= timedelta(
                minutes=EVENT_IMMINENT_MINUTES
            ):
                state = "imminent"
            elif start > now_utc:
                state = "upcoming"
            else:
                state = "past"
            items.append({
                "id": str(exp.id),
                "source_system": exp.source_system,
                "source_object_id": exp.source_object_id,
                "source_version": exp.source_version,
                "title": exp.title,
                "start": start.isoformat(),
                "end": end.isoformat() if end else None,
                "starts_in_minutes": (
                    int((start - now_utc).total_seconds() // 60)
                    if start > now_utc
                    else 0
                ),
                "state": state,
            })
        priority = {"imminent": 0, "ongoing": 1, "upcoming": 2, "past": 3}
        items.sort(key=lambda item: (priority.get(item["state"], 9), item["start"]))
        return items[:6]

    @staticmethod
    async def _compile_commitment_candidates(
        db: AsyncSession,
        workspace_id: str,
        owner_peer_id: str,
        *,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        """Bounded 'Sophie noticed' surface: derived commitment candidates that
        are concrete enough to bother the user about. Ask-authority only; act
        candidates are materialized by the app, not surfaced. Vague
        background thoughts stay invisible."""
        if not owner_peer_id:
            return []
        rows = await commitment_candidate_service.list_pending(
            db, workspace_id=workspace_id, owner_peer_id=owner_peer_id,
            authority=CommitmentCandidateAuthority.ASK, limit=6,
        )
        return [
            {
                "candidate_key": row.candidate_key,
                "title": row.title,
                "evidence_verbatim": row.evidence_verbatim,
                "evidence_class": row.evidence_class,
                "source_message_id": row.source_message_id,
                "created_at": row.created_at.isoformat(),
            }
            for row in rows[:3]
            if row.evidence_class != "vague_self_talk"
        ]

    @staticmethod
    def _compile_gap_signals(recurring_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Recurrence slippage is expectation/gap/attention intelligence, NOT
        curiosity. It says 'a commitment is slipping'; curiosity says 'there is
        a useful unknown'. They are surfaced separately."
        """
        gaps = [
            {
                "type": "routine_gap",
                "topic": item["title"],
                "reason": "this routine has been slipping this week",
                "progress": item.get("progress_line"),
            }
            for item in recurring_items
            if item.get("slipping")
        ]
        return gaps[:2]

    @staticmethod
    async def _compile_curiosity(
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        recurrences: List[RecurringIntention],
        user_day,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        """Curiosity = useful unknowns, bounded and gated. Sources: pending
        clarifications (an answer is genuinely outstanding), and recurring
        intentions that have existed for a while but have never been observed
        (e.g. 'what their normal morning actually looks like').

        Delivery lifecycle: every admission is marked surfaced in the surface
        registry, which enforces a per-key cooldown and max-count budget so a
        candidate can never nag indefinitely. Clarifications that go stale
        (> CLARIFICATION_MAX_AGE_DAYS) or exhaust their surface budget are
        dismissed (real state transition), not surfaced forever.
        """
        registry = SurfaceRegistry()
        now_native_utc = (
            now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
        )
        message_id = f"packet:{int(now_native_utc.timestamp())}"
        now_naive = now_native_utc
        items: List[Dict[str, Any]] = []

        clarifications = (await db.execute(select(ClarificationCandidate).where(
            ClarificationCandidate.honcho_workspace_id == workspace_id,
            ClarificationCandidate.honcho_session_id == session_id,
            ClarificationCandidate.status == ClarificationStatus.PENDING,
        ).order_by(ClarificationCandidate.created_at.desc()).limit(4))).scalars().all()
        for clarification in clarifications:
            key = f"clarification:{clarification.id}"
            created = clarification.created_at
            if (now_naive - created).total_seconds() / 3600.0 > CLARIFICATION_MAX_AGE_HOURS:
                clarification.status = ClarificationStatus.DISMISSED
                db.add(clarification)
                await registry.resolve(db, workspace_id=workspace_id, session_id=session_id,
                    message_id=message_id, key=key, now=now)
                continue
            outcome = await registry.mark(db, workspace_id=workspace_id, session_id=session_id,
                message_id=message_id, key=key, now=now,
                cooldown_seconds=CURIOSITY_COOLDOWN_SECONDS, max_count=CURIOSITY_MAX_SURFACES)
            if outcome == "cooldown":
                continue
            if outcome == "maxed":
                clarification.status = ClarificationStatus.DISMISSED
                db.add(clarification)
                continue
            items.append({
                "type": "clarification",
                "topic": clarification.description,
                "reason": "an answer is still outstanding",
                "salience": 0.6,
                "not_before": now.isoformat(),
            })
        if clarifications:
            await db.commit()

        for recurrence in recurrences:
            if recurrence.started_at and (now_naive - recurrence.started_at).days >= 3:
                count = (await db.execute(select(func.count()).select_from(RecurringOccurrence).where(
                    RecurringOccurrence.recurring_intention_id == recurrence.id,
                    # Packet compilation creates a pending occurrence as a
                    # deterministic ledger slot. That is not an observation of
                    # the routine; only an occurrence backed by user evidence
                    # closes the "never observed" curiosity.
                    RecurringOccurrence.source_message_id.is_not(None),
                ))).scalar_one()
                if count == 0:
                    key = f"unobserved:{recurrence.id}"
                    outcome = await registry.mark(db, workspace_id=workspace_id, session_id=session_id,
                        message_id=message_id, key=key, now=now,
                        cooldown_seconds=CURIOSITY_COOLDOWN_SECONDS, max_count=CURIOSITY_MAX_SURFACES)
                    if outcome != "allowed":
                        continue
                    items.append({
                        "type": "unobserved_routine",
                        "topic": recurrence.title,
                        "reason": "you don't yet know what their usual times look like for this",
                        "salience": 0.55,
                        "not_before": now.isoformat(),
                    })
        return items[:2]

    @staticmethod
    async def _compile_sleep_signal(
        db: AsyncSession,
        workspace_id: str,
        session_id: str,
        *,
        now: datetime,
        timezone_str: str,
    ) -> Dict[str, Any]:
        """Compact decision-ready sleep signal. Only problem signals surface;
        confidence and the observation ledger stay backstage (promotion role).
        Stale episodes (TTL exceeded) stop surfacing.
        """
        payload = await SleepSignalTracker().read(
            db,
            workspace_id=workspace_id,
            session_id=session_id,
            now=now,
        )
        signal = (payload or {}).get("signal")
        if signal not in ("short_sleep_likely", "unusually_late_night_likely"):
            return {"signal": None}
        return {"signal": signal}

    @staticmethod
    def _compile_continuity_context(
        packet: Dict[str, Any], *, now: datetime, timezone_str: str
    ) -> Dict[str, Any]:
        """Canonical bounded context shared by reactive and proactive callers."""
        daypart = resolve_daypart(now, timezone_str)
        try:
            local_now = now.astimezone(ZoneInfo(timezone_str))
        except Exception:
            local_now = now

        continuity: List[Dict[str, Any]] = []
        brief = packet.get("intelligence_brief") or {}
        has_brief = bool(brief)
        horizons = brief.get("horizons") or {}
        brief_now_ids = {
            str(item.get("id")) for item in horizons.get("now", [])
            if item.get("id")
        }
        brief_unresolved_ids = {
            str(item.get("id")) for item in horizons.get("unresolved", [])
            if item.get("id")
        }
        # Deadlines are highest-value and must be admitted before the five-item cap.
        for item in packet.get("hard_deadlines", [])[:2]:
            temporal_state = item.get("temporal_state") or "unknown"
            if temporal_state not in (
                "deadline_passed", "deadline_approaching", "window_elapsed"
            ):
                continue
            continuity.append({
                "type": "deadline",
                "topic": item.get("title") or "Earlier deadline",
                "status": temporal_state,
                "why_relevant_now": "The recorded deadline makes this relevant now.",
                "evidence_refs": [item.get("honcho_message_id")]
                if item.get("honcho_message_id") else [],
            })
        # Source-linked task/event attention: explicit reminder windows, due
        # dates and event timing outrank generic follow-up inference.
        for item in packet.get("commitments", [])[:3]:
            state = item.get("state")
            if state not in ("overdue", "reminder_due"):
                continue
            if state == "reminder_due" and item.get("reminder_surfaced"):
                continue
            if any(
                str(existing.get("topic", "")).lower()
                == str(item.get("title", "")).lower()
                for existing in continuity
            ):
                continue
            if state == "reminder_due":
                why = "An explicit reminder window for this commitment is open now."
            else:
                why = "This commitment is past its due date and still open."
            continuity.append({
                "type": "task_due",
                "topic": item.get("title") or "Open commitment",
                "status": state,
                "source_system": item.get("source_system"),
                "source_object_id": item.get("source_object_id"),
                "why_relevant_now": why,
                "evidence_refs": [],
            })
        for item in packet.get("events", [])[:2]:
            if item.get("state") not in ("imminent", "ongoing"):
                continue
            if any(
                str(existing.get("topic", "")).lower()
                == str(item.get("title", "")).lower()
                for existing in continuity
            ):
                continue
            why = (
                "This event is happening now."
                if item.get("state") == "ongoing"
                else "This event starts within the hour."
            )
            continuity.append({
                "type": "event_upcoming",
                "topic": item.get("title") or "Calendar event",
                "status": item.get("state"),
                "source_system": item.get("source_system"),
                "source_object_id": item.get("source_object_id"),
                "why_relevant_now": why,
                "evidence_refs": [],
            })
        for item in packet.get("sophie_attention", [])[:5]:
            if item.get("source_system") != "google_calendar":
                continue
            if any(
                str(existing.get("topic", "")).lower()
                == str(item.get("content", "")).lower()
                for existing in continuity
            ):
                continue
            continuity.append({
                "type": "event_followup",
                "topic": item.get("content") or "Recent event",
                "status": "callback_window_open",
                "source_system": item.get("source_system"),
                "source_object_id": item.get("source_object_id"),
                "why_relevant_now": "This event finished recently; a bounded follow-up window is open.",
                "evidence_refs": item.get("evidence_refs") or [],
            })
        # Derived commitment candidates ('Sophie noticed') sit below every
        # canonical fact: they are hypotheses, and context is never a forced
        # question directive — the runtime decides whether to ask.
        for item in packet.get("commitment_candidates", [])[:2]:
            if len(continuity) >= 5:
                break
            if any(
                str(existing.get("topic", "")).lower()
                == str(item.get("title", "")).lower()
                for existing in continuity
            ):
                continue
            continuity.append({
                "type": "commitment_candidate",
                "topic": item.get("title") or "Possible commitment",
                "status": "unconfirmed",
                "candidate_key": item.get("candidate_key"),
                "evidence": item.get("evidence_verbatim"),
                "why_relevant_now": "Sophie noticed a possible commitment; it is unconfirmed.",
                "evidence_refs": [item.get("source_message_id")]
                if item.get("source_message_id") else [],
            })
        for item in packet.get("followups", [])[:3]:
            if has_brief and str(item.get("id")) not in brief_unresolved_ids:
                continue
            temporal_state = item.get("temporal_state") or "unknown"
            topic = item.get("title") or item.get("summary") or "Earlier plan"
            if any(
                str(existing.get("topic", "")).lower() == str(topic).lower()
                for existing in continuity
            ):
                continue
            continuity.append({
                "type": "expectation_due",
                "topic": topic,
                "status": temporal_state,
                "why_relevant_now": item.get("reason") or "A follow-up window is active.",
                "evidence_refs": [item.get("honcho_message_id")]
                if item.get("honcho_message_id") else [],
            })
        for item in packet.get("recurring_intentions", [])[:2]:
            if (
                item.get("occurrence_status") != "pending"
                or (has_brief and str(item.get("id")) not in brief_now_ids)
                or len(continuity) >= 5
            ):
                continue
            continuity.append({
                "type": "recurring_intention",
                "topic": item.get("title") or "Recurring intention",
                "status": "pending_today",
                "why_relevant_now": "This occurrence is pending for the current UserDay.",
                "evidence_refs": [item.get("evidence_ref")] if item.get("evidence_ref") else [],
            })
        seen_topics = {str(item.get("topic", "")).lower() for item in continuity}
        for item in packet.get("active_expectations", [])[:4]:
            if has_brief and str(item.get("id")) not in brief_now_ids:
                continue
            topic = item.get("title") or item.get("summary") or "Earlier plan"
            if str(topic).lower() in seen_topics:
                continue
            temporal_state = item.get("temporal_state") or "unknown"
            if temporal_state not in ("window_open", "deadline_approaching"):
                continue
            continuity.append({
                "type": "expectation_due",
                "topic": topic,
                "status": temporal_state,
                "why_relevant_now": "The recorded time window is active now.",
                "evidence_refs": [item.get("honcho_message_id")]
                if item.get("honcho_message_id") else [],
            })
            seen_topics.add(str(topic).lower())
        open_threads = [
            {
                "type": "open_loop",
                "topic": item.get("title") or item.get("summary") or "Open thread",
                "status": "open",
                "why_relevant_now": "This conversation thread remains unresolved.",
                "explicitly_invited": bool(item.get("explicitly_invited")),
                "evidence_refs": [item.get("honcho_message_id")]
                if item.get("honcho_message_id") else [],
            }
            for item in packet.get("open_loops", [])[:3]
        ]
        sophie_attention = packet.get("sophie_attention", [])[:5]
        recent_resolutions = [
            {
                "topic": item.get("title") or "Resolved thread",
                "status": item.get("outcome_state") or "resolved",
            }
            for item in packet.get("recent_resolutions", [])[:3]
        ]
        avoid_repeating = [
            {
                "topic": item.get("topic_or_entity") or item.get("target_type") or "suppressed topic",
                "reason": item.get("reason") or "The user asked not to surface this.",
                "until": item.get("suppressed_until"),
            }
            for item in packet.get("suppressed_targets", [])[:5]
        ]
        return {
            "now": {
                "local_time": local_now.isoformat(),
                "timezone": timezone_str,
                "daypart": daypart,
            },
            "brief": {
                "version": brief.get("version"),
                "user_day": brief.get("user_day"),
                "daypart": brief.get("daypart"),
                "horizons": {
                    key: (horizons.get(key) or [])[:5]
                    for key in ("now", "today", "tomorrow", "unresolved")
                },
                "task_candidates": (brief.get("task_candidates") or [])[:3],
                "constraints": brief.get("constraints") or {},
            },
            "continuity": continuity[:5],
            "open_threads": open_threads,
            "sophie_attention": sophie_attention,
            "recent_resolutions": recent_resolutions,
            "avoid_repeating": avoid_repeating,
            "relevant_honcho_message_ids": packet.get(
                "relevant_honcho_message_ids", []
            )[:8],
        }
