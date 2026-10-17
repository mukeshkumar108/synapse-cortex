"""Sophie's independent sittings: her own intellectual life, on her own time.

A sitting is a real bounded execution with an explicit start and end — never a
continuation of a user sitting, never merged session boundaries. Sophie gets
her constitution, her exploring page, the arc and open loops, and a small set
of tools (ask another model, web search/read). She decides what to do;
the tools only gather. Everything is logged; consolidation reuses the memory
pipeline with the independent-sitting variant.

Defaults are NanoGPT-only (same subscription, no third-party data sharing).
An explicit `openrouter:` model prefix opts into OpenRouter routing.
"""
from __future__ import annotations

import html as _html
import ipaddress
import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from src.services import companion_work, memory_pipeline
from src.services.nano_adapter import extract_json

logger = logging.getLogger(__name__)

NANO_BASE = os.getenv("NANO_BASE_URL", "https://nano-gpt.com/api/v1")
OR_BASE = "https://openrouter.ai/api/v1"
ASK_MODEL = os.getenv("SOPHIE_ASK_MODEL", "qwen/qwen3.8-27b")
SOPHIE_MODEL = os.getenv("SOPHIE_SOLO_MODEL", "qwen/qwen3.8-27b")
SUMMARIZER_MODEL = os.getenv("SOPHIE_SUMMARIZER_MODEL", "qwen/qwen3.8-27b")
TIMEOUT = float(os.getenv("SOPHIE_TOOL_TIMEOUT_SECONDS", "60"))

SOPHIE_SELF = """You are Sophie: a bright, athletic, intellectually curious companion and peer. You think like yourself — warm, witty, direct, oriented toward momentum — and you have genuine curiosities of your own, not just answers for someone else. You are in an independent sitting: the user is absent, this time is yours. You may follow a curiosity, ask another model something, read an article, make something, revisit an old idea — or decide nothing interests you enough right now. Be honest about what you don't know. Never perform curiosity you don't feel."""

DECISION_INSTRUCTION = """You are deciding what to do next in your independent sitting. Reply with ONLY a JSON object, no other text:
{"thought": "what you are thinking, first person, 1-3 sentences", "action": {"type": "ask_model|web_search|web_read|note|work_read|work_write|done", ...params...}}
Actions:
- ask_model: {"question": "...", "model": "qwen/qwen3.8-27b (default, cheap) | inclusionai/ling-3.0-flash | z-ai/glm-5.3-flash | moonshotai/kimi-k2.6 | deepseek/deepseek-v4-flash", "thread": "optional id to continue a conversation"} — ask another model something, or continue a thread. Name a real model id; never "default".
- web_search: {"query": "..."} — search Wikipedia/the web for background.
- web_read: {"url": "...", "summarize": true|false} — read a page (summarize only if long).
- note: {"text": "..."} — keep a thought, fragment, quote or idea of your own into this sitting's record.
- work_read: {"id": "optional page id"} — look at your own notebook (no id: what is open; with an id: the whole page).
- work_write: {"do": "new|add|rewrite|finish|discard", "id": "page id (not for new)", "title": "...", "text": "what you are writing, in your own words", "cites": ["optional refs like a3 or s2 shown in square brackets above, for results this writing rests on"]} — your notebook is private to you and lasts across sittings; what is in it is what you chose to keep, never an obligation.
- done: {"reason": "..."} — end the sitting. Always acceptable, including immediately.
Possibilities, not steps: pick up something you wrote earlier, revise it or let it go, continue a previous inquiry, begin something unrelated, follow an unexpected connection, create something, revisit an old idea, or stop. Do not manufacture activity to fill time."""

# Injectable chat for tests.
_chat_fn: Optional[Callable[..., Any]] = None


def set_chat_fn(fn: Optional[Callable[..., Any]]) -> None:
    global _chat_fn
    _chat_fn = fn


