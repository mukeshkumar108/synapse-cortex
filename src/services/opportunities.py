"""What may be worth the companion's attention at the moment it speaks (EXPERIMENT H11, productised from the golden-moments harness).

Deterministic, no model. It reads the maintained records (the connected world and the ledger) and answers one question: of everything held, what is worth a light
mention, an offer of help, or only holding, right now?

Rules (each one came from a measured failure, see the Cortex review, "Results so far: H11"):
  * Tense comes from DATES, never from stored words. Summaries and timing text carry relative words ("tomorrow", "this Saturday") written days earlier; they are not shown.
  * A candidate needs real stakes (a significant happening or situation, or a dated ledger matter close in time). Everything else is background.
  * Facts only: what, when, who. How to behave with them (whether to raise one, how lightly, what to leave) is the product's policy, carried by the persona, never by
    this module. The person's own boundary is a fact like any other: a matter they asked not to be prompted about stays in the packet with their words and the day
    they said it ("They asked me on Sat 24 Oct not to bring this up: ..."), and she decides what to do with that.
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


def _asked(e: Any, tz) -> str:
    """The person's own boundary about this matter, as a fact: the day they said it and (when we have it) their words. Empty when they have not asked."""
    if not e.suppressed:
        return ""
    refs = [r for r in known_world._refs(e.source_refs_json) if r.get("asked")]
    ref = refs[-1] if refs else {}
    day = _day(ref.get("asked") or e.updated_at, tz)
    on = f" on {day.strftime('%a')} {day.day} {day.strftime('%b')}" if day else ""
    quote = str(ref.get("quote") or "")[:160]
    return f"They asked me{on} not to bring this up" + (f": \"{quote}\"" if quote else ".")


def relative_time_in(text: str) -> bool:
    from src.services.world_agent import relative_time_problem
    return bool(relative_time_problem(text))


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


async def read(db: AsyncSession, ws: str, owner: str, ctx: "known_world.Ctx", *, world_on: bool = True, ledger_rows: Optional[List[Any]] = None, notes_on: bool = False) -> Dict[str, Any]:
    now, tz, today = ctx.now, ctx.now.tzinfo, ctx.today
    cands: List[Dict[str, Any]] = []
    background: List[Dict[str, Any]] = []
    people: List[str] = []
    people_notes: Dict[str, str] = {}      # a known person's name -> their stored one-line summary ("the person's twelve-year-old nephew")

    if world_on:
        entities = await known_world.list_all(db, ws, owner, statuses=("active",), limit=300)
        for e in entities:
            if e.name_key == "the person":
                continue
            if e.kind == "person" and not (e.form or "") and e.name:
                if e.suppressed:
                    continue
                people.append(str(e.name))
                if (e.summary or "").strip() and not relative_time_in(e.summary):
                    people_notes[str(e.name)] = str(e.summary).strip()
                continue
            if e.form not in ("happening", "situation"):
                continue
            od = _day(e.occurred_on, tz)
            sig = int(e.significance or 1)
            quotes = [r.get("quote") for r in known_world._refs(e.source_refs_json) if r.get("quote")]
            said = str(quotes[-1])[:160] if quotes else ""
            asked = _asked(e, tz)
            if asked:
                said = ""                                          # their last quoted words ARE the request, shown once below
            within = od is None or -PAST_DAYS <= (od.date() - today).days <= AHEAD_DAYS
            if sig >= 2 and within:
                cands.append({"id": f"world:{e.id}", "text": str(e.name), "when": relative_label(od, today) if od else "", "said": said, "asked": asked, "source": "world", "ref": str(e.id), "score": sig + (1 if od and 0 <= (today - od.date()).days <= PAST_DAYS else 0), "sort": od})
            else:
                background.append({"id": f"world:{e.id}", "text": str(e.name), "said": said, "asked": asked, "source": "world", "ref": str(e.id)})

    for r in ledger_rows or []:
        if r.status not in ("open", "waiting", "watching"):
            continue
        ed = _day(r.expected_date, tz)
        imp = int(r.importance or 1)
        if ed is not None and -PAST_DAYS <= (ed.date() - today).days <= LEDGER_AHEAD_DAYS and (imp >= 2 or 0 <= (ed.date() - today).days <= 1):      # low-importance matters count only when imminent, never after the fact
            cands.append({"id": f"ledger:{r.situation_key}", "text": str(r.title), "when": relative_label(ed, today), "source": "ledger",
                          "ref": str(r.situation_key), "score": max(imp, 2) + (1 if abs((ed.date() - today).days) <= 2 else 0), "sort": ed})
        else:
            background.append({"id": f"ledger:{r.situation_key}", "text": str(r.title), "source": "ledger", "ref": str(r.situation_key)})

    if notes_on:                       # what keeps coming up in their own words (counted in code from the notes), with dates: facts, never a question to ask
        from src.services import notes as _notes
        cands.extend(await _notes.ask_candidates(db, ws, owner, today))

    cands.sort(key=lambda c: (-c["score"], c["sort"] or now))
    seen: set = set()
    top: List[Dict[str, Any]] = []
    for c in cands:
        key = c["text"].lower()[:40]
        if key not in seen:
            seen.add(key)
            top.append(c)
    top = top[:MAX_CANDIDATES]
    bg_items, bg_seen = [], set()
    for b in background:
        k = b["text"].lower()[:40]
        if k not in seen and k not in bg_seen:
            bg_seen.add(k)
            bg_items.append(b)
    bg_items = bg_items[:MAX_BACKGROUND]
    bg = [b["text"] for b in bg_items]

    parts: List[str] = []
    if top:
        parts.append("From earlier:\n" + "\n".join(f"- {c['text']}" + (f" [{c['when']}]" if c["when"] else "") for c in top))
    if bg or people:
        parts.append("Also held: " + "; ".join(bg + ([f"people: {', '.join(people[:5])}"] if people else [])))
    return {"text": "\n\n".join(parts), "candidates": [{k: v for k, v in c.items() if k != "sort"} for c in top], "background": bg, "background_items": bg_items,
            "people": people[:8], "people_notes": people_notes, "now": now.isoformat(), "time_zone": ctx.tz}


