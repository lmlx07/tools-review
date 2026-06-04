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
  - 爬虫
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
// 正常浏览器：navigator.webdriver = undefined 或 false
// 自动化浏览器：navigator.webdriver = true
```

This is the most basic test. Selenium and Puppeteer will set this flag by default.

### 2. Chrome-specific properties

```javascript
// 真实 Chrome 有 chrome 对象
typeof window.chrome !== 'undefined'

// 但自动化工具可能暴露过多属性
window.chrome.runtime  // Puppeteer 模式下存在这个
```

### 3. Behavioral characteristics

```javascript
// 鼠标是否真实移动？
// 滚动是否太"完美"？
// 点击间隔是否太规律？
// 页面加载后是否立即触发所有事件？
```

### 4. Permissions API

```javascript
// 自动化浏览器通常返回提示状态
navigator.permissions.query({name: 'notifications'})
// 真实用户：prompt（默认）
// headless 浏览器：denied
```

### 5. CDP detection

Some advanced detection tools can detect the presence of CDP connections:

```javascript
// 检测 DevTools 是否打开
// 检测 WebSocket 调试连接
// 检测 performance API 中的异常
```

---

## Two ways for CDP to modify fingerprints

CDP provides two ways to modify browser fingerprints:

### Page.addScriptToEvaluateOnNewDocument

Inject a script before each new document is executed. The properties and methods modified here will overwrite the native implementation.

```python
cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        // 这段代码在每个页面加载前执行
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
    """注入脚本覆盖 navigator.webdriver"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // 覆盖 webdriver 属性
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined,
            configurable: true
        });
        
        // 因为一些检测会用 Object.getOwnPropertyDescriptor 来检查
        // 所以需要确保看起来像是原生未定义的属性
        '''
    })

# 在 Page.enable 之后、Page.navigate 之前调用
override_webdriver(ws)
```

Verification effect:

```python
result = cmd(ws, 'Runtime.evaluate', {
    'expression': 'navigator.webdriver',
    'returnByValue': True
})
print(result['result']['value'])  # 输出：undefined
```

### Advanced: Handling more in-depth inspections

Some websites check the **property descriptor** of `navigator.webdriver`:

```javascript
// 检测是否被 Object.defineProperty 覆盖过
const desc = Object.getOwnPropertyDescriptor(navigator, 'webdriver');
// 如果是原生 undefined，desc 应该是 undefined
// 如果被覆盖过，desc 会是一个属性描述符对象
```

A more thorough bypass:

```python
def stealth_webdriver(ws):
    """深度隐藏 webdriver 痕迹"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // 使用 Proxy 隐藏 webdriver
        const originalNavigator = window.navigator;
        const navigatorProxy = new Proxy(originalNavigator, {
            get(target, prop) {
                if (prop === 'webdriver') return undefined;
                if (prop === 'plugins' && target.plugins.length === 0) {
                    // 模拟几个插件
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
        
        // 用 Proxy 替换 navigator
        // 注意：这种方法更激进，可能会被检测
        // 但实际上，更简单的方式就够用
        '''
    })
```

---

## Practice 2: Modify User-Agent and platform information

User-Agent is one of the most obvious fingerprints, and the `Emulation` domain of CDP provides a specialized modification method:

```python
def set_user_agent(ws, ua=None, platform=None):
    """设置自定义 User-Agent 和平台"""
    
    if ua is None:
        # Windows 11 + Chrome 125 的标准 UA
        ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36'
    
    if platform is None:
        platform = 'Win32'
    
    cmd(ws, 'Emulation.setUserAgentOverride', {
        'userAgent': ua,
        'platform': platform,
        'acceptLanguage': 'zh-CN,zh;q=0.9,en;q=0.8'
    })

# 调用
set_user_agent(ws)
```

What is easier to overlook here is the **platform** parameter. If you only change UA but not platform:

```javascript
// navigator.platform 仍然是 'MacIntel'（如果你在用 Mac）
// 但 UA 写的是 Windows，这就露出马脚了
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
    """修改 Canvas 指纹，每次返回略有差异的结果"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // 保存原始方法
        const originalToDataURL = HTMLCanvasElement.prototype.toDataURL;
        const originalToBlob = HTMLCanvasElement.prototype.toBlob;
        
        // 添加少量噪声来改变指纹
        function addNoise(canvas) {
            // 在画布角落添加一个几乎不可见的像素
            const ctx = canvas.getContext('2d');
            if (!ctx) return canvas;
            
            const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
            // 修改第一个像素的蓝色通道
            if (imageData.data.length > 3) {
                imageData.data[0] = imageData.data[0] ^ 1;  // XOR 1 来翻转最低位
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
    """每次注入不同的噪声来产生变化"""
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
    """修改 WebGL 参数，隐藏真实显卡信息"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // 修改 WebGLRenderingContext 的 getParameter 方法
        const originalGetParameter = WebGLRenderingContext.prototype.getParameter;
        
        WebGLRenderingContext.prototype.getParameter = function(param) {
            const result = originalGetParameter.call(this, param);
            
            // UNMASKED_VENDOR (0x9245) 和 UNMASKED_RENDERER (0x9246) 暴露显卡信息
            if (param === 0x9245) {  // UNMASKED_VENDOR_WEBGL
                return 'Intel Inc.';
            }
            if (param === 0x9246) {  // UNMASKED_RENDERER_WEBGL
                return 'Intel Iris OpenGL Engine';
            }
            
            // RENDERER (0x1F01) 和 VENDOR (0x1F00)
            if (param === 0x1F00) {  // VENDOR
                return 'WebKit';
            }
            if (param === 0x1F01) {  // RENDERER
                return 'WebKit WebGL';
            }
            
            // 修改 extensions 返回结果
            if (param === 0x1F03) {  // EXTENSIONS
                // 删掉一些不常见的扩展
                const extStr = String(result);
                const blocked = ['WEBGL_debug_renderer_info', 'WEBGL_debug_shaders'];
                return extStr.split(' ').filter(e => !blocked.includes(e)).join(' ');
            }
            
            return result;
        };
        
        // 还要处理 WebGL2
        if (WebGL2RenderingContext) {
            WebGL2RenderingContext.prototype.getParameter = WebGLRenderingContext.prototype.getParameter;
        }
        '''
    })
```

### Get the real WebGL parameters

You can start by getting these parameters from a real Windows machine:

```javascript
// 在真实浏览器中执行，记录返回值
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
    """修改 AudioContext 指纹"""
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': '''
        // 修改 AudioContext 的方法来改变指纹
        const originalGetChannelData = AudioBuffer.prototype.getChannelData;
        
        AudioBuffer.prototype.getChannelData = function(channel) {
            const data = originalGetChannelData.call(this, channel);
            // 在返回的数据中添加微小的噪声（0.0001% 级别）
            for (let i = 0; i < data.length; i += 10) {
                data[i] *= 1.000001;  // 几乎不可感知的差异
            }
            return data;
        };
        
        // 覆盖 AudioContext 的创建，使其使用修改后的方法
        // 或者直接覆盖 createOscillator / createAnalyser
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
    """设置浏览器视口和屏幕参数"""
    
    # 使用 Emulation 域设置
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

# 用法
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
    """设置时区和语言环境"""
    
    # 修改时区（Emulation 域）
    cmd(ws, 'Emulation.setTimezoneOverride', {
        'timezoneId': timezone
    })
    
    # 修改语言（通过脚本注入）
    cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
        'source': f'''
        Object.defineProperties(navigator, {{
            language: {{ get: () => '{locale}' }},
            languages: {{ get: () => ['{locale}', 'en'] }},
        }});
        '''
    })

