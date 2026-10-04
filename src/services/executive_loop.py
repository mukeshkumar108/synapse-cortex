"""Background driver for the executive tick: a cheap SQL scan every minute; the model runs only for worlds with a due wake (see executive.tick)."""
import asyncio
import logging
import os

from src.db import async_session_maker

logger = logging.getLogger(__name__)
TICK_SECONDS = float(os.getenv("EXECUTIVE_TICK_SECONDS", "60"))


async def run_forever() -> None:
    from src.runtime_model import get_agenda_adapter
    from src.services import executive
    await asyncio.sleep(20)                  # let the service finish starting
    while True:
        try:
            adapter = get_agenda_adapter()
            if adapter is not None:
                async with async_session_maker() as db:
                    result = await executive.tick(db, adapter=adapter)
                    if result["ran"]:
                        logger.info("executive tick: %s", result)
        except asyncio.CancelledError:
            raise
        except Exception as exc:             # the loop must outlive any single failure
            logger.warning("executive tick failed: %s", exc)
        await asyncio.sleep(TICK_SECONDS)
