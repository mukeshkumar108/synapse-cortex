"""Session/scene working sets: disposable projections of relevant state.

Cortex compiles; Runtime caches and selects locally per turn. The working set
is NEVER canonical truth: if stale or corrupted, throw it away and recompile.
Recompile/refresh only on: session start, material events (external evidence,
reminder due, worker completion, runtime-reported mutation), turn/elapsed
thresholds, or explicit invalidation (required context absent/stale).

Two compositions, one builder, no product copies:
- session (Sophie-style companion): concerns, open matters, waiting-ons,
  reminders/deadlines, eligible callbacks, relationship trajectory, world
  state, suppressions/defer-until, candidate moves, budgets.
- scene (RPD2-style narrative): scene anchor + character identities,
  relationship current meaning, salient recent events, character-owned
  undertakings, unresolved narrative threads, pact terms in force, expected
  near-future world events, latent callbacks, emotional trajectory.
Pressure policy differs by product (sophie opportunistic / rpd2 narrative /
healthcare mandatory); the compiler is shared, the policy is a parameter.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

WORKING_SET_VERSION = "session-working-set-v1"

PRESSURE_POLICIES = {
    # product -> {mandatory_kinds, opportunistic_default, max_proactive}
    "sophie": {"mandatory_kinds": (), "opportunistic_default": True,
               "max_proactive_per_day": 2},
    "rpd2": {"mandatory_kinds": (), "opportunistic_default": True,
             "max_proactive_per_day": 4},
    "healthcare": {"mandatory_kinds": ("reminder", "commitment"),
                   "opportunistic_default": False, "max_proactive_per_day": 6},
}


def _naive_utc(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value


def _stable_hash(payload: Any) -> str:
    return hashlib.sha1(
        json.dumps(payload, ensure_ascii=False, default=str,
                   sort_keys=True).encode()).hexdigest()[:16]


async def _source_fingerprint(db: AsyncSession, workspace_id: str,
                              session_id: str) -> Dict[str, Any]:
    """Cheap staleness signal: per-table counts + max updated_at. Recompute
    without compiling to answer 'refresh?'."""
    from src.models.attention_candidate import AttentionCandidate
    from src.models.clarification import ClarificationCandidate
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.current_meaning import CurrentMeaning
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop
    from src.models.semantic import SemanticRelation
    fingerprint: Dict[str, Any] = {}
    for model, name in (
            (Expectation, "expectations"), (OpenLoop, "open_loops"),
            (CommitmentCandidate, "commitments"),
            (ClarificationCandidate, "clarifications"),
            (AttentionCandidate, "attention"),
            (SemanticRelation, "relations"),
            (CurrentMeaning, "meaning")):
        try:
            filt = [model.honcho_workspace_id == workspace_id]
            if hasattr(model, "honcho_session_id"):
                filt.append(model.honcho_session_id == session_id)
            count = (await db.execute(
                select(func.count()).select_from(model).where(*filt))).scalar_one()
            latest = (await db.execute(
                select(func.max(model.updated_at)).where(*filt))).scalar_one()
            fingerprint[name] = {
                "count": count,
                "latest": latest.isoformat() if latest else None,
            }
        except Exception as err:
            logger.warning("fingerprint %s failed: %s", name, err)
            fingerprint[name] = {"count": -1, "latest": None}
    return fingerprint


async def _contacts_today(db: AsyncSession, workspace_id: str, owner_peer_id: str,
                          now: datetime) -> int:
    from src.models.operational_state import ProactiveLog
    day_start = _naive_utc(now).replace(hour=0, minute=0, second=0, microsecond=0)
    try:
        return (await db.execute(select(func.count()).select_from(ProactiveLog).where(
            ProactiveLog.honcho_workspace_id == workspace_id,
            ProactiveLog.owner_peer_id == owner_peer_id,
            ProactiveLog.at >= day_start,
        ))).scalar_one()
    except Exception as err:
        logger.warning("contacts_today failed: %s", err)
        return 0


async def compile_session_working_set(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    owner_peer_id: Optional[str],
    now: datetime,
    timezone_str: str = "UTC",
    product: str = "sophie",
    scene: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compile the disposable working set from independent views (never the
    foreground packet). Scene present -> narrative composition; else session
    composition. Pure read path."""
    from src.services.candidate_moves import derive_moves
    from src.services.state_views import compile_views

    policy = PRESSURE_POLICIES.get((product or "sophie").lower(),
                                   PRESSURE_POLICIES["sophie"])
    views = await compile_views(
        db, workspace_id=workspace_id, session_id=session_id,
        owner_peer_id=owner_peer_id, now=now, timezone_str=timezone_str)
    moves = await derive_moves(
        db, workspace_id=workspace_id, session_id=session_id,
        owner_peer_id=owner_peer_id, now=now)
    suppressions = await _active_suppressions(db, workspace_id, now)
    fingerprint = await _source_fingerprint(db, workspace_id, session_id)
    contacts = await _contacts_today(db, workspace_id, owner_peer_id or "", now)

    if scene:
        sections = _compose_scene(views, moves, suppressions, scene=scene)
        composition = "scene"
    else:
        sections = _compose_session(views, moves, suppressions)
        composition = "session"
    artifact = {
        "version": WORKING_SET_VERSION,
        "composition": composition,
        "product": product,
        "workspace_id": workspace_id,
        "session_id": session_id,
        "compiled_at": _naive_utc(now).isoformat(),
        "source_version": _stable_hash(fingerprint),
        "fingerprint": fingerprint,
        "budgets": {
            "max_proactive_per_day": policy["max_proactive_per_day"],
            "contacts_today": contacts,
            "proactive_remaining": max(
                0, policy["max_proactive_per_day"] - contacts),
            "max_foreground_items": 3,
        },
        "mandatory_kinds": list(policy["mandatory_kinds"]),
        "sections": sections,
        "scene": scene or {},
    }
    return artifact


