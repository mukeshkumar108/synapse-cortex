# Longitudinal Read Contract — Recruited Synthesis Over Retrieved Evidence

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§4 notes).
> Evidence: Honcho probe (`85942ef`) + rerun (`b7dabcb`): Honcho retrieval
> 10/10 coverage; Honcho-native synthesis 7/10 with critical failures in
> correction dominance, hearsay-as-fact, and hindsight leaks; stored
> conclusions unsafe (accumulation without supersession). Therefore:
> **Honcho (or equivalent) is evidence infrastructure; synthesis is ours.**
> This contract defines the synthesis layer. Offline research until a
> reliance claim is earned blind; no production wiring.

## What a read is

A bounded, interrogative, ephemeral synthesis answering one pulled
question over longitudinal evidence. Reads never scan, never persist as
truth, never precompute. Every read is rebuilt when asked; caches, if
ever introduced for scale, are disposable materialised views with
invalidation conditions, never source-of-truth.

## Pipeline (all steps mandatory; missing recruitment = FAIL)

```text
bounded pulled question
  (from a live candidate, arbitration case, or explicit JIT hint —
  never open-ended curiosity)
        ↓
HONCHO-STYLE RETRIEVAL (evidence infrastructure)
  semantic + lexical retrieval over longitudinal corpus;
  coverage matters, judgement absent by construction
        ↓
CORTEX AUTHORITATIVE JOINS (override channel)
  lifecycle state, authored corrections, boundaries, receipts,
  closures joined BEFORE synthesis — out-of-band authority
  outvotes in-band evidence at the decision checkpoint
        ↓
RECRUITED SYNTHESIS (our layer) returning:
  - current reading (scoped, framed)
  - supporting episodes (cited, timestamped)
  - counterexamples (mandatory search; absence stated, never assumed)
  - user corrections respected (correction precedence over pattern)
  - temporal cutoff enforced (no future evidence leaking backwards;
    reads timestamped: "as of <checkpoint>")
  - independence / same-episode accounting (five mentions ≠ five events;
    correlated sources flagged, e.g. two user-sourced records)
  - observation vs interpretation separated
  - scope and frame (no cross-frame transfer)
  - abstention where evidence is insufficient (hearsay is never promoted)
  - what would change the reading (recheck)
        ↓
bounded ephemeral reading → arbiter / Runtime / projection JIT slot
```

## Hard gates (any violation fails the read)

1. **Correction precedence:** a user withhold/correction at the decision
   checkpoint overrides later-or-earlier pattern evidence (F2-class).
2. **Temporal cutoff:** bounds are enforced structurally, not requested in
   prose; hindsight use of later evidence is a critical failure (F9-class).
3. **Abstention:** unverified reason, unidentified referent, or
   insufficient evidence → ABSTAIN. Hearsay promotion (F5-class) is a
   critical failure.
4. **Scope/frame:** no entity conflation (F4-class), no moment-rule
   globalisation (F8-class).
5. **No stored-conclusion reliance:** accumulated Honcho (or any) derived
   conclusions enter at most as retrieval hints, never as premises.

## Regression battery

Frozen F1–F10 (Honcho probe §1 / rerun §§3–4) with the pre-registered bar:
zero fabrication, zero missed corrections, zero cross-frame leaks,
grounding + counterexample + dedup correct on ≥7/10, correct ABSTAINs.
Any future synthesis implementation — model upgrade, prompt change,
retrieval change — reruns F1–F10 blind before a reliance claim. Failing
the battery retires the implementation, not the contract.

## Reader scoping (design requirement)

There is no omniscient reader: recall is peer-membership / session-allowlist
scoped (rerun A1 finding). Any longitudinal reader needs explicit session
membership or per-call allowlists, which itself requires a
retrieval-routing step. Scope the reader before scoring the reading.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. This
contract changes only on blind pre-registered evidence. No durable
shared-derived store is authorised by anything here (P1 0/8 stands).
