"""Deterministic, time-aware views over the maintained operational ledger.

Interpretation happens once, when information enters or changes (the witness + maintenance agent).
Everything here is retrieval: pure functions over stored rows and the current clock. No model, no
transcript, no re-interpretation. The only meaning the code relies on was recorded by the model at
write time (`time_role`: does the thing HAPPEN at that time, or is it DUE by it?); the code never infers it.

Distinctions it keeps (they are different facts):
- a scheduled thing whose time has passed is NOT overdue: we know it was scheduled, not what happened
  ("Things to check up on"). An obligation whose deadline passed while still open IS overdue.
- precision is explicit: date-only, exact time, and unknown are different knowledge; nothing is invented.
- time passing never completes, cancels or abandons anything.
- a cue is a presentation of existing state, not a second source of truth.

The same module serves every product: it takes rows, a clock and a zone.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple
from zoneinfo import ZoneInfo

OPEN = ("open", "waiting", "watching")
CLOSED = ("done", "cancelled", "answered")
IMMINENT_HOURS = 3
CHECK_UP_DAYS = 3           # a passed item older than this stops claiming the foreground (still reachable by query)
WEEK_DAYS = 7
SECTION_CAP = 8
CLOSED_VISIBLE_DAYS = 7


def _zone(name: Optional[str], fallback: str = "UTC") -> ZoneInfo:
    for n in (name, fallback, "UTC"):
        try:
            return ZoneInfo(str(n))
        except Exception:
            continue
    return ZoneInfo("UTC")


def _d(value: Any) -> Optional[date]:
    try:
        return datetime.strptime(str(value or "")[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


@dataclass
class Item:
    key: str
    title: str
    status: str
    kind: str
    day: Optional[date]
    clock: Optional[time]
    zone: ZoneInfo
    role: str
    basis: str
    importance: int
    waiting_on: str
    question: str
    detail: str
    updated: Optional[date]
    created: str

    @property
    def instant(self) -> Optional[datetime]:
        if self.day is None or self.clock is None:
            return None
        return datetime.combine(self.day, self.clock).replace(tzinfo=self.zone)


def to_item(row: Dict[str, Any], default_zone: ZoneInfo) -> Item:
    t = None
    raw = str(row.get("expected_time") or "").strip()
    if raw:
        try:
            t = datetime.strptime(raw, "%H:%M").time()
        except ValueError:
            t = None
    day = _d(row.get("expected_date"))
    return Item(
        key=str(row.get("key") or ""), title=str(row.get("title") or "untitled"), status=str(row.get("status") or "open"),
        kind=str(row.get("kind") or ""), day=day, clock=t if day else None,
        zone=_zone(row.get("time_zone"), default_zone.key), role=str(row.get("time_role") or ""),
        basis=str(row.get("time_basis") or ("stated" if t else "")),
        importance=int(row.get("importance") or 2), waiting_on=str(row.get("waiting_on") or ""),
        question=str(row.get("question") or row.get("question_text") or ""), detail=str(row.get("detail") or ""),
        updated=_d(row.get("updated_at")), created=str(row.get("created_at") or ""))


# ------------------------------------------------------------------ text ----

def _clock_text(t: time) -> str:
    return t.strftime("%-I:%M%p").lower()


def confirmed_instant(it: "Item") -> Optional[datetime]:
    """The moment to use for any ACTION (a timed reminder, a call, an alarm): only a time the person actually gave.
    An assumed time may inform what we show and say, but it never authorises a timed action."""
    return it.instant if it.basis == "stated" else None


def _day_text(day: date, today: date) -> str:
    if day == today:
        return "today"
    if day == today + timedelta(days=1):
        return f"tomorrow ({day.strftime('%a %-d %b')})"
    if day == today - timedelta(days=1):
        return f"yesterday ({day.strftime('%a %-d %b')})"
    return day.strftime("%a %-d %b")


def when_text(it: Item, today: date) -> str:
    if it.day is None:
        return "no date"
    d = _day_text(it.day, today)
    if it.clock is not None:
        c = _clock_text(it.clock) + (" (assumed; not confirmed)" if it.basis == "assumed" else "")
        return f"{c} {d}" if it.day == today else f"{d}, {c}"
    return d


def _flags(it: Item) -> str:
    bits: List[str] = []
    if it.role == "happens" and it.day is not None and it.clock is None:
        bits.append("time not recorded")
    if it.waiting_on:
        bits.append(f"waiting on {it.waiting_on}")
    if it.question:
        bits.append(f"open question: {it.question}")
    return ("; " + "; ".join(bits)) if bits else ""


def line(it: Item, band: str, today: date) -> str:
    w = when_text(it, today)
    if band == "overdue":
        return f"- {it.title}: was due {w}; not marked done{_flags(it)}"
    if band == "check_up_on":
        return f"- {it.title}: was scheduled for {w}; outcome not recorded{_flags(it)}"
    if band in ("imminent", "today", "week", "later"):
        verb = "due" if it.role == "deadline" else ""
        return f"- {it.title}: {(verb + ' ') if verb else ''}{w}{_flags(it)}"
    if band == "undated":
        return f"- {it.title}{_flags(it)}"
    if band == "waiting":
        return f"- {it.title}{_flags(it)}"
    return f"- {it.title}: {w}{_flags(it)}"


# ----------------------------------------------------------------- bands ----

def classify(it: Item, now: datetime, today: date) -> str:
    """Primary band for one open item. Pure function of the stored fields and the clock."""
    inst = it.instant
    if it.day is None:
        return "waiting" if it.status == "waiting" else "undated"
    if inst is not None:
        if inst >= now:
            if inst - now <= timedelta(hours=IMMINENT_HOURS):
                return "imminent"
            if it.day == today:
                return "today"
            return "week" if (it.day - today).days <= WEEK_DAYS else "later"
        passed = True
    else:
        if it.day == today:
            return "today"
        if it.day > today:
            return "week" if (it.day - today).days <= WEEK_DAYS else "later"
        passed = True
    if passed and (today - it.day).days > CHECK_UP_DAYS:
        return "older"
    return "overdue" if it.role == "deadline" else "check_up_on"


def _sort_key(it: Item, now: datetime) -> Tuple:
    inst = it.instant
    return (it.day or date.max, inst or datetime.max.replace(tzinfo=timezone.utc), -it.importance, it.created)


HER_KINDS = ("commitment", "reminder")      # what the companion owes, as against what she wishes or wonders about


def is_hers(row: Dict[str, Any], companion_name: str) -> bool:
    """A record where the outstanding part is the companion's: she promised the person something (hers alone, or shared with the part that is hers named in `waiting_on`).
    The person's plate is theirs; her promises are not their to-dos, and her private wishes are neither."""
    if not companion_name:
        return False
    party = str(row.get("party") or "")
    if party == "companion":
        return str(row.get("kind") or "") in HER_KINDS
    return party == "shared" and companion_name.lower() in str(row.get("waiting_on") or "").lower()


