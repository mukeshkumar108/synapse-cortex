"""Who caused this model call (Cortex's half of the substrate-wide call ledger).

The Runtime sends the identity of the turn it is serving in an `X-Call-Context` header; a small middleware binds it for the request, background tasks started from the request
inherit it, and every model call Cortex makes records it (module, model, tokens, cost, status) into `model_calls`. Work Cortex starts on its own (the executive's self-scheduled
review, the Heart) carries no request context and is recorded with trigger `self_scheduled`. Best-effort: recording never raises into the work it describes."""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
CTX: "contextvars.ContextVar[Optional[Dict[str, Any]]]" = contextvars.ContextVar("cortex_call_context", default=None)
_FIELDS = ("product", "world_owner", "conversation_id", "turn_id", "medium", "mode", "trigger", "traffic")
_ready = False
_pending: "set[asyncio.Task]" = set()


def parse_header(value: Optional[str]) -> Dict[str, Any]:
    try:
        data = json.loads(value or "{}")
        return {k: str(data[k])[:120] for k in _FIELDS if k in data and data[k] is not None} if isinstance(data, dict) else {}
    except ValueError:
        return {}


def current() -> Dict[str, Any]:
    return dict(CTX.get() or {})


async def _write(row: Dict[str, Any]) -> None:
    global _ready
    try:
        from sqlalchemy import text
        from src.db import engine
        async with engine.begin() as conn:
            if not _ready:
                await conn.execute(text("""CREATE TABLE IF NOT EXISTS model_calls (
                    id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), product text, world_owner text, conversation_id text, turn_id text, medium text, traffic text,
                    module text, mode text, trigger text, provider text, model text, status text, tokens_in integer, tokens_out integer, tokens_reasoning integer, cost_usd double precision)"""))
                await conn.execute(text("CREATE INDEX IF NOT EXISTS model_calls_at ON model_calls (at DESC)"))
                _ready = True
            cols = list(row)
            await conn.execute(text(f"INSERT INTO model_calls ({', '.join(cols)}) VALUES ({', '.join(':' + c for c in cols)})"), row)
    except Exception as exc:
        logger.debug("model_calls write failed: %s", type(exc).__name__)


def record(*, module: str, provider: str, model: str, usage: Optional[Dict[str, Any]] = None, cost: Optional[float] = None, status: str = "ok") -> None:
    try:
        usage = usage or {}
        ctx = current()
        row: Dict[str, Any] = {k: ctx.get(k) for k in _FIELDS}
        row["trigger"] = ctx.get("trigger") or ("request" if ctx else "self_scheduled")
        row["mode"] = ctx.get("mode") or ("blocking" if ctx else "async")
        row.update(module=module, provider=provider, model=model, status=status, tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"),
                   tokens_reasoning=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"), cost_usd=cost)
        task = asyncio.get_running_loop().create_task(_write(row))
        _pending.add(task)
        task.add_done_callback(_pending.discard)
    except Exception as exc:
        logger.debug("model_call record failed: %s", type(exc).__name__)


def person_of(world_owner: Optional[str]) -> Optional[str]:
    """The human behind an owner key: `user_<id>` (a person-scoped world) or `world:rpd2:<id>:<character>:<chat>` (a per-chat story world). Cost is a property of the PERSON,
    not of a chat: ten chats are still one user's bill."""
    owner = str(world_owner or "")
    if owner.startswith("world:"):
        parts = owner.split(":")
        return parts[2] if len(parts) > 2 and parts[2] else owner
    if owner.startswith("user_"):
        return owner[5:]
    return owner or None


_spend_cache: Dict[str, Any] = {}


async def person_spent_today(person: str, *, ttl: float = 20.0) -> float:
    """Dollars of recorded model spend for this person since 00:00 UTC (all their worlds). Cached briefly: it is consulted before every model call. Unknown (no database) -> 0."""
    import time
    hit = _spend_cache.get(person)
    if hit and time.monotonic() - hit[0] < ttl:
        return hit[1]
    try:
        from sqlalchemy import text
        from src.db import engine
        async with engine.begin() as conn:
            row = (await conn.execute(text(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM model_calls WHERE at >= date_trunc('day', now() AT TIME ZONE 'utc') AT TIME ZONE 'utc' "
                "AND (world_owner = :u OR world_owner LIKE :w)"), {"u": f"user_{person}", "w": f"world:%:{person}:%"})).first()
        value = float(row[0] or 0.0)
    except Exception as exc:
        logger.debug("person spend lookup failed: %s", type(exc).__name__)
        value = hit[1] if hit else 0.0
    _spend_cache[person] = (time.monotonic(), value)
    return value
