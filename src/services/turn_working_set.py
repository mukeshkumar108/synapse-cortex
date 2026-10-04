"""Turn Working Set: the tiny per-turn selection (3-5 items).

Durability is not prompt inclusion. AttentionState (what is unusually relevant
in this temporal window) and a WorldModel fragment (alive Matters, people,
known unknowns) are structured source material; this module selects the
smallest sufficient set for the CURRENT TURN, each item carrying provenance and
a pointer to the projection holding more depth. Disposable, never canonical;
the whole WorldModel is never injected. WHAT is relevant to the turn, and which time span the user refers to, are a model's judgement
(`judge`); this module only packs under budgets, enforces surface/lifecycle rules and serialises. No lexical overlap, no phrase regexes.
(docs/CORTEX_ARCHITECTURE.md §10)

Budgets (documented choice):
  HOT   <=  600 chars  - turn + posture + immediate conversational operation
  WARM  <= 2800 chars  - ~700 tokens of bounded life/project state
  REFS  <=  900 chars  - retrieval handles only, never content
  TOTAL <=  4800 chars - ~1200 tokens, leaving reserve for scene, memory and
                          voice modules in the foreground prompt.

Domain-shift behavior: warm items are admitted by the model's relevance judgement for the
current turn, or because they are time-critical (now-horizon deadlines). When
the user changes domain ("Ashley just called" after a coding session), coding
items lose overlap and are dropped unless they are time-critical.
"""

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)
MAX_WARM_ITEMS = 5
HOT_BUDGET_CHARS = 600
WARM_BUDGET_CHARS = 2800
REFS_BUDGET_CHARS = 900
TOTAL_BUDGET_CHARS = HOT_BUDGET_CHARS + WARM_BUDGET_CHARS + REFS_BUDGET_CHARS
# chars ~ 4 tokens for this kind of compact typed payload
ESTIMATED_TOKENS_PER_CHAR = 0.25

USER_DAY_START_HOUR = 5

OUT_OF_WINDOW_PENALTY = 0.35
RELEVANCE_FLOOR = 0.2                      # policy over the model's 0..1 relevance: below this an item is not needed for the turn
TIME_REFERENCES = ("none", "today", "this_morning", "this_afternoon", "yesterday", "recent_days", "this_week")
WORKING_SET_MODEL = os.getenv("WORKING_SET_MODEL", os.getenv("AGENDA_MODEL", "google/gemini-3.7-flash")).strip()


def window_for(reference: str, now: Optional[datetime], tz_name: str) -> Optional[Tuple[datetime, datetime]]:
    """[start, end) in naive UTC for a time reference the MODEL identified in the turn (calendar arithmetic only), else None."""
    if now is None or reference not in TIME_REFERENCES or reference == "none":
        return None
    try:
        zone = ZoneInfo(tz_name)
    except Exception:
        zone = ZoneInfo("UTC")
    aware = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    local = aware.astimezone(zone)
    day = local.date() if local.hour >= USER_DAY_START_HOUR else (local - timedelta(days=1)).date()
    day_start = datetime.combine(day, time(USER_DAY_START_HOUR), tzinfo=zone)
    start_local, end_local = day_start, local
    if reference == "this_morning":
        end_local = min(local, datetime.combine(day, time(12), tzinfo=zone))
    elif reference == "this_afternoon":
        start_local = max(day_start, datetime.combine(day, time(12), tzinfo=zone))
    elif reference == "yesterday":
        start_local, end_local = day_start - timedelta(days=1), day_start
    elif reference == "recent_days":
        start_local = day_start - timedelta(days=3)
    elif reference == "this_week":
        start_local = day_start - timedelta(days=7)
    to_naive = lambda value: value.astimezone(timezone.utc).replace(tzinfo=None)
    return to_naive(start_local), to_naive(end_local)


@dataclass
class Judgement:
    """The model's reading of the turn against the candidate items: per-item relevance (0..1) and the time span the user refers to."""
    scores: Dict[str, float] = field(default_factory=dict)
    time_reference: str = "none"


