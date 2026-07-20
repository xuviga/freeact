"""Data extraction — get markdown, HTML, text, title, and screenshots.

Stability fix: turndown.js is loaded from local bundle (no CDN dependency).
Uses state engine to locate elements by index.
"""

import io
from pathlib import Path
from playwright.async_api import Page
from PIL import Image

from freeact.state import get_element_selector

_TURNDOWN_JS = (Path(__file__).parent / "turndown.js").read_text(encoding="utf-8")

_TURNDOWN_LOADER = f"""
() => {{
    if (window.__freeact_turndown) return true;
    try {{
        {_TURNDOWN_JS}
        window.__freeact_turndown = TurndownService;
        return true;
    }} catch(e) {{
        return false;
    }}
}}
"""


async def get_title(page: Page) -> str:
    return await page.title()


async def get_html(page: Page, selector: str | None = None) -> str:
    if selector:
        el = page.locator(selector)
        if await el.count() > 0:
            return await el.first.inner_html()
        return ""
    return await page.content()


async def get_markdown(page: Page) -> str:
    try:
        await page.evaluate(_TURNDOWN_LOADER)
        result = await page.evaluate(
            """
            () => {
                if (!window.__freeact_turndown) return null;
                const ts = new window.__freeact_turndown({
                    headingStyle: 'atx',
                    codeBlockStyle: 'fenced',
                });
                ts.remove(['script', 'style', 'noscript', 'svg', 'meta', 'link']);
                return ts.turndown(document.documentElement.outerHTML);
            }
        """
        )
        if result is not None:
            return result
    except Exception:
        pass

    try:
        from markdownify import markdownify as md
        html_content = await page.content()
        return md(html_content, heading_style="ATX")
    except Exception:
        return await page.content()


async def get_element_text(page: Page, index: int) -> str:
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        text = await page.locator(selector).first.text_content()
        return text.strip() if text else ""
    except Exception as e:
        return f"Error: {e}"


async def get_element_value(page: Page, index: int) -> str:
    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        return await page.locator(selector).first.input_value()
    except Exception:
        try:
            return await page.locator(selector).first.get_attribute("value") or ""
        except Exception as e:
            return f"Error: {e}"


async def take_screenshot(page: Page, path: str | None = None, full_page: bool = False) -> str:
    try:
        if path:
            await page.screenshot(path=path, full_page=full_page)
            return f"Screenshot saved to {path}"
        else:
            data = await page.screenshot(full_page=full_page)
            img = Image.open(io.BytesIO(data))
            return f"Screenshot captured: {img.size[0]}x{img.size[1]}px"
    except Exception as e:
        return f"Error taking screenshot: {e}"


async def evaluate_js(page: Page, js: str) -> str:
    try:
        result = await page.evaluate(js)
        if result is None:
            return "undefined"
        if isinstance(result, (dict, list)):
            import json
            return json.dumps(result, indent=2, ensure_ascii=False, default=str)
        return str(result)
    except Exception as e:
        return f"Error evaluating JS: {e}"
