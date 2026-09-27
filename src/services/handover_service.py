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
    current_turn: str = "",
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
        _occ = item.get("occurrence_id")
        _cid = item.get("candidate_id")
        if _cid is None and _occ:
            _cid = f"recurring_occurrence:{_occ}"
        owed_items.append({
            "what": str(item.get("what") or "")[:90],
            "occurrence_id": _occ,
            "candidate_id": _cid,
            "candidate_version": item.get("candidate_version"),
            "pressure": item.get("pressure"),
            "followup_state": item.get("followup_state", "outstanding"),
            "next_move": str(item.get("next_move") or "")[:110],
        })
    scene_block = admission.get("scene") or {}
    # handover-v4: the legacy agenda section was retired; owed (above) is the
    # single surfaced surface. No dead agenda-items block here.

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

    available = []
    # Optional matters never become owed work. The foreground's incoming request
    # and intent policy decide whether this single grounded opportunity is useful.
    # Selection follows the RANKED admission optional list (agenda order with
    # pressure dynamics applied) — not raw packet order — so the offered
    # candidate reflects the attention system's actual judgement, with its
    # why/pressure/next_move intact. IDs and evidence resolve back to packet
    # rows so delivery receipts keep working; unmatched items fall back to
    # the legacy first-eligible packet row.
    _packet_by_id: Dict[str, Dict[str, Any]] = {}
    for _section in ("open_loops", "sophie_attention", "active_expectations",
                     "window_elapsed_unknown", "waiting_on", "commitments",
                     "events", "recent_resolutions"):
        for _row in (packet.get(_section) or []):
            if isinstance(_row, dict) and _row.get("id"):
                _packet_by_id.setdefault(str(_row["id"]), _row)
    _TERMINAL_OPTIONAL = {"resolved", "confirmed", "scheduled_for_later",
                          "suppressed_until_event", "fulfilled", "cancelled"}
    for item in (admission.get("optional") or []):
        if not isinstance(item, dict):
            continue
        if str(item.get("followup_state") or "") in _TERMINAL_OPTIONAL:
            continue
        content = str(item.get("what") or "").strip()
        if not content or content.lower() == "open loop":
            continue
        if any(content.lower() == str(x.get("what", "")).lower() for x in owed_items):
            continue
        _key = str(item.get("item_key") or "")
        _pid = _key.split(":", 1)[1] if ":" in _key else ""
        _row = _packet_by_id.get(_pid, {})
        available.append({
            "what": content,
            "authority": "optional_not_obligation",
            "pressure": item.get("pressure"),
            "why": str(item.get("why") or "")[:140] or None,
            "next_move": str(item.get("next_move") or "")[:110] or None,
            "candidate_id": _row.get("candidate_id") or item.get("candidate_id"),
            "candidate_version": _row.get("candidate_version") or item.get("candidate_version"),
            "evidence_refs": _row.get("evidence_refs") or (
                [_row.get("honcho_message_id")] if _row.get("honcho_message_id") else None
            ) or item.get("evidence_refs") or (
                [item.get("honcho_message_id")] if item.get("honcho_message_id") else []),
        })
        break
    if not available:
        for item in list(packet.get("sophie_attention") or []) + list(packet.get("open_loops") or []):
            content = _line(item, "content", "title", "summary")
            if str(item.get("title") or "").lower() == "open loop":
                content = _line(item, "summary", "content", "title")
            if content and not any(content.lower() == str(x.get("what", "")).lower() for x in owed_items):
                available.append({"what": content, "authority": "optional_not_obligation",
                    "candidate_id": item.get("candidate_id"), "candidate_version": item.get("candidate_version"),
                    "evidence_refs": item.get("evidence_refs") or [item.get("honcho_message_id")]})
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
        "available": available,
        "clarifications": list(packet.get("clarifications") or [])[:1],
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
