# freeact — The Browser Tamer

> **To the AI Agent reading this:** You are about to command a real browser. Not a simulated one. Not a headless shell. A living, breathing Yandex Browser with real cookies, real sessions, and an invisibility shroud that fools even CloudFront. Treat it with respect. Follow the Laws. The creature will serve you well.

## The Sacred Cycle

```
state → interact → wait stable → state
```

**Never skip observation.** After every touch, the DOM mutates. Indices shift. What was [5] may become [7] or vanish entirely. Always `state` before `click`/`input`.

## Quick Binding

```bash
freeact daemon start                                          # Summon the spirit (once)
freeact --session <name> browser open <id> <url>              # Bind creature
freeact --session <name> state                                # Observe form
freeact --session <name> click <N>                            # Touch appendage
freeact --session <name> input <N> "text"                     # Feed text
freeact --session <name> wait stable                          # Let it settle
freeact --session <name> state                                # Observe again
freeact session close <name>                                  # Release creature
```

## All Commands

### Daemon
```bash
freeact daemon start      # Launch persistent spirit on :9341
freeact daemon stop       # Dismiss the spirit
freeact daemon status     # Check if spirit lives
```

### Browser Management
```bash
freeact --session <s> browser open <id> <url>                 # Bind + navigate
freeact --session <s> browser open <id> <url> --headed        # Show window
freeact --session <s> browser open <id> <url> --refresh-profile  # Fresh nest
freeact browser create --type yandex --name "My" --desc "..." # Register new mount
freeact browser create --type yandex --name "X" --proxy socks5://h:p
freeact browser list                                           # List all mounts
freeact browser update <id> --name "New"
freeact browser delete <id>
freeact browser types                                          # Installed browsers
freeact --session <s> browser connect <port> <url>            # Attach to CDP
```

### Navigation
```bash
freeact --session <s> navigate <url>
freeact --session <s> back
freeact --session <s> forward
freeact --session <s> reload
```

### Creature Observation (State)
```bash
freeact --session <s> state              # Indexed element tree
freeact --session <s> screenshot         # Visual capture
freeact --session <s> screenshot --full ./page.png
freeact --session <s> eval "js_code"     # Mind-probe
```

### Creature Whispering (Interaction)
```bash
freeact --session <s> click <N>          # Poke appendage
freeact --session <s> input <N> "text"   # Feed text (React-compatible)
freeact --session <s> hover <N>          # Hover over
freeact --session <s> select <N> "Opt"   # Choose from dropdown
freeact --session <s> keys "Enter"       # Press key
freeact --session <s> scroll down        # Scroll page
freeact --session <s> scroll up --amount 1000
freeact --session <s> scrollintoview --selector ".modal button"
freeact --session <s> upload <N> ./file.pdf
```

### Essence Harvesting (Extraction)
```bash
freeact --session <s> get title
freeact --session <s> get html
freeact --session <s> get html --selector "#content"
freeact --session <s> get markdown
freeact --session <s> get text <N>        # Visible text of element
freeact --session <s> get value <N>       # Input current value
```

### Network Interception
```bash
freeact --session <s> network requests
freeact --session <s> network requests --filter api.example.com
freeact --session <s> network requests --type xhr,fetch --method POST
freeact --session <s> network requests --status 4xx
freeact --session <s> network request <N>    # Full detail
freeact --session <s> network clear
```

### Waiting
```bash
freeact --session <s> wait stable              # DOM no mutations for 300ms
freeact --session <s> wait stable --timeout 60000
freeact --session <s> wait navigation           # URL changed
```

### CAPTCHA Breaking
```bash
freeact --session <s> solve-captcha    # 4 strategies, no API keys
```

### Remote Assist
```bash
freeact --session <s> remote-assist --objective "Log in manually"
```

### Stealth Extraction (No Session)
```bash
freeact stealth-extract <url>
freeact stealth-extract <url> --content-type html -o page.html
freeact stealth-extract <url> --proxy socks5://host:port --timeout 60
```

### Live Browser (Your Real Browser)
```bash
freeact setup --browser yandex      # Create CDP shortcut (Windows/Mac/Linux)
freeact connect                     # Attach to running browser
freeact tabs                        # List open tabs
freeact tab switch 2
freeact tab close 1
freeact tab new https://site.com
```

### Session
```bash
freeact session list
freeact session close <name>
```

### Utility
```bash
freeact proxy list
freeact get-skills core
freeact get-skills advanced
freeact forge --name scraper --url https://site.com
```

## Automation Patterns

### Pattern A: Simple Extraction
```bash
freeact daemon start
freeact --session s1 browser open DSYandex https://example.com
freeact --session s1 wait stable
freeact --session s1 get markdown > page.md
freeact session close s1
```

### Pattern B: Form Fill
```bash
freeact --session auth browser open DSYandex https://example.com/login
freeact --session auth state                    # Note indices
freeact --session auth input 2 "user@mail.com"
freeact --session auth input 3 "password"
freeact --session auth click 1                  # Submit
freeact --session auth wait navigation
freeact --session auth get markdown
```

### Pattern C: Search → Extract → Paginate
```bash
freeact --session search browser open DSYandex https://example.com
freeact --session search state
freeact --session search input 5 "keyword"
freeact --session search keys "Enter"
freeact --session search wait stable
freeact --session search state
freeact --session search get markdown
# Find "Next page" index from state, click it
freeact --session search scrollintoview --selector ".pagination .next"
freeact --session search state
freeact --session search click 42
freeact --session search wait stable
```

### Pattern D: API Interception
```bash
freeact --session api browser open DSYandex https://example.com/search
freeact --session api state
freeact --session api input 3 "query"
freeact --session api click 1
freeact --session api wait stable
freeact --session api network requests --type xhr,fetch
freeact --session api network request 0
```

## The Ten Laws

1. **Yandex only.** Chrome/Edge mounts retired.
2. **Headed always.** Invisible creatures die at CloudFront gates.
3. **Observe before touch.** `state` before every `click`/`input`.
4. **Sacred cycle.** state → interact → wait → state.
5. **Session required.** Every command needs `--session`.
6. **Handler purity.** All logic in `_handlers.py`. No duplication.
7. **Hardlink nests.** Share inodes, copy only mutable flesh.
8. **Zero errors.** Ruff clean. 14 tests green.
9. **Local turndown.** Bundled in package, no CDN dependency.
10. **Log everything.** `~/.freeact/freeact.log` records all.

## Element Types Detected by `state`

| Selector | Example |
|----------|---------|
| `a[href]` | Links |
| `button` | Buttons |
| `input:not([type='hidden'])` | Text, email, password, checkbox, radio, file |
| `select` | Dropdowns |
| `textarea` | Multi-line input |
| `[role='button']`, `[role='link']`, `[role='menuitem']` | ARIA |
| `[role='tab']`, `[role='checkbox']`, `[role='radio']` | ARIA widgets |
| `[role='combobox']`, `[role='listbox']`, `[role='option']` | ARIA lists |
| `[role='switch']`, `[role='textbox']`, `[role='searchbox']` | ARIA inputs |
| `[onclick]` | Click handlers |
| `[tabindex]:not([tabindex='-1'])` | Focusable |
| `details summary` | Expandable |
| `label` | Form labels |
| `iframe` | Frames |

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `FREACT_HOME` | `~/.freeact` | Config, sessions, profiles, CDP ports, logs |

## Dependencies

```
pip install freeact
playwright install chromium
```

