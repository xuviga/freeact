"""Network monitoring — capture XHR/fetch requests, HAR recording."""

import json
import io
from pathlib import Path
from typing import Optional
from playwright.async_api import Page


async def start_network_monitoring(page: Page):
    await page.route(
        "**/*",
        lambda route: route.continue_(),
    )
    await page.evaluate(
        """
        () => {
            if (!window.__freeact_network_log) {
                window.__freeact_network_log = [];
                const origFetch = window.fetch;
                window.fetch = async function(...args) {
                    const start = Date.now();
                    const request = {
                        id: 'fetch-' + Math.random().toString(36).substring(2, 10),
                        url: typeof args[0] === 'string' ? args[0] : args[0].url,
                        method: (args[1] && args[1].method) || 'GET',
                        type: 'fetch',
                        headers: args[1] && args[1].headers ? args[1].headers : {},
                        start: start,
                    };
                    if (args[1] && args[1].body) request.body = args[1].body;

                    try {
                        const response = await origFetch.apply(this, args);
                        const cloned = response.clone();
                        request.status = response.status;
                        request.statusText = response.statusText;
                        request.end = Date.now();
                        request.duration = request.end - start;

                        try {
                            const ct = response.headers.get('content-type') || '';
                            if (ct.includes('json')) {
                                request.responseBody = await cloned.json();
                            } else if (ct.includes('text') || ct.includes('xml') || ct.includes('html')) {
                                const text = await cloned.text();
                                request.responseBody = text.substring(0, 10000);
                            }
                        } catch(e) {}

                        window.__freeact_network_log.push(request);
                        return response;
                    } catch(err) {
                        request.error = err.message;
                        request.status = 0;
                        request.end = Date.now();
                        window.__freeact_network_log.push(request);
                        throw err;
                    }
                };

                const origXHROpen = XMLHttpRequest.prototype.open;
                const origXHRSend = XMLHttpRequest.prototype.send;

                XMLHttpRequest.prototype.open = function(method, url) {
                    this.__fract_req = {
                        id: 'xhr-' + Math.random().toString(36).substring(2, 10),
                        url: url.toString(),
                        method: method,
                        type: 'xhr',
                        start: Date.now(),
                    };
                    return origXHROpen.apply(this, arguments);
                };

                XMLHttpRequest.prototype.send = function(body) {
                    if (this.__fract_req) {
                        this.__fract_req.body = body;
                    }
                    this.addEventListener('load', function() {
                        if (this.__fract_req) {
                            this.__fract_req.status = this.status;
                            this.__fract_req.statusText = this.statusText;
                            this.__fract_req.end = Date.now();
                            this.__fract_req.duration = this.__fract_req.end - this.__fract_req.start;
                            const ct = this.getResponseHeader('content-type') || '';
                            try {
                                if (ct.includes('json')) {
                                    this.__fract_req.responseBody = JSON.parse(this.responseText);
                                } else {
                                    this.__fract_req.responseBody = this.responseText.substring(0, 10000);
                                }
                            } catch(e) {
                                this.__fract_req.responseBody = this.responseText.substring(0, 10000);
                            }
                            window.__freeact_network_log.push(this.__fract_req);
                        }
                    });
                    this.addEventListener('error', function() {
                        if (this.__fract_req) {
                            this.__fract_req.error = 'Network error';
                            this.__fract_req.status = 0;
                            window.__freeact_network_log.push(this.__fract_req);
                        }
                    });
                    return origXHRSend.apply(this, arguments);
                };
            }
        }
    """
    )


