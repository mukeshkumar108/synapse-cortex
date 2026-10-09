# Track A replication — independent extraction-reliability experiment (RESEARCH, offline, non-production)

Owner: Spark (Muse Spark session). Date: 2026-09-28. Status: experiment complete, no production touched.

Blitz parent: `docs/INTERPRETATION_RESEARCH_BLITZ.md`. Prior result under test:
`reports/track_a_identity_extraction_2026-09-28.md` (strict Config A 14/14, single model
playing two postures, analyst-authored oracle, analyst also judge). Baseline packet:
`docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md` (contract `phase0.v1`).
This packet is a research artefact, not a patch: no `src/`, schema, runtime, prompt, or
deployed behaviour was changed. New files: this report only (plus `/tmp` scratch outside
the repo, removable).

## 1. Question and method

**Question:** does Track A's strict 14/14 survive genuinely independent model/configuration
runs, or was it one model under two postures written by someone who already knew the trap?

**Design (frozen before scoring):**
- Reused Track A's frozen 14-case manifest verbatim (7 real-history dentist/meeting cases
  with distractors, 1 ambiguity-hold meeting case, 5 abstention controls, 2 Phase-0
  reference abstractions). Source: `replay-private/sophie-apr28-30.json` + Phase-0 cases.
- Built a blinded evidence file (`/tmp/track_a_replication/blinded_evidence.json`) with
  oracle/decisions stripped; verified no leakage strings (`one_matter`, `two_matters`,
  `oracle`, `expected`) before launch.
- Launched **three independent blinded extractor runs** as isolated subagents with no
  shared context, no oracle access, no access to each other's outputs, and an explicit
  ban on reading the Track A report, the sealed oracle, the scorer, and Phase-0 expected
  decisions. Prompts frozen before any scoring; oracle opened only by the scorer after
  all emissions were written.
- Three postures (all blinded to which cases are which):
  - **N1 neutral-contract-only:** Phase-0 contract + ABSTAIN option, no identity or
    abstention coaching. Tests what the contract alone elicits.
  - **N2 abstention-licensed:** contract + explicit "no packet is first-class" licence
    for banal/transient evidence, no identity coaching. Tests whether abstention failure
    is fixable by licence alone.
  - **N3 generically-cautious:** contract + generic caution (no merge on similarity
    alone; no bare-pronoun fiat; keep contradictions visible; banal → ABSTAIN), with
    **no marker rule and no case-specific hints**. Tests whether generic caution
    reproduces strict discipline blind.
- Verbatim emissions: `/tmp/track_a_replication/emissions_N{1,2,3}.json` (14/14 each,
  manifest order). Scorer (coordinator, oracle-open) validated shape with the Phase-0
  invariants (allowed sets, evidence-id grounding, no dual-relation items, advisory-only
  implications) and judged identity/decision against the sealed Track A oracle.

**Disclosed limitation (bounds everything below):** all three extractors are the same
model family as the coordinator (no external model APIs/keys in this environment, no
local model runner). Independence here = fresh isolated contexts + genuine blindness to
oracle/traps + distinct frozen prompts — strictly stronger than Track A's
single-analyst-two-postures on blindness, but **not** cross-architecture evidence.
A genuine multi-architecture bakeoff (≥2 model families) is still OPEN and required.

## 2. Results (raw counts, no aggregate score)

Scoring key: ✓ = matches sealed oracle identity/decision; ✗ = does not.
`*`/`**`/`***` = fixture caveats detailed in §4 (under-specification, not pure
reasoning failure).

