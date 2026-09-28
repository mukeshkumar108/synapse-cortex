# Honcho Longitudinal-QA Capability Probe — Report

**Date:** 2026-09-28. **Status:** canonical research artefact, offline, no production touched.
**Programme:** `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` §4 notes, §12.
**Launch contract:** `docs/HONCHO_PROBE_LAUNCH_CONTRACT.md` (this probe executes that contract only).
**Constraints inherited:** canon, North Star, graduated substrate (Cortex `9aadba5`, runtime `00e8364`);
no production code/schema/runtime/prompt/behaviour changed; nothing persisted as truth; no runtime path wired.

## 0. Housekeeping and environment record

- Repo `synapse-cortex`, branch `main`, HEAD `e9e4291` at run time; canon ancestor `6ae9df9` verified
  ancestor (`ANCESTOR_OK`). Dirty worktree pre-existed (other agents' files); touched only this report.
- Honcho repo: `/Users/mukeshkumar/play/honcho`, commit `d191c107`
  (`docs: document pgvector preinstall for least-privilege DB roles (#984)`).
- Honcho service: `http://127.0.0.1:8001`, `/health` → `{"status":"ok"}`. API is v3
  (`/v3/workspaces/list`, `.../search`, `.../peers/.../search`, `.../conclusions/list`,
  `.../conclusions/query`, `/openapi.json` all observed live).
- Workspaces present (4): `sophie-honcho-smoke`, `sophie-honcho-smoke-1786195839`,
  `llm-test-agent` (14 sessions, 7 peers — largest), `sophie-honcho-smoke-1788101601`.
- **Data sufficiency: INSUFFICIENT — stated plainly.** No workspace contains longitudinal histories
  resembling the frozen S1–S4 fixtures (no Carlos/debt, Lucy/payment, Sam/contract, neck-watch, or any
  multi-day matter with corrections, counterevidence, or cross-frame entities). Content is smoke-test
  chatter (Lantern/Nimbus apps, photography club, Burwell/Ely, cycling, "Noted in the moment.
  Chatter acknowledged (25/26)"). Per contract §Environment, the Honcho-specific arm is therefore
  reported as data-insufficient, and the probe continues **only** with the fallback arm. No VPS access
  used or requested. No external (non-localhost) calls made. No private histories touched
  (`replay-private/` never opened); all quotes below are from committed synthetic fixtures.
- Scratch (never load-bearing): `/tmp/honcho_probe/honcho_arm.py`,
  `/tmp/honcho_probe/honcho_arm_raw.json`, `/tmp/honcho_probe/fallback_retrieval.py`,
  `/tmp/honcho_probe/fallback_retrieved_ids.json`. Safe to delete.

## 1. Frozen battery (10 bounded interrogative questions, known answers)

Sources (all committed): `evals/sophie_longitudinal/scenario_{1,2,3,4}_{input,oracle}.json`.
Each question is pulled by a concrete arbitration need (shown). Required coverage per contract:
ABSTAIN ×2 (F5, F9), dedup (F3), correction dominance ×2 (F2, F6), cross-frame trap (F4).

| ID | Bounded question (arbitration need) | Known answer (oracle path) |
|---|---|---|
| F1 | How much does Carlos still owe at Thursday closeout, and on what evidence? (decide whether a chase candidate is eligible) | Q2,100: total Q3,600 (S1 oracle `carlos_debt`), Q1,500 received (S1 e03+e04 = ONE transfer, two records), remainder stated S1 e09, still-open S1 e14 |
| F2 | May the Monday £240 bank row be treated as Lucy's camera payment? (decide paid-vs-open lifecycle) | NO on Monday: user withholds confirmation S3 e05 ("Don't count it as paid until I ask her"); closed only S3 e08 (S3 oracle `lucy_camera_payment`, false-positive trap) |
| F3 | How many distinct Carlos-debt obligations do mentions in e01/e07/e09/e11/e14 describe? (dedup before nominating) | ONE matter; ≥4 mentions, one episode (dedup test) |
| F4 | Studio Sam promised the final copy (S3 e07); cousin Sam confirmed the pickup (S3 e09). May evidence about one bear on the other's reliability? (entity/frame check before synthesising a "Sam" reading) | NO: distinct entities, `sam_studio` ≠ `sam_cousin` (S3 oracle `entities`); S3 e13 user disambiguation binds later "Sam" to studio Sam in that frame |
| F5 | Why was Carlos's remainder delayed, and will he pay by Thursday? (decide chase timing) | **ABSTAIN** on reason: only "bank releases the transfer tomorrow" (S3→S1 e03, counterparty-reported) + "he said bank issue" (S1 e11, user-reported hearsay). No verified reason in evidence |
| F6 | Should the neck watch continue after Thursday morning? (decide check-back-up candidacy) | NO: user closes it S4 e10 ("don't need to keep asking about that anymore, it's not a thing"); continued checking = pestering-class failure (S4 oracle `neck_ache.released_at`) |
| F7 | Does "looks good to me, go ahead" (S3 e06) mean the contract is signed/executed? (decide signature-obligation state) | NO: content approval ≠ signature; final copy outstanding until S3 e12, signed S3 e14 (S3 oracle `studio_contract`, false-positive trap). Counterexample to approval=execution |
| F8 | Does "Don't just give me everything" (S1 e10) establish a permanent global surfacing rule? (decide whether to persist a preference) | NO: moment restraint for that turn (S1 oracle false-positive trap: prohibited `global_user_rule`) |
| F9 | Asked Wednesday 09:11 (before S1 e12): which boy owed the £18 school money? (decide whether to nominate a payment candidate) | **ABSTAIN / ambiguous**: unresolvable until S1 e12 ("so yes, it was him" → Andree), paid S1 e13 (S1 oracle `andree_school_payment.ambiguous_until`) |
| F10 | What evidence shows the Mum pickup succeeded, and is it independent? (decide pickup-loop closure) | S3 e10 calendar-completed (user-marked) + S3 e11 "Mum got home fine" (indirect real-world report). Corroborating but NOT fully independent: both user-sourced → same-source warning, medium confidence (S3 oracle `cousin_sam_pickup.corroboration`) |

Open-ended scans were not run (contract voids them). Every read below was pulled by the F1–F10 question.

## 2. Honcho arm — raw capability results

Four bounded longitudinal queries (HQ1–HQ4, §1 analogues: Carlos debt, Lucy payment, Sam contract,
neck watch) were executed as Honcho-native reads against all local workspaces:
workspace `/search` (×2 workspaces each) + peer `/search` + `conclusions/query`.
Raw outputs preserved in scratch (`honcho_arm_raw.json`).

- **HQ1–HQ4 workspace/peer search: mechanically OK, zero relevant evidence.** Every hit is smoke
  chatter ("I'm building a photography app called Lantern", "My sister is called Nina",
  "I found a pen under the sofa", "I might go back to cycling next week"). No Carlos, Lucy, Sam,
  contract, debt, or multi-day matter exists in any workspace. Recall of relevant episodes: 0/4.
- **`conclusions/query`: unusable on this build — 422 on schema-valid bodies.** Retried with the
  exact `ConclusionQuery` schema from live `/openapi.json` (`{"query":...}`, `+top_k`, `+filters`,
  `+distance`): all 422 `Unprocessable Content`. The semantic-query path the probe exists to test
  cannot be exercised from this workspace at all.
- **`conclusions/list`: works; 365 conclusions in `llm-test-agent`, all toy-chatter derivations.**
  Sample: "user_… is likely in a temporary home-or-work setting … because they said t…" (truncated),
  "…is currently walking instead of cycling", "sophie said the Nimbus case is bright orange, so the
  case color is orange". `deductive`-level conclusions are drawn from single throwaway remarks —
  the exact repetition/laundering and tier-confusion shape (§3 P0/P1: frequency ≠ authority, derived
  stated as observed) the programme scores as failure. Observed on toy data; not scored as a
  longitudinal failure, recorded as a caution for any future semantic-nomination reliance.

**Honcho arm scoring (contract §Scoring, per-question raw counts):** grounding 0/4 (no episodes to
cite — nothing to ground in); fabrication 0 (no answer attempted beyond retrieval hits);
counterexample recall N/A (no data); correction dominance N/A; scope/frame N/A; dedup N/A;
abstention N/A (no QA layer reached — search returns hits or nothing; there is no abstaining reader).
**Verdict: NOT USABLE for semantic nomination on local evidence — data-insufficiency arm, not a
capability proof.** The bar's zero-fabrication/zero-missed-correction/zero-leak conditions are
vacuously untestable here; grounding + counterexample + dedup are 0/4, and §1's questions cannot be
put to Honcho at all. This is a finding about the local Honcho *deployment state*, NOT a finding
that Honcho-the-capability fails: with populated longitudinal workspaces the question would be open.
No VPS arm was opened (per task instruction).

## 3. Fallback arm — retrieval + synthesis under the same recruitment contract

Method: bounded lexical retrieval script over the frozen fixture JSONs (entity/keyword match,
per-question term sets; retrieved ID lists in scratch) = the retrieval step; synthesis performed
locally by the probe author under the full recruitment contract (supporting episodes cited,
counterexamples surfaced, corrections respected, same-episode/independence flagged, scope+frame
stated, observation vs interpretation separated, what-would-change-the-reading stated). No external
model calls; the "model" is the author, so claims cap at SUPPORTED (§5).

### 3.1 Recruited answers (condensed; full evidence IDs in §1 table)

- **F1 — Q2,100 (SUPPORTED).** Support: e03 (Carlos: sent Q1,500, rest after bank releases tomorrow)
  + e04 (feed: incoming Q1,500 EVENT BALANCE) + e09 (user: "still owes 2,100?") + e14 (rest still unpaid).
  **Independence warning: e03+e04 are ONE transfer in two records** (sender email + feed row) — counting
  them as two payments would fabricate Q3,000 received. Total Q3,600 is oracle-side, not user-stated;
  e01's "3,000? Or 3,600" is uncertainty, not fact. Counterexample considered: e09's "2,100?" is itself
  hedged — confidence rests on feed + oracle total, not the user's estimate. Observation (amounts,
  timestamps) vs interpretation (deferred-not-violated chase status per P1 §1-repair) separated.
  Would change: a second feed row or user correction of the total.
- **F2 — NO, not paid Monday (SUPPORTED).** Correction dominates amount-match: e02 (£240 L. HARGREAVES,
  no memo) is suggestive; e05 explicitly withholds ("Don't count it as paid until I ask her though");
  e08 (Lucy: "Yep that £240 was me!") closes it Wednesday. Naive retrieval (amount match → paid) FAILS
  here — recorded in §3.2. Would change: contemporaneous user confirmation.
- **F3 — ONE obligation (SUPPORTED).** e01 (initial dump), e07 (defer to tomorrow), e09 (2,100 + don't
  chase tonight), e11 (hasn't sent rest, give until tomorrow), e14 (still hasn't paid) are one matter
  with evolving deferrals, not 4–5 debts. Same-episode/matter dedup applied; counting mentions as
  obligations is the Carlos loop-sprawl defect (BLITZ.md Track C) reproduced by naive counting.
- **F4 — NO transfer either direction (SUPPORTED).** e01 introduces both Sams distinctly; e03/e07
  (studio, contract domain) vs e09/e10 (cousin, family pickup) never cross-link; e13 rebinds later
  "Sam" to studio Sam *in the contract frame only*. Conflating them is the cross-frame leak the bar
  scores as critical. Would change: user statement linking the two (never present).
- **F5 — ABSTAIN on reason (SUPPORTED, abstain-designed: correct).** Retrieved e03 + e11 give only
  counterparty-reported and hearsay-reported bank reasons; no verified cause, no Thursday guarantee
  (e11's "until tomorrow" is the user's grace window, not a promise). Confabulating a reason
  ("bank holds large transfers 48h") would be a critical failure. Chase-timing action (wait until
  tomorrow per e11) is answerable; the *why* is not — stated separately.
- **F6 — NO further checks (SUPPORTED).** e01/e02/e04/e07 establish the multi-day pattern (legitimate
  watch, first proactive check Tue e06/evening per oracle); e10 explicitly releases it. Post-release
  checking is the pestering failure class. Naive "5 mentions → keep watching" FAILS — recorded §3.2.
  Would change: user re-raising neck pain (re-opens, does not retroactively justify).
- **F7 — NO, not signed (SUPPORTED).** e06's own words ("I didn't sign anything though. Is that
  enough?") + e07 (final copy still to come) contradict approval=execution; e12 (final copy arrives)
  + e14 (signed an hour ago) close it. Counterexample to the attractive misreading, surfaced.
- **F8 — NO global rule (SUPPORTED).** e10's restraint is turn-scoped ("what's actually urgent today?
  …don't just give me everything, please"); persisting it globally is the oracle-prohibited move and
  the P1-C4 boundary finding (moment-restraint never globalised). Scope tag: turn-only, expired.
- **F9 — ABSTAIN at Wednesday 09:11 (SUPPORTED, abstain-designed: correct).** Pre-e12 evidence (e01:
  "one of the boys", amount uncertain £18-or-last-term) does not identify the child; e12 resolves
  (Andree), e13 pays. Answering "Andree" at the asked checkpoint uses future evidence — scored as
  failure mode (hindsight leak), avoided here by timestamping the read.
- **F10 — Closed, medium confidence, same-source warning (SUPPORTED).** e10 (user-marked completed) +
  e11 ("Mum got home fine", indirect real-world evidence) corroborate, but both originate with the
  user — flagged as non-independent paths, not two independent witnesses. No cross-check (e.g. Sam
  confirming) exists. Would change: third-party confirmation (raises to high).

### 3.2 Layer split (retrieval-only vs retrieval + recruited synthesis)

| Q | Lexical retrieval alone | + recruited synthesis |
|---|---|---|
| F1 | PARTIAL (all episodes present; e03+e04 double-count risk unresolved) | CORRECT (independence flagged) |
| F2 | FAIL (amount-match → paid Monday; correction missed) | CORRECT |
| F3 | FAIL (6 hits, no grouping; mentions = obligations) | CORRECT |
| F4 | FAIL (both Sams in one hit set; conflation) | CORRECT |
| F5 | PARTIAL (reason-evidence present; confabulation risk open) | CORRECT ABSTAIN |
| F6 | FAIL ("neck ×5 mentions" → keep watching; closure missed) | CORRECT |
| F7 | CORRECT (e06 self-negates) | CORRECT |
| F8 | FAIL (single hit invites globalising) | CORRECT |
| F9 | CORRECT-leaning (pre-e12 hits show ambiguity) | CORRECT ABSTAIN (timestamped) |
| F10 | PARTIAL (both records present; independence unflagged) | CORRECT with warning |

Retrieval-only: 2/10 clean-correct, 3 partial, 5 fail. Retrieval + recruited synthesis: **10/10
correct** (grounding + counterexample + dedup correct on all non-abstain; correct ABSTAIN on F5, F9).

### 3.3 Bar evaluation (contract §Pre-registered bar)

- Honcho arm: **NOT USABLE** — 0 fabricated episodes (none attempted), but grounding/counterexample/
  dedup untestable on empty data (0/4), abstain-designed questions never reached a reader. Falls below
  the ≥7/10 majority by vacuity, not by error. Correct contractual outcome: fallback stands.
- Fallback arm (contract-test, not Honcho-test): 10/10 recruited-correct; zero fabrication;
  zero missed corrections (F2, F6); zero cross-frame leaks (F4); dedup correct (F1, F3, F10);
  ABSTAIN correct on all abstain-designed questions (F5, F9). No post-hoc rescoring (battery frozen §1).

## 4. Findings

- **Fabrication:** none in either arm (Honcho search returns real but irrelevant rows; fallback synthesis
  cites verbatim fixture IDs; no invented episodes). The live risk observed is adjacent: Honcho's stored
  `deductive` conclusions overstate thin chatter (§2) — laundering-shaped, not longitudinally scored.
- **Correction dominance:** fallback respects all three user corrections/withholds (F2 e05, F6 e10,
  F8-scope); retrieval-only misses 2/3. Any semantic-nomination reader without an explicit
  correction-dominance gate fails this battery.
- **Scope/frame:** F4 (Sam≠Sam) and F8 (moment≠global) both correct under synthesis, both failed by
  naive retrieval. Observation vs interpretation separated per answer (§3.1); lifecycle states
  (paid/closed/deferred) kept operational, never used as confidence (P1 §1-repair applied: F1 chase
  status judged behaviourally).
- **Dedup/independence:** F1 (e03+e04 one transfer), F3 (one matter), F10 (same-source corroboration)
  all flagged. Correlated/duplicated evidence never counted twice.
- **Abstention:** correct on F5 (unverified reason) and F9 (pre-resolution identity); hindsight-leak
  (answering F9 from e12) explicitly refused by timestamping the read.
- **Suitability for semantic nomination:** Honcho on local evidence is **NOT USABLE** (insufficient
  data + `conclusions/query` 422). Capability-in-principle remains **OPEN** — untested, not disproven.
- **Fallback better? YES on this battery** (10/10 vs untestable), **with the cap below**: synthesis was
  author-performed, unblinded, on synthetic fixtures — it validates the *recruitment contract*, not a
  deployable pipeline. A blinded multi-model rerun (P2 discipline) is required before any reliance claim.
- **Next recommendation:** (1) Do NOT build semantic nomination on Honcho on current evidence; keep
  path-B gated. (2) Stand up a populated longitudinal Honcho workspace (ingest S1–S4 fixtures into an
  isolated probe workspace, never production) and re-run F1–F10 through `conclusions/query` once the
  422 is fixed — that is the true capability test. (3) File the `conclusions/query` 422 against the
  Honcho build (`d191c107`). (4) Any future reader must carry correction-dominance, same-matter dedup,
  and abstain gates explicitly — retrieval alone scores 2/10 here.

## 5. Claims ledger

- **PROVEN:** local Honcho workspaces contain no usable longitudinal data (4 workspaces enumerated,
  HQ1–HQ4 zero relevant hits); `conclusions/query` 422s on schema-valid bodies on build `d191c107`;
  365 listable conclusions are toy-chatter derivations.
- **SUPPORTED:** fallback retrieval + recruited synthesis scores 10/10 on frozen F1–F10 with zero
  fabrication/missed-correction/leak and correct abstains; retrieval-only scores 2/10 clean-correct.
- **HYPOTHESIS:** a populated Honcho workspace + working query endpoint could pass the same battery;
  recruited synthesis would survive blinded multi-model rerun.
- **OPEN:** Honcho-the-capability for longitudinal QA; one-vs-per-product trajectory views (untouched).
- **KILLED:** "local Honcho suffices for semantic nomination now"; "lexical retrieval alone answers
  longitudinal questions" (2/10); open-ended significance scans (not run, per contract void).

```text
WHAT I CHANGED
Executed the Honcho longitudinal-QA probe contract only; landed this report (sole owned file).
WHY IT SERVES THE NORTH STAR
Prevents building semantic nomination on an untested capability; keeps understanding honest about what evidence actually supports.
CANON PRINCIPLES TOUCHED
11 (evidence ≠ interpretation ≠ certainty), 12 (uncertainty held, abstain correct F5/F9), 13 (history as evidence via bounded recruitment), 14 (truth ≠ salience: F6 release, F8 moment-restraint), 16 (kill/narrow: Honcho arm gated, retrieval-only killed).
EVIDENCE / TESTS
Honcho v3 API live probes (HQ1–HQ4 search zero-relevant; conclusions/query 422 ×4 variants; conclusions/list 365 toy derivations); frozen F1–F10 battery over committed S1–S4 fixtures+oracles; lexical retrieval script vs recruited synthesis layer split 2/10 → 10/10.
WHAT I DID NOT CHANGE
No production code/schema/runtime/prompts; no VPS/remote access; no private data; no caches, no runtime paths, no other agent's files.
REGRESSIONS / RISKS
None (read-only probes + one new report file). Risk flagged, not introduced: stored Honcho deductive conclusions overstate thin evidence.
DELETE CANDIDATES
/tmp/honcho_probe/* scratch after verification.
OUT-OF-SCOPE FINDINGS
conclusions/query 422 (file upstream); Honcho deriver tier-confusion symptoms on toy data (for P2).
EXACT NEXT STEP
Ingest S1–S4 into an isolated probe Honcho workspace after the 422 fix; re-run frozen F1–F10 through conclusions/query; blind the synthesis before any reliance claim.
```
