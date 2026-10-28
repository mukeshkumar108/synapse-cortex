"""Notes: the one thing a sitting writes. Dated, append-only sentences about a subject, each carrying the life area it touches and how sure the
person was. Everything else (patterns, people, cards, things worth asking) is a QUERY over these rows, never another model pass.

Lossy on purpose: a note is what a close friend would still remember, with the person's own words beside it so a wrong reading can be seen and
corrected. Corrections supersede (history kept); nothing is rewritten in place."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID, uuid4

from sqlmodel import Field, SQLModel

from src.models.world import utc_now


class Note(SQLModel, table=True):
    __tablename__ = "notes"

    id: UUID = Field(default_factory=uuid4, primary_key=True)
    honcho_workspace_id: str = Field(index=True, nullable=False)
    owner_peer_id: Optional[str] = Field(default=None, index=True)
    product: str = Field(default="sophie", index=True, nullable=False)
    run_id: Optional[UUID] = Field(default=None, index=True)
    session_id: str = Field(default="", index=True)
    sitting_on: datetime = Field(nullable=False, index=True)                # the person's local date of the sitting
    subject: str = Field(nullable=False)                                    # "the person", or the name used for someone/something else
    subject_key: str = Field(default="", index=True, nullable=False)        # normalised, for grouping
    area: str = Field(default="other", index=True, nullable=False)          # one of notes.AREAS (the shared headings)
    certainty: str = Field(default="stated", index=True, nullable=False)    # stated | intention | hypothetical | hearsay | unclear
    when_on: Optional[datetime] = Field(default=None)                       # the day the note is about, when it is about a particular day
    key: str = Field(default="", index=True, nullable=False)                # standing facts only (birthday, residence): a later note with the same key replaces it
    text: str = Field(nullable=False)
    quote: str = Field(default="")                                          # the person's own words, copied exactly
    quote_verified: bool = Field(default=False)                             # the quote was found in the person's own lines
    source: str = Field(default="session")                                  # session | import
    status: str = Field(default="current", index=True, nullable=False)      # current | superseded | resolved
    replaced_by_id: Optional[UUID] = Field(default=None)
    created_at: datetime = Field(default_factory=utc_now, nullable=False)