def candidate_key(kind: str, item: Dict[str, Any]) -> str:
    return f"{kind}:{item.get('matter_id') or item.get('id') or item.get('ref') or item.get('title') or item.get('summary') or ''}"


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
        judgement: Optional["Judgement"] = None,
    ) -> Dict[str, Any]:
        hints = director_hints or {}
        window = window_for(judgement.time_reference if judgement else "none", now, timezone_name)
        intent = str(hints.get("intent") or "")
        primary_act = str(hints.get("primary_act") or "")
        task_intent = intent in ("task", "mixed")

        hot: Dict[str, Any] = {
            "turn": (turn_text or "")[:240],
            "message_id": current_message_id,
            "posture": posture,
            "operation": conversational_operation,
            "task_intent": task_intent,
        }
        hot_chars = len(_serialize(hot))

        # ---- WARM selection ---------------------------------------------
        horizons = ((packet.get("window") or {}).get("scopes") or {})
        candidates: List[tuple] = []
        for key, item, kind, canonical, horizon, base in self.candidates(packet, world_model):
            if kind == "deadline":
                score = 1.0                                   # Cortex's own time-critical state is admitted regardless of the turn
            else:
                score = self._relevance(judgement, key, base)
                if task_intent and kind in ("task", "event"):
                    score = max(score, 0.9)
                if kind == "backstage_attention":
                    score = min(score, 0.6)
            candidates.append((score, item, kind, canonical, horizon))
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

    def candidates(self, packet: Dict[str, Any], world_model: Optional[Dict[str, Any]]) -> List[tuple]:
        """Every item that COULD earn a place: (key, item, kind, canonical, horizon, base). `base` is an eligibility prior only (how near the item is
        in Cortex's own horizons); relevance to the turn comes from the model's judgement."""
        out: List[tuple] = []
        brief = packet.get("window") or {}
        horizons = brief.get("scopes") or {}
        for horizon, base in (("immediate", 0.5), ("today", 0.35), ("upcoming", 0.15)):
            for item in horizons.get(horizon, []):
                kind = str(item.get("kind") or "state")
                out.append((candidate_key(kind, item), item, kind, kind in ("task", "event"), horizon, base))
        for item in (packet.get("sophie_attention") or [])[:8]:
            out.append((candidate_key("backstage_attention", item), item, "backstage_attention", False, "backstage", 0.0))
        for item in horizons.get("unresolved", [])[:8]:
            out.append((candidate_key("unresolved", item), item, "unresolved", False, "unresolved", 0.0))
        for item in packet.get("open_loops", [])[:5]:
            out.append((candidate_key("open_loop", item), item, "open_loop", False, "open_loops", 0.3))
        for item in packet.get("hard_deadlines", [])[:3]:
            if item.get("temporal_state") in ("deadline_passed", "deadline_approaching"):
                out.append((candidate_key("deadline", item), item, "deadline", True, "deadlines", 1.0))
        for m in ((world_model or {}).get("matters") or {}).get("active", [])[:12]:
            item = {"title": m.get("title"), "id": m.get("id"), "matter_id": m.get("id"), "people": m.get("people"),
                    "why_relevant_now": "an alive matter this turn touches", "status": m.get("status"), "confidence": 0.8,
                    "depth": f"projection matter({m.get('id')})"}
            out.append((candidate_key("matter", item), item, "matter", False, "matters", 0.0))
        for g in (((world_model or {}).get("coverage") or {}).get("gaps") or [])[:10]:
            if g.get("status") in ("unknown", "partial", "conflicting"):
                item = {"title": f"not yet known: {g.get('subject_key')}", "id": g.get("subject_key"),
                        "why_relevant_now": g.get("why_useful") or "a useful gap this turn touches", "status": g.get("status"), "confidence": 0.5,
                        "depth": "projection knowledge_gaps()"}
                out.append((candidate_key("knowledge_gap", item), item, "knowledge_gap", False, "gaps", 0.0))
        return out

    async def judge(self, packet: Dict[str, Any], world_model: Optional[Dict[str, Any]], *, turn_text: str, adapter: Any,
                    recent: Optional[List[Dict[str, str]]] = None) -> Optional[Judgement]:
        """ONE cheap model call: how relevant is each candidate to this turn, and which time span (if any) does the user refer to? Returns None when
        no model is available or it fails: the caller then packs by Cortex's own horizons only (never by word overlap)."""
        if adapter is None or not (turn_text or "").strip():
            return None
        cands = [(k, it, kind) for k, it, kind, _c, _h, _b in self.candidates(packet, world_model) if kind != "deadline"]
        if not cands:
            return Judgement()
        listing = [{"key": k, "kind": kind, "text": " ".join(_item_text(it).split())[:200] or str(it.get("title") or "")[:200]} for k, it, kind in cands]
        system = ("You pick what a companion needs from stored state to answer the user's latest message. For EACH item give relevance 0..1: 1 = the "
                  "message is about it or the reply needs it; 0 = unrelated (a change of subject makes earlier-domain items 0). Meaning, not word overlap: "
                  "'Ashley rang' makes the Ashley matter relevant even if the words differ, in any language. Also say which time span the user refers to, if "
                  "any: none | today | this_morning | this_afternoon | yesterday | recent_days | this_week. Echo each key exactly. Never invent keys.")
        prompt = ("RECENT:\n" + "\n".join(f"{t.get('role')}: {str(t.get('content'))[:240]}" for t in (recent or [])[-3:]) + "\n\n" if recent else "") + \
            f"USER MESSAGE: {turn_text[:600]}\n\nITEMS:\n{json.dumps(listing, ensure_ascii=False)}"
        try:
            raw = await adapter.generate_structured(
                system=system, prompt=prompt, model_id=WORKING_SET_MODEL, max_tokens=1500, temperature=0.0, strict=True, timeout=8.0,
                json_schema={"type": "object", "properties": {
                    "items": {"type": "array", "items": {"type": "object", "properties": {"key": {"type": "string"}, "relevance": {"type": "number"}},
                                                         "required": ["key", "relevance"]}},
                    "time_reference": {"type": "string"}}, "required": ["items"], "additionalProperties": False})
        except Exception as exc:
            logger.warning("working-set judgement failed open: %s", exc)
            return None
        if not isinstance(raw, dict):
            return None
        known = {k for k, _it, _kind in cands}
        scores: Dict[str, float] = {}
        for row in raw.get("items") or []:
            try:
                if isinstance(row, dict) and row.get("key") in known:
                    scores[row["key"]] = max(0.0, min(1.0, float(row.get("relevance"))))
            except (TypeError, ValueError):
                continue
        ref = str(raw.get("time_reference") or "none").strip().lower()
        return Judgement(scores=scores, time_reference=ref if ref in TIME_REFERENCES else "none")

    @staticmethod
    def _relevance(judgement: Optional[Judgement], key: str, base: float) -> float:
        """Combine Cortex's eligibility prior with the model's relevance. With no judgement (model unavailable) only items Cortex itself places in the
        immediate horizons are admitted, at reduced weight; nothing is admitted by guessing at words."""
        if judgement is None:
            return base * 0.5 if base >= 0.3 else 0.0
        r = judgement.scores.get(key)
        if r is None or r < RELEVANCE_FLOOR:
            return 0.0
        return min(1.0, base + 0.4 + 0.5 * r)
