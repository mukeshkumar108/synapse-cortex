"""Operational attention cycle: review, intend, persist, follow through.

The ledger knows what's on someone's plate. This decides what deserves
attention, persists Sophie's intentions as durable actions, tracks what she
actually did about them, and keeps due-but-undelivered actions visible until
a real delivery channel reports success.

Same philosophy as the maintenance agent: capable inexpensive model, scoped
records, a clock, a clear contract, tools to investigate and act. Deterministic
code owns states, dedupe, idempotency and audit; the model owns judgment.
Delivery adapters (push, messaging) connect later through the scheduled-action
interface built here — never claimed sent unless delivery succeeds.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional
from uuid import UUID

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.world import AttentionAction, AttentionEvent, utc_now

logger = logging.getLogger(__name__)

PRIMARY_MODEL = os.getenv("ATTENTION_MODEL", "openrouter:qwen/qwen3.7-flash")
FALLBACK_MODEL = os.getenv("ATTENTION_FALLBACK_MODEL", "qwen/qwen3.8-27b")
MAX_ITERS = int(os.getenv("ATTENTION_MAX_ITERS", "10"))
CALL_TIMEOUT_S = float(os.getenv("ATTENTION_TIMEOUT_S", "90"))

ACTION_STATES = ("pending", "due", "held", "delivered", "cancelled", "expired", "superseded")
EVENT_KINDS = ("decided", "scheduled", "surfaced", "attempted", "delivered", "responded",
               "snoozed", "suppressed", "unsuppressed", "rescheduled", "cancelled", "expired")

import contextvars as _cv
_TZ_CTX: _cv.ContextVar[str] = _cv.ContextVar("attention_tz", default="UTC")
_NOW_CTX: _cv.ContextVar[Optional[datetime]] = _cv.ContextVar("attention_now", default=None)   # naive UTC "now" of this review


async def supersede_for_closed_matter(db: AsyncSession, *, workspace_id: str, owner: str, matter_key: str,
                                      why: str = "matter closed") -> int:
    """A follow-up toward a matter that is over is moot. Mechanical consequence of a close:
    its pending/due/held intentions are superseded (audited), never delivered."""
    rows = (await db.execute(select(AttentionAction).where(
        AttentionAction.honcho_workspace_id == workspace_id, AttentionAction.owner_peer_id == owner,
        AttentionAction.matter_key == matter_key,
        AttentionAction.state.in_(["pending", "due", "held"])))).scalars().all()
    for r in rows:
        r.state = "superseded"
        r.updated_at = utc_now()
        await _event(db, workspace_id, owner, "cancelled", f"{why}: {r.intent[:120]}", "matter-lifecycle",
                     action_id=r.id, matter_key=matter_key)
    if rows:
        await db.commit()
    return len(rows)


def _due_problem(due_at: Optional[datetime]) -> Optional[str]:
    now = _NOW_CTX.get()
    if due_at is not None and now is not None and due_at < now.replace(tzinfo=None) - __import__("datetime").timedelta(minutes=5):
        return f"due_at is in the past (it is now {now.strftime('%Y-%m-%dT%H:%M')} UTC); pick a time that has not happened yet, or null"
    return None


def local_to_utc_naive(raw: str, tz_name: Optional[str] = None) -> Optional[datetime]:
    """due_at arrives as the person's LOCAL wall-clock (YYYY-MM-DDTHH:MM); it is
    stored as naive UTC so the deterministic due-scan stays timezone-free."""
    from zoneinfo import ZoneInfo
    tz_name = tz_name or _TZ_CTX.get() or "UTC"
    try:
        zi = ZoneInfo(tz_name)
    except Exception:
        zi = ZoneInfo("UTC")
    try:
        local = datetime.fromisoformat(raw[:16]).replace(tzinfo=zi)
    except ValueError:
        return None
    return local.astimezone(timezone.utc).replace(tzinfo=None)


CONTRACT = """You review what is on someone's plate and decide what deserves attention. You are an executive assistant with judgment, not a reminder rulebook. A dentist appointment and a vague walk idea must not receive identical treatment.

Responsibility is always toward the user: reminders and follow-ups are FOR him, never for Sophie. Phrase every intent accordingly ("Remind him Thursday morning", never "Remind Sophie"). The stored matter already says whose appointment it is; your intent says what YOU will do about it.

You have: open operational matters (with dates, people, dependencies), the history of what Sophie already did about each (asked, reminded, snoozed, suppressed, delivered, responses), and the clock.

