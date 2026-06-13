---
title: CDP Worker 调试指南：用 Python 调试 Web Workers
date: 2026-06-05 19:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Web Worker
  - Service Worker
  - 浏览器自动化
  - 多线程调试
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）调试 Web Workers。涵盖 Worker 自动检测、通信拦截、Console 日志捕获、JS 执行注入、以及 Dedicated/Shared Worker 调试技巧。
---

> **一句话总结**：CDP 可以通过 Target 域的 autoAttach 机制自动发现并连接到所有 Worker 线程，然后像操作主页面一样对 Worker 执行 Runtime.evaluate、捕获 Console 日志、监控 Worker 生命周期。

---

## 目录

1. [Web Worker 调试概述](#web-worker-调试概述)
2. [自动附加 Worker 线程](#自动附加-worker-线程)
3. [使用 Worker 域](#使用-worker-域)
4. [Dedicated Worker 调试](#dedicated-worker-调试)
5. [Shared Worker 调试](#shared-worker-调试)
6. [在 Worker 上下文中执行 JS](#在-worker-上下文中执行-js)
7. [捕获 Worker 的 Console 日志](#捕获-worker-的-console-日志)
8. [Worker 生命周期监控](#worker-生命周期监控)
9. [常见踩坑与最佳实践](#常见踩坑与最佳实践)
10. [完整参考：CDP Worker 调试类](#完整参考cdp-worker-调试类)

---

## Web Worker 调试概述

| 挑战 | 说明 |
|------|------|
| 独立上下文 | Worker 没有 DOM，调试需要特殊方法 |
| 通信通道 | postMessage 消息难以追踪 |
| 生命周期 | Worker 随时创建和销毁 |

CDP 提供两种调试方式：**Target.autoAttach**（推荐）自动发现 Worker 并创建独立 CDP 会话；**Worker 域**是传统 API，逐步被 autoAttach 取代。

---

## 自动附加 Worker 线程

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
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]


async def setup_auto_attach(ws):
    """启用 Target.autoAttach，自动发现 Workers"""
    return await cdp(ws, "Target.setAutoAttach", {
        "autoAttach": True,
        "waitForDebuggerOnStart": False,
        "flatten": True
    })


async def monitor_worker_creation(ws, duration=30):
    """监听并收集 Worker 事件"""
    await setup_auto_attach(ws)
    workers = {}
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method, p = data.get("method", ""), data.get("params", {})
            
            if method == "Target.attachedToTarget":
                info = p.get("targetInfo", {})
                if info.get("type") in ("worker", "shared_worker", "service_worker"):
                    workers[info["targetId"]] = {
                        "type": info["type"],
                        "url": info.get("url", ""),
                        "session_id": p.get("sessionId"),
                        "attached_at": datetime.now().isoformat()
                    }
                    print(f"[Worker] 检测到: {info['type']} -> {info.get('url','')}")
            
            elif method == "Target.detachedFromTarget":
                if p.get("targetId") in workers:
                    workers[p["targetId"]]["detached"] = datetime.now().isoformat()
                    print(f"[Worker] 分离: {p['targetId']}")
                    
        except asyncio.TimeoutError:
            continue
    return workers
```

---

## 使用 Worker 域

```python
async def setup_worker_domain(ws, session_id):
    """使用 Worker 域启用调试"""
    await cdp(ws, "Worker.enable", session_id=session_id)
    await cdp(ws, "Worker.setAutoconnectToWorkers", {"value": True}, session_id=session_id)
    print("[Worker] Worker 域已启用")


async def worker_domain_monitor(ws, session_id, duration=30):
    await setup_worker_domain(ws, session_id)
    workers = {}
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            d = json.loads(msg); m, p = d.get("method",""), d.get("params",{})
            if m == "Worker.workerCreated":
                workers[p["workerId"]] = {"url": p.get("url"), "created": datetime.now().isoformat()}
                print(f"[Worker] 创建: {p.get('url', '')}")
            elif m == "Worker.workerTerminated":
                if p.get("workerId") in workers:
                    workers[p["workerId"]]["terminated"] = datetime.now().isoformat()
        except asyncio.TimeoutError:
            continue
    return workers
```

---

## Dedicated Worker 调试

```python
async def inject_and_debug_dedicated_worker(ws, session_id, worker_url):
    """注入并调试 Dedicated Worker"""
    await setup_auto_attach(ws)
    await cdp(ws, "Page.addScriptToEvaluateOnNewDocument", {
        "source": f"""
            const w = new Worker('{worker_url}');
            w.onmessage = e => console.log('[Main] Worker说:', e.data);
            w.postMessage({{cmd:'start'}});
        """
    }, session_id=session_id)
    
    worker_sessions = {}
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < 10:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            d = json.loads(msg)
            if d.get("method") == "Target.attachedToTarget":
                info = d["params"]["targetInfo"]
                if info["type"] == "worker":
                    wid = info["targetId"]
                    worker_sessions[wid] = {"session_id": d["params"]["sessionId"], "url": info.get("url","")}
                    print(f"[Dedicated Worker] 已附加: {info.get('url','')}")
        except asyncio.TimeoutError:
            continue
    return worker_sessions
```

---

## Shared Worker 调试

```python
async def monitor_shared_worker(ws, duration=30):
    """监控 Shared Worker 连接"""
    await setup_auto_attach(ws)
    workers = {}
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            d = json.loads(msg)
            if d.get("method") == "Target.attachedToTarget":
                info = d["params"]["targetInfo"]
                if info["type"] == "shared_worker":
                    workers[info["targetId"]] = {
                        "session_id": d["params"]["sessionId"],
                        "url": info.get("url"), "attached": datetime.now().isoformat()
                    }
                    print(f"[Shared Worker] 已附加: {info.get('url','')}")
        except asyncio.TimeoutError:
            continue
    return workers


async def enumerate_worker_clients(ws, worker_session_id):
    """枚举连接到 Shared Worker 的页面"""
    js = """(async ()=>{const c=await self.clients.matchAll();return c.map(x=>({id:x.id,type:x.type,url:x.url}));})()"""
    r = await cdp(ws, "Runtime.evaluate", {"expression": js, "awaitPromise": True, "returnByValue": True}, session_id=worker_session_id)
    return r.get("result",{}).get("value",[])
```

---

## 在 Worker 上下文中执行 JS

```python
async def evaluate_in_worker(ws, worker_session_id, expression):
    """在 Worker 中执行 JS 并返回值"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": expression, "returnByValue": True
    }, session_id=worker_session_id)
    v = result.get("result", {})
    return v.get("value") or v.get("description")


async def inspect_worker_state(ws, worker_session_id):
    """检查 Worker 状态"""
    return {
        "constructor": await evaluate_in_worker(ws, worker_session_id, "self.constructor.name"),
        "location": await evaluate_in_worker(ws, worker_session_id, "self.location.href"),
        "userAgent": await evaluate_in_worker(ws, worker_session_id, "self.navigator.userAgent"),
    }


async def send_to_worker(ws, worker_session_id, message):
    """向 Worker 发送消息（模拟 postMessage）"""
    js = f"self.dispatchEvent(new MessageEvent('message', {{data: {json.dumps(message)}}}));"
    return await evaluate_in_worker(ws, worker_session_id, js)


async def call_worker_function(ws, worker_session_id, func_name, *args):
    """调用 Worker 中定义的函数"""
    args_str = ", ".join(json.dumps(a) for a in args)
    return await evaluate_in_worker(ws, worker_session_id,
        f"(typeof {func_name}==='function')?{func_name}({args_str}):null")
```

---

## 捕获 Worker 的 Console 日志

```python
async def capture_worker_console(ws, worker_session_id, duration=30):
    """捕获 Worker 中的 Console 日志"""
    await cdp(ws, "Console.enable", session_id=worker_session_id)
    logs = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            d = json.loads(msg)
            if d.get("sessionId") != worker_session_id:
                continue
            if d.get("method") == "Console.messageAdded":
                m = d["params"]["message"]
                logs.append({"level": m.get("level"), "text": m.get("text")})
                print(f"[Worker Console] [{m.get('level')}] {m.get('text')}")
        except asyncio.TimeoutError:
            continue
    return logs
```

---

## Worker 生命周期监控

```python
async def trace_worker_lifecycle(ws, duration=60):
    """追踪 Worker 完整生命周期"""
    await setup_auto_attach(ws)
    lifecycle = {"attached": None, "runtime_enabled": None, "detached": None}
    wid = None
    
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            d, m, p = json.loads(msg), d.get("method",""), d.get("params",{})
            
            if m == "Target.attachedToTarget":
                info = p.get("targetInfo", {})
                if info["type"] == "worker":
                    wid = info["targetId"]
                    lifecycle["attached"] = datetime.now().isoformat()
                    # 自动启用 Runtime
                    await cdp(ws, "Runtime.enable", session_id=p["sessionId"])
                    print(f"[生命周期] Worker 已附加: {info.get('url','')}")
            
            elif m == "Runtime.executionContextCreated" and wid:
                lifecycle["runtime_enabled"] = datetime.now().isoformat()
                print("[生命周期] 执行上下文已创建")
            
            elif m == "Target.detachedFromTarget" and p.get("targetId") == wid:
                lifecycle["detached"] = datetime.now().isoformat()
                print("[生命周期] Worker 已分离")
                break
        except asyncio.TimeoutError:
            continue
    
    if lifecycle["attached"] and lifecycle["detached"]:
        from datetime import datetime as dt
        lifespan = (dt.fromisoformat(lifecycle["detached"]) - dt.fromisoformat(lifecycle["attached"])).total_seconds()
        print(f"Worker 存活: {lifespan:.1f}s")
    return lifecycle
```

---

## 常见踩坑与最佳实践

- **autoAttach 优先**：使用 Target.setAutoAttach，比 Worker 域更稳定
- **waitForDebuggerOnStart**：设为 True 时 Worker 启动后会暂停，需额外调用 Runtime.runIfWaitingForDebugger 恢复
- **Session 管理**：每个 Worker 有独立 sessionId，需维护 target_id -> session_id 映射
- **无 DOM API**：Worker 中没有 document/window，Runtime.evaluate 只能使用 Worker 支持的 API

| 注意点 | 建议 |
|--------|------|
| autoAttach 优先 | 使用 Target.setAutoAttach |
| flatten=True | 始终使用 flatten 保持会话扁平化 |
| 启用 Runtime | 附加 Worker 后立即调用 Runtime.enable |
| 资源清理 | Worker 终止后清理对应 session |

---

## 完整参考：CDP Worker 调试类

```python
import asyncio, json
from datetime import datetime


class CDPWorkerDebugger:
    """CDP Worker 调试器"""
    
    def __init__(self, ws, session_id):
        self.ws, self._psid = ws, session_id
        self._cid = 0
        self.workers = {}
    
    async def _cmd(self, method, params=None, sid=None):
        self._cid += 1
        msg = {"id": self._cid, "method": method, "params": params or {}}
        if sid or self._psid:
            msg["sessionId"] = sid or self._psid
        await self.ws.send(json.dumps(msg))
        async for r in self.ws:
            d = json.loads(r)
            if d.get("id") == self._cid:
                return d.get("result", {})
    
    async def start(self):
        await self._cmd("Target.setAutoAttach", {"autoAttach": True, "waitForDebuggerOnStart": False, "flatten": True})
    
    async def listen(self, duration=30):
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                d, m, p = json.loads(msg), d.get("method",""), d.get("params",{})
                if m == "Target.attachedToTarget":
                    info = p["targetInfo"]
                    if info["type"] in ("worker", "shared_worker", "service_worker"):
                        self.workers[info["targetId"]] = {
                            "sid": p["sessionId"], "url": info.get("url",""),
                            "type": info["type"], "attached": datetime.now().isoformat()
                        }
                        await self._cmd("Runtime.enable", sid=p["sessionId"])
                elif m == "Target.detachedFromTarget":
                    if p.get("targetId") in self.workers:
                        self.workers[p["targetId"]]["detached"] = datetime.now().isoformat()
            except asyncio.TimeoutError:
                continue
    
    async def evaluate(self, worker_id, expr):
        if worker_id not in self.workers: raise ValueError(f"Worker {worker_id} not found")
        r = await self._cmd("Runtime.evaluate", {"expression": expr, "returnByValue": True}, sid=self.workers[worker_id]["sid"])
        return r.get("result",{}).get("value")
    
    async def send_message(self, worker_id, msg):
        return await self.evaluate(worker_id, f"self.dispatchEvent(new MessageEvent('message', {{data: {json.dumps(msg)}}}));")
    
    def summary(self):
        return {"total": len(self.workers), "active": sum(1 for w in self.workers.values() if "detached" not in w)}
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    psid = await connect_page(ws)
    d = CDPWorkerDebugger(ws, psid)
    await d.start()
    await cdp(ws, "Page.navigate", {"url": "https://example.com/worker-demo"}, session_id=psid)
    await d.listen(duration=15)
    if d.workers:
        wid = next(iter(d.workers))
        url = await d.evaluate(wid, "self.location.href")
        print(f"Worker URL: {url}")
    print(f"结果: {d.summary()}")
```

---

> **总结**：CDP 的 autoAttach 机制提供了 Worker 调试的完整解决方案——自动发现 Worker、获取独立 CDP 会话、在 Worker 上下文中执行 JS、捕获 Console 日志、追踪完整生命周期。这让 Web Workers 的调试变得像调试主页面一样简单。

---

*上一篇回顾：CDP 媒体与 WebRTC 调试：用 Python 控制音视频。*

*下一篇预告：CDP CI/CD 集成指南：用 Docker 部署浏览器自动化。*