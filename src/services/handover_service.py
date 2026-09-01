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
    agenda: Optional[List[Dict[str, Any]]] = None,
    admission: Optional[Dict[str, Any]] = None,
    compiled_by: str = "fallback",
) -> Dict[str, Any]:
    """Handover v4: ONE live agenda is the center of behavioral attention.
    The fragmented section pile (now/changed/uncertain/...) is retired; the
    ranked agenda, patterns (context-only), avoid list and scene are all that
    remains. Everything upstream exists to build and maintain the agenda."""
    profile = get_profile(product)
    brief = packet.get("intelligence_brief") or {}
    daypart = str(brief.get("daypart") or "").lower()

    # --- OWED (admitted) + SCENE: foreground admission control output ---
    admission = admission or {}
    owed_items: List[Dict[str, Any]] = []
    for item in (admission.get("owed") or [])[: profile.handover_limits.get("agenda", 3)]:
        owed_items.append({
            "what": str(item.get("what") or "")[:90],
            "occurrence_id": item.get("occurrence_id"),
            "followup_state": item.get("followup_state", "outstanding"),
            "next_move": str(item.get("next_move") or "")[:110],
        })
    scene_block = admission.get("scene") or {}
    agenda_items_unused: List[Dict[str, Any]] = []
    for item in (agenda or [])[:0]:
        what = str(item.get("what") or "").strip()
        if not what:
            continue
        pressure = float(item.get("pressure") or 0.0)
        entry: Dict[str, Any] = {
            "what": what,
            "owner": str(item.get("owner") or "user"),
            "status": str(item.get("status") or "unresolved"),
            "pressure": "high" if pressure >= 0.6 else ("medium" if pressure >= 0.35 else "low"),
        }
        if item.get("next_move"):
            entry["next_move"] = str(item["next_move"])[:120]
        agenda_items.append(entry)

    # --- PATTERNS: context, never actionable ---
    pattern_lines: List[str] = []
    for item in (packet.get("recurring_intentions") or []):
        if str(item.get("semantic_type")) == "observed_pattern" and item.get("occurrence_status") == "pending":
            line = _line(item, "title")
            if line and line.lower() not in {p.lower() for p in pattern_lines}:
                pattern_lines.append(f"{line} (observed pattern - context, not a commitment)")

    # --- AVOID: active suppressions ---
    avoid_lines: List[str] = []
    for item in (packet.get("suppressed_targets") or []):
        line = _line(item, "topic_or_entity")
        if not line or _looks_like_id(line):
            continue
        avoid_lines.append(line)
        if len(avoid_lines) >= profile.handover_limits["avoid"]:
            break

    handover: Dict[str, Any] = {
        "version": "handover-v4",
        "product": profile.name,
        "generated_at": (now or datetime.now(timezone.utc)).isoformat(),
        "scene": {
            "time_of_day": daypart or "unknown",
            **{k: v for k, v in scene_block.items() if v not in (None, "")},
        },
        "owed": owed_items,
        "optional_count": len(admission.get("optional") or []),
        "patterns": pattern_lines,
        "avoid": avoid_lines,
        "constraints": {
            "unknown_is_not_failed": True,
            "absence_of_evidence_is_not_missed_obligation": True,
            "user_statements_override_context": True,
        },
    }

    import json as _json
    total = len(_json.dumps(handover))
    budget = profile.handover_char_budget
    while total > budget and handover["patterns"]:
        handover["patterns"].pop()
        total = len(_json.dumps(handover))
    while total > budget and len(handover["owed"]) > 1:
        handover["owed"].pop()
        total = len(_json.dumps(handover))
    handover["metrics"] = {
        "chars": total,
        "estimated_tokens": int(total / 4),
        "within_budget": total <= budget,
        "compiled_by": compiled_by,
    }
    return handover
