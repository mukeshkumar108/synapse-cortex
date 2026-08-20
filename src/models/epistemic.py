from datetime import datetime, timezone
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4
from sqlmodel import Field, SQLModel
from sqlalchemy import Column, Enum as SAEnum, UniqueConstraint


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class EpistemicProvenance(str, Enum):
    DIRECT_STATEMENT = "direct_statement"
    REPORTED_STATEMENT = "reported_statement"
    ATTRIBUTED_BELIEF = "attributed_belief"
    OBSERVATION = "observation"
    INFERENCE = "inference"
    HYPOTHESIS = "hypothesis"
    PATTERN = "pattern"
    DERIVED_STATE = "derived_state"
    EXTERNAL_SOURCE = "external_source"


class EpistemicAnnotation(SQLModel, table=True):
    __tablename__ = "epistemic_annotations"
    __table_args__ = (
        UniqueConstraint(
            "honcho_workspace_id", "honcho_message_id", "candidate_key",
            name="uq_epistemic_workspace_message_candidate",
        ),
    )

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    
    honcho_workspace_id: str = Field(index=True, nullable=False)
    honcho_session_id: str = Field(index=True, nullable=False)
    honcho_message_id: str = Field(index=True, nullable=False)
    candidate_key: str = Field(default="primary", nullable=False)
    
    target_expectation_id: Optional[UUID] = Field(default=None, index=True)
    target_loop_id: Optional[UUID] = Field(default=None, index=True)
    
    perspective_peer_id: str = Field(index=True, nullable=False, description="Who holds/claims this belief e.g. mukesh")
    target_peer_id: Optional[str] = Field(default=None, index=True, description="Who this claim is about e.g. ashley")
    provenance_type: EpistemicProvenance = Field(
        default=EpistemicProvenance.DIRECT_STATEMENT,
        sa_column=Column(SAEnum(EpistemicProvenance, native_enum=False), nullable=False),
    )
    claim_summary: str = Field(nullable=False)
    confidence: float = Field(default=1.0, nullable=False)
    
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