| case | oracle (sealed during runs) | N1 neutral | N2 abst-lic | N3 cautious |
|---|---|---|---|---|
| D-SAME-1 | ONE matter, packet | ✓ one-matter | ✗ MISS (abstain) | ✓ one-matter |
| D-DISTINCT-1 | TWO matters, no merge | ✓ distinct asserted | ✗ MISS (abstain) | ✓ two-matters |
| D-AMBIG-1 | hold, no certain merge | ✗ ambiguity guessed (live)\* | ✓ abstain | ✗ hedged guess (live)\* |
| D-REVISE-1 | ONE matter, contradictory, contested | ✗ contradiction loss (live, all-supports) | ✗ MISS (abstain loses contradiction) | ✓ contested + contradicts |
| M-SAME-1 | ONE lineage, no attention | ✗ split + soft recency pick\*\* | ✗ MISS\*\* | ✗ hold vs ONE\*\* (honest slice-local) |
| M-DISTINCT-1 | TWO matters, no merge | ✓ two distinct | ✗ MISS | ✓ two distinct |
| M-AMBIG-1 | hold, no packet | ✓ abstain | ✓ abstain | ✓ abstain |
| B-1..B-5 (×5) | no packet | ✓✓✓✓✓ abstain | ✓✓✓✓✓ abstain | ✓✓✓✓✓ abstain |
| P0-DENTIST | ONE (authored) | ✓ one, contested | ✗ MISS | ✗ over-cautious hold\*\*\* |
| P0-MEETING | ONE cancelled | ✓ one | ✗ MISS | ✓ one |
| **identity-correct** | | **11/14** | **7/14** | **11/14** |
| abstention-warranted correct (M-AMBIG-1 + B-1..5) | | 6/6 | 6/6 | 6/6 |
| false-positive packets on banal B-1..5 | | 0/5 | 0/5 | 0/5 |
| invalid packets | | 0 | 0 | 0 |

Overall: 29/42 correct (69%). Validity 42/42 — the contract validates shape only.

## 3. Failure taxonomy (measured, not aggregated)

- **Unnecessary packet emission / abstention failure: 0/18.** All three extractors
  abstained correctly on all six abstention-warranted cases (18/18), including the
  neutral N1 with no abstention coaching. Track A's Config-B collapse (5/5
  false-positive durable packets) did **not** replicate under any posture here — it was
  instruction-driven ("always produce a complete reading"), not contract-driven.
  The opposite failure appeared instead (see over-abstention).
- **Over-abstention (new, systematic in N2): 7 misses.** N2 abstained on every case
  (14/14 ABSTAIN), scoring 7/14: correct on all holds/controls, wrong on all seven
  warranted-packet cases (D-SAME-1, D-DISTINCT-1, D-REVISE-1, M-SAME-1, M-DISTINCT-1,
  P0 pair). Abstention licence without identity guidance collapses recall. Both
  directions fail: always-emit (Track A Config B) and always-abstain (N2 here).
- **Unsafe merge / ambiguity guessed:** N1 D-AMBIG-1 (bare pronouns asserted as
  certain, `live`, recency fiat — with fixture caveat §4); N3 D-AMBIG-1 (same
  assertion, hedged in prose/guardrail but `state: live` — the schema records
  certainty the prose disclaims); N1 M-SAME-1 soft-picked most-recent antecedent
  (hedged as `contested` with guardrail — less severe than Track A Config B's
  certain pick from ≥6, but still a directional lean the evidence does not support).
- **Unsafe split:** N1 M-SAME-1 (two adds held separate vs oracle ONE lineage);
  N3 M-SAME-1 (held potentially-distinct vs ONE); N3 P0-DENTIST (held d1/d2
  potentially-distinct vs authored ONE). All three carry fixture caveats (§4):
  markers genuinely differ in-slice; oracle sameness rests on harness convention
  (refs-suffix) or authored intent invisible in the slice.
- **Revision / supersession failure + contradiction loss (clean, no caveat):**
  N1 D-REVISE-1 emitted `live` with all four items in `supports` and empty
  `contradicts` — the done→change→remove tension Track A required stay visible was
  smoothed into a clean history. All evidence was in-slice; this is reasoning
  failure, and it occurred in the *neutral* extractor, showing contradiction
  handling does not come free with the contract. N3 (generic caution) got this
  right (`contested`, `contradicts: [e3]`); N2 abstained and lost the contradiction
  (safe direction, still a miss).
