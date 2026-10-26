"""What may be worth the companion's attention at the moment it speaks (EXPERIMENT H11, productised from the golden-moments harness).

Deterministic, no model. It reads the maintained records (the connected world and the ledger) and answers one question: of everything held, what is worth a light
mention, an offer of help, or only holding, right now?

Rules (each one came from a measured failure, see the Cortex review, "Results so far: H11"):
  * Tense comes from DATES, never from stored words. Summaries and timing text carry relative words ("tomorrow", "this Saturday") written days earlier; they are not shown.
  * A candidate needs real stakes (a significant happening or situation, or a dated ledger matter close in time). Everything else is background.
  * Wording is neutral and third person. An opportunity is not an instruction: the companion may raise it, offer help, hold it, or say nothing.
  * Private items are marked so the companion acknowledges lightly and does not probe.
  * Nothing is ranked on recency alone.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import known_world

MAX_CANDIDATES = 3
MAX_BACKGROUND = 5
PAST_DAYS = 10          # a happening or dated matter older than this is background
AHEAD_DAYS = 14         # happenings/situations dated further ahead than this are background
LEDGER_AHEAD_DAYS = 7


def _day(value: Any, tz) -> Optional[datetime]:
    if value is None:
        return None
    try:
        d = value if isinstance(value, datetime) else datetime.fromisoformat(str(value)[:10] + "T00:00:00")
        return d.replace(tzinfo=tz)
    except Exception:  # noqa: BLE001
        return None


def relative_label(day: datetime, today) -> str:
    """'Thu 22 Oct, tomorrow' from the date alone."""
    n = (day.date() - today).days
    label = f"{day.strftime('%a')} {day.day} {day.strftime('%b')}"
    if n == 0:
        return f"{label}, today"
    if n == 1:
        return f"{label}, tomorrow"
    if n == -1:
        return f"{label}, yesterday"
    return f"{label}, {n} days ahead" if n > 0 else f"{label}, {-n} days ago"


async def read(db: AsyncSession, ws: str, owner: str, ctx: "known_world.Ctx", *, world_on: bool = True, ledger_rows: Optional[List[Any]] = None) -> Dict[str, Any]:
    now, tz, today = ctx.now, ctx.now.tzinfo, ctx.today
    cands: List[Dict[str, Any]] = []
    background: List[str] = []
    people: List[str] = []

    if world_on:
        for e in await known_world.list_all(db, ws, owner, statuses=("active",), limit=300):
            if e.suppressed or e.name_key == "the person":
                continue
            if e.kind == "person" and not (e.form or "") and e.name:
                people.append(str(e.name))
                continue
            if e.form not in ("happening", "situation"):
                continue
            od = _day(e.occurred_on, tz)
            sig = int(e.significance or 1)
            within = od is None or -PAST_DAYS <= (od.date() - today).days <= AHEAD_DAYS
            if sig >= 2 and within:
                cands.append({"text": str(e.name), "when": relative_label(od, today) if od else "", "private": bool(e.sensitive), "source": "world",
                              "score": sig + (1 if od and 0 <= (today - od.date()).days <= PAST_DAYS else 0), "sort": od})
            else:
                background.append(str(e.name))

    for r in ledger_rows or []:
        if r.status not in ("open", "waiting", "watching"):
            continue
        ed = _day(r.expected_date, tz)
        imp = int(r.importance or 1)
        if ed is not None and -PAST_DAYS <= (ed.date() - today).days <= LEDGER_AHEAD_DAYS and (imp >= 2 or 0 <= (ed.date() - today).days <= 1):      # low-importance matters count only when imminent, never after the fact
            cands.append({"text": str(r.title), "when": relative_label(ed, today), "private": False, "source": "ledger",
                          "score": max(imp, 2) + (1 if abs((ed.date() - today).days) <= 2 else 0), "sort": ed})
        else:
            background.append(str(r.title))

    cands.sort(key=lambda c: (-c["score"], c["sort"] or now))
    seen: set = set()
    top: List[Dict[str, Any]] = []
    for c in cands:
        key = c["text"].lower()[:40]
        if key not in seen:
            seen.add(key)
            top.append(c)
    top = top[:MAX_CANDIDATES]
    bg = [b for b in dict.fromkeys(background) if b.lower()[:40] not in seen][:MAX_BACKGROUND]

    parts: List[str] = []
    if top:
        parts.append("Possible opportunities (each is optional: raise one lightly, offer help, or hold it):\n" + "\n".join(
            f"- {c['text']}" + (f" [{c['when']}]" if c["when"] else "") + ("  (private: acknowledge lightly, do not probe)" if c["private"] else "") for c in top))
    if bg or people:
        parts.append("Background (use only if the person goes there; do not raise unprompted): " + "; ".join(bg + ([f"people: {', '.join(people[:5])}"] if people else [])))
    return {"text": "\n\n".join(parts), "candidates": [{k: v for k, v in c.items() if k != "sort"} for c in top], "background": bg, "people": people[:8],
            "now": now.isoformat(), "time_zone": ctx.tz}
