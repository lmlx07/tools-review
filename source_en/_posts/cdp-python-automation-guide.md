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
│  Your Python Script │ ◄──────────────────────► │  Chrome Browser    │
│                  │    ws://localhost:9222     │                  │
└─────────────────┘                            │  ┌────────────┐  │
                                               │  │  Tab 1      │  │
                                               │  ├────────────┤  │
                                               │  │  Tab 2      │  │
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
           │     Playwright / Puppeteer    │  ← High-level, friendliest API
           ├─────────────────────────┤
           │        Selenium WebDriver       │  ← Middle layer, cross-browser standard
           ├─────────────────────────┤
           │  Chrome DevTools Protocol (CDP) │  ← Lowest-level, most powerful
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
| Dependencies | websockets only | Browser installation required | WebDriver required |

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
pip install websockets
```

That’s right, you can communicate with Chrome using just `websockets`. There is no need to install ChromeDriver or download browser binaries.

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
    "title": "New Tab",
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
import asyncio
import json
import urllib.request
import websockets

# ========== Step 1: Get the WebSocket URL of the page ==========

CDP_HTTP = 'http://localhost:9222'

def get_page_ws(pattern=''):
    """Get the WebSocket URL of the first page matching pattern"""
    data = json.loads(
        urllib.request.urlopen(f'{CDP_HTTP}/json', timeout=5).read()
    )
    for page in data:
        if pattern in page.get('url', ''):
            return page['webSocketDebuggerUrl']
    # If there is no match, the first page will be taken by default.
    return data[0]['webSocketDebuggerUrl'] if data else None

CMD_ID = [0]

async def cdp(ws, method, params=None):
    """Send CDP command and wait for the result to be returned"""
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
        # Enable necessary domains
        await cdp(ws, 'Page.enable')
        await cdp(ws, 'Runtime.enable')

        # Navigate to target page
        result = await cdp(ws, 'Page.navigate', {'url': 'https://www.example.com'})
        print(f'Navigation started, frameId: {result.get("frameId")}')

        # Execute JavaScript on the current page
        result = await cdp(ws, 'Runtime.evaluate', {
            'expression': 'document.title',
            'returnByValue': True
        })
        print(f'Page title: {result["result"]["value"]}')

asyncio.run(main())
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

# Full page screenshot
result = await cdp(ws, 'Page.captureScreenshot', {
    'format': 'png'
})

with open('screenshot.png', 'wb') as f:
    f.write(base64.b64decode(result['data']))
print('Screenshot saved as screenshot.png')


# Screenshot (crop) of specified area
# clip = x, y, width, height
result = await cdp(ws, 'Page.captureScreenshot', {
    'format': 'png',
    'clip': {'x': 0, 'y': 0, 'width': 800, 'height': 600, 'scale': 1}
})

```

> **Tips**: `fromSurface: True` will intercept the complete rendering result (including GPU composition layer), set to `False` to only intercept the viewport content.

### 2. Execute JavaScript and get the return value

This is one of the most powerful capabilities of CDP - execute arbitrary JS in the context of the page and get the return value.

```python
# Get page information
result = await cdp(ws, 'Runtime.evaluate', {
    'expression': 'JSON.stringify({title: document.title, url: location.href, cookies: document.cookie})',
    'returnByValue': True
})
page_info = json.loads(result['result']['value'])
print(page_info)

# Get the text content of an element
result = await cdp(ws, 'Runtime.evaluate', {
    'expression': 'document.querySelector("h1").innerText',
    'returnByValue': True
})
print(f'H1 text: {result["result"]["value"]}')

# Modify the page (can perform any JS operation)
await cdp(ws, 'Runtime.evaluate', {
    'expression': 'document.title = "Title modified by CDP"',
    'returnByValue': True
})

```

**Important Parameters**:
- `returnByValue`: When set to `true`, the return value will be serialized into JSON; when set to `false` (default), an object reference is returned, which can be further viewed with `Runtime.getProperties`
- `awaitPromise`: When set to `true`, it will wait for Promise resolution to complete before returning (applicable to asynchronous operations)

### 3. DOM operations

CDP's DOM operations are implemented through `DOM` fields, using "node IDs" to locate elements.

```python
# Get the document root node
result = await cdp(ws, 'DOM.getDocument')
root_node_id = result['root']['nodeId']

# Find elements by selector
result = await cdp(ws, 'DOM.querySelector', {
    'nodeId': root_node_id,
    'selector': 'div.content'
})
content_node_id = result['nodeId']

# Get the HTML of an element
result = await cdp(ws, 'DOM.getOuterHTML', {
    'nodeId': content_node_id
})
print(f'Element HTML: {result["outerHTML"][:200]}...')

# Modify element attributes
await cdp(ws, 'DOM.setAttributeValue', {
    'nodeId': content_node_id,
    'name': 'style',
    'value': 'background-color: yellow;'
})

```

> **Features of CDP**: DOM operations are based on the **internal representation** of Chrome's Blink rendering engine, bypassing the page's JavaScript framework. This means that even if the page uses React/Vue, you can directly manipulate the final rendering result.

### 4. Network interception and monitoring

