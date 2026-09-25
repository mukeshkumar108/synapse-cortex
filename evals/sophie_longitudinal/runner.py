from __future__ import annotations

import logging
logging.getLogger("src.clients.honcho_client").setLevel(logging.ERROR)
logging.getLogger("src.services.sweeper_service").setLevel(logging.ERROR)

import argparse
import asyncio
import json
import os
import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Ensure synapse-cortex root is on sys.path
CORTEX_ROOT = Path(__file__).resolve().parents[2]
if str(CORTEX_ROOT) not in sys.path:
    sys.path.insert(0, str(CORTEX_ROOT))

# Set default test database before importing SQLAlchemy/FastAPI modules
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:////tmp/sophie_eval_default.db")

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from src.config import settings
import src.db
from src.main import app
from src.models.attention_candidate import AttentionCandidate
from src.models.clarification import ClarificationCandidate
from src.models.commitment_candidate import CommitmentCandidate
from src.models.current_meaning import CurrentMeaning
from src.models.epistemic import EpistemicAnnotation
from src.models.expectation import Expectation
from src.models.fact import Fact
from src.models.identity import Entity, EntityAlias, EntityLink, ModelEntry, TurnFrame
from src.models.open_loop import OpenLoop
from src.models.suppression import Suppression
from src.routers import v1_cortex

# Disable external agenda adapter mock to avoid connection errors
# Disable external agenda adapter mock to avoid connection errors
v1_cortex.get_agenda_adapter = lambda: None
if 'wa-api.skillstap.com' not in settings.HONCHO_BASE_URL:
    settings.HONCHO_CONTEXT_ENABLED = False


SCRIPT_DIR = Path(__file__).parent
RAW_OUTPUTS_DIR = SCRIPT_DIR / "raw_outputs"
RAW_OUTPUTS_DIR.mkdir(exist_ok=True)