# 常见时区
# 'Asia/Shanghai' — 中国
# 'America/New_York' — 美东
# 'Europe/London' — 伦敦
# 'Asia/Tokyo' — 东京
```

**Note**: `Emulation.setTimezoneOverride` modifies the time zone at the browser kernel level, `Date.toString()`, `Intl.DateTimeFormat`, etc. will be affected, which is more thorough than JS injection.

However, the `Emulation` domain does not have a direct language setting interface, so the language needs to be modified with JS injection.

---

## Practical combat eight: Complete anti-detection tool class

Integrate all the above techniques into a complete tool class:

```python
import json, urllib.request, websocket, time, random, base64

class CDPAntiDetect:
    """CDP 反检测工具类"""
    
    # 常用分辨率
    VIEWPORTS = {
        'desktop':  {'width': 1920, 'height': 1080, 'scale': 1.0},
        'laptop':   {'width': 1366, 'height': 768,  'scale': 1.0},
        'macbook':  {'width': 1440, 'height': 900,  'scale': 2.0},
    }
    
    # 常用 User-Agent
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
        """连接 Chrome"""
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
        """注入页面脚本"""
        result = self._cmd('Page.addScriptToEvaluateOnNewDocument', {'source': source})
        self.script_ids.append(result.get('identifier'))
        return self
    
    def apply_preset(self, preset='desktop'):
        """应用完整预设"""
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
        
        # 1. 设置 User-Agent 和平台
        self._cmd('Emulation.setUserAgentOverride', {
            'userAgent': config['ua'],
            'platform': config['platform'],
        })
        
        # 2. 设置视口和分辨率
        vp = config['viewport']
        self._cmd('Emulation.setDeviceMetricsOverride', {
            'width': vp['width'], 'height': vp['height'],
            'deviceScaleFactor': vp['scale'],
            'mobile': False,
            'screenWidth': vp['width'], 'screenHeight': vp['height'],
            'positionX': 0, 'positionY': 0,
        })
        
        # 3. 设置时区
        self._cmd('Emulation.setTimezoneOverride', {'timezoneId': config['timezone']})
        
        # 4. 注入反检测脚本
        seed = random.randint(1, 255)
        self._inject_js(f'''
        // 覆盖 webdriver
        Object.defineProperty(navigator, 'webdriver', {{ get: () => undefined }});
        
        // 设置语言
        Object.defineProperties(navigator, {{
            language: {{ get: () => '{config["locale"]}' }},
            languages: {{ get: () => ['{config["locale"]}', 'en', 'en-US'] }},
        }});
        
        // Canvas 指纹噪声
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
        
        // WebGL 指纹覆盖
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
        
        // 覆盖 plugins 数组（非自动化浏览器通常有插件）
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
        """导航到目标页面（已应用反检测）"""
        self._cmd('Page.navigate', {'url': url})
        time.sleep(2)
        return self
    
    def close(self):
        if self.ws:
            self.ws.close()


# ====== 使用示例 ======
ad = CDPAntiDetect().connect()

# 应用桌面端反检测预设
ad.apply_preset('desktop')

# 访问目标网站
ad.navigate('https://bot.sannysoft.com/')  # 一个检测自动化浏览器的页面
time.sleep(3)

# 截屏验证
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
// 检查 WebSocket 连接
// 自动化浏览器通常有活跃的 WebSocket 连接到调试端口
// 一些高级检测可以尝试发现这个连接
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