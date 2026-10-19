"""LAB ONLY — coding-agent reconciliation experiment. Not production code.

Gives a model scoped operational tools over ONE owner's ledger plus the
maintenance contract, then lets it work: inspect, query, update, verify.
Every tool call + result is traced to /tmp/agent_trace.jsonl.
"""
import asyncio
import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.insert(0, "/app")
from src.db import async_session_maker
from src.models.world import LedgerItem, utc_now

OWNER = os.environ["AGENT_OWNER"]
NANO_KEY = os.environ["NANO_KEY"]
MODEL = os.getenv("AGENT_MODEL", "qwen/qwen3.8-27b")
TRACE = open("/tmp/agent_trace.jsonl", "w")

CONTRACT = """You maintain one person's operational agenda in a database you can inspect and change through tools. Goal and invariants:

Maintain an accurate operational agenda from the new evidence. Inspect existing records before making changes. Reuse records when they refer to the same matter. Preserve relevant changes and source evidence. Do not invent commitments, dates or completions. Never treat silence as resolution.

Rules: closing anything (done/cancelled/answered) requires quoting the evidence that proves it. A changed date updates the record, never duplicates it. Set expected_date (YYYY-MM-DD) whenever evidence states or implies a concrete date — a timing change with no date update is an incomplete job. Subtasks of a tracked matter fold into its detail; before create_item, search and confirm no open row covers it. Aspirations stay open. If a tool call fails, read the error and adapt.

VERIFY (consequential, not ceremonial): before finish, re-list all records and check field-by-field: every intended status change present? every intended date set in its expected_date FIELD (prose alone does not count — if evidence moved a deadline, the date field must show it)? any two open rows covering the same matter (near-duplicate titles)? If anything is off, correct it first — a failed check blocks finish. Today is known from evidence dates; when in doubt about the calendar, set timing_text prose and leave expected_date empty rather than guessing."""

TOOLS = [
    {"type": "function", "function": {"name": "list_open", "description": "List all open situations with keys, titles, status, detail, timing", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search", "description": "Substring search over titles+details. Use when unsure which record matches.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "history", "description": "Show a record's evidence history and past states.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "update_item", "description": "Change fields of one record by key. detail/timing_text/waiting_on/question_text merge; expected_date sets the concrete date (YYYY-MM-DD only, rejected otherwise — use when evidence moves a deadline); status must be open/waiting/watching/suppressed/done/cancelled/answered; done/cancelled/answered REQUIRE evidence quoting proof.", "parameters": {"type": "object", "properties": {"key": {"type": "string"}, "detail": {"type": "string"}, "timing_text": {"type": "string"}, "expected_date": {"type": "string"}, "waiting_on": {"type": "string"}, "question_text": {"type": "string"}, "status": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["key"]}}},
    {"type": "function", "function": {"name": "create_item", "description": "Create a genuinely new record (title, kind, detail, timing). Never duplicate an existing matter.", "parameters": {"type": "object", "properties": {"title": {"type": "string"}, "kind": {"type": "string"}, "detail": {"type": "string"}, "timing": {"type": "string"}}, "required": ["title"]}}},
    {"type": "function", "function": {"name": "finish", "description": "End the job. Only call after verifying the agenda against the evidence.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}}, "required": ["summary"]}}},
]


def row_view(r):
    return {"key": r.situation_key, "kind": r.kind, "status": r.status, "title": r.title,
            "detail": (r.detail or "")[:400], "timing": r.timing_text, "waiting_on": r.waiting_on,
            "confidence": r.confidence}


async def run_tools(db, name, args):
    if name == "list_open":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.owner_peer_id == OWNER,
            LedgerItem.status.in_(["open", "waiting", "watching", "suppressed"])))).scalars().all()
        return {"records": [row_view(r) for r in rows]}
    if name == "search":
        q = str(args.get("query") or "").lower()
        rows = (await db.execute(select(LedgerItem).where(LedgerItem.owner_peer_id == OWNER))).scalars().all()
        return {"matches": [row_view(r) for r in rows
                            if q in (str(r.title or "") + " " + str(r.detail or "")).lower()]}
    if name == "history":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.owner_peer_id == OWNER, LedgerItem.situation_key == args.get("key")))).scalars().all()
        if not rows:
            return {"error": "no such key"}
        r = rows[0]
        return {"record": row_view(r), "sources": r.source_refs_json[:1500]}
    if name == "update_item":
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.owner_peer_id == OWNER, LedgerItem.situation_key == args.get("key")))).scalars().all()
        if not rows:
            return {"error": "no such key — inspect first, never invent keys"}
        r = rows[0]
        st = str(args.get("status") or "").strip()
        if st and st not in ("open", "waiting", "watching", "suppressed", "done", "cancelled", "answered"):
            return {"error": f"illegal status {st}"}
        if st in ("done", "cancelled", "answered") and not str(args.get("evidence") or "").strip():
            return {"error": "closing requires evidence quoting proof"}
        for f, a in (("detail", "detail"), ("timing_text", "timing"), ("waiting_on", "waiting_on"),
                       ("question_text", "question")):
            v = args.get(f) or args.get(a)
            if isinstance(v, str) and v.strip():
                setattr(r, f, v.strip()[:2000] if f == "detail" else v.strip()[:500])
        if st:
            r.status = st
        import re as _re2
        ed = str(args.get("expected_date") or "").strip()
        if ed:
            if not _re2.match(r"^\d{4}-\d{2}-\d{2}$", ed):
                return {"error": "expected_date must be YYYY-MM-DD — relative dates go in timing_text"}
            from datetime import datetime as _dtd
            try:
                r.expected_date = _dtd.strptime(ed[:10], "%Y-%m-%d")
            except ValueError:
                return {"error": "expected_date is not a real calendar date"}
        ev = str(args.get("evidence") or "").strip()
        if ev:
            try:
                refs = json.loads(r.source_refs_json or "{}")
            except Exception:
                refs = {}
            if not isinstance(refs, dict):
                refs = {"prior": refs}
            prior = refs.get("agent_evidence") or refs.get("evidence") or []
            refs["agent_evidence"] = ([prior] if isinstance(prior, str) else (prior or [])) + [ev[:500]]
            r.source_refs_json = json.dumps(refs)[:4000]
        r.updated_at = utc_now()
        await db.commit()
        return {"ok": True, "record": row_view(r)}
    if name == "create_item":
        title = str(args.get("title") or "").strip()
        if not title:
            return {"error": "title required"}
        import re as _re
        key = _re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]
        rows = (await db.execute(select(LedgerItem).where(
            LedgerItem.owner_peer_id == OWNER, LedgerItem.situation_key == key))).scalars().all()
        if rows:
            return {"error": f"key {key} exists — update it instead of duplicating"}
        db.add(LedgerItem(honcho_workspace_id="llm-test-agent", owner_peer_id=OWNER,
                          kind=str(args.get("kind") or "situation")[:40], title=title[:500],
                          detail=str(args.get("detail") or "")[:2000], status="open",
                          situation_key=key, timing_text=str(args.get("timing") or "")[:300]))
        await db.commit()
        return {"ok": True, "key": key}
    return {"error": "unknown tool"}


