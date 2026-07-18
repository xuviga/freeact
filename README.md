# FreeAct — Free Browser Agent CLI

**Browser automation for AI agents that cannot be detected as automation.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Version](https://img.shields.io/badge/version-0.3.1-orange.svg)]()

FreeAct controls **your real browser** — the one you use every day. No new profiles, no re-logins, no lost passwords. Anti-bot systems see a normal user, because it IS your normal browser.

## Quick Start (30 seconds)

```bash
# 1. Install
pip install freeact
playwright install chromium

# 2. That's it! A shortcut "Yandex (FreeAct)" appears on your desktop.
#    Use it for daily browsing — freeact connects anytime.

# 3. Connect to your browser
freeact connect
# → Connected! 5 tabs — your profile, passwords, everything intact

# 4. Interact with any page
freeact --session live state               # 96 indexed elements
freeact --session live input 12 "iPhone"   # Type in search
freeact --session live keys Enter          # Press Enter
freeact --session live wait stable         # Wait for results
freeact --session live get markdown        # Extract content

# 5. Extract any URL (no browser needed)
freeact stealth-extract https://example.com

# 6. Solve CAPTCHAs (free, multi-strategy)
freeact --session live solve-captcha
```

## How It Works

```
You open Yandex (FreeAct) shortcut → normal browsing, all your logins work
                                          ↓
                            Browser runs with CDP on port 9222
                                          ↓
              freeact connect → attaches to YOUR browser
                                          ↓
              AI agent controls YOUR tabs, YOUR logins, YOUR pages
```

**No copying, no restarting, no re-logging in.** The browser you use every day.

## Features

### Live Browser Mode — Control Your Real Browser
```bash
freeact connect                     # Connect to your running browser
freeact tabs                        # List all open tabs
freeact tab switch 0                # Switch to a tab
freeact tab new https://site.com    # Open new tab
freeact tab close 2                 # Close tab

# All commands work on current tab (session: live)
freeact --session live state        # Indexed elements
freeact --session live click 6      # Click by index
freeact --session live input 2 "text"
freeact --session live get markdown
```

### CAPTCHA Solver — Free & Multi-Strategy
```bash
freeact --session live solve-captcha
```
Audio → speech-to-text. OCR → image recognition. Behavioral → mouse simulation.
reCAPTCHA v2, hCaptcha, Cloudflare Turnstile. All free.

### Daemon Mode — Persistent Browser
```bash
freeact daemon start     # HTTP server on 127.0.0.1:9341
freeact daemon stop      # Commands are instant when daemon runs
```

### Standalone Browser — For Anti-Bot Sites
```bash
freeact browser create --name wb --desc "Wildberries"
freeact --session wb browser open <id> https://www.wildberries.ru
```
Launches browser via subprocess. Zero automation flags. Undetectable.

### Remote Assist & Skill Forge
```bash
freeact --session live remote-assist --objective "Log in"
freeact forge --name scraper --url https://site.com
```

## All Commands

| Group | Commands |
|-------|----------|
| **Setup** | `setup` — create desktop shortcut (auto-runs on first launch) |
| **Live Browser** | `connect`, `tabs`, `tab switch/close/new` |
| **Daemon** | `daemon start/stop/status` |
| **Browser** | `browser create/open/list/update/delete/types` |
| **Navigation** | `navigate`, `back`, `forward`, `reload` |
| **Interaction** | `click`, `input`, `hover`, `select`, `keys`, `scroll`, `scrollintoview`, `upload` |
| **Extraction** | `get title/text/html/markdown/value`, `eval`, `screenshot` |
| **Network** | `network requests/request/clear` |
| **CAPTCHA** | `solve-captcha` |
| **Remote** | `remote-assist` |
| **Skill** | `forge` |
| **Session** | `session list/close` |
| **Other** | `stealth-extract`, `get-skills`, `proxy`, `wait` |

## Browser Support

| Type | Browser | TLS Fingerprint | Anti-Bot |
|------|---------|----------------|----------|
| `yandex` | Yandex Browser | Yandex native | Bypasses Wildberries, Ozon, Avito |
| `chrome` | Google Chrome | Chrome native | General use |
| `edge` | Microsoft Edge | Edge native | Enterprise |
| `chromium` | Playwright Chromium | Standard | Headless only |

## Project Structure

```
freeact/
├── freeact/
│   ├── cli.py           # Typer CLI — 40+ commands
│   ├── live.py          # Live browser (CDP — user's real browser)
│   ├── daemon.py        # HTTP server for persistent browser
│   ├── browser.py       # Real browser launch + CDP
│   ├── captcha.py       # Multi-strategy CAPTCHA solver
│   ├── session.py       # Session persistence
│   ├── state.py         # Indexed element tree [N]
│   ├── interaction.py   # click, input, hover, scroll, upload
│   ├── extraction.py    # get markdown/text/html, screenshot, eval
│   ├── network.py       # XHR/fetch interception
│   ├── stealth.py       # Anti-detection patches
│   ├── proxy.py         # SOCKS5/HTTP proxy
│   ├── remote.py        # Remote assist
│   ├── skillforge.py    # Skill generator
│   ├── skills.py        # get-skills for AI agents
│   └── config.py        # ~/.freeact/ configuration
├── SKILL.md             # OpenCode/Claude Code skill
└── pyproject.toml       # Package config
```

## Installation

```bash
pip install freeact
playwright install chromium
```

A **«Yandex (FreeAct)»** shortcut appears on your desktop automatically.
Use it for daily browsing. FreeAct connects anytime.

### Optional Dependencies

```bash
pip install SpeechRecognition   # Audio CAPTCHA
pip install pytesseract          # Image CAPTCHA (also needs Tesseract installed)
```

### For AI Agents (OpenCode, Claude Code, Cursor)

> Install freeact skill from https://github.com/xuviga/freeact

Or manually: `cp SKILL.md ~/.config/opencode/skills/freeact/SKILL.md`

## How It Beats Anti-Bot

| Protection | FreeAct |
|---|---|
| IP reputation | Same IP as user's normal browsing |
| WebDriver detection | No `--enable-automation` flag |
| Canvas/WebGL fingerprint | Real browser GPU + stealth patches |
| reCAPTCHA | Free audio/OCR solver |
| Turnstile (Cloudflare) | Human-like behavioral simulation |
| Profile/cookie check | Real profile — user's actual cookies |
| Session/auth check | Already logged in everywhere |

## Changelog

### v0.3.1 — Auto-Setup
- Desktop shortcut auto-created on first run
- `connect` never kills or restarts browser
- Original profile used directly — no copy, no data loss

### v0.3.0 — Live Browser Mode
- `connect`, `tabs`, `tab switch/close/new`
- `--session live` for real browser control

### v0.2.0 — Daemon, CAPTCHA, Remote, Forge
- Daemon mode, CAPTCHA solver (4 strategies), Remote assist, Skill Forge

### v0.1.0 — Initial Release
- Real browser mode, indexed interaction, network capture, stealth extraction

## License

MIT — no API keys, no paid tiers, no cloud.
