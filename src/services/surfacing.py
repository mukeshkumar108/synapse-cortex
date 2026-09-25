"""Surfacing lifecycle report-back + working-set staleness protocol.

Runtime owns local surfacing state during a session (surfaced / deferred /
dismissed / answered / still-open) and reconciles outcomes back here in
bounded batches — never a round trip before every response. Every outcome
maps onto existing durable machinery:

- surfaced      -> SurfaceRegistry.mark (cooldown/max-count bookkeeping)
- answered      -> resolve the source row where one exists (clarification),
                   plus a delivered receipt
- resolved      -> resolve/dismiss the source row (matter settled)
- deferred      -> suppression with reopen_condition (not-now != never)
- dismissed     -> strong suppression ("stop asking" outranks silence)
- ignored       -> mark only; stays eligible later (ignored != resolved)
- suppressed    -> suppression row as reported
- still-open    -> no write; acknowledged but unresolved

"Stop asking" always wins over silence: explicit dismissal writes a
suppression, mere non-response only advances cooldown/max-count.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

TERMINAL_SOURCE_OUTCOMES = {"answered", "resolved"}


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


async def report_back(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    owner_peer_id: str,
    events: List[Dict[str, Any]],
    now: datetime,
    message_id: str,
    channel: str = "chat",
) -> Dict[str, Any]:
    """Apply a bounded batch of surfacing outcomes. Returns per-event results.
    Unknown matter kinds/ids are recorded as skipped, never invented."""
    from src.models.suppression import (
        Suppression, SuppressionStatus, SuppressionTarget,
    )
    from src.models.clarification import ClarificationCandidate, ClarificationStatus
    from src.models.operational_state import CandidateReceipt
    from src.services.surface_lifecycle import SurfaceRegistry

    applied: List[Dict[str, Any]] = []
    for ev in events or []:
        matter_kind = str(ev.get("matter_kind") or "")
        matter_id = str(ev.get("matter_id") or "")
        outcome = str(ev.get("outcome") or "")
        move_key = str(ev.get("move_key") or f"{matter_kind}:{matter_id}")
        try:
            result = await _apply_one(
                db, workspace_id=workspace_id, session_id=session_id,
                owner_peer_id=owner_peer_id, matter_kind=matter_kind,
                matter_id=matter_id, outcome=outcome, move_key=move_key,
                message_id=message_id, channel=channel, now=now,
                Suppression=Suppression, SuppressionStatus=SuppressionStatus,
                SuppressionTarget=SuppressionTarget,
                ClarificationCandidate=ClarificationCandidate,
                ClarificationStatus=ClarificationStatus,
                CandidateReceipt=CandidateReceipt,
            )
        except Exception as err:
            logger.warning("report_back event failed: %s", err)
            result = {"matter": f"{matter_kind}:{matter_id}",
                      "outcome": outcome, "applied": False,
                      "reason": f"error:{str(err)[:120]}"}
        applied.append(result)
    return {"applied": applied,
            "ok": sum(1 for r in applied if r.get("applied"))}


async def _apply_one(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    owner_peer_id: str, matter_kind: str, matter_id: str, outcome: str,
    move_key: str, message_id: str, channel: str, now: datetime,
    Suppression, SuppressionStatus, SuppressionTarget,
    ClarificationCandidate, ClarificationStatus, CandidateReceipt,
) -> Dict[str, Any]:
    from src.services.surface_lifecycle import SurfaceRegistry

    record = {"matter": f"{matter_kind}:{matter_id}", "outcome": outcome}
    if not matter_id or outcome not in (
            "surfaced", "answered", "resolved", "deferred", "dismissed",
            "ignored", "suppressed", "still-open"):
        return {**record, "applied": False, "reason": "unknown outcome/matter"}

    if outcome in ("surfaced", "ignored"):
        # Ignored advances cooldown bookkeeping only; eligibility survives.
        await SurfaceRegistry().mark(
            db, workspace_id=workspace_id, session_id=session_id,
            message_id=message_id, key=f"surface:{move_key}", now=now)
        await db.commit()
        return {**record, "applied": True,
                "reason": "cooldown advanced; matter still eligible"}

    if outcome in ("answered", "resolved") and matter_kind == "clarification":
        row = await db.get(ClarificationCandidate, _uuid_or_none(matter_id))
        if row is None:
            return {**record, "applied": False, "reason": "row gone"}
        row.status = (ClarificationStatus.RESOLVED if outcome == "answered"
                      else ClarificationStatus.DISMISSED)
        row.updated_at = _naive_utc(now)
        db.add(row)
        await db.commit()
        return {**record, "applied": True, "reason": f"clarification {outcome}"}

    if outcome in ("deferred", "dismissed", "suppressed"):
        # "Stop asking" (dismissed) writes a bare strong suppression;
        # deferred carries a reopen condition (not-now != never).
        strong = outcome == "dismissed"
        db.add(Suppression(
            honcho_workspace_id=workspace_id,
            honcho_session_id=session_id,
            honcho_message_id=message_id,
            owner_peer_id=owner_peer_id,
            target_type=SuppressionTarget.TOPIC,
            topic_or_entity=str((await _matter_title(
                db, matter_kind, matter_id)) or "")[:160] or None,
            target_id=matter_id if matter_kind != "graph" else None,
            reason=f"runtime report-back: {outcome}",
            surface_scope="all_surfaces" if strong else "followup_prompt",
            suppressed_until=None if strong else None,
            reopen_condition=None if strong else "user re-raises topic",
            status=SuppressionStatus.ACTIVE,
        ))
        await db.commit()
        return {**record, "applied": True,
                "reason": "strong suppression" if strong else "deferred with reopen"}

    if outcome == "still-open":
        return {**record, "applied": True, "reason": "acknowledged, no write"}

    # answered/resolved on non-clarification matters: receipt only.
    db.add(CandidateReceipt(
        receipt_id=str(uuid.uuid4()),
        decision_id=f"report-back:{message_id}",
        turn_id=message_id,
        candidate_id=move_key,
        candidate_version=_naive_utc(now).isoformat(),
        honcho_workspace_id=workspace_id,
        owner_peer_id=owner_peer_id,
        stage="delivered",
        channel=channel,
        occurred_at=_naive_utc(now),
        effect="resolved" if outcome == "resolved" else "answered",
    ))
    await db.commit()
    return {**record, "applied": True, "reason": "receipt recorded"}


def _uuid_or_none(value: str):
    try:
        from uuid import UUID
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        return None


async def _matter_title(db: AsyncSession, matter_kind: str,
                        matter_id: str) -> str:
    uid = _uuid_or_none(matter_id)
    if uid is None:
        return matter_id[:160]
    if matter_kind == "clarification":
        from src.models.clarification import ClarificationCandidate
        row = await db.get(ClarificationCandidate, uid)
        return str(getattr(row, "description", "") or "") if row else ""
    if matter_kind == "open_loop":
        from src.models.open_loop import OpenLoop
        row = await db.get(OpenLoop, uid)
        return str(getattr(row, "title", "") or "") if row else ""
    if matter_kind == "attention":
        from src.models.attention_candidate import AttentionCandidate
        row = await db.get(AttentionCandidate, uid)
        return str(getattr(row, "content", "") or "") if row else ""
    return ""
