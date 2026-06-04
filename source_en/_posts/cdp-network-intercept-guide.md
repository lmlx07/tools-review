---
lang: en
title: "CDP network interception and request tampering practice: A complete guide to controlling Chrome packet capture and modification with Python"
date: "2026-06-04 14:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Network Interception
  - 爬虫
categories:
  - CDP Basics
  - Python Practice
description: Use CDP to intercept and modify HTTP requests and responses to implement advanced operations such as API mocking, automatic page turning, lazy image loading triggering, request blocking, etc. It comes with complete Python practical code.
---

> **One sentence summary**: CDP’s network interception capabilities allow you to modify the request before it reaches the server and tamper with the response before it reaches the browser - all without the need for a proxy server and completely within Chrome.

---

## Why CDP network interception is needed

Traditionally, to intercept network requests at the browser level, you had a few options:

| Solution | Advantages | Disadvantages |
|------|------|------|
| **Fiddler / Charles agent** | Powerful and user-friendly | System agent needs to be configured and cannot be controlled programmatically |
| **mitmproxy** | Programmable | Requires certificate installation, handles HTTPS decryption |
| **Selenium Wire** | Integrated in Selenium | Relies on middleman proxy, large performance loss |
| **Playwright route()** | Simple API | Black box operation, underlying opacity |
| **CDP Fetch/Network domain** | No proxy required, native support, fine-grained control | Requires understanding of CDP protocol |

The advantages of the CDP approach are obvious:

- **No proxy server required**, Chrome supports it natively
- **Requests and responses can both intercept modifications**, including binary data
- **Can be blocked on demand** to prevent requests from being sent out (saving traffic and improving speed)
- **Minimum performance overhead** because the interception happens inside Chrome, no additional network jumps

---

## Network and Fetch domains: two interception methods

The Chrome DevTools Protocol provides two domains to control the network:

### Network domain

The traditional method corresponds to the Network panel in DevTools.

```python
# Network 域可以监听到所有网络活动
cmd(ws, 'Network.enable')
```

**Can be done**: monitor requests, obtain response bodies, and block cookies
**DO NOT DO**: Modify the request before it is issued, abort the request

### Fetch domain (recommended)

The Fetch domain is a more modern API that allows you to "pause" the request, make changes in the middle, and then decide to release, modify, or abort.

```python
# Fetch 域启用后，每个请求都会被"拦截"
cmd(ws, 'Fetch.enable', {
    'patterns': [{'urlPattern': '*', 'requestStage': 'Request'}]
})
```

**Core Concept**:

1. The browser initiates a request
2. CDP pauses the request and issues the `Fetch.requestPaused` event
3. When your code receives the event, you can:
   - **Release**: `Fetch.continueRequest` — send directly without modification
   - **Release after modification**: Modify header, method, body before sending
   - **Abort**: `Fetch.failRequest` — Fail the request
   - **Provide alternative response**: `Fetch.fulfillRequest` — Return custom content directly

| Comparison | Network domain | Fetch domain |
|------|-----------|---------|
| Listen for requests | ✅ | ✅ |
| Get response body | ✅ (requires additional call) | ❌ (not directly supported) |
| Modify request header | ❌ | ✅ |
| Modify request body | ❌ | ✅ |
| Abort request | ❌ | ✅ |
| Custom responses | ❌ | ✅ |
| Get response content | ✅ | Need to cooperate with Network domain |

In actual development, **Fetch domain + Network domain are often used together**:
- Fetch domain for interception and modification
- Network domain monitors and obtains response data

---

## Preliminary knowledge: Monitoring network events

Let’s start with the basics — connecting to Chrome and listening for network events.

### Basic connection template

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

This is a standard CDP connection template, and all subsequent examples are based on it.

### Listen to all network requests

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

You will see output similar to this:

```
➡ GET https://example.com/
⬅ 200 https://example.com/
➡ GET https://example.com/style.css
⬅ 200 https://example.com/style.css
➡ GET https://example.com/script.js
⬅ 200 https://example.com/script.js
```

---

## Practical combat one: intercept the request and modify the header

Some sites check for `Referer` or `User-Agent`, or you need to add custom authentication headers. This can be easily accomplished using the Fetch field.

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

**Note**: The `headers` parameter of `Fetch.continueRequest` needs to pass an `{name, value}` object array instead of an ordinary dictionary. This is the format requirement for Fetch fields.

If you want to **modify the request body** (such as a POST request), you can do this:

```python
if request['method'] == 'POST':
    # 修改 POST 请求体
    new_body = json.dumps({"modified": True, "original": request.get('postData', '')})
    cmd(ws, 'Fetch.continueRequest', {
        'requestId': request_id,
        'postData': base64.b64encode(new_body.encode()).decode()
    })
```

POST data needs to be Base64 encoded before being sent back.

---

## Practice 2: Intercept the response and replace the content

This is a more advanced feature - modifying the content of the response before it reaches the browser. for example:

- Replace the CSS/JS of the page for debugging
- Mock API returns data
- Inject custom scripts

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

**Note**: `Fetch.fulfillRequest` replaces the entire response, and the browser will not actually request the server. This feature is particularly suitable for:
- Test the frontend's performance when the API returns different status codes
- Offline debugging
- Rapid prototyping

### Replace page JS or CSS

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

## Practice 3: Block specific requests (advertisements/pictures/statistics)

Blocking unnecessary requests can significantly speed up page loading and reduce bandwidth consumption.

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

