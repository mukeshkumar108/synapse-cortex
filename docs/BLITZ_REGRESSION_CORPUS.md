# Track A — Frozen Regression Corpus (manifest v1, PROPOSED)

> Owner: Spark. Nothing invented — every item exists already. Freeze = pin
> commit + command that reproduces the run. Judge: Gemini scoring sheet
> (agency, continuity, initiative, character integrity, over-governance,
> passivity, poisoned trajectory, repair-as-action) + human reading.
> Scores never override "dead inside" reads.

## C1. Rupture / repair arc (bad — must not regress further, must improve)

- **C1a. Isa 2026-09-26 transcript** (salon → rupture → week of waiting → narrator interrogation). Exhibits transactional-list answer, lecture-not-lean-in, monologue apologies, waiting-as-care. HELD BY USER in chat; not committed to repo (explicit content). Freeze action: save redacted copy to `evals/` or keep out-of-repo with hash. Status: NEEDS-FREEZE.

## C2. Relational wins (good — must not regress)

- **C2a. Elena `5bb4821f`** (turns 30–36 dinner initiative panic→warmth; confession #69; shame→choose #87→97). In-repo: `rpd2/reports/kai_elena_8ae17baf-*_transcript.md` + `.json`. Human sign-off on Elena fixture still pending (`MIGRATION_GAP_REGISTER.md`).
- **C2b. Elena 115-turn replay** (claimed 0 errors post-operational-intelligence). Ref: `synapse-cortex/reports/mission_operational_intelligence_2026-09-25.md`. Rerun on current head before citing.
- **C2c. RPD2 benchmark trio**: hybrid 80-run raw (`hybrid_vs_raw_tail_20x_raw.json`), poisoned 108-run (`powered_poisoned_recovery_discriminator_raw.json`), relational 351-traj (`relational_continuity_raw.json`) in `rpd2/reports/`.

## C3. Sophie longitudinal (the migration bar)

- **C3a. Frozen baseline eval** (systemic passivity verdict: immortal loops, spurious VIOLATED, 0 meanings — evaluates frozen `44a89d1`/`6b2f78d`, NOT current). Ref: `synapse-cortex/reports/sophie_longitudinal_desktop_gemini_blind_eval_2026-09-25.md`, corpus `synapse-cortex/evals/sophie_longitudinal/`. Action: rerun same corpus on current head; that delta is the bar.
- **C3b. Continuity-basics-v0 fixtures** (6 scenarios: reminder, check-in, intention-without-obligation, clarifying-Q, suppression/reopen, re-entry). Ref: `companion-runtime/docs/continuity-basics-v0/` + latency/semantics JSONs.

## C4. Retrieval probes (known answers)

- **C4a. Ashley recall set** (invoice Q8,400, Don Héctor chairs, Valentina/Rodrigo/Yoshi): `synapse-v3/ashley_v3_*probe*.json`, `ashley_recall_*`, `docs/experiments/2026-06-ashley-*.md`.
- **C4b. Narrow 14-turn matrix + bakeoff**: `synapse-cortex/evals/narrow_contract_cases.json`, `results/narrow_model_bakeoff.json` (4 clean MATCH before 402 stall; rerun pending credits).
- **C4c. Reconciliation trio (hard-code first)**: Mati (old state → later evidence → revised), meeting (scheduled → outcome → follow-up), Ashley-ambiguity (strong claim → contradictory evidence → confidence revision without false closure). Sources: C1–C4a transcripts. Status: TO-BUILD from existing material.

## C5. Morning / re-entry (progressive disclosure)

- **C5a. Turn-1/2/3+ injection + resume/handshake fixtures**: `test-starter/fixtures/prompt-playback.json` + `outputs/prompt-playback-*.json` (~40 runs), `fixtures/vnext-turn-replay/*.json` (5), brief-day set `fixtures/brief-day/*.json` (8).

## Run protocol (per item)

`frozen-input → old/current/changed → Gemini sheet + human read → ledger entry`.
Keep raw outputs under `reports/` (RPD2 convention: reports are dirty, never commit blindly — check repo rules). No new eval infra this blitz beyond a runner that emits standard folders (Agnes candidate).
