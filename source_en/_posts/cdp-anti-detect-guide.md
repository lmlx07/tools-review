---
lang: en
title: "CDP browser fingerprinting and anti-detection practice: using Python to modify fingerprints to bypass automated detection"
date: "2026-06-04 16:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Fingerprinting
  - Anti-Detection
  - Web Scraping
categories:
  - CDP Basics
  - Python Practice
description: Detailed explanation of the composition of browser fingerprints (Canvas, WebGL, AudioContext, fonts, etc.), and how to use CDP to modify these fingerprint parameters to bypass WebDriver detection, Cloudflare verification and fingerprint tracking systems.
---

> **One sentence summary**: Browser fingerprint is the "digital identity" that the website uses to identify you. CDP can modify these fingerprint parameters to make you look like a real user browser, not an automated script.

---

## What is browser fingerprinting?

When you visit a website, your browser leaks a lot of information: operating system version, browser type, screen resolution, installed fonts, graphics card model, time zone, language, etc. This information combined is enough to uniquely identify your device among hundreds of thousands of visitors.

**Common fingerprint dimensions:**

| Fingerprint type | Source | Uniqueness |
|---------|------|--------|
| Canvas fingerprint | `HTMLCanvasElement.toDataURL()` | ⭐⭐⭐⭐ |
| WebGL Fingerprint | `WebGLRenderingContext.getParameter()` | ⭐⭐⭐⭐⭐ |
| AudioContext fingerprint | `AudioContext.getChannelData()` | ⭐⭐⭐ |
| Font fingerprint | `document.fonts` / Flash | ⭐⭐⭐ |
| Screen information | `screen.width` / `screen.height` / `colorDepth` | ⭐⭐ |
| Time zone | `Intl.DateTimeFormat` / `Date.getTimezoneOffset()` | ⭐⭐ |
| Languages | `navigator.language` / `navigator.languages` | ⭐ |
| Hardware Concurrency | `navigator.hardwareConcurrency` | ⭐⭐ |
| Device Memory | `navigator.deviceMemory` | ⭐⭐ |
| Touch support | `navigator.maxTouchPoints` | ⭐⭐ |

---

## Common means of automated detection

Before discussing how to bypass it, let’s first understand how websites detect automated tools:

### 1. WebDriver logo

```javascript
// Normal browser: navigator.webdriver = undefined or false
// Automated browser: navigator.webdriver = true

```

This is the most basic test. Selenium and Puppeteer will set this flag by default.

### 2. Chrome-specific properties

```javascript
// Real Chrome has chrome objects
typeof window.chrome !== 'undefined'

// But automated tools can expose too many attributes
window.chrome.runtime // This exists in Puppeteer mode


```

### 3. Behavioral characteristics

```javascript
// Is the mouse really moving?
// Is the scroll too "perfect"?
// Is the click interval too regular?
// Are all events triggered immediately after the page loads?

```

### 4. Permissions API

```javascript
// Automated browsers usually return to the prompt state
navigator.permissions.query({name: 'notifications'})
// Real users: prompt (default)
// headless browser: denied

```

### 5. CDP detection

Some advanced detection tools can detect the presence of CDP connections:

```javascript
// Detect DevTools on
// Detect WebSocket debug connections
// Detect anomalies in the performance API

```

---

## Two ways for CDP to modify fingerprints

CDP provides two ways to modify browser fingerprints:

### Page.addScriptToEvaluateOnNewDocument

Inject a script before each new document is executed. The properties and methods modified here will overwrite the native implementation.

```python
cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        // This code executes before each page loads
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
    '''
})

```

**Good for**: Modifying JavaScript-level properties and methods

### Emulation field

The Emulation domain of CDP can modify parameters at the browser kernel level, which is lower level than JS injection.

```python
cmd(ws, 'Emulation.setUserAgentOverride', {
    'userAgent': 'Mozilla/5.0 ...'
})
```

**Suitable**: Modify engine-level parameters such as User-Agent, resolution, time zone, etc.

