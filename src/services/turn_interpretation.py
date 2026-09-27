"""Bounded semantic turn interpretation: what does this utterance DO?

Live-boundary entry point for turns the extractor left at zero durable
yield. A pure reference ("How's he doing?") contains no NEW state, so a
new-state extractor correctly emits nothing — but the turn still needs
interpretation against EXISTING state. That second job belongs here, not
in the extractor and not in downstream shape-gates.

Division of labour (deliberate, not incidental):
- CODE owns: budgets, candidate retrieval, validation, ambiguity policy,
  mutation, provenance, kill-switch. It never decides meaning.
- MODEL owns: is this a reference to a live matter / genuinely new
  trackable content / incidental noise / unresolvable uncertainty — and,
  for references, WHICH matter. One call, strict schema, fail-closed.

Healthy pattern preserved: retrieve candidates -> semantic judgement ->
deterministic validation/invariants -> mutation. The model never writes.

Runs on the ingest (shadow/write, 202-accepted) path — effectively
nearline already: nothing here blocks foreground generation. The hot
reads (attention/handshake/handover) are untouched.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from uuid import UUID

from sqlmodel import select

from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import ExtractionTrace

logger = logging.getLogger(__name__)

# Kill-switch: TURN_INTERPRETATION_ENABLED=0 restores pre-tranche behaviour
# (zero-yield turns hold silently, exactly as today).
ENABLED_ENV = "TURN_INTERPRETATION_ENABLED"

# Extractor-version tag for interpreter-originated NEW candidates. Downstream
# shape-gates must NOT re-litigate the reference-vs-new decision the
# interpreter already made with the same live set in view — they keep their
# prevention-direction guards (entity reuse, settled history) but skip the
# entity-less hold, which would otherwise second-guess NEW back into a hold.
INTERPRETER_VERSION = "turn-interpretation-v1"

# Budgets — all hard caps, none of them semantic:
# - MIN_TEXT_CHARS: cost floor. Turns shorter than this carry no groundable
#   referential content worth a model call (span grounding needs SOMETHING
#   to quote). "ok"/"lol" skip; "Still nothing?" (15) runs.
# - MAX_LIVE_MATTERS: bounded retrieval into the prompt, recent-first.
# - Prompt/output char caps bound tokens regardless of matter verbosity.
MIN_TEXT_CHARS = 8
MAX_LIVE_MATTERS = 4
MATTER_TITLE_CAP = 120
UTTERANCE_CAP = 500
PROMPT_CHAR_CAP = 2000
MIN_CONFIDENCE = 0.6

DECISIONS = ("reference", "new", "incidental", "uncertain")


@dataclass(frozen=True)
class LiveMatter:
    """One retrievable candidate. Retrieval only — never authority."""

    id: str
    title: str


@dataclass(frozen=True)
class TurnInterpretation:
    decision: str
    primary_id: Optional[str]  # live-matter id for "reference", else None
    also_ids: List[str]  # other plausible ids (ambiguity signal)
    confidence: float
    evidence_span: str
    rationale: str = ""


def interpretation_enabled() -> bool:
    return os.getenv(ENABLED_ENV, "1") == "1"


def build_prompt(text: str, matters: List[LiveMatter]) -> str:
    """Enumerate the bounded live set for the judgement. Retrieval text
    only; the decision is the model's."""
    lines = [
        "TURN INTERPRETER: decide what the user's utterance DOES about the open matters.",
        "",
        "Currently OPEN matters (if any):",
    ]
    if matters:
        for i, matter in enumerate(matters[:MAX_LIVE_MATTERS]):
            lines.append(f"[{i}] {(matter.title or 'untitled')[:MATTER_TITLE_CAP]}")
    else:
        lines.append("(none)")
    lines.extend([
        "",
        f"UTTERANCE:\n{(text or '').strip()[:UTTERANCE_CAP]}",
        "",
        "Decide exactly one:",
        '- "reference": it asks about / refers to exactly one listed matter and carries no new trackable state.',
        '- "new": it introduces genuinely new trackable content (a situation, worry, plan, event worth remembering) not covered above.',
        '- "incidental": chit-chat, acknowledgement, politeness, or vague noise with nothing worth remembering longitudinally.',
        '- "uncertain": it clearly reaches back to prior context but you cannot tell which matter (or whether it is new at all).',
        "",
        "Rules: quote a VERBATIM substring of UTTERANCE as evidence_span (empty string only for incidental). "
        "primary_index is the [n] of the referred matter for reference, else null. "
        "also_plausible lists other [n] that could fit (empty when sure). "
        "Conservative: prefer uncertain over guessing, incidental over inventing trackable content.",
    ])
    return "\n".join(lines)[:PROMPT_CHAR_CAP]


