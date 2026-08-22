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
