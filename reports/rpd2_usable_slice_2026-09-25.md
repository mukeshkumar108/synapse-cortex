# Usable RPD2 slice: character switching + actor-model routing (2026-09-25)

No new architecture. Product path made controllable: dropdown selection
reaches the foreground actor, fallbacks are loud, traces show requested vs
actual, characters resolve to profiles.

## Character roster migration status

- Fully migrated (mechanical speaker contract on shared runtime):
  `elena-voss`, `isabella-morales` (new), `sophie`.
- Persona/voice/kernels/canon stay in RPD2 for all characters (never copied).
- Missing (raise unknown-companion, never substitute): arabella-whitcombe,
  audrey-vale, lila-harper, mia-voss, natalie-hayes, raven-kane,
  sophia-bennett, sophie-laurent, yuki-sato. One mechanical profile each
  when their turn comes; no per-character runtime stacks ever.

## Model dropdown wiring

- RPD2 `buildForegroundTurnInput` now carries the entitlement-guarded
  dropdown selection (`resolvedChatModel`) as `selected_model_id`, plus the
  resolved `characterId` (was hardcoded `elena-voss`/`chat-model`).
- Runtime lane decision: explicit (non-alias) selection tries FIRST for
  foreground generation; lane default becomes fallback. Internal models
  (Jev, extraction, judges) never read the field. Alias selections
  (`chat-model` etc.) keep prior lane behavior byte-identical.
- Eligibility extended to `isabella-morales` behind its own flag
  (`RPD2_RUNTIME_FOREGROUND_ISA`); repair exclusion unchanged.

## NanoGPT actor routing (verified live, all 4 historical IDs present)

296 models listed; `MeroMero-v2`, `doubao-seed-character`, `DarkIdol`,
`deepseek-v4-flash` all live. Requires `NANO_API_KEY` + `NANOGPT_ENABLED=true`
in the runtime process env (not committed anywhere).

## Fallback semantics

- Invalid/dead ids fall through lane default → env fallback LOUDLY
  (`requested_model_unavailable` provenance + warning), never fail the turn
  silently, never route to the Jev model. Abort semantics untouched.
- Trace shows requested model, actual `speaker_model`, `fallback_used`,
  candidate chain.

## Live receipts (real models, evaluation namespace)

- Elena + MeroMero-v2 → served by MeroMero-v2, no fallback.
- Isa + deepseek-v4-flash → served by DeepSeek, no fallback.
- Elena + bogus id → served by lane default, `fallback_used: true` + flag.
- Elena + DeepSeek (switch) → served by DeepSeek (model switching proven).

## Gaps blocking tonight

- None for Elena/Isa via API path with keys present. RPD2 TS unit tests
  not runnable here (no node toolchain); TS edits are minimal and reviewed.
- Frontend itself not clicked (no browser); API-path verified end to end.
