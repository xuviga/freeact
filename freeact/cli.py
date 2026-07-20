"""Free Browser Agent CLI — main entry point.

All commands route through the daemon (127.0.0.1:9341) when it's running.
Direct mode is fallback only — used when daemon is not running.
"""

import asyncio
import io
import json
import sys
import warnings
from pathlib import Path
from typing import Optional

import typer  # noqa: E402
from rich.console import Console  # noqa: E402

from freeact import __version__  # noqa: E402
from freeact._handlers import (  # noqa: E402
    h_back, h_click, h_eval, h_forward, h_get, h_hover,
    h_input, h_keys, h_navigate, h_network, h_reload,
    h_screenshot, h_scroll, h_scrollintoview, h_select,
    h_state, h_upload, h_wait,
)
from freeact.browser import get_browser_manager  # noqa: E402
from freeact.config import BrowserConfig, FreeactConfig, get_config  # noqa: E402
from freeact.extraction import (  # noqa: E402
    get_markdown,
)
from freeact.network import (  # noqa: E402
    start_network_monitoring,
)
from freeact.session import get_session_manager  # noqa: E402
from freeact.skills import get_skills_advanced, get_skills_core  # noqa: E402
from freeact.state import (  # noqa: E402
    init_state_engine, wait_for_dom_stable,
)

warnings.simplefilter("ignore", ResourceWarning)
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

app = typer.Typer(
    name="freeact",
    help="Free Browser Agent CLI — browser automation for AI agents",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"obj": {}},
)

console = Console(force_terminal=True, legacy_windows=False)


# ─── Helpers ─────────────────────────────────────────────


def _ctx_session(ctx: typer.Context, opt: Optional[str] = None) -> Optional[str]:
    return opt or ctx.obj.get("session")


def _req_session(ctx: typer.Context, opt: Optional[str] = None) -> str:
    s = _ctx_session(ctx, opt)
    if not s:
        console.print("Error: --session required")
        raise typer.Exit(1)
    return s


def _daemon_call(path: str, body: dict) -> dict | None:
    try:
        from freeact.daemon import is_daemon_running, send_daemon_command
        if is_daemon_running():
            return send_daemon_command(path, body)
    except Exception:
        pass
    return None


def _try_daemon(path: str, body: dict, fallback_fn) -> bool:
    """Try daemon first. If daemon responds, print result and return True.
    Otherwise run the fallback async function and return False."""
    result = _daemon_call(path, body)
    if result is not None:
        if result.get("ok"):
            console.print(result.get("result", ""))
        else:
            console.print(f"[red]{result.get('error', str(result))}[/red]")
        return True
    console.print(asyncio.run(fallback_fn()))
    return False


# ─── Daemon ──────────────────────────────────────────────


@app.command()
def daemon(
    action: str = typer.Argument("start", help="start, stop, or status"),
):
    if action == "start":
        from freeact.daemon import start_daemon_background
        result = start_daemon_background()
        if result.get("ok"):
            console.print(f"[green]{result.get('message')}[/green]")
        else:
            console.print(f"[red]{result.get('error')}[/red]")
    elif action == "stop":
        from freeact.daemon import stop_daemon
        result = stop_daemon()
        if result.get("ok"):
            console.print(f"[green]{result.get('message')}[/green]")
        else:
            console.print(f"[red]{result.get('error', 'Failed to stop daemon')}[/red]")
    elif action == "status":
        from freeact.daemon import is_daemon_running, send_daemon_command
        if is_daemon_running():
            result = send_daemon_command("/cmd/daemon", {"action": "status"})
            port = result.get('port', 9341)
            uptime = result.get('uptime', 0)
            version = result.get('version', '?')
            console.print(f"[green]Daemon running[/green] v{version} on port {port} (uptime: {uptime:.0f}s)")
        else:
            console.print("[yellow]Daemon not running[/yellow]")
    else:
        console.print("Usage: freeact daemon [start|stop|status]")


# ─── Browser ─────────────────────────────────────────────


