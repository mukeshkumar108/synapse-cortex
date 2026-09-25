# Phase-A.5 Validation — Real-Evidence Precision Pass (2026-09-25)

No production changes. No schema changes. No new abstractions (one runner-level
addition: sequential prefix replay + snapshot diffing, which is measurement,
not architecture). Shadow/test/report files only.

## 0. Evidence availability verdict (blocking finding)

**Kai/Elena and Kai/Isa transcripts are not replayable from this repo.**
RPD2 is a frozen external reference: `docs/GRADUATION-LEDGER.md` confirms the
boundary, `/tmp/` holds only IPC pipes (not baselines), Notion sources are
unfetchable. Real RPD2 verbatim available in-repo is limited to fragments
embedded in tests: Elena msg-17 `"I'll give you space. I'll be here."` and the
grief fragment `"he was diagnosed. and then less than a year later he was gone."`
(`tests/test_bilateral_state.py`).

What A.5 replayed instead, without simplification:
- **Full S1 (14 events) and full S4 (15 events)** through the shadow path,
  sequentially (every prefix), including interleaved email/payment-feed/
  calendar/assistant turns — this is the actual mess, not a slice.
- S2 Freepik chain, S3 Sam chain, Elena fragment, Sophie promise (s4_e03),
  observability pair as before.
- Five RECONSTRUCTED probes retained only where the corpus has nothing
  (Isa pact, Marko, Dad probe, stale-loop bridge, Sam-promise pair) and are
  now explicitly marked as non-evidence for the persistence decision.

Criterion "real messy evidence reliably produces useful relations" is therefore
evaluated on S1/S3/S4 + fragment, **not** on RPD2 arcs. The Isa-pact
representation claim from Phase A remains a capability demo, not replay proof.

## 1. Candidate precision

### Elif: Phase A produced a genuine false positive — caught and fixed
s4_e04 regret ("wish I'd remembered to message her") → s4_e10 self-resolution
("I finally messaged Elif, she's loving the new job"). Phase A emitted a
user-facing `FOLLOW_UP` because of a hardcoded `"elif" in content` carve-out.
That carve-out is deleted. Now: `resolves(finally-messaged → regret)` retires
the matter; full replay shows **zero** Elif moves. Sequential replay shows the
correct arc: restraint at e04 (assertional-only, NO_MOVE) → invalidation at e10.
Test `test_c5_elif_self_resolution_invalidates_followup` pins it. Verdict: the
trap now works as designed, but only after A.5 caught the FP — precision was
**not** proven in Phase A.

### Carlos: all moves accounted for (full S1 replay, final: 3 moves, 2 UF)
- `WATCH/MONITOR` on partial payment — internal, eligible. Correct: remainder
  outstanding, feed partially reconciles (`verify_feed → partial`).
- `FOLLOW_UP/CHECK_BACK` cake vendor — user-facing. Justified: never resolved
  in-corpus (still open at e14), user asked to be kept straight. Not avoidable
  without dropping a real open matter.
- `REMIND/DUE` urgency roundup — user-facing. Justified: explicit user request
  (modality `intended` exempts it from T2 dampening). Not avoidable.
- Debt itself: `MOVE_HELD` (amount ambiguity held for internal reconcile;
  later settled by the 2,100 `refines`), remainder/bank/chase matters all
  `NO_MOVE_WARRANTED` with `reconcile_sources/verify_feed` attempts.
- **Zero Carlos-related user-facing moves.** The 2 UF moves are non-Carlos and
  both authorized. System attention demonstrably absorbed the rest.

### Neck vs headache
Neck on real evidence: silent (1–2 mentions) → internal `WATCH` at e04 (3rd
mention, persistent, unresolved; real s4_e06 assistant check-back corroborates
the judgement) → retired at e07 (`refines` improving) → confirmed at e10
(`resolves` "basically fine / not a thing"), with s4_e11 assistant drop as
corroboration. No suppression object at any point; no user question ever.
**Headache: zero mentions corpus-wide — untestable on real evidence.**
The one-off-headache side of the comparison remains a theoretical property of
the pipeline (≤2 refs → assertional-only → NO_MOVE), not an observed result.

### Chairs re-ask (rupture/repair microcosm)
e05 "told the venue yes" `fulfils` → e07 "Did I ever sort the chairs?"
`reopens` → **question answered from history, zero moves** (`NO_MOVE_WARRANTED`,
`search_state → resolved`). This is the SA-gate working as specified.

## 2. Entity identity, both directions (real S1 evidence)
- Positive: `same_as` matias-Friday↔matias-Thursday and yoshi-Wed↔yoshi-Thu,
  IDF-weighted (score ≥ 2.0) + shared non-user subject. Yoshi-calendar identity
  rides convergent `refines` edges to the same target.
