---
title: CDP vs Playwright：浏览器自动化方案选型指南
date: 2026-06-05 23:45:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Playwright
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 深入对比 CDP 直连与 Playwright 封装两种浏览器自动化方案，帮助你在不同场景下做出正确的技术选型。
---

> **一句话总结**：CDP 是浏览器自动化的"汇编语言"——最强大也最繁琐；Playwright 是"高级编程语言"——易用但牺牲了部分控制权。选哪个取决于你想要多少控制力，愿意承受多少复杂度。

---

## 目录

1. [两种方案的架构差异](#两种方案的架构差异)
2. [代码对比：相同的任务，不同的写法](#代码对比相同的任务不同的写法)
3. [何时选择 CDP](#何时选择-cdp)
4. [何时选择 Playwright](#何时选择-playwright)
5. [性能对比：开销分析](#性能对比开销分析)
6. [混合方案：Playwright + CDPSession](#混合方案playwright--cdpsession)
7. [能力对比表](#能力对比表)
8. [总结与选型决策](#总结与选型决策)

---

## 两种方案的架构差异

### CDP 直连方案

CDP（Chrome DevTools Protocol）是 Chrome 浏览器原生暴露的调试协议。直连方案意味着你的代码直接通过 WebSocket 与浏览器通信，中间没有任何封装层。

```
┌─────────────────────────────────────────────┐
│  你的 Python 脚本                             │
│  ┌─────────────────────────────────────────┐ │
│  │  asyncio 事件循环                        │ │
│  │  ↓                                      │ │
│  │  cdp() 函数 → JSON 命令 → WebSocket      │ │
│  └─────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────┘
                       │ WebSocket (JSON)
                       ▼
┌─────────────────────────────────────────────┐
│  Chrome 浏览器                               │
│  ┌─────────────────────────────────────────┐ │
│  │  调试层 → 协议解析 → 命令分发 → 各模块     │ │
│  └─────────────────────────────────────────┘ │
└─────────────────────────────────────────────┘
```

这是本文系列一致使用的 CDP 帮助函数：

```python
CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]:
            return data.get("result", {})
```

其核心流程：

1. 通过 `http://localhost:9222/json` 获取目标页面的 WebSocket URL
2. 使用 `websockets` 库建立 WebSocket 连接
3. 手动构造 JSON 格式的命令，通过 `ws.send()` 发送
4. 通过 `id` 字段匹配响应，拿到结果

**关键特征**：一切都需要你亲手操办——连接管理、命令封装、响应匹配、错误处理、生命周期管理。

### Playwright 封装方案

Playwright 在底层也使用 CDP（对 Chromium 而言），但它加了三层抽象：

```
┌─────────────────────────────────────────────┐
│  你的 Python 脚本                             │
│  ┌─────────────────────────────────────────┐ │
│  │  page.goto()  /  page.screenshot()      │ │
│  │  page.wait_for_selector()               │ │
│  └──────────────┬──────────────────────────┘ │
└─────────────────┼────────────────────────────┘
                  │
┌─────────────────▼────────────────────────────┐
│  Playwright API 层                            │
│  ┌─────────────────────────────────────────┐ │
│  │  Browser → BrowserContext → Page         │ │
│  │  自动元素等待、智能重试、事件管理         │ │
│  └─────────────────────────────────────────┘ │
└─────────────────┬────────────────────────────┘
                  │ CDP (内部使用)
┌─────────────────▼────────────────────────────┐
│  Chrome 浏览器                               │
└───────────────────────────────────────────────┘
```

Playwright 帮开发者处理了大量底层细节：

- **自动等待**：所有操作自动等待元素可达，无需手动 `sleep`
- **状态管理**：自动管理浏览器实例、上下文、页面的生命周期
- **跨浏览器兼容**：同一套 API 操作 Chromium、Firefox、WebKit
- **智能重试**：操作失败自动重试，内置超时机制
- **事件体系**：以 Python 回调方式处理浏览器事件

---

## 代码对比：相同的任务，不同的写法

下面用三个典型任务来对比两种方案的代码量和复杂度。

### 任务 1：导航并截图

**CDP 直连方案：**

```python
import asyncio
import json
import urllib.request
import websockets
import base64

# CDP 帮助函数
CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]:
            return data.get("result", {})

async def main():
    # 1. 获取 WebSocket URL
    data = json.loads(urllib.request.urlopen(
        'http://localhost:9222/json', timeout=5).read())
    ws_url = data[0]['webSocketDebuggerUrl']

    # 2. 建立 WebSocket 连接
    async with websockets.connect(ws_url, max_size=2**24) as ws:
        # 3. 启用 Page 域
        await cdp(ws, 'Page.enable')

        # 4. 导航
        await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})

        # 5. 等待页面加载
        await cdp(ws, 'Page.loadEventFired')
        await asyncio.sleep(1)

        # 6. 设置视口
        await cdp(ws, 'Emulation.setDeviceMetricsOverride', {
            'width': 1280, 'height': 720,
            'deviceScaleFactor': 1, 'mobile': False
        })

        # 7. 截图
        result = await cdp(ws, 'Page.captureScreenshot', {'format': 'png'})
        with open('screenshot.png', 'wb') as f:
            f.write(base64.b64decode(result['data']))

        print('截图保存成功：screenshot.png')

asyncio.run(main())
```

**Playwright 方案：**

```python
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('https://example.com')
        await page.set_viewport_size({'width': 1280, 'height': 720})
        await page.screenshot(path='screenshot.png')
        print('截图保存成功：screenshot.png')
        await browser.close()

asyncio.run(main())
```

CDP 直连版本大约 40 行，Playwright 版本 12 行。Playwright 将环境搭建、连接管理、协议交互全部封装好了。

### 任务 2：网络拦截

拦截图片请求并统计数量。

**CDP 直连方案：**

```python
import asyncio
import json
import urllib.request
import websockets

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]:
            return data.get("result", {})

async def main():
    data = json.loads(urllib.request.urlopen(
        'http://localhost:9222/json', timeout=5).read())
    ws_url = data[0]['webSocketDebuggerUrl']

    image_count = 0

    async with websockets.connect(ws_url, max_size=2**24) as ws:
        await cdp(ws, 'Network.enable')

        # 异步监听事件：需要额外的 task 来处理推送消息
        async def listen_events():
            nonlocal image_count
            async for msg in ws:
                data = json.loads(msg)
                # 过滤掉命令响应（有 id 字段的是响应）
                if 'method' not in data:
                    continue
                method = data['method']
                if method == 'Network.requestWillBeSent':
                    req = data['params']['request']
                    if 'image' in req.get('type', '').lower():
                        image_count += 1
                        print(f'图片请求: {req["url"][:60]}...')

        listener_task = asyncio.create_task(listen_events())
        await asyncio.sleep(0.1)

        await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
        await cdp(ws, 'Page.loadEventFired')
        await asyncio.sleep(2)

        listener_task.cancel()
        print(f'共拦截图片请求：{image_count} 个')

asyncio.run(main())
```

**Playwright 方案：**

```python
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        image_count = 0

        page.on('request', lambda req: nonlocal image_count
            if req.resource_type == 'image':
                image_count += 1
                print(f'图片请求: {req.url[:60]}...')
        )

        await page.goto('https://example.com')
        await page.wait_for_timeout(2000)
        print(f'共拦截图片请求：{image_count} 个')
        await browser.close()

asyncio.run(main())
```

CDP 直连需要手动管理事件监听器（WebSocket 的消息是混合了命令响应和事件的），而 Playwright 提供了清晰的 `page.on()` 事件 API。

### 任务 3：拦截并修改响应

将页面中所有图片替换为占位图。

**CDP 直连方案：**

```python
import asyncio
import json
import urllib.request
import websockets

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]:
            return data.get("result", {})

async def main():
    data = json.loads(urllib.request.urlopen(
        'http://localhost:9222/json', timeout=5).read())
    ws_url = data[0]['webSocketDebuggerUrl']

    async with websockets.connect(ws_url, max_size=2**24) as ws:
        await cdp(ws, 'Network.enable')

        # 设置拦截模式
        await cdp(ws, 'Network.setRequestInterception', {
            'patterns': [{'urlPattern': '*', 'resourceType': 'Image'}]
        })

        async def handle_interception():
            async for msg in ws:
                data = json.loads(msg)
                if data.get('method') == 'Network.requestIntercepted':
                    interception_id = data['params']['interceptionId']
                    # 返回一个 1x1 像素的 GIF 占位图
                    gif_data = 'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7'
                    await cdp(ws, 'Network.continueInterceptedRequest', {
                        'interceptionId': interception_id,
                        'rawResponse': base64.b64encode(
                            f'HTTP/1.1 200 OK\r\nContent-Type: image/gif\r\n\r\n'
                            .encode()).decode() + gif_data
                    })

        listener_task = asyncio.create_task(handle_interception())
        await asyncio.sleep(0.1)

        await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
        await cdp(ws, 'Page.loadEventFired')
        await asyncio.sleep(3)

        listener_task.cancel()
        print('图片拦截完成')

asyncio.run(main())
```

**Playwright 方案：**

```python
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # 使用路由拦截——Playwright 最优雅的 API 之一
        await page.route('**/*.{png,jpg,jpeg,gif,webp}',
            lambda route: route.fulfill(
                status=200,
                content_type='image/gif',
                body=base64.b64decode(
                    'R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7')
            )
        )

        await page.goto('https://example.com')
        print('图片拦截完成')
        await browser.close()

asyncio.run(main())
```

Playwright 的 `page.route()` API 将"拦截匹配模式的请求并修改响应"这个常见需求封装成一个函数调用，而 CDP 直连需要手动处理拦截 ID、构造原始 HTTP 响应、管理异步事件循环。

---

## 何时选择 CDP

### 1. 需要最大控制力

CDP 直连暴露了 Chrome 调试协议的每一个角落。某些底层功能 Playwright 没有直接暴露：

```python
# CDP 独有的底层操作示例

# 跟踪性能——CDP 提供的事件种类远超 Playwright 封装
await cdp(ws, 'Tracing.start', {
    'categories': '-*,disabled-by-default-devtools.timeline,devtools.timeline',
    'transferMode': 'ReturnAsStream'
})

# 直接控制协议扩展（非标准 CDP 命令）
await cdp(ws, 'Security.setIgnoreCertificateErrors', {'ignore': True})

# 细粒度的浏览器设置
await cdp(ws, 'Network.setCookie', {
    'name': 'session', 'value': 'abc123',
    'domain': '.example.com', 'httpOnly': True,
    'sameSite': 'Lax', 'priority': 'High'
})
```

### 2. 反检测需求

对于安全测试和反爬场景，CDP 直连比 Playwright 更难被检测。Playwright 在浏览器上下文中会留下自动化痕迹——`navigator.webdriver` 属性的处理方式与原生 CDP 不同。

```python
# CDP 直连：在页面加载前注入脚本，完全不可见
await cdp(ws, 'Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
        window.chrome = {runtime: {}, loadTimes: () => {}, csi: () => {}};
    '''
})

# 自定义 CDP 特征覆盖
await cdp(ws, 'Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        const origDefProp = Object.defineProperty;
        Object.defineProperty = function(obj, prop, desc) {
            if (prop === 'webdriver') return;
            return origDefProp(obj, prop, desc);
        };
    '''
})
```

### 3. 自定义浏览器启动参数

某些场景需要使用非标准的 CDP 命令或自定义启动参数。CDP 直连没有框架限制，你可以自由组合任何协议命令。

### 4. 学习价值

理解 CDP 是掌握浏览器自动化的最佳途径。当你遇到 Playwright 无法解决的问题时，CDP 知识就是你的"应急通道"。

---

## 何时选择 Playwright

### 1. 多浏览器支持

Playwright 的最大优势：一套代码在 Chromium、Firefox、WebKit 上都能运行。

```python
# Playwright 一行换浏览器
browser = await p.chromium.launch()   # 或
browser = await p.firefox.launch()     # 或
browser = await p.webkit.launch()      # 或
```

CDP 直连只能控制基于 Chromium 的浏览器（Chrome、Edge、Brave 等）。

### 2. 自动等待机制

Playwright 的所有操作都内置了自动等待：

```python
# Playwright 会自动等待元素出现，最多等 30 秒
await page.click('#submit-button')
await page.fill('#username', 'admin')
await page.wait_for_selector('.result-table')

# CDP 直连需要手动实现等待逻辑
await cdp(ws, 'Runtime.evaluate', {
    'expression': '''
        new Promise(resolve => {
            const check = () => {
                const el = document.querySelector('#submit-button');
                if (el && el.offsetParent !== null) {
                    el.click(); resolve(true);
                } else {
                    setTimeout(check, 100);
                }
            };
            check();
        })
    ''',
    'awaitPromise': True
})
```

### 3. 稳定的 API 和工具链

Playwright 提供了完整的开箱即用生态：

- **自动浏览器下载**：`playwright install` 自动安装浏览器
- **内置断言**：`expect(page.locator(...)).to_be_visible()`
- **测试运行器**：Playwright Test 内置报告、重试、并行执行
- **录制器**：`playwright codegen` 录制用户操作生成脚本
- **Trace Viewer**：可视化调试测试失败

### 4. 团队协作和可维护性

如果项目有多个开发者参与，Playwright 的声明式 API 比 CDP 直连更易于维护和审查。

---

## 性能对比：开销分析

### 启动时间

| 方案 | 首次启动浏览器 | 重复使用已有浏览器 |
|------|--------------|-----------------|
| CDP 直连（连接已有浏览器） | 0ms（浏览器已运行） | 约 50-100ms 建立 WS |
| Playwright（launch） | 约 2-5s | 约 300-800ms |
| Playwright（connect） | 约 50-200ms | 约 50-200ms |

### 命令延迟

```python
# CDP 直连：一次命令的完整往返
start = time.time()
await cdp(ws, 'Runtime.evaluate', {
    'expression': 'document.title',
    'returnByValue': True
})
cdp_latency = time.time() - start

# Playwright：同样操作
start = time.time()
title = await page.title()
pw_latency = time.time() - start

# 实测结果（局域网 localhost）：
# CDP 直连：约 3-8ms（一次往返）
# Playwright：约 5-15ms（额外 API 层开销）
```

Playwright 的额外开销主要来自：

1. **API 层封装**：Python 对象方法调用 → 内部 CDP 命令生成 → 序列化 → WebSocket 发送
2. **自动等待检查**：每个操作前检查元素状态
3. **事件管理**：Playwright 维护自己的事件队列和状态同步

### 内存开销

| 方案 | 额外内存 | 备注 |
|------|---------|------|
| CDP 直连 | 几乎为 0 | 只有 Python 端的 WebSocket 缓冲区 |
| Playwright | 约 50-100MB | 包含浏览器驱动进程、内部状态管理 |

### 大规模任务测试

假设需要同时控制 10 个浏览器页面进行爬取：

```python
# CDP 直连：10 个 WebSocket 连接，纯异步
tasks = [handle_page(ws_urls[i]) for i in range(10)]
await asyncio.gather(*tasks)

# Playwright：10 个 BrowserContext，内部维护 10 个 CDP 连接
contexts = [await browser.new_context() for _ in range(10)]
pages = [await ctx.new_page() for ctx in contexts]
```

在 10 个页面的规模下，两者差距不大。当页面数增加到 100+ 时，CDP 直连的内存优势开始显现——Playwright 的每个 BrowserContext 和 Page 对象都会额外占用几十 KB 到几 MB 的 Python 内存。

### 综合性能评分

| 指标 | CDP 直连 | Playwright |
|------|---------|-----------|
| 命令延迟 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 内存占用 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 大规模并发 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 启动速度（可用浏览器） | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 启动速度（新浏览器） | ⭐⭐⭐ | ⭐⭐⭐⭐ |

---

## 混合方案：Playwright + CDPSession

Playwright 允许通过 `CDPSession` 直接访问底层 CDP，这是两全其美的最佳实践。

```python
import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        # 1. 使用 Playwright 管理浏览器
        browser = await p.chromium.launch(headless=False)
        page = await browser.new_page()

        # 2. 获取 CDP Session——直接控制底层协议
        cdp_session = await page.context.new_cdp_session(page)

        # 现在你可以同时使用两种方式：

        # Playwright API——稳定、简洁
        await page.goto('https://example.com')
        title = await page.title()
        print(f'页面标题: {title}')

        # CDP 直连——访问 Playwright 未封装的协议
        result = await cdp_session.send('Performance.getMetrics')
        print(f'JS 堆大小: {result["metrics"][0]["value"]}')

        # 混合示例：Playwright 导航 + CDP 性能数据
        await page.goto('https://example.com')
        metrics = await cdp_session.send('Performance.getMetrics')
        heap = next(m for m in metrics['metrics'] if m['name'] == 'JSHeapUsedSize')
        print(f'JS 堆使用: {heap["value"] / 1024 / 1024:.1f} MB')

        # CDP 独有的追踪功能
        await cdp_session.send('Tracing.start', {
            'categories': 'devtools.timeline,loading'
        })
        await page.wait_for_timeout(3000)
        tracing_data = await cdp_session.send('Tracing.end')

        # Playwright 截图（Playwright 管理）
        await page.screenshot(path='hybrid.png')

        await browser.close()

asyncio.run(main())
```

### 典型混合场景

| 场景 | Playwright 负责 | CDPSession 负责 |
|------|---------------|----------------|
| 反爬虫绕检测 | 浏览器启动、页面导航 | `Page.addScriptToEvaluateOnNewDocument`、修改特征 |
| 性能分析 | 导航、交互操作 | `Tracing.start`、`Performance.getMetrics` |
| 网络篡改 | 基础拦截（page.route） | 原始 HTTP 响应构造、WebSocket 拦截 |
| 安全测试 | 页面操作、DOM 查询 | `Security.setIgnoreCertificateErrors`、`Network.setCookies` |
| 截图监控 | 常规页面截图 | `Page.captureSnapshot`、`DOM.getDocument` |

### 使用 CDPSession 的注意事项

```python
# 正确的使用方法——通过 page.context 创建
session = await page.context.new_cdp_session(page)

# 错误：CDP 调用的 session_id 参数在这里不适用
# 你可以直接用 session.send()，无需手动处理 session_id

# 重要：CDPSession.send() 的返回值已经是 result 字段的解析结果
# 无需像 CDP 直连一样手动解析
metrics = await session.send('Performance.getMetrics')
print(metrics)  # 直接是 {"metrics": [...]} 中的内容

# 但你需要手动处理域启用
await session.send('Performance.enable')
await session.send('Network.enable')
# ... 与 CDP 直连一样
```

---

## 能力对比表

| 能力 | CDP 直连 | Playwright | Playwright + CDPSession |
|------|---------|-----------|----------------------|
| 页面导航与控制 | ✅ | ✅（更简洁） | ✅ |
| DOM 操作 | ✅ | ✅（自动等待） | ✅ |
| JavaScript 注入 | ✅ | ✅ | ✅ |
| 网络请求拦截 | ✅（手动处理） | ✅（page.route） | ✅ |
| 修改请求/响应 | ✅（手动构造） | ✅（route.fulfill） | ✅ |
| 截屏（页面/元素） | ✅ | ✅（更丰富格式） | ✅ |
| 生成 PDF | ✅ | ✅ | ✅ |
| 性能追踪 | ✅（完整 Tracing） | ❌ 部分 API | ✅（完整 Tracing） |
| 内存分析 | ✅（HeapProfiler） | ❌ | ✅ |
| Cookie 管理 | ✅ | ✅（更简洁） | ✅ |
| Service Worker | ✅ | ✅ | ✅ |
| WebSocket 拦截 | ✅（手动） | ❌ | ✅ |
| 自定义协议扩展 | ✅ | ❌ | ✅ |
| 跨浏览器支持 | ❌（仅 Chromium） | ✅（3 引擎） | ✅（3 引擎） |
| 自动等待 | ❌ | ✅ | ✅ |
| 自动重试 | ❌ | ✅ | ✅ |
| 测试运行器 | ❌ | ✅ | ✅ |
| Trace Viewer | ❌ | ✅ | ✅ |
| 录制器 | ❌ | ✅ | ✅ |
| Docker 支持 | ❌ | ✅（内置） | ✅ |
| CI/CD 集成 | ❌ | ✅（完善） | ✅ |
| 学习曲线 | 陡峭 | 平缓 | 中等 |
| 代码量（相同任务） | 3-5x | 1x | 1.5-2x |
| 反检测能力 | 强 | 中 | 强 |
| 文档丰富度 | 中等 | 非常丰富 | 丰富 |
| 社区活跃度 | 中等 | 非常高 | 高 |

---

## 总结与选型决策

选择 CDP 还是 Playwright，取决于你的核心需求：

```
你的需求是什么？
│
├─ 1️⃣ 只需要 Chrome/Chromium？
│   │
│   ├─ 需要最大控制力、反检测、操作底层协议？
│   │   └─ ► CDP 直连
│   │
│   └─ 一般自动化、测试、爬虫？
│       └─ ► Playwright（或 Playwright + CDPSession）
│
├─ 2️⃣ 需要跨浏览器（Firefox/Safari）？
│   └─ ► Playwright
│
├─ 3️⃣ 需要完整的测试框架和工具链？
│   └─ ► Playwright
│
├─ 4️⃣ 做浏览器内核研究、性能分析工具？
│   └─ ► CDP 直连
│
├─ 5️⃣ 学习浏览器自动化原理？
│   │
│   ├─ 初学者快速上手？
│   │   └─ ► Playwright，然后学 CDP
│   │
│   └─ 从原理出发理解？
│       └─ ► CDP 直连，然后学 Playwright
│
└─ 6️⃣ 需要生产级可靠 + 底层控制？
    └─ ► Playwright + CDPSession（最佳实践）
```

### 最终建议

**大多数情况下，选择 Playwright + CDPSession 混合方案是最佳路径**。你用 Playwright 完成 80% 的常规任务，遇到 Playwright 的边界时通过 CDPSession 钻到协议层解决问题。

如果你的项目需要**最高级别的反检测能力**（比如安全测试中的浏览器指纹绕过），CDP 直连更合适。这需要你承受更高的开发成本和维护复杂度。

> **核心原则**：用 Playwright 写应用，用 CDP 知识救火。两者不是对手，而是互补的搭档——理解了 CDP，才能真正驾驭 Playwright；用好了 Playwright，才能避免在 CDP 的细节中迷失方向。
