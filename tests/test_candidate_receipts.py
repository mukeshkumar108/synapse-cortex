from datetime import date, datetime, timezone

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.operational_state import (
    CandidateReceipt,
    RecurringIntention,
    RecurringOccurrence,
)


async def _seed_candidate():
    async with async_session_maker() as db:
        intention = RecurringIntention(
            honcho_workspace_id="workspace-1",
            honcho_session_id="session-1",
            honcho_message_id="message-1",
            owner_peer_id="owner-1",
            candidate_key="daily-walk",
            canonical_key="daily-walk",
            title="Take the daily walk",
            cadence="daily",
            source_evidence="User said they intend to walk daily.",
        )
        db.add(intention)
        await db.flush()
        occurrence = RecurringOccurrence(
            recurring_intention_id=intention.id,
            honcho_workspace_id="workspace-1",
            user_day=date(2026, 9, 22),
            source_message_id="message-1",
        )
        db.add(occurrence)
        await db.commit()
        return str(occurrence.id)


@pytest.mark.asyncio
async def test_candidate_query_is_pure_and_neutral(async_client):
    occurrence_id = await _seed_candidate()
    payload = {
        "workspace_id": "workspace-1",
        "owner_peer_id": "owner-1",
        "now": "2026-09-22T12:00:00Z",
    }
    first = await async_client.post("/v1/cortex/candidates/query", json=payload)
    second = await async_client.post("/v1/cortex/candidates/query", json=payload)
    assert first.status_code == 200
    assert first.json() == second.json()
    candidate = first.json()["candidates"][0]
    assert candidate["candidate_id"] == f"recurring_occurrence:{occurrence_id}"
    assert set(candidate).isdisjoint({"should_appear", "next_move", "prompt", "persona"})

    async with async_session_maker() as db:
        occurrence = (await db.execute(select(RecurringOccurrence))).scalar_one()
        receipts = (await db.execute(select(CandidateReceipt))).scalars().all()
        assert occurrence.asked_at is None
        assert occurrence.ask_count == 0
        assert receipts == []


@pytest.mark.asyncio
async def test_only_delivered_asked_receipt_updates_ledger_once(async_client):
    occurrence_id = await _seed_candidate()
    candidate_id = f"recurring_occurrence:{occurrence_id}"
    candidate_response = await async_client.post("/v1/cortex/candidates/query", json={
        "workspace_id": "workspace-1",
        "owner_peer_id": "owner-1",
        "now": "2026-09-22T12:00:00Z",
    })
    candidate_version = candidate_response.json()["candidates"][0]["candidate_version"]

    def body(stage: str, receipt_id: str, effect=None):
        return {
            "contract_version": "candidate-receipts-v1",
            "workspace_id": "workspace-1",
            "owner_peer_id": "owner-1",
            "receipts": [{
                "receipt_id": receipt_id,
                "decision_id": "decision-1",
                "turn_id": "turn-1",
                "candidate_id": candidate_id,
                "candidate_version": candidate_version,
                "stage": stage,
                "channel": "inbound",
                "occurred_at": "2026-09-22T12:00:00Z",
                "assistant_message_id": "assistant-1" if stage == "delivered" else None,
                "effect": effect,
            }],
        }

    for stage in ("selected", "surfaced"):
        response = await async_client.post(
            "/v1/cortex/candidate-receipts",
            json=body(stage, f"receipt-{stage}"),
        )
        assert response.status_code == 200
        async with async_session_maker() as db:
            occurrence = (await db.execute(select(RecurringOccurrence))).scalar_one()
            assert occurrence.ask_count == 0
            assert occurrence.asked_at is None

    delivered = body("delivered", "receipt-delivered", "asked")
    response = await async_client.post("/v1/cortex/candidate-receipts", json=delivered)
    assert response.json() == {
        "contract_version": "candidate-receipts-v1",
        "accepted": 1,
        "duplicates": 0,
    }
    replay = await async_client.post("/v1/cortex/candidate-receipts", json=delivered)
    assert replay.json()["accepted"] == 0
    assert replay.json()["duplicates"] == 1

    async with async_session_maker() as db:
        occurrence = (await db.execute(select(RecurringOccurrence))).scalar_one()
        receipts = (await db.execute(select(CandidateReceipt))).scalars().all()
        assert occurrence.ask_count == 1
        assert occurrence.asked_at == datetime(2026, 9, 22, 12, 0)
        assert len(receipts) == 3


