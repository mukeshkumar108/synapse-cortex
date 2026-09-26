# Consolidated Learnings — Companion Substrate

> Purpose: single consolidation of 2+ months of experiments across
> `synapse-v3`, `test-starter` (Sophie voice+chat), `rpd2` (Elena),
> `companion-runtime`, `synapse-cortex` — so proven magic stops getting
> lost in each migration.
>
> Status: 2026-09-26. Sources mined read-only; no behavior changed.
> Canonical runtime handoff remains `ash-ai/docs/COMPANION_PLATFORM_RUNTIME.md`.
> Boundary ledger remains `docs/GRADUATION-LEDGER.md`.

## 0. Thesis in one paragraph

Honcho owns semantic evidence (transcripts, vectors, conclusions, summaries).
Cortex owns lifecycle state (expectations, loops, suppressions, recurrences,
candidates, receipts). Runtime owns authority + execution (aperture, gears,
prompt assembly, generation). Model proposes, code commits. Supersede,
never delete. Unknown ≠ failed. Current words outrank recall.

Magic = kept promises + perfect re-entry + withheld nudges. Not more memory.

## 1. What was PROVEN (keep, with evidence)

### 1.1 Retrieval science (synapse-v3)

| Finding | Evidence |
|---|---|
| Planner-first query expansion surfaces missed records (invoice rank 3 first time) | `synapse-v3/ashley_v3_planner_first_probe.json/.md` |
| Planner-first + Cohere rerank = best specificity (Q8,400 invoice #1) | `synapse-v3/ashley_v3_planner_first_rerank_probe.json/.md` |
| Scoped-evidence answering beats strict, 0 hallucinations (3/10→6/10 frozen) | `synapse-v3/ashley_v3_answer_scoped_frozen.json`, `ashley_v3_frozen_evidence.json` |
| Independent-pool RRF repaired 8/10, Jaccard ~0–0.11 proves complementarity; BM25 8/10 | `synapse-v3/docs/experiments/2026-06-ashley-bm25-rrf-eval.md` |
| Deterministic lanes Top-1 9/12, Top-5 12/12, MRR 0.8542 | `synapse-v3/docs/retrieval_quality_eval.md`, `EXPERIMENT_OVERVIEW.md` §8 |
| Operational state-first truthful; v1.1 storage 0.878 / retrieval 0.667 / answer 0.667, waiting-on + money 1.0, 0 leakage | `synapse-v3/operational_memory_eval_v1_1.json`, `docs/experiments/2026-06-operational-memory-eval-v1.md` |
| Router bakeoff: llama-3.1-8b most accurate 72.3%, nova-micro fastest p50 1045ms, granite-micro last 59.6% | `synapse-v3/router_model_bakeoff_v1.json` |
| Narrow bakeoff: gpt-4o-mini 0.929 acc p50 2.6s wins; granite fastest but hallucinates narration; deepseek slowest-clean | `synapse-cortex/docs/NARROW_CONTRACT_SHADOW_FINDINGS_2026-09-01.md`, `synapse-cortex/evals/results/narrow_model_bakeoff.json` |
| Refined single-pass Llama planner: 100% action + 100% slots, 0 unsafe | `synapse-v3/planner_eval_llama8b_refined.json` |
| Per-query cap 10 controls pool growth 37–88 (dedup removes 60–82%) | `synapse-v3/ashley_v3_planner_first_rerank_answer_probe.json` |

Surviving model routing (`synapse-v3/core/model_routes.py`):
classifier/planner → Llama-3.1-8B / Nova-Micro; loose+shaper → DeepSeek-V4-Flash;
reconciler/judge/summarizer → gpt-4o-mini; rerank-eval → cohere/rerank-v3.5.

### 1.2 Friendliness + restraint (test-starter)

| Finding | Location |
|---|---|
| Friendliness = 5 locked kernels (persona/posture/style-guard/user-context/stance+tactic) + steering, locked by test | `test-starter/prompts/00_model_kernel.md`, `10_identity_kernel.md`, `20_steering_kernel.md`, `40_style_kernel.md`, `src/app/api/__tests__/promptStackV2.test.ts` |
| Continuity = cached resume/handshake + turn-1/2/3+ injection rules + 30-min session window (fixed 5-min fragmentation) | `test-starter/src/lib/services/session/resumePacket.ts`, `docs/runtime-flow.md:46-56`, `docs/current-decision-log.md:115-135` |
| Proactivity = gated overlays: curiosity 1/session, accountability 1/day + 48h backoff, rupture cooldowns, ops↔recall mutual exclusion | `test-starter/src/lib/services/memory/overlaySelector.ts` |
| Agency = LLM interprets, code enforces; reads execute, writes via `POST /api/actions/confirm` + Idempotency-Key | `test-starter/docs/sophie-action-api.md`, `docs/sophie-vnext-runtime.md:202-258` |
| Keyword-gated recall FAILS ("what do you know about Ashley?" missed); fix = `toolChoice:auto`, semantic descriptions | `test-starter/docs/memory-recall-diagnosis-2026-04-09.md` |
| Scene-keyword loops ("How's your walk going?" every turn); fix = affirmative present-tense + prompt order, not more regex | `test-starter/docs/changelog.md:66-75` |
| Tier/burst routing: T1 default / T2 companion-depth / T3 2-turn burst per stance event; risk HIGH/CRISIS bypass | `test-starter/docs/runtime-flow.md:56-74` |
| Day-brief 10-min cache + deterministic-vs-model answer split | `test-starter/docs/sophie-vnext-runtime.md:289-316` |

### 1.3 Relational spine (rpd2, Elena, real-world)

| Finding | Evidence |
|---|---|
| Hybrid compaction (T-1 verbatim + T-2 compacted): Salon rupture 60%→90% (75% failure reduction), 80 runs | `rpd2/reports/HYBRID_VS_RAW_TAIL_20X_REPORT.md` |
| Poisoned recovery: identity 100% (36/36), compounding 25%→8.3%, reversal 83% under NPC cruelty, 0% parroting, 108 runs | `rpd2/reports/POWERED_POISONED_RECOVERY_DISCRIMINATOR_REPORT.md` |
| Condition-C closes repair-action gap 3.0→4.5/5, outsourcing −85%, prohibited recurrence 0%, 351 trajectories | `rpd2/reports/RELATIONAL_CONTINUITY_FINDINGS.md` |
| Director union-selector: prose 9/9 but moves 3/9 → exact-match validation murdered `A.[id]` commits → union schema → 9/9 | `rpd2/reports/DIRECTOR_ISOLATION_REPORT.md`, `DIRECTOR_COMMITMENT_REPORT.md` |
| Initiative works only as executive pin, not bare label: 7/7 stop, 4/4 yields, 0 violations | `rpd2/reports/INITIATIVE_V1_REPORT.md`, `BANTER_FIRE_REPORT.md` |
| Killed with reason: Tiny-CONTINUE lost 6-1-1 to full compiler on healthy banter; bare expectation lines don't move policy | `rpd2/reports/CONTINUE_AB_REPORT.md`, `EXPECTATION_RENT_REPORT.md` |
| Magic transcripts: dinner initiative turns 30–36 (panic→warmth), confession #69, shame→choose #87→97, car-door reversals, NPC-pressure refusal | `rpd2/reports/kai_elena_8ae17baf-*`, `docs/RUNTIME-HANDOFF.md`, commit `64cfd044` |

Canon: `rpd2/docs/DYNAMIC-CONTEXT.md` (15 principles), `AUTHORITY-CONTRACT.md`
(5 roles), `EXPERIMENT-LEDGER.md` (items 0–21), `relational-memory-architecture.md`
(+2026-09 hardening), `AGENTIC_CHALLENGER_V1_SPEC.md` (emergence = non-prescribed
action retrospectively well-supported by state; invented memory scores against).

### 1.4 Shared-spine LIVE (already graduated)

Per `docs/GRADUATION-LEDGER.md`: CurrentMeaning + revise-sync (fail-closed);
release/backgrounding v1 (authority-only); first-beat trajectory authority
(≤1500ms, single-consumption); sustain/yield (N+1 reaction). Pending live
validation: semantic relations/claims (`0028`/`0029`, 13-type edges, 9-kind judge,
11 views). Parity GRADUATE: backgrounding + sustain/yield; HOLD: meaning-rewrite;
INCONCLUSIVE: initiative (`companion-runtime/audit-round3/10-stage-b-review.md`).

## 2. What was LOST / never carried over (recover in order)

| # | Lost learning | Last known good | Recover to |
|---|---|---|---|
| 1 | Rerank default + metadata-policy ON + planner-first fan-out + frozen-evidence harness | `synapse-v3`: Cohere rerank best, metadata ON, cap-10, frozen evidence; prod hardcoded `noop`/OFF | Cortex retrieval path behind flag; rerun `evals/narrow_contract_compare.py` + full matrix + 7-day soak |
| 2 | Referent resolution ("mark that done") + session suppression/deflection machine | `synapse-v3/docs/architecture/*`: resolver 0 callers, suppression unwired (`V3_CAPABILITY_WIRING_MATRIX.md`) | Wire into message path before more extractor kinds |
| 3 | Session-close → full ingest + resume refresh + 30-min window + retry×3; turn-1/2/3+ handover rules; `use_bridge` | `test-starter/src/lib/services/session/*`, `docs/runtime-flow.md` | Durable cron (not in-process 300s debounce); decide initiative owner `[C-i]` vs `[C-ii]` (`audit-round3/03-initiative-paths.md` still DEFERRED) |
| 4 | Overlay proactivity policy (caps, backoffs, rupture suppression, mutual exclusion) | `test-starter/src/lib/services/memory/overlaySelector.ts` | Cortex `suppressions` table needs the *policy*, not just the table |
| 5 | Confirmation-gated agency shape (`pendingActions`, `recentActionReferences`, clarify-on-ambiguity, dedupeKey) | `test-starter/docs/sophie-action-api.md` | Do not let V3 direct-write bypass confirm UX |
| 6 | RPD2 → shared queue: easing/backgrounding full loop, union Director, subtraction projection, executability filter, write screens, initiative pin/sustain | `GRADUATION-LEDGER.md:103-108` PORT-not-started | Port in ledger order; no premature "have" claims without parity battery |
| 7 | Handover merged into message path; answer generation; post-response writeback; 7/12 runtime tools | `V3_CAPABILITY_WIRING_MATRIX.md` gaps | Merge-or-keep-separate handover decision + one real `/v3/message` smoke (<$0.10) |
| 8 | External workers: calendar/gmail OAuth + sync, 30-min sealer, decay, outreach, EOD/weekly packets | `Synapse_V3_Tasks_6_10.md` T6–T10; `workers/` empty | Spec exists; needs owner + schedule |
| 9 | 21-category companion envelopes + relationship-thesis modes (second beats, pauses, refusals-as-texture) | `synapse-v3/docs/COMPANION_MEMORY_PRIMITIVES.md`, `RELATIONSHIP_SHAPED_RUNTIME_THESIS.md` | Needs extraction + restraint contracts first (per README: do not approximate as continuity objects) |
| 10 | Honcho depth: `representation` / `session.context()` / `conclusions/query` / `peer.chat(depth)` / peer cards / Dream status | Honcho `3.0.11` offers; Cortex uses `list`+recent+search only | Switch Cortex reads to representation+context+semantic query; keep lifecycle projection thin |

## 3. Explicitly DEFERRED (do not reopen without contract)

* Narrative-scene richness, pattern hypotheses/surfacing, belief revision,
  comm-profile extraction, trajectory governor, canon-confidence model —
  `companion-runtime/docs/SESSION_MODE_AND_BELIEF_SPINE.md:50-59`,
  `audit-round3/11-canon-confidence-parked.md`, synapse-cortex `README.md:40-43`.
* Greeting/re-entry wiring, streaming foreground call, suite-stall isolation,
  lexical-fallback retirement — `docs/SOPHIE_HANDOFF_2026-09-01.md:139-150`.
* W1 ledger / W2 task model / W3 rhythm / W4 brief+window / W5 triggers / W6 greeting —
  `docs/MISSION_WORK_AND_ATTENTION.md:48-127` (day packet + `sweeper_triggers.py` partial only).
* Gates 6–10 (Sophie seam → RPD2 parity → candidate selection → canary →
  views/proactive/voice); Voice blockers 1–4 —
  `companion-runtime/docs/MIGRATION_GAP_REGISTER.md:220-226`, `VOICE_ROLLOUT_GATE.md`.
* Moves/ops packet wiring, `same_as` writer, `restated`, source-coverage telemetry,
  Isa replay, judge cost/latency — `reports/mission_operational_intelligence_2026-09-25.md:73-82`.
* Initiative clock split-brain (cron vs tick vs idle); Honcho pre-gate recall battery;
  scene TTLs/anchor contract; per-product thresholds —
  `companion-runtime/docs/PERCEPTION_CONSOLIDATION_SPEC.md:217-223`.

## 4. Intentionally DROPPED (do not resurrect)

Graphiti/FalkorDB coupling; monolithic user model; 6-pass verbatim prompts;
SQL-heavy merges; duplicate candidate tables; per-scene kernel injection;
fictional clock / off-screen sim / gifts; per-fetish taxonomy / unlock bars;
`shared_facts[]` / `pending_plan` stores; keyword gating as semantic authority;
local Shadow Judge per-turn; summary spine as scene truth; per-message ingest;
live startbrief blocking turn-1; lexical goodbye triggers; TTS caps; filler clips
without tool-in-progress signal. (`SYNAPSE_V2_INTELLIGENCE_EXPORT.md` do-not-copy;
`CONSOLIDATION-ROADMAP.md` dedupe map; `PERCEPTION_CONSOLIDATION_SPEC.md:211-214`
do-not-port 11.)

## 5. Silently at-risk (writers without consumers — wire or retire)

Epistemic/domain annotations, `/working-set` HOT branch, WorkItem external checks,
streaming receipts (`effect=null`), original `createdAt` (outbox uses delivery `now`),
AgendaSnapshot-as-center, RPD2 Account merge, dead steer, B/C kernels.
Refs: `companion-runtime/audit-current-code-2026-09-24/REPORT.md:122-131`;
`reports/control_convergence_2026-09-25.md:84-96,162-168`.
Also: RPD2 addressee `[EXPRESSION]` 3-test mismatch (unassigned);
Elena fixture human sign-off pending; `src/models/__init__.py` import fix committed
locally NOT pushed; Neon drift repairs; `SYNAPSE_MEANING_TIMEOUT_MS` 1.5s→12s
(`reports/prod_deploy_2026-09-26.md`).

## 6. Dead / Alive table (one-line verdicts)

| Mechanism | Verdict |
|---|---|
| Loose→shape extraction, temporal grounding, reconciliation-as-judge | ALIVE in Cortex (`turn_extractor.py`, `temporal_grounding.py`, `turn_reconciliation.py`) |
| BM25 + RRF fusion, metadata-policy ON, Cohere rerank default, planner-first prod | DEAD — highest-priority recovery (§2.1) |
| Referent resolver, suppression machine, handover-merged path, writeback | DEAD — wire before new kinds (§2.2, §2.7) |
| Resume/handshake bookends, 30-min window, turn-1/2/3+ rules, overlay caps | DEAD in shared path — re-import constants (§2.3–2.4) |
| Confirmation-gated agency, day-brief cache+split | PARTIAL — Runtime defers lanes, BFF confirms; keep shape (§2.5) |
| CurrentMeaning, release/backgrounding-v1, first-beat, sustain/yield | ALIVE + LIVE (ledger) |
| Easing full loop, union Director, subtraction, executability, write screen, initiative pin/sustain | QUEUED — not started, do not claim (§2.6) |
| Narrative scene, patterns, belief revision, trajectory governor | DEFERRED with preconditions (§3) |
| Workers (calendar/gmail/sealer/decay/outreach), EOD/weekly, memory-control UI | NEVER BUILT — spec exists (§2.8) |
| Companion envelopes (21 cats), relationship modes | NEVER GRADUATED — needs contracts (§2.9) |
| Honcho representation/context/semantic-query/Dialectic-depth/cards/Dream | ALIVE in Honcho, DEAD in our reads (§2.10) |

## 7. VPS / original synapse notes

* VPS `161.97.150.246` cited in `docs/BOUNDED_PROBLEM_HONCHO_DERIVER.md`:
  Lane-2 sweeper `evidence_packets:0` from `honcho-deriver` RateLimitError
  (OpenRouter quota). Fallback = `conclusions/list` + workspace search over
  3,396 derived docs (history OK, minutes-fresh blocked). No implementation
  ticket or verification recorded after — confirm key/quota, verify `peer_search`
  <2min, rerun `background_tick` + `unrelated_reentry`.
* Local probe history: real root cause of one "Honcho empty" incident was probing
  `synapse-api:8000` not `honcho-api` (`docs/SOPHIE_HANDOFF_2026-09-01.md` §6.1,
  `evals/honcho_probe.py`). Re-verify host/port before blaming retrieval.
* To diff VPS original: needs SSH or dump of `/opt/stack` (nginx conf, compose,
  env, deriver logs, queue status). Not accessible from this doc session.

## 8. What to do next (ordered)

1. Metadata-policy ON + heuristic rerank default + planner-first flag; rerun
   `evals/narrow_contract_compare.py` + full matrix + 7-day soak (unblocks §2.1).
2. Wire referent + suppression into message path (§2.2).
3. Durable session-close→ingest + resume refresh via app cron; decide initiative
   owner `[C-i]` vs `[C-ii]` (§2.3).
4. Port graduation queue in order (§2.6); rerun Sophie longitudinal blind eval
   (`reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md` baseline:
   immortal loops, spurious VIOLATED, 0 meanings — do not cite as current without rerun).
5. Re-import test-starter constants verbatim (§2.4–2.5).
6. Switch Cortex Honcho reads to representation/context/semantic-query (§2.10).

## 9. Source index (start here, in order)

1. `rpd2/docs/DYNAMIC-CONTEXT.md` + `AUTHORITY-CONTRACT.md` (doctrine)
2. `rpd2/docs/EXPERIMENT-LEDGER.md:8-21` + `CONSOLIDATION-ROADMAP.md:37-67,131-160` (evidence→port map)
3. `rpd2/docs/RPD2-RUNTIME-INTEGRATION-HANDOFF.md:0-8` + this repo `docs/GRADUATION-LEDGER.md` (boundary + what crossed)
4. `synapse-v3/docs/experiments/EXPERIMENT_OVERVIEW.md` + `V2_BEHAVIOURAL_BASELINE_REVIEW.md` (retrieval + parity checklist)
5. `test-starter/docs/SOPHIE_SYNAPSE_V2_INTEGRATION_AUDIT.md:§5-8` + `SOPHIE_RUNTIME_RESPONSIBILITY_AUDIT.md` (carryover risk list)
6. `companion-runtime/docs/MIGRATION_GAP_REGISTER.md` + `PLATFORM_ARCHITECTURE.md` + `PERCEPTION_CONSOLIDATION_SPEC.md` (gates + architecture)
7. This repo `docs/SOPHIE_HANDOFF_2026-09-01.md` + `MISSION_WORK_AND_ATTENTION.md` + `reports/` (current state + slices)
