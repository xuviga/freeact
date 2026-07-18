"""Browser management — real browser via CDP, zero automation flags."""

import asyncio
import json
import shutil
import socket
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from freeact.config import FREACT_HOME, BrowserConfig, FreeactConfig, get_config
from freeact.stealth import apply_stealth_patches
from freeact.proxy import parse_proxy_config

BROWSER_MAP = {
    "chrome": {
        "name": "Chrome",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
        ],
        "profile": Path.home() / r"AppData\Local\Google\Chrome\User Data",
        "exe": "chrome.exe",
    },
    "edge": {
        "name": "Edge",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ],
        "profile": Path.home() / r"AppData\Local\Microsoft\Edge\User Data",
        "exe": "msedge.exe",
    },
    "yandex": {
        "name": "Yandex",
        "paths": [
            r"C:\Program Files (x86)\Yandex\YandexBrowser\Application\browser.exe",
            Path.home() / r"AppData\Local\Yandex\YandexBrowser\Application\browser.exe",
        ],
        "profile": Path.home() / r"AppData\Local\Yandex\YandexBrowser\User Data",
        "exe": "browser.exe",
    },
}

CDP_DIR = FREACT_HOME / "cdp"
CDP_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR = FREACT_HOME / "copied_profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)


def find_browser(browser_type: str) -> dict | None:
    bt = browser_type.lower()
    for key, info in BROWSER_MAP.items():
        if bt == key or bt in info["name"].lower():
            for p in info["paths"]:
                if Path(p).exists():
                    return {**info, "found_path": str(p), "key": key}
    for info in BROWSER_MAP.values():
        for p in info["paths"]:
            if Path(p).exists():
                return {**info, "found_path": str(p), "key": "chrome"}
    return None


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _kill_browser(exe_name: str):
    try:
        subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, timeout=10)
    except Exception:
        pass


