**Agency-loop pass (later the same evening, deployed: Cortex `80f7ad2`, Runtime `31f48e5`):** writer audit for Sophie done (live writers now: the interpreter; app-owned objects via
`/v1/events/object`; user-accepted commitment candidates; the executive's own work_items): the assistant-turn lane was the last legacy writer and is closed for
interpreter-owned worlds. Deep-memory retrieval (A3) no longer returns Honcho's derived conclusions (default mode was `conclusions/query`, i.e. old Honcho reasoning about
Sophie): it is raw message search. Delivery composer is model-composed (not a template); it now forwards the intent's gist/why, uses `companion_id`, and returns
`intent_id` (the app must persist it on the outbound message to link replies to the move: app change pending). Executive plans across concerns (`depends_on`,
`combine_with`, horizons/stances, agenda). Real-model loop replay (scratch): 5 operational items captured -> executive planned (urgent surfaced with a pre-deadline wake,
walk+call combined and deferred, passport deferred, James dependency tracked) -> reply closed the deliverable by id -> executive closed its intent and replanned without
nagging. Known miss: interpreter created a replacement instead of completing a listed wait (prompt tightened, not re-verified). The wake heartbeat already lives in
Cortex (asyncio loop); only delivery depends on the Sophie app (Vercel cron -> app -> Runtime proactive tick): needs the app's production URL + CRON_SECRET or Vercel access.

# UPDATE 2026-10-04 (night): the agency loop closed in production. Read this first.
**Delivery (fixed, root cause):** the Sophie app (GitHub `mukeshkumar108/ash-ai`, Vercel project `project-z963i`, local worktree `llm-agent-test-consumer-cutover`, branch
`consumer-cutover`, deployed with `vercel deploy --prod` from that worktree) only built proactive candidates from its OWN tables (RelationshipOpportunity, TaskReminder,
calendar follow-ups) and only asked Cortex's gate per candidate. Crons were firing fine (every minute); the executive was simply never a candidate source. Now
`fetchExecutiveSpeakCandidates()` (app) polls Cortex `POST /v1/executive/speak-candidates` (SQL only) and each owner becomes a candidate on their most recently active chat;
claim -> Runtime compose (model, in voice, now fed the intent's gist) -> persist -> complete is unchanged. Heartbeat for wakes stays in Cortex (asyncio loop).
**Proven live:** an executive intent ("Take a daytime walk") was raised through the real gate and delivered; ledger `appeared`; intent SURFACED. Runtime records what it composed on the
exact intent (`POST /v1/executive/outbound`, called with the intent id it was given; the earlier timing-heuristic link was removed).
**Action loop (proven live):** product-declared capability catalogue in world policy (`capabilities.tools`; the PRODUCT declares each tool's consequence/reversibility, the model's
claim can never lower it; unknown tools are dropped). Executive chose `task.create` -> autonomous (explicit request + low + reversible) -> app cron `/api/cron/executive-actions`
claims with a `started` receipt (never twice), executes `createTask`, posts a real receipt (task id) -> intent `done` -> the task flows back to Cortex via the existing object push.
Inferred-authority actions become a confirmation request; when the executive judges the user said yes it updates the intent with `authority_basis` and permission is re-derived.
**Bug found by that proof and fixed:** the receipt woke the executive but completed actions were not in its context, so it re-proposed the same action and a DUPLICATE task was created.
Fixed: `recent_actions` (with receipts) in context + prompt rule, and an exact-duplicate guard (identical tool+args never created twice). Cleanup: the stray confirmation request was
cancelled; the duplicate task could not be removed from here (production DB password is a sensitive Vercel var): **delete the task titled "Evening walk" with the note "Take the planned
evening walk at 7pm." (id 701c2972-38d8-4f33-bd59-84ee59d7d755); keep "Evening walk at 7pm" (76fe87a1-...).**
**Operational reconciliation contract:** the interpreter must return a verdict for EVERY listed open operational item (holds/updated/completed/cancelled/superseded/unclear; closing verdicts
need evidence and apply by exact id; coverage recorded); creating a new item is a separate act. **Not done:** executive ask/confirm round-trip with a real user reply; second capability;
executive reasoning over action failures; per-message intent id on the app message (the link is recorded in Cortex on the intent instead).

# UPDATE 2026-10-04 (evening): Sophie convergence + executive layer. Read after the update below; see COGNITION_ARCHITECTURE.md "Layer 3 and Sophie convergence".
Deployed: Cortex `main` (executive, operational output, close-by-id, per-world operational owner), Runtime `2bd09f2` (all owners interpreted, Jev `time_bound`). Rollback images:
`*:pre-sophie-converge`. Sophie's world (`llm-test-agent` / `user_5377a025-...`): executive enabled, `operational.owner=interpreter`, Honcho `observe_me=false` (revert: PUT peer
configuration `observe_me:true`). Verified: real-model executive replay (scratch); production executive pass on Sophie's real state (about $0.006); production smoke of
reminder-create -> time grounded -> completion closes by id (isolated workspace, purged, verified). Jev `time_bound` 9/10 on realistic phrasings (miss: a bare completion with no context).
**Open:** (1) delivery cron (Vercel project not visible to my tools: check production deployment/crons/`RELATIONSHIP_SERVER_INITIATIVE_ENABLED`/CRON_SECRET; Runtime and Cortex
saw zero ticks since Sep 2); (2) tool execution layer; (3) Runtime -> Cortex hop for Sophie is unit-tested, not smoked end to end with a live turn; (4) legacy ingestion deletion
(~28 test files drive it) which also removes the transitional policy switch; (5) dead modules: Runtime episode_state/episode_store/episode_async are no longer live readers;
(6) `/v1/world/delta` kept on purpose: it is the typed seam for observations/receipts from non-conversational producers.