**Principle**: If you can use the Emulation field, use Emulation. Its modifications are deeper and more difficult to detect.

---

## Practice 1: Bypass navigator.webdriver detection

This is the most basic bypass and required by almost every anti-detection scheme:

```python
def override_webdriver(ws):
    """Injection script overrides navigator.webdriver"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // Override webdriver properties
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        
        // because some tests are checked with Object.getOwnPropertyDescriptor
        // So we need to make sure it looks like a native undefined property.
        '''
    })

# Called after Page.enable, before Page.navigate
override_webdriver(ws)

```

Verification effect:

```python
result = cmd(ws, 'Runtime.evaluate', {
    'expression': 'navigator.webdriver',
    'returnByValue': True
})
print(result['result']['value']) # Output: undefined

```

### Advanced: Handling more in-depth inspections

Some websites check the **property descriptor** of `navigator.webdriver`:

```javascript
// Detect if overridden by Object.defineProperty
const desc = Object.getOwnPropertyDescriptor(navigator, 'webdriver');
// If native undefined, desc should be undefined
// If overridden, desc will be a property descriptor object

```

A more thorough bypass:

```python
def stealth_webdriver(ws):
    """Hide webdriver traces in depth"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // Hide webdriver with proxy
        const originalNavigator = window.navigator;
        const navigatorProxy = new Proxy(originalNavigator, {
            get(target, prop) {
                if (prop === 'webdriver') return undefined;
                if (prop === 'plugins' && target.plugins.length === 0) {
                    // Simulate several plugins
                    return {
                        ...target.plugins,
                        length: 3,
                        0: {name: 'Chrome PDF Plugin'},
                        1: {name: 'Chrome PDF Viewer'},
                        2: {name: 'Native Client'}
                    };
                }
                return target[prop];
            }
        });
        
        // Replace navigator with proxy
        // Note: This method is more aggressive and may be tested
        // But actually, the simpler way is enough.
        '''
    })

```

---

## Practice 2: Modify User-Agent and platform information

User-Agent is one of the most obvious fingerprints, and the `Emulation` domain of CDP provides a specialized modification method:

```python
def set_user_agent(ws, ua=None, platform=None):
    """Set up custom User-Agent and Platform"""
    
    if ua is None:
        # Standard UA for Windows 11 + Chrome 125
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    
    if platform is None:
        platform = 'Win32'
    
    cmd(ws, 'Emulation.setUserAgentOverride', {
        'userAgent': ua,
        'platform': platform,
        'acceptLanguage': 'zh-CN,zh;q=0.9,en;q=0.8'
    })

# Recall
set_user_agent(ws)

```

What is easier to overlook here is the **platform** parameter. If you only change UA but not platform:

```javascript
// navigator.platform is still 'MacIntel' (if you're using a Mac)
// But UA is writing Windows, which shows the horse's feet.

```

### Use real device UA

For more realism, UA can be collected from real devices. Or use some well-known UA list:

```
Windows Chrome 125:  Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36
macOS Chrome 125:    Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36
Windows Edge 125:    Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0
```

---

## Practice 3: Canvas fingerprint modification

The principle of Canvas fingerprinting: the website uses JavaScript to draw text and graphics on the canvas, and then calls `toDataURL()` to obtain the pixel data. The drawing results of different graphics cards, drivers, and operating systems are slightly different, and this difference is the fingerprint.

```python
def override_canvas_fingerprint(ws):
    """Modify your Canvas fingerprint to return slightly different results each time"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // Save original method
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalToBlob = HTMLCanvasElement.prototype.toBlob;
        
        // Add a little noise to change your fingerprint
        function addNoise(canvas) {
            // Add an almost invisible pixel to the corner of the canvas
            const ctx = canvas.getContext('2d');
            if (!ctx) return canvas;
            
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            // Modify the blue channel of the first pixel
            if (imageData.data.length > 3) {
                imageData.data[0] = imageData.data[0] ^ 1; // XOR 1 to flip the lowest bit
                ctx.putImageData(imageData, 0, 0);
            }
            return canvas;
        }
        
        HTMLCanvasElement.prototype.toDataURL = function(...args) {
            addNoise(this);
            return originalToDataURL.apply(this, args);
        };
        
        HTMLCanvasElement.prototype.toBlob = function(...args) {
            addNoise(this);
            return originalToBlob.apply(this, args);
        };
        '''
    })


```

