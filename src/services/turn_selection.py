"""Per-turn selection policy: pure, cheap, no IO.

Operates on a cached session/scene working set + turn envelope + local
surfacing state. No Cortex retrieval, no model calls — this is the hot path
Runtime runs locally every turn. Cortex recomputes the working set only on
material change; selection never mutates canonical state.

Contract:
- user-initiated turns: answer first. Proactive items join only on turn
  overlap, protective override, or must-resolve duty. No hijacking.
- proactive/background turns: only must-resolve/priority/opportunistic
  within budget; empty selection (silence) is valid.
- protective items may override restraint (bounded: max 1).
- budgets, arbitration (dominant/combine/hold), repetition avoidance,
  suppressions, and no-response gestures are structural, not vibes.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def _parse_moment(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        moment = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        return None
    return moment.astimezone(timezone.utc).replace(tzinfo=None) if moment.tzinfo else moment


def effective_clock(now: Optional[datetime], scene_time: Optional[str]) -> datetime:
    """Scene-clock override for fictional time: a jump from Monday to Friday
    wakes latent items locally. Temporal eligibility only — never mutates
    the underlying claim."""
    if scene_time:
        parsed = _parse_moment(scene_time)
        if parsed is not None:
            return parsed
    base = now or datetime.now(timezone.utc)
    return base.astimezone(timezone.utc).replace(tzinfo=None) if base.tzinfo else base


def window_gate(item: Dict[str, Any], clock: datetime) -> Optional[str]:
    """Cheap local eligibility over cached metadata. Returns a hold reason or
    None when eligible. Missing/unparseable metadata never gates."""
    not_before = _parse_moment(item.get("not_before"))
    if not_before is not None and clock < not_before:
        return "held:not_yet_due"
    for key in ("expires_at", "expires", "valid_until"):
        expiry = _parse_moment(item.get(key))
        if expiry is not None and clock > expiry:
            return "held:window_passed"
    window = item.get("window")
    if isinstance(window, dict):
        start = _parse_moment(window.get("start") or window.get("from"))
        end = _parse_moment(window.get("end") or window.get("until"))
        if start is not None and clock < start:
            return "held:not_yet_due"
        if end is not None and clock > end:
            return "held:window_passed"
    return None


def _tokens(text: str) -> set:
    from src.services.working_set_service import _tokens as _ws_tokens
    return _ws_tokens(text)


def _item_text(item: Dict[str, Any]) -> str:
    # Title/topic/summary/content/evidence only. Rationale/why strings
    # (owner names, provenance, policy notes) must never drive relevance:
    # otherwise every turn mentioning Elena injects all her undertakings.
    return " ".join(str(item.get(k) or "") for k in ("title", "topic", "summary", "content", "evidence"))


def pressure_of(item: Dict[str, Any]) -> str:
    """Five tiers from machine signals only (never content reading)."""
    signals = item.get("signals") or {}
    kind = str(item.get("kind") or "")
    user_facing = bool(item.get("user_facing", True))
    if signals.get("urgent") and signals.get("actionable") \
            and kind in ("reminder", "commitment", "occurrence"):
        return "must_resolve"
    if signals.get("protective") or (
            signals.get("urgent") and user_facing) \
            or (signals.get("actionable") and kind == "commitment"):
        return "priority"
    if user_facing and item.get("telemetry") == "MOVE_ELIGIBLE":
        return "active"
    if kind in ("callback", "open_loop", "clarification", "followup",
                "attention", "graph") or signals.get("actionable"):
        return "opportunistic"
    return "background"


_PRESSURE_RANK = {"must_resolve": 4, "priority": 3, "active": 2,
                  "opportunistic": 1, "background": 0}


def _suppressed(item: Dict[str, Any],
                suppressions: List[Dict[str, Any]]) -> Optional[str]:
    item_id = str(item.get("id") or "")
    text_tokens = _tokens(_item_text(item))
    for supp in suppressions or []:
        if supp.get("target_id") and str(supp["target_id"]) == item_id:
            return "suppressed:target"
        topic = str(supp.get("topic_or_entity") or "")
        topic_tokens = {t for t in _tokens(topic) if len(t) >= 4}
        if topic_tokens and topic_tokens & text_tokens:
            return "suppressed:topic"
    return None


def select_for_turn(
    working_set: Dict[str, Any],
    *,
    turn_text: str = "",
    initiated_by: str = "user",
    channel: str = "chat",
    local_state: Optional[Dict[str, Any]] = None,
    now: Optional[datetime] = None,
    scene_time: Optional[str] = None,
) -> Dict[str, Any]:
    """Select the minimal foreground bundle. See module docstring."""
    local_state = local_state or {}
    clock = effective_clock(now, scene_time)
    sections = working_set.get("sections", {}) or {}
    budgets = working_set.get("budgets", {}) or {}
    mandatory = set(working_set.get("mandatory_kinds", []) or [])
    suppressions = sections.get("suppressions_deferrals", []) or []

    max_items = int(budgets.get("max_foreground_items", 3) or 3)
    proactive_remaining = budgets.get("proactive_remaining")
    proactive_remaining = (999 if proactive_remaining is None
                           else int(proactive_remaining))

    turn_tokens = _tokens(turn_text or "")
    user_turn = initiated_by == "user" and bool(turn_tokens)
    recent_topics = [str(t).lower() for t in (local_state.get("surfaced_topics") or [])]
    recent_shapes = [str(s) for s in (local_state.get("surfaced_shapes") or [])]

    # Flatten candidate pool with section provenance.
    pool: List[Dict[str, Any]] = []
    for section, view_items in sections.items():
        if not isinstance(view_items, list) or section in (
                "suppressions_deferrals", "scene_anchor"):
            continue
        for item in view_items:
            if not isinstance(item, dict) or not (item.get("title") or item.get("topic")):
                continue
            pool.append({**item, "section": section,
                         "pressure": pressure_of(item)})

    # Combine same-matter duplicates (stable matter identity first, then
    # normalized text): keep the highest-pressure instance, note sections.
    by_matter: Dict[str, Dict[str, Any]] = {}

    def _matter_key(item: Dict[str, Any]) -> str:
        kind = str(item.get("kind") or "")
        mid = str(item.get("id") or "")
        if kind and mid and not mid.startswith("id-"):
            return f"{kind}:{mid}"
        return _item_text(item).lower().strip()
    for item in pool:
        key = _matter_key(item)
        if not key:
            continue
        prev = by_matter.get(key)
        if prev is None or _PRESSURE_RANK[item["pressure"]] > _PRESSURE_RANK[prev["pressure"]]:
            if prev is not None:
                item = {**item, "combined_from": sorted({
                    str(prev.get("section")), str(item.get("section"))})}
            by_matter[key] = item
        elif _PRESSURE_RANK[item["pressure"]] == _PRESSURE_RANK[prev["pressure"]]:
            prev_sections = set(prev.get("combined_from", [str(prev.get("section"))]))
            prev_sections.add(str(item.get("section")))
            prev["combined_from"] = sorted(prev_sections)

    include: List[Dict[str, Any]] = []
    held: List[Dict[str, Any]] = []
    suppressed: List[Dict[str, Any]] = []
    protective_used = 0

    for item in by_matter.values():
        pressure = item["pressure"]
        signals = item.get("signals", {}) or {}
        overlap = bool(turn_tokens & _tokens(_item_text(item)))
        timing = window_gate(item, clock)
        if timing is not None:
            held.append({**item, "hold_reason": timing})
            continue
        # Suppressions restrain companion initiative, never the user's own
        # inquiry: a directly overlapping user turn pierces topic suppression.
        reason = None if (user_turn and overlap) else _suppressed(item, suppressions)
        if reason is not None:
            suppressed.append({**item, "suppress_reason": reason})
            continue
        topic = _item_text(item).lower().strip()
        if topic in recent_topics and pressure not in ("must_resolve", "priority"):
            held.append({**item, "hold_reason": "recently_surfaced"})
            continue

        wants_foreground = False
        why_select = ""
        if pressure == "must_resolve" or item.get("kind") in mandatory:
            wants_foreground, why_select = True, "duty"
        elif user_turn and overlap:
            wants_foreground, why_select = True, "turn_relevant"
        elif user_turn and signals.get("protective") and protective_used < 1:
            wants_foreground, why_select = True, "protective_override"
            protective_used += 1
        elif not user_turn and pressure in ("must_resolve", "priority", "opportunistic"):
            wants_foreground, why_select = True, f"proactive:{pressure}"
        elif not user_turn and pressure == "active":
            wants_foreground, why_select = True, "proactive:active"

        if not wants_foreground:
            held.append({**item, "hold_reason": "no_claim_on_attention"})
            continue
        # Proactive budget: duty + protective override bypass; rest consumes it.
        if not user_turn or (user_turn and not overlap and why_select != "protective_override"):
            if why_select not in ("duty", "protective_override"):
                if proactive_remaining <= 0:
                    held.append({**item, "hold_reason": "proactive_budget_spent"})
                    continue
                proactive_remaining -= 1
        expects_response = item.get("kind") in (
            "followup", "clarification", "open_loop", "question") or str(
            item.get("kind") or "").upper() in ("QUESTION", "FOLLOW_UP")
        include.append({**item, "select_reason": why_select,
                        "expects_response": expects_response})

    # Arbitration: dominant first; cap the bundle; hold the rest.
    include.sort(key=lambda i: (
        -_PRESSURE_RANK.get(i["pressure"], 0),
        i.get("kind") in recent_shapes,
        str(i.get("title") or i.get("topic") or "")))
    foreground, overflow = include[:max_items], include[max_items:]
    for item in overflow:
        held.append({**item, "hold_reason": "arbitrated_out"})

    if user_turn:
        posture = "FOLLOW"
    elif any(i["pressure"] == "must_resolve" for i in foreground):
        posture = "LEAD"
    elif any((i.get("signals", {}) or {}).get("protective") for i in foreground):
        posture = "REPAIR"
    elif foreground:
        posture = "LEAD"
    else:
        posture = "HOLD"

    return {
        "posture": posture,
        "initiated_by": initiated_by,
        "channel": channel,
        "clock": clock.isoformat(),
        "scene_time": scene_time,
        "include": foreground,
        "held": held,
        "suppressed": suppressed,
        "proactive_remaining": proactive_remaining,
        "reasons": {
            "user_first": user_turn,
            "protective_override_used": bool(protective_used),
        },
    }
