"""Daemon mode — persistent browser with HTTP command server.

Architecture:
    CLI commands → HTTP POST to daemon (127.0.0.1:9341) → browser action → JSON response

The daemon keeps the browser alive between commands, eliminating startup delay
and preserving JS state, cookies, and network logs across command invocations.

Daemon lifecycle:
    freeact daemon start  → spawns background process → returns immediately
    freeact daemon stop   → sends stop command → daemon exits gracefully
    freeact daemon status → checks if daemon is reachable

Stability:
    - Background process via subprocess (DETACHED_PROCESS on Windows)
    - Readiness detection — CLI waits for daemon to accept connections
    - Robust HTTP parsing with Content-Length support
    - Proper cleanup on stop (closes all browsers, removes PID file)
"""

import asyncio
import json
import os
import subprocess
import sys
import time
import warnings
from pathlib import Path

warnings.simplefilter("ignore", ResourceWarning)

from freeact import __version__  # noqa: E402
from freeact._handlers import (  # noqa: E402
    h_back, h_click, h_eval, h_forward, h_get, h_hover,
    h_input, h_keys, h_navigate, h_network, h_reload,
    h_screenshot, h_scroll, h_scrollintoview, h_select,
    h_state, h_upload, h_wait,
)
from freeact.browser import BrowserManager, get_browser_manager  # noqa: E402
from freeact.config import BrowserConfig, FreeactConfig, get_config  # noqa: E402
from freeact.extraction import (  # noqa: E402
    get_markdown,
)
from freeact.logger import log  # noqa: E402
from freeact.network import (  # noqa: E402
    start_network_monitoring,
)
from freeact.session import get_session_manager  # noqa: E402
from freeact.state import (  # noqa: E402
    init_state_engine, wait_for_dom_stable,
)

DAEMON_PORT = 9341
DAEMON_HOST = "127.0.0.1"
PID_FILE = Path.home() / ".freeact" / "daemon.pid"
PORT_FILE = Path.home() / ".freeact" / "daemon.port"
STARTUP_TIMEOUT = 15  # seconds
STOP_TIMEOUT = 5


def _cleanup_files():
    for f in (PID_FILE, PORT_FILE):
        try:
            f.unlink(missing_ok=True)
        except Exception:
            pass


