# Cortex Cutover

Status: Accepted architecture — implementation source of truth
Date: 2026-10-01

HOW companion to `CORTEX_ARCHITECTURE.md` (WHY/WHAT). Direct cutover: no flags,
no shadow architecture, no compatibility period. Recoverability, not theatre.

## 0. Recoverability

- Code: annotated pre-cutover state is tag `pre-cortex-cutover-2026-10-01`
  (HEAD `dec1ae4`). Restore a file/tree with `git checkout pre-cortex-cutover-2026-10-01 -- <path>`.
  Per `AGENT_BOOTSTRAP.md` the shared worktree is dirty by other agents' research
  files (docs/reports/evals/uv.lock); they were **not** swept into a checkpoint
  commit and are not touched by this work. Only files this cutover owns are committed.
- Database: every migration has a working `downgrade()`; rollback target is
  `0031_consolidation_runs`. New tables are additive; existing-table changes are
  nullable column adds (no drops of existing columns, no data rewrites in migrations).
  Production (Postgres) operators: `pg_dump` before `alembic upgrade head`; the
  local dev sqlite file was copied aside before work. Backfill is a separate,
  idempotent, re-runnable script — never part of a migration.
- Verified: upgrade → downgrade → upgrade on a scratch sqlite DB (see §10).

## 1. Starting state (inspected, not assumed)

- Branch `main`, HEAD `dec1ae4`; alembic head `0031_consolidation_runs`.
- **No previous-agent implementation of the cutover existed** (no matter/world-model
  files, models, migrations or services). Uncommitted work was research docs
  (`docs/BLITZ_GOVERNOR_MAP…`, `INTERPRETATION_*`, `GEMINI_BEHAVIOURAL_EVAL`),
  `evals/interpretation_phase0/`, reports, two research tests
  (`test_attention_handover_reuse_parity.py`, `test_interpretation_phase0.py`) and
  `uv.lock`. All retained untouched; `test_attention_handover_reuse_parity.py`
  depends on the handover path and is migrated (§7).
- Baseline: 563 passed, 17 skipped, **15 failed — all in
  `tests/test_continuity_basics_product_path.py`**, pre-existing: they import
  the sibling `../companion-runtime` repo whose
  `build_sophie_reply_system_prompt()` no longer accepts `interaction_mode`.
  Unrelated to this cutover (see Deviations D4).
- The word "matter" is already used informally: `session_apply` ops
  (`new_matter`, `resolve_matter`), `surfacing.report_back(matter_kind, matter_id)`
  and Track D/E "matter identity" tests refer to *primitive rows*, not the new
  durable `Matter`. They are left as-is (rename is churn); this doc and the code
  say `Matter` (capitalised, `matters` table) for the new primitive.
- Existing bilateral machinery reused: `ownership.resolve_owner`, assistant-turn
  lane (`ingest_assistant_turn`, speaker-owned promises), `CommitmentCandidate.evidence_class`,
  `Expectation.formation`, `WorkItem.owner`, `AttentionCandidate.kind`.

## 2. Repo mapping (existing → role)

| Existing | Role after cutover | Action |
|---|---|---|
| Expectation, RecurringIntention/Occurrence, OpenLoop, Attention/Commitment/ClarificationCandidate, Suppression | authoritative lifecycle primitives | keep; add nullable `direction` where needed |
| Entity, EntityAlias, RelationshipEdge, EntityLink | identity graph; EntityLink also links entity↔Matter | keep |
| ModelEntry | single epistemic/supersession store | extend columns (claim_kind, subject_matter_id, epistemic_status, evidence_refs_json, holder_actor, direction) |
| SemanticClaim/Relation | relation evidence; feeds Matter identity + Matter relations | keep (read) |
| Fact, DomainAnnotation, CurrentMeaning, DerivedSignal, WorkItem | keep; linked to Matters via `matter_links` | keep |
| TurnStamp/SceneState/ConsolidationRun | chronology/provenance | keep |
| InitiativeEngine, Sweeper, LongitudinalRead | keep (Sweeper + consolidation unified write path §6) | keep/extend |
| agenda_service, followthrough_service | follow-through ledger + ranking feeding AttentionState | keep; re-point to AttentionState |
| CortexPacketService (`compile_attention_packet`) | **AttentionStateService** | refactor/rename; drop `intelligence_brief` + `continuity_context`; add scopes + Matter links |
| HandoverService | — | **delete** |
| session_workingset (`compile_session_working_set`, `needs_refresh`) | — | **delete** |
| state_views, candidate_moves | — | **delete**; `unresolved()`/`today()`/`week()` projections + AttentionState replace |
| working_set_service (per-turn L0/L1/L2) | **Turn Working Set** | replace with `turn_working_set.py` |
| cortex_handshake_service | entry orientation (chronology/sitting) | keep, re-point to AttentionState (+ WorldModel header) |
| ProductProfile | product policy | extend with generic Matter-kind weights; drop `handover_*` |

