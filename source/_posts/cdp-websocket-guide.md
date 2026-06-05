---
title: CDP WebSocket 调试指南：用 Python 拦截与检查 WebSocket 帧
date: 2026-06-05 23:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - WebSocket
  - 网络调试
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）调试 WebSocket 连接。涵盖监听 WebSocket 帧、拦截和修改帧内容、分析 WebSocket 流量、以及自动化 WebSocket 协议测试。
---

> **一句话总结**：CDP 的 Network 域提供了完整的 WebSocket 调试能力——你可以捕获每个 WebSocket 帧的内容、检查帧的方向（发送/接收），甚至拦截和修改帧数据。

---

## 目录

1. [为什么用 CDP 调试 WebSocket](#为什么用-cdp-调试-websocket)
2. [监听 WebSocket 帧](#监听-websocket-帧)
3. [分析 WebSocket 流量](#分析-websocket-流量)
4. [拦截与修改 WebSocket 帧](#拦截与修改-websocket-帧)
5. [实战：WebSocket 协议测试](#实战websocket-协议测试)
6. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 调试 WebSocket

WebSocket 调试比普通 HTTP 更困难——它是全双工的、持续连接的。CDP 提供了对 WebSocket 帧的完整可见性：

| 功能 | 浏览器 DevTools | CDP WebSocket API |
|------|----------------|-------------------|
| 查看 WebSocket 帧 | ✅ Network 面板 | ✅ 事件捕获 |
| 区分发送/接收 | ✅ 显示方向 | ✅ `type` 字段区分 |
| 帧内容分析 | ✅ 手动查看 | ✅ 编程分析 |
| 拦截并修改帧 | ❌ 只读 | ✅ 可修改 |
| 自动化测试 | ❌ 手动 | ✅ 完全可编程 |
| 历史流量导出 | ✅ 可保存 | ✅ JSON 格式导出 |

---

## 监听 WebSocket 帧

### 启用 Network 域并监听帧事件

```python
import asyncio
import websockets
import json
from datetime import datetime

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."
CMD_ID = [0]

async def cdp(ws, session_id, method, params=None):
    CMD_ID[0] += 1; cmd_id = CMD_ID[0]
    await ws.send(json.dumps({"sessionId": session_id, "id": cmd_id,
                               "method": method, "params": params or {}}))
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


async def enable_websocket_monitoring(ws, session_id):
    """启用 WebSocket 监控"""
    return await cdp(ws, session_id, "Network.enable")


async def capture_websocket_frames(ws, session_id, duration=30):
    """捕获 WebSocket 帧"""
    await enable_websocket_monitoring(ws, session_id)
    
    frames = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            
            if method == "Network.webSocketCreated":
                p = data["params"]
                print(f"[WS 创建] {p.get('url', '')}")
                frames.append({
                    "event": "created",
                    "url": p.get("url"),
                    "ws_id": p.get("requestId"),
                    "time": datetime.now().isoformat()
                })
            
            elif method == "Network.webSocketFrameSent":
                p = data["params"]
                response = p.get("response", {})
                frames.append({
                    "event": "sent",
                    "ws_id": p.get("requestId"),
                    "payload": response.get("payloadData", ""),
                    "opcode": response.get("opcode", 1),
                    "mask": response.get("mask", False),
                    "time": datetime.now().isoformat()
                })
            
            elif method == "Network.webSocketFrameReceived":
                p = data["params"]
                response = p.get("response", {})
                frames.append({
                    "event": "received",
                    "ws_id": p.get("requestId"),
                    "payload": response.get("payloadData", ""),
                    "opcode": response.get("opcode", 1),
                    "mask": response.get("mask", False),
                    "time": datetime.now().isoformat()
                })
            
            elif method == "Network.webSocketClosed":
                p = data["params"]
                print(f"[WS 关闭] 代码: {p.get('code')}, 原因: {p.get('reason', '')}")
                frames.append({
                    "event": "closed",
                    "ws_id": p.get("requestId"),
                    "code": p.get("code"),
                    "reason": p.get("reason"),
                    "time": datetime.now().isoformat()
                })
                    
        except asyncio.TimeoutError:
            continue
    
    return frames
```

### 实时输出 WebSocket 流量

```python
async def live_websocket_monitor(ws, session_id, duration=30):
    """实时监控 WebSocket 流量"""
    await enable_websocket_monitoring(ws, session_id)
    
    sent_count = 0
    received_count = 0
    start = asyncio.get_event_loop().time()
    
    print("WebSocket 实时监控启动...")
    print("-" * 60)
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            p = data.get("params", {})
            
            if method == "Network.webSocketCreated":
                print(f"🟢 新建 WS: {p.get('url')}")
            
            elif method == "Network.webSocketFrameSent":
                sent_count += 1
                payload = p.get("response", {}).get("payloadData", "")
                print(f"⬆ 发送 [{sent_count}]: {payload[:100]}")
            
            elif method == "Network.webSocketFrameReceived":
                received_count += 1
                payload = p.get("response", {}).get("payloadData", "")
                print(f"⬇ 接收 [{received_count}]: {payload[:100]}")
            
            elif method == "Network.webSocketClosed":
                print(f"🔴 WS 关闭 (代码={p.get('code')})")
                    
        except asyncio.TimeoutError:
            continue
    
    print("-" * 60)
    print(f"统计: 发送 {sent_count} 帧, 接收 {received_count} 帧")
    return {"sent": sent_count, "received": received_count}
```

---

## 分析 WebSocket 流量

### 帧格式分析

```python
def analyze_websocket_frames(frames):
    """分析 WebSocket 帧数据"""
    analysis = {
        "total_frames": len(frames),
        "sent": 0,
        "received": 0,
        "by_opcode": {},
        "payload_sizes": [],
        "connections": set()
    }
    
    for frame in frames:
        if frame["event"] == "sent":
            analysis["sent"] += 1
        elif frame["event"] == "received":
            analysis["received"] += 1
        
        if "ws_id" in frame:
            analysis["connections"].add(frame["ws_id"])
        
        opcode = frame.get("opcode", 1)
        opcode_name = {
            1: "text",
            2: "binary",
            8: "close",
            9: "ping",
            10: "pong"
        }.get(opcode, f"unknown({opcode})")
        
        analysis["by_opcode"][opcode_name] = \
            analysis["by_opcode"].get(opcode_name, 0) + 1
        
        if "payload" in frame:
            analysis["payload_sizes"].append(len(frame["payload"]))
    
    if analysis["payload_sizes"]:
        analysis["avg_payload_size"] = sum(analysis["payload_sizes"]) / len(analysis["payload_sizes"])
        analysis["max_payload_size"] = max(analysis["payload_sizes"])
        analysis["min_payload_size"] = min(analysis["payload_sizes"])
    
    analysis["connection_count"] = len(analysis["connections"])
    
    return analysis


def print_ws_analysis(analysis):
    """打印 WebSocket 分析结果"""
    print("=" * 50)
    print("WebSocket 流量分析")
    print("=" * 50)
    print(f"总帧数: {analysis['total_frames']}")
    print(f"发送: {analysis['sent']}")
    print(f"接收: {analysis['received']}")
    print(f"连接数: {analysis['connection_count']}")
    print(f"按操作码分布:")
    for opcode, count in analysis.get("by_opcode", {}).items():
        print(f"  {opcode}: {count}")
    if "avg_payload_size" in analysis:
        print(f"平均载荷: {analysis['avg_payload_size']:.0f} 字节")
        print(f"最大载荷: {analysis['max_payload_size']} 字节")
```

### JSON 消息解析

许多 WebSocket 传输 JSON 格式的消息。可以自动解析：

```python
async def capture_json_websocket_messages(ws, session_id, duration=30):
    """捕获并解析 JSON 格式的 WebSocket 消息"""
    frames = await capture_websocket_frames(ws, session_id, duration)
    
    json_messages = {"sent": [], "received": []}
    raw_messages = {"sent": [], "received": []}
    
    for frame in frames:
        payload = frame.get("payload", "")
        target = "sent" if frame["event"] == "sent" else "received"
        
        # 尝试解析 JSON
        try:
            parsed = json.loads(payload)
            json_messages[target].append(parsed)
        except (json.JSONDecodeError, TypeError):
            raw_messages[target].append(payload)
    
    print(f"JSON 消息: 发送 {len(json_messages['sent'])} 条, "
          f"接收 {len(json_messages['received'])} 条")
    print(f"原始消息: 发送 {len(raw_messages['sent'])} 条, "
          f"接收 {len(raw_messages['received'])} 条")
    
    return {
        "json": json_messages,
        "raw": raw_messages,
        "all": frames
    }
```

---

## 拦截与修改 WebSocket 帧

CDP 本身没有直接拦截 WebSocket 帧的 API，但可以通过 Fetch 域拦截 WebSocket **连接建立**，或通过 `Page.addScriptToEvaluateOnNewDocument` 注入代码来修改帧：

### 注入 WebSocket 拦截器

```python
async def inject_websocket_interceptor(ws, session_id):
    """
    注入 WebSocket 拦截脚本
    在页面中 Hook 原生 WebSocket，实现帧的读取和修改
    """
    script = """
    (function() {
        const OriginalWebSocket = window.WebSocket;
        
        window.WebSocket = function(url, protocols) {
            const ws = new OriginalWebSocket(url, protocols);
            
            // 记录连接信息
            console.log('[CDP WS] 连接:', url);
            
            // 拦截发送
            const originalSend = ws.send;
            ws.send = function(data) {
                console.log('[CDP WS] 发送:', data);
                // 可以在这里修改 data
                return originalSend.call(this, data);
            };
            
            // 拦截接收
            ws.addEventListener('message', function(event) {
                console.log('[CDP WS] 接收:', event.data);
                // 可以在这里修改 event.data
            });
            
            return ws;
        };
        
        // 复制静态属性
        window.WebSocket.CONNECTING = 0;
        window.WebSocket.OPEN = 1;
        window.WebSocket.CLOSING = 2;
        window.WebSocket.CLOSED = 3;
    })();
    """
    
    return await cdp(ws, session_id, "Page.addScriptToEvaluateOnNewDocument", {
        "source": script
    })
```

### 记录 WebSocket 流量到文件

```python
async def record_websocket_traffic(ws, session_id, output_file, duration=30):
    """记录 WebSocket 流量到 JSON 文件"""
    frames = await capture_websocket_frames(ws, session_id, duration)
    
    # 提取摘要信息
    summary = []
    for frame in frames:
        summary.append({
            "time": frame.get("time"),
            "event": frame.get("event"),
            "payload": frame.get("payload", "")[:200],  # 截断长消息
            "size": len(frame.get("payload", "")),
        })
    
    output = {
        "recorded_at": datetime.now().isoformat(),
        "total_frames": len(frames),
        "frames": summary
    }
    
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"已记录 {len(frames)} 帧到 {output_file}")
    return output
```

---

## 实战：WebSocket 协议测试

### 自动化 WebSocket 通信测试

```python
async def test_websocket_communication(ws, session_id, url):
    """
    测试页面的 WebSocket 通信是否正常
    验证连接建立、消息收发、连接关闭
    """
    await enable_websocket_monitoring(ws, session_id)
    
    test_results = {
        "connection_established": False,
        "messages_sent": 0,
        "messages_received": 0,
        "connection_closed": False,
        "close_code": None,
        "errors": []
    }
    
    # 导航到页面
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    
    # 监控 15 秒
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < 15:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            p = data.get("params", {})
            
            if method == "Network.webSocketCreated":
                test_results["connection_established"] = True
                test_results["ws_url"] = p.get("url")
            
            elif method == "Network.webSocketFrameSent":
                test_results["messages_sent"] += 1
            
            elif method == "Network.webSocketFrameReceived":
                test_results["messages_received"] += 1
            
            elif method == "Network.webSocketClosed":
                test_results["connection_closed"] = True
                test_results["close_code"] = p.get("code")
            
            elif method == "Network.webSocketFrameError":
                test_results["errors"].append(p.get("errorMessage"))
                    
        except asyncio.TimeoutError:
            continue
    
    # 评估结果
    test_results["passed"] = (
        test_results["connection_established"] and
        test_results["messages_received"] > 0
    )
    
    print(f"\n=== WebSocket 通信测试 ===")
    print(f"连接建立: {'✅' if test_results['connection_established'] else '❌'}")
    print(f"消息发送: {test_results['messages_sent']} 条")
    print(f"消息接收: {test_results['messages_received']} 条")
    print(f"连接关闭: {'✅' if test_results['connection_closed'] else '❌'}")
    print(f"测试结果: {'✅ 通过' if test_results['passed'] else '❌ 失败'}")
    
    return test_results
```

### 多页面 WebSocket 连接监控

```python
async def monitor_all_websockets(ws, session_id, duration=30):
    """监控所有 WebSocket 连接"""
    await enable_websocket_monitoring(ws, session_id)
    
    connections = {}  # ws_id -> info
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            p = data.get("params", {})
            
            ws_id = p.get("requestId")
            if not ws_id:
                continue
            
            if method == "Network.webSocketCreated":
                connections[ws_id] = {
                    "url": p.get("url"),
                    "sent": 0,
                    "received": 0,
                    "created": datetime.now().isoformat()
                }
                print(f"[WS] 新建: {p.get('url')}")
            
            elif method == "Network.webSocketFrameSent":
                if ws_id in connections:
                    connections[ws_id]["sent"] += 1
            
            elif method == "Network.webSocketFrameReceived":
                if ws_id in connections:
                    connections[ws_id]["received"] += 1
            
            elif method == "Network.webSocketClosed":
                if ws_id in connections:
                    connections[ws_id]["closed"] = datetime.now().isoformat()
                    connections[ws_id]["code"] = p.get("code")
                    
        except asyncio.TimeoutError:
            continue
    
    print(f"\nWS 连接汇总 ({len(connections)} 个):")
    for wid, info in connections.items():
        print(f"  {info.get('url', '')[:50]}: "
              f"↑{info.get('sent', 0)} ↓{info.get('received', 0)}")
    
    return connections
```

---

## 常见踩坑与最佳实践

### 踩坑 1：WebSocket 帧内容是 Base64 编码的吗？

```python
# Network.webSocketFrameSent / Received 中的 payloadData
# 文本帧（opcode=1）：直接是 UTF-8 字符串
# 二进制帧（opcode=2）：Base64 编码

# 解码二进制帧
import base64
payload = frame.get("payload", "")
if frame.get("opcode") == 2:  # 二进制
    binary_data = base64.b64decode(payload)
```

### 踩坑 2：WebSocket 帧事件只在 Network.enable 后触发

```python
# ❌ 没启用 Network
# 收不到任何 WebSocket 事件

# ✅ 先启用
await cdp(ws, session_id, "Network.enable")
# 然后才能收到 webSocketCreated, webSocketFrameSent 等
```

### 踩坑 3：Inject 脚本在现有 WebSocket 连接上无效

```python
# Page.addScriptToEvaluateOnNewDocument 只对新创建的页面生效
# 对于已经建立 WebSocket 连接的页面，注入脚本不会 Hook 已有连接

# ✅ 在导航前注入
await inject_websocket_interceptor(ws, session_id)
await cdp(ws, session_id, "Page.navigate", {"url": url})

# ❌ 导航后注入对已有 WS 连接无效
await cdp(ws, session_id, "Page.navigate", {"url": url})
await inject_websocket_interceptor(ws, session_id)  # 现有 WS 不会被 Hook
```

### 踩坑 4：不同 frame 的 WebSocket 分开处理

```python
# 每个 frame 中的 WebSocket 是独立的
# webSocketCreated 事件包含 frameId
# 可以通过 frameId 区分不同 iframe 中的 WS 连接
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 启用 Network | 必须在监听前调用 Network.enable |
| 注入时机 | 拦截脚本需在导航前注入 |
| 帧编码 | 文本帧 UTF-8，二进制帧 Base64 |
| JSON 解析 | WebSocket 常用 JSON，尝试解析 payload |
| 多连接 | 通过 requestId 区分不同 WS 连接 |
| 流量导出 | 定期导出到文件避免内存溢出 |

---

## 完整参考：CDP WebSocket 调试类

```python
import asyncio
import json
from datetime import datetime


class CDPWebSocketDebugger:
    """CDP WebSocket 调试器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws; self.session_id = session_id
        self._cmd_id = 0; self.frames = []; self.connections = {}
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        await self.ws.send(json.dumps({
            "sessionId": self.session_id, "id": self._cmd_id,
            "method": method, "params": params or {}
        }))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def start(self):
        await self._cmd("Network.enable")
    
    async def capture(self, duration=30):
        self.frames = []
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
                data = json.loads(msg)
                m, p = data.get("method", ""), data.get("params", {})
                
                if m == "Network.webSocketCreated":
                    self.connections[p["requestId"]] = {"url": p["url"]}
                elif m in ("Network.webSocketFrameSent", "Network.webSocketFrameReceived"):
                    self.frames.append({
                        "direction": "sent" if m == "Network.webSocketFrameSent" else "received",
                        "payload": p["response"]["payloadData"],
                        "opcode": p["response"]["opcode"],
                        "time": datetime.now().isoformat()
                    })
            except asyncio.TimeoutError:
                continue
        return self.frames
    
    def summary(self):
        sent = sum(1 for f in self.frames if f["direction"] == "sent")
        recv = sum(1 for f in self.frames if f["direction"] == "received")
        return {"total": len(self.frames), "sent": sent, "received": recv, "connections": len(self.connections)}
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    ws_debug = CDPWebSocketDebugger(ws, session_id)
    await ws_debug.start()
    
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    frames = await ws_debug.capture(duration=15)
    print(f"捕获 {ws_debug.summary()['total']} 帧")
```

---

> **总结**：CDP 的 Network 域提供了完整的 WebSocket 帧可见性——捕获每个帧的内容和方向、分析流量模式、注入拦截脚本。这让 WebSocket 协议的自动化测试和调试变得简单可靠。

---

*上一篇回顾：CDP 安全与证书处理指南——用 Python 管理浏览器安全策略。*

*这是 CDP 系列教程的最后一篇。十篇文章覆盖了从基础自动化到高级调试的完整技术栈。Happy coding! 🚀*
