"""Agentic operational maintenance (bakeoff winner: qwen3.7-flash).

Replaces the single-shot match judge: the agent receives witness observations,
existing ledger access, the session clock and a maintenance contract, then
investigates (list/search/history), acts (update/create with validation) and
verifies (re-list + field checks). Deterministic code owns keys, dates,
evidence gates, tenant scope and audit — the agent owns judgment.

Primary: qwen3.7-flash via OpenRouter. Fallback: qwen3.8-27b via NanoGPT
(availability fallback only — same validation either way).
Completion is grounded in observed state: finish requires inspection, and a run
that never inspected anything is reported never_inspected, never success.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.world import LedgerItem, utc_now

logger = logging.getLogger(__name__)

PRIMARY_MODEL = os.getenv("MAINTENANCE_MODEL", "qwen/qwen3.7-flash")
FALLBACK_MODEL = os.getenv("MAINTENANCE_FALLBACK_MODEL", "qwen/qwen3.8-27b")
MAX_ITERS = int(os.getenv("MAINTENANCE_MAX_ITERS", "10"))
CALL_TIMEOUT_S = float(os.getenv("MAINTENANCE_TIMEOUT_S", "90"))

CONTRACT = """You maintain one person's operational agenda. Goal and invariants:

Maintain an accurate operational agenda from the new observations. Inspect existing records before making changes. Reuse records when they refer to the same matter. Preserve relevant changes and source evidence. Do not invent commitments, dates or completions. Never treat silence as resolution.

Rules: closing anything (done/cancelled/answered) requires quoting the evidence that proves it — the quote must come from this session's transcript; invented proof is rejected. Close only when the event happened, the item was delivered, or the matter is explicitly over: planning detail (a time or date getting fixed, "locked in") is an UPDATE, never a close. When evidence moves a deadline, set expected_date (YYYY-MM-DD) as well as prose — prose alone does not count. When closing, keep the record's existing expected_date unless the closing session states a different explicit date — the day you process it is not the due date. Self-reminders and to-dos are open (actionable by the person), never watching — watching is for external developments you monitor. Subtasks of a tracked matter fold into its detail; search before creating. Aspirations stay open. If a tool call fails, read the error and adapt.