## 3. Schema / migrations

All new tables carry `honcho_workspace_id`; person scope is `owner_peer_id`.

**0032_matters**
- `matters`: `id`, `honcho_workspace_id`, `owner_peer_id` (nullable: legacy/shared),
  `kind` (project|topic|concern|relationship_situation|goal|life_situation|routine|other),
  `title`, `canonical_key` (index; normalized significant tokens), `status`
  (active|dormant|resolved|archived), `first_seen`, `active_since`, `last_touched`,
  `resolved_at`, `merged_into_id` (nullable; merge repair), `summary_entry_id`
  (nullable ModelEntry ref; summary is a cache/reference only), `confidence`,
  `formation` (explicit|inferred), `origin_session_id`/`origin_message_id`/
  `last_touched_session_id` (**all nullable provenance, never ownership**),
  `salience_components_json` (derived cache), timestamps.
- `matter_links`: matter ↔ primitive (`object_type`, `object_id`, `role`, `confidence`,
  provenance); unique `(matter_id, object_type, object_id)`.
- `matter_relations`: `from_matter_id`, `to_matter_id`, `rel_type` CHECK
  `related_to|part_of|depends_on`, evidence, unique active edge.
- Entity↔Matter: existing `entity_links` with `object_type='matter'` (no schema change).

**0033_epistemic_direction**
- `model_entries` + `claim_kind`, `subject_matter_id`, `epistemic_status`
  (default `current`), `evidence_refs_json` (default `[]`), `holder_actor`, `direction`.
- `expectations`, `open_loops`, `commitment_candidates` + nullable `direction`.
  (AttentionCandidate/WorkItem direction is derived from `kind`/`owner`; no column.)

**0034_world_model_coverage**
- `world_model_snapshots` (workspace, owner, `version`, `compiled_at`, `snapshot_json`,
  per-section `fingerprints_json`, `superseded_by_id`).
- `knowledge_coverage` (workspace, owner, `subject_key` path, `parent_key`, `status`,
  `basis`, `evidence_count`, `evidence_refs_json`, `last_evidence_at`, `why_useful`,
  `source`, unique `(workspace, owner, subject_key)`).
- `session_episodes` (workspace, lane `honcho_session_id`, `temporal_session_id`,
  `consolidation_run_id`, `owner_peer_id`, `summary`, `writes_json` (refs to canonical
  writes with role), `detected_json`, `matters_touched_json`, `entities_touched_json`).
  Holds **references and prose only**; no repair/expectation/decision truth.

## 4. New services

| Module | Responsibility |
|---|---|
| `models/matter.py`, `models/world_model.py` | SQLModel tables above |
| `services/epistemics.py` | formation classes, annotation→class mapping, status derivation, `why()` evidence trail |
| `services/actor_direction.py` | direction vocabulary; structural derivation (no text keywords); write-time stamping |
| `services/matter_service.py` | `resolve_or_create_matter`, lifecycle, links, relations, `merge_matters`, salience components, `sync_primitives` (idempotent reconcile/backfill core) |
| `services/world_read.py` | private typed item collectors over primitives (shared by WorldModel + projections; never exposed whole) |
| `services/world_model_service.py` | compile/get/invalidate/patch snapshots with section fingerprints |
| `services/projection_service.py` | the ten projections + `why` |
| `services/attention_state_service.py` | refactored packet lifecycle logic → scoped AttentionState |
| `services/knowledge_coverage_service.py` | derive/register/query coverage; gaps → curiosity |
| `services/turn_working_set.py` | 3–5 item per-turn selection |
| `services/session_episode_service.py` | episode records referencing canonical writes |

## 5. Matter identity (`resolve_or_create_matter`)

