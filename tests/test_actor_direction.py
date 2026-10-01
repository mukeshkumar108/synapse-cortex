"""Actor direction: user->system, system->user, shared, user_self, world —
derived structurally, stamped on insert, never flattened."""
import pytest
from sqlmodel import select

from src.db import async_session_maker
from src.models.attention_candidate import AttentionCandidate, AttentionCandidateKind
from src.models.expectation import Expectation, ExpectationType
from src.models.open_loop import OpenLoop
from src.services import actor_direction as ad
from tests.cortex_fixtures import (NOW, SYSTEM, USER, WS, ago, commitment, exp, loop, save,
                                   work_item, build_longitudinal_world)


def test_vocabulary_is_small_and_closed():
    assert ad.DIRECTIONS == {"user_to_system", "system_to_user", "shared", "user_self", "world"}


def test_structural_derivation_without_text_matching():
    assert ad.direction_from_row(exp("x", etype=ExpectationType.FOLLOWUP_INVITATION)) == "user_to_system"
    assert ad.direction_from_row(exp("x", etype=ExpectationType.EXTERNAL_DEPENDENCY)) == "world"
    assert ad.direction_from_row(exp("x", owner="external:bank")) == "world"
    assert ad.direction_from_row(exp("walk")) == "user_self"
    assert ad.direction_from_row(loop("x", invited=True)) == "user_to_system"
    assert ad.direction_from_row(loop("x")) == "user_self"
    assert ad.direction_from_row(commitment("x", evidence_class="character_promise")) == "system_to_user"
    assert ad.direction_from_row(commitment("x")) == "user_self"
    assert ad.direction_from_row(work_item("expectation", "p", "do", owner="sophie")) == "system_to_user"
    assert ad.direction_from_row(work_item("expectation", "p", "do", owner="user")) == "user_self"
    att = AttentionCandidate(honcho_workspace_id=WS, honcho_session_id="s", source_message_id="m",
                             candidate_key="k", kind=AttentionCandidateKind.PROMISE, content="c")
    assert ad.direction_from_row(att) == "system_to_user"


def test_wording_never_decides_direction():
    # "remind me" / "I'll check in" wording must not change the structural answer
    assert ad.direction_from_row(exp("Sophie will check in with me")) == "user_self"
    assert ad.direction_from_row(loop("please follow up with me")) == "user_self"


@pytest.mark.asyncio
async def test_direction_is_stamped_on_insert_and_explicit_value_wins():
    inv = loop("Report back after the dentist", invited=True)
    plain = exp("Finish report")
    predicted = exp("Kai will probably reschedule", formation="inferred")
    predicted.direction = "system_to_user"   # a system-held working prediction
    await save(inv, plain, predicted)
    async with async_session_maker() as db:
        got = {r.title: r.direction for r in (await db.execute(select(Expectation))).scalars().all()}
        lp = (await db.execute(select(OpenLoop))).scalars().all()[0]
    assert got["Finish report"] == "user_self"
    assert got["Kai will probably reschedule"] == "system_to_user"
    assert lp.direction == "user_to_system"


def test_effective_direction_recognises_system_held_rows_by_ownership_in_scope():
    e = exp("Follow up on interview", owner=SYSTEM)
    assert ad.effective_direction(e) == "user_self"                      # no scope knowledge
    assert ad.effective_direction(e, user_peer_id=USER) == "system_to_user"
    assert ad.effective_direction(exp("mine"), user_peer_id=USER) == "user_self"
    ext = exp("bank said", owner="external:bank")
    assert ad.effective_direction(ext, user_peer_id=USER) == "world"      # third parties are never "the system"


@pytest.mark.asyncio
async def test_sweeper_promise_is_system_to_user_not_user_self_commitment():
    from src.models.commitment_candidate import CommitmentCandidate
    from src.services.sweeper_service import SweeperService
    cand = {"valid": True, "kind": "sophie_promise", "title": "Sophie will push on daytime walks",
            "summary": "", "confidence": 0.85, "evidence_text": "I'll push you on the walks",
            "evidence_id": "e-prom", "evidence_session_id": "lane-1", "validation_notes": []}
    async with async_session_maker() as db:
        await SweeperService().promote(db, workspace_id=WS, peer_id=USER, candidates=[cand], now=NOW)
        row = (await db.execute(select(CommitmentCandidate))).scalars().one()
    assert row.evidence_class == "character_promise" and row.direction == "system_to_user"


@pytest.mark.asyncio
async def test_world_model_keeps_the_four_directions_apart():
    from src.services import world_model_service as wm
    await build_longitudinal_world()
    async with async_session_maker() as db:
        model = await wm.compile_world_model(db, workspace_id=WS, owner_peer_id=USER, now=NOW,
                                             timezone_str="Europe/London")
    rel = model["relationship_with_system"]
    assert any("Report back" in i["title"] for i in rel["user_to_system"])
    assert all(i["direction"] == "user_to_system" for i in rel["user_to_system"])
    owed = rel["system_to_user"]["commitments"]
    assert any("Check in after the presentation" in i["title"] for i in owed)
    assert all(i["direction"] == "system_to_user" and i.get("holder") == "system" for i in owed)
    assert any("Find a short stretch video" in (i["title"] + i.get("summary", "")) or "presentation" in i["title"].lower()
               for i in rel["system_to_user"]["commitments"])
    assert any("pushy" in i["title"] for i in rel["shared"]["repair"])
    # user->system request never leaks into what the system owes, and vice versa
    assert not {i["ref"] for i in rel["user_to_system"]} & {i["ref"] for i in owed}
    # system perspective stays in its own labelled section and out of world claims
    persp = model["system_perspective"]
    assert persp["actor"] == "system" and any("overextended" in e["title"] for e in persp["entries"])
    assert not any("overextended" in c["title"] for c in model["person"]["claims"])
