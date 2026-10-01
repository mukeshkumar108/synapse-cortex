"""World-model sections of session consolidation (docs/CORTEX_ARCHITECTURE.md §12).

Session reconstruction already proposes matters / uncertainties / attentions /
suppressions. This module adds the rest of what a session may establish — as
validated proposals that are applied through the SAME canonical primitives:

  claims[]    durable interpretive claims (pattern, observation, correction,
              relationship_development, repair, decision, perspective) ->
              ModelEntry via the epistemic write path (formation classes,
              no hardening of interpretation into fact, system perspective
              stays actor-owned)
  directed[]  expectations with an explicit direction (user_to_system /
              system_to_user) -> Expectation(direction=...)
  gaps[]      useful known-unknowns -> knowledge_coverage (registered as
              `unknown`, never a value)

The model never writes state: code validates verbatim evidence and the
epistemic rules below, then `apply_world_op` commits through the existing
persistence. The SessionEpisode only references what these wrote.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import timezone
from typing import Any, Dict, List, Optional, Tuple

from src.services.epistemics import CLAIM_KINDS, FORMATION_CLASSES, is_firm
from src.services.knowledge_coverage_service import KEY_RE

MAX_CLAIMS = 6
MAX_DIRECTED = 4
MAX_GAPS = 4
CLAIM_CONFIDENCE_FLOOR = 0.6
DIRECTIONS = ("user_to_system", "system_to_user")
CLAIM_KINDS_PROPOSABLE = tuple(sorted(CLAIM_KINDS - {"matter_summary", "user_model"}))

WORLD_OPS = ("claim", "directed_expectation", "knowledge_gap")


@dataclass(frozen=True)
class SnapshotClaim:
    id: str
    claim_kind: str
    formation: str
    text: str
    holder: str = ""


PROMPT_BLOCK = "\n".join([
    "",
    "WORLD SECTIONS (all optional; propose NOTHING unless the evidence carries it):",
    "claims[]: durable interpretive claims. {claim, claim_kind "
    + "|".join(CLAIM_KINDS_PROPOSABLE) + ", formation explicit|reported|observed|inferred|hypothesis,",
    "  subjects[], related_ids[] (start-state matter ids), supersedes_claim_id (from CLAIMS AT START only),",
    "  direction shared|user_to_system|system_to_user (only for relationship claims), evidence{message_ids,spans},",
    "  confidence, rationale}. EPISTEMIC RULES: formation explicit/reported REQUIRES verbatim spans and means",
    "  the user actually said it (reported = they relayed what someone else said/did). observed/inferred/hypothesis",
    "  are YOUR reading: state them as readings, never as facts about other people (valid: 'Kai has repeatedly",
    "  reported feeling Ashley defended her actions'; invalid: 'Ashley is defensive'). An inferred claim may NOT",
    "  replace an explicit one. claim_kind=perspective is the COMPANION's own thought/hypothesis/question, not world truth.",
    "directed[]: {direction user_to_system|system_to_user, title, formation explicit|inferred, subjects[],",
    "  evidence, confidence, rationale}. user_to_system = something the user asks/expects of the companion;",
    "  system_to_user = something the companion promised/owes or reasonably predicts it should follow up.",
    "gaps[]: {subject_key (generic path, e.g. routines/weekday_morning), why_useful}. A useful thing we do not know and",
    "  would learn naturally. Never a guessed value.",
])

SCHEMA_PROPERTIES = {
    "claims": {"type": "array", "maxItems": MAX_CLAIMS, "items": {
        "type": "object", "required": ["claim", "claim_kind", "formation", "confidence", "rationale"],
        "additionalProperties": True}},
    "directed": {"type": "array", "maxItems": MAX_DIRECTED, "items": {
        "type": "object", "required": ["direction", "title", "formation", "confidence", "rationale"],
        "additionalProperties": True}},
    "gaps": {"type": "array", "maxItems": MAX_GAPS, "items": {
        "type": "object", "required": ["subject_key", "why_useful"], "additionalProperties": True}},
}


def prompt_claims_block(claims: List[SnapshotClaim]) -> str:
    if not claims:
        return ""
    lines = ["", "CLAIMS AT START (current claims; reference ids only via supersedes_claim_id):"]
    for c in claims[:8]:
        lines.append(f"- [claim {c.id}] {c.claim_kind} ({c.formation}"
                     + (f", held by {c.holder}" if c.holder else "") + f"): {c.text[:160]}")
    return "\n".join(lines)


async def capture_claims(db: Any, *, workspace_id: str, session_id: str,
                         owner_peer_id: Optional[str]) -> List[SnapshotClaim]:
    """Current (non-superseded) claims in this world, newest first, bounded."""
    from sqlmodel import select
    from src.models.identity import ModelEntry
    from src.services.epistemics import formation_class
    try:
        stmt = select(ModelEntry).where(ModelEntry.honcho_workspace_id == workspace_id,
                                        ModelEntry.superseded_by_id.is_(None))
        if owner_peer_id:
            stmt = stmt.where(ModelEntry.owner_peer_id == owner_peer_id)
        else:
            stmt = stmt.where(ModelEntry.honcho_session_id == session_id)
        rows = (await db.execute(stmt.order_by(ModelEntry.created_at.desc()).limit(8))).scalars().all()
        return [SnapshotClaim(id=str(r.id), claim_kind=r.claim_kind or r.model_kind,
                              formation=formation_class(r.formation), text=r.claim,
                              holder=r.holder_actor or "") for r in rows]
    except Exception:
        return []


def _norm_subjects(raw: Any, cap: int = 4) -> List[str]:
    out: List[str] = []
    for s in (raw or []) if isinstance(raw, list) else []:
        if isinstance(s, str) and s.strip() and s.strip()[:40] not in out:
            out.append(s.strip()[:40])
        if len(out) >= cap:
            break
    return out


def validate_world_sections(
    raw: Any, *, quotable: Dict[str, str], by_msg: Dict[str, str], known_ids: set,
    known_claim_ids: set, ground_spans: Any, mids_fn: Any, conf_fn: Any, rationale_fn: Any,
) -> Tuple[Dict[str, List[Dict[str, Any]]], List[Dict[str, Any]]]:
    """Deterministic validation of claims/directed/gaps. Never raises.
    (Grounding helpers are injected from session_reconstruction so evidence
    rules stay defined in exactly one place.)"""
    out: Dict[str, List[Dict[str, Any]]] = {"claims": [], "directed": [], "gaps": []}
    rejected: List[Dict[str, Any]] = []
    if not isinstance(raw, dict):
        return out, rejected

    def evidence(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        ev_raw = entry.get("evidence") if isinstance(entry.get("evidence"), dict) else {}
        mids = mids_fn(ev_raw.get("message_ids"), quotable)
        spans = ground_spans(ev_raw.get("spans"), quotable)
        if mids is None or spans is None:
            return None
        return {"message_ids": mids, "spans": spans}

    claims = raw.get("claims")
    if claims is not None and not isinstance(claims, list):
        rejected.append({"where": "claims", "reason": "not_a_list"})
        claims = []
    for i, e in enumerate((claims or [])[:MAX_CLAIMS]):
        where = f"claims[{i}]"
        if not isinstance(e, dict):
            rejected.append({"where": where, "reason": "not_an_object"})
            continue
        text = str(e.get("claim") or "").strip()
        kind = str(e.get("claim_kind") or "").strip()
        formation = str(e.get("formation") or "").strip()
        if not text or kind not in CLAIM_KINDS_PROPOSABLE or formation not in FORMATION_CLASSES:
            rejected.append({"where": where, "reason": "bad_claim_shape"})
            continue
        ev = evidence(e)
        if ev is None:
            rejected.append({"where": where, "reason": "bad_evidence"})
            continue
        if is_firm(formation) and not ev["spans"]:
            # explicit/reported = the user actually said it: needs verbatim spans.
            rejected.append({"where": where, "reason": "firm_claim_needs_verbatim_spans"})
            continue
        if not ev["message_ids"]:
            rejected.append({"where": where, "reason": "claim_needs_provenance"})
            continue
        conf = conf_fn(e)
        if conf is None or conf < CLAIM_CONFIDENCE_FLOOR:
            rejected.append({"where": where, "reason": "confidence_below_floor"})
            continue
        sup = str(e.get("supersedes_claim_id") or "").strip()
        if sup and sup not in known_claim_ids:
            rejected.append({"where": where, "reason": "unknown_claim_id"})
            continue
        direction = str(e.get("direction") or "").strip()
        if direction and direction not in ("shared",) + DIRECTIONS:
            rejected.append({"where": where, "reason": "bad_direction"})
            continue
        if kind == "perspective":
            direction = "system_to_user"
            if is_firm(formation):
                formation = "inferred"  # the companion's own thought is never testimony
        related = [str(r) for r in (e.get("related_ids") or []) if str(r) in known_ids][:4]
        out["claims"].append({
            "claim": text[:600], "claim_kind": kind, "formation": formation,
            "subjects": _norm_subjects(e.get("subjects")), "related": related,
            "supersedes_claim_id": sup, "direction": direction or None,
            "evidence": ev, "confidence": conf, "rationale": rationale_fn(e)})

    directed = raw.get("directed")
    if directed is not None and not isinstance(directed, list):
        rejected.append({"where": "directed", "reason": "not_a_list"})
        directed = []
    for i, e in enumerate((directed or [])[:MAX_DIRECTED]):
        where = f"directed[{i}]"
        if not isinstance(e, dict):
            rejected.append({"where": where, "reason": "not_an_object"})
            continue
        direction = str(e.get("direction") or "").strip()
        title = str(e.get("title") or "").strip()
        formation = str(e.get("formation") or "").strip()
        if direction not in DIRECTIONS or not title or formation not in ("explicit", "inferred"):
            rejected.append({"where": where, "reason": "bad_directed_shape"})
            continue
        ev = evidence(e)
        if ev is None or not ev["message_ids"]:
            rejected.append({"where": where, "reason": "bad_evidence"})
            continue
        if formation == "explicit" and not ev["spans"]:
            rejected.append({"where": where, "reason": "explicit_needs_verbatim_spans"})
            continue
        conf = conf_fn(e)
        if conf is None:
            rejected.append({"where": where, "reason": "confidence_below_floor"})
            continue
        out["directed"].append({
            "direction": direction, "title": title[:280], "formation": formation,
            "subjects": _norm_subjects(e.get("subjects")), "evidence": ev,
            "confidence": conf, "rationale": rationale_fn(e)})

    gaps = raw.get("gaps")
    if gaps is not None and not isinstance(gaps, list):
        rejected.append({"where": "gaps", "reason": "not_a_list"})
        gaps = []
    for i, e in enumerate((gaps or [])[:MAX_GAPS]):
        where = f"gaps[{i}]"
        key = str((e or {}).get("subject_key") or "").strip().strip("/") if isinstance(e, dict) else ""
        why = str((e or {}).get("why_useful") or "").strip() if isinstance(e, dict) else ""
        if not KEY_RE.match(key) or not why:
            rejected.append({"where": where, "reason": "bad_gap"})
            continue
        out["gaps"].append({"subject_key": key, "why_useful": why[:240]})
    return out, rejected


def world_ops(validated: Dict[str, List[Dict[str, Any]]], make_op: Any) -> list:
    """validated world sections -> ValidatedOp list (make_op = ValidatedOp)."""
    ops = []
    for c in validated.get("claims", []):
        ops.append(make_op(op="claim", data={k: c[k] for k in (
            "claim", "claim_kind", "formation", "subjects", "related", "supersedes_claim_id",
            "direction", "evidence")}, confidence=c["confidence"], rationale=c["rationale"]))
    for d in validated.get("directed", []):
        ops.append(make_op(op="directed_expectation", data={k: d[k] for k in (
            "direction", "title", "formation", "subjects", "evidence")},
            confidence=d["confidence"], rationale=d["rationale"]))
    for g in validated.get("gaps", []):
        ops.append(make_op(op="knowledge_gap", data=dict(g), confidence=0.7,
                           rationale="model-noted useful unknown"))
    return ops


# ----------------------------------------------------------------------- apply
def _stable(*parts: str) -> str:
    return hashlib.sha1("|".join(parts).encode()).hexdigest()[:16]


async def apply_world_op(db: Any, op: Any, *, workspace_id: str, session_id: str,
                         message_id: str, user_peer_id: str, now: Any,
                         create_conf: float) -> Optional[Dict[str, Any]]:
    """Commit one validated world op through the canonical write paths.
    Returns an outcome dict (same shape as session_apply outcomes) or None
    when `op` is not a world op."""
    kind = getattr(op, "op", "")
    if kind not in WORLD_OPS:
        return None
    data = getattr(op, "data", {}) or {}
    conf = float(getattr(op, "confidence", 0) or 0)
    mids = [str(m) for m in ((data.get("evidence") or {}).get("message_ids") or [])]
    spans = [str(s.get("span") or "") for s in ((data.get("evidence") or {}).get("spans") or [])
             if isinstance(s, dict)]
    if kind == "knowledge_gap":
        from src.services import knowledge_coverage_service as kcs
        from src.services.world_scope import resolve_scope
        scope = await resolve_scope(db, workspace_id, user_peer_id, session_id)
        row = await kcs.register_gap(db, scope=scope, subject_key=data["subject_key"],
                                     why_useful=data.get("why_useful", ""),
                                     basis=f"registered by consolidation:{session_id}")
        return {"op": kind, "applied": True, "row_id": str(row.id), "row_kind": "knowledge_coverage",
                "data": data}
    if conf < create_conf:
        return {"op": kind, "reason": "below_create_threshold", "data": data}
    if kind == "claim":
        from uuid import UUID
        from src.services.epistemics import write_claim
        sup = None
        if data.get("supersedes_claim_id"):
            try:
                sup = UUID(str(data["supersedes_claim_id"]))
            except ValueError:
                sup = None
        claim_kind = data["claim_kind"]
        holder = "system" if claim_kind == "perspective" else None
        entry = await write_claim(
            db, workspace_id=workspace_id, session_id=session_id, message_id=message_id,
            owner_peer_id=user_peer_id,
            model_kind="relationship" if claim_kind in ("relationship_development", "repair") else "user",
            claim=data["claim"], evidence_verbatim=" … ".join(spans)[:2000] or data["claim"],
            formation=data["formation"], confidence=conf, claim_kind=claim_kind,
            holder_actor=holder, direction=data.get("direction"),
            evidence_refs=mids, supersedes_id=sup)
        return {"op": kind, "applied": True, "row_id": str(entry.id), "row_kind": "model_entry",
                "claim_kind": claim_kind, "related": data.get("related") or [],
                "subjects": data.get("subjects") or [], "data": data}
    # directed_expectation
    from src.models.expectation import ExpectationType
    from src.services.persistence import save_expectation_idempotent
    now_naive = now.astimezone(timezone.utc).replace(tzinfo=None) if getattr(now, "tzinfo", None) else now
    key = f"dir:{_stable(workspace_id, session_id, data['direction'], data['title'])}"
    record = {
        "honcho_workspace_id": workspace_id, "honcho_session_id": session_id,
        "honcho_message_id": message_id, "owner_peer_id": user_peer_id,
        "candidate_key": key, "extractor_version": "session-consolidation-v1",
        "subject_peer_id": user_peer_id, "expectation_type": ExpectationType.EXPECTED_OUTCOME,
        "title": data["title"][:200], "summary": (" … ".join(spans) or data["title"])[:1000],
        "anchor_timezone": "UTC", "extraction_confidence": conf,
        "formation": data["formation"], "effective_at": now_naive,
        "direction": data["direction"], "reminder_requested": False,
    }
    row, created = await save_expectation_idempotent(db, record, grounding_now=now_naive)
    return {"op": kind, "applied": True, "row_id": str(row.id), "row_kind": "expectation",
            "direction": data["direction"], "created": created,
            "subjects": data.get("subjects") or [], "data": data}