class DaemonServer:
    def __init__(self):
        self.manager: BrowserManager | None = None
        self.config: FreeactConfig | None = None
        self._started_at = time.time()
        self._state_initialized: set = set()
        self._running = True
        self._page_cache: dict[str, object] = {}
        self._page_cache_urls: dict[str, str] = {}
        self._page_targets: dict[str, str] = {}

    async def _ensure_live_connected(self):
        if self._page_cache.get("live") and not self._page_cache["live"].is_closed():
            return self._page_cache["live"]
        try:
            from freeact.live import detect_browser_cdp
            detected = detect_browser_cdp()
            if not detected:
                return None
            await self.manager.start()
            lb = await self.manager._playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{detected['port']}"
            )
            ctx = lb.contexts[0] if lb.contexts else await lb.new_context()
            import uuid
            tag = str(uuid.uuid4())
            live_page = await ctx.new_page()
            await live_page.evaluate(f"window.__freeact_agent_tag = '{tag}'")
            self._page_targets["live"] = tag
            self._page_cache["live"] = live_page
            self._page_cache_urls["live"] = live_page.url
            return live_page
        except Exception:
            return None

    async def _ensure_state_engine(self, session_name: str, page):
        if session_name not in self._state_initialized:
            try:
                max_entries = self.config.max_network_entries if self.config else 500
                await start_network_monitoring(page, max_entries=max_entries)
                await init_state_engine(page)
                self._state_initialized.add(session_name)
            except Exception:
                pass

    async def handle_request(self, method: str, path: str, body: dict, api_key: str | None = None) -> dict:
        if self.config and self.config.api_key:
            if not api_key or api_key != self.config.api_key:
                return {"ok": False, "error": "Unauthorized: invalid or missing API key"}
        try:
            handlers = {
                "/cmd/daemon": self._cmd_daemon,
                "/cmd/state": self._cmd_state,
                "/cmd/click": self._cmd_click,
                "/cmd/input": self._cmd_input,
                "/cmd/hover": self._cmd_hover,
                "/cmd/select": self._cmd_select,
                "/cmd/keys": self._cmd_keys,
                "/cmd/scroll": self._cmd_scroll,
                "/cmd/scrollintoview": self._cmd_scrollintoview,
                "/cmd/upload": self._cmd_upload,
                "/cmd/navigate": self._cmd_navigate,
                "/cmd/back": self._cmd_back,
                "/cmd/forward": self._cmd_forward,
                "/cmd/reload": self._cmd_reload,
                "/cmd/get": self._cmd_get,
                "/cmd/eval": self._cmd_eval,
                "/cmd/frames": self._cmd_frames,
                "/cmd/frame-click": self._cmd_frame_click,
                "/cmd/screenshot": self._cmd_screenshot,
                "/cmd/wait": self._cmd_wait,
                "/cmd/network": self._cmd_network,
                "/cmd/browser": self._cmd_browser,
                "/cmd/session": self._cmd_session,
                "/cmd/stealth-extract": self._cmd_stealth_extract,
                "/cmd/solve-captcha": self._cmd_solve_captcha,
                "/cmd/remote-assist": self._cmd_remote_assist,
                "/cmd/connect": self._cmd_connect,
                "/cmd/tabs": self._cmd_tabs,
                "/cmd/tab-switch": self._cmd_tab_switch,
                "/cmd/tab-close": self._cmd_tab_close,
                "/cmd/tab-new": self._cmd_tab_new,
            }
            handler = handlers.get(path)
            if handler:
                return await handler(body)
            return {"ok": False, "error": f"Unknown command: {path}"}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    async def _get_page(self, session_name: str):
        sm = get_session_manager()
        s = sm.get(session_name)

        if not s and session_name == "live":
            sm.create("live", "live")
            s = sm.get("live")

        if not s:
            self._page_cache.pop(session_name, None)
            return None, None

        cached = self._page_cache.get(session_name)
        if cached is not None:
            try:
                if not cached.is_closed():
                    expected_tag = self._page_targets.get(session_name)
                    if expected_tag:
                        try:
                            actual_tag = await cached.evaluate("() => window.__freeact_agent_tag || ''")
                            if actual_tag == expected_tag:
                                self._page_cache_urls[session_name] = cached.url
                                return cached, s
                        except Exception:
                            pass
                        saved_url = self._page_cache_urls.get(session_name)
                        cur_url = cached.url
                        if saved_url and cur_url and saved_url == cur_url:
                            self._page_targets[session_name] = ""
                            return cached, s
                    else:
                        self._page_cache_urls[session_name] = cached.url
                        return cached, s
            except Exception:
                pass
            self._page_cache.pop(session_name, None)

        if s.browser_id == "live" or s.browser_id not in self.config.browsers:
            try:
                await self.manager.start()
                cfg = {}
                try:
                    from freeact.live import get_live_config
                    cfg = get_live_config()
                except Exception:
                    pass
                port = cfg.get("port", 9222)
                browser = await self.manager._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}"
                )
                contexts = browser.contexts
                if not contexts:
                    return None, None
                import uuid
                tag = str(uuid.uuid4())
                page = await contexts[0].new_page()
                self._page_cache[session_name] = page
                self._page_cache_urls[session_name] = page.url
                self._page_targets[session_name] = tag
                try:
                    await page.evaluate(f"window.__freeact_agent_tag = '{tag}'")
                except Exception:
                    pass
                return page, s
            except Exception:
                return None, None

        bc = self.config.browsers.get(s.browser_id)
        if not bc:
            bc = BrowserConfig(id=s.browser_id, name=s.browser_id)
        page = await self.manager.get_page(s.browser_id, bc, self.config)

        if page is None and s.browser_id not in self.config.browsers:
            try:
                await self.manager.start()
                cfg = {}
                try:
                    from freeact.live import get_live_config
                    cfg = get_live_config()
                except Exception:
                    pass
                port = cfg.get("port", 9222)
                browser = await self.manager._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}"
                )
                contexts = browser.contexts
                if contexts:
                    import uuid
                    tag = str(uuid.uuid4())
                    page = await contexts[0].new_page()
                    self.manager._pages[s.browser_id] = page
                    self._page_targets[s.browser_id] = tag
                    try:
                        await page.evaluate(f"window.__freeact_agent_tag = '{tag}'")
                    except Exception:
                        pass
                if page:
                    self.manager._browsers[s.browser_id] = browser
                    self.manager._contexts[s.browser_id] = contexts[0]
            except Exception:
                pass

        if page:
            saved = await self.manager.get_saved_url(session_name)
            if saved:
                try:
                    cur = page.url
                    if cur in ("about:blank", "") or cur.startswith("chrome://"):
                        await page.goto(saved, wait_until="domcontentloaded")
                        await wait_for_dom_stable(page, timeout_ms=5000)
                except Exception:
                    pass
            self._page_cache[session_name] = page
            self._page_cache_urls[session_name] = page.url
        return page, s

    # ─── Command handlers ─────────────────────────────────

    async def _cmd_daemon(self, body: dict) -> dict:
        action = body.get("action", "status")
        if action == "status":
            return {
                "ok": True,
                "version": __version__,
                "uptime": time.time() - self._started_at,
                "port": DAEMON_PORT,
            }
        elif action == "stop":
            self._running = False
            return {"ok": True, "result": "Daemon stopping"}
        return {"ok": False, "error": f"Unknown action: {action}"}

    async def _cmd_state(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        await self._ensure_state_engine(body["session"], page)
        result = await h_state(page)
        return {"ok": True, "result": result}

    async def _cmd_click(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_click(page, body["index"])
        return {"ok": True, "result": result}

    async def _cmd_input(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_input(page, body["index"], body["text"])
        return {"ok": True, "result": result}

    async def _cmd_hover(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_hover(page, body["index"])
        return {"ok": True, "result": result}

    async def _cmd_select(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_select(page, body["index"], body["option"])
        return {"ok": True, "result": result}

    async def _cmd_keys(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_keys(page, body["key"])
        return {"ok": True, "result": result}

    async def _cmd_scroll(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_scroll(page, body["direction"], body.get("amount", 500))
        return {"ok": True, "result": result}

    async def _cmd_scrollintoview(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_scrollintoview(page, body["selector"])
        return {"ok": True, "result": result}

    async def _cmd_upload(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_upload(page, body["index"], body["file_path"])
        return {"ok": True, "result": result}

    async def _cmd_navigate(self, body: dict) -> dict:
        page, s = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        url = body["url"]
        result = await h_navigate(page, url)
        if s:
            await self.manager.save_page_url(s.browser_id, body["session"], page.url)
        self._state_initialized.discard(body["session"])
        self._page_cache_urls[body["session"]] = page.url
        return {"ok": True, "result": result}

    async def _cmd_back(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_back(page)
        self._state_initialized.discard(body["session"])
        self._page_cache_urls[body["session"]] = page.url
        return {"ok": True, "result": result}

    async def _cmd_forward(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_forward(page)
        self._state_initialized.discard(body["session"])
        self._page_cache_urls[body["session"]] = page.url
        return {"ok": True, "result": result}

    async def _cmd_reload(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_reload(page)
        self._state_initialized.discard(body["session"])
        return {"ok": True, "result": result}

    async def _cmd_get(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_get(page, body["what"], body.get("arg"), body.get("selector"))
        return {"ok": True, "result": result}

    async def _cmd_eval(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_eval(page, body["js"])
        return {"ok": True, "result": result}

    async def _cmd_frames(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        frames = []
        for i, frame in enumerate(page.frames):
            try:
                frames.append({"index": i, "name": frame.name, "url": frame.url})
            except Exception:
                frames.append({"index": i, "name": "?", "url": "?"})
        return {"ok": True, "result": frames}

    async def _cmd_frame_click(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        frame_index = body.get("frame_index", -1)
        selector = body.get("selector", "button")
        target_frame = None
        if frame_index >= 0 and frame_index < len(page.frames):
            target_frame = page.frames[frame_index]
        else:
            for f in page.frames:
                if "accounts.google.com" in f.url or "gsi" in f.url:
                    target_frame = f
                    break
            if not target_frame:
                for f in page.frames:
                    if f != page.main_frame:
                        target_frame = f
                        break
        if not target_frame:
            return {"ok": False, "error": "No suitable frame found"}
        try:
            btn = target_frame.locator(selector).first
            await btn.click(timeout=5000, force=True)
            return {"ok": True, "result": f"Clicked {selector} in {target_frame.url}"}
        except Exception as e:
            try:
                await target_frame.evaluate(f"document.querySelector('{selector}')?.click()")
                return {"ok": True, "result": f"Clicked {selector} via JS in {target_frame.url}"}
            except Exception:
                return {"ok": False, "error": str(e)}

    async def _cmd_screenshot(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_screenshot(page, body.get("path"), body.get("full", False))
        return {"ok": True, "result": result}

    async def _cmd_wait(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_wait(page, body.get("what", "stable"), body.get("timeout", 30000))
        return {"ok": True, "result": result}

    async def _cmd_network(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await h_network(
            page, body["action"], body.get("arg"),
            url_filter=body.get("filter"), types=body.get("type"),
            method=body.get("method"), status=body.get("status"),
            clear=body.get("clear", False),
        )
        return {"ok": True, "result": result}

    async def _cmd_browser(self, body: dict) -> dict:
        action = body["action"]
        match action:
            case "open":
                session_name = body["session"]
                browser_id = body["browser_id"]
                url = body.get("url", "about:blank")
                if "://" not in url and url != "about:blank":
                    url = "https://" + url

                live_page = await self._ensure_live_connected()
                if live_page:
                    agent_tabs = sum(1 for k in self._page_cache if k != "live" and not k.endswith("_target"))
                    if agent_tabs >= 5:
                        return {"ok": False, "error": "Agent tab limit (5) reached. Close a session first."}
                    try:
                        import uuid
                        tag = str(uuid.uuid4())
                        page = await live_page.context.new_page()
                        if url and url != "about:blank":
                            try:
                                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                                await wait_for_dom_stable(page, timeout_ms=5000)
                            except Exception as e:
                                return {"ok": False, "error": f"Navigation failed: {e}"}
                        await page.evaluate(f"window.__freeact_agent_tag = '{tag}'")
                        self._page_targets[session_name] = tag
                        sm = get_session_manager()
                        sm.create(session_name, browser_id)
                        self._page_cache[session_name] = page
                        self._page_cache_urls[session_name] = page.url
                        return {"ok": True,
                                "result": f"New tab opened in live browser, session '{session_name}' started"}
                    except Exception as e:
                        return {"ok": False, "error": f"Failed to create tab: {e}"}

                bc = self.config.browsers.get(browser_id)
                if not bc:
                    bc = BrowserConfig(id=browser_id, name=browser_id,
                                       type=body.get("type", self.config.default_browser))

                try:
                    page = await self.manager.get_page(browser_id, bc, self.config)
                except RuntimeError:
                    return {"ok": False, "error": f"Cannot launch browser '{browser_id}'. Check that the browser is not already running."}

                if not page:
                    return {"ok": False, "error": f"Browser '{browser_id}' not available"}

                await self._ensure_state_engine(session_name, page)
                if url and url != "about:blank":
                    try:
                        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                        await wait_for_dom_stable(page, timeout_ms=5000)
                    except Exception as e:
                        return {"ok": False, "error": f"Navigation failed: {e}"}

                await self.manager.save_page_url(browser_id, session_name, page.url)
                sm = get_session_manager()
                sm.create(session_name, browser_id)
                self._page_cache[session_name] = page
                self._page_cache_urls[session_name] = page.url
                return {"ok": True,
                        "result": f"Browser '{browser_id}' opened, session '{session_name}' started"}

            case "list":
                if not self.config.browsers:
                    return {"ok": True, "result": "No browsers configured"}
                lines = ["Browsers:"]
                for bid, bc in self.config.browsers.items():
                    px = f" proxy={bc.proxy}" if bc.proxy else ""
                    lines.append(f"  {bid}: name={bc.name}, type={bc.type}, desc={bc.desc}{px}")
                return {"ok": True, "result": "\n".join(lines)}

            case "create":
                name = body.get("name")
                if not name:
                    return {"ok": False, "error": "--name required"}
                bid = self.manager.generate_browser_id()
                bc = BrowserConfig(
                    id=bid, name=name,
                    type=body.get("type", self.config.default_browser),
                    desc=body.get("desc", ""),
                    proxy=body.get("proxy"),
                )
                self.config.browsers[bid] = bc
                self.config.save()
                return {"ok": True, "result": f"Browser created: id={bid}, name={name}, type={bc.type}"}

            case "update":
                bid = body.get("browser_id")
                if not bid:
                    return {"ok": False, "error": "Browser ID required"}
                bc = self.config.browsers.get(bid)
                if not bc:
                    return {"ok": False, "error": f"Browser '{bid}' not found"}
                if "name" in body:
                    bc.name = body["name"]
                if "desc" in body:
                    bc.desc = body["desc"]
                if "desc_append" in body:
                    bc.desc = (bc.desc + " " + body["desc_append"]) if bc.desc else \
                        body["desc_append"]
                if body.get("no_proxy"):
                    bc.proxy = None
                elif body.get("proxy"):
                    bc.proxy = body["proxy"]
                self.config.save()
                return {"ok": True, "result": f"Browser '{bid}' updated"}

            case "delete":
                bid = body.get("browser_id")
                if not bid:
                    return {"ok": False, "error": "Browser ID required"}
                self.config.browsers.pop(bid, None)
                self.config.save()
                await self.manager.close_context(bid)
                return {"ok": True, "result": f"Browser '{bid}' deleted"}

            case "types":
                from freeact.browser import BROWSER_MAP
                lines = ["Available real browsers:"]
                for key, info in BROWSER_MAP.items():
                    found = "NOT FOUND"
                    for p in info["paths"]:
                        if Path(p).exists():
                            found = str(p)
                            break
                    lines.append(f"  {info['name']}: {found}")
                    lines.append(f"    profile: {info['profile']}")
                return {"ok": True, "result": "\n".join(lines)}

            case _:
                return {"ok": False, "error": f"Unknown browser action: {action}"}

    async def _cmd_session(self, body: dict) -> dict:
        action = body["action"]
        sm = get_session_manager()
        match action:
            case "list":
                sessions = sm.list_sessions()
                if not sessions:
                    return {"ok": True, "result": "No active sessions"}
                lines = ["Active sessions:"]
                for s in sessions:
                    lines.append(f"  {s.name}: browser={s.browser_id}")
                return {"ok": True, "result": "\n".join(lines)}
            case "close":
                name = body.get("name")
                if not name:
                    return {"ok": False, "error": "Session name required"}
                sm.close(name)
                await self.manager.close_context(name)
                self._state_initialized.discard(name)
                self._page_cache.pop(name, None)
                self._page_cache_urls.pop(name, None)
                return {"ok": True, "result": f"Session '{name}' closed"}
            case _:
                return {"ok": False, "error": f"Unknown session action: {action}"}

    async def _cmd_stealth_extract(self, body: dict) -> dict:
        from playwright.async_api import async_playwright
        from freeact.stealth import apply_stealth_patches

        url = body["url"]
        if "://" not in url:
            url = "https://" + url
        content_type = body.get("content_type", "markdown")
        timeout = body.get("timeout", 30)

        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            await apply_stealth_patches(context)
            page = await context.new_page()
            try:
                await page.goto(url, wait_until="networkidle", timeout=timeout * 1000)
                content = await page.content() if content_type == "html" else await get_markdown(
                    page)
                output = body.get("output")
                if output:
                    Path(output).write_text(content, encoding="utf-8")
                    return {"ok": True, "result": f"Content saved to {output}"}
                return {"ok": True, "result": content}
            except Exception as e:
                return {"ok": False, "error": f"Error extracting: {e}"}
            finally:
                await browser.close()

    async def _cmd_solve_captcha(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        from freeact.captcha import solve_captcha_on_page
        result = await solve_captcha_on_page(page)
        return result

    async def _cmd_remote_assist(self, body: dict) -> dict:
        page, s = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        from freeact.remote import start_remote_assist
        result = await start_remote_assist(page, body.get("objective", ""))
        return result

    async def _cmd_connect(self, body: dict) -> dict:
        live_page = await self._ensure_live_connected()
        if live_page:
            sm = get_session_manager()
            sm.create("live", "live")
            return {
                "ok": True,
                "message": "Connected to live browser — new tab created",
            }
        return {"ok": False, "error": "Browser not running with CDP. Run: freeact setup"}

    async def _cmd_tabs(self, body: dict) -> dict:
        from freeact.live import list_tabs, get_live_config
        cfg = get_live_config()
        port = body.get("port", cfg.get("port", 9222))
        return await list_tabs(port)

    async def _cmd_tab_switch(self, body: dict) -> dict:
        from freeact.live import switch_tab, get_live_config
        cfg = get_live_config()
        port = body.get("port", cfg.get("port", 9222))
        return await switch_tab(port, body["index"])

    async def _cmd_tab_close(self, body: dict) -> dict:
        from freeact.live import close_tab, get_live_config
        cfg = get_live_config()
        port = body.get("port", cfg.get("port", 9222))
        return await close_tab(port, body["index"])

    async def _cmd_tab_new(self, body: dict) -> dict:
        from freeact.live import new_tab, get_live_config
        cfg = get_live_config()
        port = body.get("port", cfg.get("port", 9222))
        return await new_tab(port, body.get("url", "about:blank"))


# ─── HTTP Server ─────────────────────────────────────────


async def _run_http_server(server: DaemonServer):
    """Robust async HTTP server with proper Content-Length parsing."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            raw = bytearray()
            content_length = 0
            headers_parsed = False

            while True:
                try:
                    chunk = await asyncio.wait_for(reader.read(8192), timeout=30)
                except asyncio.TimeoutError:
                    break
                if not chunk:
                    break
                raw.extend(chunk)

                if not headers_parsed:
                    header_end = raw.find(b"\r\n\r\n")
                    if header_end == -1:
                        if len(raw) > 65536:
                            break
                        continue

                    headers_parsed = True
                    header_bytes = bytes(raw[:header_end])
                    header_text = header_bytes.decode("utf-8", errors="replace")
                    header_lines = header_text.split("\r\n")
                    if not header_lines:
                        break

                    first_line = header_lines[0].split(" ")
                    method = first_line[0] if len(first_line) > 0 else "GET"
                    path = first_line[1] if len(first_line) > 1 else "/"

                    api_key = None
                    for line in header_lines[1:]:
                        if line.lower().startswith("content-length:"):
                            try:
                                content_length = int(line.split(":", 1)[1].strip())
                            except ValueError:
                                pass
                        elif line.lower().startswith("x-api-key:"):
                            api_key = line.split(":", 1)[1].strip()

                if headers_parsed:
                    body_start = raw.find(b"\r\n\r\n") + 4
                    body_len = len(raw) - body_start
                    if body_len >= content_length:
                        break

            if not headers_parsed:
                try:
                    writer.close()
                    await writer.wait_closed()
                except Exception:
                    pass
                return

            body_start = raw.find(b"\r\n\r\n") + 4
            body_bytes = bytes(raw[body_start:body_start + content_length]) if content_length > 0 else b""

            body = {}
            if body_bytes:
                try:
                    body = json.loads(body_bytes.decode("utf-8", errors="replace"))
                except json.JSONDecodeError:
                    pass

            response = await server.handle_request(method, path, body, api_key)
            response_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")

            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                "Access-Control-Allow-Origin: *\r\n"
                "Access-Control-Allow-Methods: POST, GET, OPTIONS\r\n"
                "Access-Control-Allow-Headers: Content-Type\r\n"
                f"Content-Length: {len(response_bytes)}\r\n"
                "Connection: keep-alive\r\n"
                "\r\n"
            )
            writer.write(header.encode("utf-8"))
            writer.write(response_bytes)
            await writer.drain()
        except Exception:
            pass
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

    server_coro = await asyncio.start_server(handle_client, DAEMON_HOST, DAEMON_PORT)

    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    PORT_FILE.write_text(str(DAEMON_PORT))

    print(f"FreeAct daemon v{__version__} running on {DAEMON_HOST}:{DAEMON_PORT}")
    print(f"PID: {os.getpid()}")
    log(f"Daemon started on {DAEMON_HOST}:{DAEMON_PORT}")

    async def _shutdown():
        server_coro.close()
        await server_coro.wait_closed()
        if server.manager:
            await server.manager.stop()
        _cleanup_files()

    try:
        async with server_coro:
            while server._running:
                await asyncio.sleep(0.5)
    except asyncio.CancelledError:
        pass
    finally:
        await _shutdown()
        print("Daemon stopped")


# ─── Daemon lifecycle ────────────────────────────────────


def _run_daemon_foreground():
    """Internal entry point for the daemon subprocess. Runs blocking."""
    try:
        os.dup2(sys.__stdout__.fileno(), sys.__stderr__.fileno())
    except Exception:
        pass

    async def main():
        manager = await get_browser_manager()
        config = get_config()
        server = DaemonServer()
        server.manager = manager
        server.config = config
        await _run_http_server(server)

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDaemon stopped")
    except Exception as e:
        print(f"Daemon error: {e}")
        sys.exit(1)


def start_daemon_background():
    """Start daemon as a detached background process. Returns immediately."""
    if is_daemon_running():
        return {"ok": True, "message": f"Daemon already running on port {DAEMON_PORT}"}

    _cleanup_files()

    daemon_script = (
        "import sys; sys.path.insert(0, r'" + str(Path(__file__).parent.parent) + "'); "
        "from freeact.daemon import _run_daemon_foreground; "
        "_run_daemon_foreground()"
    )

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if sys.platform == "win32":
        creationflags = subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP
        proc = subprocess.Popen(
            [sys.executable, "-c", daemon_script],
            creationflags=creationflags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(
            [sys.executable, "-c", daemon_script],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            env=env,
            start_new_session=True,
            close_fds=True,
        )

    for _ in range(STARTUP_TIMEOUT * 2):
        time.sleep(0.5)
        if is_daemon_running():
            return {"ok": True, "message": f"Daemon started on port {DAEMON_PORT}"}

    if proc.poll() is not None:
        _cleanup_files()
        return {"ok": False, "error": f"Daemon exited with code {proc.returncode}"}

    return {"ok": False, "error": f"Daemon did not respond within {STARTUP_TIMEOUT}s. Check port {DAEMON_PORT} is free."}


def stop_daemon():
    """Stop a running daemon. Returns when the daemon has exited or timed out."""
    if not is_daemon_running():
        _cleanup_files()
        return {"ok": True, "message": "Daemon was not running"}

    result = send_daemon_command("/cmd/daemon", {"action": "stop"})
    if not result.get("ok"):
        return result

    for _ in range(STOP_TIMEOUT * 2):
        time.sleep(0.5)
        if not is_daemon_running():
            _cleanup_files()
            return {"ok": True, "message": "Daemon stopped"}

    _cleanup_files()
    return {"ok": True, "message": "Daemon stop signal sent"}


# ─── CLI helpers ─────────────────────────────────────────


def send_daemon_command(path: str, body: dict | None = None) -> dict:
    """Send command to running daemon via HTTP. Used by CLI commands."""
    import http.client

    body_json = json.dumps(body or {}).encode("utf-8")
    config = get_config()
    headers = {
        "Content-Type": "application/json",
        "Content-Length": str(len(body_json)),
    }
    if config.api_key:
        headers["X-API-Key"] = config.api_key
    try:
        conn = http.client.HTTPConnection(DAEMON_HOST, DAEMON_PORT, timeout=120)
        conn.request("POST", path, body=body_json, headers=headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        conn.close()
        return data
    except (ConnectionRefusedError, OSError, http.client.HTTPException):
        return {"ok": False, "error": "Daemon not running. Start with: freeact daemon"}
    except json.JSONDecodeError:
        return {"ok": False, "error": "Invalid response from daemon"}


def is_daemon_running() -> bool:
    result = send_daemon_command("/cmd/daemon", {"action": "status"})
    return result.get("ok", False)