This is the most commonly used feature in crawlers and penetration testing. CDP can capture every request made by a page.

```python
# Enable network domain
await cdp(ws, 'Network.enable')

# Store event callbacks
event_handlers = {}

def on(event_name):
    """Decorator: register CDP event handler"""
    def decorator(fn):
        event_handlers[event_name] = fn
        return fn
    return decorator

@on('Network.requestWillBeSent')
async def on_request(event_data):
    """Called every time there is a network request"""
    request = event_data['params']['request']
    url = request['url']
    method = request['method']
    print(f'[{method}] {url}')

async def event_listener(ws):
    """Background task: Continuously receive CDP events"""
    async for msg in ws:
        try:
            data = json.loads(msg)
            if 'method' in data:
                handler = event_handlers.get(data['method'])
                if handler:
                    await handler(data)
        except Exception as e:
            print(f'Event listener error: {e}')

# Start event listening task
listener_task = asyncio.create_task(event_listener(ws))

# Navigate to page
await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})

# ...The page is loading, the event listener will output all requests...
await asyncio.sleep(5) # Wait for page to load


```

**Advanced usage of Network domain**:

```python
# Block specific URL patterns
await cdp(ws, 'Network.setBlockedURLs', {
    'urls': ['*.jpg', '*.png', '*.gif'] # Block all pictures
})

# Simulate weak network environment
await cdp(ws, 'Network.emulateNetworkConditions', {
    'offline': False,
    'latency': 300, # Delay 300ms
    'downloadThroughput': 500 * 1024, # Download 500 KB/s
    'uploadThroughput': 100 * 1024 # Upload 100 KB/s
})

# Get response body
# First get the requestId in the Network.responseReceived event
# Then:
result = await cdp(ws, 'Network.getResponseBody', {
    'requestId': request_id
})
print(f'Response body: {result["body"][:500]}')
print(f'Base64 encoded: {result["base64Encoded"]}')


```

### 5. Mouse and keyboard simulation

CDP's `Input` field can simulate mouse clicks and keyboard input, which is key to implementing RPA (Robotic Process Automation).

```python
async def click(ws, x, y, button='left'):
    """Click at the specified coordinates"""
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
    """Enter text"""
    await cdp(ws, 'Input.insertText', {'text': text})

async def press_enter(ws):
    """Press Enter"""
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

# Usage example: Autofill forms
await click(ws, 500, 300) # Click on the input box
await type_text(ws, 'hello@example.com') # Enter email
await press_enter(ws) # submit


```

---

## Advanced skills

### 1. Bypass automated detection

Selenium and Playwright leave automation traces in the browser (e.g. `navigator.webdriver` property is `true`). CDP can be controlled from a lower level and is harder to detect.

```python
# Inject scripts before page loads to override automation features
await cdp(ws, 'Page.addScriptToEvaluateOnNewDocument', {
    'source': '''
        // Override webdriver properties
        Object.defineProperty(navigator, 'webdriver', {
            get: () => undefined
        });
        
        // Override chrome object
        window.chrome = {
            runtime: {},
            loadTimes: function() {},
            csi: function() {},
            app: {}
        };
        
        // Coverage permission query
        const originalQuery = navigator.permissions.query;
        navigator.permissions.query = (params) => (
            params.name === 'notifications' ?
                Promise.resolve({state: Notification.permission}) :
                originalQuery(params)
        );
        
        // Override plugins
        Object.defineProperty(navigator, 'plugins', {
            get: () => [1, 2, 3, 4, 5]
        });
        
        // Override languages
        Object.defineProperty(navigator, 'languages', {
            get: () => ['zh-CN', 'zh', 'en']
        });
    '''
})

# The above script will be automatically executed on every new page
# and then navigate
await cdp(ws, 'Page.navigate', {'url': 'https://bot.sannysoft.com/'})

```

> **Note**: Anti-crawling technology is constantly evolving, and what is shown here is only basic protection. In actual use, it needs to be adjusted according to the detection mechanism of the target website.

### 2. Handling new windows/new tabs

```python
# Listen to the Target.targetCreated event
# When a new window opens, automatically get its WebSocket URL

@on('Target.targetCreated')
async def on_target_created(event_data):
    target_info = event_data['params']['targetInfo']
    print(f'New tab: {target_info["url"]}')
    # The WebSocket URL of the new page can be obtained via CDP_HTTP/json

# Enable the Target domain to receive events
await cdp(ws, 'Target.setAutoAttach', {
    'autoAttach': True,
    'flatten': True,
    'waitForDebuggerOnStart': False
})
```

### 3. Performance tracking

```python
# Start performance tracking
await cdp(ws, 'Performance.enable')

# navigation
await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
await asyncio.sleep(3)

# Get performance metrics
result = await cdp(ws, 'Performance.getMetrics')
metrics = {m['name']: m['value'] for m in result['metrics']}

print(f'DOMContentLoaded: {metrics.get("DomContentLoaded", "N/A")} ms')
print(f'First Paint: {metrics.get("FirstPaint", "N/A")} ms')
print(f'JS Heap Size: {metrics.get("JSHeapUsedSize", "N/A")} bytes')
print(f'Layouts: {metrics.get("LayoutCount", "N/A")}')
print(f'Style Recalculations: {metrics.get("RecalcStyleCount", "N/A")}')

```

