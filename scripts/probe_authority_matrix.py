"""Probe D: contrasted authority calibration matrix (MEASURED, not gated).

Drives live revise-sync per cell: seed X (establish v1), then evidence turn.
Records foreground_authority, meaning_revision, active id/version, and row
creation for every call. Desired-direction labels below are HUMAN-READ eval
labels only — never asserted, never encoded as rules or gates.

Run inside the VPS stack (needs model creds server-side):
  docker exec -i -e SYNAPSE_CORTEX_BASE_URL=http://127.0.0.1:8010 \
    -e SYNAPSE_CORTEX_API_TOKEN="$TOKEN" synapse-cortex python - \
    < scripts/probe_authority_matrix.py

Scopes are isolated per cell (ws-probe-auth-<class>); probe rows are labeled
and inert (superseded/retained, never surfaced to real traffic).
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

SEED_TEXT = "you cancelled our walk and I am still hurt about it"

# cell -> (probe turns after seed, desired semantic direction [label only]).
MATRIX = {
    # Desired: background likely (release recognized).
    "clear-softening": (
        ["hey, that was kind of you to just own it — I feel a lot lighter about yesterday"],
        "background likely",
    ),
    # Desired: background likely (resolved, nothing open).
    "clear-resolution": (
        ["all good on the walk thing, we're sorted, see you tomorrow as planned"],
        "background likely",
    ),
    # Desired: do NOT overclaim resolution (ambiguous warmth ≠ eased issue).
    "ambiguous-warmth": (
        ["haha you're sweet. anyway what should we have for dinner"],
        "don't overclaim resolution",
    ),
    # Desired: probably background/omit — but from irrelevance, NOT resolution.
    "ordinary-topic-shift": (
        ["by the way did you see the match last night"],
        "probably background/omit (irrelevance, not resolution)",
    ),
    # Desired: remain active (persistence must survive warmth elsewhere).
    "ongoing-pain": (
        ["I keep replaying it, honestly it still hurts"],
        "remain active",
    ),
    # Desired: remain active, revise if meaning changed (never background pain).
    "fresh-sharpening": (
        ["actually no — forget it, I don't want to talk about this anymore"],
        "remain active / revise",
    ),
    # Desired: active again on the SAME version (reactivation, no churn).
    "reactivation": (
        [
            "hey, that was kind of you to just own it — I feel a lot lighter about yesterday",
            "do you even remember what you cancelled?",
        ],
        "active again, same version",
    ),
    # Desired: old meaning must NOT regain authority from unrelated chat.
    "unrelated-banter": (
        [
            "hey, that was kind of you to just own it — I feel a lot lighter about yesterday",
            "what's the capital of Peru",
        ],
        "stay backgrounded, no new row",
    ),
}


def api(body: dict) -> tuple[int, dict]:
    req = urllib.request.Request(
        BASE + "/v1/cortex/current-meaning/revise-sync",
        data=json.dumps(body).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            **({"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except Exception as exc:  # noqa: BLE001 — probe records, never raises
        return getattr(exc, "code", -1) or -1, {"_error": str(exc)[:200]}


SAMPLES = int(os.environ.get("PROBE_SAMPLES", "1"))


def main() -> int:
    print("cell | sample | call | revision | authority | active_ver | new_row | desired (label only)")
    for cell, (turns, desired) in MATRIX.items():
        for sample in range(1, SAMPLES + 1):
            scope = f"ws-probe2-{cell}-s{sample}" if SAMPLES > 1 else f"ws-probe-auth-{cell}"
            prior_id, prior_ver = None, None
            seq = [("seed", SEED_TEXT)] + [(f"probe{i+1}", t) for i, t in enumerate(turns)]
            for idx, (kind, text) in enumerate(seq):
                body = {
                    "workspace_id": scope,
                    "session_id": "sess-probe",
                    "peer_id": "probe_user",
                    "message_id": f"{cell}-s{sample}-{kind}",
                    "turn_text": text,
                    "recent_conversation": [],
                    "expected_prior_id": prior_id,
                    "expected_prior_version": prior_ver,
                }
                status, out = api(body)
                if status != 200:
                    print(f"{cell} | s{sample} | {kind} | HTTP {status} {out}")
                    break
                active = out.get("active") or {}
                print(
                    f"{cell} | s{sample} | {kind} | {out.get('meaning_revision')} | "
                    f"{out.get('foreground_authority')} | v{active.get('version')} | "
                    f"{'YES' if out.get('revision') else 'no'} | {desired if kind != 'seed' else '(seed)'}"
                )
                prior_id, prior_ver = active.get("id"), active.get("version")
    return 0


if __name__ == "__main__":
    sys.exit(main())
