# Track B — current-HEAD Sophie hot path (2026-09-26)

Scope: one ordinary authenticated Sophie `reply_only` turn. Verified against
committed HEADs (all equal `origin/main`): ash-ai `447164b`, companion-runtime
`351ed35`, synapse-cortex `6da210f`. Uncommitted checkout changes were excluded.

Classifications: `REQUIRED` is on the live reply path and affects its result;
`DUPLICATE` repeats another live read/projection; `LEGACY` is a live fallback;
`DORMANT` exists but does not affect this production turn; `UNKNOWN` lacks proof.

## Current call graph

1. **BFF ingress and canonical pre-write — REQUIRED**
   - `ash-ai/app/(chat)/api/chat/route.ts::POST` is called by `/api/chat`.
   - Synchronous/critical before Runtime: authenticates; reads chat messages,
     cross-chat handshake facts and `CompanionUserState`; computes authoritative
     chronology/re-entry/entry context; persists the incoming user `Message_v2`.
   - Reads the last 40 visible messages by default for the runtime request.
   - Concurrently reads `readCurrentContinuityDayPacket` from app Postgres. This
     is a persisted daily slow-loop artifact; the live turn does not regenerate it.
     Missing/error returns an empty orientation packet and fails open.
   - Calls `lib/companion-runtime.ts::streamCompanionRuntimeTurn`, authenticated
     `POST /v1/turns/stream`, with a 250s BFF timeout and request-abort signal.

2. **Runtime admission/idempotency — REQUIRED**
   - `runtime_api/routes/turns.py::stream_turn` is called by the BFF SSE client.
   - It claims/reuses a durable `companion_runtime_turns` record, then calls
     `_execute_new_turn` -> `TurnExecutionPipeline.execute_turn` with a 240s
     deadline and a 15s lease heartbeat. The terminal Runtime result is durably
     stored; client disconnect detaches streaming but does not cancel execution.

3. **Turn-local gather barrier — REQUIRED as a barrier; mixed usefulness**
   - `companion_core/runtime/turn_executor.py::execute_turn` concurrently runs:
     `run_epistemic`, `run_memory`, `run_cortex`, `run_revise`, and (only when a
     prior trajectory exists) `run_reaction`. The slowest live member delays
     prompt construction.
   - The ordinary social/emotional turn bypasses the session Director, but still
     runs the epistemic model and later Dual Aperture. Behavioural choreography
     is recorded here only to locate substrate consumers; it is Track C.

4. **Honcho compiler and targeted semantic retrieval — REQUIRED**
   - Caller: `run_memory` ->
     `adapters/honcho/client.py::HonchoAdapter.prepare_turn_memory`.
   - First calls a structured compiler model, default
     `deepseek/deepseek-v4-flash`, timeout 10s. If confidence >= 0.65 and older
     context is needed, it calls `_retrieve_relevant_memory`, timeout 12s.
   - Retrieval routing is local/config-only, not Cortex `/route`:
     `HONCHO_RETRIEVAL_MODE=targeted_chat` calls Honcho peer `/chat`; otherwise
     `/conclusions/query` (20 candidates, 10 retained) then user-message `/search`
     fallback (6). It returns a fallible packet capped at 1,200 characters.
   - Compiler/retrieval errors fail open to no memory. Retrieval may get-or-create
     the Honcho peer (durable side effect). The packet reaches the foreground only
     when `select_prompt_modules` sees a Director plan whose `primaryAct` is
     `callback` or `objectAction` is `advance|close`; otherwise it is fetched but
     omitted. Thus Honcho is **REQUIRED conditionally**, with per-turn compiler
     cost even when prompt selection later omits it.