def _copy_profile(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    skip = {"Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache",
            "Service Worker", "blob_storage", "WebStorage", "Crashpad"}
    for item in src.iterdir():
        if item.name in skip or item.name == "Local State":
            continue
        dest = dst / item.name
        try:
            if item.is_dir():
                shutil.copytree(item, dest, ignore=lambda d, f: [x for x in f if x in skip])
            else:
                shutil.copy2(item, dest)
        except (PermissionError, OSError):
            pass
    ls = src / "Local State"
    if ls.exists():
        try:
            shutil.copy2(ls, dst / "Local State")
        except Exception:
            pass
    return dst


class BrowserManager:
    def __init__(self):
        self._playwright = None
        self._contexts: dict[str, BrowserContext] = {}
        self._browsers: dict[str, Browser] = {}
        self._proc: dict[str, subprocess.Popen] = {}

    async def start(self):
        if self._playwright is None:
            self._playwright = await async_playwright().start()
        return self._playwright

    async def stop(self):
        for proc in self._proc.values():
            try:
                proc.terminate()
            except Exception:
                pass
        self._proc.clear()
        for ctx in self._contexts.values():
            try:
                await ctx.close()
            except Exception:
                pass
        for br in self._browsers.values():
            try:
                await br.close()
            except Exception:
                pass
        self._contexts.clear()
        self._browsers.clear()
        if self._playwright:
            try:
                await self._playwright.stop()
            except Exception:
                pass
            self._playwright = None

    def _port_file(self, bid: str) -> Path:
        return CDP_DIR / f"{bid}.port"

    def _save_port(self, bid: str, port: int):
        self._port_file(bid).write_text(str(port))

    def _load_port(self, bid: str) -> int | None:
        f = self._port_file(bid)
        if f.exists():
            try:
                return int(f.read_text().strip())
            except (ValueError, OSError):
                pass
        return None

    async def _try_reconnect(self, bid: str) -> tuple[Browser, BrowserContext] | None:
        port = self._load_port(bid)
        if not port:
            return None
        try:
            await self.start()
            browser = await self._playwright.chromium.connect_over_cdp(f"http://127.0.0.1:{port}")
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            self._browsers[bid] = browser
            self._contexts[bid] = context
            return browser, context
        except Exception:
            return None

    async def _launch_new(self, bc: BrowserConfig, config: FreeactConfig) -> tuple[Browser, BrowserContext]:
        await self.start()

        info = find_browser(bc.type or "Chrome")
        if not info:
            raise RuntimeError(f"No browser found for type: {bc.type}")

        # Don't kill existing browser — we use a copied profile

        port = _free_port()
        self._save_port(bc.id, port)

        if bc.private:
            profile_dir = PROFILES_DIR / f"{bc.id}_tmp"
            profile_dir.mkdir(parents=True, exist_ok=True)
        else:
            profile_dir = info["profile"]

        args = [
            info["found_path"],
            f"--remote-debugging-port={port}",
            f"--user-data-dir={profile_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-extensions",
            "--disable-default-apps",
            "--disable-breakpad",
            "--disable-hang-monitor",
            "--no-pings",
            "--window-size=1920,1080",
            "--disable-features=TranslateUI,OptimizationHints,MediaRouter",
        ]

        if config.headless:
            args.append("--headless=new")

        if bc.proxy or config.proxy:
            pc = parse_proxy_config(bc.proxy or config.proxy)
            args.append(f"--proxy-server={pc['server']}")

        proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self._proc[bc.id] = proc

        cdp = f"http://127.0.0.1:{port}"
        for i in range(25):
            try:
                browser = await self._playwright.chromium.connect_over_cdp(cdp)
                break
            except Exception:
                if i == 24:
                    proc.kill()
                    raise RuntimeError("CDP connect failed")
                await asyncio.sleep(1.2)

        context = browser.contexts[0] if browser.contexts else await browser.new_context(
            viewport={"width": 1920, "height": 1080})

        if config.stealth:
            for p in context.pages:
                try:
                    await apply_stealth_patches(context)
                except Exception:
                    pass

        self._browsers[bc.id] = browser
        self._contexts[bc.id] = context
        return browser, context

    async def get_or_create_context(self, bc: BrowserConfig, config: FreeactConfig | None = None):
        if config is None:
            config = get_config()

        if bc.id in self._contexts:
            ctx = self._contexts[bc.id]
            try:
                ctx.pages
                return self._browsers.get(bc.id), ctx
            except Exception:
                del self._contexts[bc.id]

        bt = (bc.type or config.default_browser).lower()
        if bt in ("chromium", "playwright"):
            ctx = await self._playwright.chromium.launch_persistent_context(
                user_data_dir=str(PROFILES_DIR / bc.id),
                headless=config.headless,
                viewport={"width": 1920, "height": 1080},
                args=["--no-sandbox", "--disable-gpu"],
            )
            if config.stealth:
                await apply_stealth_patches(ctx)
            self._browsers[bc.id] = ctx
            self._contexts[bc.id] = ctx
            return ctx, ctx

        reconnected = await self._try_reconnect(bc.id)
        if reconnected:
            return reconnected

        return await self._launch_new(bc, config)

    async def get_page(self, browser_id: str, bc: BrowserConfig | None = None,
                       global_config: FreeactConfig | None = None) -> Page | None:
        if global_config is None:
            global_config = get_config()
        if bc is None:
            bc = BrowserConfig(id=browser_id, name=browser_id, type=global_config.default_browser)

        _, context = await self.get_or_create_context(bc, global_config)
        if context.pages:
            page = context.pages[0]
            try:
                page.url
                return page
            except Exception:
                return await context.new_page()
        return await context.new_page()

    async def save_page_url(self, browser_id: str, session_name: str, url: str):
        f = FREACT_HOME / "sessions" / f"{session_name}.json"
        data = {}
        if f.exists():
            try:
                data = json.loads(f.read_text())
            except json.JSONDecodeError:
                pass
        data["url"] = url
        data["browser_id"] = browser_id
        f.write_text(json.dumps(data))

    async def get_saved_url(self, session_name: str) -> str | None:
        f = FREACT_HOME / "sessions" / f"{session_name}.json"
        if f.exists():
            try:
                data = json.loads(f.read_text())
                return data.get("url")
            except json.JSONDecodeError:
                pass
        return None

    async def close_context(self, browser_id: str):
        proc = self._proc.pop(browser_id, None)
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        ctx = self._contexts.pop(browser_id, None)
        if ctx:
            try:
                await ctx.close()
            except Exception:
                pass
        br = self._browsers.pop(browser_id, None)
        if br and br is not ctx:
            try:
                await br.close()
            except Exception:
                pass
        pf = self._port_file(browser_id)
        if pf.exists():
            pf.unlink()

    def generate_browser_id(self) -> str:
        return f"browser_{uuid.uuid4().hex[:12]}"


_browser_manager: BrowserManager | None = None


async def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager
