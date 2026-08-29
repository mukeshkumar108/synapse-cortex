"""Bounded per-turn working-set compiler (L0 HOT / L1 WARM / L2 COLD refs).

Durability is not prompt inclusion. The attention packet / intelligence brief
is structured source material; this module selects the smallest sufficient
working set for the current cognitive problem. Deterministic, zero LLM calls.

Budgets (documented choice):
  HOT   <=  600 chars  - turn + posture + immediate conversational operation
  WARM  <= 2800 chars  - ~700 tokens of bounded life/project state
  REFS  <=  900 chars  - retrieval handles only, never content
  TOTAL <=  4800 chars - ~1200 tokens, leaving reserve for scene, memory and
                          voice modules in the foreground prompt.

Domain-shift behavior: warm items are admitted by token overlap with the
current turn, or because they are time-critical (now-horizon deadlines). When
the user changes domain ("Ashley just called" after a coding session), coding
items lose overlap and are dropped unless they are time-critical.
"""

import json
import re
from typing import Any, Dict, List, Optional

HOT_BUDGET_CHARS = 600
WARM_BUDGET_CHARS = 2800
REFS_BUDGET_CHARS = 900
TOTAL_BUDGET_CHARS = HOT_BUDGET_CHARS + WARM_BUDGET_CHARS + REFS_BUDGET_CHARS
# chars ~ 4 tokens for this kind of compact typed payload
ESTIMATED_TOKENS_PER_CHAR = 0.25

_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "of", "to", "in", "on", "at",
    "for", "with", "about", "is", "are", "was", "were", "be", "been", "am",
    "do", "does", "did", "have", "has", "had", "i", "me", "my", "you", "your",
    "it", "its", "this", "that", "just", "so", "can", "will", "would", "ok",
    "hey", "hi", "im", "ive", "dont", "what", "how", "why", "she", "her",
    "he", "him", "they", "them", "we", "us", "not", "no", "yes", "really",
    "some", "any", "get", "got", "go", "going", "talk", "talking",
}

# Task-intent cues: when present, canonical task/calendar state is admitted
# even without topical overlap, because the user is querying it directly.
_TASK_INTENT_TOKENS = {
    "task", "tasks", "todo", "todos", "reminder", "reminders", "deadline",
    "list", "due", "calendar", "schedule", "planned",
}


def _tokens(text: str) -> set:
    return {
        token for token in re.findall(r"[a-z0-9']+", (text or "").lower())
        if len(token) >= 3 and token not in _STOPWORDS
    }


def _item_text(item: Dict[str, Any]) -> str:
    return " ".join(
        str(item.get(key) or "")
        for key in ("title", "topic", "summary", "content", "evidence",
                    "observation", "why_relevant_now", "notes")
    )


def _compact_item(item: Dict[str, Any], kind: str, score: float,
                  *, surface_safe: str, proactive_eligible: bool,
                  canonical: bool) -> Optional[Dict[str, Any]]:
    topic = (
        item.get("title") or item.get("topic")
        or item.get("summary") or item.get("content") or ""
    )
    if not topic:
        return None
    refs = [
        ref for ref in (
            item.get("honcho_message_id"), item.get("evidence_ref"),
            item.get("id"), item.get("source_object_id"),
            item.get("source_message_id"),
        ) if ref
    ]
    return {
        "what": str(topic)[:160],
        "kind": kind,
        "temporal_state": item.get("temporal_state")
        or item.get("status") or item.get("state") or item.get("outcome_state")
        or "unknown",
        "why_relevant_now": str(item.get("why_relevant_now")
                                or item.get("reason") or item.get("uncertainty")
                                or "selected by current-turn relevance")[:160],
        "confidence": item.get("confidence") if isinstance(
            item.get("confidence"), (int, float)) else 0.7,
        "relevance": round(score, 3),
        "refs": [str(ref) for ref in refs[:3]],
        "surface_safe": surface_safe,
        "proactive_eligible": proactive_eligible,
        "canonical": canonical,
    }


def _serialize(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, default=str, separators=(",", ":"))


