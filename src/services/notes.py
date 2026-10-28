"""Notes: ONE write per sitting, and everything else is a query.

A sitting is read once, while its meaning is still visible (a joke, a what-if, something relayed by someone else), and written as dated notes: subject, the
life area it touches (a fixed shared list: the headings), how sure the person was, the day it concerns, a key for standing facts, and their own words. No other
pass re-reads the same material. Patterns are the number of distinct sittings an area appears in, counted in code; a person's card is the notes about them;
current facts are the latest note per key; "things worth asking" is a query. The companion (the persona) decides what to do with them: Cortex serves what was
said, when, and how sure they were, never an instruction. Understanding here is lossy and revisable by design: a reading can be wrong, and the person's
correction simply supersedes it.

Rules the code enforces (not model obedience): areas and certainties come from fixed lists; a `stated` note whose quote is not in the person's own lines is
stored as `unclear`; relative time words are refused once and re-asked (every rendered note also carries the date of its sitting); a later note with the same
subject and key replaces the earlier one; `resolves` closes an open intention only by its id.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Sequence, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.note import Note

logger = logging.getLogger(__name__)

AREAS: Dict[str, str] = {
    "identity": "who someone is: age, birthday, where they live, employer, family role",
    "preferences": "likes, dislikes, values, beliefs, boundaries, how they want the companion to talk to them, things they asked not to be raised",
    "sleep-energy": "sleep, tiredness, exhaustion, being awake late",
    "body-health": "pain, injury, illness, physio, medical matters (for the person or someone close)",
    "exercise": "running, climbing, walking for fitness, training",
    "food": "meals, cooking, eating",
    "mood-stress": "feeling low, stressed, anxious, relieved, proud",
    "work-load": "how much work there is, deadlines, long hours, work spilling into other time",
    "work-boundary": "limits on work, leaving on time, protecting evenings, skipping things for work",
    "work-people": "colleagues, manager, clients, conflicts or praise at work",
    "career-direction": "jobs, applying, portfolio, wanting to change work",
    "money": "rent, costs, income, spending",
    "home": "housing, flat, repairs, belongings, moving",
    "pets": "a dog or other pet",
    "family-parents": "mother, father, their health, living situation or death",
    "family-siblings": "sister or brother, their children",
    "partner": "dating, a partner, a relationship",
    "friends": "friends, social plans, social obligations",
    "past-relationships": "an ex, their wedding, old relationships",
    "grief-memory": "bereavement, anniversaries, remembering someone",
    "aspiration": "daydreams, wishes, things they would like to make or become",
    "goals-plans": "stated intentions, things they mean to do or enter",
    "decisions": "an undecided choice, waiting to decide",
    "nature-outdoors": "time outdoors, nature, weather, walks for the pleasure of it, animals seen",
    "reading-culture": "books, music, films, making things",
    "other": "none of the above",
}
LABELS: Dict[str, str] = {
    "sleep-energy": "sleep and energy", "body-health": "health and pain", "mood-stress": "mood and stress", "work-load": "work load", "work-boundary": "limits on work",
    "money": "money", "aspiration": "wishes and daydreams", "nature-outdoors": "time outdoors", "exercise": "exercise", "goals-plans": "plans",
}
CERTAINTIES = ("stated", "intention", "hypothetical", "hearsay", "unclear")
SELF = "the person"
_SELF_WORDS = {"the person", "person", "the user", "user", "the user themself", "they", "them", "he", "she", "i", "me", "myself", "self"}
STRAIN = ("sleep-energy", "mood-stress", "work-load", "body-health", "money")     # areas where coming up again and again is worth a gentle question
RECURRING_MIN = 3
MAX_NOTES = 14
RECENT_DAYS = 45
INTENTION_LINES = 12


def models() -> List[str]:
    return [m.strip() for m in os.getenv("MEMORY_NOTES_MODELS", "qwen/qwen3.8-27b").split(",") if m.strip()]


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(s or "").lower()).strip()


def subject_key(subject: str) -> str:
    n = norm(subject)
    return SELF if n in _SELF_WORDS else n


def fmt_day(d: Optional[datetime]) -> str:
    return "" if d is None else f"{d.strftime('%a')} {d.day} {d.strftime('%b')}"


SYSTEM = """You write the notes a companion keeps after one conversation with one person: what a close friend would want to remember the next time they talk, including small things (how they felt today, what they plan, something they keep saying and never do). Skip only pleasantries and chatter that says nothing about them. Reply with ONE JSON object: {"notes": [{"subject": "...", "area": "...", "certainty": "...", "when": "...", "key": "...", "text": "...", "quote": "...", "resolves": "..."}]}

