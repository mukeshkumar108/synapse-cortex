"""Pressure dynamics: when an unresolved matter deserves attention again.

Static category pressure (overdue 0.85, reminder_due 0.7, approaching 0.6,
gaps 0.25, intentions 0.2, ...) answers "how important is this kind of
thing". This module answers the temporal question: given age, surfacing
history and fresh evidence, how strongly should it compete RIGHT NOW.

Rules (deterministic, explainable, fail-open — missing fields skip that
adjustment, never zero the item):

- DUE BYPASS: pressure >= 0.6 is contractual (overdue, open reminder
  windows, approaching deadlines). Untouched. Exactly-once firing and
  quiet-hours remain hard gates elsewhere.
- AGE GROWTH (organic only, pressure < 0.6): +0.04 per 12h of age, capped
  at +0.20. A waiting thread on day 3 outranks the same thread on day 1,
  but never outranks contractual items. Needs age_hours or created_at.
- SURFACING FATIGUE: shown recently => compete weaker now.
  last surfaced <24h ago => x0.5; <72h ago => x0.75. ask/surface count
  >= 3 => cap at 0.35. Needs surfaced_count/ask_count/last_surfaced_at.
- NEW-EVIDENCE BOOST: matter updated since it was last surfaced
  (updated_at > last surfaced marker) => fatigue is skipped. New
  information re-opens attention; repetition does not.
- Suppression, deferral (unmet reopen conditions), cooldowns and
  max-counts are hard gates owned elsewhere and dominate unconditionally;
  this module never raises a suppressed/deferred item.

Distinctions honored: unresolved != surface-now (growth is slow and
capped); surfaced != resolved (fatigue decays, eligibility survives);
ignored != resolved (no receipt effect here — ignored only advances
cooldowns upstream); explicit due-time != organic follow-up (bypass vs
dynamics); suppression/deferral always wins.

Every adjustment appends a short human-readable reason to the candidate's
`why` so the foreground (and evaluators) can see the mechanism, and
correction stays possible via receipts/suppressions rather than retuning.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

GROWTH_PER_12H = 0.04
GROWTH_CAP = 0.20
DUE_BYPASS_PRESSURE = 0.6
FATIGUE_24H_FACTOR = 0.5
FATIGUE_72H_FACTOR = 0.75
FATIGUE_WINDOW_HOURS = 72.0
RECENT_WINDOW_HOURS = 24.0
ASK_CAP_COUNT = 3
ASK_CAP_PRESSURE = 0.35
# Contractual lanes own their own ask/pressure logic (occurrences, tasks,
# deadlines) and are never touched here. Everything else is eligible for
# dynamics unless terminally resolved.
CONTRACTUAL_TYPES = {"objective", "recurring_action", "commitment", "deadline"}
TERMINAL_STATUSES = {"resolved", "confirmed", "fulfilled", "cancelled"}


def _naive(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
        except ValueError:
            return None
    if isinstance(value, (int, float)):
        return None
    return None


def _age_hours(item: Dict[str, Any], now: datetime) -> Optional[float]:
    raw = item.get("age_hours")
    try:
        if raw is not None:
            return max(0.0, float(raw))
    except (TypeError, ValueError):
        pass
    created = _naive(item.get("created_at"))
    if created is not None:
        return max(0.0, (now - created).total_seconds() / 3600.0)
    return None


def _last_surfaced(item: Dict[str, Any]) -> Optional[datetime]:
    for key in ("last_surfaced_at", "asked_at", "last_asked_at"):
        parsed = _naive(item.get(key))
        if parsed is not None:
            return parsed
    return None


def _surface_count(item: Dict[str, Any]) -> int:
    for key in ("surfaced_count", "ask_count", "surface_count"):
        try:
            if item.get(key) is not None:
                return max(0, int(item.get(key)))
        except (TypeError, ValueError):
            continue
    return 0


def _updated(item: Dict[str, Any]) -> Optional[datetime]:
    for key in ("updated_at", "candidate_version", "last_evidence_at"):
        parsed = _naive(item.get(key))
        if parsed is not None:
            return parsed
    return None


def adjust_candidate(candidate: Dict[str, Any], *, now: datetime) -> Dict[str, Any]:
    """Apply dynamics to one agenda candidate in place (copy). Pure."""
    item = dict(candidate)
    try:
        base = float(item.get("pressure") or 0.0)
    except (TypeError, ValueError):
        return item
    if base >= DUE_BYPASS_PRESSURE:
        return item  # contractual: untouched
    if str(item.get("semantic_type") or "") in CONTRACTUAL_TYPES:
        return item  # contractual lane with its own ask logic: untouched
    if str(item.get("status") or "") in TERMINAL_STATUSES:
        return item  # resolved things decay elsewhere, never grow here
    reasons: List[str] = []
    pressure = base

    age = _age_hours(item, now)
    if age is not None and age > 0:
        growth = min(GROWTH_CAP, (age / 12.0) * GROWTH_PER_12H)
        if growth > 0:
            pressure += growth
            reasons.append(f"unresolved {age:.0f}h (+{growth:.2f})")

    last = _last_surfaced(item)
    count = _surface_count(item)
    updated = _updated(item)
    if last is not None and (updated is None or updated <= last):
        # No fresh evidence since last shown: fatigue applies.
        gap_hours = (now - last).total_seconds() / 3600.0
        if gap_hours < 0:
            pass
        elif gap_hours < RECENT_WINDOW_HOURS:
            pressure *= FATIGUE_24H_FACTOR
            reasons.append("shown <24h ago (x0.5)")
        elif gap_hours < FATIGUE_WINDOW_HOURS:
            pressure *= FATIGUE_72H_FACTOR
            reasons.append("shown <72h ago (x0.75)")
    elif last is not None and updated is not None and updated > last:
        reasons.append("new evidence since shown (no fatigue)")
    if count >= ASK_CAP_COUNT and pressure > ASK_CAP_PRESSURE:
        pressure = ASK_CAP_PRESSURE
        reasons.append(f"asked {count}x without resolution (capped)")

    pressure = max(0.0, min(1.0, round(pressure, 3)))
    item["pressure"] = pressure
    if reasons:
        prior = str(item.get("why") or "")
        item["why"] = (prior + " | " + "; ".join(reasons)).strip(" |")[:220]
    return item


def apply_pressure_dynamics(candidates: List[Dict[str, Any]], *,
                            now: datetime) -> List[Dict[str, Any]]:
    """Map adjust_candidate over agenda candidates. Pure, fail-open per item."""
    out = []
    for cand in candidates or []:
        try:
            out.append(adjust_candidate(cand, now=now))
        except Exception:
            out.append(cand)
    return out
