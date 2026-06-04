---
lang: en
title: "The Complete Guide to Chrome DevTools Protocol (CDP): The Ultimate Solution to Controlling Your Browser with Python"
date: "2026-06-03 14:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Automation
  - Selenium
  - Playwright
categories:
  - CDP Basics
  - Python Practice
description: What is Chrome DevTools Protocol (CDP)? Why is it said to be a more powerful browser automation solution than Selenium? This article will help you start from scratch, use Python to directly control the Chrome browser through WebSocket, and implement advanced operations such as navigation, screenshots, and network interception, and attaches complete practical code.
---

> **Summary in one sentence**: Chrome DevTools Protocol (CDP) is Chrome's built-in "remote control API", which allows you to directly control everything in the browser with code - from opening web pages to intercepting network requests, from taking screenshots to tracking performance. It is the underlying foundation of tools such as Puppeteer and Playwright.

---

## What is CDP

Chrome DevTools Protocol (CDP for short) is a communication protocol based on **WebSocket**. Essentially, it's the "backend API" for all the functionality you see in Chrome Developer Tools (F12).

Whenever you open the Elements, Console, or Network panels of DevTools, Chrome internally communicates with the DevTools frontend via CDP. In other words: anything DevTools can do, CDP can do through code.

### What CDP can do

| Functional areas | Typical application scenarios |
|---------|----------------|
| Page navigation and control | Open URL, forward/backward, refresh |
| DOM operations | Get/modify page elements and monitor DOM changes |
| JavaScript execution | Run arbitrary JS code in the context of the page |
| Network interception | Capture requests/responses, modify request headers, simulate network conditions |
| Screenshots and recording | Page screenshots, element screenshots, and PDF generation |
| Performance tracking | Loading performance analysis, memory snapshot, FPS monitoring |
| Simulate device | Modify User-Agent, viewport size, geographical location |
| Security & Authentication | Handling SSL Certificates, Basic Authentication, Cookie Management |

### Communication model of CDP

```
┌─────────────────┐         WebSocket         ┌──────────────────┐
│  你的 Python 脚本 │ ◄──────────────────────► │  Chrome 浏览器    │
│                  │    ws://localhost:9222     │                  │
└─────────────────┘                            │  ┌────────────┐  │
                                               │  │  页面 Tab 1  │  │
                                               │  ├────────────┤  │
                                               │  │  页面 Tab 2  │  │
                                               │  ├────────────┤  │
                                               │  │  ...        │  │
                                               │  └────────────┘  │
                                               └──────────────────┘
```

Each command is sent in JSON format, and Chrome returns results in JSON. **Requests and responses correspond one-to-one through the `id` field**, which is the core convention of CDP communication.

---

## CDP vs Selenium vs Playwright: How to choose

Many beginners will ask: "Since there are Selenium and Playwright, why should I learn CDP?"

The answer is: **They are not on the same level**.

```
           ┌─────────────────────────┐
           │     Playwright / Puppeteer    │  ← 高层封装，API 最友好
           ├─────────────────────────┤
           │        Selenium WebDriver       │  ← 中间层，跨浏览器标准
           ├─────────────────────────┤
           │  Chrome DevTools Protocol (CDP) │  ← 底层协议，能力最强
           └─────────────────────────┘
```

Playwright and Puppeteer are essentially high-level encapsulation of CDP. They wrap CDP's original commands into concise APIs such as `page.goto()` and `page.screenshot()`.

### Comparison table

| Features | CDP (native) | Playwright | Selenium |
|------|-----------|-----------|----------|
| Learning Curve | Steep | Smooth | Smooth |
| Control granularity | **Finest** | Medium | Coarse |
| Network interception | Native support, full control | Support, well packaged | Limited (intermediate agent required) |
| Performance Tracking | Native Support | Supported | Not Supported |
| Cross-browser | ❌ Chrome/Chromium series | ✅ Chromium + Firefox + WebKit | ✅ Widest |
| Debug Transparency | **Highest** (can see every command) | Medium | Low |
| Dependencies | websocket-client only | Browser installation required | WebDriver required |

