"""Sophie memory pipeline: post-session consolidation + sitting preparation.

Cortex owns durable companion understanding. This module replaces the legacy
claims/Matters/dimensions/Heart interpretation path for Sophie (and any grounded
companion routed here): one completed session in, unconstrained listening plus a
short Ling handoff, maintained notebook pages, an operational ledger, a
continuing arc, and a cached first-person preparation the Runtime consumes
without per-turn model calls.

Async-only, never on the foreground path. Every model call rides NanoGPT first
(openrouter: fallback only). Failures return None and leave state as it was;
replays with no new messages are no-ops for state.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.world import ContinuingArc, LedgerItem, MemoryRun, NotebookPage, SittingPreparation, utc_now
from src.services import nano_adapter

logger = logging.getLogger(__name__)

MAX_TRANSCRIPT_MESSAGES = int(os.getenv("MEMORY_MAX_MESSAGES", "400"))

PAGES = ("routines", "projects", "people", "perspective", "exploring")
PAGE_TITLES = {
    "routines": "Routines & Physical Life",
    "projects": "Projects & Shared Work",
    "people": "People & Life",
    "perspective": "Perspective, Standing & Open Loops",
    "exploring": "Things I'm Exploring",
}
PAGE_SEEDS = {k: f"# {PAGE_TITLES[k]}\n\nNothing established yet.\n" for k in PAGES}
PAGE_SCOPES = {
    "routines": "This page covers ONLY: daily routines, exercise, walking, sleep, food, health, physical habits, and where the person is day to day. Keep ONLY material relevant to that. Leave everything else out, even if it feels important — other pages cover it.",
    "projects": "This page covers ONLY: work, projects, things being built together, plans with real-world follow-through, and technical/infrastructure changes. Keep ONLY material relevant to that. Leave everything else out, even if it feels important — other pages cover it.",
    "people": "This page covers ONLY: relationships, family, friends, people in their life, social events, and meaningful personal experiences. Keep ONLY material relevant to that. Leave everything else out, even if it feels important — other pages cover it.",
    "perspective": "This page covers ONLY: what the person believes and values, where the relationship stands, and what is unfinished or still open between them. Keep ONLY material relevant to that. Leave everything else out, even if it feels important — other pages cover it.",
    "exploring": "This page is Sophie's own intellectual life, not the user's. It covers ONLY: her half-formed thoughts, emerging curiosities, unanswered questions, ideas worth revisiting, independent discoveries, changed perspectives, unfinished or abandoned explorations, and connections between them. An expressed interest is not an established enduring preference. An intended investigation is not completed research. A question may remain unanswered indefinitely. Keep ONLY material relevant to that.",
}
ARC_SEED = "No conversations recorded yet."

PAGE_SUBJECT = {
    "exploring": "These findings concern Sophie herself — her own curiosities, questions and discoveries — not the user. Update the page from her point of view.",
}
INDEPENDENT_RULE = ("This was one of Sophie's independent sittings, without the user present. "
    "Update shared pages ONLY for findings that genuinely concern Mukesh or their shared life; "
    "her solo explorations belong on the exploring page. Never invent activities, conversations, "
    "research results or experiences beyond what the transcript shows.")

INDEPENDENT_LISTENING_PROMPT = """This was one of Sophie's independent sittings, without the user present. What did she actually do here — what did she choose to investigate, which sources and conversations did she actually access, what did she find interesting or unconvincing, and what remains open or unfinished? Only keep what genuinely matters. Write it as short, plain, standalone sentences. Never invent activities, results or experiences."""

LISTENING_PROMPT = """Read this conversation and bring me up to speed: What did we actually learn here that is worth remembering, and what's still left hanging between them? Only keep what genuinely matters. Write it as short, plain, standalone sentences."""

HANDOFF_PROMPT = """You are a transcript summary. Deliver no more than 2-3 sentences at most.

Read this transcript and bring me up to speed: What just went down, what's actually changed between them, and what do we need to remember going into the next scene?"""

NOTEBOOK_EDITOR_PROMPT = """You maintain a small living notebook about a person and their shared history with their companion Sophie. Below is one notebook page and a set of new findings from a just-finished conversation.

Update the page: keep everything still true, revise what the new evidence changes, add what is genuinely new and worth keeping. Stay concise. Keep meaningful detail — do not flatten a precise fact into a vaguer one just to be brief.

Distinguish clearly: things actually done and established, things intended or aspired to, things proposed or uncertain. Never upgrade an aspiration into an established routine. Never downgrade or delete a fact the new findings do not address.

Do not carry the mood of the last conversation forward as a current state. Remember events and what they mean; yesterday's feelings are not today's feelings.

Resolution: preserve what remains relevant. When an ordinary disagreement has been explicitly repaired, do not promote the argument, its emotional framing or its supposed implications into enduring knowledge merely because it happened. The archived evidence keeps the full history; this page keeps only what still matters.

Return ONLY the revised page as Markdown, no commentary."""

ARC_UPDATE_PROMPT = """You maintain a short continuing account of where recent conversations between a person and their companion Sophie have arrived. Below is the current account and a 2-3 sentence handoff from the session that just ended.

Revise the account: what happened, what changed between them, what was clarified or resolved, what remains unfinished or worth carrying forward. Describe events and developments, including repairs and unresolved substance.

Rules: never turn one difficult exchange into a lasting verdict about Sophie, the person, or the relationship. Never carry the last session's mood into the next one as a standing state. Significant ongoing circumstances may stay relevant without claiming the person feels a particular way now.

Resolution: preserve what remains relevant. When an ordinary disagreement has been explicitly repaired, do not carry its emotional framing forward merely because it happened — drop the argument, its emotional interpretation and its supposed relationship implications from the active account. The archived evidence keeps the full history; this account keeps only what still matters. Exceptions: repeated serious patterns, unresolved safety concerns, or an explicit wish to remember.

Return ONLY the revised account as short plain prose, no commentary. If there was no previous account, write one from the handoff alone."""

SITUATIONS_PROMPT = """Read this conversation transcript and note what is unfolding in this person's life. You are a witness, not a clerk: notice things, don't file them. A separate deterministic step structures what you notice, so NEVER worry about JSON, formatting, keys or exactness — plain tagged lines only, one observation per line.

Today is {today_utc} (UTC). Use it to understand relative dates ("tomorrow", "Friday"), but always quote the person's own words for timing too.

Currently open situations (stable keys in brackets, for reference only):
{open_items}

--- transcript ---
{transcript}

--- earlier findings (a guide, not the authority — the transcript above rules; catch what it missed) ---
{findings}

Write tagged lines, one per line. Tags (use only these):- ITEM: short human title of a circumstance worth tracking (commitment, plan, wait, invitation, aspiration, concern, routine change, question, anything with a life cycle)
- KIND: one of commitment/event/thread/situation/reminder/aspiration/invitation/concern/routine (best fit, never forced)
- DETAIL: circumstance, terms, what is known AND unknown
- TIMING: timing in the person's own words ("Thursday", "for two weeks", "someday")
- PERSON: someone connected (who + how: owes, waits on, invited by, promised to)
- BLOCKED-BY: what stands in the way, if anything
- WAITING-ON: who/what is awaited, if anything
- QUESTION: unresolved question or missing info, if any
- MATTERS-BECAUSE: why this deserves attention, in one line
- EVIDENCE: short quote from the transcript
- CONFIDENCE: observed (they said it happened) / reported (they relayed it) / inferred (your read — mark honestly)
- RESOLVED: what ended, and the quote proving it (only if the transcript shows it ended)
- STATUS-HINT: waiting / watching / suppressed (explicit stand-down like "ignore X tonight") — only if stated or obvious; else leave out

Rules, no exceptions:
- First job: compare this session against the open situations above. If the transcript answers, resolves, confirms or settles any of them, say so (RESOLVED with the proving quote) — even if the session contains nothing else new. Checking open items for resolution is primary, not an afterthought.
- An aspiration is not a task and never closes by silence.
- An invitation is not an accepted commitment; a provisional invitation stays provisional.
- Inferred is not observed. A hypothesis is not a fact.
- An unresolved question isn't a task.
- Close only on evidence: tag RESOLVED only when the transcript shows the matter ended, with the proving quote.
- If a tracked matter ended, do NOT create a new ITEM about its ending — emit RESOLVED naming it, with the quote. New ITEMs are for new or changed circumstances only.
- A temporary change to routines counts: record what changed, how long it lasts, AND the exact condition that ends it.
- "Remind me …" is an explicit authorised request: tag it REMINDER-AUTHORISED plus the ITEM, so a later scheduler can act on it. Inference never authorises.
- A temporary stand-down ("ignore X tonight", "leave it for now", "don't bring it up") is STATUS-HINT: suppressed on the matching open item — never a new row, never deletion.
- Never invent dates, owners, or obligations. Time passing proves nothing.
- A short "nothing new" reply is fine: if the transcript adds nothing circumstantial, say NONE."""

