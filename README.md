# 🕷️ freeact — The Browser Tamer

> *"Your browser doesn't know it's being automated. Neither does CloudFront."*

**freeact** is a CLI tool that controls REAL installed browsers (Yandex, Chrome, Edge) through their own debugging protocol. No automation flags. No `chromedriver`. No Selenium. The browser literally has no idea it's being puppeted — anti-bot systems see a perfectly normal browsing session.

```
                  ┌──────────┐
                  │   YOU    │
                  │ (AI/CLI) │
                  └────┬─────┘
                       │ HTTP :9341
                  ┌────▼─────┐
                  │  DAEMON  │ ← persistent spirit
                  └────┬─────┘
                       │ CDP (Chrome DevTools Protocol)
                  ┌────▼─────┐
                  │  YANDEX  │ ← real binary, real profile
                  │  BROWSER │   real cookies, real session
                  └──────────┘
```

## Why This Exists

| Traditional Automation | freeact |
|---|---|
| Headless Chromium with flags | Real Yandex binary, no `--automation` |
| Detected by CloudFlare/Wildberries | CloudFront says "Welcome" |
| Fake profile, no cookies | Your actual browser profile |
| CAPTCHA = dead end | Free solver: audio + OCR + behavioral |
| Selenium/Playwright wrapper | Direct CDP commands |

## 5-Second Start

```bash
pip install freeact
playwright install chromium

freeact daemon start
freeact --session demo browser open DSYandex https://example.com
freeact --session demo state
# → [1]<a href=...> Sign In
# → [2]<input placeholder=Email>
freeact --session demo click 1
freeact --session demo wait stable
freeact --session demo get markdown
freeact session close demo
```

## The Sacred Law

```
state → interact → wait stable → state
```

Never touch without observing. The DOM mutates after every interaction. Indices are reborn each time you call `state`.

## Features

- **Daemon mode** — browser stays alive between commands. No startup delay.
- **15-layer stealth** — webdriver deletion, canvas noise, WebGL spoofing, plugin faking
- **Free CAPTCHA solver** — audio + OCR + reCAPTCHA + hCaptcha + Turnstile
- **Network capture** — all fetch/XHR logged automatically, zero overhead
- **Live browser** — connect to your daily browser with all real cookies
- **Turndown bundling** — markdown conversion without CDN dependency
- **Cross-platform** — Windows, macOS, Linux (paths + shortcuts)
- **Hardlink profiles** — share inodes, copy only mutable data
- **API key auth** — daemon guards commands with X-API-Key

## Documentation

```bash
open docs/field-guide.html    # The Browser Tamer's Field Guide
```

Or read [SKILL.md](SKILL.md) for the full command reference.

## Project State

```
Ruff:   0 errors
Tests:  14/14 pass
Modules: 19
```

## Pro Tips

- **Yandex + headed = CloudFront bypass.** This is not optional.
- **Always `state` before `click`/`input`.** Indices are ephemeral.
- **Use `wait stable` after interactions that change the DOM.**
- **Use `wait navigation` after clicks that change the URL.**
- **Close sessions when done** — they auto-expire after 8 hours anyway.
- **Turndown.js is local** — no CDN needed for `get markdown`.
- **Network log limit** is configurable via `max_network_entries` in config.

---

<p align="center"><em>19 creatures. 14 tests. 0 errors. Made with 🕷️ in the deep woods.</em></p>
