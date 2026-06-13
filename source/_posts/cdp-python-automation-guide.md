---
title: Chrome DevTools Protocol (CDP) 完全指南：用 Python 控制浏览器的终极方案
date: 2026-06-03 14:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 浏览器自动化
  - Selenium
  - Playwright
categories:
  - CDP 基础
  - Python 实战
description: Chrome DevTools Protocol（CDP）是什么？为什么说它是比 Selenium 更强大的浏览器自动化方案？本文将带你从零开始，用 Python 通过 WebSocket 直接控制 Chrome 浏览器，实现导航、截图、网络拦截等高级操作，并附完整的实战代码。
---

> **一句话总结**：Chrome DevTools Protocol（CDP）是 Chrome 内置的"远程控制 API"，让你可以用代码直接操控浏览器的一切 — 从打开网页到拦截网络请求，从截取截图到追踪性能。它正是 Puppeteer、Playwright 这些工具的底层基石。

---

## 目录

1. [CDP 是什么](#cdp-是什么)
2. [CDP vs Selenium vs Playwright：该怎么选](#cdp-vs-selenium-vs-playwright该怎么选)
3. [环境搭建](#环境搭建)
4. [第一个 CDP 程序：连接 Chrome](#第一个-cdp-程序连接-chrome)
5. [核心命令实战](#核心命令实战)
6. [进阶技巧](#进阶技巧)
7. [完整实战：自动化截图工具](#完整实战自动化截图工具)
8. [踩坑记录与最佳实践](#踩坑记录与最佳实践)
9. [总结与下一步](#总结与下一步)

---

## CDP 是什么

Chrome DevTools Protocol（简称 CDP）是一个基于 **WebSocket** 的通信协议。本质上，它就是你在 Chrome 开发者工具（F12）中看到的所有功能的"后台 API"。

每当你打开 DevTools 的 Elements、Console、Network 面板时，Chrome 就在内部通过 CDP 和 DevTools 前端通信。换句话说：**DevTools 能做的任何事情，CDP 都能通过代码做到**。

### CDP 能做什么

| 功能领域 | 典型应用场景 |
|---------|------------|
| 页面导航与控制 | 打开 URL、前进/后退、刷新 |
| DOM 操作 | 获取/修改页面元素、监听 DOM 变化 |
| JavaScript 执行 | 在页面上下文中运行任意 JS 代码 |
| 网络拦截 | 捕获请求/响应、修改请求头、模拟网络条件 |
| 截图与录制 | 页面截图、元素截图、生成 PDF |
| 性能追踪 | 加载性能分析、内存快照、FPS 监控 |
| 模拟设备 | 修改 User-Agent、视口大小、地理位置 |
| 安全与认证 | 处理 SSL 证书、基本认证、Cookie 管理 |

### CDP 的通信模型

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

每个命令以 JSON 格式发送，Chrome 也同样以 JSON 返回结果。**请求和响应通过 `id` 字段一一对应**，这是 CDP 通信的核心约定。

---

## CDP vs Selenium vs Playwright：该怎么选

很多初学者会问："既然有 Selenium 和 Playwright，为什么还要学 CDP？"

答案是：**它们不在同一个层次上**。

```
           ┌─────────────────────────┐
           │     Playwright / Puppeteer    │  ← 高层封装，API 最友好
           ├─────────────────────────┤
           │        Selenium WebDriver       │  ← 中间层，跨浏览器标准
           ├─────────────────────────┤
           │  Chrome DevTools Protocol (CDP) │  ← 底层协议，能力最强
           └─────────────────────────┘
```

Playwright 和 Puppeteer 本质上就是对 CDP 的高层封装。它们把 CDP 的原始命令包装成 `page.goto()`、`page.screenshot()` 这样简洁的 API。

### 对比表格

| 特性 | CDP（原生） | Playwright | Selenium |
|------|-----------|-----------|----------|
| 学习曲线 | 陡峭 | 平缓 | 平缓 |
| 控制粒度 | **最细** | 中等 | 粗 |
| 网络拦截 | 原生支持，全量控制 | 支持，封装良好 | 有限（需中间代理） |
| 性能追踪 | 原生支持 | 支持 | 不支持 |
| 跨浏览器 | ❌ Chrome/Chromium 系 | ✅ Chromium + Firefox + WebKit | ✅ 最广 |
| 调试透明度 | **最高**（能看到每个命令） | 中等 | 低 |
| 依赖 | 仅 websockets | 需要安装浏览器 | 需要 WebDriver |

### 什么时候该用 CDP？

直接用 CDP（而非高层框架）的场景：

1. **需要最细粒度的控制** — 比如要精确控制网络请求的 timing，或拦截 WebSocket 连接
2. **绕过自动化检测** — Selenium/Playwright 的特征容易被反爬识别，CDP 更接近真实用户
3. **爬虫/逆向工程** — 需要拦截加密参数、追踪 JS 调用栈
4. **性能分析自动化** — 需要采集 Lighthouse 级别的性能数据
5. **构建自己的工具框架** — 你想在 Playwright 之上做二次开发，需要理解底层机制
6. **调试和学习** — 想深入理解浏览器工作原理

> **小建议**：如果是常规的 E2E 测试或简单爬虫，优先用 Playwright。需要精细控制或反反爬时，再下沉到 CDP。

---

## 环境搭建

### 1. 安装 Python 依赖

只需要一个库：

```bash
pip install websockets
```

没错，只靠 `websockets` 就能和 Chrome 通信。不需要安装 ChromeDriver、不需要下载浏览器二进制文件。

### 2. 安装 / 确认 Chrome 浏览器

任何基于 Chromium 的浏览器都可以（Chrome、Edge、Brave 等）。确保版本不要太旧（Chrome 90+ 即可）。

查看版本：地址栏输入 `chrome://version/`

### 3. 启动 Chrome 的远程调试模式

这是最关键的一步。关闭所有 Chrome 窗口后，用命令行启动：

```bash
# Windows
chrome.exe --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run --no-default-browser-check

# macOS
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run

# Linux
google-chrome --remote-debugging-port=9222 --remote-allow-origins=* --no-first-run
```

参数说明：
- `--remote-debugging-port=9222`：开启远程调试，端口 9222
- `--remote-allow-origins=*`：允许来自任何来源的 WebSocket 连接
- `--no-first-run`：跳过首次运行引导
- `--no-default-browser-check`：不检查默认浏览器

> **⚠️ 安全提醒**：`--remote-allow-origins=*` 会让任何能访问 9222 端口的程序控制你的浏览器。**仅在受信任的本地网络中使用**，不要在生产环境的服务器上开启。

### 验证连接

启动 Chrome 后，在浏览器中打开 `http://localhost:9222/json`，应该能看到类似这样的 JSON 响应：

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

这个 `webSocketDebuggerUrl` 就是我们接下来要连接的目标。

---

## 第一个 CDP 程序：连接 Chrome

### 基础框架

下面是一个最精简的 CDP 连接示例。它完成了三件事：发现页面 → 建立 WebSocket → 发送命令。

```python
import asyncio
import json
import urllib.request
import websockets

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

CMD_ID = [0]

async def cdp(ws, method, params=None):
    """发送 CDP 命令并等待返回结果"""
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    request = {'id': cmd_id, 'method': method, 'params': params or {}}
    await ws.send(json.dumps(request))
    async for msg in ws:
        response = json.loads(msg)
        if response.get('id') == cmd_id:
            return response.get('result', {})


async def main():
    ws_url = get_page_ws()
    print(f'Connecting to: {ws_url}')

    async with websockets.connect(ws_url) as ws:
        # 启用必要域
        await cdp(ws, 'Page.enable')
        await cdp(ws, 'Runtime.enable')

        # 导航到目标页面
        result = await cdp(ws, 'Page.navigate', {'url': 'https://www.example.com'})
        print(f'Navigation started, frameId: {result.get("frameId")}')

        # 在当前页面执行 JavaScript
        result = await cdp(ws, 'Runtime.evaluate', {
            'expression': 'document.title',
            'returnByValue': True
        })
        print(f'Page title: {result["result"]["value"]}')

asyncio.run(main())
```

运行这段代码，你会看到控制台输出页面的标题。恭喜，你已经通过 CDP 直接控制浏览器了！

### 代码解析

这段代码虽然简单，但包含了 CDP 通信的核心模式：

1. **发现阶段**：通过 HTTP 请求 `http://localhost:9222/json` 获取所有页面列表
2. **连接阶段**：使用页面的 `webSocketDebuggerUrl` 建立 WebSocket 连接
3. **就绪阶段**：通过 `Page.enable` / `Runtime.enable` 启用需要的"域"（Domain）
4. **命令阶段**：发送命令（如 `Page.navigate`）并等待对应的响应

每个命令通过递增的 `id` 来匹配请求和响应。这是 CDP 协议的重要设计：**同一个 WebSocket 连接上可以同时发送多个命令，通过 id 来区分返回结果归属**。

---

## 核心命令实战

掌握 CDP 的关键是理解它的"域"（Domain）体系。CDP 将功能划分为几十个域，每个域下有一组相关命令：

| 域名 | 用途 | 常用命令 |
|------|------|---------|
| `Page` | 页面控制 | `navigate`, `reload`, `captureScreenshot`, `printToPDF` |
| `Runtime` | JS 运行时 | `evaluate`, `runScript`, `getProperties` |
| `DOM` | DOM 操作 | `getDocument`, `querySelector`, `getOuterHTML` |
| `Network` | 网络控制 | `enable`, `setBlockedURLs`, `getResponseBody` |
| `Input` | 输入模拟 | `dispatchMouseEvent`, `dispatchKeyEvent`, `insertText` |
| `Console` | 控制台 | `enable`, `clearMessages` |
| `Performance` | 性能 | `enable`, `getMetrics`, `getTime` |
| `Overlay` | 可视化 | `highlightNode`, `setShowFPSCounter` |

下面逐一介绍最常用的命令。

### 1. 页面截图

截图是 CDP 的"Hello World"。它比 Selenium 的截图更灵活——你可以截取**整个页面**（包括不可见部分）或**单个元素**。

```python
import base64

# 全页截图
result = await cdp(ws, 'Page.captureScreenshot', {
    'format': 'png'
})

with open('screenshot.png', 'wb') as f:
    f.write(base64.b64decode(result['data']))
print('Screenshot saved as screenshot.png')


# 指定区域的截图（裁剪）
# clip = x, y, width, height
result = await cdp(ws, 'Page.captureScreenshot', {
    'format': 'png',
    'clip': {'x': 0, 'y': 0, 'width': 800, 'height': 600, 'scale': 1}
})
```

> **小技巧**：`fromSurface: True` 会截取完整的渲染结果（含 GPU 合成层），设为 `False` 则只截取视口内容。

### 2. 执行 JavaScript 并获取返回值

这是 CDP 最强大的能力之一——在页面上下文中执行任意 JS，并获取返回值。

```python
# 获取页面信息
result = await cdp(ws, 'Runtime.evaluate', {
    'expression': 'JSON.stringify({title: document.title, url: location.href, cookies: document.cookie})',
    'returnByValue': True
})
page_info = json.loads(result['result']['value'])
print(page_info)

# 获取元素的文本内容
result = await cdp(ws, 'Runtime.evaluate', {
    'expression': 'document.querySelector("h1").innerText',
    'returnByValue': True
})
print(f'H1 text: {result["result"]["value"]}')

# 修改页面（可以执行任何 JS 操作）
await cdp(ws, 'Runtime.evaluate', {
    'expression': 'document.title = "被 CDP 修改的标题"',
    'returnByValue': True
})
```

**重要参数**：
- `returnByValue`：设为 `true` 时，返回值会序列化为 JSON；设为 `false`（默认）时，返回一个对象引用，可以用 `Runtime.getProperties` 进一步查看
- `awaitPromise`：设为 `true` 时，会等待 Promise 解析完成再返回（适用于异步操作）

### 3. DOM 操作

CDP 的 DOM 操作通过 `DOM` 域实现，使用"节点 ID"来定位元素。

```python
# 获取文档根节点
result = await cdp(ws, 'DOM.getDocument')
root_node_id = result['root']['nodeId']

# 通过选择器查找元素
result = await cdp(ws, 'DOM.querySelector', {
    'nodeId': root_node_id,
    'selector': 'div.content'
})
content_node_id = result['nodeId']

# 获取元素的 HTML
result = await cdp(ws, 'DOM.getOuterHTML', {
    'nodeId': content_node_id
})
print(f'Element HTML: {result["outerHTML"][:200]}...')

# 修改元素的属性
await cdp(ws, 'DOM.setAttributeValue', {
    'nodeId': content_node_id,
    'name': 'style',
    'value': 'background-color: yellow;'
})
```

> **CDP 的特性**：DOM 操作是基于 Chrome 的 Blink 渲染引擎的**内部表示**，绕过了页面的 JavaScript 框架。这意味着即使页面用了 React/Vue，你也可以直接操作最终的渲染结果。

### 4. 网络拦截与监控

这是爬虫和渗透测试中最常用的功能。CDP 可以捕获页面发出的每一个请求。

```python
# 启用网络域
await cdp(ws, 'Network.enable')

# 存储事件回调
event_handlers = {}

def on(event_name):
    """装饰器：注册 CDP 事件处理器"""
    def decorator(fn):
        event_handlers[event_name] = fn
        return fn
    return decorator

@on('Network.requestWillBeSent')
async def on_request(event_data):
    """每次有网络请求时被调用"""
    request = event_data['params']['request']
    url = request['url']
    method = request['method']
    print(f'[{method}] {url}')

async def event_listener(ws):
    """后台任务：持续接收 CDP 事件"""
    async for msg in ws:
        try:
            data = json.loads(msg)
            if 'method' in data:
                handler = event_handlers.get(data['method'])
                if handler:
                    await handler(data)
        except Exception as e:
            print(f'Event listener error: {e}')

# 启动事件监听任务
listener_task = asyncio.create_task(event_listener(ws))

# 导航到页面
await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})

# ... 页面加载中，事件监听器会输出所有请求 ...
await asyncio.sleep(5)  # 等待页面加载
```

**Network 域的高级用法**：

```python
# 拦截特定 URL 模式
await cdp(ws, 'Network.setBlockedURLs', {
    'urls': ['*.jpg', '*.png', '*.gif']   # 拦截所有图片
})

# 模拟弱网环境
await cdp(ws, 'Network.emulateNetworkConditions', {
    'offline': False,
    'latency': 300,          # 延迟 300ms
    'downloadThroughput': 500 * 1024,   # 下载 500 KB/s
    'uploadThroughput': 100 * 1024      # 上传 100 KB/s
})

# 获取响应体
# 首先在 Network.responseReceived 事件中拿到 requestId
# 然后：
result = await cdp(ws, 'Network.getResponseBody', {
    'requestId': request_id
})
print(f'Response body: {result["body"][:500]}')
print(f'Base64 encoded: {result["base64Encoded"]}')
```

### 5. 鼠标与键盘模拟

CDP 的 `Input` 域可以模拟鼠标点击和键盘输入，这是实现 RPA（机器人流程自动化）的关键。

```python
async def click(ws, x, y, button='left'):
    """在指定坐标点击"""
    await cdp(ws, 'Input.dispatchMouseEvent', {
        'type': 'mousePressed',
        'x': x, 'y': y,
        'button': button,
        'clickCount': 1
    })
    await cdp(ws, 'Input.dispatchMouseEvent', {
        'type': 'mouseReleased',
        'x': x, 'y': y,
        'button': button,
        'clickCount': 1
    })

async def type_text(ws, text):
    """输入文本"""
    await cdp(ws, 'Input.insertText', {'text': text})

async def press_enter(ws):
    """按 Enter 键"""
    await cdp(ws, 'Input.dispatchKeyEvent', {
        'type': 'rawKeyDown',
        'windowsVirtualKeyCode': 13,
        'key': 'Enter'
    })
    await cdp(ws, 'Input.dispatchKeyEvent', {
        'type': 'keyUp',
        'windowsVirtualKeyCode': 13,
        'key': 'Enter'
    })

# 使用示例：自动填写表单
await click(ws, 500, 300)          # 点击输入框
await type_text(ws, 'hello@example.com')  # 输入邮箱
await press_enter(ws)              # 提交
```

---

## 进阶技巧

### 1. 绕过自动化检测

Selenium 和 Playwright 会在浏览器中留下自动化痕迹（如 `navigator.webdriver` 属性为 `true`）。CDP 可以从更底层控制，更难被检测。

```python
# 在页面加载前注入脚本，覆盖自动化特征
await cdp(ws, 'Page.addScriptToEvaluateOnNewDocument', {
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
await cdp(ws, 'Page.navigate', {'url': 'https://bot.sannysoft.com/'})
```

> **注意**：反爬技术不断进化，这里展示的只是基础防护。实际使用时需要根据目标网站的检测机制针对性调整。

### 2. 处理新窗口 / 新标签页

```python
# 监听 Target.targetCreated 事件
# 当新窗口打开时，自动获取它的 WebSocket URL

@on('Target.targetCreated')
async def on_target_created(event_data):
    target_info = event_data['params']['targetInfo']
    print(f'新标签页: {target_info["url"]}')
    # 可以通过 CDP_HTTP/json 获取新页面的 WebSocket URL
    # 或用 Target.attachToTarget 命令附加到新页面

# 启用 Target 域以接收事件
await cdp(ws, 'Target.setAutoAttach', {
    'autoAttach': True,
    'flatten': True,
    'waitForDebuggerOnStart': False
})
```

### 3. 性能追踪

```python
# 开始性能追踪
await cdp(ws, 'Performance.enable')

# 导航
await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
await asyncio.sleep(3)

# 获取性能指标
result = await cdp(ws, 'Performance.getMetrics')
metrics = {m['name']: m['value'] for m in result['metrics']}

print(f'DOMContentLoaded: {metrics.get("DomContentLoaded", "N/A")} ms')
print(f'首次绘制: {metrics.get("FirstPaint", "N/A")} ms')
print(f'JS 堆大小: {metrics.get("JSHeapUsedSize", "N/A")} bytes')
print(f'布局次数: {metrics.get("LayoutCount", "N/A")}')
print(f'重绘次数: {metrics.get("RecalcStyleCount", "N/A")}')
```

### 4. 生成 PDF

```python
result = await cdp(ws, 'Page.printToPDF', {
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

## 完整实战：自动化截图工具

下面是一个完整的实战项目——一个命令行截图工具，可以指定 URL、输出路径和视口大小。

```python
#!/usr/bin/env python3
"""
CDP 命令行截图工具

用法：
    python cdp_screenshooter.py https://example.com -o screenshot.png -w 1920 -h 1080
"""
import asyncio
import json
import urllib.request
import websockets
import base64
import argparse

# ========== 工具函数 ==========

def find_page_ws(cdp_url, pattern=''):
    data = json.loads(urllib.request.urlopen(f'{cdp_url}/json', timeout=5).read())
    for page in data:
        if pattern.lower() in page.get('url', '').lower():
            return page['webSocketDebuggerUrl']
    return data[0]['webSocketDebuggerUrl'] if data else None

CMD_ID = [0]

async def cdp(ws, method, params=None):
    """发送 CDP 命令并等待返回结果"""
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    request = {'id': cmd_id, 'method': method, 'params': params or {}}
    await ws.send(json.dumps(request))
    async for msg in ws:
        response = json.loads(msg)
        if response.get('id') == cmd_id:
            return response.get('result', {})

class CDPConnection:
    """CDP 连接封装（异步版）"""
    
    def __init__(self, ws_url):
        self.ws = None
        self._ws_url = ws_url
    
    async def __aenter__(self):
        self.ws = await websockets.connect(self._ws_url, max_size=2**24)
        await self.cdp('Page.enable')
        await self.cdp('Runtime.enable')
        return self
    
    async def __aexit__(self, *args):
        await self.ws.close()
    
    async def cdp(self, method, params=None):
        return await cdp(self.ws, method, params)
    
    async def navigate(self, url):
        """导航到 URL 并等待页面加载完成"""
        await self.cdp('Page.navigate', {'url': url})
        # 等待页面加载（生产环境应监听 Page.loadEventFired 事件）
        await asyncio.sleep(3)
    
    async def screenshot(self, output_path, width=1920, height=1080):
        """截取页面截图"""
        # 设置视口大小
        await self.cdp('Emulation.setDeviceMetricsOverride', {
            'width': width,
            'height': height,
            'deviceScaleFactor': 1,
            'mobile': False
        })
        await asyncio.sleep(0.5)
        
        # 截图
        result = await self.cdp('Page.captureScreenshot', {
            'format': 'png'
        })
        
        with open(output_path, 'wb') as f:
            f.write(base64.b64decode(result['data']))
        print(f'✅ 截图已保存: {output_path} ({width}x{height})')


async def main():
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
    
    async with CDPConnection(ws_url) as cdp_conn:
        print(f'🌐 导航到: {args.url}')
        await cdp_conn.navigate(args.url)
        await cdp_conn.screenshot(args.output, args.width, args.height)
    
    print('🎉 完成！')


if __name__ == '__main__':
    asyncio.run(main())
```

使用方法：

```bash
# 基础用法
python cdp_screenshooter.py https://www.example.com

# 指定输出和尺寸
python cdp_screenshooter.py https://www.baidu.com -o baidu.png -w 1920 -H 1080

# 截取特定标签页
python cdp_screenshooter.py https://example.com --pattern "login"
```

---

## 踩坑记录与最佳实践

### 常见问题

#### ❌ 连接被拒绝（Connection Refused）

```
websockets.exceptions.InvalidStatusCode: server rejected WebSocket connection: HTTP 500
```

**原因**：Chrome 没有以 `--remote-debugging-port` 参数启动。

**解决**：确保所有 Chrome 进程已关闭，重新用命令行启动 Chrome。

#### ❌ WebSocket 连接超时

```
socket.timeout: timed out
```

**原因**：端口被防火墙拦截，或者启动了多个 Chrome 实例导致端口冲突。

**解决**：
- 检查 `http://localhost:9222/json` 是否能正常访问
- 检查防火墙是否放行了 9222 端口
- 如果有多个 Chrome 实例，把旧的全部关闭再重试

#### ❌ 找不到页面（get_page_ws 返回 None）

**原因**：`http://localhost:9222/json` 返回空列表，还没有打开任何标签页。

**解决**：确保 Chrome 中至少有一个标签页打开（而不是只有一个"新标签页"）。

#### ❌ `Input.insertText` 在 xterm.js 终端中不生效

**原因**：xterm.js 等基于 Canvas 渲染的终端不会触发标准的 DOM 输入事件。

**解决**：改用 JavaScript 直接操作 textarea：
```python
result = await cdp(ws, 'Runtime.evaluate', {
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

### 最佳实践总结

1. **始终先 `enable` 再使用**：每个域在使用前必须先调用对应的 `enable` 方法
2. **事件监听用异步任务**：CDP 事件通过 WebSocket 主动推送，使用 `asyncio.create_task()` 处理
3. **合理等待页面加载**：`Page.navigate` 不会等待页面完全加载，建议监听 `Page.loadEventFired` 事件
4. **注意内存泄漏**：每次 `Runtime.evaluate` 创建的对象引用会占用内存，用完后调用 `Runtime.releaseObject`
5. **使用独立用户数据目录**：用 `--user-data-dir=/path/to/profile` 指定独立的浏览器配置目录，避免与日常浏览器冲突
6. **异常处理**：WebSocket 连接可能因网络问题断开，建议加入重连机制
7. **日志记录**：CDP 返回的数据可能很大（尤其是截图和响应体），注意控制日志输出

---

## 总结与下一步

通过本文，你已经掌握了 CDP 的核心概念和实战技能：

- ✅ CDP 是什么以及它的通信模型
- ✅ CDP 与 Selenium/Playwright 的定位差异
- ✅ 如何搭建环境并连接 Chrome
- ✅ 5 个核心域的使用：Page、Runtime、DOM、Network、Input
- ✅ 进阶技巧：反检测、新标签页处理、性能追踪
- ✅ 完整项目：命令行截图工具

### 接下来可以尝试的方向

| 方向 | 适合场景 | 参考资源 |
|------|---------|---------|
| **爬虫** | 拦截 SPA 页面的 XHR 请求、绕过反爬 | 查看本站的"爬虫实战"系列 |
| **RPA 自动化** | 重复性网页操作、跨系统数据迁移 | 查看本站的"RPA 实战"系列 |
| **性能测试** | Core Web Vitals 采集、页面加载分析 | 查看本站的"性能优化"系列 |
| **安全测试** | XSS 探测、CSRF 验证、信息泄露检测 | Playwright + CDP 结合使用 |
| **工具开发** | 构建自己的无头浏览器管理平台 | 关注本站的"框架搭建"系列 |

> 💡 **小提示**：如果你想快速上手生产级应用，建议先掌握本文的 CDP 基础，然后去学习 [Playwright](https://playwright.dev/) 或 [Puppeteer](https://pptr.dev/)。理解了底层协议后，使用高层框架会更加得心应手。

---

*本文是「CDP 自动化指南」系列的开篇之作。后续将深入 CDP 爬虫实战、RPA 流程自动化、Playwright 底层原理等话题，敬请关注。*



---

**觉得有用？分享给更多人：**

<!-- 分享按钮区域（待添加） -->

**遇到问题或有建议？** 欢迎在评论区留言讨论，或提交 [GitHub Issue](https://github.com/your-repo/issues)。

*下一篇预告：CDP 网络拦截与请求篡改实战：Python 控制 Chrome 抓包改包完全指南。*