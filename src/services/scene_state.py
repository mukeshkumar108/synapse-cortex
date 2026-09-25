"""Deterministic scene truth maintenance + epoch protocol.

Jev detects bounded deltas (arrivals, departures, addressee/activity shifts,
time jumps); THIS module decides whether they update truth, by authority
rules. T2/background decides what the change means. Three separate jobs,
three separate places.

Authority: user_explicit (3) > external_event/entry_context (2) >
model_inferred (1) > default (0). Higher rank always wins; equal rank goes
to the newer evidence. Participants add monotonically; removal needs
explicit departure evidence. Location/activity/mode/clock go to the
highest-ranked evidence. Nothing here reads prose semantically.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.scene import AUTHORITY_RANK, CurrentScene, SceneEpoch

logger = logging.getLogger(__name__)


def _now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _loads(raw: Any) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw or "{}")
    except (ValueError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def empty_fields() -> Dict[str, Any]:
    return {}


def apply_detections(
    fields: Dict[str, Any],
    detections: Dict[str, Any],
    *,
    source: str = "model_inferred",
    confidence: float = 0.7,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Pure deterministic merge. Returns new fields dict (input untouched)."""
    now_naive = _now_naive() if now is None else (
        now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now)
    rank = AUTHORITY_RANK.get(str(source), 0)
    stamp = now_naive.isoformat()
    out = {k: dict(v) for k, v in (fields or {}).items()}

    def set_field(name: str, value: Any) -> None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return
        if isinstance(value, list) and not value:
            return
        current = out.get(name) or {}
        current_rank = AUTHORITY_RANK.get(str(current.get("authority", "default")), 0)
        if rank > current_rank or (
                rank == current_rank and stamp >= str(current.get("updated_at", ""))):
            out[name] = {"value": value, "source": str(source),
                         "authority": str(source) if str(source) in AUTHORITY_RANK
                         else "model_inferred",
                         "confidence": confidence, "updated_at": stamp}

    det = detections or {}
    if det.get("location"):
        set_field("location", str(det["location"])[:160])
    if det.get("addressee"):
        set_field("addressee", str(det["addressee"])[:80])
    if det.get("activity"):
        set_field("activity", str(det["activity"])[:120])
    if det.get("mode"):
        set_field("mode", str(det["mode"])[:40])
    if det.get("clock"):
        set_field("clock", det["clock"])
    participants = _participants(out.get("participants"))
    for name in _names(det.get("arrived")):
        if name not in participants:
            participants.append(name)
    for name in _names(det.get("departed")):
        # Removal needs explicit departure evidence: only this path removes,
        # and only names it names. Never infer absence.
        if name in participants:
            participants.remove(name)
    if participants != _participants(out.get("participants")) or (
            _names(det.get("arrived")) or _names(det.get("departed"))):
        out["participants"] = {
            "value": participants, "source": str(source),
            "authority": str(source) if str(source) in AUTHORITY_RANK else "model_inferred",
            "confidence": confidence, "updated_at": stamp,
        }
    return out


def _names(value: Any) -> List[str]:
    if isinstance(value, str):
        value = value.replace(";", ",").split(",")
    return [str(v).strip()[:60] for v in (value or []) if str(v).strip()][:6]


def _participants(entry: Any) -> List[str]:
    if isinstance(entry, dict) and isinstance(entry.get("value"), list):
        return [str(v) for v in entry["value"]]
    return []


async def get_active_scene(db: AsyncSession, workspace_id: str,
                           session_id: str) -> Optional[CurrentScene]:
    return (await db.execute(select(CurrentScene).where(
        CurrentScene.honcho_workspace_id == workspace_id,
        CurrentScene.honcho_session_id == session_id,
    ))).scalar_one_or_none()


async def report_detections(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    detections: Dict[str, Any],
    source: str = "model_inferred",
    confidence: float = 0.7,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Apply detections to the active scene (creating it), commit, and return
    the scene dict. Advisory-fail-open wrapper lives at the route layer."""
    now_naive = _now_naive() if now is None else (
        now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now)
    row = await get_active_scene(db, workspace_id, session_id)
    if row is None:
        row = CurrentScene(honcho_workspace_id=workspace_id,
                           honcho_session_id=session_id, epoch_id=1)
        db.add(row)
    fields = apply_detections(_loads(row.fields_json), detections,
                              source=source, confidence=confidence, now=now_naive)
    row.fields_json = json.dumps(fields)
    row.updated_at = now_naive
    db.add(row)
    await db.commit()
    return {"epoch_id": row.epoch_id, "fields": fields}


async def close_epoch(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    reason: str,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    """Synchronous epoch close: snapshot reference + carried matter IDs only.
    Async consolidation reads the epoch row later; its failure can never
    prevent the next epoch opening (this function does not call it)."""
    from src.models.expectation import Expectation, OutcomeState
    from src.models.open_loop import OpenLoop, OpenLoopStatus

    now_naive = _now_naive() if now is None else (
        now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now)
    row = await get_active_scene(db, workspace_id, session_id)
    epoch_id = (row.epoch_id if row else 1)
    fields = _loads(row.fields_json) if row else {}
    carried: List[str] = []
    try:
        open_exps = (await db.execute(select(Expectation.id).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_session_id == session_id,
            Expectation.outcome_state == OutcomeState.UNKNOWN,
            Expectation.superseded_by_id.is_(None),
        ).limit(10))).scalars().all()
        carried.extend(f"expectation:{e}" for e in open_exps)
        open_loops = (await db.execute(select(OpenLoop.id).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_session_id == session_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        ).limit(10))).scalars().all()
        carried.extend(f"open_loop:{l}" for l in open_loops)
    except Exception as err:
        logger.warning("epoch carry-forward listing failed: %s", err)
    db.add(SceneEpoch(
        honcho_workspace_id=workspace_id, honcho_session_id=session_id,
        epoch_id=epoch_id, opened_at=row.created_at if row else now_naive,
        closed_at=now_naive, close_reason=(reason or "")[:200],
        final_snapshot_json=json.dumps(fields),
        carried_matter_ids_json=json.dumps(carried)))
    if row is None:
        row = CurrentScene(honcho_workspace_id=workspace_id,
                           honcho_session_id=session_id, epoch_id=epoch_id + 1)
    else:
        row.epoch_id = epoch_id + 1
    row.carried_matter_ids_json = json.dumps(carried)
    row.updated_at = now_naive
    db.add(row)
    await db.commit()
    return {"closed_epoch": epoch_id, "new_epoch": epoch_id + 1,
            "carried": carried}