### When should you use CDP?

Scenarios using CDP directly (instead of high-level framework):

1. **Requires the most fine-grained control** — for example, to precisely control the timing of network requests, or to intercept WebSocket connections
2. **Bypass automated detection** — Selenium/Playwright features are easily identified by anti-crawling, and CDP is closer to real users
3. **Crawler/Reverse Engineering** — Need to intercept encrypted parameters and trace JS call stack
4. **Performance Analysis Automation** — Need to collect Lighthouse-level performance data
5. **Build your own tool framework** — If you want to do secondary development on Playwright, you need to understand the underlying mechanism
6. **Debug and Learn** — Want to deeply understand how the browser works

> **Tips**: If it is a regular E2E test or a simple crawler, use Playwright first. When fine control or anti-reverse climbing is required, then sink to CDP.

---

## Environment setup

### 1. Install Python dependencies

Only one library is needed:

```bash
pip install websocket-client
```

That’s right, you can communicate with Chrome using just `websocket-client`. There is no need to install ChromeDriver or download browser binaries.

### 2. Install/Confirm Chrome Browser

Any Chromium-based browser will do (Chrome, Edge, Brave, etc.). Make sure the version is not too old (Chrome 90+ will do).

View version: Enter `chrome://version/` in the address bar

### 3. Start Chrome’s remote debugging mode

This is the most critical step. After closing all Chrome windows, launch it from the command line:

```bash
# Windows
chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run

# Linux
google-chrome --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run
```

Parameter description:
- `--remote-debugging-port=9222`: Enable remote debugging, port 9222
- `--remote-allow-origins=*`: Allow WebSocket connections from any origin
- `--no-first-run`: skip first run boot
- `--no-default-browser-check`: Do not check the default browser

> **⚠️ Security Reminder**: `--remote-allow-origins=*` will allow any program that can access port 9222 to control your browser. **Only use within a trusted local network**, do not enable it on a production server.

### Verify connection

After starting Chrome, open `http://localhost:9222/json` in the browser and you should see a JSON response similar to this:

```json
[
  {
    "id": "1A2B3C4D",
    "title": "新标签页",
    "url": "chrome://new-tab-page/",
    "webSocketDebuggerUrl": "ws://localhost:9222/devtools/page/1A2B3C4D"
  }
]
```

This `webSocketDebuggerUrl` is the target we want to connect to next.

---

## First CDP program: Connect Chrome

### Basic framework

Below is a minimal example of a CDP connection. It does three things: Discover the page → Establish the WebSocket → Send the command.

```python
import json
import urllib.request
import websocket

# ========== 第一步：获取页面的 WebSocket URL ==========

CDP_HTTP = 'http://localhost:9222'

def get_page_ws(pattern=''):
    """获取第一个匹配 pattern 的页面的 WebSocket URL"""
    data = json.loads(
        urllib.request.urlopen(f'{CDP_HTTP}/json', timeout=5).read()
    )
    for page in data:
        if pattern in page.get('url', ''):
            return page['webSocketDebuggerUrl']
    # 如果没有匹配，默认取第一个页面
    return data[0]['webSocketDebuggerUrl'] if data else None

ws_url = get_page_ws()
print(f'Connecting to: {ws_url}')

# ========== 第二步：建立 WebSocket 连接 ==========

ws = websocket.create_connection(ws_url, timeout=30)

# ========== 第三步：封装 send/receive ==========

_request_id = 1

def send_cmd(ws, method, params=None):
    """发送 CDP 命令并等待返回结果"""
    global _request_id
    if params is None:
        params = {}
    _request_id += 1
    request = {'id': _request_id, 'method': method, 'params': params}
    ws.send(json.dumps(request))
    
    while True:
        response = json.loads(ws.recv())
        if response.get('id') == _request_id:
            return response.get('result', {})

# ========== 第四步：启用必要域 ==========

send_cmd(ws, 'Page.enable')       # 启用页面域
send_cmd(ws, 'Runtime.enable')    # 启用运行时域

# ========== 第五步：开始操控浏览器 ==========

# 导航到目标页面
result = send_cmd(ws, 'Page.navigate', {'url': 'https://www.example.com'})
print(f'Navigation started, frameId: {result.get("frameId")}')

# 在当前页面执行 JavaScript
result = send_cmd(ws, 'Runtime.evaluate', {
    'expression': 'document.title',
    'returnByValue': True
})
print(f'Page title: {result["result"]["value"]}')

# 关闭连接
ws.close()
```

