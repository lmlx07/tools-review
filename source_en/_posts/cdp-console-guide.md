---
lang: en
title: "CDP Console Debugging Guide: Capture Page Logs & Exceptions with Python"
date: "2026-06-05 18:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Console
  - Debugging
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to capturing browser console output using Chrome DevTools Protocol (CDP). Learn to listen for console.log/warn/error, catch uncaught exceptions, filter log levels, inject custom console commands, and build automated error monitoring tools.
---

> **Summary in one sentence**: CDP's Console API lets you capture everything in the browser console — log, warn, error, assertion failures, and uncaught exceptions — just like having DevTools open, but fully programmable.

---

## Table of Contents

1. [Why Use CDP for Console Capture](#why-use-cdp-for-console-capture)
2. [Basic: Listening for Console Messages](#basic-listening-for-console-messages)
3. [Capturing JavaScript Exceptions](#capturing-javascript-exceptions)
4. [Filtering & Categorizing Logs](#filtering--categorizing-logs)
5. [Injecting Custom Console Commands](#injecting-custom-console-commands)
6. [Practical: Automated Error Monitoring](#practical-automated-error-monitoring)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Console Capture

| Feature | DevTools Console | CDP Console API |
|---------|-----------------|-----------------|
| console.log/warn/error | ✅ Live view | ✅ Capturable |
| Uncaught exceptions | ✅ Displayed | ✅ Capturable |
| Network errors | ✅ Displayed | ✅ Via Network domain |
| Assertion failures | ✅ Displayed | ✅ Capturable |
| Filter/Categorize | ✅ Manual | ✅ Programmatic |
| History | ✅ Retained | ✅ Continuously collected |
| CI/CD integration | ❌ Cannot automate | ✅ Fully programmable |

---

## Basic: Listening for Console Messages

### Enabling Console Domain

```python
import asyncio
import websockets
import json

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."
CMD_ID = [0]

async def cdp(ws, session_id, method, params=None):
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": cmd_id,
        "method": method,
        "params": params or {}
    }))
    async for msg in ws:
        resp = json.loads(msg)
        if resp.get("id") == cmd_id:
            return resp.get("result", {})

async def connect_page(ws):
    targets = await cdp(ws, None, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, None, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]


async def enable_console(ws, session_id):
    return await cdp(ws, session_id, "Console.enable")


async def collect_console_messages(ws, session_id, duration=10):
    await enable_console(ws, session_id)
    
    messages = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "Console.messageAdded":
                msg_data = data["params"]["message"]
                messages.append({
                    "level": msg_data["level"],
                    "text": msg_data["text"],
                    "source": msg_data["source"],
                    "url": msg_data.get("url", ""),
                    "line": msg_data.get("line", 0),
                })
                    
        except asyncio.TimeoutError:
            continue
    
    return messages
```

### Console Message Structure

```python
{
    "level": "error",           # log | info | warning | error | debug
    "text": "Uncaught TypeError: ...",
    "source": "javascript",     # javascript | network | console-api | ...
    "timestamp": 1700000000000, # milliseconds
    "url": "https://example.com/app.js",
    "line": 42,
    "column": 10,
    "stackTrace": {
        "callFrames": [...]
    }
}
```

---

## Capturing JavaScript Exceptions

### Using the Runtime Domain

```python
async def enable_runtime(ws, session_id):
    return await cdp(ws, session_id, "Runtime.enable")


async def capture_exceptions(ws, session_id, duration=10):
    await enable_runtime(ws, session_id)
    
    exceptions = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            
            if method == "Runtime.exceptionThrown":
                exc = data["params"]["exceptionDetails"]
                exceptions.append({
                    "text": exc.get("text", ""),
                    "url": exc.get("url", ""),
                    "line": exc.get("lineNumber", 0),
                    "stack_trace": exc.get("stackTrace", {}),
                })
                print(f"[Exception] {exc.get('text', '')}")
            
            elif method == "Runtime.consoleAPICalled":
                api_data = data["params"]
                args = [a.get("value", str(a.get("description", ""))) 
                        for a in api_data.get("args", [])]
                exceptions.append({
                    "type": "console_api",
                    "level": api_data.get("type", ""),
                    "text": " ".join(str(a) for a in args),
                    "stack_trace": api_data.get("stackTrace", {}),
                })
                
        except asyncio.TimeoutError:
            continue
    
    return exceptions


def format_exception(exc):
    text = exc.get("text", "")
    url = exc.get("url", "")
    line = exc.get("line", 0)
    stack = exc.get("stack_trace", {})
    frames = stack.get("callFrames", [])
    
    result = f"[{exc.get('type', 'exception').upper()}] {text}\n"
    result += f"  Location: {url}:{line}\n"
    for frame in frames[:5]:
        result += f"    at {frame.get('functionName', '(anonymous)')} "
        result += f"({frame.get('url', '')}:{frame.get('lineNumber', 0)})\n"
    return result
```

### Console vs Runtime API

```python
"""
Console.messageAdded   vs   Runtime.consoleAPICalled
────────────────────────────────────────────────────
Simpler, text-only           More detailed with arg types
Good for quick collection    Better for deep analysis
No stack info                Includes stack traces
Requires Console.enable      Requires Runtime.enable

Recommendation:
- Quick check: Use Console
- Exception debugging: Use Runtime
- Best: Enable both simultaneously
"""
```

---

## Filtering & Categorizing Logs

### Filter by Level

```python
async def collect_filtered_logs(ws, session_id, duration=10, min_level="info"):
    levels = {"debug": 0, "info": 1, "log": 1, "warning": 2, "error": 3}
    min_level_num = levels.get(min_level, 1)
    
    await enable_console(ws, session_id)
    
    filtered = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "Console.messageAdded":
                msg_data = data["params"]["message"]
                if levels.get(msg_data["level"], 1) >= min_level_num:
                    filtered.append(msg_data)
                    
        except asyncio.TimeoutError:
            continue
    
    by_level = {}
    for log in filtered:
        level = log["level"]
        if level not in by_level:
            by_level[level] = []
        by_level[level].append(log["text"])
    
    return {"total": len(filtered), "by_level": by_level}
```

### Categorize by Source

```python
async def categorize_logs(ws, session_id, duration=10):
    logs = await collect_console_messages(ws, session_id, duration)
    
    categories = {
        "javascript": [],
        "console_api": [],
        "network": [],
        "security": [],
        "other": []
    }
    
    for log in logs:
        source = log.get("source", "other")
        if source in categories:
            categories[source].append(log)
        else:
            categories["other"].append(log)
    
    print("Log categories:")
    for source, items in categories.items():
        print(f"  {source}: {len(items)} entries")
    
    return categories
```

---

## Injecting Custom Console Commands

```python
async def inject_console_monitor(ws, session_id):
    script = """
    (function() {
        const originalError = console.error;
        const originalWarn = console.warn;
        const originalLog = console.log;
        
        const timestamp = () => {
            const now = new Date();
            return `[${now.toISOString()}]`;
        };
        
        console.log = function(...args) {
            originalLog.apply(console, [timestamp(), ...args]);
        };
        
        console.warn = function(...args) {
            originalWarn.apply(console, [timestamp(), '[WARN]', ...args]);
        };
        
        console.error = function(...args) {
            window.__cdp_error_happened__ = true;
            originalError.apply(console, [timestamp(), '[ERROR]', ...args]);
        };
        
        console.info('Console monitor injected');
    })();
    """
    
    return await cdp(ws, session_id, "Page.addScriptToEvaluateOnNewDocument", {
        "source": script
    })


async def monitor_api_errors(ws, session_id, duration=30):
    logs = await collect_console_messages(ws, session_id, duration)
    api_keywords = ["api", "fetch", "xhr", "axios", "timeout", "5xx", "4xx", "network"]
    
    api_logs = [l for l in logs 
                if any(kw in l.get("text", "").lower() for kw in api_keywords)]
    
    errors = [l for l in api_logs if l["level"] == "error"]
    warnings = [l for l in api_logs if l["level"] == "warning"]
    
    print(f"API-related logs: {len(api_logs)} entries")
    print(f"  - Errors: {len(errors)}")
    print(f"  - Warnings: {len(warnings)}")
    
    return api_logs
```

---

## Practical: Automated Error Monitoring

```python
from datetime import datetime


async def monitor_page_errors(ws, session_id, url, duration=30):
    await enable_console(ws, session_id)
    await enable_runtime(ws, session_id)
    await inject_console_monitor(ws, session_id)
    
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(2)
    
    errors = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            
            if method == "Console.messageAdded":
                msg_data = data["params"]["message"]
                if msg_data["level"] in ("error", "warning"):
                    errors.append({
                        "type": "console_" + msg_data["level"],
                        "text": msg_data["text"],
                        "source": msg_data.get("source"),
                        "url": msg_data.get("url"),
                        "line": msg_data.get("line"),
                        "time": datetime.now().isoformat()
                    })
            
            elif method == "Runtime.exceptionThrown":
                exc = data["params"]["exceptionDetails"]
                errors.append({
                    "type": "exception",
                    "text": exc.get("text", ""),
                    "url": exc.get("url"),
                    "line": exc.get("lineNumber"),
                    "stack": exc.get("stackTrace"),
                    "time": datetime.now().isoformat()
                })
                    
        except asyncio.TimeoutError:
            continue
    
    report = {
        "url": url,
        "duration": duration,
        "total_errors": len(errors),
        "errors_by_type": {},
        "errors": errors
    }
    
    for err in errors:
        err_type = err["type"]
        report["errors_by_type"][err_type] = report["errors_by_type"].get(err_type, 0) + 1
    
    print(f"\n=== Error Monitor Report ===")
    print(f"URL: {url}")
    print(f"Duration: {duration}s")
    print(f"Total errors: {report['total_errors']}")
    print(f"By type: {report['errors_by_type']}")
    
    return report
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Console State Resets on Navigation

```python
# ❌ Console events stop after navigation
await enable_console(ws, session_id)
await cdp(ws, session_id, "Page.navigate", {"url": url})
# No more Console events arriving!

# ✅ Re-enable after navigation
await cdp(ws, session_id, "Page.navigate", {"url": url})
await enable_console(ws, session_id)
```

### Pitfall 2: Runtime.enable Required for consoleAPICalled

```python
# ❌ Only Console.enabled — no Runtime.consoleAPICalled events
await cdp(ws, session_id, "Console.enable")

# ✅ Enable both for full coverage
await cdp(ws, session_id, "Console.enable")
await cdp(ws, session_id, "Runtime.enable")
```

### Pitfall 3: Stack Traces May Be Empty

```python
exc = data["params"]["exceptionDetails"]
if not exc.get("stackTrace"):
    # Minified or eval'd code may lack stack traces
    print("Warning: No stack trace (minified code?)")
```

### Pitfall 4: Non-String Console Arguments

```python
# Page does: console.log({foo: "bar"}, [1,2,3])
# Console.messageAdded text may be JSON or "[object Object]"
# Use Runtime.consoleAPICalled for richer arg info
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Re-enable after navigation | Navigation resets Console push state |
| Enable Console + Runtime | Complementary — both for full data |
| Stack traces | May be empty for minified code |
| Argument types | Use Runtime.consoleAPICalled for rich args |
| Log volume | Clear buffers periodically for long sessions |
| Script injection | Use addScriptToEvaluateOnNewDocument |

---

## Complete Reference: CDP Console Monitor Class

```python
import asyncio
import json
from datetime import datetime


class CDPConsoleMonitor:
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self.messages = []
        self.exceptions = []
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        msg = {
            "sessionId": self.session_id,
            "id": self._cmd_id,
            "method": method,
            "params": params or {}
        }
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def start(self):
        await self._cmd("Console.enable")
        await self._cmd("Runtime.enable")
    
    async def collect(self, duration=10):
        self.messages = []
        self.exceptions = []
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                if method == "Console.messageAdded":
                    self.messages.append(data["params"]["message"])
                elif method == "Runtime.exceptionThrown":
                    self.exceptions.append(data["params"]["exceptionDetails"])
            except asyncio.TimeoutError:
                continue
        return {
            "messages": self.messages,
            "exceptions": self.exceptions,
            "error_count": sum(1 for m in self.messages if m["level"] == "error"),
        }
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    monitor = CDPConsoleMonitor(ws, session_id)
    await monitor.start()
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    result = await monitor.collect(duration=10)
    print(f"Errors: {result['error_count']}")
```

---

> **Summary**: CDP's Console and Runtime APIs can capture everything in the browser console — logs, warnings, errors, and exceptions. Combined with stack trace analysis, you can build automated page error monitoring for CI/CD pipelines.

---

*Previous: CDP Screenshot & PDF Export Guide: Generate Precise Page Snapshots with Python*

*Next up: CDP Storage Operations Guide: Manage LocalStorage, IndexedDB & Cache with Python*