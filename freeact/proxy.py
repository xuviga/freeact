"""Proxy configuration support."""

from typing import Optional
from urllib.parse import urlparse


def parse_proxy_config(proxy_url: str) -> Optional[dict]:
    if not proxy_url:
        return None
    parsed = urlparse(proxy_url)
    server = f"{parsed.hostname}:{parsed.port}"
    proxy = {"server": server}
    if parsed.username:
        proxy["username"] = parsed.username
    if parsed.password:
        proxy["password"] = parsed.password
    return proxy


def validate_proxy_url(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https", "socks5"):
        return False
    if not parsed.hostname or not parsed.port:
        return False
    return True
