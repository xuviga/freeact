"""get-skills system — dynamic runtime content for AI agents."""

from pathlib import Path

from freeact import __version__
from freeact.config import get_config


def get_skills_core(skill_version: str = "0.1.0") -> str:
    config = get_config()

    lines = [
        "## Core interaction",
        "",
        "Choose one path based on the task:",
        "",
        "**Stealth extraction (WebFetch replacement)** — read-only content extraction with JS rendering.",
        "No browser to manage, no session to name, no cleanup required. Each call is independent.",
        "",
        "```bash",
        "freeact stealth-extract <url>",
        "freeact stealth-extract <url> --content-type markdown    # also supports: html",
        "freeact stealth-extract <url> --proxy socks5://host:port  # custom proxy",
        "```",
        "",
        "**Full browser automation** — Open -> State -> Interact -> Verify -> Close loop:",
        "",
        "```bash",
        "# 1. Open browser",
        "freeact --session <name> browser open <id> <url>",
        "",
        "# 2. Inspect page elements",
        "freeact --session <name> state",
        "# Output: [1]<button> Login, [2]<input type=email placeholder=Email>, [3]<input type=password placeholder=Password>",
        "",
        "# 3. Interact (use index numbers from state)",
        "freeact --session <name> input 2 \"user@example.com\"",
        "freeact --session <name> input 3 \"password123\"",
        "freeact --session <name> click 1",
        "",
        "# 4. Wait for page to stabilize, then re-fetch indices",
        "freeact --session <name> wait stable",
        "freeact --session <name> state",
        "",
        "# 5. Extract data",
        "freeact --session <name> get markdown",
        "freeact --session <name> get text 5",
        "freeact --session <name> network requests --type xhr,fetch",
        "",
        "# 6. Close session",
        "freeact session close <name>",
        "```",
        "",
        "## Core commands",
        "",
        "All browser operation commands require `--session <name>`.",
        "",
        "Session rules:",
        "- A session name identifies a currently running session",
        "- Close your sessions when done (`session close <name>`)",
        "- Globally unique session names across browsers",
        "",
        "```bash",
        "# Open browser",
        "freeact --session <name> browser open <id> <url>",
        "freeact --session <name> browser open <id> <url> --headed",
        "",
        "# Browser list",
        "freeact browser list",
        "",
        "# Browser create",
        "freeact browser create --type chromium --name <name> --desc <desc>",
        "freeact browser create --type chromium --name <name> --desc <desc> --proxy socks5://host:port",
        "",
        "# Browser update",
        "freeact browser update <id> --name <new-name>",
        "freeact browser update <id> --desc <text>",
        "freeact browser update <id> --desc-append <text>",
        "freeact browser update <id> --proxy socks5://host:port",
        "freeact browser update <id> --no-proxy",
        "",
        "# Browser delete",
        "freeact browser delete <id>",
        "",
        "# Navigation",
        "freeact --session <name> navigate <url>",
        "freeact --session <name> back",
        "freeact --session <name> forward",
        "freeact --session <name> reload",
        "",
        "# Page state and interaction",
        "freeact --session <name> state",
        "freeact --session <name> screenshot",
        "freeact --session <name> screenshot ./page.png",
        "freeact --session <name> click <index>",
        "freeact --session <name> hover <index>",
        "freeact --session <name> input <index> \"text\"",
        "freeact --session <name> select <index> \"option\"",
        "freeact --session <name> keys \"Enter\"",
        "freeact --session <name> scroll down",
        "freeact --session <name> scroll up --amount 1000",
        "freeact --session <name> scrollintoview --selector \"h1\"",
        "freeact --session <name> upload <index> <file_path>",
        "",
        "# Data extraction",
        "freeact --session <name> get title",
        "freeact --session <name> get html",
        "freeact --session <name> get markdown",
        "freeact --session <name> get text <index>",
        "freeact --session <name> get value <index>",
        "freeact --session <name> network requests",
        "freeact --session <name> network requests --filter api.example.com",
        "freeact --session <name> network requests --type xhr,fetch",
        "freeact --session <name> network requests --method POST",
        "freeact --session <name> network request <id>",
        "",
        "# JavaScript",
        "freeact --session <name> eval \"document.title\"",
        "",
        "# Wait",
        "freeact --session <name> wait stable",
        "freeact --session <name> wait navigation",
        "freeact --session <name> wait stable --timeout 60000",
        "",
        "# Session",
        "freeact session list",
        "freeact session close <name>",
        "",
        "# Proxy",
        "freeact proxy list",
        "",
        "# Stealth extract (no session needed)",
        "freeact stealth-extract <url>",
        "freeact stealth-extract <url> --content-type html",
        "freeact stealth-extract <url> --proxy socks5://host:port",
        "```",
        "",
        "## Environment",
        "",
        "CLI:",
        f"  version: v{__version__}",
        f"  default_browser: {config.default_browser}",
        f"  headless: {'yes' if config.headless else 'no'}",
        f"  proxy: {config.proxy or 'none'}",
        "",
        "Available real browsers:",
    ]

    from freeact.browser import BROWSER_MAP
    for key, info in BROWSER_MAP.items():
        found = False
        for p in info["paths"]:
            if Path(p).exists():
                found = True
                break
        status = "installed" if found else "not found"
        lines.append(f"  {info['name']}: {status}")

    lines += [
        "",
        "Configured browsers:",
    ]

    if config.browsers:
        for bid, bc in config.browsers.items():
            lines.append(
                f"  {bid}: name={bc.name}, type={bc.type}, desc={bc.desc}"
            )
    else:
        lines.append("  none")

    lines += [
        "",
        "Active sessions:",
    ]
    from freeact.session import get_session_manager

    sm = get_session_manager()
    sessions = sm.list_sessions()
    if sessions:
        for s in sessions:
            lines.append(f"  {s.name}: browser={s.browser_id}")
    else:
        lines.append("  none")

    lines += [
        "",
        "Directives:",
    ]
    if not config.browsers:
        lines.append(
            "No browsers configured. To create one: freeact browser create --type chromium --name <name> --desc <desc>"
        )

    return "\n".join(lines)


