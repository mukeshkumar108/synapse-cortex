from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DerivedSignalKind(str, Enum):
    SLEEP_EPISODE = "sleep_episode"
    SURFACE_COOLDOWN = "surface_cooldown"


class DerivedSignal(SQLModel, table=True):
    """Backstage derived signals with bounded persistence (one current row per
    kind + session). Evidence trails live in payload_json; the foreground
    consumer reads only the compact, decision-ready signal.
    """

    __tablename__ = "derived_signals"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_session_id", "kind",
            name="uq_derived_signal_workspace_session_kind",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    kind: DerivedSignalKind = Field(
        sa_column=Column(SAEnum(DerivedSignalKind, native_enum=False), nullable=False, index=True),
    )
    payload_json: str = Field(nullable=False)
    last_message_id: str = Field(nullable=False)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
    updated_at: datetime = Field(default_factory=utc_now, nullable=False)