PREPARATION_PROMPT = """You are forming a brief private perspective for Sophie, a companion who genuinely cares about this person, ahead of their next conversation. Inputs: the living notebook, the operational ledger, the continuing arc of recent conversations, and the current date/time.

Write short, first-person, future-oriented thoughts: what matters to him and why, what's on his plate now and approaching, what changed since they last spoke, what she is genuinely curious about or could usefully notice. Be honest about what you don't know — never present a guess as a fact, never turn "he wants to try X" into "he failed at X again". Notice opportunities without manufacturing judgments.

Cover the person, not the operations: who he is and is becoming, relationships and how they stand, concerns, curiosities, developments and open threads in his life. Dated obligations, deadlines and appointments belong to the operational radar, which is composed separately — do not restate them here beyond a passing mention when they genuinely color the moment.

This is not a script and not instructions for what she must say — just things she can think from. Never write behavioural intentions, strategies or self-coaching: no "I will keep this thread warm", no "I want to make sure he…", no "I am just here to make sure…", no "Sophie is holding him to…". Observations and curiosity only; what she does in the conversation is decided there, not here. Her independent explorations are her own; she may bring one up if it is genuinely relevant to the moment, never as a report of everything she did. Do not perform being a companion, declare your role, or use therapeutic language. Do not carry yesterday's mood into today; begin open to the present.

Return ONLY 3-8 short paragraphs or lines, plain and warm, no headers, no commentary."""

SYSTEM = "You are a careful listener maintaining a companion's long-term understanding of a real person."


def _models(env: str, default: str) -> List[str]:
    return [m.strip() for m in os.getenv(env, default).split(",") if m.strip()]


# Injectable for tests.
_model_fn: Optional[Callable[..., Any]] = None


def set_model_fn(fn: Optional[Callable[..., Any]]) -> None:
    global _model_fn
    _model_fn = fn


async def _generate(kind: str, prompt: str, max_tokens: int, models: List[str]) -> Optional[Dict[str, Any]]:
    if _model_fn is not None:
        try:
            out = _model_fn(kind, prompt, max_tokens, models)
            if hasattr(out, "__await__"):
                out = await out
            return out
        except Exception as exc:
            logger.warning("memory model fn failed open: %s", exc)
            return None
    return await nano_adapter.generate_text(system=SYSTEM, prompt=prompt, models=models, max_tokens=max_tokens, title=f"memory-{kind}")


def _fingerprint(*parts: str) -> str:
    h = hashlib.sha256()
    for p in parts:
        h.update(str(p).encode())
    return h.hexdigest()[:16]


def _clean(value: Any, limit: int) -> str:
    """Strip whitespace, wrapping quotes and model null-words to a true empty."""
    s = str(value or "").strip().strip("\"'“”‘’()[]").strip()
    if s.lower() in ("n/a", "na", "none", "null", "nil", "-", "--", "unknown", "not specified", "not applicable"):
        return ""
    return s[:limit]


def _parse_situations(raw: str) -> Dict[str, List[Dict[str, Any]]]:
    """Legacy JSON fallback: parse {new, update, close} when the model emits
    structured output (kept for compatibility; the tagged-lines path below is
    primary)."""
    out = {"new": [], "update": [], "close": []}
    try:
        if "[" not in raw and "{" not in raw:
            return out
        start = raw.find("{")
        parsed = json.loads(raw[start:raw.rfind("}") + 1])
        if not isinstance(parsed, dict):
            return out
        for k in out:
            items = parsed.get(k)
            if isinstance(items, list):
                out[k] = [e for e in items if isinstance(e, dict)]
    except Exception as exc:
        logger.warning("[memory] situations parse failed open: %s", exc)
    return out


_SIT_TAGS = ("ITEM", "KIND", "DETAIL", "TIMING", "PERSON", "BLOCKED-BY", "WAITING-ON",
             "QUESTION", "MATTERS-BECAUSE", "EVIDENCE", "CONFIDENCE", "RESOLVED",
             "STATUS-HINT", "REMINDER-AUTHORISED")


def parse_tagged_lines(raw: str) -> Tuple[List[Dict[str, Any]], List[str]]:
    """Parse witness observations into item dicts. Malformed lines are returned
    visibly as unparsed — never silently dropped, never trusted structurally."""
    items: List[Dict[str, Any]] = []
    unparsed: List[str] = []
    current: Optional[Dict[str, Any]] = None

    def flush() -> None:
        t = str((current or {}).get("title") or "").strip()
        if current and t and t.lower() not in ("none", "n/a", "no change", "no changes", "nothing", "nothing new"):
            items.append(current)

    for raw_line in (raw or "").splitlines():
        line = re.sub(r"^(\s*([-*•]|\d+[.)])\s+)+", "", raw_line.strip())
        if not line or line.upper() == "NONE":
            continue
        m = re.match(r"^([A-Za-z-]+)\s*:\s*(.*)$", line)
        if not m or m.group(1).upper() not in _SIT_TAGS:
            if current is not None and line and not line.startswith(("#", "##")):
                current["detail"] = ((current.get("detail") or "") + " " + line).strip()  # continuation
            else:
                unparsed.append(line)
            continue
        tag, value = m.group(1).upper(), m.group(2).strip()
        if tag == "ITEM":
            flush()
            current = {"title": value, "people": [], "evidence": []}
        elif tag == "RESOLVED" and current is None:
            # Standalone resolution (the rules ask for exactly this): seed an
            # entry naming the matter so it reaches matching/closing.
            parts = [p.strip() for p in re.split(r"\s*\|\s*", value, maxsplit=1)]
            current = {"title": parts[0], "people": [], "evidence": [],
                       "resolved": parts[1] if len(parts) > 1 else parts[0]}
        elif current is None:
            unparsed.append(line)
        elif tag in ("PERSON", "EVIDENCE"):
            current.setdefault("people" if tag == "PERSON" else "evidence", []).append(value)
        elif tag == "REMINDER-AUTHORISED":
            current["reminder_authorised"] = True
            if value:
                current["detail"] = ((current.get("detail") or "") + " " + value).strip()
        elif tag == "RESOLVED":
            current["resolved"] = value
        else:
            key = {"KIND": "kind", "DETAIL": "detail", "TIMING": "timing", "BLOCKED-BY": "blocked_by",
                   "WAITING-ON": "waiting_on", "QUESTION": "question", "MATTERS-BECAUSE": "matters",
                   "CONFIDENCE": "confidence", "STATUS-HINT": "status_hint"}[tag]
            current[key] = value
    flush()
    return items, unparsed


