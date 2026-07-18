"""Daemon mode — persistent browser with HTTP command server.

Architecture:
    CLI commands → HTTP POST to daemon (127.0.0.1:9341) → browser action → JSON response

The daemon keeps the browser alive between commands, eliminating startup delay
and preserving JS state, cookies, and network logs across command invocations.
"""

import asyncio
import json
import signal
import sys
import time
from pathlib import Path
from typing import Optional

from freeact import __version__
from freeact.browser import BrowserManager, get_browser_manager
from freeact.config import BrowserConfig, FreeactConfig, get_config
from freeact.extraction import (
    evaluate_js, get_element_text, get_element_value,
    get_html, get_markdown, get_title, take_screenshot,
)
from freeact.interaction import (
    click_element, hover_element, input_text, scroll_by_selector,
    scroll_page, select_option, send_keys, upload_file,
)
from freeact.network import (
    clear_network_requests, get_network_request_detail,
    get_network_requests, start_network_monitoring,
)
from freeact.session import get_session_manager
from freeact.state import get_page_state

DAEMON_PORT = 9341
DAEMON_HOST = "127.0.0.1"
PID_FILE = Path.home() / ".freeact" / "daemon.pid"
PORT_FILE = Path.home() / ".freeact" / "daemon.port"


class DaemonServer:
    def __init__(self):
        self.manager: BrowserManager | None = None
        self.config: FreeactConfig | None = None
        self._started_at = time.time()

    async def handle_request(self, method: str, path: str, body: dict) -> dict:
        try:
            if path == "/cmd/daemon":
                return await self._cmd_daemon(body)
            elif path == "/cmd/state":
                return await self._cmd_state(body)
            elif path == "/cmd/click":
                return await self._cmd_click(body)
            elif path == "/cmd/input":
                return await self._cmd_input(body)
            elif path == "/cmd/hover":
                return await self._cmd_hover(body)
            elif path == "/cmd/select":
                return await self._cmd_select(body)
            elif path == "/cmd/keys":
                return await self._cmd_keys(body)
            elif path == "/cmd/scroll":
                return await self._cmd_scroll(body)
            elif path == "/cmd/scrollintoview":
                return await self._cmd_scrollintoview(body)
            elif path == "/cmd/upload":
                return await self._cmd_upload(body)
            elif path == "/cmd/navigate":
                return await self._cmd_navigate(body)
            elif path == "/cmd/back":
                return await self._cmd_back(body)
            elif path == "/cmd/forward":
                return await self._cmd_forward(body)
            elif path == "/cmd/reload":
                return await self._cmd_reload(body)
            elif path == "/cmd/get":
                return await self._cmd_get(body)
            elif path == "/cmd/eval":
                return await self._cmd_eval(body)
            elif path == "/cmd/screenshot":
                return await self._cmd_screenshot(body)
            elif path == "/cmd/wait":
                return await self._cmd_wait(body)
            elif path == "/cmd/network":
                return await self._cmd_network(body)
            elif path == "/cmd/browser":
                return await self._cmd_browser(body)
            elif path == "/cmd/session":
                return await self._cmd_session(body)
            elif path == "/cmd/stealth-extract":
                return await self._cmd_stealth_extract(body)
            elif path == "/cmd/solve-captcha":
                return await self._cmd_solve_captcha(body)
            elif path == "/cmd/remote-assist":
                return await self._cmd_remote_assist(body)
            elif path == "/cmd/connect":
                return await self._cmd_connect(body)
            elif path == "/cmd/tabs":
                return await self._cmd_tabs(body)
            elif path == "/cmd/tab-switch":
                return await self._cmd_tab_switch(body)
            elif path == "/cmd/tab-close":
                return await self._cmd_tab_close(body)
            elif path == "/cmd/tab-new":
                return await self._cmd_tab_new(body)
            else:
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
            return None, None

        if s.browser_id == "live":
            await self.manager.start()
            cfg = {}
            try:
                from freeact.live import get_live_config
                cfg = get_live_config()
            except Exception:
                pass
            port = cfg.get("port", 9222)
            try:
                browser = await self.manager._playwright.chromium.connect_over_cdp(
                    f"http://127.0.0.1:{port}"
                )
                contexts = browser.contexts
                for ctx in contexts:
                    for page in ctx.pages:
                        try:
                            title = await page.title()
                            return page, s
                        except Exception:
                            continue
                for ctx in contexts:
                    if ctx.pages:
                        return ctx.pages[0], s
                for ctx in contexts:
                    page = await ctx.new_page()
                    return page, s
            except Exception:
                return None, None

        bc = self.config.browsers.get(s.browser_id)
        if not bc:
            bc = BrowserConfig(id=s.browser_id, name=s.browser_id)
        page = await self.manager.get_page(s.browser_id, bc, self.config)
        if page:
            saved = await self.manager.get_saved_url(session_name)
            if saved:
                try:
                    cur = page.url
                    if cur in ("about:blank", "") or cur.startswith("chrome://"):
                        await page.goto(saved, wait_until="domcontentloaded")
                except Exception:
                    pass
        return page, s

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
            asyncio.get_event_loop().call_later(0.5, lambda: sys.exit(0))
            return {"ok": True, "result": "Daemon stopping"}
        return {"ok": False, "error": f"Unknown action: {action}"}

    async def _cmd_state(self, body: dict) -> dict:
        session = body["session"]
        page, s = await self._get_page(session)
        if not page:
            return {"ok": False, "error": f"Session '{session}' not found"}
        await start_network_monitoring(page)
        result = await get_page_state(page)
        return {"ok": True, "result": result}

    async def _cmd_click(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await click_element(page, body["index"])
        return {"ok": True, "result": result}

    async def _cmd_input(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await input_text(page, body["index"], body["text"])
        return {"ok": True, "result": result}

    async def _cmd_hover(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await hover_element(page, body["index"])
        return {"ok": True, "result": result}

    async def _cmd_select(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await select_option(page, body["index"], body["option"])
        return {"ok": True, "result": result}

    async def _cmd_keys(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await send_keys(page, body["key"])
        return {"ok": True, "result": result}

    async def _cmd_scroll(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await scroll_page(page, body["direction"], body.get("amount", 500))
        return {"ok": True, "result": result}

    async def _cmd_scrollintoview(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await scroll_by_selector(page, body["selector"])
        return {"ok": True, "result": result}

    async def _cmd_upload(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await upload_file(page, body["index"], body["file_path"])
        return {"ok": True, "result": result}

    async def _cmd_navigate(self, body: dict) -> dict:
        page, s = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        url = body["url"]
        if "://" not in url:
            url = "https://" + url
        await page.goto(url, wait_until="domcontentloaded")
        if s:
            await self.manager.save_page_url(s.browser_id, body["session"], page.url)
        return {"ok": True, "result": f"Navigated to {url}"}

    async def _cmd_back(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        await page.go_back()
        return {"ok": True, "result": "Navigated back"}

    async def _cmd_forward(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        await page.go_forward()
        return {"ok": True, "result": "Navigated forward"}

    async def _cmd_reload(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        await page.reload()
        return {"ok": True, "result": "Page reloaded"}

    async def _cmd_get(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        what = body["what"]
        arg = body.get("arg")
        selector = body.get("selector")
        match what:
            case "title":
                result = await get_title(page)
            case "html":
                result = await get_html(page, selector)
            case "markdown":
                result = await get_markdown(page)
            case "text":
                if not arg:
                    return {"ok": False, "error": "Index required for get text"}
                result = await get_element_text(page, int(arg))
            case "value":
                if not arg:
                    return {"ok": False, "error": "Index required for get value"}
                result = await get_element_value(page, int(arg))
            case _:
                return {"ok": False, "error": f"Unknown get type: {what}"}
        return {"ok": True, "result": result}

    async def _cmd_eval(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await evaluate_js(page, body["js"])
        return {"ok": True, "result": result}

    async def _cmd_screenshot(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        result = await take_screenshot(page, body.get("path"), body.get("full", False))
        return {"ok": True, "result": result}

    async def _cmd_wait(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        what = body.get("what", "stable")
        timeout = body.get("timeout", 30000)
        if what == "stable":
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout)
                result = "Page stable"
            except Exception as e:
                result = f"Wait timeout: {e}"
        else:
            result = f"Unknown wait type: {what}"
        return {"ok": True, "result": result}

    async def _cmd_network(self, body: dict) -> dict:
        page, _ = await self._get_page(body["session"])
        if not page:
            return {"ok": False, "error": "Session not found"}
        action = body["action"]
        match action:
            case "requests":
                result = await get_network_requests(
                    page, url_filter=body.get("filter"),
                    types=body.get("type"), method=body.get("method"),
                    status=body.get("status"), clear=body.get("clear", False),
                )
            case "request":
                idx = body.get("arg")
                if idx is None:
                    return {"ok": False, "error": "Request index required"}
                result = await get_network_request_detail(page, int(idx))
            case "clear":
                await clear_network_requests(page)
                result = "Network log cleared"
            case _:
                return {"ok": False, "error": f"Unknown network action: {action}"}
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

                bc = self.config.browsers.get(browser_id)
                if not bc:
                    bc = BrowserConfig(id=browser_id, name=browser_id, type=body.get("type", self.config.default_browser))

                page = await self.manager.get_page(browser_id, bc, self.config)
                await start_network_monitoring(page)
                if url and url != "about:blank":
                    await page.goto(url, wait_until="domcontentloaded")

                await self.manager.save_page_url(browser_id, session_name, page.url)
                sm = get_session_manager()
                sm.create(session_name, browser_id)
                return {"ok": True, "result": f"Browser '{browser_id}' opened, session '{session_name}' started"}

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
                    bc.desc = (bc.desc + " " + body["desc_append"]) if bc.desc else body["desc_append"]
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
                content = await page.content() if content_type == "html" else await get_markdown(page)
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
        from freeact.live import detect_browser_cdp, connect_to_live_browser
        detected = detect_browser_cdp()
        if detected:
            result = await connect_to_live_browser(detected["port"])
            if result.get("ok"):
                return {
                    "ok": True,
                    "mode": "reconnect",
                    "browser": detected["browser"],
                    "port": detected["port"],
                    "tabs": result.get("tabs", 0),
                    "pages": result.get("pages", []),
                    "message": f"Connected to {detected['browser']} on port {detected['port']} — {result.get('tabs', 0)} tabs",
                }
        return {
            "ok": False,
            "error": "Browser not running with CDP. Run: freeact setup"
        }

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


async def _run_http_server(server: DaemonServer):
    """Simple asyncio HTTP server without external dependencies."""
    import asyncio

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=30)
            if not data:
                return

            request = data.decode("utf-8", errors="replace")
            lines = request.split("\r\n")
            if not lines:
                return

            first_line = lines[0].split(" ")
            method = first_line[0] if len(first_line) > 0 else "GET"
            path = first_line[1] if len(first_line) > 1 else "/"

            body_str = ""
            header_end = False
            for line in lines[1:]:
                if line == "":
                    header_end = True
                    continue
                if not header_end:
                    continue
                body_str += line

            body = {}
            if body_str:
                try:
                    body = json.loads(body_str)
                except json.JSONDecodeError:
                    pass

            response = await server.handle_request(method, path, body)
            response_bytes = json.dumps(response, ensure_ascii=False).encode("utf-8")

            header = (
                "HTTP/1.1 200 OK\r\n"
                "Content-Type: application/json; charset=utf-8\r\n"
                "Access-Control-Allow-Origin: *\r\n"
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
            writer.close()

    server_coro = await asyncio.start_server(handle_client, DAEMON_HOST, DAEMON_PORT)
    import os as _os
    PID_FILE.write_text(str(_os.getpid()))
    PORT_FILE.write_text(str(DAEMON_PORT))

    print(f"FreeAct daemon v{__version__} running on {DAEMON_HOST}:{DAEMON_PORT}")
    print(f"PID: {_os.getpid()}")

    async with server_coro:
        await server_coro.serve_forever()


def run_daemon():
    """Entry point for `freeact daemon`."""
    print(f"FreeAct daemon v{__version__} starting...")

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


def send_daemon_command(path: str, body: dict | None = None) -> dict:
    """Send command to running daemon via HTTP. Used by CLI commands."""
    import http.client

    body_json = json.dumps(body or {}).encode("utf-8")
    try:
        conn = http.client.HTTPConnection(DAEMON_HOST, DAEMON_PORT, timeout=30)
        conn.request("POST", path, body=body_json, headers={
            "Content-Type": "application/json",
            "Content-Length": str(len(body_json)),
        })
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        conn.close()
        return data
    except (ConnectionRefusedError, OSError, http.client.HTTPException):
        return {"ok": False, "error": "Daemon not running. Start with: freeact daemon"}


def is_daemon_running() -> bool:
    result = send_daemon_command("/cmd/daemon", {"action": "status"})
    return result.get("ok", False)
