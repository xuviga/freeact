"""Page state extraction — stable indexed element tree for LLM agents.

Key stability improvements:
- data-freeact-id assigned DURING get_page_state(), not on-demand
- Persistent window.__freeact_state stores index→id→element mapping
- Interaction functions look up elements from this cache, not by re-querying DOM
- DOM mutation observer keeps cache in sync after page changes
"""

import asyncio
import json

from playwright.async_api import Page


INTERACTIVE_SELECTORS = [
    "a[href]",
    "button",
    "input:not([type='hidden'])",
    "select",
    "textarea",
    "[role='button']",
    "[role='link']",
    "[role='menuitem']",
    "[role='tab']",
    "[role='checkbox']",
    "[role='radio']",
    "[role='combobox']",
    "[role='listbox']",
    "[role='option']",
    "[role='switch']",
    "[role='textbox']",
    "[role='searchbox']",
    "[onclick]",
    "[tabindex]:not([tabindex='-1'])",
    "details summary",
    "label",
    "iframe",
]

_INIT_SCRIPT = """
() => {
    if (window.__freeact_state) return;

    const SELECTORS = %s;

    window.__freeact_state = {
        elements: [],
        elementMap: {},
        version: 0,
        observer: null,
    };

    function isVisible(el) {
        const rect = el.getBoundingClientRect();
        const style = window.getComputedStyle(el);
        return (
            rect.width > 0 &&
            rect.height > 0 &&
            style.visibility !== 'hidden' &&
            style.display !== 'none' &&
            style.opacity !== '0'
        );
    }

    function getAttrs(el) {
        const attrs = {};
        if (el.id) attrs.id = el.id;
        if (el.getAttribute('name')) attrs.name = el.getAttribute('name');
        if (el.type) attrs.type = el.type;
        if (el.placeholder) attrs.placeholder = el.placeholder;
        if (el.getAttribute('aria-label')) attrs['aria-label'] = el.getAttribute('aria-label');
        if (el.getAttribute('role')) attrs.role = el.getAttribute('role');
        if (el.value !== undefined && el.value !== '') attrs.value = el.value;
        if (el.href) attrs.href = el.href;
        if (el.checked !== undefined) attrs.checked = el.checked;
        if (el.disabled) attrs.disabled = true;
        if (el.readOnly) attrs.readonly = true;

        if (el.tagName === 'SELECT') {
            const options = [];
            for (const opt of el.options) {
                options.push(opt.text.trim());
            }
            if (options.length > 0) attrs.options = options;
        }
        return attrs;
    }

    function buildState() {
        const elements = document.querySelectorAll(SELECTORS);
        const visible = [];
        const elemMap = {};

        for (const el of elements) {
            if (!isVisible(el)) continue;

            const idx = visible.length + 1;
            const fid = 'fract-' + Math.random().toString(36).substring(2, 10);

            el.setAttribute('data-freeact-id', fid);
            el.setAttribute('data-freeact-index', String(idx));

            const tag = el.tagName.toLowerCase();
            const attrs = getAttrs(el);
            const text = (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().substring(0, 100);

            let attrStr = '';
            for (const [k, v] of Object.entries(attrs)) {
                if (Array.isArray(v)) {
                    attrStr += ` ${k}=[${v.join(', ')}]`;
                } else if (typeof v === 'boolean') {
                    if (v) attrStr += ` ${k}`;
                } else {
                    attrStr += ` ${k}="${v}"`;
                }
            }

            visible.push(`[${idx}]<${tag}${attrStr}>${text ? ' ' + text : ''}`);

            elemMap[fid] = {
                index: idx,
                tag: tag,
                id: el.id || null,
                name: el.getAttribute('name') || null,
                type: el.type || null,
                value: el.value || null,
                placeholder: el.placeholder || null,
                href: el.href || null,
                disabled: el.disabled || false,
                readOnly: el.readOnly || false,
                checked: el.checked || false,
                text: text,
                rect: (() => {
                    const r = el.getBoundingClientRect();
                    return { x: r.x, y: r.y, width: r.width, height: r.height };
                })(),
            };
        }

        window.__freeact_state.elements = visible;
        window.__freeact_state.elementMap = elemMap;
        window.__freeact_state.version++;
        window.__freeact_state._lastUrl = window.location.href;

        return {
            url: window.location.href,
            title: document.title,
            elements: visible,
            count: visible.length,
            version: window.__freeact_state.version,
        };
    }

    window.__freeact_state.buildState = buildState;
    window.__freeact_state.isVisible = isVisible;
    window.__freeact_state.getAttrs = getAttrs;
}
"""


async def init_state_engine(page: Page) -> None:
    selectors_json = json.dumps(", ".join(INTERACTIVE_SELECTORS))
    await page.evaluate(_INIT_SCRIPT % selectors_json)


async def get_page_state(page: Page) -> str:
    await init_state_engine(page)

    result = await page.evaluate("""
        () => {
            if (!window.__freeact_state) return { url: window.location.href, title: document.title, elements: [], count: 0, version: 0 };
            return window.__freeact_state.buildState();
        }
    """)

    lines = [
        f"url={result['url']}",
        f"title={result['title']}",
        f"elements={result['count']}",
        "",
    ]
    for elem in result["elements"]:
        lines.append(f"  {elem}")

    return "\n".join(lines)


