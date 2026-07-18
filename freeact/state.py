"""Page state extraction — indexed element tree for LLM agents."""

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
    "[onclick]",
    "[tabindex]:not([tabindex='-1'])",
    "details summary",
    "label",
    "iframe",
]


async def get_page_state(page: Page) -> str:
    selector_union = ", ".join(INTERACTIVE_SELECTORS)

    result = await page.evaluate(
        f"""
        () => {{
            const elements = document.querySelectorAll({json.dumps(selector_union)});
            const visible = [];
            let index = 0;

            for (const el of elements) {{
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                const isVisible = (
                    rect.width > 0 &&
                    rect.height > 0 &&
                    style.visibility !== 'hidden' &&
                    style.display !== 'none' &&
                    style.opacity !== '0'
                );
                if (!isVisible) continue;

                index++;
                const tag = el.tagName.toLowerCase();
                const attrs = {{}};

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

                if (el.tagName === 'SELECT') {{
                    const options = [];
                    for (const opt of el.options) {{
                        options.push(opt.text.trim());
                    }}
                    if (options.length > 0) attrs.options = options;
                }}

                const text = (el.textContent || el.value || el.placeholder || el.getAttribute('aria-label') || '').trim().substring(0, 100);

                let attrStr = '';
                for (const [k, v] of Object.entries(attrs)) {{
                    if (Array.isArray(v)) {{
                        attrStr += ` ${{k}}=[${{v.join(', ')}}]`;
                    }} else if (typeof v === 'boolean') {{
                        if (v) attrStr += ` ${{k}}`;
                    }} else {{
                        attrStr += ` ${{k}}="${{v}}"`;
                    }}
                }}

                visible.push(`[${{index}}]<${{tag}}${{attrStr}}>${{text ? ' ' + text : ''}}`);
            }}

            return {{
                url: window.location.href,
                title: document.title,
                elements: visible,
                count: visible.length,
            }};
        }}
    """
    )

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
    selector_union = ", ".join(INTERACTIVE_SELECTORS)

    result = await page.evaluate(
        f"""
        () => {{
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
            const idx = {index} - 1;
            if (idx < 0 || idx >= visible.length) return null;

            const el = visible[idx];
            return {{
                tag: el.tagName.toLowerCase(),
                id: el.id || null,
                name: el.getAttribute('name') || null,
                type: el.type || null,
                value: el.value || null,
                placeholder: el.placeholder || null,
                href: el.href || null,
                disabled: el.disabled || false,
                text: (el.textContent || '').trim().substring(0, 200),
                rect: {{ x: el.getBoundingClientRect().x, y: el.getBoundingClientRect().y, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height }},
            }};
        }}
    """
    )
    return result


async def scroll_into_view(page: Page, index: int) -> bool:
    selector_union = ", ".join(INTERACTIVE_SELECTORS)
    result = await page.evaluate(
        f"""
        () => {{
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
            const idx = {index} - 1;
            if (idx < 0 || idx >= visible.length) return false;
            visible[idx].scrollIntoView({{ behavior: 'instant', block: 'center' }});
            return true;
        }}
    """
    )
    return result
