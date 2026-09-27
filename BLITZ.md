# Companion Blitz — cockpit

> Mutable. Today, this week, who owns what, what branch, what won, what dies.
> No essays. Canonical docs live here (single copy — never fork):
> `docs/COMPANION_NORTH_STAR.md` → `docs/COMPANION_CANON.md` → this file.

## BLITZ CLOSED — 2026-09-27

### Why the blitz happened
We had accumulated capable components but had not proven they formed one
coherent longitudinal loop. The recurring failure pattern was: per-turn
semantic patching; state in incompatible namespaces; evidence dropped at
boundaries; ranked attention not reaching foreground; actions without durable
feedback; long-session evidence mechanically covered but not honestly
semantically completed.

### What the blitz established (milestones, not commits)
- Live context and durable cognition are different jobs (hot packet vs
  reconstruction/ledger).
- Session/boundary reconstruction is the primary durable-understanding
  mechanism; per-turn semantic extraction stays opportunistic hot-path,
  never semantic authority.
- Durable lane identity is stable across temporal sessions;
  temporal_session_id is provenance, never a separate namespace.
- Cortex owns authoritative durable start state; raw transcript stays
  canonical; server-owned snapshots beat caller-supplied state.
- Receipts/consumed evidence are quotable factual evidence; checkpoints
  are navigation-only, never evidence.
- Long sessions segment without silent truncation (bounded raw windows,
  apply-continue/prior-proposal context, explicit coverage accounting).
- Packing completeness and semantic completeness are distinct; both are
  required for a run to be complete.
- Failed semantic segments stay visible and retryable (skip-covered,
  transcript-pinned, chained runs, stable idempotency keys).
- Partial runs persist successful windows honestly and stay explicitly
  partial — no atomic rollback of good grounded state, no silent partial
  truth.
- Attention ranking reaches handover/runtime; available never forces
  surfacing; HOLD creates no false delivery history.
- Owed and available share one receipt-identity contract
  (`recurring_occurrence`/`attention`/`open_loop`/`clarification`/
  `expectation` + version-fenced); reactions feed future attention across
  sessions (welcomed→answered, redirected→ignored, refused→dismissed,
  neutral→still-open); new evidence revives fatigued matters; suppression
  and resolution remain dominant.

### Graduation statement
**Operational Longitudinal Cognition Substrate — Graduated Baseline.**
Cortex: `9aadba5`. Runtime: `00e8364`.
Graduated means: coherent enough to build products and higher cognition on;
not frozen forever; future changes require evidence of a violated substrate
invariant rather than interpretation imperfection.

### What is parked (may return in its own phase; none reopens this blitz)
Further Track D/E rescue work; generic per-turn semantic patching; pressure
coefficient tuning; organic-proactive authority policy; daily/idle
consolidation; universal relational ontology; broad Jev insertion; further
replay/evaluation infrastructure; task/product UI; dentist/same-matter
interpretation; pronoun/reference interpretation; title hygiene;
affirmation-only semantic ratchets; RPD2 rupture/repair interpretation;
the 0029/SQLite migration incompatibility (pre-existing, dev-only,
production Postgres unaffected).

## Canonical baseline (minimum trusted content — NOT a HEAD pin)

- `synapse-cortex` CANON CONTENT BASELINE: `6ae9df9` (2026-09-26 — programme
  centre first commit holding North Star / Canon / BLITZ).
- Agents do NOT require current HEAD to equal `6ae9df9`. Legitimate descendant
  commits are expected. Verify with: `git merge-base --is-ancestor 6ae9df9 HEAD`.
- Report current HEAD separately in every handoff. STOP only if: canonical files
  are missing; `6ae9df9` is not an ancestor of HEAD; the repo/workspace is not
  the authorised one; or unexpected state makes continuing unsafe.
- Authorised local blitz execution branch is `main`. Do NOT instruct agents to
  switch to or check out other branches in the shared dirty workspace.
  `blitz/hot-path` and `blitz/behaviour` remain logical workstream names only.

## Agent bootstrap — hard requirement

Work from the existing canonical local checkout. Do NOT clone a fresh copy
unless explicitly instructed. Canonical workspace: `/Users/mukeshkumar/play/`.
Remain on the current authorised branch (`main`); do not switch branches unless
explicitly authorised.

Before doing any work, verify these files exist:

- `synapse-cortex/docs/COMPANION_NORTH_STAR.md`
- `synapse-cortex/docs/COMPANION_CANON.md`
- `synapse-cortex/BLITZ.md`

Then verify the content baseline is an ancestor of your HEAD:

- `git -C synapse-cortex merge-base --is-ancestor 6ae9df9 HEAD`

If ANY file is missing, or the baseline is not an ancestor, or the
repo/workspace is not the authorised one: STOP. Do not substitute older docs.
Do not infer product intent. Do not create replacements. Report branch, HEAD,
and which check failed. Before modifying code report: repo, branch, HEAD,
working-tree status, canonical-doc existence. Do not reset, checkout, rebase,
clone, pull, or overwrite another agent's work unless explicitly authorised.

## Read first

1. `docs/COMPANION_NORTH_STAR.md`
2. `docs/COMPANION_CANON.md`
3. This file.

Do not redesign product intent from implementation. Architecture is disposable.
New architectural ideas are hypotheses. Product norms are authorship — do not
infer them from code.

## Current objective

Untangle 12 months of R&D into one coherent working substrate without losing
proven companion behaviour.

## Success this blitz

- Foreground gets room to behave autonomously.
- Correct small context reaches it (session orientation + tiny turn deltas).
- Live matters persist across time; new evidence can revise them.
- Existing successful relational behaviour does not regress.
- Duplicate / governor paths begin disappearing.

## Track A — Truth / recovery (owner: Spark, reviewer: programme lead)

