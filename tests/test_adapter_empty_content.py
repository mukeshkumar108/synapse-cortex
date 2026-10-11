"""Adapter integrity: empty or truncated model output must fail loudly, never parse
as valid empty data (an applied-empty run silently orphans the evidence)."""
import pytest

from src.runtime_model import AgendaRankerAdapter


class _Resp:
    def __init__(self, body):
        self._body = body

    def raise_for_status(self):
        pass

    def json(self):
        return self._body


class _Client:
    def __init__(self, body):
        self._body = body

    async def __aenter__(self):
        return self

    async def __aexit__(self, * _):
        return False

    async def post(self, url, headers=None, json=None):
        return _Resp(self._body)


def _body(content, finish="stop"):
    return {"choices": [{"message": {"content": content}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def _adapter(monkeypatch, content, finish="stop"):
    import httpx
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: _Client(_body(content, finish)))
    return AgendaRankerAdapter()


@pytest.mark.asyncio
async def test_empty_content_from_reasoning_exhaustion_raises(monkeypatch):
    adapter = _adapter(monkeypatch, "", finish="length")
    with pytest.raises(ValueError, match="empty content"):
        await adapter.generate_structured(system="s", prompt="p", json_schema={}, model_id="m")


@pytest.mark.asyncio
async def test_empty_content_with_stop_raises(monkeypatch):
    adapter = _adapter(monkeypatch, "   ", finish="stop")
    with pytest.raises(ValueError, match="empty content"):
        await adapter.generate_structured(system="s", prompt="p", json_schema={}, model_id="m")


@pytest.mark.asyncio
async def test_truncated_mid_object_raises(monkeypatch):
    adapter = _adapter(monkeypatch, '{"scene": "Kai asked about the trip', finish="length")
    with pytest.raises(ValueError, match="length"):
        await adapter.generate_structured(system="s", prompt="p", json_schema={}, model_id="m")


@pytest.mark.asyncio
async def test_valid_and_fenced_json_still_parse(monkeypatch):
    adapter = _adapter(monkeypatch, '{"scene": "ok"}')
    assert (await adapter.generate_structured(system="s", prompt="p", json_schema={}, model_id="m")) == {"scene": "ok"}
    adapter = _adapter(monkeypatch, '```json\n{"scene": "ok"}\n```')
    assert (await adapter.generate_structured(system="s", prompt="p", json_schema={}, model_id="m")) == {"scene": "ok"}
