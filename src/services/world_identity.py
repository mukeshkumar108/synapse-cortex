"""Pinned world identities. The product says who the human's actor and the companion's actor are; Cortex pins them to stable entities for the
world and the interpreter references them by id. Nothing here reads prose: an unsupplied user identity is a typed placeholder, never a guess
and never an actor named "the user" invented from the dialogue."""
from __future__ import annotations

from typing import Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from src.models.identity import Entity, EntityAlias
from src.models.world import WorldIdentity
from src.services import entity_service

USER_ROLE, COMPANION_ROLE = "user_actor", "companion_actor"
PLACEHOLDER_USER_NAME = "User (name not supplied)"


async def ensure(db: AsyncSession, *, workspace_id: str, owner: str, session_id: str, user_name: Optional[str], companion_name: Optional[str],
                 first_message_id: str) -> Dict[str, Entity]:
    """Return {role: Entity} for the world, creating or renaming only on the product's say-so."""
    out: Dict[str, Entity] = {}
    rows = {r.role: r for r in (await db.execute(select(WorldIdentity).where(
        WorldIdentity.honcho_workspace_id == workspace_id, WorldIdentity.owner_peer_id == owner))).scalars().all()}
    wanted = {USER_ROLE: (user_name or "").strip() or None, COMPANION_ROLE: (companion_name or "").strip() or None}
    for role, name in wanted.items():
        row = rows.get(role)
        if row is None and name is None and role == COMPANION_ROLE:
            continue
        entity = await db.get(Entity, row.entity_id) if row is not None else None
        if entity is None and name is not None:
            # The product names this actor. If this world already holds exactly one entity answering to that name (created earlier by the
            # interpreter before identities were supplied), that IS the actor: pin it instead of minting a twin. Several matches = real
            # ambiguity: mint nothing guessed, pin a fresh entity and leave the older ones as they are.
            matches = await entity_service.find_entities(db, workspace_id=workspace_id, alias=name, frame=owner)
            taken = {r.entity_id for r in rows.values()}
            matches = [m for m in matches if m.id not in taken]
            if len(matches) == 1:
                entity = matches[0]
                entity.provisional = False
                db.add(entity)
                row = WorldIdentity(honcho_workspace_id=workspace_id, owner_peer_id=owner, role=role, entity_id=entity.id, name_supplied=True)
                db.add(row)
                await db.commit()
                out[role] = entity
                continue
        if entity is None:
            display = name or PLACEHOLDER_USER_NAME
            entity = await entity_service._provision(db, workspace_id=workspace_id, session_id=session_id, display_name=display, frame=owner,
                                                     message_id=first_message_id, entity_type="character" if role == COMPANION_ROLE else "person", confidence=1.0)
            entity.provisional = name is None
            db.add(entity)
            row = WorldIdentity(honcho_workspace_id=workspace_id, owner_peer_id=owner, role=role, entity_id=entity.id, name_supplied=name is not None)
            db.add(row)
            await db.commit()
        elif name is not None and (entity.display_name != name or not row.name_supplied):
            entity.display_name, entity.provisional = name, False        # the product is the authority on its own identities
            row.name_supplied = True
            alias = entity_service.normalize_alias(name)
            have = {a.alias for a in (await db.execute(select(EntityAlias).where(EntityAlias.entity_id == entity.id))).scalars().all()}
            if alias and alias not in have:
                db.add(EntityAlias(entity_id=entity.id, alias=alias, provenance_message_id=first_message_id))
            db.add(entity)
            db.add(row)
            await db.commit()
        out[role] = entity
    return out