Run this code and you will see the title of the console output page. Congratulations, you now control your browser directly through CDP!

### Code analysis

Although this code is simple, it contains the core pattern of CDP communication:

1. **Discovery phase**: Obtain a list of all pages through HTTP request `http://localhost:9222/json`
2. **Connection phase**: Use the `webSocketDebuggerUrl` of the page to establish a WebSocket connection
3. **Ready Phase**: Enable the required "Domain" through `Page.enable` / `Runtime.enable`
4. **Command phase**: Send commands (such as `Page.navigate`) and wait for the corresponding response

Each command is matched against requests and responses by an incrementing `id`. This is an important design of the CDP protocol: **Multiple commands can be sent simultaneously on the same WebSocket connection, and the ownership of the returned results is distinguished by id**.

---

## Core command actual combat

The key to mastering CDP is to understand its "Domain" system. CDP divides functions into dozens of domains, and each domain has a set of related commands:

| Domain name | Purpose | Common commands |
|------|------|---------|
| `Page` | Page control | `navigate`, `reload`, `captureScreenshot`, `printToPDF` |
| `Runtime` | JS runtime | `evaluate`, `runScript`, `getProperties` |
| `DOM` | DOM operations | `getDocument`, `querySelector`, `getOuterHTML` |
| `Network` | Network Control | `enable`, `setBlockedURLs`, `getResponseBody` |
| `Input` | Input simulation | `dispatchMouseEvent`, `dispatchKeyEvent`, `insertText` |
| `Console` | Console | `enable`, `clearMessages` |
| `Performance` | Performance | `enable`, `getMetrics`, `getTime` |
| `Overlay` | Visualization | `highlightNode`, `setShowFPSCounter` |

The most commonly used commands are introduced one by one below.

### 1. Screenshot of the page

The screenshot is CDP's "Hello World". It's more flexible than Selenium's screenshots - you can screenshot the entire page (including invisible parts) or individual elements.

```python
import base64

# 全页截图
result = send_cmd(ws, 'Page.captureScreenshot', {
    'format': 'png',
    'quality': 80,
    'fromSurface': True
})

with open('screenshot.png', 'wb') as f:
    f.write(base64.b64decode(result['data']))
print('Screenshot saved as screenshot.png')


# 指定区域的截图（裁剪）
# clip = x, y, width, height
result = send_cmd(ws, 'Page.captureScreenshot', {
    'format': 'png',
    'clip': {'x': 0, 'y': 0, 'width': 800, 'height': 600, 'scale': 1}
})
```

> **Tips**: `fromSurface: True` will intercept the complete rendering result (including GPU composition layer), set to `False` to only intercept the viewport content.

### 2. Execute JavaScript and get the return value

This is one of the most powerful capabilities of CDP - execute arbitrary JS in the context of the page and get the return value.

```python
# 获取页面信息
result = send_cmd(ws, 'Runtime.evaluate', {
    'expression': 'JSON.stringify({title: document.title, url: location.href, cookies: document.cookie})',
    'returnByValue': True
})
page_info = json.loads(result['result']['value'])
print(page_info)

# 获取元素的文本内容
result = send_cmd(ws, 'Runtime.evaluate', {
    'expression': 'document.querySelector("h1").innerText',
    'returnByValue': True
})
print(f'H1 text: {result["result"]["value"]}')

# 修改页面（可以执行任何 JS 操作）
send_cmd(ws, 'Runtime.evaluate', {
    'expression': 'document.title = "被 CDP 修改的标题"',
    'returnByValue': True
})
```

