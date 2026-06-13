---
lang: en
title: "CDP Event System Guide: Listening to Browser Events with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Automation
  - Event-Driven
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to the Chrome DevTools Protocol (CDP) event-driven architecture. Learn how to listen for CDP events, one-shot vs persistent listener patterns, common event types (network requests, page loading, console messages), event filtering & throttling, and a complete event manager class.
---

> **Summary in one sentence**: CDP's event system is the "message bus" of browser automation — instead of polling for state changes, you let the browser notify you when events happen, enabling truly reactive automation scripts.

---

## Table of Contents

1. [Why CDP Events Matter](#why-cdp-events-matter)
2. [Prerequisites: Connecting to Chrome](#prerequisites-connecting-to-chrome)
3. [Understanding the CDP Event Model](#understanding-the-cdp-event-model)
4. [Listening to Events: Basic Pattern](#listening-to-events-basic-pattern)
5. [One-Shot vs Persistent Listening](#one-shot-vs-persistent-listening)
6. [Common CDP Events & Applications](#common-cdp-events--applications)
7. [Event Filtering & Throttling](#event-filtering--throttling)
8. [Complete Reference: CDP Event Manager](#complete-reference-cdp-event-manager)
9. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why CDP Events Matter

In previous articles, we always called CDP commands "actively" — send a request, wait for a response. But some scenarios require "reactive" responses:

| Scenario | Active Polling | CDP Event Listening |
|----------|---------------|---------------------|
| Wait for page load | `Page.loadEventFired` post-processing | ✅ Notified on fire |
| Monitor network | Poll `Network.getCookies` | ✅ Real-time push |
| Catch JS errors | Poll `Runtime.evaluate` | ✅ Automatic notification |
| Detect DOM changes | MutationObserver polling | ✅ CDP DOM events push |

CDP events transform automation from "polling" to "waiting" — more timely and efficient.

---

## Prerequisites: Connecting to Chrome

Using the standard CDP connection pattern:

```python
import asyncio, json, websockets

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    """Send CDP command and wait for result"""
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]:
            return data.get("result", {})

async def attach_to_page(ws):
    """Connect to a page target and return session_id"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

---

## Understanding the CDP Event Model

The CDP WebSocket connection carries two types of messages:

1. **Command responses** (with `id` field) — return values from `cdp()` calls
2. **Event pushes** (with `method` field, no `id`) — browser-initiated notifications

```python
# Example message received from WebSocket
{
    "method": "Network.requestWillBeSent",  # ← This is an event
    "params": {
        "requestId": "12345",
        "request": {"url": "https://example.com/api", "method": "GET"},
        "timestamp": 1234567.89
    }
}
```

Event push characteristics:
- **No `id` field** — only `method` and `params`
- **Domain must be enabled first** — e.g., `Network.enable` before receiving network events
- **Arrive asynchronously** — can come at any time

---

## Listening to Events: Basic Pattern

### Simple Event Listener

```python
async def listen_events(ws, session_id, timeout=30):
    """Listen for CDP events, return on timeout or specific event"""
    # Enable Network domain first
    await cdp(ws, "Network.enable", session_id=session_id)
    
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                # Skip command responses (have id field)
                if "id" in data:
                    continue
                
                method = data.get("method", "")
                params = data.get("params", {})
                
                print(f"[Event] {method}")
                
                # Example: stop when page loads
                if method == "Page.loadEventFired":
                    print("Page loaded!")
                    return params
                
                # Example: detect network requests
                if method == "Network.requestWillBeSent":
                    req = params.get("request", {})
                    print(f"  Request: {req.get('url', '')[:80]}")
    except asyncio.TimeoutError:
        print("Listener timeout")
```

### Using the Event Listener

```python
async def demo_event_listener():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        
        # Enable event domains
        await cdp(ws, "Page.enable", session_id=session_id)
        await cdp(ws, "Network.enable", session_id=session_id)
        await cdp(ws, "Runtime.enable", session_id=session_id)
        
        # Start background listener task
        listener = asyncio.create_task(
            listen_events(ws, session_id, timeout=15)
        )
        
        # Navigate (events will arrive during navigation)
        await cdp(ws, "Page.navigate",
                  {"url": "https://example.com"}, session_id)
        
        await listener
```

---

## One-Shot vs Persistent Listening

### One-Shot Listener: Wait for a Specific Event

```python
async def wait_for_event(ws, session_id, target_method, timeout=30):
    """Wait for a specific CDP event to fire"""
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                if data.get("method") == target_method:
                    return data.get("params", {})
    except asyncio.TimeoutError:
        return None

# Usage
async def demo_wait_once():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        await cdp(ws, "Page.enable", session_id=session_id)
        
        # Navigate and wait for load
        nav_task = asyncio.create_task(
            cdp(ws, "Page.navigate", {"url": "https://example.com"}, session_id)
        )
        result = await wait_for_event(ws, session_id, "Page.loadEventFired")
        if result:
            print(f"Page loaded, timestamp: {result.get('timestamp')}")
        await nav_task
```

### Persistent Listener: Continuous Event Processing

```python
async def persistent_listener(ws, session_id, handlers, timeout=None):
    """Persistent listener dispatching events via handlers dict"""
    try:
        async with asyncio.timeout(timeout) if timeout else nullcontext():
            async for msg in ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                method = data.get("method", "")
                if method in handlers:
                    await handlers[method](data.get("params", {}))
    except asyncio.TimeoutError:
        pass

# Define event handlers
async def on_request(event):
    req = event.get("request", {})
    print(f"Request: {req.get('url', '')[:60]}")

async def on_response(event):
    print(f"Response: {event.get('response', {}).get('status')}")

async def on_console(event):
    print(f"Console: {event.get('message', {}).get('text', '')}")

# Usage
async def demo_persistent():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        await cdp(ws, "Page.enable", session_id=session_id)
        await cdp(ws, "Network.enable", session_id=session_id)
        
        handlers = {
            "Network.requestWillBeSent": on_request,
            "Network.responseReceived": on_response,
        }
        
        # Start listener
        listener = asyncio.create_task(
            persistent_listener(ws, session_id, handlers, timeout=10)
        )
        
        await cdp(ws, "Page.navigate",
                  {"url": "https://example.com"}, session_id)
        await listener
```

---

## Common CDP Events & Applications

### Page Lifecycle Events

After enabling `Page.enable`:

| Event | Trigger | Typical Use |
|-------|---------|-------------|
| `Page.domContentEventFired` | DOM parsed | Earliest safe DOM access |
| `Page.loadEventFired` | All resources loaded | Full page ready |
| `Page.frameStartedLoading` | iframe starts loading | Sub-frame tracking |
| `Page.frameStoppedLoading` | iframe finishes | Frame status monitoring |
| `Page.lifecycleEvent` | Lifecycle phase changes | Fine-grained load control |

### Network Events

After enabling `Network.enable`:

```python
# Real-time network request monitor
async def monitor_network(ws, session_id, timeout=30):
    requests = {}
    
    async def on_request(event):
        req_id = event.get("requestId")
        requests[req_id] = {
            "url": event.get("request", {}).get("url", ""),
            "method": event.get("request", {}).get("method", ""),
            "started": event.get("timestamp")
        }
    
    async def on_response(event):
        req_id = event.get("requestId")
        if req_id in requests:
            requests[req_id]["status"] = event.get("response", {}).get("status")
            requests[req_id]["end"] = event.get("timestamp")
    
    handlers = {
        "Network.requestWillBeSent": on_request,
        "Network.responseReceived": on_response,
    }
    
    await cdp(ws, "Network.enable", session_id=session_id)
    await persistent_listener(ws, session_id, handlers, timeout)
    return requests
```

### Console Message Events

After enabling `Runtime.enable`:

```python
async def capture_console(ws, session_id, timeout=30):
    """Capture browser console output"""
    messages = []
    
    async def on_console(event):
        msg = event.get("message", {})
        messages.append({
            "level": msg.get("level", "log"),
            "text": msg.get("text", ""),
            "timestamp": msg.get("timestamp"),
        })
        print(f"[{msg.get('level')}] {msg.get('text', '')[:100]}")
    
    handlers = {"Runtime.consoleAPICalled": on_console}
    
    await cdp(ws, "Runtime.enable", session_id=session_id)
    await persistent_listener(ws, session_id, handlers, timeout)
    return messages
```

### Exception Events

```python
async def capture_exceptions(ws, session_id, timeout=30):
    """Capture uncaught page exceptions"""
    exceptions = []
    
    async def on_exception(event):
        desc = event.get("exceptionDetails", {}).get("text", "")
        url = event.get("exceptionDetails", {}).get("url", "")
        line = event.get("exceptionDetails", {}).get("lineNumber", 0)
        exceptions.append({"text": desc, "url": url, "line": line})
        print(f"Exception: {desc} at {url}:{line}")
    
    handlers = {"Runtime.exceptionThrown": on_exception}
    
    await cdp(ws, "Runtime.enable", session_id=session_id)
    await persistent_listener(ws, session_id, handlers, timeout)
    return exceptions
```

### Target Events

Essential for multi-tab management:

| Event | Trigger |
|-------|---------|
| `Target.targetCreated` | New tab/window opened |
| `Target.targetDestroyed` | Tab closed |
| `Target.targetInfoChanged` | Tab info changed |

```python
async def monitor_targets(ws, timeout=60):
    """Monitor browser tab changes"""
    targets = {}
    
    async def on_created(event):
        info = event.get("targetInfo", {})
        targets[info.get("targetId")] = info
        print(f"New tab: {info.get('title', '')} ({info.get('url', '')[:50]})")
    
    async def on_destroyed(event):
        tid = event.get("targetId")
        if tid in targets:
            print(f"Tab closed: {targets[tid].get('title', '')}")
            del targets[tid]
    
    handlers = {
        "Target.targetCreated": on_created,
        "Target.targetDestroyed": on_destroyed,
    }
    
    async with websockets.connect(CDP_URL) as ws_conn:
        await cdp(ws_conn, "Target.setDiscoverTargets", {"discover": True})
        await persistent_listener(ws_conn, None, handlers, timeout)
        return targets
```

---

## Event Filtering & Throttling

In high-frequency event scenarios (network requests, DOM changes), filtering and throttling help:

```python
import time

class EventThrottle:
    """CDP event throttle"""
    
    def __init__(self, interval=0.5):
        self.interval = interval
        self.last_time = {}
    
    def should_process(self, event_method):
        """Check if event should be processed (throttled)"""
        now = time.time()
        last = self.last_time.get(event_method, 0)
        if now - last >= self.interval:
            self.last_time[event_method] = now
            return True
        return False


# URL filter
class URLFilter:
    """URL filter for events"""
    
    def __init__(self, include_patterns=None, exclude_patterns=None):
        self.include = include_patterns or []
        self.exclude = exclude_patterns or []
    
    def match(self, url):
        if self.exclude and any(p in url for p in self.exclude):
            return False
        if self.include and not any(p in url for p in self.include):
            return False
        return True


# Combined usage
async def filtered_network_monitor(ws, session_id, url_filter, throttle):
    """Network monitor with filtering and throttling"""
    handlers = {}
    
    original_on_request = on_request  # assume defined
    
    async def throttled_handler(event):
        method = "Network.requestWillBeSent"
        if not throttle.should_process(method):
            return
        url = event.get("request", {}).get("url", "")
        if url_filter.match(url):
            await original_on_request(event)
    
    handlers["Network.requestWillBeSent"] = throttled_handler
    await persistent_listener(ws, session_id, handlers, timeout=30)
```

---

## Complete Reference: CDP Event Manager

```python
import asyncio
import json
import websockets
from typing import Callable, Dict, Any, Optional


class CDPEventManager:
    """CDP Event Manager"""
    
    def __init__(self, ws, session_id=None):
        self.ws = ws
        self.session_id = session_id
        self._handlers: Dict[str, list] = {}
        self._running = False
        self._task = None
        self._cmd_id = 0
    
    async def _cdp(self, method, params=None):
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method, "params": params or {}}
        if self.session_id:
            msg["sessionId"] = self.session_id
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    def on(self, method: str, handler: Callable):
        """Register an event listener"""
        if method not in self._handlers:
            self._handlers[method] = []
        self._handlers[method].append(handler)
    
    def off(self, method: str, handler: Callable = None):
        """Remove an event listener"""
        if handler is None:
            self._handlers.pop(method, None)
        elif method in self._handlers:
            self._handlers[method] = [
                h for h in self._handlers[method] if h != handler
            ]
    
    async def _event_loop(self):
        """Event loop"""
        while self._running:
            try:
                async with asyncio.timeout(1):
                    async for msg in self.ws:
                        data = json.loads(msg)
                        if "id" in data:
                            continue
                        method = data.get("method", "")
                        if method in self._handlers:
                            for handler in self._handlers[method]:
                                await handler(data.get("params", {}))
                        # Wildcard listener
                        if "*" in self._handlers:
                            for handler in self._handlers["*"]:
                                await handler(method, data.get("params", {}))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"Event loop error: {e}")
                break
    
    async def start(self):
        """Start event listening"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._event_loop())
    
    async def stop(self):
        """Stop event listening"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
    
    async def wait_for(self, method: str, timeout: float = 30):
        """Wait for a specific event (one-shot)"""
        future = asyncio.get_event_loop().create_future()
        
        async def handler(params):
            if not future.done():
                future.set_result(params)
        
        self.on(method, handler)
        try:
            return await asyncio.wait_for(future, timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self.off(method, handler)
    
    async def enable_domain(self, domain: str):
        """Enable an event domain"""
        await self._cdp(f"{domain}.enable")
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await attach_to_page(ws)
    mgr = CDPEventManager(ws, session_id)
    
    # Register event handlers
    mgr.on("Network.requestWillBeSent", lambda e:
        print(f"Request: {e.get('request', {}).get('url', '')[:60]}"))
    
    mgr.on("Runtime.consoleAPICalled", lambda e:
        print(f"Console: {e.get('message', {}).get('text', '')[:100]}"))
    
    # Start listening
    await mgr.start()
    
    # Enable event domains
    await mgr.enable_domain("Network")
    await mgr.enable_domain("Runtime")
    
    # Navigate and wait for load
    await mgr._cdp("Page.navigate", {"url": "https://example.com"})
    result = await mgr.wait_for("Page.loadEventFired", timeout=15)
    
    # Stop listening
    await mgr.stop()
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Forgetting to Enable Domains

```python
# ❌ Network not enabled, no events received
listener = asyncio.create_task(listen_events(ws, session_id))

# ✅ Must enable first
await cdp(ws, "Network.enable", session_id=session_id)
await cdp(ws, "Page.enable", session_id=session_id)
```

### Pitfall 2: `async for` Monopolizes WebSocket

`async for msg in ws:` continuously reads from WebSocket, blocking other operations:

```python
# ✅ Run event loop in background with asyncio.create_task
listener = asyncio.create_task(event_loop(ws, handlers))
await navigate(ws, session_id, url)
await listener

# ✅ Or use wait_for for single-event waiting
result = await mgr.wait_for("Page.loadEventFired")
```

### Pitfall 3: Events May Be Lost

Race condition between enabling domain and listening:

```python
# ❌ Navigate first, enable later — may miss early events
await navigate(ws, session_id, url)
await cdp(ws, "Network.enable", session_id=session_id)

# ✅ Enable first, then navigate
await cdp(ws, "Network.enable", session_id=session_id)
await navigate(ws, session_id, url)
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Domain enable order | Enable first, then operate |
| Listening mode | Use persistent for UI events, `wait_for` for one-shot |
| Cleanup | Call `stop()` when done to prevent coroutine leaks |
| Error handling | Wrap handlers in try/catch to prevent single-event crashes |
| Timeout guard | Add total timeout for persistent listeners |

---

> **Summary**: CDP's event system is the foundation for building reactive automation scripts. By listening to network requests, page lifecycle events, console logs, JS exceptions, and more, you can write automation tools that are far more efficient and timely than polling-based approaches.

*Previous: CDP WebSocket Debugging Guide: Intercept and Inspect WebSocket Frames with Python*

*Next up: CDP Target Management: Controlling Multiple Pages with Python*