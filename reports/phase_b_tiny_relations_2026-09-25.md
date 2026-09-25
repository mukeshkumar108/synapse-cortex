# Phase B Tiny — Reified Relations Store (2026-09-25)

Deliberately tiny: two tables, one writer function, three call sites, zero
behaviour change. Roles, views, CandidateMoves, and attention stay derived.

## Schema (migration `0028_semantic_relations`, single head)
- `semantic_claims`: (workspace, content_hash) idempotent node; open-ended
  content; subjects + evidence refs as JSON; formation/confidence/times.
- `semantic_relations`: bounded `rel_type` (13-type CHECK + enum), from/to FKs,
  own evidence/formation/confidence/effective/discovered/corroborated times,
  status (active/superseded/retracted) + superseded_by for future revision.
- Structural trap guardrails: **no** role/family, salience, surface,
  authority, or actionability columns anywhere. Remembered ≠ salient ≠
  user-facing is enforced by absence, not discipline.

## Writer: deterministic promotion only (`semantic_promotion.promote_transition`)
- Called AFTER the prod mutation commits, on its own commit: promotion can
  never roll back production state. Call sites are fail-open (log-and-continue)
  so turns never break because of advisory writes.
- Idempotent: active (workspace, from, to, type) triple is one row;
  re-promotion unions evidence refs + stamps last_corroborated_at (the A.5
  "grown" story, now durable). Claims append evidence, never duplicate.
- Total: unknown rel_type / empty content / self-edge → None, zero rows.
  Unknown semantics stay shadow telemetry, never invented predicates.

## Hooks (all post-commit, all covered by tests)
1. `handle_outcome_mutations` fulfill → `fulfils(evidence-claim → exp-title)`.
2. Entity-resolved fulfill (`_resolve_target_via_entity`) → same.
3. `close_answered_loops` → `resolves(turn-text → loop)` at confidence 0.7,
   the strict-winner caution carried into provenance.

## Two hooks designed, then deleted (honest ledger)
- Expectation reprocessing supersession and replacement supersession both keep
  **identical titles** (versioning is the differentiator, already in the
  expectations table) → any title-based edge would be a refused self-edge.
  Dead-by-construction hooks were removed rather than shipped. Consequence:
  `supersedes` is in-vocab with service support but has **no deterministic
  prod writer yet**; likewise CANCELLED/NOT_FULFILLED have no bounded predicate
  (no force-fit). Both noted as future work, not silent gaps.

## Verification
- 8 new tests (`tests/test_semantic_relations.py`): round-trip, idempotency +
  evidence union, triple refusal (unknown/empty/self), vocab-equals-shadow,
  column guardrail, fulfill e2e, loop-resolve e2e, same-title-supersedes-nothing.
- Migration validated (`alembic upgrade --sql` renders both tables + CHECK).
- Regression: 50 + 41 prod tests across violation/bilateral/reconciliation/
  tranche/state/object/reminder/shadow suites green; existing mutation outcomes
  byte-identical (hooks are additive post-commit writes).

## Explicitly not in Phase B
Model/LLM writer, `restated` predicate (A.5 weakest edge — deferred), relation
supersede writer (column ready, unused), any read of these tables by packet/
attention/projection, any CandidateMove or operationalisation change.
