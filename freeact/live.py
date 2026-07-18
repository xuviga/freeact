"""Live browser connection — control user's REAL running browser.

Connects to an already-running browser instance via CDP.
The user sees everything the agent does in real-time.
All tabs, cookies, logins, and sessions are preserved.
"""

import asyncio
import json
import subprocess
import time
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from freeact.config import FREACT_HOME

LIVE_CONFIG = FREACT_HOME / "live_browser.json"
CDP_DEFAULT_PORT = 9222


def get_live_config() -> dict:
    if LIVE_CONFIG.exists():
        try:
            return json.loads(LIVE_CONFIG.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {}


def save_live_config(data: dict):
    LIVE_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    LIVE_CONFIG.write_text(json.dumps(data, indent=2))


def detect_browser_cdp() -> Optional[dict]:
    """Try to detect a browser already running with CDP on common ports."""
    import http.client

    for port in [9222, 9223, 9224, 9225]:
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
            conn.request("GET", "/json/version")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            conn.close()
            browser_name = data.get("Browser", "Unknown")
            return {
                "port": port,
                "url": f"http://127.0.0.1:{port}",
                "ws_url": data.get("webSocketDebuggerUrl", ""),
                "browser": browser_name,
            }
        except Exception:
            continue
    return None


def launch_browser_with_cdp(browser_type: str = "chrome", port: int = CDP_DEFAULT_PORT) -> Optional[dict]:
    """Launch browser with CDP + original profile. Kills existing instance if needed.
    Returns CDP info on success, None on failure.
    """
    from freeact.browser import find_browser

    info = find_browser(browser_type)
    if not info:
        return None

    exe = info["found_path"]
    profile = str(info["profile"])
    exe_name = info["exe"]

    import subprocess as sp
    try:
        sp.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(1.5)

    args = [
        exe,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--restore-last-session",
        "--no-first-run",
        "--no-default-browser-check",
        "--window-size=1920,1080",
    ]

    try:
        sp.Popen(args, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
    except Exception as e:
        return None

    import http.client
    for attempt in range(20):
        time.sleep(1)
        try:
            conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/json/version")
            resp = conn.getresponse()
            data = json.loads(resp.read().decode())
            conn.close()

            config = {
                "port": port,
                "url": f"http://127.0.0.1:{port}",
                "ws_url": data.get("webSocketDebuggerUrl", ""),
                "browser": data.get("Browser", info["name"]),
                "browser_type": browser_type,
            }
            save_live_config(config)
            return config
        except Exception:
            continue

    return None


async def connect_to_live_browser(port: int = 0) -> dict:
    """Connect Playwright to a running browser via CDP.

    Returns info about the connection including open tabs.
    """
    if port == 0:
        detected = detect_browser_cdp()
        if detected:
            port = detected["port"]
        else:
            config = get_live_config()
            port = config.get("port", CDP_DEFAULT_PORT)

    pw = await async_playwright().start()

    try:
        browser = await pw.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
    except Exception as e:
        await pw.stop()
        return {"ok": False, "error": f"Cannot connect to browser on port {port}: {e}"}

    contexts = browser.contexts
    all_pages = []
    for ctx in contexts:
        for page in ctx.pages:
            try:
                all_pages.append({
                    "url": page.url,
                    "title": await page.title(),
                })
            except Exception:
                all_pages.append({"url": "unknown", "title": "unknown"})

    config = {
        "port": port,
        "url": f"http://127.0.0.1:{port}",
        "connected": True,
    }
    save_live_config(config)

    return {
        "ok": True,
        "port": port,
        "tabs": len(all_pages),
        "pages": all_pages,
        "browser": pw,
        "cdp_browser": browser,
    }


async def list_tabs(port: int = CDP_DEFAULT_PORT) -> dict:
    """List all open tabs in the connected browser via CDP HTTP API."""
    import http.client

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/json/list")
        resp = conn.getresponse()
        pages = json.loads(resp.read().decode())
        conn.close()

        tabs = []
        for i, p in enumerate(pages):
            if p.get("type") == "page":
                tabs.append({
                    "id": i,
                    "title": p.get("title", ""),
                    "url": p.get("url", ""),
                    "cdp_id": p.get("id", ""),
                })

        return {"ok": True, "tabs": tabs, "count": len(tabs)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def switch_tab(port: int, tab_index: int) -> dict:
    """Activate a specific tab by index (from list_tabs)."""
    import http.client

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/json/list")
        resp = conn.getresponse()
        pages = json.loads(resp.read().decode())
        conn.close()

        real_pages = [p for p in pages if p.get("type") == "page"]
        if tab_index < 0 or tab_index >= len(real_pages):
            return {"ok": False, "error": f"Tab index {tab_index} out of range (0-{len(real_pages)-1})"}

        target_id = real_pages[tab_index]["id"]

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", f"/json/activate/{target_id}")
        resp = conn.getresponse()
        resp.read()
        conn.close()

        return {
            "ok": True,
            "activated": tab_index,
            "title": real_pages[tab_index]["title"],
            "url": real_pages[tab_index]["url"],
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def close_tab(port: int, tab_index: int) -> dict:
    """Close a tab by index."""
    import http.client

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", "/json/list")
        resp = conn.getresponse()
        pages = json.loads(resp.read().decode())
        conn.close()

        real_pages = [p for p in pages if p.get("type") == "page"]
        if tab_index < 0 or tab_index >= len(real_pages):
            return {"ok": False, "error": f"Tab index {tab_index} out of range"}

        target_id = real_pages[tab_index]["id"]

        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("GET", f"/json/close/{target_id}")
        resp = conn.getresponse()
        resp.read()
        conn.close()

        return {"ok": True, "closed": tab_index}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def new_tab(port: int, url: str = "about:blank") -> dict:
    """Open a new tab in the connected browser."""
    import http.client

    try:
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=3)
        conn.request("PUT", f"/json/new?{url}")
        resp = conn.getresponse()
        data = json.loads(resp.read().decode())
        conn.close()

        return {
            "ok": True,
            "url": data.get("url", url),
            "title": data.get("title", ""),
            "cdp_id": data.get("id", ""),
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}
