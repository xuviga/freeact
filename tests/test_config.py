"""Tests for configuration management."""

from freeact.config import FreeactConfig, BrowserConfig, invalidate_config_cache


def test_default_config():
    invalidate_config_cache()
    config = FreeactConfig()
    assert config.default_browser == "yandex"
    assert config.headless is False
    assert config.stealth is True
    assert config.timeout == 30000
    assert config.api_key is None
    assert config.browsers == {}


def test_browser_config():
    bc = BrowserConfig(id="test", name="Test")
    assert bc.id == "test"
    assert bc.type == "chromium"


def test_config_save_load(tmp_path):
    invalidate_config_cache()
    config = FreeactConfig()
    config.browsers["b1"] = BrowserConfig(id="b1", name="B1", type="yandex")

    from freeact.config import CONFIG_FILE
    test_file = tmp_path / "config.json"
    original = str(CONFIG_FILE)
    import freeact.config as cfg_module
    cfg_module.CONFIG_FILE = test_file

    try:
        config.save()
        loaded = FreeactConfig.load()
        assert "b1" in loaded.browsers
        assert loaded.browsers["b1"].type == "yandex"
    finally:
        cfg_module.CONFIG_FILE = type(cfg_module.CONFIG_FILE)(original)
        invalidate_config_cache()