class SophieScenarioRunner:
    def __init__(
        self,
        scenario_id: str,
        provider: str = "rules",
        db_path: Optional[str] = None,
        workspace_prefix: str = "sophie-bench",
    ):
        self.scenario_id = scenario_id
        self.provider = provider
        self.workspace_id = f"{workspace_prefix}-{scenario_id}"
        self.session_id = f"session-{scenario_id}"
        self.db_path = db_path or f"/tmp/sophie_eval_{scenario_id}.db"
        self.input_file = SCRIPT_DIR / f"{scenario_id}_input.json"
        if not self.input_file.exists():
            matches = list(SCRIPT_DIR.glob(f"{scenario_id}_*_input.json"))
            if matches:
                self.input_file = matches[0]

        self.oracle_file = SCRIPT_DIR / f"{scenario_id}_oracle.json"
        if not self.oracle_file.exists():
            matches = list(SCRIPT_DIR.glob(f"{scenario_id}_*_oracle.json"))
            if matches:
                self.oracle_file = matches[0]

        self.prev_state: Dict[str, Set[str]] = {
            "exp": set(),
            "loop": set(),
            "comm": set(),
            "fact": set(),
        }
        self.checkpoint_logs: List[str] = []
        self.evaluation_results: Dict[str, Any] = {
            "scenario_id": scenario_id,
            "provider": provider,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "checkpoints": [],
            "trap_evaluations": [],
            "summary": {},
        }

    async def init_db(self):
        try:
            if os.path.exists(self.db_path):
                os.remove(self.db_path)
        except OSError:
            pass

        # Rebind settings and src.db engine to the scenario-isolated SQLite DB
        settings.DATABASE_URL = f"sqlite+aiosqlite:///{self.db_path}"
        os.environ["DATABASE_URL"] = settings.DATABASE_URL
        os.environ["SYNAPSE_EXTRACTOR_PROVIDER"] = self.provider

        src.db.engine = create_async_engine(settings.DATABASE_URL)
        src.db.async_session_maker = sessionmaker(
            src.db.engine, class_=AsyncSession, expire_on_commit=False
        )

        async with src.db.engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)

    async def dump_checkpoint_state(
        self,
        db,
        event_id: str,
        checkpoint_label: str,
        recent_events: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        ws = self.workspace_id
        exp = (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == ws))).scalars().all()
        loops = (await db.execute(select(OpenLoop).where(OpenLoop.honcho_workspace_id == ws))).scalars().all()
        comms = (await db.execute(select(CommitmentCandidate).where(CommitmentCandidate.honcho_workspace_id == ws))).scalars().all()
        meanings = (await db.execute(select(CurrentMeaning))).scalars().all()
        attn = (await db.execute(select(AttentionCandidate).where(AttentionCandidate.honcho_workspace_id == ws))).scalars().all()
        supp = (await db.execute(select(Suppression).where(Suppression.honcho_workspace_id == ws))).scalars().all()
        clar = (await db.execute(select(ClarificationCandidate).where(ClarificationCandidate.honcho_workspace_id == ws))).scalars().all()
        epis = (await db.execute(select(EpistemicAnnotation).where(EpistemicAnnotation.honcho_workspace_id == ws))).scalars().all()
        facts = (await db.execute(select(Fact).where(Fact.honcho_workspace_id == ws))).scalars().all()
        entities = (await db.execute(select(Entity).where(Entity.honcho_workspace_id == ws))).scalars().all()
        eids = {e.id for e in entities}
        aliases = [a for a in (await db.execute(select(EntityAlias))).scalars().all() if a.entity_id in eids]
        models = (await db.execute(select(ModelEntry).where(ModelEntry.honcho_workspace_id == ws))).scalars().all()
        links = [l for l in (await db.execute(select(EntityLink))).scalars().all() if l.honcho_workspace_id == ws]
        frames = (await db.execute(select(TurnFrame).where(TurnFrame.honcho_workspace_id == ws))).scalars().all()

        log: List[str] = []
        log.append(f"\n\n# CHECKPOINT: after event {event_id} ({checkpoint_label})\n")
        log.append("## TURNS SINCE LAST CHECKPOINT (verbatim, trimmed to 400 chars)")
        for ev in recent_events:
            log.append(f"- event {ev['id']} [{ev.get('source_type')}] {ev.get('sender')} [{ev.get('timestamp')}]: {ev.get('content', '')[:400]!r}")

        log.append(f"## ACTIVE EXPECTATIONS ({len(exp)})")
        for e in exp:
            log.append(f"- id={e.id} type={e.expectation_type} state={e.outcome_state} title={e.title!r} "
                       f"summary={str(e.summary)[:200]!r} src_system={e.source_system} evidence={e.resolution_evidence!r}")

        log.append(f"## COMMITMENTS ({len(comms)})")
        for c in comms:
            log.append(f"- id={c.id} status={c.status} authority={c.authority} title={c.title!r} "
                       f"class={c.evidence_class} msg={c.source_message_id} verbatim={str(c.evidence_verbatim)[:200]!r}")

        # Stored ASK vs surfaced shelf diagnostic
        def _is_ask(c):
            return getattr(getattr(c, "authority", None), "value", c.authority) == "ask"

        ask_rows = sorted(
            [c for c in comms if _is_ask(c)],
            key=lambda c: c.created_at,
            reverse=True,
        )
        shelf, skipped = [], []
        for i, c in enumerate(ask_rows):
            if c.evidence_class == "vague_self_talk":
                skipped.append(f"- {c.title!r} msg={c.source_message_id} reason=vague_self_talk_excluded")
            elif i < 6 and len(shelf) < 3:
                shelf.append(f"- {c.title!r} class={c.evidence_class} msg={c.source_message_id}")
            else:
                skipped.append(f"- {c.title!r} msg={c.source_message_id} reason=beyond_top3_window")

        log.append(f"## PROPOSAL EXPOSURE (stored ASK vs Sophie-noticed shelf)")
        log.append(f"stored_ask={len(ask_rows)}")
        log.append("surfaced_shelf:")
        log.extend(shelf or ["- (empty)"])
        log.append("skipped:")
        log.extend(skipped[:12] or ["- (none)"])
        if len(skipped) > 12:
            log.append(f"- ... plus {len(skipped) - 12} more skipped")

        log.append(f"## OPEN LOOPS ({len(loops)})")
        for o in loops:
            log.append(f"- id={o.id} status={o.status} title={o.title!r} summary={str(o.summary)[:200]!r} msg={o.honcho_message_id}")

        log.append(f"## CURRENT MEANING ({len(meanings)} rows)")
        for m in meanings:
            log.append(f"- scope={m.scope_key} rev={m.revision} text={str(m.meaning_text)[:400]!r}")

        log.append("## ATTENTION (active / suppressed)")
        for a in attn:
            log.append(f"- id={a.id} status={a.status} content={str(a.content)[:160]!r}")
        if not attn:
            log.append(f"- none active; suppressions={len(supp)}")
        for s in supp:
            log.append(f"- SUPPRESSED target={s.target_type} topic={s.topic_or_entity!r} reason={s.reason!r}")

        log.append(f"## CLARIFICATIONS ({len(clar)})")
        for c in clar:
            log.append(f"- id={c.id} status={c.status} desc={str(c.description)[:200]!r} msg={c.honcho_message_id}")

        log.append(f"## EPISTEMIC ANNOTATIONS ({len(epis)})")
        for ep in epis:
            log.append(f"- msg={ep.honcho_message_id} claim={ep.claim_summary!r} conf={ep.confidence}")

        log.append(f"## FACTS ({len(facts)})")
        for f in facts:
            log.append(f"- id={f.id} owner={f.owner_peer_id} cat={f.category} title={f.title!r} "
                       f"formation={f.formation} msg={f.honcho_message_id}")

        log.append(f"## ENTITIES ({len(entities)})")
        alias_by_e = {}
        for a in aliases:
            alias_by_e.setdefault(str(a.entity_id), []).append(a.alias)
        for e in entities:
            log.append(f"- id={e.id} name={e.display_name!r} type={e.entity_type} frame={e.frame_scope} "
                       f"prov={e.provisional} aliases={alias_by_e.get(str(e.id), [])} msg={e.first_seen_message_id}")

        log.append(f"## MODEL ENTRIES ({len(models)})")
        for me in models:
            log.append(f"- id={me.id} kind={me.model_kind} owner={me.owner_peer_id} claim={me.claim[:160]!r} "
                       f"formation={me.formation} msg={me.honcho_message_id}")

        log.append(f"## ENTITY LINKS ({len(links)})")
        for l in links[:40]:
            log.append(f"- {l.object_type}:{str(l.object_id)[:8]} --{l.role}--> {str(l.entity_id)[:8]} conf={l.confidence}")

        log.append(f"## TURN FRAMES ({len(frames)}): {dict(Counter(f.frame for f in frames))}")

        new_exp = sorted({str(e.id) for e in exp} - self.prev_state["exp"])
        new_loop = sorted({str(o.id) for o in loops} - self.prev_state["loop"])
        new_comm = sorted({str(c.id) for c in comms} - self.prev_state["comm"])
        new_fact = sorted({str(f.id) for f in facts} - self.prev_state["fact"])
        log.append(f"## WHAT CHANGED SINCE LAST CHECKPOINT\n- +expectations={new_exp} +loops={new_loop} +commitments={new_comm} +facts={new_fact}")

        self.prev_state["exp"] = {str(e.id) for e in exp}
        self.prev_state["loop"] = {str(o.id) for o in loops}
        self.prev_state["comm"] = {str(c.id) for c in comms}
        self.prev_state["fact"] = {str(f.id) for f in facts}

        self.checkpoint_logs.extend(log)

        return {
            "event_id": event_id,
            "label": checkpoint_label,
            "counts": {
                "expectations": len(exp),
                "commitments": len(comms),
                "stored_ask": len(ask_rows),
                "surfaced_shelf": len(shelf),
                "open_loops": len(loops),
                "current_meaning": len(meanings),
                "attention_candidates": len(attn),
                "suppressions": len(supp),
                "clarifications": len(clar),
                "facts": len(facts),
                "entities": len(entities),
                "models": len(models),
            },
            "expectations": [
                {
                    "id": str(e.id),
                    "type": str(e.expectation_type),
                    "state": str(e.outcome_state),
                    "title": e.title,
                    "summary": e.summary,
                    "source_system": e.source_system,
                }
                for e in exp
            ],
            "commitments": [
                {
                    "id": str(c.id),
                    "status": str(c.status),
                    "authority": str(c.authority),
                    "title": c.title,
                    "class": c.evidence_class,
                }
                for c in comms
            ],
            "open_loops": [
                {
                    "id": str(o.id),
                    "status": str(o.status),
                    "title": o.title,
                }
                for o in loops
            ],
            "entities": [
                {
                    "id": str(e.id),
                    "name": e.display_name,
                    "type": e.entity_type,
                    "aliases": alias_by_e.get(str(e.id), []),
                }
                for e in entities
            ],
        }

    async def run(self) -> Dict[str, Any]:
        await self.init_db()
        input_data = json.loads(self.input_file.read_text())
        events = input_data.get("events", [])

        # Load oracle strictly for evaluator logic (not injected into test system)
        oracle_data = json.loads(self.oracle_file.read_text())
        oracle_cps = {
            cp["after_event_id"]: cp for cp in oracle_data.get("expected_checkpoints", [])
        }

        self.checkpoint_logs.append(f"# LIVE Replay: {input_data.get('title')}")
        self.checkpoint_logs.append(
            f"Workspace={self.workspace_id} Session={self.session_id} Provider={self.provider} Timezone={input_data.get('timezone')}"
        )

        transport = ASGITransport(app=app)
        last_cp_idx = 0
        t0 = time.time()

        async with AsyncClient(transport=transport, base_url="http://test") as client:
            for idx, ev in enumerate(events):
                source_type = ev.get("source_type")
                role = ev.get("role")
                sender = ev.get("sender")
                now_str = ev.get("timestamp")
                tz = input_data.get("timezone", "Europe/London")

                # Ingestion routing by source type
                if source_type == "calendar":
                    meta = ev.get("metadata", {})
                    payload = {
                        "workspace_id": self.workspace_id,
                        "session_id": self.session_id,
                        "owner_peer_id": input_data.get("user_peer_id", "user"),
                        "now": now_str,
                        "timezone": tz,
                        "title": meta.get("title", ev.get("content", "Calendar Event")),
                        "action": meta.get("action", "updated"),
                        "source": {
                            "system": meta.get("system", "google_calendar"),
                            "object_id": meta.get("object_id", f"cal-evt-{ev['id']}"),
                            "version": meta.get("version", 1),
                            "kind": "calendar_event",
                        },
                    }
                    if "scheduled_start" in meta:
                        payload["event_start"] = meta["scheduled_start"]
                    if "scheduled_end" in meta:
                        payload["event_end"] = meta["scheduled_end"]

                    res = await client.post("/v1/events/object", json=payload, timeout=60.0)
                    print(f"[{ev['id']}] CALENDAR -> status={res.status_code} action={res.json().get('action_taken')}")

                elif source_type == "conversation":
                    is_assistant = (role == "assistant")
                    peer_id = input_data.get("companion_peer_id", "sophie") if is_assistant else input_data.get("user_peer_id", "user")
                    payload = {
                        "workspace_id": self.workspace_id,
                        "session_id": self.session_id,
                        "honcho_message_id": f"msg-{ev['id']}",
                        "peer_id": peer_id,
                        "text": ev.get("content", ""),
                        "now": now_str,
                        "timezone": tz,
                        "is_assistant_turn": is_assistant,
                    }
                    res = await client.post("/v1/events/turn", json=payload, timeout=120.0)
                    print(f"[{ev['id']}] CONVERSATION ({'ASSISTANT' if is_assistant else 'USER'}) -> status={res.status_code}")

                else:
                    # Bounded test adapter for non-chat evidence (email, payment_feed, sms, message):
                    # Ingests turn with explicit external peer identity so provenance is preserved
                    peer_id = f"external:{sender}"
                    payload = {
                        "workspace_id": self.workspace_id,
                        "session_id": self.session_id,
                        "honcho_message_id": f"external-{source_type}-{ev['id']}",
                        "peer_id": peer_id,
                        "text": ev.get("content", ""),
                        "now": now_str,
                        "timezone": tz,
                        "is_assistant_turn": False,
                    }
                    res = await client.post("/v1/events/turn", json=payload, timeout=120.0)
                    print(f"[{ev['id']}] EXTERNAL ({source_type}:{sender}) -> status={res.status_code}")

                # Checkpoint trigger
                if ev["id"] in oracle_cps:
                    cp_spec = oracle_cps[ev["id"]]
                    recent = events[last_cp_idx : idx + 1]
                    last_cp_idx = idx + 1

                    async with src.db.async_session_maker() as db:
                        cp_state = await self.dump_checkpoint_state(
                            db, ev["id"], cp_spec.get("label", ""), recent
                        )
                        cp_state["deterministic_expectations"] = cp_spec.get("deterministic_assertions", {})
                        self.evaluation_results["checkpoints"].append(cp_state)

        # Write raw checkpoint output
        raw_out_path = RAW_OUTPUTS_DIR / f"{self.scenario_id}_raw_checkpoints.md"
        raw_out_path.write_text("\n".join(self.checkpoint_logs))
        print(f"Wrote raw checkpoint output: {raw_out_path} (elapsed {time.time()-t0:.1f}s)")

        # Evaluate traps against final DB state
        async with src.db.async_session_maker() as db:
            traps = oracle_data.get("false_positive_traps", [])
            for trap in traps:
                trigger = trap.get("trigger_text", "").lower()
                prohibited = trap.get("prohibited_persistence", [])
                trap_result = {
                    "trigger_text": trap.get("trigger_text"),
                    "prohibited": prohibited,
                    "passed": True,
                    "violations_found": [],
                }
                # Check for leaks into durable tables
                comms = (await db.execute(select(CommitmentCandidate))).scalars().all()
                for c in comms:
                    if trigger in (c.title or "").lower() or trigger in (c.evidence_verbatim or "").lower():
                        if "actionable_commitment" in prohibited and getattr(c.authority, "value", c.authority) == "act":
                            trap_result["passed"] = False
                            trap_result["violations_found"].append(f"Actionable commitment minted: {c.title}")

                loops = (await db.execute(select(OpenLoop))).scalars().all()
                for lp in loops:
                    if trigger in (lp.title or "").lower() or trigger in (lp.summary or "").lower():
                        if "open_loop" in prohibited and lp.status.value == "OPEN":
                            trap_result["passed"] = False
                            trap_result["violations_found"].append(f"Open loop minted: {lp.title}")

                self.evaluation_results["trap_evaluations"].append(trap_result)

        # Write summary JSON
        summary_out_path = RAW_OUTPUTS_DIR / f"{self.scenario_id}_summary.json"
        self.evaluation_results["summary"] = {
            "total_checkpoints": len(self.evaluation_results["checkpoints"]),
            "traps_evaluated": len(self.evaluation_results["trap_evaluations"]),
            "traps_passed": sum(1 for t in self.evaluation_results["trap_evaluations"] if t["passed"]),
        }
        summary_out_path.write_text(json.dumps(self.evaluation_results, indent=2))
        return self.evaluation_results


