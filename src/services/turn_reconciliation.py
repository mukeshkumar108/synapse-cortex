"""Deterministic reconciliation between the real-time fast path and the
background watcher.

Two speeds, one lifecycle:
- Fast path (app interpreter) commits canonical actions synchronously and
  reports them as `materialized_actions` on the turn payload.
- The watcher still sees every turn; a deterministic reconciliation step
  suppresses only the conversation-derived candidates that would duplicate an
  already-materialized canonical action from the same turn (same lane family
  AND same evidence — verbatim containment or heavy token overlap).

Cross-message paraphrase dedup is deliberately NOT handled here: that is the
watcher's semantic reconciliation job. Same-turn precision only.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

from src.schemas.candidate import ExtractionCandidate
from src.schemas.expectation import MaterializedAction

logger = logging.getLogger(__name__)

# Which conversation-derived candidate lanes a canonical action absorbs.
LANE_SUPPRESSION: Dict[str, set[str]] = {
    "created": {"expectation", "open_loop"},
    "completed": {"completion", "expectation"},
    "cancelled": {"cancellation"},
    "updated": {"expectation"},
}

_STOPWORDS = {
    "about", "after", "again", "also", "been", "could", "from", "have",
    "into", "just", "that", "their", "them", "then", "there", "they",
    "this", "what", "when", "where", "which", "with", "would", "your",
    "remind", "please",
}

_WORD_RE = re.compile(r"[a-z0-9]+")


def _tokens(value: Optional[str]) -> set[str]:
    if not value:
        return set()
    words = _WORD_RE.findall(value.lower())
    return {w for w in words if len(w) >= 3 and w not in _STOPWORDS}


def _evidence_related(candidate: ExtractionCandidate, action: MaterializedAction) -> bool:
    """Deterministic same-action evidence test: verbatim containment (either
    direction) or heavy token overlap between the candidate's evidence and the
    materialized action's evidence text."""
    evidence = (action.evidence_span or "").strip()
    if not evidence:
        return False
    evidence_lower = evidence.lower()
    candidate_texts = [
        candidate.raw_evidence,
        candidate.observation,
        candidate.canonical_title,
    ]
    for text in candidate_texts:
        if not text:
            continue
        text_lower = text.lower().strip()
        if not text_lower:
            continue
        if text_lower in evidence_lower or evidence_lower in text_lower:
            return True
        cand_tokens = _tokens(text)
        evi_tokens = _tokens(evidence)
        if not cand_tokens or not evi_tokens:
            continue
        shared = cand_tokens & evi_tokens
        # Heavy overlap only: near-zero tolerance for wrong suppression means
        # a loose majority is not enough.
        if (
            len(shared) >= 2
            and min(len(cand_tokens), len(evi_tokens)) >= 3
            and len(shared) / min(len(cand_tokens), len(evi_tokens)) >= 0.75
        ):
            return True
    return False


def _effective_lane(candidate: ExtractionCandidate) -> Optional[str]:
    """Lane resolution works for both extraction backends: the model path sets
    operational_kind at shape time; the rules path leaves it None with an
    expectation_type_hint instead."""
    if candidate.operational_kind:
        return candidate.operational_kind
    hint = candidate.expectation_type_hint
    if hint in ("user_commitment", "user_intention", "planned_event", "expected_outcome"):
        return "expectation"
    if hint == "followup_invitation":
        return "open_loop"
    return None


def suppress_materialized_duplicates(
    candidates: Iterable[ExtractionCandidate],
    materialized_actions: List[MaterializedAction],
) -> Tuple[List[ExtractionCandidate], List[Dict[str, Any]]]:
    """Returns (kept_candidates, suppression_records) deterministically."""
    if not materialized_actions:
        return list(candidates), []
    kept: List[ExtractionCandidate] = []
    suppressed: List[Dict[str, Any]] = []
    for candidate in candidates:
        lane = _effective_lane(candidate)
        matched = None
        if lane:
            for action in materialized_actions:
                if lane in LANE_SUPPRESSION.get(action.action, set()) and _evidence_related(
                    candidate, action
                ):
                    matched = action
                    break
        if matched is not None:
            suppressed.append({
                "candidate_key": candidate.candidate_key,
                "reason": "duplicate_of_canonical",
                "matched_action": matched.action,
                "matched_object_id": matched.object_id,
            })
            continue
        kept.append(candidate)
    if suppressed:
        logger.info(
            "Reconciliation suppressed %d conversation-derived candidate(s) duplicating canonical actions",
            len(suppressed),
        )
    return kept, suppressed
