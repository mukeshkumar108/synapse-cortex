# Semantic-boundary inventory (Runtime + Cortex live paths)

Rule: deterministic code validates, grounds, canonicalises, expires, renders. Models decide open-ended meaning. A cheap lexical step may NOMINATE
candidates for a model; it never decides. No code was changed for this audit except keeping `WORLD_DELTA_ENABLED` off.

Classes: **MECHANICAL** (operation over already-decided meaning) · **POLICY** (explicit authored constraint, threshold or budget) ·
**SEMANTIC** (open-ended judgement about meaning, intent, relevance, continuity, relationship, trajectory) · **MIXED**.
Verdict: OK · POLICY-OK (explicit, should be documented/configurable) · **VIOLATION** (semantic judgement made by hand-written code) ·
UNREAD (not yet traced; not claimed clean).

Method: read the function bodies below (not docs). ~45 decision points across both repos. Read list at the end.

## A. New world path (written this week)

| # | Decision | Where | Mechanism today | Class | Who makes the semantic call | Verdict |
|---|---|---|---|---|---|---|
| A1 | What a plausible repair path is / what the trajectory note says | `world_materializer.default_trajectory_note` | Fixed English template ("toward honesty or reconnection") | SEMANTIC | Hand-written string. `note_writer` hook exists, nothing supplies it | **VIOLATION** |
| A2 | Whether a character is at risk / drifting | `_reconcile` | Thresholds the extractor's own `state` labels; "any at_risk objective => character at_risk" | SEMANTIC | Flash Lite label, then a rule | **VIOLATION** |
| A3 | Which objectives exist, their cause, state, conflicts | `_objectives`, producer | Flash Lite is sole author, no reconciliation; identity = hash of normalised wording (paraphrase duplicates, latest extraction overwrites state) | SEMANTIC | Cheap model with authority | **VIOLATION** |
| A4 | Whether two objectives conflict | producer `conflicts_with` | Whatever the cheap model lists | SEMANTIC | Cheap model, no judge | **VIOLATION** |
| A5 | Does this need continuity (Matter admission) | `_matters`: `CONTINUITY_MEMBER_KINDS`, `CONTINUITY_MATTER_KINDS` | Hard-coded kind lists | SEMANTIC | Hand-written category list | **VIOLATION** |
| A6 | Auto relationship Matter + its title | `_matters`: `RELATIONAL_KINDS`, `RELATIONAL_LABEL`, `RELATIONAL_PRIORITY` | If any member is a listed kind, create one; title from a fixed English label table | SEMANTIC | Hand-written list/table | **VIOLATION** |
| A7 | Relationship dimension vocabulary | `world_delta.DIMENSIONS` (schema Literal) + producer normalise | Closed set of 8; anything else dropped | SEMANTIC (ontology) | Hand-written list | **VIOLATION** |
| A8 | Who is unaware of a concealment | `_derive_awareness` | Rule keyed on the narrative kind "concealment"; concealer = holder name, else whichever name appears first in the text | SEMANTIC | Hand-written rule + text position | **VIOLATION** |
| A9 | Is a claim "just a quote" | `_is_quote` | English first-person regex + substring | SEMANTIC | Hand-written regex (English-only; "I love you" can be real relational state) | **VIOLATION** |
| A10 | Are two events the same occurrence | `_similar_event` | `difflib` ratio thresholds 0.9 / 0.6 / 0.75 over labels, subset of participants, string equality of time/place | SEMANTIC | Hand-picked thresholds | **VIOLATION** (nominate only; a model decides) |
| A11 | Which relational narrative kinds reach the foreground brief | `_BRIEF_NARRATIVE` in `build_continuation` | Closed list; emotional_state/perspective can never appear | SEMANTIC | Hand-written list | **VIOLATION** |
| A12 | Brief selection/ordering/truncation | `build_continuation` | Sort by confidence, take 4, truncate at 900 chars | MIXED | Code chooses which meaning is shown | **VIOLATION** until a model composes and code only stores/renders |
| A13 | Constitutional objective text | `world_checkpoint.RELATIONSHIP_OBJECTIVE`, `delta.constitution`, `_constitution` | One global env string, stamped into every delta, overwritten in Cortex from the delta each checkpoint | POLICY | Product config, but travelling through extraction output and not per character | POLICY, **wrong channel** |
| A14 | Grounded-policy downgrade | `_assistant_asserted` | By speaker role; applies to claims only (not events/narrative); commitments pass | POLICY | Product policy, incomplete coverage | POLICY-OK, **incomplete** |
| A15 | Claim kind for a claim | `_claims`: `"attribute" if predicate and subject is actor else "assertion"` | Rule | MIXED | Hand-written | VIOLATION (minor) |
| A16 | Speaker attribution repair | `_repair_holder`, Runtime `repair_attribution` | Message role is a fact; Runtime version also regex-matches English leading names | MECHANICAL / MIXED | Role fact; regex on names | OK (Cortex) / minor (Runtime regex) |
| A17 | Evidence ids exist, span verbatim, schema, refs, provenance, supersession bookkeeping, `possible_same_as` linking | materialiser | Deterministic | MECHANICAL | n/a | OK |
| A18 | `covered_through` | `build_world_layer` | Keyed by producer name only (latest run), no stages; Runtime reads it nowhere, so nothing retires on it today | MECHANICAL | n/a | Claim "per stage" was overstated; no harm yet |
| A19 | Snapshot freshness after Cortex materialises | Runtime `needs_hydration` | New session, `invalidated` flag, or 6h; nothing sets the flag on a receipt | MECHANICAL | n/a | **Gap** (brief stale until rehydration) |