async def get_network_requests(
    page: Page,
    url_filter: str | None = None,
    types: str | None = None,
    method: str | None = None,
    status: str | None = None,
    clear: bool = False,
) -> str:
    result = await page.evaluate(
        f"""
        () => {{
            if (!window.__freeact_network_log) return [];
            let requests = window.__freeact_network_log;

            const filter = {json.dumps(url_filter)};
            const typeFilter = {json.dumps(types)};
            const methodFilter = {json.dumps(method)};
            const statusFilter = {json.dumps(status)};
            const shouldClear = {json.dumps(clear)};

            if (filter) {{
                requests = requests.filter(r => r.url.includes(filter));
            }}
            if (typeFilter) {{
                const types = typeFilter.split(',').map(t => t.trim());
                requests = requests.filter(r => types.includes(r.type));
            }}
            if (methodFilter) {{
                requests = requests.filter(r => r.method === methodFilter.toUpperCase());
            }}
            if (statusFilter) {{
                const s = statusFilter;
                if (s === '2xx') requests = requests.filter(r => r.status >= 200 && r.status < 300);
                else if (s === '3xx') requests = requests.filter(r => r.status >= 300 && r.status < 400);
                else if (s === '4xx') requests = requests.filter(r => r.status >= 400 && r.status < 500);
                else if (s === '5xx') requests = requests.filter(r => r.status >= 500 && r.status < 600);
                else requests = requests.filter(r => r.status === parseInt(s));
            }}

            if (shouldClear) {{
                window.__freeact_network_log = [];
            }}

            return requests.map(r => ({{
                id: r.id,
                url: r.url,
                method: r.method,
                type: r.type,
                status: r.status,
                duration: r.duration,
                error: r.error,
            }}));
        }}
    """
    )

    if not result:
        return "No requests captured"

    lines = [f"Requests ({len(result)}):", ""]
    for i, req in enumerate(result):
        status_str = str(req.get("status", "?"))
        duration_str = f"{req.get('duration', 0)}ms" if req.get("duration") else ""
        error_str = f" ERROR: {req['error']}" if req.get("error") else ""
        lines.append(
            f"  [{i}] {req['method']} {status_str} {req['url'][:120]}{error_str}"
        )
        lines.append(f"       id={req['id']}  type={req['type']}  {duration_str}")

    return "\n".join(lines)


async def get_network_request_detail(page: Page, request_index: int) -> str:
    result = await page.evaluate(
        f"""
        () => {{
            if (!window.__freeact_network_log) return null;
            const idx = {request_index};
            if (idx < 0 || idx >= window.__freeact_network_log.length) return null;
            const req = window.__freeact_network_log[idx];
            return {{
                id: req.id,
                url: req.url,
                method: req.method,
                type: req.type,
                status: req.status,
                statusText: req.statusText,
                headers: req.headers,
                body: req.body,
                responseBody: req.responseBody,
                duration: req.duration,
                error: req.error,
            }};
        }}
    """
    )

    if not result:
        return "Request not found"

    import json

    lines = [
        f"Request [{result['id']}]:",
        f"  URL: {result['url']}",
        f"  Method: {result['method']}",
        f"  Type: {result['type']}",
        f"  Status: {result['status']} {result.get('statusText', '')}",
        f"  Duration: {result.get('duration', '?')}ms",
    ]

    if result.get("error"):
        lines.append(f"  Error: {result['error']}")

    if result.get("headers"):
        lines.append("  Headers:")
        for k, v in result["headers"].items():
            lines.append(f"    {k}: {v}")

    if result.get("body"):
        body_str = result["body"]
        if isinstance(body_str, str) and len(body_str) > 500:
            body_str = body_str[:500] + "..."
        lines.append(f"  Request Body: {body_str}")

    if result.get("responseBody"):
        resp = result["responseBody"]
        if isinstance(resp, (dict, list)):
            resp = json.dumps(resp, indent=2, ensure_ascii=False)
        if isinstance(resp, str) and len(resp) > 2000:
            resp = resp[:2000] + "..."
        lines.append(f"  Response Body: {resp}")

    return "\n".join(lines)


async def clear_network_requests(page: Page):
    await page.evaluate("() => { window.__freeact_network_log = []; }")


async def set_offline(page: Page, offline: bool):
    if offline:
        await page.route("**/*", lambda route: route.abort())
    else:
        await page.unroute("**/*")
