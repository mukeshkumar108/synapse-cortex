"""One tool-capable chat call, shared by agents that need it (the connect pass). Same provider routing and error
behaviour as the maintenance agent: `openrouter:`-prefixed models go to OpenRouter, everything else to NanoGPT;
failures return None; `finish_reason` is surfaced so truncated tool calls are never executed as if complete.

(The maintenance and attention agents still carry their own copies of this call. Consolidating them is deliberate
future work, not done here, to avoid touching reliability-tuned code: see docs/IMPLEMENTATION_STATUS.md.)
"""
from __future__ import annotations

import logging
import os
import time
from typing import Any, Callable, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

CALL_TIMEOUT_S = float(os.getenv("AGENT_TIMEOUT_S", "90"))


async def chat(model: str, messages: List[Dict[str, Any]], tools: List[Dict[str, Any]], *, max_tokens: int, module: str,
               injected: Optional[Callable[..., Any]] = None) -> Optional[Dict[str, Any]]:
    if injected is not None:
        out = injected(model, messages)
        if hasattr(out, "__await__"):
            out = await out
        return out
    via_or = model.startswith("openrouter:")
    mid = model.split(":", 1)[1] if via_or else model
    key = (os.getenv("OPENROUTER_API_KEY", "") if via_or else os.getenv("NANO_API_KEY", "")).strip()
    base = "https://openrouter.ai/api/v1" if via_or else os.getenv("NANO_BASE_URL", "https://nano-gpt.com/api/v1").rstrip("/")
    if not key:
        return None
    t0 = time.monotonic()
    try:
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        if via_or:
            headers["X-Title"] = f"cortex-{module}"
        async with httpx.AsyncClient(timeout=CALL_TIMEOUT_S) as client:
            resp = await client.post(base + "/chat/completions", headers=headers,
                                     json={"model": mid, "messages": messages, "tools": tools, "tool_choice": "auto", "max_tokens": max_tokens})
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            msg = choice["message"]
            used = data.get("usage") or {}
            logger.info("llm_usage module=%s provider=%s model=%s in=%s out=%s ms=%d", module, "openrouter" if via_or else "nanogpt", mid,
                        used.get("prompt_tokens"), used.get("completion_tokens"), int((time.monotonic() - t0) * 1000))
            return {"content": msg.get("content") or "", "tool_calls": msg.get("tool_calls") or [], "finish_reason": choice.get("finish_reason"),
                    "model": model, "provider": "openrouter" if via_or else "nanogpt", "usage": used}
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", None)
        logger.warning("%s chat failed (%s): %s%s", module, model, type(exc).__name__, f" HTTP {status}" if status else "")
        return None
