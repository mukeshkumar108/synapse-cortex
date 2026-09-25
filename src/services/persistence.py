import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.expectation import Expectation, OutcomeState
from src.models.fact import Fact

logger = logging.getLogger(__name__)


async def get_expectation_by_message_id(
    session: AsyncSession, workspace_id: str, honcho_message_id: str,
    candidate_key: str = "primary"
) -> Optional[Expectation]:
    """Retrieve one extracted candidate from a Honcho message."""
    stmt = select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.honcho_message_id == honcho_message_id,
        Expectation.candidate_key == candidate_key,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def save_expectation_idempotent(
    session: AsyncSession,
    expectation_data: dict,
    *,
    grounding_now: datetime | None = None,
) -> Tuple[Expectation, bool]:
    """
    Saves an expectation in an idempotent manner.
    If an expectation with the same `honcho_message_id` exists, returns (existing, False).
    Otherwise creates and returns (new_expectation, True).
    """
    message_id = expectation_data["honcho_message_id"]
    workspace_id = expectation_data["honcho_workspace_id"]
    candidate_key = expectation_data.get("candidate_key", "primary")
    existing = await get_expectation_by_message_id(
        session, workspace_id, message_id, candidate_key
    )
    if existing:
        logger.info("Idempotent hit for honcho_message_id=%s", message_id)
        return existing, False

    # Conversational reminder synthesis: explicit "remind me ..." intent with a
    # grounded window becomes an executable reminder window at persistence time
    # (previously only source-linked app objects got windows, so conversational
    # reminders were stored but could never fire).
    if not expectation_data.get("reminder_windows_json"):
        blob = f"{expectation_data.get('title', '')} {expectation_data.get('summary', '')}".lower()
        window_start = expectation_data.get("expected_window_start")
        reminder_flag = expectation_data.get("reminder_requested")
        etype = str(expectation_data.get("expectation_type") or "").lower()
        phrase = expectation_data.get("raw_temporal_phrase")
        # Time-grounded commitments and intentions get exactly one outcome
        # check by default ("she comes back and asks"). The interpreter's
        # explicit false still opts out; explicit true always applies.
        if reminder_flag is None and etype in ("user_commitment", "user_intention") and phrase:
            reminder_flag = True
        # Second-chance grounding at the commit boundary: the creation path
        # sometimes fails to bind the window even when a temporal phrase
        # exists. Re-ground once here before deciding.
        if reminder_flag and window_start is None and phrase:
            from src.services.temporal_grounding import TemporalGrounding
            try:
                anchor_tz = expectation_data.get("anchor_timezone") or "UTC"
                re_start, re_end, _ = TemporalGrounding().ground_expression(
                    raw_phrase=phrase,
                    now=grounding_now or datetime.now(timezone.utc),
                    timezone_str=anchor_tz,
                )
                if re_start:
                    expectation_data["expected_window_start"] = re_start
                    expectation_data["expected_window_end"] = re_end
                    window_start = re_start
            except Exception:
                pass
        if reminder_flag and window_start is not None:
            start = window_start if window_start.tzinfo is None else window_start.astimezone(timezone.utc).replace(tzinfo=None)
            window_end = expectation_data.get("expected_window_end") or window_start
            end = window_end if window_end.tzinfo is None else window_end.astimezone(timezone.utc).replace(tzinfo=None)
            if end <= start:
                end = start + timedelta(hours=12)
            expectation_data["reminder_windows_json"] = json.dumps([{
                "start": start.isoformat(), "end": end.isoformat(),
                "label": expectation_data.get("raw_temporal_phrase") or "reminder",
            }])

    expectation = Expectation(**expectation_data)
    session.add(expectation)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await get_expectation_by_message_id(
            session, workspace_id, message_id, candidate_key
        )
        if existing:
            return existing, False
        raise
    await session.refresh(expectation)
    prior_rows = (await session.execute(select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.honcho_message_id == message_id,
        Expectation.id != expectation.id,
        Expectation.superseded_by_id.is_(None),
    ))).scalars().all()
    for prior in prior_rows:
        equivalent = (
            prior.expectation_type == expectation.expectation_type
            and prior.subject_peer_id.lower() == expectation.subject_peer_id.lower()
            and prior.title.lower() == expectation.title.lower()
        )
        if equivalent:
            prior.outcome_state = OutcomeState.SUPERSEDED
            prior.superseded_by_id = expectation.id
            prior.resolution_evidence = f"extractor_reconciliation:{expectation.extractor_version}"
            session.add(prior)
    if prior_rows:
        await session.commit()
    logger.info("Created new expectation id=%s for message_id=%s", expectation.id, message_id)
    return expectation, True


async def save_fact_idempotent(session: AsyncSession, fact_data: dict) -> Tuple[Fact, bool]:
    """Idempotent fact write keyed on (workspace, message, candidate_key).

    Facts are holder-scoped settled content (health, biography, grief history,
    vocation). They never participate in expectation supersession, outcome
    lifecycle or violation derivation — they are evidence the rest of the
    substrate reads, including later dreaming cognition.
    """
    existing = (await session.execute(select(Fact).where(
        Fact.honcho_workspace_id == fact_data["honcho_workspace_id"],
        Fact.honcho_message_id == fact_data["honcho_message_id"],
        Fact.candidate_key == fact_data.get("candidate_key", "primary"),
    ))).scalar_one_or_none()
    if existing:
        return existing, False
    fact = Fact(**fact_data)
    session.add(fact)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = (await session.execute(select(Fact).where(
            Fact.honcho_workspace_id == fact_data["honcho_workspace_id"],
            Fact.honcho_message_id == fact_data["honcho_message_id"],
            Fact.candidate_key == fact_data.get("candidate_key", "primary"),
        ))).scalar_one_or_none()
        if existing:
            return existing, False
        raise
    await session.refresh(fact)
    logger.info("Created new fact id=%s for message_id=%s", fact.id, fact.honcho_message_id)
    return fact, True


async def save_model_entry(session: AsyncSession, entry_data: dict) -> Tuple["ModelEntry", bool]:
    """Idempotent Model-primitive write.

    Durable beliefs about a person/relationship (fear, preference, tendency,
    posture). Dedupe key is (workspace, message, normalized claim): the same
    claim re-evidenced is one row. Revised by supersession, never
    fulfilled/violated — no caller may route these rows into outcome
    transitions.
    """
    from src.models.identity import ModelEntry
    claim = str(entry_data.get("claim") or "").strip()
    if not claim:
        raise ValueError("model entry requires a claim")
    existing = (await session.execute(select(ModelEntry).where(
        ModelEntry.honcho_workspace_id == entry_data["honcho_workspace_id"],
        ModelEntry.honcho_message_id == entry_data["honcho_message_id"],
    ))).scalars().all()
    for row in existing:
        if row.claim.strip().lower() == claim.lower():
            return row, False
    entry = ModelEntry(**entry_data)
    session.add(entry)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise
    await session.refresh(entry)
    logger.info("Created new model entry id=%s for message_id=%s", entry.id, entry.honcho_message_id)
    return entry, True
