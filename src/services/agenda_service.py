"""Sophie's live agenda compiler (the center of behavioral attention).

Consumes normalized semantic candidates from existing Cortex state:
  L1 world:      state, event, objective, plan, expectation, commitment, recurrence
  L2 dynamics:   transition, gap, open loop, pattern deviation, thread
  L3 understanding: question, hypothesis, blocker, Sophie intention

Deterministic code computes every factual/temporal field (importance, urgency,
time pressure, unresolvedness, prior surfacing, status, expiry). A cheap async
model ranks competing candidates into the live agenda when semantic judgment
helps; a deterministic scored fallback owns degradation. The compiled agenda is
replaceable derived state, read synchronously by turns, greetings, proactive
paths and steering. ask-style booleans are gone: follow-up pressure is a
ranked salience input with an explicit ask ledger underneath.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.attention_candidate import AttentionCandidate
from src.models.operational_state import (
    AgendaSnapshot, OperationalStatus, RecurringOccurrence,
)

logger = logging.getLogger(__name__)

_AGENDA_MODEL = os.getenv("AGENDA_MODEL", "google/gemini-3.7-flash").strip()
_AGENDA_TTL_HOURS = float(os.getenv("AGENDA_TTL_HOURS", "3.5"))
_MAX_ITEMS = int(os.getenv("AGENDA_MAX_ITEMS", "4"))

_SEMANTIC_IMPORTANCE = {
    "measurable_goal": 0.75, "adherence_action": 0.85, "recurring_action": 0.7,
    "recurring_ritual": 0.65, "deadline": 0.9, "event": 0.75,
    "commitment": 0.8, "expectation": 0.6, "durable_objective": 0.65,
    "open_loop": 0.5, "sophie_intention": 0.45,
}


def _naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def _is_stale(item: Dict[str, Any]) -> bool:
    try:
        return float(item.get("age_hours") or 0) > 30.0
    except (TypeError, ValueError):
        return False


def extract_candidates(packet: Dict[str, Any], *, now: datetime, timezone_str: str) -> List[Dict[str, Any]]:
    """Deterministic L1/L2/L3 candidate extraction from the attention packet.
    Code owns every factual and temporal field. No model involved here."""
    now = _naive(now)
    brief = packet.get("intelligence_brief") or {}
    daypart = str(brief.get("daypart") or "").lower()
    candidates: List[Dict[str, Any]] = []

    def cand(**kw: Any) -> None:
        kw.setdefault("importance", _SEMANTIC_IMPORTANCE.get(kw.get("semantic_type", "objective"), 0.5))
        kw.setdefault("urgency", 0.3)
        kw.setdefault("pressure", 0.0)
        kw.setdefault("status", "unresolved")
        kw.setdefault("owner", "user")
        kw.setdefault("why", "")
        kw.setdefault("next_move", "")
        kw.setdefault("horizon", "day")
        candidates.append(kw)

    # L1 - objectives (actionable recurrences with occurrence state)
    stale_ids = {str(i.get("id")) for i in (packet.get("window_elapsed_unknown") or [])}
    for item in (packet.get("recurring_intentions") or []):
        if item.get("semantic_type") == "observed_pattern" or item.get("occurrence_status") != "pending":
            continue
        urgency, pressure = 0.35, 0.0
        preferred = str(item.get("preferred_window") or "").strip().lower()
        window_passed = bool(preferred and daypart and preferred not in ("any", "none") and preferred not in daypart)
        if window_passed or daypart in ("evening", "night"):
            urgency, pressure = 0.8, 0.75
        elif daypart == "afternoon":
            urgency, pressure = 0.68, 0.65
        else:  # morning: the day is young but the objective is already live
            urgency, pressure = 0.6, 0.55
        urgency += min(0.15, 0.03 * float(item.get("ask_count") or 0))
        target = item.get("target_amount")
        what = str(item.get("title") or "")[:80]
        if target is not None and item.get("target_unit"):
            what = f"{what} ({target:g} {item['target_unit']})"
        asks = int(item.get("ask_count") or 0)
        cand(item_key=f"obj:{item.get('id')}", what=what,
             semantic_type=str(item.get("semantic_type") or "recurring_action"),
             urgency=min(1.0, urgency), pressure=pressure, occurrence_id=item.get("occurrence_id"),
             why=f"daily objective unconfirmed today ({asks} ask(s) so far)",
             next_move=("ask status; adapt strategy if window closed" if (window_passed or daypart in ("evening", "night")) else "check in naturally"),
             horizon="now" if (window_passed or daypart in ("evening", "night")) else "day")

    # L1 - deadlines & active plans (fresh only)
    for item in (packet.get("active_expectations") or []):
        if str(item.get("id")) in stale_ids or _is_stale(item):
            continue
        approaching = item.get("temporal_state") == "deadline_approaching"
        cand(item_key=f"exp:{item.get('id')}", what=str(item.get("title") or "")[:100],
             semantic_type="deadline" if approaching else "expectation",
             urgency=0.8 if approaching else 0.5,
             pressure=0.6 if approaching else 0.3,
             why=str(item.get("expected_window_label") or "")[:80],
             next_move="confirm status or offer prep help",
             horizon="now" if approaching else "day")

    # L2 - gaps (elapsed windows without outcome evidence, recent only)
    for item in (packet.get("window_elapsed_unknown") or []):
        try:
            age = float(item.get("age_hours") or 0)
        except (TypeError, ValueError):
            age = 0.0
        if age > 48:
            continue
        cand(item_key=f"gap:{item.get('id')}", what=str(item.get("title") or "")[:90],
             semantic_type="open_loop", urgency=0.4, pressure=0.25,
             why=f"no outcome evidence yet ({age:.0f}h old)",
             next_move="ask outcome naturally once", horizon="day")

    # L2 - transitions (recent resolutions worth acknowledging)
    for item in (packet.get("recent_resolutions") or []):
        line = str(item.get("title") or "")[:90]
        if line:
            cand(item_key=f"tr:{item.get('id')}", what=line, semantic_type="transition",
                 importance=0.35, urgency=0.25, pressure=0.15, status="resolved",
                 why="recently resolved", next_move="acknowledge or follow up on aftermath",
                 horizon="2h")

    # L3 - Sophie intentions (grounded attention candidates)
    for item in (brief.get("backstage_attention") or [])[:6]:
        content = str(item.get("content") or item.get("title") or "").strip()
        if not content:
            continue
        cand(item_key=f"si:{item.get('id')}", what=content[:110], semantic_type="sophie_intention",
             owner="sophie", importance=0.45, urgency=0.3, pressure=0.2,
             why="follow-up Sophie wants to make when an opening appears",
             next_move="raise at a natural opening", horizon="6h")

    return candidates


def fallback_rank(candidates: List[Dict[str, Any]], *, daypart: str) -> List[Dict[str, Any]]:
    """Deterministic scored fallback: salience = importance + urgency +
    pressure - surfacing fatigue. Used when the ranker model is unavailable."""
    ranked = []
    for c in candidates:
        score = c.get("importance", 0.5) * 0.45 + c.get("urgency", 0.3) * 0.4 + c.get("pressure", 0.0) * 0.25
        if c.get("semantic_type") == "transition" and c.get("status") == "resolved":
            score -= 0.1
        ranked.append({**c, "score": round(score, 3)})
    ranked.sort(key=lambda x: x["score"], reverse=True)
    top = ranked[:_MAX_ITEMS]
    for i, item in enumerate(top):
        item["rank"] = i
    return top


async def model_rank(candidates: List[Dict[str, Any]], *, daypart: str, adapter: Any) -> Optional[List[Dict[str, Any]]]:
    """Cheap async model: semantic judgment over competing candidates.
    Returns None on any failure (caller falls back)."""
    if not candidates:
        return []
    for i, c in enumerate(candidates):
        c["cid"] = f"c{i}"
    compact = [{k: c.get(k) for k in ("cid", "what", "semantic_type", "owner", "importance", "urgency", "pressure", "status", "why", "next_move")} for c in candidates]
    system = (
        "You compile a companion's LIVE AGENDA: the 3-4 things that most deserve her attention "
        "right now, from competing candidates of mixed kinds (goals, plans, emotional matters, "
        "her own follow-ups). Judge relative salience and displacement: an acute event outranks "
        "everything; a mild emotional matter may deserve one beat; objectives with closing windows "
        "rise; recently surfaced items lose urgency; nothing important means an empty agenda is the "
        "correct answer. For each item return: what, semantic_type, owner, importance 0-1, urgency 0-1, "
        "pressure 0-1 (follow-up pressure), status, why (under 12 words), next_move (under 12 words, conversational "
        "direction, not a script), horizon (now/2h/6h/day). Copy 'what' VERBATIM from the candidate - never reword. Echo 'cid' exactly. Never invent candidates."
    )
    try:
        raw = await adapter.generate_structured(
            system=system,
            prompt=f"TIME OF DAY: {daypart}\nCANDIDATES:\n{json.dumps(compact)}",
            json_schema={
                "type": "object",
                "properties": {"items": {"type": "array", "items": {
                    "type": "object",
                    "properties": {
                        "what": {"type": "string"}, "semantic_type": {"type": "string"},
                        "owner": {"type": "string"}, "importance": {"type": "number"},
                        "urgency": {"type": "number"}, "pressure": {"type": "number"},
                        "status": {"type": "string"}, "why": {"type": "string"},
                        "next_move": {"type": "string"}, "horizon": {"type": "string"}},
                    "required": ["what", "next_move"],
                }}},
                "required": ["items"], "additionalProperties": False},
            model_id=_AGENDA_MODEL, max_tokens=int(os.getenv("AGENDA_RANKER_MAX_TOKENS", "2000")), temperature=0.2, strict=True,
        )
    except Exception as exc:
        logger.warning("[agenda] ranker failed, using deterministic fallback: %s", exc)
        return None
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return None
    # The model SELECTS and ORDERS; deterministic code owns item text,
    # status and pressure. Merge model fields (why/next_move/horizon) onto
    # the matching candidate by echoed cid (or verbatim-what fallback).
    by_cid = {c.get("cid"): c for c in candidates}
    by_what = {c.get("what", "").lower(): c for c in candidates}
    clean: List[Dict[str, Any]] = []
    for item in items[:_MAX_ITEMS]:
        if not isinstance(item, dict):
            continue
        src = by_cid.get(item.get("cid")) or by_what.get(str(item.get("what") or "").lower())
        if src is None:
            continue
        merged = {**src, "rank": len(clean)}
        for field in ("why", "next_move", "horizon"):
            if str(item.get(field) or "").strip():
                merged[field] = str(item[field])[:200]
        clean.append(merged)
    return clean or None


async def ensure_occurrence_rows(db: AsyncSession, *, workspace_id: str, packet: Dict[str, Any], now: datetime) -> None:
    """Write-path companion to the packet read: actionable recurrences get a
    PENDING occurrence row for today (with ask ledger fields) so follow-up
    accounting has something to attach to. Read-path semantics (curiosity,
    pattern deviation from ABSENT occurrences) are untouched."""
    from src.models.operational_state import RecurringIntention
    now = _naive(now)
    user_day = now.date()
    for item in (packet.get("recurring_intentions") or []):
        stype = str(item.get("semantic_type") or "")
        if stype == "observed_pattern" or item.get("occurrence_status") != "pending" or item.get("occurrence_id"):
            continue
        rec = (await db.execute(select(RecurringIntention).where(
            RecurringIntention.id == item.get("id"),
        ))).scalars().first()
        if rec is None or rec.status != OperationalStatus.ACTIVE:
            continue
        row = RecurringOccurrence(
            recurring_intention_id=rec.id,
            honcho_workspace_id=workspace_id,
            user_day=user_day,
        )
        db.add(row)
        await db.flush()
        item["occurrence_id"] = str(row.id)
        item["ask_count"] = 0


async def compile_agenda(db: AsyncSession, *, workspace_id: str, owner_peer_id: Optional[str],
                         packet: Dict[str, Any], now: datetime, timezone_str: str,
                         adapter: Any, force: bool = False) -> Dict[str, Any]:
    """Read-or-compile the live agenda. Fresh snapshot returns instantly.
    Otherwise compile deterministically, persist, and refresh via the model
    in the background (never blocking the foreground)."""
    from src.db import async_session_maker
    now = _naive(now)
    horizon = "day"
    snap = (await db.execute(select(AgendaSnapshot).where(
        AgendaSnapshot.honcho_workspace_id == workspace_id,
        AgendaSnapshot.owner_peer_id == owner_peer_id,
        AgendaSnapshot.horizon == horizon,
    ).with_for_update())).scalars().first()
    if snap is not None and snap.expires_at > now and not force:
        try:
            return {"items": json.loads(snap.items_json), "compiled_by": snap.compiled_by,
                    "compiled_at": snap.compiled_at.isoformat(), "stale": False}
        except (TypeError, ValueError):
            pass

    daypart = str((packet.get("intelligence_brief") or {}).get("daypart") or "").lower()
    await ensure_occurrence_rows(db, workspace_id=workspace_id, packet=packet, now=now)
    candidates = extract_candidates(packet, now=now, timezone_str=timezone_str)
    items = fallback_rank(candidates, daypart=daypart)
    compiled_by = "fallback"

    # Persist the fallback snapshot immediately so the foreground never waits.
    # Concurrent handover requests converge: on the rare unique violation the
    # losing request re-reads and updates the winning row instead of failing.
    try:
        if snap is not None:
            snap.items_json = json.dumps(items)
            snap.compiled_by = compiled_by
            snap.compiled_at = now
            snap.expires_at = now + timedelta(hours=_AGENDA_TTL_HOURS)
            db.add(snap)
        else:
            db.add(AgendaSnapshot(honcho_workspace_id=workspace_id, owner_peer_id=owner_peer_id,
                                  horizon=horizon, items_json=json.dumps(items),
                                  compiled_by=compiled_by, compiled_at=now,
                                  expires_at=now + timedelta(hours=_AGENDA_TTL_HOURS)))
        await db.commit()
    except Exception:
        await db.rollback()
        loser = (await db.execute(select(AgendaSnapshot).where(
            AgendaSnapshot.honcho_workspace_id == workspace_id,
            AgendaSnapshot.owner_peer_id == owner_peer_id,
            AgendaSnapshot.horizon == horizon,
        ))).scalars().first()
        if loser is not None:
            loser.items_json = json.dumps(items)
            loser.compiled_by = compiled_by
            loser.compiled_at = now
            loser.expires_at = now + timedelta(hours=_AGENDA_TTL_HOURS)
            db.add(loser)
            await db.commit()

    # Model-ranked refresh in the background: better judgment, zero latency cost.
    if adapter is not None:
        asyncio.create_task(_background_model_refresh(
            workspace_id, owner_peer_id, candidates, daypart, adapter, now))

    return {"items": items, "compiled_by": compiled_by, "compiled_at": now.isoformat(), "stale": False}


async def _background_model_refresh(workspace_id: str, owner_peer_id: Optional[str],
                                    candidates: List[Dict[str, Any]], daypart: str,
                                    adapter: Any, now: datetime) -> None:
    from src.db import async_session_maker
    try:
        ranked = await model_rank(candidates, daypart=daypart, adapter=adapter)
        if not ranked:
            return
        now = _naive(now)
        async with async_session_maker() as db:
            snap = (await db.execute(select(AgendaSnapshot).where(
                AgendaSnapshot.honcho_workspace_id == workspace_id,
                AgendaSnapshot.owner_peer_id == owner_peer_id,
                AgendaSnapshot.horizon == "day",
            ).with_for_update())).scalars().first()
            if snap is None:
                db.add(AgendaSnapshot(honcho_workspace_id=workspace_id, owner_peer_id=owner_peer_id,
                                      horizon="day", items_json=json.dumps(ranked),
                                      compiled_by="model", compiled_at=now,
                                      expires_at=now + timedelta(hours=_AGENDA_TTL_HOURS)))
            else:
                snap.items_json = json.dumps(ranked)
                snap.compiled_by = "model"
                snap.compiled_at = now
                snap.expires_at = now + timedelta(hours=_AGENDA_TTL_HOURS)
                db.add(snap)
            await db.commit()
    except Exception:
        logger.exception("[agenda] background model refresh failed")
