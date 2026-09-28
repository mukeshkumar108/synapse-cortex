# Honcho Rerun Contract — Capability Test With Data (Two-Stage Gate)

> Programme: `docs/LONGITUDINAL_COMPANION_COGNITION_BLITZ.md` (§4 notes,
> §12). First run: `reports/honcho_longitudinal_qa_probe_2026-09-28.md`
> (local data insufficient + `conclusions/query` 422; fallback 10/10
> recruited). This rerun answers Honcho-the-capability, still nothing else.
> Offline research only; persists nothing; wires no runtime path.

## Stage 1 — Fix or route around `conclusions/query` (gate; stop if blocked)

Resolve the 422 on schema-valid bodies against the Honcho build in use
(local checkout `/Users/mukeshkumar/play/honcho`; VPS stack runs its own
build — record both versions/commits). Either fix forward, identify the
correct query API if the probe used the wrong one, or document the defect
upstream with request/response pairs. Do not proceed to scored runs
through a broken endpoint by hacking around it in ways production could
not reproduce. If Stage 1 fails, report it as the finding and stop —
capability remains OPEN, fallback stands, no Stage 2.

## Stage 2 — Frozen F1–F10 blind through a populated workspace

- **Corpus:** frozen longitudinal histories with known evidence and
  counterevidence (S1–S4 fixtures at minimum). Ingest into a probe
  workspace on the VPS live stack (preferred — richer test histories and
  the real deriver) or local Honcho, at the agent's documented choice.
- **Cleanliness rules (methodological, not privacy theatre — the operator
  is the sole user and VPS histories are deliberate test data):** frozen
  corpus committed or hashed before runs; probe workspace used for scoring
  contains the frozen corpus plus only explicitly listed additions;
  **stored Honcho conclusions are excluded from the scored semantic-read
  path** (they may be inspected as a separate failure surface per §4, but
  must not help the main result); no open-ended scans (void if run).
- **Questions:** the frozen F1–F10 battery (same IDs, same known answers,
  same trap coverage: ABSTAIN ×2, dedup, correction dominance ×2,
  cross-frame trap), run blind (reader sees questions + workspace, never
  the oracle). Reader may be Honcho-native QA or model-over-Honcho
  retrieval — record which; the recruitment contract binds both.
- **Recruitment discipline** is part of every read (reading + support +
  counterexamples + corrections + independence warning + scope/frame +
  what-would-change-it). Missing recruitment = FAIL for that question.

## Scoring and bar (unchanged from the probe contract)

Zero fabricated episodes, zero missed user corrections, zero cross-frame
leaks; grounding + counterexample + dedup correct on ≥7/10; correct
ABSTAINs on F5/F9. Anything less = NOT USABLE for semantic nomination
(fallback stands). Separately report: stored-conclusion inspection
findings (deriver tier-confusion rate on the probe corpus); endpoint
reliability (latency, error rate over the run); what breaks first at this
corpus scale.

## Claims and landing

Label every claim PROVEN / SUPPORTED / HYPOTHESIS / OPEN / KILLED. Raw
counts and failure classes; state Honcho build(s), workspace IDs, corpus
hash, endpoint used, and every external call made. Create only: this
task's report at `reports/honcho_rerun_<YYYY-MM-DD>.md` (+ `/tmp`
scratch, never load-bearing). Commit only owned files. Completion states
canonical path + commit hash + owned-files-only confirmation. Do not
persist reads, design caches, or wire runtime paths.