5. **Cortex fan-out — REQUIRED container with duplicate/live edges**
   - Caller: `run_cortex` ->
     `adapters/cortex/client.py::CortexAdapter.fetch_cortex_context`.
   - Config timeout is 1.5s per request. First wave is concurrent:
     - `GET /v1/cortex/attention-packet` — **DUPLICATE / LEGACY**. Router
       `get_cortex_attention_packet` ->
       `CortexPacketService.compile_attention_packet`. It returns the broad
       deterministic lifecycle packet and `continuity_context`. It performs no
       LLM call, but a read can expire suppressions, create daily recurring
       occurrences and touch surface eligibility state, so it is not pure and
       can mutate Cortex Postgres. Its payload is normally replaced in the
       foreground by handover; it remains the fallback if handover is absent and
       also gates the whole adapter (attention failure drops otherwise-successful
       Cortex results). Verified read-side writes are suppression expiry, daily
       recurring-occurrence creation, and stale clarification dismissal. Surface
       eligibility checks themselves are reads and do not consume a receipt.
    - `POST /v1/cortex/handshake` — **REQUIRED projection + DUPLICATE packet
      compilation on session entry; skipped on continuing sessions**. Router `get_cortex_handshake` ->
       `CortexHandshakeService.compile_handshake`, which calls
       `compile_attention_packet` again and projects orientation/daypart/live
       threads/follow-ups/avoid/memory refs. Runtime skips it when app chronology
       says `temporalSession=same`. Its returned handshake is not independently
       rendered: prompt builder explicitly deletes `handshake`; app-owned
       `entry_context` supplies arrival facts. On entry it can repeat the packet's
       read-side durable mutations.
     - `POST /v1/cortex/candidates/query` — **DORMANT for generation**. Router
       `query_neutral_candidates` is a pure Postgres read returning up to 20
       pending recurring occurrences. Runtime stores these on `CortexContext`
       and later only records unselected candidate references in the decision
       record; they do not influence routing, module selection or the prompt.
       Candidate failure independently fails open.
   - Second wave, serial after the first wave:
     - `POST /v1/cortex/handover/preview` — **REQUIRED, but DUPLICATE compilation**.
       Router `preview_session_handover` -> `_compile_session_handover` ->
       `compile_attention_packet` again -> `compile_agenda` ->
       `compute_admission` -> `compile_handover`. It returns the tiny
       `{owed,scene,patterns,avoid,clarifications,available}` product-edited
       handover. The rollback session makes this preview zero-write; background
       agenda refresh is disabled. It feeds Dual Aperture standing context and
       normally replaces the broad packet in the foreground prompt. Failure
       falls open to the legacy attention payload.
   - Net effect on a new session: the same packet compiler runs three times
     (attention, handshake, preview); on a continuing session it runs twice.

6. **Current meaning fast revision — REQUIRED and state-mutating**
   - Caller: parallel `run_revise` ->
     `CortexAdapter.revise_current_meaning_sync` -> router
     `revise_current_meaning_sync` -> current-meaning service helpers.
   - Uses the Cortex agenda model adapter and product meaning lens on the current
     turn, last six active-session messages, prior meaning and Cortex evidence.
     Runtime timeout is `SYNAPSE_MEANING_TIMEOUT_MS` (code default 1.5s; deploy
     record says production tuned to 12s).
   - Returns active/backgrounded/unknown authority; commits a new version only
     for a validated genuine revision, with idempotent revision key and stale-
     prior rejection. Later evidence can therefore revise a live matter.
   - `TurnExecutionPipeline._apply_current_meaning_revision` projects the result;
     `select_prompt_modules` renders it only when authority is exactly `active`.
     Failure fails closed to prompt omission, while preserving prior durable state.

7. **Working-set / snapshot / day-packet status**
   - `POST /v1/cortex/session-working-set` and refresh machinery in
     `src/services/session_workingset.py::compile_session_working_set` are
     **DORMANT** for this production turn: Runtime never calls them.
   - The older `working-set-v1` endpoint is also **DORMANT** on this path.
   - There is no live session-snapshot fetch. App `Chat.sessionRouting` plus
     cross-chat `CompanionUserState.liveSituation/corrections` act as persisted
     start-of-turn session state and are **REQUIRED** inputs; Runtime returns
     `next_session_state`, which the BFF writes asynchronously after the reply.
   - `ContinuityBrief` `daily-packet-v1` is **REQUIRED when present** as an
     app-Postgres read. Prompt builder adds only summary (`luna_brief`, currently
     absent from this packet shape) and orientation; priorities/watchItems/plan
     are not rendered by the current builder. In practice the orientation is the
     live contribution; missing/stale packets fail open.

8. **Prompt module selection — REQUIRED**
   - `companion_core/prompts/sophie_prompt_builder.py::select_prompt_modules`
     selects context, and `build_sophie_reply_system_prompt` assembles it.
   - Handover replaces working-set/full-packet payload; working set replaces
     legacy payload; legacy packet is last fallback. Social intent includes
     handover `available`; non-social intent omits it.
   - Current meaning requires live `active` authority. Honcho memory requires a
     callback/advance/close plan. Entry appears only on new temporal session,
     first contact, or non-continuation re-entry. Provenance is task/mixed only;
     ambient location only for location/weather/travel objectives. Composition
     trace explicitly records selected and omitted modules.
   - Handshake is accepted but deliberately not injected. This avoids one prompt
     duplicate even though its HTTP/DB work may already have happened.

