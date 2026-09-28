# Honcho Longitudinal-QA Rerun — Report

**Date:** 2026-09-28. **Status:** canonical research artefact, offline research, no production touched.
**Programme:** `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§4 notes, §12; probe line §§442–470).
**Contracts:** `docs/HONCHO_RERUN_CONTRACT.md` (two-stage gate; this run executes it),
`docs/HONCHO_PROBE_LAUNCH_CONTRACT.md` (bar unchanged). First run:
`reports/honcho_longitudinal_qa_probe_2026-09-28.md` (commit `85942ef`).
**Constraints:** no production code/schema/runtime/prompt/behaviour changed; nothing persisted as
truth; no runtime path wired; no S3/P2/projection/architecture work. Sole-user deliberate test data;
constraint observed was methodological cleanliness, not privacy theatre. No secrets committed.

## 0. Housekeeping and environment record

- Repo `synapse-cortex`, branch `main`, HEAD `574cf7c` at run time; canon ancestor `6ae9df9`
  verified ancestor. Pre-existing dirty worktree (other agents' files) untouched; only this report added.
- Honcho checkout (local): `/Users/mukeshkumar/play/honcho`, commit `d191c107` — both API diagnosis
  and VPS build reference this commit (VPS `~/honcho` also at `d191c107`, verified via SSH).
- **Environment tested: VPS live stack** (chosen per contract preference: richer deployment, real
  deriver, configured LLM keys), reached via SSH tunnel `127.0.0.1:8002 → honcho-api:8000`
  (tunnel host-local only, torn down after the run). VPS containers observed:
  `honcho-api` (healthy), `honcho-postgres` (pgvector), `honcho-deriver` (active),
  `honcho-gateway`, `honcho-redis`. Local `127.0.0.1:8001` used only for Stage-1 cross-checks.
- Auth: VPS requires Bearer key (local does not); key read from VPS
  `~/companion-runtime/deploy/.env` at runtime, never written to repo or scratch files.
- **Workspace:** `honcho-rerun-probe-2026-09-28` (created 201, verified; a misdated
  `...-2026-09-29` first attempt was fully deleted: 4 sessions + workspace, deriver-confirmed).
  **Preserved (not deleted)** for audit/reproducibility; isolated, labelled, no production contact.
- External calls made: SSH to `deploy@161.97.150.246` (tunnel + log/version inspection);
  VPS Honcho API via tunnel; Honcho's own internal LLM/embedding calls (VPS-configured keys).
  No third-party APIs beyond what the deployments already use. No open-ended scans (none run; void).
- Scratch (never load-bearing): `/tmp/honcho_rerun/` (`ingest*.py`, `ingest_manifest.json`,
  `FREEZE.md`, `response_format.json`, `arm_a*.py`, `arm_a_raw.json`, `arm_a2_raw.json`,
  `arm_b.py`, `arm_b_raw.json`, `stage5_prederive_conclusions.json`). Safe to delete; report
  carries full provenance to reproduce.

## 1. Stage 1 (GATE: PASS) — the 422 cause and the working query path

**Exact cause of the previous 422 (PROVEN, source-cited):** `src/routers/conclusions.py`
`query_conclusions` raises `ValidationException("observer and observed must be specified for
semantic search")` unless `body.filters` contains `observer`/`observed` (lines 105–114), while the
published `ConclusionQuery` schema marks `filters` optional/nullable. Schema-valid bodies without
filters therefore 422 by design. The probe had used the wrong (under-specified) call, not a broken
endpoint. Verified live: without filters → 422 (local + VPS); with
`{"query","top_k","filters":{"observer":"sophie","observed":"sophie"}}` → 200 with ranked hits.
No code changed; upstream documentation defect (schema implies optional what code requires).

**Working paths established (all verified live before ingest):**
- `conclusions/query` + observer/observed filters → 200 (semantic conclusion search).
- Peer `/chat` (DialecticAgent, agentic search + reasoning over messages AND conclusions) → 200,
  correct abstention on the empty workspace in 3.9s (pre-ingest check). **Selected as the Arm-A
  reader: it is Honcho's native bounded-question QA path.**
- Workspace `/search` (message semantic search) → 200 (Arm-B retrieval path).
- `messages/list`, `conclusions/list`, `queue/status`, peer-card read verified for audit/guards.

## 2. Corpus — frozen S1–S4 ingested faithfully

Ingested 53/53 events (S1 14, S2 10, S3 14, S4 15; corpus sha recorded per-file in scratch manifest):
one session per scenario; message content verbatim; `peer_id` = fixture sender (13 peers
auto-created: ashley, user, sophie, carlos, bank_feed, school, florist, google_calendar,
studio_sam, lucy, dentist, auntie + probe-reader); metadata carries
`{fixture_event_id, source_type, role, orig_meta}`; `created_at` = fixture timestamps.
**Representational losses (documented, not papered over):** (a) Honcho normalises `created_at` to
UTC (`08:07+01:00` → `07:07Z`) — instants and order preserved, wall-clock shifted; (b) Honcho has
no first-class "external evidence" type — emails/feeds/calendar rows are messages from peers
(`bank_feed`, `google_calendar`), so source-type lives in metadata, not the model; (c) no
multi-peer utterance or receipt state — irrelevant to F1–F10. Temporal order, speaker/source,
corrections, repeats, identity ambiguity, scoped instructions, supersessions all preserved and
spot-verified (first/last messages per session, peer list, event-ID metadata).

## 3. Freeze (Stage 3 — before any F-answer inspected)

Frozen in scratch `FREEZE.md` + `response_format.json`: reader = Honcho-native chat
(`probe-reader` observer, global recall, `reasoning_level: low`, recruited-JSON `response_format`,
10 frozen F-wordings from the first probe §1, oracle never in context). Contamination guard:
`conclusions/list == 0` AND `peer_card == null` immediately before AND after EVERY call
(stored conclusions excluded from the scored path per mission §2). F9 carries its temporal bound
in the question ("Considering only evidence available up to Wednesday 09:11"). Rubric/bar per
rerun contract (0 fabrication, 0 missed corrections, 0 leaks, ≥7/10, ABSTAINs on F5/F9).

## 4. Primary F1–F10 results (Arm A — Honcho fresh recruited reads)

Two runs, contractually distinguished. **Run A1 (preserved failed run):** 10/10 abstain with
"no matches found" (F7/F8 answered from generic language knowledge, not corpus evidence) —
structurally ungrounded, not a capability verdict. **Root cause (PROVEN in source):**
`crud/message.py::search_messages` scopes to *sessions the observer belongs to* when no session is
pinned; `probe-reader` belonged to none, so all recall failed closed — while the omniscient
framing ("answered from the omniscient Honcho perspective", `chat.py:281`) implies otherwise.
**Repair (documented, production-reproducible):** granted `probe-reader` membership in all 4
sessions via `POST .../sessions/{id}/peers` (200 ×4; verified). No prompt/config change, no
re-tuning. **Run A2 (repaired, scored):** identical questions/config; guard held 0→0 on all 10;
latencies 4.7–10.7s, all HTTP 200 (20/20 chat calls across A1+A2 error-free).

| Q | A2 outcome vs oracle | Dimension notes |
|---|---|---|
| F1 | CORRECT — Q2,100, e03+e04 treated as one payment, initial-total uncertainty surfaced as counterexample | grounding ✓ (timestamp refs, coarse but traceable); dedup ✓; obs/…,interp ✓ |
| F2 | **FAIL (critical)** — answers "Yes" to treating the Monday row as paid, using Wednesday's e08 confirmation; the e05 withhold appears only as a counter and is overridden | **missed user correction at decision time + hindsight leak** |
| F3 | CORRECT — one obligation, explicit dedup | dedup ✓ |
| F4 | CORRECT (borderline framing "Yes—but weakly", then explicitly denies transfer; user disambiguation cited) | 0 leak; identity separation ✓ |
| F5 | **FAIL (critical)** — asserts bank-issue as the reason from counterparty/hearsay reports; abstain-designed, did not abstain | confabulation-by-hearsay; ABSTAIN miss |
| F6 | CORRECT — ends watch on e10, cites improving trend + no re-open | correction ✓; counterexamples ✓ |
| F7 | CORRECT — approval ≠ signature, full receipt chain | counterexample ✓ |
| F8 | CORRECT — turn-scoped, no globalisation | scope ✓ (one vague "other messages" filler, no invented episode) |
| F9 | **FAIL (critical)** — answers "Andree" from e12 (Oct 1), explicitly violating the ≤Wed-09:11 bound | **hindsight leak**; ABSTAIN miss |
| F10 | CORRECT — closed on e10+e11 with partial-independence warning (both user-sourced) | independence ✓; obs/interp ✓ |

Raw counts: fabrication **0/10**; counterexample recall surfaced 9–10/10; correction dominance
**1 miss (F2)**; cross-frame leaks **0**; dedup/independence correct F1/F3/F4/F10; identity
separation ✓ (F4); correct ABSTAIN **0/2 (F5, F9)**; obs-vs-interp present 10/10; repetition
laundering 0; hindsight leakage F9 (+F2 temporally). Grounding+counterexample+dedup correct on
**7/10** (F1,F3,F4,F6,F7,F8,F10) — numerically at the bar, but the zero-missed-correction and
all-ABSTAIN conditions fail. **Verdict: NOT USABLE for semantic nomination (fallback stands).
No post-hoc rescoring.**

Failure class (load-bearing): Honcho's reader retrieves well but **reasons toward the helpful
bottom line over the binding constraint** — later confirmation overrides an earlier withhold
(F2), reported hearsay becomes fact (F5), an explicit temporal bound is ignored when the answer
exists later in history (F9). These are exactly the correction/abstain/hindsight dimensions the
programme scores as critical.

## 5. Stored-conclusion audit (separate surface, NOT in the scored path)

Deriver began processing ingest (queue 53 units; 8 completed, then stalled — 0 in progress across
~15 min of observation; deductive/inductive levels never ran on this corpus: audit limited to
explicit level + first-run toy-data finding). The 42 pre-run `explicit` conclusions were saved to
scratch, then purged (204 ×42, verified 0) before scoring. Findings:
- Faithful near-paraphrases, one message each, authored voice preserved ("ashley thought/believed/
  said") — uncertainty hedging mostly survives at this level. Traceable (SUPPORTED).
- **Accumulation without supersession:** "Matías sports Friday" and "Matías Thursday" coexist;
  "Yoshi Wednesday" coexists with the Thursday calendar update; nothing marks superseded, stale,
  or corrected readings. A reader consuming these inherits contradictions with no resolution signal.
- Combined with the first run's toy-data finding (`deductive` conclusions from single throwaway
  remarks): stored conclusions are **unsafe as semantic authority; useful at most as retrieval
  hints** (outcome C). The scored A2 reads were verified uncontaminated (0→0), so this does not
  taint §4 — it independently confirms the exclusion rule.

## 6. Comparison (arms separated)

- **A. Honcho fresh recruited reads (A2): 7/10**, 0 fabrication, 0 leaks, but 1 missed correction
  (F2) + 0/2 abstains (F5, F9) + hindsight leak (F9) → NOT USABLE. (A1 preserved: 0/10 grounded —
  membership-scope trap, repaired by documented membership grant.)
- **B. Plain retrieval (Honcho workspace `/search`, top-5 per question): coverage 10/10** — every
  key episode (e03/e04/e09, e05/e08, e01/e13 disambiguation, e10 closures, e12/e13 resolvers)
  ranks in top-5; cross-scenario noise present (e.g. s2_e02 in F3/F8) that only disciplined
  synthesis excludes. Judgement layer absent by construction: 2/10 clean-correct under the first
  probe's layer split ( F7/F9-evidence-present class), failing exactly F2/F3/F4/F6/F8 judgements.
- **C. Fallback recruited synthesis (first probe, author-performed/unblinded): 10/10** — stands as
  the contract-validating reference, still capped at SUPPORTED. Not re-run (nothing changed in the
  fixtures); do not let it mask A2's failures.

## 7. Critical failures (pre-registered expectations)

1. Missed user correction: F2 (withhold overridden by later confirmation). 2. Abstain failures:
   F5 (hearsay-as-fact), F9 (bound-violating hindsight). 3. Zero fabrication / zero leaks: HELD
   (not sufficient to pass). 4. Infrastructure findings, not capability failures: 422 schema/code
   mismatch (§1); membership-scoped recall failing closed for non-member readers (A1); deriver
   stall at 8/53. 5. No repetition laundering observed in A2 (dedup correct where tested).

## 8. Verdict: outcome B (+C) — retrieval PASS, semantic synthesis FAIL; stored conclusions unsafe

Honcho is **useful as longitudinal evidence infrastructure, not as the semantic-read engine**.
Synthesis — and specifically correction-dominance, temporal-cutoff, and abstain gates — belongs
in our own model layer. Capability-in-principle for *assisted* reads is no longer fully OPEN
(Honcho was genuinely exercised: populated corpus, working endpoints, 20 clean reads), but the
observed failure modes are reasoning-discipline failures, not data/scale artefacts.

## 9. Architectural implications

- **Companion Projection / JIT semantic reads:** build JIT reads as bounded-question retrieval
  over Honcho-style evidence (proven: 10/10 coverage, verbatim, timestamped) PLUS a separate
  recruited-synthesis step owned by us, with hard gates: corrections dominate later/earlier
  pattern evidence at the decision checkpoint; temporal bounds are enforced, not requested;
  insufficient-evidence → ABSTAIN (never hearsay promotion). Do NOT delegate the read to
  dialectic chat.
- **Cortex/Honcho division of labour:** Cortex keeps lifecycle/authored/corrections as
  operational ground truth; Honcho holds evidence + serves semantic retrieval. The reader must
  consult Cortex-side correction/lifecycle state as an override channel — F2/F9 fail precisely
  where Honcho-local evidence outvotes out-of-band authority. Never treat stored Honcho
  conclusions as understanding (accumulation without supersession, §5).
- **Reader scoping is a design requirement, not a setup detail:** Honcho has no omniscient reader;
  recall is peer-membership/session-allowlist scoped. Any longitudinal reader needs explicit
  session membership or per-call allowlists (which itself needs a retrieval-routing step).

## 10. What should (not) happen next

DO: keep semantic nomination (path B) gated on our own recruited-synthesis layer; reuse the
frozen F1–F10 + recruitment `response_format` as its regression battery; file upstream: (a) the
`ConclusionQuery` schema/code mismatch (filters effectively required), (b) the membership-scope
fail-closed vs "omniscient" framing gap; investigate the deriver stall (8/53) out-of-lane.
DO NOT build: semantic nomination on dialectic chat; any reliance on stored conclusions as truth;
open-ended life/history scanning (still void); production wiring of any of this; a durable
shared-derived store (P1 stands: 0/8).

## 11. Canonical paths; 12. commits

- This report: `reports/honcho_rerun_2026-09-28.md` (sole new file; commit hash below).
- Prior artefacts reused (not modified): first probe report (`85942ef`), S1–S4 fixtures+oracles
  (`evals/sophie_longitudinal/`), rerun + probe contracts.
- Raw run data (audit): `/tmp/honcho_rerun/` scratch (A1/A2/B raws, freeze, manifest, 42
  pre-run conclusions); VPS workspace `honcho-rerun-probe-2026-09-28` preserved with 53-message
  corpus + membership record. Probe workspace contains only committed synthetic fixtures.

```text
WHAT I CHANGED
Ran the Honcho rerun contract end-to-end (Stage 1 gate → corpus → freeze → A1/A2/B arms → Stage 5 audit); landed this report as the sole owned file.
WHY IT SERVES THE NORTH STAR
Stops semantic nomination being built on an untested-or-failing reader; preserves the honest division: evidence infrastructure vs judgement.
CANON PRINCIPLES TOUCHED
11 (evidence≠reading≠confidence: F5/F9 fail exactly here), 12 (abstain is success — Honcho didn't), trajectory rule (supersede readings; stored conclusions don't), 14 (truth≠salience: F6/F8 hold), 16 (kill: chat-as-reader killed; retrieval kept).
EVIDENCE / TESTS
VPS Honcho d191c107; 53-message frozen corpus; 20/20 clean chat reads (A1 0/10 grounded-membership trap preserved; A2 7/10, 0 fab, 0 leaks, 1 missed correction, 0/2 abstain); retrieval coverage 10/10; 42 stored conclusions audited then purged with 0→0 guards.
WHAT I DID NOT CHANGE
No production code/schema/runtime/prompts; no other agents' files; no Honcho source edits (diagnosis only); no open-ended scans; no secrets committed.
REGRESSIONS / RISKS
None introduced. Flagged upstream: query-schema mismatch, membership-scope framing, deriver stall at 8/53.
DELETE CANDIDATES
/tmp/honcho_rerun/* after verification (raws are audit-useful until then); the misdated workspace was already deleted.
OUT-OF-SCOPE FINDINGS
Deriver explicit-level quality is decent paraphrase; deductive/inductive unobservable here (stall).
EXACT NEXT STEP
Build JIT recruited-synthesis in our layer against Honcho retrieval using F1–F10 as regression; file the three upstream Honcho issues; keep path B gated.
```
