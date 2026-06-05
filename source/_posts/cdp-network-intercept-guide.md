---
title: CDP 网络拦截与请求篡改实战：Python 控制 Chrome 抓包改包完全指南
date: 2026-06-04 14:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 网络拦截
  - 爬虫
categories:
  - CDP 基础
  - Python 实战
description: 用 CDP 拦截、修改 HTTP 请求和响应，实现 API Mock、自动翻页、图片懒加载触发、请求屏蔽等高级操作，附带完整的 Python 实战代码。
---

> **一句话总结**：CDP 的网络拦截能力让你可以在请求到达服务器之前修改它，也可以在响应到达浏览器之前篡改它 — 这一切都不需要代理服务器，完全在 Chrome 内部完成。

---

## 目录

1. [为什么需要 CDP 网络拦截](#为什么需要-cdp-网络拦截)
2. [Network 与 Fetch 域：两种拦截方式](#network-与-fetch-域两种拦截方式)
3. [预备知识：监听网络事件](#预备知识监听网络事件)
4. [实战一：拦截请求并修改 Header](#实战一拦截请求并修改-header)
5. [实战二：拦截响应并替换内容](#实战二拦截响应并替换内容)
6. [实战三：屏蔽特定请求（广告/图片/统计）](#实战三屏蔽特定请求广告图片统计)
7. [实战四：SPA 页面自动翻页抓取](#实战四spa-页面自动翻页抓取)
8. [实战五：Mock API 做前端测试](#实战五mock-api-做前端测试)
9. [实战六：提前触发图片懒加载](#实战六提前触发图片懒加载)
10. [踩坑记录与最佳实践](#踩坑记录与最佳实践)

---

## 为什么需要 CDP 网络拦截

传统上，要在浏览器层面拦截网络请求，你有几个选择：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Fiddler / Charles 代理** | 功能强大、UI 友好 | 需要配置系统代理、无法编程控制 |
| **mitmproxy** | 可编程 | 需要安装证书、处理 HTTPS 解密 |
| **Selenium Wire** | 集成在 Selenium 中 | 依赖中间人代理、性能损耗大 |
| **Playwright route()** | 简洁的 API | 黑盒操作、底层不透明 |
| **CDP Fetch/Network 域** | 无需代理、原生支持、细粒度控制 | 需要理解 CDP 协议 |

CDP 方式的优势很明显：

- **不需要任何代理服务器**，Chrome 原生就支持
- **请求和响应都可以拦截修改**，包括二进制数据
- **可以按需阻断**，不让请求发出去（省流量、提速度）
- **性能开销极小**，因为拦截发生在 Chrome 内部，没有额外的网络跳转

---

## Network 与 Fetch 域：两种拦截方式

Chrome DevTools Protocol 提供了两个域来控制网络：

### Network 域

传统方式，对应 DevTools 中的 Network 面板。

```python
# Network 域可以监听到所有网络活动
cmd(ws, 'Network.enable')
```

**可以做**：监听请求、获取响应体、屏蔽 Cookie
**不能做**：在请求发出前修改它、中止请求

### Fetch 域（推荐）

Fetch 域是更现代的 API，允许你 "暂停" 请求，在中间做修改，然后决定放行、修改、或中止。

```python
# Fetch 域启用后，每个请求都会被"拦截"
cmd(ws, 'Fetch.enable', {
    'patterns': [{'urlPattern': '*', 'requestStage': 'Request'}]
})
```

**核心概念**：

1. 浏览器发起一个请求
2. CDP 暂停这个请求，发出 `Fetch.requestPaused` 事件
3. 你的代码收到事件，可以：
   - **放行**：`Fetch.continueRequest` — 不做修改直接发送
   - **修改后放行**：修改 header、method、body 后再发送
   - **中止**：`Fetch.failRequest` — 让请求失败
   - **提供替代响应**：`Fetch.fulfillRequest` — 直接返回自定义内容

| 对比 | Network 域 | Fetch 域 |
|------|-----------|---------|
| 监听请求 | ✅ | ✅ |
| 获取响应体 | ✅（需额外调用） | ❌（不直接支持） |
| 修改请求头 | ❌ | ✅ |
| 修改请求体 | ❌ | ✅ |
| 中止请求 | ❌ | ✅ |
| 自定义响应 | ❌ | ✅ |
| 获取响应内容 | ✅ | 需配合 Network 域 |

实际开发中，**Fetch 域 + Network 域经常配合使用**：
- Fetch 域做拦截和修改
- Network 域做监听和获取响应数据

---

## 预备知识：监听网络事件

我们先从最基础的开始 — 连接 Chrome 并监听网络事件。

### 基础连接模板

```python
import json, urllib.request, websocket, time

# ====== 连接 CDP ======
CDP_HTTP = 'http://localhost:9222'

def get_ws():
    data = json.loads(urllib.request.urlopen(f'{CDP_HTTP}/json', timeout=5).read())
    for t in data:
        if t.get('type') == 'page':
            return t['webSocketDebuggerUrl']
    return None

def cmd(ws, method, params=None):
    if params is None: params = {}
    cmd._id += 1
    ws.send(json.dumps({'id': cmd._id, 'method': method, 'params': params}))
    while True:
        r = json.loads(ws.recv())
        if r.get('id') == cmd._id: return r.get('result', {})

cmd._id = 1

ws_url = get_ws()
ws = websocket.create_connection(ws_url, timeout=30)
cmd(ws, 'Page.enable')
cmd(ws, 'Network.enable')
```

这是一个标准的 CDP 连接模板，后续所有例子都基于它。

### 监听所有网络请求

```python
# 启动后，所有网络事件都会通过 WebSocket 推送
cmd(ws, 'Page.navigate', {'url': 'https://example.com'})
time.sleep(3)

# 持续接收消息（设置超时避免卡死）
ws.settimeout(1)
try:
    while True:
        msg = json.loads(ws.recv())
        method = msg.get('method', '')
        if method == 'Network.requestWillBeSent':
            req = msg['params']['request']
            url = req['url']
            method_http = req['method']
            print(f'➡ {method_http} {url}')
        elif method == 'Network.responseReceived':
            resp = msg['params']['response']
            print(f'⬅ {resp["status"]} {resp["url"]}')
except websocket.TimeoutError:
    pass
```

你会看到类似这样的输出：

```
➡ GET https://example.com/
⬅ 200 https://example.com/
➡ GET https://example.com/style.css
⬅ 200 https://example.com/style.css
➡ GET https://example.com/script.js
⬅ 200 https://example.com/script.js
```

---

## 实战一：拦截请求并修改 Header

有些网站会检查 `Referer` 或 `User-Agent`，或者你需要添加自定义认证头。用 Fetch 域可以轻松实现。

```python
# 启用 Fetch 拦截
cmd(ws, 'Fetch.enable', {
    'patterns': [{
        'urlPattern': '*',
        'requestStage': 'Request'
    }]
})

pending_requests = {}

def process_message(msg):
    """处理 CDP 消息，拦截并修改请求"""
    params = msg.get('params', {})
    method = msg.get('method', '')
    
    if method == 'Fetch.requestPaused':
        request_id = params['requestId']
        request = params['request']
        url = request['url']
        
        # 跳过 ws:// 和 data: 协议
        if url.startswith('data:') or url.startswith('blob:'):
            cmd(ws, 'Fetch.continueRequest', {
                'requestId': request_id
            })
            return
        
        # 修改请求头：添加自定义 Header
        headers = request.get('headers', {})
        headers['X-Custom-Header'] = 'my-value'
        headers['Referer'] = 'https://my-custom-referer.com/'
        
        print(f'✏ Modifying: {url[:60]}...')
        
        cmd(ws, 'Fetch.continueRequest', {
            'requestId': request_id,
            'headers': [{'name': k, 'value': v} for k, v in headers.items()]
        })

# 导航到目标页面
cmd(ws, 'Page.navigate', {'url': 'https://httpbin.org/headers'})

# 持续处理消息
timeout = 10
start = time.time()
while time.time() - start < timeout:
    try:
        ws.settimeout(0.5)
        msg = json.loads(ws.recv())
        process_message(msg)
    except websocket.TimeoutError:
        break
```

**注意**：`Fetch.continueRequest` 的 `headers` 参数需要传一个 `{name, value}` 对象数组，而不是普通字典。这是 Fetch 域的格式要求。

如果要**修改请求体**（比如 POST 请求），可以这样：

```python
if request['method'] == 'POST':
    # 修改 POST 请求体
    new_body = json.dumps({"modified": True, "original": request.get('postData', '')})
    cmd(ws, 'Fetch.continueRequest', {
        'requestId': request_id,
        'postData': base64.b64encode(new_body.encode()).decode()
    })
```

POST 数据需要 Base64 编码后再传回。

---

## 实战二：拦截响应并替换内容

这是更高级的功能 — 在响应到达浏览器之前，修改它的内容。比如：

- 替换页面的 CSS/JS 来做调试
- Mock API 返回数据
- 注入自定义脚本

```python
# 启用 Fetch 拦截（Request + Response 两个阶段）
cmd(ws, 'Fetch.enable', {
    'patterns': [{
        'urlPattern': '*',
        'requestStage': 'Response'
    }]
})

def process_response(msg):
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    request = params['request']
    url = request['url']
    
    # 只拦截 API 请求
    if '/api/' not in url:
        cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
        return
    
    # 构造替代响应
    response_body = json.dumps({
        "code": 0,
        "message": "This is mocked by CDP",
        "data": {"items": [], "total": 0}
    })
    
    print(f'🔧 Mocking API: {url[:60]}')
    
    # 使用 Fetch.fulfillRequest 直接返回自定义内容
    cmd(ws, 'Fetch.fulfillRequest', {
        'requestId': request_id,
        'responseCode': 200,
        'responseHeaders': [
            {'name': 'Content-Type', 'value': 'application/json'},
            {'name': 'Access-Control-Allow-Origin', 'value': '*'}
        ],
        'body': base64.b64encode(response_body.encode()).decode()
    })
```

**需要注意**：`Fetch.fulfillRequest` 替代的是整个响应，浏览器不会真的去请求服务器。这个功能特别适合：
- 测试前端在 API 返回不同状态码时的表现
- 离线调试
- 快速原型验证

### 替换页面 JS 或 CSS

```python
def inject_script(msg):
    """拦截 JavaScript 文件，注入自定义代码"""
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    url = params['request']['url']
    
    # 只拦截 main.js
    if 'main.js' not in url:
        cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
        return
    
    # 原本的 JS 被替换成我们的代码
    custom_js = '''
    console.log("CDP injected script!");
    // 修改页面标题
    document.title = "[CDP Modified] " + document.title;
    // 注入全局变量
    window.__CDP_INJECTED__ = true;
    '''
    
    cmd(ws, 'Fetch.fulfillRequest', {
        'requestId': request_id,
        'responseCode': 200,
        'responseHeaders': [
            {'name': 'Content-Type', 'value': 'application/javascript'}
        ],
        'body': base64.b64encode(custom_js.encode()).decode()
    })
```

---

## 实战三：屏蔽特定请求（广告/图片/统计）

屏蔽不必要的请求可以显著加快页面加载速度，减少带宽消耗。

```python
# 定义屏蔽规则
BLOCKED_PATTERNS = [
    'google-analytics.com',
    'doubleclick.net',
    'facebook.net',
    'googlesyndication.com',
    'amazon-adsystem.com',
    '.jpg',   # 屏蔽所有图片
    '.png',
    '.gif',
]

def block_requests(msg):
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    url = params['request']['url']
    
    # 检查是否命中屏蔽列表
    for pattern in BLOCKED_PATTERNS:
        if pattern in url:
            print(f'🚫 Blocked: {url[:60]}')
            # 使用 Fetch.failRequest 让请求失败
            cmd(ws, 'Fetch.failRequest', {
                'requestId': request_id,
                'errorReason': 'BlockedByClient'
            })
            return
    
    # 放行其他请求
    cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
```

可选的中止原因（`errorReason`）：
- `BlockedByClient` — 最常见的屏蔽
- `AddressUnreachable`
- `ConnectionAborted`
- `ConnectionRefused`
- `ConnectionReset`
- `InternetDisconnected`
- `NameNotResolved`
- `TimedOut`

---

## 实战四：SPA 页面自动翻页抓取

SPA（单页应用）站点用传统的 `requests` 很难抓取，因为内容是通过 JavaScript 动态加载的。CDP 可以监听到 XHR/Fetch 请求并提取数据。

```python
def crawl_spa():
    """抓取 SPA 页面的 API 数据"""
    
    captured_data = []
    start_time = time.time()
    
    def handle_response(msg):
        """处理单个网络响应消息"""
        params = msg.get('params', {})
        if msg.get('method') != 'Network.responseReceived':
            return
        
        resp = params['response']
        url = resp['url']
        
        # 识别 API 请求（根据 URL 特征）
        if '/api/' not in url and '/graphql' not in url:
            return
        
        request_id = params['requestId']
        
        # 获取响应体
        result = cmd(ws, 'Network.getResponseBody', {
            'requestId': request_id
        })
        
        if 'body' in result:
            body = result['body']
            print(f'📦 Captured API: {url[:50]}')
            print(f'   Data size: {len(body)} bytes')
            captured_data.append({
                'url': url,
                'body': body[:500]
            })
    
    def process_events(duration):
        """持续处理 WebSocket 消息（阻塞，最多 duration 秒）"""
        end = time.time() + duration
        while time.time() < end:
            try:
                ws.settimeout(0.3)
                msg = json.loads(ws.recv())
                handle_response(msg)
            except websocket.TimeoutError:
                continue
    
    # 导航
    cmd(ws, 'Network.enable')
    cmd(ws, 'Page.navigate', {'url': 'https://example-spa.com/list'})
    
    # 等待页面加载并捕获初始请求
    process_events(3)
    
    # 模拟翻页：点击"下一页"按钮
    cmd(ws, 'Runtime.evaluate', {
        'expression': 'document.querySelector(".next-page").click()',
        'returnByValue': True
    })
    
    # 捕获翻页后的 API 响应
    process_events(2)
    
    # 再翻一页
    cmd(ws, 'Runtime.evaluate', {
        'expression': 'document.querySelector(".next-page").click()',
        'returnByValue': True
    })
    
    process_events(2)
    
    return captured_data
```

这种方式比传统的 Selenium + 解析 HTML 更高效，因为你直接拿到了 API 返回的原始 JSON 数据，省去了解析 HTML 的步骤。

### 进阶：等待特定 API 响应

有时候你需要等某个 API 返回了再执行下一步，可以用 `Network.responseReceived` + 条件判断：

```python
def wait_for_api(ws, url_pattern, timeout=10):
    """等待特定的 API 请求完成"""
    import re
    pattern = re.compile(url_pattern)
    start = time.time()
    
    while time.time() - start < timeout:
        try:
            ws.settimeout(0.3)
            msg = json.loads(ws.recv())
            if msg.get('method') == 'Network.responseReceived':
                url = msg['params']['response']['url']
                if pattern.search(url):
                    request_id = msg['params']['requestId']
                    result = cmd(ws, 'Network.getResponseBody', {
                        'requestId': request_id
                    })
                    return json.loads(result.get('body', '{}'))
        except websocket.TimeoutError:
            continue
    
    return None

# 用法
data = wait_for_api(ws, r'/api/products\?page=2')
if data:
    print(f'Got {len(data.get("items", []))} products')
```

---

## 实战五：Mock API 做前端测试

前端测试时经常需要 mock API 响应。CDP 可以让你在不修改代码的情况下实现接口 Mock。

```python
# Mock 配置：URL 模式 -> 模拟响应
MOCK_CONFIG = {
    '/api/user/info': {
        'code': 0,
        'data': {
            'id': 10001,
            'name': '测试用户',
            'avatar': 'https://example.com/avatar.png',
            'vip': True
        }
    },
    '/api/products/list': {
        'code': 0,
        'data': {
            'items': [
                {'id': 1, 'name': '商品A', 'price': 99.00},
                {'id': 2, 'name': '商品B', 'price': 199.00},
            ],
            'total': 2,
            'page': 1
        }
    }
}

# 模拟 500 错误
MOCK_ERROR = {
    '/api/error/test': {
        'status': 500,
        'body': {'code': -1, 'message': '服务器内部错误'}
    }
}

def handle_mock(msg):
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    url = params['request']['url']
    
    # 检查是否匹配 Mock 配置
    for pattern, mock_data in MOCK_CONFIG.items():
        if pattern in url:
            print(f'🎭 Mocking: {url[:50]}')
            body = json.dumps(mock_data)
            cmd(ws, 'Fetch.fulfillRequest', {
                'requestId': request_id,
                'responseCode': 200,
                'responseHeaders': [
                    {'name': 'Content-Type', 'value': 'application/json'}
                ],
                'body': base64.b64encode(body.encode()).decode()
            })
            return
    
    # 检查错误模拟
    for pattern, error_data in MOCK_ERROR.items():
        if pattern in url:
            print(f'💥 Simulating error: {url[:50]}')
            body = json.dumps(error_data['body'])
            cmd(ws, 'Fetch.fulfillRequest', {
                'requestId': request_id,
                'responseCode': error_data['status'],
                'responseHeaders': [
                    {'name': 'Content-Type', 'value': 'application/json'}
                ],
                'body': base64.b64encode(body.encode()).decode()
            })
            return
    
    # 放行未配置的请求
    cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
```

这个技巧在以下场景特别有用：
- **前端开发**：后端 API 还没写好，前端先 mock
- **E2E 测试**：控制 API 返回确保测试稳定
- **演示/Demo**：不需要真实后端就能跑通全流程

---

## 实战六：提前触发图片懒加载

很多现代网站使用懒加载（loading="lazy"），图片只在进入视口时才加载。如果你想抓取所有图片，可以用 CDP 提前触发：

```python
def trigger_all_images(ws):
    """触发页面中所有懒加载图片开始加载"""
    
    # 通过 Fetch 域拦截图片加载
    cmd(ws, 'Fetch.enable', {
        'patterns': [
            {'urlPattern': '*.jpg', 'requestStage': 'Request'},
            {'urlPattern': '*.png', 'requestStage': 'Request'},
            {'urlPattern': '*.webp', 'requestStage': 'Request'},
            {'urlPattern': '*.gif', 'requestStage': 'Request'}
        ]
    })
    
    # 滚动页面到底部，触发懒加载
    cmd(ws, 'Runtime.evaluate', {
        'expression': '''
        (async () => {
            const delay = ms => new Promise(r => setTimeout(r, ms));
            const scrollStep = 500;
            const totalScroll = document.body.scrollHeight;
            
            for (let y = 0; y < totalScroll; y += scrollStep) {
                window.scrollTo(0, y);
                await delay(300);  // 等待图片触发加载
            }
            
            // 回到顶部
            window.scrollTo(0, 0);
            return 'Scrolled full page';
        })()
        ''',
        'returnByValue': True,
        'awaitPromise': True
    })
    
    # 收集所有图片 URL
    images = cmd(ws, 'Runtime.evaluate', {
        'expression': '''
        (() => {
            const imgs = document.querySelectorAll('img');
            return Array.from(imgs)
                .filter(img => img.src && !img.src.startsWith('data:'))
                .map(img => img.src)
                .join('\\n');
        })()
        ''',
        'returnByValue': True
    })
    
    return images.get('result', {}).get('value', '')
```

等图片加载完成后，还可以用 `Page.captureScreenshot` 来截取包含所有图片的完整页面截图。

---

## 踩坑记录与最佳实践

### 1. Fetch 请求必须响应，否则会卡住

启用 `Fetch.enable` 后，每一个匹配模式的请求都会被暂停，直到你调用 `continueRequest`、`fulfillRequest` 或 `failRequest`。**如果你不处理某个请求，页面会一直等待**，其他请求也会被阻塞。

```python
# ❌ 错误：只处理部分请求
# 未处理的请求会一直挂起

# ✅ 正确：所有请求都有对应处理
def safe_handler(msg):
    if msg.get('method') != 'Fetch.requestPaused':
        return
    request_id = msg['params']['requestId']
    
    if should_intercept(msg):
        do_intercept(msg)
    else:
        # 一定要放行！
        cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
```

### 2. Base64 编码的坑

`Fetch.fulfillRequest` 的 `body` 需要 Base64 编码，而 `Fetch.continueRequest` 的 `postData` 也需要。但不是所有语言和库的 Base64 实现都兼容：

```python
import base64

# 正确做法
body = '{"key": "value"}'
encoded = base64.b64encode(body.encode()).decode()  # 标准 Base64

# 注意：不是 URL-safe 的 base64
encoded_wrong = base64.urlsafe_b64encode(body.encode()).decode()  # ❌
```

### 3. 同时使用 Fetch 和 Network 域的冲突

如果你同时启用了 `Fetch.enable` 和 `Network.enable`，Fetch 域拦截的请求在 Network 域中可能显示为 `(canceled)`，因为请求实际上被暂停了。这是正常行为，不代表请求失败。

解决方案：**只用 Fetch 做拦截，用 `Fetch.continueRequest` 中的 `headers` 参数来获取请求信息**，而不是依赖 Network 域。

### 4. 拦截顺序和性能

拦截大量请求（特别是页面初始加载时的 100+ 个请求）会带来一些性能开销。建议：

- 只拦截你需要的 URL 模式
- 在 `Fetch.enable` 的 `patterns` 中指定准确的 URL 模式，而不是 `*`
- 不需要拦截时调用 `Fetch.disable` 关闭

```python
# 精准拦截
cmd(ws, 'Fetch.enable', {
    'patterns': [
        {'urlPattern': '*/api/*', 'requestStage': 'Request'},
        {'urlPattern': '*.json', 'requestStage': 'Response'}
    ]
})
# 不要用 {'urlPattern': '*'} 除非确实需要拦截所有请求
```

### 5. WebSocket 请求的特殊处理

WebSocket 请求（`ws://` 和 `wss://`）通过 Fetch 域拦截时需要特殊处理：

```python
if url.startswith('ws://') or url.startswith('wss://'):
    # WebSocket 请求必须放行，不支持修改
    cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
    return
```

### 6. 请求体获取限制

`Fetch.requestPaused` 事件中，`request.postData` 只有在请求体是文本时才可用。如果请求体是二进制数据（如文件上传），`postData` 可能为空。

此时可以通过 Network 域来捕获请求体：

```python
# 在 Network 域中监听
# Network.requestWillBeSent 事件中有更完整的 request.postData
```

---

## 完整示例：一个通用的网络拦截器

最后，我把以上技巧综合成一个完整的网络拦截器工具类：

```python
import json, websocket, time, base64, urllib.request

class CDPNetworkInterceptor:
    """CDP 网络拦截器"""
    
    def __init__(self, host='localhost:9222'):
        self.host = host
        self.ws = None
        self._id = 1
        self.blocked_count = 0
        self.mock_count = 0
    
    def connect(self):
        """连接 CDP"""
        data = json.loads(urllib.request.urlopen(
            f'http://{self.host}/json', timeout=5).read())
        ws_url = data[0]['webSocketDebuggerUrl']
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._cmd('Page.enable')
        self._cmd('Network.enable')
        return self
    
    def _cmd(self, method, params=None):
        if params is None: params = {}
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == self._id: return r.get('result', {})
    
    def start_intercept(self, patterns=None):
        """启动请求拦截"""
        if patterns is None:
            patterns = [{'urlPattern': '*', 'requestStage': 'Request'}]
        self._cmd('Fetch.enable', {'patterns': patterns})
        print(f'🔍 Intercept started with {len(patterns)} pattern(s)')
    
    def stop_intercept(self):
        """停止拦截"""
        self._cmd('Fetch.disable')
        print('⏹ Intercept stopped')
    
    def run(self, url, handlers=None, timeout=15):
        """
        打开页面并运行拦截处理
        
        Args:
            url: 要打开的页面
            handlers: 自定义处理函数，接收 request_id, url, params
            timeout: 运行时间（秒）
        """
        if handlers is None:
            handlers = {'on_request': None, 'on_response': None}
        
        self._cmd('Page.navigate', {'url': url})
        
        start = time.time()
        while time.time() - start < timeout:
            try:
                self.ws.settimeout(0.3)
                msg = json.loads(self.ws.recv())
                
                if msg.get('method') == 'Fetch.requestPaused':
                    params = msg['params']
                    request_id = params['requestId']
                    url = params['request']['url']
                    
                    # 跳过特殊协议
                    if url.startswith('data:') or url.startswith('blob:') or url.startswith('ws'):
                        self._cmd('Fetch.continueRequest', {'requestId': request_id})
                        continue
                    
                    # 调用自定义处理
                    if handlers.get('on_request'):
                        handled = handlers['on_request'](request_id, url, params)
                        if handled:
                            continue
                    
                    # 默认放行
                    self._cmd('Fetch.continueRequest', {'requestId': request_id})
                    
            except websocket.TimeoutError:
                continue
    
    def close(self):
        if self.ws:
            self.ws.close()


# ====== 使用示例 ======
# 创建一个拦截器
interceptor = CDPNetworkInterceptor().connect()
interceptor.start_intercept()

# 访问页面，拦截广告
interceptor.run('https://example.com', {
    'on_request': lambda rid, url, params: (
        # 屏蔽 Google Analytics
        'google-analytics.com' in url and (
            interceptor._cmd('Fetch.failRequest', {
                'requestId': rid,
                'errorReason': 'BlockedByClient'
            }) or True  # 返回 True 表示已处理
        )
    ) or None
})

interceptor.stop_intercept()
interceptor.close()
```

---

## 总结

CDP 的网络拦截能力让它成为浏览器自动化中最强大的方案之一：

- **Fetch 域**可以拦截、修改、中止请求，也可以直接返回自定义响应
- **Network 域**适合监听和获取响应数据
- **两者配合**可以实现完整的"请求 → 修改 → 获取响应"流程
- **不需要代理服务器**，Chrome 原生支持

下一篇文章我会继续深入 CDP 的**浏览器指纹与反检测**主题，敬请期待。
