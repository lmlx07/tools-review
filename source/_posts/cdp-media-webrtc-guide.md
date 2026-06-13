---
title: CDP 媒体与 WebRTC 调试：用 Python 控制音视频
date: 2026-06-05 18:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 媒体调试
  - WebRTC
  - 音视频
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）调试媒体播放与 WebRTC 连接。涵盖媒体播放事件监听、WebRTC ICE 连接状态监控、数据通道分析、WebRTC 统计信息采集、以及视频帧截图。
---

> **一句话总结**：CDP 的 Media 域和 WebRTC 域让你可以编程式监控媒体播放器的状态变化、追踪 WebRTC 连接的 ICE 协商全过程、分析数据通道流量，甚至捕获视频帧进行截图。

---

## 目录

1. [CDP 媒体调试概览](#cdp-媒体调试概览)
2. [启用 Media 域并监听播放器事件](#启用-media-域并监听播放器事件)
3. [WebRTC 调试基础与 ICE 状态监控](#webrtc-调试基础与-ice-状态监控)
4. [分析数据通道](#分析数据通道)
5. [WebRTC 统计信息采集](#webrtc-统计信息采集)
6. [媒体播放控制与视频帧截图](#媒体播放控制与视频帧截图)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)
8. [完整参考：CDP 媒体/WebRTC 调试类](#完整参考cdp-媒体webrtc-调试类)

---

## CDP 媒体调试概览

| CDP 域 | 适用场景 | 核心能力 |
|--------|---------|----------|
| `Media` | 媒体播放器（video/audio） | 监控播放状态、缓冲、错误事件 |
| `WebRTC` | 实时通信（RTCPeerConnection） | ICE 状态、数据通道、统计信息 |

---

## 启用 Media 域并监听播放器事件

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


async def monitor_media_events(ws, session_id, duration=30):
    """监控媒体播放器事件"""
    await cdp(ws, "Media.enable", session_id=session_id)
    players = {}
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method, p = data.get("method", ""), data.get("params", {})
            
            if method == "Media.playerPropertiesChanged":
                pid = p["playerId"]
                if pid not in players:
                    players[pid] = {"events": [], "errors": []}
                for prop in p.get("properties", []):
                    players[pid]["events"].append({
                        "name": prop["name"], "value": prop["value"],
                        "time": datetime.now().isoformat()
                    })
                    print(f"[媒体] {prop['name']} = {prop['value']}")
            
            elif method == "Media.playerErrorsRaised":
                pid = p["playerId"]
                if pid not in players:
                    players[pid] = {"events": [], "errors": []}
                for err in p.get("errors", []):
                    players[pid]["errors"].append(err)
                    print(f"[媒体] 错误: {err.get('message', '')}")
                    
        except asyncio.TimeoutError:
            continue
    return players
```

---

## WebRTC 调试基础与 ICE 状态监控

### 启用 WebRTC 并监控连接

```python
async def monitor_webrtc_connections(ws, session_id, duration=30):
    """监控 WebRTC 连接和 ICE 状态"""
    await cdp(ws, "WebRTC.enable", session_id=session_id)
    connections = {}
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method, p = data.get("method", ""), data.get("params", {})
            
            if method == "WebRTC.connectionCreated":
                cid = p["connectionId"]
                connections[cid] = {"created": datetime.now().isoformat()}
                print(f"[WebRTC] 连接创建: {cid}")
            
            elif method == "WebRTC.connectionStateChanged":
                cid = p["connectionId"]
                if cid in connections:
                    connections[cid]["state"] = p["state"]
                print(f"[WebRTC] 状态变更 [{cid}]: {p['state']}")
            
            elif method == "WebRTC.iceGatheringStateChanged":
                cid = p["connectionId"]
                if cid in connections:
                    connections[cid]["ice_gathering"] = p["state"]
                print(f"[ICE 收集] [{cid}]: {p['state']}")
            
            elif method == "WebRTC.iceCandidatePairChanged":
                cid = p["connectionId"]
                pair = p.get("candidatePair", {})
                if cid in connections:
                    connections[cid].setdefault("pairs", []).append({
                        "state": pair.get("state"),
                        "time": datetime.now().isoformat()
                    })
                print(f"[ICE 候选对] [{cid}]: {pair.get('state')}")
            
            elif method == "WebRTC.connectionClosed":
                cid = p["connectionId"]
                if cid in connections:
                    connections[cid]["closed"] = datetime.now().isoformat()
                print(f"[WebRTC] 连接关闭: {cid}")
                    
        except asyncio.TimeoutError:
            continue
    return connections


def diagnose_ice_connections(connections):
    """诊断 ICE 连接"""
    for cid, info in connections.items():
        state = info.get("state", "unknown")
        pairs = info.get("pairs", [])
        succeeded = sum(1 for p in pairs if p["state"] == "succeeded")
        failed = sum(1 for p in pairs if p["state"] == "failed")
        status = "Healthy" if state in ("connected", "completed") else \
                 "Failed" if state == "failed" else "Warning"
        print(f"[{cid}] 状态: {state}, 候选对: {succeeded}成功/{failed}失败 => {status}")
```

---

## 分析数据通道

```python
async def monitor_data_channels(ws, session_id, duration=30):
    """监控 WebRTC 数据通道"""
    await cdp(ws, "WebRTC.enable", session_id=session_id)
    channels = {}
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method, p = data.get("method", ""), data.get("params", {})
            
            if method == "WebRTC.dataChannelCreated":
                dc = p.get("dataChannel", {})
                channels[dc["id"]] = {
                    "label": dc.get("label"),
                    "state": dc.get("state"),
                    "created": datetime.now().isoformat(),
                    "sent": 0, "received": 0
                }
                print(f"[DataChannel] 创建: {dc.get('label')}")
            
            elif method == "WebRTC.dataChannelStateChanged":
                dc = p.get("dataChannel", {})
                if dc["id"] in channels:
                    channels[dc["id"]]["state"] = dc["state"]
                print(f"[DataChannel] [{dc['id']}] -> {dc['state']}")
            
            elif method == "WebRTC.dataChannelMessageReceived":
                if p.get("dataChannel", {}).get("id") in channels:
                    channels[p["dataChannel"]["id"]]["received"] += 1
            
            elif method == "WebRTC.dataChannelMessageSent":
                if p.get("dataChannel", {}).get("id") in channels:
                    channels[p["dataChannel"]["id"]]["sent"] += 1
                    
        except asyncio.TimeoutError:
            continue
    return channels
```

---

## WebRTC 统计信息采集

```python
async def collect_connection_stats(ws, session_id, conn_id):
    """采集 WebRTC 统计信息"""
    stats = await cdp(ws, "WebRTC.getStats", {
        "connectionId": conn_id
    }, session_id=session_id)
    parsed = {}
    for report in stats.get("reports", []):
        rtype = report.get("type", "unknown")
        rid = report.get("id", "")
        values = report.get("stats", {})
        values.pop("timestamp", None)
        parsed.setdefault(rtype, {})[rid] = values
    return parsed


async def monitor_webrtc_stats(ws, session_id, conn_id, duration=30):
    """定时采集统计信息"""
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        stats = await collect_connection_stats(ws, session_id, conn_id)
        inbound = stats.get("inbound-rtp", {})
        outbound = stats.get("outbound-rtp", {})
        for r in inbound.values():
            print(f"[入站] bytes={r.get('bytesReceived',0)} "
                  f"packets={r.get('packetsReceived',0)} "
                  f"lost={r.get('packetsLost',0)}")
        for r in outbound.values():
            print(f"[出站] bytes={r.get('bytesSent',0)}")
        await asyncio.sleep(3)
```

---

## 媒体播放控制与视频帧截图

```python
async def control_playback(ws, session_id, action="toggle", index=0):
    """控制媒体播放"""
    js = {
        "play": f"document.querySelectorAll('video,audio')[{index}].play()",
        "pause": f"document.querySelectorAll('video,audio')[{index}].pause()",
        "toggle": f"""
            (()=>{{const e=document.querySelectorAll('video,audio')[{index}];
            e.paused?e.play():e.pause();return e.paused?'paused':'playing';}})()"""
    }[action]
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True
    }, session_id=session_id)
    return result.get("result", {}).get("value")


async def capture_video_frame(ws, session_id, index=0):
    """捕获视频帧（Canvas 方案）"""
    js = f"""
    (()=>{{const v=document.querySelectorAll('video')[{index}];
    if(!v)return null;const c=document.createElement('canvas');
    c.width=v.videoWidth||v.clientWidth;
    c.height=v.videoHeight||v.clientHeight;
    c.getContext('2d').drawImage(v,0,0);
    return c.toDataURL('image/png');}})()
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": js, "returnByValue": True
    }, session_id=session_id)
    data_url = result.get("result", {}).get("value", "")
    if data_url.startswith("data:image"):
        import base64
        return base64.b64decode(data_url.split(",")[1])
    return None


async def save_video_frame(ws, session_id, path, index=0):
    """保存视频帧到文件"""
    img = await capture_video_frame(ws, session_id, index)
    if img:
        with open(path, "wb") as f:
            f.write(img)
        print(f"帧已保存: {path} ({len(img)} bytes)")
        return True
    return False


async def inspect_media_element(ws, session_id, tag="video", index=0):
    """检查媒体元素状态"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (()=>{{const el=document.querySelectorAll('{tag}')[{index}];
            if(!el)return null;
            return{{src:el.currentSrc,duration:el.duration,
            currentTime:el.currentTime,paused:el.paused,ended:el.ended,
            volume:el.volume,readyState:el.readyState,
            videoWidth:el.videoWidth,videoHeight:el.videoHeight}};}})()
        """,
        "returnByValue": True
    }, session_id=session_id)
    return result.get("result", {}).get("value")
```

---

## 常见踩坑与最佳实践

- **启用顺序**：Media.enable 和 WebRTC.enable 需在导航前调用，否则可能错过初始事件
- **视频帧黑屏**：确保视频处于播放状态再截取 Canvas，否则得到黑帧
- **跨域 CORS**：跨域视频源的 Canvas toDataURL 会抛安全错误，可通过 Security.setIgnoreCertificateErrors 绕过
- **ICE 事件风暴**：大量 ICE candidate pair 事件建议使用批处理，不要在事件循环中做繁重操作
- **统计采集**：getStats 需要有效的 connectionId，在 connectionCreated 之后调用

| 注意点 | 建议 |
|--------|------|
| 启用顺序 | Media/WebRTC 域要在导航前启用 |
| 视频截图 | 先 play() 等待再截取，避免黑屏 |
| 帧率 | Canvas 截图间隔不低于 100ms |
| 资源清理 | 测试完成后关闭连接 |

---

## 完整参考：CDP 媒体/WebRTC 调试类

```python
import asyncio, json, base64
from datetime import datetime


class CDPMediaDebugger:
    """CDP 媒体与 WebRTC 调试器"""
    
    def __init__(self, ws, session_id):
        self.ws, self.sid = ws, session_id
        self._cid = 0
        self.players, self.rtc, self.channels = {}, {}, {}
    
    async def _cmd(self, method, params=None, sid=None):
        self._cid += 1
        msg = {"id": self._cid, "method": method, "params": params or {}}
        if sid or self.sid:
            msg["sessionId"] = sid or self.sid
        await self.ws.send(json.dumps(msg))
        async for r in self.ws:
            d = json.loads(r)
            if d.get("id") == self._cid:
                return d.get("result", {})
    
    async def start(self):
        await self._cmd("Media.enable")
        await self._cmd("WebRTC.enable")
    
    async def monitor(self, duration=30):
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                d, m, p = json.loads(msg), d.get("method",""), d.get("params",{})
                if m == "Media.playerPropertiesChanged":
                    self.players.setdefault(p["playerId"],{"events":[]})["events"].extend(p.get("properties",[]))
                elif m == "WebRTC.connectionCreated":
                    self.rtc[p["connectionId"]] = {}
                elif m == "WebRTC.connectionStateChanged":
                    if p["connectionId"] in self.rtc:
                        self.rtc[p["connectionId"]]["state"] = p["state"]
                elif m == "WebRTC.dataChannelCreated":
                    dc = p["dataChannel"]
                    self.channels[dc["id"]] = {"label": dc.get("label")}
            except asyncio.TimeoutError:
                continue
    
    async def capture_frame(self, idx=0):
        r = await self._cmd("Runtime.evaluate", {
            "expression": f"(()=>{{const v=document.querySelectorAll('video')[{idx}];if(!v)return null;const c=document.createElement('canvas');c.width=v.videoWidth||v.clientWidth;c.height=v.videoHeight||v.clientHeight;c.getContext('2d').drawImage(v,0,0);return c.toDataURL('image/png');}})()",
            "returnByValue": True
        })
        du = r.get("result",{}).get("value","")
        return base64.b64decode(du.split(",")[1]) if du.startswith("data:image") else None
    
    async def get_stats(self, conn_id):
        return await self._cmd("WebRTC.getStats", {"connectionId": conn_id})
    
    def summary(self):
        return {"players": len(self.players), "rtc_connections": len(self.rtc), "data_channels": len(self.channels)}
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    debugger = CDPMediaDebugger(ws, session_id)
    await debugger.start()
    await cdp(ws, "Page.navigate", {"url": "https://example.com/webrtc-demo"}, session_id=session_id)
    await debugger.monitor(duration=15)
    frame = await debugger.capture_frame()
    if frame:
        with open("frame.png", "wb") as f: f.write(frame)
    print(f"结果: {debugger.summary()}")
```

---

> **总结**：CDP 的 Media 域和 WebRTC 域为音视频调试提供了全面的编程接口。你可以监控媒体播放器状态、追踪 WebRTC 的 ICE 连接全过程、分析数据通道流量、采集统计信息，还能通过 Canvas 方案捕获视频帧。

---

*上一篇回顾：CDP 无障碍树指南：用 Python 做自动化可访问性测试。*

*下一篇预告：CDP Worker 调试指南：用 Python 调试 Web Workers。*