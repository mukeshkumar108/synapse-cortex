"""The connect pass: maintain the person's connected world (entities, aliases, links, situations) after a session.

The ONLY place a model touches the connected layer. Reads are deterministic (known_world.py). Like the ledger agent: a
small tool-using agent that investigates, acts and verifies; deterministic code owns validity (unknown / malformed /
truncated tool calls are refused, a `stated` claim needs a quote that exists in the transcript, links must point at real
records), the model owns meaning. It sees the transcript as ground truth and never copies operational facts: it LINKS to the
ledger record that owns them.
"""
from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Set
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.known_world import KnownEntity, KnownLink
from src.models.world import AttentionAction, LedgerItem
from src.services import agent_runtime, known_world as kw

logger = logging.getLogger(__name__)

PRIMARY_MODEL = os.getenv("WORLD_AGENT_MODEL", "qwen/qwen3.8-27b")
FALLBACK_MODEL = os.getenv("WORLD_AGENT_FALLBACK_MODEL", "openrouter:qwen/qwen3.7-flash")
MAX_ITERS = int(os.getenv("WORLD_AGENT_MAX_ITERS", "14"))
MAX_TOKENS = int(os.getenv("WORLD_AGENT_MAX_TOKENS", "2500"))
MAX_ENTITIES = 400
MAX_FINISH_BOUNCES = 2
STATUSES = ("active", "dormant", "resolved")

CONTRACT = """You maintain a small, accurate picture of one person's WORLD: who and what it is about, and how those things connect. You read a finished conversation (the transcript is the ground truth) and keep an entity registry current. You are not the task list.

What belongs:
- Entities: people, projects, organisations, places and topics that matter beyond a passing mention (a collaborator, family member, a project, a recurring concern: yes; a barista mentioned once: no).
- Situations (kind "situation", or a more specific word such as "health" or "decision"): developing matters that are NOT tasks — a worry, a family illness, a health observation, an unresolved decision, a relationship in transition, a curiosity worth returning to. Their state lives in a short summary; whether to follow up is decided elsewhere.
- - Happenings (form "happening"): something that occurred and may matter later, even when its meaning is not yet known — an argument, a kiss, a celebration, an injury, a setback, a visit, something a third party disclosed. Record WHAT happened in plain words, when (occurred_on, the person's local date), who or what it involved (link it to those entities and to "the person", relation like "involved"), how consequential it seems (significance 1 minor, 2 ordinary, 3 consequential) and tags. Do NOT interpret it, assign a motive or decide what it means; if the person said what it means, say so and quote it. A happening is not a task or an open loop. It only becomes an unresolved concern if the person says it is (then record the concern as a situation, linked to it).
- Dispositions (form "disposition"): durable likes, dislikes, favourites, interests, hopes, fears, values, ambitions ("my favourite book is The Count of Monte Cristo"). Stated by the person, with a quote. Update or supersede when their view changes. Tag them so they can be found when the subject arises.
- Patterns (form "pattern"): only when SEVERAL happenings or observations recur in a way the person or the evidence supports (e.g. each overnight stay at their mother's: poor sleep, tension). A pattern is a short, provisional, revisable reading: basis "inferred" unless the person says it; link it "supported by" each happening; revise the summary or retire it (status resolved) when new evidence contradicts it. No diagnoses, no psychological labels, no motives. One happening is not a pattern.
- tags: up to 8 short lower-case soft signals used to find a record when the subject comes up: a broad domain and facet as "domain/facet" (relationships/romantic, relationships/family, health/sleep, culture/literature, work/projects) plus any ordinary words the person might use ("books", "reading"). They are hints for relevance, never boundaries.

Operational matters (appointments, deadlines, promises, things awaited) belong to the LEDGER, which is maintained separately. Never copy their dates, times or status into a summary. Instead LINK the entity to the ledger record by its key (link_entity with ledger_key) so the record is read from its owner every time. The records touched in this session are listed for you.

Summaries: one or two plain sentences saying what or who this is and where it stands, in the person's terms. No dates or commitments. No diagnoses. No feelings the person did not express. Say only what the person said: something they are considering stays "considering", an open question stays open, never restated as decided or done. The no-assumed-gender rule below applies to summaries AND to the notes and reasons you write. Update the summary when the situation develops, rather than adding to it.

The person: the registry always contains an entity named "the person" (kind self). It stands for the person you are talking with. Use it as the other end of any relationship to them (Ashley "partner of" the person; Priya "manager of" the person). NEVER let another entity stand in for the person, and never edit "the person" itself. Do not assume the person's gender or marital status: refer to them as "they/them/their" in plain active sentences, never as "the person" ("Ashley is their partner and thinks they should lead it", "They are weighing whether to lead the pilot"), and record "wife", "husband", "he" or "she" only if the person said so. Summaries describe the thing itself; the relationship to the person lives in a link, not in prose. Do not state kinship or other relationships BETWEEN other people in a summary ("Ashley's mum", "Ruth's sibling"): put them in links, where they carry a basis and can be corrected.

Ledger links: link an operational record to the entity it is actually about (the appointment belongs to the person, not to the organisation they work for); if it is simply the person's own, link it from "the person".

The companion: the registry also contains an entity for the companion herself (kind companion, e.g. "Sophie"). She is a party of her own. Her interests, wishes, curiosities, plans and conclusions are linked to HER (e.g. Sophie "interested in" a topic, Sophie "wants to see" something), never to "the person". What she said or felt about the relationship is her reading, not a fact about the person. The person's own interests, plans and feelings are linked to "the person". A happening or idea that belongs to both is linked to both. Never edit or duplicate either of them.

Names: aliases are the names the person actually uses: a first name, a short form ("the Bloom pilot"). Add them. Read a relation as "<from> <relation> <to>" and give the link the direction that reads true.

Relationships: describe them in plain words between two things ("adviser on", "potential pilot for", "worried about"). basis "stated" ONLY if the person said it, and you must give the quote — it is checked against the transcript and downgraded to "inferred" if it is not there. Inferred relations are welcome (they help) but stay labelled; never promote an inference to a fact. A different relation between the same two things can coexist (an adviser can also be a friend). When a relationship CHANGES or is corrected, add the new link and supersede_link the old with the reason, taking the link id from get_entity: only the link that actually changed. If you retire the wrong one, restore_link brings it back. A stated quote may come only from the person's own words (not the assistant's), copied exactly.

Care: set sensitive true for emotional, health or family difficulty. If the person says not to bring something up, set suppressed true — the memory is kept, it just stops being raised unprompted. Corrections ("that's not right", a wrong name) fix the entity or merge the duplicate; they are never ignored.

Method: list_entities first, search before creating, create only what is genuinely new, link what this session connected, then re-read (list_entities or get_entity) after your last change and finish with `considered`: one line saying what you deliberately did NOT record and why (or "nothing notable"). Making no changes is a correct outcome when nothing durable was said."""