**Important Parameters**:
- `returnByValue`: When set to `true`, the return value will be serialized into JSON; when set to `false` (default), an object reference is returned, which can be further viewed with `Runtime.getProperties`
- `awaitPromise`: When set to `true`, it will wait for Promise resolution to complete before returning (applicable to asynchronous operations)

### 3. DOM operations

CDP's DOM operations are implemented through `DOM` fields, using "node IDs" to locate elements.

```python
# 获取文档根节点
result = send_cmd(ws, 'DOM.getDocument')
root_node_id = result['root']['nodeId']

# 通过选择器查找元素
result = send_cmd(ws, 'DOM.querySelector', {
    'nodeId': root_node_id,
    'selector': 'div.content'
})
content_node_id = result['nodeId']

# 获取元素的 HTML
result = send_cmd(ws, 'DOM.getOuterHTML', {
    'nodeId': content_node_id
})
print(f'Element HTML: {result["outerHTML"][:200]}...')

# 修改元素的属性
send_cmd(ws, 'DOM.setAttributeValue', {
    'nodeId': content_node_id,
    'name': 'style',
    'value': 'background-color: yellow;'
})
```

> **Features of CDP**: DOM operations are based on the **internal representation** of Chrome's Blink rendering engine, bypassing the page's JavaScript framework. This means that even if the page uses React/Vue, you can directly manipulate the final rendering result.

### 4. Network interception and monitoring

This is the most commonly used feature in crawlers and penetration testing. CDP can capture every request made by a page.

```python
# 启用网络域
send_cmd(ws, 'Network.enable')

# 设置请求拦截的回调
def on_request(event_data):
    """每次有网络请求时被调用"""
    request = event_data['params']['request']
    url = request['url']
    method = request['method']
    print(f'[{method}] {url}')
    
    # 可以修改请求头
    # 返回 {'continue': True} 表示继续请求

# 注册请求事件监听
# CDP 的事件通过 WebSocket 主动推送，需要单独处理
import threading

def event_listener(ws):
    """后台线程：持续接收 CDP 事件"""
    while True:
        try:
            msg = json.loads(ws.recv())
            if 'method' in msg:
                if msg['method'] == 'Network.requestWillBeSent':
                    on_request(msg)
                # 可以添加更多事件处理
        except Exception as e:
            print(f'Event listener error: {e}')
            break

# 启动事件监听线程
threading.Thread(target=event_listener, args=(ws,), daemon=True).start()

# 导航到页面
send_cmd(ws, 'Page.navigate', {'url': 'https://example.com'})

# ... 页面加载中，事件监听器会输出所有请求 ...
import time
time.sleep(5)  # 等待页面加载
```

**Advanced usage of Network domain**:

```python
# 拦截特定 URL 模式
send_cmd(ws, 'Network.setBlockedURLs', {
    'urls': ['*.jpg', '*.png', '*.gif']   # 拦截所有图片
})

# 模拟弱网环境
send_cmd(ws, 'Network.emulateNetworkConditions', {
    'offline': False,
    'latency': 300,          # 延迟 300ms
    'downloadThroughput': 500 * 1024,   # 下载 500 KB/s
    'uploadThroughput': 100 * 1024      # 上传 100 KB/s
})

# 获取响应体
# 首先在 Network.responseReceived 事件中拿到 requestId
# 然后：
result = send_cmd(ws, 'Network.getResponseBody', {
    'requestId': request_id
})
print(f'Response body: {result["body"][:500]}')
print(f'Base64 encoded: {result["base64Encoded"]}')
```

### 5. Mouse and keyboard simulation

CDP's `Input` field can simulate mouse clicks and keyboard input, which is key to implementing RPA (Robotic Process Automation).

