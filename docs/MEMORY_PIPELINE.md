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

## Deploy checklist (not done from here)

Rebuild/redeploy the Cortex container with this code; confirm VPS env
(`NANO_API_KEY`, `AGENCY_MODELS` — Ling must be reachable; note the pipeline
pins Ling for the handoff via `MEMORY_HANDOFF_MODELS`). The Runtime needs no
flag change: its legacy Sophie calls become instant superseded receipts, and
its memory signals start landing once Cortex is up. Then recover remaining
history via backfill and flip `SOPHIE_LEGACY_INTERPRETER_ENABLED=false` once
one live sitting is observed.