def get_skills_advanced() -> str:
    lines = [
        "# Advanced Features",
        "",
        "## Browser types",
        "",
        "- `chromium` — Chromium browser (fast, reliable, default)",
        "- `firefox` — Firefox browser (better privacy)",
        "- `webkit` — WebKit/Safari browser",
        "",
        "## Confirmation Gate",
        "",
        "Operations requiring explicit user confirmation:",
        "- Browser creation (`browser create`)",
        "- Browser deletion (`browser delete`)",
        "- Profile import (`browser import-profile`)",
        "- Proxy changes (`browser update --proxy`)",
        "",
        "## Proxy support",
        "",
        "```bash",
        "# Custom proxy (SOCKS5/HTTP)",
        "freeact browser create --type chromium --name s1 --desc \"...\" --proxy socks5://user:pass@host:port",
        "freeact browser update <id> --proxy socks5://host:port",
        "freeact browser update <id> --no-proxy",
        "",
        "# Proxy list",
        "freeact proxy list",
        "```",
        "",
        "## Stealth mode",
        "",
        "Built-in anti-detection patches (enabled by default):",
        "- navigator.webdriver hidden",
        "- Chrome runtime faked",
        "- Canvas/WebGL fingerprint randomization",
        "- Plugin array spoofed",
        "- Permission override",
        "",
        "Disable: set `stealth: false` in ~/.freeact/config.json or use --no-stealth flag",
        "",
        "## Profile management",
        "",
        "```bash",
        "# Import cookies from JSON file",
        "freeact cookies import ./cookies.json",
        "",
        "# Export cookies",
        "freeact --session <name> cookies export ./cookies.json",
        "",
        "# Clear cookies",
        "freeact --session <name> cookies clear",
        "```",
        "",
        "## Remote assist (VNC)",
        "",
        "When automation gets stuck, the user can take over:",
        "```bash",
        "freeact --session <name> remote-assist --objective \"Complete CAPTCHA\"",
        "```",
        "Opens browser in headed mode and returns control to the user.",
    ]

    return "\n".join(lines)
