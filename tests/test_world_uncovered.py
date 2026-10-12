"""Uncovered-evidence ledger: ids offered to interpretation but covered by no applied
run must be re-offerable by id — timestamps alone cannot prove coverage."""
import json

import pytest

from src.db import async_session_maker
from src.models.world import ProducerRun


def _run(workspace, owner, status, message_ids, offered=None, producer="world-interpreter"):
    return ProducerRun(honcho_workspace_id=workspace, owner_peer_id=owner, producer=producer,
                       model="test", version="wi-2", status=status,
                       input_json=json.dumps({"session_id": "s", "message_ids": message_ids,
                                              "offered_ids": offered if offered is not None else message_ids}))


@pytest.mark.asyncio
async def test_failed_run_ids_are_uncovered_until_an_applied_run_covers_them(async_client):
    async with async_session_maker() as db:
        db.add(_run("w-u", "u1", "applied", ["m1", "m2"]))
        db.add(_run("w-u", "u1", "failed", ["m3", "m4"]))
        await db.commit()
    body = (await async_client.get("/v1/world/uncovered", params={"workspace_id": "w-u", "owner": "u1"})).json()
    assert body["uncovered"] == ["m3", "m4"] and body["offered_count"] == 4 and body["covered_count"] == 2
    assert body["sessions"] == {"m3": "s", "m4": "s"}

    async with async_session_maker() as db:
        db.add(_run("w-u", "u1", "applied", ["m3", "m4", "m5"]))
        await db.commit()
    body = (await async_client.get("/v1/world/uncovered", params={"workspace_id": "w-u", "owner": "u1"})).json()
    assert body["uncovered"] == [] and body["covered_count"] == 5


@pytest.mark.asyncio
async def test_coverage_is_owner_scoped_and_order_stable(async_client):
    async with async_session_maker() as db:
        db.add(_run("w-u", "u1", "failed", ["a1"]))
        db.add(_run("w-u", "u2", "failed", ["b1"]))
        await db.commit()
    one = (await async_client.get("/v1/world/uncovered", params={"workspace_id": "w-u", "owner": "u1"})).json()
    two = (await async_client.get("/v1/world/uncovered", params={"workspace_id": "w-u", "owner": "u2"})).json()
    assert one["uncovered"] == ["a1"] and two["uncovered"] == ["b1"]


@pytest.mark.asyncio
async def test_second_producer_runs_do_not_confer_discovery_coverage(async_client):
    """A tool close processes evidence for a decision but never mines it: the ids stay
    uncovered until an interpreter pass reads them."""
    async with async_session_maker() as db:
        db.add(_run("w-u", "u1", "applied", ["m1"], producer="runtime-tool"))
        await db.commit()
    body = (await async_client.get("/v1/world/uncovered", params={"workspace_id": "w-u", "owner": "u1"})).json()
    assert body["uncovered"] == ["m1"]
