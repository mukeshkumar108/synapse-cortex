# BOUNDED PROBLEM — Honcho deriver RateLimitError blocks Lane 2 sweeps

## Symptom
- Lane 2 sweeper (`/v1/cortex/sweeper/run`) returns `evidence_packets: 0` even
  though messages were just written to Honcho and 10-minute retry window was used.
- Root cause of empty evidence: `docker logs honcho-deriver` shows repeated
  `tenacity.RetryError ... raised RateLimitError` from `src/llm/api.py honcho_llm_call`.
  The deriver cannot run its LLM calls (representation/embedding derivation),
  so `peer_search` finds no derived documents for new messages.
- When the deriver IS healthy, the full acceptance loop PASSES end-to-end
  (proven: background_tick_proactive_followup passed in run matrixA at ~14:05;
  the unrelated_reentry fixture passed its sweep + promotion, agenda item
  "Daily 10,000 steps goal (10000 steps)" reached OWED — see
  /app/evals2/results/unrelated_reentry_with_outstanding_morning_objective_53a24940.json).

## Where
- VPS 161.97.150.246, container honcho-deriver (up 3 weeks).
- Honcho deploy: ~/honcho with .env containing the deriver's LLM credentials.
- Error: RateLimitError (OpenRouter/LLM provider) retried via tenacity, ultimately dropped.

## What we think is wrong
- The honcho .env LLM key is a different/limited account from the cortex one
  (which we just topped up), and it is rate-limited/out of credits.
- Possibly heavy per-message derive load (representation + dialects on every
  message) burns the quota faster than expected.

## Desired outcome
1. Confirm which provider/key honcho-deriver uses and its quota state.
2. Fix the quota (top up / rotate key / switch deriver LLM to a cheaper model
   via honcho config.toml or env).
3. Verify: seed a message, wait <2 min, `peer_search` returns the derived doc.
4. Then rerun: `python3 scenario_runner.py scenarios/background_tick_proactive_followup.json
   scenarios/unrelated_reentry_with_outstanding_morning_objective.json --base http://localhost:8010`
   (inside synapse-cortex container, /app/evals2, with SYNAPSE_CORTEX_API_TOKEN
   and HONCHO_API_KEY env) — both should PASS.

## Fallback if quota cannot be fixed quickly
- The sweeper's evidence layer can fall back to `conclusions/list` +
  workspace-level search over ALREADY-derived history (all 3,396 existing docs
  are embedded and searchable). Only NEW messages' derivation is blocked.
  This still unblocks historical sweeps (e.g. Sophie promises from Aug 23) but
  not "minutes-fresh" findings.
