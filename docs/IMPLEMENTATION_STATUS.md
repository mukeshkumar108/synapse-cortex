# Implementation status (memory work, as of 2026-10-20 night)

Three words are used on purpose: **intended** (the design), **implemented** (code exists, tests pass), **observed** (seen working or failing with real models/data).
Where observed is weaker than implemented, that is the finding. Decisions: `DECISIONS.md`. Architecture and evidence: `CONNECTED_UNDERSTANDING.md`,
`MEMORY_CONTRACTS_2026-10-20.md`.

## Versions, deployment, rollback

| | Commit | On the VPS | Rollback image (taken before this deploy) |
|---|---|---|---|
| Cortex | `aded6c0` (previous deploy `6995578`) | `deploy-api:latest`, built from `aded6c0` | `deploy-api:pre-connected-2026-10-20` |
| Runtime | `11adb0f` (previous deploy `7236b0b`) | `companion-runtime:local`, built from `11adb0f` | `companion-runtime:pre-connected-2026-10-20` |

Deployed 2026-10-20 ~18:00 BST: Cortex healthy, `CONNECTED_WORLD_ENABLED=False` confirmed inside the container, new tables (`known_entities`, `known_entity_aliases`, `known_links`,
`cue_exposure`) and columns (`attention_actions.source/source_ref/expires_at`, ledger time columns) present, `GET /v1/memory/world` answers `enabled:false` and `GET /v1/memory/ledger`
answers for a smoke workspace (read-only; nothing written, nothing to purge); source md5 on the VPS matches the repo. Runtime healthy, world flag off. Post-deploy canary: first run
**FAIL — provider outage** (NanoGPT 503 `all_fallbacks_failed` on the canary's character model, visible in the Runtime log, not a code path I changed), second run **PASS**.
Scratch environment used for all model-backed runs was torn down (containers, network, env copy shredded, tunnels closed).

Flags after this deploy: `CONNECTED_WORLD_ENABLED` **off** in Cortex and Runtime (connected understanding is dark). Bloom **off** (`MEMORY_PIPELINE_COMPANIONS=sophie`).
`MEMORY_LEDGER_MODELS` not set (single-model witness, as before). New schema is additive (four tables, a few nullable columns); rolling the images back leaves
the extra tables/columns inert. To roll back: `docker tag deploy-api:pre-connected-2026-10-20 deploy-api:latest` then `docker compose -f docker-compose.vps.yml up -d api`
(Cortex) and the same for `companion-runtime`. To switch the new layer off without a rollback: set the two flags to `false` and restart.

## Update, 2026-10-20 night

- **Enabled in production for the founder.** `CONNECTED_WORLD_ENABLED=true` in Cortex (passed through `deploy/docker-compose.vps.yml`) and Runtime `.env`. Bloom and all other users remain off. Kill switch: set both to `false`, restart.
- New since the table below: happenings/dispositions/patterns + soft tags + pertinent selection (`CONNECTED_UNDERSTANDING.md` §13), export/delete endpoints, continuity `RETRACT`, attention/ledger-link/pronoun contract lines,
  `inspect` shows the new fields. Rollback images taken before this deploy: `deploy-api:pre-happenings-2026-10-20`, `companion-runtime:pre-happenings-2026-10-20`.
- Verified on the deployed system with a synthetic user (§14): the full Runtime path with real Sophie, four probe turns, the assembled prompt read back. Mixed results are listed there and are not repeated here.
- Tests: Cortex full suite and Runtime suite green at the commits below (see git log); the end-to-end driver is a manual harness.

## Hardening pass, 2026-10-20 late (measured, then fixed)

- **Latency** (stage timings now in every run bundle, `GET /run/{id}` → `stage_ms`): one consolidation was 167–410 s; the attention agent was the bottleneck (42–270 s; repeated 2500-token no-tool replies from the OpenRouter
  model, unfinished in 2 of 3 runs). Fixes: attention on the flat-rate qwen3.8-27b (27 s, verified); notebook edits overlap the ledger chain; the first read of the ledger/registry is handed to the agent by code. Provider speed varies 3-4x by time of day, so
  wall time stays 2-4 min. **Duplicates:** the same sitting arrived by 2-3 routes (end signal, next-sitting hand-off, idle) with different message ids and was consolidated each time; now deduped by content fingerprint and a replay costs ~1 s, no model calls.
  **During the gap** Cortex reports `pending_consolidations`; the Runtime then shows the previous conversation's last exchanges verbatim ("JUST BEFORE THIS") until the record catches up.
- **Rolling continuity was effectively off in production**: the scene narrator rewrote the sitting state after every turn and erased the stored account. Fixed (`sitting_store.put` preserves it); verified in a real 18-turn sitting across the checkpoint.
  Open to-dos now stay addressable (H-lines) and are re-checked each step. Remaining lag: a correction reaches the summary one 6-message step later (the raw tail carries it meanwhile).
  First-ever conversation depends on the app marking the first turn as a new sitting (`entry_context.chronology.temporalSession`), otherwise no sitting id and no rolling account.
- **Deletion boundary** is in `DATA_LIFECYCLE.md`: Cortex delete is now schema-wide (a real account has rows in 33 tables); `erase_user` removes Cortex + Runtime + Honcho and verifies (waits for Honcho's async queue). Verified empty on 3 synthetic users. Not erased: backups, vendor logs, the empty Honcho peer.
- **Attention**: 5 real follow-ups inspected; free-standing ones are now steered to attach to a happening/pattern/situation (not yet re-measured).
- Reliability after the agent changes: 67/69 checks, 11/12 clean reps (`reports/reliability_20261020_200637.md`); the miss was a past-tense "was due Sunday" left undated (known class).
- Decided to stop full-suite and sweep ceremony for small changes (founder's call): tests only where they guard something that can hurt a user.

## Capability table (first version; see the update above for later additions)

| Capability | Intended | Implemented | Observed |
|---|---|---|---|
| Operational ledger reliability (witness contract, grounded agent, finish gate) | ledger matches what the person said across sittings | yes, deployed `1e63c39`+`6995578` | sweeps: 48/48 ×4 on the pre-time code; with time fields: 66/69 (`reports/reliability_20261020_152023.md`) and 35/36 on the Vinesh fixture (`…_154340.md`); the residual failure is the same mid-step premature close (~1 in 6) |
| Structured time, deterministic views, `schedule` tool | models stop reasoning about "today"; code computes bands | yes (this commit) | busy-day, mixed-plate and dentist fixtures clean in the last sweeps; Runtime packet renders Cortex's text verbatim |
| Stated vs assumed times | reasonable assumptions allowed, never shown as said; actions need stated | yes | assumed labels appear in views; no real reminders fired (attention has no delivery path) |
| Product isolation at the request boundary | no product reads another's data | yes, deployed `6995578`/`7236b0b` | mutation checks: removing each guard fails 1–6 tests; legacy shared credential and non-memory routes still bypass (known) |
| Connected understanding: data, connect pass, deterministic views, endpoints | first working version, inspectable, flag-off | yes (this commit) | three real-model runs (`reports/world_*`): relationship corrections, state changes, first-name resolution, self-anchored relationships work; defects F1–F8 found and fixed; kinship-in-prose leak found in run 3 and only patched in the contract, **not re-verified** |
| Entity-sourced attention intentions | an intention can belong to a situation, expire, be suppressed | yes, unit-tested | not run on a real attention model |
| Runtime: world block, `know` tool, exposure report | foreground gets who/what the person just named, no search | yes, flag off | the real `build_sections` was run on real Cortex output: `reports/sophie_connected_packet_20261020.txt` (the person named Morgan and Priya; both snapshots arrived, with the open status-update matter read live). The **full executor was not run end to end with the flag on** (the canary ran with it off); wiring is covered by unit tests |
| Happenings, dispositions, patterns, pertinent selection | remember what happened and what they like without interpreting; surface a few pertinent items | yes, enabled for the founder | e2e (§14): disposition used for a book recommendation; a romantic incident reached a conversation about Ashley with no direct link; a pattern reached the "mum's again" turn and was used. Retrieval depends on model-written tags (untested at scale) |
| Export / delete | person-level controls | yes; delete takes the owner lock | live-tested on a synthetic user; found and fixed resurrection by an in-flight run; Honcho evidence and Runtime stores NOT covered |
| Continuity retraction | a later correction removes the contradicted sentence | yes (`RETRACT`) | partial: the named sentence dropped, stale hanging bullets stayed |
| Entity-sourced attention on real models | check-ins tied to situations | yes | 1 of 5 real intentions was entity-sourced; the rest free-standing; intents used "he/his" (line added, unverified) |
| In-session continuity assessment | find what rolling continuity loses or distorts | inspected with real packets (40 messages) | stale checkpoint narrative coexists with newer corrections → labelled "Since then…"; root cause (patches cannot retract narrative) **not fixed**; small-model inventions seen |
| Documentation | decisions, status, architecture, evidence, continuation | these files | — |

## Partial, deferred, not done (explicitly)

- Enabled for the founder only. Before anyone else: review `inspect` for their data, a `world_sensitive` decision per product, and full erasure (Honcho evidence, Runtime turn logs/sitting state and queued consolidations are not removed by the delete endpoint).
- Attention has no delivery path; entity-sourced intentions are computed, stored and exposed, never delivered.
- Connect-pass cost not budgeted: observed 6–12 model calls per significant sitting; first sitting once hit the 14-turn cap (`unfinished`, writes stand).
- Replay on real consented sessions, multi-week decay of dormant entities, merge suggestions, curiosity/health-specific handling beyond free-text kinds: not built.
- `rolling_continuity` retraction is partial (D-W17). Consolidation latency is ~6–7 minutes per run, serialised per person, two runs per chat (modality + episode_end): not changed.
- `MEMORY_LEDGER_MODELS=deepseek/deepseek-v4-flash,qwen/qwen3.8-27b`: evidence is directional (8 runs, 0 omissions); not enabled in production.
- Ledger row titles go stale when only detail is updated (e.g. "awaiting results").
- NanoGPT 429s at concurrency >4 fall back to paid OpenRouter (29 paid calls in one overloaded sweep). Production cost risk if volume rises; noted in the runbook below.
- Founder's three ledger rows from earlier solo-sitting output are untouched (ask before editing real rows). Bloom page-set confirmation and Bloom enablement are the founder's.

## Tests at this commit

Cortex `865 passed, 6 skipped (full suite, 6m33s)`; Runtime `554 passed, 12 skipped`. Mutation checks for isolation recorded in `DECISIONS.md` D-O6 / above. The scenario harness (`scripts/eval_world.py`) and the
reliability harness (`scripts/eval_reliability.py`) need a live Cortex and are run by hand against an isolated scratch environment, never against production owners.

## Experiments and where the evidence is

| Question | Method | Result | File |
|---|---|---|---|
| Is the ledger reliable across sittings | `eval_reliability.py`, 4 fixtures, reps | see table above; misses listed per rep | `reports/reliability_20261020_*.{md,json}` (two earlier runs were deleted as **invalid** — harness errors, not behaviour) |
| Does connected understanding work on a realistic story | `eval_world.py`, 3 sittings, real models | run 1 exposed F1–F8; run 2 clean on those; run 3 (Bloom) found kinship leak | `reports/world_20261020_170140.md`, `world_run2.md`, `world_run3_bloom.md` |
| What does in-session continuity lose | `inspect_rolling_continuity.py`, 40 messages, real model | stale narrative vs newer correction; invented lead role | `reports/rolling_continuity_inspect.json` |

## Runbook notes

- Scratch environment recipe (isolated Postgres + `deploy-api:latest` with mounted `src`, env copied minus DB/schedulers; concurrency ≤4; tear down with
  `docker rm -f`, network and directory removal, `shred` of the env copy).
- Never point pytest at the Postgres a live Cortex uses (fixtures drop tables). Cross-owner overlap is only asserted on Postgres.
- Credentials: the Neon credential exposed earlier is still pending rotation by the founder.

## Continue from here (updated)

0. Next highest value: (a) re-verify the unverified contract lines (kinship in prose, ledger-link target, pronouns in attention) with one more e2e run; (b) measure tag quality — are the right records found when the subject changes? —
   on a real week of the founder's conversations; (c) decide whether the Runtime should fire one consolidation per chat instead of two; (d) full erasure path across Honcho/Runtime; (e) tie attention intents to entities consistently.

## Continue from here (original)

1. Founder review of `reports/world_run2.md` / `world_run3_bloom.md` (read the "inspect" sections), then decide on enabling for Sophie only.
2. Re-run `eval_world.py` once to verify the kinship contract line; sweep the Vinesh fixture again if the ledger contract changes.
3. Fix `rolling_continuity` retraction; run the attention agent on entity-sourced intentions with real models.
4. Build export/delete before any sensitive-data product goes live.

## Update, 2026-10-26 (behaviour-first experiments; see DECISIONS D-R1..D-R6)

- Added (tested, 883 pass): `GET /v1/memory/opportunities` (read-only, deterministic, versioned packets by stage), code refusal of relative time words in entity summaries, "next <weekday>" naming both dates, the flagged one-call ledger writer (`LEDGER_WRITER`, default `agent`).
- Not built: anything that consumes the packets (Runtime), Jev's connection-versus-task flag, preparation ahead of time, the five-event log, a fix for asides becoming tracked situations.
- One test fails on main and here, unrelated and time-dependent: `tests/test_attention_cycle.py::test_review_schedules_and_verifies` asserts a date that has passed.
- Evidence and harnesses: `reports/h1_h2_2026-10-26`, `reports/h11_golden_moments_2026-10-26`, `reports/h12_progressive_2026-10-26`, `scripts/golden_*.py`, `scripts/h2_gate.py`, `scripts/progressive_test.py`.
