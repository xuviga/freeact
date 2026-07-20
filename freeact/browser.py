"""Browser management — real browser via CDP, zero automation flags.

Stability improvements:
- Robust reconnection with retries
- Better page lifecycle handling (handles closed/detached pages)
- Page pool with `get_active_page()` that finds a working page
- Configurable connection timeout
"""

import asyncio
import json
import os
import shutil
import socket
import subprocess
import uuid
from pathlib import Path

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from freeact.config import FREACT_HOME, BrowserConfig, FreeactConfig, get_config
from freeact.logger import log, log_error
from freeact.stealth import apply_stealth_patches
from freeact.proxy import parse_proxy_config

BROWSER_MAP = {
    "chrome": {
        "name": "Chrome",
        "paths": [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            Path.home() / r"AppData\Local\Google\Chrome\Application\chrome.exe",
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/usr/bin/google-chrome",
            "/usr/bin/google-chrome-stable",
            "/snap/bin/chromium",
        ],
        "profile": Path.home() / r"AppData\Local\Google\Chrome\User Data",
        "alt_profiles": [
            Path.home() / "Library/Application Support/Google/Chrome",
            Path.home() / ".config/google-chrome",
        ],
        "exe": "chrome.exe",
    },
    "edge": {
        "name": "Edge",
        "paths": [
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/usr/bin/microsoft-edge",
        ],
        "profile": Path.home() / r"AppData\Local\Microsoft\Edge\User Data",
        "alt_profiles": [
            Path.home() / "Library/Application Support/Microsoft Edge",
            Path.home() / ".config/microsoft-edge",
        ],
        "exe": "msedge.exe",
    },
    "yandex": {
        "name": "Yandex",
        "paths": [
            r"C:\Program Files (x86)\Yandex\YandexBrowser\Application\browser.exe",
            Path.home() / r"AppData\Local\Yandex\YandexBrowser\Application\browser.exe",
            "/Applications/Yandex.app/Contents/MacOS/Yandex",
            "/usr/bin/yandex-browser",
        ],
        "profile": Path.home() / r"AppData\Local\Yandex\YandexBrowser\User Data",
        "alt_profiles": [
            Path.home() / "Library/Application Support/Yandex/YandexBrowser",
            Path.home() / ".config/yandex-browser",
        ],
        "exe": "browser.exe",
    },
}

CDP_DIR = FREACT_HOME / "cdp"
CDP_DIR.mkdir(parents=True, exist_ok=True)
PROFILES_DIR = FREACT_HOME / "copied_profiles"
PROFILES_DIR.mkdir(parents=True, exist_ok=True)

CDP_CONNECT_TIMEOUT = 30
CDP_RETRY_INTERVAL = 0.8
CDP_MAX_RETRIES = 20


def find_browser(browser_type: str) -> dict | None:
    bt = browser_type.lower()
    import sys
    for key, info in BROWSER_MAP.items():
        if bt == key or bt in info["name"].lower():
            for p in info["paths"]:
                if Path(p).exists():
                    result = {**info, "found_path": str(p), "key": key}
                    if sys.platform != "win32":
                        for alt in info.get("alt_profiles", []):
                            if alt.exists():
                                result["profile"] = alt
                                break
                    return result
    for info in BROWSER_MAP.values():
        for p in info["paths"]:
            if Path(p).exists():
                result = {**info, "found_path": str(p), "key": "chrome"}
                if sys.platform != "win32":
                    for alt in info.get("alt_profiles", []):
                        if alt.exists():
                            result["profile"] = alt
                            break
                return result
    return None


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _kill_browser(exe_name: str):
    try:
        import sys
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", exe_name], capture_output=True, timeout=10)
        else:
            subprocess.run(["pkill", "-f", exe_name], capture_output=True, timeout=10)
    except Exception:
        pass


def _copy_file_fast(src: str, dst: str, *, follow_symlinks: bool = True):
    """Hardlink-first copy: use os.link to share inodes, fallback to copy2."""
    try:
        os.link(src, dst, follow_symlinks=follow_symlinks)
    except OSError:
        shutil.copy2(src, dst, follow_symlinks=follow_symlinks)


def _copy_profile(src: Path, dst: Path) -> Path:
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    dst.mkdir(parents=True, exist_ok=True)
    skip = {"Cache", "Code Cache", "GPUCache", "GrShaderCache", "ShaderCache",
            "Service Worker", "blob_storage", "WebStorage", "Crashpad",
            "CrashpadMetrics", "CrashpadMetadata",
            "BrowserMetrics", "browserMetrics-spare.pma",
            "SingletonLock", "SingletonSocket", "SingletonCookie",
            "Lockfile", "RunningChromeVersion"}
    errors: list[str] = []
    for item in src.iterdir():
        if item.name in skip or item.name == "Local State":
            continue
        dest = dst / item.name
        try:
            if item.is_dir():
                shutil.copytree(item, dest, copy_function=_copy_file_fast,
                                ignore=lambda d, f: [x for x in f if x in skip])
            else:
                _copy_file_fast(str(item), str(dest))
        except PermissionError:
            errors.append(f"{item.name}: permission denied")
        except OSError as e:
            errors.append(f"{item.name}: {e}")
    ls = src / "Local State"
    if ls.exists():
        try:
            shutil.copy2(ls, dst / "Local State")
        except Exception as e:
            errors.append(f"Local State: {e}")
    if errors:
        import warnings as _w
        _w.warn(f"Profile copy completed with {len(errors)} errors: {'; '.join(errors[:5])}")
    return dst


