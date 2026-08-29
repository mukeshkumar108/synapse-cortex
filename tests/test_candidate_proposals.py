import pytest


@pytest.mark.asyncio
async def test_chief_of_staff_proposal_is_derived_and_idempotent(async_client):
    body = {
        "workspace_id": "ws-brief",
        "session_id": "session-brief",
        "owner_peer_id": "user-1",
        "source_message_id": "brief-2026-08-29-morning",
        "candidates": [{
            "key": "fix-audio",
            "title": "Fix the disappearing audio recording bug",
            "evidence_verbatim": "I need to fix the audio recording bug.",
            "authority": "ask",
        }],
    }
    first = await async_client.post(
        "/v1/cortex/commitment-candidates/propose", json=body
    )
    second = await async_client.post(
        "/v1/cortex/commitment-candidates/propose", json=body
    )
    assert first.status_code == 200
    assert first.json()["candidate_keys"] == second.json()["candidate_keys"]

    listed = await async_client.get(
        "/v1/cortex/commitment-candidates",
        params={"workspace_id": "ws-brief", "owner_peer_id": "user-1"},
    )
    candidates = listed.json()["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["title"] == "Fix the disappearing audio recording bug"
    assert candidates[0]["authority"] == "ask"