A more refined solution: **change the amount of noise** at each startup to avoid returning a fixed fingerprint value (because the fixed value itself is also a fingerprint).

```python
def override_canvas_with_variation(ws, seed=None):
    """Make a difference by injecting a different noise each time"""
    import random
    if seed is None:
        seed = random.randint(1, 255)
    
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': f'''
        const CANVAS_NOISE = {seed};
        
        HTMLCanvasElement.prototype.toDataURL = (function(original) {{
            return function(...args) {{
                const canvas = this;
                const ctx = canvas.getContext('2d');
                if (ctx) {{
                    const imageData = ctx.getImageData(0, 0, 1, 1);
                    if (imageData.data.length > 0) {{
                        imageData.data[3] = imageData.data[3] ^ CANVAS_NOISE;
                        ctx.putImageData(imageData, 0, 0);
                    }}
                }}
                return original.apply(this, args);
            }};
        }})(HTMLCanvasElement.prototype.toDataURL);
        '''
    })

```

---

## Practice 4: WebGL fingerprint modification

WebGL provides a wealth of information: graphics card models, renderers, vendors, supported feature lists, and more. This is one of the most distinguishing fingerprints.

```python
def override_webgl_fingerprint(ws):
    """Modify WebGL parameters to hide real video card information"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // Modify the getParameter method of the WebGLRenderingContext
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        
        WebGLRenderingContext.prototype.getParameter = function(param) {
            const result = originalGetParameter.call(this, param);
            
            // UNMASKED_vendor (0x9245) and UNMASKED_render (0x9246) exposed graphics card information
            if (param === 0x9245) {  // UNMASKED_VENDOR_WEBGL
                return 'Intel Inc.';
            }
            if (param === 0x9246) {  // UNMASKED_RENDERER_WEBGL
                return 'Intel Iris OpenGL Engine';
            }
            
            // Renderer (0x1F01) and vendor (0x1F00)
            if (param === 0x1F00) {  // VENDOR
                return 'WebKit';
            }
            if (param === 0x1F01) {  // RENDERER
                return 'WebKit WebGL';
            }
            
            // Modify extensions to return results
            if (param === 0x1F03) {  // EXTENSIONS
                // Remove some unusual extensions
                const extStr = String(result);
                const blocked = ['WEBGL_debug_renderer_info', 'WEBGL_debug_shaders'];
                return extStr.split(' ').filter(e => !blocked.includes(e)).join(' ');
            }
            
            return result;
        };
        
        // Also work on WebGL2
        if (WebGL2RenderingContext) {
            WebGL2RenderingContext.prototype.getParameter = WebGLRenderingContext.prototype.getParameter;
        }
        '''
    })

```

### Get the real WebGL parameters

You can start by getting these parameters from a real Windows machine:

```javascript
// Execute in real browser, record return value
const canvas = document.createElement('canvas');
const gl = canvas.getContext('webgl');
console.log({
    vendor: gl.getParameter(gl.VENDOR),
    renderer: gl.getParameter(gl.RENDERER),
    unmaskedVendor: gl.getExtension('WEBGL_debug_renderer_info')
        ?.getParameter(gl.UNMASKED_VENDOR_WEBGL),
    unmaskedRenderer: gl.getExtension('WEBGL_debug_renderer_info')
        ?.getParameter(gl.UNMASKED_RENDERER_WEBGL)
});

```

These real values ​​are then used to override the automation browser's WebGL parameters.

---

## Practical combat five: AudioContext fingerprint modification

AudioContext fingerprint obtains subtle differences in the device audio stack by processing audio signals:

