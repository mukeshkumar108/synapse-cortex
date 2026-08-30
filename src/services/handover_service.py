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

    # --- NOW: foreground-worthy canonical/recent items, priority-ordered ---
    now_items: List[Dict[str, Any]] = []
    for item in packet.get("hard_deadlines", []):
        now_items.append({"kind": "deadline", "item": item})
    for item in packet.get("active_expectations", []):
        now_items.append({"kind": "task", "item": item})
    for horizon in ("now", "today"):
        for item in horizons.get(horizon, []):
            now_items.append({"kind": str(item.get("kind") or "state"), "item": item})

    seen_titles: set = set()
    now_lines: List[str] = []
    for entry in sorted(now_items, key=lambda e: profile.priority(e["kind"])):
        line = _line(entry["item"], "title", "what", "summary")
        if not line or line.lower() in seen_titles:
            continue
        seen_titles.add(line.lower())
        now_lines.append(line)
        if len(now_lines) >= limits["now"]:
            break

    # --- CHANGED: recent resolutions / cancellations ---
    changed_lines: List[str] = []
    for item in (packet.get("recent_resolutions") or [])[: limits["changed"]]:
        line = _line(item, "title", "summary", "target_text")
        if line:
            changed_lines.append(line)

    # --- UNRESOLVED: unknown-outcome items, explicitly not failures ---
    unresolved_lines: List[str] = []
    for item in (horizons.get("unresolved") or [])[: limits["unresolved"]]:
        line = _line(item, "title", "what", "summary")
        if line:
            unresolved_lines.append(line)

    # --- AVOID: active suppressions (do not callback / do not frame) ---
    avoid_lines: List[str] = []
    for item in (packet.get("suppressed_targets") or [])[: limits["avoid"]]:
        line = _line(item, "topic_or_entity")
        if line:
            avoid_lines.append(line)

    # --- ATTENTION: grounded things Sophie may still carry ---
    attention_lines: List[str] = []
    for item in (brief.get("backstage_attention") or [])[: limits["attention"]]:
        line = _line(item, "content", "title", "what")
        if line:
            attention_lines.append(line)

    handover: Dict[str, Any] = {
        "version": "handover-v1",
        "product": profile.name,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "now": now_lines,
        "changed": changed_lines,
        "unresolved": unresolved_lines,
        "avoid": avoid_lines,
        "attention": attention_lines,
        "constraints": {
            "unknown_is_not_failed": True,
            "absence_of_evidence_is_not_missed_obligation": True,
        },
    }

    # Character budget: trim lowest-priority sections first (attention,
    # unresolved, changed) so `now` always survives intact.
    import json as _json
    total = len(_json.dumps(handover))
    budget = profile.handover_char_budget
    for section in ("attention", "unresolved", "changed", "avoid"):
        while total > budget and handover[section]:
            handover[section].pop()
            total = len(_json.dumps(handover))
    handover["metrics"] = {
        "chars": total,
        "estimated_tokens": int(total / 4),
        "within_budget": total <= budget,
    }
    return handover
