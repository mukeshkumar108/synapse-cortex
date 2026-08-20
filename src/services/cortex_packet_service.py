import logging
from typing import Any, Dict, List
from datetime import datetime, timedelta, timezone
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.expectation import Expectation, OutcomeState, ExpectationType
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionStatus
from src.services.expectation_engine import derive_expectation_read_model, derive_temporal_state

logger = logging.getLogger(__name__)


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
    ) -> Dict[str, Any]:
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
            Expectation.honcho_session_id == session_id,
            Expectation.superseded_by_id.is_(None),
        ).order_by(Expectation.created_at.desc())
        res_exp = await db.execute(stmt_exp)
        expectations = res_exp.scalars().all()

        followups = []
        window_elapsed_unknown = []
        hard_deadlines = []
        waiting_on = []
        active_expectations = []
        recent_resolutions = []
        suppressed_expectation_ids: set[str] = set()
        suppressed_message_ids: set[str] = set()

        for exp in expectations:
            read_model = derive_expectation_read_model(exp, now)
            
            # Check suppression match
            exp_text = f"{exp.title} {exp.summary}".lower()
            is_suppressed = any(
                (supp.target_type.value == "expectation" and supp.target_id == str(exp.id))
                or (
                    supp.topic_or_entity
                    and any(
                        token in exp_text
                        for token in supp.topic_or_entity.lower().split()
                        if len(token) >= 4
                    )
                )
                for supp in active_suppressions
            )

            if is_suppressed:
                suppressed_expectation_ids.add(str(exp.id))
                suppressed_message_ids.add(exp.honcho_message_id)
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
                active_expectations.append({
                    "id": str(exp.id),
                    "honcho_message_id": exp.honcho_message_id,
                    "title": exp.title,
                    "summary": exp.summary,
                    "expectation_type": exp.expectation_type.value,
                    "temporal_state": read_model["temporal_state"],
                })

        # 3. Fetch Open Loops
        stmt_loop = select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_session_id == session_id,
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
                (supp.target_type.value == "open_loop" and supp.target_id == str(loop.id))
                or (
                    supp.topic_or_entity
                    and (
                        supp.topic_or_entity.lower() in loop.title.lower()
                        or supp.topic_or_entity.lower() in loop.summary.lower()
                    )
                )
                for supp in active_suppressions
            ) or (loop.expectation_id is not None and str(loop.expectation_id) in suppressed_expectation_ids) \
                or loop.honcho_message_id in suppressed_message_ids
            if not is_suppressed:
                linked_expectation = expectations_by_id.get(loop.expectation_id)
                open_loops_list.append({
                    "id": str(loop.id),
                    "honcho_message_id": loop.honcho_message_id,
                    "title": (
                        linked_expectation.title
                        if linked_expectation and loop.title == "Invited follow-up"
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

        temporal_priority = {
            "deadline_passed": 0,
            "window_elapsed": 1,
            "deadline_approaching": 2,
            "window_open": 3,
            "not_due": 4,
        }
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

        packet = {
            "workspace_id": workspace_id,
            "session_id": session_id,
            "timestamp": now.isoformat(),
            "followups": followups[:3],
            "open_loops": open_loops_list[:3],
            "active_expectations": active_expectations[:4],
            "window_elapsed_unknown": window_elapsed_unknown[:2],
            "hard_deadlines": hard_deadlines[:2],
            "waiting_on": waiting_on[:3],
            "recent_resolutions": recent_resolutions[:3],
            "suppressed_targets": [
                {
                    "id": str(s.id),
                    "target_type": s.target_type.value,
                    "topic_or_entity": s.topic_or_entity,
                    "reason": s.reason,
                    "suppressed_until": s.suppressed_until.isoformat() if s.suppressed_until else None,
                }
                for s in active_suppressions[:5]
            ],
            "important_but_can_wait": [],
            "relevant_honcho_message_ids": sorted({
                item["honcho_message_id"] for item in followups[:5]
            } | {
                item["honcho_message_id"] for item in open_loops_list[:5]
            }),
        }
        packet["continuity_context"] = self._compile_continuity_context(
            packet, now=now, timezone_str=timezone_str
        )
        return packet

    @staticmethod
    def _compile_continuity_context(
        packet: Dict[str, Any], *, now: datetime, timezone_str: str
    ) -> Dict[str, Any]:
        """Canonical bounded context shared by reactive and proactive callers."""
        try:
            from zoneinfo import ZoneInfo

            local_now = now.astimezone(ZoneInfo(timezone_str))
        except Exception:
            local_now = now
        hour = local_now.hour
        daypart = (
            "morning" if 5 <= hour < 12 else
            "afternoon" if 12 <= hour < 17 else
            "evening" if 17 <= hour < 22 else "night"
        )

        continuity: List[Dict[str, Any]] = []
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
        for item in packet.get("followups", [])[:3]:
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
        seen_topics = {str(item.get("topic", "")).lower() for item in continuity}
        for item in packet.get("active_expectations", [])[:4]:
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
            "continuity": continuity[:5],
            "open_threads": open_threads,
            "recent_resolutions": recent_resolutions,
            "avoid_repeating": avoid_repeating,
            "relevant_honcho_message_ids": packet.get(
                "relevant_honcho_message_ids", []
            )[:8],
        }
