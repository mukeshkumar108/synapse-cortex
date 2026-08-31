"""Agenda ranker adapter: a minimal generate_structured over the OpenRouter
chat-completions API, reusing the extractor's key/model configuration. Fails
closed (returns None-shaped errors) so the agenda falls back deterministically."""

from __future__ import annotations

import json
import os

import httpx


class AgendaRankerAdapter:
    """Async structured-output adapter for the cheap agenda ranking model."""

    async def generate_structured(self, *, system: str, prompt: str, json_schema: dict,
                                  model_id: str, max_tokens: int = 900,
                                  temperature: float = 0.2, strict: bool = True, **_: object):
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or ""
        url = ("https://openrouter.ai/api/v1/chat/completions"
               if os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY")
               else os.getenv("SYNAPSE_MODEL_URL") or "https://api.openai.com/v1/chat/completions")
        headers = {"Content-Type": "application/json"}
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
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {"type": "json_object"},
        }
        async with httpx.AsyncClient(timeout=float(os.getenv("AGENDA_RANKER_TIMEOUT_SECONDS", "12"))) as client:
            resp = await client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            content = resp.json()["choices"][0]["message"]["content"] or "{}"
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