```python
def override_audio_fingerprint(ws):
    """Modify AudioContext Fingerprint"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // Method to modify AudioContext to change fingerprint
        const originalGetChannelData = AudioBuffer.prototype.getChannelData;
        
        AudioBuffer.prototype.getChannelData = function(channel) {
            const data = originalGetChannelData.call(this, channel);
            // Add tiny noise (level 0.0001%) to the returned data
            for (let i = 0; i < data.length; i += 10) {
                data[i] *= 1.000001; // Almost imperceptible difference
            }
            return data;
        };
        
        // Override the creation of the AudioContext to use the modified method
        // or just overwrite createOscillator/createAnalyser
        const originalCreateOscillator = BaseAudioContext.prototype.createOscillator;
        BaseAudioContext.prototype.createOscillator = function() {
            console.log('[CDP] AudioContext access blocked');
            return originalCreateOscillator.call(this);
        };
        '''
    })


```

---

## Practice 6: Modify screen resolution and viewport

```python
def set_viewport(ws, width=1920, height=1080, device_scale_factor=1.0):
    """Setting Browser Viewport and Screen Parameters"""
    
    # Use Emulation Domain Settings
    cmd(ws, 'Emulation.setDeviceMetricsOverride', {
        'width': width,
        'height': height,
        'deviceScaleFactor': device_scale_factor,
        'mobile': False,
        'screenWidth': width,
        'screenHeight': height,
        'positionX': 0,
        'positionY': 0,
        'screenOrientation': {'type': 'landscapePrimary', 'angle': 0}
    })

# Usage Example
set_viewport(ws, width=1920, height=1080)

```

**Why it matters**:
- Many anti-fraud systems check `screen.width` and `screen.height`
- The default CDP window may only be 800x600, exposing automation features
- The mismatch between the viewport and screen parameters is also a suspect

### Common resolution configurations

```python
VIEWPORTS = {
    'desktop_1080p': {'width': 1920, 'height': 1080, 'scale': 1.0},
    'desktop_2k':    {'width': 2560, 'height': 1440, 'scale': 1.0},
    'macbook_pro':   {'width': 1440, 'height': 900, 'scale': 2.0},
    'thinkpad':      {'width': 1366, 'height': 768, 'scale': 1.0},
}
```

---

## Practice 7: Modify the time zone and locale

Some websites use time zone and language to determine whether a user is using an agent or automated tool:

```python
def set_timezone_and_locale(ws, timezone='Asia/Shanghai', locale='zh-CN'):
    """Set time zone and locale"""
    
    # Modify Time Zone (Emulation Field)
    cmd(ws, 'Emulation.setTimezoneOverride', {
        'timezoneId': timezone
    })
    
    # Change language (via script injection)
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': f'''
        Object.defineProperties(navigator, {{
            language: {{ get: () => '{locale}' }},
            languages: {{ get: () => ['{locale}', 'en'] }},
        }});
        '''
    })

# Common Time Zones
# 'Asia/Shanghai' — China
# 'America/New_York' — East Coast
# 'Europe/London' — London
# 'Asia/Tokyo' — Tokyo

```

**Note**: `Emulation.setTimezoneOverride` modifies the time zone at the browser kernel level, `Date.toString()`, `Intl.DateTimeFormat`, etc. will be affected, which is more thorough than JS injection.

However, the `Emulation` domain does not have a direct language setting interface, so the language needs to be modified with JS injection.

---

## Practical combat eight: Complete anti-detection tool class

Integrate all the above techniques into a complete tool class:

