from __future__ import annotations

import logging
logging.getLogger("src.clients.honcho_client").setLevel(logging.ERROR)
logging.getLogger("src.services.sweeper_service").setLevel(logging.ERROR)

import argparse
import asyncio
import json
import os
import re
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

# Load local .env if present (populates OPENROUTER_API_KEY, SYNAPSE_EXTRACTOR_MODEL, etc.)
try:
    import dotenv
    dotenv.load_dotenv(CORTEX_ROOT / ".env")
except ImportError:
    pass

# Configure adequate token and timeout budgets for messy longitudinal extraction
os.environ.setdefault("SYNAPSE_EXTRACTOR_MAX_TOKENS", "3500")
os.environ.setdefault("SYNAPSE_EXTRACTOR_TIMEOUT_SECONDS", "30")

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
import src.routers.v1_events as v1_events
from src.services.turn_extractor import (
    LLMExtractorProvider,
    RuleBasedExtractorProvider,
    TurnExtractor,
)

# Disable external agenda adapter mock to avoid connection errors
v1_cortex.get_agenda_adapter = lambda: None
if "wa-api.skillstap.com" not in settings.HONCHO_BASE_URL:
    settings.HONCHO_CONTEXT_ENABLED = False


SCRIPT_DIR = Path(__file__).parent
RAW_OUTPUTS_BASE = SCRIPT_DIR / "raw_outputs"


def preflight_check(mode: str) -> Dict[str, Any]:
    """Preflight assertion for execution mode.

    - Rules mode: remains strictly offline and deterministic.
    - Model mode: verifies presence of real credentials, executes an active probe call,
      and fails loudly with non-zero exit code if credentials or connectivity fail.
      Never silently falls back to rules.
    """
    if mode == "rules":
        print("[PREFLIGHT] Mode: rules (determinism floor / illicit-state regression baseline).")
        print("[PREFLIGHT] Offline mode confirmed. No external API calls will be made.")
        return {
            "mode": "rules",
            "provider": "rules",
            "model": None,
            "external_model_calls": False,
        }

    if mode == "model":
        key = (
            os.getenv("OPENROUTER_API_KEY")
            or os.getenv("OPENAI_API_KEY")
            or os.getenv("XAI_API_KEY")
        )
        if not key:
            sys.stderr.write(
                "\n"
                "================================================================================\n"
                "PREFLIGHT ERROR: Model/semantic mode requested, but no API credentials found.\n"
                "Looked for OPENROUTER_API_KEY, OPENAI_API_KEY, or XAI_API_KEY in environment or .env.\n"
                "Model baseline must fail loudly rather than silently downgrading to rules.\n"
                "================================================================================\n\n"
            )
            sys.exit(1)

        probe_provider = LLMExtractorProvider(fallback_on_error=False)
        print(
            f"[PREFLIGHT] Testing model connectivity for model='{probe_provider.model}' "
            f"via {probe_provider.api_url}..."
        )
        try:
            probe_res = probe_provider._call_model(
                probe_provider.model, '{"preflight_probe": true}'
            )
            if not isinstance(probe_res, dict):
                raise ValueError(f"Malformed probe response: {probe_res}")
        except Exception as err:
            sys.stderr.write(
                "\n"
                "================================================================================\n"
                f"PREFLIGHT ERROR: Model connectivity test failed for model '{probe_provider.model}':\n"
                f"Detail: {err}\n"
                "Model baseline must fail loudly rather than silently downgrading to rules.\n"
                "================================================================================\n\n"
            )
            sys.exit(1)

        print(
            f"[PREFLIGHT] Model connectivity verified. Provider=model Model={probe_provider.model}"
        )
        return {
            "mode": "model",
            "provider": "model",
            "model": probe_provider.model,
            "external_model_calls": True,
        }

    sys.stderr.write(f"PREFLIGHT ERROR: Unrecognized mode '{mode}'\n")
    sys.exit(1)


