import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import httpx
from src.schemas.candidate import ExtractionCandidate, ExtractionResult, LooseObservation

logger = logging.getLogger(__name__)


class BaseExtractorProvider:
    """Interface for turn extraction providers (LLM or Rule-based)."""
    def extract(self, text: str, peer_id: Optional[str] = None) -> List[ExtractionCandidate]:
        raise NotImplementedError


class RuleBasedExtractorProvider(BaseExtractorProvider):
    """
    High-precision deterministic rule-based extractor.
    Produces typed ExtractionCandidate instances with source spans, candidate keys, and V4 layer hints.
    """

    INTENT_PATTERNS = [
        (r"\b(i'm not going to|i am not going to|i won't|i'm not planning to|not going to)\s+([^.,!?;\n]+)", "user_intention", True, False, False),
        (r"\b(i'm going to|i am going to|i'll|i will|gonna|planning to|plan to)\s+([^.,!?;\n]+)", "user_intention", False, False, False),
        (r"\b(i have to|i need to|i must)\s+([^.,!?;\n]+)", "user_commitment", False, False, False),
        (r"\b(i have a|i've got a|appointment|meeting|flight|dentist)\s+([^.,!?;\n]+)", "planned_event", False, False, False),
        (r"\b(remind me to|ask me|follow up on)\s+([^.,!\?;\n]+)", "followup_invitation", False, False, False),
        (r"\b(waiting for|depends on|said (he|she|they)'ll|said (he|she|they) would|said)\s+([^.,!\?;\n]+)", "external_dependency", False, False, True),
        (r"\b(call|contact|email|message|reach out to|send)\s+([^.,!\?;\n]+)", "user_intention", False, False, False),
        (r"\b(might|could|maybe)\s+([^.,!\?;\n]+)", "user_intention", False, True, False),
        (r"\b(?:the\s+[\w\s-]+|it)\s+(?:should|is expected to|will)\s+(?:finish|complete|arrive|happen)\b([^.,!\?;\n]*)", "expected_outcome", False, False, False),
    ]

    TEMPORAL_PATTERNS = [
        r"\b(by\s+\d{1,2}(:\d{2})?\s*(am|pm)(\s+(on\s+)?\w+)?)\b",
        r"\b(now|today|tonight|this evening|tomorrow(\s+(morning|afternoon|evening))?)\b",
        r"\b(next\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|week|month))\b",
        r"\b(this\s+week|for\s+a\s+few\s+days|until\s+tomorrow|until\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday))\b",
        r"\b(this\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday|evening|afternoon))\b",
        r"\b(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b",
        r"\b(after\s+the\s+[^.,!\?;\n]+|when\s+[^.,!\?;\n]+\s+(gets back|finishes|arrives)|once\s+[^.,!\?;\n]+)\b",
    ]

    def extract(self, text: str, peer_id: Optional[str] = None) -> List[ExtractionCandidate]:
        candidates: List[ExtractionCandidate] = []
        if not text or not text.strip():
            return candidates

        clauses = self._split_clauses(text)

        for clause_text, clause_start in clauses:
            cand = self._extract_candidate_from_clause(clause_text, clause_start, peer_id, text)
            if cand:
                candidates.append(cand)

        return candidates

    def _split_clauses(self, text: str) -> List[tuple[str, int]]:
        clauses = []
        delimiters = r"(;\s*|\.\s+|\n+|,\s+but\s+|\b\s+and\s+\b)"
        parts = re.split(delimiters, text, flags=re.IGNORECASE)
        
        current_offset = 0
        for part in parts:
            if not part:
                continue
            if re.match(r"^;\s*$|^\.\s*$|^\n+$|^,\s+but\s+$|^\s+and\s+$", part, re.IGNORECASE):
                current_offset += len(part)
                continue
            
            clause_str = part.strip()
            start_idx = text.find(clause_str, current_offset)
            if start_idx != -1:
                current_offset = start_idx + len(clause_str)
            else:
                start_idx = current_offset
                current_offset += len(part)

            clauses.append((clause_str, start_idx))

        return clauses

    def _extract_candidate_from_clause(
        self, clause: str, clause_start: int, peer_id: Optional[str], full_text: str
    ) -> Optional[ExtractionCandidate]:
        lower_clause = clause.lower().strip()

        # Check for quoted speech
        is_quoted = bool(re.search(r'["\'].*?\b(i\'ll|i will|going to)\b.*?["\']', clause, re.IGNORECASE))

        # Check for negation e.g. "don't", "not", "won't"
        is_negated = bool(re.search(r"(n't|\bnot\b|\bnever\b|\bno longer\b)", lower_clause))

        # Check for hypothetical
        is_hypothetical = bool(re.search(r"\b(if\s+i|in case|maybe\s+i|might|could)\b", lower_clause)) and not is_negated
        is_sarcastic = "🙄" in clause or bool(re.search(r"\b(yeah right|as if)\b", lower_clause))

        # Discussion of one's earlier words is evidence about speech, not a fresh intention.
        discusses_prior_speech = bool(re.search(
            r"\b(i\s+(?:told|said)|i was wrong when i said)\b", lower_clause
        ))
        if discusses_prior_speech:
            is_quoted = True

        # Check for reported speech
        is_reported = bool(re.search(
            r"\b(?:said\s+(?:he|she|they)|told\s+me|reported\s+that)\b",
            lower_clause,
        )) or ("said" in lower_clause and "he'll" in lower_clause)

        # 1. Check for Suppression patterns: e.g. "Don't ask me about Ashley until next week", "stop asking me", "leave this alone"
        suppression_hint = None
        reopen_match = re.search(
            r"\b(?:actually\s+)?(?:we can (?:talk about|discuss|mention)|"
            r"you can ask me about)\s+(.+?)\s+now\b",
            lower_clause,
        )
        suppression_match = re.search(
            r"\b(?:don't\s+ask\s+me\s+about|stop\s+asking\s+me\s+about|"
            r"don't\s+mention|don't\s+bring)\s+(.+?)(?=\s+(?:until|unless|today|tonight|tomorrow|this\s+week|next\s+week|for\s+(?:now|a\s+few\s+days))\b|$)",
            lower_clause,
        )
        bring_up_match = re.search(r"\b(?:don't|never)\s+bring\s+(.+?)\s+up\b", lower_clause)
        if reopen_match:
            suppression_hint = {
                "action": "reopen",
                "target_type": "topic",
                "topic_or_entity": reopen_match.group(1).strip(),
                "reason": "user_explicit_reopen",
            }
        elif suppression_match or bring_up_match:
            topic_target = re.sub(
                r"\s+up$", "", (suppression_match or bring_up_match).group(1).strip()
            )
            suppression_hint = {
                "target_type": "topic",
                "topic_or_entity": topic_target,
                "reason": f"User requested suppression: {clause}",
                "raw_temporal_phrase": self._extract_temporal_phrase(lower_clause),
                "reopen_condition": (
                    "user_mentions_topic" if re.search(r"\b(?:until i bring it up|unless i mention it)\b", lower_clause)
                    else "indefinite" if re.search(r"\bnever\b", lower_clause)
                    else None
                ),
            }
        elif re.search(r"\b(not now|leave (?:this|that|it) alone|drop it)\b", lower_clause):
            suppression_hint = {
                "target_type": "topic",
                "topic_or_entity": None,
                "reason": f"User requested suppression: {clause}",
                "ambiguous_target": True,
            }

        # 2. Check for Resolutions / Outcome Updates e.g. "Actually I'm not doing that tonight", "James sent it", "James replied"
        resolution_hint = None
        reschedule = re.search(
            r"\b(?:actually|sorry|instead|still).*?\b(?:now|tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday|morning|afternoon|evening)\b.*?\b(?:not\s+(?:tomorrow|today|tonight|monday|tuesday|wednesday|thursday|friday|saturday|sunday))?",
            lower_clause,
        )
        changed_not_abandoned = re.search(r"\bstill\s+(?:doing|going|sending|calling).*?\bjust\s+not\b", lower_clause)
        correction_date = re.search(r"\b(?:sorry,?\s*)?(friday|saturday|sunday|monday|tuesday|wednesday|thursday),?\s+not\s+(friday|saturday|sunday|monday|tuesday|wednesday|thursday)\b", lower_clause)
        if changed_not_abandoned or correction_date or (reschedule and re.search(r"\b(?:i'll|i will|i'm testing|i am testing|do it|make it|appointment)\b", lower_clause)):
            resolution_hint = {
                "action": "reschedule",
                "wrong_value": correction_date.group(2) if correction_date else None,
                "correct_value": correction_date.group(1) if correction_date else self._extract_temporal_phrase(lower_clause),
                "target_text": clause,
                "evidence": clause,
            }
        elif re.search(
            r"\b(?:actually|change of plan)\b.*?\b(?:not doing|cancelling|postponing)\b|"
            r"\b(?:scratch that|forget (?:that|the (?:first|second|third) one)|"
            r"changed my mind|no longer relevant)\b",
            lower_clause,
        ):
            resolution_hint = {
                "action": "cancel",
                "evidence": clause,
            }
        elif re.search(r"\b(\w+)\s+(sent it|replied|finished|done|submitted|completed)\b", lower_clause):
            m_res = re.search(r"\b(\w+)\s+(sent it|replied|finished|done|submitted|completed)\b", lower_clause)
            resolution_hint = {
                "action": "fulfill",
                "actor": m_res.group(1) if m_res else peer_id,
                "evidence": clause,
            }
        elif re.fullmatch(r"\s*(done|that's sorted|it happened)\s*[.!]?\s*", lower_clause):
            resolution_hint = {"action": "fulfill", "evidence": clause}
        elif re.search(
            r"\b(?:looks like|turns out)\s+i(?:'ll| will| am going to)\s+"
            r"(?:be\s+)?starting\s+(?:there|with them)\b",
            lower_clause,
        ):
            # A natural indirect acceptance update (for example, starting at a
            # new job) resolves a single outstanding outcome without requiring
            # the user to repeat the earlier wording.
            resolution_hint = {"action": "fulfill", "evidence": clause}
        elif re.search(r"\b(never happened|never called|didn't happen)\b", lower_clause):
            resolution_hint = {"action": "cancel", "evidence": clause}
        elif re.search(r"\bactually\s+i\s+said\s+(\w+),\s*not\s+(\w+)\b", lower_clause):
            m_corr = re.search(r"\bactually\s+i\s+said\s+(\w+),\s*not\s+(\w+)\b", lower_clause)
            resolution_hint = {
                "action": "correct",
                "correct_value": m_corr.group(1) if m_corr else None,
                "wrong_value": m_corr.group(2) if m_corr else None,
                "evidence": clause,
            }

        # 3. Check for Open Loop hints e.g. "ask me tomorrow how the appointment went", "report back"
        open_loop_hint = None
        if re.search(r"\b(ask me|follow up|remind me)\b", lower_clause):
            open_loop_hint = f"Follow-up on: {clause}"

        # 4. Check Epistemic Attribution e.g. "I think Ashley might be stressed because of work"
        epistemic_provenance = None
        actor_peer_id = peer_id
        target_peer_id = None

        epistemic_claim = None
        nested_ep = re.search(r"\b(\w+)\s+thinks\s+(\w+)\s+believes\s+(?:she|he|they)\s*(?:is|are)?\s*([^.,!?;\n]+)", lower_clause)
        third_ep = re.search(r"\b(\w+)\s+thinks\s+(\w+)\s+(?:is|are)\s+([^.,!?;\n]+)", lower_clause)
        ep_match = re.search(r"\b(i think|i believe|seems like|reckon)\s+(\w+)\s+(might|could|is)\s+([^.,!?;\n]+)", lower_clause)
        if nested_ep:
            epistemic_provenance = "attributed_belief"
            actor_peer_id, target_peer_id = nested_ep.group(1), nested_ep.group(2)
            epistemic_claim = {"perspective": actor_peer_id, "target": target_peer_id, "claim": f"believes they are {nested_ep.group(3)}", "nested": True}
        elif third_ep:
            epistemic_provenance = "attributed_belief"
            actor_peer_id, target_peer_id = third_ep.group(1), third_ep.group(2)
            epistemic_claim = {"perspective": actor_peer_id, "target": target_peer_id, "claim": third_ep.group(3), "nested": False}
        elif ep_match:
            epistemic_provenance = "attributed_belief"
            target_peer_id = ep_match.group(2)
            epistemic_claim = {"perspective": peer_id or "user", "target": target_peer_id, "claim": ep_match.group(4), "nested": False}
        elif is_reported:
            epistemic_provenance = "reported_statement"
            reported_actor = re.search(
                r"\b([a-zA-Z]+)\s+(?:said|told|reported)\b", clause
            )
            if reported_actor and reported_actor.group(1).lower() not in ("i", "he", "she", "they"):
                actor_peer_id = reported_actor.group(1)
        elif re.search(r"\b(i'm going to|i will|i have to|i must)\b", lower_clause):
            epistemic_provenance = "direct_statement"

        # 5. Check Domain & Category Tags
        domain_tag = None
        category_tag = None
        if "work" in lower_clause or "report" in lower_clause or "deploy" in lower_clause:
            domain_tag = "work"
        elif any(name in lower_clause for name in ["ashley", "james", "morgan", "family"]):
            domain_tag = "relationship"

        if re.search(r"\b(stressed|anxious|worried|fear)\b", lower_clause):
            category_tag = "struggle"
        elif re.search(r"\b(excited|win|won|accomplished)\b", lower_clause):
            category_tag = "win"

        # Match intent patterns
        matched_intent = None
        matched_type_hint = None
        for pattern, type_hint, is_neg, is_hyp, is_rep in self.INTENT_PATTERNS:
            m = re.search(pattern, lower_clause, re.IGNORECASE)
            if m:
                matched_intent = m.group(0)
                matched_type_hint = type_hint
                if is_neg:
                    is_negated = True
                if is_hyp:
                    is_hypothetical = True
                if is_rep:
                    is_reported = True
                break

        if not matched_intent and not is_reported and not suppression_hint and not resolution_hint and not epistemic_provenance and not ("appointment" in lower_clause or "meeting" in lower_clause):
            return None

        # Check for temporal phrase
        temporal_phrase = self._extract_temporal_phrase(lower_clause)

        key_raw = f"{clause_start}:{clause_start+len(clause)}:{clause}"
        candidate_key = f"c_{hashlib.md5(key_raw.encode('utf-8')).hexdigest()[:10]}"

        confidence = 0.9
        if is_hypothetical or is_negated or is_quoted or is_sarcastic:
            confidence = 0.3

        return ExtractionCandidate(
            candidate_key=candidate_key,
            source_start=clause_start,
            source_end=clause_start + len(clause),
            observation=clause,
            actor_peer_id=actor_peer_id,
            subject_peer_id=target_peer_id or peer_id,
            semantic_type="expectation_candidate",
            expectation_type_hint=matched_type_hint,
            temporal_phrase=temporal_phrase,
            confidence=confidence,
            is_negated=is_negated,
            is_hypothetical=is_hypothetical,
            is_reported_speech=is_reported,
            is_quoted=is_quoted,
            is_sarcastic=is_sarcastic,
            open_loop_hint=open_loop_hint,
            suppression_hint=suppression_hint,
            epistemic_provenance=epistemic_provenance,
            domain_tag=domain_tag,
            category_tag=category_tag,
            resolution_hint=resolution_hint,
            epistemic_claim=epistemic_claim,
        )

    def _extract_temporal_phrase(self, lower_clause: str) -> Optional[str]:
        for t_pat in self.TEMPORAL_PATTERNS:
            t_m = re.search(t_pat, lower_clause, re.IGNORECASE)
            if t_m:
                return t_m.group(0)
        return None