### 4. Generate PDF

```python
result = await cdp(ws, 'Page.printToPDF', {
    'paperWidth': 8.27, # A4 width (inches)
    'paperHeight': 11.69, # A4 height
    'marginTop': 0.4,
    'marginBottom': 0.4,
    'marginLeft': 0.4,
    'marginRight': 0.4,
    'printBackground': True,
    'displayHeaderFooter': True,
    'headerTemplate': '<span style="font-size:10px;margin-left:10px;">Title</span>',
    'footerTemplate': '<span style="font-size:10px;margin-right:10px;">Page <span class="pageNumber"></span> of <span class="totalPages"></span></span>'
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
CDP Command Line Screenshot Tool

Usage:
    python cdp_screenshooter.py https://example.com -o screenshot.png -w 1920 -h 1080
"""
import asyncio
import json
import urllib.request
import websockets
import base64
import argparse

# ========== Tool functions ==========

def find_page_ws(cdp_url, pattern=''):
    data = json.loads(urllib.request.urlopen(f'{cdp_url}/json', timeout=5).read())
    for page in data:
        if pattern.lower() in page.get('url', '').lower():
            return page['webSocketDebuggerUrl']
    return data[0]['webSocketDebuggerUrl'] if data else None

CMD_ID = [0]

async def cdp(ws, method, params=None):
    """Send CDP command and wait for the result to be returned"""
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    request = {'id': cmd_id, 'method': method, 'params': params or {}}
    await ws.send(json.dumps(request))
    async for msg in ws:
        response = json.loads(msg)
        if response.get('id') == cmd_id:
            return response.get('result', {})

class CDPConnection:
    """CDP connection encapsulation (async version)"""
    
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
        """Navigate to the URL and wait for the page to finish loading"""
        await self.cdp('Page.navigate', {'url': url})
        # Wait for the page to load (production environments should listen to the Page.loadEventFired event)
        await asyncio.sleep(3)
    
    async def screenshot(self, output_path, width=1920, height=1080):
        """Take a screenshot of the page"""
        # Set viewport size
        await self.cdp('Emulation.setDeviceMetricsOverride', {
            'width': width,
            'height': height,
            'deviceScaleFactor': 1,
            'mobile': False
        })
        await asyncio.sleep(0.5)
        
        # screenshot
        result = await self.cdp('Page.captureScreenshot', {
            'format': 'png'
        })
        
        with open(output_path, 'wb') as f:
            f.write(base64.b64decode(result['data']))
        print(f'Screenshot saved: {output_path} ({width}x{height})')
    
    async def close(self):
        await self.ws.close()


async def main():
    parser = argparse.ArgumentParser(description='CDP command line screenshot tool')
    parser.add_argument('url', help='Target URL')
    parser.add_argument('-o', '--output', default='screenshot.png', help='Output file path')
    parser.add_argument('-w', '--width', type=int, default=1920, help='Viewport width')
    parser.add_argument('-H', '--height', type=int, default=1080, help='Viewport height')
    parser.add_argument('--cdp', default='http://localhost:9222', help='CDP HTTP address')
    parser.add_argument('--pattern', default='', help='Match specific tab')
    args = parser.parse_args()
    
    print(f'Connecting to Chrome: {args.cdp}')
    ws_url = find_page_ws(args.cdp, args.pattern)
    if not ws_url:
        print('No available page found')
        return
    
    print(f'WebSocket: {ws_url[:60]}...')
    
    async with CDPConnection(ws_url) as cdp_conn:
        print(f'Navigating to: {args.url}')
        await cdp_conn.navigate(args.url)
        await cdp_conn.screenshot(args.output, args.width, args.height)
    
    print('Done!')


if __name__ == '__main__':
    asyncio.run(main())

```

How to use:

```bash
# Basic usage
python cdp_screenshooter.py https://www.example.com

# Specify output and dimensions
python cdp_screenshooter.py https://www.baidu.com -o baidu.png -w 1920 -H 1080

# Capture specific tab page
python cdp_screenshooter.py https://example.com --pattern "login"

```

---

## Pitfall records and best practices

### FAQ

#### ❌ Connection Refused

```
websockets.exceptions.InvalidStatusCode: server rejected WebSocket connection: HTTP 500
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
result = await cdp(ws, 'Runtime.evaluate', {
    'expression': '''
        (() => {
            const ta = document.querySelector('.xterm-helper-textarea');
            if (!ta) return false;
            ta.value = 'command to enter';
            ta.dispatchEvent(new Event('input', {bubbles: true}));
            return true;
        })()
    ''',
    'returnByValue': True
})
```

### Summary of best practices

1. **Always `enable` before using**: Each field must call the corresponding `enable` method before using it.
2. **Async tasks for event monitoring**: CDP events are actively pushed through WebSocket. Use `asyncio.create_task()` to handle them.
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

*Next up: CDP network interception and request tampering practice: A complete guide to controlling Chrome packet capture and modification with Python*