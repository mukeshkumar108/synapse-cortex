"""EXPERIMENT (H1): a bounded one-call delta writer for the operational ledger.

Not the default. It runs only when LEDGER_WRITER is `light` or `hybrid`; unset means the maintenance agent, exactly as before.

What changes against the maintenance agent: the model does not loop with tools. It gets the open records, the numbered observations and the
transcript, and replies once with a JSON object of operations. Code applies each operation through the SAME `maintenance_agent._tools` (same argument
checks, evidence rules, time parsing), re-reads the ledger itself, and runs the SAME finish gate (`_check_finish`: accounting for every observation,
touched records, advisories). If the gate returns problems, the model gets ONE repair round with those problems and the current state of the records
it touched. At most two model calls. `hybrid` hands anything that still fails to the maintenance agent.

Models decide meaning; code validates. Nothing here decides what a matter means.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from src.services import maintenance_agent as ma
from src.services import nano_adapter

logger = logging.getLogger(__name__)

MODELS = [m.strip() for m in os.getenv("LEDGER_LIGHT_MODELS", ma.PRIMARY_MODEL).split(",") if m.strip()]
MAX_ROUNDS = int(os.getenv("LEDGER_LIGHT_ROUNDS", "2"))
MAX_TOKENS = int(os.getenv("LEDGER_LIGHT_MAX_TOKENS", "2500"))

FORMAT = """

OUTPUT FORMAT (this overrides every instruction above about calling tools, listing, re-listing or finishing: you cannot call tools here).
The current open records are given to you. Reply with ONE JSON object and nothing else:

{"ops": [{"tool": "create_item", "args": {...}}, {"tool": "update_item", "args": {"key": "...", ...}}],
 "accounting": [{"obs": 1, "treatment": "applied|merged|no_change|skipped", "key": "record key", "note": "why, for no_change or skipped"}],
 "transcript_sweep": "one line: what, if anything, the transcript held that no observation covered, or 'nothing beyond the observations'",
 "summary": "one line"}

Rules for ops: `args` take exactly the fields of the tool described above (create_item: title, kind, detail, timing, expected_date, status, waiting_on,
question_text, confidence, evidence, expected_time, time_basis, time_role, importance, party; update_item: key plus the fields to change). Operations are applied
in order by code. A record you create in this reply cannot be updated in the same reply (you do not know its key yet): put its complete state in create_item.
Every observation O1..On must appear once in `accounting`; `applied` and `merged` need the `key` of an existing record you updated (or, for a record you create, leave
`key` empty and say "created" in `note`). Search the open records before creating: never duplicate a matter that is already tracked."""


def _records_text(rows: List[Dict[str, Any]]) -> str:
    return json.dumps(rows, ensure_ascii=False)[:9000]


def _compose(contract_day: str, opening: Dict[str, Any], observations: str, transcript: str) -> Dict[str, str]:
    system = ma.CONTRACT + contract_day + FORMAT
    user = ("New session observations. Maintain the agenda.\n\nCurrent open records:\n" + _records_text(opening.get("records") or [])
            + "\n\n" + observations
            + (("\n\n--- session transcript (ground truth; quote the person's own words as evidence) ---\n" + transcript[-8000:]) if transcript else ""))
    return {"system": system, "user": user}


async def _apply(db: AsyncSession, workspace_id: str, owner: str, session_id: str, ops: Any, state: ma.RunState,
                 changes: Dict[str, int], created_keys: List[str]) -> List[Dict[str, Any]]:
    """Apply operations in order through the agent's own tool layer. Returns one result per operation."""
    results: List[Dict[str, Any]] = []
    if not isinstance(ops, list):
        return [{"error": "ops must be a list"}]
    for op in ops:
        if not isinstance(op, dict) or str(op.get("tool") or "") not in ("create_item", "update_item") or not isinstance(op.get("args"), dict):
            results.append({"error": "each op must be {tool: create_item|update_item, args: {...}}", "op": str(op)[:120]})
            continue
        name, args = str(op["tool"]), op["args"]
        try:
            res = await ma._tools(db, workspace_id, owner, name, args, session_id=session_id, state=state)
        except Exception as exc:  # noqa: BLE001
            res = {"error": f"{type(exc).__name__}: {str(exc)[:200]}"}
        if isinstance(res, dict) and res.get("ok") is True:
            if name == "create_item":
                changes["created"] += 1
                if res.get("key"):
                    created_keys.append(str(res["key"]))
            elif str(args.get("status") or "") in ma.CLOSING:
                changes["closed"] += 1
            else:
                changes["updated"] += 1
        results.append({"tool": name, "result": ma._trim(res, 400)})
    return results


