"""Shared command handlers — used by both daemon and CLI direct mode.

Every handler takes a Page and returns a result dict or string.
Daemon wraps these in HTTP responses. CLI direct wraps in console output.
"""


from playwright.async_api import Page

from freeact.extraction import (
    evaluate_js, get_element_text, get_element_value,
    get_html, get_markdown, get_title, take_screenshot,
)
from freeact.interaction import (
    click_element, hover_element, input_text, scroll_by_selector,
    scroll_page, select_option, send_keys, upload_file,
)
from freeact.network import (
    clear_network_requests, get_network_request_detail,
    get_network_requests,
)
from freeact.state import (
    get_page_state, wait_for_dom_stable, wait_for_navigation,
)


async def h_state(page: Page) -> str:
    return await get_page_state(page)


async def h_click(page: Page, index: int) -> str:
    return await click_element(page, index, wait=True)


async def h_input(page: Page, index: int, text: str) -> str:
    return await input_text(page, index, text, wait=True)


async def h_hover(page: Page, index: int) -> str:
    return await hover_element(page, index)


async def h_select(page: Page, index: int, option: str) -> str:
    return await select_option(page, index, option)


async def h_keys(page: Page, key: str) -> str:
    return await send_keys(page, key)


async def h_scroll(page: Page, direction: str, amount: int = 500) -> str:
    return await scroll_page(page, direction, amount)


async def h_scrollintoview(page: Page, selector: str) -> str:
    return await scroll_by_selector(page, selector)


async def h_upload(page: Page, index: int, file_path: str) -> str:
    return await upload_file(page, index, file_path)


async def h_navigate(page: Page, url: str) -> str:
    if "://" not in url:
        url = "https://" + url
    await page.goto(url, wait_until="domcontentloaded", timeout=30000)
    await wait_for_dom_stable(page, timeout_ms=5000)
    return f"Navigated to {url}"


async def h_back(page: Page) -> str:
    await page.go_back(wait_until="domcontentloaded", timeout=15000)
    await wait_for_dom_stable(page, timeout_ms=5000)
    return "Navigated back"


async def h_forward(page: Page) -> str:
    await page.go_forward(wait_until="domcontentloaded", timeout=15000)
    await wait_for_dom_stable(page, timeout_ms=5000)
    return "Navigated forward"


async def h_reload(page: Page) -> str:
    await page.reload(wait_until="domcontentloaded", timeout=15000)
    await wait_for_dom_stable(page, timeout_ms=5000)
    return "Page reloaded"


async def h_get(page: Page, what: str, arg: str | None = None, selector: str | None = None) -> str:
    match what:
        case "title":
            return await get_title(page)
        case "html":
            return await get_html(page, selector)
        case "markdown":
            return await get_markdown(page)
        case "text":
            if not arg:
                return "Error: index required for 'get text'"
            return await get_element_text(page, int(arg))
        case "value":
            if not arg:
                return "Error: index required for 'get value'"
            return await get_element_value(page, int(arg))
        case _:
            return f"Error: unknown get type '{what}'"


async def h_eval(page: Page, js: str) -> str:
    return await evaluate_js(page, js)


async def h_screenshot(page: Page, path: str | None = None, full: bool = False) -> str:
    return await take_screenshot(page, path, full)


async def h_wait(page: Page, what: str = "stable", timeout: int = 30000) -> str:
    if what == "stable":
        return await wait_for_dom_stable(page, timeout_ms=timeout)
    elif what == "navigation":
        return await wait_for_navigation(page, timeout_ms=timeout)
    return f"Unknown wait type: {what}"


async def h_network(page: Page, action: str, arg: str | None = None,
                    url_filter: str | None = None, types: str | None = None,
                    method: str | None = None, status: str | None = None,
                    clear: bool = False) -> str:
    match action:
        case "requests":
            return await get_network_requests(
                page, url_filter=url_filter, types=types,
                method=method, status=status, clear=clear,
            )
        case "request":
            if not arg:
                return "Error: request index required"
            return await get_network_request_detail(page, int(arg))
        case "clear":
            await clear_network_requests(page)
            return "Network log cleared"
        case _:
            return f"Unknown network action: {action}"
