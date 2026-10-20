# Decisions (Cortex memory work, October 2026)

Each entry: what was decided, why, what was rejected, and what would change our mind. Newest area last. "Evidence" points at files in `reports/` or tests.
IDs are stable; supersede an entry by adding a new one that names it.

## Operational memory (ledger)

**D-O1 — Failures were interface failures, not model randomness.** Production traces showed the same witness signal producing three agent behaviours,
`create_item` unable to carry a date, one observation silently dropped, and an evaluation that reported only the last fault. Fix the contracts (numbered
observations, ENDED vs CHANGED, full-state `create_item`, finish gate with accounting), not the prompts alone. *Rejected:* a deterministic verifier that
re-derives truth after the agent (would resurrect superseded dates and put meaning in code); a bigger model as the first move. *Revisit if:* clean-rep rate
falls below ~5/6 on the sweep. Evidence: `docs/MEMORY_CONTRACTS_2026-10-20.md`, `reports/reliability_20261020_*.md`.

**D-O2 — Structured time on the record; exact instants derived on read.** `expected_date`, `expected_time` (HH:MM local), code-stamped `time_zone`,
model-set `time_role` (happens|deadline), `time_basis` (stated|assumed), `importance`. Views (bands: imminent/today/overdue/check-up/waiting/week/later/
undated/older) are computed by code from these every time; the model never reasons about "what is today" again. *Rejected:* re-asking a model to rank
urgency per turn; storing relative words.

**D-O3 — "Reason freely, record uncertainty faithfully" replaced "never guess am/pm".** A blanket prohibition removed useful reasonable readings. The record
now carries WHAT IS KNOWN: `time_basis=assumed` plus the person's exact words and an open question; assumed times are labelled in every view and **actions
(reminders) require a stated time**. *Rejected:* forbidding assumptions; presenting assumptions as facts. Evidence: ledger view tests; chatgpt-review note in
the 2026-10-20 conversation.

**D-O4 — Scheduled-event-passed is not overdue; deadlines are.** A meeting whose time passed with no word is "ask how it went", not "overdue". Closed rows age out
of views after 3 days.

**D-O5 — The deterministic fallback runs only if the agent wrote nothing.** After partial writes the run is flagged `ledger_needs_review` and the agent's
state stands (a second pass used to overwrite correct work).

**D-O6 — Product isolation at the request boundary.** The product is derived from its credential (`SYNAPSE_PRODUCT_TOKENS`), the workspace is
`<product>::<workspace>` (Sophie unprefixed for compatibility), routes are default-deny, the Runtime sets one product context at the entry. Bloom stays
disabled until sign-off. *Rejected:* per-product database; trusting a `product` field in the body. Known holes: legacy shared credential and non-memory
routes bypass the boundary; Honcho has a single API key.

## Connected understanding

**D-W1 — A separate layer, linking to the ledger rather than copying it.** Entities/links/situations are their own tables; operational facts stay in the
ledger and are read live through `KnownLink(target_kind=ledger)`. *Why:* a copied date is a second source of truth that goes stale (observed in design
review; verified by `test_a_state_change_in_a_source_record_shows_up_with_no_model_and_no_copying`). *Rejected:* making entities ledger rows; making the
ledger an entity graph; a single "memory graph" table.

**D-W2 — Models decide meaning, code validates and renders.** One tool-using agent (the connect pass) decides identity, relationship, supersession, merge;
code refuses invalid calls and enforces evidence rules. Retrieval is deterministic nomination + rendering. *Rejected:* a fixed relationship/kind
vocabulary (kinds and relations are free text; only "situation-like" kinds get situation treatment, and that list is a mechanical flag); a model call on every
mention. Honours the standing rule "determinism never replaces semantics".

