---
lang: en
title: "CDP WebSocket Debugging Guide: Intercept and Inspect WebSocket Frames with Python"
date: "2026-06-05 23:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - WebSocket
  - Network Debugging
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to debugging WebSocket connections using Chrome DevTools Protocol (CDP). Learn to capture WebSocket frames, intercept and modify frame content, analyze WebSocket traffic, and automate WebSocket protocol testing.
---

> **Summary in one sentence**: CDP's Network domain provides complete WebSocket debugging capabilities — you can capture every WebSocket frame's content, inspect frame direction (sent/received), and even intercept and modify frame data.

---

## Table of Contents

1. [Why Use CDP for WebSocket Debugging](#why-use-cdp-for-websocket-debugging)
2. [Listening to WebSocket Frames](#listening-to-websocket-frames)
3. [Analyzing WebSocket Traffic](#analyzing-websocket-traffic)
4. [Intercepting and Modifying WebSocket Frames](#intercepting-and-modifying-websocket-frames)
5. [Practical: WebSocket Protocol Testing](#practical-websocket-protocol-testing)
6. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for WebSocket Debugging

WebSocket debugging is more difficult than regular HTTP — it's full-duplex and persistent. CDP provides complete visibility into WebSocket frames:

| Feature | Browser DevTools | CDP WebSocket API |
|---------|-----------------|-------------------|
| View WebSocket frames | ✅ Network panel | ✅ Event capture |
| Distinguish sent/received | ✅ Shows direction | ✅ `type` field distinguishes |
| Frame content analysis | ✅ Manual viewing | ✅ Programmatic analysis |
| Intercept and modify frames | ❌ Read-only | ✅ Modifiable |
| Automated testing | ❌ Manual | ✅ Fully programmable |
| Historical traffic export | ✅ Can save | ✅ JSON format export |

---

## Listening to WebSocket Frames

### Enable Network Domain and Listen for Frame Events

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
    """Enable WebSocket monitoring"""
    return await cdp(ws, session_id, "Network.enable")


async def capture_websocket_frames(ws, session_id, duration=30):
    """Capture WebSocket frames"""
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
                print(f"[WS Created] {p.get('url', '')}")
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
                print(f"[WS Closed] Code: {p.get('code')}, Reason: {p.get('reason', '')}")
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

### Live WebSocket Traffic Monitor

```python
async def live_websocket_monitor(ws, session_id, duration=30):
    """Live WebSocket traffic monitoring"""
    await enable_websocket_monitoring(ws, session_id)

    sent_count = 0
    received_count = 0
    start = asyncio.get_event_loop().time()

    print("WebSocket Live Monitor Started...")
    print("-" * 60)

    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            p = data.get("params", {})

            if method == "Network.webSocketCreated":
                print(f"🟢 New WS: {p.get('url')}")

            elif method == "Network.webSocketFrameSent":
                sent_count += 1
                payload = p.get("response", {}).get("payloadData", "")
                print(f"⬆ Sent [{sent_count}]: {payload[:100]}")

            elif method == "Network.webSocketFrameReceived":
                received_count += 1
                payload = p.get("response", {}).get("payloadData", "")
                print(f"⬇ Received [{received_count}]: {payload[:100]}")

            elif method == "Network.webSocketClosed":
                print(f"🔴 WS Closed (code={p.get('code')})")

        except asyncio.TimeoutError:
            continue

    print("-" * 60)
    print(f"Summary: {sent_count} frames sent, {received_count} frames received")
    return {"sent": sent_count, "received": received_count}
```

---

## Analyzing WebSocket Traffic

### Frame Format Analysis

```python
def analyze_websocket_frames(frames):
    """Analyze WebSocket frame data"""
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
    """Print WebSocket analysis results"""
    print("=" * 50)
    print("WebSocket Traffic Analysis")
    print("=" * 50)
    print(f"Total frames: {analysis['total_frames']}")
    print(f"Sent: {analysis['sent']}")
    print(f"Received: {analysis['received']}")
    print(f"Connections: {analysis['connection_count']}")
    print(f"By opcode:")
    for opcode, count in analysis.get("by_opcode", {}).items():
        print(f"  {opcode}: {count}")
    if "avg_payload_size" in analysis:
        print(f"Average payload: {analysis['avg_payload_size']:.0f} bytes")
        print(f"Max payload: {analysis['max_payload_size']} bytes")
```

### JSON Message Parsing

Many WebSocket connections transmit JSON-formatted messages. You can automatically parse them:

```python
async def capture_json_websocket_messages(ws, session_id, duration=30):
    """Capture and parse JSON WebSocket messages"""
    frames = await capture_websocket_frames(ws, session_id, duration)

    json_messages = {"sent": [], "received": []}
    raw_messages = {"sent": [], "received": []}

    for frame in frames:
        payload = frame.get("payload", "")
        target = "sent" if frame["event"] == "sent" else "received"

        # Try to parse as JSON
        try:
            parsed = json.loads(payload)
            json_messages[target].append(parsed)
        except (json.JSONDecodeError, TypeError):
            raw_messages[target].append(payload)

    print(f"JSON messages: {len(json_messages['sent'])} sent, "
          f"{len(json_messages['received'])} received")
    print(f"Raw messages: {len(raw_messages['sent'])} sent, "
          f"{len(raw_messages['received'])} received")

    return {
        "json": json_messages,
        "raw": raw_messages,
        "all": frames
    }
```

---

## Intercepting and Modifying WebSocket Frames

CDP itself doesn't have a direct WebSocket frame interception API, but you can intercept WebSocket **connection establishment** via the Fetch domain, or inject code via `Page.addScriptToEvaluateOnNewDocument` to modify frames:

### Inject WebSocket Interceptor

```python
async def inject_websocket_interceptor(ws, session_id):
    """
    Inject WebSocket interceptor script
    Hooks the native WebSocket in the page to read and modify frames
    """
    script = """
    (function() {
        const OriginalWebSocket = window.WebSocket;

        window.WebSocket = function(url, protocols) {
            const ws = new OriginalWebSocket(url, protocols);

            // Log connection info
            console.log('[CDP WS] Connection:', url);

            // Intercept send
            const originalSend = ws.send;
            ws.send = function(data) {
                console.log('[CDP WS] Sending:', data);
                // Modify data here if needed
                return originalSend.call(this, data);
            };

            // Intercept receive
            ws.addEventListener('message', function(event) {
                console.log('[CDP WS] Received:', event.data);
                // Modify event.data here if needed
            });

            return ws;
        };

        // Copy static properties
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

### Record WebSocket Traffic to File

```python
async def record_websocket_traffic(ws, session_id, output_file, duration=30):
    """Record WebSocket traffic to a JSON file"""
    frames = await capture_websocket_frames(ws, session_id, duration)

    # Extract summary info
    summary = []
    for frame in frames:
        summary.append({
            "time": frame.get("time"),
            "event": frame.get("event"),
            "payload": frame.get("payload", "")[:200],  # Truncate long messages
            "size": len(frame.get("payload", "")),
        })

    output = {
        "recorded_at": datetime.now().isoformat(),
        "total_frames": len(frames),
        "frames": summary
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"Recorded {len(frames)} frames to {output_file}")
    return output
```

---

## Practical: WebSocket Protocol Testing

### Automated WebSocket Communication Test

```python
async def test_websocket_communication(ws, session_id, url):
    """
    Test if a page's WebSocket communication works properly
    Verifies connection establishment, message sending/receiving, and connection closure
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

    # Navigate to page
    await cdp(ws, session_id, "Page.navigate", {"url": url})

    # Monitor for 15 seconds
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

    # Evaluate results
    test_results["passed"] = (
        test_results["connection_established"] and
        test_results["messages_received"] > 0
    )

    print(f"\n=== WebSocket Communication Test ===")
    print(f"Connection established: {'✅' if test_results['connection_established'] else '❌'}")
    print(f"Messages sent: {test_results['messages_sent']}")
    print(f"Messages received: {test_results['messages_received']}")
    print(f"Connection closed: {'✅' if test_results['connection_closed'] else '❌'}")
    print(f"Test result: {'✅ PASSED' if test_results['passed'] else '❌ FAILED'}")

    return test_results
```

### Multi-Page WebSocket Connection Monitoring

```python
async def monitor_all_websockets(ws, session_id, duration=30):
    """Monitor all WebSocket connections"""
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
                print(f"[WS] Created: {p.get('url')}")

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

    print(f"\nWS Connection Summary ({len(connections)} connections):")
    for wid, info in connections.items():
        print(f"  {info.get('url', '')[:50]}: "
              f"↑{info.get('sent', 0)} ↓{info.get('received', 0)}")

    return connections
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Are WebSocket Frame Contents Base64 Encoded?

```python
# payloadData in Network.webSocketFrameSent / Received:
# Text frames (opcode=1): direct UTF-8 string
# Binary frames (opcode=2): Base64 encoded

# Decode binary frames
import base64
payload = frame.get("payload", "")
if frame.get("opcode") == 2:  # binary
    binary_data = base64.b64decode(payload)
```

### Pitfall 2: WebSocket Frame Events Only Fire After Network.enable

```python
# ❌ Network not enabled
# No WebSocket events will be received

# ✅ Enable first
await cdp(ws, session_id, "Network.enable")
# Then webSocketCreated, webSocketFrameSent, etc. will fire
```

### Pitfall 3: Inject Script Doesn't Affect Existing WebSocket Connections

```python
# Page.addScriptToEvaluateOnNewDocument only affects newly created pages
# Already established WebSocket connections won't be hooked

# ✅ Inject before navigation
await inject_websocket_interceptor(ws, session_id)
await cdp(ws, session_id, "Page.navigate", {"url": url})

# ❌ Navigation-first injection won't hook existing WS connections
await cdp(ws, session_id, "Page.navigate", {"url": url})
await inject_websocket_interceptor(ws, session_id)  # Existing WS won't be hooked
```

### Pitfall 4: WebSocket Connections in Different Frames Are Separate

```python
# Each frame's WebSocket is independent
# The webSocketCreated event includes a frameId
# Use frameId to distinguish WS connections from different iframes
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Enable Network | Must call Network.enable before listening |
| Injection timing | Interceptor script must be injected before navigation |
| Frame encoding | Text frames UTF-8, binary frames Base64 |
| JSON parsing | WebSocket commonly uses JSON, try to parse payload |
| Multiple connections | Use requestId to distinguish different WS connections |
| Traffic export | Periodically export to file to avoid memory overflow |

---

## Complete Reference: CDP WebSocket Debugger Class

```python
import asyncio
import json
from datetime import datetime


class CDPWebSocketDebugger:
    """CDP WebSocket Debugger"""

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

**Usage Example:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    ws_debug = CDPWebSocketDebugger(ws, session_id)
    await ws_debug.start()

    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    frames = await ws_debug.capture(duration=15)
    print(f"Captured {ws_debug.summary()['total']} frames")
```

---

> **Summary**: CDP's Network domain provides complete WebSocket frame visibility — capture each frame's content and direction, analyze traffic patterns, and inject interception scripts. This makes WebSocket protocol automated testing and debugging straightforward and reliable.

---

*Previous: CDP Security & Certificate Handling Guide: Manage Browser Security with Python*

*Next up: CDP Event System Guide: Listening to Browser Events with Python*