# ----------------------------------------------------------------------------------------------------------------------------------------------------------
# The packet contract (version 1). ONE shape, whether a packet is built on demand now or prepared ahead of time later. A packet is a temporary piece of
# attention, never part of the companion's prompt or personality. Retiring a PACKET (its items were used, or the conversation moved on) is not retiring the
# MATTER: "he is having surgery next Thursday" keeps the matter alive and may prepare a new opportunity; "he's fine now" may resolve it. The matter's life
# cycle belongs to the ledger and the world records, not to exposure.
# ----------------------------------------------------------------------------------------------------------------------------------------------------------
PACKET_VERSION = 1
_TASK_WORDS = ("help me", "can you help", "could you", "tighten", "practise", "practice", "make it shorter", "rewrite", "draft", "proofread", "thoughts?")


_STOP = frozenset("the and his her for with that this you your are was were but not how did does doing have has had from they them their what when where who why will would "
                  "can could should about into over just like very really also than then there here out off our its ive im".split())


def _stems(text: str) -> set:
    """Word stems of three letters or more, minus function words, so 'Leo' and 'leg' count and 'the' and 'with' do not."""
    import re
    return {w[:5] for w in re.findall(r"[a-z]{3,}", (text or "").lower().replace("'", "")) if w not in _STOP}


def looks_like_task(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in _TASK_WORDS)


LEDGER_HEAD = "Things I need to catch up on with them, because they matter to them:"
WORLD_HEAD = "What is on my mind about them, because it matters to them:"
NOTICED_HEAD = "What I have been noticing about them over our conversations:"


def _fact(i: Dict[str, Any]) -> str:
    return f"- {i['text']}" + (f" ({i['when']})" if i.get("when") else "")


