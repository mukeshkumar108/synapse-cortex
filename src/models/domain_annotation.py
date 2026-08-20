from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DomainTag(str, Enum):
    WORK = "work"
    RELATIONSHIP = "relationship"
    HEALTH = "health"
    FAMILY = "family"
    GOAL = "goal"
    DECISION = "decision"
    EMOTIONAL_LANDMARK = "emotional_landmark"


class CategoryTag(str, Enum):
    WIN = "win"
    ACCOMPLISHMENT = "accomplishment"
    STRUGGLE = "struggle"
    HOPE = "hope"
    FEAR = "fear"
    INSIDE_JOKE = "inside_joke"
    COMFORT_PREFERENCE = "comfort_preference"
    AVOID_TOPIC = "avoid_topic"
    ASK_ABOUT_LATER = "ask_about_later"


class DomainAnnotation(SQLModel, table=True):
    __tablename__ = "domain_annotations"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_message_id", "candidate_key",
            name="uq_domain_workspace_message_candidate",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    candidate_key: str = Field(default="primary", nullable=False)
    
    domain: DomainTag = Field(
        default=DomainTag.WORK,
        sa_column=Column(SAEnum(DomainTag, native_enum=False), nullable=False, index=True),
    )
    category: CategoryTag = Field(
        default=CategoryTag.WIN,
        sa_column=Column(SAEnum(CategoryTag, native_enum=False), nullable=False, index=True),
    )
    annotation_summary: str = Field(nullable=False)
    
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
