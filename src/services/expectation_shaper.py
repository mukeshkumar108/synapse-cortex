import re
from typing import Any, Dict, Optional
from src.models.expectation import ExpectationType
from src.schemas.candidate import ExtractionCandidate


# Pseudo-temporal markers the model emits for "happening now / ongoing /
# background" content. These are not future-state grounding: a USER_INTENTION
# carrying only one of these has no temporal scope and must not be minted.
# (Deterministic check on the writer's own gate values, not on conversation
# language — relational semantics are never keyword-matched.)
_NON_FUTURE_TEMPORAL = frozenset({"present", "current", "ongoing", "recent", "past", "now"})


def _has_future_temporal(phrase: Optional[str]) -> bool:
    if not phrase:
        return False
    return phrase.strip().lower().strip("()") not in _NON_FUTURE_TEMPORAL


_TYPE_SUMMARY_PREFIX = {
    ExpectationType.USER_INTENTION: "User intends",
    ExpectationType.USER_COMMITMENT: "User committed",
    ExpectationType.EXTERNAL_DEPENDENCY: "Expected from another",
    ExpectationType.PLANNED_EVENT: "Planned event",
    ExpectationType.EXPECTED_OUTCOME: "Expected outcome",
    ExpectationType.FOLLOWUP_INVITATION: "Follow-up invited",
}


def _type_summary(expectation_type: ExpectationType, title: str) -> str:
    prefix = _TYPE_SUMMARY_PREFIX.get(expectation_type, "Tracked")
    return f"{prefix}: {title}"


class ExpectationShaper:
    """
    Shapes typed `ExtractionCandidate` contracts into structured Synapse expectation payloads.
    Prefers returning `None` (no expectation) over creating false positives.
    """

    def shape_expectation(
        self, candidate: ExtractionCandidate, subject_peer_id: str
    ) -> Optional[Dict[str, Any]]:
        # High-precision rejection rules (evaluated FIRST)
        if candidate.operational_kind == "semantic_only":
            return None
        if candidate.operational_kind == "event":
            # Events are records of what happened, not future-state beliefs.
            # They belong to evidence/fact lanes, never the expectation table.
            return None
        minimum_confidence = 0.65 if candidate.operational_kind == "durable_objective" else 0.8
        if candidate.confidence < minimum_confidence:
            return None
        if candidate.is_negated:
            return None
        if candidate.is_quoted:
            return None
        if candidate.is_sarcastic:
            return None
        if candidate.is_hypothetical:
            return None
        if not candidate.expectation_type_hint:
            return None

        obs_text = candidate.observation.strip()
        lower_obs = obs_text.lower()

        # Reject pure excitement or non-action statements
        if any(h in lower_obs for h in ["excited about", "love", "hate", "glad", "happy"]) and not candidate.temporal_phrase:
            if not any(k in lower_obs for k in ["going to", "will", "have to", "need to", "remind me"]):
                return None

        # Rejection rules for hypothetical or non-intended actions
        if any(h in lower_obs for h in ["if i had time", "maybe i'll", "wondering if", "not sure if"]):
            return None

        # Determine ExpectationType. An unmappable hint is rejected: the
        # writer must never default unknown content into USER_INTENTION.
        # (The model contract requires an explicit type per candidate; the
        # sink this replaces minted "planned actions" for arbitrary turns.)
        expectation_type: Optional[ExpectationType] = None

        if candidate.is_reported_speech:
            expectation_type = ExpectationType.EXTERNAL_DEPENDENCY
        elif candidate.expectation_type_hint:
            try:
                expectation_type = ExpectationType(candidate.expectation_type_hint)
            except ValueError:
                return None
        if expectation_type is None:
            return None

        if (
            expectation_type == ExpectationType.USER_INTENTION
            and not _has_future_temporal(candidate.temporal_phrase)
            and candidate.operational_kind != "durable_objective"
        ):
            return None

        # Extract title
        title = self._clean_title(obs_text)
        if not title or len(title) < 3:
            return None

        summary = _type_summary(expectation_type, title)
        if candidate.temporal_phrase:
            summary += f" ({candidate.temporal_phrase})"

        return {
            "candidate_key": candidate.candidate_key,
            "source_start": candidate.source_start,
            "source_end": candidate.source_end,
            "expectation_type": expectation_type,
            "title": title,
            "summary": summary,
            "raw_temporal_phrase": candidate.temporal_phrase,
            "subject_peer_id": candidate.actor_peer_id or subject_peer_id,
            "confidence": candidate.confidence,
            # Formation is the model's own explicit/inferred marking,
            # defaulting to explicit for verbatim user-turn evidence.
            # Background/dreaming authors later write formation="inferred"
            # with holder=companion; the column accepts both from the start
            # so no schema rework is needed when that cognition arrives.
            "formation": candidate.formation or "explicit",
        }

    def _clean_title(self, raw_text: str) -> str:
        text = raw_text.strip().rstrip(".!?")
        
        # Remove common prefixes
        prefixes = [
            r"^i'm going to\s+",
            r"^i am going to\s+",
            r"^i'll\s+",
            r"^i will\s+",
            r"^gonna\s+",
            r"^i have to\s+",
            r"^i need to\s+",
            r"^remind me to\s+",
            r"^ask me to\s+",
            r"^ask me\s+",
            r"^\w+\s+said\s+(he|she|they)('ll|'d)?\s+",
        ]
        
        cleaned = text
        for p in prefixes:
            cleaned = re.sub(p, "", cleaned, flags=re.IGNORECASE)

        # Remove trailing temporal phrases if embedded
        cleaned = re.sub(
            r"\s+(tonight|today|tomorrow(\s+\w+)?|by\s+5pm\s+\w+|friday|next\s+\w+|after\s+the\s+[^.,!\?]+)$",
            "",
            cleaned,
            flags=re.IGNORECASE,
        ).strip().rstrip(".!?")

        # Capitalize first letter
        if cleaned:
            cleaned = cleaned[0].upper() + cleaned[1:]

        return cleaned