@pytest.mark.asyncio
async def test_receipt_cannot_cross_owner_scope(async_client):
    occurrence_id = await _seed_candidate()
    response = await async_client.post("/v1/cortex/candidate-receipts", json={
        "contract_version": "candidate-receipts-v1",
        "workspace_id": "workspace-1",
        "owner_peer_id": "other-owner",
        "receipts": [{
            "receipt_id": "receipt-cross-owner",
            "decision_id": "decision-1",
            "turn_id": "turn-1",
            "candidate_id": f"recurring_occurrence:{occurrence_id}",
            "candidate_version": "v1",
            "stage": "delivered",
            "channel": "inbound",
            "occurred_at": "2026-09-22T12:00:00Z",
            "assistant_message_id": "assistant-1",
            "effect": "asked",
        }],
    })
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_conflicting_or_stale_receipts_fail_closed(async_client):
    occurrence_id = await _seed_candidate()
    candidate_id = f"recurring_occurrence:{occurrence_id}"
    query = await async_client.post("/v1/cortex/candidates/query", json={
        "workspace_id": "workspace-1",
        "owner_peer_id": "owner-1",
        "now": "2026-09-22T12:00:00Z",
    })
    version = query.json()["candidates"][0]["candidate_version"]
    base = {
        "contract_version": "candidate-receipts-v1",
        "workspace_id": "workspace-1",
        "owner_peer_id": "owner-1",
        "receipts": [{
            "receipt_id": "receipt-selected",
            "decision_id": "decision-1",
            "turn_id": "turn-1",
            "candidate_id": candidate_id,
            "candidate_version": version,
            "stage": "selected",
            "channel": "inbound",
            "occurred_at": "2026-09-22T12:00:00Z",
            "assistant_message_id": None,
            "effect": None,
        }],
    }
    assert (await async_client.post("/v1/cortex/candidate-receipts", json=base)).status_code == 200

    conflict = {**base, "receipts": [{**base["receipts"][0], "turn_id": "turn-other"}]}
    assert (await async_client.post("/v1/cortex/candidate-receipts", json=conflict)).status_code == 409

    stale = {**base, "receipts": [{
        **base["receipts"][0],
        "receipt_id": "receipt-surfaced",
        "stage": "surfaced",
        "candidate_version": "stale-version",
    }]}
    assert (await async_client.post("/v1/cortex/candidate-receipts", json=stale)).status_code == 409

    missing_message = {**base, "receipts": [{
        **base["receipts"][0],
        "receipt_id": "receipt-delivered",
        "stage": "delivered",
    }]}
    assert (await async_client.post("/v1/cortex/candidate-receipts", json=missing_message)).status_code == 422


@pytest.mark.asyncio
async def test_candidate_query_excludes_future_and_already_asked(async_client):
    occurrence_id = await _seed_candidate()
    async with async_session_maker() as db:
        occurrence = (await db.execute(select(RecurringOccurrence))).scalar_one()
        occurrence.user_day = date(2026, 9, 23)
        await db.commit()
    payload = {
        "workspace_id": "workspace-1",
        "owner_peer_id": "owner-1",
        "now": "2026-09-22T12:00:00Z",
    }
    assert (await async_client.post("/v1/cortex/candidates/query", json=payload)).json()["candidates"] == []

    async with async_session_maker() as db:
        occurrence = await db.get(RecurringOccurrence, __import__("uuid").UUID(occurrence_id))
        occurrence.user_day = date(2026, 9, 22)
        occurrence.asked_at = datetime(2026, 9, 22, 11, 0)
        await db.commit()
    assert (await async_client.post("/v1/cortex/candidates/query", json=payload)).json()["candidates"] == []
