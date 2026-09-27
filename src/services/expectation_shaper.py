import re
from typing import Any, Dict, Optional
from src.models.expectation import ExpectationType
from src.schemas.candidate import ExtractionCandidate
from src.services.ownership import is_external_counterparty

# Types that assert the user (or companion) as the acting party. Ownership
# authority forecloses these when the resolved owner is a non-user external
# sender — the same commitment-sink boundary (CommitmentCandidateService)
# applied to the expectation layer, so an external counterparty's own
# first-person promise ("I'll send it tomorrow") cannot be minted as
# ExpectationType.USER_INTENTION just because the extractor's free-text
# hint said so.
_ACTOR_ASSERTING_TYPES = frozenset({
    ExpectationType.USER_INTENTION, ExpectationType.USER_COMMITMENT,
})


# Pseudo-temporal markers the model emits for "happening now / ongoing /
# background" content. These are not future-state grounding: a USER_INTENTION
# carrying only one of these has no temporal scope and must not be minted.
# (Deterministic check on the writer's own gate values, not on conversation
# language — relational semantics are never keyword-matched.)
_NON_FUTURE_TEMPORAL = frozenset({
    "present", "current", "ongoing", "recent", "past", "now",
    "recurring", "for weeks", "always",
})


def _has_future_temporal(phrase: Optional[str]) -> bool:
    if not phrase:
        return False
    return phrase.strip().lower().strip("()") not in _NON_FUTURE_TEMPORAL


# Self-referential actor-assertion prefixes: the extractor's own free-text
# `observation` sometimes narrates the acting party as "I"/"the user" even
# when the true actor (per authoritative ownership) is someone else — the
# extraction model describes external first-person speech ("I'll send it
# tomorrow") in its own third-person narration ("The user will send it"),
# which is simply wrong when the row's owner is external. This is the same
# family of modal-verb self-reference already stripped for first person
# below; the third-person "(the) user ..." forms are the model's own
# mis-narration of that identical construct, not a new linguistic category.
_ACTOR_ASSERTION_RE = re.compile(
    r"^(?:i'm going to|i am going to|i'll|i will|gonna|i have to|i need to|"
    r"(?:the\s+)?user\s+(?:will|is going to|has to|needs? to|wants? to))\s+",
    re.IGNORECASE,
)


def _strip_leading_actor_assertion(text: str) -> tuple[str, bool]:
    stripped = _ACTOR_ASSERTION_RE.sub("", text, count=1)
    return stripped, stripped != text


def _owner_display_name(owner_peer_id: str) -> str:
    """Deterministic, structural label from a trusted peer-id — never a
    per-name special case. Operates only on the ingest-adapter-owned
    ``external:<slug>`` identifier shape (the same provenance boundary
    ``is_external_counterparty`` already trusts), not on conversation
    content: "external:studio_sam" -> "Studio Sam"."""
    raw = owner_peer_id.split(":", 1)[-1] if ":" in owner_peer_id else owner_peer_id
    words = [w for w in re.split(r"[_\s]+", raw.strip()) if w]
    return " ".join(w.capitalize() for w in words) if words else owner_peer_id


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
        self, candidate: ExtractionCandidate, subject_peer_id: str,
        *, owner_peer_id: Optional[str] = None,
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

        # Ownership authority overrides the extractor's self-reported
        # category: resolved owner provenance (ingest-adapter-supplied,
        # never keyword-matched) is trusted over free-text classification.
        # A row owned by a non-user external sender cannot assert the user
        # or companion as the acting party, regardless of how the extractor
        # phrased or hinted it. Reported third-party speech within the
        # user's own turn is already routed to EXTERNAL_DEPENDENCY above;
        # this covers the direct-first-person case (the external sender's
        # own message/email/etc.), which is not "reported speech".
        resolved_owner = owner_peer_id or candidate.actor_peer_id or subject_peer_id
        owner_overridden_external = bool(
            expectation_type in _ACTOR_ASSERTING_TYPES
            and resolved_owner
            and is_external_counterparty(resolved_owner)
        )
        if owner_overridden_external:
            expectation_type = ExpectationType.EXTERNAL_DEPENDENCY

        if (
            expectation_type
            in (
                ExpectationType.USER_INTENTION,
                ExpectationType.PLANNED_EVENT,
                ExpectationType.EXPECTED_OUTCOME,
                ExpectationType.FOLLOWUP_INVITATION,
            )
            and not _has_future_temporal(candidate.temporal_phrase)
            and candidate.operational_kind != "durable_objective"
        ):
            # Future-scoped types without a future scope are not expectations:
            # replay showed health states minted as PLANNED_EVENT ("neck ache
            # (recurring)"). Commitments and dependencies may be open-ended;
            # dated intentions, events, outcomes and follow-ups may not.
            return None

        # Extract title
        title = self._clean_title(obs_text)
        if not title or len(title) < 3:
            return None

        if owner_overridden_external:
            # The extractor's free-text observation was actor-asserting the
            # wrong party (ownership authority already overrode the type
            # above); if we can deterministically isolate the bare action
            # clause (a self-referential modal-verb prefix was stripped —
            # never a guess), rebuild the title around the authoritative
            # owner instead of leaving "the user"/"I" in derived Cortex
            # state. Raw evidence (the honcho message this candidate is
            # linked to) is untouched by this — only the derived title
            # changes. If no such prefix was present, the observation's
            # actor framing is unknown shape: leave the title as extracted
            # rather than fabricate a reconstruction we can't ground.
            action, had_actor_prefix = _strip_leading_actor_assertion(obs_text.rstrip(".!?"))
            if had_actor_prefix:
                action_title = self._clean_title(action)
                if action_title:
                    owner_display = _owner_display_name(resolved_owner)
                    title = f"{owner_display} will {action_title[0].lower()}{action_title[1:]}"

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
