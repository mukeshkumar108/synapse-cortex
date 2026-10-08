"""Every model call has a reasoning effort, a hard output ceiling, usage accounting and a daily dollar breaker that fails open."""
import pytest

from src import runtime_model as rm
from src.services import nano_adapter


class _Resp:
    def __init__(self, usage): self._u = usage
    def raise_for_status(self): pass
    def json(self): return {"choices": [{"message": {"content": "{\"ok\": true}"}}], "usage": self._u}


class _Client:
    sent = []
    def __init__(self, *a, **k): pass
    async def __aenter__(self): return self
    async def __aexit__(self, *a): return False
    async def post(self, url, headers=None, json=None):
        _Client.sent.append(json)
        return _Resp(_Client.usage)


@pytest.mark.asyncio
async def test_reasoning_is_budgeted_per_job_the_output_is_capped_and_spend_is_counted(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(rm.httpx, "AsyncClient", _Client)
    rm._spent.clear(); _Client.sent.clear()
    _Client.usage = {"prompt_tokens": 500, "completion_tokens": 100, "cost": 0.01, "completion_tokens_details": {"reasoning_tokens": 0}}
    await rm.AgendaRankerAdapter().generate_structured(system="s", prompt="p", json_schema={"a": 1}, model_id="openai/gpt-5.6-luna", max_tokens=999_999)
    sent = _Client.sent[0]
    assert sent["max_tokens"] == rm.HARD_MAX_OUTPUT_TOKENS                              # a caller can never ask for an unbounded answer
    assert sent["reasoning"] == {"effort": "low", "exclude": True}                      # not left to the model ("unset" thinks as long as it likes)
    await rm.AgendaRankerAdapter().generate_structured(system="s", prompt="p", json_schema={}, model_id="google/gemini-3.1-flash-lite", max_tokens=300)
    assert "reasoning" not in _Client.sent[1]                                           # only sent to reasoning families that take it
    assert sum(rm.spent_today().values()) == pytest.approx(0.02)


@pytest.mark.asyncio
async def test_the_daily_breaker_refuses_further_calls_for_a_module_that_has_spent_its_budget(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k"); monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setattr(rm.httpx, "AsyncClient", _Client)
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD_TEST_LLM_BUDGETS", "0.015")
    rm._spent.clear(); _Client.sent.clear()
    _Client.usage = {"prompt_tokens": 10, "completion_tokens": 10, "cost": 0.01}
    a = rm.AgendaRankerAdapter()
    await a.generate_structured(system="s", prompt="p", json_schema={}, model_id="openai/gpt-5.6-luna")
    await a.generate_structured(system="s", prompt="p", json_schema={}, model_id="openai/gpt-5.6-luna")      # crosses the 0.015 line
    with pytest.raises(rm.BudgetExceeded):
        await a.generate_structured(system="s", prompt="p", json_schema={}, model_id="openai/gpt-5.6-luna")
    assert len(_Client.sent) == 2                                                                              # the third never left the building


def test_nano_pass_is_capped_and_budgeted():
    assert nano_adapter.HARD_MAX_OUTPUT_TOKENS <= 4000 and nano_adapter.DAILY_OUTPUT_TOKEN_BUDGET > 0
    assert nano_adapter.usage_today()["out"] >= 0


@pytest.mark.asyncio
async def test_agency_chain_crosses_providers_and_the_fallback_is_budgeted(monkeypatch):
    calls = []

    class C(_Client):
        async def post(self, url, headers=None, json=None):
            calls.append((url, json.get("model"), json.get("reasoning")))
            if "nano-gpt.com" in url:
                raise RuntimeError("nanogpt is down")
            return _Resp({"prompt_tokens": 5, "completion_tokens": 7})
    monkeypatch.setenv("NANO_API_KEY", "n"); monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setattr(nano_adapter.httpx, "AsyncClient", C)
    monkeypatch.setattr(nano_adapter, "ATTEMPTS_PER_MODEL", 1)

    async def no_sleep(_): pass
    monkeypatch.setattr(nano_adapter.asyncio, "sleep", no_sleep)
    out = await nano_adapter.generate_json(system="s", prompt="p", models=["z-ai/glm-5.3-flash", "openrouter:openai/gpt-5.6-luna"], title="t")
    assert out["_model"] == "openrouter:openai/gpt-5.6-luna" and out["ok"] is True
    assert calls[0][0].startswith("https://nano-gpt.com") and calls[1][0].startswith("https://openrouter.ai")
    assert calls[1][2] == {"effort": "low", "exclude": True}