- Status: first pass delivered 2026-09-26; Track B facts folded in; awaiting Track C governor map.
- Output:
  - `docs/BLITZ_MECHANISM_INVENTORY.md` (25 mechanisms + orphans + dead list; Track B verified facts folded at top).
  - `docs/BLITZ_REGRESSION_CORPUS.md` (C1 Isa bad arc — NEEDS-FREEZE, held by user; C2 Elena/RPD2 wins; C3 Sophie longitudinal + continuity-basics; C4 retrieval probes + reconciliation trio TO-BUILD; C5 morning/re-entry fixtures; run protocol included).
  - `docs/PRODUCT_CONSTITUTION_SOURCES.md` (Isa/Sophie pointers with sources; Luna/Bloom/health mostly UNSPECIFIED — highest-risk blank).
- Constitution gaps: Luna/Bloom/healthcare safety + phase norms unwritten; Elena fixture human sign-off pending; Isa transcript freeze pending.
- Blocking: Track C governor map (to confirm/overturn DUPLICATE* rows #1/#7/#8).

## Track B — Hot path / substrate (owner: Codex, reviewer: Claude Code, adversarial: DeepSeek/GLM)

- Branch: `blitz/hot-path`.
- Status: candidate cut implemented; handshake retained; packet reuse validated/future; likely-garbled transcript memory work safely gated; counterparty promises blocked from companion/user action authority.
- Verified local heads for the counterparty-authority session: companion-runtime `118d249`; synapse-cortex `e2f0c50`; rpd2 `7e5167b`, all on `main`; canon baseline `6ae9df9` is an ancestor of synapse-cortex HEAD. Existing dirty checkout changes preserved.
- Output: `docs/TRACK_B_CURRENT_HEAD_HOT_PATH_2026-09-26.md`.
- Live path: app persists user turn + reads chronology/session state/day packet → Runtime durable turn claim → parallel epistemic/Honcho/Cortex/current-meaning barrier → selective prompt modules → Sophie foreground model → Runtime durable result → app durable assistant message → async session/semantic/Honcho/Cortex writeback.
- Verified duplication: Cortex packet compiler runs 2x on a continuing session (attention + handover preview), 3x on session entry (+ handshake); handover normally replaces the broad packet in the prompt; handshake is not independently rendered.
- Verified dormant on ordinary turn: Cortex `/route`, both working-set endpoints, and neutral candidates as a generation input (`candidates/query` only reaches the decision record).
- Verified live delta/reconciliation: `current-meaning/revise-sync` runs in the parallel barrier, may version durable meaning, and renders only with live `active` authority.
- Cut: companion-runtime defaults `SYNAPSE_CORTEX_CANDIDATES_QUERY_ENABLED=false`; setting it to `true` restores the compatibility fetch. Normal turns make one fewer Cortex request.
- Parity evidence: candidate-on vs default-off returned identical Cortex context excluding inert `neutralCandidates`, byte-identical foreground prompt, identical selected/omitted prompt modules, no candidate receipt/write request, and no warnings. Runtime only recorded fetched candidates as rejected compatibility metadata; `candidate_refs` stayed empty, so the app enqueued no delivery receipt. Deterministic 50ms candidate delay was removed from the adapter barrier (asserted improvement >30ms).
- Handshake parity result: NOT SAFE TO GATE/REMOVE. With vs empty handshake projection had identical authoritative entry context, orientation, continuity/handover, prompt bytes, prompt modules and routing, but handshake uniquely populated returned `CortexContext.daypart`, `live`, `avoidSurface`, and `memoryRefs`. It adds one new-session request and can sit on the gather barrier; a synthetic 50ms response measured >=45ms. It invokes the same mutation-capable attention compiler, adding no unique lifecycle mutation beyond that duplicate compiler pass.
- Attention/preview parity result: substituting the exact committed attention response at preview's internal packet boundary preserved the public handover byte-for-byte after excluding timing metrics, including agenda/admission/scene/owed/available/avoid. In the seeded SQLite fixture it reduced preview from 26 to 8 SQL statements and measured 19.1→5.05ms end-to-end (compiler metric 15.2→2.8ms). The required attention read durably expired one suppression, created one daily occurrence and dismissed one stale clarification; both preview arms remained zero-write, and eligibility reads created no surface receipt. Production consolidation was not made: attention and preview are separate HTTP requests/transactions and no existing request contract transfers the packet; process-local caching would be unsafe under concurrency/multi-worker routing, while adding a packet/schema/combined-endpoint contract is outside this surgical session.
- Honcho cost result: `run_memory` starts on every configured turn in the initial gather. It always pays one structured compiler call (default `deepseek/deepseek-v4-flash`, 10s timeout); a positive decision at confidence >=0.65 then performs live peer get-or-create plus targeted chat, or conclusions query with user-message search fallback (12s aggregate retrieval timeout). Ordinary social/emotional turns later use `react/none`, so fetched memory cannot render, but the Director plan does not exist when the parallel call starts. Non-ordinary Director evaluation also consumes `memoryAvailable`, so prompt omission alone is not a safe pre-gate.
- Honcho cut: default-on `HONCHO_SKIP_INELIGIBLE_TRANSCRIPT_MEMORY` skips compiler/retrieval only for `likely_garbled` transcripts; `false` restores compatibility. That status is already forced by the transcript guard to reply/social ordinary bypass and is excluded from TurnEvent/prompt memory. `uncertain` deliberately still runs. Harness: rendered callback memory, omitted ordinary memory, compiler-negative/no-retrieval, compatibility-on vs default skip, and uncertain false-negative control. Prompt bytes (apart from wall-clock normalization), modules, routing/decision record, response and warnings were unchanged; one compiler+retrieval call and a synthetic 40ms barrier member were removed, with no peer creation or receipt. The durable terminal turn now records an empty Honcho packet for skipped turns instead of unused retrieved text; no downstream dependency on that diagnostic payload was found.
- Counterparty-authority root cause: external feed identity already survives ingress as `external:<sender>`, and model candidates retain actor attribution, but `CommitmentCandidateService.upsert_from_candidate` previously trusted model `authority=act`/`character_promise` after ownership resolution. Unknown reported actors deliberately fall back to the turn sender, so “Sam said he’d send” could inherit user ownership; `evaluate_due` then violated every pending temporal ACT row without an owner-kind check.
- Counterparty-authority cut: the commitment persistence boundary now treats trusted `external:*` ownership, explicit `counterparty_promise`, and attributed third-party reported-future speech whose actor differs from the resolved owner as `counterparty_promise + ASK`. Evidence/title/timing remain stored; ASK never enters due violation. Re-observation cannot promote these rows to ACT. Genuine user and companion promises retain existing ACT/class/lifecycle behavior. No names or fixture strings are special-cased.
- Counterparty tests: failing-first Carlos and Studio Sam external-feed fixtures, a user-reported Studio Sam regression, and a genuine user positive control. Focused commitment/bilateral/violation/surface suite: `27 passed`; only pre-existing datetime deprecation warnings. Model Sophie scenarios were not rerun because model mode requires paid external calls; the focused fixtures reproduce the exact persisted shapes from the blinded checkpoints.
- Downstream finding for Track C/Claude: the same blinded Scenario 3 also contains an external Studio Sam statement misfiled as a user-intention expectation, and later evidence may leave counterparty ASK evidence pending. Those are expectation classification/reconciliation defects, not caused by the commitment authority fix; no closure or expectation machinery was changed here.
- Tests: companion-runtime Honcho/memory/telemetry/guard/contracts focused suite `34 passed`; API/adapter/parity sweep `41 passed, 1 pre-existing failure` (`test_parity_emotional_judgment_turn` expects `chat-model` fallback while current HEAD returns the pinned Gemini model; reproduces alone and is outside this diff). Cortex packet-reuse parity plus entry/context/lifecycle suites pass. Warnings are pre-existing dependency/datetime deprecations.
- Delete after win: candidate compatibility branch and `neutralCandidates` decision-record plumbing after rollback window; attention packet remains protected because its reads mutate state.
- Next smallest bounded cut: measure how often ordinary-bypass turns fetch memory that is later omitted. Any broader gate must use an authority available before `run_memory` without serializing eligible retrieval or removing `memoryAvailable` from non-ordinary Director evaluation; current evidence does not authorize one. Candidate compatibility cleanup remains safe after its rollback window.

## Track C — Behaviour / trajectory (owner: Claude Code, evidence: Spark, judge: Gemini, support: Codex)

- Branch: `blitz/behaviour`.
- Status: governor map delivered 2026-09-26; one bounded patch made.
- Verified local heads used for tracing: companion-runtime `547e848`; rpd2 `7e5167b`; synapse-cortex `705f5a6`.
- Output: `docs/BLITZ_GOVERNOR_MAP_2026-09-26.md` — full mechanism-by-mechanism map (companion-runtime, rpd2, synapse-cortex) with lifecycle/control-strength classification, cited file:line evidence, and verification of the prior cloud session's 5 hypotheses (4 confirmed/partially-confirmed, 1 not independently locatable by name).
- Confirmed over-governance finding: `companion-runtime/companion_core/policy/perception_gate.py`'s own docstring claims "telemetry only, never changes routing" but its wiring in `turn_executor.py` forced Dual Aperture to HOLD by default on ordinary REPLY_ONLY turns whenever a cheap semantic classifier scored the turn as not matching a fixed "problem" wake-list — denying the foreground's own initiative mechanism (ENRICH/LEAD) a chance to run on turns that simply weren't a rupture/ambiguity/tool-need case. Default was enforcing (`PERCEPTION_GATE_OFF` defaulted to `"0"` = gate ON).
- Patch made (see doc for full detail): perception-gate suppression of Dual Aperture now requires explicit `PERCEPTION_GATE_ENFORCE=1`; default is shadow-only (the classifier still runs and logs every eligible turn, unchanged). `PERCEPTION_GATE_OFF=1` remains a hard kill-switch. One-flag, reversible, no new architecture.
- Quiet-turn gate for CurrentMeaning (prior cloud session's speculative patch): NOT ported. No quiet-turn/triviality gate exists anywhere in synapse-cortex for CurrentMeaning or attention-packet compilation (verified by exhaustive grep); none is justified — no evidence of harm, and Canon explicitly prefers unnecessary interpretation over suppressing meaningful short turns ("thanks ❤️", "fine" carry real relational weight depending on trajectory).
- Corrections flagged to other tracks: Track A inventory row #10 (Director) says 17 moves — current rpd2 HEAD has 21 (`lib/ai/moves.ts`); Track A inventory row #19 ("Release/backgrounding-v1, first-beat, sustain/yield") has zero footprint in synapse-cortex — likely mislabeled repo or stale; Track B doc's "CurrentMeaning timeout: code default 1.5s" is not supported by current code (`MEANING_TIMEOUT_SECONDS` defaults to 12 and is dead/unused; live timeout is `AGENDA_RANKER_TIMEOUT_SECONDS`, default 12).
- Not resolved (left open, per Canon §6 non-decisions): Navigator vs Trajectory-observer duplication (rpd2) — confirmed as a deliberate, already-logged A/B shadow comparison, not accidental duplication; do not merge or delete either side without the shadow-agreement evidence the code itself is already collecting.
- Tests: `companion-runtime/tests/test_perception_gate.py` 11/11 pass (new test proves default no longer suppresses Dual Aperture); full companion-runtime suite 321 passed, 14 failed/11 errored, all pre-existing on `main` (Postgres-dependent + unrelated fixture mismatches, verified via `git stash`) — zero regressions from this patch.
- Delete after win: — (no deletions this session; DUPLICATE* rows #1/#7/#8 from Track A remain open pending Navigator/Trajectory-observer shadow-agreement evidence, not overturned or confirmed here).
- 2026-09-27 session (post-counterparty-fix follow-up, HEAD `8170bd9`): fixed the expectation-layer agency defect flagged by Track B (line above) — `ExpectationShaper.shape_expectation` trusted the extractor's free-text `expectation_type_hint` even when the resolved row owner was a non-user external sender, so a counterparty's own first-person promise (Studio Sam: "I'll... send the final signature copy tomorrow") persisted as `owner_peer_id=external:studio_sam` + `ExpectationType.USER_INTENTION` — internally incoherent. Fix mirrors the already-shipped commitment-sink boundary: extracted `is_external_counterparty` from `commitment_candidate_service.py` into the shared `src/services/ownership.py` (both now import one function); `shape_expectation` gained an `owner_peer_id` kwarg and now remaps `USER_INTENTION`/`USER_COMMITMENT` to the existing `ExpectationType.EXTERNAL_DEPENDENCY` whenever the resolved owner is external — no new ontology, no names/fixture special-casing. `v1_events.py`'s one call site now passes the already-computed `row_owner`. Fulfilment/reconciliation code (`lifecycle_service.py`) was verified type-agnostic (matches by owner/content/target_id, never by `ExpectationType`), so Case 3 (later external fulfilment) transitions correctly through unchanged machinery — confirmed by test, not assumed.
- Fulfilment warrant finding: the original (mistyped) Studio Sam expectation's `FULFILLED` transition in the blind S3 run was evidence-correct (matched `external-email-s3_e12`, the real follow-up email) despite the type being wrong — agency/type correctness and evidence-reconciliation correctness are separate axes here, confirmed empirically via the new fixtures rather than assumed.
- Carlos loop-sprawl (documented only, per instruction — no dedupe implemented): root cause is **source-specific loop creation with no cross-message existing-loop check**, not duplicate creation, not failed semantic matching, not lifecycle reminting. `LifecycleService.create_open_loop_if_needed` (`src/services/lifecycle_service.py:844-902`) only dedupes an exact `(workspace_id, message_id, candidate_key)` replay of the *same* extraction event (its sole guard, line 859-866); it has no query for an already-`OPEN` loop about the same real-world matter from an earlier message before minting a new row. Evidence: blinded Scenario 1 (`evals/sophie_longitudinal/raw_outputs/model/scenario_1_raw_checkpoints.md`) shows 4 separate OPEN-loop rows about the identical Carlos-debt matter, one per mention, each from a different `msg-s1_e0{7,9,11,14}` (`6d75bd6e`, `49ff0ebd`, `3b941ffa`, `189bd9e5`) plus 2 earlier genuinely-distinct sub-questions from `msg-s1_e01` (invoice-amount vs Friday-date, correctly separate). Expectations already have a belief-reconciliation supersession step for this exact class of problem (`lifecycle_service.reconcile_new_expectation`, called at `v1_events.py:624`); OpenLoop has no equivalent. Not fixed here per explicit instruction (broad dedupe on title similarity is exactly what was asked NOT to do); flagging the asymmetry and the missing-check location for whoever picks this up, with the same content-overlap primitive already used by `_resolve_targets` (`lifecycle_service.py:601`) as the likely reusable building block rather than a new mechanism.
- Tests (2026-09-27 agency-boundary session): new `tests/test_expectation_agency_boundary.py` (8 cases: unit Cases 1/2 + integration Cases 1-4) all pass; full pre-existing expectation/lifecycle/commitment suite (`test_expectation_classification.py`, `test_extraction_shaping.py`, `test_extraction_semantics.py`, `test_identity_model.py`, `test_counterparty_commitment_authority.py`, `test_belief_reconciliation.py`, `test_expectation_engine.py`, `test_multi_expectation_endpoint.py`, `test_reconciliation_and_candidates.py`, `test_surface_lifecycle.py`, `test_violation_lifecycle.py`) 87 passed, zero regressions; full synapse-cortex suite 391 passed.
- 2026-09-27 follow-up session (HEAD `fe7f793`, post-agency-boundary S3 model run confirmed type/owner correct but title still said "The user will send..."): fixed the residual **derived-title agency mismatch**. Root cause: `ExpectationShaper._clean_title` derives the title purely from the extractor's free-text `observation`; its prefix-stripper only recognized first-person self-reference ("I'll", "I will", ...), not the extraction model's own third-person mis-narration ("the user will ..."), so an EXTERNAL_DEPENDENCY row's title kept asserting "the user" as actor even after the type/owner fix. Raw evidence was confirmed untouched by this: Expectation rows carry no verbatim-text column at all — provenance is the linked `honcho_message_id`/`candidate_key`/source span back to the untouched conversational log, and title/summary are Cortex's own derived description, so correcting them cannot destroy source provenance. Patch: extended the existing prefix-stripper (`_strip_leading_actor_assertion`, same modal-verb family already handled for first person, generalized to its third-person "the user will/is going to/has to/needs to/wants to" narration) plus a deterministic, structural `_owner_display_name(owner_peer_id)` (splits/title-cases the trusted `external:<slug>` provenance string — e.g. "external:studio_sam" -> "Studio Sam" — never a per-name special case, never parses conversation content). When the ownership override already fired (external owner, actor-asserting type) AND a self-referential actor prefix was found and stripped, the title is rebuilt as `"{Owner} will {action}"`; when no recognizable actor-assertion prefix is present, the STOP-clause applies and the title is left exactly as extracted (no fabrication) — verified by a dedicated test rather than assumed. Genuine user-owned rows and unresolved/ambiguous ownership are provably unaffected (existing behavior path, untouched).
- Downstream matcher effect: `lifecycle_service._resolve_targets`'s content-overlap scoring (title/summary/subject_peer_id tokens) can now also match on the owner's name words, which can only add matchable tokens, never remove them; the `target_id`-based direct-match path used by explicit fulfilment resolution is unaffected either way. Confirmed via the existing Case-3 fulfilment fixture, unchanged.
- Tests (this follow-up): 2 new unit tests added to `tests/test_expectation_agency_boundary.py` (ambiguous/unresolved-owner control; STOP-clause "no recognizable actor phrasing" control) plus 3 existing title assertions updated to the corrected, owner-attributed expectation; file now 10/10 pass. Same expectation/lifecycle/commitment suite re-run: 89 passed. Full synapse-cortex suite: 393 passed, zero regressions.
- 2026-09-27 Carlos loop-sprawl session (HEAD `fe7f793`, expectation-agency/title line CLOSED, not reopened): fixed the documented OpenLoop matter-identity gap. Classification confirmed by tracing: not duplicate creation, not failed semantic matching, not lifecycle reminting — the missing primitive was **actor/owner-aware matching**, and specifically that OpenLoop (unlike Expectation) has no `subject_peer_id` column and was never entity-linked at all (commitment/fact/model_entry/expectation rows all call `entity_service.link_candidate_subjects`; open_loop was the one lane missing it — an oversight, not a design choice). `create_open_loop_if_needed` (`src/services/lifecycle_service.py`) only ever deduped an exact `(workspace_id, message_id, candidate_key)` replay, so every mention of a still-open matter minted a fresh row.
- Patch (existing-infrastructure reuse only, no new subsystem): (1) parity fix — OpenLoop creation now calls `entity_service.link_candidate_subjects` exactly like the other four lanes, so loops become entity-linked and therefore findable later; (2) new `LifecycleService._find_reusable_open_loop`, consulted before every new-loop creation: resolves the incoming candidate's `subject_refs` to entities (reusing `entity_service.resolve_mention`, unchanged), looks up existing OPEN loops already linked (via `EntityLink`) to the SAME entity, and only among those requires >=1 shared significant content token via the same `_significant_tokens` primitive `close_answered_loops`/`reconcile_new_expectation` already use (the actor's own name tokens are excluded from that count first, since the entity gate already proved actor identity and leaving the name in would make the check trivially pass for any same-actor pair). This is a deliberate AND, not an OR: unlike expectation supersession (title overlap alone can suffice there), **title overlap alone is never sufficient authority for OpenLoop** — no resolvable shared entity means no reuse, full stop, matching the explicit instruction not to merge on wording alone (Case C: "Carlos payment" vs "Studio Sam payment" never merges, structurally, because the entity gate itself fails, not because of a threshold). Reuse touches only `updated_at` (+ backfills `expectation_id` if newly available) and records an inspectable `promote_transition(rel_type="same_as", ...)` audit edge, reusing the `same_as` relation type that already existed in the schema's `RELATION_VOCAB` but had no consumer — no new ontology value was added. A RESOLVED loop is excluded from the reuse lookup by construction (status==OPEN only), so it can never be silently reopened or mutated by this path.
- Distinct-matter / resolution controls verified by test: same actor + different topic (Case B: payment vs venue details, zero shared non-name tokens) stays two loops; different actors + near-identical wording (Case C: Carlos vs Studio Sam payment) never merges (entity gate fails); a RESOLVED loop is never touched by a later same-actor/same-content mention (Case D); an unresolved matter stays OPEN with no reuse partner (Case E); a candidate with no resolvable `subject_refs` never reuses via content alone (falls back to existing create-a-new-row behavior, the safe default for Case D's "ambiguous actor" analogue at the OpenLoop layer).
- Remaining gap, documented not fixed (STOP-clause, not casually invented): whether a retrospective question about an already-RESOLVED matter ("did Carlos ever send that money?") avoids minting a brand-new loop at all depends on the extractor's own classification of that utterance as open_loop-hint-bearing or not — that classification happens upstream of this fix (no prompt changes were in scope) and was not tested with the paid model. This patch guarantees the RESOLVED row itself is never corrupted or reopened either way; it does not guarantee zero-loop-creation for that specific utterance shape, which would need either extractor-side changes or a new judge-question kind (e.g. "is this a recall query about a settled matter") — flagged for whoever owns extractor prompts next, not invented here.
- Before/after (blinded Scenario 1 evidence, reproduced exactly as a fixture using the model's own historical title wording — including its inconsistent "Carlos'"/"Carlos's"/"Carlos" spellings, unaffected since matching runs on tokens/entities, not exact strings): 4 messages (`s1_e07`/`e09`/`e11`/`e14`) that previously minted 4 separate OPEN loops now produce exactly 1 (the original `s1_e07` row, `status=OPEN`, `updated_at` bumped by each later message) — see `tests/test_open_loop_matter_identity.py::test_blinded_scenario_1_carlos_sequence_collapses_to_one_loop`.
- Tests (this session): new `tests/test_open_loop_matter_identity.py` (7 cases: A–E + no-actor-signal control + direct S1-evidence reproduction) all pass. Same expectation/lifecycle/commitment suite re-run: 95 passed. Full synapse-cortex suite: 400 passed, zero regressions. Did not rerun the paid Sophie Scenario 1 model scenario — the deterministic fixture directly reproduces the persisted shapes from the blinded checkpoint and the extractor's own classification behavior is untouched by this patch.
- 2026-09-27 R2 tranche (HEAD `ea446c4`): three verified R2 benchmark failures — chairs (completion→VIOLATED→resurrected as OPEN), Studio Sam (false self-commitment surviving the type/agency fixes), school-trip (duplicate ACT commitments + dead bank-feed evidence) — traced to **two shared root causes**, not three independent bugs:
  (1) **`CommitmentCandidate` had no terminal "done" state at all** (only PENDING/MATERIALIZED/DISMISSED/EXPIRED/VIOLATED — no `FULFILLED`, unlike `Expectation.OutcomeState`) and **no consumer ever wired completion evidence to it** (Expectation/OpenLoop both have this; commitments never did) — so a genuine self-commitment ("I promised the venue I'd confirm chairs... so that's done") could only ever wait to VIOLATE, and a bank-feed payment could never close anything.
  (2) **`implicit_self_commitment`+ACT was granted without checking the evidence actually contains first-person commitment language** — "Sam ... said he'd send the revised contract" and "Andree ... needs the school money" both became the SENDER's own ACT obligation despite containing no self-commitment by the sender at all (third-party reported promise / third-party reported need, respectively) — the existing counterparty-authority check's actor-distinctness gate can miss this when the extractor doesn't attribute a distinct `actor_peer_id`, and pure "no promise at all" cases don't match its reported-future regex either.
- Patch (1) — `models/commitment_candidate.py`: added `CommitmentCandidateStatus.FULFILLED` (direct parity addition, mirroring `Expectation.OutcomeState.FULFILLED`, not a new architecture). `commitment_candidate_service.py`: new `try_fulfill()`, wired into `v1_events.py` alongside the existing `handle_outcome_mutations` call. Deliberately **owner-agnostic in its search** (matches the already-shipped, owner-agnostic Expectation-outcome-mutation pattern) because completion evidence legitimately arrives from a different sender than the commitment's owner (a bank feed closing the user's own obligation) — scoping to the current message's sender would silently miss exactly the cross-source case this exists to fix. Structured-first: explicit `target_id` trusted directly; otherwise `_significant_tokens` overlap is used only to retrieve/rank candidates (cheap prefilter, never sole authority) — a strong deterministic overlap (>=2 shared tokens, same bar as the existing `_fulfill_grounded` precedent) proceeds directly, a weaker one is confirmed by the existing `semantic_judge` "fulfils" question, and anything left ambiguous (no clear single winner, or the judge unavailable/unconvinced) is left PENDING rather than guessed — per the addendum, uncertainty holds provisionally and never becomes a clarification question.
- Patch (2) — `commitment_candidate_service.py`: new deterministic `_FIRST_PERSON_COMMITMENT_RE` floor, gating ACT authority for `implicit_self_commitment` candidates on the evidence actually containing first-person commitment language ("I'll/I will/I'm/I'd/I promise/..."). Fails CLOSED to ASK (the safer state, since ACT is what can later VIOLATE) when absent — this is a narrow grammatical-attribution check, not a semantic-identity/merge decision, so a deterministic floor is the right tool; no existing judge-question actually asks "who is the actor of this commitment" (the closest, "undertaking", asks genuineness-vs-joke, not attribution), so one was not force-fit — documented rather than misused. Preserves the row as useful ASK evidence (never deleted/suppressed), consistent with "preserve useful state."
- Patch (3), Problem A's retrospective-resurrection half — `lifecycle_service.py`: new `_already_resolved_elsewhere()`, consulted by `create_open_loop_if_needed` when the existing entity-based reuse check (previous session) finds nothing (e.g. "chairs" has no resolvable person-entity). Reuses the `semantic_judge` "resolves" question (repurposed — earlier=the new question, later="Already completed: <fulfilled commitment / resolved loop>" — not a grammatically perfect fit but the right question, and adding a new judge-kind for this narrow a need was judged not worth it) over a lexically-prefiltered, bounded set of FULFILLED commitments (same owner) and RESOLVED loops (same session). Fails OPEN (creates the loop as before) when no judge adapter is configured or nothing is confirmed — documented, tested limitation: this half of Problem A only self-heals when a semantic-judge adapter is actually wired at runtime.
- Semantic matching approach: no step in any of the three patches uses lexical/keyword overlap as final authority for a merge/resolution decision. Token overlap appears only as (a) a cheap retrieval/ranking prefilter narrowing which rows reach the judge, or (b) a same-bar-as-existing-precedent deterministic shortcut when overlap is unambiguously strong (>=2 tokens, matching `_fulfill_grounded`'s already-shipped bar) — genuinely uncertain cases are confirmed by `semantic_judge` or left unresolved, never guessed, and uncertainty never spawns a clarification question.
- Pendulum controls verified by test: a completion-evidenced commitment never later violates (A1/A1b); an unresolved commitment still violates normally (A3, over-persistence fix must not cause blanket non-violation); a genuine first-person commitment keeps ACT (B2); a downgraded-to-ASK row can still be promoted to ACT by later explicit corroboration (existing mechanism, now gated through the same marker check, unaffected); two equally-strong candidate matches for one piece of fulfilment evidence stay PENDING rather than guessing which one it means; superficially-overlapping-but-unrelated evidence (shared amount, no real content match) does not close a commitment.
- What remains unfixed, documented not hidden: (a) the retrospective-resurrection guard is judge-adapter-dependent (fails open without one — see Patch (3) above); (b) **"pay school money" (now ASK) and "pay for school trip" (ACT) remain two separate `CommitmentCandidate` rows** for what is arguably one real-world obligation — the marker-gate fix removes the actual harm (only one row can ever violate; the ASK row is inert), but `CommitmentCandidate` has no supersession/same-obligation-linking field analogous to `Expectation.superseded_by_id`, so a clean merge was not attempted here per the addendum's explicit instruction not to casually invent a new ontology mid-tranche when a fitting primitive is missing — documented as the exact next step (add `superseded_by_id` + reuse the existing `semantic_judge` "supersedes" question, mirroring `reconcile_new_expectation`'s pattern exactly) rather than smuggled in as a string-based workaround.
- Tests (this tranche): new `tests/test_commitment_lifecycle_correctness.py` (9 cases: A1/A1b/A3, B1/B2, C-school-authority-split, C3-bank-fulfils-cross-owner, C4-unrelated-evidence-stays-pending, ambiguous-two-match-stays-pending) all pass; 2 new tests in `tests/test_open_loop_matter_identity.py` (judge-confirmed retrospective guard + documented fail-open control) pass. Full pre-existing expectation/lifecycle/commitment suite re-run: 105 passed, zero regressions. Full synapse-cortex suite: **411 passed**, zero regressions. Did not rerun paid Sophie Scenario 1/3 model scenarios — deterministic fixtures reproduce the exact verbatim evidence from the R2 blind packet (`evals/sophie_longitudinal/raw_outputs/blind_judging_20260926_r2/RUN-Z/`) directly.
- 2026-09-27 Spark-audited follow-up (HEAD `9cfcee9`, banked at `b1dea0e` + canon uncertainty principles 11-13 at `9cfcee9`; this tranche does NOT reopen that banked work): Spark's audit accepted `FULFILLED`/the fulfilment consumer/the retrospective-resurrection guard as sound, tightened `try_fulfill`'s deterministic shortcut (a >=2-token match may no longer fulfil when a competing candidate exists — sole-candidate only; do not undo this), and rejected `superseded_by_id` as the wrong primitive for the school-trip duplicate (same thing observed twice ≠ replacement — supersession is for correction/reschedule/newer-plan-replaces-older, not for two mentions of one obligation). This tranche owns the two problems that produced: **A — commitment same-matter identity** and **B — semantic actor attribution**, generalizing (not copying) the OpenLoop entity-identity principle and replacing the ACT floor's implicit assumption that a regex is semantic authority.
- **Problem B (actor attribution) mechanism**: the `_FIRST_PERSON_COMMITMENT_RE` floor is now explicitly a cheap, hard-boundary GUARD only — it short-circuits (skips a model call) only when it agrees AND the evidence is not quoted/reported-speech (a literal "I'll" inside a quotation no longer short-circuits — closes a real gap Spark's audit flagged). Whenever the marker is absent, defeated, or the evidence is otherwise gray-zone, a new semantic-judge question — `self_undertaking` ("does the EARLIER-named party [the sender] personally undertake this, vs a third party, vs nobody") — decides, with the sender's own peer-id passed as CONTEXT (not a name special-case) so named-self reference ("Mukesh will sort it" when Mukesh IS the sender) can be recognised generically. Fails CLOSED to ASK on any unavailability/no/unclear verdict. Regex remains as the ONLY thing gating whether the (bounded) model call happens at all on the common case — it is never itself the semantic authority anymore.
- **Problem A (commitment same-matter identity) mechanism**: generalises OpenLoop's entity-AND-content principle rather than copying its code, because commitment semantics genuinely differ — a DISMISSED/VIOLATED/FULFILLED/MATERIALIZED commitment must never silently absorb new evidence (only PENDING rows are eligible, unlike OpenLoop's OPEN-only-but-otherwise-permissive scope). New `CommitmentCandidateService._find_same_matter_commitment`: an `EntityLink` match (completing the SAME already-existing `object_type="commitment"` linking the router already performed — `_link_subjects("commitment", ...)` — just newly *consulted*, not newly created) is REQUIRED before anything else runs; confirmation uses a second new judge question, `same_matter` ("do EARLIER/LATER describe the SAME specific obligation, not just the same topic/actor"), explicitly worded to make A3 (same actor, different obligation — trip payment vs permission form) safe by construction rather than by threshold. Lexical overlap appears nowhere in the decision: entity-matched PENDING candidates are all sent to the judge (bounded to 5, ordered by recency, never filtered by word overlap first) specifically so A4 (cross-language/poor-lexical-overlap paraphrase) is not defeated by an English-token dependency. Zero or >1 confirmed matches (A5, ambiguous) creates a new, distinct row rather than guessing — matching this file's own stated principle that a wrong merge is worse than a duplicate. On confirmed match: evidence is APPENDED (not overwritten, "evidence accumulates") and a `same_as` audit relation is recorded (same existing, previously-dormant relation type the OpenLoop fix already reuses).
- Shared vs separate: the two problems share the SAME structural primitive (`entity_service`/`EntityLink`) and the same posture (structured identity gates before any semantic step; semantic judgement — never lexical overlap — resolves genuine ambiguity; fail-closed/fail-open chosen per which side is safer for that specific decision), but were kept as two independent code paths and two independent judge questions (`self_undertaking` vs `same_matter`) — they answer different questions (who acts vs which matter) and forcing them into one call/one kind would have produced a worse-fitting question for both.
- Uncertainty behaviour (Canon §2.12/13, newly landed): neither mechanism ever escalates ambiguity into a clarification question — B7 (ambiguous actor) and A5 (ambiguous matter) both fail to the safe, non-mutating state (ASK / a new distinct row) silently, for the foreground to resolve socially if it chooses, not for Cortex to interrogate over.
- Tests (this tranche): new `tests/test_actor_attribution.py` (10 cases: B1-B8 + no-adapter control, including B6/B6b quotation/reported-speech defeating the marker and B3 proving owner-identity-as-context works generically) and `tests/test_commitment_matter_identity.py` (7 cases: A1-A5 + no-adapter control + no-shared-entity control, including one genuinely poor-lexical-overlap/cross-language A4 case) — 17/17 pass. Regression sweep (commitment/expectation/lifecycle/counterparty/semantic-pipeline, 17 files): 136 passed. Full synapse-cortex suite: **433 passed**, zero regressions (validated in a clean window — a parallel Spark session iterating on a separate Honcho/history-recruitment investigation in this same shared, uncommitted workspace caused intermittent, unrelated `sqlalchemy`/"no such table" contention against the shared `/tmp/synapse_test.db` test database during several earlier attempts; this is environmental test-infra contention between two concurrently-running agents sharing one file, not a defect in this tranche — confirmed by observing the other session's own `git stash`/pytest cycles in `ps aux` and by this tranche's files passing 100% in every isolated run).
- Delete after win: —

## Eval / judge (owner: Gemini)

- Status: waiting on corpus freeze.
- Task: behavioural scoring sheet (agency, continuity, initiative, character integrity, over-governance, passivity, poisoned trajectory, repair-as-action) for before/after runs. Read conversations, not just scores.

## Red team (DeepSeek / GLM)

- Status: waiting on diffs. Bounded question only: "what regression does this introduce?" with canon clauses attached. No fresh architectures.

## Bounded worker (Agnes, probation)

- Status: unassigned. Candidates: frozen-corpus CLI runner emitting standard results; current call-graph extraction. Small, self-contained, tests included.

## Decisions (dated, one line)

- 2026-09-26 — Canon signed; architecture subordinate to canon.
- 2026-09-26 — North Star + Canon + Blitz are the three canonical docs (single copy here).
- 2026-09-26 — Reconciliation before ambient; watch-eligibility before any all-vs-all matching.
- 2026-09-26 — Track A first pass delivered (inventory + corpus manifest + constitution sources); filenames per assignment (`BLITZ_MECHANISM_INVENTORY.md`, `BLITZ_REGRESSION_CORPUS.md`, `PRODUCT_CONSTITUTION_SOURCES.md`); Track B hot-path facts folded into inventory.
- 2026-09-26 — Corpus C2–C5 approved/frozen; C1 stays PRIVATE_FIXTURE / NEEDS LOCATION (not blocking). `docs/GEMINI_EVAL_PACKET.md` created (E1–E6, result/interpretation split, runnable-vs-transcript-only per item; no scoring framework — Gemini's job). Track B sessions 2–4 folded: candidates default-off with parity; handshake retained (daypart/live/avoidSurface/memoryRefs unique); projection reuse VALIDATED OPTIMISATION / NOT AUTHORISED FOR IMPLEMENTATION; read-mutations verified as 3 classes.
- 2026-09-27 — Track B corrected counterparty commitment authority at the persistence boundary: external/reported third-party promises remain ASK evidence and cannot become due/VIOLATED user or companion commitments; expectation/closure follow-ups remain separate.
- 2026-09-27 — Track C corrected the matching expectation-layer defect: `ExpectationShaper` now forecloses `USER_INTENTION`/`USER_COMMITMENT` and remaps to existing `EXTERNAL_DEPENDENCY` when resolved ownership is a non-user external sender (same `external:` provenance boundary as the commitment fix, shared via `src/services/ownership.py`). Carlos loop-sprawl documented as a separate, unfixed defect (source-specific `OpenLoop` creation with no cross-message existing-loop check).
- 2026-09-27 — Track C follow-up corrected the residual derived-title agency mismatch: `EXTERNAL_DEPENDENCY` titles no longer assert "the user" as actor (rebuilt as owner-attributed text when a self-referential actor prefix is deterministically found; left as-extracted otherwise — no fabrication). Raw evidence/provenance (`honcho_message_id`) untouched.
- 2026-09-27 — Track C fixed Carlos OpenLoop loop-sprawl: same-matter reuse now requires a resolvable shared subject entity (via existing `entity_service`/`EntityLink`, extended to the `open_loop` lane for parity with commitment/fact/model_entry/expectation) AND non-trivial shared content beyond the actor's own name — never title overlap alone. 4-loop S1 evidence collapses to 1; distinct-matter/cross-actor/resolved-matter cases verified to stay separate.
- 2026-09-27 — Track C R2 tranche (chairs/Sam/school-trip): added the missing `CommitmentCandidate` fulfilment consumer + `FULFILLED` status (owner-agnostic search, matching Expectation's existing pattern) and a deterministic first-person-commitment-marker floor gating ACT authority for `implicit_self_commitment` rows — two shared root causes explaining all three failures, not three separate bugs. Documented, not fixed: `CommitmentCandidate` still lacks a supersession field (`Expectation.superseded_by_id` has no equivalent), so paraphrased same-obligation rows ("pay school money"/"pay for school trip") stay as two rows (one inert ASK, one live ACT) rather than merging — no violation-risk harm remains, but the identity duplication itself needs that primitive added, not smuggled around, before it can be closed.
- 2026-09-27 — Spark audit banked the above tranche with one correction (fulfilment's deterministic overlap shortcut is sole-candidate-only now) and rejected `superseded_by_id` as the fix for school-trip identity (observed-twice ≠ replaces). Canon gained uncertainty principles 11-13 (evidence ≠ interpretation ≠ certainty; uncertainty held privately, never auto-escalated to the user; history as evidence for live ambiguity). Track C's follow-up generalised OpenLoop's entity-identity principle to `CommitmentCandidate` (new `_find_same_matter_commitment`, entity-match required before any semantic step, confirmed via a new `same_matter` judge question) and replaced the regex actor floor with a proper semantic-judge question (`self_undertaking`, sender identity passed as context) so the regex is now only ever a cheap short-circuit guard, never the authority itself.

## Open questions (genuine undecided only)

- Universal/shared mechanism vs shared contract for behavioural selection?
- Exact intervention ladder implementation?
- Transient vs durable boundary; thread lifecycle vocabulary?
- Watch-list mechanism (ingest intersect vs query-on-due vs subscriptions)?
- Tier-0 persistence?
- Session-close durability owner?

## Delete queue (cut once replacement wins regression — git remembers)

- (empty — nominations from Tracks B/C land here with evidence)

## Agent handoff format (required — end every work report with this, no essays)

```text
WHAT I CHANGED
WHY IT SERVES THE NORTH STAR
CANON PRINCIPLES TOUCHED
EVIDENCE / TESTS
WHAT I DID NOT CHANGE
REGRESSIONS / RISKS
DELETE CANDIDATES
OUT-OF-SCOPE FINDINGS
EXACT NEXT STEP
```

## Regression corpus (frozen — see `docs/GEMINI_EVAL_PACKET.md` for item sheets)

- C1 Isa 2026-09-26 transcript (bad arc): PRIVATE_FIXTURE / NEEDS LOCATION — not blocking.
- C2–C5 APPROVED/FROZEN: Elena/RPD2 wins, Sophie longitudinal blind baseline, retrieval probes, re-entry/morning, mechanism evals (Condition-C, union-selector, subtraction, hybrid, poisoned), keyword/scene-loop negatives.