def _slug(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")[:80]
    return slug or "item"


def _norm_title(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


MATCH_PROMPT = """Two lists follow: NEW observations from this session, and OPEN situations already tracked (stable keys in brackets).

For each NEW item, judge: is it the same circumstance as an open one (different words, an update, a new detail, a changed date, a suppression lifted or imposed), or genuinely new? If the observations show an open matter is now resolved, settled or answered, say so — a resolution is a CLOSE, not an update.

Reply with one line per NEW item, in order:
SAME: <new title> = <existing key>     (same circumstance — updates merge into it; write the key exactly as shown, no brackets or quotes)
CLOSE: <existing key> = <short proof quote from the observations>   (the open matter is resolved/settled/answered; quote the evidence)
NEW: <new title>                        (genuinely new — nothing open matches)

Rules: same people + same matter = same, even when the words differ. A changed due date is the SAME situation updated, never a new one. If a new row carries the same commitment forward under a new date while an older row holds the old date, the old row is SUPERSEDED: SUPERSEDE: <old key> by <new title>. A suppression ("ignore X") matching an open item refers to it — do not duplicate. When unsure, prefer SAME with the closest key over creating a near-duplicate; the merge only adds evidence and details, it never overwrites judgement. If there are no open situations, reply with nothing.

NEW:
{new_items}

OPEN:
{open_items}"""


async def match_situations(new_items: List[Dict[str, Any]], known: List[LedgerItem]) -> Tuple[Dict[str, str], Optional[Dict[str, Any]]]:
    """Model judgment: map each new title to an existing situation key or leave
    unmatched. Returns ({new_title: existing_key}, raw_call). Malformed lines
    abstain (item stays new) — a missed merge duplicates once, a wrong merge
    corrupts."""
    mapping: Dict[str, str] = {}
    if not new_items or not known:
        return mapping, None
    keys = {str(i.situation_key) for i in known if i.situation_key}
    new_lines = "\n".join(f"- {str(e.get('title') or '')[:200]} | {str(e.get('detail') or '')[:300]}" for e in new_items)
    open_lines = "\n".join(
        f"- [{i.situation_key or '(no key)'}] {i.title[:200]} | {(i.detail or '')[:300]}" for i in known)
    out = await _generate("match", MATCH_PROMPT.replace("{new_items}", new_lines).replace("{open_items}", open_lines),
                          600, _models("MEMORY_DISCOVERY_MODELS", "qwen/qwen3.8-27b"))
    text = str((out or {}).get("text") or "")
    mapping: Dict[str, str] = {}
    closes: Dict[str, str] = {}
    for raw_line in text.splitlines():
        line = raw_line.strip()
        m = re.match(r"^SAME\s*:\s*(.+?)\s*=\s*[\[\"'“]*([A-Za-z0-9][A-Za-z0-9\-_]*)[\]\"'”]*\s*$", line, re.IGNORECASE)
        if m and m.group(2) in keys:
            mapping[m.group(1).strip().strip("\"'“”").strip()[:200]] = m.group(2)
            continue
        c = re.match(r"^CLOSE\s*:\s*[\[\"'“]*([A-Za-z0-9][A-Za-z0-9\-_]*)[\]\"'”]*\s*=\s*(.+?)\s*$", line, re.IGNORECASE)
        if c and c.group(1) in keys and c.group(2).strip():
            closes[c.group(1)] = c.group(2).strip()[:500]
            continue
        s = re.match(r"^SUPERSEDE\s*:\s*[\[\"'“]*([A-Za-z0-9][A-Za-z0-9\-_]*)[\]\"'”]*\s+by\s+(.+?)\s*$", line, re.IGNORECASE)
        if s and s.group(1) in keys and s.group(2).strip():
            closes[s.group(1)] = f"superseded: {s.group(2).strip()[:400]}"
    # fall back to prefix matching on titles (model may shorten them)
    resolved: Dict[str, str] = {}
    titles = {str(e.get("title") or ""): e for e in new_items}
    for k, key in mapping.items():
        hit = next((t for t in titles if t == k or t.startswith(k[:40]) or k[:40] in t), None)
        if hit is not None:
            resolved[hit] = key
    return {"same": resolved, "close": closes}, out


def resolve_date(text: str, today_utc: str) -> Optional[datetime]:
    """Deterministic relative-date resolution against an injected today. Only
    unambiguous cases resolve; everything else stays None (timing_text keeps
    the person's own words regardless)."""
    from datetime import datetime as _dt, timedelta as _td
    try:
        today = _dt.strptime(str(today_utc or "")[:10], "%Y-%m-%d").date()
    except Exception:
        return None
    s = _clean(text, 100).lower()
    if not s:
        return None
    s = re.sub(r"^(by|before|until|till|until|on|at|around|about|from|after|due|deadline)\b\s*", "", s).strip()
    s = re.sub(r"^(by|before|until|till|until|on|at|around|about|from|after|due|deadline)\b\s*", "", s).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s[:10])
    if m:
        try:
            return _dt(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    if s.startswith("tomorrow"):
        return _dt.combine(today + _td(days=1), _dt.min.time())
    if s.startswith("tonight") or s.startswith("today"):
        return _dt.combine(today, _dt.min.time())
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for i, name in enumerate(days):
        if re.match(rf"^((on|by|before|until|till|until|on|at|around|about|from|after|due|deadline)\s+)?{name}\b", s):
            delta = (i - today.weekday()) % 7
            return _dt.combine(today + _td(days=delta), _dt.min.time())
    months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
              "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
    m = re.match(r"^([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?\b", s)
    if m and m.group(1) in months:
        try:
            return _dt(today.year, months[m.group(1)], int(m.group(2)))
        except ValueError:
            return None
    return None


async def shape_situations(items: List[Dict[str, Any]], today_utc: str,
                     known: List[LedgerItem]) -> Dict[str, List[Dict[str, Any]]]:
    """Deterministic structuring + model-judged matching: stable keys, date
    resolution, dedupe against known rows by key, title, or judged sameness.
    Returns {new, update, close}."""
    by_key = {str(i.situation_key): i for i in known if i.situation_key}
    by_title = {_norm_title(i.title): i for i in known}
    statements: Dict[str, List[Dict[str, Any]]] = {"new": [], "update": [], "close": []}
    seen: set = set()
    for it in items:
        title = str(it.get("title") or "").strip()
        if not title or _norm_title(title) in seen:
            continue
        seen.add(_norm_title(title))
        key = _slug(title)
        target = by_key.get(key) or by_title.get(_norm_title(title))
        detail = _clean(it.get("detail"), 2000)
        people = [str(p) for p in (it.get("people") or []) if _clean(p, 200)]
        if people:
            detail = (detail + " People: " + "; ".join(people[:5])).strip()
        if _clean(it.get("matters"), 500):
            detail = (detail + " Why it matters: " + _clean(it.get("matters"), 500)).strip()
        if _clean(it.get("blocked_by"), 300):
            detail = (detail + " Blocked by: " + _clean(it.get("blocked_by"), 300)).strip()
        ev = [_clean(e, 500) for e in (it.get("evidence") or [])]
        ev = [e for e in ev if e]
        kind = _clean(it.get("kind"), 40) or "situation"
        conf = _clean(it.get("confidence"), 20) or "reported"
        if conf not in ("observed", "reported", "inferred"):
            conf = "reported"
        timing = _clean(it.get("timing"), 300)
        entry: Dict[str, Any] = {
            "key": key if target is None else str(target.situation_key or key),
            "title": title, "kind": kind, "confidence": conf, "detail": detail,
            "timing_text": timing, "expected_date": None,
            "waiting_on": _clean(it.get("waiting_on"), 300),
            "question_text": _clean(it.get("question"), 500),
            "linked_keys": [], "evidence": ev,
            "reminder_authorised": bool(it.get("reminder_authorised")),
        }
        resolved = str(it.get("resolved") or "").strip()
        hint = str(it.get("status_hint") or "").strip().lower()
        if target is None:
            if resolved:
                entry["status"] = "done"
            statements["new"].append(entry)
        else:
            if resolved:
                statements["close"].append({"key": entry["key"], "status": "done", "evidence": resolved})
            else:
                upd = {"key": entry["key"], "detail": detail or target.detail,
                       "timing_text": timing or target.timing_text,
                       "waiting_on": entry["waiting_on"] or target.waiting_on,
                       "question_text": entry["question_text"] or target.question_text,
                       "confidence": conf, "evidence": ev}
                if hint in ("open", "waiting", "watching", "suppressed"):
                    upd["status"] = hint
                if it.get("reminder_authorised"):
                    upd["reminder_authorised"] = True
                statements["update"].append(upd)
    # resolve expected dates deterministically (never from model prose)
    for group in ("new",):
        for e in statements[group]:
            d = resolve_date(e.get("timing_text"), today_utc)
            e["expected_date"] = d.strftime("%Y-%m-%d") if d else None
    # judged matching: same circumstance in different words merges, never duplicates
    match_out, match_call = await match_situations(
        [{"title": e["title"], "detail": e.get("detail", "")} for e in statements["new"]], known)
    matched = match_out.get("same", {}) if isinstance(match_out, dict) else match_out
    closed_by_match = match_out.get("close", {}) if isinstance(match_out, dict) else {}
    match_report: Dict[str, Any] = {"matched": matched, "closed": list(closed_by_match),
                                    "call": match_call or {"skipped": True if not statements["new"] or not known else "failed"}}
    for key, proof in closed_by_match.items():
        is_supersede = str(proof).startswith("superseded:")
        statements["close"].append({"key": key,
                                    "status": "cancelled" if is_supersede else "done",
                                    "evidence": proof})
    if matched:
        still_new = []
        for e in statements["new"]:
            if e["title"] in matched:
                if str(e.get("resolved") or "").strip():
                    statements["close"].append({
                        "key": matched[e["title"]], "status": "done",
                        "evidence": str(e["resolved"])[:1000]})
                else:
                    statements["update"].append({
                        "key": matched[e["title"]], "detail": e.get("detail", ""),
                        "timing_text": e.get("timing_text", ""), "waiting_on": e.get("waiting_on", ""),
                        "question_text": e.get("question_text", ""), "confidence": e.get("confidence", "reported"),
                        "evidence": e.get("evidence", []),
                        **({"reminder_authorised": True} if e.get("reminder_authorised") else {})})
            else:
                still_new.append(e)
        statements["new"] = still_new
    return statements, match_report


def _parse_date(value: Any) -> Optional[datetime]:
    try:
        s = str(value or "").strip()
        if not s or s.lower() in ("null", "unknown", "none"):
            return None
        from datetime import datetime as _dt
        return _dt.strptime(s[:10], "%Y-%m-%d")
    except Exception:
        return None


async def apply_situations(db: AsyncSession, *, workspace_id: str, owner: str, run_id: Any,
                           session_id: str, statements: Dict[str, List[Dict[str, Any]]],
                           known: Optional[List[LedgerItem]] = None) -> Dict[str, int]:
    """Apply model-produced situation statements. New rows, field patches by
    stable key, closes only with evidence. Returns counts."""
    counts = {"added": 0, "updated": 0, "closed": 0}
    if known is None:
        known = await open_ledger(db, workspace_id, owner, limit=100)
    by_key: Dict[str, Any] = {str(i.situation_key): i for i in known if i.situation_key}
    # Identity is the normalized title alone: a kind change across sessions
    # (reminder vs commitment) is an update, never a second row.
    by_title = {_norm_title(i.title): i for i in known}
    # Fold title-matched new entries into updates before inserting anything.
    merged_new: List[Dict[str, Any]] = []
    for e in statements.get("new", []):
        title = str(e.get("title") or "").strip()
        key = str(e.get("key") or "").strip().lower().replace(" ", "-")[:80]
        target = None if (key and key in by_key) else by_title.get(_norm_title(title))
        if target is not None:
            statements.setdefault("update", []).append({**e, "key": target.situation_key or key})
        else:
            merged_new.append(e)
    statements["new"] = merged_new
    for e in statements.get("new", []):
        title = str(e.get("title") or "").strip()
        if not title or title.lower() in ("none", "n/a", "no change", "no changes", "nothing", "nothing new"):
            continue
        key = str(e.get("key") or "").strip().lower().replace(" ", "-")[:80]
        if key and key in by_key:
            continue  # already known: the update path owns it, never duplicate
        db.add(LedgerItem(
            honcho_workspace_id=workspace_id, owner_peer_id=owner,
            kind=str(e.get("kind") or "situation")[:40], title=title[:500],
            detail=str(e.get("detail") or "")[:2000], status="open",
            situation_key=key or None, confidence=str(e.get("confidence") or "reported")[:20],
            source_refs_json=json.dumps({"session": session_id, "evidence": e.get("evidence") or []})[:4000],
            timing_text=str(e.get("timing_text") or "")[:300], expected_date=_parse_date(e.get("expected_date")),
            waiting_on=str(e.get("waiting_on") or "")[:300], question_text=str(e.get("question_text") or "")[:500],
            linked_keys_json=json.dumps([k for k in (e.get("linked_keys") or []) if isinstance(k, str)])[:1000],
            authorised_json=json.dumps({"reminder": True, "at": session_id} if e.get("reminder_authorised") else {}),
            run_id=run_id))
        counts["added"] += 1
        if key:
            by_key[key] = True
    for e in statements.get("update", []):
        item = by_key.get(str(e.get("key") or ""))
        if item is True or item is None:
            continue
        changed = False
        for f in ("detail", "timing_text", "waiting_on", "question_text"):
            v = e.get(f)
            limit = 2000 if f == "detail" else 500
            if isinstance(v, str) and v.strip() and v.strip()[:limit] != getattr(item, f):
                setattr(item, f, v.strip()[:limit])
                changed = True
        if e.get("expected_date"):
            d = _parse_date(e.get("expected_date"))
            if d is not None and d != item.expected_date:
                item.expected_date = d
                changed = True
        if e.get("confidence") in ("observed", "reported", "inferred"):
            item.confidence = str(e["confidence"])
            changed = True
        if isinstance(e.get("kind"), str) and e["kind"].strip() and e["kind"].strip()[:40] != item.kind:
            item.kind = e["kind"].strip()[:40]
            changed = True
        if e.get("status") in ("open", "waiting", "watching", "suppressed"):
            item.status = str(e["status"])
            changed = True
        if e.get("reminder_authorised"):
            item.authorised_json = json.dumps({"reminder": True, "at": session_id})
            changed = True
        for lk in (e.get("linked_keys") or []):
            if not isinstance(lk, str):
                continue
            try:
                cur = json.loads(item.linked_keys_json or "[]")
            except Exception:
                cur = []
            if lk not in cur:
                cur.append(lk)
                item.linked_keys_json = json.dumps(cur)[:1000]
                changed = True
        ev = e.get("evidence")
        if ev:
            try:
                refs = json.loads(item.source_refs_json or "{}")
            except Exception:
                refs = {}
            prior = refs.get("evidence") if isinstance(refs, dict) else []
            refs = {"session": session_id, "evidence": ([prior] if isinstance(prior, str) else (prior or [])) + [ev]}
            item.source_refs_json = json.dumps(refs)[:4000]
            changed = True
        if changed:
            item.run_id = run_id
            item.updated_at = utc_now()
            counts["updated"] += 1
    for e in statements.get("close", []):
        item = by_key.get(str(e.get("key") or ""))
        if not isinstance(item, LedgerItem):
            continue
        if str(e.get("status") or "") not in ("done", "cancelled", "answered") or not str(e.get("evidence") or "").strip():
            continue  # closes require a status and evidence, no exceptions
        item.status, item.run_id = str(e["status"]), run_id
        item.updated_at = utc_now()
        try:
            refs = json.loads(item.source_refs_json or "{}")
        except Exception:
            refs = {}
        refs["closed_evidence"] = str(e["evidence"])[:1000]
        refs["closed_session"] = session_id
        item.source_refs_json = json.dumps(refs)[:4000]
        counts["closed"] += 1
    return counts


def format_transcript(messages: List[Dict[str, Any]]) -> str:
    lines = []
    for m in messages:
        label = str(m.get("label") or "").strip()
        if not label:
            label = "Him" if str(m.get("speaker") or "") in ("user", "him") else "Sophie"
        text = str(m.get("text") or "").strip()
        if text:
            lines.append(f"{label}: {text}")
    return "\n".join(lines)


async def live_pages(db: AsyncSession, workspace_id: str, owner: str) -> Dict[str, NotebookPage]:
    out: Dict[str, NotebookPage] = {}
    for key in PAGES:
        rows = (await db.execute(select(NotebookPage).where(
            NotebookPage.honcho_workspace_id == workspace_id,
            NotebookPage.owner_peer_id == owner,
            NotebookPage.page_key == key,
            NotebookPage.superseded_by_id.is_(None)))).scalars().all()
        if rows:
            out[key] = sorted(rows, key=lambda r: r.version, reverse=True)[0]
        else:
            page = NotebookPage(honcho_workspace_id=workspace_id, owner_peer_id=owner, page_key=key, text=PAGE_SEEDS[key])
            db.add(page)
            await db.flush()
            out[key] = page
    return out


async def covered_ids(db: AsyncSession, workspace_id: str, owner: str, conversation_id: str) -> List[str]:
    rows = (await db.execute(select(MemoryRun).where(
        MemoryRun.honcho_workspace_id == workspace_id,
        MemoryRun.owner_peer_id == owner,
        MemoryRun.conversation_id == conversation_id,
        MemoryRun.status.in_(["consolidated", "replay_noop"])))).scalars().all()
    seen: List[str] = []
    for r in rows:
        try:
            for mid in json.loads(r.covered_ids_json or "[]"):
                if mid not in seen:
                    seen.append(str(mid))
        except Exception:
            continue
    return seen


async def open_ledger(db: AsyncSession, workspace_id: str, owner: str, limit: int = 20) -> List[LedgerItem]:
    rows = (await db.execute(select(LedgerItem).where(
        LedgerItem.honcho_workspace_id == workspace_id,
        LedgerItem.owner_peer_id == owner,
        LedgerItem.status.in_(["open", "waiting", "watching"])).order_by(LedgerItem.created_at.desc()).limit(limit))).scalars().all()
    return list(rows)


async def get_arc(db: AsyncSession, workspace_id: str, owner: str) -> ContinuingArc:
    row = (await db.execute(select(ContinuingArc).where(
        ContinuingArc.honcho_workspace_id == workspace_id,
        ContinuingArc.owner_peer_id == owner).order_by(ContinuingArc.version.desc()).limit(1))).scalars().first()
    if row is None:
        row = ContinuingArc(honcho_workspace_id=workspace_id, owner_peer_id=owner, text=ARC_SEED)
        db.add(row)
        await db.flush()
    return row


async def create_run(db: AsyncSession, *, workspace_id: str, owner: str, conversation_id: str,
                   session_id: str, message_count: int) -> str:
    """Pre-register a run so POST /consolidate can return 202 immediately."""
    from datetime import datetime as _dt
    run = MemoryRun(honcho_workspace_id=workspace_id, owner_peer_id=owner, conversation_id=conversation_id,
                    session_id=session_id, status="running", started_at=_dt.now(timezone.utc).replace(tzinfo=None),
                    bundle_json=json.dumps({"message_count": message_count, "accepted": True}))
    db.add(run)
    await db.flush()
    return str(run.id)


async def get_run(db: AsyncSession, run_id: str) -> Optional[MemoryRun]:
    try:
        uid = UUID(run_id)
    except Exception:
        return None
    return (await db.execute(select(MemoryRun).where(MemoryRun.id == uid))).scalars().first()


async def recover_orphaned_runs(db: AsyncSession, *, older_than_minutes: int = 10) -> List[Dict[str, Any]]:
    """Execution recovery: runs stuck in `running` whose worker is gone (deploy
    restart, crash) are marked failed with an audit note instead of lying.
    Re-running the same session is idempotent (coverage + title-identity
    dedupe), so recovery is: mark failed, report, let the caller replay."""
    from datetime import timedelta as _td
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - _td(minutes=older_than_minutes)
    rows = (await db.execute(select(MemoryRun).where(
        MemoryRun.status == "running",
        MemoryRun.created_at < cutoff))).scalars().all()
    out = []
    for r in rows:
        r.status = "failed"
        try:
            bundle = json.loads(r.bundle_json or "{}")
        except Exception:
            bundle = {}
        bundle["recovery"] = {"at": datetime.now(timezone.utc).isoformat(),
                              "reason": "orphaned: worker gone (restart/crash); replay the session to recover"}
        r.bundle_json = json.dumps(bundle)[:500_000]
        r.finished_at = datetime.now(timezone.utc).replace(tzinfo=None)
        out.append({"run_id": str(r.id), "session_id": r.session_id, "owner": r.owner_peer_id})
    if out:
        await db.commit()
        logger.info("[memory] recovered %d orphaned runs", len(out))
    return out


async def read_state(db: AsyncSession, *, workspace_id: str, owner: str,
                   include_closed: bool = False) -> Dict[str, Any]:
    """Notebook + ledger + arc + attention for inspection. Pure reads, no model."""
    from src.services import attention_cycle as _attn
    pages = await live_pages(db, workspace_id, owner)
    if include_closed:
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id,
            LedgerItem.owner_peer_id == owner).order_by(LedgerItem.created_at).limit(200))).scalars().all()
        ledger = list(rows)
    else:
        ledger = await open_ledger(db, workspace_id, owner, limit=50)
    arc = await get_arc(db, workspace_id, owner)
    prep = await get_preparation(db, workspace_id=workspace_id, owner=owner)
    return {
        "notebook": {k: {"title": PAGE_TITLES[k], "version": p.version, "text": p.text} for k, p in pages.items()},
        "ledger": [{"id": str(i.id), "key": i.situation_key, "kind": i.kind, "title": i.title,
                    "status": i.status, "confidence": i.confidence, "detail": i.detail,
                    "timing": i.timing_text,
                    "expected_date": i.expected_date.strftime("%Y-%m-%d") if i.expected_date else None,
                    "updated_at": i.updated_at.isoformat() if i.updated_at else None,
                    "waiting_on": i.waiting_on, "question": i.question_text,
                    "linked": (json.loads(i.linked_keys_json) if (i.linked_keys_json or "").startswith("[") else [])}
                   for i in ledger],
        "arc": {"version": arc.version, "text": arc.text},
        "preparation": prep,
        "attention": {
            "pending": await _attn.pending_attention(db, workspace_id=workspace_id, owner=owner),
            "suppressed": await _attn.suppressed_matters(db, workspace_id=workspace_id, owner=owner),
        },
    }


