---
title: CDP 事件系统指南：用 Python 监听浏览器事件
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 浏览器自动化
  - 事件驱动
categories:
  - CDP 进阶
  - Python 实战
description: 详解 Chrome DevTools Protocol（CDP）的事件驱动机制。涵盖如何监听 CDP 事件、一次性 vs 持久监听模式、常见事件类型（网络请求、页面加载、控制台消息等）、事件过滤与节流，以及完整的事件管理器封装类。
---

> **一句话总结**：CDP 的事件系统是浏览器自动化的"消息总线"——你不再是轮询检查页面状态，而是让浏览器在事件发生时主动通知你，实现真正的响应式自动化。

---

## 目录

1. [为什么需要 CDP 事件系统](#为什么需要-cdp-事件系统)
2. [前置准备：连接 Chrome](#前置准备连接-chrome)
3. [理解 CDP 事件模型](#理解-cdp-事件模型)
4. [监听事件：基础模式](#监听事件基础模式)
5. [一次性 vs 持久监听](#一次性-vs-持久监听)
6. [常见 CDP 事件及应用](#常见-cdp-事件及应用)
7. [事件过滤与节流](#事件过滤与节流)
8. [完整参考：CDP 事件管理器](#完整参考cdp-事件管理器)
9. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么需要 CDP 事件系统

在之前的文章中，我们都是"主动"调用 CDP 命令——发送请求、等待响应。但有些场景需要"被动"响应：

| 场景 | 主动轮询 | CDP 事件监听 |
|------|---------|-------------|
| 等待页面加载完成 | `Page.loadEventFired` 后续处理 | ✅ 事件触发即知 |
| 监听网络请求 | 定时 `Network.getCookies` | ✅ 实时推送 |
| 捕获 JS 异常 | 轮询 `Runtime.evaluate` | ✅ 异常时自动通知 |
| 检测 DOM 变化 | MutationObserver 轮询 | ✅ CDP DOM 事件推送 |

CDP 事件让自动化脚本从"定时查"变成"等着听"——更及时、更高效。

---

## 前置准备：连接 Chrome

使用标准的 CDP 连接模式，与之前文章一致：

```python
import asyncio, json, websockets

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    """发送 CDP 命令并等待返回"""
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
    """连接到页面目标并返回 session_id"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

---

## 理解 CDP 事件模型

CDP 的 WebSocket 连接上会收到两类消息：

1. **命令响应**（带 `id` 字段）—— 对应 `cdp()` 函数的返回值
2. **事件推送**（带 `method` 字段，无 `id`）—— 浏览器主动推送的通知

```python
# 从 WebSocket 收到的消息示例
{
    "method": "Network.requestWillBeSent",  # ← 这是事件
    "params": {
        "requestId": "12345",
        "request": {"url": "https://example.com/api", "method": "GET"},
        "timestamp": 1234567.89
    }
}
```

事件推送的特点：
- **没有 `id` 字段**，只有 `method` 和 `params`
- **需要先启用**对应域（domain），例如 `Network.enable` 后才能收到网络事件
- **异步到达**，任何时候都可能推送

---

## 监听事件：基础模式

### 简单事件监听器

```python
async def listen_events(ws, session_id, timeout=30):
    """监听 CDP 事件，在超时或遇到特定事件时返回"""
    # 先启用 Network 域
    await cdp(ws, "Network.enable", session_id=session_id)
    
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                # 跳过命令响应（有 id 字段）
                if "id" in data:
                    continue
                
                method = data.get("method", "")
                params = data.get("params", {})
                
                print(f"[事件] {method}")
                
                # 示例：检测到页面加载完成就停止
                if method == "Page.loadEventFired":
                    print("页面加载完成！")
                    return params
                
                # 示例：检测到网络请求
                if method == "Network.requestWillBeSent":
                    req = params.get("request", {})
                    print(f"  请求: {req.get('url', '')[:80]}")
    except asyncio.TimeoutError:
        print("监听超时")
```

### 使用事件监听

```python
async def demo_event_listener():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        
        # 启用需要的事件域
        await cdp(ws, "Page.enable", session_id=session_id)
        await cdp(ws, "Network.enable", session_id=session_id)
        await cdp(ws, "Runtime.enable", session_id=session_id)
        
        # 启动后台事件监听任务
        listener = asyncio.create_task(
            listen_events(ws, session_id, timeout=15)
        )
        
        # 导航到页面（事件会在此过程中推送）
        await cdp(ws, "Page.navigate",
                  {"url": "https://example.com"}, session_id)
        
        await listener
```

---

## 一次性 vs 持久监听

### 一次性监听：等待特定事件

```python
async def wait_for_event(ws, session_id, target_method, timeout=30):
    """等待特定 CDP 事件发生"""
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

# 使用示例
async def demo_wait_once():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        await cdp(ws, "Page.enable", session_id=session_id)
        
        # 导航并等待加载完成
        nav_task = asyncio.create_task(
            cdp(ws, "Page.navigate", {"url": "https://example.com"}, session_id)
        )
        result = await wait_for_event(ws, session_id, "Page.loadEventFired")
        if result:
            print(f"页面加载完成，时间戳: {result.get('timestamp')}")
        await nav_task
```

### 持久监听：持续处理事件流

```python
async def persistent_listener(ws, session_id, handlers, timeout=None):
    """持久监听，用 handlers 字典分发事件"""
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

# 定义事件处理函数
async def on_request(event):
    req = event.get("request", {})
    print(f"请求: {req.get('url', '')[:60]}")

async def on_response(event):
    print(f"响应: {event.get('response', {}).get('status')}")

async def on_console(event):
    print(f"控制台: {event.get('message', {}).get('text', '')}")

# 使用
async def demo_persistent():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        await cdp(ws, "Page.enable", session_id=session_id)
        await cdp(ws, "Network.enable", session_id=session_id)
        
        handlers = {
            "Network.requestWillBeSent": on_request,
            "Network.responseReceived": on_response,
        }
        
        # 启动监听器
        listener = asyncio.create_task(
            persistent_listener(ws, session_id, handlers, timeout=10)
        )
        
        await cdp(ws, "Page.navigate",
                  {"url": "https://example.com"}, session_id)
        await listener
```

---

## 常见 CDP 事件及应用

### 页面生命周期事件

启用 `Page.enable` 后可收到：

| 事件 | 触发时机 | 典型用途 |
|------|---------|---------|
| `Page.domContentEventFired` | DOM 解析完成 | 最早可操作 DOM 的时机 |
| `Page.loadEventFired` | 所有资源加载完成 | 等待页面完全就绪 |
| `Page.frameStartedLoading` | iframe 开始加载 | 跟踪子框架加载 |
| `Page.frameStoppedLoading` | iframe 加载完成 | 监控框架加载状态 |
| `Page.lifecycleEvent` | 页面生命周期阶段变化 | 精细控制加载流程 |

### 网络事件

启用 `Network.enable` 后可收到：

```python
# 实时监控所有网络请求
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

### Console 消息事件

启用 `Runtime.enable` 后可收到：

```python
async def capture_console(ws, session_id, timeout=30):
    """捕获浏览器控制台输出"""
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

### 异常事件

```python
async def capture_exceptions(ws, session_id, timeout=30):
    """捕获页面未捕获异常"""
    exceptions = []
    
    async def on_exception(event):
        desc = event.get("exceptionDetails", {}).get("text", "")
        url = event.get("exceptionDetails", {}).get("url", "")
        line = event.get("exceptionDetails", {}).get("lineNumber", 0)
        exceptions.append({"text": desc, "url": url, "line": line})
        print(f"异常: {desc} at {url}:{line}")
    
    handlers = {"Runtime.exceptionThrown": on_exception}
    
    await cdp(ws, "Runtime.enable", session_id=session_id)
    await persistent_listener(ws, session_id, handlers, timeout)
    return exceptions
```

### Target 事件

多标签页管理中非常有用：

| 事件 | 触发时机 |
|------|---------|
| `Target.targetCreated` | 新标签页/窗口打开 |
| `Target.targetDestroyed` | 标签页关闭 |
| `Target.targetInfoChanged` | 标签页信息变更 |

```python
async def monitor_targets(ws, timeout=60):
    """监控浏览器标签页变化"""
    targets = {}
    
    async def on_created(event):
        info = event.get("targetInfo", {})
        targets[info.get("targetId")] = info
        print(f"新标签页: {info.get('title', '')} ({info.get('url', '')[:50]})")
    
    async def on_destroyed(event):
        tid = event.get("targetId")
        if tid in targets:
            print(f"标签页关闭: {targets[tid].get('title', '')}")
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

## 事件过滤与节流

在高频事件场景（如网络请求、DOM 变化），可能需要过滤或节流：

```python
import time

class EventThrottle:
    """CDP 事件节流器"""
    
    def __init__(self, interval=0.5):
        self.interval = interval
        self.last_time = {}
    
    def should_process(self, event_method):
        """判断是否应该处理该事件（节流）"""
        now = time.time()
        last = self.last_time.get(event_method, 0)
        if now - last >= self.interval:
            self.last_time[event_method] = now
            return True
        return False


# URL 过滤器
class URLFilter:
    """URL 过滤器"""
    
    def __init__(self, include_patterns=None, exclude_patterns=None):
        self.include = include_patterns or []
        self.exclude = exclude_patterns or []
    
    def match(self, url):
        if self.exclude and any(p in url for p in self.exclude):
            return False
        if self.include and not any(p in url for p in self.include):
            return False
        return True


# 组合使用
async def filtered_network_monitor(ws, session_id, url_filter, throttle):
    """带过滤和节流的网络监控"""
    handlers = {}
    
    original_on_request = on_request  # 假设已定义
    
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

## 完整参考：CDP 事件管理器

```python
import asyncio
import json
import websockets
from typing import Callable, Dict, Any, Optional


class CDPEventManager:
    """CDP 事件管理器"""
    
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
        """注册事件监听器"""
        if method not in self._handlers:
            self._handlers[method] = []
        self._handlers[method].append(handler)
    
    def off(self, method: str, handler: Callable = None):
        """移除事件监听器"""
        if handler is None:
            self._handlers.pop(method, None)
        elif method in self._handlers:
            self._handlers[method] = [
                h for h in self._handlers[method] if h != handler
            ]
    
    async def _event_loop(self):
        """事件循环"""
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
                        # 通配符监听器
                        if "*" in self._handlers:
                            for handler in self._handlers["*"]:
                                await handler(method, data.get("params", {}))
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                print(f"事件循环异常: {e}")
                break
    
    async def start(self):
        """启动事件监听"""
        if self._running:
            return
        self._running = True
        self._task = asyncio.create_task(self._event_loop())
    
    async def stop(self):
        """停止事件监听"""
        self._running = False
        if self._task:
            self._task.cancel()
            self._task = None
    
    async def wait_for(self, method: str, timeout: float = 30):
        """等待特定事件（一次性）"""
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
        """启用事件域"""
        await self._cdp(f"{domain}.enable")
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await attach_to_page(ws)
    mgr = CDPEventManager(ws, session_id)
    
    # 注册事件处理器
    mgr.on("Network.requestWillBeSent", lambda e:
        print(f"请求: {e.get('request', {}).get('url', '')[:60]}"))
    
    mgr.on("Runtime.consoleAPICalled", lambda e:
        print(f"控制台: {e.get('message', {}).get('text', '')[:100]}"))
    
    # 启动监听
    await mgr.start()
    
    # 启用事件域
    await mgr.enable_domain("Network")
    await mgr.enable_domain("Runtime")
    
    # 导航并等待加载
    await mgr._cdp("Page.navigate", {"url": "https://example.com"})
    result = await mgr.wait_for("Page.loadEventFired", timeout=15)
    
    # 停止监听
    await mgr.stop()
```

---

## 常见踩坑与最佳实践

### 踩坑 1：忘记启用域

```python
# ❌ 没启用 Network，收不到事件
listener = asyncio.create_task(listen_events(ws, session_id))

# ✅ 必须先启用
await cdp(ws, "Network.enable", session_id=session_id)
await cdp(ws, "Page.enable", session_id=session_id)
```

### 踩坑 2：async for 独占 WebSocket

`async for msg in ws:` 会持续读取 WebSocket，阻塞其他操作。正确做法：

```python
# ✅ 用 asyncio.create_task 在后台运行
listener = asyncio.create_task(event_loop(ws, handlers))
await navigate(ws, session_id, url)
await listener

# ✅ 或用 wait_for 等待特定事件
result = await mgr.wait_for("Page.loadEventFired")
```

### 踩坑 3：事件可能丢失

在启用域和开始监听之间有竞态条件：

```python
# ❌ 先导航，再启用——可能错过早期事件
await navigate(ws, session_id, url)
await cdp(ws, "Network.enable", session_id=session_id)

# ✅ 先启用域，再导航
await cdp(ws, "Network.enable", session_id=session_id)
await navigate(ws, session_id, url)
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 启用域顺序 | 先 `enable`，后操作 |
| 监听方式 | UI 事件用持久监听，单次等待用 `wait_for` |
| 资源清理 | 用完 `stop()` 停止监听，避免协程泄漏 |
| 异常处理 | 事件处理器内部 try/catch，防止单事件崩溃整个监听 |
| 超时保护 | 持久监听加总超时，防无限等待 |

---

> **总结**：CDP 的事件系统是构建响应式自动化脚本的核心。通过监听网络请求、页面生命周期、控制台日志、JS 异常等事件，你可以写出比轮询式脚本更高效、更及时的自动化工具。

*上一篇回顾：CDP WebSocket 调试指南：用 Python 拦截与检查 WebSocket 帧。*

*下一篇预告：CDP 多标签页管理：用 Python 控制多个页面。*