VERIFY before finish: re-list all records and check field-by-field — every intended status change present, every intended date in its expected_date field, no two open rows on the same matter. A failed check blocks finish."""

TOOLS = [
    {"type": "function", "function": {"name": "list_open", "description": "List open situations: keys, titles, status, detail, timing, expected dates.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search", "description": "Substring search over titles and details.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "history", "description": "Evidence history of one record by key.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "update_item", "description": "Change one record by key. expected_date must be YYYY-MM-DD. done/cancelled REQUIRE evidence quoting proof. Valid statuses: open, waiting, watching, suppressed, done, cancelled.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "detail": {"type": "string"}, "timing_text": {"type": "string"}, "expected_date": {"type": "string"}, "waiting_on": {"type": "string"}, "question_text": {"type": "string"}, "status": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "create_item", "description": "Create a genuinely new record. Search first; never duplicate tracked matters. Attach the proving quote as evidence on every write, not just closes.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "kind": {"type": "string"}, "detail": {"type": "string"}, "timing": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "finish", "description": "End only after verifying. Summarize what changed.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]

# Injectable for tests.
_chat_fn: Optional[Callable[..., Any]] = None

import contextvars as _cv
_TRANSCRIPT_CTX: _cv.ContextVar[str] = _cv.ContextVar("maintenance_transcript", default="")


def set_chat_fn(fn: Optional[Callable[..., Any]]) -> None:
    global _chat_fn
    _chat_fn = fn


def _openrouter_key() -> str:
    return os.getenv("OPENROUTER_API_KEY", "").strip()


def _nano_key() -> str:
    return os.getenv("NANO_API_KEY", "").strip()


async def _chat(model: str, messages: List[Dict[str, str]]) -> Optional[Dict[str, Any]]:
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
                                "tool_choice": "auto", "max_tokens": 1200}
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as client:
            resp = await client.post(base + "/chat/completions", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            msg = data["choices"][0]["message"]
            used = data.get("usage") or {}
            logger.info("llm_usage module=maintenance provider=%s model=%s in=%s out=%s reasoning=%s ms=%d",
                        "openrouter" if via_or else "nanogpt", mid, used.get("prompt_tokens"),
                        used.get("completion_tokens"), used.get("reasoning_tokens", 0),
                        int((time.monotonic() - t0) * 1000))
            return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [],
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
            "waiting_on": r.waiting_on, "confidence": r.confidence}


async def _tools(db: AsyncSession, workspace_id: str, owner: str, name: str, args: Dict[str, Any],
               session_id: str = "") -> Dict[str, Any]:
    from sqlmodel import select
    if name == "list_open":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.status.in_(["open", "waiting", "watching", "suppressed"])).order_by(LedgerItem.created_at))).scalars().all()
        return {"records": [_row_view(r) for r in rows]}
    if name == "search":
        q = str(args.get("query") or "").lower()
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner))).scalars().all()
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
        if st and st not in ("open", "waiting", "watching", "suppressed", "done", "cancelled", "answered"):
            return {"error": f"illegal status {st}"}
        if st in ("done", "cancelled", "answered") and not str(args.get("evidence") or "").strip():
            return {"error": "closing requires evidence quoting proof"}
        if st in ("done", "cancelled", "answered") and _TRANSCRIPT_CTX.get():
            ev_check = str(args.get("evidence") or "")
            if not _evidence_in_transcript(ev_check, _TRANSCRIPT_CTX.get() or ""):
                return {"error": "evidence quote not found in this session's transcript — quote what was actually said"}
        for f, lim in (("detail", 2000), ("timing_text", 300), ("waiting_on", 300), ("question_text", 500)):
            v = args.get(f)
            if isinstance(v, str) and v.strip():
                setattr(r, f, v.strip()[:lim])
        ed = str(args.get("expected_date") or "").strip()
        if ed:
            import re as _re
            from datetime import datetime as _dt
            if not _re.match(r"^\d{4}-\d{2}-\d{2}$", ed):
                return {"error": "expected_date must be YYYY-MM-DD"}
            try:
                r.expected_date = _dt.strptime(ed[:10], "%Y-%m-%d")
            except ValueError:
                return {"error": "expected_date is not a real calendar date"}
        if st:
            r.status = st
        ev = str(args.get("evidence") or "").strip()
        if ev:
            try:
                refs = json.loads(r.source_refs_json or "{}")
            except Exception:
                refs = {}
            if not isinstance(refs, dict):
                refs = {"prior": refs}
            prior = refs.get("agent_evidence") or refs.get("evidence") or []
            verified, reported = _evidence_spans(ev, _TRANSCRIPT_CTX.get() or "")
            refs["agent_evidence"] = ([prior] if isinstance(prior, str) else (prior or [])) + verified
            if reported:
                prior_rep = refs.get("reported") or []
                refs["reported"] = ([prior_rep] if isinstance(prior_rep, str) else (prior_rep or [])) + [reported]
            r.source_refs_json = json.dumps(refs)[:4000]
        r.updated_at = utc_now()
        await db.commit()
        return {"ok": True, "record": _row_view(r)}
    if name == "create_item":
        import re as _re
        title = str(args.get("title") or "").strip()
        if not title or title.lower() in ("none", "n/a", "no change", "no changes", "nothing", "nothing new"):
            return {"error": "title required — NONE/nothing is not a trackable matter"}
        key = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.honcho_workspace_id == workspace_id, LedgerItem.owner_peer_id == owner,
            LedgerItem.situation_key == key))).scalars().all()
        if rows:
            return {"error": f"key {key} exists — update it instead of duplicating"}
        timing = str(args.get("timing") or "").strip()
        ev = str(args.get("evidence") or "").strip()
        refs = {"session": session_id, "evidence": [ev[:500]] if ev else []}
        db.add(LedgerItem(honcho_workspace_id=workspace_id, owner_peer_id=owner,
                          kind=str(args.get("kind") or "situation")[:40], title=title[:500],
                          detail=str(args.get("detail") or "")[:2000], status="open",
                          situation_key=key, timing_text=timing,
                          source_refs_json=json.dumps(refs)[:4000]))
        await db.commit()
        return {"ok": True, "key": key}
    return {"error": "unknown tool"}


def _norm_text(s: str) -> str:
    import re as _re
    return _re.sub(r"\s+", " ", str(s or "").lower()).strip()


def _evidence_spans(evidence: str, transcript: str) -> tuple[list, str]:
    """Split evidence into transcript-verified quotes vs reported paraphrase.
    Only verified spans are stored as quotations; the rest is kept separately
    as reported (never presented as quoted proof)."""
    import re as _re
    norm_t = _norm_text(transcript)
    verified: list = []
    reported: list = []
    if not norm_t:
        return verified, evidence.strip()
    for raw in _re.split(r"\n", evidence):
        line = raw.strip()
        if not line:
            continue
        spans = [s.strip() for s in _re.split(r"[\"“”']", line) if s.strip()]
        cands = [c for c in spans if len(_norm_text(c)) >= 20]
        if not cands:
            cands = [s.strip() for s in _re.split(r"[.!?]+", line) if len(_norm_text(s)) >= 20][:1]
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


async def run_maintenance(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str,
                          observations: str, today_utc: str,
                          transcript: str = "") -> Dict[str, Any]:
    """Agentic maintenance loop over witness observations. Returns outcome with
    inspection grounding: verified / no_change_verified / never_inspected."""
    from datetime import datetime as _dt
    started = _dt.now(timezone.utc)
    token = _TRANSCRIPT_CTX.set(transcript or "")
    try:
        return await _run_maintenance_inner(
            db, workspace_id=workspace_id, owner=owner, session_id=session_id,
            observations=observations, today_utc=today_utc, started=started)
    finally:
        _TRANSCRIPT_CTX.reset(token)


async def _run_maintenance_inner(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str,
                                 observations: str, today_utc: str, started: Any) -> Dict[str, Any]:
    from datetime import datetime as _dt
    calls: List[Dict[str, Any]] = []
    inspected = False
    finished_summary: Optional[str] = None
    changes = {"created": 0, "updated": 0, "closed": 0}
    models_tried = [PRIMARY_MODEL]
    if FALLBACK_MODEL and FALLBACK_MODEL != PRIMARY_MODEL:
        models_tried.append(FALLBACK_MODEL)
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": CONTRACT + f"\n\nToday is {today_utc} (UTC)."},
        {"role": "user", "content": "New session observations. Maintain the agenda.\n\n" + observations[:6000]}]
    model_used = models_tried[0]
    for _ in range(MAX_ITERS):
        out = await _chat(model_used, messages)
        if out is None and len(models_tried) > 1 and model_used == models_tried[0]:
            logger.warning("maintenance primary failed, trying fallback %s", models_tried[1])
            model_used = models_tried[1]
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
            messages.append({"role": "user", "content": "You made no tool calls. Inspect the records (list_open minimum) before finishing — unverified claims of completion will be recorded as never_inspected."})
            continue
        done = False
        for tc in out["tool_calls"]:
            fn = tc.get("function") or {}
            try:
                args = json.loads(fn.get("arguments") or "{}")
            except Exception:
                args = {}
            if not isinstance(args, dict):
                args = {}
            calls[-1].setdefault("ops", []).append(fn.get("name"))
            if fn.get("name") in ("list_open", "search", "history"):
                inspected = True
            if fn.get("name") == "finish":
                finished_summary = str(args.get("summary") or "")[:500]
                done = True
                break
            try:
                res = await _tools(db, workspace_id, owner, str(fn.get("name")), args,
                                   session_id=session_id)
            except Exception as exc:
                res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            if isinstance(res, dict) and res.get("ok") is True:
                if fn.get("name") == "create_item":
                    changes["created"] += 1
                elif fn.get("name") == "update_item":
                    if str(args.get("status") or "") in ("done", "cancelled", "answered"):
                        changes["closed"] += 1
                    else:
                        changes["updated"] += 1
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
    logger.info("[maintenance] %s %s -> %s (%d calls)", owner, session_id, status, len(calls))
    return {"status": status, "summary": finished_summary, "calls": calls,
            "inspected": inspected, "model": model_used, "ms": ms, "changes": changes}
