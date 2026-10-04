# Interpretation / Meaning — Phase 0 offline sidecar

This is a research fixture, not a production path. It has no imports from
`src/`, no database, no model call, and no authority to mutate Cortex state.
It tests whether a small, inspectable hypothesis packet changes bounded
decisions when added to evidence and graduated state.

`cases.json` contains heterogeneous trajectories. Sophie and RPD2 references
point to the frozen, gitignored historical replay artefacts documented in
`docs/HISTORICAL_CORPUS.md`; Bloom, worldview, and astrology cases are clearly
labelled synthetic. Excerpts are deliberately short and non-diagnostic.

Run:

```bash
./.venv/bin/python evals/interpretation_phase0/run.py
```

The runner validates the bounded representation, compares the current-state
decision with the sidecar decision, and writes no files. The checked-in
research conclusion is `docs/INTERPRETATION_PHASE_0_RESEARCH_PACKET.md`.

## Candidate packet (tested, not canonical)

Each case supplies one `matter` identity claim and one or more hypotheses.
Each hypothesis has:

- a proposition and product scope;
- an ordinal confidence with a textual basis (never computed by score sum);
- evidence references separated into `supports`, `qualifies`, and
  `contradicts`;
- a revision state: `live`, `contested`, or `superseded`;
- a persistence bound and a concrete `recheck_when` condition;
- one bounded downstream implication with an explicit guardrail.

Evidence remains outside the hypothesis and canonical. References are enough
for this experiment; copying observations into a graph was unnecessary.

