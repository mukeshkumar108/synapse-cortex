"""LLM_NANO_ONLY: the flat-rate NanoGPT subscription is the only provider. The requested model gets 3 attempts, then other
subscription models take over (2 attempts each), and OpenRouter is never called. Without the flag nothing changes."""
import pytest

from src import runtime_model as rm


class _Resp:
    def __init__(self, content='{"ok": true}', finish="stop"):
        self._c, self._f = content, finish

    def raise_for_status(self):
        pass

    def json(self):
        return {"choices": [{"message": {"content": self._c}, "finish_reason": self._f}], "usage": {"prompt_tokens": 5, "completion_tokens": 7}}


def _client(plan):
    """plan: callable(url, model, n) -> _Resp or an Exception to raise; records every call."""
    calls = []

    class C:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, headers=None, json=None):
            n = sum(1 for c in calls if c[1] == json["model"])
            calls.append((url, json["model"]))
            out = plan(url, json["model"], n)
            if isinstance(out, Exception):
                raise out
            return out

    return C, calls


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("NANO_API_KEY", "n")
    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.setenv("LLM_NANO_ONLY", "1")
    monkeypatch.delenv("LLM_NANO_FALLBACKS", raising=False)
    rm._spent.clear()

    async def no_sleep(_):
        pass

    monkeypatch.setattr(rm.asyncio, "sleep", no_sleep)


async def _run(monkeypatch, plan, model="moonshotai/kimi-k2.6"):
    C, calls = _client(plan)
    monkeypatch.setattr(rm.httpx, "AsyncClient", C)
    result = None
    err = None
    try:
        result = await rm.AgendaRankerAdapter().generate_structured(system="s", prompt="p", json_schema={}, model_id=model)
    except Exception as exc:
        err = exc
    return result, err, calls


@pytest.mark.asyncio
async def test_retries_the_requested_model_before_moving_on(monkeypatch):
    result, err, calls = await _run(monkeypatch, lambda u, m, n: RuntimeError("down") if n < 2 else _Resp())
    assert result == {"ok": True} and err is None
    assert [m for _, m in calls] == ["moonshotai/kimi-k2.6"] * 3                  # two failures, third attempt succeeds
    assert all(u.startswith("https://nano-gpt.com") for u, _ in calls)


@pytest.mark.asyncio
async def test_falls_to_other_subscription_models_after_three_attempts(monkeypatch):
    result, err, calls = await _run(monkeypatch, lambda u, m, n: RuntimeError("down") if m == "moonshotai/kimi-k2.6" else _Resp())
    assert result == {"ok": True}
    models = [m for _, m in calls]
    assert models[:3] == ["moonshotai/kimi-k2.6"] * 3
    assert models[3] != "moonshotai/kimi-k2.6" and len(calls) == 4
    assert all("openrouter" not in u for u, _ in calls)


@pytest.mark.asyncio
async def test_exhausting_everything_raises_and_still_never_calls_openrouter(monkeypatch):
    result, err, calls = await _run(monkeypatch, lambda u, m, n: RuntimeError("all down"))
    assert result is None and isinstance(err, RuntimeError)
    assert len(calls) == 3 + 2 * rm.NANO_FALLBACK_MODELS                          # 3 on the requested model, then 2 on each of the others
    assert len({m for _, m in calls}) >= 3                                          # the requested model plus at least two others
    assert all(u.startswith("https://nano-gpt.com") for u, _ in calls)


@pytest.mark.asyncio
async def test_a_model_outside_the_subscription_is_substituted_not_sent_to_openrouter(monkeypatch):
    result, err, calls = await _run(monkeypatch, lambda u, m, n: _Resp(), model="openai/gpt-5.6-luna")
    assert result == {"ok": True}
    assert len(calls) == 1 and calls[0][1] != "openai/gpt-5.6-luna" and calls[0][0].startswith("https://nano-gpt.com")


@pytest.mark.asyncio
async def test_truncation_moves_to_the_next_model_instead_of_repeating(monkeypatch):
    result, err, calls = await _run(monkeypatch, lambda u, m, n: _Resp('{"a":', "length") if m == "moonshotai/kimi-k2.6" else _Resp())
    assert result == {"ok": True}
    assert [m for _, m in calls].count("moonshotai/kimi-k2.6") == 1


