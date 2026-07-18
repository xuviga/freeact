"""Free Browser Agent CLI — main entry point."""

import asyncio
import sys
import io
import json
from pathlib import Path
from typing import Optional

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import typer
from rich.console import Console

from freeact import __version__
from freeact.browser import get_browser_manager
from freeact.config import BrowserConfig, get_config
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
from freeact.skills import get_skills_advanced, get_skills_core
from freeact.state import get_page_state

app = typer.Typer(
    name="freeact",
    help="Free Browser Agent CLI — browser automation for AI agents",
    add_completion=False,
    no_args_is_help=True,
    context_settings={"obj": {}},
)

console = Console(force_terminal=True, legacy_windows=False)


def _ctx_session(ctx: typer.Context, opt: Optional[str] = None) -> Optional[str]:
    return opt or ctx.obj.get("session")


def _req_session(ctx: typer.Context, opt: Optional[str] = None) -> str:
    s = _ctx_session(ctx, opt)
    if not s:
        console.print("Error: --session required")
        raise typer.Exit(1)
    return s


def _daemon_call(path: str, body: dict) -> dict | None:
    """Try daemon first, return None if daemon not running."""
    try:
        from freeact.daemon import is_daemon_running, send_daemon_command
        if is_daemon_running():
            return send_daemon_command(path, body)
    except Exception:
        pass
    return None