def chat(messages):
    body = {"model": MODEL, "messages": messages, "tools": TOOLS, "tool_choice": "auto", "max_tokens": 1200}
    req = urllib.request.Request("https://nano-gpt.com/api/v1/chat/completions", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "Authorization": "Bearer " + NANO_KEY})
    out = json.loads(urllib.request.urlopen(req, timeout=120).read().decode())
    msg = out["choices"][0]["message"]
    return msg, out.get("usage") or {}


async def main():
    evidence = open("/tmp/agent_evidence.txt").read()
    today = datetime.now(timezone.utc).date().isoformat()
    messages = [{"role": "system", "content": CONTRACT + f"\n\nToday is {today} (UTC). Use it to resolve weekday references into expected_date values."},
                {"role": "user", "content": "New session evidence. Maintain the agenda.\n\n" + evidence}]
    total_in = total_out = 0
    async with async_session_maker() as db:
        for i in range(12):
            msg, usage = chat(messages)
            total_in += int(usage.get("prompt_tokens") or 0)
            total_out += int(usage.get("completion_tokens") or 0)
            TRACE.write(json.dumps({"iter": i, "content": (msg.get("content") or "")[:1000],
                                    "tool_calls": msg.get("tool_calls")}) + "\n")
            TRACE.flush()
            messages.append({"role": "assistant", "content": msg.get("content") or "",
                             **({"tool_calls": msg["tool_calls"]} if msg.get("tool_calls") else {})})
            if not msg.get("tool_calls"):
                messages.append({"role": "user", "content": "You made no tool calls. Inspect the records before finishing — use list_open at minimum, then finish."})
                continue
            finished = False
            for tc in msg["tool_calls"]:
                fn = tc["function"]
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except Exception:
                    args = {}
                if fn["name"] == "finish":
                    print("FINISH:", args.get("summary", "")[:300], flush=True)
                    finished = True
                    break
                try:
                    res = await run_tools(db, fn["name"], args)
                except Exception as e:
                    res = {"error": f"{type(e).__name__}: {str(e)[:200]}"}
                TRACE.write(json.dumps({"iter": i, "tool": fn["name"], "result": str(res)[:1500]}) + "\n")
                TRACE.flush()
                messages.append({"role": "tool", "tool_call_id": tc["id"], "name": fn["name"],
                                 "content": json.dumps(res)[:3000]})
            if finished:
                break
    print(f"TOKENS in={total_in} out={total_out}", flush=True)


asyncio.run(main())
