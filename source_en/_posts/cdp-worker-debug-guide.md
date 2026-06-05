---
lang: en
title: "CDP Worker Debug Guide: Debugging Web Workers with Python"
date: "2026-06-05 19:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Web Worker
  - Service Worker
  - Browser Automation
  - Multithread Debugging
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to debugging Web Workers using Chrome DevTools Protocol (CDP). Covers automatic Worker detection, communication interception, Console log capture, JS injection, and Dedicated/Shared Worker debugging techniques.
---

> **Summary in one sentence**: CDP's Target domain autoAttach mechanism automatically discovers and connects to all Worker threads, allowing you to execute Runtime.evaluate, capture Console logs, and monitor Worker lifecycle just like you would with the main page.

---

## Table of Contents

1. [Web Worker Debugging Overview](#web-worker-debugging-overview)
2. [Auto-Attaching Worker Threads](#auto-attaching-worker-threads)
3. [Using the Worker Domain](#using-the-worker-domain)
4. [Dedicated Worker Debugging](#dedicated-worker-debugging)
5. [Shared Worker Debugging](#shared-worker-debugging)
6. [Executing JS in Worker Context](#executing-js-in-worker-context)
7. [Capturing Worker Console Logs](#capturing-worker-console-logs)
8. [Worker Lifecycle Monitoring](#worker-lifecycle-monitoring)
9. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)
10. [Complete Reference: CDP Worker Debugger Class](#complete-reference-cdp-worker-debugger-class)

---

## Web Worker Debugging Overview

| Challenge | Description |
|-----------|-------------|
| Isolated context | Workers have no DOM, requiring special debugging |
| Communication | postMessage messages are hard to track |
| Lifecycle | Workers can be created/destroyed at any time |

CDP provides two approaches: **Target.autoAttach** (recommended) automatically discovers Workers and creates independent CDP sessions; the **Worker domain** is a legacy API being phased out.

---

## Auto-Attaching Worker Threads

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
    """Enable Target.autoAttach to auto-discover Workers"""
    return await cdp(ws, "Target.setAutoAttach", {
        "autoAttach": True,
        "waitForDebuggerOnStart": False,
        "flatten": True
    })


async def monitor_worker_creation(ws, duration=30):
    """Listen for and collect Worker events"""
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
                    print(f"[Worker] Detected: {info['type']} -> {info.get('url','')}")
            
            elif method == "Target.detachedFromTarget":
                if p.get("targetId") in workers:
                    workers[p["targetId"]]["detached"] = datetime.now().isoformat()
                    print(f"[Worker] Detached: {p['targetId']}")
                    
        except asyncio.TimeoutError:
            continue
    return workers
```

---

## Using the Worker Domain

```python
async def setup_worker_domain(ws, session_id):
    """Enable debugging using the Worker domain"""
    await cdp(ws, "Worker.enable", session_id=session_id)
    await cdp(ws, "Worker.setAutoconnectToWorkers", {"value": True}, session_id=session_id)


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
            elif m == "Worker.workerTerminated" and p.get("workerId") in workers:
                workers[p["workerId"]]["terminated"] = datetime.now().isoformat()
        except asyncio.TimeoutError:
            continue
    return workers
```

---

## Dedicated Worker Debugging

```python
async def inject_and_debug_dedicated_worker(ws, session_id, worker_url):
    """Inject and debug a Dedicated Worker"""
    await setup_auto_attach(ws)
    await cdp(ws, "Page.addScriptToEvaluateOnNewDocument", {
        "source": f"""
            const w = new Worker('{worker_url}');
            w.onmessage = e => console.log('[Main] Worker says:', e.data);
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
                    print(f"[Dedicated Worker] Attached: {info.get('url','')}")
        except asyncio.TimeoutError:
            continue
    return worker_sessions
```

---

## Shared Worker Debugging

```python
async def monitor_shared_worker(ws, duration=30):
    """Monitor Shared Worker connections"""
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
                    workers[info["targetId"]] = {"session_id": d["params"]["sessionId"], "url": info.get("url")}
                    print(f"[Shared Worker] Attached: {info.get('url','')}")
        except asyncio.TimeoutError:
            continue
    return workers


async def enumerate_worker_clients(ws, worker_session_id):
    """Enumerate clients connected to the Shared Worker"""
    js = """(async ()=>{const c=await self.clients.matchAll();return c.map(x=>({id:x.id,type:x.type,url:x.url}));})()"""
    r = await cdp(ws, "Runtime.evaluate", {"expression": js, "awaitPromise": True, "returnByValue": True}, session_id=worker_session_id)
    return r.get("result",{}).get("value",[])
```

---

## Executing JS in Worker Context

```python
async def evaluate_in_worker(ws, worker_session_id, expression):
    """Evaluate JS in the Worker context"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": expression, "returnByValue": True
    }, session_id=worker_session_id)
    v = result.get("result", {})
    return v.get("value") or v.get("description")


async def inspect_worker_state(ws, worker_session_id):
    """Inspect Worker state"""
    return {
        "constructor": await evaluate_in_worker(ws, worker_session_id, "self.constructor.name"),
        "location": await evaluate_in_worker(ws, worker_session_id, "self.location.href"),
        "userAgent": await evaluate_in_worker(ws, worker_session_id, "self.navigator.userAgent"),
    }


async def send_to_worker(ws, worker_session_id, message):
    """Send a message to the Worker (simulate postMessage)"""
    js = f"self.dispatchEvent(new MessageEvent('message', {{data: {json.dumps(message)}}}));"
    return await evaluate_in_worker(ws, worker_session_id, js)


async def call_worker_function(ws, worker_session_id, func_name, *args):
    """Call a function defined in the Worker"""
    args_str = ", ".join(json.dumps(a) for a in args)
    return await evaluate_in_worker(ws, worker_session_id,
        f"(typeof {func_name}==='function')?{func_name}({args_str}):null")
```

---

## Capturing Worker Console Logs

```python
async def capture_worker_console(ws, worker_session_id, duration=30):
    """Capture Console logs from a Worker"""
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

## Worker Lifecycle Monitoring

```python
async def trace_worker_lifecycle(ws, duration=60):
    """Track complete Worker lifecycle"""
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
                    await cdp(ws, "Runtime.enable", session_id=p["sessionId"])
                    print(f"[Lifecycle] Worker attached: {info.get('url','')}")
            
            elif m == "Runtime.executionContextCreated" and wid:
                lifecycle["runtime_enabled"] = datetime.now().isoformat()
            
            elif m == "Target.detachedFromTarget" and p.get("targetId") == wid:
                lifecycle["detached"] = datetime.now().isoformat()
                break
        except asyncio.TimeoutError:
            continue
    
    if lifecycle["attached"] and lifecycle["detached"]:
        from datetime import datetime as dt
        lifespan = (dt.fromisoformat(lifecycle["detached"]) - dt.fromisoformat(lifecycle["attached"])).total_seconds()
        print(f"Worker lifespan: {lifespan:.1f}s")
    return lifecycle
```

---

## Common Pitfalls & Best Practices

- **Prioritize autoAttach**: Use Target.setAutoAttach, more stable than Worker domain
- **waitForDebuggerOnStart**: When True, Workers pause on creation; call Runtime.runIfWaitingForDebugger to resume
- **Session management**: Each Worker has its own sessionId; maintain a target_id -> session_id mapping
- **No DOM API**: Workers lack document/window; Runtime.evaluate can only use Worker-supported APIs

| Consideration | Recommendation |
|---------------|----------------|
| Prioritize autoAttach | Use Target.setAutoAttach |
| flatten=True | Always use flatten for flat sessions |
| Enable Runtime | Call Runtime.enable immediately after attach |
| Resource cleanup | Clean up sessions when Workers terminate |

---

## Complete Reference: CDP Worker Debugger Class

```python
import asyncio, json
from datetime import datetime


class CDPWorkerDebugger:
    """CDP Worker Debugger"""
    
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

**Usage Example:**

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
    print(f"Results: {d.summary()}")
```

---

> **Summary**: CDP's autoAttach mechanism provides a complete Worker debugging solution — auto-discover Workers, obtain independent CDP sessions, execute JS in Worker contexts, capture Console logs, and track lifecycle. This makes debugging Web Workers as straightforward as debugging the main page.

---

*Previous: CDP Media & WebRTC Debugging: Controlling Audio/Video with Python*

*Next up: CDP CI/CD Integration Guide: Deploying Browser Automation with Docker*