# Jev consumer + semantic reactivation (Cortex side, 2026-09-25)

Companion to the runtime shared dispatcher. Cortex consumes flags; it does
not run a second dispatcher.

## What changed (all additive, fallback-safe)

1. **`turn_selection(jev_flags=...)`** — shared-dispatcher gear defaults
   posture (`hold/follow/lead/repair`); unknown/absent gear keeps local
   derivation untouched (offline-safe). Output gains `compiler_flags`
   (gear/initiative/memory_scope/domains/reasoning_need/posture) for prompt
   assemblers. Budgets/arbitration unaffected by flags.
2. **Semantic reactivation** — counting still owns cooldowns, but a
   suppression with a reopen condition whose target row changed after the
   suppression is eligible again (`reactivated_by_new_evidence`), computed in
   the working-set compiler (has DB) from row `updated_at` vs suppression
   `created_at`. Strong dismissals (no reopen condition) never reactivate;
   topic-only suppressions rely on user-overlap piercing as before.

## Verification

- 16 attention-controller tests green, incl. flags-override/fallback and
  reactivation cases.
- Full Cortex suite green (369 passed).
