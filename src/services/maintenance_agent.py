"""Agentic operational maintenance.

The agent receives numbered witness observations, existing ledger access, the
person's local date and a maintenance contract, then investigates (list/search/
history), acts (update/create with validation) and verifies (re-list, then
account for every observation). Deterministic code owns keys, dates, evidence
gates, tenant scope, tool-call validity and audit — the agent owns judgment.

Interface guarantees (code, not model obedience):
- tool calls with malformed or truncated arguments are rejected, never run as {};
- unknown arguments are rejected, never silently ignored;
- creating a record can carry its full state (status, expected date, ...);
- `finish` is accepted only after the state was re-read following the last
  write and every numbered observation is accounted for against a real record
  touched in this run (or explicitly set aside with a reason).

Models: qwen3.8-27b via NanoGPT (flat-rate) primary; qwen3.7-flash via OpenRouter
as the cross-provider availability fallback. Same validation either way.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Set

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.world import LedgerItem, utc_now

logger = logging.getLogger(__name__)

# Observed in production (2026-10-20): every one of 123 runs executed on qwen3.8-27b because NanoGPT
# answers HTTP 403 for qwen3.7-flash. The model that actually runs is now the primary (flat-rate NanoGPT);
# the fallback is a different PROVIDER (OpenRouter, pay-per-call, used only if NanoGPT fails).
PRIMARY_MODEL = os.getenv("MAINTENANCE_MODEL", "qwen/qwen3.8-27b")
FALLBACK_MODEL = os.getenv("MAINTENANCE_FALLBACK_MODEL", "openrouter:qwen/qwen3.7-flash")
MAX_ITERS = int(os.getenv("MAINTENANCE_MAX_ITERS", "14"))
MAX_TOKENS = int(os.getenv("MAINTENANCE_MAX_TOKENS", "2500"))
CALL_TIMEOUT_S = float(os.getenv("MAINTENANCE_TIMEOUT_S", "90"))
MAX_FINISH_BOUNCES = 3

CONTRACT = """You maintain one person's operational agenda. Goal and invariants:

Maintain an accurate operational agenda from the new observations. Inspect existing records before making changes. Reuse records when they refer to the same matter. Preserve relevant changes and source evidence. Do not invent commitments, dates or completions. Never treat silence as resolution.

You also receive the session transcript, which is the ground truth. The numbered observations are a witness's quick reading of it: a witness can miss a matter, merge two, garble one or add flourishes the transcript does not support. If the transcript holds an operational matter no observation covers (a promise, an appointment, a requested reminder, a stand-down, something awaited), handle it yourself with the person's own words as evidence and account for it as obs 0. If an observation says something the transcript does not support, set it aside (skipped, with the reason).

Observations are numbered [O1], [O2]... They come from a witness who read the session. Tags: CHANGED = something about a matter changed but it did not end (a question was answered, a time/date/place was fixed or moved, terms changed). ENDED = the matter itself is over (it happened, was delivered, cancelled or dropped). "RESOLVED (legacy tag)" is unclassified: decide from the words which of those it is.

How to act:
- A CHANGED observation is an UPDATE to the existing record: write the new fact into detail and timing_text, set expected_date (YYYY-MM-DD) when a date or day is fixed or moved, clear question_text/waiting_on that the news answers, and return status waiting -> open the moment what was awaited has arrived. Confirming an appointment's time does not close the appointment. A moved review, meeting or deadline changes that record; it does not close or re-date other records unless the observation says they moved too.
- An input arriving (a number, a reply, a file, a confirmation) updates what a matter is waiting on; it does not end the matter that depends on it. Close only the matter whose own outcome happened.
- ENDED outranks STATUS-HINT: when an observation says the matter is over, close it; a waiting/watching hint on an ended matter is noise and must not keep it open.
- Only an observation that says the matter itself is over closes anything. That is normally tagged ENDED, but the witness sometimes states a delivery or completion ("the proposal was sent", "approved") under CHANGED or in the detail: judge by the words, and a promised thing that has been done is over — close it with the person's own quote as evidence. Do not invent a new waiting state for a promise that was kept. Closing (done/cancelled) requires evidence quoting proof from this session's transcript; invented proof is rejected. When closing, keep the record's existing expected_date unless the session states a different explicit date — the day you process it is not the due date.
- STATUS-HINT is the witness's reading of what the person said about this matter: apply it as the record's status when the transcript supports it (suppressed = the person asked not to be bothered about it for now; waiting = they are waiting on someone; watching = they are monitoring it). A suppressed matter keeps its own name — never rewrite it as an action like "Ignore X" — and keeps its place on the agenda.
- waiting means you cannot progress until someone else supplies something. Self-reminders and to-dos are open (actionable by the person); watching is for external developments you monitor. Aspirations stay open.
- Subtasks of a tracked matter fold into its detail; several observations about one matter fold into one record. Search before creating; create_item takes the complete state (status, expected_date, timing, waiting_on, question_text, confidence).
- Structure the time. time_role: set "happens" for something that occurs at a time (appointment, meeting, call, event) and "deadline" for something the person must do by a time; leave it empty if unclear. You set it from the person's words; code never guesses it. expected_time: 24-hour HH:MM in the person's local time, with time_basis. Reason freely: if the person says "tomorrow at 6" you may take the likeliest reading (18:00) — but record WHAT YOU KNOW: time_basis "stated" when they gave the time unambiguously ("3pm", "15:30"), "assumed" when it is your reading ("at 6"). For an assumed time keep their exact words in timing_text and put the open question in question_text ("6 am or 6 pm?"). Never present an assumption as something they said. If you have no usable reading, leave expected_time empty. If a date moves and the time is not known, clear the old time with expected_time "". importance: 3 = real consequences if missed (medical, money, legal, a promise to someone), 1 = casual, otherwise 2.
- Direction matters. A weekday the person speaks of in the past tense ("was due on Sunday", "last Friday") is a PAST date: take it from the past-days list in the date reference, never from the coming days.
- Missing details are information. An appointment with an unknown time or place is still an appointment: record the date, and put what is missing in question_text ("what time?", "where?"). That is how it gets raised later. Clear question_text when it is answered.
- Keep confidence honest: observed (they said it happened) / reported (they relayed it) / inferred (your read).
- Records are read days later. In timing_text and detail never leave relative words ("today", "tonight", "tomorrow", "this morning", "next week") standing alone: write the named day and date and keep the person's own time-of-day words ("Tue 20 Oct 2026, at 6pm").
- Never assume the person's gender, or anyone's relationship to them that they did not state. Write "the person" or "they" (not he/she/him/her) for the person in titles and details; use a pronoun for someone else only if the person's words show it.
- Reason freely, record uncertainty faithfully. A reasonable assumption (a call "at 6" is probably 18:00) is welcome; an assumption that looks like a fact is not. The person's own words, what you inferred, and what is still unresolved must all stay visible on the record.
- If a tool call fails, read the error and adapt.

