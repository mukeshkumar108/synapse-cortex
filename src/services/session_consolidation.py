"""Session -> Cortex consolidation (experiment, SHADOW ONLY).

Semantic unit under test: the whole completed session, not the single turn.
Given Cortex state at session start + the complete session transcript, a
bounded model proposes a STRUCTURED DELTA (what changed longitudinally as
a result of this session). This is not a summary; it is a proposed delta
with evidence and provenance per op.

Division of labour:
- MODEL owns: what was discussed, what references resolved to, what is new
  vs incidental, duplicates, completions (incl. partial), expectation
  changes, contradictions, meaningful uncertainty, future attention,
  suppressions/boundaries. One call per session, strict schema.
- CODE owns: evidence provenance, validation, lifecycle invariants
  (resolved-state protection, single policies), ambiguity handling,
  idempotency, auditability, budgets, safe failure.

This module NEVER mutates interpreted state. It validates the proposal,
reports per-op would-apply against current rows, and writes ONE audit
trace (stage="session_consolidation", status shadow/error). Authoritative
apply is deliberately not implemented in this tranche.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

ENABLED_ENV = "SESSION_CONSOLIDATION_ENABLED"

MAX_TURNS = 40
TRANSCRIPT_CHAR_CAP = 6000
MAX_MATTERS = 20
MATTER_TITLE_CAP = 160
MAX_OPS = 24
MIN_CONFIDENCE = 0.6

OP_TYPES = (
    "affirm_matter",      # existing matter is correct as-is (precision ballast)
    "new_matter",         # genuinely new trackable content
    "resolve_matter",     # an open matter completed/cancelled this session
    "partial_fulfilment", # part done, remainder outstanding
    "same_as",            # two rows are the same underlying matter
    "revise_expectation", # expectation outcome/state change
    "suppress",           # boundary/suppression established
    "attend",             # future attention opportunity
    "uncertainty",        # meaningful uncertainty, no action
    "incidental",         # explicit discard: nothing durable here
)

MATTER_KINDS = ("open_loop", "commitment", "expectation")
RESOLVE_VIA = ("completed", "cancelled", "superseded")
EXPECTATION_OUTCOMES = ("fulfilled", "violated", "unknown")
NEW_KINDS = ("obligation", "watch", "uncertainty", "event")


@dataclass(frozen=True)
class SessionTurn:
    message_id: str
    speaker: str
    text: str


@dataclass(frozen=True)
class SnapshotMatter:
    id: str
    kind: str  # open_loop | commitment | expectation
    title: str
    status: str
    owner: str = ""


@dataclass(frozen=True)
class StartSnapshot:
    matters: List[SnapshotMatter] = field(default_factory=list)
    attentions: List[str] = field(default_factory=list)
    suppressions: List[str] = field(default_factory=list)
    people: List[str] = field(default_factory=list)
    # Current epistemic claims (SnapshotClaim, services/consolidation_world.py):
    # lets a session revise a claim by id without the model inventing ids.
    claims: List[Any] = field(default_factory=list)


@dataclass
class ValidatedOp:
    op: str
    data: Dict[str, Any]
    confidence: float
    rationale: str = ""


@dataclass
class ConsolidationResult:
    accepted: List[ValidatedOp] = field(default_factory=list)
    rejected: List[Dict[str, Any]] = field(default_factory=list)
    would_apply: List[Dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    error: str = ""
    prompt_chars: int = 0


def consolidation_enabled() -> bool:
    return os.getenv(ENABLED_ENV, "1") == "1"


def build_prompt(snapshot: StartSnapshot, transcript: List[SessionTurn],
                 created: Optional[List[SnapshotMatter]] = None) -> str:
    turns = transcript[:MAX_TURNS]
    lines = [
        "SESSION CONSOLIDATOR: propose the structured Cortex delta for this completed session.",
        "This is not a summary. Propose what CHANGED longitudinally: updates, new matters,",
        "resolutions (incl. partial), duplicates, expectation changes, suppressions, future",
        "attention, meaningful uncertainty — and explicitly mark incidental turns as incidental.",
        "Conservative: prefer fewer ops over guessing; never invent facts or message IDs.",
        "",
        "CORTEX STATE AT SESSION START (open/tracked matters):",
    ]
    if snapshot.matters:
        for m in snapshot.matters[:MAX_MATTERS]:
            lines.append(
                f"- [matter {m.id}] {m.kind} {m.status}"
                + (f" owner={m.owner}" if m.owner else "")
                + f": {(m.title or 'untitled')[:MATTER_TITLE_CAP]}")
    else:
        lines.append("(none tracked)")
    if created:
        lines.append("")
        lines.append("MATTERS FIRST SEEN THIS SESSION (created by incremental ingest "
                     "during these turns — review them, do not double-count):")
        for m in created[:MAX_MATTERS]:
            lines.append(
                f"- [matter {m.id}] {m.kind} {m.status}"
                + (f" owner={m.owner}" if m.owner else "")
                + f": {(m.title or 'untitled')[:MATTER_TITLE_CAP]}")
    if snapshot.people:
        lines.append("PEOPLE: " + ", ".join(snapshot.people[:12]))
    if snapshot.suppressions:
        lines.append("ACTIVE SUPPRESSIONS: " + "; ".join(snapshot.suppressions[:8]))
    lines.append("")
    lines.append("SESSION TRANSCRIPT (in order, speakers: user / external:<name> / bank_feed / system):")
    used = 0
    for t in turns:
        chunk = f"[msg:{t.message_id}] {t.speaker}: {(t.text or '').strip()}"
        if used + len(chunk) > TRANSCRIPT_CHAR_CAP:
            break
        lines.append(chunk)
        used += len(chunk)
    lines.extend([
        "",
        "Output exactly the delta as ops. Op types: affirm_matter{matter_id}, "
        "new_matter{title, matter_kind, evidence{message_ids, spans}}, "
        "resolve_matter{matter_id, via, evidence}, "
        "partial_fulfilment{matter_id, evidence, remainder}, "
        "same_as{matter_id_a, matter_id_b, evidence}, "
        "revise_expectation{expectation_id, outcome, note, evidence}, "
        "suppress{topic_or_entity, reason, evidence}, "
        "attend{content, related_ids, evidence}, "
        "uncertainty{content, alternatives, related_ids, evidence}, "
        "incidental{message_ids}.",
        "Every state-changing op needs evidence{message_ids[], spans[]} with VERBATIM spans "
        "from the cited turns; affirm_matter/incidental need no spans. "
        "Include confidence 0..1 per op and a one-line rationale. Max "
        f"{MAX_OPS} ops.",
    ])
    return "\n".join(lines)


def _spans_grounded(spans: Any, by_msg: Dict[str, str]) -> bool:
    if not isinstance(spans, list):
        return False
    for entry in spans:
        if not isinstance(entry, dict):
            return False
        mid = str(entry.get("message_id") or "")
        span = str(entry.get("span") or "")
        if mid not in by_msg or not span.strip():
            return False
        if span.strip() not in (by_msg[mid] or ""):
            return False
    return True


def _evidence(raw: Any, by_msg: Dict[str, str], *, required: bool) -> Optional[Dict[str, Any]]:
    """Validate the evidence block. Returns normalized {message_ids, spans}
    or None when invalid (or when required and empty)."""
    if not isinstance(raw, dict):
        return None if required else {"message_ids": [], "spans": []}
    mids = raw.get("message_ids") or []
    spans = raw.get("spans") or []
    if not isinstance(mids, list) or not all(isinstance(m, str) for m in mids):
        return None
    if any(m not in by_msg for m in mids):
        return None
    if required and not mids:
        return None
    if spans and not _spans_grounded(spans, by_msg):
        return None
    if required and not spans:
        return None
    return {"message_ids": [str(m) for m in mids],
            "spans": [{"message_id": str(s.get("message_id")),
                       "span": str(s.get("span"))} for s in spans] if spans else []}


def validate_ops(raw_ops: Any, *, snapshot: StartSnapshot,
                 transcript: List[SessionTurn],
                 extra_known_ids: Optional[set] = None) -> tuple[list, list]:
    """Deterministic validation. Returns (accepted, rejected). Never raises.

    `extra_known_ids`: matter ids first seen during this session (created by
    incremental ingest) — referenceable so the delta can review them, but
    they never substitute for evidence."""
    accepted: List[ValidatedOp] = []
    rejected: List[Dict[str, Any]] = []
    if not isinstance(raw_ops, list):
        return accepted, [{"op": "?", "reason": "ops_not_a_list"}]
    by_msg = {t.message_id: t.text or "" for t in transcript}
    known_ids = {m.id for m in snapshot.matters} | set(extra_known_ids or set())
    seen: set = set()
    for raw in raw_ops[:MAX_OPS]:
        if not isinstance(raw, dict):
            rejected.append({"op": "?", "reason": "op_not_an_object"})
            continue
        op = str(raw.get("op") or "").strip()
        if op not in OP_TYPES:
            rejected.append({"op": op or "?", "reason": "unknown_op"})
            continue
        try:
            conf = float(raw.get("confidence") or 0.0)
        except (TypeError, ValueError):
            rejected.append({"op": op, "reason": "bad_confidence"})
            continue
        if not (MIN_CONFIDENCE <= conf <= 1.0):
            rejected.append({"op": op, "reason": "confidence_below_floor"})
            continue
        rationale = str(raw.get("rationale") or "")[:280]
        data: Dict[str, Any] = {}
        ok = True

        def need_evidence() -> Optional[Dict[str, Any]]:
            ev = _evidence(raw.get("evidence"), by_msg, required=True)
            if ev is None:
                rejected.append({"op": op, "reason": "bad_evidence"})
                return None
            return ev

        if op == "affirm_matter":
            mid = str(raw.get("matter_id") or "")
            if mid not in known_ids:
                rejected.append({"op": op, "reason": "unknown_matter_id"})
                continue
            data = {"matter_id": mid}
        elif op == "new_matter":
            title = str(raw.get("title") or "").strip()
            kind = str(raw.get("matter_kind") or "").strip()
            if not title or kind not in NEW_KINDS:
                rejected.append({"op": op, "reason": "bad_new_matter"})
                continue
            ev = need_evidence()
            if ev is None:
                continue
            data = {"title": title[:280], "matter_kind": kind, "evidence": ev}
        elif op in ("resolve_matter", "partial_fulfilment"):
            mid = str(raw.get("matter_id") or "")
            if mid not in known_ids:
                rejected.append({"op": op, "reason": "unknown_matter_id"})
                continue
            ev = need_evidence()
            if ev is None:
                continue
            if op == "resolve_matter":
                via = str(raw.get("via") or "").strip()
                if via not in RESOLVE_VIA:
                    rejected.append({"op": op, "reason": "bad_via"})
                    continue
                data = {"matter_id": mid, "via": via, "evidence": ev}
            else:
                remainder = str(raw.get("remainder") or "").strip()
                if not remainder:
                    rejected.append({"op": op, "reason": "partial_needs_remainder"})
                    continue
                data = {"matter_id": mid, "evidence": ev,
                        "remainder": remainder[:280]}
        elif op == "same_as":
            a = str(raw.get("matter_id_a") or "")
            b = str(raw.get("matter_id_b") or "")
            if not a or not b or a == b or a not in known_ids or b not in known_ids:
                rejected.append({"op": op, "reason": "bad_same_as_targets"})
                continue
            ev = need_evidence()
            if ev is None:
                continue
            data = {"matter_id_a": a, "matter_id_b": b, "evidence": ev}
        elif op == "revise_expectation":
            eid = str(raw.get("expectation_id") or "")
            outcome = str(raw.get("outcome") or "").strip()
            if eid not in known_ids or outcome not in EXPECTATION_OUTCOMES:
                rejected.append({"op": op, "reason": "bad_expectation_target"})
                continue
            ev = need_evidence()
            if ev is None:
                continue
            data = {"expectation_id": eid, "outcome": outcome,
                    "note": str(raw.get("note") or "")[:280], "evidence": ev}
        elif op == "suppress":
            topic = str(raw.get("topic_or_entity") or "").strip()
            reason = str(raw.get("reason") or "").strip()
            if not topic or not reason:
                rejected.append({"op": op, "reason": "bad_suppress"})
                continue
            ev = need_evidence()
            if ev is None:
                continue
            data = {"topic_or_entity": topic[:160], "reason": reason[:280],
                    "evidence": ev}
        elif op in ("attend", "uncertainty"):
            content = str(raw.get("content") or "").strip()
            if not content:
                rejected.append({"op": op, "reason": "empty_content"})
                continue
            related = [str(i) for i in (raw.get("related_ids") or [])
                       if str(i) in known_ids]
            data = {"content": content[:500], "related_ids": related}
            if op == "uncertainty":
                alts = [str(a) for a in (raw.get("alternatives") or [])][:4]
                data["alternatives"] = [a[:160] for a in alts if a.strip()]
            ev = _evidence(raw.get("evidence"), by_msg, required=False)
            if ev is None:
                rejected.append({"op": op, "reason": "bad_evidence"})
                continue
            # Grounding rule (generic, not scenario-specific): an attention
            # or uncertainty hold must be traceable — verbatim spans, or a
            # link to a known matter plus cited transcript provenance.
            # Bare content with neither is unauditable future clutter.
            if not ev["spans"] and not (related and ev["message_ids"]):
                rejected.append({"op": op, "reason": "ungrounded_no_spans_no_link"})
                continue
            data["evidence"] = ev
        elif op == "incidental":
            mids = raw.get("message_ids") or []
            if (not isinstance(mids, list) or not mids
                    or not all(isinstance(m, str) and m in by_msg for m in mids)):
                rejected.append({"op": op, "reason": "bad_incidental_mids"})
                continue
            data = {"message_ids": [str(m) for m in mids]}
        if not ok:
            continue
        fingerprint = (op, json.dumps(data, sort_keys=True, default=str))
        if fingerprint in seen:
            rejected.append({"op": op, "reason": "duplicate_op"})
            continue
        seen.add(fingerprint)
        accepted.append(ValidatedOp(op=op, data=data, confidence=conf,
                                   rationale=rationale))
    if isinstance(raw_ops, list) and len(raw_ops) > MAX_OPS:
        rejected.append({"op": "*", "reason": f"ops_capped_at_{MAX_OPS}"})
    return accepted, rejected


async def capture_snapshot(db: Any, *, workspace_id: str, session_id: str) -> StartSnapshot:
    """Read the current interpreted state as the consolidation start point.
    Non-mutating; fail-open empty."""
    from sqlmodel import select

    from src.models.attention_candidate import (
        AttentionCandidate, AttentionCandidateStatus,
    )
    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.models.suppression import Suppression, SuppressionStatus

    snap = StartSnapshot()
    try:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_session_id == session_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        ).order_by(OpenLoop.created_at))).scalars().all()
        snap.matters.extend(SnapshotMatter(
            id=str(l.id), kind="open_loop", title=f"{l.title or ''}",
            status="OPEN", owner=l.owner_peer_id or "") for l in loops)
        commits = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.honcho_session_id == session_id,
        ).order_by(CommitmentCandidate.created_at))).scalars().all()
        snap.matters.extend(SnapshotMatter(
            id=str(c.id), kind="commitment",
            title=f"{c.title or ''}",
            status=f"{c.status.value if hasattr(c.status, 'value') else c.status}"
                   f"/{c.authority.value if hasattr(c.authority, 'value') else c.authority}",
            owner=c.owner_peer_id or "") for c in commits)
        exps = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_session_id == session_id,
        ).order_by(Expectation.created_at))).scalars().all()
        snap.matters.extend(SnapshotMatter(
            id=str(e.id), kind="expectation", title=f"{e.title or ''}",
            status=str(getattr(e.outcome_state, "value", e.outcome_state)),
            owner=e.owner_peer_id or "") for e in exps)
        atts = (await db.execute(select(AttentionCandidate).where(
            AttentionCandidate.honcho_workspace_id == workspace_id,
            AttentionCandidate.status == AttentionCandidateStatus.ACTIVE,
        ).limit(6))).scalars().all()
        snap.attentions.extend((a.content or "")[:160] for a in atts)
        supps = (await db.execute(select(Suppression).where(
            Suppression.honcho_workspace_id == workspace_id,
            Suppression.status == SuppressionStatus.ACTIVE,
        ).limit(8))).scalars().all()
        snap.suppressions.extend(
            (s.topic_or_entity or "")[:80] for s in supps if s.topic_or_entity)
    except Exception as err:
        logger.warning("consolidation snapshot failed (fail-open): %s", err)
    try:
        from src.services.consolidation_world import capture_claims
        snap.claims.extend(await capture_claims(
            db, workspace_id=workspace_id, session_id=session_id, owner_peer_id=None))
    except Exception as err:
        logger.warning("consolidation claim snapshot failed (fail-open): %s", err)
    return snap


async def check_would_apply(db: Any, *, workspace_id: str,
                            accepted: List[ValidatedOp]) -> List[Dict[str, Any]]:
    """Shadow apply-check: for each accepted op, verify the invariant outcome
    against CURRENT rows without mutating anything. Reports per-op
    would_apply + reason — the evidence an authoritative applier would need."""
    from sqlmodel import select
    from uuid import UUID as _UUID

    from src.models.commitment_candidate import (
        CommitmentCandidate, CommitmentCandidateStatus,
    )
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop, OpenLoopStatus
    from src.models.suppression import Suppression, SuppressionStatus

    async def _row(model: Any, mid: str) -> Any:
        try:
            uuid = _UUID(str(mid))
        except (TypeError, ValueError):
            return None
        try:
            row = (await db.execute(select(model).where(
                model.id == uuid,
                model.honcho_workspace_id == workspace_id))).scalar_one_or_none()
        except Exception:
            return None
        return row

    report: List[Dict[str, Any]] = []
    for op in accepted:
        d = op.data
        if op.op == "affirm_matter":
            found = await _row(OpenLoop, d["matter_id"]) \
                or await _row(CommitmentCandidate, d["matter_id"]) \
                or await _row(Expectation, d["matter_id"])
            report.append({"op": op.op, "would_apply": found is not None,
                           "reason": "target_present" if found is not None else "target_missing"})
        elif op.op == "new_matter":
            report.append({"op": op.op, "would_apply": True,
                           "reason": "novel_title_would_mint"})
        elif op.op in ("resolve_matter", "partial_fulfilment"):
            row = await _row(OpenLoop, d["matter_id"]) \
                or await _row(CommitmentCandidate, d["matter_id"])
            if row is None:
                report.append({"op": op.op, "would_apply": False,
                               "reason": "target_missing"})
            else:
                status = str(getattr(row.status, "value", row.status)).upper()
                live = status in ("OPEN", "PENDING")
                if op.op == "resolve_matter":
                    report.append({
                        "op": op.op, "would_apply": live,
                        "reason": "target_open_or_pending" if live
                        else f"resolved_state_protected:{status}"})
                else:
                    report.append({
                        "op": op.op, "would_apply": live,
                        "reason": "partial_accumulates_pending" if live
                        else f"resolved_state_protected:{status}"})
        elif op.op == "same_as":
            ra = await _row(OpenLoop, d["matter_id_a"]) \
                or await _row(CommitmentCandidate, d["matter_id_a"])
            rb = await _row(OpenLoop, d["matter_id_b"]) \
                or await _row(CommitmentCandidate, d["matter_id_b"])
            if ra is None or rb is None:
                report.append({"op": op.op, "would_apply": False,
                               "reason": "target_missing"})
            else:
                sa = str(getattr(ra.status, "value", ra.status)).upper()
                sb = str(getattr(rb.status, "value", rb.status)).upper()
                live = sa in ("OPEN", "PENDING") and sb in ("OPEN", "PENDING")
                report.append({"op": op.op, "would_apply": live,
                               "reason": "both_live_link" if live
                               else "resolved_state_protected"})
        elif op.op == "revise_expectation":
            row = await _row(Expectation, d["expectation_id"])
            report.append({"op": op.op,
                           "would_apply": row is not None,
                           "reason": "expectation_present" if row is not None
                           else "target_missing"})
        elif op.op == "suppress":
            existing = (await db.execute(select(Suppression).where(
                Suppression.honcho_workspace_id == workspace_id,
                Suppression.status == SuppressionStatus.ACTIVE,
            ).limit(50))).scalars().all()
            topic = (d["topic_or_entity"] or "").lower()
            dup = any((s.topic_or_entity or "").lower() == topic for s in existing)
            report.append({"op": op.op, "would_apply": not dup,
                           "reason": "novel_boundary" if not dup
                           else "duplicate_suppression_idempotent"})
        elif op.op in ("attend", "uncertainty"):
            known = True
            try:
                from sqlmodel import select as _s
                for mid in d.get("related_ids", []):
                    if await _row(OpenLoop, mid) is None \
                            and await _row(CommitmentCandidate, mid) is None \
                            and await _row(Expectation, mid) is None:
                        known = False
            except Exception:
                known = False
            report.append({"op": op.op, "would_apply": known,
                           "reason": "related_known" if known
                           else "related_missing"})
        elif op.op == "incidental":
            report.append({"op": op.op, "would_apply": True,
                           "reason": "discard_needs_no_mutation"})
        elif op.op == "claim":
            report.append({"op": op.op, "would_apply": True,
                           "reason": f"epistemic_claim_{d.get('formation', 'inferred')}_would_write"})
        elif op.op == "directed_expectation":
            report.append({"op": op.op, "would_apply": True,
                           "reason": f"{d.get('direction')}_expectation_would_mint"})
        elif op.op == "knowledge_gap":
            report.append({"op": op.op, "would_apply": True,
                           "reason": "unknown_would_be_registered_without_value"})
        else:
            report.append({"op": op.op, "would_apply": False,
                           "reason": "unknown_op"})
    return report


async def capture_session_created(db: Any, *, workspace_id: str,
                                   session_mids: set) -> List[SnapshotMatter]:
    """Rows first seen during this session (incremental ingest creations).
    Review lane for the delta: the model may affirm/merge/resolve them, but
    validation never lets them substitute for transcript evidence."""
    from sqlmodel import select

    from src.models.commitment_candidate import CommitmentCandidate
    from src.models.expectation import Expectation
    from src.models.open_loop import OpenLoop

    out: List[SnapshotMatter] = []
    if not session_mids:
        return out
    try:
        loops = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_message_id.in_(session_mids),
        ))).scalars().all()
        out.extend(SnapshotMatter(
            id=str(l.id), kind="open_loop", title=f"{l.title or ''}",
            status=str(getattr(l.status, "value", l.status)).upper(),
            owner=l.owner_peer_id or "") for l in loops)
        commits = (await db.execute(select(CommitmentCandidate).where(
            CommitmentCandidate.honcho_workspace_id == workspace_id,
            CommitmentCandidate.source_message_id.in_(session_mids),
        ))).scalars().all()
        out.extend(SnapshotMatter(
            id=str(c.id), kind="commitment", title=f"{c.title or ''}",
            status=str(getattr(c.status, "value", c.status)).upper(),
            owner=c.owner_peer_id or "") for c in commits)
        exps = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id,
            Expectation.honcho_message_id.in_(session_mids),
        ))).scalars().all()
        out.extend(SnapshotMatter(
            id=str(e.id), kind="expectation", title=f"{e.title or ''}",
            status=str(getattr(e.outcome_state, "value", e.outcome_state)).upper(),
            owner=e.owner_peer_id or "") for e in exps)
    except Exception as err:
        logger.warning("session-created capture failed (fail-open): %s", err)
    return out


async def consolidate_session(
    db: Any,
    *,
    workspace_id: str,
    session_id: str,
    transcript: List[SessionTurn] | List[Dict[str, Any]],
    start_snapshot: Optional[StartSnapshot] = None,
    adapter: Any = ...,
) -> ConsolidationResult:
    """Run one session consolidation in SHADOW mode. Returns the validated
    proposal + would-apply report. Mutates nothing except one audit trace.
    Any failure holds existing state: raw evidence is canonical, a later
    pass can retry."""
    from src.models.operational_state import ExtractionTrace
    from src.services import semantic_judge

    result = ConsolidationResult()
    turns = [t if isinstance(t, SessionTurn) else SessionTurn(
        message_id=str(t.get("message_id") or ""),
        speaker=str(t.get("speaker") or ""),
        text=str(t.get("text") or "")) for t in (transcript or [])]
    turns = [t for t in turns if t.message_id and (t.text or "").strip()]
    if not consolidation_enabled():
        result.error = "disabled"
        return result
    if not turns:
        result.summary = "empty session: no change, raw evidence retained"
        return result
    if start_snapshot is None:
        start_snapshot = await capture_snapshot(
            db, workspace_id=workspace_id, session_id=session_id)
    session_mids = {t.message_id for t in turns}
    created = await capture_session_created(
        db, workspace_id=workspace_id, session_mids=session_mids)
    prompt = build_prompt(start_snapshot, turns, created)
    result.prompt_chars = len(prompt)

    async def _trace(status: str, detail: Dict[str, Any]) -> None:
        try:
            db.add(ExtractionTrace(
                honcho_workspace_id=workspace_id,
                honcho_session_id=session_id,
                honcho_message_id=f"consolidation:{session_id}",
                stage="session_consolidation",
                item_key=f"consolidation:{session_id}",
                status=status,
                model=semantic_judge.judge_model_id(),
                detail_json=json.dumps(detail, default=str)[:4000],
            ))
            await db.commit()
        except Exception as err:
            logger.warning("consolidation trace failed: %s", err)
            try:
                await db.rollback()
            except Exception:
                pass

    if adapter is ...:
        adapter = semantic_judge._adapter()
    if adapter is None:
        result.error = "no_adapter"
        result.summary = "no model available: existing state holds, retry later"
        await _trace("error", {"error": result.error})
        return result
    try:
        raw = await adapter.generate_structured(
            system=(
                "You are a session consolidator for a companion-memory system. "
                "Propose the longitudinal delta implied by the whole session. "
                "Conservative: fewer ops over guessing. Never invent facts, "
                "message IDs, or matter IDs."
            ),
            prompt=prompt,
            json_schema={
                "type": "object",
                "properties": {
                    "session_summary": {"type": "string"},
                    "ops": {
                        "type": "array",
                        "maxItems": MAX_OPS,
                        "items": {
                            "type": "object",
                            "properties": {
                                "op": {"type": "string"},
                                "matter_id": {"type": "string"},
                                "matter_id_a": {"type": "string"},
                                "matter_id_b": {"type": "string"},
                                "expectation_id": {"type": "string"},
                                "outcome": {"type": "string"},
                                "via": {"type": "string"},
                                "title": {"type": "string"},
                                "matter_kind": {"type": "string"},
                                "topic_or_entity": {"type": "string"},
                                "reason": {"type": "string"},
                                "note": {"type": "string"},
                                "content": {"type": "string"},
                                "alternatives": {"type": "array",
                                                 "items": {"type": "string"}},
                                "related_ids": {"type": "array",
                                                "items": {"type": "string"}},
                                "message_ids": {"type": "array",
                                                "items": {"type": "string"}},
                                "remainder": {"type": "string"},
                                "confidence": {"type": "number"},
                                "rationale": {"type": "string"},
                                "evidence": {"type": "object"},
                            },
                            "required": ["op", "confidence", "rationale"],
                            "additionalProperties": True,
                        },
                    },
                },
                "required": ["session_summary", "ops"],
                "additionalProperties": False,
            },
            model_id=semantic_judge.judge_model_id(),
            max_tokens=2000,
            temperature=0.0,
            strict=True,
        )
    except Exception as exc:
        logger.warning("consolidation call failed (fail-open): %s", exc)
        result.error = "call_failed"
        result.summary = "model unavailable: existing state holds, retry later"
        await _trace("error", {"error": result.error})
        return result
    if not isinstance(raw, dict) or not isinstance(raw.get("ops"), list):
        result.error = "malformed"
        result.summary = "invalid model output: existing state holds, retry later"
        await _trace("error", {"error": result.error})
        return result
    result.summary = str(raw.get("session_summary") or "")[:500]
    accepted, rejected = validate_ops(
        raw.get("ops"), snapshot=start_snapshot, transcript=turns,
        extra_known_ids={m.id for m in created})
    result.accepted = accepted
    result.rejected = rejected
    if not accepted and not rejected:
        # A model that proposes nothing verifiable leaves no trace of its
        # reasoning otherwise: record the fail-closed hold explicitly so
        # later passes can distinguish "held empty" from "never ran".
        await _trace("held_empty", {"summary": result.summary})
        return result
    try:
        result.would_apply = await check_would_apply(
            db, workspace_id=workspace_id, accepted=accepted)
    except Exception as err:
        logger.warning("would-apply check failed: %s", err)
        result.would_apply = []
    await _trace("shadow", {
        "summary": result.summary,
        "accepted": [(o.op, o.data) for o in accepted],
        "rejected": rejected,
        "would_apply": result.would_apply,
    })
    return result


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