@app.command()
def browser(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="open, list, create, update, delete, types, connect"),
    arg1: Optional[str] = typer.Argument(None, help="Browser ID or URL"),
    arg2: Optional[str] = typer.Argument(None, help="URL"),
    type: Optional[str] = typer.Option(None, "--type", help="Browser type (chrome/yandex/edge/chromium). Defaults to config default_browser"),
    name: Optional[str] = typer.Option(None, "--name", help="Browser name"),
    desc: Optional[str] = typer.Option(None, "--desc", help="Browser description"),
    desc_append: Optional[str] = typer.Option(None, "--desc-append", help="Append to description"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL (socks5://host:port)"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Remove proxy"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
    refresh_profile: bool = typer.Option(False, "--refresh-profile", help="Re-copy browser profile from source"),
):
    session_name = _ctx_session(ctx, session)
    config = get_config()

    # ── browser open ──
    if action == "open":
        if not arg1:
            console.print("[red]Error: browser ID required[/red]")
            return
        if not session_name:
            console.print("[red]Error: --session required[/red]")
            return

        bc = config.browsers.get(arg1)
        if not bc:
            bc = BrowserConfig(id=arg1, name=arg1, type=type or config.default_browser)
        elif bc.confirm_before_use:
            console.print(f"[yellow]Browser '{bc.name}' requires confirmation before use.[/yellow]")
            console.print(f"Type: {bc.type} | Proxy: {bc.proxy or 'none'}")
            response = typer.confirm("Continue?", default=True)
            if not response:
                return

        url = arg2 or "about:blank"
        dm_body = {
            "action": "open", "browser_id": arg1, "url": url,
            "session": session_name, "type": type or config.default_browser,
        }
        dm = _daemon_call("/cmd/browser", dm_body)
        if dm is not None:
            console.print(dm.get("result", dm.get("error", str(dm))))
            return

        async def _run():
            manager = await get_browser_manager()
            if "://" not in url and url != "about:blank":
                url_fixed = "https://" + url
            else:
                url_fixed = url
            bc = config.browsers.get(arg1)
            if not bc:
                bc = BrowserConfig(id=arg1, name=arg1, type=type or config.default_browser)
            page_config = FreeactConfig(
                browsers=config.browsers,
                default_browser=config.default_browser,
                headless=config.headless if not headed else False,
                timeout=config.timeout,
                proxy=config.proxy,
                stealth=config.stealth,
                api_key=config.api_key,
            )
            page = await manager.get_page(arg1, bc, page_config)
            if refresh_profile:
                await manager.refresh_profile(bc, page_config)
            await _ensure_page_state(page)
            if url_fixed and url_fixed != "about:blank":
                await page.goto(url_fixed, wait_until="domcontentloaded", timeout=30000)
                await wait_for_dom_stable(page, timeout_ms=5000)
            await manager.save_page_url(arg1, session_name, page.url)
            sm = get_session_manager()
            sm.create(session_name, arg1)
            return f"Browser '{arg1}' opened, session '{session_name}' started"
        console.print(asyncio.run(_run()))
        return

    # ── browser create ──
    if action == "create":
        if not name:
            console.print("[red]Error: --name required[/red]")
            return
        dm_body = {"action": "create", "name": name, "type": type or config.default_browser,
                    "desc": desc or "", "proxy": proxy or None}
        dm = _daemon_call("/cmd/browser", dm_body)
        if dm is not None:
            console.print(dm.get("result", dm.get("error", str(dm))))
            return

        async def _run():
            manager = await get_browser_manager()
            bid = manager.generate_browser_id()
            bc = BrowserConfig(id=bid, name=name, type=type or config.default_browser,
                               desc=desc or "", proxy=proxy or None)
            config.browsers[bid] = bc
            config.save()
            return f"Browser created: id={bid}, name={name}, type={bc.type}"
        console.print(asyncio.run(_run()))
        return

    # ── browser list / update / delete / types ──
    dm = _daemon_call("/cmd/browser", {"action": action, "browser_id": arg1,
                     "name": name, "desc": desc, "desc_append": desc_append,
                     "proxy": proxy, "no_proxy": no_proxy})
    if dm is not None:
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    async def _run():
        manager = await get_browser_manager()
        match action:
            case "list":
                if not config.browsers:
                    return "No browsers configured"
                lines = ["Browsers:"]
                for bid, bc in config.browsers.items():
                    px = f" proxy={bc.proxy}" if bc.proxy else ""
                    lines.append(f"  {bid}: name={bc.name}, type={bc.type}, desc={bc.desc}{px}")
                return "\n".join(lines)
            case "update":
                if not arg1:
                    return "Error: browser ID required"
                bc = config.browsers.get(arg1)
                if not bc:
                    return f"Error: browser '{arg1}' not found"
                if name:
                    bc.name = name
                if desc:
                    bc.desc = desc
                if desc_append:
                    bc.desc = (bc.desc + " " + desc_append) if bc.desc else desc_append
                if no_proxy:
                    bc.proxy = None
                elif proxy:
                    bc.proxy = proxy
                config.save()
                return f"Browser '{arg1}' updated"
            case "delete":
                if not arg1:
                    return "Error: browser ID required"
                config.browsers.pop(arg1, None)
                config.save()
                await manager.close_context(arg1)
                return f"Browser '{arg1}' deleted"
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
                return "\n".join(lines)
            case "connect":
                if not arg1:
                    return "Error: CDP URL or port required"
                cdp_url = arg1
                if cdp_url.isdigit():
                    cdp_url = f"http://127.0.0.1:{cdp_url}"
                if not session_name:
                    return "Error: --session required for browser connect"
                await manager.start()
                browser = await manager._playwright.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                await _ensure_page_state(page)
                if arg2:
                    nav_url = arg2
                    if "://" not in nav_url:
                        nav_url = "https://" + nav_url
                    await page.goto(nav_url, wait_until="domcontentloaded", timeout=30000)
                    await wait_for_dom_stable(page, timeout_ms=5000)
                    await manager.save_page_url("cdp", session_name, page.url)
                sm = get_session_manager()
                sm.create(session_name, "cdp")
                manager._browsers["cdp"] = browser
                manager._contexts["cdp"] = context
                return f"Connected to {cdp_url}, session '{session_name}' started"
            case _:
                return f"Unknown browser action: {action}"
    console.print(asyncio.run(_run()))


# ─── Direct-mode helpers ─────────────────────────────────


async def _ensure_page_state(page) -> None:
    await start_network_monitoring(page)
    await init_state_engine(page)


async def _get_page(session_name: str):
    sm = get_session_manager()
    s = sm.get(session_name)
    if not s:
        return None

    if s.browser_id == "live":
        from freeact.live import get_live_config, connect_to_live_browser
        cfg = get_live_config()
        port = cfg.get("port", 9222)
        result = await connect_to_live_browser(port)
        if result.get("ok"):
            br = result["cdp_browser"]
            manager = await get_browser_manager()
            saved_url = None
            try:
                saved_url = await manager.get_saved_url(session_name)
            except Exception:
                pass
            for ctx in br.contexts:
                for page in ctx.pages:
                    try:
                        await page.title()
                        if saved_url and saved_url in page.url:
                            return page
                    except Exception:
                        continue
            for ctx in br.contexts:
                for page in ctx.pages:
                    try:
                        await page.title()
                        return page
                    except Exception:
                        continue
        return None

    manager = await get_browser_manager()
    config = get_config()
    bc = config.browsers.get(s.browser_id)
    if not bc:
        bc = BrowserConfig(id=s.browser_id, name=s.browser_id)
    page = await manager.get_page(s.browser_id, bc, config)
    if page:
        saved_url = await manager.get_saved_url(session_name)
        if saved_url:
            try:
                cur = page.url
                if cur in ("about:blank", "") or cur.startswith("chrome://"):
                    await page.goto(saved_url, wait_until="domcontentloaded")
                    await wait_for_dom_stable(page, timeout_ms=5000)
            except Exception:
                pass
    return page


async def _get_page_with_state(session_name: str):
    page = await _get_page(session_name)
    if page:
        await _ensure_page_state(page)
    return page


# ─── Navigation ──────────────────────────────────────────


@app.command()
def navigate(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="URL to navigate to"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/navigate", {"session": s, "url": url}, lambda: _navigate_direct(s, url))


async def _navigate_direct(s: str, url: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    result = await h_navigate(page, url)
    manager = await get_browser_manager()
    sm = get_session_manager()
    sess = sm.get(s)
    if sess:
        await manager.save_page_url(sess.browser_id, s, page.url)
    return result


@app.command()
def back(ctx: typer.Context, session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/back", {"session": s}, lambda: _back_direct(s))


async def _back_direct(s: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_back(page)


@app.command()
def forward(ctx: typer.Context, session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/forward", {"session": s}, lambda: _forward_direct(s))


async def _forward_direct(s: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_forward(page)


@app.command()
def reload(ctx: typer.Context, session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/reload", {"session": s}, lambda: _reload_direct(s))


async def _reload_direct(s: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_reload(page)


# ─── Page State ──────────────────────────────────────────


@app.command()
def state(ctx: typer.Context, session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/state", {"session": s}, lambda: _state_direct(s))


async def _state_direct(s: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_state(page)


@app.command()
def screenshot(
    ctx: typer.Context,
    path: Optional[str] = typer.Argument(None, help="Save path (optional)"),
    full: bool = typer.Option(False, "--full", help="Full page screenshot"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/screenshot", {"session": s, "path": path, "full": full},
                lambda: _screenshot_direct(s, path, full))


async def _screenshot_direct(s: str, path: str | None, full: bool):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_screenshot(page, path, full)


# ─── Interaction ─────────────────────────────────────────


@app.command()
def click(ctx: typer.Context, index: int = typer.Argument(..., help="Element index from state"),
          session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/click", {"session": s, "index": index}, lambda: _click_direct(s, index))


async def _click_direct(s: str, index: int):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_click(page, index)


@app.command()
def input(ctx: typer.Context, index: int = typer.Argument(..., help="Element index from state"),
          text: str = typer.Argument(..., help="Text to type"),
          session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/input", {"session": s, "index": index, "text": text},
                lambda: _input_direct(s, index, text))


async def _input_direct(s: str, index: int, text: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_input(page, index, text)


@app.command()
def hover(ctx: typer.Context, index: int = typer.Argument(..., help="Element index from state"),
          session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/hover", {"session": s, "index": index}, lambda: _hover_direct(s, index))


async def _hover_direct(s: str, index: int):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_hover(page, index)


@app.command()
def select(ctx: typer.Context, index: int = typer.Argument(..., help="Element index from state"),
           option: str = typer.Argument(..., help="Option text to select"),
           session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/select", {"session": s, "index": index, "option": option},
                lambda: _select_direct(s, index, option))


async def _select_direct(s: str, index: int, option: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_select(page, index, option)


@app.command()
def keys(ctx: typer.Context, key: str = typer.Argument(..., help="Key to send (Enter, Tab, Escape, etc.)"),
         session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/keys", {"session": s, "key": key}, lambda: _keys_direct(s, key))


async def _keys_direct(s: str, key: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_keys(page, key)


@app.command()
def scroll(ctx: typer.Context, direction: str = typer.Argument(..., help="Direction: up or down"),
           amount: int = typer.Option(500, "--amount", help="Scroll amount in pixels"),
           session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/scroll", {"session": s, "direction": direction, "amount": amount},
                lambda: _scroll_direct(s, direction, amount))


async def _scroll_direct(s: str, direction: str, amount: int):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_scroll(page, direction, amount)


@app.command()
def scrollintoview(ctx: typer.Context, selector: str = typer.Option(..., "--selector", help="CSS selector"),
                   session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/scrollintoview", {"session": s, "selector": selector},
                lambda: _scrollintoview_direct(s, selector))


async def _scrollintoview_direct(s: str, selector: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_scrollintoview(page, selector)


@app.command()
def upload(ctx: typer.Context, index: int = typer.Argument(..., help="File input element index"),
           file_path: str = typer.Argument(..., help="Path to file to upload"),
           session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/upload", {"session": s, "index": index, "file_path": file_path},
                lambda: _upload_direct(s, index, file_path))


async def _upload_direct(s: str, index: int, file_path: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_upload(page, index, file_path)


# ─── Data Extraction ─────────────────────────────────────


@app.command()
def get(
    ctx: typer.Context,
    what: str = typer.Argument(..., help="What to get: title, html, markdown, text <index>, value <index>"),
    arg: Optional[str] = typer.Argument(None, help="Index for text/value"),
    selector: Optional[str] = typer.Option(None, "--selector", help="CSS selector for html"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/get", {"session": s, "what": what, "arg": arg, "selector": selector},
                lambda: _get_direct(s, what, arg, selector))


async def _get_direct(s: str, what: str, arg: str | None, selector: str | None):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_get(page, what, arg, selector)


@app.command()
def eval(ctx: typer.Context, js: str = typer.Argument(..., help="JavaScript to execute"),
         session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/eval", {"session": s, "js": js}, lambda: _eval_direct(s, js))


async def _eval_direct(s: str, js: str):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_eval(page, js)


# ─── Wait ─────────────────────────────────────────────────


@app.command()
def wait(
    ctx: typer.Context,
    what: str = typer.Argument("stable", help="What to wait for: stable, navigation"),
    timeout: int = typer.Option(30000, "--timeout", help="Timeout in ms"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)
    _try_daemon("/cmd/wait", {"session": s, "what": what, "timeout": timeout},
                lambda: _wait_direct(s, what, timeout))


async def _wait_direct(s: str, what: str, timeout: int):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_wait(page, what, timeout)


# ─── Network ──────────────────────────────────────────────


@app.command()
def network(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="Action: requests, request <id>, clear"),
    arg: Optional[str] = typer.Argument(None, help="Request ID/index"),
    filter: Optional[str] = typer.Option(None, "--filter", help="Filter by URL substring"),
    type: Optional[str] = typer.Option(None, "--type", help="Filter by type (xhr,fetch)"),
    method: Optional[str] = typer.Option(None, "--method", help="Filter by HTTP method"),
    status: Optional[str] = typer.Option(None, "--status", help="Filter by status code"),
    clear: bool = typer.Option(False, "--clear", help="Clear after listing"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)
    dm_body = {"session": s, "action": action, "arg": arg, "filter": filter,
               "type": type, "method": method, "status": status, "clear": clear}
    _try_daemon("/cmd/network", dm_body, lambda: _network_direct(s, action, arg, filter, type, method, status, clear))


async def _network_direct(s: str, action: str, arg: str | None, url_filter: str | None,
                          types: str | None, method: str | None, status: str | None, clear: bool):
    page = await _get_page_with_state(s)
    if not page:
        return f"Error: session '{s}' not found"
    return await h_network(page, action, arg, url_filter, types, method, status, clear)


# ─── Session ──────────────────────────────────────────────


@app.command()
def session(action: str = typer.Argument(..., help="Action: list, close <name>"),
            name: Optional[str] = typer.Argument(None, help="Session name")):
    dm = _daemon_call("/cmd/session", {"action": action, "name": name})
    if dm is not None:
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    sm = get_session_manager()
    match action:
        case "list":
            sessions = sm.list_sessions()
            if not sessions:
                console.print("No active sessions")
                return
            console.print("Active sessions:")
            for s in sessions:
                console.print(f"  {s.name}: browser={s.browser_id}")
        case "close":
            if not name:
                console.print("Error: session name required")
                return

            async def _close():
                manager = await get_browser_manager()
                sm.close(name)
                await manager.close_context(name)

            asyncio.run(_close())
            console.print(f"Session '{name}' closed")
        case _:
            console.print(f"Unknown session action: {action}")


# ─── CAPTCHA ──────────────────────────────────────────────


@app.command()
def solve_captcha(ctx: typer.Context, session: Optional[str] = typer.Option(None, "--session", help="Session name")):
    s = _req_session(ctx, session)

    async def _run():
        dm = _daemon_call("/cmd/solve-captcha", {"session": s})
        if dm is not None:
            return dm
        page = await _get_page_with_state(s)
        if not page:
            return {"ok": False, "error": f"Session '{s}' not found"}
        from freeact.captcha import solve_captcha_on_page
        return await solve_captcha_on_page(page)

    result = asyncio.run(_run())
    if result.get("solved"):
        console.print(f"[green]CAPTCHA solved![/green] Method: {result.get('method', 'auto')}")
    else:
        console.print(f"[yellow]CAPTCHA not solved: {result.get('error', 'unknown')}[/yellow]")


# ─── Remote Assist ───────────────────────────────────────


@app.command()
def remote_assist(
    ctx: typer.Context,
    objective: Optional[str] = typer.Option("Manual browser intervention", "--objective", "-o",
                                             help="What the user should do"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        dm = _daemon_call("/cmd/remote-assist", {"session": s, "objective": objective})
        if dm is not None:
            return dm
        page = await _get_page_with_state(s)
        if not page:
            return {"ok": False, "error": f"Session '{s}' not found"}
        from freeact.remote import start_remote_assist
        return await start_remote_assist(page, objective)

    asyncio.run(_run())
    console.print("[cyan]Remote assist active[/cyan]")
    console.print(f"Objective: {objective}")
    console.print("Browser window is visible. Complete the action, then the agent will continue.")


# ─── Stealth Extract ──────────────────────────────────────


@app.command()
def stealth_extract(
    url: str = typer.Argument(..., help="URL to extract content from"),
    content_type: str = typer.Option("markdown", "--content-type", help="Output format: markdown, html"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to file"),
):
    dm_body = {"url": url, "content_type": content_type, "proxy": proxy,
               "timeout": timeout, "output": output}
    dm = _daemon_call("/cmd/stealth-extract", dm_body)
    if dm is not None:
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    async def _run():
        from playwright.async_api import async_playwright
        from freeact.proxy import parse_proxy_config
        from freeact.stealth import apply_stealth_patches
        async with async_playwright() as pw:
            launch_opts = {"headless": True}
            if proxy:
                launch_opts["proxy"] = parse_proxy_config(proxy)
            browser = await pw.chromium.launch(**launch_opts)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})
            await apply_stealth_patches(context)
            page = await context.new_page()
            try:
                goto_url = url
                if "://" not in goto_url:
                    goto_url = "https://" + goto_url
                await page.goto(goto_url, wait_until="networkidle", timeout=timeout * 1000)
                content = await page.content() if content_type == "html" else await get_markdown(page)
                if output:
                    Path(output).write_text(content, encoding="utf-8")
                    return f"Content saved to {output}"
                return content
            except Exception as e:
                return f"Error extracting {url}: {e}"
            finally:
                await browser.close()
    console.print(asyncio.run(_run()))


# ─── Live Browser ─────────────────────────────────────────


@app.command()
def connect(browser: Optional[str] = typer.Option("yandex", "--browser", "-b", help="Browser: yandex, chrome, edge"),
            port: Optional[int] = typer.Option(0, "--port", "-p", help="CDP port (0=auto-detect)")):
    dm = _daemon_call("/cmd/connect", {"browser": browser, "port": port})
    if dm is not None:
        if dm.get("ok"):
            console.print(f"[green]{dm.get('message')}[/green]")
            for p in dm.get("pages", []):
                console.print(f"  Tab: {p.get('title', '?')[:80]}")
        else:
            console.print(f"[red]{dm.get('error')}[/red]")
        return

    async def _run():
        from freeact.live import detect_browser_cdp, connect_to_live_browser
        detected = detect_browser_cdp(browser or "yandex")
        if detected:
            console.print(f"[dim]Found {detected['browser']} on port {detected['port']}[/dim]")
            return await connect_to_live_browser(detected["port"])
        console.print("[yellow]Browser not running with CDP.[/yellow]")
        console.print("Run: [green]freeact setup --browser yandex[/green] for one-time setup")
        return {"ok": False, "error": "Browser not running with CDP. Run: freeact setup"}
    result = asyncio.run(_run())
    if result.get("ok"):
        sm = get_session_manager()
        sm.create("live", "live")
        console.print(f"[green]Connected![/green] {result.get('tabs', 0)} tabs")
        for p in result.get("pages", []):
            console.print(f"  Tab: {p.get('title', '?')[:80]}")


@app.command()
def setup(browser: Optional[str] = typer.Option("yandex", "--browser", "-b", help="Browser: yandex, chrome, edge"),
          port: Optional[int] = typer.Option(9222, "--port", "-p", help="CDP port")):
    from freeact.live import setup_browser_cdp
    result = setup_browser_cdp(browser, port or 9222)
    if result.get("ok"):
        console.print(f"[green]{result['message']}[/green]")
    else:
        console.print(f"[red]{result.get('error')}[/red]")


@app.command()
def tabs():
    dm = _daemon_call("/cmd/tabs", {})
    if dm is not None:
        if dm.get("ok"):
            for t in dm.get("tabs", []):
                console.print(f"  [{t['id']}] {t['title'][:80]}")
                console.print(f"       {t['url'][:100]}")
        else:
            console.print(f"[red]{dm.get('error')}[/red]")
        return
    from freeact.live import list_tabs, get_live_config
    cfg = get_live_config()
    result = asyncio.run(list_tabs(cfg.get("port", 9222)))
    if result.get("ok"):
        for t in result.get("tabs", []):
            console.print(f"  [{t['id']}] {t['title'][:80]}")
            console.print(f"       {t['url'][:100]}")
    else:
        console.print(f"[red]{result.get('error')}[/red]")


@app.command()
def tab(action: str = typer.Argument(..., help="switch <id>, close <id>, new [url]"),
        arg: Optional[str] = typer.Argument(None, help="Tab index or URL")):
    dm_path = {"switch": "/cmd/tab-switch", "close": "/cmd/tab-close", "new": "/cmd/tab-new"}.get(action)
    if not dm_path:
        console.print(f"Unknown action: {action}. Use: switch <N>, close <N>, new <url>")
        return
    if action != "new":
        dm_body = {"index": int(arg) if arg else 0}
    else:
        dm_body = {"url": arg or "about:blank"}
    dm = _daemon_call(dm_path, dm_body)
    if dm is not None:
        console.print(dm.get("message", dm.get("result", dm.get("error", json.dumps(dm)))))
        return

    async def _run():
        from freeact.live import switch_tab, close_tab, new_tab, get_live_config
        cfg = get_live_config()
        port = cfg.get("port", 9222)
        if action == "switch":
            return await switch_tab(port, int(arg) if arg else 0)
        elif action == "close":
            return await close_tab(port, int(arg) if arg else 0)
        elif action == "new":
            return await new_tab(port, arg or "about:blank")
    result = asyncio.run(_run())
    console.print(result.get("message", result.get("error", str(result))))


# ─── Utility ──────────────────────────────────────────────


@app.command()
def proxy(action: str = typer.Argument("list", help="Action: list")):
    config = get_config()
    if action == "list":
        if not config.browsers:
            console.print("No browsers configured")
            return
        for bid, bc in config.browsers.items():
            console.print(f"  {bc.name}: proxy={bc.proxy or 'none'}")


@app.command()
def get_skills(topic: str = typer.Argument(..., help="Topic: core, advanced, main"),
               skill_version: Optional[str] = typer.Option(None, "--skill-version", help="Skill version")):
    match topic:
        case "core":
            content = get_skills_core(skill_version or __version__)
        case "advanced":
            content = get_skills_advanced()
        case "main":
            skill_path = Path(__file__).parent.parent / "SKILL.md"
            content = skill_path.read_text(encoding="utf-8") if skill_path.exists() else "# FreeAct"
        case _:
            content = f"Unknown topic: {topic}"
    console.print(content)


@app.command()
def forge(name: str = typer.Option(..., "--name", help="Skill name"),
          url: str = typer.Option(..., "--url", help="Target URL"),
          desc: str = typer.Option("", "--desc", help="Description"),
          params: Optional[str] = typer.Option(None, "--params", help="Parameters as JSON list"),
          output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory")):
    import json as _json
    parameters = []
    if params:
        try:
            parameters = _json.loads(params)
        except _json.JSONDecodeError:
            console.print("Error: --params must be valid JSON")
            return
    if not parameters:
        parameters = [{"name": "keyword", "description": "Search keyword"}]
    from freeact.skillforge import explore_and_generate
    result = explore_and_generate(skill_name=name, target_url=url,
                                  description=desc or f"Extract data from {url}",
                                  parameters=parameters, output_dir=output)
    if result.get("ok"):
        console.print("[green]Skill generated![/green]")
        console.print(f"Output: {result['output_dir']}")
        for f in result.get("files", []):
            console.print(f"  - {f}")
    else:
        console.print(f"[red]Error: {result.get('error')}[/red]")


# ─── Main ─────────────────────────────────────────────────


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context,
         session: Optional[str] = typer.Option(None, "--session", help="Session name"),
         version: bool = typer.Option(False, "--version", "-v", help="Show version")):
    ctx.ensure_object(dict)
    ctx.obj["session"] = session
    if version:
        console.print(f"freeact v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        _auto_setup_shortcut()
        console.print("[bold cyan]Free Browser Agent CLI[/bold cyan]")
        console.print(f"Version: {__version__}")
        console.print("Run [green]freeact --help[/green] for available commands")


def _auto_setup_shortcut():
    shortcut = Path.home() / "Desktop" / "Yandex (FreeAct).lnk"
    if not shortcut.exists():
        from freeact.live import setup_browser_cdp
        try:
            setup_browser_cdp("yandex")
        except Exception:
            pass


def main_cli():
    app()


if __name__ == "__main__":
    main_cli()