VERIFY and ACCOUNT before finish: re-list the records after your last write and check field-by-field — intended status changes, every intended date in its expected_date field, no two open rows on the same matter. Then call finish with `transcript_sweep` (one line on anything in the transcript no observation covered) and `accounting`: one entry per observation number (plus obs 0 entries for anything you added from the transcript) — treatment applied (you changed/created a record: give its key), merged (folded into another observation's record: give its key), no_change (a record already reflects it: give its key and a note) or skipped (not an operational matter: note why). A finish that leaves an observation unaccounted for, or names a record you did not touch, is refused."""

TREATMENTS = ("applied", "merged", "no_change", "skipped")
STATUSES = ("open", "waiting", "watching", "suppressed")
CLOSING = ("done", "cancelled", "answered")

_CREATE_PROPS = {
    "title": {"type": "string"}, "kind": {"type": "string"}, "detail": {"type": "string"},
    "timing": {"type": "string"}, "expected_date": {"type": "string"},
    "status": {"type": "string"}, "waiting_on": {"type": "string"}, "question_text": {"type": "string"},
    "confidence": {"type": "string"}, "reminder_authorised": {"type": "boolean"}, "evidence": {"type": "string"},
    "expected_time": {"type": "string"}, "time_basis": {"type": "string"}, "time_role": {"type": "string"}, "importance": {"type": "integer"},
}
_UPDATE_PROPS = {
    "key": {"type": "string"}, "detail": {"type": "string"}, "timing_text": {"type": "string"},
    "expected_date": {"type": "string"}, "waiting_on": {"type": "string"}, "question_text": {"type": "string"},
    "status": {"type": "string"}, "kind": {"type": "string"}, "confidence": {"type": "string"},
    "reminder_authorised": {"type": "boolean"}, "evidence": {"type": "string"},
    "expected_time": {"type": "string"}, "time_basis": {"type": "string"}, "time_role": {"type": "string"}, "importance": {"type": "integer"},
}
_FINISH_PROPS = {
    "summary": {"type": "string"},
    "transcript_sweep": {"type": "string", "description": "one line: what, if anything, the transcript contained that no observation covered (or 'nothing beyond the observations')"},
    "accounting": {"type": "array", "items": {"type": "object", "properties": {
        "obs": {"type": "integer"}, "treatment": {"type": "string", "enum": list(TREATMENTS)},
        "key": {"type": "string"}, "note": {"type": "string"}}, "required": ["obs", "treatment"]}},
}
ALLOWED_ARGS = {
    "list_open": set(), "search": {"query"}, "history": {"key"},
    "update_item": set(_UPDATE_PROPS), "create_item": set(_CREATE_PROPS),
    "finish": set(_FINISH_PROPS),
}

TOOLS = [
    {"type": "function", "function": {"name": "list_open", "description": "List open situations: keys, titles, status, detail, timing, expected dates.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search", "description": "Substring search over titles and details (includes closed records).", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "history", "description": "Evidence history of one record by key.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "update_item", "description": "Change one record by key. detail/timing_text REPLACE the old text (keep what is still true). expected_date must be YYYY-MM-DD. done/cancelled REQUIRE evidence quoting proof. Valid statuses: open, waiting, watching, suppressed, done, cancelled. Unknown arguments are rejected.", "parameters": {"type": "object", "properties": _UPDATE_PROPS, "required": ["key"]}}},
    {"type": "function", "function": {"name": "create_item", "description": "Create a genuinely new record with its complete state. Search first; never duplicate tracked matters. status is open (default), waiting, watching or suppressed. expected_date YYYY-MM-DD when a date is fixed. confidence observed/reported/inferred. Attach the proving quote as evidence. Unknown arguments are rejected.", "parameters": {"type": "object", "properties": _CREATE_PROPS, "required": ["title"]}}},
    {"type": "function", "function": {"name": "finish", "description": "End only after re-listing the records following your last write. accounting must cover every observation number.", "parameters": {"type": "object", "properties": _FINISH_PROPS, "required": ["summary", "accounting", "transcript_sweep"]}}},
]

# Injectable for tests.
_chat_fn: Optional[Callable[..., Any]] = None

import contextvars as _cv
_TRANSCRIPT_CTX: _cv.ContextVar[str] = _cv.ContextVar("maintenance_transcript", default="")
_TODAY_CTX: _cv.ContextVar[str] = _cv.ContextVar("maintenance_today", default="")
_TZ_CTX: _cv.ContextVar[str] = _cv.ContextVar("maintenance_tz", default="")
TIME_ROLES = ("happens", "deadline")
TIME_BASES = ("stated", "assumed")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _parse_time_fields(args: Dict[str, Any], existing_date: Any) -> tuple[Dict[str, Any], Optional[str]]:
    """Validate expected_time / time_role / importance. Returns (fields to set, error)."""
    out: Dict[str, Any] = {}
    if "expected_time" in args:
        t = str(args.get("expected_time") or "").strip()
        if t and not _HHMM.match(t):
            return {}, "expected_time must be 24-hour HH:MM in the person's local time (e.g. 15:00), or empty to clear it"
        out["expected_time"] = t
    if "time_basis" in args:
        b = str(args.get("time_basis") or "").strip().lower()
        if b and b not in TIME_BASES:
            return {}, "time_basis must be 'stated' (the person gave that time) or 'assumed' (your likeliest reading of what they said)"
        out["time_basis"] = b
    if "time_role" in args:
        r = str(args.get("time_role") or "").strip().lower()
        if r and r not in TIME_ROLES:
            return {}, "time_role must be 'happens' (occurs at that time) or 'deadline' (must be done by it), or empty if unclear"
        out["time_role"] = r
    if "importance" in args:
        try:
            i = int(args.get("importance"))
        except (TypeError, ValueError):
            return {}, "importance must be 1 (casual), 2 (normal) or 3 (real consequences if missed)"
        if not 1 <= i <= 3:
            return {}, "importance must be 1 (casual), 2 (normal) or 3 (real consequences if missed)"
        out["importance"] = i
    return out, None


def set_chat_fn(fn: Optional[Callable[..., Any]]) -> None:
    global _chat_fn
    _chat_fn = fn


def _openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def _nano_key() -> str:
    return os.getenv("NANO_API_KEY", "").strip()


async def _chat(model: str, messages: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """One tool-capable call. OpenRouter `openrouter:` models, else NanoGPT."""
    if _chat_fn is not None:
        out = _chat_fn(model, messages)
        if hasattr(out, "__await__"):
            out = await out
        return out
    via_or = model.startswith("openrouter:")
    mid = model.split(":", 1)[1] if via_or else model
    key = _openrouter_key() if via_or else _nano_key()
    base = "https://openrouter.ai/api/v1" if via_or else os.getenv("NANO_BASE_URL", "https://nano-gpt.com/api/v1").rstrip("/")
    if not key:
        return None
    t0 = time.monotonic()
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if via_or:
            headers["X-Title"] = "cortex-maintenance"
        body: Dict[str, Any] = {"model": mid, "messages": messages, "tools": TOOLS,
                                "tool_choice": "auto", "max_tokens": MAX_TOKENS}
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as client:
            resp = await client.post(base + "/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            used = data.get("usage") or {}
            logger.info("llm_usage module=maintenance provider=%s model=%s in=%s out=%s reasoning=%s ms=%d",
                        "openrouter" if via_or else "nanogpt", mid, used.get("prompt_tokens"),
                        used.get("completion_tokens"), used.get("reasoning_tokens", 0),
                        int((time.monotonic() - t0) * 1000))
            return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [],
                    "finish_reason": choice.get("finish_reason"),
                    "model": model, "provider": "openrouter" if via_or else "nanogpt", "usage": used}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("maintenance chat failed (%s): %s%s", model, type(exc).__name__,
                       f" HTTP {status}" if status else "")
        return None


def _row_view(r: LedgerItem) -> Dict[str, Any]:
    return {"key": r.situation_key, "kind": r.kind, "status": r.status, "title": r.title,
            "detail": (r.detail or "")[:500], "timing": r.timing_text,
            "expected_date": r.expected_date.strftime("%Y-%m-%d") if r.expected_date else None,
            "waiting_on": r.waiting_on, "question": r.question_text, "confidence": r.confidence,
            "expected_time": r.expected_time, "time_basis": r.time_basis, "time_role": r.time_role, "importance": r.importance}


class RunState:
    """What happened in this run, tracked by code (never reported by the model)."""

    def __init__(self, n_obs: int = 0) -> None:
        self.n_obs = n_obs
        self.touched: Set[str] = set()
        self.seq = 0
        self.last_write_seq = 0
        self.last_read_seq = 0
        self.finish_bounces = 0
        self.advisory_rounds = 0
        self.has_transcript = False
        self.obs_timing: Dict[int, str] = {}
        self.accounting: List[Dict[str, Any]] = []
        self.gate_failures: List[str] = []

    def wrote(self) -> bool:
        return self.last_write_seq > 0


def _record_view_fields(r: LedgerItem) -> Dict[str, Any]:
    return {"status": r.status, "expected_date": r.expected_date.strftime("%Y-%m-%d") if r.expected_date else None,
            "timing_text": r.timing_text, "waiting_on": r.waiting_on, "question_text": r.question_text,
            "kind": r.kind, "confidence": r.confidence, "detail": r.detail,
            "expected_time": r.expected_time, "time_basis": r.time_basis, "time_role": r.time_role, "importance": r.importance}


def _diff(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in after.items():
        if before.get(k) != v:
            old = before.get(k)
            out[k] = {"from": (str(old)[:160] if old is not None else None), "to": (str(v)[:160] if v is not None else None)}
    return out


def _advisories(r: LedgerItem) -> List[str]:
    """Self-consistency of one record's own fields. Advice only; never writes."""
    out: List[str] = []
    if r.status in ("open", "waiting", "watching") and r.timing_text and r.expected_date is None:
        today = _TODAY_CTX.get()
        if today:
            from src.services.memory_pipeline import resolve_date
            d = resolve_date(r.timing_text, today)
            if d is not None:
                prev = d - timedelta(days=7) if d.strftime("%Y-%m-%d") != today else None
                both = (f"the upcoming one is {d.strftime('%Y-%m-%d')}, the most recent is {prev.strftime('%Y-%m-%d')}; set the one the person meant"
                        if prev is not None else f"that is {d.strftime('%Y-%m-%d')}; set it if right")
                out.append(f"{r.situation_key}: timing_text '{r.timing_text[:60]}' names a day but expected_date is empty — {both}.")
    if r.status in ("open", "waiting", "watching") and r.expected_date is not None and not (r.time_role or "").strip():
        out.append(f"{r.situation_key}: has a date but no time_role — if the person's words make clear it HAPPENS at that time "
                   f"(appointment, meeting, call) or is a DEADLINE, set time_role; leave it empty only if unclear.")
    if r.status == "waiting" and not (r.waiting_on or "").strip():
        out.append(f"{r.situation_key}: status is waiting but waiting_on is empty — say what is awaited, or set status open.")
    return out


def _parse_date_arg(ed: str):
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", ed):
        return None, "expected_date must be YYYY-MM-DD"
    try:
        return datetime.strptime(ed[:10], "%Y-%m-%d"), None
    except ValueError:
        return None, "expected_date is not a real calendar date"


def _unknown_args(name: str, args: Dict[str, Any]) -> Optional[str]:
    allowed = ALLOWED_ARGS.get(name)
    if allowed is None:
        return None
    extra = sorted(set(args) - allowed)
    if extra:
        return (f"unsupported argument(s) for {name}: {', '.join(extra)}. "
                f"Allowed: {', '.join(sorted(allowed)) or '(none)'}. Nothing was changed.")
    return None


async def _tools(db: AsyncSession, workspace_id: str, owner: str, name: str, args: Dict[str, Any],
                 session_id: str = "", state: Optional[RunState] = None) -> Dict[str, Any]:
    from sqlmodel import select
    state = state or RunState()
    bad = _unknown_args(name, args)
    if bad:
        return {"error": bad}
    if name == "list_open":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.status.in_(["open", "waiting", "watching", "suppressed"])).order_by(LedgerItem.created_at))).scalars().all()
        state.seq += 1
        state.last_read_seq = state.seq
        return {"records": [_row_view(r) for r in rows]}
    if name == "search":
        q = str(args.get("query") or "").lower()
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner))).scalars().all()
        state.seq += 1
        state.last_read_seq = state.seq
        return {"matches": [_row_view(r) for r in rows
                            if q and q in (str(r.title or "") + " " + str(r.detail or "")).lower()]}
    if name == "history":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.situation_key == str(args.get("key") or "")))).scalars().all()
        if not rows:
            return {"error": "no such key — inspect first, never invent keys"}
        return {"record": _row_view(rows[0]), "sources": (rows[0].source_refs_json or "")[:1500]}
    if name == "update_item":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.situation_key == str(args.get("key") or "")))).scalars().all()
        if not rows:
            return {"error": "no such key — inspect first, never invent keys"}
        r = rows[0]
        st = str(args.get("status") or "").strip()
        if st == "answered":
            st = "done"  # contract status: answered approvals resolve as done
        if st and st not in STATUSES + CLOSING:
            return {"error": f"illegal status {st}"}
        if st in CLOSING and not str(args.get("evidence") or "").strip():
            return {"error": "closing requires evidence quoting proof"}
        if st in CLOSING and _TRANSCRIPT_CTX.get():
            ev_check = str(args.get("evidence") or "")
            if not _evidence_in_transcript(ev_check, _TRANSCRIPT_CTX.get() or ""):
                return {"error": "evidence quote not found in this session's transcript — quote what was actually said"}
        conf = str(args.get("confidence") or "").strip().lower()
        if conf and conf not in ("observed", "reported", "inferred"):
            return {"error": "confidence must be observed, reported or inferred"}
        ed = str(args.get("expected_date") or "").strip()
        new_date = None
        if ed:
            new_date, err = _parse_date_arg(ed)
            if err:
                return {"error": err}
        tf, terr = _parse_time_fields(args, r.expected_date)
        if terr:
            return {"error": terr}
        if tf.get("expected_time") and new_date is None and r.expected_date is None:
            return {"error": "expected_time needs an expected_date (set the date in the same call)"}
        if st in CLOSING and new_date is not None and r.expected_date is not None and new_date.date() != r.expected_date.date():
            return {"error": "a close does not change when the thing was due. Keep the record's date as it is (the completion time belongs in the evidence quote); "
                             "if the person really moved the date, update the date in a separate call first, then close."}
        before = _record_view_fields(r)
        prior_detail = r.detail or ""
        for f, lim in (("detail", 2000), ("timing_text", 300), ("waiting_on", 300), ("question_text", 500)):
            v = args.get(f)
            if isinstance(v, str) and v.strip():
                setattr(r, f, v.strip()[:lim])
        # An explicit empty string clears a stale wait/question the news has answered.
        for f in ("waiting_on", "question_text"):
            if f in args and isinstance(args.get(f), str) and not args[f].strip():
                setattr(r, f, "")
        if isinstance(args.get("kind"), str) and args["kind"].strip():
            r.kind = args["kind"].strip()[:40]
        if conf:
            r.confidence = conf
        if new_date is not None:
            r.expected_date = new_date
        if tf.get("expected_time") and not (tf.get("time_basis") or r.time_basis):
            return {"error": "when you set expected_time also set time_basis: 'stated' if the person gave that time, 'assumed' if it is your likeliest reading (e.g. 'at 6' -> 18:00; keep the ambiguity in question_text)"}
        if "expected_time" in tf and not tf["expected_time"]:
            tf["time_basis"] = ""
        for k, v in tf.items():
            setattr(r, k, v)
        if (new_date is not None or tf.get("expected_time")) and _TZ_CTX.get():
            r.time_zone = _TZ_CTX.get()          # code stamps the zone the date/time were stated in
        if st:
            r.status = st
        ev = str(args.get("evidence") or "").strip()
        try:
            refs = json.loads(r.source_refs_json or "{}")
        except Exception:
            refs = {}
        if not isinstance(refs, dict):
            refs = {"prior": refs}
        if prior_detail and (r.detail or "") != prior_detail:
            hist = refs.get("detail_history") or []
            refs["detail_history"] = (hist + [prior_detail[:500]])[-5:]
        if args.get("reminder_authorised") is True:
            r.authorised_json = json.dumps({"reminder": True, "at": session_id})
        if ev:
            prior = refs.get("agent_evidence") or refs.get("evidence") or []
            verified, reported = _evidence_spans(ev, _TRANSCRIPT_CTX.get() or "")
            refs["agent_evidence"] = ([prior] if isinstance(prior, str) else (prior or [])) + verified
            if reported:
                prior_rep = refs.get("reported") or []
                refs["reported"] = ([prior_rep] if isinstance(prior_rep, str) else (prior_rep or [])) + [reported]
        r.source_refs_json = json.dumps(refs)[:4000]
        r.updated_at = utc_now()
        await db.commit()
        state.seq += 1
        state.last_write_seq = state.seq
        state.touched.add(str(r.situation_key))
        out: Dict[str, Any] = {"ok": True, "changed": _diff(before, _record_view_fields(r)), "record": _row_view(r)}
        if st in CLOSING:
            try:       # a follow-up toward a matter that is over is moot
                from src.services import attention_cycle as _ac
                n = await _ac.supersede_for_closed_matter(db, workspace_id=workspace_id, owner=owner, matter_key=str(r.situation_key))
                if n:
                    out["follow_ups_superseded"] = n
            except Exception as exc:
                logger.warning("[maintenance] supersede follow-ups failed open: %s", exc)
        adv = _advisories(r)
        if adv:
            out["advisories"] = adv
        return out
    if name == "create_item":
        title = str(args.get("title") or "").strip()
        if not title or title.lower() in ("none", "n/a", "no change", "no changes", "nothing", "nothing new"):
            return {"error": "title required — NONE/nothing is not a trackable matter"}
        key = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.situation_key == key))).scalars().all()
        if rows:
            return {"error": f"key {key} exists — update it instead of duplicating"}
        st = str(args.get("status") or "open").strip() or "open"
        if st not in STATUSES:
            return {"error": f"a new record starts open/waiting/watching/suppressed, not {st}"}
        conf = str(args.get("confidence") or "reported").strip().lower() or "reported"
        if conf not in ("observed", "reported", "inferred"):
            return {"error": "confidence must be observed, reported or inferred"}
        ed = str(args.get("expected_date") or "").strip()
        new_date = None
        if ed:
            new_date, err = _parse_date_arg(ed)
            if err:
                return {"error": err}
        tf, terr = _parse_time_fields(args, new_date)
        if terr:
            return {"error": terr}
        if tf.get("expected_time") and new_date is None:
            return {"error": "expected_time needs an expected_date (set the date in the same call)"}
        if tf.get("expected_time") and not tf.get("time_basis"):
            return {"error": "when you set expected_time also set time_basis: 'stated' if the person gave that time, 'assumed' if it is your likeliest reading (e.g. 'at 6' -> 18:00; keep the ambiguity in question_text)"}
        timing = str(args.get("timing") or "").strip()
        ev = str(args.get("evidence") or "").strip()
        verified, reported = _evidence_spans(ev, _TRANSCRIPT_CTX.get() or "") if ev else ([], "")
        refs = {"session": session_id, "evidence": verified if _TRANSCRIPT_CTX.get() else ([ev[:500]] if ev else [])}
        if reported:
            refs["reported"] = [reported]
        row = LedgerItem(honcho_workspace_id=workspace_id, owner_peer_id=owner,
                         kind=str(args.get("kind") or "situation")[:40], title=title[:500],
                         detail=str(args.get("detail") or "")[:2000], status=st,
                         situation_key=key, timing_text=timing[:300], expected_date=new_date,
                         waiting_on=str(args.get("waiting_on") or "")[:300],
                         question_text=str(args.get("question_text") or "")[:500],
                         confidence=conf, source_refs_json=json.dumps(refs)[:4000],
                         expected_time=tf.get("expected_time", ""), time_basis=tf.get("time_basis", "") if tf.get("expected_time") else "",
                         time_role=tf.get("time_role", ""),
                         importance=tf.get("importance", 2),
                         time_zone=(_TZ_CTX.get() if (new_date is not None) else ""),
                         authorised_json=json.dumps({"reminder": True, "at": session_id}) if args.get("reminder_authorised") is True else "{}")
        db.add(row)
        await db.commit()
        state.seq += 1
        state.last_write_seq = state.seq
        state.touched.add(key)
        out = {"ok": True, "key": key, "record": _row_view(row)}
        adv = _advisories(row)
        if adv:
            out["advisories"] = adv
        return out
    return {"error": "unknown tool"}