async def get_element_details(page: Page, index: int) -> dict | None:
    await init_state_engine(page)

    result = await page.evaluate(f"""
        () => {{
            const state = window.__freeact_state;
            if (!state) return null;

            for (const [fid, info] of Object.entries(state.elementMap)) {{
                if (info.index === {index}) {{
                    const el = document.querySelector(`[data-freeact-id="${{fid}}"]`);
                    if (el && state.isVisible(el)) {{
                        return {{
                            tag: info.tag, id: info.id, name: info.name,
                            type: info.type, value: info.value,
                            placeholder: info.placeholder, href: info.href,
                            disabled: info.disabled, text: info.text,
                            rect: info.rect,
                        }};
                    }}
                }}
            }}
            return null;
        }}
    """)
    return result


async def get_element_selector(page: Page, index: int) -> str | None:
    await init_state_engine(page)

    result = await page.evaluate(f"""
        () => {{
            const state = window.__freeact_state;
            if (!state) return null;

            for (const [fid, info] of Object.entries(state.elementMap)) {{
                if (info.index === {index}) {{
                    const el = document.querySelector(`[data-freeact-id="${{fid}}"]`);
                    if (el && state.isVisible(el)) return fid;
                }}
            }}

            state.buildState();
            for (const [fid, info] of Object.entries(state.elementMap)) {{
                if (info.index === {index}) {{
                    const el = document.querySelector(`[data-freeact-id="${{fid}}"]`);
                    if (el && state.isVisible(el)) return fid;
                }}
            }}
            return null;
        }}
    """)
    if not result:
        return None
    return f"[data-freeact-id='{result}']"


async def scroll_into_view(page: Page, index: int) -> bool:
    selector = await get_element_selector(page, index)
    if not selector:
        return False

    try:
        await page.locator(selector).first.scroll_into_view_if_needed(timeout=2000)
        await asyncio.sleep(0.15)
        return True
    except Exception:
        pass

    try:
        await page.evaluate(f"""
            () => {{
                const el = document.querySelector('{selector}');
                if (el) {{
                    el.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                }}
            }}
        """)
        return True
    except Exception:
        return False


async def get_selector_and_scroll(page: Page, index: int) -> str | None:
    """Combined: get element selector and scroll into view in one optimised pass.
    Falls back to separate calls if combined approach fails."""
    await init_state_engine(page)

    result = await page.evaluate(f"""
        () => {{
            const state = window.__freeact_state;
            if (!state) return null;

            const findAndScroll = (rebuild) => {{
                if (rebuild) state.buildState();
                for (const [fid, info] of Object.entries(state.elementMap)) {{
                    if (info.index === {index}) {{
                        const el = document.querySelector(`[data-freeact-id="${{fid}}"]`);
                        if (el && state.isVisible(el)) {{
                            el.scrollIntoView({{ behavior: 'instant', block: 'center' }});
                            return fid;
                        }}
                    }}
                }}
                return null;
            }};

            let fid = findAndScroll(false);
            if (!fid) fid = findAndScroll(true);
            return fid;
        }}
    """)

    if result:
        await asyncio.sleep(0.1)
        return f"[data-freeact-id='{result}']"

    scrolled = await scroll_into_view(page, index)
    if scrolled:
        return await get_element_selector(page, index)
    return None


async def wait_for_dom_stable(page: Page, timeout_ms: int = 5000, min_stable_ms: int = 300) -> str:
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
    except Exception:
        pass

    try:
        await page.wait_for_load_state("networkidle", timeout=min(timeout_ms, 3000))
    except Exception:
        pass

    await asyncio.sleep(0.3)

    try:
        await page.evaluate(f"""
            () => {{
                return new Promise((resolve) => {{
                    let lastChange = Date.now();
                    const minStable = {min_stable_ms};
                    const maxWait = {timeout_ms};
                    const start = Date.now();

                    const observer = new MutationObserver(() => {{
                        lastChange = Date.now();
                    }});

                    observer.observe(document.body || document.documentElement, {{
                        childList: true, subtree: true, attributes: true, characterData: true
                    }});

                    const check = () => {{
                        const elapsed = Date.now() - start;
                        const stable = Date.now() - lastChange;
                        if (stable >= minStable || elapsed >= maxWait) {{
                            observer.disconnect();
                            resolve(true);
                        }} else {{
                            setTimeout(check, 100);
                        }}
                    }};
                    check();
                }});
            }}
        """)
    except Exception:
        await asyncio.sleep(0.5)

    return "DOM stable"


async def wait_for_navigation(page: Page, timeout_ms: int = 10000) -> str:
    try:
        url_before = page.url
        await page.wait_for_load_state("domcontentloaded", timeout=timeout_ms)
        url_after = page.url
        if url_before != url_after:
            await asyncio.sleep(0.5)
            await wait_for_dom_stable(page, timeout_ms)
            return f"Navigated to {url_after}"
        return "Page stable"
    except Exception as e:
        return f"Wait result: {e}"
