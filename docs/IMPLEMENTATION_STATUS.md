# Implementation status (memory work, as of 2026-10-20 evening)

Three words are used on purpose: **intended** (the design), **implemented** (code exists, tests pass), **observed** (seen working or failing with real models/data).
Where observed is weaker than implemented, that is the finding. Decisions: `DECISIONS.md`. Architecture and evidence: `CONNECTED_UNDERSTANDING.md`,
`MEMORY_CONTRACTS_2026-10-20.md`.

## Versions, deployment, rollback

| | Commit | On the VPS | Rollback image (taken before this deploy) |
|---|---|---|---|
| Cortex | `{CORTEX_SHA}` (previous deploy `6995578`) | `deploy-api:latest`, built from `{CORTEX_SHA}` | `deploy-api:pre-connected-2026-10-20` |
| Runtime | `{RUNTIME_SHA}` (previous deploy `7236b0b`) | `companion-runtime:local`, built from `{RUNTIME_SHA}` | `companion-runtime:pre-connected-2026-10-20` |

Flags after this deploy: `CONNECTED_WORLD_ENABLED` **off** in Cortex and Runtime (connected understanding is dark). Bloom **off** (`MEMORY_PIPELINE_COMPANIONS=sophie`).
`MEMORY_LEDGER_MODELS` not set (single-model witness, as before). New schema is additive (four tables, a few nullable columns); rolling the images back leaves
the extra tables/columns inert. To roll back: `docker tag deploy-api:pre-connected-2026-10-20 deploy-api:latest` then `docker compose -f docker-compose.vps.yml up -d api`
(Cortex) and the same for `companion-runtime`. To switch the new layer off without a rollback: set the two flags to `false` and restart.

## Capability table

| Capability | Intended | Implemented | Observed |
|---|---|---|---|
| Operational ledger reliability (witness contract, grounded agent, finish gate) | ledger matches what the person said across sittings | yes, deployed `1e63c39`+`6995578` | sweeps: 48/48 ×4 on the pre-time code; with time fields: 66/69 (`reports/reliability_20261020_152023.md`) and 35/36 on the Vinesh fixture (`…_154340.md`); the residual failure is the same mid-step premature close (~1 in 6) |
| Structured time, deterministic views, `schedule` tool | models stop reasoning about "today"; code computes bands | yes (this commit) | busy-day, mixed-plate and dentist fixtures clean in the last sweeps; Runtime packet renders Cortex's text verbatim |
| Stated vs assumed times | reasonable assumptions allowed, never shown as said; actions need stated | yes | assumed labels appear in views; no real reminders fired (attention has no delivery path) |
| Product isolation at the request boundary | no product reads another's data | yes, deployed `6995578`/`7236b0b` | mutation checks: removing each guard fails 1–6 tests; legacy shared credential and non-memory routes still bypass (known) |
| Connected understanding: data, connect pass, deterministic views, endpoints | first working version, inspectable, flag-off | yes (this commit) | three real-model runs (`reports/world_*`): relationship corrections, state changes, first-name resolution, self-anchored relationships work; defects F1–F8 found and fixed; kinship-in-prose leak found in run 3 and only patched in the contract, **not re-verified** |
| Entity-sourced attention intentions | an intention can belong to a situation, expire, be suppressed | yes, unit-tested | not run on a real attention model |
| Runtime: world block, `know` tool, exposure report | foreground gets who/what the person just named, no search | yes, flag off | assembled only through `build_sections` + handler tests; **full executor not run end to end** against the new path |
| In-session continuity assessment | find what rolling continuity loses or distorts | inspected with real packets (40 messages) | stale checkpoint narrative coexists with newer corrections → labelled "Since then…"; root cause (patches cannot retract narrative) **not fixed**; small-model inventions seen |
| Documentation | decisions, status, architecture, evidence, continuation | these files | — |

## Partial, deferred, not done (explicitly)

- **Not enabled for any user.** Enabling needs the founder's review of `inspect` output on a real run, a `world_sensitive` decision per product, and a data export/delete path.
- No user-data deletion/export endpoint (any layer). Needed before sensitive-data products (Bloom wellbeing, health).
- Attention has no delivery path; entity-sourced intentions are computed, stored and exposed, never delivered.
- Connect-pass cost not budgeted: observed 6–12 model calls per significant sitting; first sitting once hit the 14-turn cap (`unfinished`, writes stand).
- Replay on real consented sessions, multi-week decay of dormant entities, merge suggestions, curiosity/health-specific handling beyond free-text kinds: not built.
- `rolling_continuity` retract-on-correction: not built (D-W12).
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

## Continue from here

1. Founder review of `reports/world_run2.md` / `world_run3_bloom.md` (read the "inspect" sections), then decide on enabling for Sophie only.
2. Re-run `eval_world.py` once to verify the kinship contract line; sweep the Vinesh fixture again if the ledger contract changes.
3. Fix `rolling_continuity` retraction; run the attention agent on entity-sourced intentions with real models.
4. Build export/delete before any sensitive-data product goes live.
