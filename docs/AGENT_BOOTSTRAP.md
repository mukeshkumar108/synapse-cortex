# Agent Bootstrap (operational — 1 page)

> Read before touching anything. Canon outranks everything below.

1. Workspace: `/Users/mukeshkumar/play/`. Stay on `main`. Never clone fresh, switch branches, reset, rebase, stash, or clean — dirty files may belong to another agent.
2. Canon baseline: `6ae9df9` must be an ancestor of HEAD (`git merge-base --is-ancestor 6ae9df9 HEAD`). HEAD ahead is normal. Verify, then report branch + HEAD + status before modifying code.
3. Read order: `synapse-cortex/docs/COMPANION_NORTH_STAR.md` → `docs/COMPANION_CANON.md` → `synapse-cortex/BLITZ.md`. If any is missing: STOP, no substitutes, no replacements, report.
4. Logical tracks (hot-path / behaviour) are NOT git branches. One shared `main`; coordinate via BLITZ.md.
5. Test command: `./.venv/bin/python -m pytest tests/ -q` from `synapse-cortex` (433 collected, ~130s, per-process isolated DBs — parallel runs are safe).
6. Programme state: `BLITZ.md` (cockpit) → `docs/BLITZ_MECHANISM_INVENTORY.md`, `docs/GEMINI_EVAL_PACKET.md`, governor map, eval packets. Blind packets + sealed mappings: judge never sees the mapping.
7. Commit locally, never push unless explicitly authorised. End work with the handoff format in BLITZ.md.

## Parallel-agent working discipline

> Why this exists: earlier agents returned important research in chat without
> landing it in the repo, so later agents believed the work did not exist.
> A result is **not available** to other agents until it is landed below.

8. Read before acting: this file → `docs/COMPANION_NORTH_STAR.md` →
   `docs/COMPANION_CANON.md` → `BLITZ.md` → the research programme doc that
   owns your task (e.g. `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md`) →
   the reports it names. If a named report is missing from the repo: STOP on
   that dependency, report it, do not reconstruct it from memory or chat.
9. Shared `main`, dirty worktree is normal. Never reset, clean, stash,
   rebase, or overwrite. Touch only files your task explicitly assigns you;
   never sweep up, move, or "tidy" another agent's files.
10. Two kinds of output, never confused:
    - **CHAT-ONLY RESEARCH** — discussion, drafts, provisional analysis.
      Useful, but no later agent may treat it as evidence or prior work.
    - **CANONICAL RESEARCH ARTEFACT** — a report, fixture, or result file
      committed to the repo at a stated path. Only this counts downstream.
11. Landing rule: reports, fixtures, and results needed by later agents must
    be committed (new files under `reports/` or `docs/`, or a task-specified
    path). Your completion report states: canonical path(s), commit hash,
    and confirmation that only owned files were committed. No path + no
    hash = work did not happen, however good the chat summary.
12. Scratch (tool outputs, emissions, scorers) may live outside the repo
    (e.g. `/tmp/...`) but must never be load-bearing: nothing downstream may
    depend on a path that is not committed. Note scratch locations in your
    handoff so synthesis can verify, then delete.
13. Private stays private: transcripts, backups, and source DBs remain under
    gitignored boundaries (e.g. `replay-private/`). Commit only synthetic,
    redacted, or safely derived fixtures. Never copy full private
    trajectories into committed files.
14. Isolate side effects: experiments needing a database copy, replay DB,
    branch, or worktree use a separate copy/location, never shared or live
    state. Report where it lives and whether it must be preserved or can be
    deleted. Migrations or production mutations require explicit programme
    authority — never assume it.
15. If the canonical artefact for your dependency is missing and its
    originating agent is still available, ask for it to be landed. Do not
    silently rebuild another agent's experiment from chat memory.
