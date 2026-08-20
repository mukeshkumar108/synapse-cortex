import pytest


def event(ws, session, message, text):
    return {"workspace_id": ws, "session_id": session, "honcho_message_id": message,
            "peer_id": "mukesh", "text": text, "now": "2026-08-11T14:00:00Z",
            "timezone": "Europe/London"}


@pytest.mark.asyncio
async def test_reschedule_creates_linked_replacement(async_client):
    await async_client.post("/v1/events/turn", json=event("w", "s", "1", "I'll test Sophie tonight."))
    result = await async_client.post("/v1/events/turn", json=event("w", "s", "2", "Actually I'll do it tomorrow morning."))
    assert result.status_code == 202
    debug = (await async_client.get("/v1/debug/decisions", params={"workspace_id": "w", "session_id": "s"})).json()
    assert len(debug["decisions"]) == 2
    assert {row["outcome_state"] for row in debug["decisions"]} == {"unknown", "superseded"}


@pytest.mark.asyncio
async def test_ordinal_target_and_ambiguous_shield(async_client):
    for mid, text in [("1", "I'll call James tomorrow."), ("2", "I'll send Morgan the report Friday.")]:
        await async_client.post("/v1/events/turn", json=event("wo", "so", mid, text))
    resolved = await async_client.post("/v1/events/turn", json=event("wo", "so", "3", "Forget the second one."))
    assert len(resolved.json()["mutated_expectation_ids"]) == 1


@pytest.mark.asyncio
async def test_nested_belief_not_flattened(async_client):
    await async_client.post("/v1/events/turn", json=event("we", "se", "1", "Ashley thinks James believes she's angry."))
    debug = (await async_client.get("/v1/debug/decisions", params={"workspace_id": "we"})).json()
    assert debug["epistemic_annotations"][0]["perspective_peer_id"] == "ashley"
    assert debug["epistemic_annotations"][0]["target_peer_id"] == "james"
    assert "believes" in debug["epistemic_annotations"][0]["claim_summary"]