# UPDATE 2026-10-04 (later): Layer-2 protocol pass. Read this block first; it supersedes conflicting statements below.

**Integrity audit of the previous handoff (verified against git, VPS and the DB):** commits, deployed images (byte-identical key files), flags, models, Honcho
mirroring (`observe_me=false`, embeddings, **summaries do get produced**: 3 summary tasks processed, content present), Matter repair, rollback tags and scratch
cleanup were all correct. Corrections: (1) the two independent audits and the ChatGPT review were never in either repo (user-supplied; untracked files in the
Runtime working tree are other audits); (2) the stated Cortex test result (687) was only reproducible on one machine: 2 committed tests read an untracked
`evals/interpretation_phase0/` (now tracked: `run.py`, `cases.json`, `README.md`); (3) "watch `world interpretation:` in logs" never worked (INFO was dropped by
logging config; Runtime now prints `[world-interpret]` lines); (4) the Cortex VPS checkout holds untracked `deploy/.env.bak*` files that Cortex's `.gitignore`
does not cover (never `git add -A` there).

**Defects found by observing real RPD2 sessions and fixed:** the interpreter never knew who the human's character was (the actor was literally "the user");
checkpoint and session-end windows overlapped and were interpreted twice (seen in real runs); checkpoint marker advanced on submit so a failed window was lost;
checkpoint evidence used synthetic ids (`-u/-a`) different from the persisted ids; no per-world serialisation; rejection reasons were dropped; **replacement facets
the model wrote were silently dropped when it referenced a known relationship/actor by id (root cause of the Elena stale-awareness case)**; a durable reading
could not supersede an `unknown`-tier facet; the resident `covered_through` would have lagged a run; the foreground saw only the last 6 messages while the brief
refreshed every 10 turns (a hole of up to ~14 messages); Sophie narrow lane returned 500 on concurrent duplicate delivery.

**Built and deployed (Cortex `b1d861c`+`295aea5`, Runtime `22c69db`):** see `COGNITION_ARCHITECTURE.md` Part A. In one line: leased, transactional,
id-ledgered interpretation with run states and a single trace endpoint; product-pinned identities; reference resolution by local ref or known id; state review;
Runtime offers persisted-id windows and shows the foreground everything after Cortex's coverage frontier; Runtime episode ledger off for interpreted worlds
(rollback lever `WORLD_OWNERS_USE_EPISODE_LEDGER=true`; whole-protocol rollback images `*:pre-layer2-protocol`).

