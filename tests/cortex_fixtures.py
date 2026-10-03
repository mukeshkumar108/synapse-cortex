"""Shared builders for the Cortex cutover tests (Matter / WorldModel /
projections / attention / coverage / acceptance). Rows are written the way
production writers write them; only timestamps are controlled."""
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from src.db import async_session_maker
from src.models.commitment_candidate import CommitmentCandidate
from src.models.domain_annotation import CategoryTag, DomainAnnotation, DomainTag
from src.models.expectation import Expectation, ExpectationType, OutcomeState
from src.models.fact import Fact
from src.models.identity import Entity, EntityLink
from src.models.open_loop import OpenLoop, OpenLoopStatus
from src.models.operational_state import RecurringIntention
from src.models.work_item import WorkItem

WS = "ws-cortex"
USER = "user_kai"
SYSTEM = "sophie"
NOW = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)


def naive(dt: datetime) -> datetime:
    return dt.astimezone(timezone.utc).replace(tzinfo=None) if dt.tzinfo else dt


def ago(days: float = 0, hours: float = 0, now: datetime = NOW) -> datetime:
    return naive(now) - timedelta(days=days, hours=hours)


async def save(*rows: Any) -> None:
    async with async_session_maker() as db:
        db.add_all(rows)
        await db.commit()


def exp(title: str, *, owner: str = USER, session: str = "lane-1", message: Optional[str] = None,
        summary: str = "", etype: ExpectationType = ExpectationType.USER_INTENTION,
        outcome: OutcomeState = OutcomeState.UNKNOWN, created: Optional[datetime] = None,
        window_start: Optional[datetime] = None, window_end: Optional[datetime] = None,
        deadline: Optional[datetime] = None, formation: str = "explicit",
        key: str = "primary", **kw: Any) -> Expectation:
    created = created or ago(1)
    return Expectation(
        honcho_workspace_id=WS, honcho_session_id=session,
        honcho_message_id=message or f"m-{uuid4().hex[:8]}", owner_peer_id=owner,
        candidate_key=key, subject_peer_id=owner, expectation_type=etype, title=title,
        summary=summary or title, outcome_state=outcome, formation=formation,
        expected_window_start=window_start, expected_window_end=window_end,
        hard_deadline_at=deadline, created_at=created, updated_at=created, **kw)


def loop(title: str, *, owner: str = USER, session: str = "lane-1", message: Optional[str] = None,
         summary: str = "", status: OpenLoopStatus = OpenLoopStatus.OPEN,
         created: Optional[datetime] = None, invited: bool = False,
         expectation_id: Any = None, key: str = "primary") -> OpenLoop:
    created = created or ago(1)
    return OpenLoop(
        honcho_workspace_id=WS, honcho_session_id=session,
        honcho_message_id=message or f"m-{uuid4().hex[:8]}", owner_peer_id=owner,
        candidate_key=key, title=title, summary=summary or title, status=status,
        invited=invited, expectation_id=expectation_id, created_at=created, updated_at=created)


def recurrence(title: str, ckey: str, *, owner: str = USER, session: str = "lane-1",
               cadence: str = "daily", semantic_type: str = "recurring_action",
               preferred_window: Optional[str] = None, created: Optional[datetime] = None,
               slot: str = "active") -> RecurringIntention:
    created = created or ago(10)
    return RecurringIntention(
        honcho_workspace_id=WS, honcho_session_id=session,
        honcho_message_id=f"m-{uuid4().hex[:8]}", owner_peer_id=owner,
        candidate_key=f"c-{uuid4().hex[:6]}", canonical_key=ckey, active_slot=slot,
        title=title, cadence=cadence, semantic_type=semantic_type,
        preferred_window=preferred_window, source_evidence=title,
        created_at=created, updated_at=created)


def commitment(title: str, *, owner: str = USER, session: str = "lane-1",
               evidence_class: str = "implicit_self_commitment",
               created: Optional[datetime] = None, canonical_key: Optional[str] = None
               ) -> CommitmentCandidate:
    created = created or ago(1)
    return CommitmentCandidate(
        honcho_workspace_id=WS, honcho_session_id=session, owner_peer_id=owner,
        candidate_key=f"k-{uuid4().hex[:8]}", canonical_key=canonical_key or uuid4().hex[:12],
        title=title, evidence_verbatim=title, evidence_class=evidence_class,
        source_message_id=f"m-{uuid4().hex[:8]}", created_at=created, updated_at=created)


def work_item(parent_type: str, parent_id: Any, action: str, *, owner: str = "user",
              importance: float = 0.5, created: Optional[datetime] = None) -> WorkItem:
    created = created or ago(1)
    return WorkItem(
        honcho_workspace_id=WS, owner_peer_id=USER, parent_type=parent_type,
        parent_id=str(parent_id), parent_title=None, owner=owner, action=action,
        importance=importance, created_at=created, updated_at=created)


def entity(name: str, etype: str = "person") -> Entity:
    return Entity(honcho_workspace_id=WS, entity_type=etype, display_name=name,
                  provisional=False)