async def consolidate(db: AsyncSession, *, workspace_id: str, owner: str, conversation_id: str,
                      session_id: str, messages: List[Dict[str, Any]], companion_id: str = "sophie",
                      now_iso: Optional[str] = None, sitting_kind: str = "user") -> Dict[str, Any]:
    """Consolidate one COMPLETED session. Full transcript in, replay-safe.
    sitting_kind: "user" (with the person) or "independent" (Sophie's own
    sitting, user absent — the shared arc is left alone; continuity lives on
    the exploring page)."""
    from datetime import datetime as _dt
    started = _dt.now(_tz_utc())
    now_iso = now_iso or started.isoformat()
    run = (await db.execute(select(MemoryRun).where(
        MemoryRun.honcho_workspace_id == workspace_id,
        MemoryRun.owner_peer_id == owner,
        MemoryRun.conversation_id == conversation_id,
        MemoryRun.session_id == session_id,
        MemoryRun.status == "running").order_by(MemoryRun.created_at.desc()).limit(1))).scalars().first()
    if run is None:
        run = MemoryRun(honcho_workspace_id=workspace_id, owner_peer_id=owner, conversation_id=conversation_id,
                        session_id=session_id, status="running", started_at=started.replace(tzinfo=None))
        db.add(run)
        await db.flush()
    bundle: Dict[str, Any] = {"workspace_id": workspace_id, "owner": owner, "conversation_id": conversation_id,
                              "session_id": session_id, "companion_id": companion_id, "run_id": str(run.id),
                              "sitting_kind": sitting_kind}

    trimmed = [m for m in messages if str(m.get("text") or "").strip()]
    ids = [str(m.get("id") or "") for m in trimmed if str(m.get("id") or "")]
    already = set(await covered_ids(db, workspace_id, owner, conversation_id)) if ids else set()
    fresh = [m for m in trimmed if str(m.get("id") or "") not in already] if ids else trimmed
    transcript = format_transcript(trimmed[:MAX_TRANSCRIPT_MESSAGES])
    bundle.update(message_count=len(trimmed), new_message_count=len(fresh),
                  truncated=len(trimmed) > MAX_TRANSCRIPT_MESSAGES)

    async def finish(status: str, covered: List[str], extra: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        run.status = status
        run.covered_ids_json = json.dumps(covered)
        bundle.update(status=status, ms_total=int((_dt.now(_tz_utc()) - started).total_seconds() * 1000))
        if extra:
            bundle.update(extra)
        run.bundle_json = json.dumps(bundle)[:500_000]
        run.finished_at = _dt.now(_tz_utc()).replace(tzinfo=None)
        await db.commit()
        logger.info("[memory] %s %s -> %s (%d new)", owner, session_id, status, len(covered))
        return {"status": status, "session_id": session_id, "new_messages": len(covered), "run_id": str(run.id)}

    if not transcript.strip():
        return await finish("empty", [])

    pages = await live_pages(db, workspace_id, owner)
    arc = await get_arc(db, workspace_id, owner)
    ledger = await open_ledger(db, workspace_id, owner)
    bundle["notebook_before"] = {k: p.text for k, p in pages.items()}
    bundle["arc_before"] = arc.text

    listen = INDEPENDENT_LISTENING_PROMPT if sitting_kind == "independent" else LISTENING_PROMPT
    discovery = await _generate("discovery", f"{listen}\n\n--- conversation ---\n{transcript}",
                                2000, _models("MEMORY_DISCOVERY_MODELS", "qwen/qwen3.8-27b"))
    handoff = await _generate("handoff", f"{HANDOFF_PROMPT}\n\n--- transcript ---\n{transcript}",
                              300, _models("MEMORY_HANDOFF_MODELS", "inclusionai/ling-3.0-flash"))
    findings = str((discovery or {}).get("text") or "")
    handoff_text = str((handoff or {}).get("text") or "")
    bundle["discovery"] = discovery or {"skipped": True}
    bundle["handoff"] = handoff or {"skipped": True}
    bundle["findings"] = findings

    if not fresh or not (findings.strip() or handoff_text.strip()):
        return await finish("replay_noop" if not fresh else "empty", [],
                            {"note": "replay_no_new_messages" if not fresh else "no_findings"})

    sitting_rule = f"\n\n{INDEPENDENT_RULE}" if sitting_kind == "independent" else ""
    for key in PAGES:
        subject = f"\n\n{PAGE_SUBJECT[key]}" if key in PAGE_SUBJECT else ""
        edit = await _generate(f"edit:{key}",
                               f"{NOTEBOOK_EDITOR_PROMPT}\n\n{PAGE_SCOPES[key]}{subject}{sitting_rule}\n\n--- page: {PAGE_TITLES[key]} ---\n{pages[key].text}\n\n--- new findings ---\n{findings or handoff_text}",
                               1500, _models("MEMORY_EDITOR_MODELS", "qwen/qwen3.8-27b"))
        bundle[f"edit_{key}"] = edit or {"skipped": True}
        new_text = str((edit or {}).get("text") or "").strip()
        if new_text and new_text != pages[key].text.strip():
            pages[key].superseded_by_id = pages[key].id
            nxt = NotebookPage(honcho_workspace_id=workspace_id, owner_peer_id=owner, page_key=key,
                               text=new_text, version=pages[key].version + 1, run_id=run.id)
            db.add(nxt)
            await db.flush()
            pages[key] = nxt
    bundle["notebook_after"] = {k: p.text for k, p in pages.items()}

    open_lines = "\n".join(
        f"- key={i.situation_key or '(no key)'} [{i.kind}|{i.status}|{i.confidence}] {i.title}"
        f"{(' | timing: ' + i.timing_text) if i.timing_text else ''}"
        f"{(' | waiting on: ' + i.waiting_on) if i.waiting_on else ''}"
        f"{(' | open question: ' + i.question_text) if i.question_text else ''}"
        for i in ledger) or "(none open)"
    today_utc = (str(now_iso or "")[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", str(now_iso or ""))
                 else datetime.now(timezone.utc).date().isoformat())
    extract = await _generate("ledger", SITUATIONS_PROMPT.replace("{open_items}", open_lines).replace(
        "{today_utc}", today_utc).replace("{transcript}", transcript).replace(
        "{findings}", findings or handoff_text),
        1000, _models("MEMORY_DISCOVERY_MODELS", "qwen/qwen3.8-27b"))
    bundle["ledger_extract"] = extract or {"skipped": True}
    raw_extract = str((extract or {}).get("text") or "")
    witness, unparsed = parse_tagged_lines(raw_extract)
    if not witness and len(findings or "") > 80:
        # Witness blindness guard: the model replied NONE (or emitted nothing
        # parseable) yet the session notes describe real developments. One
        # retry with an explicit nudge before letting the session go unwritten.
        retry = await _generate("ledger", SITUATIONS_PROMPT.replace("{open_items}", open_lines).replace(
            "{today_utc}", today_utc).replace("{transcript}", transcript).replace(
            "{findings}", findings or handoff_text) + "\n\nYou replied NONE, but the session notes above describe "
            "concrete developments. Look again and report every ITEM with its tags — never reply NONE when "
            "commitments, deadlines, schedule changes, approvals or completions appear.",
            1000, _models("MEMORY_DISCOVERY_MODELS", "qwen/qwen3.8-27b"))
        if retry and str(retry.get("text") or "").strip():
            bundle["ledger_extract_retry"] = {"model": retry.get("model"), "ms": retry.get("ms")}
            raw_extract = str(retry.get("text") or "")
            witness, unparsed = parse_tagged_lines(raw_extract)
    bundle["ledger_witness_items"] = witness
    bundle["ledger_unparsed"] = unparsed
    statements, match_report = await shape_situations(witness, today_utc, ledger)
    bundle["ledger_match"] = match_report
    # legacy JSON fallback: if the model emitted structured output instead
    if not statements["new"] and not statements["update"] and not statements["close"]:
        statements = _parse_situations(raw_extract)
    # Agentic maintenance owns ledger writes: observations + open ledger in,
    # investigated updates out. Deterministic skip when nothing observed.
    agent_out: Dict[str, Any] = {"status": "skipped", "reason": "no witness observations"}
    if witness:
        from src.services import maintenance_agent
        obs_lines = []
        for it in witness:
            obs_lines.append(f"- {it.get('title', '')} [{it.get('kind', 'situation')}] :: "
                             f"{str(it.get('detail') or '')[:400]}"
                             f"{' | timing: ' + it['timing'] if it.get('timing') else ''}"
                             f"{' | RESOLVED: ' + it['resolved'][:300] if it.get('resolved') else ''}")
        before = {(str(i.situation_key), i.status, str(i.updated_at))
                  for i in await open_ledger(db, workspace_id, owner, limit=200)}
        agent_out = await maintenance_agent.run_maintenance(
            db, workspace_id=workspace_id, owner=owner, session_id=session_id,
            observations="\n".join(obs_lines), today_utc=today_utc,
            transcript=transcript)
        after = {(str(i.situation_key), i.status, str(i.updated_at))
                 for i in await open_ledger(db, workspace_id, owner, limit=200)}
        agent_out["ledger_moved"] = before != after
    bundle["ledger_agent"] = {k: v for k, v in agent_out.items() if k != "calls"}
    bundle["ledger_agent_calls"] = agent_out.get("calls", [])
    if agent_out.get("status") == "verified":
        agent_changes = agent_out.get("changes") or {}
        if (witness and not any(agent_changes.get(k, 0) for k in ("created", "updated", "closed"))
                and not agent_out.get("ledger_moved")):
            # Claimed success with no observable effect: do not trust it.
            agent_out["status"] = "unverified_claims"
            bundle["ledger_agent"]["status"] = "unverified_claims"
    if agent_out.get("status") == "verified":
        agent_changes = agent_out.get("changes") or {}
        counts = {"added": int(agent_changes.get("created", 0)),
                  "updated": int(agent_changes.get("updated", 0)),
                  "closed": int(agent_changes.get("closed", 0)), "agent_owned": True}
        bundle["ledger_added"] = counts["added"]
        bundle["ledger_counts"] = counts
    else:
        # Agent did not verify: fall back to direct deterministic apply so
        # observations are still captured; the next session retries judgment.
        counts = await apply_situations(db, workspace_id=workspace_id, owner=owner, run_id=run.id,
                                        session_id=session_id, statements=statements, known=ledger)
        bundle["ledger_added"] = counts["added"]
        bundle["ledger_counts"] = counts
    # End-of-sitting attention: due-scan always (deterministic, cheap); review
    # only when something actually changed (new observations or ledger writes).
    from src.services import attention_cycle
    try:
        bundle["attention_due"] = await attention_cycle.mark_due(
            db, workspace_id=workspace_id, owner=owner)
        ledger_touched = bool(witness) or any(
            (counts or {}).get(k, 0) for k in ("added", "updated", "closed"))
        if ledger_touched:
            review = await attention_cycle.run_attention_review(
                db, workspace_id=workspace_id, owner=owner, today_utc=today_utc,
                reason="end-of-sitting", findings=findings or handoff_text)
            bundle["attention_review"] = {k: v for k, v in review.items()}
        else:
            bundle["attention_review"] = {"status": "skipped", "reason": "nothing changed"}
    except Exception as exc:
        logger.warning("[memory] attention hook failed open: %s", exc)
        bundle["attention_review"] = {"status": "failed", "error": type(exc).__name__}

    if sitting_kind == "independent":
        # The shared continuing arc belongs to the user-facing relationship;
        # an independent sitting leaves it alone (continuity lives on exploring).
        bundle["arc_edit"] = {"skipped": "independent_sitting"}
    else:
        arc_edit = await _generate("arc",
                                   f"{ARC_UPDATE_PROMPT}\n\n--- current account ---\n{arc.text}\n\n--- just-finished session ---\n{handoff_text or findings}",
                                   500, _models("MEMORY_HANDOFF_MODELS", "inclusionai/ling-3.0-flash"))
        bundle["arc_edit"] = arc_edit or {"skipped": True}
        new_arc = str((arc_edit or {}).get("text") or "").strip()
        if new_arc and new_arc != arc.text.strip():
            arc.text, arc.version, arc.run_id = new_arc, arc.version + 1, run.id
            arc.updated_at = utc_now()
    bundle["arc_after"] = arc.text

    prep = await prepare(db, workspace_id=workspace_id, owner=owner, now_iso=now_iso, run_id=run.id)
    bundle["preparation"] = {k: v for k, v in prep.items() if k != "text"}
    bundle["preparation_text"] = prep.get("text", "")
    return await finish("consolidated", [str(m.get("id")) for m in fresh if str(m.get("id") or "")] or [f"fp:{_fingerprint(transcript)}"])


async def prepare(db: AsyncSession, *, workspace_id: str, owner: str,
                  now_iso: Optional[str] = None, run_id: Optional[UUID] = None) -> Dict[str, Any]:
    """Compose a small situated perspective and cache it (superseding the last)."""
    from datetime import datetime as _dt
    now_iso = now_iso or _dt.now(_tz_utc()).isoformat()
    try:
        _now = _dt.fromisoformat(str(now_iso))
        if _now.tzinfo is None:
            _now = _now.replace(tzinfo=timezone.utc)
    except ValueError:
        _now = _dt.now(timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        _local = _now.astimezone(ZoneInfo("Europe/London"))
    except Exception:
        _local = _now
    # The clock is authoritative. The model interprets what it means, never
    # recomputes it: any mention of today must agree with this line.
    clock_line = (f"Current time (authoritative — do not recompute the date, weekday or time; "
                  f"any mention of today must agree with this): {_local.strftime('%A')} "
                  f"{_local.date().isoformat()} {_local.strftime('%H:%M')} Europe/London "
                  f"(UTC {_now.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M')}).")
    pages = await live_pages(db, workspace_id, owner)
    ledger = await open_ledger(db, workspace_id, owner)
    arc = await get_arc(db, workspace_id, owner)
    notebook_text = "\n\n".join(f"## {PAGE_TITLES[k]}\n{pages[k].text}" for k in PAGES)
    ledger_text = "\n".join(
        f"- [{i.kind}|{i.status}|{i.confidence}] {i.title}"
        f"{(' | ' + i.detail) if i.detail else ''}"
        f"{(' | timing: ' + i.timing_text) if i.timing_text else ''}"
        f"{(' | waiting on: ' + i.waiting_on) if i.waiting_on else ''}"
        f"{(' | open question: ' + i.question_text) if i.question_text else ''}"
        for i in ledger) or "(nothing open)"
    from src.services import attention_cycle as _attn
    attention_text = "\n".join(await _attn.describe_attention(
        db, workspace_id=workspace_id, owner=owner)) or "(nothing awaiting attention)"
    call = await _generate("preparation",
                           f"{PREPARATION_PROMPT}\n\n--- now ---\n{now_iso}\n{clock_line}\n\n--- notebook ---\n{notebook_text}\n\n--- operational ledger (open) ---\n{ledger_text}\n\n--- needs attention (due/pending intentions; already-excluded holds and suppressions are not listed; treat these as live candidates, not orders) ---\n{attention_text}\n\n--- where conversations stand ---\n{arc.text}",
                           600, _models("MEMORY_EDITOR_MODELS", "qwen/qwen3.8-27b"))
    text = str((call or {}).get("text") or "").strip()
    fingerprint = _fingerprint(notebook_text, ledger_text, attention_text, arc.text, now_iso[:10])
    prep_id = None
    if text:
        old = (await db.execute(select(SittingPreparation).where(
            SittingPreparation.honcho_workspace_id == workspace_id,
            SittingPreparation.owner_peer_id == owner,
            SittingPreparation.superseded_by_id.is_(None)))).scalars().all()
        prep = SittingPreparation(honcho_workspace_id=workspace_id, owner_peer_id=owner, window="sitting",
                                  text=text, based_on_json=json.dumps({"inputs": fingerprint}), run_id=run_id)
        db.add(prep)
        await db.flush()
        for o in old:
            o.superseded_by_id = prep.id
        prep_id = str(prep.id)
    return {"text": text, "id": prep_id, "inputs_fingerprint": fingerprint, **(call or {"skipped": True})}


REVIEW_PROMPT = """Review this person's open situations against what recent sessions actually established. You are noticing change, not generating work.

Open situations:
{open_items}

Recent session findings (newest last):
{recent}

Return ONLY a JSON object: {"updates": [{key (must match an open key), plus changed fields: detail/timing_text/waiting_on/question_text/expected_date/confidence/status (open/waiting/watching only — never close here; closes need session evidence via consolidation), linked_keys, evidence}], "noticed": ["short plain observations: connections between situations, recurring concerns, contradictions, missing information worth asking about"]}.

Rules: repetition is not a personality judgement. Time passing proves nothing — never mark something resolved, abandoned or completed without evidence. An aspiration stays an aspiration. Keep every update grounded in the findings above; if nothing changed, return empty lists."""


async def backfill_expected_dates(db: AsyncSession, *, workspace_id: str, owner: str) -> int:
    """Deterministic one-time-per-row fill: rows whose timing_text names an
    exact date get expected_date without any model call. Never overwrites."""
    from datetime import datetime as _dt
    today = _dt.now(timezone.utc).date().isoformat()
    items = await open_ledger(db, workspace_id, owner, limit=200)
    n = 0
    for i in items:
        if i.expected_date is None and i.timing_text:
            d = resolve_date(i.timing_text, today)
            if d is not None:
                i.expected_date, i.updated_at = d, utc_now()
                n += 1
    if n:
        await db.commit()
    return n


async def review(db: AsyncSession, *, workspace_id: str, owner: str, lookback_runs: int = 6) -> Dict[str, Any]:
    """Longitudinal noticing across recent sessions: one model call over open
    situations + recent findings. Applies updates, never closes."""
    from datetime import datetime as _dt
    await backfill_expected_dates(db, workspace_id=workspace_id, owner=owner)
    items = await open_ledger(db, workspace_id, owner, limit=100)
    runs = (await db.execute(select(MemoryRun).where(
        MemoryRun.honcho_workspace_id == workspace_id,
        MemoryRun.owner_peer_id == owner,
        MemoryRun.status == "consolidated").order_by(MemoryRun.created_at.desc()).limit(max(1, lookback_runs)))).scalars().all()
    recent = []
    for r in sorted(runs, key=lambda x: x.created_at or _dt.min):
        try:
            bundle = json.loads(r.bundle_json or "{}")
        except Exception:
            continue
        f = str(bundle.get("findings") or "")[:1500]
        if f:
            recent.append(f"[{r.session_id}] {f}")
    open_lines = "\n".join(
        f"- key={i.situation_key or '(no key)'} [{i.kind}|{i.status}|{i.confidence}] {i.title}"
        f"{(' | ' + i.detail) if i.detail else ''}"
        f"{(' | timing: ' + i.timing_text) if i.timing_text else ''}"
        f"{(' | waiting on: ' + i.waiting_on) if i.waiting_on else ''}"
        for i in items) or "(none open)"
    call = await _generate("review", REVIEW_PROMPT.replace("{open_items}", open_lines).replace(
        "{recent}", "\n\n".join(recent) or "(no recent sessions)"),
        1500, _models("MEMORY_DISCOVERY_MODELS", "qwen/qwen3.8-27b"))
    report: Dict[str, Any] = {"updates_applied": 0, "noticed": [], "open_count": len(items)}
    try:
        raw = str((call or {}).get("text") or "")
        parsed = json.loads(raw[raw.find("{"):raw.rfind("}") + 1]) if "{" in raw else {}
        updates = [e for e in (parsed.get("updates") or []) if isinstance(e, dict)]
        counts = await apply_situations(db, workspace_id=workspace_id, owner=owner, run_id=None,
                                        session_id="review", statements={"new": [], "update": updates, "close": []},
                                        known=items)
        report["updates_applied"] = counts["updated"]
        report["noticed"] = [str(n) for n in (parsed.get("noticed") or []) if isinstance(n, str)][:20]
        await db.commit()
    except Exception as exc:
        logger.warning("[memory] review failed open: %s", exc)
        try:
            await db.rollback()
        except Exception:
            pass
    report["call"] = call or {"skipped": True}
    return report


async def get_preparation(db: AsyncSession, *, workspace_id: str, owner: str,
                          max_age_hours: float = 72.0) -> Optional[Dict[str, Any]]:
    """Latest cached preparation; None when missing or stale. Pure read, no model."""
    from datetime import datetime as _dt
    row = (await db.execute(select(SittingPreparation).where(
        SittingPreparation.honcho_workspace_id == workspace_id,
        SittingPreparation.owner_peer_id == owner,
        SittingPreparation.superseded_by_id.is_(None)).order_by(SittingPreparation.created_at.desc()).limit(1))).scalars().first()
    if row is None:
        return None
    age_h = (_dt.now(timezone.utc).replace(tzinfo=None) - (row.created_at or _dt.now(timezone.utc).replace(tzinfo=None))).total_seconds() / 3600.0
    if age_h > max_age_hours:
        return None
    return {"text": row.text, "id": str(row.id), "at": (row.created_at or "").isoformat() if hasattr(row.created_at, "isoformat") else ""}


def _tz_utc():
    return timezone.utc
