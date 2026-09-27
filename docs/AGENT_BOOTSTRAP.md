# Agent Bootstrap (operational — 1 page)

> Read before touching anything. Canon outranks everything below.

1. Workspace: `/Users/mukeshkumar/play/`. Stay on `main`. Never clone fresh, switch branches, reset, rebase, stash, or clean — dirty files may belong to another agent.
2. Canon baseline: `6ae9df9` must be an ancestor of HEAD (`git merge-base --is-ancestor 6ae9df9 HEAD`). HEAD ahead is normal. Verify, then report branch + HEAD + status before modifying code.
3. Read order: `synapse-cortex/docs/COMPANION_NORTH_STAR.md` → `docs/COMPANION_CANON.md` → `synapse-cortex/BLITZ.md`. If any is missing: STOP, no substitutes, no replacements, report.
4. Logical tracks (hot-path / behaviour) are NOT git branches. One shared `main`; coordinate via BLITZ.md.
5. Test command: `./.venv/bin/python -m pytest tests/ -q` from `synapse-cortex` (433 collected, ~130s, per-process isolated DBs — parallel runs are safe).
6. Programme state: `BLITZ.md` (cockpit) → `docs/BLITZ_MECHANISM_INVENTORY.md`, `docs/GEMINI_EVAL_PACKET.md`, governor map, eval packets. Blind packets + sealed mappings: judge never sees the mapping.
7. Commit locally, never push unless explicitly authorised. End work with the handoff format in BLITZ.md.
