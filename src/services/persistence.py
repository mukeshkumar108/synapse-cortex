import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple
from sqlmodel import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.expectation import Expectation, OutcomeState

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
    session: AsyncSession, expectation_data: dict
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
        if (expectation_data.get("reminder_requested") or "remind" in blob) and window_start is not None:
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
