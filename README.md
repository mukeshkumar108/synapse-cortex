# synapse-cortex

Companion State & JIT Context Compiler Sidecar for **Honcho** & **Sophie**.

## Architecture Overview

`synapse-cortex` operates alongside **Honcho** (`play/honcho`) to provide relational companion state and deterministic follow-up context packets for **Sophie**.

### Memory Rules
- **Memory-worthy -> Honcho:** Raw transcripts, vector embeddings, sessions, static observations.
- **Lifecycle-worthy -> Synapse:** Dynamic expectations, expected windows, suppressions, open loops.
- **Moment-worthy -> Cortex:** JIT context compilation, follow-up packets, prompt surfaces.

## Operational watcher

Production uses a two-stage, model-led watcher: meaning-first loose observations are
lane-shaped into bounded proposals, then deterministic services validate, dedupe,
reconcile, persist and expire them. Honcho remains the semantic evidence substrate.
Cortex stores only lifecycle-worthy state: expectations, time-bounded loops,
suppressions, recurring intentions and occurrence-level completions, and progress on
durable objectives. App/Postgres remains authoritative for chronology and timezone.

## Cross-repository production contract

The canonical full-system handoff is maintained in
`ash-ai/docs/COMPANION_PLATFORM_RUNTIME.md`.

- `ash-ai` / `llm-agent-test` owns authenticated ingress, canonical messages,
  chronology, user operational state and the durable `CortexOutbox`.
- `/api/cron/cortex-delivery` asynchronously sends canonical turns here with
  lease/retry/quarantine semantics; ingestion never blocks the visible reply.
- `companion-runtime` fetches the bounded attention/handshake packet before
  generation and selectively injects relevant continuity as optional context.
- Current user words, explicit corrections and trusted current scene/time outrank
  Cortex. This service does not select HOLD/ENRICH/LEAD/ATTEND, foreground gears
  or the user-visible response.
- Honcho is semantic evidence; Cortex is lifecycle state. Neither is a second
  canonical chat store.
- Explicit getting-to-know-you `sessionMode` is app-owned per-chat authority;
  Sophie's seeded belief spine is runtime-owned persona data. Neither belongs
  in Cortex. Narrative-scene extraction and probabilistic user-pattern
  hypotheses remain deferred until their own extraction and restraint contracts
  exist; do not approximate them as continuity objects.

Do not add foreground prompt directives or duplicate app chronology here. New
scheduled onboarding/product cadence requires its own explicit authority
contract; it must not be inferred merely because remembered information exists.

Set `SYNAPSE_EXTRACTOR_PROVIDER=model` plus either `OPENAI_API_KEY` or
`OPENROUTER_API_KEY`. `SYNAPSE_EXTRACTOR_MODEL`, `SYNAPSE_MODEL_URL`, and
`SYNAPSE_EXTRACTOR_TIMEOUT_SECONDS` are configurable. Model failure is observable and
does not silently fall back to rules. Set the provider to `rules` only for explicit
legacy/smoke-test operation.

## Quickstart

```bash
# Install dependencies
pip install -e .[dev]

# Run tests
pytest

# Start local dev server
uvicorn src.main:app --port 8010 --reload
```