- Negative: Studio Sam ↔ Cousin Sam still `blocks`, never `same_as`
  (subject-disjoint veto).
- Precision history (reported, not hidden): raw shared-token counting first
  merged same-person/different-matter pairs (Carlos debt↔bank-issue) and
  cross-kid pairs (Yoshi↔Matías via "school/uncertain"); fixed by IDF weights
  + subject rule. Cross-source alone is **not** a merge signal.

## 3. Relation revision (sequential S1, 14 prefixes, 10 changing steps)
- `partially_fulfils` born at e03 (email), evidence grown at e04 (feed) —
  original ref preserved, never rewritten.
- Debt `UNKNOWN`-with-roles → role-shedding as `refines`(2,100 at e09),
  `conditioned_on`(bank at e11), `refines`(still-unpaid at e14) land.
- Yoshi Wed → calendar correction (e06, roles shed) → Thu dance confirm (e09,
  `same_as` + `refines` converge).
- Florist open → `resolves` at e09; school-money uncertain → `fulfils` at e13
  (feed); Freepik chain supersedes ×2.
- No relation was ever edited in place; revision = new edges + evidence
  growth + role change. Reified relations behave as revisable state.
- Mechanical fix en route: per-prefix id namespaces made stable + `same_as`
  direction canonicalized after phantom direction-flips polluted diffs.

## 4. Directed obligations, four directions (real evidence only)
| Direction | Evidence | Frame | Downstream |
|---|---|---|---|
| Third party → user | Carlos→Ashley (email+feed), school→parent (consent deadline) | obligor `carlos`/`school` | internal WATCH / reconciled views; never self debt |
| Character → user | Elena→Kai msg-17 fragment | obligor `elena`, beneficiary `kai` | internal WATCH; `companion_obligation` empty |
| Companion → user | Sophie s4_e03 "I'll come back to it later" | obligor `sophie` | `ACT/FULFIL_OWN_PROMISE`, internal — genuine self-accounting path |
| User → third party | venue chairs (done), Priya £12 (paid), florist colours (sent) | obligor `user` | completions assertional-only; open ones (cake) FOLLOW_UP |
| Character → character | **none in corpus** | — | Marko→Isa stays RECONSTRUCTED; flagged, not evidence |

Same `ObligationFrame` shape handles all four; consequences diverge correctly.
Third-party obligations are watchable/reconcilable but never self debt; the
companion's own promise is the only self-accounting row.

## 5. Pass/fail against the seven criteria
1. Real messy evidence produces useful relations — **PASS** (S1: 15 rels over
   14 events; S4 chains; Sam disambiguation; all with provenance/confidence).
2. Provenance allows later revision — **PASS** (sequential diffs; append-only
   evidence; role shedding; nothing rewritten).
3. Positive and negative linking both work — **PASS with note**
   (positives: Yoshi, Matías; negative: Sams; Yoshi-calendar via refines only).
4. Semantic closure without false closure — **PASS** (florist, school, Elif,
   neck, Freepik closed; cake correctly stays open; zero re-asks).
5. Move precision over move count — **PASS with correction** (Elif FP caught
   and fixed in this pass; Carlos 0 debt-related UF; chairs answered
   internally; final S1: 3 moves for 25 claims).
6. `NO_MOVE_WARRANTED` for Elif/headache-style cases — **PARTIAL**
   (Elif: pass after fix; headache: untestable, no corpus evidence).
7. System attention prevents unnecessary user attention — **PASS**
   (chairs re-ask, Friday-ambiguity held, third-party watches internal,
   T2 dampening with explicit-request exemption).

## 6. Special casing removed/added (honest ledger)
- REMOVED: Elif hardcoded carve-out (was the FP source); raw token-count T2
  weights (inflated by `mess`⊂`message` etc.); first-match hint resolution
  (mis-targeted Matías→Yoshi until subject-preferred `find_for`).
- ADDED (narrow, evidence-backed): completion strip (`signed`, `finally
  messaged`); persistent-somatic WATCH (≥3 refs, no resolution edge);
  question-from-history resolution; IDF+subject `same_as` gate.
- REMAINING WEAKNESS: same-person-restated promise claims (email vs feed
  paraphrase of Carlos's remainder) merge via `same_as` on thin overlap —
  defensible (same commitment restated) but the lowest-confidence edge class;
  worth a `restated` relation type before persistence.

## Recommendation
Phase B (single reified claim/relation store with provenance) is justified **for
the S1/S3/S4-proven relation classes** (refines/supersedes/resolves/fulfils/
partially_fulfils/reopens/conditioned_on/blocks + gated same_as). Two items
stay out of the persistence case until RPD2 transcripts are replayable: Isa
multi-turn pact extraction from mess, and character→character obligations.
Headache one-off restraint is predicted but unobserved — do not cite it as
proven. Consider adding a `restated` predicate for paraphrase identity before
migrating.
