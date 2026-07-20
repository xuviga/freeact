"""Interaction commands — robust click, input, hover, scroll, upload, keys.

Stability improvements:
- Retry logic with exponential backoff (up to 3 attempts)
- Multiple fallback strategies for clicks (Playwright → dispatchEvent → JS click)
- React/Vue-aware input: focus → clear → type → dispatch change events
- Force-click when element is covered by overlay
- Pre-action scroll-into-view on every retry
- Post-action DOM stability wait
"""

import asyncio
from playwright.async_api import Page

from freeact.state import (
    get_element_selector, get_selector_and_scroll, scroll_into_view, wait_for_dom_stable,
)

MAX_RETRIES = 3
BASE_DELAY = 0.3


async def _retry_with_backoff(fn, max_retries: int = MAX_RETRIES):
    last_error = None
    for attempt in range(max_retries):
        try:
            result = await fn()
            if result is not None:
                return result
        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                await asyncio.sleep(BASE_DELAY * (2 ** attempt))
    if last_error:
        raise last_error
    return None


async def click_element(page: Page, index: int, wait: bool = True) -> str:
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            await asyncio.sleep(BASE_DELAY * (2 ** attempt))

        selector = await get_selector_and_scroll(page, index)
        if not selector:
            if attempt == 0:
                await page.evaluate("() => { if (window.__freeact_state) window.__freeact_state.buildState(); }")
                await asyncio.sleep(0.2)
                selector = await get_element_selector(page, index)
            if not selector:
                continue

        try:
            await page.click(selector, timeout=5000)
            if wait:
                await wait_for_dom_stable(page, timeout_ms=5000)
            return f"Clicked element [{index}]"
        except Exception as e:
            err_str = str(e).lower()

            if "covered" in err_str or "intercept" in err_str or "visible" in err_str:
                try:
                    await page.click(selector, force=True, timeout=3000)
                    if wait:
                        await wait_for_dom_stable(page, timeout_ms=5000)
                    return f"Clicked element [{index}] (force)"
                except Exception:
                    pass
            elif "stable" in err_str or "timeout" in err_str:
                try:
                    await page.click(selector, force=True, timeout=3000)
                    if wait:
                        await wait_for_dom_stable(page, timeout_ms=5000)
                    return f"Clicked element [{index}] (force)"
                except Exception:
                    pass

            if attempt == MAX_RETRIES - 1:
                try:
                    await page.dispatch_event(selector, "click", timeout=3000)
                    if wait:
                        await wait_for_dom_stable(page, timeout_ms=5000)
                    return f"Clicked element [{index}] (dispatch)"
                except Exception:
                    pass

            if attempt == MAX_RETRIES - 1:
                try:
                    js_selector = selector.replace("[data-freeact-id='", "").replace("']", "")
                    await page.evaluate(f"""
                        () => {{
                            const el = document.querySelector('[data-freeact-id="{js_selector}"]');
                            if (el) {{
                                el.focus();
                                el.click();
                            }}
                        }}
                    """)
                    if wait:
                        await wait_for_dom_stable(page, timeout_ms=5000)
                    return f"Clicked element [{index}] (js)"
                except Exception:
                    pass

    return f"Error clicking element [{index}] after {MAX_RETRIES} attempts"


async def input_text(page: Page, index: int, text: str, wait: bool = True) -> str:
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            await asyncio.sleep(BASE_DELAY * (2 ** attempt))

        selector = await get_selector_and_scroll(page, index)
        if not selector:
            if attempt == 0:
                await page.evaluate("() => { if (window.__freeact_state) window.__freeact_state.buildState(); }")
                await asyncio.sleep(0.2)
                selector = await get_element_selector(page, index)
            if not selector:
                continue

        try:
            locator = page.locator(selector).first
            await locator.click(timeout=3000)
            await asyncio.sleep(0.1)
            await locator.fill("")
            await asyncio.sleep(0.05)
            await locator.fill(text)
            if wait:
                await wait_for_dom_stable(page, timeout_ms=3000)
            return f"Typed '{text}' into element [{index}]"
        except Exception:
            pass

        try:
            locator = page.locator(selector).first
            await locator.click(timeout=3000)
            await asyncio.sleep(0.1)
            await page.keyboard.press("Control+a")
            await asyncio.sleep(0.05)
            await page.keyboard.type(text, delay=30)
            if wait:
                await wait_for_dom_stable(page, timeout_ms=3000)
            return f"Typed '{text}' into element [{index}] (keyboard)"
        except Exception:
            pass

        if attempt == MAX_RETRIES - 1:
            try:
                js_selector = selector.replace("[data-freeact-id='", "").replace("']", "")
                escaped_text = text.replace("\\", "\\\\").replace("'", "\\'").replace("\n", "\\n")
                await page.evaluate(f"""
                    () => {{
                        const el = document.querySelector('[data-freeact-id="{js_selector}"]');
                        if (el) {{
                            el.focus();
                            el.value = '';
                            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(
                                window.HTMLInputElement.prototype, 'value'
                            );
                            if (nativeInputValueSetter && nativeInputValueSetter.set) {{
                                nativeInputValueSetter.set.call(el, '{escaped_text}');
                            }} else {{
                                el.value = '{escaped_text}';
                            }}
                            el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                            el.dispatchEvent(new Event('change', {{ bubbles: true }}));
                        }}
                    }}
                """)
                if wait:
                    await wait_for_dom_stable(page, timeout_ms=3000)
                return f"Typed '{text}' into element [{index}] (js)"
            except Exception:
                pass

    return f"Error typing into element [{index}] after {MAX_RETRIES} attempts"