**D-W3 — Epistemic status is carried per entity and per link, shown in every view.** `stated` requires a quote that appears verbatim in the **person's own lines**
(not the assistant's); otherwise `inferred`, rendered "(inferred, not confirmed)". Corrections supersede, never overwrite (history shown as "Earlier
understanding"). *Rejected:* a confidence number; silently promoting inference after repeated mention.

**D-W4 — A reserved `self` entity ("the person").** Added after the first real-model run attached the user's own relationships to a project. Created by code,
not editable by the model, excluded from overview/mentions. *Rejected:* letting the model create its own self-entity (it chose a project); a free-text
`relation_to_user` column on every entity (loses direction and history).

**D-W5 — Mentions are nominations by alias, plus first name for people; ambiguity is reported, not resolved.** *Why:* "Morgan texted" must find Morgan Ellis
without a model; two Morgans must not be guessed between. *Rejected:* embedding/semantic search (cost, opacity, no evidence it was needed); resolving
ambiguity by recency.

**D-W6 — Exposure is not engagement, and both are separate from state.** Five states kept distinct: state, computed cue, durable intention, exposed in a
packet, raised/responded. Exposure counts once per 45-minute sitting window; a situation shown ≥3 sittings with no engagement and untouched ≥3 days drops out
of the overview. *Rejected:* demoting by number of turns; deleting un-engaged situations.

**D-W7 — Suppression is of prompting, not of memory.** `suppressed` removes an entity from the overview and from pending attention; the record, links and
inspect view remain. The person saying "don't bring that up" must be honoured without destroying what we know.

**D-W8 — The connect pass runs after the ledger, in its own session, fail-open, behind a flag defaulting to off.** It writes new categories of personal
data (family, health-adjacent), so enabling for users needs the founder's explicit review. Deployed dark. *Rejected:* running before the ledger (it needs the
ledger keys to link to); a shared session (a rollback in the world pass once poisoned the consolidation session — observed, `MissingGreenlet`).

**D-W9 — Evidence is whole-quote or nothing.** First implementation reused the ledger's span-splitter, which split on apostrophes and stored stitched
fragments ("s got a chest infection that won / re waiting…"). Replaced by exact normalised containment; no repair. *Rejected:* fuzzy matching (would let
paraphrase pass as quotation).

**D-W10 — The agent can undo its own supersede (`restore_link`) and sees what it retired.** Observed: a dentist link retired with a note about Morgan.
Making the mistake visible and reversible was chosen over a semantic validator in code. *Rejected:* refusing supersedes without a second model opinion
(extra call, still model judgement).

**D-W11 — The Runtime carries the layer as plain factual blocks, plus a `know` tool for depth.** No directives ("be careful with X"); the companion model
decides. One GET per turn, 3s timeout, fail-open. Placement: after continuity, before operational awareness. *Rejected:* injecting full snapshots for every
entity each turn; putting instructions in the block.

**D-W12 — In-session continuity: label, don't rewrite (for now).** Real packets showed a stale checkpoint narrative next to a newer correction. The cheap,
safe fix is to label the later lines "more recent; where this differs … this is current". Letting a patch retract narrative text is a larger change to a
module outside this workstream's remit and was deferred. *Revisit if:* the foreground is seen to follow the stale line.

**D-W13 — Honest scope.** Not built: user-data export/delete, replay on real consented sessions, entity-intention evaluation on real attention models, merge
suggestions, decay of dormant entities, health-observation-specific handling beyond free-text kinds. Listed in `IMPLEMENTATION_STATUS.md`.

## Process decisions

**D-P1 — Scratch environment for every model-backed experiment.** Isolated Postgres + the production image with mounted source, keys copied minus DB/
schedulers, torn down afterwards; concurrency ≤4 (higher caused NanoGPT 429s and paid OpenRouter fallbacks). *Rejected:* testing on production with test
owners (pollution risk); mocking models (hides exactly what we were measuring).

**D-P2 — Report failures, including the ones that moved.** Sweep reports keep every miss; two invalid runs were deleted *because they were invalid*
(harness error, not behaviour) and that is stated in `IMPLEMENTATION_STATUS.md`.