def compute(rows: Iterable[Dict[str, Any]], now: datetime, time_zone: str, default_zone: str = "UTC", companion_name: str = "") -> Dict[str, Any]:
    zone = _zone(time_zone, default_zone)
    now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
    today = now.date()
    bands: Dict[str, List[Item]] = {k: [] for k in ("imminent", "today", "overdue", "check_up_on", "waiting", "week", "later", "undated", "older")}
    closed: List[Item] = []
    hers: List[Item] = []
    for r in rows:
        if is_hers(r, companion_name):
            it = to_item(r, zone)
            if it.status in OPEN:
                hers.append(it)
            continue                    # presented to her as hers, never on the person's plate
        if str(r.get("party") or "") == "companion":
            continue                    # the companion's own wishes and reflections are not the person's plate
        it = to_item(r, zone)
        if it.status in OPEN:
            bands[classify(it, now, today)].append(it)
        elif it.status in CLOSED and it.status != "cancelled" and it.updated is not None and (today - it.updated).days <= CLOSED_VISIBLE_DAYS:
            closed.append(it)
    for k, v in bands.items():
        v.sort(key=lambda x: _sort_key(x, now))
    hers.sort(key=lambda x: _sort_key(x, now))
    return {"now": now, "today": today, "zone": zone, "bands": bands, "closed": closed, "hers": hers, "companion": companion_name}


def cues(view: Dict[str, Any]) -> List[Dict[str, Any]]:
    """The shared cue shape: a presentation of existing ledger state (never a second source of truth)."""
    out: List[Dict[str, Any]] = []
    today = view["today"]
    for band, items in view["bands"].items():
        for it in items:
            out.append({"source": "ledger", "key": it.key, "title": it.title, "band": band, "line": line(it, band, today)[2:],
                        "when": (it.instant.isoformat() if it.instant else (it.day.isoformat() if it.day else None)),
                        "time_basis": it.basis, "importance": it.importance})
    return out


# ---------------------------------------------------------------- render ----

_SECTIONS = (
    ("imminent", "Right now (next {h} hours)"),
    ("today", "Today"),
    ("overdue", "Overdue"),
    ("check_up_on", "Things to check up on"),
    ("waiting", "Waiting on"),
    ("week", "This week"),
    ("later", "Later"),
    ("undated", "No date"),
)


def _clock_label(now: datetime) -> str:
    return f"{now.strftime('%A %-d %B %Y, %-I:%M%p').replace('AM', 'am').replace('PM', 'pm')} ({now.tzinfo.key if hasattr(now.tzinfo, 'key') else now.tzname()})"


