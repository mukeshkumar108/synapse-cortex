# synapse-cortex

Companion State & JIT Context Compiler Sidecar for **Honcho** & **Sophie**.

## Architecture Overview

`synapse-cortex` operates alongside **Honcho** (`play/honcho`) to provide relational companion state and deterministic follow-up context packets for **Sophie**.

### Memory Rules
- **Memory-worthy -> Honcho:** Raw transcripts, vector embeddings, sessions, static observations.
- **Lifecycle-worthy -> Synapse:** Dynamic expectations, expected windows, suppressions, open loops.
- **Moment-worthy -> Cortex:** JIT context compilation, follow-up packets, prompt surfaces.

## Phase 1 Scope (Expectation Vertical Slice)
Phase 1 implements ONLY the expectation lifecycle:
1. `expectations` table schema (Migration `0001`).
2. Multi-pass extraction pipeline (`turn_extractor`, `expectation_shaper`, `temporal_grounding`).
3. Pure deterministic expectation read model (`expectation_engine`).
4. Event ingestion (`POST /v1/events/turn`) & Follow-up packet (`GET /v1/context/followup-packet`).

## Quickstart

```bash
# Install dependencies
pip install -e .[dev]

# Run tests
pytest

# Start local dev server
uvicorn src.main:app --port 8010 --reload
```
