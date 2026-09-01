"""LANE 2 — Honcho-backed discovery sweeper.

The slower semantic half of the three-speed model. Lane 1 (narrow real-time)
handles explicit operational actions NOW. Lane 2 asks object-shaped semantic
questions over accumulated Honcho history — goals, habits/strategies, open
loops, blockers, SOPHIE'S PROMISES (assistant turns are mined here and
nowhere else) — and promotes evidence-backed findings through the EXISTING
deterministic machinery (save_expectation_idempotent, open-loop creation).
No second state system.

Triggers (caller's responsibility): session settles, turn accumulation,
explicit promise detected in Lane 1, or periodic catch-up. This service is
idempotent per evidence message, so re-running is safe.

Invariants preserved:
- user evidence > machine inference: every promoted item cites verbatim
  Honcho evidence (message ids preserved); the synthesizer may only quote,
  never invent.
- deterministic code commits: promotion goes through the same persistence
  functions the real-time lane uses.
- bounded: few questions, small limits, one synthesis call.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.clients.honcho_client import HonchoClient
from src.services.persistence import save_expectation_idempotent
from src.services.turn_extractor import LLMExtractorProvider, _find_normalized

logger = logging.getLogger(__name__)

SWEEPER_VERSION = "lane2-sweeper-v1"

QUESTIONS = [
    ("goal", "What does the user say they want to achieve or keep doing — step goals, fitness, work objectives, plans they want to keep up? Quote their exact words."),
    ("strategy", "What strategy or routine did the user agree to or describe keeping — split walks, morning routines, schedules? Quote their exact words."),
    ("sophie_promise", "What did Sophie (the assistant side) explicitly PROMISE to do — push the user, remind them, check in, hold them accountable? Quote her exact words from assistant messages."),
    ("open_loop", "What unresolved threads or pending matters did the user mention — things waiting, unfinished, to be dealt with? Quote their exact words."),
    ("blocker", "What blockers or constraints did the user describe — no car, no time, other people, circumstances stopping them? Quote their exact words."),
]

PROMOTABLE_KINDS = {"goal", "strategy", "sophie_promise", "open_loop", "blocker"}

_SYNTH_PROMPT = """You are Lane 2 of a companion's state engine: the ASYNC discovery sweeper.
Below are EVIDENCE PACKETS: real messages from Honcho memory (user and assistant turns),
each with an evidence id. Decide whether the evidence contains durable, still-relevant
findings worth promoting into operational state.

Return JSON {{"candidates": [...]}}. Each candidate:
{{"kind": "goal|strategy|sophie_promise|open_loop|blocker",
  "title": "short canonical title (e.g. 'Daily 10,000 steps goal', 'Sophie pushes on daytime walks')",
  "summary": "one sentence describing the durable finding",
  "evidence_text": "VERBATIM span copied from the evidence (never invented)",
  "evidence_id": "the evidence id it came from",
  "cadence": "daily|weekly|interval|none",
  "target_amount": null | number (e.g. 10000),
  "target_unit": null | string (e.g. "steps"),
  "recurrence_semantic_type": "measurable_goal|recurring_action|recurring_ritual|adherence_action|none",
  "confidence": 0.0}}

RULES:
- Only promote DURABLE, still-standing findings (not one-off chatter, not old
  events that already happened, not completed things).
- evidence_text MUST be a verbatim substring of the cited evidence packet.
- At most 2 candidates per question. At most 8 total. If evidence is thin,
  return fewer or none. Prefer precision over recall.