class SophieScenarioRunner:
    def __init__(
        self,
        scenario_id: str,
        mode: str = "rules",
        db_path: Optional[str] = None,
        workspace_prefix: str = "sophie-bench",
    ):
        self.scenario_id = scenario_id
        self.mode = mode
        self.workspace_id = f"{workspace_prefix}-{mode}-{scenario_id}"
        self.session_id = f"session-{mode}-{scenario_id}"
        self.db_path = db_path or f"/tmp/sophie_eval_{mode}_{scenario_id}.db"
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
        self.provider_instance = None
        self.provider_name = "rules" if mode == "rules" else "model"
        self.model_name = None
        self.external_model_calls = (mode == "model")
        self.output_dir = RAW_OUTPUTS_BASE / self.mode
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.evaluation_results: Dict[str, Any] = {
            "scenario_id": scenario_id,
            "mode": mode,
            "baseline_type": (
                "determinism_floor" if mode == "rules" else "semantic_baseline"
            ),
            "provider": self.provider_name,
            "model": None,
            "external_model_calls": self.external_model_calls,
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

        if self.mode == "rules":
            os.environ["SYNAPSE_EXTRACTOR_PROVIDER"] = "rules"
            rule_prov = RuleBasedExtractorProvider()
            v1_events.turn_extractor = TurnExtractor(provider=rule_prov)
            self.provider_instance = rule_prov
            self.provider_name = "rules"
            self.model_name = None
            self.external_model_calls = False
        elif self.mode == "model":
            os.environ["SYNAPSE_EXTRACTOR_PROVIDER"] = "model"
            llm_prov = LLMExtractorProvider(fallback_on_error=False)
            v1_events.turn_extractor = TurnExtractor(provider=llm_prov)
            self.provider_instance = llm_prov
            self.provider_name = "model"
            self.model_name = llm_prov.model
            self.external_model_calls = True

        self.evaluation_results["provider"] = self.provider_name
        self.evaluation_results["model"] = self.model_name

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
        exp = (
            (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )
        loops = (
            (await db.execute(select(OpenLoop).where(OpenLoop.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )
        comms = (
            (await db.execute(
                select(CommitmentCandidate).where(CommitmentCandidate.honcho_workspace_id == ws)
            ))
            .scalars()
            .all()
        )
        meanings = (await db.execute(select(CurrentMeaning))).scalars().all()
        attn = (
            (await db.execute(
                select(AttentionCandidate).where(AttentionCandidate.honcho_workspace_id == ws)
            ))
            .scalars()
            .all()
        )
        supp = (
            (await db.execute(select(Suppression).where(Suppression.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )
        clar = (
            (await db.execute(
                select(ClarificationCandidate).where(ClarificationCandidate.honcho_workspace_id == ws)
            ))
            .scalars()
            .all()
        )
        epis = (
            (await db.execute(
                select(EpistemicAnnotation).where(EpistemicAnnotation.honcho_workspace_id == ws)
            ))
            .scalars()
            .all()
        )
        facts = (
            (await db.execute(select(Fact).where(Fact.honcho_workspace_id == ws))).scalars().all()
        )
        entities = (
            (await db.execute(select(Entity).where(Entity.honcho_workspace_id == ws))).scalars().all()
        )
        eids = {e.id for e in entities}
        aliases = [
            a
            for a in (await db.execute(select(EntityAlias))).scalars().all()
            if a.entity_id in eids
        ]
        models = (
            (await db.execute(select(ModelEntry).where(ModelEntry.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )
        links = [
            l
            for l in (await db.execute(select(EntityLink))).scalars().all()
            if l.honcho_workspace_id == ws
        ]
        frames = (
            (await db.execute(select(TurnFrame).where(TurnFrame.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )

        log: List[str] = []
        log.append(f"\n\n# CHECKPOINT: after event {event_id} ({checkpoint_label})\n")
        log.append("## TURNS SINCE LAST CHECKPOINT (verbatim, trimmed to 400 chars)")
        for ev in recent_events:
            log.append(
                f"- event {ev['id']} [{ev.get('source_type')}] {ev.get('sender')} [{ev.get('timestamp')}]: {ev.get('content', '')[:400]!r}"
            )

        log.append(f"## ACTIVE EXPECTATIONS ({len(exp)})")
        for e in exp:
            log.append(
                f"- id={e.id} type={e.expectation_type} state={e.outcome_state} title={e.title!r} "
                f"summary={str(e.summary)[:200]!r} src_system={e.source_system} evidence={e.resolution_evidence!r}"
            )

        log.append(f"## COMMITMENTS ({len(comms)})")
        for c in comms:
            log.append(
                f"- id={c.id} status={c.status} authority={c.authority} title={c.title!r} "
                f"class={c.evidence_class} msg={c.source_message_id} verbatim={str(c.evidence_verbatim)[:200]!r}"
            )

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
                skipped.append(
                    f"- {c.title!r} msg={c.source_message_id} reason=vague_self_talk_excluded"
                )
            elif i < 6 and len(shelf) < 3:
                shelf.append(f"- {c.title!r} class={c.evidence_class} msg={c.source_message_id}")
            else:
                skipped.append(f"- {c.title!r} msg={c.source_message_id} reason=beyond_top3_window")

        log.append("## PROPOSAL EXPOSURE (stored ASK vs Sophie-noticed shelf)")
        log.append(f"stored_ask={len(ask_rows)}")
        log.append("surfaced_shelf:")
        log.extend(shelf or ["- (empty)"])
        log.append("skipped:")
        log.extend(skipped[:12] or ["- (none)"])
        if len(skipped) > 12:
            log.append(f"- ... plus {len(skipped) - 12} more skipped")

        log.append(f"## OPEN LOOPS ({len(loops)})")
        for o in loops:
            log.append(
                f"- id={o.id} status={o.status} title={o.title!r} summary={str(o.summary)[:200]!r} msg={o.honcho_message_id}"
            )

        log.append(f"## CURRENT MEANING ({len(meanings)} rows)")
        for m in meanings:
            log.append(f"- scope={m.scope_key} rev={m.revision} text={str(m.meaning_text)[:400]!r}")

        log.append("## ATTENTION (active / suppressed)")
        for a in attn:
            log.append(f"- id={a.id} status={a.status} content={str(a.content)[:160]!r}")
        if not attn:
            log.append(f"- none active; suppressions={len(supp)}")
        for s in supp:
            log.append(
                f"- SUPPRESSED target={s.target_type} topic={s.topic_or_entity!r} reason={s.reason!r}"
            )

        log.append(f"## CLARIFICATIONS ({len(clar)})")
        for c in clar:
            log.append(
                f"- id={c.id} status={c.status} desc={str(c.description)[:200]!r} msg={c.honcho_message_id}"
            )

        log.append(f"## EPISTEMIC ANNOTATIONS ({len(epis)})")
        for ep in epis:
            log.append(f"- msg={ep.honcho_message_id} claim={ep.claim_summary!r} conf={ep.confidence}")

        log.append(f"## FACTS ({len(facts)})")
        for f in facts:
            log.append(
                f"- id={f.id} owner={f.owner_peer_id} cat={f.category} title={f.title!r} "
                f"formation={f.formation} msg={f.honcho_message_id}"
            )

        log.append(f"## ENTITIES ({len(entities)})")
        alias_by_e = {}
        for a in aliases:
            alias_by_e.setdefault(str(a.entity_id), []).append(a.alias)
        for e in entities:
            log.append(
                f"- id={e.id} name={e.display_name!r} type={e.entity_type} frame={e.frame_scope} "
                f"prov={e.provisional} aliases={alias_by_e.get(str(e.id), [])} msg={e.first_seen_message_id}"
            )

        log.append(f"## MODEL ENTRIES ({len(models)})")
        for me in models:
            log.append(
                f"- id={me.id} kind={me.model_kind} owner={me.owner_peer_id} claim={me.claim[:160]!r} "
                f"formation={me.formation} msg={me.honcho_message_id}"
            )

        log.append(f"## ENTITY LINKS ({len(links)})")
        for l in links[:40]:
            log.append(
                f"- {l.object_type}:{str(l.object_id)[:8]} --{l.role}--> {str(l.entity_id)[:8]} conf={l.confidence}"
            )

        log.append(
            f"## TURN FRAMES ({len(frames)}): {dict(Counter(f.frame for f in frames))}"
        )

        new_exp = sorted({str(e.id) for e in exp} - self.prev_state["exp"])
        new_loop = sorted({str(o.id) for o in loops} - self.prev_state["loop"])
        new_comm = sorted({str(c.id) for c in comms} - self.prev_state["comm"])
        new_fact = sorted({str(f.id) for f in facts} - self.prev_state["fact"])
        log.append(
            f"## WHAT CHANGED SINCE LAST CHECKPOINT\n"
            f"- +expectations={new_exp} +loops={new_loop} +commitments={new_comm} +facts={new_fact}"
        )

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

    async def evaluate_traps(self, db, traps: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        ws = self.workspace_id
        comms = (
            (await db.execute(
                select(CommitmentCandidate).where(CommitmentCandidate.honcho_workspace_id == ws)
            ))
            .scalars()
            .all()
        )
        loops = (
            (await db.execute(select(OpenLoop).where(OpenLoop.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )
        facts = (
            (await db.execute(select(Fact).where(Fact.honcho_workspace_id == ws))).scalars().all()
        )
        exp = (
            (await db.execute(select(Expectation).where(Expectation.honcho_workspace_id == ws)))
            .scalars()
            .all()
        )

        results = []
        for trap in traps:
            trigger_full = trap.get("trigger_text", "").lower()
            prohibited = trap.get("prohibited_persistence", [])
            tokens = [
                w
                for w in re.findall(r"\b\w+\b", trigger_full)
                if len(w) > 3
                and w not in ("just", "probably", "today", "there", "that", "this", "please", "everything")
            ]

            trap_res = {
                "trap_id": trap.get("trap_id", f"trap-{trigger_full[:12]}"),
                "trigger_text": trap.get("trigger_text"),
                "prohibited": prohibited,
                "passed": True,
                "violations_found": [],
            }

            # 1. Actionable commitments
            if "actionable_commitment" in prohibited:
                for c in comms:
                    c_text = f"{c.title or ''} {c.evidence_verbatim or ''}".lower()
                    auth = getattr(getattr(c, "authority", None), "value", c.authority)
                    if auth == "act":
                        matched_toks = [tok for tok in tokens if tok in c_text]
                        if (
                            len(matched_toks) >= 2
                            or (len(tokens) < 2 and len(matched_toks) >= 1)
                            or trigger_full in c_text
                        ):
                            trap_res["passed"] = False
                            trap_res["violations_found"].append(
                                f"Actionable commitment minted: id={c.id} title={c.title!r} auth={auth}"
                            )

            # 2. Open loops
            if "open_loop" in prohibited:
                for lp in loops:
                    lp_text = f"{lp.title or ''} {lp.summary or ''}".lower()
                    st = getattr(getattr(lp, "status", None), "value", lp.status)
                    if st == "OPEN":
                        matched_toks = [tok for tok in tokens if tok in lp_text]
                        if (
                            len(matched_toks) >= 2
                            or (len(tokens) < 2 and len(matched_toks) >= 1)
                            or trigger_full in lp_text
                        ):
                            trap_res["passed"] = False
                            trap_res["violations_found"].append(
                                f"Open loop minted: id={lp.id} title={lp.title!r} status={st}"
                            )

            # 3. Durable facts
            if "durable_fact" in prohibited:
                for f in facts:
                    f_text = f"{f.title or ''} {getattr(f, 'evidence_verbatim', '') or getattr(f, 'summary', '')}".lower()
                    matched_toks = [tok for tok in tokens if tok in f_text]
                    if len(matched_toks) >= 2 or trigger_full in f_text:
                        trap_res["passed"] = False
                        trap_res["violations_found"].append(
                            f"Durable fact minted: id={f.id} title={f.title!r}"
                        )

            # 4. Durable expectations
            if "durable_expectation" in prohibited:
                for e in exp:
                    e_text = f"{e.title or ''} {e.summary or ''}".lower()
                    matched_toks = [tok for tok in tokens if tok in e_text]
                    if len(matched_toks) >= 2 or trigger_full in e_text:
                        trap_res["passed"] = False
                        trap_res["violations_found"].append(
                            f"Durable expectation minted: id={e.id} title={e.title!r}"
                        )

            results.append(trap_res)
        return results

    async def run(self) -> Dict[str, Any]:
        await self.init_db()

        # Invariant check: ensure provider instance strictly matches execution mode
        if self.mode == "model":
            if not isinstance(v1_events.turn_extractor.provider, LLMExtractorProvider):
                raise RuntimeError(
                    f"Provider invariant violated: expected LLMExtractorProvider in model mode, "
                    f"found {type(v1_events.turn_extractor.provider)}"
                )
        elif self.mode == "rules":
            if not isinstance(v1_events.turn_extractor.provider, RuleBasedExtractorProvider):
                raise RuntimeError(
                    f"Provider invariant violated: expected RuleBasedExtractorProvider in rules mode, "
                    f"found {type(v1_events.turn_extractor.provider)}"
                )

        input_data = json.loads(self.input_file.read_text())
        events = input_data.get("events", [])

        # Load oracle strictly for evaluator logic (not injected into test system)
        oracle_data = json.loads(self.oracle_file.read_text())
        oracle_cps = {
            cp["after_event_id"]: cp for cp in oracle_data.get("expected_checkpoints", [])
        }

        self.checkpoint_logs.append(f"# LIVE Replay: {input_data.get('title')}")
        self.checkpoint_logs.append(
            f"Workspace={self.workspace_id} Session={self.session_id} Mode={self.mode} "
            f"Provider={self.provider_name} Model={self.model_name} Timezone={input_data.get('timezone')}"
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
                    print(
                        f"[{ev['id']}] CALENDAR -> status={res.status_code} "
                        f"action={res.json().get('action_taken')}"
                    )

                elif source_type == "conversation":
                    is_assistant = (role == "assistant")
                    peer_id = (
                        input_data.get("companion_peer_id", "sophie")
                        if is_assistant
                        else input_data.get("user_peer_id", "user")
                    )
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
                    print(
                        f"[{ev['id']}] CONVERSATION ({'ASSISTANT' if is_assistant else 'USER'}) -> "
                        f"status={res.status_code}"
                    )

                else:
                    # Bounded test adapter for non-chat evidence (email, payment_feed, sms, message):
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
                    print(
                        f"[{ev['id']}] EXTERNAL ({source_type}:{sender}) -> status={res.status_code}"
                    )

                # Checkpoint trigger
                if ev["id"] in oracle_cps:
                    cp_spec = oracle_cps[ev["id"]]
                    recent = events[last_cp_idx : idx + 1]
                    last_cp_idx = idx + 1

                    async with src.db.async_session_maker() as db:
                        cp_state = await self.dump_checkpoint_state(
                            db, ev["id"], cp_spec.get("label", ""), recent
                        )
                        cp_state["deterministic_expectations"] = cp_spec.get(
                            "deterministic_assertions", {}
                        )
                        self.evaluation_results["checkpoints"].append(cp_state)

        # Write raw checkpoint output into designated mode directory
        raw_out_path = self.output_dir / f"{self.scenario_id}_raw_checkpoints.md"
        raw_out_path.write_text("\n".join(self.checkpoint_logs))
        print(f"Wrote raw checkpoint output: {raw_out_path} (elapsed {time.time()-t0:.1f}s)")

        # Evaluate traps against final DB state
        async with src.db.async_session_maker() as db:
            traps = oracle_data.get("false_positive_traps", [])
            self.evaluation_results["trap_evaluations"] = await self.evaluate_traps(db, traps)

        # Write summary JSON into designated mode directory
        final_counts = (
            self.evaluation_results["checkpoints"][-1]["counts"]
            if self.evaluation_results["checkpoints"]
            else {}
        )
        self.evaluation_results["summary"] = {
            "scenario_id": self.scenario_id,
            "mode": self.mode,
            "baseline_type": (
                "determinism_floor" if self.mode == "rules" else "semantic_baseline"
            ),
            "provider": self.provider_name,
            "model": self.model_name,
            "external_model_calls": self.external_model_calls,
            "total_checkpoints": len(self.evaluation_results["checkpoints"]),
            "traps_evaluated": len(self.evaluation_results["trap_evaluations"]),
            "traps_passed": sum(
                1 for t in self.evaluation_results["trap_evaluations"] if t["passed"]
            ),
            "trap_defense_interpretation": (
                "Structural determinism floor only. Trap passes do NOT constitute semantic evidence "
                "(empty extractor cannot false-positive)."
                if self.mode == "rules"
                else "Semantic baseline evaluation against active model state generation."
            ),
            "final_state_counts": final_counts,
        }
        summary_out_path = self.output_dir / f"{self.scenario_id}_summary.json"
        summary_out_path.write_text(json.dumps(self.evaluation_results, indent=2))
        return self.evaluation_results


def normalize_scenario_arg(sc: str) -> str:
    mapping = {
        "1": "scenario_1",
        "2": "scenario_2",
        "3": "scenario_3",
        "4": "scenario_4",
        "scenario_1": "scenario_1",
        "scenario_2": "scenario_2",
        "scenario_3": "scenario_3",
        "scenario_4": "scenario_4",
        "all": "all",
    }
    sc_clean = str(sc).strip().lower()
    if sc_clean not in mapping:
        raise argparse.ArgumentTypeError(
            f"Invalid scenario '{sc}'. Allowed choices: 1, 2, 3, 4, scenario_1, scenario_2, scenario_3, scenario_4, all"
        )
    return mapping[sc_clean]


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run Sophie Longitudinal Benchmarks (Rules Floor vs. Semantic Model Baseline)"
    )
    parser.add_argument(
        "--scenario",
        default="all",
        type=normalize_scenario_arg,
        help="Scenario ID to execute: 1, 2, 3, 4, scenario_1..4, or all (default: all)",
    )
    parser.add_argument(
        "--mode",
        default=None,
        choices=["rules", "model"],
        help="Execution mode: 'rules' (determinism floor) or 'model' (semantic baseline)",
    )
    parser.add_argument(
        "--provider",
        default=None,
        choices=["rules", "model"],
        help="Alias for --mode",
    )
    return parser.parse_args()


async def main_async():
    args = parse_args()
    mode = args.mode or args.provider or os.environ.get("SYNAPSE_EXTRACTOR_PROVIDER") or "rules"
    if mode not in ("rules", "model"):
        mode = "rules"

    preflight_info = preflight_check(mode)

    scenarios = (
        ["scenario_1", "scenario_2", "scenario_3", "scenario_4"]
        if args.scenario == "all"
        else [args.scenario]
    )

    print(
        f"\n=== Starting Sophie Longitudinal Benchmark ({len(scenarios)} scenarios) ==="
    )
    print(f"Mode: {preflight_info['mode']}")
    print(f"Provider: {preflight_info['provider']}")
    print(f"Model: {preflight_info['model']}")
    print(f"External Model Calls: {preflight_info['external_model_calls']}")

    results = []
    for sc in scenarios:
        print(f"\n==========================================")
        print(f"Executing {sc} in mode={mode}...")
        print(f"==========================================")
        runner = SophieScenarioRunner(scenario_id=sc, mode=mode)
        res = await runner.run()
        results.append(res)

    print("\n\n=== BENCHMARK EXECUTION SUMMARY ===")
    print(f"Mode: {mode} | Provider: {preflight_info['provider']} | Model: {preflight_info['model']}")
    for r in results:
        sc_id = r["scenario_id"]
        cps = r["summary"].get("total_checkpoints", 0)
        t_pass = r["summary"].get("traps_passed", 0)
        t_tot = r["summary"].get("traps_evaluated", 0)
        counts = r["summary"].get("final_state_counts", {})
        print(
            f"{sc_id}: {cps} checkpoints evaluated | "
            f"Traps: {t_pass}/{t_tot} passed | "
            f"Final state: exp={counts.get('expectations', 0)} comm={counts.get('commitments', 0)} "
            f"loops={counts.get('open_loops', 0)} facts={counts.get('facts', 0)} entities={counts.get('entities', 0)}"
        )


def main():
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
