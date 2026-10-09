"""An edited / retried / regenerated conversation: what was derived from the discarded messages loses authority; what predates it stays."""
import json
from datetime import datetime, timedelta

import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.scene import SceneNarrative
from src.models.identity import Entity, ModelEntry
from src.models.world import ProducerRun, RowProvenance, WorldEvent
from src.services import world_rewind
from src.services.standing_requests import StandingRequest
from src.services.world_interpreter import message_hash

WS, OWNER = "w-rw", "world:rpd2:u1:isa:c1"


@pytest.mark.asyncio
async def test_rewind_retracts_the_runs_that_read_discarded_messages_and_resets_the_sitting():
    t0 = datetime.utcnow() - timedelta(hours=1)
    async with async_session_maker() as db:
        old_run = ProducerRun(honcho_workspace_id=WS, owner_peer_id=OWNER, producer="world-interpreter", status="applied", created_at=t0,
                              input_json=json.dumps({"message_ids": ["m1", "m2"]}))
        ghost_run = ProducerRun(honcho_workspace_id=WS, owner_peer_id=OWNER, producer="world-interpreter", status="applied", created_at=t0 + timedelta(minutes=30),
                                input_json=json.dumps({"message_ids": ["t9-u", "t9-a"], "synthetic_hashes": [message_hash("assistant", "I kissed Marco last night")]}))
        db.add_all([old_run, ghost_run])
        await db.commit()
        kept = WorldEvent(honcho_workspace_id=WS, owner_peer_id=OWNER, label="Marco sent photos", created_at=t0 + timedelta(minutes=1))
        ghost = WorldEvent(honcho_workspace_id=WS, owner_peer_id=OWNER, label="Isa kissed Marco", created_at=t0 + timedelta(minutes=31))
        db.add_all([kept, ghost])
        await db.commit()
        db.add_all([RowProvenance(honcho_workspace_id=WS, run_id=old_run.id, row_type="event", row_id=kept.id),
                    RowProvenance(honcho_workspace_id=WS, run_id=ghost_run.id, row_type="event", row_id=ghost.id)])
        db.add(SceneNarrative(honcho_workspace_id=WS, honcho_session_id="chat_c1", text="Isa kissed Marco.", pending_json='[{"speaker":"user","text":"x"}]',
                              anchors_json=json.dumps([{"id": "a1", "kind": "external", "text": "Marco sent photos", "status": "established", "at": (t0 + timedelta(minutes=2)).isoformat()},
                                                       {"id": "a2", "kind": "claim", "text": "Isa says she kissed Marco", "status": "claimed", "at": (t0 + timedelta(minutes=32)).isoformat()}])))
        await db.commit()

        later_run = ProducerRun(honcho_workspace_id=WS, owner_peer_id=OWNER, producer="world-interpreter", status="applied", created_at=t0 + timedelta(minutes=40),
                                input_json=json.dumps({"message_ids": ["m9"]}))                  # read only surviving messages, but with the ghost in the world it was shown
        db.add(later_run)
        marco = Entity(honcho_workspace_id=WS, display_name="Marco", created_at=t0 + timedelta(minutes=31))
        sam = Entity(honcho_workspace_id=WS, display_name="Sam", created_at=t0 + timedelta(minutes=1))
        db.add_all([marco, sam])
        await db.commit()
        db.add_all([RowProvenance(honcho_workspace_id=WS, run_id=ghost_run.id, row_type="entity", row_id=marco.id),
                    RowProvenance(honcho_workspace_id=WS, run_id=old_run.id, row_type="entity", row_id=sam.id)])
        later_event = WorldEvent(honcho_workspace_id=WS, owner_peer_id=OWNER, label="Isa told Kai she hid it", created_at=t0 + timedelta(minutes=41))
        db.add_all([later_event, StandingRequest(honcho_workspace_id=WS, owner_peer_id=OWNER, text="Do not mention Marco", key="do not mention marco", created_at=t0 + timedelta(minutes=33)),
                    StandingRequest(honcho_workspace_id=WS, owner_peer_id=OWNER, text="Call me Kai", key="call me kai", created_at=t0 + timedelta(minutes=3))])
        await db.commit()
        db.add(RowProvenance(honcho_workspace_id=WS, run_id=later_run.id, row_type="event", row_id=later_event.id))
        await db.commit()

        out = await world_rewind.rewind(db, workspace_id=WS, owner=OWNER, session_ids=["chat_c1"], since=t0 + timedelta(minutes=30),
                                        deleted=[{"id": "gone-1", "speaker": "assistant", "text": "I kissed Marco last night"}])
        assert out["runs_retracted"] == 2 and out["rows_removed"] == 2 and out["actors_removed"] == 1 and out["standing_removed"] == 1 and out["anchors_dropped"] == 1 and out["anchors_kept"] == 1
        labels = [e.label for e in (await db.execute(select(WorldEvent).where(WorldEvent.honcho_workspace_id == WS))).scalars().all()]
        assert labels == ["Marco sent photos"]
        runs = {r.id: r.status for r in (await db.execute(select(ProducerRun).where(ProducerRun.honcho_workspace_id == WS))).scalars().all()}
        assert runs[ghost_run.id] == "retracted" and runs[later_run.id] == "retracted" and runs[old_run.id] == "applied"
        names = [e.display_name for e in (await db.execute(select(Entity).where(Entity.honcho_workspace_id == WS))).scalars().all()]
        assert names == ["Sam"]                                                             # the actor only the ghost introduced is gone; the one an earlier run knew stays
        asks = [r.text for r in (await db.execute(select(StandingRequest).where(StandingRequest.owner_peer_id == OWNER))).scalars().all()]
        assert asks == ["Call me Kai"]       # the retracted run's messages are uncovered again: re-derivable
        row = (await db.execute(select(SceneNarrative).where(SceneNarrative.honcho_workspace_id == WS))).scalars().first()
        assert row.text == "" and json.loads(row.pending_json) == [] and [a["id"] for a in json.loads(row.anchors_json)] == ["a1"]