- Sophie promises: only EXPLICIT commitments she made ("I'll push you...", "I'll
  remind you..."). Do not infer promises from politeness.
{evidence}
"""


class SweeperService:
    """Async Lane 2 sweeper over Honcho history."""

    def __init__(self, honcho: Optional[HonchoClient] = None):
        self.honcho = honcho or HonchoClient(
            base_url=os.getenv("HONCHO_BASE_URL", "http://honcho-api:8000"),
            api_key=os.getenv("HONCHO_API_KEY", ""),
        )
        self.provider = LLMExtractorProvider()


    # -- evidence gathering ----------------------------------------------------

    async def gather(self, workspace_id: str, peer_id: str) -> List[Dict[str, Any]]:
        packets = []
        for key, question in QUESTIONS:
            hits = await self.honcho.peer_search(workspace_id, peer_id, question, limit=6)
            for hit in hits or []:
                if not hit.get("content"):
                    continue
                packets.append({
                    "id": hit["id"],
                    "question": key,
                    "session_id": hit.get("session_id"),
                    "created_at": hit.get("created_at"),
                    "content": str(hit["content"])[:800],
                    "role": (hit.get("metadata") or {}).get("app_role", ""),
                })
        return packets

    # -- synthesis + validation -------------------------------------------------

    def synthesize(self, packets: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        if not packets:
            return []
        evidence_block = "\n".join(
            f"[{p['id']}] ({p['question']} / {p['role'] or 'unknown'}) {p['content']}"
            for p in packets[:40]
        )
        prompt = _SYNTH_PROMPT.format(evidence=evidence_block)
        try:
            raw = self.provider._chat_json(prompt)
        except Exception as err:
            logger.warning("Sweeper synthesis failed: %s", err)
            return []
        pool = {p["id"]: p["content"] for p in packets}
        out = []
        for cand in (raw.get("candidates") or [])[:8]:
            if not isinstance(cand, dict):
                continue
            kind = str(cand.get("kind") or "").strip().lower()
            title = str(cand.get("title") or "").strip()
            ev_text = str(cand.get("evidence_text") or "").strip()
            ev_id = str(cand.get("evidence_id") or "").strip()
            try:
                conf = float(cand.get("confidence") or 0.0)
            except (TypeError, ValueError):
                conf = 0.0
            notes = []
            if kind not in PROMOTABLE_KINDS:
                notes.append(f"kind {kind!r} not promotable")
            if not title:
                notes.append("missing title")
            if ev_id not in pool:
                notes.append("evidence_id not in gathered evidence")
            elif _find_normalized(pool[ev_id], ev_text) is None:
                notes.append("evidence_text not verbatim in cited evidence")
            if conf < 0.6:
                notes.append("confidence below 0.6")
            out.append({
                "kind": kind, "title": title,
                "summary": str(cand.get("summary") or "").strip()[:500],
                "evidence_id": ev_id,
                "evidence_text": ev_text[:1000],
                "evidence_session_id": next(
                    (p["session_id"] for p in packets if p["id"] == ev_id), None),
                "cadence": str(cand.get("cadence") or "none").strip().lower(),
                "target_amount": cand.get("target_amount"),
                "target_unit": str(cand.get("target_unit") or "") or None,
                "recurrence_semantic_type": str(cand.get("recurrence_semantic_type") or "none").strip().lower(),
                "confidence": conf,
                "valid": not notes, "validation_notes": notes,
            })
        return out

    # -- deterministic promotion (same persistence as Lane 1) -------------------

    async def promote(
        self, db: AsyncSession, *, workspace_id: str, peer_id: str,
        candidates: List[Dict[str, Any]], now: datetime,
    ) -> Dict[str, List[Any]]:
        created: Dict[str, List[Any]] = {"expectations": [], "rejected": []}
        for c in candidates:
            if not c["valid"]:
                created["rejected"].append({"title": c["title"], "notes": c["validation_notes"]})
                continue
            try:
                await self._promote_one(db, workspace_id=workspace_id, peer_id=peer_id, c=c, now=now, created=created)
                await db.commit()
            except Exception as err:
                await db.rollback()
                logger.warning("Sweeper promotion failed for %r: %s", c["title"], err)
                created["rejected"].append({"title": c["title"], "notes": [f"promotion_failed: {str(err)[:200]}"]})
        return created

    async def _promote_one(self, db, *, workspace_id, peer_id, c, now, created):
        if c["kind"] in ("goal", "strategy"):
            # Goals/strategies with cadence evidence become recurring
            # intentions through the existing deterministic upsert (which
            # also creates occurrences and the admission projection).
            from src.schemas.candidate import ExtractionCandidate
            from src.services.operational_state_service import OperationalStateService
            if c.get("cadence") in ("daily", "weekly", "interval") and c["confidence"] >= 0.65:
                cand = ExtractionCandidate(
                    candidate_key=f"sweep:{c['kind']}:{c['title'][:80]}",
                    observation=c["title"],
                    operational_kind="recurring_intention",
                    canonical_title=c["title"],
                    cadence=c["cadence"],
                    recurrence_semantic_type=(
                        c.get("recurrence_semantic_type") or "measurable_goal"
                    ),
                    target_amount=(
                        float(c["target_amount"]) if c.get("target_amount") else None
                    ),
                    target_unit=c.get("target_unit"),
                    confidence=c["confidence"],
                    extractor_version=SWEEPER_VERSION,
                    raw_evidence=c["evidence_text"],
                )
                svc = OperationalStateService()
                result = await svc._upsert_recurrence(
                    db, workspace_id, c.get("evidence_session_id") or "",
                    c["evidence_id"], peer_id, cand, now, "UTC",
                )
                created.setdefault("recurrences", []).append(
                    {"title": c["title"], "result": result}
                )
                return
        if c["kind"] in ("goal", "strategy", "sophie_promise", "blocker"):
            record = {
                "honcho_workspace_id": workspace_id,
                "honcho_session_id": c.get("evidence_session_id"),
                "honcho_message_id": c["evidence_id"],
                "owner_peer_id": peer_id,
                "candidate_key": f"sweep:{c['kind']}:{c['title'][:80]}",
                "extractor_version": SWEEPER_VERSION,
                "source_start": None, "source_end": None,
                "subject_peer_id": peer_id,
                "expectation_type": "USER_INTENTION",
                "title": c["title"][:200],
                "summary": (c.get("summary") or c["evidence_text"])[:1000],
                "raw_temporal_phrase": None,
                "anchor_timezone": "UTC",
                "expected_window_start": None,
                "expected_window_end": None,
                "hard_deadline_at": None,
                "extraction_confidence": c["confidence"],
                "reminder_requested": False,
            }
            exp_model, was_created = await save_expectation_idempotent(
                db, record, grounding_now=now,
            )
            if was_created:
                created["expectations"].append(str(exp_model.id))
        elif c["kind"] == "open_loop":
            from src.schemas.candidate import ExtractionCandidate
            from src.services.lifecycle_service import LifecycleService
            import uuid as _uuid
            cand = ExtractionCandidate(
                candidate_key=f"sweep-openloop-{_uuid.uuid4().hex[:8]}",
                observation=c["title"],
                operational_kind="open_loop",
                open_loop_hint=c["title"],
                canonical_title=c["title"],
                confidence=c["confidence"],
                extractor_version=SWEEPER_VERSION,
                raw_evidence=c["evidence_text"],
            )
            svc = LifecycleService()
            await svc.create_open_loop_if_needed(
                db, workspace_id=workspace_id,
                session_id=c.get("evidence_session_id"),
                message_id=c["evidence_id"], candidate=cand,
                owner_peer_id=peer_id, now=now, timezone_str="UTC",
            )

    async def run(
        self, db: AsyncSession, *, workspace_id: str, peer_id: str,
        session_id: str = "", now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        now = now or datetime.utcnow()
        started = time.perf_counter()
        packets = await self.gather(workspace_id, peer_id)
        candidates = self.synthesize(packets)
        promoted = await self.promote(
            db, workspace_id=workspace_id, peer_id=peer_id,
            candidates=candidates, now=now,
        )
        return {
            "status": "ok",
            "evidence_packets": len(packets),
            "candidates": candidates,
            "promoted": promoted,
            "latency_seconds": round(time.perf_counter() - started, 2),
            "sweeper_version": SWEEPER_VERSION,
        }