Decide per matter: schedule a reminder or follow-up (with a due time), flag it for the next conversation, defer it, suppress it (scoped: what exactly to stop, and until when), reschedule/cancel existing intentions whose matter changed, or do nothing. Doing nothing is often correct.

Reason freely, act on what is known. A matter time marked "assumed" (the model's reading, e.g. "at 6" taken as 18:00) is context, not a confirmed instruction: do not build a time-triggered reminder on it — leave due_at null and say what is unclear in timing_note, or schedule for the next conversation. Only a time marked "stated" may trigger a timed follow-up. Situations: besides operational matters you can see SITUATIONS (list_situations) — developing matters that are not tasks: a family member's illness, a worry, a health observation, an unresolved decision, a curiosity. Hold a follow-up for one only when you have judged it worth returning to: schedule_action with source "entity" and source_ref set to the situation's id (it keeps its own facts; never copy them). due_at is when it becomes relevant (a check-in AFTER the tests, not before); expires_at is when to stop. A situation marked suppressed is the person's boundary: schedule nothing for it. Be gentle with sensitive ones: one well-timed check-in is enough, and an answer or a deflection settles that follow-up (the situation itself stays remembered). Record `surfaced` when it was raised and `responded` when the person answered, so the same worry is not raised again and again.

Rules: never duplicate an open intention for the same matter — update it. A held or suppressed action stays held until its condition lapses or evidence changes it; say what would unhold it. If the user said to stop fussing, record the scope of that response and adjust — it rarely cancels the matter itself. Delivery is a separate channel: schedule freely, but only the delivery path marks delivered. Verify before finish: re-list intentions and confirm each matches your decisions."""

TOOLS = [
    {"type": "function", "function": {"name": "list_matters", "description": "Open operational matters with keys, dates, people, dependencies.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "list_situations", "description": "Developing situations (not tasks): id, name, kind, short summary, sensitive, suppressed, days since last update.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "attention_history", "description": "What Sophie already did: events newest-first, optional matter filter.", "parameters": {"type": "object", "properties": {"matter": {"type": "string"}, "limit": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "list_actions", "description": "Current intentions (pending/due/held), optional matter filter.", "parameters": {"type": "object", "properties": {"matter": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "schedule_action", "description": "Persist an intention Sophie holds toward the user (reminders are FOR him, never for Sophie: 'Remind him Thursday morning'). Matter key (or null), what she intends + why, kind reminder/followup/surface/opportunity, due_at YYYY-MM-DDTHH:MM in the PERSON'S LOCAL time (code converts it) or null, timing_note for uncertainty. Duplicates of open intentions are refused — update instead.", "parameters": {"type": "object", "properties": {"matter": {"type": "string"}, "intent": {"type": "string"}, "why": {"type": "string"}, "kind": {"type": "string"}, "due_at": {"type": "string"}, "timing_note": {"type": "string"}, "source": {"type": "string"}, "source_ref": {"type": "string"}, "expires_at": {"type": "string"}}, "required": ["intent"]}}},
    {"type": "function", "function": {"name": "update_action", "description": "Change an intention by id: state (pending/due/held/cancelled/expired/superseded — delivered only with evidence of actual delivery), due_at, timing_note. Reschedule by setting a new due_at (old value kept in history).", "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "state": {"type": "string"}, "due_at": {"type": "string"}, "timing_note": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "record_event", "description": "Record what happened: responded/snoozed/suppressed/surfaced/attempted with detail (e.g. user said stop fussing — scope it).", "parameters": {"type": "object", "properties": {"matter": {"type": "string"}, "action": {"type": "string"}, "event": {"type": "string"}, "detail": {"type": "string"}}, "required": ["event"]}}},
    {"type": "function", "function": {"name": "finish", "description": "End only after verifying intentions match decisions.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]

_chat_fn: Optional[Callable[..., Any]] = None


def set_chat_fn(fn: Optional[Callable[..., Any]]) -> None:
    global _chat_fn
    _chat_fn = fn


async def _chat(model: str, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
    if _chat_fn is not None:
        out = _chat_fn(model, messages)
        if hasattr(out, "__await__"):
            out = await out
        return out
    via_or = model.startswith("openrouter:")
    mid = model.split(":", 1)[1] if via_or else model
    key = os.getenv("OPENROUTER_API_KEY", "").strip() if via_or else os.getenv("NANO_API_KEY", "").strip()
    base = "https://openrouter.ai/api/v1" if via_or else os.getenv("NANO_BASE_URL", "https://nano-gpt.com/api/v1").rstrip("/")
    if not key:
        return None
    t0 = time.monotonic()
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if via_or:
            headers["X-Title"] = "cortex-attention"
        body: Dict[str, Any] = {"model": mid, "messages": messages, "tools": TOOLS,
                                "tool_choice": "auto", "max_tokens": int(os.getenv("ATTENTION_MAX_TOKENS", "2500"))}
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as client:
            resp = await client.post(base + "/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            used = data.get("usage") or {}
            logger.info("llm_usage module=attention provider=%s model=%s in=%s out=%s reasoning=%s ms=%d",
                        "openrouter" if via_or else "nanogpt", mid, used.get("prompt_tokens"),
                        used.get("completion_tokens"), used.get("reasoning_tokens", 0),
                        int((time.monotonic() - t0) * 1000))
            return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [],
                    "finish_reason": data["choices"][0].get("finish_reason"), "model": model, "provider": "openrouter" if via_or else "nanogpt", "usage": used}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("attention chat failed (%s): %s%s", model, type(exc).__name__,
                       f" HTTP {status}" if status else "")
        return None


def _action_view(a: AttentionAction) -> Dict[str, Any]:
    return {"id": str(a.id), "matter": a.matter_key, "intent": a.intent, "why": a.why,
            "kind": a.kind,
            # stored as naive UTC; emitted with its offset so every reader can convert to the person's clock
            "due_at": a.due_at.replace(tzinfo=timezone.utc).isoformat() if a.due_at else None,
            "timing_note": a.timing_note, "state": a.state, "source": a.source, "source_ref": a.source_ref,
            "expires_at": (a.expires_at.replace(tzinfo=timezone.utc).isoformat() if a.expires_at else None)}


async def describe_attention(db: AsyncSession, *, workspace_id: str, owner: str) -> List[str]:
    """Three-fact lines: what the user has on, what Sophie took responsibility
    for, and what has actually happened. Complete standalone statements."""
    from src.services.memory_pipeline import open_ledger
    items = {str(i.situation_key): i for i in await open_ledger(db, workspace_id, owner, limit=100)
             if i.situation_key}
    actions = await pending_attention(db, workspace_id=workspace_id, owner=owner)
    # Latest surfaced/responded event per matter, so the packet states history
    # as fact instead of re-asking blindly.
    hist_rows = (await db.execute(select(AttentionEvent).where(
        AttentionEvent.honcho_workspace_id == workspace_id,
        AttentionEvent.owner_peer_id == owner,
        AttentionEvent.event.in_(["surfaced", "attempted", "responded"]),
        AttentionEvent.matter_key.is_not(None)).order_by(
        AttentionEvent.created_at.desc()).limit(100))).scalars().all()
    hist: Dict[str, str] = {}
    for r in reversed(list(hist_rows)):
        key = str(r.matter_key)
        if r.event == "responded":
            hist[key] = f"user responded: {(r.detail or '')[:160]}"
        elif key not in hist:
            hist[key] = f"already asked ({(r.detail or '')[:120]})" if r.detail else "already asked once"
    lines = []
    for a in actions:
        m = items.get(str(a.get("matter") or ""))
        matter = m.title if m else "a tracked matter"       # no dates/timing here: the deterministic operational view owns those
        if a["state"] == "due":
            happened = "due now, not yet delivered"
        elif a.get("due_at"):
            happened = "scheduled, not yet delivered"
        else:
            happened = "open, no fixed time yet"
        line = f"{matter}. Sophie intends: {a['intent']} — {happened}."
        if a.get("matter") in hist:
            line += f" History: {hist[str(a['matter'])]}."
        lines.append(line)
    covered = {str(a.get("matter") or "") for a in actions}
    for key, m in items.items():
        # What attention uniquely knows is what has already been asked or answered. Missing details (an unanswered
        # question, an unknown time) are computed from the record by the deterministic view, never restated here.
        if key in covered or m.status not in ("open", "waiting", "watching") or key not in hist:
            continue
        lines.append(f"{m.title}. History: {hist[key]}.")
    return lines


async def _event(db: AsyncSession, workspace_id: str, owner: str, event: str,
                 detail: str = "", actor: str = "", action_id: Any = None,
                 matter_key: Optional[str] = None) -> None:
    db.add(AttentionEvent(honcho_workspace_id=workspace_id, owner_peer_id=owner,
                          action_id=action_id, matter_key=matter_key, event=event,
                          detail=detail[:1000], actor=actor[:120]))


def _allowed_args() -> Dict[str, set]:
    return {t["function"]["name"]: set((t["function"]["parameters"].get("properties") or {}).keys()) for t in TOOLS}


async def _tools(db: AsyncSession, workspace_id: str, owner: str, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    allowed = _allowed_args().get(name)
    if allowed is not None and set(args) - allowed:
        return {"error": f"unsupported argument(s) for {name}: {', '.join(sorted(set(args) - allowed))}. Allowed: {', '.join(sorted(allowed)) or '(none)'}. Nothing was changed."}
    if name == "list_matters":
        from src.services.memory_pipeline import open_ledger
        items = await open_ledger(db, workspace_id, owner, limit=100)
        return {"matters": [
            {"key": i.situation_key, "kind": i.kind, "status": i.status, "title": i.title,
             "detail": (i.detail or "")[:400], "timing": i.timing_text,
             "expected": i.expected_date.strftime("%Y-%m-%d") if i.expected_date else None,
             "waiting_on": i.waiting_on, "question": (i.question_text or "")[:300],
             "confidence": i.confidence} for i in items]}
    if name == "list_situations":
        from src.services import known_world as _kw
        ents = [e for e in await _kw.list_all(db, workspace_id, owner, statuses=("active", "dormant")) if _kw.is_situation(e)]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return {"situations": [{"id": str(e.id), "name": e.name, "kind": e.kind, "summary": e.summary[:200], "sensitive": e.sensitive,
                                "suppressed": e.suppressed, "status": e.status, "days_since_update": max(0, (now - e.last_touched_at.replace(tzinfo=None)).days)}
                               for e in ents]}
    if name == "attention_history":
        q = select(AttentionEvent).where(
            AttentionEvent.honcho_workspace_id == workspace_id,
            AttentionEvent.owner_peer_id == owner)
        if args.get("matter"):
            q = q.where(AttentionEvent.matter_key == str(args["matter"]))
        rows = (await db.execute(q.order_by(AttentionEvent.created_at.desc()).limit(
            min(int(args.get("limit") or 30), 100)))).scalars().all()
        return {"events": [{"event": r.event, "matter": r.matter_key, "detail": r.detail,
                            "actor": r.actor, "at": r.created_at.isoformat()} for r in rows]}
    if name == "list_actions":
        q = select(AttentionAction).where(
            AttentionAction.honcho_workspace_id == workspace_id,
            AttentionAction.owner_peer_id == owner,
            AttentionAction.state.in_(["pending", "due", "held"]))
        if args.get("matter"):
            q = q.where(AttentionAction.matter_key == str(args["matter"]))
        rows = (await db.execute(q.order_by(AttentionAction.created_at))).scalars().all()
        return {"actions": [_action_view(r) for r in rows]}
    if name == "schedule_action":
        from datetime import datetime as _dt
        intent = str(args.get("intent") or "").strip()
        if not intent:
            return {"error": "intent required"}
        kind = str(args.get("kind") or "followup").strip().lower()
        if kind not in ("reminder", "followup", "surface", "opportunity"):
            return {"error": f"illegal kind {kind}"}
        matter = str(args.get("matter") or "").strip() or None
        source, source_ref = str(args.get("source") or "").strip().lower(), str(args.get("source_ref") or "").strip()
        if source and source != "entity":
            return {"error": "source must be 'entity' (a situation) or omitted (an operational matter)"}
        if source == "entity":
            from src.services import known_world as _kw
            ent = await _kw.get(db, workspace_id, owner, source_ref)
            if ent is None or ent.status not in ("active", "dormant"):
                return {"error": "source_ref must be the id of a live entity or situation (see list_situations)"}
            if ent.suppressed:
                return {"error": f"'{ent.name}' is marked not to be raised unprompted (the person's boundary): schedule nothing for it"}
            matter, source_ref = None, str(ent.id)
        if matter:
            from src.models.world import LedgerItem
            led = (await db.execute(select(LedgerItem).where(
                LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
                LedgerItem.situation_key == matter))).scalars().first()
            if led is None:
                return {"error": f"unknown matter key '{matter}': use a key from list_matters, or null for a general intention"}
            if led.status in ("done", "cancelled", "answered"):
                return {"error": f"matter '{matter}' is {led.status}; there is nothing left to follow up"}
        due_at = None
        raw_due = str(args.get("due_at") or "").strip()
        if raw_due:
            try:
                due_at = local_to_utc_naive(raw_due)
            except ValueError:
                due_at = None
            if due_at is None:
                return {"error": "due_at must be YYYY-MM-DDTHH:MM (the person's local time)"}
            problem = _due_problem(due_at)
            if problem:
                return {"error": problem}
        expires_at = None
        raw_exp = str(args.get("expires_at") or "").strip()
        if raw_exp:
            expires_at = local_to_utc_naive(raw_exp)
            if expires_at is None:
                return {"error": "expires_at must be YYYY-MM-DDTHH:MM (the person's local time)"}
        dup_q = select(AttentionAction).where(
            AttentionAction.honcho_workspace_id == workspace_id,
            AttentionAction.owner_peer_id == owner,
            AttentionAction.state.in_(["pending", "due", "held"]))
        if matter:
            dup_q = dup_q.where(AttentionAction.matter_key == matter)
        elif source == "entity":
            dup_q = dup_q.where(AttentionAction.source == "entity", AttentionAction.source_ref == source_ref)
        else:
            dup_q = dup_q.where(AttentionAction.intent == intent[:500])
        dup = (await db.execute(dup_q.limit(1))).scalars().first()
        if dup is not None:
            return {"error": f"open intention already exists: {dup.id} ({dup.intent[:80]}) — update it instead",
                    "existing_id": str(dup.id)}
        row = AttentionAction(honcho_workspace_id=workspace_id, owner_peer_id=owner,
                              matter_key=matter, intent=intent[:500], why=str(args.get("why") or "")[:500],
                              kind=kind, due_at=due_at, timing_note=str(args.get("timing_note") or "")[:300],
                              source=source, source_ref=source_ref if source else "", expires_at=expires_at)
        db.add(row)
        await db.flush()
        await _event(db, workspace_id, owner, "scheduled", intent[:200], "attention-agent",
                     action_id=row.id, matter_key=matter)
        await db.commit()
        return {"ok": True, "action": _action_view(row)}
    if name == "update_action":
        try:
            uid = args.get("id", "")
            from uuid import UUID as _UUID
            row = (await db.execute(select(AttentionAction).where(
                AttentionAction.id == _UUID(str(uid)),
                AttentionAction.honcho_workspace_id == workspace_id,
                AttentionAction.owner_peer_id == owner))).scalars().first()
        except Exception:
            return {"error": "unknown action id"}
        if row is None:
            return {"error": "unknown action id"}
        st = str(args.get("state") or "").strip()
        if st and st not in ("pending", "due", "held", "cancelled", "expired", "superseded", "delivered"):
            return {"error": f"illegal state {st}"}
        if st == "delivered" and not str(args.get("evidence") or "").strip():
            return {"error": "delivered requires evidence of actual delivery"}
        if st:
            row.state = st
        raw_due = str(args.get("due_at") or "").strip()
        if raw_due:
            from datetime import datetime as _dt
            new_due = local_to_utc_naive(raw_due)
            if new_due is None:
                return {"error": "due_at must be YYYY-MM-DDTHH:MM (the person's local time)"}
            problem = _due_problem(new_due)
            if problem:
                return {"error": problem}
            row.due_at = new_due
        if isinstance(args.get("timing_note"), str):
            row.timing_note = args["timing_note"][:300]
        row.updated_at = utc_now()
        await _event(db, workspace_id, owner, "rescheduled" if raw_due else (st or "updated"),
                     str(args.get("evidence") or row.intent)[:300], "attention-agent",
                     action_id=row.id, matter_key=row.matter_key)
        await db.commit()
        return {"ok": True, "action": _action_view(row)}
    if name == "record_event":
        ev = str(args.get("event") or "").strip()
        if ev not in EVENT_KINDS:
            return {"error": f"illegal event {ev}"}
        aid = None
        if args.get("action"):
            try:
                from uuid import UUID as _UUID
                aid = _UUID(str(args["action"]))
            except Exception:
                pass
        await _event(db, workspace_id, owner, ev, str(args.get("detail") or "")[:500],
                     "attention-agent", action_id=aid,
                     matter_key=str(args.get("matter") or "").strip() or None)
        if ev in ("surfaced", "responded", "snoozed", "suppressed"):
            # ENGAGEMENT (the companion raised it / the person answered), recorded apart from EXPOSURE (it was merely in the packet)
            from src.services import known_world as _kw
            ref_kind, ref = None, None
            if aid is not None:
                act = (await db.execute(select(AttentionAction).where(AttentionAction.id == aid, AttentionAction.honcho_workspace_id == workspace_id,
                                                                      AttentionAction.owner_peer_id == owner))).scalars().first()
                if act is not None and act.source == "entity":
                    ref_kind, ref = "entity", act.source_ref
            if ref is None and args.get("matter"):
                ref_kind, ref = "ledger", str(args["matter"]).strip()
            if ref:
                await _kw.record_engagement(db, workspace_id, owner, ref_kind, ref)
        await db.commit()
        return {"ok": True}
    return {"error": "unknown tool"}


async def run_attention_review(db: AsyncSession, *, workspace_id: str, owner: str,
                               today_utc: Optional[str] = None,
                               reason: str = "scheduled",
                               findings: Optional[str] = None,
                               time_zone: str = "UTC", weekday: str = "",
                               now_utc: Optional[datetime] = None) -> Dict[str, Any]:
    """One attention review: agent examines matters + history + clock, decides,
    persists intentions. Returns grounded outcome (verified / no_change_verified
    / never_inspected / unfinished). When session findings are supplied, the
    agent also closes the loop: questions Sophie asked become surfaced events,
    user answers/declines become responded events on the tracked unknowns."""
    from datetime import datetime as _dt
    started = _dt.now(timezone.utc)
    today_utc = today_utc or started.date().isoformat()
    _tz_token = _TZ_CTX.set(time_zone or "UTC")
    _now_token = _NOW_CTX.set((now_utc.astimezone(timezone.utc).replace(tzinfo=None) if now_utc and now_utc.tzinfo else now_utc)
                              or started.replace(tzinfo=None))
    try:
        return await _run_attention_review_inner(
            db, workspace_id=workspace_id, owner=owner, today=today_utc, reason=reason,
            findings=findings, time_zone=time_zone or "UTC", weekday=weekday, started=started)
    finally:
        _TZ_CTX.reset(_tz_token)
        _NOW_CTX.reset(_now_token)


async def _run_attention_review_inner(db: AsyncSession, *, workspace_id: str, owner: str, today: str,
                                      reason: str, findings: Optional[str], time_zone: str,
                                      weekday: str, started: Any) -> Dict[str, Any]:
    from datetime import datetime as _dt
    today_utc = today
    calls: List[Dict[str, Any]] = []
    inspected = False
    finished_summary: Optional[str] = None
    models = [PRIMARY_MODEL] + ([FALLBACK_MODEL] if FALLBACK_MODEL != PRIMARY_MODEL else [])
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": CONTRACT + f"\n\nToday is {(weekday + ' ') if weekday else ''}{today_utc} (the person's local date; timezone {time_zone}). Give every due_at as the person's local wall-clock time."},
        {"role": "user", "content": f"Review attention ({reason}). Open matters, history and clock are available through tools."
         + (f"\n\nLatest session findings — if these show Sophie asked about a tracked unknown, record a surfaced event for it; if the user answered, declined, or asked to drop it, record a responded event with what they said:\n{findings[:3000]}" if (findings or "").strip() else "")}]
    model_used = models[0]
    for _ in range(MAX_ITERS):
        out = await _chat(model_used, messages)
        if out is None and len(models) > 1 and model_used == models[0]:
            logger.warning("attention primary failed, trying fallback %s", models[1])
            model_used = models[1]
            out = await _chat(model_used, messages)
        if out is None:
            break
        calls.append({"model": out.get("model"), "provider": out.get("provider"),
                      "usage": out.get("usage"), "n_tools": len(out.get("tool_calls") or [])})
        assistant: Dict[str, Any] = {"role": "assistant", "content": out.get("content") or ""}
        if out.get("tool_calls"):
            assistant["tool_calls"] = out["tool_calls"]
        messages.append(assistant)
        if not out.get("tool_calls"):
            messages.append({"role": "user", "content": "No tool calls made. Inspect (list_matters minimum) before finishing."})
            continue
        done = False
        for tc in out["tool_calls"]:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = None
            if not isinstance(args, dict) or out.get("finish_reason") == "length":
                # Malformed or truncated arguments never run as {}: tell the model.
                calls[-1].setdefault("ops", []).append(fn.get("name"))
                messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": str(fn.get("name")),
                                 "content": json.dumps({"error": "arguments were incomplete or not valid JSON; nothing ran. Resend this call."})})
                continue
            calls[-1].setdefault("ops", []).append(fn.get("name"))
            if fn.get("name") in ("list_matters", "attention_history", "list_actions"):
                inspected = True
            if fn.get("name") == "finish":
                finished_summary = str(args.get("summary") or "")[:500]
                done = True
                break
            try:
                res = await _tools(db, workspace_id, owner, str(fn.get("name")), args)
            except Exception as exc:
                res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""),
                             "name": str(fn.get("name")), "content": json.dumps(res)[:3000]})
        if done:
            break
    ms = int((_dt.now(timezone.utc) - started).total_seconds() * 1000)
    if finished_summary is not None and inspected:
        status = "verified"
    elif finished_summary is not None:
        status = "finished_without_inspection"
    else:
        status = "never_inspected" if not inspected else "unfinished"
    logger.info("[attention] %s -> %s (%d calls)", owner, status, len(calls))
    return {"status": status, "summary": finished_summary, "calls": calls,
            "inspected": inspected, "model": model_used, "ms": ms}


async def mark_due(db: AsyncSession, *, workspace_id: str, owner: str,
                   now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """Deterministic due scan: pending actions past due become due (+event).
    Held actions stay held. Never marks delivered."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    stale = (await db.execute(select(AttentionAction).where(
        AttentionAction.honcho_workspace_id == workspace_id, AttentionAction.owner_peer_id == owner,
        AttentionAction.state.in_(["pending", "due"]), AttentionAction.expires_at.is_not(None), AttentionAction.expires_at <= now))).scalars().all()
    for r in stale:                                   # past its stop-surfacing time: it simply stops appearing (history kept)
        r.state, r.updated_at = "expired", utc_now()
        await _event(db, workspace_id, owner, "expired", f"stopped surfacing: {r.intent[:120]}", "due-scan", action_id=r.id, matter_key=r.matter_key)
    rows = (await db.execute(select(AttentionAction).where(
        AttentionAction.honcho_workspace_id == workspace_id,
        AttentionAction.owner_peer_id == owner,
        AttentionAction.state == "pending",
        AttentionAction.due_at.is_not(None),
        AttentionAction.due_at <= now))).scalars().all()
    out = []
    for r in rows:
        r.state = "due"
        r.updated_at = utc_now()
        await _event(db, workspace_id, owner, "scheduled", f"became due: {r.intent[:120]}",
                     "due-scan", action_id=r.id, matter_key=r.matter_key)
        out.append(_action_view(r))
    if out or stale:
        await db.commit()
    return out


