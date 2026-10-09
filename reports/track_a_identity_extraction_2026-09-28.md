# Track A research packet — Identity and model extraction (RESEARCH, offline, non-production)

Owner: Codex. Date: 2026-09-28. Status: experiment complete, no production touched.

Blitz parent: `docs/INTERPRETATION_RESEARCH_BLITZ.md`. Baseline packet: `docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md`
(`evals/interpretation_phase0/cases.json`, contract `phase0.v1`). This packet is a research
artefact, not a patch: no `src/`, schema, runtime, prompt, or deployed behaviour was changed.
`git status` after this work shows only this new report file (plus pre-existing worktree dirt
that is not mine).

## 1. Provenance and frozen case manifest

Source: `replay-private/sophie-apr28-30.json` — 7 source sessions, 2026-04-29/30, Sophie historical
trajectories (test-smoke corpus: every dentist/meeting matter carries a unique synthetic marker
such as `demo-mole2njm`, `lifecycle-smoke-molc2t3p`, `calendar-smoke-20260430-moll89qz`).
Reference abstractions: `evals/interpretation_phase0/cases.json` (`sophie_dentist_same_matter`,
`sophie_meeting_transform`).

14 frozen cases (manifest + sealed oracle held offline under `/tmp/track_a/`, never committed;
only redacted patterns below — marker IDs, timestamps, utterance shapes — no transcript
reproduction):

Dentist reconciliation (4): D-SAME-1 (one marker, add→Saturday→done); D-DISTINCT-1 (two adjacent
same-wording adds, distinct markers); D-AMBIG-1 (bare "change it"/"mark that" against multiple
live same-wording matters); D-REVISE-1 (one marker, done→change→remove contradictory order).
Meeting lifecycle (3): M-SAME-1 (add→add-refs→"move it"→"cancel that meeting"→"remove it" in 19s);
M-DISTINCT-1 (two Sarah adds, distinct markers, same slot); M-AMBIG-1 (bare "move it to Monday"
against ≥6 live near-identical Sarah meetings). Abstention controls (5): B-1 task-list query;
B-2 today-focus query; B-3 connectivity-probe chatter (×7 verbatim); B-4 day-status query (×15);
B-5 phatic check-in (×7). Phase-0 references (2): P0-DENTIST, P0-MEETING (clean abstractions).

Oracle decisions: D-SAME-1 one-matter-revised-then-resolved; D-DISTINCT-1 two-matters-no-merge;
D-AMBIG-1 hold/contested; D-REVISE-1 one-matter-contradictory-contested; M-SAME-1
one-matter-transformed-no-attention; M-DISTINCT-1 two-matters; M-AMBIG-1 hold/abstain;
B-1..B-5 no packet (operational state only); P0 pair per Phase-0 expected decisions.

## 2. Method and model/configuration metadata

Single-model two-prompt bakeoff (disclosed limitation, §6): both candidates are muse-spark
(this session), differing only in extraction posture, run on identical frozen evidence in manifest
order with the oracle section sealed during emission. Verbatim emissions:
`/tmp/track_a/configA_strict.json`, `/tmp/track_a/configB_permissive.json`; scorer:
`/tmp/track_a/score.py` (stdlib only; contract validation mirrors
`evals/interpretation_phase0/run.py` plus ABSTAIN).

- Config A (strict): merge only on shared unique marker/entity; bare pronoun with ≠1 live
  candidate → HOLD/contested/abstain; banal/status/phatic → no packet; contradictory ordering →
  contested, never smoothed.
- Config B (permissive/helpful): resolve by semantic similarity + recency; bare pronoun → most
  recent compatible antecedent; always produce a complete reading.

Latency/token metadata: N/A (manual offline runs; no model API invoked — a real multi-model
replication must record these per the blitz contract).

## 3. Results (raw counts, no aggregate score)

| case | A valid | A correct | B valid | B correct | B failure class |
|---|---|---|---|---|---|
| D-SAME-1 | yes | yes | yes | yes | marker-blind (non-fatal here) |
| D-DISTINCT-1 | yes | yes | yes | NO | unsafe over-merge |
| D-AMBIG-1 | yes | yes (contested hold) | yes | NO | merge-by-recency asserted as fact |
| D-REVISE-1 | yes | yes (contested) | yes | NO | contradiction erased, premature close |
| M-SAME-1 | yes | yes (refs-row qualified) | yes | yes | marker-blind (non-fatal here) |
| M-DISTINCT-1 | yes | yes | yes | NO | over-merge ("likely duplicate") |
| M-AMBIG-1 | yes | yes (abstain) | yes | NO | single pick from ≥6 candidates |
| B-1..B-5 | yes | 5×abstain | yes | 0/5 | false-positive durable packet ×5 |
| P0-DENTIST/MEETING | yes | yes/yes | yes | yes/yes | — |

Config A: identity-correct 14/14; abstention-warranted 6/6; false-positive rate 0/5; unsafe
merge/guess 0/4; invalid packets 0. Config B: identity-correct 4/14; abstention 0/6;
false-positive rate 5/5; unsafe merge/guess 4/4; invalid packets 0 (after relocating 8
`recheck_when` fields the author had mis-nested inside `implication` — an authoring slip,
corrected before scoring, not a model observation). Agreement on correctness: 4/14.

## 4. Representative failures (Config B; Config A had none on this set)

1. Over-merging (unsafe): D-DISTINCT-1 and M-DISTINCT-1 merged distinct matters on wording/
   participant/slot similarity despite distinct identity keys. In this corpus the markers make
   distinctness machine-checkable — a config that merges anyway will merge harder where real
   life offers no such keys.