TOOLS = [
    {"type": "function", "function": {"name": "list_entities", "description": "All current entities (active and dormant) with ids, kind, status and a short summary.", "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {"name": "search_entities", "description": "Find entities by name or alias (includes resolved ones).", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_entity", "description": "One entity in full: aliases and its links, with link ids.", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "create_entity", "description": "Create a new entity. kind is free text (person, project, organisation, place, topic, situation, health, ...). aliases are other names the person uses for it. basis stated needs a quote from the transcript.",
                                      "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "kind": {"type": "string"}, "summary": {"type": "string"}, "aliases": {"type": "array", "items": {"type": "string"}},
                                                                                     "sensitive": {"type": "boolean"}, "basis": {"type": "string"}, "evidence": {"type": "string"},
                                                                                     "form": {"type": "string", "description": "empty (a person/project/organisation/place/topic) | situation | happening | disposition | pattern"},
                                                                                     "tags": {"type": "array", "items": {"type": "string"}}, "occurred_on": {"type": "string", "description": "YYYY-MM-DD, happenings"},
                                                                                     "significance": {"type": "integer"}}, "required": ["name", "kind"]}}},
    {"type": "function", "function": {"name": "update_entity", "description": "Change an entity: name, kind, summary (replaces), status active|dormant|resolved, sensitive, suppressed, add_aliases.",
                                      "parameters": {"type": "object", "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "kind": {"type": "string"}, "summary": {"type": "string"}, "status": {"type": "string"},
                                                                                     "sensitive": {"type": "boolean"}, "suppressed": {"type": "boolean"}, "add_aliases": {"type": "array", "items": {"type": "string"}},
                                                                                     "basis": {"type": "string"}, "evidence": {"type": "string"},
                                                                                     "form": {"type": "string"}, "tags": {"type": "array", "items": {"type": "string"}}, "occurred_on": {"type": "string"},
                                                                                     "significance": {"type": "integer"}}, "required": ["id"]}}},
    {"type": "function", "function": {"name": "link_entity", "description": "Connect an entity to exactly one target: another entity (to_entity_id), a ledger record (ledger_key), or an attention intention (attention_id). relation is plain words. basis stated needs a transcript quote.",
                                      "parameters": {"type": "object", "properties": {"from_id": {"type": "string"}, "relation": {"type": "string"}, "to_entity_id": {"type": "string"}, "ledger_key": {"type": "string"},
                                                                                     "attention_id": {"type": "string"}, "basis": {"type": "string"}, "evidence": {"type": "string"}}, "required": ["from_id", "relation", "basis"]}}},
    {"type": "function", "function": {"name": "supersede_link", "description": "Mark a link as no longer true or corrected (kept as history), with the reason.", "parameters": {"type": "object", "properties": {"link_id": {"type": "string"}, "reason": {"type": "string"}}, "required": ["link_id", "reason"]}}},
    {"type": "function", "function": {"name": "restore_link", "description": "Undo a supersede_link that was a mistake.", "parameters": {"type": "object", "properties": {"link_id": {"type": "string"}}, "required": ["link_id"]}}},
    {"type": "function", "function": {"name": "merge_entities", "description": "Two names for one thing: absorb_id is merged into keep_id (aliases and links move; nothing is deleted).", "parameters": {"type": "object", "properties": {"keep_id": {"type": "string"}, "absorb_id": {"type": "string"}}, "required": ["keep_id", "absorb_id"]}}},
    {"type": "function", "function": {"name": "finish", "description": "End after re-reading the registry following your last change.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "considered": {"type": "string"}}, "required": ["summary", "considered"]}}},
]
ALLOWED = {t["function"]["name"]: set((t["function"]["parameters"].get("properties") or {}).keys()) for t in TOOLS}

_chat_fn: Optional[Callable[..., Any]] = None


def set_chat_fn(fn: Optional[Callable[..., Any]]) -> None:
    global _chat_fn
    _chat_fn = fn


class State:
    def __init__(self, ws: str, owner: str, session_id: str, run_id: Optional[UUID], transcript: str, person_label: str = "") -> None:
        self.ws, self.owner, self.session_id, self.run_id, self.transcript = ws, owner, session_id, run_id, transcript
        self.person_text = _person_lines(transcript, person_label)
        self.seq = self.last_read = self.last_write = 0
        self.bounces = 0
        self.touched: Set[str] = set()
        self.changes = {"created": 0, "updated": 0, "linked": 0, "superseded": 0, "merged": 0}
        self.gate: List[str] = []


def _brief(e: KnownEntity, aliases: Optional[List[str]] = None) -> Dict[str, Any]:
    return {"id": str(e.id), "name": e.name, "kind": e.kind, "status": e.status, "sensitive": e.sensitive, "suppressed": e.suppressed,
            "basis": e.basis, "summary": e.summary[:160], **({"aliases": aliases} if aliases is not None else {})}


def _parse_extras(args: Dict[str, Any]) -> tuple:
    """(extras dict, error). form/tags/occurred_on/significance, validated; nothing guessed."""
    out: Dict[str, Any] = {}
    if "form" in args:
        f = str(args.get("form") or "").strip().lower()
        if f not in kw.FORMS:
            return {}, "form must be empty, situation, happening, disposition or pattern"
        out["form"] = f
    if "tags" in args:
        out["tags"] = kw.norm_tags(args.get("tags") if isinstance(args.get("tags"), (list, str)) else [])
    if "occurred_on" in args and str(args.get("occurred_on") or "").strip():
        try:
            out["occurred_on"] = datetime.strptime(str(args["occurred_on"]).strip()[:10], "%Y-%m-%d")
        except ValueError:
            return {}, "occurred_on must be YYYY-MM-DD"
    if "significance" in args:
        try:
            out["significance"] = min(3, max(1, int(args["significance"])))
        except (TypeError, ValueError):
            return {}, "significance must be 1, 2 or 3"
    return out, ""


def _person_lines(transcript: str, label: str) -> str:
    """The person's own words only (a stated claim cannot be backed by something the assistant said). No label known: everything."""
    if not label:
        return transcript or ""
    pre = label.strip().lower() + ":"
    return "\n".join(l.strip()[len(pre):] for l in (transcript or "").splitlines() if l.strip().lower().startswith(pre))


def _nq(s: str) -> str:
    s = str(s or "").replace("\u2019", "'").replace("\u2018", "'").replace("\u201c", '"').replace("\u201d", '"')
    return re.sub(r"\s+", " ", s).strip().lower()


def _quote(evidence: str, st: "State") -> str:
    """The evidence as the person said it, or "" if it is not in their words. Whole-quote check (pieces joined by an ellipsis are each
    checked); nothing is repaired or stitched together."""
    ev = str(evidence or "").strip().strip("\"'\u201c\u201d")
    if not ev:
        return ""
    hay = _nq(st.person_text)
    pieces = [p.strip() for p in re.split(r"\u2026|\.\.\.", ev) if p.strip()]
    if not pieces or any(len(_nq(p)) < 6 or _nq(p) not in hay for p in pieces):
        return ""
    return " \u2026 ".join(pieces)[:400]


async def _tool(db: AsyncSession, st: State, name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    ws, owner = st.ws, st.owner
    extra = sorted(set(args) - ALLOWED.get(name, set()))
    if extra:
        return {"error": f"unsupported argument(s) for {name}: {', '.join(extra)}. Allowed: {', '.join(sorted(ALLOWED.get(name, set()))) or '(none)'}. Nothing was changed."}

    def read() -> None:
        st.seq += 1
        st.last_read = st.seq

    def write() -> None:
        st.seq += 1
        st.last_write = st.seq

    if name == "list_entities":
        read()
        ents = await kw.list_all(db, ws, owner, statuses=("active", "dormant"))
        return {"entities": [_brief(e, [a.alias for a in await kw.aliases_of(db, ws, owner, e.id) if kw.norm(a.alias) != e.name_key][:4]) for e in ents]}
    if name == "search_entities":
        read()
        return {"matches": [_brief(e) for e in (await kw.find(db, ws, owner, str(args.get("query") or "")))[:8]]}
    if name == "get_entity":
        read()
        e = await kw.get(db, ws, owner, args.get("id"))
        if e is None:
            return {"error": "no such entity — list or search first, never invent ids"}
        links = (await db.execute(select(KnownLink).where(KnownLink.honcho_workspace_id == ws, KnownLink.owner_peer_id == owner,
                                                          KnownLink.from_entity_id == e.id))).scalars().all()
        return {"entity": _brief(e, [a.alias for a in await kw.aliases_of(db, ws, owner, e.id)]),
                "links": [{"id": str(l.id), "relation": l.relation, "target_kind": l.target_kind, "target": l.target_ref, "basis": l.basis, "status": l.status} for l in links]}
    if name == "create_entity":
        nm, kind = str(args.get("name") or "").strip(), str(args.get("kind") or "").strip()
        if not nm or not kind:
            return {"error": "name and kind are required"}
        if kind.lower() == kw.SELF_KIND or kw.norm(nm) == kw.norm(kw.SELF_NAME):
            return {"error": "the person already has their own entity ('the person'); link to it instead of creating another"}
        if kind.lower() == kw.COMPANION_KIND:
            return {"error": "the companion already has her own entity; link to it instead of creating another"}
        if await kw.find(db, ws, owner, nm, statuses=("active", "dormant", "resolved"), exact=True):
            hit = (await kw.find(db, ws, owner, nm, exact=True))[0]
            return {"error": f"'{nm}' already exists as {hit.id} ({hit.name}) — update it, or add an alias, instead of duplicating"}
        if len(await kw.list_all(db, ws, owner, statuses=("active", "dormant", "resolved"), limit=MAX_ENTITIES + 1)) > MAX_ENTITIES:
            return {"error": "the registry is at its size limit; merge or resolve entities first"}
        quote = _quote(str(args.get("evidence") or ""), st)
        extras, err = _parse_extras(args)
        if err:
            return {"error": err}
        basis = "stated" if (str(args.get("basis") or "").strip().lower() == "stated" and quote) else "inferred"
        e = await kw.create(db, ws, owner, name=nm, kind=kind, summary=str(args.get("summary") or ""), sensitive=bool(args.get("sensitive")),
                            basis=basis, aliases=[a for a in (args.get("aliases") or []) if isinstance(a, str)], run_id=st.run_id,
                            session_id=st.session_id, quote=quote, **extras)
        write()
        st.touched.add(str(e.id))
        st.changes["created"] += 1
        out = {"ok": True, "entity": _brief(e)}
        if str(args.get("basis") or "").strip().lower() == "stated" and basis == "inferred":
            out["note"] = "recorded as inferred: no quote was supplied, or it is not in the person's own words (copy it exactly)"
        return out
    if name == "update_entity":
        e = await kw.get(db, ws, owner, args.get("id"))
        if e is None:
            return {"error": "no such entity — list or search first, never invent ids"}
        if kw.is_self(e) or kw.is_companion(e):
            return {"error": "'the person' and the companion stand for the two parties and are not edited; link other things to them"}
        extras, err = _parse_extras(args)
        if err:
            return {"error": err}
        if "status" in args and str(args["status"]).strip().lower() not in STATUSES:
            return {"error": "status must be active, dormant or resolved (merge_entities is the way to combine two)"}
        if isinstance(args.get("name"), str) and args["name"].strip():
            await kw.add_alias(db, ws, owner, e.id, e.name)                   # the old name keeps resolving
            e.name, e.name_key = args["name"].strip()[:200], kw.norm(args["name"])
            await kw.add_alias(db, ws, owner, e.id, e.name)
        if isinstance(args.get("kind"), str) and args["kind"].strip():
            e.kind = args["kind"].strip().lower()[:40]
        if isinstance(args.get("summary"), str):
            e.summary = args["summary"].strip()[:kw.SUMMARY_MAX]
        if "status" in args:
            e.status = str(args["status"]).strip().lower()
        for flag in ("sensitive", "suppressed"):
            if flag in args:
                setattr(e, flag, bool(args[flag]))
        for a in (args.get("add_aliases") or []):
            if isinstance(a, str):
                await kw.add_alias(db, ws, owner, e.id, a)
        for k_, v_ in extras.items():
            setattr(e, k_, v_)
        quote = _quote(str(args.get("evidence") or ""), st)
        if quote and str(args.get("basis") or "").strip().lower() == "stated" and e.basis != "stated":
            e.basis = "stated"                     # the person has now said it themself (verified quote): the entity is no longer a mere inference
        await kw.touch(db, e, st.session_id, quote)
        write()
        st.touched.add(str(e.id))
        st.changes["updated"] += 1
        return {"ok": True, "entity": _brief(e, [a.alias for a in await kw.aliases_of(db, ws, owner, e.id)])}
    if name == "link_entity":
        frm = await kw.get(db, ws, owner, args.get("from_id"))
        if frm is None:
            return {"error": "from_id is not a known entity — list or search first"}
        relation = str(args.get("relation") or "").strip()
        if not relation:
            return {"error": "relation is required, in plain words"}
        targets = [k for k in ("to_entity_id", "ledger_key", "attention_id") if str(args.get(k) or "").strip()]
        if len(targets) != 1:
            return {"error": "give exactly one target: to_entity_id, ledger_key or attention_id"}
        t = targets[0]
        if t == "to_entity_id":
            to = await kw.get(db, ws, owner, args["to_entity_id"])
            if to is None:
                return {"error": "to_entity_id is not a known entity"}
            if to.id == frm.id:
                return {"error": "an entity cannot be linked to itself"}
            tkind, tref = "entity", str(to.id)
        elif t == "ledger_key":
            led = (await db.execute(select(LedgerItem).where(LedgerItem.honcho_workspace_id == ws, LedgerItem.owner_peer_id == owner,
                                                             LedgerItem.situation_key == str(args["ledger_key"])))).scalars().first()
            if led is None:
                return {"error": f"no ledger record with key '{args['ledger_key']}' — use a key from the records listed for you"}
            tkind, tref = "ledger", led.situation_key
        else:
            try:
                act = (await db.execute(select(AttentionAction).where(AttentionAction.id == UUID(str(args["attention_id"])), AttentionAction.honcho_workspace_id == ws,
                                                                      AttentionAction.owner_peer_id == owner))).scalars().first()
            except Exception:
                act = None
            if act is None:
                return {"error": "no such attention intention"}
            tkind, tref = "attention", str(act.id)
        quote = _quote(str(args.get("evidence") or ""), st)
        want = str(args.get("basis") or "").strip().lower()
        basis = "stated" if (want == "stated" and quote) else "inferred"
        lk, created = await kw.link(db, ws, owner, from_id=frm.id, relation=relation, target_kind=tkind, target_ref=tref, basis=basis,
                                    evidence=quote, session_id=st.session_id, run_id=st.run_id)
        await kw.touch(db, frm, st.session_id, quote)
        write()
        st.touched.add(str(frm.id))
        st.changes["linked"] += 1 if created else 0
        out = {"ok": True, "link": {"id": str(lk.id), "relation": lk.relation, "basis": lk.basis, "created": created}}
        if want == "stated" and basis == "inferred":
            out["note"] = "recorded as inferred: no quote was supplied, or it is not in the person's own words (copy it exactly)"
        return out
    if name == "supersede_link":
        lk = await kw.supersede(db, ws, owner, args.get("link_id"), str(args.get("reason") or ""))
        if lk is None:
            return {"error": "no such link"}
        write()
        st.changes["superseded"] += 1
        # say exactly what was retired, so a wrong id is visible right away (restore_link undoes it)
        return {"ok": True, "link": {"id": str(lk.id), "status": lk.status, "retired": await _describe_link(db, ws, owner, lk)}}
    if name == "restore_link":
        lk = await kw.restore(db, ws, owner, args.get("link_id"))
        if lk is None:
            return {"error": "no such link"}
        write()
        st.changes["superseded"] = max(0, st.changes["superseded"] - 1)
        return {"ok": True, "link": {"id": str(lk.id), "status": lk.status, "restored": await _describe_link(db, ws, owner, lk)}}
    if name == "merge_entities":
        kept = await kw.merge(db, ws, owner, args.get("keep_id"), args.get("absorb_id"))
        if kept is None:
            return {"error": "could not merge: both must be known, different entities"}
        write()
        st.touched.add(str(kept.id))
        st.changes["merged"] += 1
        return {"ok": True, "entity": _brief(kept, [a.alias for a in await kw.aliases_of(db, ws, owner, kept.id)])}
    return {"error": "unknown tool"}


async def _describe_link(db: AsyncSession, ws: str, owner: str, lk: KnownLink) -> str:
    frm = await kw.get(db, ws, owner, lk.from_entity_id)
    to = (await kw.get(db, ws, owner, lk.target_ref)).name if lk.target_kind == "entity" and await kw.get(db, ws, owner, lk.target_ref) else lk.target_ref
    return f"{frm.name if frm else '?'} — {lk.relation} — {to}"


def _trim(v: Any, n: int) -> str:
    s = v if isinstance(v, str) else json.dumps(v, default=str)
    return s if len(s) <= n else s[:n] + "…"


async def run(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str, run_id: Optional[UUID], transcript: str,
              ledger_context: str, date_reference: str, time_zone: str, person_label: str = "", companion_name: str = "") -> Dict[str, Any]:
    st = State(workspace_id, owner, session_id, run_id, transcript, person_label)
    await kw.ensure_self(db, workspace_id, owner)
    if companion_name:
        await kw.ensure_companion(db, workspace_id, owner, companion_name)
    await db.commit()
    models = [PRIMARY_MODEL] + ([FALLBACK_MODEL] if FALLBACK_MODEL and FALLBACK_MODEL != PRIMARY_MODEL else [])
    model_used = models[0]
    # The first read is always list_entities, so code does it and hands the result over (one fewer model round trip). The finish gate still needs a re-read after the last write.
    registry = await _tool(db, st, "list_entities", {})
    inspected = True
    messages: List[Dict[str, Any]] = [
        {"role": "system", "content": CONTRACT + f"\n\n{date_reference} (timezone {time_zone}).\nMake all independent tool calls in a single turn."},
        {"role": "user", "content": "A finished session. Update the person's connected world.\n\n--- current entities (already listed for you; list again after your last change) ---\n" + _trim(registry, 7000)
                                    + "\n\n--- operational records touched or open (link to these by key; never copy their dates) ---\n"
                                    + (ledger_context or "(none)") + "\n\n--- session transcript (ground truth) ---\n" + transcript[-9000:]}]
    calls: List[Dict[str, Any]] = []
    summary: Optional[str] = None
    gate_ok = False
    for _ in range(MAX_ITERS):
        out = await agent_runtime.chat(model_used, messages, TOOLS, max_tokens=MAX_TOKENS, module="world", injected=_chat_fn)
        if out is None and len(models) > 1 and model_used == models[0]:
            model_used = models[1]
            out = await agent_runtime.chat(model_used, messages, TOOLS, max_tokens=MAX_TOKENS, module="world", injected=_chat_fn)
        if out is None:
            break
        tcs = out.get("tool_calls") or []
        calls.append({"model": out.get("model"), "finish_reason": out.get("finish_reason"), "n_tools": len(tcs), "usage": out.get("usage"), "trace": []})
        assistant: Dict[str, Any] = {"role": "assistant", "content": out.get("content") or ""}
        if tcs:
            assistant["tool_calls"] = tcs
        messages.append(assistant)
        if not tcs:
            messages.append({"role": "user", "content": "You made no tool calls. Call list_entities first, then act, then finish."})
            continue
        truncated = out.get("finish_reason") == "length"
        done = False
        for tc in tcs:
            fn = tc.get("function") or {}
            nm = str(fn.get("name") or "")
            raw = fn.get("arguments") or "{}"
            res: Dict[str, Any]
            if truncated:
                res = {"error": "your output was cut off, so this call may be incomplete. Nothing ran. Resend it, shorter."}
            else:
                try:
                    args = json.loads(raw) if isinstance(raw, str) else raw
                except Exception:
                    args = None
                if not isinstance(args, dict):
                    res = {"error": "arguments were not a valid JSON object. Nothing ran. Resend with valid JSON."}
                elif nm == "finish":
                    unknown = sorted(set(args) - ALLOWED["finish"])
                    problems: List[str] = []
                    if unknown:
                        problems.append(f"unsupported argument(s): {', '.join(unknown)}")
                    if st.last_write and st.last_read < st.last_write:
                        problems.append("Re-read (list_entities or get_entity) AFTER your last change before finishing.")
                    if not str(args.get("considered") or "").strip():
                        problems.append("considered is required: one line on what you deliberately did not record (or 'nothing notable').")
                    if problems and st.bounces < MAX_FINISH_BOUNCES:
                        st.bounces += 1
                        res = {"error": "finish refused — fix these and finish again", "problems": problems}
                    else:
                        summary, gate_ok, done = str(args.get("summary") or "")[:500], not problems, True
                        st.gate = problems
                        res = {"ok": True}
                else:
                    if nm in ("list_entities", "search_entities", "get_entity"):
                        inspected = True
                    try:
                        res = await _tool(db, st, nm, args)
                        await db.commit()
                    except Exception as exc:
                        await db.rollback()
                        res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
            calls[-1]["trace"].append({"name": nm, "args": _trim(raw, 500), "result": _trim(res, 400)})
            messages.append({"role": "tool", "tool_call_id": tc.get("id", ""), "name": nm, "content": json.dumps(res)[:3000]})
            if done:
                break
        if done:
            break
    status = ("verified" if gate_ok else "finished_unchecked") if summary is not None and inspected else ("unfinished" if inspected else "never_inspected")
    return {"status": status, "summary": summary, "changes": st.changes, "touched": sorted(st.touched), "calls": calls, "model": model_used,
            "gate_failures": st.gate, "wrote": st.last_write > 0}
