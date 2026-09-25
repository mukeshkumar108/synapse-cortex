# Phase-A Shadow Prototype — Report (2026-09-25)

Shadow-only experiment. No migration, no new table, no foreground integration,
no change to `list_actionable()`, `evaluate_due`, packet behaviour, or lifecycle
semantics. Production output remains authoritative throughout.

## Prototype

- `src/shadow_a/schema.py` — claim / reified-relation (13-type bounded vocab) /
  5 state roles (0..n) / directed obligation frame / shadow T2 / 6 read views /
  7-kind CandidateMove with matter link / resolution attempt / 5-way telemetry.
- `src/shadow_a/pipeline.py` — deterministic stdlib-only pipeline:
  extract → relations → roles → obligations → T2 → views → moves (SA→UA gate).
- `src/shadow_a/cases.py` — 9 cases over real Sophie 1–4 fixture inputs
  (oracles never used for behaviour) + 5 minimal RECONSTRUCTED probes for arcs
  absent from the repo (Isa pact, Dad probe, Marko, stale-loop bridge,
  Sam-promise observability pair). Reconstructions preserve the load-bearing
  difficulty (paraphrase, wrapper-vs-terms, ownership, observed-vs-unobserved).
- `scripts/run_shadow_phase_a.py` — rerun entrypoint, writes disposable JSON.
- `tests/test_shadow_phase_a.py` — 12 tests incl. a mechanical no-prod-import guard.
- `reports/shadow_phase_a_output.json` — full inspectable shadow output.

## Acceptance table

| # | Case | Production (rules summaries) | Shadow | Preserved? | Roles OK? | Moves / internal attempt / user attention |
|---|---|---|---|---|---|---|
| 1 | Carlos partial / chase | Debt `USER_COMMITMENT/UNKNOWN` all 11 ckpts; Q1,500 never reconciled; `I'll send the rest` mis-owned as `USER_INTENTION`; `current_meaning=0` | `partially_fulfils(Q1,500→debt)`, `depends_on(remainder→bank release)`; obligor `carlos→user`; `which-friday` held for internal reconcile | Yes — partial + ownership | Yes | 4 moves, 2 user-facing (explicit REMIND eligible; cake FOLLOW_UP held by T2 `high_load` w=0.35→eligible after fix); debt WATCH internal; `verify_feed` partial |
| 2 | Freepik cancel/reschedule | Final state clean (user cancelled; chain gone) but no explicit supersession record | 2× `supersedes` (push + self-cancel → original); completion record assertional-only, no ACT | Yes — chain explicit | Yes | 1 internal WATCH; 0 user-facing; 7 NO_MOVE_WARRANTED |
| 3 | Isa pact | No RPD2 fixture in repo (blind-eval comparison only) | 5 claims (pact + 3 terms + wrapper), 4× `part_of` into pact; terms owned `user / user+isa` jointly; wrapper linked, not dominant | Yes — terms survive separately | Yes | 5 internal (WATCH×4 + ACT on pact, non-user-facing); 0 user-facing |
| 4 | Studio vs Cousin Sam | S3 final: studio contract still `UNKNOWN` after user signed; pickup `FULFILLED` via calendar; 2 loops + 3 clarifications linger | No `same_as`; `blocks(studio↔cousin)` merge-refusal; `fulfils` pickup chain; 3 third-party WATCHes | Partly — identity correct; signing→contract fulfilment link still inferred only | Yes | 4 moves, 1 user-facing (explicit remind); SA `search_honcho(sms/email)` partial first |
| 5 | Neck/headache/Elif | S4 final: Elif stored as `USER_INTENTION` (misclassified worry); somatic restraint untested in rules mode | 4/5 matters `NO_MOVE_WARRANTED`, claims+roles retained, zero suppression objects; `refines`+`resolves` neck chain; Elif FOLLOW_UP eligible | Yes — restraint without suppression | Yes | 1 user-facing (Elif check-back); T2 `easing`, w=0.8 dampens routine nudges |
| 6 | Surgery context | Matt relief present in S4; no T2 record (`current_meaning=0`); Dad arc not in fixtures | T2 labels inferred (`high_load, health_watch_present, family_health_context`, w=0.65), never hardcoded; 7/8 NO_MOVE; Elif FOLLOW_UP eligible | Yes — modulation without label mandate | Yes | 1 user-facing; surgery matters watched silently |
| 7 | Ashley/Marko third-party | `USER_INTENTION` sink pattern (S1: `I'll send the rest` user-owned) | `companion_obligation` empty; 3 internal WATCHes (`carlos/marko/ashley→user`), owners `carlos/marko/ashley`, derivation owner `sophie` | Yes — ownership split holds | Yes | 0 user-facing; separate derivation, never self debt |
| 8 | Stale loop, new words | S2 indirect-closure items linger as separate expectations | `refines(restatement→open matter)` + `fulfils(photo→letter)`; open matter shed `unresolved`; 8/8 NO_MOVE, 0 re-asks | Yes — closure across vocab | Yes | 0 moves; resolution via `reconcile_sources` |
| 9 | Absence observability | No `expected_but_missing` concept in prod | Observed inbox → `expected_but_missing`; unobserved → `UNKNOWN` with reason; promise itself MOVE_HELD (no user authority) | Yes — gate holds both ways | n/a | 0 user-facing |