```python
def click(ws, x, y, button='left'):
    """在指定坐标点击"""
    send_cmd(ws, 'Input.dispatchMouseEvent', {
        'type': 'mousePressed',
        'x': x, 'y': y,
        'button': button,
        'clickCount': 1
    })
    send_cmd(ws, 'Input.dispatchMouseEvent', {
        'type': 'mouseReleased',
        'x': x, 'y': y,
        'button': button,
        'clickCount': 1
    })

def type_text(ws, text):
    """输入文本"""
    send_cmd(ws, 'Input.insertText', {'text': text})

def press_enter(ws):
    """按 Enter 键"""
    send_cmd(ws, 'Input.dispatchKeyEvent', {
        'type': 'rawKeyDown',
        'windowsVirtualKeyCode': 13,
        'key': 'Enter'
    })
    send_cmd(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyUp',
        'windowsVirtualKeyCode': 13,
        'key': 'Enter'
    })

# 使用示例：自动填写表单
click(ws, 500, 300)          # 点击输入框
type_text(ws, 'hello@example.com')  # 输入邮箱
press_enter(ws)              # 提交
```

---

## Advanced skills

### 1. Bypass automated detection

Selenium and Playwright leave automation traces in the browser (e.g. `navigator.webdriver` property is `true`). CDP can be controlled from a lower level and is harder to detect.

```python
# 在页面加载前注入脚本，覆盖自动化特征
send_cmd(ws, 'Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        // 覆盖 webdriver 属性
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // 覆盖 chrome 对象
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // 覆盖权限查询
        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = (params) => (
            params.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(params)
        );
        
        // 覆盖 plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // 覆盖 languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en']
        });
    '''
})

# 以上脚本会在每个新页面上自动执行
# 然后再导航
send_cmd(ws, 'Page.navigate', {'url': 'https://bot.sannysoft.com/'})
```

> **Note**: Anti-crawling technology is constantly evolving, and what is shown here is only basic protection. In actual use, it needs to be adjusted according to the detection mechanism of the target website.

### 2. Handling new windows/new tabs

```python
# 监听 Target.targetCreated 事件
# 当新窗口打开时，自动获取它的 WebSocket URL

def on_target_created(event_data):
    target_info = event_data['params']['targetInfo']
    print(f'新标签页: {target_info["url"]}')
    # 可以通过 CDP_HTTP/json 获取新页面的 WebSocket URL

# 也可以用 --remote-debugging-pipe 参数使用管道而非 WebSocket
# 或者用 Target.attachToTarget 命令
```

### 3. Performance tracking

```python
# 开始性能追踪
send_cmd(ws, 'Performance.enable')

# 导航
send_cmd(ws, 'Page.navigate', {'url': 'https://example.com'})
time.sleep(3)

# 获取性能指标
result = send_cmd(ws, 'Performance.getMetrics')
metrics = {m['name']: m['value'] for m in result['metrics']}

print(f'DOMContentLoaded: {metrics.get("DomContentLoaded", "N/A")} ms')
print(f'首次绘制: {metrics.get("FirstPaint", "N/A")} ms')
print(f'JS 堆大小: {metrics.get("JSHeapUsedSize", "N/A")} bytes')
print(f'布局次数: {metrics.get("LayoutCount", "N/A")}')
print(f'重绘次数: {metrics.get("RecalcStyleCount", "N/A")}')
```

### 4. Generate PDF

```python
result = send_cmd(ws, 'Page.printToPDF', {
    'paperWidth': 8.27,       # A4 宽度（英寸）
    'paperHeight': 11.69,     # A4 高度
    'marginTop': 0.4,
    'marginBottom': 0.4,
    'marginLeft': 0.4,
    'marginRight': 0.4,
    'printBackground': True,
    'displayHeaderFooter': True,
    'headerTemplate': '<span style="font-size:10px;margin-left:10px;">标题</span>',
    'footerTemplate': '<span style="font-size:10px;margin-right:10px;">第 <span class="pageNumber"></span> 页 / 共 <span class="totalPages"></span> 页</span>'
})

with open('output.pdf', 'wb') as f:
    f.write(base64.b64decode(result['data']))
```