def _render(items: List[Dict[str, Any]], purpose: str) -> str:
    """The attention packet. The heading is the companion's own thought and carries the importance ("things I need to catch up on with them, because they matter to
    them"); the items under it are plain facts, so nothing is rewritten per item (measured: as often taken as per-item first-person lines, and no more nagging).
    Items the companion is carrying forward (an opening, or a matter not yet raised this sitting) sit under those headings; items the person's own words touch sit under
    a plain one. Never a behavioural instruction, never a condition."""
    if not items:
        return ""
    carried = [i for i in items if purpose in ("reconnect", "survey") or i.get("pending")]
    touched = [i for i in items if i not in carried]
    blocks: List[str] = []
    if touched:
        head = {"touched": "Their words bring to mind:", "task_support": "Relevant to what they asked for:"}.get(purpose, "Their words bring to mind:")
        blocks.append(head + "\n" + "\n".join(_fact(i) for i in touched))
    for system, head in (("ledger", LEDGER_HEAD), ("world", WORLD_HEAD), ("notes", NOTICED_HEAD)):
        grp = [i for i in carried if (i.get("source") or {}).get("system") == system]
        if grp:
            blocks.append(head + "\n" + "\n".join(_fact(i) for i in grp))
    said = [f"- {i['text']}: \"{i['said']}\"" for i in items if i.get("said")]
    if said:
        blocks.append("What they said about it, in their words:\n" + "\n".join(said))
    asked = [f"- {i['text']}: {i['asked']}" for i in items if i.get("asked")]
    if asked:
        blocks.append("What they have asked of me:\n" + "\n".join(asked))
    return "\n\n".join(blocks)


def build_packet(out: Dict[str, Any], *, stage: str = "opening", user_text: str = "", task: Optional[bool] = None, used: Optional[List[str]] = None,
                 pending: Optional[List[str]] = None, valid_minutes: Optional[int] = None) -> Dict[str, Any]:
    """Select the small packet for this moment from what `read` found. Deterministic. Empty items means: give the companion nothing.
    stage: opening (re-entry: the single top opportunity), moment (only items the person's own words touch; relational items withheld during a task),
    survey (everything, the older single-block shape). `used` are item ids already used in this conversation (packet retirement, not matter retirement).
    `pending` are item ids the companion was given earlier this sitting and has not yet raised: while she has not, they ride along on every turn that is not a task
    (a deferral is not an abandonment); once she has used one it is retired from the packet, never from the matter."""
    from datetime import datetime as _dt, timedelta as _td
    used_set = set(used or [])
    cands = [c for c in out.get("candidates", []) if c["id"] not in used_set]
    bg = [b for b in out.get("background_items", []) if b["id"] not in used_set]
    is_task = looks_like_task(user_text) if task is None else bool(task)

    def item(x: Dict[str, Any], kind: str, carried: bool = False) -> Dict[str, Any]:
        return {"id": x["id"], "kind": kind, "text": x["text"], "when": x.get("when", ""), "said": x.get("said", ""), "asked": x.get("asked", ""),
                "stakes": int(x.get("score", 1)), "source": {"system": x["source"], "ref": x["ref"]}, **({"pending": True} if carried else {})}

    if stage == "opening":
        purpose, items = "reconnect", [item(c, "opportunity") for c in cands[:1]]
    elif stage == "moment":
        touched = _stems(user_text)
        pool = [(c, "opportunity") for c in cands] + [(b, "background") for b in bg]
        hits = [(x, k) for x, k in pool if touched & _stems(x["text"])]
        purpose, items = ("task_support" if is_task else "touched"), [item(x, k) for x, k in hits[:2]]
        if not is_task:
            have = {i["id"] for i in items}
            owed = [(x, k) for x, k in pool if x["id"] in set(pending or []) and x["id"] not in have]
            items += [item(x, k, True) for x, k in owed[:1]]
    else:
        purpose, items = "survey", [item(c, "opportunity") for c in cands] + [item(b, "background") for b in bg]
    who = []
    for name, note in (out.get("people_notes") or {}).items():
        if any(name.lower() in i["text"].lower() for i in items):
            who.append(f"- {name}: {note}")
    built = _dt.fromisoformat(out["now"])
    minutes = valid_minutes if valid_minutes is not None else (360 if stage == "opening" else 30)
    import hashlib
    pid = hashlib.sha1((out["now"] + stage + "|".join(i["id"] for i in items)).encode()).hexdigest()[:12]
    return {"version": PACKET_VERSION, "id": pid, "stage": stage, "purpose": purpose, "built_at": built.isoformat(), "valid_until": (built + _td(minutes=minutes)).isoformat(),
            "items": items, "who": who, "text": _render(items, purpose) + (("\n\nWho this is:\n" + "\n".join(who)) if (who and items) else ""),
            "retire": {"packet": "when its items have been used, or the conversation moves on",
                       "matter": "never by use alone: only when the matter itself resolves (ledger status, or the person says it is settled)"}}
