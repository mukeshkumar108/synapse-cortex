"""Operations digest for the cognition side: what the interpreter and the executive actually did, so fail-open is never silent. Read-only."""
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.db import get_async_session

router = APIRouter(prefix="/v1/ops", tags=["ops"])


def _pct(values, q):
    values = sorted(values)
    return round(values[min(len(values) - 1, int(q * len(values)))], 1) if values else None


@router.get("/digest")
async def digest(hours: int = Query(24, ge=1, le=24 * 14), db: AsyncSession = Depends(get_async_session)) -> Dict[str, Any]:
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).replace(tzinfo=None)
    out: Dict[str, Any] = {"hours": hours}
    runs = (await db.execute(text(
        "select status, started_at, finished_at, detail_json, model, owner_peer_id from producer_runs where created_at > :s and producer = 'world-interpreter' order by created_at desc limit 4000"),
        {"s": since})).all()
    by_status: Dict[str, int] = {}
    durations, errors, models = [], {}, {}
    worlds = set()
    for status, started, finished, detail, model, owner in runs:
        by_status[status] = by_status.get(status, 0) + 1
        models[model] = models.get(model, 0) + 1
        worlds.add(owner)
        if started and finished and status == "applied":
            durations.append((finished - started).total_seconds())
        if status == "failed":
            try:
                err = str(json.loads(detail or "{}").get("error"))[:120]
            except ValueError:
                err = "unparseable"
            errors[err] = errors.get(err, 0) + 1
    out["interpreter"] = {"runs": len(runs), "by_status": by_status, "worlds": len(worlds), "p50_s": _pct(durations, 0.5), "p95_s": _pct(durations, 0.95),
                          "models": models, "failure_reasons": errors}
    wakes = (await db.execute(text(
        "select (consumed_at is not null) c, count(*), min(case when consumed_at is null then due_at end) from executive_wakes where created_at > :s group by 1"), {"s": since})).all()
    overdue = (await db.execute(text("select count(*) from executive_wakes where consumed_at is null and due_at < :t"),
                                {"t": datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=30)})).scalar()
    out["executive"] = {"wakes": {("consumed" if c else "pending"): n for c, n, _ in wakes}, "overdue_unconsumed_over_30min": overdue}
    out["scene"] = {"layers_updated": (await db.execute(text("select count(*) from current_scenes where updated_at > :s"), {"s": since})).scalar(),
                    "briefs_written": (await db.execute(text("select count(*) from continuation_briefs where created_at > :s"), {"s": since})).scalar(),
                    "briefs_with_spent": (await db.execute(text("select count(*) from continuation_briefs where created_at > :s and scene_json like '%\"spent\": [\"%'"), {"s": since})).scalar()}
    # Model spend and background-reasoning health as this process has seen them today: dollars per module on OpenRouter against its daily breaker, and NanoGPT calls /
    # failures / output tokens (watch the failure rate: NanoGPT is flat-rate but flaky, and the chain falls back).
    from src import runtime_model
    from src.services import nano_adapter
    out["llm_spend_today_usd"] = runtime_model.spent_today()
    out["llm_daily_budget_usd"] = runtime_model.DAILY_BUDGET_USD
    out["nanogpt_today"] = nano_adapter.usage_today()
    agency = (await db.execute(text("select producer, status, count(*) from producer_runs where created_at > :s and producer in ('character-heart','story-pressure') group by 1,2"), {"s": since})).all()
    out["agency"] = {f"{p}:{st}": n for p, st, n in agency}
    alerts = []
    nt = out["nanogpt_today"]
    if nt.get("calls", 0) + nt.get("failures", 0) >= 5 and nt.get("failures", 0) / max(1, nt.get("calls", 0) + nt.get("failures", 0)) > 0.3:
        alerts.append(f"NanoGPT failing: {nt['failures']} failures vs {nt['calls']} successes today (the chain is falling back; fallback_calls={nt.get('fallback_calls', 0)})")
    if nt.get("fallback_calls", 0) >= 3:
        alerts.append(f"agency passes served by the OpenRouter fallback {nt['fallback_calls']} times today: NanoGPT is unreliable right now")
    for module, spent in out["llm_spend_today_usd"].items():
        cap = out["llm_daily_budget_usd"].get(module, out["llm_daily_budget_usd"]["default"])
        if spent >= 0.8 * cap:
            alerts.append(f"{module} has spent ${spent:.2f} of its ${cap:.2f} daily model budget")
    failed = sum(n for k, n in out["agency"].items() if k.endswith(":failed"))
    ran = sum(out["agency"].values())
    if ran >= 4 and failed / ran > 0.5:
        alerts.append(f"character agency passes failing: {failed} of {ran} in the window")
    out["alerts"] = alerts
    return out