class WorkingSetService:
    """Compiles the L0/L1/L2 per-turn working set from a compiled packet."""

    def compile_working_set(
        self,
        packet: Dict[str, Any],
        *,
        turn_text: str = "",
        current_message_id: Optional[str] = None,
        posture: Optional[str] = None,
        conversational_operation: Optional[str] = None,
        director_hints: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        hints = director_hints or {}
        intent = str(hints.get("intent") or "")
        primary_act = str(hints.get("primary_act") or "")
        turn_tokens = _tokens(turn_text)
        task_intent = intent in ("task", "mixed") or bool(
            turn_tokens & _TASK_INTENT_TOKENS
        )

        hot: Dict[str, Any] = {
            "turn": (turn_text or "")[:240],
            "message_id": current_message_id,
            "posture": posture,
            "operation": conversational_operation,
            "task_intent": task_intent,
        }
        hot_chars = len(_serialize(hot))

        # ---- WARM selection ---------------------------------------------
        candidates: List[tuple] = []
        brief = packet.get("intelligence_brief") or {}
        horizons = brief.get("horizons") or {}

        for horizon in ("now", "today", "tomorrow", "later"):
            for item in horizons.get(horizon, []):
                kind = str(item.get("kind") or "state")
                canonical = kind in ("task", "event")
                score = self._score(item, turn_tokens, base={
                    "now": 0.5, "today": 0.35, "tomorrow": 0.2,
                    "later": 0.1,
                }[horizon])
                if task_intent and kind in ("task", "event"):
                    score = max(score, 0.9)
                candidates.append((score, item, kind, canonical, horizon))

        # Backstage / sensitive attention: admissible only when the user
        # themselves led here (active-conversation understanding), never
        # proactive. Uses existing provenance semantics: non-source
        # sophie_attention is backstage by contract.
        for item in (brief.get("backstage_attention") or [])[:8]:
            score = self._score(item, turn_tokens, base=0.0)
            if score > 0:
                candidates.append((
                    min(score, 0.6), item, "backstage_attention",
                    False, "backstage",
                ))

        # Unresolved / unknown-outcome items are not foreground by default,
        # but the user may lead into them ("did I end up going?"). Then they
        # are warm with a natural-check suggestion, never proactive.
        for item in horizons.get("unresolved", [])[:8]:
            score = self._score(item, turn_tokens, base=0.0)
            if score > 0:
                candidates.append((
                    score, item, "unresolved", False, "unresolved",
                ))

        for item in packet.get("open_loops", [])[:5]:
            score = self._score(item, turn_tokens, base=0.3)
            if score > 0:
                candidates.append((score, item, "open_loop", False, "open_loops"))

        # Time-critical canonical state is admitted even without overlap.
        for item in packet.get("hard_deadlines", [])[:3]:
            if item.get("temporal_state") in ("deadline_passed",
                                              "deadline_approaching"):
                candidates.append((1.0, item, "deadline", True, "deadlines"))

        candidates.sort(key=lambda pair: -pair[0])

        warm: List[Dict[str, Any]] = []
        dropped = 0
        warm_chars = 0
        for score, item, kind, canonical, horizon in candidates:
            if score <= 0:
                dropped += 1
                continue
            compact = _compact_item(
                item, kind, score,
                surface_safe=(
                    "user_led_only" if kind == "backstage_attention"
                    else "ask_naturally" if kind == "unresolved"
                    else "foreground_ok"
                ),
                proactive_eligible=(
                    kind not in ("backstage_attention", "unresolved")
                    and horizon in ("now", "today", "deadlines")
                ),
                canonical=canonical,
            )
            if compact is None:
                dropped += 1
                continue
            item_chars = len(_serialize(compact))
            if warm_chars + item_chars > WARM_BUDGET_CHARS:
                dropped += 1
                continue
            warm.append(compact)
            warm_chars += item_chars

        # ---- COLD references ---------------------------------------------
        refs: List[Dict[str, Any]] = []
        ref_chars = 0
        seen_refs: set = set()

        def add_ref(ref_type: str, ref_id: Any, note: str = "") -> None:
            nonlocal ref_chars
            if not ref_id:
                return
            ref_id = str(ref_id)
            if ref_id in seen_refs:
                return
            entry = {"type": ref_type, "id": ref_id, "note": note[:80]}
            entry_chars = len(_serialize(entry))
            if ref_chars + entry_chars > REFS_BUDGET_CHARS:
                return
            refs.append(entry)
            seen_refs.add(ref_id)
            ref_chars += entry_chars

        for item in warm:
            for ref in item.get("refs", []):
                add_ref(item["kind"], ref, item["what"])
        for item in horizons.get("unresolved", [])[:6]:
            add_ref("unresolved", item.get("id"), str(item.get("title") or ""))
        for message_id in packet.get("relevant_honcho_message_ids", [])[:8]:
            add_ref("honcho_evidence", message_id)

        total_chars = hot_chars + warm_chars + ref_chars
        return {
            "version": "working-set-v1",
            "levels": {
                "hot": hot,
                "warm": warm,
                "cold_refs": refs,
            },
            "budgets": {
                "hot_chars": HOT_BUDGET_CHARS,
                "warm_chars": WARM_BUDGET_CHARS,
                "refs_chars": REFS_BUDGET_CHARS,
                "total_chars": TOTAL_BUDGET_CHARS,
            },
            "metrics": {
                "hot_chars": hot_chars,
                "warm_chars": warm_chars,
                "ref_chars": ref_chars,
                "total_chars": total_chars,
                "estimated_tokens": int(total_chars * ESTIMATED_TOKENS_PER_CHAR),
                "hot_items": 1,
                "warm_items": len(warm),
                "ref_items": len(refs),
                "dropped_candidates": dropped,
                "within_budget": total_chars <= TOTAL_BUDGET_CHARS,
                "domains": sorted({item["kind"] for item in warm}),
            },
        }

    @staticmethod
    def _score(item: Dict[str, Any], turn_tokens: set, *, base: float) -> float:
        """Overlap-based relevance. `base` is an eligibility prior only:
        topical overlap with the current turn always outranks it, and a
        zero-overlap non-critical item scores 0 so a domain shift genuinely
        repacks the warm set instead of dragging stale domains along."""
        text_tokens = _tokens(_item_text(item))
        if not text_tokens:
            return 0.0 if base < 0.45 else base * 0.5
        overlap = turn_tokens & text_tokens
        if not overlap:
            return 0.0
        return min(1.0, base + 0.4 + 0.1 * len(overlap))