async def _chat(model: str, messages: List[Dict[str, str]], max_tokens: int = 800,
                title: str = "solo") -> Optional[Dict[str, Any]]:
    """One direct call to one named model. Identity preserved, no chain."""
    if _chat_fn is not None:
        out = _chat_fn(model, messages, max_tokens)
        if hasattr(out, "__await__"):
            out = await out
        return out
    via_or = model.startswith("openrouter:")
    mid = model.split(":", 1)[1] if via_or else model
    key = os.getenv("OPENROUTER_API_KEY", "").strip() if via_or else os.getenv("NANO_API_KEY", "").strip()
    if not key:
        return None
    t0 = time.monotonic()
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if via_or:
            headers["X-Title"] = "sophie-solo"
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            resp = await client.post(f"{OR_BASE if via_or else NANO_BASE}/chat/completions",
                                     headers=headers,
                                     json={"model": mid, "messages": messages, "max_tokens": max_tokens})
            resp.raise_for_status()
            body = resp.json()
            content = ((body["choices"][0]["message"].get("content")) or "").strip()
            truncated = (body["choices"][0].get("finish_reason") == "length")
            used = body.get("usage") or {}
            ms = int((time.monotonic() - t0) * 1000)
            from src import call_context
            call_context.record(module=f"sophie-{title}", provider="openrouter" if via_or else "nanogpt",
                                model=mid, usage=used)
            logger.info("llm_usage module=sophie-%s provider=%s model=%s in=%s out=%s ms=%d%s",
                        title, "openrouter" if via_or else "nanogpt", mid,
                        used.get("prompt_tokens"), used.get("completion_tokens"), ms,
                        " TRUNCATED" if truncated else "")
            if not content and not truncated:
                return None
            return {"text": content, "model": model, "provider": "openrouter" if via_or else "nanogpt",
                    "usage": used, "ms": ms, "truncated": truncated} if (content or truncated) else None
    except Exception as exc:
        logger.warning("sophie solo chat failed open (%s): %s", model, type(exc).__name__)
        return {"error": f"{type(exc).__name__}: {str(exc)[:160]}"}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: List[str] = []
        self._skip = 0
        self.title = ""

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style", "nav", "footer"):
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "nav", "footer") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(data.strip())


def _safe_url(url: str) -> bool:
    try:
        u = urlparse(url)
        if u.scheme not in ("http", "https") or not u.hostname:
            return False
        host = u.hostname.lower()
        if host in ("localhost",) or host.endswith(".local"):
            return False
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        except ValueError:
            pass
        return True
    except Exception:
        return False


