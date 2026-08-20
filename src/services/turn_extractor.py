import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional
import httpx
from src.schemas.candidate import ExtractionCandidate

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
    """
    Model-backed extraction provider utilizing configured LLM endpoint.
    Parses turn text into typed `ExtractionCandidate` models.
    """

    def __init__(
        self, api_url: Optional[str] = None, api_key: Optional[str] = None,
        model: Optional[str] = None, fallback_on_error: bool = True,
    ):
        self.api_url = api_url or os.getenv("SYNAPSE_MODEL_URL") or "https://api.openai.com/v1/chat/completions"
        self.api_key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("XAI_API_KEY") or ""
        self.model = model or os.getenv("SYNAPSE_EXTRACTOR_MODEL") or "gpt-4o-mini"
        self.fallback_on_error = fallback_on_error
        self.last_backend = "unavailable"

    def extract(self, text: str, peer_id: Optional[str] = None) -> List[ExtractionCandidate]:
        if not self.api_key:
            if not self.fallback_on_error:
                raise RuntimeError("LLM extractor credentials are unavailable")
            logger.warning("LLMExtractorProvider called without API key; falling back to RuleBasedExtractorProvider")
            self.last_backend = "rules_fallback"
            return RuleBasedExtractorProvider().extract(text, peer_id=peer_id)

        prompt = f"""Extract companion state candidates from the following turn.
Turn Text: "{text}"
Peer ID: "{peer_id or 'user'}"

Return JSON array of candidates matching this schema:
[
  {{
    "candidate_key": "ignored_by_server",
    "source_start": 0,
    "source_end": 12,
    "observation": "exact verbatim substring of Turn Text",
    "actor_peer_id": "user",
    "subject_peer_id": "user",
    "expectation_type_hint": "user_intention | user_commitment | external_dependency | planned_event | expected_outcome | followup_invitation | null",
    "temporal_phrase": "tonight",
    "confidence": 0.9,
    "is_negated": false,
    "is_hypothetical": false,
    "is_reported_speech": false,
    "is_quoted": false,
    "is_sarcastic": false,
    "epistemic_provenance": "direct_statement | attributed_belief | reported_statement",
    "domain_tag": "work | relationship | health",
    "category_tag": "win | struggle | ask_about_later",
    "open_loop_hint": null,
    "suppression_hint": null,
    "clarification_hint": null,
    "resolution_hint": null
  }}
]

Emit evidence candidates only. Never decide or mutate lifecycle state. Preserve negation,
quotation, uncertainty, reported speech, actor, subject, and exact source spans. Use null
for absent hints. Prefer no candidate over an unsupported inference."""

        try:
            with httpx.Client(timeout=4.0) as client:
                response = client.post(
                    self.api_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": 0.0,
                    },
                )
                if response.status_code == 200:
                    self.last_backend = "model"
                    content = response.json()["choices"][0]["message"]["content"]
                    match = re.search(r"\[.*\]", content, re.DOTALL)
                    if match:
                        raw_candidates = json.loads(match.group(0))
                        candidates = []
                        for i, item in enumerate(raw_candidates):
                            observation = str(item.get("observation") or "")
                            start = item.get("source_start")
                            end = item.get("source_end")
                            if not isinstance(start, int) or not isinstance(end, int) or text[start:end] != observation:
                                start = text.lower().find(observation.lower()) if observation else -1
                                end = start + len(observation) if start >= 0 else -1
                            if start < 0 or end <= start or text[start:end].lower() != observation.lower():
                                logger.warning("Discarding model candidate without verbatim source evidence")
                                continue
                            item["source_start"] = start
                            item["source_end"] = end
                            key_raw = f"{start}:{end}:{observation.lower()}"
                            item["candidate_key"] = f"c_{hashlib.md5(key_raw.encode()).hexdigest()[:10]}"
                            candidates.append(ExtractionCandidate(**item))
                        return candidates
        except Exception as err:
            logger.warning("LLMExtractorProvider call failed (%s); falling back to rules", err)

        if not self.fallback_on_error:
            raise RuntimeError("LLM extractor request failed")
        self.last_backend = "rules_fallback"
        return RuleBasedExtractorProvider().extract(text, peer_id=peer_id)


class TurnExtractor:
    """
    Coordinator for loose turn extraction.
    Consumes raw turn text and emits a list of typed `ExtractionCandidate` contracts.
    Switches between RuleBased and LLM providers via environment configuration.
    """

    def __init__(self, provider: Optional[BaseExtractorProvider] = None):
        provider_type = os.getenv("SYNAPSE_EXTRACTOR_PROVIDER", "rules").lower()
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
