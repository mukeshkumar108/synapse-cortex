"""One-time repair: worlds interpreted before identities were pinned.

The first interpreter release was handed the speaker label "the user" and turned it into an actor literally named "the user". That string is an
artifact of our own pipeline (a default label), not a reading of anyone's prose, so repairing it is mechanical: pin that entity as the world's
`user_actor` placeholder, show it as "User (name not supplied)", and keep "the user" as an alias. Nothing is deleted or merged. When the product
later supplies the human's real name, `world_identity.ensure` renames the pinned actor (or pins an existing actor that already answers to the name).

Worlds whose human character was created as an ordinary named actor (no "the user" entity) need nothing here: the first turn that carries the
product-supplied name pins it by alias.

Usage (inside the Cortex container, so DATABASE_URL never leaves it):
    python scripts/repair_world_identities.py            # dry run: prints the plan
    python scripts/repair_world_identities.py --apply
"""
import argparse
import asyncio

from sqlmodel import select

from src.db import async_session_maker
from src.models.identity import Entity, EntityAlias
from src.models.world import WorldIdentity
from src.services import entity_service
from src.services.world_identity import PLACEHOLDER_USER_NAME, USER_ROLE

LEGACY_LABEL = "the user"


async def main(apply: bool) -> None:
    async with async_session_maker() as db:
        legacy = (await db.execute(select(Entity).where(Entity.frame_scope.like("world:%")))).scalars().all()
        legacy = [e for e in legacy if e.display_name.strip().lower() == LEGACY_LABEL]
        plan = []
        for ent in legacy:
            pinned = (await db.execute(select(WorldIdentity).where(
                WorldIdentity.honcho_workspace_id == ent.honcho_workspace_id, WorldIdentity.owner_peer_id == ent.frame_scope,
                WorldIdentity.role == USER_ROLE))).scalars().first()
            plan.append((ent, pinned))
        if not plan:
            print("nothing to repair")
            return
        for ent, pinned in plan:
            owner_short = (ent.frame_scope or "")[-40:]
            if pinned is not None:
                print(f"SKIP  {owner_short}: already pinned to entity {pinned.entity_id}")
                continue
            print(f"PIN   {owner_short}: entity {ent.id} '{ent.display_name}' -> user_actor placeholder '{PLACEHOLDER_USER_NAME}' (alias kept)")
            if not apply:
                continue
            have = {a.alias for a in (await db.execute(select(EntityAlias).where(EntityAlias.entity_id == ent.id))).scalars().all()}
            alias = entity_service.normalize_alias(LEGACY_LABEL)
            if alias not in have:
                db.add(EntityAlias(entity_id=ent.id, alias=alias, provenance_message_id="repair:legacy-label"))
            ent.display_name, ent.provisional = PLACEHOLDER_USER_NAME, True
            db.add(ent)
            db.add(WorldIdentity(honcho_workspace_id=ent.honcho_workspace_id, owner_peer_id=ent.frame_scope, role=USER_ROLE, entity_id=ent.id, name_supplied=False))
            await db.commit()
        print("applied" if apply else "dry run only (use --apply)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    asyncio.run(main(parser.parse_args().apply))
