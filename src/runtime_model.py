"""Agenda ranker adapter: a minimal generate_structured over the OpenRouter
chat-completions API, reusing the extractor's key/model configuration. Fails
closed (returns None-shaped errors) so the agenda falls back deterministically."""

from __future__ import annotations

import json
import os
import sys

import httpx


import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------------------------------------------------------------
# Budgets for every model call Cortex makes through this adapter. Reasoning tokens bill as output, and an unset effort lets a reasoning model think as long as it likes
# (the Luna Pro runaway: ~46k billed tokens for an ~8k prompt). So every call gets (1) a reasoning effort chosen for its job, (2) a hard output ceiling, (3) usage logged with
# reasoning tokens and cost, and (4) a daily dollar circuit-breaker per module that fails OPEN to the caller's existing retry-at-the-next-boundary behaviour.
REASONING_EFFORT = {                       # per calling module; override with LLM_REASONING_EFFORT_<MODULE>
    "world_interpreter": "low", "scene_narrative": "none", "executive": "low", "current_meaning_service": "none",
    "semantic_judge": "none", "turn_interpretation": "none", "default": "low",
}
# THE PRODUCT'S COST CONTRACT: background cognition costs a person less than $1 on a heavy day and a few dollars a month on a normal one. The ceiling is per PERSON (all their worlds,
# all modules): above it Cortex's optional work stops until 00:00 UTC and callers fail open to the next boundary. (On 9 Oct one dogfooding user cost ~$3.3 because the interpreter ran
# after nearly every turn; the cadence was fixed at the source and this is the guarantee that a trigger bug can never do that again.)
PERSON_DAILY_BUDGET_USD = float(os.getenv("LLM_DAILY_BUDGET_PER_PERSON_USD", "0.80"))
DAILY_BUDGET_USD = {                       # per module per UTC day across EVERYONE: a runaway breaker only (it was $3 total, which would have stopped the whole product at ~4 users)
    "world_interpreter": 40.00, "scene_narrative": 15.00, "executive": 15.00, "current_meaning_service": 5.00, "semantic_judge": 5.00, "default": 5.00,
}
HARD_MAX_OUTPUT_TOKENS = int(os.getenv("LLM_HARD_MAX_OUTPUT_TOKENS", "12000"))
_spent: dict = {}


class BudgetExceeded(RuntimeError):
    pass


def _policy(table: dict, prefix: str, module: str):
    env = os.getenv(f"{prefix}_{module.upper()}")
    if env:
        return env
    return table.get(module, table["default"])


def _day() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def spent_today() -> dict:
    """Dollars spent per module today (this process): for the ops digest."""
    return {m: round(v, 4) for (d, m), v in _spent.items() if d == _day()}


class AgendaRankerAdapter:
    """Async structured-output adapter for the cheap agenda ranking model."""

    async def generate_structured(self, *, system: str, prompt: str, json_schema: dict,
                                  model_id: str, max_tokens: int = 900,
                                  temperature: float = 0.2, strict: bool = True, timeout: float | None = None, **_: object):
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        url = ("https://openrouter.ai/api/v1/chat/completions"
               if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY")
               else os.getenv("SYNAPSE_MODEL_URL") or "https://api.openai.com/v1/chat/completions")
        module = "unknown"
        try:
            module = str(sys._getframe(1).f_globals.get("__name__", "unknown")).rsplit(".", 1)[-1]
        except Exception:
            pass
        budget = float(_policy(DAILY_BUDGET_USD, "LLM_DAILY_BUDGET_USD", module))
        from src import call_context as _cc
        person = _cc.person_of(_cc.current().get("world_owner"))
        if person and PERSON_DAILY_BUDGET_USD > 0 and await _cc.person_spent_today(person) >= PERSON_DAILY_BUDGET_USD:
            logger.error("llm_person_budget_exceeded person=%s module=%s ceiling_usd=%.2f: refused until 00:00 UTC (callers fail open)", person, module, PERSON_DAILY_BUDGET_USD)
            raise BudgetExceeded(f"daily per-person budget exhausted ({module})")
        if _spent.get((_day(), module), 0.0) >= budget:
            logger.error("llm_budget_exceeded module=%s budget_usd=%.2f: call refused until tomorrow (callers fail open)", module, budget)
            raise BudgetExceeded(f"daily budget for {module} exhausted")
        headers = {"Content-Type": "application/json"}
        try:      # the module that asked: sent as X-Title so the usage log says what each call was for
            headers.update({"HTTP-Referer": "https://localhost/synapse-cortex", "X-Title": "synapse-cortex:" + str(sys._getframe(1).f_globals.get("__name__", "unknown")).rsplit(".", 1)[-1]})
        except Exception:
            pass
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        payload = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": (
                    f"{prompt}\n\nRespond with ONLY a JSON object of the shape:\n"
                    f"{json.dumps(json_schema)}"
                )},
            ],
            "max_tokens": min(int(max_tokens), HARD_MAX_OUTPUT_TOKENS),
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        if "openrouter.ai" in url:
            payload["usage"] = {"include": True}               # the response then carries its own cost (the breaker and the call ledger use it)
        if str(model_id).startswith("openai/gpt-5"):         # reasoning models: pick the effort for this job instead of letting the model decide how long to think
            payload["reasoning"] = {"effort": _policy(REASONING_EFFORT, "LLM_REASONING_EFFORT", module), "exclude": True}
        async with httpx.AsyncClient(timeout=timeout or float(os.getenv("AGENDA_RANKER_TIMEOUT_SECONDS", "12"))) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            body = resp.json()
            self.last_usage = body.get("usage")
            usage = self.last_usage or {}
            cost = usage.get("cost")
            if cost is None:      # no cost reported: assume a pessimistic $2/M tokens so the breaker still works
                cost = (int(usage.get("prompt_tokens") or 0) + int(usage.get("completion_tokens") or 0)) * 2e-6
            _spent[(_day(), module)] = _spent.get((_day(), module), 0.0) + float(cost)
            logger.info("llm_usage module=%s model=%s in=%s out=%s reasoning=%s cost_usd=%.5f day_total_usd=%.3f", module, model_id, usage.get("prompt_tokens"),
                        usage.get("completion_tokens"), (usage.get("completion_tokens_details") or {}).get("reasoning_tokens"), float(cost), _spent[(_day(), module)])
            from src import call_context
            call_context.record(module=module, provider="openrouter", model=model_id, usage=usage, cost=float(cost))
            content = body["choices"][0]["message"]["content"] or "{}"
            parsed = json.loads(content)
            if not isinstance(parsed, dict):
                raise ValueError("agenda ranker returned non-object")
            return parsed


_adapter_singleton: AgendaRankerAdapter | None = None


def get_agenda_adapter() -> AgendaRankerAdapter | None:
    """None when no model credentials exist: agenda runs on deterministic
    fallback only (correct degradation, never silence)."""
    global _adapter_singleton
    if not (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY")):
        return None
    if _adapter_singleton is None:
        _adapter_singleton = AgendaRankerAdapter()
    return _adapter_singleton