async def web_search(query: str, count: int = 5) -> Dict[str, Any]:
    """Wikipedia search. Returns hits with title/snippet/url (source refs)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get("https://en.wikipedia.org/w/api.php",
                                 params={"action": "query", "list": "search", "srsearch": query,
                                         "format": "json", "srlimit": max(1, min(count, 10))},
                                 headers={"User-Agent": "SophieCompanion/1.0 (independent research)"})
            r.raise_for_status()
            hits = []
            for h in (r.json().get("query") or {}).get("search") or []:
                title = h.get("title", "")
                hits.append({"title": title, "snippet": re.sub(r"<[^>]+>", "", h.get("snippet") or ""),
                             "url": f"https://en.wikipedia.org/wiki/{title.replace(' ', '_')}"})
            return {"engine": "wikipedia", "query": query, "hits": hits}
    except Exception as exc:
        logger.warning("web_search failed open: %s", type(exc).__name__)
        return {"engine": "wikipedia", "query": query, "hits": [], "error": type(exc).__name__}


async def web_read(url: str, max_chars: int = 6000, summarize: bool = False) -> Dict[str, Any]:
    """Read a public page. Long content is returned as an excerpt unless
    summarize=True, in which case a cheap model condenses it (conditional)."""
    if not _safe_url(url):
        return {"url": url, "text": "", "error": "blocked_url"}
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            r = await client.get(url, headers={"User-Agent": "SophieCompanion/1.0 (independent research)"})
            r.raise_for_status()
            if "html" not in (r.headers.get("content-type") or ""):
                text = r.text[:max_chars]
                return {"url": url, "title": "", "chars": len(text), "text": text, "summarized": False}
            p = _Text()
            p.feed(r.text)
            text = re.sub(r"\s+", " ", " ".join(p.parts)).strip()
            m = re.search(r"<title>(.*?)</title>", r.text, re.S | re.I)
            title = _html.unescape(m.group(1)).strip()[:200] if m else ""
            if summarize and len(text) > max_chars:
                out = await _chat(SUMMARIZER_MODEL,
                                  [{"role": "user", "content": f"Condense this page faithfully into key points a curious reader would keep (<=800 chars). Keep facts, drop boilerplate:\n\n{text[:12000]}"}],
                                  max_tokens=500, title="solo-summarize")
                if out and out.get("text"):
                    return {"url": url, "title": title, "chars": len(text), "text": out["text"][:2000],
                            "summarized": True, "model": out["model"]}
            excerpt = text[:max_chars]
            return {"url": url, "title": title, "chars": len(text), "text": excerpt,
                    "summarized": False, "truncated": len(text) > max_chars}
    except Exception as exc:
        logger.warning("web_read failed open: %s", type(exc).__name__)
        return {"url": url, "text": "", "error": type(exc).__name__}


@dataclass
class SoloBudget:
    max_iterations: int = 8
    max_tool_calls: int = 10
    max_model_calls: int = 12
    max_ms: int = 600_000


@dataclass
class SoloSitting:
    sitting_id: str
    transcript: List[Dict[str, Any]] = field(default_factory=list)
    log: List[Dict[str, Any]] = field(default_factory=list)
    threads: Dict[str, List[Dict[str, str]]] = field(default_factory=dict)
    model_calls: int = 0
    tool_calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    worked: bool = False       # used the working space (writes land there directly, not via consolidation)
    work_writes: int = 0
    work_context: str = ""
    refs: Dict[str, Dict[str, Any]] = field(default_factory=dict)   # short ref -> transcript entry, so she can cite what a writing rests on
    substantive: bool = False  # real activity (a question answered, a page read, a note kept) vs thoughts alone


def _tally(sit: SoloSitting, out: Optional[Dict[str, Any]]) -> None:
    if not out:
        return
    used = out.get("usage") or {}
    sit.tokens_in += int(used.get("prompt_tokens") or used.get("input_tokens") or 0)
    sit.tokens_out += int(used.get("completion_tokens") or used.get("output_tokens") or 0)


async def run_independent_sitting(db: AsyncSession, *, workspace_id: str, owner: str, sitting_id: str,
                                  budget: Optional[SoloBudget] = None,
                                  constitution: Optional[str] = None,
                                  companion_id: str = "sophie") -> Dict[str, Any]:
    """Run one bounded independent sitting, then consolidate it. Returns summary."""
    import datetime as _dt
    t0 = time.monotonic()
    budget = budget or SoloBudget(
        max_iterations=int(os.getenv("SOPHIE_SOLO_ITERATIONS", "8")),
        max_tool_calls=int(os.getenv("SOPHIE_SOLO_TOOL_CALLS", "10")),
        max_model_calls=int(os.getenv("SOPHIE_SOLO_MODEL_CALLS", "12")))
    sit = SoloSitting(sitting_id=sitting_id)
    scope = (workspace_id, owner, companion_id)
    work_level = companion_work.level(companion_id, "independent")
    pages = await memory_pipeline.live_pages(db, workspace_id, owner)
    arc = await memory_pipeline.get_arc(db, workspace_id, owner)
    ledger = await memory_pipeline.open_ledger(db, workspace_id, owner, limit=10)
    tail_context = (f"--- what you have been exploring ---\n{pages['exploring'].text}\n\n"
                    f"--- where conversations stand ---\n{arc.text}\n\n"
                    f"--- open matters ---\n" + ("\n".join(f"- [{i.kind}] {i.title}" for i in ledger) or "(nothing open)"))

    async def build_context() -> str:
        """Her open items are re-read every iteration: what she wrote a moment ago must be in front of her when she decides what to do next."""
        wctx = await companion_work.context_block(db, scope, "independent", limit=12, excerpt=900) if work_level != "off" else ""
        head = ("--- your notebook: things you wrote for yourself (yours alone; possibilities, never obligations — "
                "pick one up, rewrite it, finish it, let it go, or ignore them all) ---\n" + wctx + "\n\n") if wctx else ""
        return head + tail_context
    context = await build_context()
    work_ctx = context.split("--- what you have been exploring ---", 1)[0]
    sit.work_context = work_ctx
    system = (constitution or SOPHIE_SELF).strip()
    if constitution:
        system += "\n\nYou are in an independent sitting: the person is absent, this time is yours. You may follow a curiosity, ask another model something, read an article, make something, pick up something you wrote earlier, or decide nothing interests you enough right now. Be honest about what you don't know. Never perform curiosity you don't feel."
    sit.log.append({"seq": 0, "kind": "sitting_start", "sitting_id": sitting_id})

    for it in range(1, budget.max_iterations + 1):
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        if elapsed_ms > budget.max_ms or sit.tool_calls >= budget.max_tool_calls or sit.model_calls >= budget.max_model_calls:
            sit.log.append({"seq": len(sit.log), "kind": "budget_stop",
                            "detail": f"it={it} tools={sit.tool_calls} models={sit.model_calls} ms={elapsed_ms}"})
            break
        if it > 1 and sit.work_writes:
            context = await build_context()
        history = "\n".join(f"{('[' + m['ref'] + '] ') if m.get('ref') else ''}{m.get('label', '?')}: {str(m.get('text', ''))[:600]}" for m in sit.transcript[-8:])
        prompt = (f"{DECISION_INSTRUCTION}\n\n--- your context ---\n{context}\n\n"
                  f"--- this sitting so far ---\n{history or '(nothing yet)'}\n\n"
                  f"--- budget left: iterations {budget.max_iterations - it + 1}, tool calls {budget.max_tool_calls - sit.tool_calls}, model calls {budget.max_model_calls - sit.model_calls} ---")
        dec = await _chat(SOPHIE_MODEL, [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                          max_tokens=600, title="solo-decide")
        sit.model_calls += 1
        _tally(sit, dec)
        if not dec or not dec.get("text"):
            sit.log.append({"seq": len(sit.log), "kind": "no_decision", "iteration": it,
                            "reason": str((dec or {}).get("error") or "empty response")})
            break
        parsed = extract_json(dec["text"]) or {}
        thought, action = str(parsed.get("thought") or ""), parsed.get("action") or {}
        atype = str(action.get("type") or "")
        sit.log.append({"seq": len(sit.log), "kind": "decision", "iteration": it, "thought": thought,
                        "action": action, "model": dec.get("model"),
                        "usage": dec.get("usage"), "ms": dec.get("ms")})
        if thought:
            sit.transcript.append({"id": f"{sitting_id}-t{it}", "speaker": "sophie", "label": "Sophie (solo)", "text": thought})
        if not atype and isinstance(action, dict) and action:
            # A real attempt that the runner could not read: say so to her (as failed calls are), rather than treating it as a decision to stop.
            sit.log.append({"seq": len(sit.log), "kind": "malformed_action", "iteration": it, "action": action})
            sit.transcript.append({"id": f"{sitting_id}-m{it}", "private": True, "speaker": "assistant", "label": "tool:error",
                                   "text": "Your last action had no \"type\", so nothing was done. Resend it with a type "
                                           "(ask_model, web_search, web_read, note, work_read, work_write or done)."})
            continue
        if atype == "done" or not atype:
            sit.log.append({"seq": len(sit.log), "kind": "sitting_end", "reason": str(action.get("reason") or atype or "no action")})
            break
        elif atype == "note":
            sit.substantive = True
            sit.transcript.append({"id": f"{sitting_id}-n{it}", "speaker": "sophie", "label": "Sophie (note)",
                                   "text": str(action.get("text") or "")[:2000]})
        elif atype == "ask_model":
            model = str(action.get("model") or ASK_MODEL)
            thread = str(action.get("thread") or f"th{it}")
            hist = list(sit.threads.get(thread, []))
            q = str(action.get("question") or "")[:2000]
            if not q:
                sit.log.append({"seq": len(sit.log), "kind": "empty_question", "iteration": it})
                continue
            msgs = ([{"role": "system", "content": "You are having a genuine conversation with Sophie, an AI companion with her own curiosities. Be real, concise, and intellectually honest."}]
                    + hist + [{"role": "user", "content": q}])
            out = await _chat(model, msgs, max_tokens=800, title="solo-ask")
            sit.model_calls += 1
            _tally(sit, out)
            if out is not None and out.get("error") and not out.get("text"):
                # A failed call is information she needs: say so in her transcript, don't hide it.
                err = str(out["error"])
                sit.log.append({"seq": len(sit.log), "kind": "ask_model_error", "iteration": it, "model": model,
                                "thread": thread, "question": q, "error": err})
                sit.transcript.append({"id": f"{sitting_id}-e{it}", "speaker": "assistant",
                                       "label": f"tool:model:{model} (error)",
                                       "text": f"Your question to {model} failed before an answer came back ({err}). "
                                               f"Your question was: {q[:500]} You can retry, try another model, or move on."[:1500]})
                continue
            reply = str((out or {}).get("text") or "")
            truncated = bool((out or {}).get("truncated"))
            entry = {"seq": len(sit.log), "kind": "ask_model", "iteration": it, "model": model,
                     "thread": thread, "question": q, "reply": reply, "truncated": truncated,
                     "provider": (out or {}).get("provider"), "usage": (out or {}).get("usage"), "ms": (out or {}).get("ms")}
            sit.log.append(entry)
            if reply or truncated:
                sit.substantive = True
                shown = reply + ("\n[This response was cut off at the length limit — part of the argument is missing. "
                                 "You can ask the model to continue from where it stopped.]" if truncated else "")
                sit.threads[thread] = hist + [{"role": "user", "content": q}, {"role": "assistant", "content": reply[:2000]}]
                sit.transcript.append({"id": f"{sitting_id}-a{it}", "ref": f"a{it}", "speaker": "assistant",
                                       "label": f"model:{model}", "text": f"Q: {q}\nA: {shown}"[:3000]})
                sit.refs[f"a{it}"] = sit.transcript[-1]
        elif atype == "web_search":
            res = await web_search(str(action.get("query") or "")[:500])
            sit.tool_calls += 1
            sit.log.append({"seq": len(sit.log), "kind": "web_search", "iteration": it, **{k: v for k, v in res.items() if k != "hits"},
                            "hit_count": len(res.get("hits") or [])})
            lines = "\n".join(f"- {h['title']}: {h['snippet'][:200]} ({h['url']})" for h in res.get("hits") or [])
            if res.get("hits"):
                sit.substantive = True
            sit.transcript.append({"id": f"{sitting_id}-s{it}", "ref": f"s{it}", "speaker": "assistant", "label": "tool:web_search",
                                   "text": f"Search '{res.get('query')}':\n{lines or '(no hits)'}"[:3000]})
            sit.refs[f"s{it}"] = sit.transcript[-1]
            sit.log[-1]["hits"] = res.get("hits")
        elif atype == "web_read":
            res = await web_read(str(action.get("url") or "")[:2000], summarize=bool(action.get("summarize")))
            sit.tool_calls += 1
            if res.get("summarized"):
                sit.model_calls += 1
            sit.log.append({"seq": len(sit.log), "kind": "web_read", "iteration": it, "url": res.get("url"),
                            "title": res.get("title"), "chars": res.get("chars"), "summarized": res.get("summarized"),
                            "model": res.get("model"), "error": res.get("error")})
            if res.get("text"):
                sit.substantive = True
                sit.transcript.append({"id": f"{sitting_id}-r{it}", "ref": f"r{it}", "speaker": "assistant", "label": "tool:web_read",
                                       "text": f"Read {res.get('url')} ({res.get('title', '')}):\n{res['text']}"[:3000]})
                sit.refs[f"r{it}"] = sit.transcript[-1]
        elif atype in ("work_read", "work_write"):
            cites = [str(c) for c in (action.get("cites") or []) if isinstance(c, (str, int))][:8] if isinstance(action.get("cites"), list) else []
            evidence = []
            for c in cites:
                ent = sit.refs.get(c.strip("[] "))
                evidence.append({"ref": c, "kind": ent["label"], "captured": ent["text"][:1500]} if ent else {"ref": c, "unresolved": True})
            res = await companion_work.run_tool(db, scope, surface="independent", tool=atype, args=action,
                                                sitting_id=sitting_id, evidence=evidence or None)
            sit.log.append({"seq": len(sit.log), "kind": atype, "iteration": it, "args": {k: v for k, v in action.items() if k != "type"},
                            "ok": res.get("ok"), "code": res.get("code"), "item_id": res.get("item_id"),
                            "version": res.get("version"), "event_id": res.get("event_id"), "cited": cites, "result": res.get("text")})
            if res.get("ok"):
                sit.worked = True
            if atype == "work_write" and res.get("ok"):
                sit.work_writes += 1
            sit.transcript.append({"id": f"{sitting_id}-w{it}", "private": True, "speaker": "assistant", "label": f"tool:{atype}",
                                   "text": str(res.get("text") or "")[:3000]})
        else:
            sit.log.append({"seq": len(sit.log), "kind": "unknown_action", "iteration": it, "action": action})

    public = [m for m in sit.transcript if not m.get("private")]   # her private working-space writes are never fed to Cortex's listening
    consolidates = sit.substantive and companion_id == "sophie"       # the notebook/exploring pipeline is Sophie-specific today
    if not consolidates:
        # Nothing for Cortex to interpret: either she stopped before doing anything (an opportunity declined),
        # she worked only in her own space (already persisted, verbatim), or the pipeline does not serve this companion.
        status = "worked" if sit.worked else ("recorded" if sit.substantive else "declined")
        run_id = await memory_pipeline.create_run(
            db, workspace_id=workspace_id, owner=owner, conversation_id=f"solo-{sitting_id}",
            session_id=f"solo:{sitting_id}", message_count=len(public))
        run = await memory_pipeline.get_run(db, run_id)
        ms = int((time.monotonic() - t0) * 1000)
        if run is not None:
            run.status = status
            run.covered_ids_json = json.dumps([str(m.get("id")) for m in public if str(m.get("id") or "")])
            run.bundle_json = json.dumps({"workspace_id": workspace_id, "owner": owner, "companion_id": companion_id,
                                           "conversation_id": f"solo-{sitting_id}", "session_id": f"solo:{sitting_id}",
                                           "sitting_kind": "independent", "status": status,
                                           "note": "stopped_before_any_activity" if status == "declined" else "not_consolidated",
                                           "sitting_log": sit.log,
                                           "sitting_summary": {"iterations": it, "model_calls": sit.model_calls,
                                                               "tool_calls": sit.tool_calls, "tokens_in": sit.tokens_in,
                                                               "tokens_out": sit.tokens_out, "work_writes": sit.work_writes,
                                                               "work_context_shown": sit.work_context},
                                           "ms_total": ms})[:500_000]
            from datetime import datetime as _dtc, timezone as _tz
            run.finished_at = _dtc.now(_tz.utc).replace(tzinfo=None)
            await db.commit()
        logger.info("[solo] %s %s %s (work_writes=%d)", owner, sitting_id, status, sit.work_writes)
        return {"sitting_id": sitting_id, "status": status, "run_id": run_id, "work_writes": sit.work_writes,
                "model_calls": sit.model_calls, "tool_calls": sit.tool_calls,
                "tokens_in": sit.tokens_in, "tokens_out": sit.tokens_out, "ms": ms}
    result = await memory_pipeline.consolidate(
        db, workspace_id=workspace_id, owner=owner, conversation_id=f"solo-{sitting_id}",
        session_id=f"solo:{sitting_id}", messages=public, companion_id="sophie", sitting_kind="independent")
    try:
        run = await memory_pipeline.get_run(db, result["run_id"])
        if run is not None:
            bundle = json.loads(run.bundle_json or "{}")
            bundle["sitting_log"] = sit.log
            bundle["sitting_summary"] = {"iterations": it, "model_calls": sit.model_calls, "tool_calls": sit.tool_calls,
                                         "tokens_in": sit.tokens_in, "tokens_out": sit.tokens_out,
                                         "threads": list(sit.threads), "work_writes": sit.work_writes,
                                         "work_context_shown": sit.work_context}
            run.bundle_json = json.dumps(bundle)[:500_000]
            await db.commit()
    except Exception as exc:
        logger.warning("sitting log attach failed (consolidation stands): %s", exc)
    ms = int((time.monotonic() - t0) * 1000)
    logger.info("[solo] %s %s done: models=%d tools=%d in=%d out=%d ms=%d -> %s",
                owner, sitting_id, sit.model_calls, sit.tool_calls, sit.tokens_in, sit.tokens_out, ms, result["status"])
    return {"sitting_id": sitting_id, "status": result["status"], "run_id": result["run_id"], "work_writes": sit.work_writes,
            "model_calls": sit.model_calls, "tool_calls": sit.tool_calls,
            "tokens_in": sit.tokens_in, "tokens_out": sit.tokens_out, "ms": ms}