9. **Foreground model and response — REQUIRED**
   - `execute_turn` pins ordinary Sophie to `SOPHIE_FOREGROUND_MODEL`, default
     `upstage/solar-pro4`, then calls
     `ProviderExecutionAdapter.execute_direct_reply_stream`.
   - Provider resolution is normally OpenRouter for slash-qualified IDs (NanoGPT
     only for its allow-list with explicit enablement; Venice can precede generic
     OpenRouter when configured). Provider timeout is 120s; retryable errors walk
     the candidate/fallback chain. Runtime streams deltas and returns a terminal
     `CompletedTurn` containing text, beats, model/provider, packets and trace.

10. **Persistence/writeback — REQUIRED core plus async side effects**
    - Runtime `_execute_new_turn` synchronously/fenced-writes the terminal result
      to `companion_runtime_turns` before completion.
    - BFF `persistStreamedRuntimeReply` synchronously inserts the canonical
      assistant `Message_v2` before finishing the UI stream.
    - Off-path via `after()`, fail-open: persist `next_session_state` and shared
      live situation; schedule initiative; `commitTurnSemantics`; mirror the
      completed user/Sophie turn to Honcho; extract/persist Sophie attention;
      persist stream trace. These do not reach the current foreground prompt.

## Duplication map and target comparison

| Edge | Live classification | Verified mismatch with Track B target |
|---|---|---|
| attention packet -> Runtime | DUPLICATE / LEGACY | broad per-turn reconstruction; usually displaced by handover |
| handshake -> Runtime | REQUIRED + DUPLICATE internals | session-entry projection uniquely populates returned context, but recompiles the packet and is not prompt-rendered |
| handover preview -> Runtime | REQUIRED + DUPLICATE internals | desired tiny surface, but recompiles the same packet serially |
| candidates/query -> decision record | DORMANT | paid live read with no selection or prompt effect |
| current-meaning/revise-sync | REQUIRED | genuine turn delta/reconciliation, but an on-path model call |
| Honcho compiler + targeted retrieval | REQUIRED conditionally | semantic routing exists, but compiler runs every turn and is not coordinated with lifecycle routing |
| Cortex `/route` | DORMANT | advertised semantic/state router is not called by production Runtime |
| session-working-set endpoints | DORMANT | target snapshot substrate exists but is not consumed/cached by Runtime |
| app daily packet | REQUIRED when present | persisted orientation exists; most packet fields are currently omitted |

Session 1 made no code change. The obvious cuts cross fallback, prompt and
read-side mutation contracts; removing one without a focused parity test is not
low behavioural risk.

## Session 2 verified cut — candidates/query

Companion Runtime now defaults the normal-turn `candidates/query` compatibility
fetch off. `SYNAPSE_CORTEX_CANDIDATES_QUERY_ENABLED=true` restores the prior
request for rollback. The Cortex endpoint itself and receipt APIs are unchanged.

Focused adapter parity evidence:

- Candidate-on before arm: four Cortex requests (attention, handshake,
  candidates, handover); candidate present only in `neutralCandidates`.
- Default-off after arm: three requests; no candidate request.
- Returned context was identical after excluding `neutralCandidates`.
- Foreground system prompt was byte-identical and composition traces matched,
  including the same `contextModules=["cortex"]`.
- Neither arm called candidate receipts or another write endpoint; neither
  emitted warnings. Before the cut Runtime only copied the candidates into
  `rejected_candidates`; it did not populate `candidate_refs`, so the app's
  delivery-receipt enqueue was already a no-op.
- A deterministic 50ms candidate response delay was removed from the first-wave
  gather barrier; the test requires an end-to-end adapter reduction above 30ms.
- Focused companion-runtime suite: 38 passed. Compileall and diff check passed.

The next smallest duplicate is the session-entry handshake call: it recompiles
the attention packet and is not independently prompt-rendered. It still populates
fields on `CortexContext`, so the next change must begin with new-session parity
coverage; this session does not gate or alter it.

## Session 3 verified result — retain session-entry handshake

A focused new-session harness compared the real handshake projection with an
empty projection while holding attention, handover, authoritative app entry
context, current user words, prompt plan and routing policy fixed.

Parity held for:

- authoritative `entryContext` and chronology-derived `orientation=returning`;
- `continuityContext`, including the handover projection;
- foreground system-prompt bytes;
- selected/omitted prompt modules (`cortex` + `entry` selected);
- `decide_turn` routing output;
- warnings/errors (none).

Parity did **not** hold for the returned Cortex contract. Handshake uniquely
populates:

- `CortexContext.daypart`;
- `CortexContext.live` from `live_threads`;
- `CortexContext.avoidSurface` from `avoid_surface`;
- `CortexContext.memoryRefs` from `relevant_memory_refs`.

