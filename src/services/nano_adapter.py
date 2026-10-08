"""NanoGPT as a background reasoning provider.

NanoGPT is a flat-rate subscription, so it is the right home for slow, asynchronous reflection that never blocks a reply (character self-direction, story
pressure). It is OpenAI-compatible. Calls fail sometimes, so: a fallback chain of models, bounded retries with backoff, tolerant JSON extraction, and
NEVER an exception that escapes to a caller on the hot path (callers run in background tasks and treat `None` as "try again at the next boundary")."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Sequence

import httpx

logger = logging.getLogger(__name__)

BASE_URL = os.getenv("NANO_BASE_URL", "https://nano-gpt.com/api/v1")
# Ordered by how well each follows a strict JSON contract at this size (measured in the lab); every one is covered by the subscription.
DEFAULT_CHAIN = [m.strip() for m in os.getenv("AGENCY_MODELS", "z-ai/glm-5.3-flash,meta/muse-spark-1.3-contributor,openrouter:z-ai/glm-5.3-flash,openrouter:openai/gpt-5.6-luna,deepseek/deepseek-v4-flash").split(",") if m.strip()]
ATTEMPTS_PER_MODEL = int(os.getenv("AGENCY_ATTEMPTS_PER_MODEL", "2"))
TIMEOUT = float(os.getenv("AGENCY_TIMEOUT_SECONDS", "150"))
HARD_MAX_OUTPUT_TOKENS = int(os.getenv("AGENCY_HARD_MAX_OUTPUT_TOKENS", "4000"))
DAILY_OUTPUT_TOKEN_BUDGET = int(os.getenv("AGENCY_DAILY_OUTPUT_TOKEN_BUDGET", "600000"))     # flat-rate still has fair use, and a runaway loop would only waste it
_usage = {"day": "", "out": 0, "calls": 0, "failures": 0, "by_model": {}}


def usage_today() -> dict:
    from datetime import datetime, timezone
    return dict(_usage) if _usage["day"] == datetime.now(timezone.utc).strftime("%Y-%m-%d") else {"day": "", "out": 0, "calls": 0, "failures": 0, "by_model": {}}


def _roll() -> None:
    from datetime import datetime, timezone
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if _usage["day"] != today:
        _usage.update({"day": today, "out": 0, "calls": 0, "failures": 0, "by_model": {}})


def configured() -> bool:
    return bool(os.getenv("NANO_API_KEY", "").strip())


def extract_json(text: str) -> Optional[Dict[str, Any]]:
    """The first JSON object in a model's text, tolerating code fences, prose around it, and reasoning preambles."""
    if not text:
        return None
    cleaned = re.sub(r"<think>.*?</think>", "", text, flags=re.S).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.S).strip()
    try:
        value = json.loads(cleaned)
        return value if isinstance(value, dict) else None
    except ValueError:
        pass
    start = cleaned.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(cleaned)):
            ch = cleaned[i]
            if in_str:
                esc = (ch == "\\" and not esc)
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        value = json.loads(cleaned[start:i + 1])
                        if isinstance(value, dict):
                            return value
                    except ValueError:
                        break
                    break
        start = cleaned.find("{", start + 1)
    return None


async def generate_json(*, system: str, prompt: str, models: Optional[Sequence[str]] = None, max_tokens: int = 3000, temperature: float = 0.7,
                        title: str = "agency") -> Optional[Dict[str, Any]]:
    """Walk the chain until one model returns a JSON object. Returns None when everything failed (the caller leaves the state as it was)."""
    nano_key = os.getenv("NANO_API_KEY", "").strip()
    or_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not nano_key and not or_key:
        return None
    _roll()
    if _usage["out"] >= DAILY_OUTPUT_TOKEN_BUDGET:
        logger.error("%s: daily output-token budget exhausted (%d): skipping until tomorrow", title, _usage["out"])
        return None
    chain: List[str] = list(models or DEFAULT_CHAIN)
    for entry in chain:
        via_or = entry.startswith("openrouter:")
        model = entry.split(":", 1)[1] if via_or else entry
        key, base = (or_key, "https://openrouter.ai/api/v1") if via_or else (nano_key, BASE_URL)
        if not key:
            continue
        for attempt in range(ATTEMPTS_PER_MODEL):
            truncated = False
            try:
                body_req: Dict[str, Any] = {"model": model, "max_tokens": min(max_tokens, HARD_MAX_OUTPUT_TOKENS), "temperature": temperature,
                                            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]}
                if via_or and model.startswith("openai/gpt-5"):
                    body_req["reasoning"] = {"effort": "low", "exclude": True}          # a budgeted fallback, never an open-ended thinker
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body_req)
                    resp.raise_for_status()
                    body = resp.json()
                    content = (body["choices"][0]["message"].get("content")) or ""
                    truncated = body["choices"][0].get("finish_reason") == "length"
                    used = (body.get("usage") or {})
                    _usage["calls"] += 1
                    _usage["out"] += int(used.get("completion_tokens") or 0)
                    if via_or:
                        _usage["fallback_calls"] = _usage.get("fallback_calls", 0) + 1
                    _usage["by_model"][entry] = _usage["by_model"].get(entry, 0) + 1
                    from src import call_context
                    call_context.record(module=title, provider="openrouter" if via_or else "nanogpt", model=model, usage=used)
                    logger.info("llm_usage module=%s provider=%s model=%s in=%s out=%s day_out=%d", title, "openrouter" if via_or else "nanogpt", model,
                                used.get("prompt_tokens"), used.get("completion_tokens"), _usage["out"])
                parsed = extract_json(content)
                if parsed is not None:
                    parsed["_model"] = entry
                    return parsed
                logger.warning("%s: %s returned no JSON object (attempt %d)%s", title, entry, attempt + 1, " [truncated at the output ceiling]" if truncated else "")
                if truncated:
                    break          # the same prompt hits the same ceiling again: spend the next attempt on the next model, not on another 3 000 wasted tokens
            except Exception as exc:
                _usage["failures"] += 1
                logger.warning("%s: %s failed (attempt %d): %s", title, entry, attempt + 1, type(exc).__name__)
            await asyncio.sleep(min(2.0 * (attempt + 1), 6.0))
    return None
