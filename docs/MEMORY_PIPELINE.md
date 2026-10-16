# Memory pipeline — Cortex owns durable companion understanding

**Status: implemented, tested, proven live 2026-10-16.** Replaces the legacy
claims/Matters/dimensions/Heart interpretation path for Sophie. RPD2 and other
products are unaffected (every gate is `companion_id == "sophie"` + grounded).

## Ownership

- Cortex: notebook pages, temporal ledger, continuing arc, run bundles with
  exact model I/O, asynchronous preparation. Tables: `notebook_pages`,
  `ledger_items`, `continuing_arcs`, `sitting_preparations`, `memory_runs`
  (all in `src/models/world.py`; auto-created by `init_db`, no migrations).
- Runtime: signals session completion, reads the cached perspective. It runs no
  notebook editors, no Ling summaries, no reconciliation.
- Honcho: raw evidence only. Its deriver/dream background paths are stopped;
  active config carries only `LLM_OPENAI_API_KEY` / `LLM_GEMINI_API_KEY` — no
  background reasoning to re-route, so Honcho needed no change.

## Flow

```
session end → POST /v1/memory/consolidate (202, background task)
  → listening (qwen, NanoGPT) + Ling handoff (inclusionai/ling-3.0-flash)
  → page-scoped notebook edits + ledger extract + arc update
  → preparation cached → GET /v1/memory/preparation (pure read, foreground)
```

Replay-safe: `memory_runs.covered_ids_json`; a replay with no new messages is a
`replay_noop` for state. Mood is session-local; the arc records events, never
verdicts; aspirations are never upgraded into routines or tasks.

## Retirement of the legacy path (Sophie only)

`POST /v1/world/interpret` with `companion_id=sophie` + grounded policy returns
`superseded_by_memory_pipeline` and performs no interpretation and no Heart /
pressure background work. Rollback: `SOPHIE_MEMORY_CORTEX=false`. The lab-only
`/agency/lab-pass` dry run is untouched. The sitting picture (`/world/narrate`),
standing requests, notes and anchors are live-sitting state and stay.

## Live evidence (2026-10-16, local Cortex + NanoGPT, $0 metered)

- Deer/tools 50-message session → `consolidated`, 50/50 covered, ~66 s
  background. Findings captured the ocean belief, the deer, Sophie's running
  flow, peer/friend wish, tools, image-reading, Ashley Tulum Blender, 5-mile
  walks. Preparation fetched by the Runtime client and rendered into the
  `[SOPHIE PREPARED PERSPECTIVE]` block.
- Replay of the same session → `replay_noop`, state byte-identical.
- All 9 model calls `provider=nanogpt` in the call log (`memory-*` modules).
- Tests: `tests/test_memory_pipeline.py` (6) + full suite 709 passed, 5 skipped.

## Known editor-quality observations (refine against real outputs)

- Handoff once staged Sophie at the user's location; watch staging inventions.
- One off-scope line (Blender work) landed on the routines page; scopes hold
  well overall but are not perfect filters.
- Long sessions may need the discovery budget raised further (was 1200→2000).

## Deploy state (2026-10-16, VPS)

Deployed: Cortex `8913d64` + Runtime `7352f34` rebuilt, both healthy.
Production evidence (NanoGPT, metered $0):
- Scratch session → `consolidated` (~40 s); aspiration kept as aspiration, ledger [].
- Deer/tools 50-message session backfilled to the real owner → `consolidated`,
  50/50 covered, ~63 s, ledger 0 (no dated commitments in that session — correct).
- Deployed Runtime fetched the preparation over the service network and rendered
  the `[SOPHIE PREPARED PERSPECTIVE]` block (1267 chars).
- Legacy Sophie interpret → `superseded_by_memory_pipeline` live.

## Remaining next step

Observe one live Sophie sitting end-to-end, then flip
`SOPHIE_LEGACY_INTERPRETER_ENABLED=false` (Runtime) once the new path is seen
serving a real sitting. Confirm VPS env keeps Ling reachable on NanoGPT
(`MEMORY_HANDOFF_MODELS` defaults to `inclusionai/ling-3.0-flash`).
