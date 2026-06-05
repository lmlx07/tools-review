---
lang: en
title: "CDP Error Tracking Guide: Capturing Page Exceptions with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Error Tracking
  - JavaScript Debugging
  - Exception Monitoring
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to capturing and tracking JavaScript page exceptions using Chrome DevTools Protocol (CDP). Covers Runtime.exceptionThrown events, exception detail parsing, Source Map resolution, breakpoint debugging, and error aggregation.
---

> **Summary in one sentence**: CDP provides complete JavaScript exception monitoring capabilities — capture unhandled exceptions via `Runtime.exceptionThrown`, listen for error logs via `Runtime.consoleAPICalled`, inspect error context at breakpoint level via `Debugger.paused`, and pinpoint source locations with Source Map resolution.

---

## Table of Contents

1. [Exception Tracking Overview](#exception-tracking-overview)
2. [Capturing Runtime Exceptions: exceptionThrown](#capturing-runtime-exceptions-exceptionthrown)
3. [Listening for Console Errors: consoleAPICalled](#listening-for-console-errors-consoleapicalled)
4. [Exception Detail Parsing](#exception-detail-parsing)
5. [Locating Source with Source Maps](#locating-source-with-source-maps)
6. [Breakpoint-Level Error Inspection](#breakpoint-level-error-inspection)
7. [Practical: Production-Grade Error Aggregation System](#practical-production-grade-error-aggregation-system)
8. [Best Practices and Considerations](#best-practices-and-considerations)

---

## Exception Tracking Overview

JavaScript exception tracking is a core requirement for frontend monitoring. CDP provides multiple layers of exception capture:

| Capture Method | CDP Mechanism | Use Case |
|---------------|---------------|----------|
| Unhandled exceptions | `Runtime.exceptionThrown` event | Auto-capture all uncaught exceptions |
| Console errors | `Runtime.consoleAPICalled` + `console.error()` | Capture explicitly logged errors |
| Breakpoint debugging | `Debugger.paused` + breakpoint conditions | Pause and inspect at exception time |
| Exception filtering | ExceptionDetails in exceptionThrown | Analyze type, stack trace, location |

CDP's exception tracking differs from traditional `window.onerror` or `try/catch` in several key ways:

1. **Browser-level capture** — caught at the JS engine level, does not depend on page code coverage
2. **Complete stack traces** — provides full `stackTrace` with precise frame locations
3. **Source Map support** — can map back to original source code positions
4. **Cross-lifecycle persistence** — remains active across page refreshes and navigations

---

## Capturing Runtime Exceptions: exceptionThrown

### Basic Exception Listening

The `Runtime.exceptionThrown` event fires automatically whenever a JavaScript exception is not caught by a `try/catch` block. This is the most fundamental exception capture pattern:

```python
import asyncio
import websockets
import json
from datetime import datetime

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


async def connect_page(ws):
    """Connect to the first available page target"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    result = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return result["sessionId"], target_id


async def listen_exceptions(ws, session_id, duration=30):
    """Listen for Runtime.exceptionThrown events"""
    await cdp(ws, "Runtime.enable", {}, session_id)
    
    exceptions = []
    start = asyncio.get_event_loop().time()
    
    print("Listening for JavaScript exceptions...")
    print("-" * 60)
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            params = data.get("params", {})
            
            if method == "Runtime.exceptionThrown":
                details = params.get("exceptionDetails", {})
                timestamp = params.get("timestamp", datetime.now().timestamp())
                
                exception_info = {
                    "timestamp": datetime.fromtimestamp(timestamp).isoformat(),
                    "text": details.get("text", ""),
                    "url": details.get("url", ""),
                    "line": details.get("lineNumber", 0),
                    "column": details.get("columnNumber", 0),
                    "script_id": details.get("scriptId", ""),
                    "stack_trace": details.get("stackTrace", {}),
                    "exception": details.get("exception", {}),
                }
                
                exceptions.append(exception_info)
                
                print(f"[Exception] {details.get('text', '')}")
                print(f"            Location: {details.get('url', '')}:{details.get('lineNumber', '')}:{details.get('columnNumber', '')}")
                print(f"            Time: {exception_info['timestamp']}")
                print()
                
        except asyncio.TimeoutError:
            continue
    
    print(f"Captured {len(exceptions)} exceptions")
    return exceptions
```

### Injecting Test Exceptions

```python
async def inject_test_exceptions(ws, session_id):
    """Inject test JavaScript exceptions"""
    test_cases = [
        ("TypeError", """
        (function() {
            const obj = null;
            return obj.property;
        })();
        """),
        ("ReferenceError", """
        console.log(undefinedVariable);
        """),
        ("SyntaxError", """
        try {
            eval('if (true) { break; }');
        } catch(e) {
            throw e;
        }
        """),
        ("RangeError", """
        (function() {
            const arr = new Array(-1);
        })();
        """),
        ("CustomError", """
        throw new Error('This is a custom business error');
        """),
    ]
    
    for name, code in test_cases:
        try:
            await cdp(ws, "Runtime.evaluate", {
                "expression": code,
                "returnByValue": True
            }, session_id)
            print(f"[Inject] Triggered {name}")
        except Exception as e:
            print(f"[Inject] {name} execution failed: {e}")
        await asyncio.sleep(0.5)
```

---

## Listening for Console Errors: consoleAPICalled

### Capturing console.error Logs

Beyond auto-triggered exceptions, much code uses `console.error()` to actively log errors. These can be captured via `Runtime.consoleAPICalled`:

```python
class ConsoleErrorCollector:
    """Collect errors emitted via console API"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.errors = []
        self._running = False
    
    async def enable(self):
        """Enable console monitoring"""
        await cdp(self.ws, "Runtime.enable", {}, self.session_id)
        await cdp(self.ws, "Console.enable", {}, self.session_id)
        self._running = True
    
    def parse_console_args(self, args):
        """Parse console API arguments"""
        parsed = []
        for arg in args:
            arg_type = arg.get("type", "")
            if arg_type == "string":
                parsed.append(arg.get("value", ""))
            elif arg_type == "object":
                description = arg.get("description", "")
                preview = arg.get("preview", {})
                if preview:
                    properties = preview.get("properties", [])
                    props_str = ", ".join([
                        f"{p.get('name', '')}: {p.get('value', '')}"
                        for p in properties[:5]
                    ])
                    parsed.append(f"{{{props_str}}}")
                else:
                    parsed.append(description)
            elif arg_type == "number":
                parsed.append(str(arg.get("value", 0)))
            elif arg_type == "boolean":
                parsed.append(str(arg.get("value", False)))
            elif arg_type == "undefined":
                parsed.append("undefined")
            elif arg_type == "function":
                parsed.append(arg.get("description", "function()"))
            else:
                parsed.append(str(arg))
        return " ".join(parsed)
    
    async def collect_errors(self, duration=30):
        """Collect errors within the specified time period"""
        if not self._running:
            await self.enable()
        
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Runtime.consoleAPICalled":
                    api_type = params.get("type", "")
                    
                    if api_type == "error":
                        args = params.get("args", [])
                        stack_trace = params.get("stackTrace", {})
                        context = params.get("context", "")
                        
                        error_entry = {
                            "timestamp": datetime.now().isoformat(),
                            "type": "console.error",
                            "message": self.parse_console_args(args),
                            "stack_trace": stack_trace,
                            "context": context,
                            "args_count": len(args)
                        }
                        
                        self.errors.append(error_entry)
                        
                        print(f"[console.error] {error_entry['message'][:200]}")
                        if stack_trace:
                            call_frames = stack_trace.get("callFrames", [])
                            if call_frames:
                                top = call_frames[0]
                                print(f"                {top.get('url', '')}:{top.get('lineNumber', '')}")
                
                elif method == "Console.messageAdded":
                    msg_data = params.get("message", {})
                    if msg_data.get("level") == "error":
                        self.errors.append({
                            "timestamp": datetime.now().isoformat(),
                            "type": "console.message.added",
                            "message": msg_data.get("text", ""),
                            "source": msg_data.get("source", ""),
                            "line": msg_data.get("line", 0)
                        })
                        
            except asyncio.TimeoutError:
                continue
        
        return self.errors
    
    def get_error_summary(self):
        """Get error summary by deduplication"""
        by_message = {}
        for err in self.errors:
            msg = err.get("message", "")
            if msg not in by_message:
                by_message[msg] = {"count": 0, "first_seen": err["timestamp"], "last_seen": err["timestamp"]}
            by_message[msg]["count"] += 1
            by_message[msg]["last_seen"] = err["timestamp"]
        
        return {
            "total": len(self.errors),
            "unique": len(by_message),
            "by_message": by_message
        }
```

### Distinguishing Different Console Log Levels

```python
async def monitor_all_console_levels(ws, session_id, duration=20):
    """Monitor all console log levels"""
    await cdp(ws, "Runtime.enable", {}, session_id)
    
    log_counts = {"log": 0, "warn": 0, "error": 0, "info": 0, "debug": 0}
    all_logs = []
    
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "Runtime.consoleAPICalled":
                params = data["params"]
                api_type = params.get("type", "")
                
                if api_type in log_counts:
                    log_counts[api_type] += 1
                
                all_logs.append({
                    "type": api_type,
                    "args": params.get("args", []),
                    "timestamp": params.get("timestamp", 0),
                    "stack_trace": params.get("stackTrace", {})
                })
                
        except asyncio.TimeoutError:
            continue
    
    print("=" * 40)
    print("Console Log Statistics")
    print("=" * 40)
    for level, count in log_counts.items():
        print(f"  {level}: {count} entries")
    print(f"  Total: {len(all_logs)} entries")
    
    return {"counts": log_counts, "logs": all_logs}
```

---

## Exception Detail Parsing

### ExceptionDetails Structure Deep Dive

CDP's `Runtime.exceptionThrown` event contains rich exception information. Understanding its structure is key to building an effective error tracking system:

```python
class ExceptionDetailsParser:
    """CDP ExceptionDetails parser"""
    
    @staticmethod
    def parse(details):
        """Parse the full ExceptionDetails structure"""
        if not details:
            return {}
        
        return {
            "exception_id": details.get("exceptionId", 0),
            "text": details.get("text", ""),
            "line_number": details.get("lineNumber", 0),
            "column_number": details.get("columnNumber", 0),
            "script_id": details.get("scriptId", ""),
            "url": details.get("url", ""),
            "stack_trace": ExceptionDetailsParser.parse_stack_trace(
                details.get("stackTrace", {})
            ),
            "exception": ExceptionDetailsParser.parse_remote_object(
                details.get("exception", {})
            ),
            "execution_context_id": details.get("executionContextId", 0),
            "meta": ExceptionDetailsParser.extract_meta(details)
        }
    
    @staticmethod
    def parse_stack_trace(stack_trace):
        """Parse stack trace"""
        if not stack_trace:
            return {"call_frames": [], "description": ""}
        
        call_frames = []
        for frame in stack_trace.get("callFrames", []):
            call_frames.append({
                "function_name": frame.get("functionName", "(anonymous)"),
                "script_id": frame.get("scriptId", ""),
                "url": frame.get("url", ""),
                "line_number": frame.get("lineNumber", 0),
                "column_number": frame.get("columnNumber", 0),
            })
        
        return {
            "call_frames": call_frames,
            "description": stack_trace.get("description", ""),
            "parent": ExceptionDetailsParser.parse_stack_trace(
                stack_trace.get("parent")
            ) if stack_trace.get("parent") else None
        }
    
    @staticmethod
    def parse_remote_object(obj):
        """Parse the exception remote object"""
        if not obj:
            return {}
        
        parsed = {
            "type": obj.get("type", ""),
            "subtype": obj.get("subtype", ""),
            "class_name": obj.get("className", ""),
            "description": obj.get("description", ""),
        }
        
        if "preview" in obj:
            preview = obj["preview"]
            properties = {}
            for prop in preview.get("properties", []):
                properties[prop.get("name", "")] = {
                    "type": prop.get("type", ""),
                    "value": prop.get("value", ""),
                }
            parsed["preview_properties"] = properties
        
        return parsed
    
    @staticmethod
    def extract_meta(details):
        """Extract exception metadata"""
        meta = {}
        
        text = details.get("text", "")
        if "Uncaught" in text:
            meta["caught_status"] = "uncaught"
        elif "Caught" in text:
            meta["caught_status"] = "caught"
        else:
            meta["caught_status"] = "unknown"
        
        known_types = [
            "TypeError", "ReferenceError", "SyntaxError",
            "RangeError", "URIError", "EvalError",
            "Error", "AggregateError"
        ]
        for t in known_types:
            if t in text:
                meta["exception_type"] = t
                break
        else:
            meta["exception_type"] = "Unknown"
        
        return meta
    
    @staticmethod
    def format_exception_report(parsed):
        """Format as a readable exception report"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"Exception Report | {parsed['meta']['exception_type']} | {parsed['meta']['caught_status']}")
        lines.append("=" * 60)
        lines.append(f"Message: {parsed['text']}")
        lines.append(f"Location: {parsed['url']}:{parsed['line_number']}:{parsed['column_number']}")
        lines.append(f"Script ID: {parsed['script_id']}")
        lines.append("")
        
        if parsed['stack_trace']['call_frames']:
            lines.append("Stack Trace:")
            for i, frame in enumerate(parsed['stack_trace']['call_frames']):
                func = frame['function_name']
                loc = f"{frame['url']}:{frame['line_number']}:{frame['column_number']}"
                lines.append(f"  #{i} {func} ({loc})")
        
        if parsed['exception'].get('description'):
            lines.append("")
            lines.append(f"Exception Details: {parsed['exception']['description'][:300]}")
        
        lines.append("=" * 60)
        return "\n".join(lines)
```

### Pinpointing Exception Location

```python
class ExceptionLocator:
    """Exception location pinpointing — find exact source code position"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
    
    async def locate_exception_source(self, exception_details):
        """Get source code context around the exception location"""
        script_id = exception_details.get("scriptId", "")
        line_number = exception_details.get("lineNumber", 0)
        
        if not script_id:
            return None
        
        script_info = await cdp(self.ws, "Debugger.getScriptSource", {
            "scriptId": script_id
        }, self.session_id)
        
        source = script_info.get("scriptSource", "")
        if not source:
            return {"error": "Cannot get script source"}
        
        lines = source.split("\n")
        start_line = max(0, line_number - 3)
        end_line = min(len(lines), line_number + 2)
        
        context_lines = []
        for i in range(start_line, end_line):
            prefix = ">>>" if i == line_number else "   "
            context_lines.append(f"{prefix} {i + 1}: {lines[i]}")
        
        return {
            "script_url": script_info.get("url", "(inline script)"),
            "source_length": len(source),
            "line_count": len(lines),
            "error_line": line_number,
            "context": "\n".join(context_lines),
            "source_map_url": script_info.get("sourceMapURL", "")
        }
```

---

## Locating Source with Source Maps

### Source Map Resolution

Production JavaScript code is typically minified and bundled. CDP's `Debugger.getScriptSource` returns Source Map URLs that can help locate the original source:

```python
import urllib.request
import urllib.parse
import base64
import json

class CDPSourceMapResolver:
    """CDP Source Map resolver — map compiled positions back to source"""
    
    def __init__(self):
        self.source_map_cache = {}
    
    async def resolve(self, ws, session_id, script_id, line, column):
        """Resolve compiled position to source position"""
        script_info = await cdp(ws, "Debugger.getScriptSource", {
            "scriptId": script_id
        }, session_id)
        
        source_map_url = script_info.get("sourceMapURL", "")
        script_url = script_info.get("url", "")
        
        if not source_map_url:
            return {
                "original": False,
                "compiled_line": line,
                "compiled_column": column
            }
        
        if not source_map_url.startswith(("http://", "https://", "data:")):
            base_url = script_url.rsplit("/", 1)[0] if "/" in script_url else ""
            source_map_url = f"{base_url}/{source_map_url}"
        
        mappings = await self._fetch_and_parse_source_map(source_map_url)
        if not mappings:
            return {"original": False, "error": "Cannot fetch Source Map"}
        
        return self._reverse_mapping(mappings, line, column)
    
    async def _fetch_and_parse_source_map(self, source_map_url):
        """Fetch and parse a Source Map file"""
        if source_map_url in self.source_map_cache:
            return self.source_map_cache[source_map_url]
        
        try:
            content = None
            
            if source_map_url.startswith("data:"):
                _, encoded = source_map_url.split(",", 1)
                if source_map_url.split(";")[0].endswith("base64"):
                    content = base64.b64decode(encoded).decode("utf-8")
                else:
                    content = urllib.parse.unquote(encoded)
            else:
                req = urllib.request.Request(source_map_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8")
            
            if content:
                parsed = json.loads(content)
                self.source_map_cache[source_map_url] = parsed
                return parsed
                
        except Exception as e:
            print(f"[Source Map] Fetch failed: {source_map_url} - {e}")
        
        return None
    
    def _reverse_mapping(self, source_map, compiled_line, compiled_column):
        """Reverse mapping: compiled position -> source position"""
        sources = source_map.get("sources", [])
        names = source_map.get("names", [])
        mappings_str = source_map.get("mappings", "")
        
        return {
            "original": True,
            "source_map_url": source_map.get("file", ""),
            "sources": sources,
            "note": "Full mapping requires VLQ decoding (see mozilla/source-map)"
        }
```

### Getting Source Code Context

```python
async def get_source_context(ws, session_id, script_id, line_number, context_lines=5):
    """Get source code context around the exception location"""
    script_info = await cdp(self.ws, "Debugger.getScriptSource", {
        "scriptId": script_id
    }, session_id)
    
    source = script_info.get("scriptSource", "")
    if not source:
        return None
    
    lines = source.split("\n")
    start = max(0, line_number - context_lines)
    end = min(len(lines), line_number + context_lines + 1)
    
    context = []
    for i in range(start, end):
        is_error_line = (i == line_number)
        prefix = "->" if is_error_line else " "
        marker = "  <- Exception here" if is_error_line else ""
        context.append(f"{prefix} {i + 1}: {lines[i]}{marker}")
    
    return {
        "url": script_info.get("url", "(inline)"),
        "total_lines": len(lines),
        "error_line": line_number + 1,
        "context": "\n".join(context),
        "has_source_map": bool(script_info.get("sourceMapURL"))
    }
```

---

## Breakpoint-Level Error Inspection

### Debugger.paused Event

Beyond passive exception listening, you can use the `Debugger` domain to actively pause when an exception occurs and inspect the context:

```python
class ExceptionBreakpointInspector:
    """Exception breakpoint inspector — pause and inspect on exception"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.paused_data = []
    
    async def enable(self):
        """Enable the debugger"""
        await cdp(self.ws, "Debugger.enable", {}, self.session_id)
        await cdp(self.ws, "Debugger.setPauseOnExceptions", {
            "state": "uncaught"  # "none" | "uncaught" | "all"
        }, self.session_id)
        
        print("[Debugger] Enabled, will pause on uncaught exceptions")
    
    async def set_pause_on_all_exceptions(self):
        """Pause on all exceptions, including caught ones"""
        await cdp(self.ws, "Debugger.setPauseOnExceptions", {
            "state": "all"
        }, self.session_id)
        print("[Debugger] All exceptions will trigger a pause")
    
    async def listen_for_paused(self, duration=60):
        """Listen for Debugger.paused events"""
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Debugger.paused":
                    await self._inspect_paused_state(params)
                    await cdp(self.ws, "Debugger.resume", {}, self.session_id)
                    
                elif method == "Debugger.resumed":
                    print("[Debugger] Resumed execution")
                    
            except asyncio.TimeoutError:
                continue
    
    async def _inspect_paused_state(self, params):
        """Inspect the state when paused"""
        call_frames = params.get("callFrames", [])
        reason = params.get("reason", "")
        data = params.get("data", {})
        
        paused_info = {
            "timestamp": datetime.now().isoformat(),
            "reason": reason,
            "call_frames_count": len(call_frames),
            "top_frame": None,
            "variables": {},
            "exception": None
        }
        
        if reason == "exception":
            paused_info["exception"] = data.get("details", "")
        
        if call_frames:
            top = call_frames[0]
            location = top.get("location", {})
            function_name = top.get("functionName", "(anonymous)")
            
            paused_info["top_frame"] = {
                "function": function_name,
                "url": location.get("scriptId", "(unknown)"),
                "line": location.get("lineNumber", 0),
                "column": location.get("columnNumber", 0),
            }
            
            scope_chain = top.get("scopeChain", [])
            for scope in scope_chain:
                if scope.get("type") == "local":
                    scope_obj = scope.get("object", {})
                    object_id = scope_obj.get("objectId")
                    if object_id:
                        properties = await cdp(self.ws, "Runtime.getProperties", {
                            "objectId": object_id
                        }, self.session_id)
                        
                        for prop in properties.get("result", []):
                            name = prop.get("name", "")
                            value = prop.get("value", {})
                            paused_info["variables"][name] = {
                                "type": value.get("type", ""),
                                "value": value.get("value", str(value.get("description", "")))
                            }
        
        self.paused_data.append(paused_info)
        
        print(f"[Paused] Reason: {reason}")
        if paused_info["exception"]:
            print(f"          Exception: {paused_info['exception']}")
        if paused_info["top_frame"]:
            tf = paused_info["top_frame"]
            print(f"          Location: {tf['function']} ({tf['url']}:{tf['line']})")
        if paused_info["variables"]:
            print(f"          Local variables: {len(paused_info['variables'])}")
    
    async def disable(self):
        """Disable the debugger"""
        await cdp(self.ws, "Debugger.setPauseOnExceptions", {
            "state": "none"
        }, self.session_id)
        await cdp(self.ws, "Debugger.disable", {}, self.session_id)
        print("[Debugger] Disabled")
```

---

## Practical: Production-Grade Error Aggregation System

### Error Collection and Analysis Engine

```python
import sqlite3
import os
from collections import defaultdict

class CDPErrorAggregator:
    """CDP error aggregation system — collect, deduplicate, analyze"""
    
    def __init__(self, ws, session_id, db_path="error_tracking.db"):
        self.ws = ws
        self.session_id = session_id
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """Initialize SQLite database"""
        conn = sqlite3.connect(self.db_path)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS errors (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_type TEXT,
                message TEXT,
                url TEXT,
                line_number INTEGER,
                column_number INTEGER,
                stack_hash TEXT,
                full_stack TEXT,
                timestamp TEXT,
                page_url TEXT,
                session_id TEXT
            )
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_stack_hash 
            ON errors(stack_hash)
        """)
        conn.execute("""
            CREATE INDEX IF NOT EXISTS idx_timestamp 
            ON errors(timestamp)
        """)
        conn.commit()
        conn.close()
    
    @staticmethod
    def compute_stack_hash(stack_trace):
        """Compute stack hash for deduplication"""
        if not stack_trace:
            return "no_stack"
        
        call_frames = stack_trace.get("callFrames", [])
        key_parts = []
        for frame in call_frames[:3]:
            key_parts.append(f"{frame.get('functionName', '')}@{frame.get('lineNumber', '')}")
        
        import hashlib
        return hashlib.md5("|".join(key_parts).encode()).hexdigest() if key_parts else "no_frames"
    
    async def collect_with_aggregation(self, duration=60):
        """Collect and aggregate errors"""
        await cdp(self.ws, "Runtime.enable", {}, self.session_id)
        
        error_buffer = []
        start = asyncio.get_event_loop().time()
        current_page_url = ""
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Page.frameNavigated":
                    frame = params.get("frame", {})
                    if frame.get("id") == params.get("frame", {}).get("loaderId"):
                        current_page_url = frame.get("url", "")
                
                if method == "Runtime.exceptionThrown":
                    details = params.get("exceptionDetails", {})
                    stack_trace = details.get("stackTrace", {})
                    stack_hash = self.compute_stack_hash(stack_trace)
                    
                    entry = {
                        "error_type": details.get("text", "").split(":")[0] if ":" in details.get("text", "") else "Error",
                        "message": details.get("text", ""),
                        "url": details.get("url", ""),
                        "line_number": details.get("lineNumber", 0),
                        "column_number": details.get("columnNumber", 0),
                        "stack_hash": stack_hash,
                        "full_stack": json.dumps(stack_trace),
                        "timestamp": datetime.now().isoformat(),
                        "page_url": current_page_url,
                        "session_id": self.session_id
                    }
                    
                    error_buffer.append(entry)
                    
            except asyncio.TimeoutError:
                continue
        
        self._batch_insert(error_buffer)
        return self.generate_report(error_buffer)
    
    def _batch_insert(self, entries):
        """Batch insert errors to database"""
        conn = sqlite3.connect(self.db_path)
        conn.executemany("""
            INSERT INTO errors 
                (error_type, message, url, line_number, column_number, 
                 stack_hash, full_stack, timestamp, page_url, session_id)
            VALUES 
                (:error_type, :message, :url, :line_number, :column_number,
                 :stack_hash, :full_stack, :timestamp, :page_url, :session_id)
        """, entries)
        conn.commit()
        conn.close()
    
    def generate_report(self, error_buffer):
        """Generate error aggregation report"""
        if not error_buffer:
            return {"total": 0, "message": "No exceptions captured"}
        
        by_hash = defaultdict(lambda: {"count": 0, "first": "", "last": "", "entry": None})
        
        for entry in error_buffer:
            h = entry["stack_hash"]
            by_hash[h]["count"] += 1
            by_hash[h]["entry"] = entry
            if not by_hash[h]["first"]:
                by_hash[h]["first"] = entry["timestamp"]
            by_hash[h]["last"] = entry["timestamp"]
        
        by_type = defaultdict(int)
        for entry in error_buffer:
            by_type[entry["error_type"]] += 1
        
        by_page = defaultdict(int)
        for entry in error_buffer:
            by_page[entry["page_url"]] += 1
        
        return {
            "total": len(error_buffer),
            "unique_errors": len(by_hash),
            "collection_period": f"{error_buffer[0]['timestamp']} ~ {error_buffer[-1]['timestamp']}",
            "by_type": dict(by_type),
            "by_page": dict(by_page),
            "unique_stacks": [
                {
                    "hash": h,
                    "count": info["count"],
                    "type": info["entry"]["error_type"],
                    "message": info["entry"]["message"][:100],
                    "url": info["entry"]["url"],
                    "line": info["entry"]["line_number"],
                    "first_seen": info["first"],
                    "last_seen": info["last"]
                }
                for h, info in sorted(by_hash.items(), key=lambda x: -x[1]["count"])
            ]
        }
```

### Complete Monitoring Script

```python
async def full_error_monitor_workflow():
    """Complete error monitoring workflow"""
    async with websockets.connect(CDP_URL) as ws:
        session_id, target_id = await connect_page(ws)
        
        await cdp(ws, "Page.enable", {}, session_id)
        await cdp(ws, "Runtime.enable", {}, session_id)
        
        aggregator = CDPErrorAggregator(ws, session_id)
        
        print("=" * 60)
        print("CDP Error Tracking Monitor Started")
        print("=" * 60)
        
        await inject_test_exceptions(ws, session_id)
        
        report = await aggregator.collect_with_aggregation(60)
        
        print("\n" + "=" * 60)
        print("Error Tracking Report")
        print("=" * 60)
        print(f"Total exceptions: {report['total']}")
        print(f"Unique exceptions: {report['unique_errors']}")
        print(f"Collection period: {report['collection_period']}")
        
        if report.get("by_type"):
            print(f"\nBy type:")
            for t, c in sorted(report["by_type"].items(), key=lambda x: -x[1]):
                print(f"  {t}: {c} occurrences")
        
        if report.get("by_page"):
            print(f"\nBy page:")
            for url, count in sorted(report["by_page"].items(), key=lambda x: -x[1]):
                short_url = url[:60] + "..." if len(url) > 60 else url
                print(f"  {short_url}: {count} occurrences")
        
        if report.get("unique_stacks"):
            print(f"\nException details (top 10):")
            for i, stack in enumerate(report["unique_stacks"][:10]):
                print(f"\n  [{i + 1}] {stack['type']}: {stack['message']}")
                print(f"       Location: {stack['url']}:{stack['line']}")
                print(f"       Occurred {stack['count']} times")
        
        return report


# asyncio.run(full_error_monitor_workflow())
```

---

## Best Practices and Considerations

### Exception Tracking Strategy Comparison

| Strategy | Advantages | Disadvantages | Use Case |
|----------|------------|---------------|----------|
| exceptionThrown | Automatic, non-intrusive | Only unhandled exceptions | Basic exception monitoring |
| consoleAPICalled | Captures explicitly logged errors | Requires code cooperation with console.error | Applications with existing logging |
| Debugger.paused | Full context inspection | High performance overhead | Debugging, deep analysis |
| All combined | Full coverage, rich layers | More complex implementation | Production-grade monitoring |

### Common Issues

```python
class ErrorTrackingBestPractices:
    """Error tracking best practices"""
    
    @staticmethod
    def avoid_duplicate_capture():
        """Avoid duplicate capture — same exception may fire through multiple events"""
        pass  # Use stack_hash for deduplication
    
    @staticmethod
    def handle_cross_origin_errors():
        """Handle cross-origin errors"""
        # Cross-origin script errors will be reported as "Script error."
        # Server must set:
        # Access-Control-Allow-Origin: *
        # And script tags must include the crossorigin attribute
        pass
    
    @staticmethod
    def manage_event_buffer():
        """Manage event buffer — avoid memory overflow"""
        MAX_BUFFER_SIZE = 10000
        # Use sliding window or paged storage
        pass
    
    @staticmethod
    def respect_user_privacy():
        """Respect user privacy — do not include PII in error logs"""
        SENSITIVE_PATTERNS = [
            r"password=[^&\s]+",
            r"token=[^&\s]+",
            r"credit_card=\d+",
        ]
        # Sanitize error messages before storage
        pass
```

### Performance Considerations

```python
class ErrorTrackingPerformance:
    """Error tracking performance optimization"""
    
    @staticmethod
    def sampling_strategy(sample_rate=0.1):
        """Sampling strategy for high-traffic sites"""
        import random
        return random.random() < sample_rate
    
    @staticmethod
    def batch_before_flush(buffer_size=100, flush_interval=5):
        """Batch write strategy"""
        return {
            "buffer_size": buffer_size,
            "flush_interval_seconds": flush_interval
        }
    
    @staticmethod
    def selective_domain_enablement():
        """Selectively enable domains to reduce overhead"""
        return [
            "Runtime.enable",        # Required
            # "Debugger.enable",     # Enable on demand (high overhead)
            # "Console.enable",      # Lightweight, recommended
        ]
```

---

> **Summary in one sentence**: CDP's error tracking capabilities span from basic Runtime.exceptionThrown capture to breakpoint-level Debugger.paused inspection — combined with Source Map resolution and production-grade aggregation, this forms a complete JS exception monitoring solution. In the next chapter, we'll explore CDP's background service management — debugging Service Worker Background Sync and Background Fetch with Python.

*Previous: CDP Protocol Extensions Guide: Custom Domains & Chrome Extensions*

*Next up: CDP Background Services Guide: Managing Background Sync & Fetch with Python*