Optional abort reason (`errorReason`):
- `BlockedByClient` — most common blocking
- `AddressUnreachable`
- `ConnectionAborted`
- `ConnectionRefused`
- `ConnectionReset`
- `InternetDisconnected`
- `NameNotResolved`
- `TimedOut`

---

## Practical Combat 4: Automatic page turning and crawling of SPA pages

SPA (Single Page Application) sites are difficult to crawl with traditional `requests` because the content is loaded dynamically via JavaScript. CDP can listen to XHR/Fetch requests and extract data.

```python
def crawl_spa():
    """抓取 SPA 页面的 API 数据"""
    
    captured_data = []
    
    def handle_network(msg):
        params = msg.get('params', {})
        method = msg.get('method', '')
        
        if method == 'Network.responseReceived':
            resp = params['response']
            url = resp['url']
            
            # 识别 API 请求（根据 URL 特征）
            if '/api/' in url or '/graphql' in url:
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
                        'body': body[:500]  # 只保存前 500 字符
                    })
    
    # 导航
    cmd(ws, 'Network.enable')
    cmd(ws, 'Page.navigate', {'url': 'https://example-spa.com/list'})
    
    time.sleep(3)  # 等待页面加载
    
    # 模拟翻页：点击"下一页"按钮
    cmd(ws, 'Runtime.evaluate', {
        'expression': 'document.querySelector(".next-page").click()',
        'returnByValue': True
    })
    
    time.sleep(2)
    
    # 再翻一页
    cmd(ws, 'Runtime.evaluate', {
        'expression': 'document.querySelector(".next-page").click()',
        'returnByValue': True
    })
    
    time.sleep(2)
    
    return captured_data
```

This method is more efficient than traditional Selenium + parsing HTML, because you directly get the original JSON data returned by the API, eliminating the step of parsing HTML.

### Advanced: Waiting for a specific API response

Sometimes you need to wait for an API to return before performing the next step. You can use `Network.responseReceived` + conditional judgment:

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

## Practice 5: Mock API for front-end testing

Front-end testing often requires mocking API responses. CDP allows you to implement interface mocks without modifying the code.

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

This technique is particularly useful in the following scenarios:
- **Front-end development**: The back-end API has not been written yet, the front-end needs to be mocked first
- **E2E Test**: Control API returns to ensure test stability
- **Demonstration/Demo**: You can run through the entire process without the need for a real backend

---

## Practice 6: Trigger image lazy loading in advance

Many modern websites use lazy loading (loading="lazy"), where images are only loaded when they enter the viewport. If you want to capture all images, you can use CDP to trigger in advance:

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

After the images are loaded, you can also use `Page.captureScreenshot` to take a screenshot of the complete page including all images.

---

## Pitfall records and best practices

### 1. The Fetch request must respond, otherwise it will get stuck.

When `Fetch.enable` is enabled, every request matching the pattern will be suspended until you call `continueRequest`, `fulfillRequest` or `failRequest`. **If you don't handle a request, the page will wait forever** and other requests will also be blocked.

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

### 2. Pitfalls of Base64 encoding

The `body` of `Fetch.fulfillRequest` requires Base64 encoding, and so does the `postData` of `Fetch.continueRequest`. But not all languages ​​and libraries' Base64 implementations are compatible:

```python
import base64

# 正确做法
body = '{"key": "value"}'
encoded = base64.b64encode(body.encode()).decode()  # 标准 Base64

# 注意：不是 URL-safe 的 base64
encoded_wrong = base64.urlsafe_b64encode(body.encode()).decode()  # ❌
```

### 3. Conflict in using Fetch and Network domains at the same time

If you enable both `Fetch.enable` and `Network.enable`, requests intercepted by the Fetch domain may appear as `(canceled)` in the Network domain because the request is actually suspended. This is normal behavior and does not mean the request failed.

Solution: **Only use Fetch for interception and use the `headers` parameter in `Fetch.continueRequest` to obtain the request information** instead of relying on the Network domain.

### 4. Interception order and performance

Intercepting a large number of requests (especially 100+ requests on the initial load of the page) comes with some performance overhead. suggestion:

- Only intercept the URL patterns you need
- Specify exact URL patterns in `patterns` of `Fetch.enable` instead of `*`
- Call `Fetch.disable` when interception is not needed to close

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

### 5. Special handling of WebSocket requests

WebSocket requests (`ws://` and `wss://`) require special handling when intercepted through the Fetch domain:

```python
if url.startswith('ws://') or url.startswith('wss://'):
    # WebSocket 请求必须放行，不支持修改
    cmd(ws, 'Fetch.continueRequest', {'requestId': request_id})
    return
```

### 6. Request body acquisition restrictions

In the `Fetch.requestPaused` event, `request.postData` is only available when the request body is text. If the request body is binary data (such as file upload), `postData` may be empty.

At this time, the request body can be captured through the Network domain:

```python
# 在 Network 域中监听
# Network.requestWillBeSent 事件中有更完整的 request.postData
```

---

## Complete example: a generic network interceptor

Finally, I combined the above techniques into a complete network interceptor tool class:

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

## Summarize

CDP’s network blocking capabilities make it one of the most powerful solutions for browser automation:

- **Fetch domain** can intercept, modify, abort requests, or directly return a custom response
- **Network domain** is suitable for monitoring and obtaining response data
- **The combination of the two** can realize the complete "request → modify → get response" process
- **No proxy server required**, native Chrome support

In the next article, I will continue to delve into CDP’s **browser fingerprinting and anti-detection** topic, so stay tuned.