These fields are not selected into the current Sophie foreground prompt when a
handover is present, and current routing did not change in the harness. They are
nevertheless unique returned context and may be consumed by non-prompt/future
callers. The requested removal therefore fails strict parity and was not made.

Request/latency and lifecycle evidence:

- Default candidate-off new-session fetch makes three Cortex calls: attention,
  handshake, then handover. Removing handshake would structurally reduce this to
  two, but would lose the four fields above.
- With a deterministic 50ms handshake response, telemetry and wall time both
  measured at least 45ms, demonstrating that handshake can set the first-wave
  gather barrier.
- Handshake calls `CortexHandshakeService.compile_handshake`, which calls the
  same `CortexPacketService.compile_attention_packet` against a normal writable
  session. It can therefore repeat attention's suppression expiry/recurring
  occurrence effects. No handshake-specific lifecycle write exists outside that
  packet compiler; the unique contribution is its projection.
- Cortex chronology/context/lifecycle regressions passed (17 tests). Runtime
  adapter/API/contract/latency regressions passed (39 tests).

Next candidate: instrument the duplicate packet compilation inside
`handover/preview` versus the required attention read. Any future combination
must preserve attention's mutation-bearing read and preview's rollback/no-write
contract; no consolidation is authorized by this finding alone.

## Session 4 verified result — projection parity, transport blocker

A focused endpoint-level harness first performs the required production-style
`attention-packet` read, captures its returned packet, and then compares normal
`handover/preview` against a test-only arm that substitutes that exact packet at
the internal `compile_attention_packet` boundary. Both arms still execute agenda
reconciliation, admission and `compile_handover` inside the preview rollback
transaction.

Parity held after excluding the intentionally variable `metrics.cortex_ms`:

- the complete public handover projection, including scene, owed, available,
  clarifications, patterns, avoid, constraints and non-timing metrics;
- agenda extraction/ranking and follow-through admission for the same current
  turn;
- durable state after preview: no `AgendaSnapshot` survived and no second
  occurrence or other lifecycle write was committed.

The seeded attention read exercised the known mutation classes before reuse:

- one expired suppression changed from `ACTIVE` to `EXPIRED`;
- one daily `RecurringOccurrence` was created;
- one over-age clarification changed from `PENDING` to `DISMISSED`;
- surface eligibility performed reads only and created no `DerivedSignal`
  receipt. Neither preview arm changed those results.

Query and latency evidence from the deterministic local SQLite run:

- normal preview: 26 SQL statements, 19.1ms request time, 15.2ms reported
  `cortex_ms`;
- captured-packet preview: 8 SQL statements, 5.05ms request time, 2.8ms
  reported `cortex_ms`;
- the remaining statements belong to rollback-scoped agenda snapshot handling,
  admission's latest-turn read, and transaction/savepoint control. The avoided
  statements are the duplicate packet's lifecycle/evidence reads and rollbacked
  writes.

Static query attribution matches the counter. Both packet compilations read the
same owner/session-scoped suppressions, expectations/source objects, open loops
and ask receipts, attention/commitment candidates, recurring intentions and
week/today occurrences, objective progress, sleep/derived signals,
clarifications and surface-registry state. Preview then uniquely reads/locks the
agenda snapshot, reconciles or creates its fallback snapshot, and reads the
latest `TurnStamp` for admission. Those preview-only stages must still run when
the packet is reused.

Request parameters do not invalidate projection reuse within this measured
case: workspace, session, peer, `now` and timezone are identical on both calls;
`turn_text` and `current_message_id` affect downstream handover/admission work,
not packet compilation. `director_hints.product` affects final product limits,
also downstream of the packet.

No production flag was added. The two live operations are separate HTTP
requests and database transactions, potentially served by different processes.
No existing request or response contract transfers the already-compiled packet
to preview. A process-local keyed cache would add race, eviction, identity and
multi-worker correctness questions; a combined endpoint or packet-bearing
request would change the API/schema contract expressly out of scope here.
Current failure behavior also remains intact: attention failure drops Cortex
context, while preview failure independently falls open to the committed broad
attention payload.

The duplicate compilation is therefore real and locally reusable, but safe
production equivalence is blocked at transport/deployment semantics rather than
projection semantics. Next smallest bounded Track B cut: after the existing
rollback window, delete the default-off candidates compatibility fetch and its
inert `neutralCandidates`/rejected-candidate plumbing. Revisit packet reuse only
with an explicitly authorized cross-request contract; do not introduce an
implicit cache.
