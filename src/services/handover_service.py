"""Tiny session handover (Workstream 8).

A ~200-400 token, product-edited editorial object that can replace most
synchronous turn-level Cortex reasoning in the foreground. This is NOT a raw
packet dump and NOT another memory store: Honcho stays durable evidence,
Cortex rows stay canonical state, and the handover is a replaceable derived
projection compiled fresh from the same attention packet used by the working
set. One compact foreground object, not six new packet endpoints.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from src.services.product_profile import ProductProfile, get_profile


def _line(item: Dict[str, Any], *keys: str, cap: int = 140) -> Optional[str]:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value[:cap]
    return None


import re as _re

_ID_LIKE = _re.compile(r"^[0-9a-fA-F-]{8,}$|^[a-z]+_[0-9a-fA-F-]{16,}$")


def _looks_like_id(value: str) -> bool:
    return bool(_ID_LIKE.match(value.strip()))


def compile_handover(
    packet: Dict[str, Any],
    *,
    product: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    profile: ProductProfile = get_profile(product)
    limits = profile.handover_limits
    brief = packet.get("intelligence_brief") or {}
    horizons = brief.get("horizons") or {}

    # Epistemic discipline: plans whose window elapsed WITHOUT outcome
    # evidence are UNKNOWN, never failures, and must not pose as current
    # reality in `now`. They surface once, honestly, under `uncertain`.
    stale_ids = {
        str(item.get("id"))
        for item in (packet.get("window_elapsed_unknown") or [])
    }

    # --- NOW: foreground-worthy canonical/recent items, priority-ordered ---
    now_items: List[Dict[str, Any]] = []
    pattern_lines: List[str] = []
    for item in packet.get("hard_deadlines", []):
        now_items.append({"kind": "deadline", "item": item})
    for item in packet.get("active_expectations", []):
        if str(item.get("id")) in stale_ids:
            continue
        now_items.append({"kind": "task", "item": item})
    for item in packet.get("source_expectations", []):
        now_items.append({"kind": "task", "item": item})
    for horizon in ("now", "today"):
        for item in horizons.get(horizon, []):
            if str(item.get("id")) in stale_ids:
                continue
            kind = str(item.get("kind") or "state")
            if kind == "recurring_intention" and str(
                item.get("semantic_type") or ""
            ) == "observed_pattern":
                # Observed patterns are context, never actionable attention:
                # they were deliberately excluded from Task projection and
                # must not be operationalized as commitments here either.
                line = _line(item, "title", "what", "summary")
                if line and line.lower() not in {p.lower() for p in pattern_lines}:
                    pattern_lines.append(f"{line} (observed pattern — context, not a commitment)")
                continue
            now_items.append({"kind": kind, "item": item})

    seen_titles: set = set()
    now_lines: List[str] = []

    def _window_hint(item: Dict[str, Any]) -> str:
        label = str(item.get("expected_window_label") or "").strip()
        return f" (window: {label})" if label and label.lower() not in ("none", "unknown") else ""

    # Freshness: a near-term plan extracted days ago whose window still says
    # "in about 5 mins" is stale narration, not current reality. Anything
    # older than 30h leaves `now` (it remains reachable via JIT/working set).
    MAX_NOW_AGE_HOURS = 30.0

    def _is_stale(item: Dict[str, Any]) -> bool:
        try:
            age = float(item.get("age_hours"))
        except (TypeError, ValueError):
            return False
        return age > MAX_NOW_AGE_HOURS

    for entry in sorted(now_items, key=lambda e: profile.priority(e["kind"])):
        item = entry["item"]
        if _is_stale(item):
            continue
        line = _line(item, "title", "what", "summary")
        if not line or line.lower() in seen_titles:
            continue
        seen_titles.add(line.lower())
        state = str(item.get("outcome_state") or "").strip()
        if state and state.lower() != "unknown":
            line = f"{line} [{state.lower()}]"
        now_lines.append(line + _window_hint(item))
        if len(now_lines) >= limits["now"]:
            break

    # --- CHANGED: recent resolutions, with causal grounding where the
    # evidence supports it (never invented) ---
    changed_lines: List[str] = []
    for item in (packet.get("recent_resolutions") or [])[: limits["changed"] + 3]:
        line = _line(item, "title", "summary", "target_text")
        if not line:
            continue
        state = str(item.get("outcome_state") or "").strip().lower()
        evidence = str(item.get("evidence") or "").strip()
        if (
            evidence.lower().startswith("deterministic")
            or "honcho_message:" in evidence
            or "#candidate:" in evidence
            or "candidate_key" in evidence.lower()
        ):
            # Internal provenance reference, not human-readable cause.
            evidence = ""
        suffix = f" — {evidence[:110]}" if evidence else (f" [{state}]" if state else "")
        changed_lines.append(line[:120] + suffix)
        if len(changed_lines) >= limits["changed"]:
            break

    # --- UNCERTAIN: elapsed windows without outcome evidence. Absence of
    # evidence is NOT a missed obligation and NOT a failure. ---
    uncertain_lines: List[str] = []
    uncertain_titles: set = set()
    for item in (packet.get("window_elapsed_unknown") or []):
        # Days-old unknowns are noise here; review_needed carries them.
        try:
            if float(item.get("age_hours") or 0) > 48.0:
                continue
        except (TypeError, ValueError):
            pass
        if len(uncertain_lines) >= limits["unresolved"]:
            break
        line = _line(item, "title", "summary")
        if line:
            uncertain_lines.append(f"no outcome evidence yet: {line}")
            for key in ("title", "summary"):
                value = str(item.get(key) or "").strip().lower()
                if value:
                    uncertain_titles.add(value)

    # --- NO LONGER ACTIVE: superseded/resolved fragments that must not be
    # reconstructed as current reality (deduped against uncertain) ---
    no_longer_lines: List[str] = []
    for item in (horizons.get("review_needed") or [])[: limits["changed"]]:
        line = _line(item, "title", "what", "summary")
        if line and line.lower() not in uncertain_titles:
            no_longer_lines.append(line)

    # --- AVOID: active suppressions (do not callback / do not frame).
    # Entity rows store opaque ids in topic_or_entity; suppressions without a
    # human-readable topic are not surfacable language. ---
    avoid_lines: List[str] = []
    for item in (packet.get("suppressed_targets") or [])[: limits["avoid"] + 3]:
        line = _line(item, "topic_or_entity")
        if not line or _looks_like_id(line):
            continue
        avoid_lines.append(line)
        if len(avoid_lines) >= limits["avoid"]:
            break

    # --- CURRENT WINDOW: deterministic daypart/objective projection.
    # Code owns time, status and window pressure; the model owns judgment.
    # Window failure is NOT objective failure: a pending daily objective at
    # night is still alive, with pressure, needing an adaptive strategy. ---
    daypart = str(brief.get("daypart") or "").lower()
    local_time_label = " ".join(
        part for part in (str(brief.get("user_day") or ""), daypart) if part
    ) or "unknown"
    current_window: Dict[str, Any] = {
        "local_time": local_time_label,
        "objectives": [],
        "sophie_intentions": [],
    }
    for item in (packet.get("recurring_intentions") or []):
        if item.get("occurrence_status") != "pending":
            continue
        stype = str(item.get("semantic_type") or "recurring_action")
        if stype == "observed_pattern":
            continue  # context only, never operational pressure
        entry: Dict[str, Any] = {
            "what": str(item.get("title") or "")[:80],
            "semantic_type": stype,
            "state": "unconfirmed_today",
        }
        preferred = str(item.get("preferred_window") or "").strip()
        window_passed = bool(
            preferred and daypart and preferred.lower() not in ("any", "none")
            and preferred.lower() not in daypart.lower()
        )
        if window_passed:
            entry["window_pressure"] = (
                f"preferred window '{preferred}' has passed; objective still alive - "
                "plan failed, objective persists; consider an adapted strategy"
            )
        elif daypart in ("evening", "night"):
            entry["window_pressure"] = (
                "day is ending; objective still alive - consider shortened or "
                "alternative strategy rather than dropping it"
            )
        target = item.get("target_amount")
        if target is not None and item.get("target_unit"):
            entry["target"] = f"{target} {item['target_unit']}"
        # Deterministic follow-up duty (accountability partner contract):
        # an unconfirmed actionable objective with window pressure, not yet
        # asked about today (max 2 asks/day), SHOULD be asked about this
        # turn. Code owns whether; the model owns phrasing and timing.
        if (window_passed or daypart in ("evening", "night")) and int(item.get("ask_count") or 0) < 2:
            entry["ask_now"] = True
            entry["occurrence_id"] = item.get("occurrence_id")
        current_window["objectives"].append(entry)
        if len(current_window["objectives"]) >= 3:
            break
    # Sophie-owned intentions reuse the grounded attention-candidate surface
    # (background cognition creates follow-ups/questions there).
    for item in (brief.get("backstage_attention") or []):
        line = _line(item, "content", "title", "what", cap=110)
        if line:
            current_window["sophie_intentions"].append(line)
        if len(current_window["sophie_intentions"]) >= 2:
            break

    handover: Dict[str, Any] = {
        "version": "handover-v3",
        "product": profile.name,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "now": now_lines,
        "patterns": pattern_lines,
        "current_window": current_window,
        "changed": changed_lines,
        "uncertain": uncertain_lines,
        "no_longer_active": no_longer_lines,
        "avoid": avoid_lines,
        "constraints": {
            "unknown_is_not_failed": True,
            "absence_of_evidence_is_not_missed_obligation": True,
            "counterfactual_is_not_completion": True,
        },
    }

    # Character budget: trim lowest-priority sections first
    # (no_longer_active, uncertain, changed) so `now` + current_window
    # always survive intact.
    import json as _json
    total = len(_json.dumps(handover))
    budget = profile.handover_char_budget
    for section in ("no_longer_active", "uncertain", "changed", "avoid"):
        while total > budget and handover[section]:
            handover[section].pop()
            total = len(_json.dumps(handover))
    while total > budget and len(handover["current_window"]["sophie_intentions"]) > 1:
        handover["current_window"]["sophie_intentions"].pop()
        total = len(_json.dumps(handover))
    handover["metrics"] = {
        "chars": total,
        "estimated_tokens": int(total / 4),
        "within_budget": total <= budget,
    }
    return handover