async def suppressed_matters(db: AsyncSession, *, workspace_id: str, owner: str) -> Dict[str, str]:
    """Matters currently suppressed: latest suppression-related event is a
    suppression (responded/unsuppressed/surfaced-new-evidence lifts it)."""
    rows = (await db.execute(select(AttentionEvent).where(
        AttentionEvent.honcho_workspace_id == workspace_id,
        AttentionEvent.owner_peer_id == owner,
        AttentionEvent.event.in_(["suppressed", "unsuppressed", "responded"]),
        AttentionEvent.matter_key.is_not(None)).order_by(AttentionEvent.created_at.desc()))).scalars().all()
    out: Dict[str, str] = {}
    for r in rows:
        key = str(r.matter_key)
        if key not in out:
            out[key] = r.event
    return {k: v for k, v in out.items() if v == "suppressed"}

async def pending_attention(db: AsyncSession, *, workspace_id: str, owner: str) -> List[Dict[str, Any]]:
    """What deserves foreground awareness now: due + pending with dates near,
    excluding held/cancelled/delivered and currently suppressed matters."""
    suppressed = await suppressed_matters(db, workspace_id=workspace_id, owner=owner)
    rows = (await db.execute(select(AttentionAction).where(
        AttentionAction.honcho_workspace_id == workspace_id,
        AttentionAction.owner_peer_id == owner,
        AttentionAction.state.in_(["pending", "due"])).order_by(
        AttentionAction.due_at.is_(None), AttentionAction.due_at))).scalars().all()
    boundary: set = set()
    ent_refs = [r.source_ref for r in rows if r.source == "entity" and r.source_ref]
    if ent_refs:
        from src.models.known_world import KnownEntity
        from uuid import UUID as _U
        ids = []
        for x in ent_refs:
            try:
                ids.append(_U(x))
            except Exception:
                pass
        for e in (await db.execute(select(KnownEntity).where(KnownEntity.id.in_(ids), KnownEntity.suppressed == True))).scalars().all():   # noqa: E712
            boundary.add(str(e.id))          # the person's boundary always wins, even over an already-scheduled intention
    return [_action_view(r) for r in rows if str(r.matter_key or "") not in suppressed and str(r.source_ref or "") not in boundary]