```python
import json, urllib.request, websocket, time, random, base64

class CDPAntiDetect:
    """CDP Counter Detection Tool Class"""
    
    # Common resolutions
    VIEWPORTS = {
        'desktop':  {'width': 1920, 'height': 1080, 'scale': 1.0},
        'laptop':   {'width': 1366, 'height': 768,  'scale': 1.0},
        'macbook':  {'width': 1440, 'height': 900,  'scale': 2.0},
    }
    
    # Common User-Agent
    USER_AGENTS = {
        'win_chrome': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
        'mac_chrome': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36',
    }
    
    def __init__(self, host='localhost:9222'):
        self.host = host
        self.ws = None
        self._id = 1
        self.script_ids = []
    
    def connect(self):
        """Connect Chrome"""
        data = json.loads(urllib.request.urlopen(f'http://{self.host}/json', timeout=5).read())
        ws_url = data[0]['webSocketDebuggerUrl']
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._cmd('Page.enable')
        self._cmd('Runtime.enable')
        return self
    
    def _cmd(self, method, params=None):
        if params is None: params = {}
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == self._id: return r.get('result', {})
    
    def _inject_js(self, source):
        """Inject Page Script"""
        result = self._cmd('Page.addScriptToEvaluateOnNewDocument', {'source': source})
        self.script_ids.append(result.get('identifier'))
        return self
    
    def apply_preset(self, preset='desktop'):
        """Apply full preset"""
        preset_actions = {
            'desktop': {
                'viewport': self.VIEWPORTS['desktop'],
                'ua': self.USER_AGENTS['win_chrome'],
                'platform': 'Win32',
                'timezone': 'Asia/Shanghai',
                'locale': 'zh-CN',
            },
            'mac': {
                'viewport': self.VIEWPORTS['macbook'],
                'ua': self.USER_AGENTS['mac_chrome'],
                'platform': 'MacIntel',
                'timezone': 'Asia/Shanghai',
                'locale': 'zh-CN',
            },
        }
        
        config = preset_actions.get(preset, preset_actions['desktop'])
        
        # 1. Set up User-Agent and Platform
        self._cmd('Emulation.setUserAgentOverride', {
            'userAgent': config['ua'],
            'platform': config['platform'],
        })
        
        # 2. Set the viewport and resolution
        vp = config['viewport']
        self._cmd('Emulation.setDeviceMetricsOverride', {
            'width': vp['width'], 'height': vp['height'],
            'deviceScaleFactor': vp['scale'],
            'mobile': False,
            'screenWidth': vp['width'], 'screenHeight': vp['height'],
            'positionX': 0, 'positionY': 0,
        })
        
        # 3. Set time zone
        self._cmd('Emulation.setTimezoneOverride', {'timezoneId': config['timezone']})
        
        # 4. Inject the counter-detection script
        seed = random.randint(1, 255)
        self._inject_js(f'''
        // Override webdriver
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        
        // Set languages
        Object.defineProperties(navigator, {{
            language: {{ get: () => '{config["locale"]}' }},
            languages: {{ get: () => ['{config["locale"]}', 'en', 'en-US'] }},
        }});
        
        // Canvas Fingerprint Noise
        const CANVAS_NOISE = {seed};
        const _toDataURL = HTMLCanvasElement.prototype.toDataURL.bind(HTMLCanvasElement.prototype);
        HTMLCanvasElement.prototype.toDataURL = function(...args) {{
            const ctx = this.getContext('2d');
            if (ctx) {{
                try {{
                    const imageData = ctx.getImageData(0, 0, 1, 1);
                    if (imageData.data.length > 0) {{
                        imageData.data[0] ^= 1;
                        ctx.putImageData(imageData, 0, 0);
                    }}
                }} catch(e) {{}}
            }}
            return _toDataURL.apply(this, args);
        }};
        
        // WebGL Fingerprint Override
        if (WebGLRenderingContext) {{
            const _getParam = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(p) {{
                if (p === 0x9245) return 'Intel Inc.';
                if (p === 0x9246) return 'Intel Iris OpenGL Engine';
                if (p === 0x1F00) return 'WebKit';
                if (p === 0x1F01) return 'WebKit WebGL';
                return _getParam.call(this, p);
            }};
        }}
        
        // Override plugins array (non-automated browsers usually have plugins)
        if (navigator.plugins.length === 0) {{
            Object.defineProperty(navigator, 'plugins', {{
                get: () => {{
                    const arr = [
                        {{name: 'Chrome PDF Plugin', filename: 'internal-pdf-viewer'}},
                        {{name: 'Chrome PDF Viewer', filename: 'mhjfbmdgcfjbbpaeojofohoefgiehjai'}},
                        {{name: 'Native Client', filename: 'internal-nacl-plugin'}},
                    ];
                    arr.length = 3;
                    arr.item = i => arr[i];
                    arr.namedItem = n => arr.find(p => p.name === n);
                    return arr;
                }}
            }});
        }}
        ''')
        
        print(f'✅ Anti-detect preset applied: {preset}')
        return self
    
    def navigate(self, url):
        """Navigate to the destination page (anti-detection applied)"""
        self._cmd('Page.navigate', {'url': url})
        time.sleep(2)
        return self
    
    def close(self):
        if self.ws:
            self.ws.close()


# Usage Sample
ad = CDPAntiDetect().connect()

# App Desktop Anti-Detection Preset
ad.apply_preset('desktop')

# Visit target website
ad.navigate('https://bot.sannysoft.com/') # A page to detect automated browsers
time.sleep(3)

# Screenshot verification
screenshot = ad._cmd('Page.captureScreenshot', {'format': 'png'})
with open('anti_detect_result.png', 'wb') as f:
    f.write(base64.b64decode(screenshot['data']))

ad.close()


```

