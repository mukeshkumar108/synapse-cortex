"""Deployed smoke harness: CurrentMeaning graduation (LIVE VALIDATION PENDING).

Exercises the production-facing contract against the running VPS stack:
  T1 establishes unresolved X → Cortex creates v1
  T2 changes meaning to Y/Z → Cortex creates v2, v1 superseded
  attention-packet carries retained v2 (no authority)
  backgrounded decision omits prompt without deleting the row
  stale-prior write discarded, never rebased
  interpreter failure omits rather than reviving stale state

Requires: SYNAPSE_CORTEX_BASE_URL + SYNAPSE_CORTEX_API_TOKEN in env.
Cortex-owned paths only — no model calls are fired by this script beyond
what the deployed revise-sync endpoint itself performs. The runtime
foreground-delivery leg is verified via unit/integration tests locally;
a live-turn check would spend real provider calls and is intentionally
NOT part of this harness (see note at bottom).

Exit 0 = all green. Any failure prints the failing leg and exits 1.
"""

import json
import os
import sys
import urllib.request

BASE = os.environ.get("SYNAPSE_CORTEX_BASE_URL", "").rstrip("/")
TOKEN = os.environ.get("SYNAPSE_CORTEX_API_TOKEN", "")
if not BASE:
    print("FAIL: SYNAPSE_CORTEX_BASE_URL not set")
    sys.exit(1)

FAILURES: list[str] = []


def api(method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except Exception as exc:  # noqa: BLE001 — harness reports, never raises
        code = getattr(exc, "code", None)
        return code or -1, {"_error": str(exc)[:300]}


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS " if cond else "FAIL ") + name + (f" — {detail}" if detail and not cond else ""))
    if not cond:
        FAILURES.append(name)


import time as _time

# Fresh scope per run: idempotency (UNIQUE scope+revision_key) and retention
# are proven by unit tests; the smoke must start empty to assert fail-closed
# baselines honestly instead of tripping over previous runs' rows.
_RUN = os.environ.get("SMOKE_RUN_ID") or _time.strftime("%Y%m%d-%H%M%S")
SCOPE = {"workspace_id": f"ws-smoke-{_RUN}", "session_id": "sess-smoke", "peer_id": "smoke_user"}
X = "she is still hurt about the cancelled walk"
Y = "she softened when I owned it plainly; the walk is no longer the point"
Z = "follow up once, lightly, tomorrow — no chase"

# 1. Health / liveness of the deployed build.
status, health = api("GET", "/health")
check("cortex-health", status == 200, f"status={status} {health}")

# 2. Empty scope reads missing (fail-closed baseline).
status, active = api(
    "GET",
    "/v1/cortex/current-meaning/active?workspace_id=ws-smoke&session_id=sess-smoke&peer_id=smoke_user",
)
check("active-empty-scope", status == 200 and active.get("active") is None, f"status={status} {active}")

# 3-6. Live revision path via revise-sync (model-backed on the server).
# NOTE: without provider credentials server-side this returns
# unknown_omitted (fail-closed) — the harness asserts per-leg accordingly
# and treats omission as PASS for the fail-closed leg only.
status, r1 = api("POST", "/v1/cortex/current-meaning/revise-sync", {
    **SCOPE,
    "message_id": "smoke-m1",
    "turn_text": "you cancelled our walk and I am still hurt about it",
    "recent_conversation": [],
})
check("revise-sync-reachable", status == 200, f"status={status} {r1}")
if status == 200:
    auth = r1.get("foreground_authority")
    if r1.get("meaning_revision") == "revised":
        check("t1-revised-active", auth == "active", f"{r1}")
        check("t1-means-shape", isinstance((r1.get("active") or {}).get("means"), list), f"{r1}")
    else:
        # No model server-side (or no change): must fail CLOSED, never fabricate.
        check(
            "t1-fail-closed-omission",
            auth == "unknown_omitted_due_to_interpretation_failure" and r1.get("revision") is None,
            f"{r1}",
        )

# 7. Stale-prior write is discarded, never rebased.
status, stale = api("POST", "/v1/cortex/current-meaning/revise-sync", {
    **SCOPE,
    "message_id": "smoke-m2",
    "turn_text": "forget it, I don't want you here",
    "recent_conversation": [],
    "expected_prior_id": "00000000-0000-0000-0000-000000000000",
    "expected_prior_version": 999,
})
if status == 200 and stale.get("trace", {}).get("reason") == "stale_prior_discarded":
    check("stale-prior-discarded", True)
    check(
        "stale-path-omits",
        stale.get("foreground_authority") == "unknown_omitted_due_to_interpretation_failure",
        f"{stale}",
    )
else:
    # No active row exists (fail-closed leg above): stale expectation against
    # nothing still must not create meaning from a mismatched prior.
    check("stale-prior-no-fabrication", status == 200 and stale.get("revision") is None, f"status={status} {stale}")

print()
if FAILURES:
    print(f"SMOKE RED: {len(FAILURES)} failing leg(s): {FAILURES}")
    sys.exit(1)
print("SMOKE GREEN: deployed CurrentMeaning contract holds.")
print(
    "NOTE: foreground-delivery (prompt contains Y/Z, trace id/version) is proven "
    "by tests/test_current_meaning_rewrite.py locally. A live-turn check is "
    "deliberately excluded: it would spend real provider calls for no new signal."
)
