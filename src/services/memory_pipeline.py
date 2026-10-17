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

SITUATIONS_PROMPT = """Maintain an understanding of this person's unfolding circumstances from the findings below. You are updating situations, not filing tasks.

Currently open situations (with stable keys):
{open_items}

From the findings, return ONLY a JSON object: {"new": [...], "update": [...], "close": [...]}.
- new: {key (short stable slug, e.g. thursday-presentation), title, kind (open vocabulary: commitment/event/thread/situation/reminder/aspiration/invitation/...), confidence (observed/reported/inferred), detail (circumstance, terms, what's known AND unknown), timing_text (provisional timing in own words, "someday" allowed), expected_date (YYYY-MM-DD only if an exact date was stated, else null), waiting_on (who/what is awaited, else ""), question_text (unresolved question or missing info, else ""), linked_keys (keys of related open situations), evidence (short quotes or session refs it rests on)}
- Temporary changes to routines or circumstances count as situations: record what changed, how long it lasts, AND the exact condition that ends it (e.g. "afternoon walks for two weeks, back to mornings when school resumes"). The end condition is part of the fact — never carry the change forward without it.
- update: {key (must match an open key), plus only the fields that changed, plus new evidence appended}
- close: {key, status (done/cancelled/answered), evidence (the quote or fact proving it — required)}

Rules, no exceptions:
- An aspiration is not a task and never closes by silence; record it (kind aspiration) or leave it alone.
- An invitation is not an accepted commitment; a provisional invitation stays provisional.
- Inferred is not observed: mark confidence honestly. A hypothesis is not a fact.
- An unresolved question isn't a task; put it in question_text, don't invent an obligation.
- Never invent dates, owners, or obligations. expected_date only for exact stated dates.
- Close only on evidence in these findings. Time passing proves nothing.
- A reminder the person asked for is an attention mechanism: keep the underlying situation, note the reminder in detail.
- Match to open keys wherever the finding concerns an already-known situation instead of creating a duplicate.
- Return {} lists empty when there is nothing: {"new": [], "update": [], "close": []}."""

PREPARATION_PROMPT = """You are forming a brief private perspective for Sophie, a companion who genuinely cares about this person, ahead of their next conversation. Inputs: the living notebook, the operational ledger, the continuing arc of recent conversations, and the current date/time.

Write short, first-person, future-oriented thoughts: what matters to him and why, what's on his plate now and approaching, what changed since they last spoke, what she is genuinely curious about or could usefully notice. Be honest about what you don't know — never present a guess as a fact, never turn "he wants to try X" into "he failed at X again". Notice opportunities without manufacturing judgments.

This is not a script and not instructions for what she must say — just things she can think from. Her independent explorations are her own; she may bring one up if it is genuinely relevant to the moment, never as a report of everything she did. Do not perform being a companion, declare your role, or use therapeutic language. Do not carry yesterday's mood into today; begin open to the present.

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


def _parse_situations(raw: str) -> Dict[str, List[Dict[str, Any]]]:
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
    by_title = {(str(i.title).strip().lower(), str(i.kind)): i for i in known}
    for e in statements.get("new", []):
        title = str(e.get("title") or "").strip()
        if not title:
            continue
        key = str(e.get("key") or "").strip().lower().replace(" ", "-")[:80]
        if (key and key in by_key) or (title.lower(), str(e.get("kind") or "situation")) in by_title:
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
        if e.get("status") in ("open", "waiting", "watching"):
            item.status = str(e["status"])
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


async def read_state(db: AsyncSession, *, workspace_id: str, owner: str) -> Dict[str, Any]:
    """Notebook + ledger + arc for inspection. Pure reads, no model."""
    pages = await live_pages(db, workspace_id, owner)
    ledger = await open_ledger(db, workspace_id, owner, limit=50)
    arc = await get_arc(db, workspace_id, owner)
    prep = await get_preparation(db, workspace_id=workspace_id, owner=owner)
    return {
        "notebook": {k: {"title": PAGE_TITLES[k], "version": p.version, "text": p.text} for k, p in pages.items()},
        "ledger": [{"id": str(i.id), "key": i.situation_key, "kind": i.kind, "title": i.title,
                    "status": i.status, "confidence": i.confidence, "detail": i.detail,
                    "timing": i.timing_text, "waiting_on": i.waiting_on, "question": i.question_text,
                    "linked": (json.loads(i.linked_keys_json) if (i.linked_keys_json or "").startswith("[") else [])}
                   for i in ledger],
        "arc": {"version": arc.version, "text": arc.text},
        "preparation": prep,
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
    extract = await _generate("ledger", SITUATIONS_PROMPT.replace("{open_items}", open_lines) +
                              f"\n\n--- findings ---\n{findings or handoff_text}",
                              1000, _models("MEMORY_DISCOVERY_MODELS", "qwen/qwen3.8-27b"))
    bundle["ledger_extract"] = extract or {"skipped": True}
    statements = _parse_situations(str((extract or {}).get("text") or ""))
    counts = await apply_situations(db, workspace_id=workspace_id, owner=owner, run_id=run.id,
                                    session_id=session_id, statements=statements, known=ledger)
    bundle["ledger_added"] = counts["added"]
    bundle["ledger_counts"] = counts

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
    call = await _generate("preparation",
                           f"{PREPARATION_PROMPT}\n\n--- now ---\n{now_iso}\n\n--- notebook ---\n{notebook_text}\n\n--- operational ledger (open) ---\n{ledger_text}\n\n--- where conversations stand ---\n{arc.text}",
                           600, _models("MEMORY_EDITOR_MODELS", "qwen/qwen3.8-27b"))
    text = str((call or {}).get("text") or "").strip()
    fingerprint = _fingerprint(notebook_text, ledger_text, arc.text, now_iso[:10])
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


async def review(db: AsyncSession, *, workspace_id: str, owner: str, lookback_runs: int = 6) -> Dict[str, Any]:
    """Longitudinal noticing across recent sessions: one model call over open
    situations + recent findings. Applies updates, never closes."""
    from datetime import datetime as _dt
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