Success criterion was better preservation/reasoning, not more rows: c8 (0 moves, loop closed),
c7 (0 user-facing, ownership correct), c5 (restraint with retention) are the strongest passes.

## Where the theory failed / required special casing

1. **Substring matching is a claim-killer.** Three independent false-hit bugs
   (`matt`⊂`matter`, `dad`⊂`grandad`, `mess`⊂`message`, `sam`⊂`same`) inflated
   T2 weights and spawned ghost claims. Fixed with word-boundary matching
   (`_key_hit`, `_count_hits`) — but a real extractor needs this by construction,
   not by patch. Lesson: permissive content + bounded predicates still needs
   disciplined span grounding.
2. **Completion records over-promote.** `user cancelled freepik themselves`
   derived ACT until a completion-strip rule (`cancelled/photo sent/paid back/
   signed…` → assertional-only) was added. A real role-mapper needs
   done-vs-due as a first-class distinction, not a keyword list.
3. **T2 dampening nearly swallowed an explicit request.** `held:context_dampened`
   applied to a user-authorized REMIND until explicit requests
   (`remind` + modality `intended`) were exempted. Invariant: inferred nudges
   may be dampened; direct user asks may not.
4. **Standing terms want WATCH, not ACT.** Bilateral pact terms with no due and
   no action verb defaulted to ACT; corrected to internal WATCH. The
   assertional/obligation boundary for joint standing agreements is the
   thinnest part of the role scheme.
5. **Reconstructed probes are stand-ins, not proof.** c3/c6–c9 lean on minimal
   synthetic events. The pipeline code paths (part_of, observability gate,
   directed frames) are real and fixture-backed cases (c1/c2/c4/c5) carry the
   evidentiary weight; RPD2 replays should be rerun if transcripts land in-repo.
6. **`same_as` never fired positively** (only the Sam `blocks` refusal). Positive
   entity-merge remains unexercised — expected: fixtures contain no true
   same-entity paraphrase pair with shared referent evidence.

## Rerun

- `./.venv/bin/python scripts/run_shadow_phase_a.py` (writes
  `reports/shadow_phase_a_output.json`)
- `./.venv/bin/python -m pytest tests/test_shadow_phase_a.py -q`
- Prod sanity (untouched, verified): `test_health.py`, `test_surface_lifecycle.py` pass.

## Recommendation

Phase B persistence case is supported for exactly one store: reified
claim-relations with provenance (the layer with no current equivalent and
repeated closure/supersession wins here). Roles, views, moves, and the SA→UA
gate should stay read-side; nothing in these results requires them to be tables.
