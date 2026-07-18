# FreeAct — Free Browser Agent CLI

**Browser automation for AI agents that cannot be detected as automation.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()

FreeAct is a free, open-source CLI that gives AI agents (Claude Code, OpenCode, Cursor, Codex) the ability to control **real installed browsers** — Chrome, Yandex, Edge — without any automation flags that anti-bot systems can detect.

> **Why this matters**: Playwright/Puppeteer/Selenium add `--enable-automation` flags that sites like Wildberries, Cloudflare, and reCAPTCHA instantly detect. FreeAct launches browsers via subprocess — zero automation signals. The browser has no idea it's being automated.

## How It Works

```
freeact CLI → subprocess.Popen(browser.exe) → browser starts as NORMAL
                    ↓                                      ↓
           NO automation flags                    Identical to user launch
                    ↓                                      ↓
        CDP connect_over_cdp()                  Anti-bot: "looks like a real user"
                    ↓
              AI agent controls browser
```

## Quick Start

```bash
# 1. Install
pip install freeact
playwright install chromium

# 2. Extract any webpage (stealth mode)
freeact stealth-extract https://example.com

# 3. Full browser automation (Yandex default, undetectable)
freeact browser create --name wb --desc "Wildberries shopping"
freeact --session wb browser open <id> https://www.wildberries.ru
freeact --session wb state                    # [1]<button> Login, [2]<input> Search...
freeact --session wb input 2 "iPhone 15"      # Type by index
freeact --session wb keys Enter               # Press Enter
freeact --session wb wait stable              # Wait for results
freeact --session wb get markdown             # Extract page content
freeact --session wb screenshot
freeact session close wb
```

## Features

### Undetectable Browser Mode
- Launches **real installed browsers** (Chrome, Yandex, Edge) via subprocess
- **No `--enable-automation` flag** — browser doesn't know it's automated
- Copies user's real profile (cookies, localStorage, history)
- Anti-bot JS challenges (Turnstile, reCAPTCHA, Wildberries) run normally and pass

### Index-Based Interaction
- `state` returns elements indexed as `[1]`, `[2]`, `[3]`... — no DOM parsing
- `click 3`, `input 2 "text"`, `hover 5` — operate by index
- Designed for LLM reasoning, not human scripts

### Three Browser Options

| Type | Browser | Best For |
|------|---------|----------|
| `yandex` | Yandex Browser | Russian sites (Wildberries, Ozon, Avito) |
| `chrome` | Google Chrome | General use, Google services |
| `edge` | Microsoft Edge | Enterprise, Microsoft 365 |
| `chromium` | Playwright Chromium | Fast headless, disposable |

### Network Capture
```bash
freeact --session s1 network requests --type xhr,fetch
freeact --session s1 network request 0
```

### Session & Concurrency
- Multiple independent sessions on one browser (shared login state)
- Multiple browsers with isolated cookies/profiles
- Auto-cleanup after 8 hours

### Stealth Extraction
```bash
freeact stealth-extract https://example.com --content-type markdown
freeact stealth-extract https://example.com --proxy socks5://proxy:1080
```

## All Commands

| Group | Commands |
|-------|----------|
| **Browser** | `create`, `open`, `list`, `update`, `delete`, `types`, `connect` |
| **Navigation** | `navigate`, `back`, `forward`, `reload` |
| **Interaction** | `click`, `input`, `hover`, `select`, `keys`, `scroll`, `scrollintoview`, `upload` |
| **Extraction** | `get title/text/html/markdown/value`, `eval`, `screenshot` |
| **Network** | `network requests/request/clear` |
| **Session** | `session list/close` |
| **Other** | `stealth-extract`, `get-skills`, `proxy`, `wait` |

## Installation

### Prerequisites
- Python 3.12+
- At least one browser: Chrome, Yandex Browser, or Edge
- Playwright (for `chromium` type and `stealth-extract`)

```bash
pip install freeact
playwright install chromium
```

### For AI Agents (OpenCode, Claude Code, Cursor)

Tell your agent:
> Install freeact skill from https://github.com/user/freeact

Or manually:
```bash
cp SKILL.md ~/.config/opencode/skills/freeact/SKILL.md
```

## Compared to BrowserAct

| Feature | BrowserAct | FreeAct |
|---------|-----------|---------|
| Real browser mode | Chrome-direct (paid) | **Free, all browsers** |
| Stealth browsers | Paid (cloud) | Playwright Chromium (free) |
| Managed proxies | Paid | BYO proxy (free) |
| CAPTCHA solving | Paid | Not yet |
| Price | Free tier + paid | **100% free, MIT** |
| Open source | No | **Yes** |

## Project Structure

```
freeact/
├── freeact/
│   ├── cli.py           # Typer CLI — 30+ commands
│   ├── browser.py       # Real browser launch + CDP connection
│   ├── session.py       # Session persistence
│   ├── state.py         # Indexed element tree [N]
│   ├── interaction.py   # click, input, hover, scroll, upload
│   ├── extraction.py    # get markdown/text/html, screenshot, eval
│   ├── network.py       # XHR/fetch interception
│   ├── stealth.py       # Anti-detection patches (canvas, WebGL, webdriver)
│   ├── proxy.py         # SOCKS5/HTTP proxy
│   ├── skills.py        # get-skills system for AI agents
│   └── config.py        # ~/.freeact/ configuration
├── SKILL.md             # OpenCode/Claude Code agent skill
├── pyproject.toml       # Package build config
└── README.md            # This file
```

## How It Beats Anti-Bot Protection

```
YouTube, VK, Avito ─→ just works (most sites)
       │
Wildberries, Cloudflare ─→ use yandex/chrome type (real browser)

What anti-bot sees with FreeAct:
  ✓ Real browser TLS fingerprint (Yandex/Chrome native)
  ✓ Real user profile (cookies, localStorage, history)
  ✓ Normal GPU rendering (headed mode)
  ✓ No webdriver flag
  ✓ No CDP leak at launch time

What anti-bot sees with Playwright/Selenium:
  ✗ --enable-automation flag in command line
  ✗ navigator.webdriver = true
  ✗ Empty profile (no cookies, no history)
  ✗ CDP active from launch
```

## Config

`~/.freeact/config.json`:
```json
{
  "default_browser": "yandex",
  "headless": false,
  "timeout": 30000,
  "stealth": true
}
```

## Roadmap

- [x] Real browser mode (Chrome, Yandex, Edge)
- [x] Indexed interaction (state, click, input)
- [x] Network capture (XHR/fetch)
- [x] Stealth extraction
- [x] Session management
- [x] AI agent SKILL.md
- [ ] Persistent daemon mode (keep browser alive)
- [ ] CAPTCHA solving integration
- [ ] Remote assist (VNC)
- [ ] Skill Forge (scraping skill generator)

## License

MIT — do whatever you want. No API keys, no paid tiers, no cloud dependency.

## Author

FreeAct Team