def hers_lines(view: Dict[str, Any]) -> List[str]:
    """What the companion said she would do, still open. A day that has passed stays what it was (the day it was for, not recorded as done): it is never turned into an
    overdue debt, and it leaves the picture when it is old, as anything else does."""
    today, now = view["today"], view["now"]
    out: List[str] = []
    for it in view.get("hers", []):
        band = classify(it, now, today)
        if band == "older":
            continue
        when = when_text(it, today)
        flags = _flags(it).replace(f"; waiting on {it.waiting_on}", "") if it.waiting_on else _flags(it)      # "waiting on Sophie" is what these are, said to Sophie
        if band in ("overdue", "check_up_on"):
            out.append(f"- {it.title}: was for {when}; not recorded as done{flags}")
        elif it.day is None:
            out.append(f"- {it.title}{flags}")
        else:
            out.append(f"- {it.title}: {when}{flags}")
    return out[:SECTION_CAP]


def render(view: Dict[str, Any]) -> str:
    """The operational picture as plain, factual headings. No suggestions, no instructions."""
    today, now = view["today"], view["now"]
    blocks: List[str] = []
    for band, title in _SECTIONS:
        items = view["bands"][band]
        if not items:
            continue
        shown = items[:SECTION_CAP]
        body = [line(it, band, today) for it in shown]
        if len(items) > len(shown):
            body.append(f"- +{len(items) - len(shown)} more")
        blocks.append(f"{title.format(h=IMMINENT_HOURS)}:\n" + "\n".join(body))
    mine = hers_lines(view)
    if mine:
        blocks.append("Yours (you offered or promised these; they are not the person's to-dos):\n" + "\n".join(mine))
    older = view["bands"]["older"]
    if older:
        blocks.append(f"Older, still open and unresolved: {len(older)} item(s).")
    if view["closed"]:
        blocks.append("Recently closed: " + ", ".join(it.title for it in view["closed"][:6]) + ".")
    if not blocks:
        return ""
    return f"[OPERATIONAL AWARENESS — {_clock_label(now)}. Maintained record; facts, not interpretation.]\n" + "\n".join(blocks)


# ----------------------------------------------------------------- range ----

def resolve_range(keyword: str, today: date) -> Tuple[date, date]:
    k = (keyword or "week").strip().lower().replace(" ", "_")
    if k == "today":
        return today, today
    if k == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=1)
    if k in ("week", "this_week", "next_7_days"):
        return today, today + timedelta(days=6)
    if k == "next_week":
        start = today + timedelta(days=(7 - today.weekday()))
        return start, start + timedelta(days=6)
    if k in ("month", "this_month"):
        nxt = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        return today, nxt - timedelta(days=1)
    if k == "next_month":
        first = (today.replace(day=28) + timedelta(days=4)).replace(day=1)
        after = (first.replace(day=28) + timedelta(days=4)).replace(day=1)
        return first, after - timedelta(days=1)
    raise ValueError(f"unknown period '{keyword}'")


def render_range(rows: Iterable[Dict[str, Any]], start: date, end: date, now: datetime, time_zone: str,
                 include_closed: bool = False, default_zone: str = "UTC") -> Dict[str, Any]:
    zone = _zone(time_zone, default_zone)
    now = now.astimezone(zone) if now.tzinfo else now.replace(tzinfo=zone)
    today = now.date()
    inside: List[Item] = []
    earlier: List[Tuple[str, Item]] = []
    for r in rows:
        if str(r.get("party") or "") == "companion":
            continue                    # her private wishes and promises are not the person's schedule
        it = to_item(r, zone)
        is_open = it.status in OPEN
        if not is_open and not (include_closed and it.status in CLOSED):
            continue
        if it.day is not None and start <= it.day <= end:
            inside.append(it)
        elif is_open and start <= today and it.day is not None and it.day < start:
            band = classify(it, now, today)
            if band in ("overdue", "check_up_on"):
                earlier.append((band, it))
    inside.sort(key=lambda x: _sort_key(x, now))
    lines: List[str] = []
    if earlier:
        lines.append("Earlier, still open:")
        for band, it in sorted(earlier, key=lambda p: _sort_key(p[1], now)):
            lines.append(line(it, band, today))
    by_day: Dict[date, List[Item]] = {}
    for it in inside:
        by_day.setdefault(it.day, []).append(it)  # type: ignore[arg-type]
    for day in sorted(by_day):
        lines.append(f"{day.strftime('%A %-d %B')}{' (today)' if day == today else ''}:")
        for it in by_day[day]:
            st = "" if it.status in OPEN else f" [{it.status}]"
            tm = (f"{_clock_text(it.clock)}{' (assumed)' if it.basis == 'assumed' else ''} ") if it.clock else ""
            verb = "due " if it.role == "deadline" else ""
            lines.append(f"- {tm}{verb}{it.title}{st}{_flags(it)}")
    header = f"[SCHEDULE {start.strftime('%a %-d %b')}{'' if start == end else ' to ' + end.strftime('%a %-d %b %Y')} — read at {_clock_label(now)}. Maintained record; facts, not interpretation.]"
    text = header + "\n" + ("\n".join(lines) if lines else "Nothing recorded for this period.")
    return {"text": text, "count": len(inside), "earlier": len(earlier)}