def _validate(raw: Any, text: str, matters: List[LiveMatter]) -> Optional[TurnInterpretation]:
    """Deterministic validation of the model proposal. Anything malformed,
    ungrounded, or out-of-range fails closed to None — never mutated,
    never clarified over."""
    if not isinstance(raw, dict):
        return None
    decision = str(raw.get("decision") or "").strip().lower()
    if decision not in DECISIONS:
        return None
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return None
    if not (MIN_CONFIDENCE <= confidence <= 1.0):
        return None
    span = str(raw.get("evidence_span") or "")
    if decision in ("reference", "new"):
        if not span.strip() or span.strip() not in (text or ""):
            return None
    elif span.strip() and span.strip() not in (text or ""):
        return None
    bounded = matters[:MAX_LIVE_MATTERS]

    def _idx(value: Any) -> Optional[int]:
        try:
            idx = int(value)
        except (TypeError, ValueError):
            return None
        return idx if 0 <= idx < len(bounded) else None

    primary_id: Optional[str] = None
    raw_primary = raw.get("primary_index")
    if decision == "reference":
        if raw_primary is None:
            return None
        idx = _idx(raw_primary)
        if idx is None:
            return None
        primary_id = bounded[idx].id
    also_ids: List[str] = []
    raw_also = raw.get("also_plausible") or []
    if isinstance(raw_also, list):
        for item in raw_also[:MAX_LIVE_MATTERS]:
            idx = _idx(item)
            if idx is not None:
                mid = bounded[idx].id
                if mid != primary_id and mid not in also_ids:
                    also_ids.append(mid)
    return TurnInterpretation(
        decision=decision, primary_id=primary_id, also_ids=also_ids,
        confidence=confidence, evidence_span=span.strip(),
        rationale=str(raw.get("rationale") or "")[:280],
    )