def _accounting_with_created(raw: Any, created_keys: List[str]) -> Any:
    """The model cannot know the key of a record it creates in the same reply, so an `applied` entry with no key and a note saying it was created is bound,
    in order, to a record this run really created. Code binds only to keys the run produced and never invents one."""
    if not isinstance(raw, list):
        return raw
    pool = list(created_keys)
    out = []
    for e in raw:
        if (isinstance(e, dict) and str(e.get("treatment") or "") in ("applied", "merged") and not str(e.get("key") or "").strip()
                and "creat" in str(e.get("note") or "").lower() and pool):
            e = {**e, "key": pool.pop(0)}
        out.append(e)
    return out


async def run(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str, observations: str, today: str,
              n_observations: int = 0, transcript: str = "", time_zone: str = "UTC", weekday: str = "",
              obs_timing: Optional[Dict[int, str]] = None) -> Dict[str, Any]:
    """Same signature and result shape as `maintenance_agent.run_maintenance`, so the caller treats both alike."""
    started = time.monotonic()
    t_tx = ma._TRANSCRIPT_CTX.set(transcript or "")
    t_day = ma._TODAY_CTX.set(today or "")
    t_tz = ma._TZ_CTX.set(time_zone or "")
    try:
        state = ma.RunState(n_obs=n_observations)
        state.obs_timing = dict(obs_timing or {})
        state.has_transcript = bool(transcript)
        changes = {"created": 0, "updated": 0, "closed": 0}
        calls: List[Dict[str, Any]] = []
        created_keys: List[str] = []
        opening = await ma._tools(db, workspace_id, owner, "list_open", {}, session_id, state)
        day = f"\n\nToday is {weekday} {today} (the person's local date; timezone {time_zone}).".replace("  ", " ")
        prompt = _compose(day, opening, observations, transcript)
        user = prompt["user"]
        problems: List[str] = []
        finished: Optional[str] = None
        gate_passed = False
        for rnd in range(max(1, MAX_ROUNDS)):
            t0 = time.monotonic()
            reply = await nano_adapter.generate_json(system=prompt["system"], prompt=user, models=MODELS, max_tokens=MAX_TOKENS,
                                                     temperature=0.2, title="ledger-light")
            calls.append({"round": rnd + 1, "model": (reply or {}).get("_model"), "ms": int((time.monotonic() - t0) * 1000), "got_json": reply is not None})
            if reply is None:
                problems = ["the model returned no usable JSON"]
                break
            results = await _apply(db, workspace_id, owner, session_id, reply.get("ops") or [], state, changes, created_keys)
            calls[-1]["ops"] = len(reply.get("ops") or [])
            calls[-1]["op_errors"] = [r for r in results if "error" in r or '"error"' in str(r.get("result") or "")]
            # code re-reads the agenda after the last write, which is what the agent's own gate requires
            await ma._tools(db, workspace_id, owner, "list_open", {}, session_id, state)
            finish_args = {"summary": str(reply.get("summary") or "")[:500], "transcript_sweep": reply.get("transcript_sweep"),
                           "accounting": _accounting_with_created(reply.get("accounting"), created_keys)}
            problems = await ma._check_finish(db, workspace_id, owner, finish_args, state)
            errors = calls[-1]["op_errors"]
            if not problems and not errors:
                finished, gate_passed = finish_args["summary"] or "done", True
                break
            if rnd + 1 >= max(1, MAX_ROUNDS):
                finished = finish_args["summary"] or "unfinished"
                state.gate_failures = problems
                break
            # one repair round: say exactly what the code found, show the touched records as they now stand
            touched_now = await ma._tools(db, workspace_id, owner, "list_open", {}, session_id, state)
            user = (prompt["user"] + "\n\n--- your previous reply ---\n" + json.dumps(reply, ensure_ascii=False)[:4000]
                    + "\n\n--- what the code did with it ---\nOperation results: " + json.dumps(results, ensure_ascii=False)[:2500]
                    + "\nProblems found: " + json.dumps(problems + [str(e)[:200] for e in errors], ensure_ascii=False)[:2500]
                    + "\n\nCurrent open records now:\n" + _records_text(touched_now.get("records") or [])
                    + "\n\nReply again with ONE JSON object in the same format. Include ONLY the operations still needed (what is already applied stays applied) "
                      "and the COMPLETE accounting for every observation.")
        ms = int((time.monotonic() - started) * 1000)
        if finished is not None and gate_passed:
            status = "verified"
        elif finished is not None:
            status = "finished_unchecked"
        else:
            status = "unfinished"
        logger.info("[ledger-light] %s %s -> %s (%d calls)", owner, session_id, status, len(calls))
        return {"status": status, "summary": finished, "calls": calls, "inspected": True, "model": MODELS[0] if MODELS else "", "ms": ms,
                "changes": changes, "accounting": state.accounting, "gate_failures": state.gate_failures or problems,
                "touched_keys": sorted(state.touched), "wrote": state.wrote(), "writer": "light"}
    finally:
        ma._TRANSCRIPT_CTX.reset(t_tx)
        ma._TODAY_CTX.reset(t_day)
        ma._TZ_CTX.reset(t_tz)
