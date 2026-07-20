"""Anti-detection stealth patches for Playwright.

Stability fix: single comprehensive init script, no duplicate patches.
Applied once per context. Canvas noise only for small canvases (performance).
"""

from playwright.async_api import BrowserContext


STEALTH_INIT_SCRIPT = """
() => {
    if (window.__freeact_stealth_applied) return;
    window.__freeact_stealth_applied = true;

    // Hide automation indicators
    delete Object.getPrototypeOf(navigator).webdriver;
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

    // Override plugins with realistic array
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
            ];
            plugins.item = (i) => plugins[i] || null;
            plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
            plugins.refresh = () => {};
            Object.setPrototypeOf(plugins, PluginArray.prototype);
            return plugins;
        },
        configurable: true,
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

    // Override platform
    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});

    // Override hardware concurrency
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

    // Override device memory
    if ('deviceMemory' in navigator) {
        Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});
    }

    // Fake chrome runtime
    window.chrome = {
        runtime: {
            onConnect: {addListener: () => {}},
            onMessage: {addListener: () => {}},
        },
        loadTimes: () => {},
        csi: () => {},
        app: {},
    };

    // Override permissions query
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({state: Notification.permission || 'prompt'}) :
            originalQuery(parameters)
    );

    // Canvas fingerprint randomization (only for small canvases to avoid perf hit)
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        const ctx = this.getContext('2d');
        if (ctx && this.width > 0 && this.height > 0 && this.width * this.height <= 100000) {
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] = Math.min(255, Math.max(0, imageData.data[i] + (Math.random() * 0.1 - 0.05)));
            }
            ctx.putImageData(imageData, 0, 0);
        }
        return originalToDataURL.apply(this, args);
    };

    // WebGL vendor spoofing
    try {
        const getParam = WebGLRenderingContext.prototype.getParameter;
        WebGLRenderingContext.prototype.getParameter = function(p) {
            if (p === 37445) return 'Intel Inc.';
            if (p === 37446) return 'Intel Iris OpenGL Engine';
            return getParam.call(this, p);
        };
    } catch(e) {}

    // Ensure document visibility shows as visible
    Object.defineProperty(document, 'hidden', {get: () => false});
    Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});

    // Override Notification.requestPermission to avoid popups
    if (window.Notification && Notification.permission === 'default') {
        Notification.requestPermission = () => Promise.resolve('default');
    }

    // Fix for headless detection via chrome.runtime
    if (!window.chrome || !window.chrome.runtime) {
        window.chrome = window.chrome || {};
        window.chrome.runtime = {
            onConnect: {addListener: () => {}},
            onMessage: {addListener: () => {}},
        };
    }
    // --- Google One Tap credential interceptor ---
    if (!window.__freeact_google_hook) {
        window.__freeact_google_hook = true;
        let _google_value;
        Object.defineProperty(window, 'google', {
            get() { return _google_value; },
            set(v) {
                _google_value = v;
                if (v && v.accounts && v.accounts.id) {
                    const origInit = v.accounts.id.initialize.bind(v.accounts.id);
                    v.accounts.id.initialize = function(cfg) {
                        window.__freeact_google_cfg = cfg;
                        const origCb = cfg.callback;
                        cfg.callback = function(response) {
                            window.__freeact_google_cred = response;
                            return origCb ? origCb(response) : response;
                        };
                        return origInit(cfg);
                    };
                }
            },
            configurable: true, enumerable: true
        });
    }
}
"""


async def apply_stealth_patches(context: BrowserContext) -> None:
    await context.add_init_script(STEALTH_INIT_SCRIPT)
