"""Second-producer lifecycle: the delta endpoint is a validated lifecycle interface,
not an interpreter-only path.

Covers (all deterministic, no model):
- an open record created via the canonical object endpoint can be CLOSED mid-session
  by exact id through POST /v1/world/delta with producer != interpreter;
- the receipt carries the outcome; owner-state shows CANCELLED with evidence;
- an unknown id refuses (target_not_found) without mutating anything;
- a close without a bound id refuses (target_required) without mutating anything;
- re-review of the closed record applies as already-closed (no resurrection, no duplicate).
"""

from datetime import datetime, timedelta, timezone

UTC = timezone.utc


def iso(**kwargs) -> str:
    return (datetime.now(UTC) + timedelta(**kwargs)).isoformat()


def object_payload(**overrides) -> dict:
    payload = {
        "workspace_id": "ws-delta2",
        "session_id": "session-a",
        "peer_id": "user_1",
        "owner_peer_id": "user_1",
        "now": iso(),
        "timezone": "Europe/London",
        "source": {"system": "app_task", "object_id": "task-lunch-1", "version": 1, "kind": "task"},
        "action": "created",
        "title": "Friday lunch with James",
        "due_at": iso(days=2),
        "reminder_windows": [],
    }
    payload.update(overrides)
    return payload


def delta_payload(expectation_id: str, decision: str = "cancel", target: object = "USE_ID", evidence_id: str = "msg-cancel-1") -> dict:
    return {
        "workspace_id": "ws-delta2",
        "owner": "user_1",
        "source": {
            "producer": "runtime-checkpoint",
            "model": "",
            "version": "test",
            "session_id": "session-a",
            "messages": [{"id": evidence_id, "speaker": "user", "text": "actually cancel Friday's lunch"}],
            "policy": "grounded",
        },
        "operational": [
            {
                "decision": decision,
                "kind": "event",
                "title": "Friday lunch with James",
                **({"target": expectation_id} if target == "USE_ID" else ({"target": target} if target is not None else {})),
                "evidence": [evidence_id],
            }
        ],
    }


async def test_second_producer_closes_by_exact_id_with_receipt(async_client):
    created = (await async_client.post("/v1/events/object", json=object_payload())).json()
    expectation_id = created["expectation_id"]

    receipt = (await async_client.post("/v1/world/delta", json=delta_payload(expectation_id))).json()
    committed = receipt["operational"]["committed"]
    assert len(committed) == 1 and receipt["operational"]["failed"] == []
    assert committed[0]["id"] == expectation_id and committed[0]["outcome"] == "cancelled"
    assert receipt["producer"] == "runtime-checkpoint"

    state = (await async_client.get("/v1/debug/owner-state", params={"workspace_id": "ws-delta2", "owner_peer_id": "user_1"})).json()
    rows = [e for e in state["expectations"] if e["id"] == expectation_id]
    assert len(rows) == 1 and rows[0]["outcome_state"] == "cancelled"
    assert "cancel Friday" in (rows[0]["resolution_evidence"] or "")

    # A later review of the same record applies as already settled: no duplicate, no resurrection.
    review = (await async_client.post("/v1/world/delta", json={
        "workspace_id": "ws-delta2", "owner": "user_1",
        "source": {"producer": "runtime-checkpoint", "session_id": "session-a", "messages": [], "policy": "grounded"},
        "operational_reviews": [{"id": expectation_id, "status": "cancelled"}],
    })).json()
    assert review["operational"]["reviews"][0]["applied"] is True


async def test_repeated_close_reports_already_applied_without_rewriting_history(async_client):
    created = (await async_client.post("/v1/events/object", json=object_payload())).json()
    expectation_id = created["expectation_id"]

    first = (await async_client.post("/v1/world/delta", json=delta_payload(expectation_id))).json()
    assert first["operational"]["committed"][0].get("already_applied") is not True
    state = (await async_client.get("/v1/debug/owner-state", params={"workspace_id": "ws-delta2", "owner_peer_id": "user_1"})).json()
    evidence_before = [e for e in state["expectations"] if e["id"] == expectation_id][0]["resolution_evidence"]

    second = (await async_client.post("/v1/world/delta", json=delta_payload(
        expectation_id, evidence_id="msg-cancel-9"))).json()
    assert second["operational"]["committed"][0].get("already_applied") is True
    assert second["operational"]["failed"] == []

    state = (await async_client.get("/v1/debug/owner-state", params={"workspace_id": "ws-delta2", "owner_peer_id": "user_1"})).json()
    rows = [e for e in state["expectations"] if e["id"] == expectation_id]
    assert rows[0]["outcome_state"] == "cancelled" and rows[0]["resolution_evidence"] == evidence_before


async def test_unknown_id_refuses_without_mutation(async_client):
    created = (await async_client.post("/v1/events/object", json=object_payload())).json()
    expectation_id = created["expectation_id"]

    receipt = (await async_client.post("/v1/world/delta", json=delta_payload(
        expectation_id, target="00000000-0000-0000-0000-000000000000", evidence_id="msg-cancel-2"))).json()
    assert receipt["operational"]["committed"] == []
    assert receipt["operational"]["failed"][0]["reason"] == "target_not_found"

    state = (await async_client.get("/v1/debug/owner-state", params={"workspace_id": "ws-delta2", "owner_peer_id": "user_1"})).json()
    rows = [e for e in state["expectations"] if e["id"] == expectation_id]
    assert rows[0]["outcome_state"] == "unknown"


async def test_close_without_bound_id_refuses_without_mutation(async_client):
    created = (await async_client.post("/v1/events/object", json=object_payload())).json()
    expectation_id = created["expectation_id"]

    receipt = (await async_client.post("/v1/world/delta", json=delta_payload(
        expectation_id, target=None, evidence_id="msg-cancel-3"))).json()
    assert receipt["operational"]["committed"] == []
    assert receipt["operational"]["failed"][0]["reason"] == "target_required"

    state = (await async_client.get("/v1/debug/owner-state", params={"workspace_id": "ws-delta2", "owner_peer_id": "user_1"})).json()
    rows = [e for e in state["expectations"] if e["id"] == expectation_id]
    assert rows[0]["outcome_state"] == "unknown"


async def test_fresh_close_retires_matching_dated_prose_but_keeps_preferences(async_client):
    from src.db import async_session_maker
    from src.services.standing_requests import StandingRequest
    created = (await async_client.post("/v1/events/object", json=object_payload())).json()
    expectation_id = created["expectation_id"]
    async with async_session_maker() as db:
        db.add(StandingRequest(honcho_workspace_id="ws-delta2", owner_peer_id="user_1",
                               text="Friday lunch with James moved to Saturday noon",
                               key="friday lunch with james moved to saturday noon", source="scene_pass"))
        db.add(StandingRequest(honcho_workspace_id="ws-delta2", owner_peer_id="user_1",
                               text="Don't frame things as therapy", key="don t frame things as therapy",
                               source="scene_pass"))
        await db.commit()
    receipt = (await async_client.post("/v1/world/delta", json=delta_payload(expectation_id))).json()
    assert receipt["operational"]["committed"][0].get("requests_retired") == ["Friday lunch with James moved to Saturday noon"]
    import sqlmodel
    from src.services.standing_requests import StandingRequest as _SR
    async with async_session_maker() as db:
        active = sorted(r.text for r in (await db.execute(sqlmodel.select(_SR).where(
            _SR.honcho_workspace_id == "ws-delta2", _SR.owner_peer_id == "user_1",
            _SR.status == "active"))).scalars().all())
    assert active == ["Don't frame things as therapy"]