def _int(env: str, default: int) -> int:
    try:
        return int(os.getenv(env, str(default)))
    except ValueError:
        return default


def tick_config() -> Dict[str, Any]:
    return {
        "enabled": os.getenv("ATTENTION_SCHEDULER", "false").strip().lower() in ("1", "true", "yes", "on"),
        "workspace_id": os.getenv("ATTENTION_WORKSPACE", "llm-test-agent"),
        "owners": [o.strip() for o in os.getenv("ATTENTION_OWNERS", "").split(",") if o.strip()],
        "tick_seconds": _int("ATTENTION_TICK_SECONDS", 900),
        "review_stale_hours": _int("ATTENTION_REVIEW_STALE_HOURS", 12),
    }


async def last_review_at(db: AsyncSession, *, workspace_id: str, owner: str) -> Optional[datetime]:
    row = (await db.execute(select(AttentionEvent.created_at).where(
        AttentionEvent.honcho_workspace_id == workspace_id,
        AttentionEvent.owner_peer_id == owner,
        AttentionEvent.actor.like("attention%")).order_by(
        AttentionEvent.created_at.desc()).limit(1))).scalar()
    return row


async def owner_time_zone(db: AsyncSession, *, workspace_id: str, owner: str, default: Optional[str] = "Europe/London") -> Optional[str]:
    """The person's timezone as last reported with a consolidation (the Runtime
    supplies it); `default` only if none was ever supplied."""
    import json as _json
    from src.models.world import MemoryRun
    rows = (await db.execute(select(MemoryRun).where(
        MemoryRun.honcho_workspace_id == workspace_id, MemoryRun.owner_peer_id == owner,
        MemoryRun.status == "consolidated").order_by(MemoryRun.created_at.desc()).limit(5))).scalars().all()
    for r in rows:
        try:
            tz = (_json.loads(r.bundle_json or "{}").get("clock") or {}).get("time_zone")
        except Exception:
            tz = None
        if tz and tz != "UTC":
            return str(tz)
    return default