---

## Complete practice: automated screenshot tool

Below is a complete practical project - a command line screenshot tool that can specify the URL, output path and viewport size.

```python
#!/usr/bin/env python3
"""
CDP 命令行截图工具

用法：
    python cdp_screenshooter.py https://example.com -o screenshot.png -w 1920 -h 1080
"""
import json
import urllib.request
import websocket
import base64
import argparse
import time

# ========== 工具函数 ==========

def find_page_ws(cdp_url, pattern=''):
    data = json.loads(urllib.request.urlopen(f'{cdp_url}/json', timeout=5).read())
    for page in data:
        if pattern.lower() in page.get('url', '').lower():
            return page['webSocketDebuggerUrl']
    return data[0]['webSocketDebuggerUrl'] if data else None

class CDPConnection:
    """CDP 连接封装"""
    
    def __init__(self, ws_url):
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._id = 0
        # 启用核心域
        self._cmd('Page.enable')
        self._cmd('Runtime.enable')
    
    def _cmd(self, method, params=None):
        if params is None:
            params = {}
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == self._id:
                return r.get('result', {})
    
    def navigate(self, url):
        """导航到 URL 并等待页面加载完成"""
        self._cmd('Page.navigate', {'url': url})
        # 等待页面加载（生产环境应监听 Page.loadEventFired 事件）
        time.sleep(3)
    
    def screenshot(self, output_path, width=1920, height=1080):
        """截取页面截图"""
        # 设置视口大小
        self._cmd('Emulation.setDeviceMetricsOverride', {
            'width': width,
            'height': height,
            'deviceScaleFactor': 1,
            'mobile': False
        })
        time.sleep(0.5)
        
        # 截图
        result = self._cmd('Page.captureScreenshot', {
            'format': 'png',
            'fromSurface': True
        })
        
        with open(output_path, 'wb') as f:
            f.write(base64.b64decode(result['data']))
        print(f'✅ 截图已保存: {output_path} ({width}x{height})')
    
    def close(self):
        self.ws.close()


def main():
    parser = argparse.ArgumentParser(description='CDP 命令行截图工具')
    parser.add_argument('url', help='目标 URL')
    parser.add_argument('-o', '--output', default='screenshot.png', help='输出文件路径')
    parser.add_argument('-w', '--width', type=int, default=1920, help='视口宽度')
    parser.add_argument('-H', '--height', type=int, default=1080, help='视口高度')
    parser.add_argument('--cdp', default='http://localhost:9222', help='CDP HTTP 地址')
    parser.add_argument('--pattern', default='', help='匹配特定标签页')
    args = parser.parse_args()
    
    print(f'🔍 连接 Chrome: {args.cdp}')
    ws_url = find_page_ws(args.cdp, args.pattern)
    if not ws_url:
        print('❌ 未找到可用的页面')
        return
    
    print(f'🔗 WebSocket: {ws_url[:60]}...')
    cdp = CDPConnection(ws_url)
    
    print(f'🌐 导航到: {args.url}')
    cdp.navigate(args.url)
    
    cdp.screenshot(args.output, args.width, args.height)
    cdp.close()
    print('🎉 完成！')


if __name__ == '__main__':
    main()
```

How to use:

```bash
# 基础用法
python cdp_screenshooter.py https://www.example.com

# 指定输出和尺寸
python cdp_screenshooter.py https://www.baidu.com -o baidu.png -w 1920 -H 1080

# 截取特定标签页
python cdp_screenshooter.py https://example.com --pattern "login"
```

---

## Pitfall records and best practices

### FAQ

#### ❌ Connection Refused

```
websocket._exceptions.WebSocketBadStatusException: Handshake status 500
```

**Cause**: Chrome was not started with the `--remote-debugging-port` parameter.

