# Notes landscape fixtures

Two synthetic people, written by a writer model that is NOT the extractor, with the answers written first.

- `tom_sittings.json` + `tom_answer_sheet.md`: 14 sittings over four weeks (Tom Reyes). 35 planted items said in passing, 5 slow signals that should show only as a count across sittings (sleep, work spilling into evenings, Sunday runs, Dad, a daydream that comes back), 8 traps (a joke, a what-if, hearsay, the companion's own reading, a relative time word, two people with similar names). Known fixture faults: the writer called the dog both Biscuit and a spaniel and also named it Callie (the ex), Nell is never said to be Tom's sister, and Mara's birthday is corrected inside the same sitting, so supersession is not tested.
- `bloom_sessions.json`: 11 Bloom-style voice sessions (first reflection, morning, daytime, evening) for Sam: nature walks, a baby cow, a heron, deer at sunset, Mum, Morgan, a coast trip, a cottage-by-the-sea daydream that comes back.
- `run_through_runtime.py`: runs a fixture through the real path (Runtime adapter -> Cortex consolidate) for a disposable synthetic user (`LAB_USER`), inside the companion-runtime container. `score_notes.py`: keyword coverage over the 35 items plus the trap checks, over `GET /v1/memory/notes?view=inspect` output.

Baseline (2026-10-28, qwen3.8-27b via NanoGPT): the existing pipeline kept 34/35 in about 280 model calls and 38 min; one notes call per sitting kept 33-34/35 in 14 calls (~23k tokens, 77-120 s); Bloom's own memory writer 21-24/35. See `docs/DECISIONS.md` D-N1.
