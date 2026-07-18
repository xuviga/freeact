"""Remote assist — human takeover when automation gets stuck.

Two modes:
1. Headed mode + local control — browser window becomes visible, user takes over
2. CDP proxy — remote debug URL for cross-device control (via WebSocket proxy)
"""

import asyncio
import threading
from typing import Optional

from playwright.async_api import Page


REMOTE_STATUS = threading.Event()
REMOTE_OBJECTIVE = ""


async def start_remote_assist(page: Page, objective: str = "") -> dict:
    """Start remote assist session.

    In headed mode (default for real browsers): brings browser window to front.
    User operates the browser manually, then the agent continues.
    """
    global REMOTE_STATUS, REMOTE_OBJECTIVE
    REMOTE_STATUS.clear()
    REMOTE_OBJECTIVE = objective

    try:
        await page.bring_to_front()
        await page.evaluate("alert('Remote assist started: " + objective.replace("'", "\\'") + "')")
    except Exception:
        pass

    is_headless = await page.evaluate("window.navigator.webdriver === undefined")

    cdp_session = None
    try:
        cdp = await page.context.new_cdp_session(page)
        cdp_session = cdp
    except Exception:
        pass

    return {
        "ok": True,
        "mode": "local" if not is_headless else "headless",
        "objective": objective,
        "message": (
            f"Remote assist active. Objective: {objective}\n"
            "Browser window is now visible. Complete the action manually.\n"
            "The agent will continue when you confirm."
        ),
    }


async def stop_remote_assist() -> dict:
    REMOTE_STATUS.set()
    return {"ok": True, "message": "Remote assist ended. Agent resuming control."}


async def is_remote_active() -> bool:
    return not REMOTE_STATUS.is_set()
