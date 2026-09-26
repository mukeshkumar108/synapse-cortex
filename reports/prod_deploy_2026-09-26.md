# Prod deploy record (2026-09-26 ~00:30 UTC)

Pushed: companion-runtime → origin main (`351ed35`); synapse-cortex → origin
main (`48f279b`); rpd2 → origin main (`825aeb2` + `2cbd0c3`, Vercel auto-deploys).

## VPS (`161.97.150.246`)

- companion-runtime: pulled, rebuilt, restarted — healthy. Env added:
  `JEV_DISPATCH_ENABLED=1`, `RPD2_RUNTIME_FOREGROUND=elena-voss,isabella-morales`.
  Pre-existing: `NANO_API_KEY`, `NANOGPT_ENABLED=true`, `OPENROUTER_API_KEY`.
- synapse-cortex: pulled, rebuilt, restarted — healthy. Migration chain single
  head `0030_current_scene`; stamped (DB predates migration discipline).
- Prod DB (Neon) repairs (pre-existing drift: tables created via create_all,
  columns never backfilled, alembic stuck at 0017):
  - 4 tables created: semantic_claims, semantic_relations, current_scenes,
    scene_epochs.
  - 8 columns backfilled: expectations.formation/effective_at,
    open_loops.invited, suppressions.owner_peer_id/review_note,
    commitment_candidates.uttered_at/resolution_evidence.
  - Fixed `src/models/__init__.py` to import ALL models (commitment_candidate
    and work_item were missing → metadata-blind tooling). Committed locally;
    NOT yet pushed (do with next cortex push).
- Fixed by tuning, not code: `SYNAPSE_MEANING_TIMEOUT_MS=12000` (1.5s default
  starved the revise-sync model call; container restarted to apply).

## Live verification (prod, real models)

- Elena + MeroMero-v2 → served by MeroMero, in character.
- Isa + deepseek-v4-flash → served by DeepSeek, in character.
- Bogus model id → lane default with `fallback_used` + loud flag.
- revise-sync → HTTP 200 with real revision (was failing: schema drift +
  timeout, both fixed).
- Zero errors in cortex logs post-fix.

## Left for the user

- Vercel should auto-deploy RPD2 from origin main; verify in dashboard.
- `src/models/__init__.py` model-registration fix is committed locally in
  the VPS? No — it was made LOCALLY (this machine), uncommitted. Push with
  next cortex change set. (VPS runs committed code; the fix is not live
  there yet — harmless: only affects metadata completeness tooling.)
