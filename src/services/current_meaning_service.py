"""CurrentMeaning v1 service (semantic owner: Cortex fast lane).

Separation enforced here:
  current_meanings rows = what Cortex currently believes
    (means / unresolved / provenance / version-supersession ONLY).
  revise-sync result authority = whether foreground needs that belief now
    (ephemeral per-turn decision; authority change creates zero rows).

Runtime supplies: current turn + bounded recent local conversation + scope /
product (+ optional expected lens version + expected prior id/version).
Cortex assembles Cortex-owned evidence internally (prior row + bounded
objectives / loops / suppressions / resolutions) so the call stays parallel
with run_cortex() and ownership stays clean.

Concurrency: CAS on expected prior + idempotency on (scope_key,
revision_key) + per-scope advisory lock on Postgres (SQLite: rely on the
unique backstops + rollback/re-read). A result authored against a stale
prior is DISCARDED, never rebased. First-write races resolve via the same
path (lock or unique-conflict rollback + re-read); the partial unique
active index is the invariant backstop, not the algorithm.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.current_meaning import (
    CurrentMeaning,
    canonical_owner_peer,
    scope_key_for,
)
from src.models.expectation import Expectation, OutcomeState
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.suppression import Suppression, SuppressionStatus
from src.services.meaning_lens import resolve_lens

logger = logging.getLogger(__name__)

MEANING_EXTRACTOR_VERSION = "fast-meaning-v1"
MEANING_MODEL = os.getenv("MEANING_MODEL", "google/gemini-3.1-flash-lite").strip()
MEANING_MAX_TOKENS = int(os.getenv("MEANING_MAX_TOKENS", "400"))
MEANING_TIMEOUT_SECONDS = float(os.getenv("MEANING_TIMEOUT_SECONDS", "12"))

MAX_MEANS_LINES = 3
MAX_UNRESOLVED_ITEMS = 3
MAX_LINE_CHARS = 140
MAX_TURN_CHARS = 4000
MAX_HISTORY_ITEMS = 6
MAX_HISTORY_CHARS_EACH = 700


def _loads_list(raw: Any) -> List[str]:
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, ValueError):
        return []
    return [str(x) for x in data] if isinstance(data, list) else []


def _norm(text_value: str) -> str:
    return " ".join(str(text_value or "").split()).strip().lower()


def _cut_line(text_value: str) -> str:
    return " ".join(str(text_value or "").split()).strip()[:MAX_LINE_CHARS]


def row_to_dict(row: CurrentMeaning) -> Dict[str, Any]:
    return {
        "id": str(row.id),
        "version": row.version,
        "means": _loads_list(row.means_json),
        "unresolved": _loads_list(row.unresolved_json),
        "provenance": {
            "source_message_ids": _loads_list(row.source_message_ids_json),
            "extractor_version": row.extractor_version,
            "lens_version": row.lens_version,
            "observed_at": row.observed_at.isoformat() if row.observed_at else None,
        },
        "revision_key": row.revision_key,
        "scope_key": row.scope_key,
    }


async def get_active(
    db: AsyncSession, *, scope_key: str,
) -> Optional[CurrentMeaning]:
    stmt = (
        select(CurrentMeaning)
        .where(
            CurrentMeaning.scope_key == scope_key,
            CurrentMeaning.superseded_by_id.is_(None),
        )
        .order_by(CurrentMeaning.version.desc())
        .limit(1)
    )
    return (await db.execute(stmt)).scalars().first()


async def _scope_lock(db: AsyncSession, scope_key: str) -> None:
    """Per-scope serialization. Postgres: advisory xact lock. SQLite (tests /
    dev): no-op — correctness comes from CAS + unique backstops + re-read."""
    bind = db.bind
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", "") if dialect else ""
    if name.startswith("postgresql"):
        digest = hashlib.sha256(scope_key.encode()).hexdigest()[:15]
        await db.execute(
            text("SELECT pg_advisory_xact_lock(:k)"),
            {"k": int(digest, 16)},
        )


async def load_cortex_evidence(
    db: AsyncSession,
    *,
    workspace_id: str,
    session_id: str,
    owner_peer_id: str,
    now: datetime,
) -> Dict[str, Any]:
    """Bounded Cortex-owned evidence assembled INTERNALLY (never round-tripped
    through Runtime). Same bounds as turn_context digest."""
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
            .limit(4)
        )
    ).scalars().all()
    loops = (
        await db.execute(
            select(OpenLoop)
            .where(
                OpenLoop.honcho_workspace_id == workspace_id,
                OpenLoop.honcho_session_id == session_id,
                OpenLoop.status == OpenLoopStatus.OPEN,
            )
            .order_by(OpenLoop.created_at.desc())
            .limit(3)
        )
    ).scalars().all()
    suppressions = (
        await db.execute(
            select(Suppression)
            .where(
                Suppression.honcho_workspace_id == workspace_id,
                Suppression.honcho_session_id == session_id,
            )
            .order_by(Suppression.created_at.desc())
            .limit(3)
        )
    ).scalars().all()
    return {
        "objectives": [
            {"title": o.title, "summary": (o.summary or "")[:100]} for o in objectives
        ],
        "open_loops": [{"title": l.title} for l in loops],
        "suppressed_topics": [
            s.topic_or_entity for s in suppressions if s.topic_or_entity
        ][:3],
    }


def validate_proposal(
    *, raw: Dict[str, Any], turn_text: str, prior: Optional[CurrentMeaning],
) -> Optional[Dict[str, Any]]:
    """Deterministic validator. Returns cleaned proposal or None (no_change /
    invalid → carry/omit, never fabricate)."""
    if not isinstance(raw, dict):
        return None
    if raw.get("no_change") is True:
        return None
    means = [_cut_line(x) for x in (raw.get("means") or []) if str(x or "").strip()]
    unresolved = [_cut_line(x) for x in (raw.get("unresolved") or []) if str(x or "").strip()]
    means = means[:MAX_MEANS_LINES]
    unresolved = unresolved[:MAX_UNRESOLVED_ITEMS]
    if not means and not unresolved:
        return None
    authority = str(raw.get("foreground_authority") or "active").lower()
    if authority not in {"active", "backgrounded"}:
        authority = "active"
    evidence_span = str(raw.get("evidence_span") or "").strip()
    if evidence_span and _norm(evidence_span) not in _norm(turn_text):
        logger.info("[current-meaning] evidence span not verbatim; rejecting proposal")
        return None
    if prior is not None:
        prior_means = [_norm(x) for x in _loads_list(prior.means_json)]
        prior_unres = [_norm(x) for x in _loads_list(prior.unresolved_json)]
        if [_norm(x) for x in means] == prior_means and [_norm(x) for x in unresolved] == prior_unres:
            return None  # identical → carry, no churn row
    return {"means": means, "unresolved": unresolved, "foreground_authority": authority}


async def commit_revision(
    db: AsyncSession,
    *,
    scope: Dict[str, str],
    scope_key: str,
    revision_key: str,
    source_message_ids: List[str],
    proposal: Dict[str, Any],
    lens_version: str,
    now: datetime,
    expected_prior_id: Optional[str],
    expected_prior_version: Optional[int],
) -> Dict[str, Any]:
    """Transactional CAS + idempotency. Returns outcome dict; never forks.

    Outcomes: committed | idempotent_hit | stale_prior (discard, never rebase).
    """
    await _scope_lock(db, scope_key)
    # Idempotency first: same key → same version, no duplicate.
    existing = (
        await db.execute(
            select(CurrentMeaning).where(
                CurrentMeaning.scope_key == scope_key,
                CurrentMeaning.revision_key == revision_key,
            )
        )
    ).scalars().first()
    if existing is not None:
        return {"outcome": "idempotent_hit", "row": row_to_dict(existing)}

    active = await get_active(db, scope_key=scope_key)
    if expected_prior_id is not None or expected_prior_version is not None:
        active_id = str(active.id) if active else None
        active_version = active.version if active else None
        if active_id != expected_prior_id or active_version != expected_prior_version:
            # Authored against the wrong state: discard, never rebase.
            return {
                "outcome": "stale_prior",
                "active": row_to_dict(active) if active else None,
            }
    else:
        # No expectation supplied: proceed only if no active row moved under
        # us — the get_active above + unique backstop handles it.
        pass

    naive_now = now.astimezone(timezone.utc).replace(tzinfo=None) if now.tzinfo else now
    row = CurrentMeaning(
        honcho_workspace_id=scope["workspace_id"],
        product=scope["product"],
        honcho_session_id=scope["session_id"],
        owner_peer_id=canonical_owner_peer(scope.get("owner_peer_id")),
        scope_key=scope_key,
        means_json=json.dumps(proposal["means"]),
        unresolved_json=json.dumps(proposal["unresolved"]),
        source_message_ids_json=json.dumps(source_message_ids),
        extractor_version=MEANING_EXTRACTOR_VERSION,
        lens_version=lens_version,
        observed_at=naive_now,
        revision_key=revision_key,
        version=(active.version + 1) if active else 1,
    )
    try:
        if active is not None:
            # CAS re-check inside the txn: prior must still be active.
            await db.refresh(active)
            if active.superseded_by_id is not None:
                await db.rollback()
                fresh = await get_active(db, scope_key=scope_key)
                return {
                    "outcome": "stale_prior",
                    "active": row_to_dict(fresh) if fresh else None,
                }
            # Supersede BEFORE inserting: the partial unique active index
            # permits exactly one NULL-superseded row per scope, so the
            # UPDATE must land first within the transaction.
            active.superseded_by_id = row.id
            db.add(active)
            await db.flush()
        db.add(row)
        await db.flush()
        await db.commit()
    except IntegrityError:
        # Unique backstop fired (active-pointer or revision-key race):
        # rollback, re-read, report — never fork.
        await db.rollback()
        hit = (
            await db.execute(
                select(CurrentMeaning).where(
                    CurrentMeaning.scope_key == scope_key,
                    CurrentMeaning.revision_key == revision_key,
                )
            )
        ).scalars().first()
        if hit is not None:
            return {"outcome": "idempotent_hit", "row": row_to_dict(hit)}
        fresh = await get_active(db, scope_key=scope_key)
        return {"outcome": "stale_prior", "active": row_to_dict(fresh) if fresh else None}
    await db.refresh(row)
    return {"outcome": "committed", "row": row_to_dict(row)}


def build_interpreter_prompt(
    *, lens_system: str, turn_text: str, prior: Optional[Dict[str, Any]],
    history: List[Dict[str, str]], cortex_evidence: Dict[str, Any],
) -> str:
    return (
        f"{lens_system}\n\nPRIOR CURRENT MEANING:\n{json.dumps(prior)[:2000]}\n\n"
        f"BOUNDED CORTEX EVIDENCE:\n{json.dumps(cortex_evidence)[:2000]}\n\n"
        f"BOUNDED RECENT CONVERSATION (local, oldest first):\n{json.dumps(history)[:3000]}\n\n"
        f"CURRENT USER TURN:\n{turn_text[:4000]}\n\n"
        "Respond with ONLY a JSON object: "
        '{"means": [...], "unresolved": [...], '
        '"foreground_authority": "active|backgrounded", '
        '"evidence_span": "<verbatim substring of CURRENT USER TURN>", '
        '"confidence": 0..1, "no_change": true|false}.'
    )


async def run_interpreter(
    *, adapter: Any, system: str, prompt: str,
) -> Optional[Dict[str, Any]]:
    if adapter is None:
        return None
    try:
        raw = await adapter.generate_structured(
            system=system,
            prompt=prompt,
            json_schema={
                "type": "object",
                "properties": {
                    "means": {"type": "array", "items": {"type": "string"}},
                    "unresolved": {"type": "array", "items": {"type": "string"}},
                    "foreground_authority": {"type": "string"},
                    "evidence_span": {"type": "string"},
                    "confidence": {"type": "number"},
                    "no_change": {"type": "boolean"},
                },
                "required": ["means", "unresolved", "no_change"],
                "additionalProperties": False,
            },
            model_id=MEANING_MODEL,
            max_tokens=MEANING_MAX_TOKENS,
            temperature=0.0,
            strict=True,
        )
    except Exception as exc:
        logger.warning("[current-meaning] interpreter failed (fail-closed): %s", exc)
        return None
    return raw if isinstance(raw, dict) else None
