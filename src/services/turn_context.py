"""Bounded current-state digest for extraction.

Rich state lives behind this module (Honcho evidence + existing Cortex
operational state). What it emits to the extractor is intentionally compact:
a few active objectives, loops, recurrences, suppressed topics, a handful of
recent Honcho messages, the session summary and a couple of conclusions.

Honcho is evidence. Cortex operational state (expectations/open loops/
recurrences) is authoritative for lifecycle. Neither becomes a raw history
dump; each contributes at most a few bounded items.

Poor-availability behaviour: Honcho sections degrade (honcho_status
unavailable/disabled) without failing the turn.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.clients.honcho_client import HonchoClient
from src.config import settings
from src.models.expectation import Expectation, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import OperationalStatus, RecurringIntention
from src.models.suppression import Suppression, SuppressionStatus

logger = logging.getLogger(__name__)

MAX_OBJECTIVES = 4
MAX_LOOPS = 3
MAX_RECURRENCES = 3
MAX_SUPPRESSIONS = 3
MAX_EVIDENCE = 6
MAX_CONCLUSIONS = 3

_honcho: Optional[HonchoClient] = None


def _honcho_client() -> Optional[HonchoClient]:
    global _honcho
    if not settings.HONCHO_CONTEXT_ENABLED:
        return None
    if _honcho is None:
        _honcho = HonchoClient(
            base_url=settings.HONCHO_BASE_URL,
            api_key=settings.HONCHO_API_KEY,
            timeout=settings.HONCHO_TIMEOUT_SECONDS,
        )
    return _honcho


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _cut(text: Optional[str], limit: int = 120) -> Optional[str]:
    if not text:
        return None
    text = " ".join(str(text).split())
    return text[:limit]


class TurnContextAssembler:
    """Builds a small read-only prior-state packet for the loose watcher."""

    def __init__(self, honcho: Optional[HonchoClient] = None):
        self.honcho = honcho

    async def assemble(
        self,
        db: AsyncSession,
        *,
        workspace_id: str,
        session_id: str,
        peer_id: str,
        now: datetime,
        current_message_id: Optional[str] = None,
        current_text: Optional[str] = None,
        timezone_str: str = "UTC",
    ) -> Dict[str, Any]:
        digest: Dict[str, Any] = {
            "objectives": [],
            "open_loops": [],
            "recurrences": [],
            "suppressed_topics": [],
        }

        # ── Cortex operational state (authoritative for lifecycle) ───────────
        objectives = (
            await db.execute(
                select(Expectation)
                .where(
                    Expectation.honcho_workspace_id == workspace_id,
                    Expectation.honcho_session_id == session_id,
                    Expectation.outcome_state == OutcomeState.UNKNOWN,
                    Expectation.superseded_by_id.is_(None),
                )
                .order_by(Expectation.created_at.desc())
                .limit(MAX_OBJECTIVES)
            )
        ).scalars().all()
        digest["objectives"] = [
            {
                "title": exp.title,
                "summary": _cut(exp.summary, 100),
                "expectation_type": exp.expectation_type.value,
                "raw_temporal_phrase": exp.raw_temporal_phrase,
            }
            for exp in objectives
        ]

        loops = (
            await db.execute(
                select(OpenLoop)
                .where(
                    OpenLoop.honcho_workspace_id == workspace_id,
                    OpenLoop.honcho_session_id == session_id,
                    OpenLoop.status == OpenLoopStatus.OPEN,
                )
                .order_by(OpenLoop.created_at.desc())
                .limit(MAX_LOOPS)
            )
        ).scalars().all()
        digest["open_loops"] = [
            {"title": loop.title, "summary": _cut(loop.summary, 100)}
            for loop in loops
        ]

        recurrences = (
            await db.execute(
                select(RecurringIntention)
                .where(
                    RecurringIntention.honcho_workspace_id == workspace_id,
                    RecurringIntention.honcho_session_id == session_id,
                    RecurringIntention.status == OperationalStatus.ACTIVE,
                )
                .order_by(RecurringIntention.updated_at.desc())
                .limit(MAX_RECURRENCES)
            )
        ).scalars().all()
        digest["recurrences"] = [
            {
                "title": recurrence.title,
                "cadence": recurrence.cadence,
                "preferred_window": recurrence.preferred_window,
                "target_amount": recurrence.target_amount,
                "target_unit": recurrence.target_unit,
            }
            for recurrence in recurrences
        ]

        suppressions = (
            await db.execute(
                select(Suppression)
                .where(
                    Suppression.honcho_workspace_id == workspace_id,
                    Suppression.honcho_session_id == session_id,
                    Suppression.status == SuppressionStatus.ACTIVE,
                )
                .order_by(Suppression.created_at.desc())
                .limit(MAX_SUPPRESSIONS)
            )
        ).scalars().all()
        digest["suppressed_topics"] = [
            s.topic_or_entity for s in suppressions if s.topic_or_entity
        ]

        # ── Honcho evidence (bounded, fail-open) ─────────────────────────────
        client = self.honcho or _honcho_client()
        if client is None:
            digest["status"] = "ok"
            digest["honcho_status"] = "disabled"
            return digest

        message_ids_to_skip = {current_message_id} if current_message_id else set()

        async def messages_block():
            # Relevance-first: admit Honcho evidence tied to THIS turn when the
            # instance supports semantic search; fall back to the recent window
            # when the search request itself fails. An empty relevance result is
            # not a failure: the recent window still supplies continuity.
            relevant = None
            if current_text:
                relevant = await client.search_messages(
                    workspace_id, session_id, query=current_text, limit=MAX_EVIDENCE + 2
                )
            if relevant is not None and not relevant:
                recent_fallback = await client.recent_messages(
                    workspace_id, session_id, limit=MAX_EVIDENCE + 2
                )
                if recent_fallback is not None:
                    relevant = recent_fallback
            msgs = relevant
            if msgs is None:
                msgs = await client.recent_messages(
                    workspace_id, session_id, limit=MAX_EVIDENCE + 2
                )
            if msgs is None:
                return None
            return [
                {
                    "peer_id": m.get("peer_id"),
                    "content": _cut(m.get("content"), 160),
                }
                for m in msgs
                if m.get("id") not in message_ids_to_skip
            ][:MAX_EVIDENCE]

        async def conclusions_block():
            cons = await client.conclusions(workspace_id, observed=peer_id, limit=MAX_CONCLUSIONS)
            if not cons:
                return None
            return [
                {
                    "content": _cut(item.get("content"), 140),
                    "level": item.get("level"),
                    "observer_id": item.get("observer_id"),
                }
                for item in cons
            ]

        available = True
        try:
            messages, summaries_data, conclusions = await asyncio.wait_for(
                asyncio.gather(
                    messages_block(),
                    client.session_summaries(workspace_id, session_id),
                    conclusions_block(),
                ),
                timeout=settings.HONCHO_CONTEXT_BUDGET_SECONDS,
            )
        except asyncio.TimeoutError:
            logger.warning("Honcho context assembly timed out; degrading")
            available = False
            messages, summaries_data, conclusions = None, None, None

        if available:
            honcho_ok = (
                messages is not None
                and summaries_data is not None
                and conclusions is not None
                and not client.last_error
            )
            if honcho_ok:
                digest["recent_evidence"] = messages or []
                summary = (summaries_data or {}).get("short_summary")
                digest["session_summary"] = _cut(summary, 240)
                digest["conclusions"] = conclusions or []
                digest["status"] = "ok"
                digest["honcho_status"] = "ok"
            else:
                digest["status"] = "degraded"
                digest["honcho_status"] = "unavailable"
        else:
            digest["status"] = "degraded"
            digest["honcho_status"] = "unavailable"
        return digest


def context_to_prompt(digest: Dict[str, Any], limit: int = 700) -> str:
    """Serialize the digest to a bounded plain-text block for the extractor."""
    if not digest:
        return ""
    lines = []

    def section(name: str, items: Optional[List[Any]]):
        if not items:
            return
        lines.append(name)
        for item in items:
            if isinstance(item, str):
                lines.append(f"- {_cut(item, 120)}")
            elif isinstance(item, dict):
                parts = []
                for k, v in item.items():
                    if v in (None, "", [], {}):
                        continue
                    parts.append(f"{k}: {v}")
                if parts:
                    lines.append("- " + " | ".join(parts))

    section("OBJECTIVES (active)", digest.get("objectives"))
    section("OPEN LOOPS (active)", digest.get("open_loops"))
    section("RECURRING INTENTIONS (active)", digest.get("recurrences"))
    section("SUPPRESSED TOPICS", digest.get("suppressed_topics"))
    section("RECENT HONCHO MESSAGES", digest.get("recent_evidence"))
    if digest.get("session_summary"):
        lines.append("SESSION SUMMARY")
        lines.append(f"- {digest['session_summary']}")
    section("RELEVANT CONCLUSIONS", digest.get("conclusions"))
    block = "\n".join(lines)
    return block[:limit]