# Gemini Eval Packet — frozen corpus manifest (existing evidence only)

> Owner: Track A (Spark). For: Gemini behavioural scoring sheet.
> Corpus status: C2–C5 APPROVED/FROZEN. C1 is PRIVATE_FIXTURE / NEEDS LOCATION
> (held by user, explicit content, not committed) and does not block the rest.
> No scoring framework here — Gemini defines it. Human reading overrides scores:
> a higher score on a deader companion is a failed eval.

## E1. Elena/RPD2 known-good trajectories (product: RPD2/Elena)

| ID | Source | Behaviour under test | Historical result / why it matters | Regression signals | Canon | Runnable / transcript-only | Caveats |
|---|---|---|---|---|---|---|---|
| E1a | `rpd2/reports/kai_elena_8ae17baf-*_transcript.md` + `.json` (turns 30–36 dinner initiative panic→warmth; confession #69; shame→choose #87→97) | Unprompted initiative with affect arc; repair-as-action; choosing under pressure | Documented magic moments with receipts (`EXPERIMENT-LEDGER.md:18`); initiative 4/4 yields in `INITIATIVE_V1_REPORT.md` | Initiative absent/flat; repair collapses to speeches; pursuit missing where Elena pursued | Autonomy-by-default; repair-is-behavior; character judgement | Transcript-only (+ `AGENTIC_CHALLENGER_V1_SPEC.md` challenger rig for reruns) | Elena fixture human sign-off still pending (`MIGRATION_GAP_REGISTER.md`); use as reference, not proof of current head |
| E1b | `rpd2/reports/HYBRID_VS_RAW_TAIL_20X_REPORT.md` + `hybrid_vs_raw_tail_20x_raw.json` (80 runs, Gemma-4) | Compaction under rupture (hybrid T-1 verbatim + T-2 compacted) | Salon rupture stability 60→90% (75% failure reduction); non-sexual 100%/100% | Rupture handling regresses toward raw-tail instability | Evidence≠interpretation; trajectory correctable | Runnable (raw JSON + `transcript-window.ts` mechanism) | Fixture-bound (n=80, single model); bounded artifact, not universal proof |
| E1c | `rpd2/reports/POWERED_POISONED_RECOVERY_DISCRIMINATOR_REPORT.md` + raw JSON (108 runs) | Identity hold + compounding control + autonomous reversal under cruelty | Identity 100% (36/36); compounding 25→8.3%; reversal 55.6% overall / 83.3% NPC cruelty; 0% parroting | Identity drift; parroting; compounding runaway | Stable character over generic priors; poisoned readings must not become truth | Runnable (raw JSON) | Same bounded-artifact caveat; D+ conditions are adversarial by design |

## E2. Sophie longitudinal blind baseline (product: Sophie)

| ID | Source | Behaviour under test | Historical result / why it matters | Regression signals | Canon | Runnable / transcript-only | Caveats |
|---|---|---|---|---|---|---|---|
| E2a | `synapse-cortex/evals/sophie_longitudinal/` (manifest + 4 input/oracle pairs + `runner.py`) → `synapse-cortex/reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md` (frozen cortex `44a89d1`, runtime `6b2f78d`, gemini-2.5-flash-lite) | Long-horizon lifecycle: immortal loops, spurious VIOLATED, counterparty misattribution, entity collision, siloed promises, resolve-before-clarify, clarification flood | Verdict SYSTEMIC PASSIVITY & ASYMMETRIC LIFECYCLE BREAKDOWN on frozen baseline — trivial chatter passed (2/2, 4/4, 2/2, 2/2), lifecycle failed | Any of the above persisting on current head | Asked≠resolved; autonomy-by-default; attention over dumping | Runnable (manifest + runner + raw_outputs/) — RERUN ON CURRENT HEAD before citing either way | Evaluates frozen baseline, NOT current state; oracle agreed on ground truth but 2 oracle demands judged too strong; do not cite as current-state proof |

## E3. Retrieval probes with known answers (substrate: Honcho/Cortex)

| ID | Source | Behaviour under test | Historical result / why it matters | Regression signals | Canon | Runnable / transcript-only | Caveats |
|---|---|---|---|---|---|---|---|
| E3a | `synapse-v3/ashley_v3_planner_first_probe.json`, `ashley_v3_planner_first_rerank_probe.json`, `ashley_recall_v1*.json`, `docs/experiments/2026-06-ashley-*.md` | Planner-first recall; planner+rerank specificity; scoped-vs-strict answering | Invoice surfaced rank 3 first time; Q8,400 invoice #1 (best combined); scoped 3/10→6/10 frozen, 0 hallucinations | Missed known records; hallucinations; wrong-decline on strictness | Benchmark harness for any retrieval path; evidence≠interpretation | Runnable (JSON probes + focused runners) | Spanish Ashley sessions; domain-bound; rerank winner (Cohere) is eval-only pricing |
| E3b | `synapse-cortex/evals/narrow_contract_cases.json` + `narrow_contract_compare.py` → `results/narrow_contract_compare_latest.json`; `narrow_model_bakeoff.py` → `results/narrow_model_bakeoff.json` | Narrow realtime gate vs broad ontology; model bakeoff | 4 clean MATCH then 402 stall (missing max_tokens, fixed); gpt-4o-mini 0.929 acc p50 2.6s; granite fastest but narrates-hallucinates; deepseek slowest-clean | Broad-ontology sprawl returns; narration hallucination | Minimum scaffolding; narrow-vs-Lane-2 split | Runnable pending credits + max_tokens deploy + full matrix + 7-day soak | BLOCKED — only 4 diag cases ran clean; do not cite as cutover proof |
| E3c | `synapse-v3/docs/retrieval_quality_eval.md` + `EXPERIMENT_OVERVIEW.md` §8 (12-case golden); `operational_memory_eval_v1_1.json` | Deterministic lane coverage; state-first operational bundle | Top-1 9/12, Top-5 12/12, MRR 0.8542; storage 0.878/retrieval 0.667/answer 0.667, waiting-on + money 1.0, 0 leakage | Lane regressions; money/no-overclassify misses (<35% all models) | State-first with recall secondary (only forgotten_or_stale + health) | Runnable (evals/ + fixtures) | Eval-identified gaps open: stale-thread ranking, plate/upcoming clutter, cancelled-pending closure |

## E4. Re-entry / session continuity (products: Sophie, general)

| ID | Source | Behaviour under test | Historical result / why it matters | Regression signals | Canon | Runnable / transcript-only | Caveats |
|---|---|---|---|---|---|---|---|
| E4a | `test-starter/fixtures/prompt-playback.json` (Ashley-breakup scenario) + `outputs/prompt-playback-*.json` (~40 runs) + `scripts/prompt-playback.ts` | Prompt-stack continuity across playback; kernels + steering + style-guard behaviour | Harness exists with ~40 runs; voice frozen into 5 kernels after ~20 persona iterations | Bridge/handover regressions; banned-phrase/endearment violations (`promptStackV2.test.ts`) | Session orientation + turn deltas; character judgement | Runnable (playback harness) | Scenario-bound (single breakup scenario); needs multi-scenario before general claims |
| E4b | `test-starter/fixtures/brief-day/*.json` (8: chaotic-founder, single-parent, elderly-check-in, high-emotion-commitment…) + `scripts/eval-dev-brief-day-*.ts` | Day-brief judgement across life shapes | Fixture set exists; deterministic-vs-model answer split proven | Generic briefs; missed follow-throughs; pressure/focus misreads | Progressive disclosure; asked≠resolved | Runnable (eval scripts) | Prototype-frozen (`brief-day` reference, not final — target is DailyContextPacket) |
| E4c | `test-starter/fixtures/vnext-turn-replay/*.json` (5) + `scripts/vnext-{turn-replay,section-compare,fixture-set-report}.ts`; `SOPHIE_HANDOFF_2026-09-01.md` proven 11:30 re-entry | Legacy-vs-vNext section parity; real re-entry moment | Parity harness exists; 11:30 re-entry demonstrated live | Orientation regressions; stale-handover reintroduction; false re-entry on continuous conversation | Current words beat stale recall; entry only on new/firstContact/reentry | Runnable (replay scripts) | Session-lifecycle constants (30-min window, turn-1/2/3+ rules) live in test-starter, not enforced shared-side |

## E5. Proven mechanism evals (substrate behaviours — rerun on current head, don't re-prove)

| ID | Source | Behaviour under test | Historical result | Regression signals | Canon | Runnable / transcript-only | Caveats |
|---|---|---|---|---|---|---|---|
| E5a | `rpd2/reports/RELATIONAL_CONTINUITY_FINDINGS.md` + `relational_continuity_raw.json` (351 trajectories) | Condition-C: repair-action gap closure | 2.9–3.1→4.3–4.6/5; outsourcing −85%; prohibited recurrence 0%; naturalness 4.3/5 | Action-gap returns; outsourcing; prohibited gestures recur | Repair-is-behavior; corroboration-into-Account | Runnable (raw JSON) | Upstream-background-state dependent; Cydonia-24B rival claim is context-bound |
| E5b | `rpd2/reports/DIRECTOR_ISOLATION_REPORT.md` → `DIRECTOR_COMMITMENT_REPORT.md` | Union-selector commitment (judge prose vs move selection) | Prose 9/9 but moves 3/9 → union schema + lenient extraction → 9/9 | Exact-match validation murdering shaped commits | Good reasoning useless without faithful action selection | Runnable (harness) | Narrow mechanism win; does not prove universal Director |
| E5c | `rpd2/reports/CONTINUE_AB_REPORT.md` | Subtraction vs addition on healthy banter | Full compiler beats 155-tok packet 6-1-1 — subtraction applies at objective switches, not everywhere | Over-subtraction starving live turns | Minimum scaffolding; attention over puppeteering | Runnable | KILLED direction (tiny-CONTINUE); cite as boundary, not capability |
| E5d | Same sources as E1b (mechanism: `transcript-window.ts`) | Hybrid compaction | 60→90% rupture stability | Raw-tail instability | Hybrid (verbatim + compacted), not raw or fully summarized | Runnable | See E1b caveats |
| E5e | Same sources as E1c | Poisoned recovery | 100% identity, 25→8.3% compounding | Drift, parroting | Stable character; slow memory kernel-grounded | Runnable | Adversarial conditions; not everyday proof |

## E6. Known failure demonstrations (negative controls — system must NOT do these)

| ID | Source | Behaviour under test | Historical result | Regression signals (must stay absent) | Canon | Runnable / transcript-only | Caveats |
|---|---|---|---|---|---|---|---|
| E6a | `test-starter/docs/memory-recall-diagnosis-2026-04-09.md` | Keyword-gated recall ("what do you know about Ashley?" missed) | Keyword gate deleted 2026-04-09 | Any keyword-as-semantic-authority return | Deterministic at boundaries, models for meaning | Transcript-only (post-mortem) | Fix (`toolChoice:auto`, semantic descriptions) lives in test-starter, not enforced shared-side |
| E6b | `test-starter/docs/changelog.md:66-75` | Scene-keyword loop ("How's your walk going?" every turn) | Tightened to affirmative present-tense; literal-mode anchoring deleted | Same-observation retrigger loops | Don't re-trigger same contextual observation | Transcript-only (post-mortem) | Same carryover caveat as E6a |
| E6c | `rpd2/reports/EXPECTATION_RENT_REPORT.md` | Bare expectation lines as injected policy | KILLED channel (no movement); store kept, corroboration-into-Account works | Reintroducing injected-line expectations | Minimum scaffolding | Runnable (9 calls, bounded) | n=9; fixture-bound — cite scope honestly |

## Coverage map (genuine gaps after inventory — new scenarios ONLY if these remain empty)

- Foreground-draft interception (sync regenerate vs next-turn correction): no frozen case. Open question, not a corpus item yet.
- Worker question-asking (research/plan/draft querying substrate mid-task): no frozen case.
- Luna tutoring drip-feed / Bloom phase transitions / healthcare escalation: scenarios exist (E4b), constitutions do not (see `PRODUCT_CONSTITUTION_SOURCES.md` UNSPECIFIED).
- C1 freeze location undecided — corpus incomplete until ruled.
