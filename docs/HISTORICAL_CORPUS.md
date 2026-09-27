# Historical corpus manifest (regression evidence — read-only)

> Do NOT commit private raw transcripts or database dumps into git.
> `*.db` and `replay-private/` are gitignored — verified, nothing tracked.

## Sources (external, live — never copied into git)

| Source | Access | Range | Sensitivity |
|---|---|---|---|
| Sophie history (test-starter Postgres) | `../test-starter/.env` (`DATABASE_URL`) via `scripts/historical_replay.py export --source sophie` | Apr 28–30 windows + session corpora | Real user conversations — private |
| RPD2 history (BK Postgres) | `../rpd2/.env.local` (`BK_POSTGRES_URL`) via `export --source rpd2` | Elena `8ae17baf` chat + scenes | Real roleplay transcripts — private |

## Frozen local artefacts (`replay-private/`, gitignored, do not delete)

- `sophie-apr28-30.json` (+ `.sqlite`, `-report.json`, first-pass/retry variants) — export + replay DBs + reports.
- `rpd2-elena-8ae17baf.json` (+ `.sqlite`, reports incl. `after-9788032` reruns).
- `v2-check / v2-final / v2-retry / v2-partial / v2-fault / v2-sophie` report+sqlite pairs — consolidation verification runs.
- `sophie-one.json` — single-case export.
- `sophie-apr28-30.failed.sqlite` (0 bytes) — failed-run marker, keep as evidence of the failure path.

Newer runs never overwrite older artefacts — history of failure evidence is useful.

## Committed fixtures (safe, synthetic or redacted)

- `evals/sophie_longitudinal/` — inputs, oracles, manifest, runner, blind packets + sealed mappings.
- `evals/scenarios/`, `evals/fixtures.json`, `evals/session_consolidation_panel/`.
- `evals/rpd2_elena_replay.py` + `docs/` replay notes.

## Replay cases depend on

`sophie-apr28-30.json` and `rpd2-elena-8ae17baf.json` as inputs;
per-run `.sqlite` files as isolated targets (runner refuses to overwrite);
`*-report.json` as assertions/oracles for later runs.

## Backup status

- 2026-09-27 full database backups (pg_dump custom format, restorable):
  `replay-private/backups/test-starter.20260927.dump` (13 tables incl.
  Message/Memory/Session) and `replay-private/backups/rpd2-bk.20260927.dump`
  (21 tables) — taken directly from the live source DBs, verified via
  `pg_restore --list`. Plus local dev copies
  (`synapse_cortex.db.20260927`, near-empty — 1 expectation row;
  `test_rem.db.20260927`, empty).
- The "no local snapshot" flag is now CLEARED for these two sources as of
  2026-09-27. Re-take after any major product-data milestone; dumps are cheap.
- Current dev DB needs no backup for this release: migration 0031 is purely
  additive (new table + indexes, no data reinterpretation). Production deploy
  should still snapshot before migrating, per normal practice.