Order (implemented): (1) existing `matter_links` for the object; (2) lineage — superseded
predecessor / `OpenLoop.expectation_id` / WorkItem parent / sibling annotation of the same
(message, candidate); (3) existing semantic relations (same_as|refines|supersedes|resolves|
fulfils|partially_fulfils|reopens → same Matter; part_of|depends_on → Matter edge), joined by
`content_hash` of the primitive's text; (4) exact `canonical_key`; (5) linked-entity overlap
**and** non-name significant-token overlap (same bar as existing open-loop reuse); (6) bounded
`semantic_judge(kind="same_matter")` for ambiguous *or token-disjoint-but-same-entity*
candidates when an adapter is allowed (consolidation, sweeper, backfill); fail-closed → create a
new Matter plus a `related_to` edge. Primitives are resolved **chronologically**. A
`dedupe_matters` pass (judge-bounded, verdicts remembered on the pair's `related_to` edge)
repairs fragments that already exist. Matters are never created from facts (link-only) or from
app-owned source-linked tasks/events. Kind comes from the source primitive type and structured
DomainAnnotation/semantic type; never from keyword matching on text.

## 6. Unified write path / call-site changes

- `MatterService.sync_primitives(db, ws, owner)` is the single idempotent step that
  resolves unlinked primitives into Matters, updates lifecycle/salience and
  Matter relations. It is invoked by: session apply (end of run), Sweeper `run`,
  `WorldModelService.get_world_model/compile` (cheap when nothing changed), and
  the backfill script. No hooks scattered through `lifecycle_service`.
- `session_consolidation`/`session_apply` write canonical state as before, now with
  direction stamped, then write a `SessionEpisode` referencing the writes and call
  `sync_primitives` (+ coverage gap registration from model-proposed gaps).
- Router: removed `/working-set`, `/session-working-set(+/refresh)`,
  `/handover(+/evaluate,/preview)`, `/attention-packet(+/evaluate)`. Added
  `/attention-state(+/evaluate)`, `/turn-working-set`, `/world-model`
  (+`/invalidate`), `/projection/{person,matter,timeline,today,week,period,unresolved,
  recent-changes,knowledge-gaps,depth,why}`, `/knowledge-coverage` (+gap register),
  `/matters/*` (list/get/merge). `/handshake` kept (orientation) and re-pointed.
  `/background-sweep` re-pointed to AttentionState + projections.
- Evaluation (rollback-session) variants preserved so compiling is never asking.

## 7. Tests

- Updated/migrated: `test_handover_and_profile`, `test_track_choose`,
  `test_operational_views`, `test_attention_controller` (working set),
  `test_working_set`, `test_intelligence_brief`, `test_canonical_*`,
  `test_attention_handover_reuse_parity`, packet-shape tests → AttentionState.
- New: `test_matter_identity`, `test_actor_direction`, `test_epistemics`,
  `test_world_model`, `test_projections`, `test_attention_state`,
  `test_knowledge_coverage`, `test_session_episode`, `test_cortex_acceptance`
  (the 20 prepared-state questions over a realistic longitudinal fixture),
  migration up/down test.

## 8. Backfill

`scripts/backfill_matters.py` (idempotent): runs `sync_primitives` over Expectations,
OpenLoops, RecurringIntentions, CommitmentCandidates, WorkItems, ModelEntries (subject
entity/summary), Facts + DomainAnnotations (via message provenance) and EntityLinks,
stamps `direction` where structurally derivable, derives coverage, compiles the
initial WorldModel. Not a perfect reconstruction; consolidation improves it.

## 9. Deletion list (same cutover)

`services/handover_service.py`, `services/state_views.py`, `services/candidate_moves.py`,
`services/session_workingset.py`, `services/working_set_service.py`,
`services/cortex_packet_service.py` (→ attention_state_service),
`_compile_intelligence_brief`, `_compile_continuity_context`, the router endpoints in §6,
`ProductProfile.handover_*`, and the tests that exclusively covered the above
(replaced by §7).

## 10. Implementation sequence and results

Sequence executed: tag → docs → schema (0032–0034) → Matter + identity → epistemics/direction →
WorldModel → projections → AttentionState (refactor of the packet) → coverage → consolidation +
sweeper write path + SessionEpisode → backfill script → consumers migrated → obsolete code deleted
→ tests → lock/transaction isolation → Postgres validation.

### Results

| Check | Result |
|---|---|
| Existing suite (SQLite), final single full run | see "Final regression gate" below |
| New suites (Matter identity/fragmentation, actor direction, epistemics, WorldModel, projections, AttentionState, coverage, SessionEpisode, 20-question acceptance, longitudinal invariants, endpoints, migrations/backfill) | all pass on SQLite (122 + 5 Postgres-only skipped) and **all 123 pass on Postgres 16** |
| Postgres: full alembic chain upgrade, downgrade to 0031, re-upgrade | pass (see D6 for the pre-existing 35-char revision id) |
| Postgres: concurrent reconcilers (6×), WorldModel read ∥ consolidation write ∥ sync, sweeper write ∥ attention reads, repeated dedupe, rollback session, unique-subject-link enforcement | pass, 3 consecutive runs |
| Migration chain on SQLite (0032–0034 in isolation: parity with models, bounded CHECKs, full downgrade) | pass |

### Fragmentation measurement (realistic: 15 mentions of one Carlos invoice concern over 6 weeks + 3 venue mentions)

- first implementation (type-ordered resolution): 15 mentions → **10 Matters** (unacceptable);
- chronological resolution, deterministic only: **4 Matters** (largest holds 10);
- + bounded judge in sync and dedupe pass (converges over ≤4 runs, budget 6 verdicts/run): **2 Matters**
  (money = 15 members, venue = 3), money↔venue judged distinct and remembered, never re-judged.
No keyword lists exist in production code; the judge in the tests is a test double.

### SQLite `database is locked` — root cause (isolated by subset bisection, not full-suite reruns)

Reproduced with a 27-file subset; passed with the sweeper hook disabled (3/3); fixed (3/3 stable).
1. **Sweeper reconcile ran a long write transaction in the debounced background sweep** that
   outlives the request/test (`sweeper_triggers._delayed_sweep`). Fix: (a) reconcile only when the
   sweep actually promoted something; (b) `sync_primitives` commits **per primitive** (short write
   transactions, idempotent resume), never holding a write lock across later reads or judge calls.
2. **Reads wrote canonical state**: `get_world_model`/projections called `sync_primitives`. Reads now
   only rebuild disposable derived state (snapshot, coverage). Reconciliation is owned by mutation
   boundaries: sweeper, session consolidation, backfill, explicit `POST /matters/sync`.
Postgres surfaced three further real bugs (all fixed, all covered by `tests/test_postgres_concurrency.py`):
concurrent reconcilers could double-found a Matter → partial unique index `uq_matter_link_subject`
+ per-primitive SAVEPOINT; concurrent coverage derivations raced on the unique path → SAVEPOINT +
ignore; pre-existing: two concurrent attention reads racing to create today's occurrence did
`db.rollback()` which expired loaded rows (MissingGreenlet) → SAVEPOINT.

### Baseline failures (pre-existing, not caused by the cutover)

`tests/test_continuity_basics_product_path.py` — **15 failures at tag `pre-cortex-cutover-2026-10-01`
and after**: they import the sibling `../companion-runtime` whose
`build_sophie_reply_system_prompt()` no longer accepts `interaction_mode`
(`TypeError`), before any Cortex endpoint is reached. No other failures exist at head
(see final regression gate). These tests also call removed endpoints and belong to the Runtime migration.

### Final regression gate

One complete run (SQLite, after the targeted groups were stable): **665 passed, 22 skipped, 15 failed** — the 15 are exactly the
baseline failures above (`test_continuity_basics_product_path.py`, Runtime prompt-builder drift) — with **0** `database is locked`
errors. One further test in that file (`test_cached_rank_cannot_revive_suppressed_item`) fed the retired packet shape to the agenda
and was migrated to the AttentionState shape; it passes. **No additional failures are introduced by Cortex.**

## 11. Runtime API migration required (companion-runtime is NOT modified here)

Runtime's live path today: `/v1/cortex/attention-packet`, `/handshake`, `/handover/preview`
(+ `/evaluate` variants, `/handover`, `/session-working-set(+/refresh)` in `adapters/cortex/client.py`).

| Removed endpoint | Replacement | Shape change |
|---|---|---|
| `GET /attention-packet` (+`/evaluate`) | `GET /attention-state` (+`/evaluate`) | `intelligence_brief` → `window.scopes` {immediate,today,upcoming,unresolved,review_needed} (`now`→`immediate`, `tomorrow`+`later`→`upcoming`); `continuity_context.continuity` → `eligible`; `continuity_context.open_threads`/`recent_resolutions`/`avoid_repeating` → top-level `open_loops`/`recent_resolutions`/`suppressed_targets`; `continuity_context.now.daypart` → `window.daypart`; new `matters_in_window`, `knowledge_gaps`, items carry `matter_id` |
| `POST /handover`, `/handover/preview`, `/handover/evaluate` | `POST /attention-state` (`/attention-state/evaluate` is the zero-write arm) | handover `owed` → `follow_through.owed`; `available`/optional → `follow_through.optional` (rank order + `why`/`next_move`/receipt identity kept); `scene` → `follow_through.scene`; `patterns`→ WorldModel `routines_patterns.observed`; `avoid` → `suppressed_targets`. The handover's editorial string-shaping is gone: Runtime/product decides. |
| `POST /working-set` | `POST /turn-working-set` | `version: turn-working-set-v1`; ≤5 warm items; items may be `matter`/`knowledge_gap` with `depth` pointers |
| `POST /session-working-set`, `/session-working-set/refresh` | none needed: cache `POST /world-model` (cheap fingerprint check, `meta.freshness`) and query projections | session/scene composition was dormant on the live path |
| `POST /handshake` | kept; `continuity_context` → `attention` {window, eligible, open_threads, matters_in_window, recent_resolutions, avoid_repeating, …} | |
| (new) | `/world-model`, `/projection/{person,matter,timeline,today,week,period,unresolved,recent-changes,knowledge-gaps,depth,why}`, `/knowledge-coverage`(+`/gap`), `/matters/{list,sync,merge}`, `/episodes/list` | retrieval ladder: conversation → Turn Working Set → cached WorldModel fragment → projection → bounded LongitudinalRead (`scope=matter:<id>`) |

## 12. Operating notes

- Run `python scripts/backfill_matters.py --workspace WS --dry-run` then without `--dry-run`
  (idempotent; `--allow-judge` uses the bounded judge for ambiguous Matter identity).
- Matters/WorldModel lag ingestion until a mutation boundary runs (sweeper debounce, consolidation,
  backfill, `/matters/sync`). Reads never reconcile.
- Postgres tests: `CORTEX_TEST_POSTGRES_URL=postgresql+asyncpg://…@localhost:PORT/db pytest …`
  (local hosts only; sets `SYNAPSE_DB_NULLPOOL=1`).

## Implementation Notes / Deviations

- D1. Matter↔primitive link is a table (`matter_links`), not per-table columns or
  `EntityLink`: `EntityLink` is entity↔object; a many-to-many matter link avoids
  altering every primitive and supports Fact/ModelEntry/WorkItem uniformly.
- D2. Checkpoint is a **tag**, not a commit: the shared worktree contains other
  agents' uncommitted research files that `AGENT_BOOTSTRAP.md` forbids sweeping up.
- D3. Matter lifecycle/links are reconciled by one idempotent `sync_primitives` step
  rather than hooks inside each writer (lifecycle_service is 2.3k lines and many
  writers exist); fingerprinted staleness makes this equivalent and cheaper to reason about.
- D4. Companion Runtime (`../companion-runtime`) is a separate repository that
  calls the removed endpoints. Per the agreed plan ("Runtime implements retrieval
  ladder; out of scope for Cortex") its adapter is not edited here; the endpoint
  mapping Runtime must adopt is listed in §11.
- D5. The pre-existing alembic chain cannot run on SQLite (0029 drops constraints) so migration
  parity is tested by applying 0032–0034 directly via Alembic operations; the full chain was run on Postgres.
- D6. Pre-existing: revision `0026_review_and_resolution_evidence` is 35 chars but `alembic_version.version_num`
  is `varchar(32)`, so a *fresh* Postgres cannot upgrade past 0026 unless the column is widened (production
  evidently was). New revisions are ≤32 chars (`0034_world_model_coverage`; first draft id was 34 and was shortened).
  Not changed here (editing a shipped revision id is riskier than the scratch-DB workaround).
- D7. Also retired as satellites of the deleted layers (dead after the cutover, tests removed): `state_roles`,
  `operational_decision`, `turn_selection` (Runtime-side policy living in Cortex; Runtime never used it).
  The dormant "suppression reactivation by newer target row" lived only in the deleted session working set
  (live reopening via `apply_reopen_conditions` is untouched).
- D8. Found and fixed: `session_apply` `revise_expectation` referenced non-existent `OutcomeState.VIOLATED`, so every
  such op was deferred as `apply_error`; now maps to `NOT_FULFILLED` (+test).
- D9. Sweeper stored Sophie's promises as the *user's* `implicit_self_commitment`; now `character_promise`
  (system→user). Previous agent's research test `test_attention_handover_reuse_parity.py` (untracked) targeted the removed
  handover preview; its still-valid half (lifecycle effects of an attention read, evaluate rollback) was kept as
  `test_attention_state_read_effects.py`.
- D10. `Matter.summary_entry_id` references the summary ModelEntry; there is deliberately no summary text column.
- D11. Knowledge coverage is derived with rules over generic paths plus a six-parent acquaintance frame; `unknown`
  rows have no value column by design. The tool `uvx ruff` was fetched for lint checks during development only.
