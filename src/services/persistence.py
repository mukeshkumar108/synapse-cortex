import logging
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


async def get_active_expectations_for_session(
    session: AsyncSession, workspace_id: str, session_id: str
) -> list[Expectation]:
    """Fetch all expectations for a given session."""
    stmt = select(Expectation).where(
        Expectation.honcho_workspace_id == workspace_id,
        Expectation.honcho_session_id == session_id,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
