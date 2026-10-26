# H11 golden moments, 2026-10-26 (scratch stack, flat-rate NanoGPT only)

Scenarios and expected behaviours: `scripts/golden_moments.py` (fixed before any run). Runner: `scripts/golden_run.py`. Two blind judges (qwen3.8-27b, kimi-k2.6), each shown everything the person actually said.

- `golden_20261026_131415`  run 1, 2 replies per cell. SUPERSEDED: judges had not seen the unrelated sessions; the structured arm lacked the world section (runner bug).
- `golden_20261026_132454`  run 2, 4 per cell: none, every note, notes plus small selector, Cortex as served, a first re-render (v2; it mislabelled every happening "happened" and printed raw timing text).
- `golden_20261026_133052`  run 3, 4 per cell: selector control (unstable: 22/28 then 16/28) and the v3 read-side render.
- `golden_20261026_141839`  run 4, 8 per cell, after re-consolidating with the write-side fixes: none, selector, Cortex as served, and the real `/v1/memory/opportunities` endpoint.

Every generated reply, with both judges' reasons and the exact block each arm was given, is in the .md files.