class LLMExtractorProvider(BaseExtractorProvider):
    """Two-stage model-led watcher: loose noticing, then schema shaping."""

    def __init__(
        self, api_url: Optional[str] = None, api_key: Optional[str] = None,
        model: Optional[str] = None, fallback_on_error: bool = False,
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("OPENROUTER_API_KEY") or os.getenv("XAI_API_KEY") or ""
        default_url = ("https://openrouter.ai/api/v1/chat/completions"
                       if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY")
                       else "https://api.openai.com/v1/chat/completions")
        self.api_url = api_url or os.getenv("SYNAPSE_MODEL_URL") or default_url
        self.model = model or os.getenv("SYNAPSE_EXTRACTOR_MODEL") or "gpt-4o-mini"
        self.fallback_on_error = fallback_on_error
        self.last_backend = "unavailable"
        self.last_observations: List[LooseObservation] = []
        self.last_failure: Optional[str] = None
        self.last_stage_metrics: Dict[str, Dict[str, Any]] = {}
        self._last_call_usage: Dict[str, Any] = {}

    def _chat_json(self, prompt: str) -> Any:
        attempts = max(1, min(2, int(os.getenv("SYNAPSE_EXTRACTOR_MAX_ATTEMPTS", "2"))))
        last_error: Optional[Exception] = None
        for attempt in range(attempts):
            try:
                with httpx.Client(timeout=float(os.getenv("SYNAPSE_EXTRACTOR_TIMEOUT_SECONDS", "8"))) as client:
                    response = client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                        json={
                            "model": self.model,
                            "messages": [{"role": "user", "content": prompt}],
                            "temperature": 0.0,
                            "response_format": {"type": "json_object"},
                        },
                    )
                    response.raise_for_status()
                    payload = response.json()
                    self._last_call_usage = payload.get("usage") or {}
                    content = payload["choices"][0]["message"]["content"]
                    return json.loads(content)
            except (httpx.HTTPError, KeyError, TypeError, json.JSONDecodeError) as err:
                last_error = err
                if attempt + 1 < attempts:
                    logger.warning("Model stage attempt %s/%s failed; retrying", attempt + 1, attempts)
        assert last_error is not None
        raise last_error

    def extract(self, text: str, peer_id: Optional[str] = None) -> List[ExtractionCandidate]:
        if not self.api_key:
            self.last_backend = "failed"
            self.last_failure = "credentials_unavailable"
            return []

        try:
            self.last_stage_metrics = {}
            loose_started = time.perf_counter()
            loose = self._chat_json(f"""You are the loose-noticing stage of a companion's operational watcher.
Notice meaning before categorising. From the latest USER TURN, describe only things that may
have changed operationally: unresolved obligations, commitments, recurring intentions,
upcoming events, follow-ups, important current state, cancellations, completions, progress,
boundaries/suppressions, or active project focus. Static background or aspirations normally
belong in semantic memory and should not be promoted. Natural phrasing such as 'still need',
'been meaning to', 'I'd like to', 'managed to', and 'forget that' is meaningful.
Return JSON {{"observations": [...]}} with at most 8 items. Each item: description (plain
semantic English, need not be verbatim), evidence_text (verbatim supporting excerpt),
source_start/source_end when confident, confidence 0..1, actor_peer_id, subject_refs array,
temporal_language. When one turn reports concrete progress/accomplishment AND says the larger
goal remains unresolved (for example "sent three applications but still need to keep
applying"), emit two observations: the progress event and the continuing objective. Do not
collapse them. Do not assign operational types. Do not invent context.
Treat "I did my walk today" as completion of today's walk, not generic progress. Notice
explicit recurrence revisions such as changing "every day" to Monday/Wednesday/Friday as a
replacement of the prior cadence. Treat an outcome report such as "Ashley's event went
really well" as resolution/outcome of that event or follow-up, not as a newly upcoming event.
USER TURN: {json.dumps(text)}
PEER: {json.dumps(peer_id or 'user')}""")
            self.last_stage_metrics["loose"] = {
                "latency_ms": round((time.perf_counter() - loose_started) * 1000, 1),
                "usage": dict(self._last_call_usage),
            }
            observations = []
            for i, raw in enumerate((loose.get("observations") or [])[:8]):
                evidence = str(raw.get("evidence_text") or "")
                if not evidence or evidence.lower() not in text.lower():
                    continue
                start = text.lower().find(evidence.lower())
                raw.update(observation_id=f"o_{hashlib.sha1(evidence.lower().encode()).hexdigest()[:10]}",
                           source_start=start, source_end=start + len(evidence))
                observations.append(LooseObservation(**raw))
            self.last_observations = observations
            if not observations:
                self.last_backend = "model"
                return []

            shape_started = time.perf_counter()
            shaped = self._chat_json(f"""You are the lane-shaping stage. Map untrusted loose observations into
bounded operational proposals. Return JSON {{"candidates": [...]}}. Valid operational_kind:
expectation, durable_objective, recurring_intention, progress, completion, cancellation,
suppression, open_loop, event, semantic_only. Recurrence must include cadence daily/weekly/
interval; optional days_of_week uses Monday=0. Use recurring_intention ONLY when the user
explicitly states an established cadence or clear scheduled commitment (for example "every
day", "weekly", or named weekdays). Never invent a cadence for an ongoing objective, a
one-off follow-up, "keep applying", "start exercising", or something the user explicitly
says is not yet a routine. "I still need to apply for jobs" is a durable_objective, not a
recurrence. "Check in later" is a one-off open_loop. Progress must not imply parent
completion; a progress turn may also restate a durable parent objective, but never convert
that parent into an invented recurrence.
Use progress only for a concrete accomplishment or measurable advancement that already
happened (for example sent/submitted/completed/built a count or portion). "I'm fixing X
right now" is current focus/objective, not a progress event. A desire that a product should
not feel/look/sound a certain way is product semantics, not a companion suppression.
"Leave her alone while the event is happening" is an outbound_contact suppression scoped
to that event/window, while a separate desire to check in later is an open_loop.
"I did my walk today" is completion (target_key walk), not progress. "Ashley's event went
well" is completion/resolution (target_key Ashley event), not a new event. A change from
daily to Monday/Wednesday/Friday is a revised recurring_intention with cadence weekly and
days_of_week [0,2,4], so deterministic reconciliation can supersede the prior cadence.
Cancellation/completion should include target_key/canonical_title. Time-bound follow-ups use
open_loop_hint and expiry_phrase. Suppressions include suppression_hint with target_type,
topic_or_entity, action_scope, raw_temporal_phrase. Static descriptions use semantic_only.
Project descriptions, product purpose, motivation, and hoped-for impact are semantic_only
unless the turn contains a concrete operational transition beyond "I'm working on X because
I want to create Y". If the user says a possible routine is not established, preserve that
uncertainty: use durable_objective/expectation at reduced confidence or semantic_only, never
an established recurring_intention.
Each candidate must include loose_observation_id, observation, raw_evidence, confidence,
canonical_title, actor_peer_id, subject_peer_id, temporal_phrase, expectation_type_hint,
cadence, interval_days, days_of_week, preferred_window, target_amount, target_unit,
progress_amount, progress_unit, expiry_phrase, open_loop_hint, suppression_hint,
resolution_hint. Use null/[] when absent. At most one proposal per observation.
OBSERVATIONS: {json.dumps([o.model_dump() for o in observations], default=str)}""")
            self.last_stage_metrics["shape"] = {
                "latency_ms": round((time.perf_counter() - shape_started) * 1000, 1),
                "usage": dict(self._last_call_usage),
            }
            candidates = []
            by_id = {o.observation_id: o for o in observations}
            for raw in (shaped.get("candidates") or [])[:8]:
                obs = by_id.get(raw.get("loose_observation_id"))
                if not obs:
                    continue
                kind = raw.get("operational_kind")
                validation_notes = []
                for hint_field in ("resolution_hint", "suppression_hint", "clarification_hint"):
                    if raw.get(hint_field) is not None and not isinstance(raw.get(hint_field), dict):
                        raw[hint_field] = None
                        validation_notes.append(f"discarded_malformed_{hint_field}")
                if raw.get("open_loop_hint") is not None and not isinstance(raw.get("open_loop_hint"), str):
                    hint_value = raw.get("open_loop_hint")
                    raw["open_loop_hint"] = (
                        raw.get("canonical_title")
                        or (" ".join(str(value) for value in hint_value.values()) if isinstance(hint_value, dict) else None)
                    )
                    validation_notes.append("normalized_malformed_open_loop_hint")
                if raw.get("suppression_hint") and kind != "suppression":
                    raw["suppression_hint"] = None
                    validation_notes.append("discarded_suppression_hint_from_non_suppression_lane")
                if raw.get("suppression_hint"):
                    hint = raw["suppression_hint"]
                    if hint.get("target_type") not in {
                        "expectation", "open_loop", "topic", "entity", "honcho_ref"
                    }:
                        hint["target_type"] = "topic"
                        validation_notes.append("normalized_invalid_suppression_target_type")
                    if hint.get("action_scope") not in {
                        None, "all_surfaces", "followup_prompt", "outbound_contact"
                    }:
                        hint["action_scope"] = "all_surfaces"
                        validation_notes.append("normalized_invalid_suppression_action_scope")
                evidence_lower = obs.evidence_text.lower().replace("’", "'")
                normalized_text = text.replace("’", "'")
                explicit_daily = bool(re.search(r"\b(?:every day|daily|each day)\b", text, re.IGNORECASE))
                unestablished = bool(re.search(
                    r"\b(?:haven't|have not|isn't|is not|not)\b.+\b(?:habit|routine|established)\b",
                    normalized_text,
                    re.IGNORECASE,
                ))
                if kind in {"expectation", "durable_objective"} and explicit_daily and not unestablished:
                    raw["operational_kind"] = "recurring_intention"
                    raw["cadence"] = "daily"
                    raw["expectation_type_hint"] = None
                    kind = "recurring_intention"
                    validation_notes.append("promoted_explicit_daily_recurrence")
                elif kind == "recurring_intention" and unestablished:
                    raw["operational_kind"] = "durable_objective"
                    raw["cadence"] = None
                    raw["interval_days"] = None
                    raw["days_of_week"] = []
                    raw["confidence"] = min(float(raw.get("confidence", 0)), 0.75)
                    kind = "durable_objective"
                    validation_notes.append("demoted_unestablished_recurrence_to_objective")
                if kind == "suppression" and re.search(
                    r"\bdon't want (?:it|the .+?) to (?:feel|look|sound|be)\b", evidence_lower
                ):
                    raw["operational_kind"] = "semantic_only"
                    raw["suppression_hint"] = None
                    kind = "semantic_only"
                    validation_notes.append("demoted_product_preference_from_suppression")
                if kind == "progress" and not re.search(
                    r"\b(?:sent|submitted|completed|finished|did|made|built|wrote|applied|managed)\b|\b\d+\b",
                    evidence_lower,
                ):
                    raw["operational_kind"] = "durable_objective"
                    kind = "durable_objective"
                    validation_notes.append("demoted_non_accomplishment_from_progress")
                if kind == "durable_objective" and not raw.get("expectation_type_hint"):
                    raw["expectation_type_hint"] = "user_commitment"
                    validation_notes.append("defaulted_durable_objective_expectation_type")
                elif kind == "event" and not raw.get("expectation_type_hint"):
                    raw["expectation_type_hint"] = "planned_event"
                    validation_notes.append("defaulted_event_expectation_type")
                elif kind == "expectation" and not raw.get("expectation_type_hint"):
                    raw["expectation_type_hint"] = "user_intention"
                    validation_notes.append("defaulted_expectation_type")
                if kind == "open_loop" and not raw.get("open_loop_hint"):
                    raw["open_loop_hint"] = raw.get("canonical_title") or obs.description
                    validation_notes.append("defaulted_open_loop_hint")
                if kind == "durable_objective" and re.search(
                    r"\b(?:is|are|feels?) more (?:interesting|important|fun|appealing)\b",
                    evidence_lower,
                ) and not re.search(r"\b(?:still need|need to|have to|must)\b", evidence_lower):
                    raw["operational_kind"] = "semantic_only"
                    kind = "semantic_only"
                    validation_notes.append("demoted_comparative_preference_from_objective")
                if kind == "durable_objective" and re.search(
                    r"\b(?:haven't|have not|isn't|is not|not)\b.+\b(?:habit|routine|established)\b",
                    normalized_text,
                    re.IGNORECASE,
                ):
                    raw["confidence"] = min(float(raw.get("confidence", 0)), 0.75)
                    validation_notes.append("reduced_confidence_for_unestablished_routine")
                if kind == "cancellation" and not raw.get("resolution_hint"):
                    raw["resolution_hint"] = {"action": "cancel", "target_text": raw.get("canonical_title")}
                    validation_notes.append("defaulted_cancellation_resolution_hint")
                if kind == "completion" and not raw.get("resolution_hint"):
                    raw["resolution_hint"] = {"action": "fulfill", "target_text": raw.get("canonical_title")}
                    validation_notes.append("defaulted_completion_resolution_hint")
                if kind == "durable_objective" and re.search(
                    r"\b(?:i(?:'m| am)\s+)?working on\b.+\bbecause\b.+\b(?:want|hope) to (?:create|build|make)\b",
                    normalized_text,
                    re.IGNORECASE,
                ):
                    raw["operational_kind"] = "semantic_only"
                    kind = "semantic_only"
                    validation_notes.append("demoted_project_purpose_without_operational_transition")
                # Stable across model wording changes on retry; one proposal per loose observation.
                key_material = f"{obs.observation_id}:{kind}"
                raw.update(
                    candidate_key=f"c_{hashlib.sha1(key_material.lower().encode()).hexdigest()[:12]}",
                    source_start=obs.source_start, source_end=obs.source_end,
                    observation=raw.get("observation") or obs.description,
                    raw_evidence=obs.evidence_text, confidence=min(float(raw.get("confidence", 0)), obs.confidence),
                    extractor_version="model-loose-shape-v1",
                    validation_notes=validation_notes,
                )
                candidates.append(ExtractionCandidate(**raw))
            self.last_backend = "model"
            self.last_failure = None
            return candidates
        except Exception as err:
            logger.exception("Model-led extraction failed")
            self.last_backend = "failed"
            self.last_failure = f"{type(err).__name__}: {err}"[:500]

        if self.fallback_on_error:
            self.last_backend = "rules_fallback_explicit"
            return RuleBasedExtractorProvider().extract(text, peer_id=peer_id)
        return []


class TurnExtractor:
    """
    Coordinator for loose turn extraction.
    Consumes raw turn text and emits a list of typed `ExtractionCandidate` contracts.
    Switches between RuleBased and LLM providers via environment configuration.
    """

    def __init__(self, provider: Optional[BaseExtractorProvider] = None):
        provider_type = os.getenv("SYNAPSE_EXTRACTOR_PROVIDER", "model").lower()
        if provider:
            self.provider = provider
        elif provider_type in ("llm", "model"):
            self.provider = LLMExtractorProvider()
        else:
            self.provider = RuleBasedExtractorProvider()

    def extract_candidates(
        self, text: str, peer_id: Optional[str] = None
    ) -> List[ExtractionCandidate]:
        if not text or not text.strip():
            return []
        return self.provider.extract(text, peer_id=peer_id)

    def extraction_result(self, candidates: List[ExtractionCandidate]) -> ExtractionResult:
        return ExtractionResult(
            candidates=candidates,
            observations=getattr(self.provider, "last_observations", []),
            backend=getattr(self.provider, "last_backend", "rules"),
            model=getattr(self.provider, "model", None),
            failure=getattr(self.provider, "last_failure", None),
        )
