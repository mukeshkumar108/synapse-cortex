"""Step 3A entity continuity: exact-match resolution with provisional discipline.

Rules (no semantic guessing, no keyword mention-mining):
- exact normalized-alias match within frame scope: 0 hits -> provisional
  (callers invoke this only for mentions attached to rows being persisted,
  so participation in durable state is proven by construction);
  1 hit -> link; >1 hits -> ambiguous, link nothing (3B merge decides).
- explicit naming assertions ("his name is Leo", "call me Kai") attach the
  new name as an alias to the single recent role-described provisional
  entity in the session; otherwise the named mention becomes its own
  provisional entity. This is speech-act syntax handling, documented here,
  not semantic classification.
- same alias in different frames never auto-merges (frame_scope part of
  lookup); same alias twice in one frame stays linkable to two entities
  (no unique constraint) — disambiguation is 3B's job.
"""
import re
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.identity import Entity, EntityAlias

_NAMING_RE = re.compile(
    r"\b(?:his|her|their|my|your|our)\s+name\s+is\s+([A-Z][A-Za-z'-]+)"
)
_ROLE_LIKE_RE = re.compile(
    r"^(my|her|his|their|your|our|the)\s+[a-z]+", re.IGNORECASE
)
# Closed generic set: role words that never denote a resolvable referent.
# (Pronouns/role fillers, not semantic classification.)
_GENERIC_REFS = frozenset({
    "user", "assistant", "speaker", "listener", "someone", "everyone",
    "everybody", "nobody", "anyone", "you", "they", "he", "she", "it",
    "we", "them", "us",
})
_PROPER_NAME_RE = re.compile(r"^[A-Z][A-Za-z'-]+$")
# Possessive role phrases denote someone's person ("my brother"); bare
# "the X" forms ("the house") do not — they provision nothing.
_POSSESSIVE_ROLE_RE = re.compile(
    r"^(my|her|his|their|your|our)\s+[a-z]+", re.IGNORECASE
)


def normalize_alias(value: str) -> str:
    return " ".join((value or "").split()).lower()


async def find_entities(
    db: AsyncSession, *, workspace_id: str, alias: str,
    frame: Optional[str] = None,
) -> List[Entity]:
    norm = normalize_alias(alias)
    if not norm:
        return []
    rows = (await db.execute(
        select(Entity, EntityAlias)
        .join(EntityAlias, EntityAlias.entity_id == Entity.id)
        .where(
            Entity.honcho_workspace_id == workspace_id,
            EntityAlias.alias == norm,
        )
    )).all()
    entities = []
    for entity, _alias in rows:
        if entity in entities:
            continue
        if frame and entity.frame_scope and entity.frame_scope != frame:
            continue
        entities.append(entity)
    return entities


async def _provision(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    display_name: str, frame: Optional[str], message_id: str,
    entity_type: str = "person", confidence: float = 0.6,
) -> Entity:
    from src.models.identity import utc_now
    entity = Entity(
        honcho_workspace_id=workspace_id, entity_type=entity_type,
        display_name=display_name.strip(), frame_scope=frame,
        first_seen_message_id=message_id, confidence=confidence,
        provisional=True,
    )
    db.add(entity)
    await db.flush()
    db.add(EntityAlias(
        entity_id=entity.id, alias=normalize_alias(display_name),
        provenance_message_id=message_id,
    ))
    await db.commit()
    await db.refresh(entity)
    return entity


async def resolve_mention(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    mention: str, frame: Optional[str], message_id: str,
) -> Tuple[Optional[Entity], str]:
    """Returns (entity, status) with status in linked/provisioned/ambiguous/skipped.

    Provisioning gate: unknown mentions become provisional entities ONLY when
    shaped like a proper name ("Ashley", "Leo") or a possessive role phrase
    ("my brother"). Bare topics, things and generic role words ("tabs",
    "love", "the house", "you") resolve against existing entities or are
    skipped — never provisioned. Callers invoke this per persisted row, so
    participation in durable state is proven by construction.
    """
    norm = normalize_alias(mention)
    if not norm or norm in _GENERIC_REFS:
        return None, "skipped"
    hits = await find_entities(db, workspace_id=workspace_id, alias=mention, frame=frame)
    if len(hits) == 1:
        return hits[0], "linked"
    if len(hits) > 1:
        return None, "ambiguous"
    if _PROPER_NAME_RE.match(mention.strip()) or _POSSESSIVE_ROLE_RE.match(mention.strip()):
        entity = await _provision(
            db, workspace_id=workspace_id, session_id=session_id,
            display_name=mention.strip(), frame=frame, message_id=message_id)
        return entity, "provisioned"
    return None, "skipped"


