"""Turn Working Set: the tiny per-turn selection (3-5 items).

Durability is not prompt inclusion. AttentionState (what is unusually relevant
in this temporal window) and a WorldModel fragment (alive Matters, people,
known unknowns) are structured source material; this module selects the
smallest sufficient set for the CURRENT TURN, each item carrying provenance and
a pointer to the projection holding more depth. Disposable, never canonical;
the whole WorldModel is never injected. Deterministic, zero LLM calls.
(docs/CORTEX_ARCHITECTURE.md §10)

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
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

MAX_WARM_ITEMS = 5
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


USER_DAY_START_HOUR = 5

# Deictic recency words. They say WHEN, not WHAT: "our call earlier" must find
# what happened earlier today, not whichever old item shares the word "call".
_MORNING = re.compile(r"\bthis morning\b", re.IGNORECASE)
_AFTERNOON = re.compile(r"\bthis afternoon\b", re.IGNORECASE)
_EARLIER_TODAY = re.compile(
    r"\b(earlier|earlier today|today|just now|a (?:little |short )?(?:bit|while) (?:ago|back)|"
    r"(?:a few|couple of) hours ago|this (?:morning|afternoon))\b", re.IGNORECASE)
OUT_OF_WINDOW_PENALTY = 0.35


def recency_window(turn_text: str, now: Optional[datetime],
                   tz_name: str) -> Optional[Tuple[datetime, datetime]]:
    """[start, end) in naive UTC for a deictic recency phrase, else None."""
    if now is None or not _EARLIER_TODAY.search(turn_text or ""):
        return None
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        zone = ZoneInfo("UTC")
    aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    local = aware.astimezone(zone)
    day = local.date() if local.hour >= USER_DAY_START_HOUR else (local - timedelta(days=1)).date()
    start_local = datetime.combine(day, time(USER_DAY_START_HOUR), tzinfo=zone)
    end_local = local
    if _MORNING.search(turn_text):
        end_local = min(local, datetime.combine(day, time(12), tzinfo=zone))
    elif _AFTERNOON.search(turn_text):
        start_local = max(start_local, datetime.combine(day, time(12), tzinfo=zone))
    to_naive = lambda value: value.astimezone(timezone.utc).replace(tzinfo=None)
    return to_naive(start_local), to_naive(end_local)


def _as_naive_utc(value: Any) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed.astimezone(timezone.utc).replace(tzinfo=None) if parsed.tzinfo else parsed


def _item_time(item: Dict[str, Any]) -> Optional[datetime]:
    for key in ("touched_at", "last_touched", "updated_at", "created_at"):
        stamp = _as_naive_utc(item.get(key))
        if stamp is not None:
            return stamp
    return None


def _tokens(text: str) -> set:
    # Drop possessives first ("Carlos's" -> "carlos", not "carloss"), then
    # remaining apostrophes ("don't" -> "dont") so possessive mentions match
    # their base entity on both sides of an overlap comparison.
    cleaned = (text or "").lower().replace("'s", "").replace("'", "")
    raw = {
        token for token in re.findall(r"[a-z0-9]+", cleaned)
        if len(token) >= 3 and token not in _STOPWORDS
    }
    folded = set()
    for token in raw:
        folded.add(token)
        # Light plural fold so "mums" matches "mum", "checklists" matches
        # "checklist". Same fold on both sides keeps overlap symmetric.
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            folded.add(token[:-1])
    return folded


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


class TurnWorkingSetService:
    """Compiles the Turn Working Set from AttentionState (+ WorldModel fragment)."""

    def compile_turn_working_set(
        self,
        packet: Dict[str, Any],
        *,
        world_model: Optional[Dict[str, Any]] = None,
        turn_text: str = "",
        current_message_id: Optional[str] = None,
        posture: Optional[str] = None,
        conversational_operation: Optional[str] = None,
        director_hints: Optional[Dict[str, Any]] = None,
        now: Optional[datetime] = None,
        timezone_name: str = "Europe/London",
    ) -> Dict[str, Any]:
        hints = director_hints or {}
        window = recency_window(turn_text, now, timezone_name)
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
        brief = packet.get("window") or {}
        horizons = brief.get("scopes") or {}

        for horizon in ("immediate", "today", "upcoming"):
            for item in horizons.get(horizon, []):
                kind = str(item.get("kind") or "state")
                canonical = kind in ("task", "event")
                score = self._score(item, turn_tokens, base={
                    "immediate": 0.5, "today": 0.35, "upcoming": 0.15,
                }[horizon])
                if task_intent and kind in ("task", "event"):
                    score = max(score, 0.9)
                candidates.append((score, item, kind, canonical, horizon))

        # Backstage / sensitive attention: admissible only when the user
        # themselves led here (active-conversation understanding), never
        # proactive. Uses existing provenance semantics: non-source
        # sophie_attention is backstage by contract.
        for item in (packet.get("sophie_attention") or [])[:8]:
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

        # WorldModel fragment: alive Matters and known unknowns that THIS turn
        # touches (people/title overlap). Never the whole model.
        for item in self._world_candidates(world_model, turn_tokens):
            candidates.append(item)
        if window is not None:
            candidates = self._apply_recency(candidates, world_model, window)

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
                    else "ask_naturally" if kind in ("unresolved", "knowledge_gap")
                    else "foreground_ok"
                ),
                proactive_eligible=(
                    kind not in ("backstage_attention", "unresolved", "knowledge_gap", "matter")
                    and horizon in ("immediate", "today", "deadlines")
                ),
                canonical=canonical,
            )
            if compact is None:
                dropped += 1
                continue
            if kind in ("matter", "knowledge_gap"):
                compact["depth"] = item.get("depth")
                compact["matter_id"] = item.get("matter_id")
            touched = _item_time(item)
            if touched is not None:
                compact["touched_at"] = touched.isoformat()
            item_chars = len(_serialize(compact))
            if warm_chars + item_chars > WARM_BUDGET_CHARS or len(warm) >= MAX_WARM_ITEMS:
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
            "version": "turn-working-set-v1",
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
    def _apply_recency(candidates: List[tuple], world_model: Optional[Dict[str, Any]],
                       window: Tuple[datetime, datetime]) -> List[tuple]:
        """A deictic "earlier/today/this morning" turn: admit what was touched in
        the window (even with no word overlap) and demote dated items outside it."""
        start, end = window
        kept: List[tuple] = []
        for score, item, kind, canonical, horizon in candidates:
            stamp = _item_time(item)
            if stamp is not None and not (start <= stamp < end):
                score *= OUT_OF_WINDOW_PENALTY
            kept.append((score, item, kind, canonical, horizon))
        present = {str(item.get("matter_id") or item.get("id")) for _, item, *_ in kept}
        world = world_model or {}
        matters = world.get("matters") or {}
        times: Dict[str, Optional[datetime]] = {}
        for entry in list(matters.get("active") or []):
            times[str(entry.get("id"))] = _as_naive_utc(entry.get("last_touched"))
        for entry in list(matters.get("recently_resolved") or []):
            times.setdefault(str(entry.get("id")), _as_naive_utc(entry.get("resolved_at")))
        for entry in list(((world.get("recent") or {}).get("today") or {}).get("occupied") or []):
            stamp = _as_naive_utc(entry.get("last_touched"))
            if stamp is not None:
                times[str(entry.get("matter_id"))] = stamp
        titles = {str(e.get("matter_id")): e.get("title")
                  for e in list(((world.get("recent") or {}).get("today") or {}).get("occupied") or [])}
        titles.update({str(e.get("id")): e.get("title") for e in list(matters.get("active") or [])})
        titles.update({str(e.get("id")): e.get("title") for e in list(matters.get("recently_resolved") or [])})
        for matter_id, stamp in times.items():
            if stamp is None or not (start <= stamp < end) or matter_id in present or not titles.get(matter_id):
                continue
            # Newer within the window ranks a hair higher; all outrank an out-of-window lexical match.
            span = max((end - start).total_seconds(), 1.0)
            score = 0.8 + 0.15 * ((stamp - start).total_seconds() / span)
            item = {"title": titles[matter_id], "id": matter_id, "matter_id": matter_id,
                    "why_relevant_now": "touched within the time the user is referring to",
                    "status": "touched_in_window", "touched_at": stamp.isoformat(), "confidence": 0.8,
                    "depth": f"projection matter({matter_id})"}
            kept.append((min(0.95, score), item, "matter", False, "matters"))
        return kept

    @staticmethod
    def _world_candidates(world_model: Optional[Dict[str, Any]], turn_tokens: set) -> List[tuple]:
        if not world_model or not turn_tokens:
            return []
        out: List[tuple] = []
        for m in ((world_model.get("matters") or {}).get("active") or [])[:12]:
            text = " ".join([str(m.get("title") or "")] + [str(p) for p in (m.get("people") or [])])
            overlap = turn_tokens & _tokens(text)
            if overlap:
                item = {"title": m.get("title"), "id": m.get("id"), "matter_id": m.get("id"),
                        "why_relevant_now": "an alive matter this turn touches",
                        "status": m.get("status"), "confidence": 0.8,
                        "depth": f"projection matter({m.get('id')})"}
                out.append((min(1.0, 0.35 + 0.15 * len(overlap)), item, "matter", False, "matters"))
        for g in ((world_model.get("coverage") or {}).get("gaps") or [])[:10]:
            slug = str(g.get("subject_key") or "").replace("_", " ").replace("/", " ")
            overlap = turn_tokens & _tokens(slug)
            if overlap and g.get("status") in ("unknown", "partial", "conflicting"):
                item = {"title": f"not yet known: {g.get('subject_key')}", "id": g.get("subject_key"),
                        "why_relevant_now": g.get("why_useful") or "a useful gap this turn touches",
                        "status": g.get("status"), "confidence": 0.5,
                        "depth": "projection knowledge_gaps()"}
                out.append((min(0.8, 0.3 + 0.15 * len(overlap)), item, "knowledge_gap", False, "gaps"))
        return out

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
