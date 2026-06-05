---
title: CDP Console 调试指南：用 Python 捕获页面日志与异常
date: 2026-06-05 18:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Console
  - 调试
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）捕获页面控制台输出。涵盖监听 console.log/warn/error、捕获未捕获异常、过滤日志级别、注入自定义 console 命令，以及实时监控页面错误的自动化工具。
---

> **一句话总结**：CDP 的 Console API 让你可以捕获浏览器控制台的所有输出——包括 log、warn、error、断言失败和未捕获异常——就像打开 DevTools 的 Console 面板一样。

---

## 目录

1. [为什么用 CDP 捕获 Console](#为什么用-cdp-捕获-console)
2. [基础用法：监听控制台消息](#基础用法监听控制台消息)
3. [捕获 JavaScript 异常](#捕获-javascript-异常)
4. [过滤与分类日志](#过滤与分类日志)
5. [注入自定义 Console 命令](#注入自定义-console-命令)
6. [实战：自动化错误监控](#实战自动化错误监控)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 捕获 Console

在前端开发中，我们通常在 DevTools 中手动查看 Console。但在自动化测试中，我们需要以编程方式捕获这些信息：

| 功能 | DevTools Console | CDP Console API |
|------|-----------------|-----------------|
| console.log/warn/error | ✅ 实时显示 | ✅ 可捕获 |
| 未捕获异常 | ✅ 显示 | ✅ 可捕获 |
| 网络错误 | ✅ 显示 | ✅ 通过 Network 域 |
| 断言失败 | ✅ 显示 | ✅ 可捕获 |
| 过滤/分类 | ✅ 手动过滤 | ✅ 编程分类 |
| 历史回溯 | ✅ 保留 | ✅ 持续收集 |
| CI/CD 集成 | ❌ 无法自动化 | ✅ 完全可编程 |

---

## 基础用法：监听控制台消息

### 启用 Console 域并监听消息

```python
import asyncio
import websockets
import json
from datetime import datetime

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
    """启用 Console 域消息推送"""
    return await cdp(ws, session_id, "Console.enable")


async def collect_console_messages(ws, session_id, duration=10):
    """在指定时间内收集控制台消息"""
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
                    "level": msg_data["level"],      # log, info, warning, error, debug
                    "text": msg_data["text"],
                    "source": msg_data["source"],    # javascript, network, console-api, etc.
                    "timestamp": msg_data.get("timestamp", 0),
                    "url": msg_data.get("url", ""),
                    "line": msg_data.get("line", 0),
                    "column": msg_data.get("column", 0)
                })
                
        except asyncio.TimeoutError:
            continue
    
    return messages


# 使用示例
async def capture_page_logs():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        
        await cdp(ws, session_id, "Page.navigate", {
            "url": "https://example.com"
        })
        
        print("开始收集控制台消息...")
        logs = await collect_console_messages(ws, session_id, duration=10)
        
        print(f"共收集 {len(logs)} 条控制台消息")
        for log in logs:
            print(f"[{log['level'].upper()}] {log['text'][:100]}")
```

### Console API 消息结构

每条控制台消息包含以下字段：

```python
{
    "level": "error",           # 级别: log | info | warning | error | debug
    "text": "Uncaught TypeError: ...",  # 消息文本
    "source": "javascript",     # 来源: javascript | network | console-api | ...
    "timestamp": 1700000000000, # 时间戳（毫秒）
    "url": "https://example.com/app.js",  # 来源 URL
    "line": 42,                 # 行号
    "column": 10,               # 列号
    "stackTrace": {            # 堆栈跟踪（如有）
        "callFrames": [...]
    }
}
```

---

## 捕获 JavaScript 异常

### 通过 Runtime 域监听异常

除了 Console 域，`Runtime` 域提供更详细的异常信息：

```python
async def enable_runtime(ws, session_id):
    """启用 Runtime 域"""
    return await cdp(ws, session_id, "Runtime.enable")


async def capture_exceptions(ws, session_id, duration=10):
    """捕获 JavaScript 运行时异常"""
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
                    "column": exc.get("columnNumber", 0),
                    "stack_trace": exc.get("stackTrace", {}),
                    "exception": exc.get("exception", {}),
                })
                print(f"[异常] {exc.get('text', '')}")
            
            elif method == "Runtime.consoleAPICalled":
                # 比 Console.messageAdded 更详细的 console 调用
                api_data = data["params"]
                args = [a.get("value", str(a.get("description", ""))) 
                        for a in api_data.get("args", [])]
                exceptions.append({
                    "type": "console_api",
                    "level": api_data.get("type", ""),  # log, error, warn, etc.
                    "text": " ".join(str(a) for a in args),
                    "timestamp": api_data.get("timestamp", 0),
                    "stack_trace": api_data.get("stackTrace", {}),
                })
                
        except asyncio.TimeoutError:
            continue
    
    return exceptions


def format_exception(exc):
    """格式化异常信息"""
    text = exc.get("text", exc.get("text", ""))
    url = exc.get("url", "")
    line = exc.get("line", 0)
    
    # 提取堆栈
    stack = exc.get("stack_trace", {})
    frames = stack.get("callFrames", [])
    
    result = f"[{exc.get('type', 'exception').upper()}] {text}\n"
    result += f"  位置: {url}:{line}\n"
    
    for frame in frames[:5]:  # 最多显示 5 层栈
        result += f"    at {frame.get('functionName', '(anonymous)')} "
        result += f"({frame.get('url', '')}:{frame.get('lineNumber', 0)})\n"
    
    return result
```

### Console API vs Runtime API 的选择

```python
"""
Console.messageAdded  vs  Runtime.consoleAPICalled
─────────────────────────────────────────────────
更简单，文本格式            更详细，包含参数类型
适合快速收集                  适合深度分析
无堆栈信息                    包含堆栈跟踪
需要 Console.enable          需要 Runtime.enable

建议：
- 快速检查：用 Console
- 异常调试：用 Runtime
- 两者同时启用效果最好
"""
```

---

## 过滤与分类日志

### 按级别过滤

```python
async def collect_filtered_logs(ws, session_id, duration=10, min_level="info"):
    """按最小级别过滤收集日志"""
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
                level = msg_data["level"]
                
                if levels.get(level, 1) >= min_level_num:
                    filtered.append(msg_data)
                    
        except asyncio.TimeoutError:
            continue
    
    # 按级别分类
    by_level = {}
    for log in filtered:
        level = log["level"]
        if level not in by_level:
            by_level[level] = []
        by_level[level].append(log["text"])
    
    return {
        "total": len(filtered),
        "by_level": by_level,
        "raw": filtered
    }
```

### 按来源分类

```python
async def categorize_logs(ws, session_id, duration=10):
    """按消息来源分类"""
    logs = await collect_console_messages(ws, session_id, duration)
    
    categories = {
        "javascript": [],      # JS 运行时消息
        "console_api": [],     # console.log/warn/error 等
        "network": [],         # 网络相关消息
        "security": [],        # 安全策略消息
        "other": []
    }
    
    for log in logs:
        source = log.get("source", "other")
        if source in categories:
            categories[source].append(log)
        else:
            categories["other"].append(log)
    
    print("日志分类统计:")
    for source, items in categories.items():
        print(f"  {source}: {len(items)} 条")
    
    return categories
```

---

## 注入自定义 Console 命令

通过 `Page.addScriptToEvaluateOnNewDocument` 可以注入自定义的 console 方法：

```python
async def inject_console_monitor(ws, session_id):
    """
    注入自定义 console 方法，实现：
    1. 给所有 console 输出添加时间戳前缀
    2. 拦截 console.error 并触发自定义回调
    """
    script = """
    (function() {
        const originalError = console.error;
        const originalWarn = console.warn;
        const originalLog = console.log;
        
        // 给日志添加时间戳前缀
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
            // 发送自定义事件
            window.__cdp_error_happened__ = true;
            originalError.apply(console, [timestamp(), '[ERROR]', ...args]);
        };
        
        console.info('Console monitor injected');
    })();
    """
    
    return await cdp(ws, session_id, "Page.addScriptToEvaluateOnNewDocument", {
        "source": script
    })
```

### 监控特定类型的日志

```python
async def monitor_api_errors(ws, session_id, duration=30):
    """专门监控 API 相关的错误日志"""
    logs = await collect_console_messages(ws, session_id, duration)
    
    # 过滤包含 API 关键词的日志
    api_keywords = ["api", "fetch", "xhr", "axios", "timeout", "5xx", "4xx", "network"]
    
    api_logs = []
    for log in logs:
        text = log.get("text", "").lower()
        if any(kw in text for kw in api_keywords):
            api_logs.append(log)
    
    errors = [l for l in api_logs if l["level"] == "error"]
    warnings = [l for l in api_logs if l["level"] == "warning"]
    
    print(f"API 相关日志: {len(api_logs)} 条")
    print(f"  - 错误: {len(errors)} 条")
    print(f"  - 警告: {len(warnings)} 条")
    
    return api_logs
```

---

## 实战：自动化错误监控

综合运用 Console + Runtime 域，实现一个页面错误监控器：

```python
async def monitor_page_errors(ws, session_id, url, duration=30):
    """
    监控页面在指定时间内的所有错误
    返回结构化错误报告
    """
    # 1. 启用所有需要的域
    await enable_console(ws, session_id)
    await enable_runtime(ws, session_id)
    
    # 2. 注入自定义监控
    await inject_console_monitor(ws, session_id)
    
    # 3. 导航到目标页面
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(2)
    
    # 4. 收集错误
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
    
    # 5. 生成报告
    report = {
        "url": url,
        "duration": duration,
        "total_errors": len(errors),
        "errors_by_type": {},
        "errors": errors
    }
    
    for err in errors:
        err_type = err["type"]
        if err_type not in report["errors_by_type"]:
            report["errors_by_type"][err_type] = 0
        report["errors_by_type"][err_type] += 1
    
    print(f"\n=== 错误监控报告 ===")
    print(f"URL: {url}")
    print(f"监控时长: {duration}s")
    print(f"总错误数: {report['total_errors']}")
    print(f"按类型分布:")
    for err_type, count in report["errors_by_type"].items():
        print(f"  {err_type}: {count} 条")
    
    return report


async def continuous_monitor(ws, session_id, check_interval=60):
    """持续监控页面错误（每 check_interval 秒报告一次）"""
    print(f"开始持续监控，每 {check_interval}s 报告一次...")
    
    all_errors = []
    while True:
        errors = await monitor_page_errors(ws, session_id, "", duration=check_interval)
        if errors["total_errors"] > 0:
            all_errors.extend(errors["errors"])
            print(f"[{datetime.now().isoformat()}] 新发现 {errors['total_errors']} 个错误")
        
        # 这里可以加入告警逻辑
        if errors["total_errors"] > 10:
            print("⚠️ 错误数超过阈值！")
```

---

## 常见踩坑与最佳实践

### 踩坑 1：Console.enable 必须在导航前或导航后重新启用

```python
# ❌ 导航会重置 Console 状态
await enable_console(ws, session_id)
await cdp(ws, session_id, "Page.navigate", {"url": url})
# 导航后 Console 事件不再推送！

# ✅ 导航后重新启用
await cdp(ws, session_id, "Page.navigate", {"url": url})
await enable_console(ws, session_id)  # 重新启用
```

### 踩坑 2：Runtime.consoleAPICalled 需要先 Runtime.enable

```python
# ❌ 只启用了 Console 域
await cdp(ws, session_id, "Console.enable")
# 收不到 Runtime.consoleAPICalled 事件

# ✅ 同时启用 Runtime
await cdp(ws, session_id, "Console.enable")
await cdp(ws, session_id, "Runtime.enable")
```

### 踩坑 3：异常堆栈可能为空

如果代码经过压缩或使用了 eval，异常可能不包含堆栈信息：

```python
exc = data["params"]["exceptionDetails"]
if not exc.get("stackTrace"):
    # 压缩代码或 eval 中的异常可能没有堆栈
    print("警告：无堆栈信息，可能是压缩代码")
```

### 踩坑 4：console 消息可能包含非字符串参数

```python
# 页面执行：console.log({foo: "bar"}, [1,2,3], null, undefined)
# Console.messageAdded 的 text 字段可能是 JSON 或 "undefined"

# 更好的方式是用 Runtime.consoleAPICalled
# 它的 args 字段包含每个参数的类型描述
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 导航后重启用 | 导航会重置 Console 推送状态 |
| Console + Runtime 同时开 | 两者互补，同时启用信息最全 |
| 异常堆栈 | 压缩代码可能无堆栈 |
| 参数类型 | 用 Runtime.consoleAPICalled 获取完整参数 |
| 日志量 | 长时间监控建议定期清理缓冲区 |
| 注入脚本时机 | 用 addScriptToEvaluateOnNewDocument 确保注入 |

---

## 完整参考：CDP Console 调试类

```python
import asyncio
import json
from datetime import datetime


class CDPConsoleMonitor:
    """CDP Console 监控器"""
    
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
            "warning_count": sum(1 for m in self.messages if m["level"] == "warning"),
        }
    
    def print_summary(self):
        errors = [m for m in self.messages if m["level"] == "error"]
        warnings = [m for m in self.messages if m["level"] == "warning"]
        print(f"Messages: {len(self.messages)}, "
              f"Errors: {len(errors)}, "
              f"Exceptions: {len(self.exceptions)}")
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    monitor = CDPConsoleMonitor(ws, session_id)
    await monitor.start()
    
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    
    result = await monitor.collect(duration=10)
    monitor.print_summary()
```

---

> **总结**：CDP 的 Console 和 Runtime API 可以捕获浏览器控制台的所有输出——普通日志、警告、错误、异常。结合异常堆栈分析，你可以构建自动化的页面错误监控系统，在 CI/CD 中及时发现问题。

---

*上一篇回顾：CDP 截图与 PDF 导出指南——用 Python 生成精确页面快照。*

*下一篇预告：CDP 存储操作指南——如何操作 LocalStorage、IndexedDB 和 CacheStorage。*
