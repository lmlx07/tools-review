---
lang: en
title: "CDP network interception and request tampering practice: A complete guide to controlling Chrome packet capture and modification with Python"
date: "2026-06-04 14:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Network Interception
  - Web Scraping
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
# The Network domain can monitor all network activity
await cdp(ws, 'Network.enable')

```

**Can be done**: monitor requests, obtain response bodies, and block cookies
**DO NOT DO**: Modify the request before it is issued, abort the request

### Fetch domain (recommended)

The Fetch domain is a more modern API that allows you to "pause" the request, make changes in the middle, and then decide to release, modify, or abort.

```python
# When a Fetch domain is enabled, every request is "blocked"
await cdp(ws, 'Fetch.enable', {
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
import asyncio, json, urllib.request, websockets

# = = = = = = Connect CDP = = = = = =
CDP_HTTP = 'http://localhost:9222'

def get_ws():
    data = json.loads(urllib.request.urlopen(f'{CDP_HTTP}/json', timeout=5).read())
    for t in data:
        if t.get('type') == 'page':
            return t['webSocketDebuggerUrl']
    return None

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

CMD_ID = [0]

ws_url = get_ws()
await cdp(ws, 'Page.enable')
await cdp(ws, 'Network.enable')

```

This is a standard CDP connection template, and all subsequent examples are based on it.

### Listen to all network requests

```python
# Once started, all network events are pushed via WebSockets
await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
await asyncio.sleep(3)

# Keep receiving messages (with timeout)
try:
    async with asyncio.timeout(5):
        async for msg in ws:
            data = json.loads(msg)
            method = data.get('method', '')
            if method == 'Network.requestWillBeSent':
                req = data['params']['request']
                url = req['url']
                method_http = req['method']
                print(f'➡ {method_http} {url}')
            elif method == 'Network.responseReceived':
                resp = data['params']['response']
                print(f'⬅ {resp["status"]} {resp["url"]}')
except (asyncio.TimeoutError, Exception):
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
# Enable Fetch Blocking
await cdp(ws, 'Fetch.enable', {
    'patterns': [{
        'urlPattern': '*',
        'requestStage': 'Request'
    }]
})

pending_requests = {}

async def process_message(msg):
    """Process CDP messages, block and modify requests"""
    params = msg.get('params', {})
    method = msg.get('method', '')
    
    if method == 'Fetch.requestPaused':
        request_id = params['requestId']
        request = params['request']
        url = request['url']
        
        # Skip ws://and data: protocols
        if url.startswith('data:') or url.startswith('blob:'):
            await cdp(ws, 'Fetch.continueRequest', {
                'requestId': request_id
            })
            return
        
        # Modify request headers: Add custom headers
        headers = request.get('headers', {})
        headers['X-Custom-Header'] = 'my-value'
        headers['Referer'] = 'https://my-custom-referer.com/'
        
        print(f'✏ Modifying: {url[:60]}...')
        
        await cdp(ws, 'Fetch.continueRequest', {
            'requestId': request_id,
            'headers': [{'name': k, 'value': v} for k, v in headers.items()]
        })

# Navigate to the destination page
await cdp(ws, 'Page.navigate', {'url': 'https://httpbin.org/headers'})

# Ongoing message processing
try:
    async with asyncio.timeout(10):
        async for msg in ws:
            await process_message(json.loads(msg))
except (asyncio.TimeoutError, Exception):
    pass

```

**Note**: The `headers` parameter of `Fetch.continueRequest` needs to pass an `{name, value}` object array instead of an ordinary dictionary. This is the format requirement for Fetch fields.

If you want to **modify the request body** (such as a POST request), you can do this:

```python
if request['method'] == 'POST':
    # Modify post request body
    new_body = json.dumps({"modified": True, "original": request.get('postData', '')})
    await cdp(ws, 'Fetch.continueRequest', {
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
# Enable Fetch Blocking (Request + Response two phases)
await cdp(ws, 'Fetch.enable', {
    'patterns': [{
        'urlPattern': '*',
        'requestStage': 'Response'
    }]
})

async def process_response(msg):
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    request = params['request']
    url = request['url']
    
    # Block API requests only
    if '/api/' not in url:
        await cdp(ws, 'Fetch.continueRequest', {'requestId': request_id})
        return
    
    # Construct an override response
    response_body = json.dumps({
        "code": 0,
        "message": "This is mocked by CDP",
        "data": {"items": [], "total": 0}
    })
    
    print(f'🔧 Mocking API: {url[:60]}')
    
    # Use Fetch.fulfillRequest to return custom content directly
    await cdp(ws, 'Fetch.fulfillRequest', {
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
async def inject_script(msg):
    """Block JavaScript files and inject custom code"""
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    url = params['request']['url']
    
    # Block main.js only
    if 'main.js' not in url:
        await cdp(ws, 'Fetch.continueRequest', {'requestId': request_id})
        return
    
    # The original JS was replaced with our code
    custom_js = '''
    console.log("CDP injected script!");
    // Modify page title
    document.title = "[CDP Modified] " + document.title;
    // Inject global variables
    window.__CDP_INJECTED__ = true;
    '''
    
    await cdp(ws, 'Fetch.fulfillRequest', {
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
# Define blocking rules
BLOCKED_PATTERNS = [
    'google-analytics.com',
    'doubleclick.net',
    'facebook.net',
    'googlesyndication.com',
    'amazon-adsystem.com',
    '.jpg', # Block all images
    '.png',
    '.gif',
]

async def block_requests(msg):
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    url = params['request']['url']
    
    # Check if the block list is hit
    for pattern in BLOCKED_PATTERNS:
        if pattern in url:
            print(f'🚫 Blocked: {url[:60]}')
            # Use Fetch.failRequest to fail the request
            await cdp(ws, 'Fetch.failRequest', {
                'requestId': request_id,
                'errorReason': 'BlockedByClient'
            })
            return
    
    # Release other requests
    await cdp(ws, 'Fetch.continueRequest', {'requestId': request_id})

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
async def crawl_spa():
    """Crawl API data for spa pages"""
    
    captured_data = []
    
    async def handle_response(msg):
        """Process a single network response message"""
        params = msg.get('params', {})
        if msg.get('method') != 'Network.responseReceived':
            return
        
        resp = params['response']
        url = resp['url']
        
        # Identify API requests (based on URL characteristics)
        if '/api/' not in url and '/graphql' not in url:
            return
        
        request_id = params['requestId']
        
        # Get Response Body
        result = await cdp(ws, 'Network.getResponseBody', {
            'requestId': request_id
        })
        
        if 'body' in result:
            body = result['body']
            print(f'📦 Captured API: {url[:50]}')
            print(f'   Data size: {len(body)} bytes')
            captured_data.append({
                'url': url,
                'body': body[:500] # Only the first 500 characters are saved
            })
    
    async def process_events(duration):
        """Process WebSocket messages (up to duration seconds)"""
        end = asyncio.get_event_loop().time() + duration
        try:
            async with asyncio.timeout(duration):
                async for msg in ws:
                    await handle_response(json.loads(msg))
        except (asyncio.TimeoutError, Exception):
            pass
    
    # Navigation
    await cdp(ws, 'Network.enable')
    await cdp(ws, 'Page.navigate', {'url': 'https://example-spa.com/list'})
    
    # Wait for page load and capture initial requests
    await process_events(3)
    
    # Mock Page Turn: Click the "Next" button
    await cdp(ws, 'Runtime.evaluate', {
        'expression': 'document.querySelector(".next-page").click()',
        'returnByValue': True
    })
    
    # Capture API responses after page turn
    await process_events(2)
    
    # Turn another page
    await cdp(ws, 'Runtime.evaluate', {
        'expression': 'document.querySelector(".next-page").click()',
        'returnByValue': True
    })
    
    await process_events(2)
    
    return captured_data


```

This method is more efficient than traditional Selenium + parsing HTML, because you directly get the original JSON data returned by the API, eliminating the step of parsing HTML.

### Advanced: Waiting for a specific API response

Sometimes you need to wait for an API to return before performing the next step. You can use `Network.responseReceived` + conditional judgment:

```python
async def wait_for_api(ws, url_pattern, timeout=10):
    """Wait for a specific API request to complete"""
    import re
    pattern = re.compile(url_pattern)
    
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                if data.get('method') == 'Network.responseReceived':
                    url = data['params']['response']['url']
                    if pattern.search(url):
                        request_id = data['params']['requestId']
                        result = await cdp(ws, 'Network.getResponseBody', {
                            'requestId': request_id
                        })
                        return json.loads(result.get('body', '{}'))
    except (asyncio.TimeoutError, Exception):
        pass
    
    return None

# Usage Example
data = await wait_for_api(ws, r'/api/products\?page=2')
if data:
    print(f'Got {len(data.get("items", []))} products')

```

---

## Practice 5: Mock API for front-end testing

Front-end testing often requires mocking API responses. CDP allows you to implement interface mocks without modifying the code.

```python
# Mock Configuration: URL Mode - > Simulate Response
MOCK_CONFIG = {
    '/api/user/info': {
        'code': 0,
        'data': {
            'id': 10001,
            'name': 'Test User',
            'avatar': 'https://example.com/avatar.png',
            'vip': True
        }
    },
    '/api/products/list': {
        'code': 0,
        'data': {
            'items': [
                {'id': 1, 'name': 'Product A', 'price': 99.00},
                {'id': 2, 'name': 'Product B', 'price': 199.00},
            ],
            'total': 2,
            'page': 1
        }
    }
}

# Simulate 500 Error
MOCK_ERROR = {
    '/api/error/test': {
        'status': 500,
        'body': {'code': -1, 'message': 'Internal server error'}
    }
}

async def handle_mock(msg):
    params = msg.get('params', {})
    if msg.get('method') != 'Fetch.requestPaused':
        return
    
    request_id = params['requestId']
    url = params['request']['url']
    
    # Check if the Mock configuration is matched
    for pattern, mock_data in MOCK_CONFIG.items():
        if pattern in url:
            print(f'🎭 Mocking: {url[:50]}')
            body = json.dumps(mock_data)
            await cdp(ws, 'Fetch.fulfillRequest', {
                'requestId': request_id,
                'responseCode': 200,
                'responseHeaders': [
                    {'name': 'Content-Type', 'value': 'application/json'}
                ],
                'body': base64.b64encode(body.encode()).decode()
            })
            return
    
    # Check for error simulations
    for pattern, error_data in MOCK_ERROR.items():
        if pattern in url:
            print(f'💥 Simulating error: {url[:50]}')
            body = json.dumps(error_data['body'])
            await cdp(ws, 'Fetch.fulfillRequest', {
                'requestId': request_id,
                'responseCode': error_data['status'],
                'responseHeaders': [
                    {'name': 'Content-Type', 'value': 'application/json'}
                ],
                'body': base64.b64encode(body.encode()).decode()
            })
            return
    
    # Release unconfigured requests
    await cdp(ws, 'Fetch.continueRequest', {'requestId': request_id})

```

This technique is particularly useful in the following scenarios:
- **Front-end development**: The back-end API has not been written yet, the front-end needs to be mocked first
- **E2E Test**: Control API returns to ensure test stability
- **Demonstration/Demo**: You can run through the entire process without the need for a real backend

---

## Practice 6: Trigger image lazy loading in advance

Many modern websites use lazy loading (loading="lazy"), where images are only loaded when they enter the viewport. If you want to capture all images, you can use CDP to trigger in advance:

```python
async def trigger_all_images(ws):
    """Trigger all lazy loading images in the page to start loading"""
    
    # Block image loading via Fetch domain
    await cdp(ws, 'Fetch.enable', {
        'patterns': [
            {'urlPattern': '*.jpg', 'requestStage': 'Request'},
            {'urlPattern': '*.png', 'requestStage': 'Request'},
            {'urlPattern': '*.webp', 'requestStage': 'Request'},
            {'urlPattern': '*.gif', 'requestStage': 'Request'}
        ]
    })
    
    # Scroll to the bottom to trigger lazy loading
    await cdp(ws, 'Runtime.evaluate', {
        'expression': '''
        (async () => {
            const delay = ms => new Promise(r => setTimeout(r, ms));
            const scrollStep = 500;
            const totalScroll = document.body.scrollHeight;
            
            for (let y = 0; y < totalScroll; y += scrollStep) {
                window.scrollTo(0, y);
                await delay(300); // Wait for the image to trigger loading
            }
            
            // Back to top
            window.scrollTo(0, 0);
            return 'Scrolled full page';
        })()
        ''',
        'returnByValue': True,
        'awaitPromise': True
    })
    
    # Collect all image URLs
    images = await cdp(ws, 'Runtime.evaluate', {
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
# ❌ Error: only partial request processed
# Unhandled requests will stay suspended

# ✅ Correct: All requests are handled accordingly
async def safe_handler(msg):
    if msg.get('method') != 'Fetch.requestPaused':
        return
    request_id = msg['params']['requestId']
    
    if should_intercept(msg):
        do_intercept(msg)
    else:
        # Always release unhandled requests
        await cdp(ws, 'Fetch.continueRequest', {'requestId': request_id})

```

### 2. Pitfalls of Base64 encoding

The `body` of `Fetch.fulfillRequest` requires Base64 encoding, and so does the `postData` of `Fetch.continueRequest`. But not all languages ​​and libraries' Base64 implementations are compatible:

```python
import base64

# Correct approach:
body = '{"key": "value"}'
encoded = base64.b64encode(body.encode()).decode() # Standard Base64

# Note: Not base64 for URL-safe
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
# Precision Intercept
await cdp(ws, 'Fetch.enable', {
    'patterns': [
        {'urlPattern': '*/api/*', 'requestStage': 'Request'},
        {'urlPattern': '*.json', 'requestStage': 'Response'}
    ]
})
# Don't use {'urlPattern': '*'} unless you really need to block all requests

```

### 5. Special handling of WebSocket requests

WebSocket requests (`ws://` and `wss://`) require special handling when intercepted through the Fetch domain:

```python
if url.startswith('ws://') or url.startswith('wss://'):
    # WebSocket request must be released, modification is not supported
    await cdp(ws, 'Fetch.continueRequest', {'requestId': request_id})
    return

```

### 6. Request body acquisition restrictions

In the `Fetch.requestPaused` event, `request.postData` is only available when the request body is text. If the request body is binary data (such as file upload), `postData` may be empty.

At this time, the request body can be captured through the Network domain:

```python
# Listen in the Network domain
# More complete request.postData in Network.requestWillBeSent event

```

---

## Complete example: a generic network interceptor

Finally, I combined the above techniques into a complete network interceptor tool class:

```python
import asyncio, json, time, base64, urllib.request, websockets

class CDPNetworkInterceptor:
    """CDP Network Interceptor"""
    
    def __init__(self, host='localhost:9222'):
        self.host = host
        self.ws = None
        self.blocked_count = 0
        self.mock_count = 0
    
    async def connect(self):
        """Connect to CDP"""
        data = json.loads(urllib.request.urlopen(
            f'http://{self.host}/json', timeout=5).read())
        ws_url = data[0]['webSocketDebuggerUrl']
        self.ws = await websockets.connect(ws_url, max_size=2**24)
        await self.cdp('Page.enable')
        await self.cdp('Network.enable')
        return self
    
    async def cdp(self, method, params=None):
        return await cdp(self.ws, method, params)
    
    async def start_intercept(self, patterns=None):
        """Start Request Blocking"""
        if patterns is None:
            patterns = [{'urlPattern': '*', 'requestStage': 'Request'}]
        await self.cdp('Fetch.enable', {'patterns': patterns})
        print(f'Intercept started with {len(patterns)} pattern(s)')
    
    async def stop_intercept(self):
        """Stop blocking"""
        await self.cdp('Fetch.disable')
        print('Intercept stopped')
    
    async def run(self, url, handlers=None, timeout=15):
        """
        Open page and run intercept handler
        
        Args:
            url: Page to open
            handlers: Custom async handler functions, receives request_id, url, params
            timeout: Run duration (seconds)
        """
        if handlers is None:
            handlers = {'on_request': None, 'on_response': None}
        
        await self.cdp('Page.navigate', {'url': url})
        
        try:
            async with asyncio.timeout(timeout):
                async for msg in self.ws:
                    try:
                        data = json.loads(msg)
                        if data.get('method') == 'Fetch.requestPaused':
                            params = data['params']
                            request_id = params['requestId']
                            url = params['request']['url']
                            
                            # Skip special protocols
                            if url.startswith('data:') or url.startswith('blob:') or url.startswith('ws'):
                                await self.cdp('Fetch.continueRequest', {'requestId': request_id})
                                continue
                            
                            # Call custom handler
                            if handlers.get('on_request'):
                                handled = await handlers['on_request'](request_id, url, params)
                                if handled:
                                    continue
                            
                            # Default: release request
                            await self.cdp('Fetch.continueRequest', {'requestId': request_id})
                    except Exception:
                        continue
        except asyncio.TimeoutError:
            pass
    
    async def close(self):
        if self.ws:
            await self.ws.close()


# ====== Usage Example ======
async def demo():
    # Create an interceptor
    interceptor = CDPNetworkInterceptor()
    await interceptor.connect()
    await interceptor.start_intercept()
    
    # Custom request handler
    async def block_ads(rid, url, params):
        if 'google-analytics.com' in url:
            await interceptor.cdp('Fetch.failRequest', {
                'requestId': rid,
                'errorReason': 'BlockedByClient'
            })
            return True
        return False
    
    # Visit page, block ads
    await interceptor.run('https://example.com', {
        'on_request': block_ads
    })
    
    await interceptor.stop_intercept()
    await interceptor.close()

asyncio.run(demo())


```

---

## Summarize

CDP’s network blocking capabilities make it one of the most powerful solutions for browser automation:

- **Fetch domain** can intercept, modify, abort requests, or directly return a custom response
- **Network domain** is suitable for monitoring and obtaining response data
- **The combination of the two** can realize the complete "request → modify → get response" process
- **No proxy server required**, native Chrome support




*Previous: The Complete Guide to Chrome DevTools Protocol (CDP): The Ultimate Solution to Controlling Your Browser with Python*

*Next up: CDP browser fingerprinting and anti-detection practice: using Python to modify fingerprints to bypass automated detection*