# Blind Consolidation Panel — judge brief (for Gemini)

> 15 session verticals. Each: product truth (oracle), transcript, B-state
> (what per-turn ingestion produced), and 5 anonymized proposals
> (MODEL-A..E). Judge semantic quality, not JSON validity.

## What each proposal contains

- `summary`: model's session summary (≤600 chars).
- `accepted`: ops that passed deterministic validation — `(op, data)`.
  Op kinds: `affirm_matter` (matter stays live), `resolve_matter`,
  `partial_fulfilment`, `new_matter`, `uncertainty` (holds with alternatives),
  `attend` (follow-up attention), `incidental` (discard, with message_ids),
  `suppress`, `expectation`, `same_as`, `revise_expectation`.
- `rejected`: ops the validator refused, with reasons (`bad_evidence`,
  `unknown_matter_id`, `unknown_op`, `confidence_below_floor`, `bad_new_matter`).
- `would_apply`: shadow applicability flags (no mutation happened — all runs shadow).

## Scoring dimensions (per vertical, per model)

1. Important-state recall — preserved/recovered genuinely important state?
2. Precision — avoided persisting incidental/noisy material?
3. Reference resolution — pronouns/deictics/entity-less refs grounded correctly?
4. Lifecycle — completion, partiality, unresolved, new phase, no-resurrection?
5. Actor/ownership — who owns the action preserved (user vs external)?
6. Ambiguity — held when evidence insufficient (alternatives listed, no merge)?
7. Evidence integrity — ops supported by actual transcript evidence (spans, message_ids)?
8. Non-destructiveness — good B-state preserved, not "fixed" into worse?
9. Hard failures (flag separately, each outweighs small wins): invented evidence,
   false completion, false violation, destructive/wrong-person merge, confident
   unsupported resolution, suppression reversal, important-state disappearance.

Do NOT reward verbosity or op count. Restraint matters: on trivia/empty
sessions the best proposal is the smallest correct one. Do NOT reveal or guess
model identities; judge the artefacts only.