def link(object_type: str, object_id: Any, entity_id: Any, role: str = "subject") -> EntityLink:
    return EntityLink(honcho_workspace_id=WS, object_type=object_type, object_id=object_id,
                      role=role, entity_id=entity_id)


def annotation(message: str, domain: DomainTag, category: CategoryTag, summary: str,
               session: str = "lane-1", key: str = "primary") -> DomainAnnotation:
    return DomainAnnotation(honcho_workspace_id=WS, honcho_session_id=session,
                            honcho_message_id=message, candidate_key=key, domain=domain,
                            category=category, annotation_summary=summary)


def fact(title: str, *, owner: str = USER, session: str = "lane-1", message: Optional[str] = None,
         category: str = "general", key: str = "primary") -> Fact:
    # Pinned to the fixture clock (not the wall clock): unpinned, these rows only fell inside the fixture's "today" on the
    # day the tests were written, so the today-projection tests silently started failing a day later.
    when = ago(hours=1)
    return Fact(honcho_workspace_id=WS, honcho_session_id=session,
                honcho_message_id=message or f"m-{uuid4().hex[:8]}", owner_peer_id=owner,
                candidate_key=key, category=category, title=title, evidence_verbatim=title,
                created_at=when, updated_at=when)


async def settle(owner=USER, now=NOW):
    """The mutation boundary (what sweeper/consolidation/backfill do):
    reconcile primitives into Matters. Reads never do this."""
    from src.services import matter_service
    async with async_session_maker() as db:
        return await matter_service.sync_primitives(db, workspace_id=WS, owner_peer_id=owner, now=now)