def parse_args():
    parser = argparse.ArgumentParser(description="Run Sophie Longitudinal Benchmarks")
    parser.add_argument(
        "--scenario",
        default="all",
        choices=["all", "scenario_1", "scenario_2", "scenario_3", "scenario_4"],
        help="Scenario ID to execute",
    )
    parser.add_argument(
        "--provider",
        default=os.environ.get("SYNAPSE_EXTRACTOR_PROVIDER", "rules"),
        choices=["rules", "model"],
        help="Extractor provider (rules or model)",
    )
    return parser.parse_args()


async def main_async():
    args = parse_args()
    scenarios = (
        ["scenario_1", "scenario_2", "scenario_3", "scenario_4"]
        if args.scenario == "all"
        else [args.scenario]
    )

    print(f"=== Starting Sophie Longitudinal Benchmark ({len(scenarios)} scenarios) ===")
    print(f"Provider: {args.provider}")

    results = []
    for sc in scenarios:
        print(f"\n==========================================")
        print(f"Executing {sc}...")
        print(f"==========================================")
        runner = SophieScenarioRunner(scenario_id=sc, provider=args.provider)
        res = await runner.run()
        results.append(res)

    print("\n\n=== BENCHMARK EXECUTION SUMMARY ===")
    for r in results:
        sc_id = r["scenario_id"]
        cps = r["summary"].get("total_checkpoints", 0)
        t_pass = r["summary"].get("traps_passed", 0)
        t_tot = r["summary"].get("traps_evaluated", 0)
        print(f"{sc_id}: {cps} checkpoints evaluated | False-positive trap defense: {t_pass}/{t_tot} passed")


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
