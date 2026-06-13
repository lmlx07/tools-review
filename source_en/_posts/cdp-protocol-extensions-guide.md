---
lang: en
title: "CDP Protocol Extensions Guide: Custom Domains & Chrome Extensions"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Chrome Extensions
  - Protocol Extension
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A deep dive into CDP's extensibility architecture — integrating CDP through Chrome Extensions, injecting custom commands, building middleware patterns, and designing custom event dispatch systems.
---

> **Summary in one sentence**: CDP's architecture is inherently extensible — you can integrate it via Chrome Extension's `chrome.debugger` API, inject custom behaviors using `Runtime.evaluate`, and build powerful interception and event systems through middleware patterns.

---

## Table of Contents

1. [CDP's Extensibility Architecture](#cdps-extensibility-architecture)
2. [CDP Integration in Chrome Extensions](#cdp-integration-in-chrome-extensions)
3. [Injecting Custom Commands via Runtime.evaluate](#injecting-custom-commands-via-runtimeevaluate)
4. [Middleware Patterns: Intercepting and Modifying CDP Traffic](#middleware-patterns-intercepting-and-modifying-cdp-traffic)
5. [Custom Event Dispatch System](#custom-event-dispatch-system)
6. [SessionObserver: Monitoring Multiple Sessions](#sessionobserver-monitoring-multiple-sessions)
7. [Best Practices and Architecture Guidelines](#best-practices-and-architecture-guidelines)

---

## CDP's Extensibility Architecture

CDP is not a closed protocol — it is built on JSON-RPC 2.0, making it naturally extensible. Understanding CDP's extensibility starts with its core architectural layers:

| Layer | Description | Extension Approach |
|-------|-------------|-------------------|
| Transport | WebSocket connection | Can be proxied, intercepted, modified |
| Message | JSON-RPC 2.0 messages | Custom methods/events can be injected |
| Domain | Functionally-grouped domains | Can combine or extend existing domains |
| Execution | V8 engine JavaScript | Inject through Runtime.evaluate |

Each CDP domain is essentially a collection of commands and events. While you cannot register entirely new CDP domains directly in Chrome, you can:

1. **Through Chrome Extension's `chrome.debugger` API** — gain authorized CDP sessions
2. **Through `Runtime.evaluate` injection** — execute arbitrary JS in page context to simulate new capabilities
3. **Through proxy/middleware patterns** — intercept and modify CDP messages in transit
4. **Through custom event dispatch** — use `CustomEvent` in injected code to simulate CDP event flows

This multi-layered extensibility makes CDP far more than a simple automation tool — it becomes a programmable browser control platform.

---

## CDP Integration in Chrome Extensions

### chrome.debugger API Basics

Chrome Extensions can use the `chrome.debugger` API to attach to any tab and obtain a CDP session. This is the standard way for native extensions to integrate CDP:

```python
# The following code demonstrates the concept of Chrome Extension CDP
# integration simulated through Python. Actual extensions use the
# JavaScript chrome.debugger API.

import asyncio
import websockets
import json

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."
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


async def attach_to_target(ws, url_pattern=None):
    """Attach to a target to simulate extension behavior"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets.get("targetInfos", []):
        if target["type"] == "page":
            if url_pattern is None or url_pattern in target.get("url", ""):
                result = await cdp(ws, "Target.attachToTarget", {
                    "targetId": target["targetId"],
                    "flatten": True
                })
                return result["sessionId"], target["targetId"]
    return None, None
```

### Extension CDP Permission Model

The `chrome.debugger` API in Chrome Extensions provides richer permission control than remote CDP:

```python
async def simulate_extension_debugger_pattern(ws):
    """Simulate Chrome Extension debugger permission pattern"""
    targets = await cdp(ws, "Target.getTargets")
    
    # Extensions typically attach to a specific active tab
    for target in targets.get("targetInfos", []):
        if target["type"] == "page" and target.get("attached") is False:
            session_id = target["targetId"]
            
            # Extensions can scope domain permissions
            # chrome.debugger.attach({tabId: tabId}, "1.3", callback)
            await cdp(ws, "Network.enable", {}, session_id)
            await cdp(ws, "Runtime.enable", {}, session_id)
            
            # The following domains require special permissions
            # in extension scenarios:
            # - Page.enable: requires tabs permission
            # - Debugger.enable: requires debugger permission
            # - Target.attachToTarget: requires target page access
            break


def attach_to_target_simple(target_id):
    """Attach to a specific target"""
    return target_id
```

### Message Interception in Extensions

Extensions can intercept CDP messages before or after they reach Chrome. This is the key pattern for implementing custom behaviors:

```python
class CDPMessageInterceptor:
    """CDP message interceptor — simulating extension onMessage callback"""
    
    def __init__(self):
        self.handlers = {}
        self.command_interceptors = []
        self.event_interceptors = []
    
    def on_command(self, method):
        """Register a command interceptor"""
        def decorator(handler):
            self.command_interceptors.append((method, handler))
            return handler
        return decorator
    
    def on_event(self, event_name):
        """Register an event interceptor"""
        def decorator(handler):
            self.event_interceptors.append((event_name, handler))
            return handler
        return decorator
    
    async def intercept_send(self, ws, method, params, session_id=None):
        """Intercept before sending"""
        modified_method = method
        modified_params = params
        
        for pattern, handler in self.command_interceptors:
            if pattern in method:
                result = await handler(method, params, session_id)
                if result:
                    modified_method = result.get("method", modified_method)
                    modified_params = result.get("params", modified_params)
        
        await cdp(ws, modified_method, modified_params, session_id)
    
    async def intercept_receive(self, data):
        """Intercept after receiving"""
        for pattern, handler in self.event_interceptors:
            if pattern in data.get("method", ""):
                await handler(data)
        return data
```

---

## Injecting Custom Commands via Runtime.evaluate

### Injection Pattern Fundamentals

`Runtime.evaluate` is the most powerful way to execute arbitrary JavaScript in a page. Through it, you can create the effect of "custom CDP commands":

```python
class CustomCDPCommands:
    """Simulate custom CDP commands via Runtime.evaluate"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
    
    async def evaluate(self, expression):
        """Execute a JS expression"""
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        }, self.session_id)
        return result.get("result", {})
    
    async def inject_get_all_network_requests(self):
        """Inject custom command: get all network requests"""
        js = """
        (() => {
            if (window.__cdp_network_requests) {
                return JSON.stringify(window.__cdp_network_requests);
            }
            window.__cdp_network_requests = [];
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(...args) {
                window.__cdp_network_requests.push({
                    type: 'xhr',
                    method: args[0],
                    url: args[1],
                    timestamp: Date.now()
                });
                return originalOpen.apply(this, args);
            };
            
            // Intercept fetch
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                window.__cdp_network_requests.push({
                    type: 'fetch',
                    url: typeof args[0] === 'string' ? args[0] : args[0].url,
                    timestamp: Date.now()
                });
                return originalFetch.apply(this, args);
            };
            
            return JSON.stringify([]);
        })()
        """
        return await self.evaluate(js)
    
    async def get_custom_storage_usage(self):
        """Inject custom command: get detailed storage usage"""
        js = """
        (async () => {
            const estimates = await navigator.storage.estimate();
            const cookies = document.cookie;
            const localStorageKeys = Object.keys(localStorage);
            const sessionStorageKeys = Object.keys(sessionStorage);
            const cacheNames = await caches.keys();
            
            return JSON.stringify({
                storage: {
                    usage: estimates.usage,
                    quota: estimates.quota,
                    usagePercent: ((estimates.usage / estimates.quota) * 100).toFixed(2)
                },
                cookies: cookies ? cookies.split(';').length : 0,
                localStorageKeys: localStorageKeys.length,
                sessionStorageKeys: sessionStorageKeys.length,
                cacheStorageNames: cacheNames
            });
        })()
        """
        return await self.evaluate(js)
```

### Building a Custom Monitor Domain

By combining multiple `Runtime.evaluate` calls, you can build monitoring capabilities similar to native CDP domains:

```python
class CustomMonitorDomain:
    """Custom monitor domain — implemented entirely via Runtime.evaluate"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._event_callbacks = {}
    
    async def enable(self):
        """Enable custom monitoring — inject JS hooks"""
        js = """
        (() => {
            window.__cdp_monitor = window.__cdp_monitor || {
                listeners: {},
                events: [],
                
                // Register custom event listener
                addCustomListener: function(name, callback) {
                    if (!this.listeners[name]) this.listeners[name] = [];
                    this.listeners[name].push(callback);
                },
                
                // Dispatch custom event
                dispatchCustomEvent: function(name, data) {
                    this.events.push({name, data, time: Date.now()});
                    if (this.listeners[name]) {
                        this.listeners[name].forEach(cb => cb(data));
                    }
                },
                
                // Monitor DOM changes
                startDOMMonitor: function() {
                    const observer = new MutationObserver((mutations) => {
                        this.dispatchCustomEvent('domMutation', {
                            count: mutations.length,
                            timestamp: Date.now()
                        });
                    });
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true,
                        attributes: true
                    });
                    return 'DOM monitor started';
                },
                
                // Monitor console calls
                startConsoleMonitor: function() {
                    const methods = ['log', 'warn', 'error', 'info', 'debug'];
                    methods.forEach(method => {
                        const original = console[method];
                        console[method] = function(...args) {
                            this.dispatchCustomEvent('consoleCall', {
                                method: method,
                                args: args.map(a => {
                                    try { return JSON.stringify(a); }
                                    catch(e) { return String(a); }
                                }),
                                timestamp: Date.now()
                            });
                            return original.apply(this, args);
                        };
                    });
                    return 'Console monitor started';
                }
            };
            return 'Custom monitor domain enabled';
        })()
        """
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
        return result
    
    async def start_dom_monitor(self):
        """Start DOM mutation monitoring"""
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": "window.__cdp_monitor.startDOMMonitor()",
            "returnByValue": True
        }, self.session_id)
    
    async def start_console_monitor(self):
        """Start console monitoring"""
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": "window.__cdp_monitor.startConsoleMonitor()",
            "returnByValue": True
        }, self.session_id)
    
    async def get_events(self, clear=False):
        """Get accumulated custom events"""
        js = """
        (() => {
            const events = window.__cdp_monitor.events;
            if (clear) window.__cdp_monitor.events = [];
            return JSON.stringify(events);
        })()
        """
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
        return json.loads(result.get("result", {}).get("value", "[]"))
```

---

## Middleware Patterns: Intercepting and Modifying CDP Traffic

### CDP Proxy Architecture

Building a CDP proxy server is the most powerful extension approach. The proxy sits between the client and Chrome, intercepting, modifying, and logging all CDP messages:

```python
import asyncio
import json
import websockets
from datetime import datetime

class CDPProxy:
    """CDP Proxy Server — intercept and modify CDP traffic"""
    
    def __init__(self, target_cdp_url, listen_port=9223):
        self.target_cdp_url = target_cdp_url
        self.listen_port = listen_port
        self.middleware = []
        self.command_log = []
        self.event_log = []
    
    def use(self, middleware_fn):
        """Register a middleware function"""
        self.middleware.append(middleware_fn)
    
    async def handle_client(self, client_ws):
        """Handle a client connection"""
        async with websockets.connect(self.target_cdp_url) as chrome_ws:
            async def forward_to_chrome():
                """Forward client messages to Chrome"""
                async for message in client_ws:
                    modified = message
                    for mw in self.middleware:
                        modified = await mw("request", modified)
                    
                    parsed = json.loads(modified)
                    self.command_log.append({
                        "time": datetime.now().isoformat(),
                        "method": parsed.get("method", "(unknown)"),
                        "id": parsed.get("id")
                    })
                    
                    await chrome_ws.send(modified)
            
            async def forward_to_client():
                """Forward Chrome messages to client"""
                async for message in chrome_ws:
                    modified = message
                    for mw in self.middleware:
                        modified = await mw("response", modified)
                    
                    parsed = json.loads(modified)
                    if "method" in parsed:
                        self.event_log.append({
                            "time": datetime.now().isoformat(),
                            "method": parsed["method"],
                            "params": parsed.get("params", {})
                        })
                    
                    await client_ws.send(modified)
            
            await asyncio.gather(
                forward_to_chrome(),
                forward_to_client()
            )
    
    async def start(self):
        """Start the proxy server"""
        print(f"CDP Proxy started: ws://127.0.0.1:{self.listen_port}")
        print(f"Target Chrome: {self.target_cdp_url}")
        async with websockets.serve(self.handle_client, "127.0.0.1", self.listen_port):
            await asyncio.Future()
```

### Practical CDP Middleware Examples

```python
# Logging middleware
async def logging_middleware(direction, message):
    parsed = json.loads(message)
    if direction == "request":
        method = parsed.get("method", "")
        if not method.startswith("Target."):  # Filter frequent polling
            print(f"[Request] {method} id={parsed.get('id')}")
    else:
        if "method" in parsed:
            print(f"[Event] {parsed['method']}")
        elif "id" in parsed:
            pass  # Command response
    return message


# Sensitive information filtering middleware
async def sanitize_middleware(direction, message):
    """Filter sensitive information from CDP traffic"""
    parsed = json.loads(message)
    
    if direction == "response":
        # Redact sensitive info in page source content
        if parsed.get("method") == "Page.getResourceContent":
            params = parsed.get("params", {})
            content = params.get("content", "")
            content = content.replace("API_KEY=", "API_KEY=[REDACTED]")
            content = content.replace("password=", "password=[REDACTED]")
            parsed["params"]["content"] = content
            return json.dumps(parsed)
        
        # Filter tokens from network requests
        if parsed.get("method") == "Network.requestWillBeSent":
            request = parsed.get("params", {}).get("request", {})
            headers = request.get("headers", {})
            if "Authorization" in headers:
                headers["Authorization"] = "[REDACTED]"
            return json.dumps(parsed)
    
    return message


# Request blocking middleware
def create_block_middleware(block_patterns=None):
    """Create a middleware that blocks specific CDP methods"""
    block_patterns = block_patterns or []
    
    async def block_middleware(direction, message):
        if direction != "request":
            return message
        
        parsed = json.loads(message)
        method = parsed.get("method", "")
        
        if method in block_patterns:
            response = {"id": parsed["id"], "result": {}}
            print(f"[Blocked] {method} request blocked")
            return json.dumps(response)
        
        return message
    
    return block_middleware


# Usage example
async def demo_proxy():
    proxy = CDPProxy("ws://127.0.0.1:9222/devtools/browser/a1b2c3d4")
    proxy.use(logging_middleware)
    proxy.use(sanitize_middleware)
    proxy.use(create_block_middleware(["Target.setDiscoverTargets"]))
    await proxy.start()


# asyncio.run(demo_proxy())
```

---

## Custom Event Dispatch System

### Building a CDP-Style Event System in the Page

CDP's event mechanism is essentially a one-way push from browser to client. Using `Runtime.evaluate` combined with JavaScript's `CustomEvent`, you can build your own event dispatch system inside the page:

```python
class CustomEventDispatcher:
    """Custom CDP-style event dispatch system"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.event_bus = {}
    
    async def create_event_domain(self, domain_name):
        """Create a custom event domain inside the page"""
        js = f"""
        (() => {{
            const domain = window.__cdp_custom_domains = window.__cdp_custom_domains || {{}};
            
            domain['{domain_name}'] = {{
                listeners: {{}},
                history: [],
                
                // Register event listener
                on(event, callback) {{
                    if (!this.listeners[event]) this.listeners[event] = [];
                    this.listeners[event].push(callback);
                }},
                
                // Dispatch event
                dispatch(event, data) {{
                    const entry = {{event, data, timestamp: Date.now()}};
                    this.history.push(entry);
                    
                    if (this.listeners[event]) {{
                        this.listeners[event].forEach(cb => cb(entry));
                    }}
                    
                    // Forward via DOM CustomEvent
                    document.dispatchEvent(new CustomEvent('cdp:' + '{domain_name}.' + event, {{
                        detail: data,
                        bubbles: true
                    }}));
                    
                    return entry;
                }},
                
                // Enable domain
                enable() {{
                    this.enabled = true;
                    return 'Domain {domain_name} enabled';
                }},
                
                // Disable domain
                disable() {{
                    this.enabled = false;
                    return 'Domain {domain_name} disabled';
                }},
                
                // Get event history
                getHistory() {{
                    return this.history.slice();
                }}
            }};
            
            return 'Custom domain {domain_name} created';
        }})()
        """
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
    
    async def create_network_analyzer_domain(self):
        """Create a custom network analysis domain"""
        await self.create_event_domain("NetworkAnalyzer")
        
        js = """
        (() => {
            const domain = window.__cdp_custom_domains['NetworkAnalyzer'];
            
            // Monitor resource loading timing
            const observer = new PerformanceObserver((list) => {
                list.getEntries().forEach(entry => {
                    domain.dispatch('resourceTiming', {
                        name: entry.name,
                        duration: entry.duration,
                        startTime: entry.startTime,
                        transferSize: entry.transferSize || 0,
                        type: entry.entryType
                    });
                });
            });
            
            observer.observe({ entryTypes: ['resource', 'navigation'] });
            
            // Monitor connection changes
            const connection = navigator.connection;
            if (connection) {
                connection.addEventListener('change', () => {
                    domain.dispatch('connectionChange', {
                        effectiveType: connection.effectiveType,
                        downlink: connection.downlink,
                        rtt: connection.rtt
                    });
                });
            }
            
            return 'NetworkAnalyzer domain active with observers';
        })()
        """
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
    
    async def dispatch_custom_event(self, domain, event, data):
        """Trigger a custom event from outside"""
        js = f"""
        window.__cdp_custom_domains['{domain}'].dispatch('{event}', {json.dumps(data)});
        """
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
    
    async def poll_custom_events(self, domain, clear=True):
        """Poll and collect custom events"""
        js = f"""
        (() => {{
            const history = window.__cdp_custom_domains['{domain}'].history;
            const result = JSON.parse(JSON.stringify(history));
            if ({str(clear).lower()}) {{
                history.length = 0;
            }}
            return result;
        }})()
        """
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
        return json.loads(result.get("result", {}).get("value", "[]"))
```

---

## SessionObserver: Monitoring Multiple Sessions

### Multi-Tab Observation Architecture

One of CDP's most powerful extension patterns is establishing a unified observation layer across multiple targets (tabs, iframes, workers):

```python
class CDPSessionObserver:
    """Multi-session observer — monitor multiple CDP sessions simultaneously"""
    
    def __init__(self, ws):
        self.ws = ws
        self.sessions = {}
        self.global_event_handlers = {}
    
    async def discover_and_attach_all(self):
        """Discover and attach to all available targets"""
        targets = await cdp(self.ws, "Target.getTargets")
        attached = []
        
        for target in targets.get("targetInfos", []):
            if target["type"] in ("page", "iframe", "worker", "service_worker"):
                result = await cdp(self.ws, "Target.attachToTarget", {
                    "targetId": target["targetId"],
                    "flatten": True
                })
                session_id = result["sessionId"]
                self.sessions[target["targetId"]] = {
                    "session_id": session_id,
                    "target": target,
                    "event_buffer": []
                }
                attached.append(target)
        
        return attached
    
    def on(self, method_pattern):
        """Register a global event handler"""
        def decorator(handler):
            self.global_event_handlers[method_pattern] = handler
            return handler
        return decorator
    
    async def listen_all(self, duration=60):
        """Listen for events from all sessions simultaneously"""
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                session_id = data.get("sessionId")
                
                # Locate the source session
                source_target = None
                for tid, info in self.sessions.items():
                    if info["session_id"] == session_id:
                        source_target = tid
                        break
                
                # Buffer the event
                if source_target:
                    self.sessions[source_target]["event_buffer"].append({
                        "method": method,
                        "params": data.get("params", {}),
                        "time": datetime.now().isoformat()
                    })
                
                # Trigger global handlers
                for pattern, handler in self.global_event_handlers.items():
                    if pattern in method:
                        await handler(data, source_target)
                        
            except asyncio.TimeoutError:
                continue
    
    def get_session_events(self, target_id, clear=True):
        """Get buffered events for a specific session"""
        if target_id not in self.sessions:
            return []
        events = self.sessions[target_id]["event_buffer"]
        if clear:
            self.sessions[target_id]["event_buffer"] = []
        return events
    
    async def execute_on_all(self, method, params=None):
        """Execute the same command on all sessions"""
        results = {}
        for tid, info in self.sessions.items():
            result = await cdp(self.ws, method, params, info["session_id"])
            results[tid] = result
        return results
    
    async def enable_domain_on_all(self, domain_method):
        """Enable a domain on all sessions"""
        await self.execute_on_all(domain_method)
    
    async def detach_all(self):
        """Detach from all sessions"""
        for tid in list(self.sessions.keys()):
            await cdp(self.ws, "Target.detachFromTarget", {
                "targetId": tid
            })
        self.sessions.clear()


# Practical example: cross-tab monitoring
async def cross_tab_monitor_demo():
    async with websockets.connect(CDP_URL) as ws:
        observer = CDPSessionObserver(ws)
        
        # Discover and attach to all pages
        targets = await observer.discover_and_attach_all()
        print(f"Attached to {len(targets)} targets")
        
        # Enable Runtime on all sessions
        await observer.enable_domain_on_all("Runtime.enable")
        
        # Register global handler
        @observer.on("Runtime.exceptionThrown")
        async def on_exception(data, source):
            print(f"[Exception] from {source}: {data['params']['exceptionDetails']['text']}")
        
        # Listen for 30 seconds
        await observer.listen_all(30)
        
        # Collect results
        for tid, info in observer.sessions.items():
            events = observer.get_session_events(tid)
            target = info["target"]
            url = target.get("url", "(unknown)")
            print(f"Tab {url}: {len(events)} events")
        
        await observer.detach_all()


# asyncio.run(cross_tab_monitor_demo())
```

---

## Best Practices and Architecture Guidelines

### Extension Pattern Selection Guide

| Scenario | Recommended Pattern | Rationale |
|----------|--------------------|-----------|
| Need native browser features | chrome.debugger extension | Higher permissions, better lifecycle management |
| Rapid prototyping | Runtime.evaluate injection | Zero configuration, write and run immediately |
| Production interception | CDP proxy middleware | Auditable, rollback-capable, performance transparent |
| Large-scale tab management | SessionObserver pattern | Unified session management, prevents resource leaks |
| Custom metric collection | Custom event domain + polling | Flexible, decoupled from CDP event flow |

### Security Considerations

```python
class CDPExtensionSecurity:
    """CDP extension security best practices"""
    
    @staticmethod
    async def validate_command_source(ws, session_id, command):
        """Validate command source — prevent unauthorized injection"""
        # Validate against a command whitelist at the proxy layer
        ALLOWED_COMMANDS = {
            "Runtime.evaluate",
            "Runtime.runScript",
            "Page.navigate",
            "Network.enable",
        }
        
        method = command.get("method", "")
        if method not in ALLOWED_COMMANDS:
            print(f"[Security] Blocking unauthorized command: {method}")
            return False
        return True
    
    @staticmethod
    async def sanitize_evaluate_expression(expression):
        """Sanitize Runtime.evaluate expressions — prevent XSS"""
        dangerous_patterns = [
            "document.cookie",
            "localStorage.",
            "new Function(",
            "eval(",
            "import(",
        ]
        for pattern in dangerous_patterns:
            if pattern in expression:
                print(f"[Security] Dangerous pattern detected: {pattern}")
                return False
        return True
    
    @staticmethod
    def isolate_extension_context():
        """Best practices for isolating extension context"""
        return {
            "use_isolated_world": True,       # Runtime.evaluate with contextId
            "sandbox_iframes": True,           # Isolate within iframes
            "limit_session_scope": True,       # Only attach needed targets
            "audit_message_log": True,         # Log all CDP communication
        }
```

### Error Handling and Recovery

```python
class RobustExtensionPattern:
    """Robust extension pattern — handle reconnection and error recovery"""
    
    def __init__(self, cdp_url):
        self.cdp_url = cdp_url
        self.ws = None
        self.sessions = {}
        self.reconnect_attempts = 0
        self.max_reconnect = 5
    
    async def connect_with_retry(self):
        """Connect with retry mechanism"""
        while self.reconnect_attempts < self.max_reconnect:
            try:
                self.ws = await websockets.connect(self.cdp_url)
                self.reconnect_attempts = 0
                print(f"[Connect] Connected to {self.cdp_url}")
                return True
            except (ConnectionRefusedError, websockets.ConnectionClosed):
                self.reconnect_attempts += 1
                wait = 2 ** self.reconnect_attempts
                print(f"[Retry] Attempt {self.reconnect_attempts}, waiting {wait}s")
                await asyncio.sleep(wait)
        return False
    
    async def ensure_session_alive(self, target_id):
        """Ensure session is alive — auto-rebuild after disconnection"""
        if target_id not in self.sessions:
            return False
        
        try:
            await cdp(self.ws, "Runtime.evaluate", {
                "expression": "1+1"
            }, self.sessions[target_id])
            return True
        except Exception:
            result = await cdp(self.ws, "Target.attachToTarget", {
                "targetId": target_id,
                "flatten": True
            })
            self.sessions[target_id] = result["sessionId"]
            return True
```

---

> **Extended Thinking**: CDP's architecture is essentially a "reflection layer" for web browser capabilities. Understanding its extension patterns gives you the ability to programmatically expose any browser capability to external systems — from automated testing and security auditing to performance monitoring and custom debuggers. In the next chapter, we'll dive into CDP's error tracking capabilities, building a production-grade JS exception monitoring system with Python.

*Previous: CDP Browser History Management: Controlling Page Navigation with Python*

*Next up: CDP Error Tracking Guide: Capturing Page Exceptions with Python*