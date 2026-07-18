"""Interaction commands — click, input, hover, scroll, upload, keys."""

import asyncio
import json
from playwright.async_api import Page

from freeact.state import INTERACTIVE_SELECTORS, scroll_into_view


async def get_element_selector(page: Page, index: int) -> str | None:
    selector_union = ", ".join(INTERACTIVE_SELECTORS)
    result = await page.evaluate(
        f"""
        (index) => {{
            const elements = document.querySelectorAll({json.dumps(selector_union)});
            const visible = [];
            for (const el of elements) {{
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                if (rect.width > 0 && rect.height > 0 &&
                    style.visibility !== 'hidden' && style.display !== 'none') {{
                    visible.push(el);
                }}
            }}
            const idx = index - 1;
            if (idx < 0 || idx >= visible.length) return null;
            const el = visible[idx];
            if (!el.hasAttribute('data-freeact-id')) {{
                const fid = 'fract-' + Math.random().toString(36).substring(2, 10);
                el.setAttribute('data-freeact-id', fid);
            }}
            return el.getAttribute('data-freeact-id');
        }}
    """,
        index,
    )
    if not result:
        return None
    return f"[data-freeact-id='{result}']"


async def click_element(page: Page, index: int) -> str:
    await scroll_into_view(page, index)
    await asyncio.sleep(0.1)
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        await page.click(selector)
        return f"Clicked element [{index}]"
    except Exception as e:
        return f"Error clicking element [{index}]: {e}"


async def input_text(page: Page, index: int, text: str) -> str:
    await scroll_into_view(page, index)
    await asyncio.sleep(0.1)
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        await page.fill(selector, text)
        return f"Typed '{text}' into element [{index}]"
    except Exception as e:
        return f"Error typing into element [{index}]: {e}"


async def hover_element(page: Page, index: int) -> str:
    await scroll_into_view(page, index)
    await asyncio.sleep(0.1)
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        await page.hover(selector)
        return f"Hovered element [{index}]"
    except Exception as e:
        return f"Error hovering element [{index}]: {e}"


async def select_option(page: Page, index: int, option: str) -> str:
    await scroll_into_view(page, index)
    await asyncio.sleep(0.1)
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        await page.select_option(selector, label=option)
        return f"Selected '{option}' in element [{index}]"
    except Exception as e:
        return f"Error selecting in element [{index}]: {e}"


async def send_keys(page: Page, keys: str) -> str:
    try:
        await page.keyboard.press(keys)
        return f"Sent keys '{keys}'"
    except Exception as e:
        return f"Error sending keys: {e}"


async def type_text(page: Page, text: str) -> str:
    try:
        await page.keyboard.type(text)
        return f"Typed '{text}'"
    except Exception as e:
        return f"Error typing: {e}"


async def scroll_page(page: Page, direction: str, amount: int = 500) -> str:
    try:
        dy = amount if direction == "down" else -amount
        await page.evaluate(f"window.scrollBy(0, {dy})")
        return f"Scrolled {direction} by {amount}px"
    except Exception as e:
        return f"Error scrolling: {e}"


async def scroll_by_selector(page: Page, css_selector: str) -> str:
    try:
        await page.locator(css_selector).scroll_into_view_if_needed()
        return f"Scrolled to selector '{css_selector}'"
    except Exception as e:
        return f"Error scrolling to selector: {e}"


async def upload_file(page: Page, index: int, file_path: str) -> str:
    await scroll_into_view(page, index)
    await asyncio.sleep(0.1)
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: file input at index {index} not found"
    try:
        await page.set_input_files(selector, file_path)
        return f"Uploaded '{file_path}' to element [{index}]"
    except Exception as e:
        return f"Error uploading to element [{index}]: {e}"
