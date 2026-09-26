# Companion Blitz — cockpit

> Mutable. Today, this week, who owns what, what branch, what won, what dies.
> No essays. Canonical docs live here (single copy — never fork):
> `docs/COMPANION_NORTH_STAR.md` → `docs/COMPANION_CANON.md` → this file.

## Canonical baseline (update on every shared-state commit)

- `synapse-cortex: <pending first commit>`
- Every task starts from this SHA. Verify before work; mismatch = STOP.

## Agent bootstrap — hard requirement

Work from the existing canonical local checkout. Do NOT clone a fresh copy
unless explicitly instructed. Canonical workspace: `/Users/mukeshkumar/play/`.

Before doing any work, verify these files exist:

- `synapse-cortex/docs/COMPANION_NORTH_STAR.md`
- `synapse-cortex/docs/COMPANION_CANON.md`
- `synapse-cortex/BLITZ.md`

If ANY are missing: STOP. Do not substitute older docs. Do not infer product
intent. Do not create replacements. Report the missing file plus current git
branch/HEAD. Before modifying code report: repo, branch, HEAD, working-tree
status, canonical-doc existence. Do not reset, checkout, rebase, clone, pull,
or overwrite another agent's work unless explicitly authorised.

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
- Status: candidate cut implemented; handshake retained; attention-to-preview packet reuse proven locally but not production-consolidated because no safe cross-request transport exists.
- Verified heads: ash-ai `447164b`; companion-runtime `351ed35`; synapse-cortex `6da210f` (all equal `origin/main`; dirty checkout changes excluded).
- Output: `docs/TRACK_B_CURRENT_HEAD_HOT_PATH_2026-09-26.md`.
- Live path: app persists user turn + reads chronology/session state/day packet → Runtime durable turn claim → parallel epistemic/Honcho/Cortex/current-meaning barrier → selective prompt modules → Sophie foreground model → Runtime durable result → app durable assistant message → async session/semantic/Honcho/Cortex writeback.
- Verified duplication: Cortex packet compiler runs 2x on a continuing session (attention + handover preview), 3x on session entry (+ handshake); handover normally replaces the broad packet in the prompt; handshake is not independently rendered.
- Verified dormant on ordinary turn: Cortex `/route`, both working-set endpoints, and neutral candidates as a generation input (`candidates/query` only reaches the decision record).
- Verified live delta/reconciliation: `current-meaning/revise-sync` runs in the parallel barrier, may version durable meaning, and renders only with live `active` authority.
- Cut: companion-runtime defaults `SYNAPSE_CORTEX_CANDIDATES_QUERY_ENABLED=false`; setting it to `true` restores the compatibility fetch. Normal turns make one fewer Cortex request.
- Parity evidence: candidate-on vs default-off returned identical Cortex context excluding inert `neutralCandidates`, byte-identical foreground prompt, identical selected/omitted prompt modules, no candidate receipt/write request, and no warnings. Runtime only recorded fetched candidates as rejected compatibility metadata; `candidate_refs` stayed empty, so the app enqueued no delivery receipt. Deterministic 50ms candidate delay was removed from the adapter barrier (asserted improvement >30ms).
- Handshake parity result: NOT SAFE TO GATE/REMOVE. With vs empty handshake projection had identical authoritative entry context, orientation, continuity/handover, prompt bytes, prompt modules and routing, but handshake uniquely populated returned `CortexContext.daypart`, `live`, `avoidSurface`, and `memoryRefs`. It adds one new-session request and can sit on the gather barrier; a synthetic 50ms response measured >=45ms. It invokes the same mutation-capable attention compiler, adding no unique lifecycle mutation beyond that duplicate compiler pass.
- Attention/preview parity result: substituting the exact committed attention response at preview's internal packet boundary preserved the public handover byte-for-byte after excluding timing metrics, including agenda/admission/scene/owed/available/avoid. In the seeded SQLite fixture it reduced preview from 26 to 8 SQL statements and measured 19.1→5.05ms end-to-end (compiler metric 15.2→2.8ms). The required attention read durably expired one suppression, created one daily occurrence and dismissed one stale clarification; both preview arms remained zero-write, and eligibility reads created no surface receipt. Production consolidation was not made: attention and preview are separate HTTP requests/transactions and no existing request contract transfers the packet; process-local caching would be unsafe under concurrency/multi-worker routing, while adding a packet/schema/combined-endpoint contract is outside this surgical session.
- Tests: companion-runtime focused suite `39 passed` (`test_adapters_failopen.py`, `test_latency_telemetry.py`, `test_api_endpoints.py`, `test_contracts.py`); Cortex packet-reuse parity plus entry/context/lifecycle suites pass; compileall + diff check clean. Warnings were pre-existing dependency/datetime deprecations.
- Delete after win: candidate compatibility branch and `neutralCandidates` decision-record plumbing after rollback window; attention packet remains protected because its reads mutate state.
- Next smallest bounded cut: after the candidate rollback window, remove the now-default-off `candidates/query` compatibility branch and inert `neutralCandidates`/rejected-candidate decision-record plumbing. Packet reuse remains a validated optimization candidate only when an explicit cross-request transport contract is separately authorized; do not add an implicit cache.

## Track C — Behaviour / trajectory (owner: Claude Code, evidence: Spark, judge: Gemini, support: Codex)

- Branch: `blitz/behaviour`.
- Status: not started.
- Current task: trace every live governor (aperture, navigator, director, observer, Jev, overlays/gears); where foreground is informed vs steered vs overridden vs regenerated; smallest flaggable patch restoring autonomy-by-default with longitudinal observation intact.
- Tests: —
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

## Regression corpus (frozen transcripts/evals — Spark to manifest)

- Isa 2026-09-26 transcript (bad arc — regression reference).
- Elena good moments (to enumerate).
- Sophie longitudinal blind eval baseline.
- Retrieval probes with known answers.
- Morning / re-entry examples.
