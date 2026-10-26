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

from sqlmodel import select

from src.models.known_world import KnownLink
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
    background: List[Dict[str, Any]] = []
    people: List[str] = []
    private_keys: set = set()          # ledger keys that belong to a private matter
    private_stems: List[set] = []      # word stems of private entities, to catch the same matter written up separately in the ledger

    if world_on:
        entities = await known_world.list_all(db, ws, owner, statuses=("active",), limit=300)
        sensitive_ids = {e.id for e in entities if e.sensitive and not e.suppressed}
        private_stems = [_stems(f"{e.name} {e.summary}") for e in entities if e.id in sensitive_ids]
        if sensitive_ids:
            links = (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner,
                                                              KnownLink.target_kind == "ledger", KnownLink.status == "current"))).scalars().all()
            private_keys = {str(l.target_ref) for l in links if l.from_entity_id in sensitive_ids}
        for e in entities:
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
                cands.append({"id": f"world:{e.id}", "text": str(e.name), "when": relative_label(od, today) if od else "", "private": bool(e.sensitive),
                              "source": "world", "ref": str(e.id), "score": sig + (1 if od and 0 <= (today - od.date()).days <= PAST_DAYS else 0), "sort": od})
            else:
                background.append({"id": f"world:{e.id}", "text": str(e.name), "source": "world", "ref": str(e.id), "private": bool(e.sensitive)})

    for r in ledger_rows or []:
        if r.status not in ("open", "waiting", "watching"):
            continue
        ed = _day(r.expected_date, tz)
        imp = int(r.importance or 1)
        # Sensitivity belongs to the MATTER, not to the record that happens to hold it: a ledger row linked to a private entity, or sharing a distinctive word (five letters or
        # more) with one, is private too. A false positive only makes the item gentler, which is the safe direction.
        is_private = str(r.situation_key) in private_keys or any({w for w in _stems(str(r.title)) if len(w) >= 5} & {w for w in ps if len(w) >= 5} for ps in private_stems)
        if ed is not None and -PAST_DAYS <= (ed.date() - today).days <= LEDGER_AHEAD_DAYS and (imp >= 2 or 0 <= (ed.date() - today).days <= 1):      # low-importance matters count only when imminent, never after the fact
            cands.append({"id": f"ledger:{r.situation_key}", "text": str(r.title), "when": relative_label(ed, today), "private": is_private, "source": "ledger",
                          "ref": str(r.situation_key), "score": max(imp, 2) + (1 if abs((ed.date() - today).days) <= 2 else 0), "sort": ed})
        else:
            background.append({"id": f"ledger:{r.situation_key}", "text": str(r.title), "source": "ledger", "ref": str(r.situation_key), "private": is_private})

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
        parts.append("Possible opportunities (each is optional: raise one lightly, offer help, or hold it):\n" + "\n".join(
            f"- {c['text']}" + (f" [{c['when']}]" if c["when"] else "") + ("  (private: acknowledge lightly, do not probe)" if c["private"] else "") for c in top))
    if bg or people:
        parts.append("Background (use only if the person goes there; do not raise unprompted): " + "; ".join(bg + ([f"people: {', '.join(people[:5])}"] if people else [])))
    return {"text": "\n\n".join(parts), "candidates": [{k: v for k, v in c.items() if k != "sort"} for c in top], "background": bg, "background_items": bg_items,
            "people": people[:8], "now": now.isoformat(), "time_zone": ctx.tz}


# ----------------------------------------------------------------------------------------------------------------------------------------------------------
# The packet contract (version 1). ONE shape, whether a packet is built on demand now or prepared ahead of time later. A packet is a temporary piece of
# attention, never part of the companion's prompt or personality. Retiring a PACKET (its items were used, or the conversation moved on) is not retiring the
# MATTER: "he is having surgery next Thursday" keeps the matter alive and may prepare a new opportunity; "he's fine now" may resolve it. The matter's life
# cycle belongs to the ledger and the world records, not to exposure.
# ----------------------------------------------------------------------------------------------------------------------------------------------------------
PACKET_VERSION = 1
USAGE = ("Optional. Not a script and not an instruction: raise an item lightly, offer help with it, hold it, or ignore it. "
         "Do not keep returning to an item once it has been dealt with. If the person asks for help with something, help with that first.")
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


