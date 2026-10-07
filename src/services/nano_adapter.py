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
DEFAULT_CHAIN = [m.strip() for m in os.getenv("AGENCY_MODELS", "z-ai/glm-5.3-flash,meta/muse-spark-1.3-contributor,deepseek/deepseek-v4-flash").split(",") if m.strip()]
ATTEMPTS_PER_MODEL = int(os.getenv("AGENCY_ATTEMPTS_PER_MODEL", "2"))
TIMEOUT = float(os.getenv("AGENCY_TIMEOUT_SECONDS", "150"))


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
    key = os.getenv("NANO_API_KEY", "").strip()
    if not key:
        return None
    chain: List[str] = list(models or DEFAULT_CHAIN)
    for model in chain:
        for attempt in range(ATTEMPTS_PER_MODEL):
            try:
                async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                    resp = await client.post(
                        f"{BASE_URL}/chat/completions",
                        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                        json={"model": model, "max_tokens": max_tokens, "temperature": temperature,
                              "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]})
                    resp.raise_for_status()
                    content = (resp.json()["choices"][0]["message"].get("content")) or ""
                parsed = extract_json(content)
                if parsed is not None:
                    parsed["_model"] = model
                    return parsed
                logger.warning("%s: %s returned no JSON object (attempt %d)", title, model, attempt + 1)
            except Exception as exc:
                logger.warning("%s: %s failed (attempt %d): %s", title, model, attempt + 1, type(exc).__name__)
            await asyncio.sleep(min(2.0 * (attempt + 1), 6.0))
    return None