**Verified how:** Cortex full suite 698 passed / 22 skipped on the working tree (clean checkout now contains the phase0 fixtures); Runtime 260 passed; a real-model
replay on scratch SQLite (invented scenario: repeated first name, ambiguous pronoun, discovery, chaotic turn + retraction; about five cents) showed stale
awareness superseded, concealment objective resolved, chaos kept acute, redelivery skipped; production smoke (isolated workspace, purged by exact id, verified):
applied / redelivery skipped / concurrent duplicate pair applied+busy / trace endpoint / lease released. One-time repair applied: Audrey world's literal "the user"
actor pinned as the typed user placeholder (alias kept).

**Not done / pending (do not assume):** (a) **RPD2 push**: commit `29d24d3` on branch `consumer-cutover` of `rpd2-consumer-cutover` (local only) sends the human's
`rpDisplayName` as `trusted_user_context.user_display_name`; until it is pushed/deployed RPD2 worlds have a typed placeholder user and the interpreter cannot
name the human; its unit test was written but could not be run here (Playwright webserver needs a complete `node_modules`). (b) No real post-deploy RPD2 checkpoint
had been observed at the time of writing: check `GET /v1/world/trace` for the Elena/Audrey owners and the `[world-interpret]` lines in the Runtime logs.
(c) Sophie convergence: plan only (`SOPHIE_CONVERGENCE_PLAN.md`), two product decisions needed. (d) The original narrow-lane race (needs the live narrow model) is
covered by a lock + a duplicate-delivery test, not reproduced.

---

# Handoff to the next engineering instance (written 2026-10-04, end of the world-cognition rebuild)

Read this first, then the canonical architecture (`COGNITION_ARCHITECTURE.md`: Part A as built, Part B not built), then
`SEMANTIC_BOUNDARY_INVENTORY.md`. The two independent audits (Spark, Gemini/Antigravity) and the ChatGPT review are supplied by the user; load them
too. Nothing here is a plan to execute blindly: the first job of the next instance is to step back, understand the whole system, and make Layer 2 boring.

## 0. Who you are working for, and how
The user is a solo founder, one real user (themself), 14 months in, cost- and time-stressed. They want the CTO/lead to **own the architecture and
deliver**, not to take diagnostic breadcrumbs and patch symptoms. They said, at the end of this thread: "You're still the CTO and you're the lead.
I think you finally understand the real system we're making and how we need to be working. I don't want to lose that."

**Working principles (these cost real pain to learn; keep them):**
1. **Models own open-ended meaning; code owns mechanics.** No keyword/regex/word-list/threshold/template that decides intent, relevance, identity of
   two accounts, continuity, emotion, trajectory, or "what should happen next". A cheap lexical step may NOMINATE candidates for a model, never decide.
   Before adding any rule ask: mechanics or meaning? If meaning, it is a model call. Never write a "known scenarios" list. (Memory:
   `feedback_determinism_never_replaces_semantics`.)
2. **Tests that pass are not proof.** The failure pattern of this project: open semantic problem -> plausible heuristic -> fixture that matches -> green
   tests reported as success. Test PROPERTIES of the architecture (e.g. "code never merges events by similarity"), then prove behaviour with real-model
   replays on realistic, varied transcripts (no two transcripts or scenarios are ever the same; it is a conversation product, not a scenario list), and
   production smoke. Report what was observed, what was only tested, and what is unproven.
3. **Understand the actual system before changing it.** Trace real code and real data; do not trust design docs (they have repeatedly described things
   that were not running) or your own earlier summaries. Verify claims against production.
4. **Do not stop at the local fix.** When a symptom appears, ask which abstraction is wrong. But also do not start architectural features while closing
   a loop.
5. **Honest reporting.** If something was only unit-tested, say so. If a smoke found a bug, say so (this session's best finds came from production
   smokes: Honcho rejecting `:` peer ids had silently broken every Honcho call for `world:` owners).
6. **Cost discipline (memory `feedback_cost_and_eval_discipline`).** No broad evals, premium judges, or per-change benchmark sweeps without a stated
   cost. Real-model replays are small and targeted (about $0.015 per Luna Pro interpreter pass; a replay of 3-4 passes is cents). Luna Pro for deep
   background reasoning; cheap fast models only where latency matters. Never use a premium model to judge your own work.