@pytest.mark.asyncio
async def test_a_spent_budget_is_not_retried(monkeypatch):
    monkeypatch.setenv("LLM_DAILY_BUDGET_USD_TEST_LLM_NANO_ONLY", "0.0001")
    rm._spent[(rm._day(), "test_llm_nano_only")] = 1.0
    result, err, calls = await _run(monkeypatch, lambda u, m, n: _Resp())
    assert isinstance(err, rm.BudgetExceeded) and calls == []


@pytest.mark.asyncio
async def test_without_the_flag_behaviour_is_unchanged(monkeypatch):
    monkeypatch.delenv("LLM_NANO_ONLY")
    result, err, calls = await _run(monkeypatch, lambda u, m, n: RuntimeError("down"), model="openai/gpt-5.6-luna")
    assert isinstance(err, RuntimeError) and len(calls) == 1                         # one attempt, the old route (OpenRouter), no fallback
    assert calls[0][0].startswith("https://openrouter.ai") and calls[0][1] == "openai/gpt-5.6-luna"


@pytest.mark.asyncio
async def test_agency_chain_skips_openrouter_entries_when_nano_only(monkeypatch):
    from src.services import nano_adapter

    calls = []

    class C(_client(lambda *a: None)[0]):
        async def post(self, url, headers=None, json=None):
            calls.append((url, json.get("model")))
            if "nano-gpt.com" in url:
                raise RuntimeError("down")
            return _Resp()

    monkeypatch.setattr(nano_adapter.httpx, "AsyncClient", C)
    monkeypatch.setattr(nano_adapter, "ATTEMPTS_PER_MODEL", 1)

    async def no_sleep(_):
        pass

    monkeypatch.setattr(nano_adapter.asyncio, "sleep", no_sleep)
    out = await nano_adapter.generate_json(system="s", prompt="p", models=["z-ai/glm-5.3-flash", "openrouter:openai/gpt-5.6-luna"], title="t")
    assert out is None                                           # nothing succeeded, and the OpenRouter entry was never tried
    assert all(u.startswith("https://nano-gpt.com") for u, _ in calls)


def test_turn_extractor_uses_nanogpt_when_nano_only(monkeypatch):
    from src.services.turn_extractor import LLMExtractorProvider

    monkeypatch.setenv("OPENROUTER_API_KEY", "o")
    monkeypatch.delenv("SYNAPSE_MODEL_URL", raising=False)
    p = LLMExtractorProvider(model="deepseek/deepseek-v4-flash")
    assert p.api_url == "https://nano-gpt.com/api/v1/chat/completions" and p.api_key == "n"
    monkeypatch.delenv("LLM_NANO_ONLY")
    assert LLMExtractorProvider(model="deepseek/deepseek-v4-flash").api_url.startswith("https://openrouter.ai")


@pytest.mark.asyncio
async def test_the_chain_stops_after_its_time_budget(monkeypatch):
    clock = {"t": 0.0}

    class _Time:                                              # only this module sees the fake clock, not the event loop
        monotonic = staticmethod(lambda: clock["t"])

    monkeypatch.setattr(rm, "time", _Time)
    monkeypatch.setattr(rm, "NANO_TOTAL_BUDGET_S", 50.0)

    def plan(u, m, n):
        clock["t"] += 30.0                                   # every attempt burns 30 s (a hung provider)
        return RuntimeError("timeout")

    result, err, calls = await _run(monkeypatch, plan)
    assert isinstance(err, RuntimeError) and len(calls) == 2  # after two 30 s attempts it is over budget, so the third never starts


def test_empty_environment_values_mean_use_the_defaults(monkeypatch):
    # docker compose passes `${VAR:-}` through as an empty string; that must not be read as "no models"
    monkeypatch.setenv("LLM_NANO_FALLBACKS", "")
    monkeypatch.setenv("NANOGPT_MODELS", "")
    covered = rm._nano_model_set()
    assert "qwen/qwen3.8-27b" in covered
    chain = rm._nano_chain("openai/gpt-5.6-luna", covered)
    assert len(chain) >= 3 and "openai/gpt-5.6-luna" not in chain
    chain = rm._nano_chain("moonshotai/kimi-k2.6", covered)
    assert chain[0] == "moonshotai/kimi-k2.6" and len(chain) >= 3
