# Substrate status (operational orientation for future agents)

## Current phase
**Operational substrate graduated. Current programme phase: interpretation / meaning research.**

## Baseline
- Cortex `9aadba5`
- Runtime `00e8364`

## Before modifying the substrate
An agent must:

1. Identify a concrete violated invariant (not an ugly semantic result).
2. Demonstrate it from real evidence, replay output, or product behaviour.
3. Classify the failure as substrate vs interpretation/product behaviour.
4. Modify the layer that owns the failure.
5. Never add another per-turn rescue path merely because semantic judgement was imperfect.

Canon reference: `docs/COMPANION_CANON.md` §2.16 (experiments graduate or die),
§7 (pendulum check), and the decision hierarchy in §0. North Star:
`docs/COMPANION_NORTH_STAR.md`. Blitz record: `BLITZ.md` (closed).

## Known interpretation failures that are NOT substrate regressions
The substrate is working as designed when you see these; the defect lives in
extraction prompts, judge behaviour, or product policy — fix it there:

- duplicate dentist commitments / paraphrased same-obligation rows;
- add/move/cancel meeting treated as separate matters;
- pronoun/elliptical reference resolution ("how's he doing?");
- internal IDs leaking into semantic titles;
- watch-vs-uncertainty same-matter variance;
- broad themes persisting as overly durable matters;
- RPD2 rupture/repair meaning disputes;
- generic follow-up loops minted for question-shaped turns;
- incidental trivia ("getting lunch") becoming durable loops;
- resolved matters re-attracting attention without new evidence
  (check suppression/receipts first — often a missing receipt, not a broken lifecycle).

If none of the above explains what you see, re-read the canon, reproduce
against the frozen corpus (`docs/GEMINI_EVAL_PACKET.md`), and only then
propose a substrate change with a violated invariant attached.
