"""Configuration management for FreeAct."""

import os
import json
from pathlib import Path
from dataclasses import dataclass, field, asdict


FREACT_HOME = Path(os.environ.get("FREACT_HOME", Path.home() / ".freeact"))
FREACT_HOME.mkdir(parents=True, exist_ok=True)

CONFIG_FILE = FREACT_HOME / "config.json"
PROFILES_DIR = FREACT_HOME / "profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR = FREACT_HOME / "sessions"
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class BrowserConfig:
    id: str
    name: str
    type: str = "chromium"
    desc: str = ""
    proxy: str | None = None
    private: bool = False
    confirm_before_use: bool = False
    profile_path: str | None = None


@dataclass
class FreeactConfig:
    browsers: dict[str, BrowserConfig] = field(default_factory=dict)
    default_browser: str = "yandex"
    headless: bool = True
    timeout: int = 30000
    proxy: str | None = None
    stealth: bool = True
    api_key: str | None = None

    def save(self):
        data = {
            "browsers": {k: asdict(v) for k, v in self.browsers.items()},
            "default_browser": self.default_browser,
            "headless": self.headless,
            "timeout": self.timeout,
            "proxy": self.proxy,
            "stealth": self.stealth,
            "api_key": self.api_key,
        }
        CONFIG_FILE.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls) -> "FreeactConfig":
        if CONFIG_FILE.exists():
            data = json.loads(CONFIG_FILE.read_text())
            browsers = {}
            for k, v in data.pop("browsers", {}).items():
                browsers[k] = BrowserConfig(**v)
            return cls(browsers=browsers, **data)
        return cls()


def get_config() -> FreeactConfig:
    return FreeactConfig.load()
