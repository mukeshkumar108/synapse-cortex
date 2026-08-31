"""Sophie scenario harness: a THIN DRIVER around production endpoints.

Drives the real deployed/local Cortex pipeline (extraction, lifecycle,
occurrence accounting, agenda compilation, initiative engine, reminder
executor) with an injected clock and an isolated synthetic workspace per
scenario run. Implements NO behavior. Captures per-turn observability and
asserts declarative expectations (mechanism lane). Conversation judging is a
separate lane (full mode) and is NOT mocked here.

Usage:
  python evals/scenario_runner.py [scenario.json ...] [--base URL]
"""
from __future__ import annotations

import json, sys, time, uuid, urllib.request, urllib.error
from pathlib import Path

BASE = "http://127.0.0.1:8002"
TOKEN = ""
RESULTS_DIR = Path(__file__).parent / "results"


def _post(path: str, payload: dict, timeout: float = 60):
    req = urllib.request.Request(
        f"{BASE}{path}", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


def run_scenario(path: Path) -> dict:
    spec = json.loads(path.read_text())
    run_id = uuid.uuid4().hex[:8]
    ws = f"harness_{spec['name']}_{run_id}"
    session = f"sess_{run_id}"
    peer = f"user_{run_id}"
    tz = spec.get("timezone", "Europe/London")
    captures, failures = [], []
    t_idx = 0
    for step in spec["steps"]:
        t_idx += 1
        now = step["now"]
        capture = {"turn": t_idx, "now": now, "op": step["op"]}
        try:
            if step["op"] == "turn":
                capture["response"] = _post("/v1/events/turn", {
                    "workspace_id": ws, "session_id": session,
                    "honcho_message_id": f"msg_{run_id}_{t_idx}", "peer_id": peer,
                    "text": step["text"], "now": now, "timezone": tz,
                })
            elif step["op"] == "handover":
                h = _post("/v1/cortex/handover", {
                    "workspace_id": ws, "session_id": session, "peer_id": peer,
                    "now": now, "timezone": tz, "turn_text": "",
                    "director_hints": {"force_agenda": True, "product": spec.get("product", "sophie")},
                })
                capture["agenda"] = h.get("agenda")
                capture["patterns"] = h.get("patterns")
                capture["metrics"] = h.get("metrics")
            elif step["op"] == "initiative":
                capture["initiative"] = _post("/v1/cortex/initiative/tick", {
                    "workspace_id": ws, "session_id": session, "peer_id": peer,
                    "now": now, "timezone": tz,
                })
            elif step["op"] == "reminders":
                capture["reminders"] = _post("/v1/cortex/reminders/due", {
                    "workspace_id": ws, "session_id": session, "peer_id": peer,
                    "now": now, "timezone": tz,
                })
        except urllib.error.HTTPError as e:
            capture["error"] = f"HTTP {e.code}: {e.read().decode()[:300]}"
        except Exception as e:
            capture["error"] = f"{type(e).__name__}: {e}"

        # Assertions (mechanism lane)
        for want in step.get("expect", []):
            ok, detail = _check(want, capture)
            if not ok:
                failures.append({"turn": t_idx, "expect": want, "detail": detail})
        captures.append(capture)

    artifact = RESULTS_DIR / f"{spec['name']}_{run_id}.json"
    artifact.write_text(json.dumps({"spec": spec, "captures": captures,
                                    "failures": failures, "workspace": ws}, indent=1))
    status = "PASS" if not failures else f"FAIL ({len(failures)})"
    return {"name": spec["name"], "status": status, "failures": failures,
            "artifact": str(artifact)}


def _check(want: dict, capture: dict) -> tuple[bool, str]:
    kind = want.get("type")
    if kind == "agenda_contains":
        items = capture.get("agenda") or []
        text = json.dumps(items).lower()
        if want["what"].lower() not in text:
            return False, f"agenda lacks '{want['what']}'"
        if "min_pressure" in want:
            for it in items:
                if want["what"].lower() in str(it.get("what", "")).lower():
                    order = {"low": 0, "medium": 1, "high": 2}
                    if order.get(it.get("pressure"), -1) < order[want["min_pressure"]]:
                        return False, f"'{want['what']}' pressure {it.get('pressure')} < {want['min_pressure']}"
        return True, ""
    if kind == "initiative":
        ini = capture.get("initiative") or {}
        if bool(ini.get("should_appear")) != bool(want["should_appear"]):
            return False, f"initiative should_appear={ini.get('should_appear')} reason={ini.get('reason')}"
        return True, ""
    if kind == "reminders_due":
        rem = capture.get("reminders") or {}
        n = int(rem.get("count", 0))
        if "min" in want and n < want["min"]:
            return False, f"reminders due {n} < {want['min']}"
        if "exact" in want and n != want["exact"]:
            return False, f"reminders due {n} != {want['exact']}"
        return True, ""
    if kind == "no_error":
        return ("error" not in capture), capture.get("error", "")
    return False, f"unknown expectation type {kind}"


def main() -> None:
    global BASE, TOKEN
    args = sys.argv[1:]
    if "--base" in args:
        BASE = args[args.index("--base") + 1]
        args = [a for a in args if a != "--base" and a != BASE]
    for env_file in (Path(__file__).parent.parent / ".env",):
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                if line.startswith("SYNAPSE_CORTEX_API_TOKEN="):
                    TOKEN = line.split("=", 1)[1].strip()
    scenarios = [Path(a) for a in args] or sorted((Path(__file__).parent / "scenarios").glob("*.json"))
    results = [run_scenario(p) for p in scenarios]
    print(json.dumps(results, indent=1))
    failed = [r for r in results if r["status"] != "PASS"]
    print(f"\nMATRIX: {len(results) - len(failed)}/{len(results)} PASS")
    for r in failed:
        print(f"  FAIL {r['name']}")
        for f in r["failures"]:
            print(f"    T{f['turn']}: {f['expect']} -> {f['detail'][:140]}")


if __name__ == "__main__":
    main()