class BrowserManager:
    def __init__(self):
        self._playwright = None
        self._contexts: dict[str, BrowserContext] = {}
        self._browsers: dict[str, Browser] = {}
        self._proc: dict[str, subprocess.Popen] = {}
        self._pages: dict[str, Page] = {}

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
        for proc in self._proc.values():
            try:
                proc.wait(timeout=5)
            except Exception:
                pass
        self._proc.clear()

        for page in self._pages.values():
            try:
                if not page.is_closed():
                    await page.close()
            except Exception:
                pass
        self._pages.clear()

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
            browser = await self._playwright.chromium.connect_over_cdp(
                f"http://127.0.0.1:{port}",
                timeout=5000,
            )
            context = browser.contexts[0] if browser.contexts else await browser.new_context()
            self._browsers[bid] = browser
            self._contexts[bid] = context
            return browser, context
        except Exception:
            self._port_file(bid).unlink(missing_ok=True)
            return None

    async def refresh_profile(self, bc: BrowserConfig, config: FreeactConfig) -> bool:
        """Re-copy profile from source. Returns True if browser needs relaunch."""
        info = find_browser(bc.type or config.default_browser)
        if not info:
            return False
        profile_dir = PROFILES_DIR / f"{bc.id}_profile"
        _copy_profile(info["profile"], profile_dir)
        return True

    async def _launch_new(self, bc: BrowserConfig, config: FreeactConfig) -> tuple[Browser, BrowserContext]:
        await self.start()

        info = find_browser(bc.type or config.default_browser)
        if not info:
            raise RuntimeError(f"No browser found for type: {bc.type or config.default_browser}")

        port = _free_port()
        self._save_port(bc.id, port)

        if bc.private:
            profile_dir = PROFILES_DIR / f"{bc.id}_tmp"
        else:
            profile_dir = PROFILES_DIR / f"{bc.id}_profile"

        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
        profile_dir.mkdir(parents=True, exist_ok=True)

        _copy_profile(info["profile"], profile_dir)
        log(f"Launching {info['name']} (headed={not config.headless}) profile {profile_dir}")

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
        browser = None
        max_retries = CDP_MAX_RETRIES if config.headless else CDP_MAX_RETRIES + 10
        retry_interval = CDP_RETRY_INTERVAL if config.headless else 1.0
        for i in range(max_retries):
            try:
                browser = await self._playwright.chromium.connect_over_cdp(
                    cdp, timeout=CDP_CONNECT_TIMEOUT * 1000,
                )
                log(f"CDP connected to {info['name']} on port {port} (attempt {i+1})")
                break
            except Exception:
                if i == max_retries - 1:
                    proc.kill()
                    self._port_file(bc.id).unlink(missing_ok=True)
                    log_error(f"CDP connect failed after {max_retries} attempts for {info['name']}")
                    raise RuntimeError(f"CDP connect failed after {max_retries} attempts")
                await asyncio.sleep(retry_interval)

        context = browser.contexts[0] if browser.contexts else await browser.new_context(
            viewport={"width": 1920, "height": 1080})

        if config.stealth:
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
            alive = await self.is_browser_alive(bc.id)
            if not alive:
                self._pages.pop(bc.id, None)
                self._contexts.pop(bc.id, None)
                self._browsers.pop(bc.id, None)
                self._port_file(bc.id).unlink(missing_ok=True)
            else:
                ctx = self._contexts[bc.id]
                try:
                    _ = ctx.pages
                    return self._browsers.get(bc.id), ctx
                except Exception:
                    del self._contexts[bc.id]
                    self._pages.pop(bc.id, None)

        await self.start()

        bt = (bc.type or config.default_browser).lower()
        if bt in ("chromium", "playwright"):
            raise RuntimeError(
                "Chromium/Playwright browser is disabled. "
                "Use only real browsers: yandex, chrome, edge. "
                "Set config.default_browser to 'yandex'."
            )

        reconnected = await self._try_reconnect(bc.id)
        if reconnected:
            return reconnected

        return await self._launch_new(bc, config)

    def _is_page_valid(self, page: Page) -> bool:
        try:
            if page.is_closed():
                return False
            page.url
            return True
        except Exception:
            return False

    async def is_browser_alive(self, browser_id: str) -> bool:
        proc = self._proc.get(browser_id)
        if proc is not None:
            if proc.poll() is not None:
                return False
        port = self._load_port(browser_id)
        if port:
            try:
                import aiohttp
                async with aiohttp.ClientSession() as session:
                    async with session.get(f"http://127.0.0.1:{port}/json/version", timeout=aiohttp.ClientTimeout(total=2)):
                        return True
            except Exception:
                return False
        return False

    async def get_page(self, browser_id: str, bc: BrowserConfig | None = None,
                       global_config: FreeactConfig | None = None) -> Page | None:
        if global_config is None:
            global_config = get_config()
        if bc is None:
            bc = BrowserConfig(id=browser_id, name=browser_id, type=global_config.default_browser)

        cached_page = self._pages.get(browser_id)
        if cached_page and self._is_page_valid(cached_page):
            return cached_page

        _, context = await self.get_or_create_context(bc, global_config)

        for page in context.pages:
            if self._is_page_valid(page):
                self._pages[browser_id] = page
                return page

        page = await context.new_page()
        self._pages[browser_id] = page
        return page

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
        data["_saved_at"] = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        f.parent.mkdir(parents=True, exist_ok=True)
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
        self._pages.pop(browser_id, None)

        proc = self._proc.pop(browser_id, None)
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
            try:
                proc.wait(timeout=5)
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
        pf.unlink(missing_ok=True)

    def generate_browser_id(self) -> str:
        return f"browser_{uuid.uuid4().hex[:12]}"


_browser_manager: BrowserManager | None = None


async def get_browser_manager() -> BrowserManager:
    global _browser_manager
    if _browser_manager is None:
        _browser_manager = BrowserManager()
    return _browser_manager
