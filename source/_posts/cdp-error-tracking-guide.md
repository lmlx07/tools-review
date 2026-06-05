---
title: CDP 错误追踪指南：用 Python 捕获页面异常
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 错误追踪
  - JavaScript 调试
  - 异常监控
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）捕获和追踪 JavaScript 页面异常。涵盖 Runtime.exceptionThrown 事件、异常详情解析、Source Map 映射、断点调试与错误聚合。
---

> **一句话总结**：CDP 提供了完整的 JavaScript 异常监控能力——通过 `Runtime.exceptionThrown` 捕获未处理异常、通过 `Runtime.consoleAPICalled` 监听错误日志、通过 `Debugger.paused` 实现断点级错误检查，结合 Source Map 可以精确定位源码中的问题位置。

---

## 目录

1. [异常追踪概览](#异常追踪概览)
2. [捕获运行时异常：exceptionThrown](#捕获运行时异常exceptionthrown)
3. [监听控制台错误：consoleAPICalled](#监听控制台错误consoleapicalled)
4. [异常详情解析](#异常详情解析)
5. [结合 Source Map 定位源码位置](#结合-source-map-定位源码位置)
6. [断点级错误检查](#断点级错误检查)
7. [实战：生产级错误聚合系统](#实战生产级错误聚合系统)
8. [最佳实践与注意事项](#最佳实践与注意事项)

---

## 异常追踪概览

JavaScript 异常追踪是前端监控的核心需求。CDP 提供了多层次的异常捕获能力：

| 捕获方式 | CDP 机制 | 适用场景 |
|----------|----------|----------|
| 未处理异常 | `Runtime.exceptionThrown` 事件 | 自动捕获所有未捕获的异常 |
| 控制台错误 | `Runtime.consoleAPICalled` + `console.error()` | 捕获主动记录的异常 |
| 断点调试 | `Debugger.paused` + 断点条件 | 精确控制异常发生时暂停检查 |
| 异常过滤 | `Runtime.exceptionThrown` 的 ExceptionDetails | 分析异常类型、堆栈、位置 |

CDP 的异常追踪区别于传统 `window.onerror` 或 `try/catch` 的地方在于：

1. **浏览器级别**——在 JS 引擎层面捕获，不依赖页面代码覆盖
2. **完整堆栈**——提供完整的 `stackTrace`，包含调用帧的精确位置
3. **Source Map 支持**——可以映射回原始源码位置
4. **跨生命周期**——页面刷新、导航后仍然有效

---

## 捕获运行时异常：exceptionThrown

### 基础异常监听

`Runtime.exceptionThrown` 事件会在每次 JavaScript 异常未被 `try/catch` 捕获时自动触发。这是最基础的异常捕获模式：

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
    """连接到第一个可用的页面目标"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    result = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return result["sessionId"], target_id


async def listen_exceptions(ws, session_id, duration=30):
    """监听 Runtime.exceptionThrown 事件"""
    await cdp(ws, "Runtime.enable", {}, session_id)
    
    exceptions = []
    start = asyncio.get_event_loop().time()
    
    print("开始监听 JavaScript 异常...")
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
                
                print(f"[异常] {details.get('text', '')}")
                print(f"       位置: {details.get('url', '')}:{details.get('lineNumber', '')}:{details.get('columnNumber', '')}")
                print(f"       时间: {exception_info['timestamp']}")
                print()
                
        except asyncio.TimeoutError:
            continue
    
    print(f"共捕获 {len(exceptions)} 个异常")
    return exceptions
```

### 注入测试异常

```python
async def inject_test_exceptions(ws, session_id):
    """注入测试用的 JavaScript 异常"""
    test_cases = [
        # 1. 基本类型错误
        ("TypeError", """
        (function() {
            const obj = null;
            return obj.property;
        })();
        """),
        # 2. 引用错误
        ("ReferenceError", """
        console.log(undefinedVariable);
        """),
        # 3. 语法错误（需要在 eval 中）
        ("SyntaxError", """
        try {
            eval('if (true) { break; }');
        } catch(e) {
            throw e;
        }
        """),
        # 4. 范围错误
        ("RangeError", """
        (function() {
            const arr = new Array(-1);
        })();
        """),
        # 5. 自定义错误
        ("CustomError", """
        throw new Error('这是一个自定义业务错误');
        """),
    ]
    
    for name, code in test_cases:
        try:
            await cdp(ws, "Runtime.evaluate", {
                "expression": code,
                "returnByValue": True
            }, session_id)
            print(f"[注入] 已触发 {name}")
        except Exception as e:
            print(f"[注入] {name} 执行失败: {e}")
        await asyncio.sleep(0.5)
```

---

## 监听控制台错误：consoleAPICalled

### 捕获 console.error 日志

除了自动触发的异常，许多代码使用 `console.error()` 主动记录错误。通过 `Runtime.consoleAPICalled` 可以捕获这些主动日志：

```python
class ConsoleErrorCollector:
    """收集通过 console API 发出的错误"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.errors = []
        self._running = False
    
    async def enable(self):
        """启用控制台监控"""
        await cdp(self.ws, "Runtime.enable", {}, self.session_id)
        # 启用 Console 域以获取更详细的信息
        await cdp(self.ws, "Console.enable", {}, self.session_id)
        self._running = True
    
    def parse_console_args(self, args):
        """解析 console API 的参数"""
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
        """收集指定时间内的错误"""
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
        """获取错误摘要"""
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

### 区分不同类型的控制台日志

```python
async def monitor_all_console_levels(ws, session_id, duration=20):
    """监控所有控制台日志级别"""
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
    print("控制台日志统计")
    print("=" * 40)
    for level, count in log_counts.items():
        icon = {"error": "🔴", "warn": "🟡", "log": "⚪", "info": "🔵", "debug": "🟣"}
        print(f"  {icon.get(level, '•')} {level}: {count} 条")
    print(f"  总计: {len(all_logs)} 条")
    
    return {"counts": log_counts, "logs": all_logs}
```

---

## 异常详情解析

### ExceptionDetails 结构详解

CDP 的 `Runtime.exceptionThrown` 事件包含详尽的异常信息。理解其结构是构建高效错误追踪系统的关键：

```python
class ExceptionDetailsParser:
    """CDP ExceptionDetails 解析器"""
    
    @staticmethod
    def parse(details):
        """解析完整的 ExceptionDetails 结构"""
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
        """解析堆栈跟踪"""
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
        """解析异常对象"""
        if not obj:
            return {}
        
        parsed = {
            "type": obj.get("type", ""),
            "subtype": obj.get("subtype", ""),
            "class_name": obj.get("className", ""),
            "description": obj.get("description", ""),
        }
        
        # 如果异常对象有展开属性，一并提取
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
        """提取异常的元信息"""
        meta = {}
        
        # 从文本中推断异常类型
        text = details.get("text", "")
        if "Uncaught" in text:
            meta["caught_status"] = "uncaught"
        elif "Caught" in text:
            meta["caught_status"] = "caught"
        else:
            meta["caught_status"] = "unknown"
        
        # 提取异常类型名
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
        """格式化为可读的异常报告"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"异常报告 | {parsed['meta']['exception_type']} | {parsed['meta']['caught_status']}")
        lines.append("=" * 60)
        lines.append(f"消息: {parsed['text']}")
        lines.append(f"位置: {parsed['url']}:{parsed['line_number']}:{parsed['column_number']}")
        lines.append(f"脚本 ID: {parsed['script_id']}")
        lines.append("")
        
        if parsed['stack_trace']['call_frames']:
            lines.append("堆栈跟踪:")
            for i, frame in enumerate(parsed['stack_trace']['call_frames']):
                func = frame['function_name']
                loc = f"{frame['url']}:{frame['line_number']}:{frame['column_number']}"
                lines.append(f"  #{i} {func} ({loc})")
        
        if parsed['exception'].get('description'):
            lines.append("")
            lines.append(f"异常详情: {parsed['exception']['description'][:300]}")
        
        lines.append("=" * 60)
        return "\n".join(lines)
```

### 精确定位异常

```python
class ExceptionLocator:
    """异常位置精确定位器——确定异常在源码中的确切位置"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
    
    async def locate_exception_source(self, exception_details):
        """获取异常位置的源码上下文"""
        script_id = exception_details.get("scriptId", "")
        line_number = exception_details.get("lineNumber", 0)
        
        if not script_id:
            return None
        
        # 获取脚本源码
        script_info = await cdp(self.ws, "Debugger.getScriptSource", {
            "scriptId": script_id
        }, self.session_id)
        
        source = script_info.get("scriptSource", "")
        if not source:
            return {"error": "无法获取脚本源码"}
        
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

## 结合 Source Map 定位源码位置

### Source Map 映射

生产环境中 JavaScript 代码通常被压缩和混淆。CDP 的 `Debugger.getScriptSource` 返回的 Source Map URL 可以帮助我们定位到原始源码：

```python
import urllib.request
import urllib.parse
import base64
import json

class CDPSourceMapResolver:
    """CDP Source Map 解析器——将压缩后的位置映射回源码"""
    
    def __init__(self):
        self.source_map_cache = {}
    
    async def resolve(self, ws, session_id, script_id, line, column):
        """解析压缩代码中的位置到源码位置"""
        # 获取脚本信息
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
        
        # 解析 Source Map URL（处理相对路径）
        if not source_map_url.startswith(("http://", "https://", "data:")):
            base_url = script_url.rsplit("/", 1)[0] if "/" in script_url else ""
            source_map_url = f"{base_url}/{source_map_url}"
        
        # 获取并解析 Source Map
        mappings = await self._fetch_and_parse_source_map(source_map_url)
        if not mappings:
            return {"original": False, "error": "无法获取 Source Map"}
        
        # 反向映射
        return self._reverse_mapping(mappings, line, column)
    
    async def _fetch_and_parse_source_map(self, source_map_url):
        """获取并解析 Source Map 文件"""
        if source_map_url in self.source_map_cache:
            return self.source_map_cache[source_map_url]
        
        try:
            content = None
            
            if source_map_url.startswith("data:"):
                # data URL 方式的 Source Map
                _, encoded = source_map_url.split(",", 1)
                if source_map_url.split(";")[0].endswith("base64"):
                    content = base64.b64decode(encoded).decode("utf-8")
                else:
                    content = urllib.parse.unquote(encoded)
            else:
                # HTTP 方式的 Source Map
                req = urllib.request.Request(source_map_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read().decode("utf-8")
            
            if content:
                parsed = json.loads(content)
                self.source_map_cache[source_map_url] = parsed
                return parsed
                
        except Exception as e:
            print(f"[Source Map] 获取失败: {source_map_url} - {e}")
        
        return None
    
    def _reverse_mapping(self, source_map, compiled_line, compiled_column):
        """反向映射：编译后位置 -> 源码位置"""
        # VLQ 解码的简化版本
        # 实际项目中应使用成熟的 VLQ 解码库
        
        sources = source_map.get("sources", [])
        names = source_map.get("names", [])
        mappings_str = source_map.get("mappings", "")
        
        # 这里演示基本映射逻辑
        # 完整实现需要 VLQ 解码（参考 source-map 库）
        return {
            "original": True,
            "source_map_url": source_map.get("file", ""),
            "sources": sources,
            "note": "完整映射需要 VLQ 解码（参考 mozilla/source-map）"
        }
```

### 获取源码上下文

```python
async def get_source_context(ws, session_id, script_id, line_number, context_lines=5):
    """获取异常位置的源码上下文"""
    script_info = await cdp(ws, "Debugger.getScriptSource", {
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
        prefix = "→" if is_error_line else " "
        marker = "  ← 异常位置" if is_error_line else ""
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

## 断点级错误检查

### Debugger.paused 事件

除了被动监听异常，你还可以使用 `Debugger` 域在异常发生时主动暂停，进行现场检查：

```python
class ExceptionBreakpointInspector:
    """异常断点检查器——异常发生时暂停并检查上下文"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.paused_data = []
    
    async def enable(self):
        """启用调试器"""
        await cdp(self.ws, "Debugger.enable", {}, self.session_id)
        
        # 设置在异常时暂停
        await cdp(self.ws, "Debugger.setPauseOnExceptions", {
            "state": "uncaught"  # "none" | "uncaught" | "all"
        }, self.session_id)
        
        print("[调试器] 已启用，将在未捕获异常时暂停")
    
    async def set_pause_on_all_exceptions(self):
        """设置为所有异常（包括 try/catch 捕获的）都暂停"""
        await cdp(self.ws, "Debugger.setPauseOnExceptions", {
            "state": "all"
        }, self.session_id)
        print("[调试器] 所有异常都将触发暂停")
    
    async def listen_for_paused(self, duration=60):
        """监听 Debugger.paused 事件"""
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Debugger.paused":
                    await self._inspect_paused_state(params)
                    
                    # 继续执行
                    await cdp(self.ws, "Debugger.resume", {}, self.session_id)
                    
                elif method == "Debugger.resumed":
                    print("[调试器] 继续执行")
                    
            except asyncio.TimeoutError:
                continue
    
    async def _inspect_paused_state(self, params):
        """检查暂停时的状态"""
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
            
            # 获取局部变量
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
        
        print(f"[暂停] 原因: {reason}")
        if paused_info["exception"]:
            print(f"       异常: {paused_info['exception']}")
        if paused_info["top_frame"]:
            tf = paused_info["top_frame"]
            print(f"       位置: {tf['function']} ({tf['url']}:{tf['line']})")
        if paused_info["variables"]:
            print(f"       局部变量: {len(paused_info['variables'])} 个")
    
    async def disable(self):
        """禁用调试器"""
        await cdp(self.ws, "Debugger.setPauseOnExceptions", {
            "state": "none"
        }, self.session_id)
        await cdp(self.ws, "Debugger.disable", {}, self.session_id)
        print("[调试器] 已禁用")
```

---

## 实战：生产级错误聚合系统

### 错误收集与分析引擎

```python
import sqlite3
import os
from collections import defaultdict

class CDPErrorAggregator:
    """CDP 错误聚合系统——收集、去重、分析页面异常"""
    
    def __init__(self, ws, session_id, db_path="error_tracking.db"):
        self.ws = ws
        self.session_id = session_id
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化 SQLite 数据库"""
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
        """计算堆栈的哈希值用于去重"""
        if not stack_trace:
            return "no_stack"
        
        call_frames = stack_trace.get("callFrames", [])
        # 取前 3 帧的函数名和行号作为去重依据
        key_parts = []
        for frame in call_frames[:3]:
            key_parts.append(f"{frame.get('functionName', '')}@{frame.get('lineNumber', '')}")
        
        return hashlib.md5("|".join(key_parts).encode()).hexdigest() if key_parts else "no_frames"
    
    async def collect_with_aggregation(self, duration=60):
        """收集并聚合错误"""
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
        
        # 批量写入数据库
        self._batch_insert(error_buffer)
        
        return self.generate_report(error_buffer)
    
    def _batch_insert(self, entries):
        """批量写入错误到数据库"""
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
        """生成错误聚合报告"""
        if not error_buffer:
            return {"total": 0, "message": "未捕获到异常"}
        
        # 按 stack_hash 去重统计
        by_hash = defaultdict(lambda: {"count": 0, "first": "", "last": "", "entry": None})
        
        for entry in error_buffer:
            h = entry["stack_hash"]
            by_hash[h]["count"] += 1
            by_hash[h]["entry"] = entry
            if not by_hash[h]["first"]:
                by_hash[h]["first"] = entry["timestamp"]
            by_hash[h]["last"] = entry["timestamp"]
        
        # 按错误类型统计
        by_type = defaultdict(int)
        for entry in error_buffer:
            by_type[entry["error_type"]] += 1
        
        # 按页面 URL 统计
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

### 完整监控脚本

```python
async def full_error_monitor_workflow():
    """完整的错误监控工作流"""
    async with websockets.connect(CDP_URL) as ws:
        # 1. 连接到页面
        session_id, target_id = await connect_page(ws)
        
        # 2. 启用必要的域
        await cdp(ws, "Page.enable", {}, session_id)
        await cdp(ws, "Runtime.enable", {}, session_id)
        
        # 3. 创建聚合器
        aggregator = CDPErrorAggregator(ws, session_id)
        
        print("=" * 60)
        print("CDP 错误追踪监控启动")
        print("=" * 60)
        
        # 4. 注入测试异常（模拟生产环境）
        await inject_test_exceptions(ws, session_id)
        
        # 5. 收集并聚合错误
        report = await aggregator.collect_with_aggregation(60)
        
        # 6. 输出报告
        print("\n" + "=" * 60)
        print("错误追踪报告")
        print("=" * 60)
        print(f"总计异常: {report['total']}")
        print(f"唯一异常: {report['unique_errors']}")
        print(f"收集时段: {report['collection_period']}")
        
        if report.get("by_type"):
            print(f"\n按类型分布:")
            for t, c in sorted(report["by_type"].items(), key=lambda x: -x[1]):
                print(f"  {t}: {c} 次")
        
        if report.get("by_page"):
            print(f"\n按页面分布:")
            for url, count in sorted(report["by_page"].items(), key=lambda x: -x[1]):
                short_url = url[:60] + "..." if len(url) > 60 else url
                print(f"  {short_url}: {count} 次")
        
        if report.get("unique_stacks"):
            print(f"\n异常详情 (前 10):")
            for i, stack in enumerate(report["unique_stacks"][:10]):
                print(f"\n  [{i + 1}] {stack['type']}: {stack['message']}")
                print(f"      位置: {stack['url']}:{stack['line']}")
                print(f"      出现 {stack['count']} 次")
        
        return report


# asyncio.run(full_error_monitor_workflow())
```

---

## 最佳实践与注意事项

### 异常追踪策略对比

| 策略 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| exceptionThrown | 自动捕获、无侵入 | 只捕获未处理异常 | 基础异常监控 |
| consoleAPICalled | 可捕获主动记录的错误 | 需要代码配合 console.error | 已有日志体系的应用 |
| Debugger.paused | 可检查完整上下文 | 性能开销大 | 调试、深度分析 |
| 三者结合 | 全覆盖、层次丰富 | 实现略复杂 | 生产级监控系统 |

### 常见问题

```python
class ErrorTrackingBestPractices:
    """错误追踪最佳实践"""
    
    @staticmethod
    def avoid_duplicate_capture():
        """避免重复捕获——同一个异常可能通过多个事件触发"""
        pass  # 使用 stack_hash 去重
    
    @staticmethod
    def handle_cross_origin_errors():
        """处理跨域错误"""
        # 跨域脚本的错误 will be reported as "Script error."
        # 需要在服务端设置:
        # Access-Control-Allow-Origin: *
        # 并在 script 标签添加 crossorigin 属性
        pass
    
    @staticmethod
    def manage_event_buffer():
        """管理事件缓冲区——避免内存溢出"""
        MAX_BUFFER_SIZE = 10000
        # 使用滑动窗口或分页存储
        pass
    
    @staticmethod
    def respect_user_privacy():
        """尊重用户隐私——不要在错误日志中包含个人信息"""
        SENSITIVE_PATTERNS = [
            r"password=[^&\s]+",
            r"token=[^&\s]+",
            r"credit_card=\d+",
        ]
        # 在存储前清洗错误消息
        pass
```

### 性能考虑

```python
class ErrorTrackingPerformance:
    """错误追踪性能优化"""
    
    @staticmethod
    def sampling_strategy(sample_rate=0.1):
        """采样策略——高流量站点避免全部捕获"""
        import random
        return random.random() < sample_rate
    
    @staticmethod
    def batch_before_flush(buffer_size=100, flush_interval=5):
        """批量写入策略"""
        return {
            "buffer_size": buffer_size,
            "flush_interval_seconds": flush_interval
        }
    
    @staticmethod
    def selective_domain_enablement():
        """选择性启用域——只启用需要的 CDP 域以降低开销"""
        return [
            "Runtime.enable",        # 必须
            # "Debugger.enable",     # 按需启用（性能开销大）
            # "Console.enable",      # 轻量级，建议启用
        ]
```

---

> **一句话总结**：CDP 的错误追踪能力从 Runtime.exceptionThrown 的基础捕获到 Debugger.paused 的断点级调试，结合 Source Map 映射和生产级聚合，构成了一个完整的 JS 异常监控解决方案。下一章我们将探索 CDP 的后台服务管理能力——如何用 Python 调试 Service Worker 的 Background Sync 和 Background Fetch。

*上一篇回顾：CDP 协议扩展指南：自定义 CDP 域与 Chrome 扩展。*

*下一篇预告：CDP 后台服务指南：用 Python 管理 Background Sync 与 Fetch。*