def _run_or_daemon(session: str, path: str, body: dict, fallback_fn):
    """Route to daemon if available, otherwise run locally."""
    result = _daemon_call(path, {**body, "session": session})
    if result is not None:
        return result
    return asyncio.run(fallback_fn(session))


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
    version: bool = typer.Option(False, "--version", "-v", help="Show version"),
):
    ctx.ensure_object(dict)
    ctx.obj["session"] = session
    if version:
        console.print(f"freeact v{__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        console.print("[bold cyan]Free Browser Agent CLI[/bold cyan]")
        console.print(f"Version: {__version__}")
        console.print("Run [green]freeact --help[/green] for available commands")


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
            pw = result["browser"]
            br = result["cdp_browser"]
            ctxs = br.contexts
            for ctx in ctxs:
                for page in ctx.pages:
                    try:
                        await page.title()
                        return page
                    except Exception:
                        continue
            for ctx in ctxs:
                if ctx.pages:
                    return ctx.pages[0]
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
            except Exception:
                pass
    return page


def _session_cmd(fn):
    """Decorator: resolves session, gets page, runs async fn, prints result."""
    import functools

    @functools.wraps(fn)
    def wrapper(ctx: typer.Context, *args, session: Optional[str] = None, **kwargs):
        s = _req_session(ctx, session)

        async def _run():
            page = await _get_page(s)
            if not page:
                return f"Error: session '{s}' not found"
            return await fn(page, *args, **kwargs)

        console.print(asyncio.run(_run()))

    return wrapper


# ─── Navigation ───────────────────────────────────────────

@app.command()
def navigate(
    ctx: typer.Context,
    url: str = typer.Argument(..., help="URL to navigate to"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)
    dm = _daemon_call("/cmd/navigate", {"session": s, "url": url})
    if dm is not None and dm.get("ok"):
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        await start_network_monitoring(page)
        if "://" not in url:
            url = "https://" + url
        await page.goto(url, wait_until="domcontentloaded")
        manager = await get_browser_manager()
        sm = get_session_manager()
        sess = sm.get(s)
        if sess:
            await manager.save_page_url(sess.browser_id, s, page.url)
        return f"Navigated to {url}"
    console.print(asyncio.run(_run()))


@app.command()
def back(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        await page.go_back()
        return "Navigated back"

    console.print(asyncio.run(_run()))


@app.command()
def forward(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        await page.go_forward()
        return "Navigated forward"

    console.print(asyncio.run(_run()))


@app.command()
def reload(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        await page.reload()
        return "Page reloaded"

    console.print(asyncio.run(_run()))


# ─── Page State ──────────────────────────────────────────

@app.command()
def state(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    dm = _daemon_call("/cmd/state", {"session": s})
    if dm is not None and dm.get("ok"):
        console.print(dm.get("result", ""))
        return

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        await start_network_monitoring(page)
        return await get_page_state(page)

    console.print(asyncio.run(_run()))


@app.command()
def screenshot(
    ctx: typer.Context,
    path: Optional[str] = typer.Argument(None, help="Save path (optional)"),
    full: bool = typer.Option(False, "--full", help="Full page screenshot"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await take_screenshot(page, path, full)

    console.print(asyncio.run(_run()))


# ─── Interaction ─────────────────────────────────────────

@app.command()
def click(
    ctx: typer.Context,
    index: int = typer.Argument(..., help="Element index from state"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    dm = _daemon_call("/cmd/click", {"session": s, "index": index})
    if dm is not None and dm.get("ok"):
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await click_element(page, index)
    console.print(asyncio.run(_run()))


@app.command()
def input(
    ctx: typer.Context,
    index: int = typer.Argument(..., help="Element index from state"),
    text: str = typer.Argument(..., help="Text to type"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    dm = _daemon_call("/cmd/input", {"session": s, "index": index, "text": text})
    if dm is not None and dm.get("ok"):
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await input_text(page, index, text)
    console.print(asyncio.run(_run()))


@app.command()
def hover(
    ctx: typer.Context,
    index: int = typer.Argument(..., help="Element index from state"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await hover_element(page, index)

    console.print(asyncio.run(_run()))


@app.command()
def select(
    ctx: typer.Context,
    index: int = typer.Argument(..., help="Element index from state"),
    option: str = typer.Argument(..., help="Option text to select"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await select_option(page, index, option)

    console.print(asyncio.run(_run()))


@app.command()
def keys(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Key to send (Enter, Tab, Escape, etc.)"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await send_keys(page, key)

    console.print(asyncio.run(_run()))


@app.command()
def scroll(
    ctx: typer.Context,
    direction: str = typer.Argument(..., help="Direction: up or down"),
    amount: int = typer.Option(500, "--amount", help="Scroll amount in pixels"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await scroll_page(page, direction, amount)

    console.print(asyncio.run(_run()))


@app.command()
def scrollintoview(
    ctx: typer.Context,
    selector: str = typer.Option(..., "--selector", help="CSS selector"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await scroll_by_selector(page, selector)

    console.print(asyncio.run(_run()))


@app.command()
def upload(
    ctx: typer.Context,
    index: int = typer.Argument(..., help="File input element index"),
    file_path: str = typer.Argument(..., help="Path to file to upload"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await upload_file(page, index, file_path)

    console.print(asyncio.run(_run()))


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
    dm = _daemon_call("/cmd/get", {"session": s, "what": what, "arg": arg, "selector": selector})
    if dm is not None and dm.get("ok"):
        console.print(dm.get("result", dm.get("error", str(dm))))
        return

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        match what:
            case "title": return await get_title(page)
            case "html": return await get_html(page, selector)
            case "markdown": return await get_markdown(page)
            case "text":
                if not arg: return "Error: index required for 'get text'"
                return await get_element_text(page, int(arg))
            case "value":
                if not arg: return "Error: index required for 'get value'"
                return await get_element_value(page, int(arg))
            case _: return f"Error: unknown get type '{what}'"
    console.print(asyncio.run(_run()))


@app.command()
def eval(
    ctx: typer.Context,
    js: str = typer.Argument(..., help="JavaScript to execute"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        return await evaluate_js(page, js)

    console.print(asyncio.run(_run()))


# ─── Wait ────────────────────────────────────────────────

@app.command()
def wait(
    ctx: typer.Context,
    what: str = typer.Argument("stable", help="What to wait for: stable"),
    timeout: int = typer.Option(30000, "--timeout", help="Timeout in ms"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        if what == "stable":
            try:
                await page.wait_for_load_state("networkidle", timeout=timeout)
                return "Page stable"
            except Exception as e:
                return f"Wait timeout: {e}"
        return f"Unknown wait type: {what}"

    console.print(asyncio.run(_run()))


# ─── Network ─────────────────────────────────────────────

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

    async def _run():
        page = await _get_page(s)
        if not page:
            return f"Error: session '{s}' not found"
        match action:
            case "requests":
                return await get_network_requests(
                    page, url_filter=filter, types=type,
                    method=method, status=status, clear=clear,
                )
            case "request":
                if not arg:
                    return "Error: request index required"
                return await get_network_request_detail(page, int(arg))
            case "clear":
                await clear_network_requests(page)
                return "Network log cleared"
            case _:
                return f"Unknown network action: {action}"

    console.print(asyncio.run(_run()))


# ─── Session ─────────────────────────────────────────────

@app.command()
def session(
    action: str = typer.Argument(..., help="Action: list, close <name>"),
    name: Optional[str] = typer.Argument(None, help="Session name"),
):
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


# ─── Browser ─────────────────────────────────────────────

@app.command()
def browser(
    ctx: typer.Context,
    action: str = typer.Argument(..., help="Action: open, list, create, update, delete"),
    arg1: Optional[str] = typer.Argument(None, help="Browser ID or URL"),
    arg2: Optional[str] = typer.Argument(None, help="URL or arg"),
    type: Optional[str] = typer.Option("chromium", "--type", help="Browser type"),
    name: Optional[str] = typer.Option(None, "--name", help="Browser name"),
    desc: Optional[str] = typer.Option(None, "--desc", help="Browser description"),
    desc_append: Optional[str] = typer.Option(None, "--desc-append", help="Append to description"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    no_proxy: bool = typer.Option(False, "--no-proxy", help="Remove proxy"),
    headed: bool = typer.Option(False, "--headed", help="Show browser window"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    config = get_config()

    async def _run():
        manager = await get_browser_manager()

        match action:
            case "open":
                session_name = _ctx_session(ctx, session)
                if not arg1:
                    return "Error: browser ID required"
                if not session_name:
                    return "Error: --session required"

                url = arg2 or "about:blank"
                if "://" not in url and url != "about:blank":
                    url = "https://" + url

                bc = config.browsers.get(arg1)
                if not bc:
                    bc = BrowserConfig(id=arg1, name=arg1, type=type or "chromium")
                if headed:
                    config.headless = False

                page = await manager.get_page(arg1, bc, config)
                await start_network_monitoring(page)
                if url and url != "about:blank":
                    await page.goto(url, wait_until="domcontentloaded")

                await manager.save_page_url(arg1, session_name, page.url)
                sm = get_session_manager()
                sm.create(session_name, arg1)
                return f"Browser '{arg1}' opened, session '{session_name}' started"

            case "list":
                if not config.browsers:
                    return "No browsers configured"
                lines = ["Browsers:"]
                for bid, bc in config.browsers.items():
                    px = f" proxy={bc.proxy}" if bc.proxy else ""
                    lines.append(f"  {bid}: name={bc.name}, type={bc.type}, desc={bc.desc}{px}")
                return "\n".join(lines)

            case "create":
                if not name:
                    return "Error: --name required"
                bid = manager.generate_browser_id()
                bc = BrowserConfig(
                    id=bid, name=name, type=type or "chromium",
                    desc=desc or "", proxy=proxy or None,
                )
                config.browsers[bid] = bc
                config.save()
                return f"Browser created: id={bid}, name={name}, type={bc.type}"

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

            case "connect":
                if not arg1:
                    return "Error: CDP URL or port required"
                cdp_url = arg1
                if cdp_url.isdigit():
                    cdp_url = f"http://127.0.0.1:{cdp_url}"
                session_name = _ctx_session(ctx, session)
                if not session_name:
                    return "Error: --session required for browser connect"

                await manager.start()
                browser = await manager._playwright.chromium.connect_over_cdp(cdp_url)
                context = browser.contexts[0] if browser.contexts else await browser.new_context()
                page = context.pages[0] if context.pages else await context.new_page()
                await start_network_monitoring(page)
                if arg2:
                    nav_url = arg2
                    if "://" not in nav_url:
                        nav_url = "https://" + nav_url
                    await page.goto(nav_url, wait_until="domcontentloaded")
                    await manager.save_page_url("cdp", session_name, page.url)
                sm = get_session_manager()
                sm.create(session_name, "cdp")
                manager._browsers["cdp"] = browser
                manager._contexts["cdp"] = context
                return f"Connected to {cdp_url}, session '{session_name}' started"

            case "types":
                from freeact.browser import find_browser, BROWSER_MAP
                lines = ["Available real browsers:"]
                for key, info in BROWSER_MAP.items():
                    found = None
                    for p in info["paths"]:
                        if Path(p).exists():
                            found = str(p)
                            break
                    status = found or "NOT FOUND"
                    lines.append(f"  {info['name']}: {status}")
                    lines.append(f"    profile: {info['profile']}")
                return "\n".join(lines)

            case _:
                return f"Unknown browser action: {action}"

    console.print(asyncio.run(_run()))


# ─── Stealth Extract ─────────────────────────────────────

@app.command()
def stealth_extract(
    url: str = typer.Argument(..., help="URL to extract content from"),
    content_type: str = typer.Option("markdown", "--content-type", help="Output format"),
    proxy: Optional[str] = typer.Option(None, "--proxy", help="Proxy URL"),
    timeout: int = typer.Option(30, "--timeout", help="Timeout in seconds"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Save to file"),
):
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


# ─── Proxy ────────────────────────────────────────────────

@app.command()
def proxy(action: str = typer.Argument("list", help="Action: list")):
    config = get_config()
    if action == "list":
        if not config.browsers:
            console.print("No browsers configured")
            return
        for bid, bc in config.browsers.items():
            console.print(f"  {bc.name}: proxy={bc.proxy or 'none'}")


# ─── get-skills ──────────────────────────────────────────

@app.command()
def get_skills(
    topic: str = typer.Argument(..., help="Topic: core, advanced, main"),
    skill_version: Optional[str] = typer.Option(None, "--skill-version", help="Skill version"),
):
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


# ─── Daemon ──────────────────────────────────────────────

@app.command()
def daemon(
    action: str = typer.Argument("start", help="start or stop"),
):
    if action == "start":
        from freeact.daemon import run_daemon
        run_daemon()
    elif action == "stop":
        from freeact.daemon import send_daemon_command
        result = send_daemon_command("/cmd/daemon", {"action": "stop"})
        console.print(result.get("result", "Daemon stopped"))
    elif action == "status":
        from freeact.daemon import is_daemon_running
        if is_daemon_running():
            from freeact.daemon import send_daemon_command
            result = send_daemon_command("/cmd/daemon", {"action": "status"})
            console.print(f"Daemon running on port {result.get('port', 9341)}")
        else:
            console.print("Daemon not running")
    else:
        console.print("Usage: freeact daemon [start|stop|status]")


# ─── Solve CAPTCHA ──────────────────────────────────────

@app.command()
def solve_captcha(
    ctx: typer.Context,
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        from freeact.daemon import is_daemon_running, send_daemon_command
        if is_daemon_running():
            return send_daemon_command("/cmd/solve-captcha", {"session": s})

        page = await _get_page(s)
        if not page:
            return {"ok": False, "error": f"Session '{s}' not found"}
        from freeact.captcha import solve_captcha_on_page
        return await solve_captcha_on_page(page)

    result = asyncio.run(_run())
    if result.get("solved"):
        console.print(f"[green]CAPTCHA solved![/green] Method: {result.get('method', 'auto')}")
    else:
        console.print(f"[yellow]CAPTCHA not solved: {result.get('error', 'unknown')}[/yellow]")


# ─── Remote Assist ──────────────────────────────────────

@app.command()
def remote_assist(
    ctx: typer.Context,
    objective: Optional[str] = typer.Option("Manual browser intervention", "--objective", "-o", help="What the user should do"),
    session: Optional[str] = typer.Option(None, "--session", help="Session name"),
):
    s = _req_session(ctx, session)

    async def _run():
        from freeact.daemon import is_daemon_running, send_daemon_command
        if is_daemon_running():
            return send_daemon_command("/cmd/remote-assist", {"session": s, "objective": objective})

        page = await _get_page(s)
        if not page:
            return {"ok": False, "error": f"Session '{s}' not found"}
        from freeact.remote import start_remote_assist
        return await start_remote_assist(page, objective)

    result = asyncio.run(_run())
    console.print(f"[cyan]Remote assist active[/cyan]")
    console.print(f"Objective: {objective}")
    console.print("Browser window is visible. Complete the action, then the agent will continue.")


# ─── Forge ──────────────────────────────────────────────

@app.command()
def forge(
    name: str = typer.Option(..., "--name", help="Skill name"),
    url: str = typer.Option(..., "--url", help="Target URL"),
    desc: str = typer.Option("", "--desc", help="Description"),
    params: Optional[str] = typer.Option(None, "--params", help="Parameters as JSON list"),
    output: Optional[str] = typer.Option(None, "--output", "-o", help="Output directory"),
):
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
    result = explore_and_generate(
        skill_name=name,
        target_url=url,
        description=desc or f"Extract data from {url}",
        parameters=parameters,
        output_dir=output,
    )

    if result.get("ok"):
        console.print(f"[green]Skill generated![/green]")
        console.print(f"Output: {result['output_dir']}")
        for f in result.get("files", []):
            console.print(f"  - {f}")
    else:
        console.print(f"[red]Error: {result.get('error')}[/red]")


# ─── Live Browser ──────────────────────────────────────

@app.command()
def connect(
    browser: Optional[str] = typer.Option("yandex", "--browser", "-b", help="Browser: yandex, chrome, edge"),
    port: Optional[int] = typer.Option(0, "--port", "-p", help="CDP port (0=auto-detect)"),
):
    """Connect to your REAL running browser. Does NOT restart — needs browser with CDP enabled."""
    from freeact.live import detect_browser_cdp, connect_to_live_browser, save_live_config

    dm = _daemon_call("/cmd/connect", {"browser": browser, "port": port})
    if dm is not None and dm.get("ok"):
        console.print(f"[green]{dm.get('message')}[/green]")
        for p in dm.get("pages", []):
            console.print(f"  Tab: {p.get('title', '?')[:80]}")
        return

    async def _run():
        detected = detect_browser_cdp()
        if detected:
            console.print(f"[dim]Found {detected['browser']} on port {detected['port']}[/dim]")
            return await connect_to_live_browser(detected["port"])

        console.print("[yellow]Browser not running with CDP.[/yellow]")
        console.print("")
        console.print("One-time setup (30 seconds):")
        console.print(f"  [green]freeact setup --browser {browser}[/green]")
        console.print("")
        console.print("This creates a 'Yandex (FreeAct)' shortcut on your desktop.")
        console.print("Use it for daily browsing — freeact connects anytime.")
        return {"ok": False, "error": "Browser not running with CDP. Run: freeact setup"}

    result = asyncio.run(_run())
    if result.get("ok"):
        sm = get_session_manager()
        sm.create("live", "live")
        console.print(f"[green]Connected![/green] {result.get('tabs', 0)} tabs — your profile, passwords, everything intact")
        for p in result.get("pages", []):
            console.print(f"  Tab: {p.get('title', '?')[:80]}")


@app.command()
def setup(
    browser: Optional[str] = typer.Option("yandex", "--browser", "-b", help="Browser: yandex, chrome, edge"),
    port: Optional[int] = typer.Option(9222, "--port", "-p", help="CDP port"),
):
    """Create desktop shortcut: browser with CDP always enabled. One-time setup."""
    from freeact.live import setup_browser_cdp
    result = setup_browser_cdp(browser, port or 9222)
    if result.get("ok"):
        console.print(f"[green]{result['message']}[/green]")
    else:
        console.print(f"[red]{result.get('error')}[/red]")


@app.command()
def tabs():
    """List all open tabs in your connected browser."""
    dm = _daemon_call("/cmd/tabs", {})
    if dm is not None and dm.get("ok"):
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
def tab(
    action: str = typer.Argument(..., help="switch <id>, close <id>, new [url]"),
    arg: Optional[str] = typer.Argument(None, help="Tab index or URL"),
):
    """Manage browser tabs: switch, close, open new."""
    dm_path = None
    dm_body = {}

    if action == "switch":
        dm_path = "/cmd/tab-switch"
        dm_body = {"index": int(arg) if arg else 0}
    elif action == "close":
        dm_path = "/cmd/tab-close"
        dm_body = {"index": int(arg) if arg else 0}
    elif action == "new":
        dm_path = "/cmd/tab-new"
        dm_body = {"url": arg or "about:blank"}
    else:
        console.print(f"Unknown action: {action}. Use: switch <N>, close <N>, new <url>")
        return

    dm = _daemon_call(dm_path, dm_body)
    if dm is not None and dm.get("ok"):
        console.print(dm.get("message", dm.get("error", json.dumps(dm))))
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


def main_cli():
    app()


if __name__ == "__main__":
    main_cli()