Visit [bot.sannysoft.com](https://bot.sannysoft.com/) or [pixelscan.net](https://pixelscan.net/) to check your anti-camouflage effect.

---

## Limitation analysis

### 1. The CDP connection itself can be detected

```javascript
// Check WebSocket Connection
// Automated browsers typically have an active WebSocket connection to the debug port
// Some advanced tests can try to discover this connection

```

For ordinary websites, there is no need to worry, but for advanced protection systems such as Cloudflare 5-second shield and Akamai, CDP injection alone may not be enough.

### 2. Behavioral characteristics are difficult to simulate

Fingerprint parameters can be changed, but **human behavior** is difficult to simulate:
- The mouse movement trajectory is too straight → detected
- Clicks are too evenly spaced → detected
- No scrolling behavior → caught

It is recommended to use `Input.dispatchMouseEvent` to send the real mouse trajectory instead of jumping coordinates directly.

### 3. Fingerprint consistency

If you generate a different fingerprint every time you visit, it will be marked as "abnormal fingerprint change". Suggestions:
- Fixed a fingerprint for each target website
- Visit the same website multiple times with the same fingerprint
- Change fingerprints regularly (e.g. every day)

### 4. Side effects of WebGL modifications

Modifying WebGL parameters may cause rendering exceptions on some websites that use WebGL (such as 3D model viewers). In this case you can choose not to intercept WebGL.

### 5. TLS fingerprint

CDP cannot modify the fingerprint of the TLS layer (JA3/JA3S). Some advanced security systems identify automated traffic by analyzing the characteristics of TLS handshake packets. This requires lower-level solutions (such as modifying the Chrome source code or rewriting the TLS stack using Go/rust).

---

## Summarize

CDP provides rich fingerprint modification capabilities, which are enough to cope with anti-crawling and anti-automatic detection of most websites:

- ✅ **Navigator properties** — webdriver, plugins, language, etc.
- ✅ **WebGL Parameters** — Graphics card vendors, renderers
- ✅ **Canvas Fingerprint** — Pixel Noise Injection
- ✅ **AudioContext** — audio data fine-tuning
- ✅ **Screen & Viewport** — Resolution, Scaling
- ✅ **Time Zone & Language** — Emulation domain support
- ⚠️ **TLS Fingerprint** — out of reach of CDP, requires additional solutions

**Recommended protection level:**

| Goal type | Scenario |
|---------|------|
| Ordinary website (news/blog) | Only change User-Agent + webdriver |
| Medium level (e-commerce/social) | Apply desktop preset |
| Advanced level (banking/risk control) | Desktop preset + behavioral simulation |
| Enterprise Grade (Cloudflare/Akamai) | All of the above + TLS fingerprinting |

The next article will dive into CDP’s **Performance Tracking and Lighthouse Integration**, so stay tuned.