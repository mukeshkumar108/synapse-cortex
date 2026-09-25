"""Bounded semantic judge: model understands, deterministic code governs.

One semantic question per call, over caller-supplied texts. The model verdict
never writes anything: callers validate (verdict=yes + confidence floor +
verbatim evidence span in the cited text) and then route through the existing
deterministic promotion/lifecycle machinery. No credentials or model failure
ever blocks the deterministic path (fail-closed None).

No keyword/regex ontology lives here: prompts carry raw evidence strings and
the model judges meaning. Deterministic code is used only for genuinely
deterministic facts: bounds, identity of the cited text, verbatim grounding.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Closed question set. Anything else is rejected, never improvised.
QUESTION_KINDS = (
    "resolves",          # does later evidence settle the earlier matter?
    "fulfils",           # does later evidence show the undertaking fully done?
    "partially_fulfils", # does evidence partly (not fully) satisfy it?
    "factual_claim",     # does this state a biographical/historical fact?
    "same_person",       # do these references denote the same person?
    "accepts",           # does this response accept the earlier proposal?
    "eased",             # has the relational meaning eased vs the earlier state?
    "supersedes",        # does the newer plan replace the older one?
    "undertaking",       # is this a genuine future undertaking vs passing thought?
    "revisit_worthy",    # is this topic naturally worth revisiting later?
)

MIN_CONFIDENCE = 0.6


_QUESTIONS = {
    "resolves": "Does the LATER text settle/answer/complete the EARLIER matter (even in different words)?",
    "fulfils": "Does the LATER text show the earlier undertaking FULLY done/completed (not partial, not planned, not merely related)?",
    "partially_fulfils": "Does the LATER text show PART of the earlier undertaking done, with a remainder still outstanding (amounts, quantities, or explicit 'not all / rest later' language)? Full completion is NOT partial.",
    "factual_claim": "Does the quoted statement assert a biographical or historical FACT about someone or something — past events, background, possessions, losses, biography — as opposed to an intention, plan, feeling, or hypothetical?",
    "same_person": "Do the two references denote the SAME person? Same name alone is not enough; need compatible role/context and no disqualifier (e.g. studio vs cousin).",
    "accepts": "Does the LATER text accept/agree to the EARLIER proposal (vs deflecting, deferring, or merely acknowledging it)?",
    "eased": "Compared with the EARLIER relational state, does the LATER text show easing/repair (vs ongoing tension or worsening)?",
    "supersedes": "Does the NEWER plan/promise replace (not merely restate) the OLDER one?",
    "undertaking": "Is the quoted statement a genuine future undertaking/commitment (vs a passing thought, wish, joke, hypothetical, or sarcasm)?",
    "revisit_worthy": "Is this retained topic naturally worth revisiting later (unfinished business, open feeling, pending outcome) vs settled small-talk?",
}


def _adapter():
    from src.runtime_model import get_agenda_adapter
    return get_agenda_adapter()


def judge_model_id() -> str:
    return os.getenv("SYNAPSE_SEMANTIC_JUDGE_MODEL", "google/gemini-2.5-flash-lite")


@dataclass(frozen=True)
class Adjudication:
    kind: str
    verdict: str  # yes | no | unclear | unavailable
    confidence: float
    evidence_span: str
    rationale: str
    note: str  # machine reason: unavailable | rejected_kind | empty_input | ...

    @property
    def accepted(self) -> bool:
        return self.verdict == "yes" and self.confidence >= MIN_CONFIDENCE


async def adjudicate(
    *,
    kind: str,
    earlier: str,
    later: str,
    context: str = "",
    adapter: Any = None,
) -> Adjudication:
    """Always inspectable: returns the verdict (or the reason there is none).
    Only accepted verdicts may proceed to promotion; see judge()."""
    if kind not in _QUESTIONS:
        logger.warning("semantic judge refused unknown kind=%r", kind)
        return Adjudication(kind, "unavailable", 0.0, "", "", "rejected_kind")
    earlier = (earlier or "").strip()[:1500]
    later = (later or "").strip()[:1500]
    if not earlier or not later:
        return Adjudication(kind, "unavailable", 0.0, "", "", "empty_input")
    adapter = adapter if adapter is not None else _adapter()
    if adapter is None:
        return Adjudication(kind, "unavailable", 0.0, "", "", "no_adapter")
    question = _QUESTIONS[kind]
    context_block = f"\nCONTEXT:\n{context[:1000]}" if (context or "").strip() else ""
    prompt = (
        f"{question}\n\nEARLIER:\n{earlier}\n\nLATER:\n{later}"
        f"{context_block}\n\n"
        "Rules: answer ONLY from these texts. Quote a VERBATIM substring of "
        "LATER as evidence_span (empty string if the answer is no)."
    )
    try:
        raw = await adapter.generate_structured(
            system=(
                "You are a precise semantic judge for a companion-memory system. "
                "Conservative: prefer 'unclear' over guessing. Never invent facts."
            ),
            prompt=prompt,
            json_schema={
                "type": "object",
                "properties": {
                    "verdict": {"type": "string"},
                    "confidence": {"type": "number"},
                    "evidence_span": {"type": "string"},
                    "rationale": {"type": "string"},
                },
                "required": ["verdict", "confidence", "evidence_span", "rationale"],
                "additionalProperties": False,
            },
            model_id=judge_model_id(),
            max_tokens=300,
            temperature=0.0,
            strict=True,
        )
    except Exception as exc:
        logger.warning("semantic judge call failed (fail-closed): %s", exc)
        return Adjudication(kind, "unavailable", 0.0, "", "", "call_failed")
    if not isinstance(raw, dict):
        return Adjudication(kind, "unavailable", 0.0, "", "", "malformed")
    verdict = str(raw.get("verdict") or "").strip().lower()
    if verdict not in ("yes", "no", "unclear"):
        return Adjudication(kind, "unavailable", 0.0, "", "", "bad_verdict")
    try:
        confidence = float(raw.get("confidence") or 0.0)
    except (TypeError, ValueError):
        return Adjudication(kind, "unavailable", 0.0, "", "", "bad_confidence")
    return Adjudication(
        kind=kind, verdict=verdict, confidence=confidence,
        evidence_span=str(raw.get("evidence_span") or ""),
        rationale=str(raw.get("rationale") or "")[:280], note="answered")


async def judge(
    *,
    kind: str,
    earlier: str,
    later: str,
    context: str = "",
    adapter: Any = None,
) -> Optional[Adjudication]:
    """Ask one bounded semantic question. Returns the adjudication only when
    accepted AND verbatim-grounded; otherwise None (fail-closed)."""
    result = await adjudicate(kind=kind, earlier=earlier, later=later,
                              context=context, adapter=adapter)
    if not result.accepted:
        return None
    # Deterministic grounding: the cited span must occur verbatim in LATER.
    # A yes-verdict without grounding is discarded, not promoted.
    if result.evidence_span.strip() and result.evidence_span.strip() in later:
        return result
    logger.warning("semantic judge %s discarded: span not verbatim", kind)
    return None


def describe_batch(questions: List[Dict[str, str]]) -> str:
    kinds = sorted({q.get("kind", "?") for q in questions})
    return f"{len(questions)} question(s): {','.join(kinds)}"