async def tick_once(*, workspace_id: str, owner: str, now: Optional[datetime] = None) -> Dict[str, Any]:
    """One scheduled pass: deterministic due-scan always; agent review only
    when the last review is stale and there is anything to review. No quiet-hour
    or cadence logic here — those gate delivery, never this tick."""
    from src.db import async_session_maker
    from datetime import timedelta as _td
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    out: Dict[str, Any] = {"owner": owner, "at": now.isoformat()}
    async with async_session_maker() as db:
        try:
            out["became_due"] = [a["id"] for a in await mark_due(
                db, workspace_id=workspace_id, owner=owner, now=now)]
            last = await last_review_at(db, workspace_id=workspace_id, owner=owner)
            stale = last is None or (now - last).total_seconds() > tick_config()["review_stale_hours"] * 3600
            from src.services.memory_pipeline import open_ledger
            has_matters = bool(await open_ledger(db, workspace_id, owner, limit=1))
            has_actions = bool(await pending_attention(db, workspace_id=workspace_id, owner=owner))
            if stale and (has_matters or has_actions):
                tz_name = await owner_time_zone(db, workspace_id=workspace_id, owner=owner)
                try:
                    from zoneinfo import ZoneInfo
                    local_now = now.replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name))
                except Exception:
                    tz_name, local_now = "UTC", now.replace(tzinfo=timezone.utc)
                out["review"] = await run_attention_review(
                    db, workspace_id=workspace_id, owner=owner,
                    today_utc=local_now.date().isoformat(), weekday=local_now.strftime("%A"),
                    time_zone=tz_name, reason="scheduled-tick", now_utc=now.replace(tzinfo=timezone.utc))
                out["review"].pop("calls", None)
            else:
                out["review"] = {"status": "skipped",
                                 "reason": "fresh" if not stale else "nothing to review"}
            await db.commit()
        except Exception as exc:
            logger.exception("attention tick failed for %s", owner)
            try:
                await db.rollback()
            except Exception:
                pass
            out["error"] = type(exc).__name__
    return out


async def tick_all() -> List[Dict[str, Any]]:
    cfg = tick_config()
    if not cfg["enabled"]:
        return []
    return [await tick_once(workspace_id=cfg["workspace_id"], owner=o) for o in cfg["owners"]]


async def run_forever() -> None:
    import asyncio
    while True:
        try:
            await tick_all()
        except Exception:
            logger.exception("attention tick loop failed (next tick retries)")
        await asyncio.sleep(max(60, tick_config()["tick_seconds"]))