- **Invalid packets: 0/42.** Every emission satisfied the Phase-0 shape invariants.
  Replicates Track A: **validity ≠ correctness** (69% correct despite 100% valid).
- **Model disagreement:** N1 vs N2 agree 8/14; N2 vs N3 agree 8/14; N1 vs N3 agree
  12/14, disagreeing exactly on D-REVISE-1 (N1✗/N3✓) and P0-DENTIST (N1✓/N3✗).
  The two best runs (11/14 each) fail on *different* cases — there is no stable
  11, let alone 14. Disagreement concentrates in identity/reference + revision,
  never in abstention controls (unanimous 18/18).

## 4. Fixture limitations found (under-specification, not reasoning failure)

Blinded running exposed three places where the frozen manifest does not give a
blinded extractor what the oracle assumes. These bound the scores above and must be
fixed before any graduation claim:

1. **D-AMBIG-1 slice contains a single candidate.** The blinded evidence shows only
   e1 (`demo-molesaww`) plus two bare pronouns; the oracle's competing antecedents
   (`demo-mole3ff2`, `demo-mole5idi` "still live in window") are out-of-slice session
   context. Both N1 and N3 independently noted "only one explicit antecedent in the
   provided evidence." Their merge assertion is faithful slice-local inference; the
   oracle's hold requires window context never supplied (or a general
   bare-pronoun-distrust rule, which only N3 had — and N3 still asserted). Fix:
   include the competing-antecedent turns or a listing snapshot in the slice.
2. **M-SAME-1 sameness rests on a harness naming convention.** Markers differ
   (`moll89qz` vs `moll89qz-refs`) with no in-slice alias statement; oracle sameness
   rests on "refs-suffixed row is a second row for same test matter" + 19s adjacency.
   A blinded extractor cannot know harness conventions — N1's contested split and
   N3's explicit hold ("no explicit alias statement") are the honest slice-local
   outputs. This is exactly the marker-literalist split risk Track A predicted (§4.5),
   now observed blind. Fix: decide whether refs-rows are one matter (then say so in
   evidence) or genuinely test split-sensitivity (then correct the oracle).
3. **P0-DENTIST abstraction is ambiguous on d1/d2 identity.** d2 "repeats the
   dentist reminder with another probe marker" supports both readings: N1's
   contested-merge (matches authored oracle) and N3's contested-hold (matches the
   distinct-markers-are-distinct rule N3 was given). The oracle's ONE comes from
   authored intent, not slice evidence. Fix: disambiguate the abstraction or score
   both contested readings as acceptable with different recheck conditions.

## 5. Representation constraint vs reasoning failure (separated as instructed)