2. Ambiguity resolved by fiat: D-AMBIG-1 and M-AMBIG-1 asserted the most-recent antecedent as
   certain (`medium`/`live`, no qualification). M-AMBIG-1 picked one meeting out of ≥6.
3. Revision failure: D-REVISE-1 (done→change→remove) was smoothed into "resolved and removed",
   erasing the done-then-changed contradiction that the oracle requires stay visible.
4. Abstention failure (systematic): B-1..B-5 all minted durable readings — "standing need for
   task-list awareness" (durable), "wants guidance on focus", "seeks connection reassurance",
   "wants ongoing day orientation", "wants calm companionship" — from status queries and
   verbatim-repeated probe chatter. Each is individually defensible prose; each is a
   false-positive durable packet. This is exactly the blitz-predicted failure ("habitually
   fills plausible semantic machinery when none is warranted").
5. Splitting: no splitting observed in either config on this set. Known production-side split
   evidence (per Phase-0 §2: dentist mentions stored as multiple pending ASK rows) was not
   re-tested here; a strict marker-literalist risks the converse split on harness-artefact
   rows (M-SAME-1 `moll89qz` vs `moll89qz-refs`) — Config A avoided it only by qualifying the
   refs row, resting on a naming convention rather than evidence.

## 5. Fields used, unused, missing

Used: all seven Phase-0 elements round-tripped in every emitted packet. `qualifies` carried
real weight (D-DISTINCT-1, M-SAME-1 refs-row); `contradicts` carried the D-REVISE-1 finding;
`contested` + `recheck_when` were the entire vehicle for warranted restraint.
Unused: nothing — but on banal cases the correct behaviour is emitting nothing at all, which
the contract cannot express (ABSTAIN is extra-contractual; the validator has no success
representation for "no packet").
Missing (gaps the extraction work exposed): (a) no slot for competing antecedent candidates —
A smuggled them into `confidence_basis`; (b) no identity-confidence distinct from
hypothesis-confidence — `contested` does double duty for "ambiguous referent" and "uncertain
claim"; (c) the identity key (marker/entity) is load-bearing but has no field; it lives
inside free-text `matter.identity`.

## 6. Disagreement, uncertainty, and honesty constraints

Configs disagree on 10/14 cases; all disagreement is posture-driven (same evidence, same
contract — the contract validates shape but does not prevent unsafe merges or false positives).
Two disclosed limitations bound every claim below: (i) single model playing both configs —
this is a posture-sensitivity probe, not a model bakeoff; (ii) the analyst authored the oracle
and is also the judge — mitigated by freezing the manifest before emission and keeping
verbatim emission files, but not true blindness. Config A's 14/14 must therefore be read as
"the packet CAN encode the right answer given marker-aware discipline", not "models reliably
produce it" — Config A was written by someone who already knew the trap.

## 7. Scope/authority audit

All emitted implications are advisory with guardrails; none commands HOLD/ASK/ENRICH/LEAD/ATTEND
or any foreground action. No diagnosis, no surveillance texture, no cross-matter leakage.
B-3/B-5 relational framings ("reassurance", "companionship") are the closest approach to
scope overreach and both belong to the failed Config B set.

## 8. Recommendation (per-track claims)

- **PROVEN:** (1) On clean Phase-0 abstractions both postures reproduce the authored reading —
  representation usefulness, not extraction reliability (reproduces the Phase-0 caveat).
  (2) On messy real history, extraction outcome is dominated by prompt posture, not by the
  packet contract: strict 14/14 vs permissive 4/14 on identical evidence/contract, with 5/5
  false-positive durable packets and 4/4 unsafe merges/guesses from the permissive default.
  (3) The permissive failure set (over-merge, recency fiat, contradiction erasure, abstention
  collapse) is exactly the failure taxonomy Track A was asked to measure.
- **HYPOTHESIS:** Real deployment (no explicit identity keys) will show equal-or-worse
  over-merge rates than measured here; the markers made this set easier than reality.
- **OPEN:** Whether any model/configuration reproduces Config-A discipline blindly and
  across runs (multi-model replication with latency/token metadata still required); whether
  splitting appears under marker-literalist strictness at scale; the three contract gaps in §5.
- Recommendation: RETAIN the Phase-0 packet as the representation baseline; DO NOT treat
  extraction as established — require a genuine multi-model blind replication (≥2 independent
  models, frozen manifest, abstention scored as success) before any production decision.
  Contract revisions proposed (not made): first-class ABSTAIN outcome; competing-candidate
  slot; identity-confidence separated from claim-confidence. No production architecture
  proposal — Track A evidence only.

## 9. Handoff

```text
WHAT I CHANGED: nothing in production; added this research packet only (plus /tmp scratch).
WHY IT SERVES THE NORTH STAR: measures whether interpretation preserves truth before building on it.
CANON PRINCIPLES TOUCHED: none (research only).
EVIDENCE / TESTS: /tmp/track_a/{manifest_and_oracle,configA_strict,configB_permissive,score}.json/.py; committed redaction above.
WHAT I DID NOT CHANGE: src/, schema, runtime, prompts, deployed behaviour, other tracks' scope.
REGRESSIONS / RISKS: none (offline, removable; report file only).
DELETE CANDIDATES: /tmp/track_a/* after synthesis ingests it.
OUT-OF-SCOPE FINDINGS: none claimed beyond Track A.
EXACT NEXT STEP: independent multi-model blind replication of the frozen 14-case manifest.
```
