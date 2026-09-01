# SOPHIE — COMPLETE STATE & HANDOFF (2026-09-01)

Purpose: full context for a fresh session. Everything built, discovered, broken, fixed, and still open.

## 1. THE PRODUCT (north star)
Sophie is a persistent companion and accountability partner: she knows what matters to the user,
follows through on stated goals/habits over days/weeks, adapts strategies when reality changes,
asks real questions, and takes initiative — while feeling like a person. Luna Pro
(openai/gpt-5.6-luna-pro) is the frozen reference foreground model for this cycle.
Target users: busy professionals, overwhelmed single parents, lonely people needing a
conversational companion who remembers details, elderly companions. Multi-product future
(Sophie / Bluum wellbeing / elderly health / productivity) on one substrate.

## 2. CURRENT ARCHITECTURE (three layers, as built)

```
RAW TRANSCRIPT (single source of truth)
  every user+assistant turn → Honcho (full fidelity + derived docs, VPS, 3393+ docs)
        │
        ├── LANE 1 — REAL-TIME RECONCILIATION (Cortex, per turn, via app outbox)
        │     narrow job: does this turn complete/cancel/correct/progress any
        │     LIVE object, or add a new dated commitment? → state mutations
        │
        └── LANE 2 — DISCOVERY/SWEEP (async, TO BUILD - see open items)
              object-shaped semantic questions over accumulated Honcho history:
              goal? habit? open loop? blocker? commitment BY USER? commitment BY
              SOPHIE? constraint? pattern? expected event? → evidence-backed
              candidates → same deterministic shaping/validation → admission

DETERMINISTIC STATE (Cortex, Neon synapse_cortex DB)
  expectations / recurrences+occurrences+ask ledger / open loops / TurnStamps /
  attention candidates / proactive log / agenda snapshots
        │
        ▼
ADMISSION CONTROL (followthrough_service)
  OWED (contractual: pressure>=0.5, unresolved, accountability objectives)
  vs OPTIONAL (held back). Follow-through states:
  outstanding → surfaced → awaiting_answer → resolved (never silently die)
        │
        ▼
HANDOVER v5 (<=151 tokens verified)
  SCENE (time_of_day, local_date) + OWED (max 3, followup_state + next_move)
  + patterns (context-only) + avoid (suppressions) + optional_count
        │
        ├── REACTIVE: user turn → Dual Aperture trajectory arbitration
        │   (sees owed items + scene) → [DIRECTION] → Luna Pro → delivery
        │
        └── PROACTIVE (Codex, shipped): cron trigger → Runtime /v1/proactive/tick
            → Cortex initiative reservation (reserved→appeared ledger)
            → Luna Pro composes outreach → Vercel persists/delivers
            → /v1/proactive/complete closes ledger → dedupe by cadence
```

## 3. DEPLOYED STATE (all on main, production-verified)
- Cortex HEAD b87b5af (image rebuilt, healthy). Migration 0016_turn_stamp at head.
- Runtime HEAD 1bb7895 (rebuilt, healthy). Vercel app 0db3cca (READY).
- Luna Pro frozen as foreground default: SOPHIE_FOREGROUND_MODEL=openai/gpt-5.6-luna-pro
  (reactive turn_executor.py + proactive proactive_executor.py).
- Honcho auth: admin-scoped JWT shared by Cortex+Runtime (workspace JWT 401 bug fixed).
- Key services in cortex: agenda_service (rank+fallback), followthrough_service
  (admission), initiative_service (tick policy+ledger), reminder_executor,
  handover_service (v5), action_projection (recurrence→candidate), TurnStamp,
  proactive ledger. New endpoints: /v1/cortex/initiative/tick, /v1/cortex/reminders/due.

## 4. PROVEN (acceptance-verified)
- 11:30 unrelated re-entry: walk objective stays live at rising pressure;
  initiative defers to reactive path when user recently active (TurnStamp, injectable clock)
- Brain dumps extract and rank without timeouts (nginx 180s + conflict-safe occurrence rows)
- "lol" → no proactive push (anti-spam real); observed patterns never become obligations
- Ranker contract: model echoes candidate ids, code owns facts (verbatim merge)
- Initiative ledger closes on delivery; immediate retry withheld by cadence
- Proactive e2e (Codex): reserve → Luna compose → deliver → ledger appeared →
  user resolves → occurrence COMPLETED → no duplicate
- Stage-1 bakeoff: Luna Pro 8.6, Solar Pro 4 8.38 (finalists); MiniMax 6.21 (no depth);
  RETIRED: deepseek baseline 4.25 (empties+artifacts), nemotron 4.54 (sludge),
  muse-spark 2.40, glm-5.3-flash 0.00. Solar = fast/banter gear candidate.
- Consolidated Luna kernel (~300 words, old-Sophie energy, no fake biography) in
  companion_core/profiles/sophie.py + llm-agent-test lib/ai/prompts.ts parity

## 5. DISCOVERED (hard-won facts about the system)
1. Honcho doc store is RICH (10k floor, autumn-darkness constraint, split-walk
   strategy, morning routine, walks-as-reflection) but peer.chat returned "no
   information" for ALL 7 unprimed questions — chat surface disconnected from doc
   store for this peer (session-scoped). Retrieval fix = prerequisite for Lane 2.