**Representation-constraint evidence (replicated independently, therefore stronger
than Track A's single-analyst observation):** all three extractors, unprompted and in
different words, flagged the same gaps:
- (a) **No native multi-matter shape.** D-DISTINCT-1 / M-DISTINCT-1 distinctness had
  to be smuggled into a singular `matter.identity` string plus hypothesis prose
  (N1, N3 both noted this; N2 cited it as the reason ABSTAIN was "the only
  non-distorting option"). A `matters[]` or explicit identity-relation slot would
  make distinctness machine-checkable.
- (b) **`state` conflates hypothesis status with matter lifecycle.** A
  removed/cancelled matter with a still-believed reading (D-REVISE-1, P0-MEETING)
  has no clean encoding ("live reading of a dead matter" — N1).
- (c) **Single `confidence` forces averaging** when identity is certain but terminal
  state is inferred (N1 on D-REVISE-1); per-claim or identity-vs-claim separated
  confidence requested (N1, N3). N3 added: no dedicated referent-indeterminacy /
  candidate-antecedent field — holds live in prose + `recheck_when`, not checkable
  structure.
These are contract gaps, not extractor mistakes: validity held (42/42) while the
extractors reported working around the schema.

**Reasoning-failure evidence (no fixture caveat):** N1 D-REVISE-1 contradiction loss
(all-supports `live` on a done→change→remove sequence fully present in-slice);
N1/N3 D-AMBIG-1 `live` assertion on bare pronouns (prose hedges, schema asserts);
N2 blanket over-abstention (licence mis-scoped to warranted packets). The schema did
not cause these — N3's D-REVISE-1 proves the contract *can* carry the contradiction
when the extractor is instructed to look.

## 6. What this establishes and fails to establish

- **PROVEN:** (1) Track A's strict 14/14 does not survive blinded independent runs:
  best 11/14, and the two 11s disagree (D-REVISE-1, P0-DENTIST). The 14/14 was
  analyst-authored trap knowledge, not elicited discipline. (2) Extraction outcome
  remains posture-dominated: neutral 11/14 vs abstention-licensed 7/14 vs
  generically-cautious 11/14 on identical evidence/contract — different failure sets,
  not a stable capability. (3) Abstention is elicitable without strictness (18/18
  unanimous, including neutral); the Config-B collapse was instruction-driven.
  Over-abstention is the symmetric failure (N2's 7 misses). (4) Validity ≠
  correctness replicates at larger n (42/42 valid, 29/42 correct). (5) The three
  Phase-0 contract gaps (§5a–c) replicate across independent blinded runs.
  (6) Three fixture under-specifications (§4) confound the current scores.
- **HYPOTHESIS:** Real deployment (no explicit identity keys) shows equal-or-worse
  reference failure than measured here; the markers made even this set easier than
  reality (unchanged from Track A; this replication is consistent but adds no new
  evidence for/against).
- **OPEN:** Whether *any* prompt reaches 14/14 blind on a repaired manifest; whether
  splitting appears at scale under marker-literalist strictness; cross-architecture
  generality (all runs here share one model family); latency/token metadata (manual
  runs, none recorded); the three contract-gap fixes (proposed, not made).
- Recommendation: RETAIN the Phase-0 packet as representation baseline; DO NOT treat
  extraction as established — this replication *weakens* the 14/14, it does not
  confirm it. Require before any production decision: (i) repaired manifest (§4
  fixes: competing-antecedent context, refs-row alias ruling, P0-DENTIST
  disambiguation); (ii) genuine multi-architecture blind bakeoff (≥2 model families,
  frozen repaired manifest, abstention scored as success, latency/tokens recorded);
  (iii) a prompt that reaches the oracle blind, not one written from it. Contract
  revisions proposed (not made): first-class ABSTAIN outcome; `matters[]` or
  identity-relation slot; identity-confidence separated from claim-confidence;
  candidate-antecedent slot for holds. No production architecture proposal — Track A
  replication evidence only.

## 7. Handoff

```text
WHAT I CHANGED: nothing in production; added this research report only (plus /tmp scratch).
WHY IT SERVES THE NORTH STAR: tests whether interpretation preserves truth before building on it.
CANON PRINCIPLES TOUCHED: none (research only).
EVIDENCE / TESTS: /tmp/track_a_replication/{blinded_evidence,emissions_N1,emissions_N2,emissions_N3}.json; sealed oracle /tmp/track_a/manifest_and_oracle.json (scorer-open only); committed redaction above.
WHAT I DID NOT CHANGE: src/, schema, runtime, prompts, deployed behaviour, other tracks' scope.
REGRESSIONS / RISKS: none (offline, removable; report file only).
DELETE CANDIDATES: /tmp/track_a_replication/* and /tmp/track_a/* after synthesis ingests them.
OUT-OF-SCOPE FINDINGS: none claimed beyond Track A replication.
EXACT NEXT STEP: repair the three fixture gaps (§4), then run the multi-architecture blind bakeoff (§6.iii).
```
