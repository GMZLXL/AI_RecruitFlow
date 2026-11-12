import asyncio
import logging

from app.integrations.wecom.config import enabled
from app.jobs.runtime import record_cycle
from app.services.notifications import generate_reminders, process_notification
from app.services.wecom import process_inbox


def worker_enabled():
    return enabled("WECOM_WORKER_ENABLED", "true")


async def wecom_loop(wakeup: asyncio.Event):
    last_reminders = 0
    while True:
        wakeup.clear()
        try:
            if asyncio.get_running_loop().time() - last_reminders >= 30:
                generate_reminders()
                last_reminders = asyncio.get_running_loop().time()
            for _ in range(10):
                if not await process_inbox():
                    break
            for _ in range(20):
                if not await process_notification():
                    break
            record_cycle("wecom", True)
        except Exception:
            record_cycle("wecom", False)
            logging.getLogger(__name__).error("wecom_worker_cycle_failed")
        try:
            await asyncio.wait_for(wakeup.wait(), timeout=2)
        except TimeoutError:
            pass