async def apply_naming_assertion(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    text: str, message_id: str, frame: Optional[str] = None,
) -> Optional[Entity]:
    """'His name is Leo' attaches Leo to the single recent role-described
    provisional entity in the session. Anything else -> None (caller falls
    back to normal mention resolution, i.e. a separate provisional)."""
    match = _NAMING_RE.search(text or "")
    if not match:
        return None
    name = match.group(1)
    recent = (await db.execute(
        select(Entity)
        .where(
            Entity.honcho_workspace_id == workspace_id,
            Entity.provisional == True,  # noqa: E712
        )
        .order_by(Entity.created_at.desc())
        .limit(5)
    )).scalars().all()
    role_like = [e for e in recent if _ROLE_LIKE_RE.match(e.display_name or "")]
    if len(role_like) != 1:
        return None
    entity = role_like[0]
    exists = (await db.execute(select(EntityAlias).where(
        EntityAlias.entity_id == entity.id,
        EntityAlias.alias == normalize_alias(name),
    ))).scalar_one_or_none()
    if exists is None:
        db.add(EntityAlias(entity_id=entity.id, alias=normalize_alias(name),
                           provenance_message_id=message_id))
        await db.commit()
    return entity


async def link_object(
    db: AsyncSession, *, workspace_id: str, object_type: str,
    object_id: UUID, role: str, entity_id: UUID,
    confidence: float, message_id: Optional[str] = None,
) -> None:
    from src.models.identity import EntityLink
    db.add(EntityLink(
        honcho_workspace_id=workspace_id, object_type=object_type,
        object_id=object_id, role=role, entity_id=entity_id,
        confidence=confidence, provenance_message_id=message_id,
    ))
    await db.commit()


async def describe_entity(db: AsyncSession, entity_id: UUID) -> dict:
    """Projection across linked primitive state (query helper, not a store)."""
    from src.models.identity import EntityLink
    links = (await db.execute(select(EntityLink).where(
        EntityLink.entity_id == entity_id))).scalars().all()
    return {
        "entity_id": str(entity_id),
        "links": [
            {"object_type": link.object_type, "object_id": str(link.object_id),
             "role": link.role, "confidence": link.confidence}
            for link in links
        ],
    }


async def link_candidate_subjects(
    db: AsyncSession, *, workspace_id: str, session_id: str,
    object_type: str, object_id: UUID, refs: list,
    frame: str | None, message_id: str, confidence: float = 0.7,
) -> list:
    """Link a persisted row's subject refs to entities. refs come from the
    extractor's subject_refs array; each resolves via resolve_mention (exact
    match links, shaped unknowns provision, everything else skips). Returns
    the linked entities."""
    from uuid import UUID as _UUID
    linked = []
    for ref in (refs or [])[:8]:
        if not isinstance(ref, str) or not ref.strip():
            continue
        entity, status = await resolve_mention(
            db, workspace_id=workspace_id, session_id=session_id,
            mention=ref, frame=frame, message_id=message_id)
        if entity is None or status not in ("linked", "provisioned"):
            continue
        await link_object(
            db, workspace_id=workspace_id, object_type=object_type,
            object_id=object_id, role="subject", entity_id=entity.id,
            confidence=confidence if status == "linked" else 0.5,
            message_id=message_id)
        linked.append(entity)
    return linked


async def revise_edge(
    db: AsyncSession, *, edge_id, new_role: str,
    message_id: str | None = None, confidence: float = 0.8,
) -> "RelationshipEdge":
    """Structural revision without rewriting history: close the old edge
    (end_at) and open a successor row ("my friend Sarah" -> "my ex Sarah")."""
    from datetime import datetime, timezone
    from src.models.identity import RelationshipEdge
    old = await db.get(RelationshipEdge, edge_id)
    if old is None:
        raise ValueError(f"unknown edge {edge_id}")
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    old.end_at = now
    old.updated_at = now
    db.add(old)
    new_edge = RelationshipEdge(
        honcho_workspace_id=old.honcho_workspace_id,
        from_entity_id=old.from_entity_id, to_entity_id=old.to_entity_id,
        role=new_role, provenance_message_id=message_id,
        confidence=confidence, effective_at=now,
    )
    db.add(new_edge)
    await db.commit()
    await db.refresh(new_edge)
    return new_edge


async def get_or_create_edge(
    db: AsyncSession, *, workspace_id: str, from_entity_id,
    to_entity_id, role: str, message_id: str | None = None,
    confidence: float = 0.8,
) -> tuple:
    """Idempotent relationship edge: same (from, to, active role) returns the
    existing row; a different role for the same pair should use revise_edge."""
    from src.models.identity import RelationshipEdge
    existing = (await db.execute(select(RelationshipEdge).where(
        RelationshipEdge.honcho_workspace_id == workspace_id,
        RelationshipEdge.from_entity_id == from_entity_id,
        RelationshipEdge.to_entity_id == to_entity_id,
        RelationshipEdge.role == role,
        RelationshipEdge.end_at.is_(None),
    ))).scalar_one_or_none()
    if existing is not None:
        return existing, False
    edge = RelationshipEdge(
        honcho_workspace_id=workspace_id, from_entity_id=from_entity_id,
        to_entity_id=to_entity_id, role=role,
        provenance_message_id=message_id, confidence=confidence,
    )
    db.add(edge)
    await db.commit()
    await db.refresh(edge)
    return edge, True
