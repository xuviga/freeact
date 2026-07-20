# freeact Promo Kit — Copy-paste ready posts

## Reddit r/Python
Title: freeact v0.4.0 — Control REAL browsers via CDP. Undetectable. Anti-bot bypass. Free CAPTCHA solver.

Body:
I built freeact — an open-source CLI that controls your actual installed browser (Yandex/Chrome/Edge) through the Chrome DevTools Protocol. Unlike Selenium/Playwright, there are ZERO automation flags — the browser has no idea it's being automated. Anti-bot systems (CloudFront, reCAPTCHA, Cloudflare) cannot detect it.

What makes it different:
• Uses your REAL browser profile with real cookies
• 15-layer stealth patch system (webdriver deletion, canvas noise, WebGL spoofing)
• Free multi-strategy CAPTCHA solver (audio, OCR, behavioral)
• Daemon mode — browser stays alive between commands, instant response
• Network monitoring — zero-overhead fetch/XHR interception
• Live browser connection — attach to your daily browser with all your logins
• Bundled turndown.js — no CDN dependency
• Cross-platform: Windows, macOS, Linux

pip install freeact-cli==0.4.0
GitHub: https://github.com/xuviga/freeact

I'd love feedback from the community!

## Hacker News (Show HN)
Title: Show HN: freeact — undetectable browser automation via real browsers (no automation flags)

Body:
Hi HN — I built a CLI tool that controls your actual installed browser (Yandex/Chrome/Edge) through CDP. The key difference from Playwright/Selenium: no automation flags. The browser literally doesn't know it's being puppeted.

This means anti-bot systems (CloudFront, reCAPTCHA, Cloudflare Turnstile) treat the browser as a normal user. I successfully bypassed CloudFront on chat.deepseek.com using a real Yandex profile with headed mode.

Features: free CAPTCHA solver, 15-layer stealth patches, persistent daemon mode, network interception, live browser connection, built-in markdown conversion.

https://github.com/xuviga/freeact

## Twitter/X
🚀 freeact v0.4.0 — undetectable browser automation for AI agents

Control REAL browsers via CDP. No automation flags. Anti-bot cant detect it.

• Real Yandex/Chrome/Edge profiles
• Free CAPTCHA solver
• CloudFront bypass
• Daemon mode
• 15 stealth layers

pip install freeact-cli
github.com/xuviga/freeact

## LinkedIn Article
Title: Introducing freeact — The Browser Tamer: Undetectable Browser Automation for the AI Age

The web is becoming increasingly hostile to automation. CloudFront, reCAPTCHA, Cloudflare Turnstile — these systems are designed to detect and block bots. Traditional tools like Selenium and Playwright leave detectable traces: webdriver flags, headless mode signatures, inconsistent browser fingerprints.

freeact takes a fundamentally different approach: instead of launching a fresh browser with automation flags, it connects to your REAL installed browser through the Chrome DevTools Protocol — the same protocol your browser uses for debugging. No automation flags. No detectability.

Built as a CLI tool for AI agents (OpenCode, Claude Code), freeact provides:

• Real browser control — uses actual Yandex, Chrome, or Edge installations
• 15-layer stealth system — from webdriver property deletion to canvas fingerprint randomization
• Free CAPTCHA solver — audio recognition, OCR, and behavioral simulation
• Persistent daemon — browser stays alive between commands
• Live connection — attach to your daily browser with all your cookies and logins

Open source (MIT), cross-platform, 14 tests, 0 ruff errors.
pip install freeact-cli==0.4.0

## Dev.to Article
# freeact: The Browser Tamer — A New Approach to Undetectable Web Automation

## The Problem
Every Selenium/Playwright script leaves detectable traces: `navigator.webdriver === true`, missing plugins, headless mode artifacts. Anti-bot systems catch them instantly.

## The Solution
freeact controls your REAL browser — the same Yandex/Chrome/Edge you use daily — through the Chrome DevTools Protocol. The browser doesn't know it's being automated.

## Why This Matters for AI Agents
AI coding agents need to interact with the web: testing, scraping, form filling, CAPTCHA solving. Traditional automation gets blocked. freeact doesn't.

## Quick Start
```bash
pip install freeact-cli==0.4.0
freeact daemon start
freeact --session demo browser open DSYandex https://example.com
freeact --session demo state
freeact --session demo click 1
```

## Under the Hood
15 stealth layers, real browser profiles, hardlink-based profile copying, local turndown.js, adaptive CDP connection, page cache for instant commands.

GitHub: https://github.com/xuviga/freeact
