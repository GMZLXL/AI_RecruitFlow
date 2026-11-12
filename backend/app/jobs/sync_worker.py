import asyncio
import logging
import os

from app.services.sync import process_batch


def worker_enabled() -> bool:
    return os.getenv("SYNC_WORKER_ENABLED", "true").lower() == "true"


async def sync_loop(wakeup: asyncio.Event):
    while True:
        wakeup.clear()
        try:
            await process_batch()
        except Exception:
            logging.getLogger(__name__).error("sync_worker_cycle_failed")
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=2)
        except TimeoutError:
            pass
