"""Tests for proxy configuration."""

from freeact.proxy import parse_proxy_config, validate_proxy_url


def test_parse_socks5():
    result = parse_proxy_config("socks5://127.0.0.1:9050")
    assert result is not None
    assert result["server"] == "127.0.0.1:9050"


def test_parse_with_auth():
    result = parse_proxy_config("http://user:pass@proxy.com:8080")
    assert result is not None
    assert result["server"] == "proxy.com:8080"
    assert result["username"] == "user"
    assert result["password"] == "pass"


def test_parse_none():
    assert parse_proxy_config("") is None
    assert parse_proxy_config(None) is None


def test_validate_valid():
    assert validate_proxy_url("socks5://127.0.0.1:9050") is True


def test_validate_invalid_scheme():
    assert validate_proxy_url("ftp://127.0.0.1:21") is False


def test_validate_no_port():
    assert validate_proxy_url("http://proxy.com") is False