def _norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _evidence_spans(evidence: str, transcript: str) -> tuple[list, str]:
    """Split evidence into transcript-verified quotes vs reported paraphrase.
    Only verified spans are stored as quotations; the rest is kept separately
    as reported (never presented as quoted proof)."""
    norm_t = _norm_text(transcript)
    verified: list = []
    reported: list = []
    if not norm_t:
        return verified, evidence.strip()
    for raw in re.split(r"\n", evidence):
        line = raw.strip()
        if not line:
            continue
        spans = [s.strip() for s in re.split(r"[\"“”']", line) if s.strip()]
        cands = [c for c in spans if len(_norm_text(c)) >= 20]
        if not cands:
            cands = [s.strip() for s in re.split(r"[.!?]+", line) if len(_norm_text(s)) >= 20][:1]
        hit = [c for c in cands if _norm_text(c) in norm_t]
        if hit:
            verified.extend(hit)
            rest = line
            for h in hit:
                rest = rest.replace(h, "", 1)
            if _norm_text(rest).strip(" ,;:-"):
                reported.append(rest.strip(" ,;:-"))
        else:
            reported.append(line)
    return verified, " ".join(reported)[:1000]


def _evidence_in_transcript(evidence: str, transcript: str) -> bool:
    verified, _ = _evidence_spans(evidence, transcript)
    return bool(verified)