## B. Runtime live path

| # | Decision | Where | Mechanism today | Class | Semantic source | Verdict |
|---|---|---|---|---|---|---|
| B1 | What is relevant to the user's words | `resident_state._priority` (`_words` overlap, `min(overlap,3)*3`, recency buckets, rank weights) | Token overlap plus hand weights | SEMANTIC | Lexical overlap | **VIOLATION** (the exact lexical-relevance failure already found in Cortex) |
| B2 | Pressure of a Cortex item | `_cortex_pressure` | Maps Cortex-declared states to numbers (passthrough of Cortex's own state) | POLICY | Cortex states | POLICY-OK |
| B3 | Is this aggregate "what's my week" question | `overview.AGGREGATE_CUE`, `TODAY_ONLY`, `WIDER` | English phrase regex routes to today/week projection; documented as "mechanical" | SEMANTIC (user intent) | Hand-written regex, English only | **VIOLATION** (I wrote it and labelled it mechanical) |
| B4 | Is an exchange worth extracting | `episode_state.worth_extracting` | `len(text) >= 70` | SEMANTIC | Length proxy for meaning | **VIOLATION** (small, but real: a short, important message is skipped) |
| B5 | Which claims archive from the live ledger | `_archivable_ids` | Status already set by the extractor model, plus age and grace window | MECHANICAL | Extractor model's `status` | OK |
| B6 | When to checkpoint | `should_checkpoint` | Message/claim counts | POLICY | n/a | POLICY-OK |
| B7 | Post-reply gate (new durable content, corrections, scene change, ...) | `policy/post_reply` + Jev | Model answers each question; thresholds per question | POLICY over model output | Jev model | OK (thresholds are explicit policy) |
| B8 | Beat splitting | `beats.py` | Model-written marker only | MECHANICAL | Foreground model | OK |
| B9 | Medium, model routing | `infer_medium`, `foreground_model` | Product/config tables | POLICY | n/a | OK |
| B10 | Context window sizes, depth sufficiency | `_resolve_depth`, window=6 | Policy constants and Cortex/Jev flags | POLICY | Jev flags | POLICY-OK |

## C. Cortex live path (older)

| # | Decision | Where | Mechanism today | Class | Semantic source | Verdict |
|---|---|---|---|---|---|---|
| C1 | Relevance to the current turn (working set) | `turn_working_set._score` | Token overlap; zero overlap scores 0 | SEMANTIC | Lexical overlap | **VIOLATION** (known: finds "James", misses "what's happening this week") |
| C2 | Did the user complete / fail something (explicit completions) | `lifecycle_service.resolve_explicit_completions`, `COMPLETION_MARKERS`, `NEGATIVE_OUTCOME_MARKERS`, `COUNTERFACTUAL_MARKERS` | English keyword lists decide completion, negation and counterfactual framing | SEMANTIC | Hand-written marker lists | **VIOLATION** |
| C3 | Open-loop resolution | `try_resolve_open_loop` | Same marker lists as gates, then lexical overlap retrieves/ranks, "strong sole-candidate overlap resolves directly", weaker confirmed by the `resolves` judge | MIXED | Lists + lexical + a model judge on the weak path | **VIOLATION** on the direct-resolve path and the gates |
| C4 | Provision a new entity from a mention | `entity_service.resolve_mention` (`_PROPER_NAME_RE`, `_POSSESSIVE_ROLE_RE`, `_GENERIC_REFS`) | English name-shape regexes and a stop list | SEMANTIC | Hand-written regex | **VIOLATION** |
| C5 | Matter salience | `matter_service.compute_components`, `foreground_rank` | Counts and arithmetic (recency, frequency, 48h/30d windows, unresolved member count), weighted mean; `explicit_importance` comes from model-assigned importance | MIXED | Counts + hand weights | **VIOLATION** for frequency/unresolvedness-as-importance; time arithmetic itself is OK |
| C6 | Matter identity | `resolve_or_create_matter` (link, lineage, key, entity overlap, bounded `same_matter` judge; ambiguous stays separate) | Deterministic nomination, model decides same/different | MIXED | Model judge | **OK** (this is the correct shape; the model to copy) |
| C7 | Agenda ranking | `agenda_service.model_rank` (+ `fallback_rank`) | Model selects and orders; fallback is `0.45*importance + 0.4*urgency + 0.25*pressure` | SEMANTIC | Model, with arithmetic fallback | OK primary; **fallback is a violation when it fires** |
| C8 | Narrow realtime classification | `narrow_realtime.classify` | Model decides, deterministic validator grounds | MIXED | Model | **OK** |
| C9 | Expectation staleness | `expectation_engine.derive_temporal_state`, `UNANCHORED_STALE_HOURS = 36` | Time arithmetic over model-supplied windows; relative phrase with no window goes stale at 36h regardless of what it said ("next month") | MIXED | Hand threshold standing in for meaning | **VIOLATION** (written last week) |
| C10 | Lapsed commitments | `attention_state_service` `LAPSED_OVERDUE_DAYS` | Time threshold on model-supplied state | POLICY | Constants | POLICY-OK (document) |
| C11 | Pressure dynamics | `pressure_service.apply_pressure_dynamics`, `followthrough._pressure` (`high=0.8…`), `initiative._high_pressure_items` | Maps/arithmetic over model-assigned pressure | POLICY | Model labels | POLICY-OK |
| C12 | Sweeper promotion | `sweeper_service._promote_one` (cadence enum and `confidence >= 0.65`) | Threshold gating over model output | POLICY | Model output | POLICY-OK |
| C13 | Scene state merge | `scene_state.apply_detections` | Authority-ranked merge of detections | MECHANICAL | Detection source | OK |
| C14 | Historical repair duplicates | `historical_repair.classify_and_repair` | Exact normalised-title duplicate; other classification reads keywords in text | MIXED | Exact match OK; keyword part unread in full | partial / UNREAD |

## D. Not yet traced (not claimed clean)

`longitudinal_read.retrieval._score`, `shadow_a.pipeline` (`rank`, `weight`), `knowledge_coverage_service.rank`, `semantic_views`, `projection_service`
beyond `_rank`, Honcho adapter `_retrieve_relevant_memory`, `evidence_recruitment`, `surface_lifecycle.resolve`, `semantic_promotion` (bounded
vocabulary of relations, deterministic edge persistence), session extractor prompts, Jev vector pack contents, Honcho deriver/dream prompts.

## E. Counts (counted from the tables above)

43 decision points traced (A 19, B 10, C 14). **22 are violations** (A1-A12 and A15, B1, B3, B4, C1, C2, C3, C4, C5, C9); the rest are mechanical,
explicit policy, correct model-owned shapes (C6, C8, B7, C7 primary), gaps (A13, A14, A18, A19) or partly unread (C14).
Authorship of the 22: 14 are code I wrote this week (A1-A12, A15, C9), 2 are mine from earlier weeks (B3, B4), 6 predate this conversation (B1, C1,
C2, C3, C4, C5). The pattern is identical everywhere: an open semantic question was answered by a list, regex, threshold or template, and a
fixture that matched the answer was taken as proof.

## F. Where the model-owned shape already exists (copy these)

C6 matter identity (nominate deterministically, a model judges same/different, ambiguity stays separate), C8 narrow lane (model decides, validator
grounds), C7 agenda (model selects/orders, code owns text), B7 gate (model answers questions, policy owns thresholds), the epistemics ladder.

## F2. Disposition after the rebuild (2026-10-04)

Removed with the code that held them: A1-A12, A15 (template, thresholds, kind lists and label tables, closed dimension vocabulary, awareness rule,
quote regex, `difflib` event merge, brief filter/ordering, claim-kind rule, the second "judge" hook). Their decisions are now the interpreter's
(`world_interpreter.py`). Fixed: A13 (constitution is registry config, supplied by the trusted caller, never in the delta), A14 (events as well as
claims), A19 (version probe refreshes the resident packet), B3 (overview intent is Jev's `overview_scope`; production-smoked on 6 phrasings
including Spanish and a negated cue-word case), B4 (extraction gated by the model, not a length rule). A18: `covered_through` is per producer
only and nothing retires on it yet.
**Still open:** B1 and C1 (lexical relevance), C2 and C3 (completion/negation/counterfactual marker lists), C4 (entity-provisioning regex),
C5 (salience arithmetic: recency/frequency/unresolved counts feeding rank), C7 fallback, C9 (36h relative-phrase expiry), section D (untraced).

## G. Everything still to build (so none of it is lost)

1. **Semantic authoring step** (Luna Pro, async, once per checkpoint; Flash Lite recall-only): objective reconciliation, open-vocabulary directional
   relationship dimensions, continuity-required judgement, event sameness, trajectory assessment and note, brief composition. Code validates,
   stores, versions, renders. Replaces A1-A12.
2. **Honcho decision**: what Honcho produces at the checkpoint horizon vs the Runtime producer; Runtime writes raw evidence to Honcho every turn for
   every product; ingest Honcho deductions as candidates; Honcho to Luna Pro via OpenRouter with its own key (known update).
3. **Constitution from per-character config** (trusted, not in the delta); resident snapshot invalidation on materialisation receipt; per-stage
   coverage vector (`evidence_ingested`, `delta_materialised`, `interpretation`).
4. **Resident packet**: server-side cache refreshed on receipt, manifest/depth index, Jev aperture routing (A0-A3).
5. **Replace the older violations** B1, B3, B4, C1, C2, C3, C4, C5, C7-fallback, C9 with model-nominated/judged equivalents (relevance, aggregate
   intent, completion/negation/counterfactual, entity provisioning).
6. **Parity replay**, then retire redundant readers (Cortex 3-stage extractor, turn_interpretation, current_meaning if unused, Lane 2, Honcho
   per-message evaluation).
7. **Cortex one-time repairs**: 13 twin groups, raw-title relabel, goal/routine duplicates.
8. **Red-team recovery replay** (identity-breaking RPD2 scenarios: does the character steer back to the user without puppeteering) and the
   grounded Sophie acceptance on real models.
9. **Backlog**: depth-retrieval gap, Lane 2 observability (`sweeper_runs`), Cortex people/biography diagnosis, model-policy optimisation
   (DeepSeek V4 / Gemini where speed matters), complete section D.
