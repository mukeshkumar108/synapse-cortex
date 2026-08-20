from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SuppressionTarget(str, Enum):
    EXPECTATION = "expectation"
    OPEN_LOOP = "open_loop"
    TOPIC = "topic"
    ENTITY = "entity"
    HONCHO_REF = "honcho_ref"


class SuppressionStatus(str, Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REOPENED = "reopened"


class Suppression(SQLModel, table=True):
    __tablename__ = "suppressions"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_message_id", "candidate_key",
            name="uq_suppression_workspace_message_candidate",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    candidate_key: str = Field(default="primary", nullable=False)
    
    target_type: SuppressionTarget = Field(
        default=SuppressionTarget.TOPIC,
        sa_column=Column(SAEnum(SuppressionTarget, native_enum=False), nullable=False),
    )
    target_id: Optional[str] = Field(default=None, index=True)
    topic_or_entity: Optional[str] = Field(default=None, index=True)
    reason: str = Field(nullable=False)
    
    suppressed_until: Optional[datetime] = Field(default=None, index=True)
    reopen_condition: Optional[str] = Field(default=None)
    status: SuppressionStatus = Field(
        default=SuppressionStatus.ACTIVE,
        sa_column=Column(SAEnum(SuppressionStatus, native_enum=False), nullable=False, index=True),
    )
    
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)
