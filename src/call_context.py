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