async def _check_finish(db: AsyncSession, workspace_id: str, owner: str, args: Dict[str, Any],
                        state: RunState) -> List[str]:
    """Mechanical conditions for ending the run. Returns the problems found
    (empty = accepted). Judges nothing about meaning: only that the state was
    re-read after the last write, every observation is accounted for, and every
    record the agent claims to have changed was actually changed in this run."""
    from sqlmodel import select
    problems: List[str] = []
    if state.wrote() and state.last_read_seq < state.last_write_seq:
        problems.append("Re-list (list_open) AFTER your last write and check the fields before finishing.")
    acc = args.get("accounting")
    entries: List[Dict[str, Any]] = []
    if state.n_obs > 0:
        if not isinstance(acc, list) or not acc:
            problems.append(f"accounting is required: one entry per observation O1..O{state.n_obs}.")
        else:
            seen: Set[int] = set()
            for e in acc:
                if not isinstance(e, dict):
                    problems.append("each accounting entry must be an object {obs, treatment, key?, note?}.")
                    continue
                try:
                    n = int(e.get("obs"))
                except (TypeError, ValueError):
                    problems.append(f"accounting entry has no integer obs: {str(e)[:80]}")
                    continue
                if n == 0:        # a matter the agent added from the transcript: must be a record touched in this run
                    k0 = str(e.get("key") or "").strip()
                    if not k0 or k0 not in state.touched:
                        problems.append("obs 0 (added from the transcript) needs the key of a record you created or changed in this run.")
                    else:
                        entries.append({"obs": 0, "treatment": "applied", "key": k0, "note": str(e.get("note") or "")[:200] or None})
                    continue
                if not 1 <= n <= state.n_obs:
                    problems.append(f"accounting names observation {n}, but only O1..O{state.n_obs} exist.")
                    continue
                t = str(e.get("treatment") or "").strip().lower()
                key = str(e.get("key") or "").strip()
                note = str(e.get("note") or "").strip()
                if t not in TREATMENTS:
                    problems.append(f"O{n}: treatment must be one of {', '.join(TREATMENTS)}.")
                    continue
                if t in ("applied", "merged"):
                    if not key:
                        problems.append(f"O{n}: {t} needs the key of the record you changed or created.")
                    elif key not in state.touched:
                        problems.append(f"O{n}: you did not change or create '{key}' in this run. "
                                        f"Make the change, or account it as no_change (a record already reflects it) or skipped.")
                elif t == "no_change":
                    if not key or not note:
                        problems.append(f"O{n}: no_change needs the key of the record that already reflects it and a note.")
                    else:
                        exists = (await db.execute(select(LedgerItem).where(
                            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
                            LedgerItem.situation_key == key))).scalars().first()
                        if exists is None:
                            problems.append(f"O{n}: no_change names '{key}', which does not exist.")
                elif t == "skipped" and not note:
                    problems.append(f"O{n}: skipped needs a note saying why it is not an operational matter.")
                seen.add(n)
                entries.append({"obs": n, "treatment": t, "key": key or None, "note": note[:200] or None})
            missing = [n for n in range(1, state.n_obs + 1) if n not in seen]
            if missing:
                problems.append("unaccounted observations: " + ", ".join(f"O{n}" for n in missing) + ".")
    if state.has_transcript and not str(args.get("transcript_sweep") or "").strip():
        problems.append("transcript_sweep is required: in one line say what, if anything, the transcript contained that no observation covered "
                        "(a promise, appointment, reminder, stand-down, aspiration), or 'nothing beyond the observations'. Handle anything you list.")
    if state.advisory_rounds < 2 and state.touched:
        adv: List[str] = []
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.situation_key.in_(list(state.touched))))).scalars().all()
        by_key = {str(r.situation_key): r for r in rows}
        for r in rows:
            adv.extend(_advisories(r))
        # A time of day the person stated unambiguously ("by 5pm", "15:30") should reach expected_time. A lexical NOMINATION
        # for the agent to confirm or decline — it is advice; code never sets the field.
        for e in entries:
            raw_t = state.obs_timing.get(e["obs"], "")
            rec = by_key.get(str(e.get("key") or ""))
            if (raw_t and rec is not None and e["treatment"] in ("applied", "merged") and not (rec.expected_time or "").strip()
                    and rec.expected_date is not None and re.search(r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b|\b([01]?\d|2[0-3]):[0-5]\d\b", raw_t, re.IGNORECASE)):
                adv.append(f"{rec.situation_key}: O{e['obs']} states a time of day (\"{raw_t[:60]}\") but expected_time is empty — set it in 24-hour HH:MM if it is unambiguous.")
        # A precise clock time whose observation carried no am/pm must be labelled as an assumption (never silently presented as stated).
        for e in entries:
            raw_t = state.obs_timing.get(e["obs"], "")
            rec = by_key.get(str(e.get("key") or ""))
            if (raw_t and rec is not None and (rec.expected_time or "").strip() and (rec.time_basis or "") != "assumed"
                    and e["treatment"] in ("applied", "merged")
                    and re.search(r"\bat\s+\d{1,2}\b(?!\s?(:\d{2}|am|pm|a\.m|p\.m))", raw_t, re.IGNORECASE)
                    and not re.search(r"\b\d{1,2}(:\d{2})?\s?(am|pm)\b|\b([01]?\d|2[0-3]):[0-5]\d\b|\bo.clock\b|\b(morning|evening|afternoon|night|noon|midnight)\b", raw_t, re.IGNORECASE)):
                adv.append(f"{rec.situation_key}: O{e['obs']}'s words (\"{raw_t[:60]}\") give no am/pm, so expected_time {rec.expected_time} is your reading: "
                           f"set time_basis \"assumed\" and keep the open question (unless the transcript states which).")
        # A day the person named in their own timing words ("due on Sunday") should reach expected_date. Direction (past or coming)
        # is the model's call, so both candidates are offered; code never sets the field.
        from src.services.memory_pipeline import resolve_date
        today_s = _TODAY_CTX.get()
        for e in entries:
            raw_t = state.obs_timing.get(e["obs"], "")
            rec = by_key.get(str(e.get("key") or ""))
            if raw_t and today_s and rec is not None and e["treatment"] in ("applied", "merged") and rec.expected_date is None:
                d = resolve_date(raw_t.strip('"'), today_s)
                if d is not None:
                    up = d.strftime("%Y-%m-%d")
                    prev = (d - timedelta(days=7)).strftime("%Y-%m-%d") if up != today_s else None
                    adv.append(f"{rec.situation_key}: O{e['obs']} names a day (\"{raw_t[:60]}\") but expected_date is empty — "
                               + (f"upcoming {up}, most recent {prev}; set the one the person meant." if prev else f"that is {up}."))
        # The person's own words for timing must survive the hand-off ("tomorrow at 6" is not just a date).
        for e in entries:
            raw_t = state.obs_timing.get(e["obs"], "")
            rec = by_key.get(str(e.get("key") or ""))
            if raw_t and rec is not None and e["treatment"] in ("applied", "merged") and not (rec.timing_text or "").strip():
                adv.append(f"{rec.situation_key}: O{e['obs']} gave the person's own timing words \"{raw_t[:60]}\" but timing_text is empty — keep them (time of day matters).")
        if adv:
            state.advisory_rounds += 1
            problems.append("Check these before finishing (finish again if you disagree): " + " | ".join(adv))
    state.accounting = entries
    return problems


async def run_maintenance(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str,
                          observations: str, today: str, n_observations: int = 0,
                          transcript: str = "", time_zone: str = "UTC",
                          weekday: str = "", obs_timing: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    """Agentic maintenance loop over numbered witness observations. `today` is
    the person's local date (YYYY-MM-DD) at the time of the session. Returns an
    outcome with grounding: verified / finished_unchecked / unfinished / ..."""
    started = datetime.now(timezone.utc)
    t_tx = _TRANSCRIPT_CTX.set(transcript or "")
    t_day = _TODAY_CTX.set(today or "")
    t_tz = _TZ_CTX.set(time_zone or "")
    try:
        return await _run_maintenance_inner(
            db, workspace_id=workspace_id, owner=owner, session_id=session_id,
            observations=observations, today=today, n_obs=n_observations, started=started,
            time_zone=time_zone, weekday=weekday, obs_timing=obs_timing or {}, transcript=transcript)
    finally:
        _TRANSCRIPT_CTX.reset(t_tx)
        _TODAY_CTX.reset(t_day)
        _TZ_CTX.reset(t_tz)


def _trim(v: Any, n: int) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "…"


async def _run_maintenance_inner(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str,
                                 observations: str, today: str, n_obs: int, started: Any,
                                 time_zone: str, weekday: str, obs_timing: Optional[Dict[int, str]] = None,
                                 transcript: str = "") -> Dict[str, Any]:
    calls: List[Dict[str, Any]] = []
    inspected = False
    finished_summary: Optional[str] = None
    gate_passed = False
    changes = {"created": 0, "updated": 0, "closed": 0}
    state = RunState(n_obs=n_obs)
    state.obs_timing = dict(obs_timing or {})
    state.has_transcript = bool(transcript)
    models_tried = [PRIMARY_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != PRIMARY_MODEL:
        models_tried.append(FALLBACK_MODEL)
    day = f"{weekday} {today}".strip()
    # The first read of the agenda is always list_open, so code does it and hands the result over: one fewer model round trip on every run.
    # The finish gate still requires a re-read AFTER the last write.
    opening = await _tools(db, workspace_id, owner, "list_open", {}, session_id, state)
    inspected = True
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": CONTRACT + f"\n\nToday is {day} (the person's local date; timezone {time_zone}).\nMake all independent tool calls in a single turn."},
        {"role": "user", "content": "New session observations. Maintain the agenda.\n\nCurrent open records (already listed for you; list_open again after your last write):\n"
         + _trim(opening, 6000) + "\n\n" + observations
         + (("\n\n--- session transcript (ground truth; quote the person's own words as evidence) ---\n"
             + transcript[-8000:]) if transcript else "")}]
    model_used = models_tried[0]
    for _ in range(MAX_ITERS):
        out = await _chat(model_used, messages)
        if out is None and len(models_tried) > 1 and model_used == models_tried[0]:
            logger.warning("maintenance primary failed, trying fallback %s", models_tried[1])
            model_used = models_tried[1]
            out = await _chat(model_used, messages)
        if out is None:
            break
        tool_calls = out.get("tool_calls") or []
        calls.append({"model": out.get("model"), "provider": out.get("provider"), "usage": out.get("usage"),
                      "finish_reason": out.get("finish_reason"), "n_tools": len(tool_calls), "trace": []})
        assistant: Dict[str, Any] = {"role": "assistant", "content": out.get("content") or ""}
        if tool_calls:
            assistant["tool_calls"] = tool_calls
        messages.append(assistant)
        if not tool_calls:
            messages.append({"role": "user", "content": "You made no tool calls. Inspect the records (list_open minimum) before finishing — unverified claims of completion will be recorded as never_inspected."})
            continue
        truncated = out.get("finish_reason") == "length"
        done = False
        for tc in tool_calls:
            fn = tc.get("function") or {}
            name = str(fn.get("name") or "")
            raw_args = fn.get("arguments") or "{}"
            calls[-1].setdefault("ops", []).append(name)
            res: Dict[str, Any]
            args: Dict[str, Any] = {}
            if truncated:
                res = {"error": "your output was cut off (length limit) so this call's arguments may be incomplete. Nothing ran. Resend it, shorter."}
            else:
                try:
                    parsed = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except Exception:
                    parsed = None
                if not isinstance(parsed, dict):
                    res = {"error": "arguments were not a valid JSON object. Nothing ran. Resend this call with valid JSON."}
                else:
                    args = parsed
                    res = {}
            if not res:
                if name in ("list_open", "search", "history"):
                    inspected = True
                if name == "finish":
                    problems = await _check_finish(db, workspace_id, owner, args, state)
                    if problems and state.finish_bounces < MAX_FINISH_BOUNCES:
                        state.finish_bounces += 1
                        res = {"error": "finish refused — fix these and finish again", "problems": problems}
                    else:
                        finished_summary = str(args.get("summary") or "")[:500]
                        gate_passed = not problems
                        if problems:
                            state.gate_failures = problems
                            res = {"ok": True, "note": "accepted without passing the checks; recorded for review", "problems": problems}
                        else:
                            res = {"ok": True}
                        done = True
                else:
                    try:
                        res = await _tools(db, workspace_id, owner, name, args, session_id=session_id, state=state)
                    except Exception as exc:
                        res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
                    if isinstance(res, dict) and res.get("ok") is True:
                        if name == "create_item":
                            changes["created"] += 1
                        elif name == "update_item":
                            if str(args.get("status") or "") in CLOSING:
                                changes["closed"] += 1
                            else:
                                changes["updated"] += 1
            calls[-1]["trace"].append({"name": name, "args": _trim(raw_args, 600), "result": _trim(res, 500)})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": name,
                             "content": json.dumps(res)[:3000]})
            if done:
                break
        if done:
            break
    ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
    if finished_summary is not None and inspected and gate_passed:
        status = "verified"
    elif finished_summary is not None and inspected:
        status = "finished_unchecked"
    elif finished_summary is not None:
        status = "finished_without_inspection"
    else:
        status = "never_inspected" if not inspected else "unfinished"
    logger.info("[maintenance] %s %s -> %s (%d calls)", owner, session_id, status, len(calls))
    return {"status": status, "summary": finished_summary, "calls": calls,
            "inspected": inspected, "model": model_used, "ms": ms, "changes": changes,
            "accounting": state.accounting, "gate_failures": state.gate_failures,
            "touched_keys": sorted(state.touched), "wrote": state.wrote()}
