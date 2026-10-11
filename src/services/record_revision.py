"""Record-first corrections: a standing-request candidate that corrects an existing open
record revises the record instead of becoming competing prose.

Boundary (deliberate): the input is ALREADY classified — a model (picture pass or
interpreter) proposed these texts as standing requests. This module only sorts them by
record-match and temporal difference, never by phrasing: a dated correction of a matched
open event/expectation revises that record's timing with the request text as evidence and is
NOT stored as prose; everything else (genuine preferences, same-day remarks, unmatchable or
undateable texts) stores exactly as today. Nothing is ever silently dropped: every input is
stored, revised, or reported already-current.

No intent classification happens here (that ban stands): matching is token overlap with
refusal bias, dates are explicit weekday/clock mentions (EN+ES), and ambiguous matches
stay prose. Timezone-naive UTC datetimes throughout (repo convention); callers pass the
owner's IANA timezone so weekday resolution lands on the right day.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from zoneinfo import ZoneInfo

from src.models.expectation import Expectation, OutcomeState
from src.models.world import WorldEvent

MATCH_THRESHOLD = 0.5

# NOTE: there is deliberately no preference-phrasing classifier here. An earlier draft
# routed "Don't ..."/"Do not ..." straight to prose storage, which misroutes exactly the
# flagship case ("Do not describe the delivery as today; it is Friday 08:00"). Routing is
# by record-match + temporal difference only: a dated correction of a matched record revises
# it however it is phrased; a same-day or undateable match stores as prose (a behavioral
# instruction on current state); unmatched texts store as today. Phrasing never decides.

WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    "lunes": 0, "martes": 1, "miercoles": 2, "miércoles": 2, "jueves": 3, "viernes": 4, "sabado": 5, "sábado": 5, "domingo": 6,
}
CLOCK = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*(am|pm)\b", re.IGNORECASE)
CLOCK_24 = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
# Spanish clock without am/pm ("a las 8", "las 8 de la tarde"): only beside a weekday.
CLOCK_ES = re.compile(r"\b(?:a\s+)?las\s+(\d{1,2})(?:\s+de\s+la\s+(ma[nñ]ana|tarde|noche))?", re.IGNORECASE)


def _overlap(a: str, b: str) -> float:
    ta, tb = set(re.findall(r"[a-z0-9£$]+", str(a or "").lower())), set(re.findall(r"[a-z0-9£$]+", str(b or "").lower()))
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


# Content words, lightly stemmed (first five letters: blocked/blocking and Marco's/Marco
# meet — same lineage as the Runtime's anchor matcher). Union overlap punishes verbose
# prose, so record matching below uses RECALL (how much of the record's terms the text
# holds) instead: a long correction naming the record scores high, chitchat scores low.
_STOP = set("""a about after again all also am an and any are as at be because been before being but by can could did do does doing done for from had has have he her here hers him his how i if in into is it its just
me my no not of off on once only or our out over she so some than that the their them then there these they this those to too up us was we were what when where which while who why will with would you your youre
dont didnt isnt wasnt cant wont like really very much got get said say says tell told yeah yes okay ok oh well now still even ever never going gonna""".split())


def _stems(text: str) -> set:
    return {w[:5] for w in re.findall(r"[a-z0-9£$]+", str(text or "").lower().replace("'s", "")) if len(w) >= 3 and w not in _STOP}


def _tokens(text: str) -> List[str]:
    return re.findall(r"[a-z0-9£$]+", str(text or "").lower())


def match_record(text: str, events: List[Any], expectations: List[Any]) -> Optional[Tuple[str, UUID, str, float]]:
    """Best open record this correction is about, or None. Recall-oriented: the fraction of
    the RECORD's content terms present in the text (a verbose correction still scores high).
    Strictly-best-only with a 0.5 floor — ties and weak matches refuse into prose. A short
    title matching passing chatter is harmless: revision additionally requires an explicit
    temporal mention, and same-day holdings stay prose."""
    tw = _stems(text)
    scored = []
    for ev in events or []:
        label = str(getattr(ev, "label", "") or "")
        rw = _stems(label)
        if rw:
            scored.append((len(tw & rw) / len(rw), ("event", ev.id, label)))
    for ex in expectations or []:
        title = str(getattr(ex, "title", "") or "")
        rw = _stems(title)
        if rw:
            scored.append((len(tw & rw) / len(rw), ("expectation", ex.id, title)))
    scored.sort(key=lambda t: -t[0])
    if not scored or scored[0][0] < MATCH_THRESHOLD:
        return None
    if len(scored) > 1 and scored[1][0] >= scored[0][0]:
        return None
    return scored[0][1] + (scored[0][0],)


def extract_when(text: str) -> Optional[Tuple[int, Optional[Tuple[int, int]], str]]:
    """(weekday_idx, (hour, minute)|None, mention) from an explicit temporal mention,
    or None. A bare number never counts (Q4,500 is not 4 o'clock): clock time needs
    minutes, am/pm, or weekday adjacency."""
    words = _tokens(text)
    day_idx, day_pos = None, None
    for i, w in enumerate(words):
        if w in WEEKDAYS and day_idx is None:
            day_idx, day_pos = WEEKDAYS[w], i
    clock, mention = None, None
    m = CLOCK.search(text)
    if m:
        h, minute, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
        if h > 12 or minute > 59:
            return (day_idx, None, " ".join(words[day_pos:day_pos + 1])) if day_idx is not None else None
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        clock, mention = (h, minute), m.group(0)
    else:
        m24 = CLOCK_24.search(text)
        mes = CLOCK_ES.search(text)
        if mes:
            h = int(mes.group(1))
            if 0 <= h <= 23:
                part = (mes.group(2) or "").lower()
                if part in ("tarde", "noche") and h < 12:
                    h += 12
                if day_idx is not None:
                    clock, mention = (h, 0), mes.group(0)
        elif m24:
            # 24h clock only counts beside a weekday ("Friday 08:00"); standalone it is noise.
            htok = m24.group(1).lstrip("0") or "0"
            pos = next((i for i, w in enumerate(words) if w.lstrip("0") == htok), None)
            if day_idx is not None and pos is not None and abs(pos - day_pos) <= 3:
                clock, mention = (int(m24.group(1)), int(m24.group(2))), m24.group(0)
    if day_idx is None:
        return None
    day_word = [k for k, v in WEEKDAYS.items() if v == day_idx and len(k) > 3][0]
    if mention and day_word not in mention.lower():
        mention = f"{day_word} {mention}"
    elif not mention:
        mention = day_word
    return day_idx, clock, mention


def resolve_day(weekday_idx: int, now: datetime, timezone_str: str) -> Tuple[Any, Any]:
    """Next occurrence of the weekday from `now` (today if same weekday), as naive UTC
    day-start/day-end datetimes (repo convention)."""
    try:
        tz = ZoneInfo(timezone_str or "UTC")
    except Exception:
        tz = ZoneInfo("UTC")
    local = (now.replace(tzinfo=timezone.utc) if now.tzinfo is None else now.astimezone(timezone.utc)).astimezone(tz)
    delta = (weekday_idx - local.weekday()) % 7
    day = (local + timedelta(days=delta)).date()
    start = datetime(day.year, day.month, day.day, tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None)
    return start, start + timedelta(hours=23, minutes=59, seconds=59)


def _push_evidence(row: Any, text: str) -> None:
    # WorldEvent rows carry a refs list; Expectations carry one resolution string.
    if hasattr(row, "evidence_refs_json"):
        try:
            refs = json.loads(getattr(row, "evidence_refs_json", None) or "[]")
        except ValueError:
            refs = []
        refs = [r for r in refs if isinstance(r, str)]
        if text not in refs:
            refs.append(text)
        row.evidence_refs_json = json.dumps(refs[-10:])
        return
    if not getattr(row, "resolution_evidence", None):
        row.resolution_evidence = text


def _known_evidence(row: Any, text: str) -> bool:
    if hasattr(row, "evidence_refs_json"):
        try:
            return text in (json.loads(getattr(row, "evidence_refs_json", None) or "[]") or [])
        except ValueError:
            return False
    return (getattr(row, "resolution_evidence", None) or "") == text


async def revise_record(db: AsyncSession, kind: str, row_id: UUID, *, day_start: Any, clock: Optional[Tuple[int, int]],
                        mention: str, evidence: str) -> Dict[str, Any]:
    """Apply the corrected timing to the matched record. Same-day holdings are no-ops
    (already_current) so re-reads never churn timestamps or resurrect prose."""
    if kind == "event":
        row = await db.get(WorldEvent, row_id)
        if row is None:
            return {"revised": False, "reason": "record_gone"}
        if row.when_start is not None and row.when_start.date() == day_start.date():
            return {"revised": False, "reason": "already_current", "id": str(row_id),
                    "repeat": _known_evidence(row, evidence)}
        if clock is not None:
            try:
                tz = ZoneInfo("UTC")
                base = day_start.replace(tzinfo=timezone.utc)
                start = (base + timedelta(hours=clock[0], minutes=clock[1])).replace(tzinfo=None)
            except Exception:
                start = day_start
            row.when_start, row.when_end = start, start + timedelta(hours=1)
            row.when_precision = "exact"
        else:
            row.when_start, row.when_end = day_start, day_start + timedelta(hours=23, minutes=59, seconds=59)
            row.when_precision = "day"
        row.when_phrase = mention[:200]
        _push_evidence(row, evidence[:500])
        db.add(row)
        await db.commit()
        return {"revised": True, "id": str(row_id), "kind": "event"}
    exp = await db.get(Expectation, row_id)
    if exp is None:
        return {"revised": False, "reason": "record_gone"}
    from src.models.expectation import OutcomeState as _OS
    if exp.outcome_state != _OS.UNKNOWN:
        return {"revised": False, "reason": "already_settled", "id": str(row_id), "repeat": True}
    if exp.expected_window_start is not None and exp.expected_window_start.date() == day_start.date():
        return {"revised": False, "reason": "already_current", "id": str(row_id),
                "repeat": _known_evidence(exp, evidence)}
    exp.expected_window_start, exp.expected_window_end = day_start, day_start + timedelta(hours=23, minutes=59, seconds=59)
    _push_evidence(exp, evidence[:500])
    db.add(exp)
    await db.commit()
    return {"revised": True, "id": str(row_id), "kind": "expectation"}


async def route_corrections(db: AsyncSession, workspace_id: str, owner: str, texts: List[str], *,
                            now: datetime, timezone_str: str = "UTC") -> Dict[str, Any]:
    """Split standing-request candidates into preferences (store as prose) and dated
    corrections of open records (revise + skip prose). Returns
    {preferences, revised, already_current, prose_kept} where prose_kept lists texts that
    fell through to today's behavior so the caller stores exactly those."""
    preferences, revised, already, kept = [], [], [], []
    pending = [(t, " ".join(str(t).split())[:240]) for t in texts or []]
    pending = [(raw, clean) for raw, clean in pending if clean]
    if not pending:
        return {"preferences": [], "revised": [], "already_current": [], "prose_kept": []}
    events, expectations = [], []
    if pending:
        events = (await db.execute(select(WorldEvent).where(
            WorldEvent.honcho_workspace_id == workspace_id, WorldEvent.owner_peer_id == owner,
            WorldEvent.status == "current"))).scalars().all()
        expectations = (await db.execute(select(Expectation).where(
            Expectation.honcho_workspace_id == workspace_id, Expectation.owner_peer_id == owner,
            Expectation.outcome_state == OutcomeState.UNKNOWN))).scalars().all()
    for raw, clean in pending:
        hit = match_record(clean, events, expectations)
        if hit is None:
            preferences.append(clean)      # genuine preference or unmatchable: today's behavior
            kept.append(clean)
            continue
        kind, row_id, title, _ = hit
        when = extract_when(clean)
        if when is None:
            preferences.append(clean)      # a match with no date is not a correction: today's behavior
            kept.append(clean)
            continue
        day_idx, clock, mention = when
        start, _ = resolve_day(day_idx, now, timezone_str)
        out = await revise_record(db, kind, row_id, day_start=start, clock=clock, mention=mention, evidence=clean)
        if out.get("revised"):
            # The dated correction now lives in the record: storing it as prose too would
            # create the competing copy that rots on the next change. Skip it, loudly.
            revised.append({"text": clean, **{k: out[k] for k in ("kind", "id") if k in out}})
        else:
            # already_current: the timing stands. A REPEAT (this exact text is already the
            # record's evidence) skips prose so repeats never accumulate; a NEW instruction
            # that coincides with current state still stores as prose.
            already.append({"text": clean, "reason": out.get("reason"), "id": str(row_id)})
            if not out.get("repeat"):
                preferences.append(clean)
                kept.append(clean)
    return {"preferences": preferences, "revised": revised, "already_current": already, "prose_kept": kept}
