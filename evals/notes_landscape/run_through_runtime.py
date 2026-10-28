"""Arm 1 (existing pipeline, unchanged): feed the 14 Tom sittings in order to a disposable synthetic owner, wait for each consolidation,
snapshot the stored state after every sitting, and dump everything at the end. Runs inside the companion-runtime container.
The owner is NOT deleted here (the periodic-review arm reads it); delete it with owner_delete when finished."""
import asyncio, json, os, sys, time
from adapters.cortex.client import CortexAdapter, honcho_ids

USER = os.environ.get("LAB_USER", "lab-tom-a1")
OUT = os.environ.get("LAB_OUT", "/tmp/landscape_a1.json")
TZ = "Europe/London"


def save(out):
    with open(OUT, "w") as f:
        json.dump(out, f)


async def get(a, path, params):
    cfg = a._config()
    r = await a._client().get(f"{cfg['baseURL']}{path}", headers=a._headers(cfg, product_credential=True), params=params, timeout=60)
    r.raise_for_status()
    return r.json()


async def main():
    sittings = json.load(open("/tmp/sittings.json"))["sittings"]
    a = CortexAdapter()
    ids = honcho_ids(USER, "x")
    base = {"workspace_id": ids["workspaceId"], "owner": ids["userPeerId"], "companion_id": "sophie"}
    out = {"user": USER, "owner": ids["userPeerId"], "workspace": ids["workspaceId"], "started": time.time(), "sittings": {}, "done": False}
    save(out)
    for s in sittings:
        sid = s["id"]
        msgs = []
        for i, m in enumerate(s["messages"]):
            msgs.append({"id": f"{sid}-{i}-{m['role'][0]}", "speaker": m["role"], "text": m["text"]})
        t0 = time.time()
        r = await a.consolidate_memory(user_id=USER, chat_id=f"{USER}-{sid}", session_id=f"{USER}-{sid}", messages=msgs, session_time=s["when"], time_zone=TZ)
        rid = (r or {}).get("run_id")
        status = None
        for _ in range(300):
            await asyncio.sleep(4)
            try:
                run = await get(a, f"/v1/memory/run/{rid}", {})
            except Exception:
                continue
            status = run.get("status")
            if status in ("consolidated", "replay_noop", "empty", "failed"):
                break
        rec = {"run_id": rid, "status": status, "seconds": round(time.time() - t0), "summary": (run or {}).get("summary") if status else None}
        try:
            st = await get(a, "/v1/memory/state", {**base, "include_closed": "true"})
            rec["ledger"] = st.get("ledger")
            rec["notebook"] = st.get("notebook")
            rec["arc"] = st.get("arc")
        except Exception as e:  # noqa: BLE001
            rec["state_error"] = str(e)[:200]
        out["sittings"][sid] = rec
        save(out)
    # final dumps
    try:
        out["export"] = await a.owner_export(user_id=USER)
    except Exception as e:  # noqa: BLE001
        out["export_error"] = str(e)[:200]
    try:
        out["world_inspect"] = await a.world_view(user_id=USER, chat_id="x", view="inspect")
    except Exception as e:  # noqa: BLE001
        out["world_error"] = str(e)[:200]
    out["done"] = True
    out["finished"] = time.time()
    save(out)


asyncio.run(main())