**Solution**: Make sure all Chrome processes are closed and re-launch Chrome from the command line.

#### ❌ WebSocket connection timeout

```
socket.timeout: timed out
```

**Cause**: The port is blocked by the firewall, or multiple Chrome instances are started, causing port conflicts.

**Solution**:
- Check whether `http://localhost:9222/json` can be accessed normally
- Check whether the firewall has allowed port 9222
- If there are multiple instances of Chrome, close all the old ones and try again

#### ❌ Page not found (get_page_ws returns None)

**Cause**: `http://localhost:9222/json` returns an empty list and no tabs have been opened.

**Fix**: Make sure you have at least one tab open in Chrome (instead of just a "New Tab").

#### ❌ `Input.insertText` does not take effect in xterm.js terminal

**Cause**: Canvas-rendered terminals such as xterm.js do not trigger standard DOM input events.

**Solution**: Use JavaScript to directly operate the textarea:
```python
result = send_cmd(ws, 'Runtime.evaluate', {
    'expression': '''
        (() => {
            const ta = document.querySelector('.xterm-helper-textarea');
            if (!ta) return false;
            ta.value = '要输入的命令';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
            return true;
        })()
    ''',
    'returnByValue': True
})
```

### Summary of best practices

1. **Always `enable` before using**: Each field must call the corresponding `enable` method before using it.
2. **Independent threads for event monitoring**: CDP events are actively pushed through WebSocket and require a separate thread for processing.
3. **Wait reasonably for the page to load**: `Page.navigate` will not wait for the page to be fully loaded. It is recommended to listen to the `Page.loadEventFired` event.
4. **Pay attention to memory leaks**: Each time `Runtime.evaluate` creates an object reference, it will occupy memory. Call `Runtime.releaseObject` after it is used up.
5. **Use independent user data directory**: Use `--user-data-dir=/path/to/profile` to specify an independent browser configuration directory to avoid conflicts with daily browsers
6. **Exception handling**: The WebSocket connection may be disconnected due to network problems. It is recommended to add a reconnection mechanism.
7. **Logging**: The data returned by CDP may be large (especially screenshots and response bodies), so be careful to control log output.

---

## Summary and next steps

Through this article, you have mastered the core concepts and practical skills of CDP:

- ✅ What is CDP and its communication model
- ✅ Positioning differences between CDP and Selenium/Playwright
- ✅ How to set up the environment and connect Chrome
- ✅ Use of 5 core domains: Page, Runtime, DOM, Network, Input
- ✅ Advanced skills: anti-detection, new tab processing, performance tracking
- ✅ Complete project: Command line screenshot tool

### Directions you can try next

| Direction | Suitable scene | Reference resources |
|------|---------|---------|
| **Crawler** | Intercept XHR requests of SPA pages and bypass anti-crawling | Check out this site's "Crawler Combat" series |
| **RPA Automation** | Repetitive web page operations, cross-system data migration | Check out this site's "RPA Practice" series |
| **Performance Test** | Core Web Vitals collection, page loading analysis | View the "Performance Optimization" series of this site |
| **Security Testing** | XSS detection, CSRF verification, information leakage detection | Playwright + CDP combined use |
| **Tool Development** | Build your own headless browser management platform | Follow the "Framework Building" series of this site |

> 💡 **Tips**: If you want to quickly get started with production-level applications, it is recommended to master the CDP basics in this article first, and then learn [Playwright](https://playwright.dev/) or [Puppeteer](https://pptr.dev/). After understanding the underlying protocol, you will be more comfortable using the high-level framework.

---

*This article is the first in the "CDP Automation Guide" series. In the follow-up, we will delve into topics such as CDP crawler practice, RPA process automation, and the underlying principles of Playwright, so stay tuned. *

---

**Find it useful? Share with more people: **

<!-- Share button area (to be added) -->

**Have any questions or suggestions? ** Welcome to leave a message in the comment area for discussion, or submit a [GitHub Issue](https://github.com/your-repo/issues).