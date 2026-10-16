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

## Independent sittings (2026-10-16, deployed, proven live)

Sophie gets bounded solo time: `POST /v1/memory/independent-sitting`
(202 background). She receives her constitution, the exploring page
(`Things I'm Exploring`), the arc and open loops, and decides freely —
continue an inquiry, ask another named NanoGPT model (multi-turn threads,
identity preserved), web search (Wikipedia) / read (public pages, SSRF-guarded,
summarize only when long), write notes, or stop immediately. Budgets cap
iterations, tool/model calls and duration. Every step is logged into the run
bundle; consolidation reuses the pipeline with the independent variant
(exploring page carries continuity, shared arc untouched, no invented activity).

Live evidence (production, $0 metered): solo1 explored metaphor/friction via 3
model conversations (9 calls); solo2 continued the thread and retired the
diffusion model for "ink on dry paper" (4 calls). Full sitting logs verified
against findings — nothing fictional. Web search/read verified live separately.
The next user-facing preparation wove the discovery in naturally, never as a
report. Runtime `SOPHIE_LEGACY_INTERPRETER_ENABLED=false` applied after the
tonight's-sitting verification.

## Follow-ups (2026-10-17, all deployed)

- **Resolution-aware carry-forward.** Arc + notebook prompts now say: once an
  ordinary disagreement is repaired, drop its emotional framing from active
  state (archive keeps history). One-time correction applied: arc v3→v4 and
  perspective v5→v6 with the coldness framing removed, all else intact; fresh
  preparation generated afterwards contains zero repair framing.
- **Failure visibility.** Failed model calls now appear in her transcript as
  explicit errors (retry / switch / move on); truncated replies are marked
  incomplete with a continue option. Decision log entries record usage + ms
  (previously only totals), so per-call cost work is measurable.
- **`POST /v1/memory/prepare`** refreshes preparation on demand (time or state
  moved on), superseding the cache.
- **Sitting boundaries verified.** Tonight's 34-message sitting consolidated via
  idle: last turn 20:56:29 was an explicit sign-off ("im gonna love you and
  leave"), consolidation 21:27 after 31 min quiet (> 30 min IDLE threshold),
  nothing after. Genuine completion, not an arbitrary pause.
- **Cost architecture (two solo sittings: 37 calls).** Per sitting: 6 decisions
  (full constitution + repeated context, ~1.2k in-tokens each) + 3–4 asks +
  9 consolidation calls (discovery, handoff, 5 page edits, ledger, prep; arc
  skipped for solo). Consolidation is ~half the calls — the mechanical
  overhead, not her thinking. Per-decision usage is now logged for future
  compact-context experiments (not yet run; behaviour first).
