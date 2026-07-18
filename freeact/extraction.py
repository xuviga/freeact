"""Data extraction — get markdown, HTML, text, title, and screenshots."""

import base64
import io
from playwright.async_api import Page
from PIL import Image


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
        result = await page.evaluate(
            """
            async () => {
                const html = document.documentElement.outerHTML;
                if (typeof turndownService === 'undefined') {
                    const TurndownService = await import('https://unpkg.com/turndown@7/dist/turndown.js');
                    window.TurndownService = TurndownService.default || TurndownService;
                }
                const ts = new window.TurndownService({
                    headingStyle: 'atx',
                    codeBlockStyle: 'fenced',
                });
                ts.remove(['script', 'style', 'noscript', 'svg', 'meta', 'link']);
                return ts.turndown(html);
            }
        """
        )
        return result
    except Exception:
        from markdownify import markdownify as md

        html_content = await page.content()
        return md(html_content, heading_style="ATX")


async def get_element_text(page: Page, index: int) -> str:
    from freeact.interaction import get_element_selector

    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        text = await page.locator(selector).first.text_content()
        return text.strip() if text else ""
    except Exception as e:
        return f"Error: {e}"


async def get_element_value(page: Page, index: int) -> str:
    from freeact.interaction import get_element_selector

    selector = await get_element_selector(page, index)
    if not selector:
        return f"Error: element at index {index} not found"
    try:
        return await page.locator(selector).first.input_value()
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

            return json.dumps(result, indent=2, ensure_ascii=False)
        return str(result)
    except Exception as e:
        return f"Error evaluating JS: {e}"
