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
            now_items.append({"kind": str(item.get("kind") or "state"), "item": item})

    seen_titles: set = set()
    now_lines: List[str] = []

    def _window_hint(item: Dict[str, Any]) -> str:
        label = str(item.get("expected_window_label") or "").strip()
        return f" (window: {label})" if label and label.lower() not in ("none", "unknown") else ""

    for entry in sorted(now_items, key=lambda e: profile.priority(e["kind"])):
        item = entry["item"]
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
        if evidence.lower().startswith("deterministic"):
            evidence = ""
        suffix = f" — {evidence[:110]}" if evidence else (f" [{state}]" if state else "")
        changed_lines.append(line[:120] + suffix)
        if len(changed_lines) >= limits["changed"]:
            break

    # --- UNCERTAIN: elapsed windows without outcome evidence. Absence of
    # evidence is NOT a missed obligation and NOT a failure. ---
    uncertain_lines: List[str] = []
    for item in (packet.get("window_elapsed_unknown") or [])[: limits["unresolved"]]:
        line = _line(item, "title", "summary")
        if line:
            uncertain_lines.append(f"no outcome evidence yet: {line}")

    # --- NO LONGER ACTIVE: superseded/resolved fragments that must not be
    # reconstructed as current reality ---
    no_longer_lines: List[str] = []
    for item in (horizons.get("review_needed") or [])[: limits["changed"]]:
        line = _line(item, "title", "what", "summary")
        if line:
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

    # --- ATTENTION: grounded things Sophie may still carry ---
    attention_lines: List[str] = []
    for item in (brief.get("backstage_attention") or [])[: limits["attention"]]:
        line = _line(item, "content", "title", "what")
        if line:
            attention_lines.append(line)

    handover: Dict[str, Any] = {
        "version": "handover-v2",
        "product": profile.name,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "now": now_lines,
        "changed": changed_lines,
        "uncertain": uncertain_lines,
        "no_longer_active": no_longer_lines,
        "avoid": avoid_lines,
        "attention": attention_lines,
        "constraints": {
            "unknown_is_not_failed": True,
            "absence_of_evidence_is_not_missed_obligation": True,
            "counterfactual_is_not_completion": True,
        },
    }

    # Character budget: trim lowest-priority sections first (attention,
    # no_longer_active, uncertain, changed) so `now` always survives intact.
    import json as _json
    total = len(_json.dumps(handover))
    budget = profile.handover_char_budget
    for section in ("attention", "no_longer_active", "uncertain", "changed", "avoid"):
        while total > budget and handover[section]:
            handover[section].pop()
            total = len(_json.dumps(handover))
    handover["metrics"] = {
        "chars": total,
        "estimated_tokens": int(total / 4),
        "within_budget": total <= budget,
    }
    return handover