def _compose_session(views: Dict[str, List[Dict[str, Any]]],
                     moves: Dict[str, Any],
                     suppressions: List[Dict[str, Any]]) -> Dict[str, Any]:
    eligible = [m for m in moves.get("moves", [])
                if m.get("telemetry") == "MOVE_ELIGIBLE"]
    return {
        "current_meaning": views.get("relationship_context", [])[:3],
        "active_concerns": views.get("worry", [])[:5],
        "open_matters": views.get("open_matter", [])[:8],
        "waiting_ons": views.get("waiting_on", [])[:6],
        "reminders_deadlines": (views.get("reminder", []) +
                                views.get("calendar", []))[:6],
        "callbacks_checkins": [
            m for m in eligible if m.get("kind") in ("CALLBACK", "FOLLOW_UP")][:4],
        "relationship_trajectory": views.get("relationship_context", [])[:5],
        "world_state": views.get("narrative_continuity", [])[:6],
        "suppressions_deferrals": suppressions,
        "candidate_moves": eligible[:10],
        "opportunities": views.get("conversation_opportunity", [])[:5],
        "todos": views.get("todo", [])[:8],
    }


def _compose_scene(views: Dict[str, List[Dict[str, Any]]],
                   moves: Dict[str, Any],
                   suppressions: List[Dict[str, Any]], *,
                   scene: Dict[str, Any]) -> Dict[str, Any]:
    eligible = [m for m in moves.get("moves", [])
                if m.get("telemetry") == "MOVE_ELIGIBLE"]
    return {
        "scene_anchor": scene,
        "character_state": views.get("relationship_context", [])[:6],
        "relationship_meaning": views.get("relationship_context", [])[:3],
        "salient_history": views.get("conversation_opportunity", [])[:4],
        "character_undertakings": [
            i for i in views.get("narrative_continuity", [])
            if i.get("kind") == "character_undertaking"][:6],
        "narrative_threads": [
            i for i in views.get("narrative_continuity", [])
            if i.get("kind") in ("scene_thread", "expected_event")][:6],
        "pact_terms": views.get("relationship_context", [])[:4],
        "expected_world_events": [
            i for i in views.get("narrative_continuity", [])
            if i.get("kind") == "expected_event"][:4],
        "latent_callbacks": [
            m for m in eligible if m.get("kind") in ("CALLBACK", "FOLLOW_UP")][:4],
        "emotional_trajectory": views.get("worry", [])[:3],
        "suppressions_deferrals": suppressions,
        "candidate_moves": eligible[:8],
    }


async def _active_suppressions(db: AsyncSession, workspace_id: str,
                               now: datetime) -> List[Dict[str, Any]]:
    from src.models.suppression import Suppression, SuppressionStatus
    rows = (await db.execute(select(Suppression).where(
        Suppression.honcho_workspace_id == workspace_id,
        Suppression.status == SuppressionStatus.ACTIVE,
    ).limit(20))).scalars().all()
    now_utc = _naive_utc(now)
    out = []
    for s in rows:
        if s.suppressed_until and s.suppressed_until < now_utc:
            continue
        out.append({
            "target_type": str(getattr(s.target_type, "value", s.target_type) or ""),
            "target_id": s.target_id,
            "topic_or_entity": s.topic_or_entity,
            "reopen_condition": s.reopen_condition,
            "suppressed_until": (s.suppressed_until.isoformat()
                                 if s.suppressed_until else None),
        })
    return out


async def needs_refresh(
    db: AsyncSession, *,
    workspace_id: str,
    session_id: str,
    cached_source_version: str,
) -> Dict[str, Any]:
    """Cheap staleness answer without recompiling. Runtime polls this."""
    fingerprint = await _source_fingerprint(db, workspace_id, session_id)
    current = _stable_hash(fingerprint)
    return {"stale": current != cached_source_version,
            "source_version": current,
            "cached_source_version": cached_source_version}