2. Half the accountability contract is in ASSISTANT turns (Sophie: "I'll push you if
   you make excuses — I'm fully on record", Aug 23). Extraction never mines assistant
   turns → Sophie promises are represented NOWHERE. Lane 2 must capture them.
3. Cortex per-turn extraction was doing ONTOLOGY DISCOVERY per turn (expensive,
   lossy) — should be narrowed to object-graph reconciliation; discovery moves to
   Lane 2 sweeps.
4. "Remind before bedtime" next_move was a hardcoded template fabricating strategy.
   Strategy must come from evidence (Lane 2), windows from user-stated preferences.
5. Model omission of new optional fields silently defeats persistence defaults —
   schema-level contracts must be required fields, not prompt prose.
6. Temporal grounding: daypart+time combos ("tomorrow morning at 9", "tomorrow at
   11 AM" case-insensitive) now grounded; "recuérdame mañana a las 9" grounds via
   Spanish (model translates to temporal phrase).
7. Grounded USER_INTENTIONs now get follow-up windows by default ("she comes back
   and asks" generalized, opt-out explicit).
8. Concurrent handover requests raced on occurrence creation — conflict-safe retry
   shipped.
9. foreground models degenerate to EMPTY replies under long contexts (deepseek,
   muse, glm) — per-model context robustness differs; bake-off caught it.
10. background model ranking must echo candidate ids — "what" rewording broke
    agenda assertions; verbatim merge contract fixed it.

## 6. OPEN ITEMS (priority order)
1. SEMANTIC CONSOLIDATION (Codex's FAIL): "10k steps" and "daytime walk" are two
   separate recurrences; resolving one leaves the other outstanding. This is Lane
   2's first job: consolidate semantically-related obligations (one outcome, two
   strategies). Mechanism: sweeper proposes merge/linkage; deterministic code owns it.
2. Reminder window persistence: second-chance grounding + default rule deployed
   but production rows still show start=None in latest verification — needs one
   instrumented trace at the persistence site (flag may still be omitted by
   extractor model, or USER_INTENTION default gate edge).
3. Lane 1 slimming: reconcile-against-objects prompt (narrow) replacing open-ended
   per-turn ontology discovery.
4. Lane 2 sweeper build (Honcho retrieval fix first).
5. Greeting/re-entry path consuming the same owed/scene handover (not yet wired).
6. Streaming foreground call (latency: deepseek was 14-32s non-streaming; luna ~7s).
7. Deferred sanity fixtures: Doctor Who interruption, hospital interruption,
   no-contract conversation (deferred in Codex's run).
8. Runtime full suite stall isolation (11 tests, then hang — env issue).
9. Retire lexical intent fallbacks: expectation_shaper keyword gates,
   RecurrenceSemantics ritual/adherence lexicons, apply_reopen_conditions regex,
   cortex_router query regexes. Regex stays only for machine syntax/validation.
10. Trajectory governor (logged, NOT built): background analysis of user
    trajectory + Sophie support trajectory + repeated divergence + levers.

## 7. KEY FILES
- Cortex: src/services/{agenda_service,followthrough_service,initiative_service,
  handover_service,reminder_executor,action_projection,turn_extractor,
  temporal_grounding,cortex_packet_service}.py; routers/v1_cortex.py
- Runtime: companion_core/{profiles/sophie.py,policy/conversational_agency.py,
  runtime/turn_executor.py,proactive/proactive_executor.py},
  adapters/cortex/client.py, adapters/providers/model_provider.py
- App: lib/ai/prompts.ts, lib/companion-runtime.ts, lib/db/schema.ts (Task),
  app/api/tasks/candidates/*, lib/honcho.ts
- Harness: evals/scenario_runner.py, evals/scenarios/*.json (6 fixtures),
  evals/stage1_qualification.py, evals/results/*
- Migrations: 0012 semantic_type, 0013 occurrence follow-up, 0014 agenda,
  0015 proactive_log, 0016 turn_stamp

## 8. OPERATIONAL COMMANDS
- Deploy cortex: ssh VPS → ~/synapse-cortex && git pull origin main →
  cd deploy && docker compose build --no-cache api && up -d (runtime same pattern)
- Note: nginx conf at /opt/stack/nginx/nginx.conf (bind-mount inode: restart
  reverse-proxy after sed edits)
- Harness: python3 evals/scenario_runner.py scenarios/X.json --base <cortex-url>
  (env SYNAPSE_CORTEX_API_TOKEN; isolated harness_<name>_<runid> workspaces)
- Honcho prod DB: docker exec honcho-postgres psql -U postgres -d postgres
- Alembic: startup create_all may race migrations — stamp if tables pre-exist

## 9. INVARIANTS (never violate)
- model proposes; deterministic code commits (state, windows, ledgers, ids)
- no lexical/regex intent detection for human semantics (regex = machine syntax
  and validation only)
- user evidence > machine inference; provenance preserved; supersede never delete
- unknown ≠ failed; plan failure ≠ objective failure; strategy adapts
- owed items are never silently dropped — defer/recover, bounded asks (<=2/day)
- foreground receives only ADMITTED items; optional stays backstage
- Sophie promises are commitments too (currently unrepresented — Lane 2 scope)
- no test-only behavior in the harness (harness = thin driver of real paths)
- single source of attention truth: owed/scene handover feeds ALL entry paths
