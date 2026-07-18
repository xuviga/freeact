"""Anti-detection stealth patches for Playwright."""

import asyncio
import random
import string

from playwright.async_api import BrowserContext


STEALTH_SCRIPTS = [
    """
() => {
    Object.defineProperty(navigator, 'webdriver', {
        get: () => undefined,
    });
    Object.defineProperty(navigator, 'plugins', {
        get: () => [1, 2, 3, 4, 5],
    });
    Object.defineProperty(navigator, 'languages', {
        get: () => ['en-US', 'en'],
    });
    Object.defineProperty(navigator, 'platform', {
        get: () => 'Win32',
    });
    Object.defineProperty(navigator, 'hardwareConcurrency', {
        get: () => 8,
    });
    Object.defineProperty(navigator, 'deviceMemory', {
        get: () => 8,
    });
    window.chrome = {
        runtime: {},
        loadTimes: function() {},
        csi: function() {},
        app: {},
    };
    Object.defineProperty(navigator, 'permissions', {
        get: () => ({
            query: async () => ({ state: 'prompt' }),
        }),
    });
}
""",
    """
() => {
    const getParameter = WebGLRenderingContext.prototype.getParameter;
    WebGLRenderingContext.prototype.getParameter = function(parameter) {
        if (parameter === 37445) {
            return 'Intel Inc.';
        }
        if (parameter === 37446) {
            return 'Intel Iris OpenGL Engine';
        }
        return getParameter.call(this, parameter);
    };
}
""",
    """
() => {
    if (Notification && Notification.permission === 'default') {
        Notification.requestPermission = () => Promise.resolve('default');
    }
}
""",
]


async def apply_stealth_patches(context: BrowserContext) -> None:
    await context.add_init_script(
        """
    // Hide automation indicators
    delete Object.getPrototypeOf(navigator).webdriver;
    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});

    // Override plugins
    Object.defineProperty(navigator, 'plugins', {
        get: () => {
            const plugins = [
                {name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer', description: 'Portable Document Format'},
                {name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai', description: ''},
                {name: 'Native Client', filename: 'internal-nacl-plugin', description: ''},
            ];
            plugins.item = (i) => plugins[i];
            plugins.namedItem = (name) => plugins.find(p => p.name === name) || null;
            plugins.refresh = () => {};
            return Object.setPrototypeOf(plugins, PluginArray.prototype);
        }
    });

    // Override languages
    Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});

    // Override platform
    Object.defineProperty(navigator, 'platform', {get: () => 'Win32'});

    // Override hardware concurrency
    Object.defineProperty(navigator, 'hardwareConcurrency', {get: () => 8});

    // Override device memory
    Object.defineProperty(navigator, 'deviceMemory', {get: () => 8});

    // Fake chrome runtime
    window.chrome = {
        runtime: {onConnect: {addListener: () => {}}, onMessage: {addListener: () => {}}},
        loadTimes: () => {},
        csi: () => {},
        app: {},
    };

    // Override permissions
    const originalQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (parameters) => (
        parameters.name === 'notifications' ?
            Promise.resolve({state: Notification.permission}) :
            originalQuery(parameters)
    );

    // Canvas fingerprint randomization
    const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
    const originalToBlob = HTMLCanvasElement.prototype.toBlob;
    const randomNoise = () => Math.random() * 0.1;

    HTMLCanvasElement.prototype.toDataURL = function(...args) {
        const ctx = this.getContext('2d');
        if (ctx) {
            const imageData = ctx.getImageData(0, 0, this.width, this.height);
            for (let i = 0; i < imageData.data.length; i += 4) {
                imageData.data[i] = Math.min(255, Math.max(0, imageData.data[i] + randomNoise()));
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

    // Batched: hide key webdriver properties that get detected most
    Object.defineProperty(document, 'hidden', {get: () => false});
    Object.defineProperty(document, 'visibilityState', {get: () => 'visible'});
"""
    )

    for script in STEALTH_SCRIPTS:
        await context.add_init_script(script)