7. **Git/Vercel hygiene.** Never `git add -A`: the user has untracked files (audits, evals, uv.lock, reports). Targeted adds only. Never push or merge to
   Vercel-connected repos (RPD2, Sophie/llm-agent-test) without asking; each push can trigger a paid build. Runtime/Cortex deploy to the VPS (docker,
   no Vercel) and may be deployed when tested. Commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
8. **Data hygiene.** Transcripts (explicit RPD2 content) are never committed and must be deleted from the VPS after use; verify deletion. Use scratch
   databases and isolated workspaces (purge by exact workspace id) for replays; do not modify the user's production conversation data without saying so.
   Say what a broad/destructive command will touch before running it (no broad `pkill -f`).
9. **Never print secrets.** (A Cortex env dump exposed the Neon URL this session: see §6.)
10. **Product truth.** Every companion (Sophie, RPD2 characters, Edgar, healthcare) shares one constitutional orientation: the long-term positive
    relationship with the user. Characters have many competing dynamic objectives; short-term behaviour may conflict with the long-term orientation (that
    is the drama). The system must never delete objectives, rewrite history, or script lines: it reinterprets meaning/salience and offers plausible
    paths. A chaotic foreground turn is preserved as an event and acute state; only sustained evidence becomes durable. RPD2's speaking model is
    deliberately a less-constrained NanoGPT model, so the backend must tolerate contradiction and drift. Canonicalise identity, never perspective.

