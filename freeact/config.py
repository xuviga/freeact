"""Configuration management for FreeAct."""

import os
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict


FREACT_HOME = Path(os.environ.get("FREACT_HOME", Path.home() / ".freeact"))
FREACT_HOME.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = FREACT_HOME / "config.json"
PROFILES_DIR = FREACT_HOME / "profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = FREACT_HOME / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

_CONFIG_CACHE: "FreeactConfig | None" = None
_CONFIG_CACHE_TIME: float = 0.0
_CONFIG_CACHE_TTL: float = 5.0


@dataclass
class BrowserConfig:
    id: str
    name: str
    type: str = "yandex"
    desc: str = ""
    proxy: str | None = None
    private: bool = False
    confirm_before_use: bool = False
    profile_path: str | None = None


@dataclass
class FreeactConfig:
    browsers: dict[str, BrowserConfig] = field(default_factory=dict)
    default_browser: str = "yandex"
    headless: bool = False
    timeout: int = 30000
    proxy: str | None = None
    stealth: bool = True
    api_key: str | None = None
    max_network_entries: int = 500

    def save(self):
        global _CONFIG_CACHE, _CONFIG_CACHE_TIME
        data = {
            "browsers": {k: asdict(v) for k, v in self.browsers.items()},
            "default_browser": self.default_browser,
            "headless": self.headless,
            "timeout": self.timeout,
            "proxy": self.proxy,
            "stealth": self.stealth,
            "api_key": self.api_key,
            "max_network_entries": self.max_network_entries,
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2))
        _CONFIG_CACHE = None

    @classmethod
    def load(cls) -> "FreeactConfig":
        global _CONFIG_CACHE, _CONFIG_CACHE_TIME
        now = time.time()
        if _CONFIG_CACHE is not None and (now - _CONFIG_CACHE_TIME) < _CONFIG_CACHE_TTL:
            return _CONFIG_CACHE
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            browsers = {}
            for k, v in data.pop("browsers", {}).items():
                browsers[k] = BrowserConfig(**v)
            _CONFIG_CACHE = cls(browsers=browsers, **data)
        else:
            _CONFIG_CACHE = cls()
        _CONFIG_CACHE_TIME = now
        return _CONFIG_CACHE


def get_config() -> FreeactConfig:
    return FreeactConfig.load()


def invalidate_config_cache():
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