async def interpret_turn(
    text: str,
    matters: List[LiveMatter],
    *,
    adapter: Any = ...,
) -> Optional[TurnInterpretation]:
    """One bounded semantic judgement over the raw utterance + live set.
    Returns a validated interpretation, or None (fail-closed: the turn
    holds exactly as it would have without this path)."""
    from src.services import semantic_judge

    clean = (text or "").strip()
    if len(clean) < MIN_TEXT_CHARS:
        return None
    if adapter is ...:
        adapter = semantic_judge._adapter()
    if adapter is None:
        return None
    prompt = build_prompt(clean, matters)
    try:
        raw = await adapter.generate_structured(
            system=(
                "You are a precise turn interpreter for a companion-memory system. "
                "Conservative: prefer 'uncertain' over guessing. Never invent facts."
            ),
            prompt=prompt,
            json_schema={
                "type": "object",
                "properties": {
                    "decision": {"type": "string"},
                    "primary_index": {"type": ["integer", "null"]},
                    "also_plausible": {"type": "array", "items": {"type": "integer"}},
                    "confidence": {"type": "number"},
                    "evidence_span": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["decision", "confidence", "evidence_span", "rationale"],
                "additionalProperties": False,
            },
            model_id=semantic_judge.judge_model_id(),
            max_tokens=200,
            temperature=0.0,
            strict=True,
        )
    except Exception as exc:
        logger.warning("turn interpretation call failed (fail-closed): %s", exc)
        return None
    return _validate(raw, clean, matters)


async def fetch_live_matters(db: Any, *, workspace_id: str, session_id: str) -> List[LiveMatter]:
    """Bounded retrieval of the live set. Non-mutating; fail-open []."""
    try:
        rows = (await db.execute(select(OpenLoop).where(
            OpenLoop.honcho_workspace_id == workspace_id,
            OpenLoop.honcho_session_id == session_id,
            OpenLoop.status == OpenLoopStatus.OPEN,
        ).order_by(OpenLoop.updated_at.desc()).limit(MAX_LIVE_MATTERS))).scalars().all()
    except Exception as err:
        logger.warning("live-matter retrieval failed (fail-open): %s", err)
        return []
    matters = []
    for row in rows:
        title = f"{row.title or ''} {row.summary or ''}".strip() or "open loop"
        matters.append(LiveMatter(id=str(row.id), title=title))
    return matters


async def already_interpreted(db: Any, *, workspace_id: str, message_id: str) -> bool:
    """Replay guard: one interpretation per message, replays never re-judge."""
    try:
        row = (await db.execute(select(ExtractionTrace).where(
            ExtractionTrace.honcho_workspace_id == workspace_id,
            ExtractionTrace.honcho_message_id == message_id,
            ExtractionTrace.stage == "turn_interpretation",
        ).limit(1))).scalar_one_or_none()
    except Exception:
        return False
    return row is not None


async def apply_interpretation(
    db: Any,
    *,
    workspace_id: str,
    session_id: str,
    message_id: str,
    peer_id: str,
    text: str,
    now: Any,
    interp: TurnInterpretation,
    matters: List[LiveMatter],
) -> Dict[str, Any]:
    """Deterministic routing of a validated interpretation through the
    EXISTING machinery (reuse / hold / create). Ambiguity policy lives
    here, in code: reference-with-competition and uncertain never reuse —
    they hold visibly. Never clarifies. Returns a small outcome summary."""
    from src.services.lifecycle_service import (
        LifecycleService,
        record_ambiguity_attention,
    )

    outcome: Dict[str, Any] = {"decision": interp.decision, "mutated": False}
    by_id = {m.id: m for m in matters}

    async def _trace(status: str, detail: Dict[str, Any]) -> None:
        try:
            from src.services import semantic_judge
            db.add(ExtractionTrace(
                honcho_workspace_id=workspace_id,
                honcho_session_id=session_id,
                honcho_message_id=message_id,
                stage="turn_interpretation",
                item_key=f"turn_interp:{message_id}",
                status=status,
                model=semantic_judge.judge_model_id(),
                detail_json=__import__("json").dumps(detail, default=str)[:2000],
            ))
            await db.commit()
        except Exception as err:
            logger.warning("turn interpretation trace failed: %s", err)
            try:
                await db.rollback()
            except Exception:
                pass

    if interp.decision == "reference" and interp.primary_id in by_id:
        if interp.also_ids:
            # Named competition: single-winner-or-hold is policy, in code.
            names = [by_id[interp.primary_id].title] + [
                by_id[mid].title for mid in interp.also_ids if mid in by_id]
            content = (
                f"Unresolved reference {text[:160]!r} could mean "
                f"{len(names)} live matters: "
                + "; ".join(f"({i + 1}) {t[:120]}" for i, t in enumerate(names))
                + ". Held without guessing, not asked now."
            )
            try:
                await record_ambiguity_attention(
                    db, workspace_id=workspace_id, session_id=session_id,
                    message_id=message_id,
                    candidate_key=f"interp_hold:{message_id}",
                    content=content, owner_peer_id=None,
                    confidence=interp.confidence)
            except Exception as err:
                logger.warning("interpreted hold attention failed: %s", err)
            await _trace("held_ambiguous", {"alternatives": names})
            outcome["held"] = True
            return outcome
        service = LifecycleService()
        target = None
        if interp.primary_id in by_id:
            try:
                target = (await db.execute(select(OpenLoop).where(
                    OpenLoop.id == UUID(interp.primary_id)))).scalar_one_or_none()
            except Exception:
                target = None
        if target is not None and target.status == OpenLoopStatus.OPEN:
            try:
                await service._touch_reused_loop(
                    db, loop=target, entities=[],
                    matter_text=text, message_id=message_id,
                    expectation_id=None, now=now)
                await _trace("accepted_reference", {
                    "target_id": interp.primary_id,
                    "confidence": interp.confidence,
                    "evidence_span": interp.evidence_span})
                outcome.update({"mutated": True, "reused_id": interp.primary_id})
                return outcome
            except Exception as err:
                logger.warning("interpreted reuse failed (fail-open): %s", err)
        await _trace("rejected_reference", {"target_id": interp.primary_id})
        return outcome

    if interp.decision == "uncertain":
        names = [m.title for m in matters[:MAX_LIVE_MATTERS]]
        content = (
            f"Unresolved reference {text[:160]!r}"
            + (f" could mean {len(names)} live matters: "
               + "; ".join(f"({i + 1}) {t[:120]}" for i, t in enumerate(names))
               if names else ". No live matter to attach")
            + ". Held without guessing, not asked now."
        )
        try:
            await record_ambiguity_attention(
                db, workspace_id=workspace_id, session_id=session_id,
                message_id=message_id,
                candidate_key=f"interp_hold:{message_id}",
                content=content, owner_peer_id=None,
                confidence=interp.confidence)
        except Exception as err:
            logger.warning("interpreted hold attention failed: %s", err)
        await _trace("held_uncertain", {"alternatives": names})
        outcome["held"] = True
        return outcome

    if interp.decision == "new":
        from src.schemas.candidate import ExtractionCandidate
        service = LifecycleService()
        candidate = ExtractionCandidate(
            candidate_key=f"interp_new:{message_id}",
            observation=text, raw_evidence=text,
            canonical_title=text[:120], open_loop_hint=text[:120],
            operational_kind="open_loop", subject_refs=[],
            confidence=max(0.0, min(1.0, interp.confidence)),
            formation="inferred",
            extractor_version=INTERPRETER_VERSION,
        )
        try:
            row = await service.create_open_loop_if_needed(
                db, workspace_id=workspace_id, session_id=session_id,
                message_id=message_id, owner_peer_id=peer_id,
                candidate=candidate, expectation_id=None, now=now,
                frame=None,
            )
        except Exception as err:
            logger.warning("interpreted new-matter create failed: %s", err)
            row = None
        await _trace("created_new" if row is not None else "dropped_new",
                     {"confidence": interp.confidence})
        outcome["mutated"] = row is not None
        return outcome

    # "incidental": the model judges nothing worth keeping. Drop silently
    # (TurnStamp + CurrentMeaning already preserved the raw evidence).
    await _trace("incidental_drop", {})
    return outcome