STANCES = ("gentle", "forward")


def _render(items: List[Dict[str, Any]], purpose: str, stance: str = "gentle") -> str:
    """Wording matters as much as selection (measured, H13: the same opening item was taken in 6 of 24 cases with 'optional' wording and 22 of 24 with 'natural to
    mention' wording, but the stronger wording also pushed a private matter in 7 of 8 cases). So the stance is a per-product setting, and a private item is ALWAYS
    given the gentle, do-not-probe wording whatever the stance."""
    if not items:
        return ""
    forward = stance == "forward" and purpose in ("reconnect", "touched")
    head_open = {"reconnect": "Possible opportunity (optional: raise it lightly, or not):",
                 "touched": "Things the person's words touch (use only if natural; each is optional):",
                 "task_support": "Relevant to what the person asked for (optional):",
                 "survey": "Possible opportunities (each is optional: raise one lightly, offer help, or hold it):"}[purpose]
    head_forward = ("Worth attention now: something you would naturally ask about or mention if the moment is right (a light touch, never a script; leave it "
                    "only if the person is clearly occupied or it would intrude):")
    head_private = "Private (acknowledge lightly at most; do not probe, and do not open with specifics):"

    def line(i: Dict[str, Any]) -> str:
        return f"- {i['text']}" + (f" [{i['when']}]" if i.get("when") else "")
    plain = [i for i in items if not i.get("private")]
    private = [i for i in items if i.get("private")]
    out = []
    if plain:
        out.append((head_forward if forward else head_open) + "\n" + "\n".join(line(i) for i in plain))
    if private:
        out.append(head_private + "\n" + "\n".join(line(i) for i in private))
    return "\n\n".join(out)


def build_packet(out: Dict[str, Any], *, stage: str = "opening", user_text: str = "", task: Optional[bool] = None, used: Optional[List[str]] = None,
                 valid_minutes: Optional[int] = None, stance: str = "gentle") -> Dict[str, Any]:
    """Select the small packet for this moment from what `read` found. Deterministic. Empty items means: give the companion nothing.
    stage: opening (re-entry: the single top opportunity), moment (only items the person's own words touch; relational items withheld during a task),
    survey (everything, the older single-block shape). `used` are item ids already used in this conversation (packet retirement, not matter retirement)."""
    from datetime import datetime as _dt, timedelta as _td
    used_set = set(used or [])
    cands = [c for c in out.get("candidates", []) if c["id"] not in used_set]
    bg = [b for b in out.get("background_items", []) if b["id"] not in used_set]
    is_task = looks_like_task(user_text) if task is None else bool(task)

    def item(x: Dict[str, Any], kind: str) -> Dict[str, Any]:
        return {"id": x["id"], "kind": kind, "text": x["text"], "when": x.get("when", ""), "private": bool(x.get("private")),
                "stakes": int(x.get("score", 1)), "source": {"system": x["source"], "ref": x["ref"]}}

    if stage == "opening":
        purpose, items = "reconnect", [item(c, "opportunity") for c in cands[:1]]
    elif stage == "moment":
        touched = _stems(user_text)
        pool = [(c, "opportunity") for c in cands] + [(b, "background") for b in bg]
        hits = [(x, k) for x, k in pool if touched & _stems(x["text"])]
        purpose, items = ("task_support" if is_task else "touched"), [item(x, k) for x, k in hits[:2]]
    else:
        purpose, items = "survey", [item(c, "opportunity") for c in cands] + [item(b, "background") for b in bg]
    built = _dt.fromisoformat(out["now"])
    minutes = valid_minutes if valid_minutes is not None else (360 if stage == "opening" else 30)
    import hashlib
    pid = hashlib.sha1((out["now"] + stage + "|".join(i["id"] for i in items)).encode()).hexdigest()[:12]
    return {"version": PACKET_VERSION, "id": pid, "stage": stage, "purpose": purpose, "built_at": built.isoformat(), "valid_until": (built + _td(minutes=minutes)).isoformat(),
            "stance": stance if stance in STANCES else "gentle", "items": items, "text": _render(items, purpose, stance if stance in STANCES else "gentle"), "usage": USAGE,
            "retire": {"packet": "when its items have been used, or the conversation moves on",
                       "matter": "never by use alone: only when the matter itself resolves (ledger status, or the person says it is settled)"}}