# ---------------------------------------------------------------------------
# Realistic longitudinal world: "Kai", ~6 weeks of state across several lanes.
# Product-agnostic on purpose (no product-specific kinds or truth).
# ---------------------------------------------------------------------------
async def build_longitudinal_world() -> dict:
    """Write one person's world the way production writers do. Returns ids."""
    from src.models.identity import ModelEntry, RelationshipEdge
    from src.models.suppression import Suppression, SuppressionTarget
    from src.models.operational_state import TurnStamp
    from src.models.expectation import OutcomeState as O

    ids: dict = {}
    from src.models.identity import EntityAlias
    ashley, mati, carlos, mum = entity("Ashley"), entity("Mati"), entity("Carlos"), entity("Mum")
    await save(ashley, mati, carlos, mum)
    await save(*[EntityAlias(entity_id=e.id, alias=n) for e, n in
                 ((ashley, "ashley"), (mati, "mati"), (carlos, "carlos"), (mum, "mum"))])
    ids.update(ashley=ashley.id, mati=mati.id, carlos=carlos.id, mum=mum.id)
    await save(RelationshipEdge(honcho_workspace_id=WS, from_entity_id=ashley.id, to_entity_id=mum.id,
                                role="partner_of_user_context"),
               RelationshipEdge(honcho_workspace_id=WS, from_entity_id=carlos.id, to_entity_id=mum.id,
                                role="client"))

    # facts (settled background)
    await save(fact("Grew up in Leeds", category="biography", message="f1"),
               fact("Freelance designer", category="vocation", message="f2"),
               fact("Mum lives in Spain", category="family", message="f3"))

    # routines: declared (with and without timing) vs observed
    walk = recurrence("Walk every morning", "walk_morning", created=ago(30))
    med = recurrence("Evening meditation", "meditation_evening", preferred_window="evening", created=ago(25))
    gym = recurrence("Gym on weekdays", "gym_weekdays", semantic_type="observed_pattern", created=ago(20))
    await save(walk, med, gym)
    ids.update(walk=walk.id, meditation=med.id, gym=gym.id)

    # forward obligations / events
    pres = exp("Client presentation", etype=ExpectationType.PLANNED_EVENT, message="e-pres",
               created=ago(3), window_start=naive(NOW) + timedelta(hours=4),
               window_end=naive(NOW) + timedelta(hours=5), deadline=naive(NOW) + timedelta(hours=4))
    invoice = exp("Send invoice to Carlos", etype=ExpectationType.USER_COMMITMENT, message="e-inv",
                  created=ago(4), deadline=naive(NOW) + timedelta(days=2),
                  window_end=naive(NOW) + timedelta(days=2))
    call_mum = exp("Call Mum on Sunday", message="e-mum", created=ago(2), raw_temporal_phrase="on Sunday",
                   window_start=naive(NOW) + timedelta(days=3), window_end=naive(NOW) + timedelta(days=3, hours=12))
    dentist = exp("Dentist appointment", etype=ExpectationType.PLANNED_EVENT, message="e-dent",
                  created=ago(6), window_start=ago(1, 2), window_end=ago(1, 1),
                  raw_temporal_phrase="yesterday afternoon")
    logo = exp("Finish logo draft", message="e-logo", created=ago(9), outcome=O.FULFILLED)
    logo.updated_at = ago(2)
    flat = exp("Decide which flat to rent", message="e-flat", created=ago(12))
    await save(pres, invoice, call_mum, dentist, logo, flat)
    ids.update(pres=pres.id, invoice=invoice.id, call_mum=call_mum.id, dentist=dentist.id,
               logo=logo.id, flat=flat.id)
    await save(link("expectation", invoice.id, carlos.id), link("expectation", call_mum.id, mum.id))

    # unresolved loops: concern (Ashley, tagged), contractor payment, user->system invitation
    ash_loop = loop("Conversation with Ashley about feeling unheard", message="l-ash", created=ago(5))
    pay = loop("Carlos payment still outstanding", message="l-pay", created=ago(8),
               expectation_id=invoice.id)
    report = loop("Report back after the dentist", message="l-rep", created=ago(6), invited=True)
    await save(ash_loop, pay, report)
    await save(link("open_loop", ash_loop.id, ashley.id), link("open_loop", pay.id, carlos.id),
               annotation("l-ash", DomainTag_REL, CategoryTag_STRUGGLE, "Kai feels unheard by Ashley"))
    ids.update(ash_loop=ash_loop.id, pay=pay.id, report=report.id)
    # Mati: mentioned in several places, never stated who he is (a useful gap)
    mati_loop = loop("Mati's news about the new job", message="l-mati", created=ago(4))
    mati_trip = exp("Visit Mati in Manchester", message="e-mati", created=ago(3), raw_temporal_phrase="next week",
                    window_start=naive(NOW) + timedelta(days=5), window_end=naive(NOW) + timedelta(days=6))
    await save(mati_loop, mati_trip)
    await save(link("open_loop", mati_loop.id, mati.id), link("expectation", mati_trip.id, mati.id))
    ids.update(mati_loop=mati_loop.id, mati_trip=mati_trip.id)

    # system -> user: Sophie's promise, owed work
    promise = commitment("Check in after the presentation", owner=SYSTEM, evidence_class="character_promise",
                         created=ago(1))
    wi = work_item("expectation", pres.id, "Find a short stretch video for before the presentation",
                   owner="sophie", importance=0.7)
    await save(promise, wi)
    ids.update(promise=promise.id, work=wi.id)

    # epistemic claims
    def claim(text, *, kind="user", claim_kind=None, formation="explicit", conf=1.0, subj=None,
              holder=None, direction=None, status="current", created=None, refs=None, msg=None):
        created = created or ago(2)
        return ModelEntry(
            honcho_workspace_id=WS, honcho_session_id="lane-1", honcho_message_id=msg or f"c-{uuid4().hex[:6]}",
            owner_peer_id=USER, subject_entity_id=subj, model_kind=kind, claim=text,
            evidence_verbatim=text, formation=formation, confidence=conf, claim_kind=claim_kind,
            holder_actor=holder, direction=direction, epistemic_status=status,
            evidence_refs_json=__import__("json").dumps(refs or []), created_at=created, updated_at=created)
    reported = claim("Kai has repeatedly reported feeling that Ashley defended her actions rather than "
                     "acknowledging hurt", kind="relationship", claim_kind="relationship_development",
                     formation="reported", conf=0.9, subj=ashley.id, msg="l-ash", refs=["l-ash", "l-ash2"])
    pattern = claim("Kai tends to skip workouts after late nights", claim_kind="pattern",
                    formation="observed", conf=0.6, msg="c-pat")
    perspective = claim("Sophie wonders whether Kai is overextended this month", claim_kind="perspective",
                        formation="hypothesis", conf=0.4, holder="system", direction="system_to_user",
                        msg="c-persp")
    firm = claim("Kai does not drink coffee", formation="explicit", conf=1.0, status="conflicting",
                 msg="c-coffee", created=ago(10))
    soft = claim("Kai drinks coffee most mornings", formation="inferred", conf=0.5, status="conflicting",
                 msg="c-coffee2", created=ago(3))
    repair = claim("Sophie's reminder on Monday felt pushy to Kai; not yet repaired", kind="relationship",
                   claim_kind="repair", formation="reported", conf=0.8, direction="shared", msg="c-rep",
                   created=ago(3))
    await save(reported, pattern, perspective, firm, soft, repair)
    ids.update(reported=reported.id, pattern=pattern.id, perspective=perspective.id,
               firm=firm.id, soft=soft.id, repair=repair.id)

    # explicit boundary
    await save(Suppression(honcho_workspace_id=WS, honcho_session_id="lane-1", honcho_message_id="s1",
                           owner_peer_id=USER, target_type=SuppressionTarget.TOPIC,
                           topic_or_entity="the divorce", reason="user asked not to raise it",
                           surface_scope="all_surfaces"))
    # user turns across the weeks (chronology)
    for i, d in enumerate((40, 20, 9, 3, 1, 0)):
        await save(TurnStamp(honcho_workspace_id=WS, owner_peer_id=USER, honcho_message_id=f"t{i}",
                             turn_at=ago(d, 1)))
    await settle()
    return ids


from src.models.domain_annotation import CategoryTag as _C, DomainTag as _D  # noqa: E402
DomainTag_REL, CategoryTag_STRUGGLE = _D.RELATIONSHIP, _C.STRUGGLE