## 1. Production, literally (verified 2026-10-04 on the VPS `deploy@161.97.150.246`)
| Item | Value |
|---|---|
| Runtime commit deployed | `e6417f0` (repo `companion-runtime`, branch main; VPS checkout clean) |
| Cortex commit deployed | `00a7a05` (repo `synapse-cortex`; docs-only commits since, VPS pulled to `ba5ad7e`+) |
| Honcho | untouched this session (running 4 weeks); repo has an untracked `scratch/` dir that is not ours |
| Runtime image / tag | `companion-runtime:local` = tag `companion-runtime:live-e6417f0-2026-10-04` |
| Cortex image / tags | `deploy-api:latest` = `deploy-api:live-00a7a05-2026-10-04`; image before the interpreter rebuild: `deploy-api:pre-world-objectives` |
| Rollback, Cortex | `docker tag deploy-api:pre-world-objectives deploy-api:latest` then `docker compose -f docker-compose.vps.yml --env-file .env up -d` (the new tables/columns are additive; leave them) |
| Rollback, Runtime | no image tag exists for the pre-interpreter Runtime (tagging before deploys was inconsistent today). Rollback = `git checkout 92385ae` (last Runtime code before world-cognition work) + rebuild, OR set `WORLD_INTERPRETATION_ENABLED=false` in `~/companion-runtime/deploy/.env` and recreate the container (this restores the legacy consolidation path for `world:` owners and is the intended first lever) |
| Containers | companion-runtime, synapse-cortex (healthy 8h), voice-runtime, honcho-api/deriver/postgres/redis/gateway, synapse-cortex-postgres, workspace-connect(-postgres) |
| Runtime flags | `WORLD_INTERPRETATION_ENABLED=true` (env file), `WORLD_EVIDENCE_MIRROR_ENABLED` unset -> code default true, checkpoint cadence 10 turns for owners prefixed `world:`, `RAW_WINDOW_MESSAGES=6`, `SYNAPSE_CORTEX_ENABLED=true`, `HONCHO_WORKSPACE_ID=llm-test-agent`; Jev model code default `typesafe/jev-1.13` |
| Cortex flags | `SESSION_CONSOLIDATION_APPLY=0` (global OFF), `SESSION_CONSOLIDATION_APPLY_OWNER_PREFIXES=world:`, `SYNAPSE_NARROW_REALTIME=on`, extractor provider `model` with `deepseek/deepseek-v4-flash`, `HONCHO_CONTEXT_ENABLED=true` |
| Models | interpreter `openai/gpt-5.6-luna-pro` (code default via OpenRouter); working-set relevance `google/gemini-3.7-flash` (code default); agenda ranker same default; RPD2 foreground = NanoGPT chain (e.g. `Gemma-4-31B-MeroMero-v2` first) |
| RPD2 path | see `COGNITION_ARCHITECTURE.md` Part A. Interpreter replaces legacy consolidation for `world:` owners at checkpoint, session end and episode end |
| Sophie path | unchanged legacy readers (narrow lane, 3-stage consolidation with global apply OFF, turn extractor); same resident/Jev/foreground path as RPD2 |
| Legacy readers still active | for Sophie: all; for RPD2: Runtime episode ledger (per-exchange claim extraction gated by Jev) and Cortex narrow lane only if the app feeds it (RPD2's app does not mirror to the Cortex outbox, not observed) |
| Resident refresh | new session, `invalidated`, 6h age, or a newer Cortex snapshot version (version probe per turn for `world:` owners) |
| Honcho for `world:` owners | Runtime mirrors every exchange (idempotent on `app_message_id`); peers/session created with `observe_me=false`. **Code-verified** (`src/deriver/enqueue.py`): with `observe_me=false` the deriver creates no representation/observation records and dreams (driven by representation documents) never fire; session summaries are still enqueued by message count (short/long thresholds) regardless; messages are embedded and searchable (smoke-verified). **Not yet observed live:** summaries for a world session past the threshold, and the interpreter actually consuming them |
| Honcho peer-id encoding | `honcho_peer_id()` (Runtime `adapters/honcho/client.py`, identical copy in Cortex `turn_context.py`): ids matching `[A-Za-z0-9_-]+` unchanged, else unsafe chars -> `-` plus 8-char hash. Cortex owner keys stay raw (`world:...`) |
| One-time data repair applied | real account `user_5377a025*`: Matter twins merged (4 pairs, model-judged, non-destructive: archived with `merged_into_id`), long raw titles relabelled (script `scripts/repair_matters.py`) |
| Scratch/smoke artifacts | verified gone: no scratch containers/networks; `/tmp` on the VPS has no replay/transcript files from this session; smoke workspaces `smoke-ws-20261004` and `smoke-ws2-20261004` purged from Cortex (exact-workspace rows) and deleted from Honcho (verified not listed). One pre-existing file not created by this session remains: `/tmp/sophie-forensic-replay-20260825.json` (user's earlier forensic replay; left in place) |
| Backups | `~/backups/cortex-neon-pre-checkpoint-2026-10-03.sql.gz` (Cortex Neon, taken before the checkpoint feature) and older dumps |

## 2. What this session changed (chronological, condensed)
- Cortex lifecycle fixes (staleness, lapsed commitments, scoped apply by owner prefix), Runtime episode ledger/checkpoints/post-reply gate/elastic resident
  selector/overview routing (earlier work, deployed).
- Designed `WORLD_CONTRACT.md` and built a typed `WorldDelta` seam + Cortex materialiser + `world_events`, `producer_runs`, `row_provenance`,
  `world_links` tables. First proof used a Flash Lite producer and hand-written rules; the Audrey scratch run exposed the rules.
- **Audit and reset:** the user caught a deterministic trajectory template ("toward honesty or reconnection"). `SEMANTIC_BOUNDARY_INVENTORY.md` traced 43
  decision points, 22 were violations (14 mine). Live emission was switched off.
- **Rebuild:** one Cortex world interpreter (Luna Pro) owns the semantics; the materialiser became mechanics only; kind lists, closed vocabularies,
  template, `difflib` merges, quote regex and awareness rule were deleted. New tables: `world_objectives`, `relationship_dimensions`,
  `trajectory_notes`, `continuation_briefs`; additive `durability` columns (idempotent ALTER in `init_db`).
- Runtime: Flash Lite producer removed; checkpoint hands evidence + registry policy/constitution to `POST /v1/world/interpret`; `POST /v1/world/version`
  refreshes the cached packet; Honcho evidence mirror; foreground prompt blocks (story state, what each person is trying to do, trajectory note).
- Older violations fixed: lexical relevance (Runtime selector, Cortex working set -> model `judge`), completion/negation marker lists (-> extractor
  `outcome`), entity-provisioning regex, overview intent regex (-> Jev `overview_scope`), 70-char extraction gate, `shadow_a` deleted, Matter repair.
- Flipped `WORLD_INTERPRETATION_ENABLED=true` after replays and a production smoke.

## 3. Evidence (what was proven, and how)
- **Unit/property tests:** Cortex 687 pass (22 skipped; one pre-existing collection error `tests/test_continuity_basics_product_path.py` needs a module absent
  from this checkout), Runtime 257 pass (`tests/test_lease_fencing_pg.py` needs a local Postgres).
- **Real-model replays** (scratch DB, Luna Pro, ~$0.015/pass): Lila three chunks (scene; chaotic "we're done" turn; retraction) -> acute rupture kept as
  acute, durable objective retained, constitution untouched, edge never ended, retraction updated/resolved objectives, awareness "not established";
  Sophie grounded -> invented brother kept out of the user's world, reminder recorded as a commitment, dinner plan as a Matter; messy
  self-contradicting foreground -> 7 conflicts recorded, none resolved; real NanoGPT foreground replies with vs without the continuation blocks (small N,
  weak baseline): without it both samples jumped to confession, with it they stayed in character.
- **Production smokes:** Runtime -> Cortex interpret + version probe through the real adapter; Honcho mirror (idempotent, `observe_me=false`, semantic
  search returns the mirrored evidence); one real turn through the real pipeline at turn 10 (Jev, NanoGPT foreground, Cortex, Honcho, checkpoint fired,
  interpretation ran) in an isolated workspace, purged afterwards; Jev `overview_scope` on 6 phrasings including Spanish and a negated cue-word case.

## 4. Deployed but NOT observed in sustained real use
The interpreter on a real multi-session RPD2 chat; the packet refresh after a real checkpoint; Honcho session summaries for world sessions; acute
lapse (72h) in practice; the matter-repair effect on Sophie behaviour; working-set `judge` latency/quality on the live path; foreground behaviour over
dozens of turns with the continuation blocks. First task after reading: watch the first real RPD2 sessions (logs `world interpretation:`; Cortex rows by
`producer_runs`) before building on top.

## 5. Known risks
- Interpreter quality varies per run (one replay omitted an objective earlier; later prompts improved this). It sees only the last 10 turns plus state
  plus Honcho context; long-chat drift is untested. Latency of the Luna call is background-only.
- `actors: 0` can happen when a stretch contains no names (the interpreter then produces little structure).
- Runtime episode ledger and the interpreter both interpret RPD2 conversations (duplication).
- Working-set `judge` adds a model call on the depth path; failure falls back to Cortex horizons only (no lexical fallback by design).
- Entity provisioning now trusts the extractor contract: junk provisional entities are possible; they are cheap and flagged `provisional`.
- The default constitution text contains "the user" and reaches the foreground.
- Sophie's legacy readers still hold ontology overlap (CurrentMeaning, turn_interpretation, semantic judge, 3-stage consolidation).

## 6. Operational closure
- **Credential exposure (action needed by the user, nothing was rotated):** while checking extractor settings this session printed Cortex's container
  environment, which included `DATABASE_URL` for the Cortex Neon database (role `neondb_owner`, database `synapse_cortex`) with its password. Rotate it:
  Neon console -> project -> Roles -> reset the `neondb_owner` password (or create a new role), update `DATABASE_URL` in
  `~/synapse-cortex/deploy/.env`, recreate Cortex (`docker compose -f docker-compose.vps.yml --env-file .env up -d`), check `/health`. A `neon.tech` URL
  also appears in `~/companion-runtime/deploy/.env` (the Runtime episode store; may be the same or a different role: check in Neon) and in the backup
  copies `~/synapse-cortex/deploy/.env.bak-pre-scoped-apply`, `~/companion-runtime/deploy/.env.bak-pre-window`, `.env.cutover`,
  `.env.pre-cutover-20261001`. After rotation, update or delete those copies. Do not print env files again; use allowlisted keys.
- Rollback tags recorded in §1. Scratch artifacts verified gone (§1).
- Deploy recipe: `ssh deploy@161.97.150.246 'cd ~/<repo> && git pull --ff-only && cd deploy && docker compose -f docker-compose.vps.yml --env-file .env build && docker compose -f docker-compose.vps.yml --env-file .env up -d'` (repos `~/companion-runtime`, `~/synapse-cortex`).
- Replay recipe: scratch Postgres container on a throwaway docker network, `deploy-api:latest` with the repo `src` mounted, env copied from the Cortex
  container with `DATABASE_URL` pointed at scratch; delete the transcript and containers afterwards and verify.

## 7. Unresolved questions carried forward (do not "fix" these in passing)
1. **Temporary drift vs durable change:** the acute/provisional/durable mechanism exists and replays well; whether a real long chat promotes drift
   correctly (and the promotion policy thresholds) is unproven. Also: should durability sit on narrative entries, not only objectives/dimensions?
2. **Constitution vs dynamic objectives:** per-character wording in the registry; how the reconciler's tension note should evolve over weeks.
3. **Honcho actual behaviour:** summaries/derivations with reasoning disabled are code-verified but not observed; decide whether the interpreter should
   depend on them.
4. **Sophie convergence:** interpreter emits Expectations/OpenLoops? reminder semantics (product decision); retire turn extractor / CurrentMeaning /
   narrow-lane duplication; decide what Sophie's grounded policy needs beyond the current downgrade rule.
5. **Remaining unread semantic boundaries:** Honcho deriver/dream prompts; Jev pack contents beyond `overview_scope`; extractor prompt wording; Cortex
   ingest "zero-yield rescue/revision" machinery; the Runtime episode ledger's own semantic decisions; `longitudinal_read` (eval scaffold).
6. **Staged Jev A0-A3 retrieval:** today a depth ladder (`memory_relevance`, `overview_scope`, Cortex working set), not the designed two-stage aperture.
7. **Per-stage coverage / moving frontier:** `covered_through` per producer only; Runtime retires nothing on it.
8. **Unified observability:** one trace for Jev decision -> evidence fetched -> interpreter output -> Cortex change -> packet to foreground.
9. **Executive function (Layer 3):** attention over time, planning, initiative, action selection, tools/receipts, observation, revision.

## 8. Backlog in dependency order (proposal; the next instance owns the decision)
1. Observe sustained real RPD2 use; fix what real sessions show (cheap, grounds everything).
2. Observability: one cognition trace per turn/checkpoint (prerequisite for judging every later change).
3. Layer 2 ownership map: for each meaning/state transition name exactly one owner; resolve the Runtime ledger vs interpreter duplication; trace the
   unread boundaries (§7.5).
4. Sophie convergence onto the interpreter (needs the product decision in §7.4), then retire Cortex ingest duplication.
5. Staged retrieval (A0-A3) and per-stage coverage once ownership is clean.
6. Durability evaluation in sustained use; red-team recovery replays at scale.
7. Layer 3 executive function, designed over a boring Layer 2.

## 9. Read first
`docs/NEXT_INSTANCE_HANDOFF.md` (this), `docs/COGNITION_ARCHITECTURE.md`, `docs/SEMANTIC_BOUNDARY_INVENTORY.md`, `docs/WORLD_CONTRACT.md` (design history;
partly superseded: the interpreter replaced the Flash Lite producer and the conditional judge), the two audits + ChatGPT review (from the user), memory files
`feedback_determinism_never_replaces_semantics`, `feedback_cost_and_eval_discipline`, `project_constitutional_objective_and_trajectory`,
`project_cognition_architecture_state`, `project_continuity_architecture_boundaries`. Key code: Cortex `src/services/world_interpreter.py`,
`world_materializer.py`, `world_model_service.py` (`build_world_layer`, `build_continuation`), `turn_working_set.py`, `src/routers/v1_world_delta.py`;
Runtime `companion_core/runtime/cutover_executor.py`, `world_checkpoint.py`, `resident_state.py`, `episode_state.py`, `policy/tier1.py`,
`adapters/cortex/client.py`, `adapters/honcho/client.py`. Tests that encode the principles: `tests/test_world_materializer.py` (Cortex),
`tests/test_continuation_prompt.py`, `tests/test_cortex_checkpoints.py` (Runtime).