- subject: who the note is about: "the person" for the person you are talking with, otherwise the name used for someone else, a pet, a place or a project. When a note is mainly about another person that person is the subject ("Mum's knee has been bad" has subject Mum). The first time someone is named or described by relationship (my mum, my friend Morgan), also write a note whose subject is that person, with key relationship_to_the_person, saying who they are to the person.
- area: exactly one of these, by what the note is about whatever the wording:
%s
- certainty: "stated" (they said it is so or happened), "intention" (they hope, plan or mean to), "hypothetical" (a joke, a what-if, a passing fantasy said lightly), "hearsay" (someone else said or relayed it: say who in the text), or "unclear".
- when: the date the note concerns as YYYY-MM-DD if it is about a particular day (work it out from today's date and weekday), otherwise "".
- key: for a standing fact that could later change (birthday, residence, employer, relationship_to_the_person, living_situation) a short snake_case key, reusing a key from "known" for the same subject if it is the same fact; otherwise "".
- text: one plain sentence that keeps how sure or serious they were. Never use relative time words (tomorrow, yesterday, last year, this morning, tonight): use dates or a month.
- quote: a short phrase copied exactly from what THEY said.
- resolves: only if they say something listed under "open intentions" has now happened, was dropped or changed: that item's id. Otherwise "".

Rules: only what the person said, never what the companion said or guessed. How two other people are related is a note only if the person said it; if they did not, do not guess it. Do not turn a hypothetical into an intention or a relayed remark into a fact about the person it concerns. No diagnoses, no motives, no character labels. A thing they must do or an appointment is still a note (a separate ledger handles follow-through). Up to %d notes. Even a very short conversation usually gives one or two.""" % ("\n".join(f"  - {k}: {v}" for k, v in AREAS.items()), MAX_NOTES)


# ------------------------------------------------------------------ write ----

def _first_json(text: str) -> Optional[Dict[str, Any]]:
    t = re.sub(r"^```(?:json)?|```$", "", str(text or "").strip(), flags=re.M).strip()
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    try:
        v = json.loads(t[i:j + 1])
        return v if isinstance(v, dict) else None
    except ValueError:
        return None


def _parse_day(v: Any) -> Optional[datetime]:
    try:
        return datetime.strptime(str(v or "").strip()[:10], "%Y-%m-%d")
    except ValueError:
        return None


def clean(raw: Any, person_text: str) -> Tuple[List[Dict[str, Any]], Dict[str, int]]:
    """Validate what the model wrote. Nothing is repaired or guessed: a note either passes with its flags set or is dropped (and counted)."""
    stats = {"dropped": 0, "downgraded": 0, "unverified_quotes": 0}
    out: List[Dict[str, Any]] = []
    hay = norm(person_text)
    seen: set = set()
    for n in (raw if isinstance(raw, list) else [])[:MAX_NOTES * 2]:
        if not isinstance(n, dict) or not str(n.get("text") or "").strip():
            stats["dropped"] += 1
            continue
        text = str(n["text"]).strip()[:300]
        sig = norm(text)
        if sig in seen:
            stats["dropped"] += 1
            continue
        seen.add(sig)
        area = str(n.get("area") or "").strip().lower()
        certainty = str(n.get("certainty") or "").strip().lower()
        certainty = certainty if certainty in CERTAINTIES else "unclear"
        quote = str(n.get("quote") or "").strip().strip("\"'“”")[:200]
        verified = bool(quote) and len(norm(quote)) >= 4 and norm(quote) in hay
        if quote and not verified:
            stats["unverified_quotes"] += 1
            quote = ""
        if certainty == "stated" and not verified:
            certainty = "unclear"                                  # a stated note needs the person's own words behind it
            stats["downgraded"] += 1
        subject = str(n.get("subject") or "").strip()[:80] or SELF
        out.append({"subject": SELF if subject_key(subject) == SELF else subject, "subject_key": subject_key(subject),
                    "area": area if area in AREAS else "other", "certainty": certainty, "when_on": _parse_day(n.get("when")),
                    "key": re.sub(r"[^a-z0-9_]+", "_", str(n.get("key") or "").strip().lower()).strip("_")[:40],
                    "text": text, "quote": quote, "quote_verified": verified, "resolves": str(n.get("resolves") or "").strip()[:12]})
        if len(out) >= MAX_NOTES:
            break
    return out, stats


def relative_problems(notes: Sequence[Dict[str, Any]]) -> List[int]:
    from src.services.world_agent import relative_time_problem
    return [i for i, n in enumerate(notes) if relative_time_problem(n["text"])]


async def known_block(db: AsyncSession, ws: str, owner: str) -> Tuple[Dict[str, List[str]], List[Dict[str, str]]]:
    """What the writer is shown so it reuses keys and can close an intention: (subject -> keys, open intentions with short ids)."""
    rows = list((await db.execute(select(Note).where(Note.honcho_workspace_id == ws, Note.owner_peer_id == owner, Note.status == "current")
                                  .order_by(Note.sitting_on.desc(), Note.created_at.desc()).limit(600))).scalars().all())
    keys: Dict[str, List[str]] = {}
    for r in rows:
        if r.key and r.key not in keys.setdefault(r.subject, []):
            keys[r.subject].append(r.key)
    opens = [{"id": str(r.id)[:8], "text": r.text[:140], "since": fmt_day(r.sitting_on)} for r in rows if r.certainty == "intention"][:INTENTION_LINES]
    return keys, opens


async def write(db: AsyncSession, *, workspace_id: str, owner: str, product: str, session_id: str, run_id: Optional[UUID], transcript: str,
                person_label: str, companion_name: str, session_day: datetime, weekday: str, source: str = "session") -> Dict[str, Any]:
    """Read one sitting once and store its notes. Fail-open for the caller (a failure here never costs the session its other results)."""
    from src.services import memory_pipeline as mp
    from src.services.world_agent import _person_lines
    keys, opens = await known_block(db, workspace_id, owner)
    prompt = (f"{SYSTEM}\n\nToday is {session_day.date().isoformat()} ({weekday}).\nThe person's lines begin with \"{person_label}:\" and the companion's ({companion_name}) with \"{companion_name}:\".\n"
              f"Known so far (subject: keys): {json.dumps(keys, separators=(',', ':'))}\nOpen intentions: {json.dumps(opens, separators=(',', ':'))}\n\n--- conversation ---\n{transcript}")
    out = await mp._generate("notes", prompt, 3500, models())
    parsed = _first_json((out or {}).get("text") or "")
    if parsed is None:
        return {"status": "no_output", "model": (out or {}).get("model")}
    person_text = _person_lines(transcript, person_label)
    notes, stats = clean(parsed.get("notes"), person_text)
    retried = False
    bad = relative_problems(notes)
    if bad:
        retried = True
        fix = await mp._generate("notes-fix", (f"Today is {session_day.date().isoformat()} ({weekday}). Rewrite ONLY the text of these notes so none uses a relative time word "
                                               "(tomorrow, yesterday, last year, this morning, tonight, next week...): use the date or the month instead, and keep everything else. "
                                               'Reply with ONE JSON object: {"fixed": [{"i": 0, "text": "..."}]}\n\n' + json.dumps([{"i": i, "text": notes[i]["text"]} for i in bad])),
                                 1500, models())
        for f in (_first_json((fix or {}).get("text") or "") or {}).get("fixed") or []:
            try:
                i = int(f.get("i"))
                if i in bad and str(f.get("text") or "").strip():
                    notes[i]["text"] = str(f["text"]).strip()[:300]
            except (TypeError, ValueError):
                continue
    stats["still_relative"] = len(relative_problems(notes))
    stored = 0
    open_by_prefix = {o["id"]: o for o in opens}
    for n in notes:
        row = Note(honcho_workspace_id=workspace_id, owner_peer_id=owner, product=product, run_id=run_id, session_id=session_id, sitting_on=session_day,
                   subject=n["subject"], subject_key=n["subject_key"], area=n["area"], certainty=n["certainty"], when_on=n["when_on"], key=n["key"], text=n["text"],
                   quote=n["quote"], quote_verified=n["quote_verified"], source=source)
        db.add(row)
        await db.flush()
        stored += 1
        if n["key"] and n["certainty"] in ("stated", "intention"):
            for old in (await db.execute(select(Note).where(Note.honcho_workspace_id == workspace_id, Note.owner_peer_id == owner, Note.subject_key == n["subject_key"],
                                                            Note.key == n["key"], Note.status == "current", Note.id != row.id))).scalars().all():
                old.status, old.replaced_by_id = "superseded", row.id
        if n["resolves"] and n["resolves"] in open_by_prefix:
            for old in (await db.execute(select(Note).where(Note.honcho_workspace_id == workspace_id, Note.owner_peer_id == owner, Note.certainty == "intention",
                                                            Note.status == "current"))).scalars().all():
                if str(old.id).startswith(n["resolves"]) and old.id != row.id:
                    old.status, old.replaced_by_id = "resolved", row.id
    await db.commit()
    return {"status": "ok", "model": (out or {}).get("model"), "notes": stored, "retried": retried, **stats}


# ------------------------------------------------------------------ views ----
# Read-only. No model runs here. Every note shown carries the date of its sitting, so a stored word can never be read as "now".

async def _current(db: AsyncSession, ws: str, owner: str, days: Optional[int] = None, today: Optional[date] = None) -> List[Note]:
    q = select(Note).where(Note.honcho_workspace_id == ws, Note.owner_peer_id == owner, Note.status == "current")
    if days and today:
        q = q.where(Note.sitting_on >= datetime(today.year, today.month, today.day) - timedelta(days=days))
    return list((await db.execute(q.order_by(Note.sitting_on, Note.created_at))).scalars().all())


def canon_subjects(rows: Sequence[Note]) -> Dict[str, str]:
    """subject_key -> canonical key: 'morgan' joins 'morgan ellis' when exactly one longer name starts with it. A nomination for grouping, nothing more."""
    keys = sorted({r.subject_key for r in rows if r.subject_key and r.subject_key != SELF})
    longer = [k for k in keys if " " in k]
    out = {k: k for k in keys}
    for k in keys:
        if " " not in k:
            hits = [m for m in longer if m.split()[0] == k]
            if len(hits) == 1:
                out[k] = hits[0]
    return out


def _line(r: Note) -> Dict[str, Any]:
    return {"date": fmt_day(r.sitting_on), "text": r.text, "certainty": r.certainty, "area": r.area, **({"about": fmt_day(r.when_on)} if r.when_on else {}),
            **({"quote": r.quote} if r.quote else {})}


async def people(db: AsyncSession, ws: str, owner: str) -> List[Dict[str, Any]]:
    rows = await _current(db, ws, owner)
    canon = canon_subjects(rows)
    by: Dict[str, List[Note]] = {}
    for r in rows:
        if r.subject_key and r.subject_key != SELF:
            by.setdefault(canon.get(r.subject_key, r.subject_key), []).append(r)
    out = []
    for k, rs in by.items():
        facts = [r for r in rs if r.key == "relationship_to_the_person"] or [r for r in rs if r.area in ("identity", "family-parents", "family-siblings", "partner", "friends") and r.certainty == "stated"]
        latest = rs[-1]
        out.append({"name": max((r.subject for r in rs), key=len), "notes": len(rs), "sittings": len({r.sitting_on for r in rs}), "first_seen": fmt_day(rs[0].sitting_on),
                    "last_seen": fmt_day(latest.sitting_on), "line": (facts[-1] if facts else latest).text[:140], "_last": latest.sitting_on})
    out.sort(key=lambda x: (x["_last"], x["notes"]), reverse=True)
    for o in out:
        o.pop("_last")
    return out


async def card(db: AsyncSession, ws: str, owner: str, subject: str) -> Dict[str, Any]:
    rows = await _current(db, ws, owner)
    canon = canon_subjects(rows)
    want = subject_key(subject)
    want = canon.get(want, want)
    rs = [r for r in rows if (canon.get(r.subject_key, r.subject_key) == want)]
    facts = {r.key: _line(r) for r in rs if r.key and r.certainty in ("stated", "intention")}
    by_area: Dict[str, List[Dict[str, Any]]] = {}
    for r in rs:
        by_area.setdefault(r.area, []).append(_line(r))
    return {"subject": subject, "notes": len(rs), "current_facts": facts, "by_area": {a: l[-4:] for a, l in sorted(by_area.items())},
            "open_intentions": [_line(r) for r in rs if r.certainty == "intention"][-6:]}


async def recurring(db: AsyncSession, ws: str, owner: str, today: date, minimum: int = RECURRING_MIN) -> List[Dict[str, Any]]:
    """Areas of the person's own life that come up in `minimum` or more distinct sittings: a count, with the dated lines. Nothing is concluded."""
    rows = [r for r in await _current(db, ws, owner, RECENT_DAYS, today) if r.subject_key == SELF and r.certainty in ("stated", "intention") and r.area not in ("other", "identity", "preferences")]
    by: Dict[str, List[Note]] = {}
    for r in rows:
        by.setdefault(r.area, []).append(r)
    out = []
    for area, rs in by.items():
        days = sorted({r.sitting_on for r in rs})
        if len(days) >= minimum:
            out.append({"area": area, "label": LABELS.get(area, area), "sittings": len(days), "since": fmt_day(days[0]), "lines": [_line(r) for r in rs][-6:]})
    out.sort(key=lambda x: (-x["sittings"], x["area"]))
    return out


def _stems(text: str) -> set:
    stop = {"the", "and", "for", "with", "that", "this", "they", "their", "them", "have", "has", "had", "was", "were", "about", "would", "could", "person", "when", "than", "then", "also", "from", "into"}
    return {w for w in norm(text).split() if len(w) >= 4 and w not in stop}


def _meet(a: set, b: set) -> bool:
    return any(x == y or x.startswith(y) or y.startswith(x) for x in a for y in b if min(len(x), len(y)) >= 4)


async def asks(db: AsyncSession, ws: str, owner: str, today: date) -> List[Dict[str, Any]]:
    """Things worth asking about, from what was already said. Two kinds, both plain queries: (1) a strain area that keeps coming up (sleep, stress, work load,
    pain, money) in 3+ sittings; (2) something said lightly as a wish or what-if that has come back in a later sitting. Facts and dates only: whether and how to ask is
    the persona's call."""
    rows = [r for r in await _current(db, ws, owner, RECENT_DAYS, today) if r.subject_key == SELF]
    out: List[Dict[str, Any]] = []
    for r in await recurring(db, ws, owner, today):
        if r["area"] in STRAIN:
            out.append({"kind": "recurring", "area": r["area"], "sittings": r["sittings"], "text": f"{r['label'].capitalize()} has come up in {r['sittings']} conversations since {r['since']}: "
                        + "; ".join(l["text"].rstrip(".") + f" ({l['date']})" for l in r["lines"][-3:])})
    hypo = [r for r in rows if r.certainty == "hypothetical" and r.area in ("aspiration", "goals-plans", "career-direction", "home", "reading-culture")]
    for h in hypo:
        later = [r for r in rows if r.sitting_on > h.sitting_on and r.id != h.id and r.certainty in ("stated", "intention", "hypothetical") and _meet(_stems(h.text), _stems(r.text))]
        if later:
            days = sorted({r.sitting_on for r in later} | {h.sitting_on})
            out.append({"kind": "returning", "area": h.area, "sittings": len(days), "text": f"{h.text.rstrip('.')} ({fmt_day(h.sitting_on)}) has come back since: "
                        + "; ".join(r.text.rstrip(".") + f" ({fmt_day(r.sitting_on)})" for r in later[-2:])})
    seen: set = set()
    uniq = []
    for o in out:
        k = o["text"][:60]
        if k not in seen:
            seen.add(k)
            uniq.append(o)
    return uniq


async def recent(db: AsyncSession, ws: str, owner: str, today: date, days: int = 14) -> List[Dict[str, Any]]:
    rows = [r for r in await _current(db, ws, owner, days, today) if r.certainty in ("stated", "hearsay") and r.area not in ("other",)]
    return [{**_line(r), "subject": r.subject} for r in rows][-40:]


async def inspect(db: AsyncSession, ws: str, owner: str) -> Dict[str, Any]:
    rows = list((await db.execute(select(Note).where(Note.honcho_workspace_id == ws, Note.owner_peer_id == owner).order_by(Note.sitting_on, Note.created_at))).scalars().all())
    return {"notes": [{"id": str(r.id)[:8], "sitting": r.sitting_on.date().isoformat(), "subject": r.subject, "area": r.area, "certainty": r.certainty, "when": r.when_on.date().isoformat() if r.when_on else "",
                       "key": r.key, "status": r.status, "quote_verified": r.quote_verified, "text": r.text, "quote": r.quote, "source": r.source} for r in rows]}


async def ask_candidates(db: AsyncSession, ws: str, owner: str, today: date) -> List[Dict[str, Any]]:
    """The same asks as packet candidates (opportunities.py): plain facts about what keeps coming up, with their dates."""
    out = []
    for a in await asks(db, ws, owner, today):
        out.append({"id": f"notes:{a['kind']}:{a['area']}", "text": a["text"], "when": "", "said": "", "asked": "", "source": "notes", "ref": a["area"],
                    "score": 2 + (1 if a["sittings"] >= 5 else 0), "sort": None})
    return out
