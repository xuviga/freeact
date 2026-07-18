# FreeAct — Free Browser Agent CLI

**Browser automation for AI agents that cannot be detected as automation.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)]()
[![Version](https://img.shields.io/badge/version-0.3.0-orange.svg)]()

FreeAct is a free, open-source CLI that gives AI agents (Claude Code, OpenCode, Cursor, Codex) the ability to control **real installed browsers** — Chrome, Yandex, Edge — without any automation flags that anti-bot systems can detect.

> **Why this matters**: Playwright/Puppeteer/Selenium add `--enable-automation` flags that sites like Wildberries, Cloudflare, and reCAPTCHA instantly detect. FreeAct launches browsers via subprocess — zero automation signals. The browser has no idea it's being automated.

## How It Works

```
freeact daemon (HTTP server) → manages browser lifecycle
         ↓                              ↓
   subprocess.Popen(browser.exe)   NO automation flags
         ↓                              ↓
   CDP connect_over_cdp()          Anti-bot: "real user"
         ↓
   AI agent controls browser via HTTP API
```

## Quick Start

```bash
# 1. Install
pip install freeact
playwright install chromium

# 2. Start daemon (persistent browser — faster commands)
freeact daemon start

# 3. Create browser + open site (Yandex default, undetectable)
freeact --session wb browser create --name wb --desc "Wildberries"
freeact --session wb browser open <id> https://www.wildberries.ru
freeact --session wb state                    # [1]<button> Login, [2]<input>...
freeact --session wb input 12 "iPhone 15"     # Type by index
freeact --session wb keys Enter
freeact --session wb wait stable
freeact --session wb get markdown

# 4. Solve CAPTCHAs (free, multi-strategy)
freeact --session wb solve-captcha

# 5. Generate reusable scraping skills
freeact forge --name my-scraper --url https://site.com

# 6. When done
freeact daemon stop
```

## Features

### Live Browser Mode (v0.3.0) — Control Your Real Browser
Connect to your already-running browser. All tabs, logins, cookies preserved.
You see everything the agent does in real-time.

```bash
freeact connect                     # Auto-detect and connect to your browser
freeact tabs                        # List all open tabs
# [0] Wildberries: iPhone 15
# [1] Dzen: news
# [2] YouTube: music

freeact tab switch 0                # Switch to Wildberries tab
freeact tab new https://ozon.ru     # Open a new tab
freeact tab close 2                 # Close a tab

# Interact with any page in your real browser
freeact --session live state        # 96 indexed elements from YOUR browser
freeact --session live click 6      # Click "Login"
freeact --session live input 2 "text"
freeact --session live get markdown
freeact --session live solve-captcha
```

### Daemon Mode (v0.2.0)
Background HTTP server on `127.0.0.1:9341` keeps the browser alive between commands. Commands are instant — no per-command startup delay, JS state preserved.

```bash
freeact daemon start     # Start background server
freeact daemon status    # Check if running
freeact daemon stop      # Stop daemon
```

### CAPTCHA Solver (v0.2.0) — Free & Unique
Multi-strategy approach, tries in order:
1. **Audio CAPTCHA** + speech-to-text (Google Speech API or Whisper)
2. **Image CAPTCHA** + OCR (Tesseract or EasyOCR)
3. **reCAPTCHA v2** — checkbox click with human-like bezier mouse movement
4. **hCaptcha / Cloudflare Turnstile** — behavioral simulation + timing delays
5. **Custom image CAPTCHAs** — finds captcha images and input fields automatically

```bash
freeact --session wb solve-captcha
# → "CAPTCHA solved! Method: audio (text: 284719)"
```

### Remote Assist (v0.2.0)
When automation gets stuck, hand control to a human:
```bash
freeact --session wb remote-assist --objective "Log in to complete the purchase"
```

### Skill Forge (v0.2.0)
Generate reusable scraping skills from a single command:
```bash
freeact forge --name wb-scraper --url https://www.wildberries.ru --desc "WB product search"
# Output: output/wb-scraper/skill.py + SKILL.md + requirements.txt
```

### Undetectable Browser Mode
- Launches **real installed browsers** (Chrome, Yandex, Edge) via subprocess
- **No `--enable-automation` flag** — browser doesn't know it's automated
- Copies user's real profile (cookies, localStorage, history)
- Anti-bot JS challenges (Turnstile, reCAPTCHA) run normally and pass

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

## All Commands

| Group | Commands |
|-------|----------|
| **Daemon** | `start`, `stop`, `status` |
| **Live Browser** | `connect`, `tabs`, `tab switch/close/new` |
| **Browser** | `create`, `open`, `list`, `update`, `delete`, `types` |
| **Navigation** | `navigate`, `back`, `forward`, `reload` |
| **Interaction** | `click`, `input`, `hover`, `select`, `keys`, `scroll`, `scrollintoview`, `upload` |
| **Extraction** | `get title/text/html/markdown/value`, `eval`, `screenshot` |
| **Network** | `network requests/request/clear` |
| **CAPTCHA** | `solve-captcha` |
| **Remote** | `remote-assist` |
| **Skill** | `forge` |
| **Session** | `session list/close` |
| **Other** | `stealth-extract`, `get-skills`, `proxy`, `wait` |

## Installation

### Prerequisites
- Python 3.12+
- Yandex Browser, Chrome, or Edge
- Playwright (for `chromium` type and `stealth-extract`)

```bash
pip install freeact
playwright install chromium
```

### Optional Dependencies

```bash
# Audio CAPTCHA solving
pip install SpeechRecognition

# OR local Whisper (no internet needed):
pip install openai-whisper

# Image CAPTCHA solving
pip install pytesseract
# OR
pip install easyocr
```

### For AI Agents (OpenCode, Claude Code, Cursor)

Tell your agent:
> Install freeact skill from https://github.com/xuviga/freeact

Or manually:
```bash
cp SKILL.md ~/.config/opencode/skills/freeact/SKILL.md
```

## Project Structure

```
freeact/
├── freeact/
│   ├── cli.py           # Typer CLI — 35+ commands with daemon routing
│   ├── live.py          # Live browser connection (CDP — user's real browser)
│   ├── daemon.py         # HTTP server (127.0.0.1:9341) for persistent browser
│   ├── browser.py       # Real browser launch + CDP connection
│   ├── captcha.py       # Multi-strategy CAPTCHA solver (audio/OCR/behavioral)
│   ├── session.py       # Session persistence
│   ├── state.py         # Indexed element tree [N]
│   ├── interaction.py   # click, input, hover, scroll, upload
│   ├── extraction.py    # get markdown/text/html, screenshot, eval
│   ├── network.py       # XHR/fetch interception
│   ├── stealth.py       # Anti-detection patches (canvas, WebGL, webdriver)
│   ├── proxy.py         # SOCKS5/HTTP proxy
│   ├── remote.py        # Remote assist (headed takeover)
│   ├── skillforge.py    # Skill generator (skill.py + SKILL.md)
│   ├── skills.py        # get-skills system for AI agents
│   └── config.py        # ~/.freeact/ configuration
├── SKILL.md             # OpenCode/Claude Code agent skill
├── pyproject.toml       # Package build config
└── README.md            # This file
```

## How It Beats Anti-Bot Protection

| Protection | FreeAct Approach |
|---|---|
| **IP reputation** | Uses real browser (Yandex TLS fingerprint) + profile copy |
| **WebDriver detection** | No `--enable-automation` flag, `navigator.webdriver` hidden |
| **Canvas/WebGL fingerprint** | Stealth patches randomize canvas output |
| **JS Challenges (reCAPTCHA)** | Free audio/OCR/behavioral solver |
| **Turnstile (Cloudflare)** | Human-like mouse + timing simulation |
| **hCaptcha** | Checkbox click + behavioral analysis bypass |
| **Profile/cookie check** | Real profile copy with existing cookies |

## Changelog

### v0.3.0 — Live Browser Mode
- `connect` — one command to connect to user's running browser (auto-detect Chrome/Yandex/Edge)
- `tabs` — list all open tabs with titles and URLs
- `tab switch <N>` — activate a specific tab
- `tab new <url>` — open a new tab
- `tab close <N>` — close a tab
- `--session live` — all commands (state, click, input, get) work on the live browser's active tab
- Browser stays untouched — all logins, cookies, tabs preserved

### v0.2.0 — Daemon, CAPTCHA, Remote, Forge
- Daemon mode: HTTP server on 127.0.0.1:9341 for persistent browser
- CAPTCHA solver: 4 strategies (audio, OCR, reCAPTCHA, Turnstile/hCaptcha)
- Remote assist: headed takeover for manual intervention
- Skill Forge: generates reusable skill.py + SKILL.md packages
- Daemon-aware CLI routing: commands auto-detect daemon vs fallback

### v0.1.0 — Initial Release
- Real browser mode (Chrome, Yandex, Edge) via subprocess
- Index-based interaction (state, click, input)
- Network capture (XHR/fetch)
- Stealth extraction
- Session management
- AI agent SKILL.md

## License

MIT — do whatever you want. No API keys, no paid tiers, no cloud dependency.

## Author

FreeAct Team