async def hover_element(page: Page, index: int) -> str:
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            await asyncio.sleep(BASE_DELAY * (2 ** attempt))

        selector = await get_selector_and_scroll(page, index)
        if not selector:
            if attempt == 0:
                await page.evaluate("() => { if (window.__freeact_state) window.__freeact_state.buildState(); }")
                await asyncio.sleep(0.2)
                selector = await get_element_selector(page, index)
            if not selector:
                continue

        try:
            await page.hover(selector, timeout=5000)
            return f"Hovered element [{index}]"
        except Exception:
            if attempt == MAX_RETRIES - 1:
                try:
                    await page.hover(selector, force=True, timeout=3000)
                    return f"Hovered element [{index}] (force)"
                except Exception:
                    pass

    return f"Error hovering element [{index}] after {MAX_RETRIES} attempts"


async def select_option(page: Page, index: int, option: str) -> str:
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            await asyncio.sleep(BASE_DELAY * (2 ** attempt))

        selector = await get_selector_and_scroll(page, index)
        if not selector:
            if attempt == 0:
                await page.evaluate("() => { if (window.__freeact_state) window.__freeact_state.buildState(); }")
                await asyncio.sleep(0.2)
                selector = await get_element_selector(page, index)
            if not selector:
                continue

        try:
            await page.select_option(selector, label=option, timeout=5000)
            return f"Selected '{option}' in element [{index}]"
        except Exception:
            try:
                await page.select_option(selector, value=option, timeout=5000)
                return f"Selected '{option}' in element [{index}]"
            except Exception:
                try:
                    await page.select_option(selector, index=int(option) if option.isdigit() else 0, timeout=5000)
                    return f"Selected '{option}' in element [{index}]"
                except Exception as e:
                    if attempt == MAX_RETRIES - 1:
                        return f"Error selecting in element [{index}]: {e}"

    return f"Error selecting in element [{index}] after {MAX_RETRIES} attempts"


async def send_keys(page: Page, keys: str) -> str:
    try:
        await page.keyboard.press(keys)
        return f"Sent keys '{keys}'"
    except Exception as e:
        return f"Error sending keys: {e}"


async def type_text(page: Page, text: str) -> str:
    try:
        await page.keyboard.type(text, delay=20)
        return f"Typed '{text}'"
    except Exception as e:
        return f"Error typing: {e}"


async def scroll_page(page: Page, direction: str, amount: int = 500) -> str:
    try:
        dy = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {dy})")
        await asyncio.sleep(0.2)
        return f"Scrolled {direction} by {amount}px"
    except Exception as e:
        return f"Error scrolling: {e}"


async def scroll_by_selector(page: Page, css_selector: str) -> str:
    try:
        await page.locator(css_selector).first.scroll_into_view_if_needed(timeout=5000)
        await asyncio.sleep(0.2)
        return f"Scrolled to selector '{css_selector}'"
    except Exception as e:
        return f"Error scrolling to selector: {e}"


async def upload_file(page: Page, index: int, file_path: str) -> str:
    for attempt in range(MAX_RETRIES):
        if attempt > 0:
            await asyncio.sleep(BASE_DELAY * (2 ** attempt))

        scrolled = await scroll_into_view(page, index)
        if not scrolled:
            continue

        selector = await get_element_selector(page, index)
        if not selector:
            continue

        try:
            await page.set_input_files(selector, file_path, timeout=5000)
            return f"Uploaded '{file_path}' to element [{index}]"
        except Exception as e:
            if attempt == MAX_RETRIES - 1:
                return f"Error uploading to element [{index}]: {e}"

    return f"Error uploading to element [{index}] after {MAX_RETRIES} attempts"
