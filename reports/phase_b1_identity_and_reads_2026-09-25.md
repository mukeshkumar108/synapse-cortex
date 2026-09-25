# Identity fix + B.1 read-side proof (2026-09-25)

## 1. Claim identity verdict: ChatGPT was right, fixed before readers

As shipped, `semantic_claims` keyed identity by `(workspace, content_hash)` —
one row per normalized wording per workspace. That collapses semantically
distinct occurrences: "I'll call you tomorrow" from Ashley on Monday and from
Sophie three weeks later would have been one row with merged evidence.

Fix (migration `0029_claim_occurrence_identity`, single head):
- Claim identity is now `(workspace, content_hash, source_key)` where
  `source_key` is the birth occurrence (e.g. `honcho_message:m2#candidate:c1`).
  Content hash assists dedupe of the *same evidence replayed*, nothing more.
- Cross-occurrence sameness is a `same_as` relation, never a merge.
- Logical edge identity is content-based `(workspace, from/to content-hash,
  type, subject-keys)` with a partial unique index on active rows: replaying
  the same transition merges; new corroborating evidence grows the edge
  (A.5 "grown" now durable); identical wording with disjoint known subjects
  (Ashley vs Sophie) can never merge — enforced identically in Python and by
  the DB constraint, after the first version proved they can disagree (the
  constraint fired on a case the app rule refused; the rule was wrong-shaped,
  the constraint right — both now agree).
- 0028 was never applied to any database (verified), so 0029 is a clean
  forward fix, no data migration involved.

## 2. B.1 read-side proof (`src/services/semantic_views.py`, pure, unwired)

Seven answers over durable rows, proven with the same deterministic writer
production uses, plus one prod-path integration test (real fulfill + loop
resolve → views). Nothing in packet/attention/projection imports this yet.

| Question | Answer on S1-shaped graph |
|---|---|
| fulfilled? | School trip money (partial excluded by construction) |
| partially fulfilled, still outstanding? | Carlos debt (drops out once settled) |
| resolved? | Florist follow-up (across vocabulary change) |
| waiting on? | Remainder-on-bank-release (sources of wait-edges, unsettled) |
| dependencies? | remainder → debt, one hop |
| superseded/refined chain? | Matías Friday → Thursday revision walk |
| third-party still matters? | Carlos debt (non-self subjects, active edges, unsettled); settled ones excluded |
| disappear-without-delete? | Florist + school rows backgrounded; partial stays foreground |

## 3. Verification
- 12 relation/identity tests + 3 views tests green, incl. the Ashley/Sophie
  separation test and the cross-evidence merge test (4 occurrence rows, 1 edge).
- 78-test regression sweep (violation, bilateral, reconciliation, v4 core,
  object, shadow) green; prod mutation outcomes unchanged.
- Migrations 0028→0029 render clean SQL, single head.

## 4. Still out (unchanged)
Model writer, `restated` predicate, relation-supersede writer, CANCELLED/
NOT_FULFILLED predicates, any foreground read of these tables. The next layer
— task/reminder/calendar/watch/chase/plan/callback/nothing — now has a proven
relation-aware state to read from, which was the gate for building it.
