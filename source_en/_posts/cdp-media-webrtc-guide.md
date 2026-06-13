---
lang: en
title: "CDP Media & WebRTC Debugging: Controlling Audio/Video with Python"
date: "2026-06-05 18:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Media Debugging
  - WebRTC
  - Audio/Video
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to debugging media playback and WebRTC connections using Chrome DevTools Protocol (CDP). Covers media player event monitoring, WebRTC ICE connection state tracking, data channel analysis, WebRTC stats collection, and video frame capture.
---

> **Summary in one sentence**: CDP's Media domain and WebRTC domain allow you to programmatically monitor media player state changes, track the full ICE negotiation process of WebRTC connections, analyze data channel traffic, and even capture video frames for screenshots.

---

## Table of Contents

1. [CDP Media Debugging Overview](#cdp-media-debugging-overview)
2. [Enabling the Media Domain and Listening for Player Events](#enabling-the-media-domain-and-listening-for-player-events)
3. [WebRTC Debugging and ICE State Monitoring](#webrtc-debugging-and-ice-state-monitoring)
4. [Analyzing Data Channels](#analyzing-data-channels)
5. [Collecting WebRTC Statistics](#collecting-webrtc-statistics)
6. [Media Playback Control and Video Frame Capture](#media-playback-control-and-video-frame-capture)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)
8. [Complete Reference: CDP Media/WebRTC Debugger Class](#complete-reference-cdp-mediawebrtc-debugger-class)

---

## CDP Media Debugging Overview

| CDP Domain | Use Case | Core Capabilities |
|------------|----------|-------------------|
| `Media` | Media players (video/audio) | Monitor playback state, buffering, error events |
| `WebRTC` | Real-time communication (RTCPeerConnection) | ICE state, data channels, statistics |

---

## Enabling the Media Domain and Listening for Player Events

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
    """Monitor media player events"""
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
                    print(f"[Media] {prop['name']} = {prop['value']}")
            
            elif method == "Media.playerErrorsRaised":
                pid = p["playerId"]
                if pid not in players:
                    players[pid] = {"events": [], "errors": []}
                for err in p.get("errors", []):
                    players[pid]["errors"].append(err)
                    print(f"[Media] Error: {err.get('message', '')}")
                    
        except asyncio.TimeoutError:
            continue
    return players
```

---

## WebRTC Debugging and ICE State Monitoring

### Enabling WebRTC and Monitoring Connections

```python
async def monitor_webrtc_connections(ws, session_id, duration=30):
    """Monitor WebRTC connections and ICE states"""
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
                print(f"[WebRTC] Connection created: {cid}")
            
            elif method == "WebRTC.connectionStateChanged":
                cid = p["connectionId"]
                if cid in connections:
                    connections[cid]["state"] = p["state"]
                print(f"[WebRTC] State changed [{cid}]: {p['state']}")
            
            elif method == "WebRTC.iceGatheringStateChanged":
                cid = p["connectionId"]
                if cid in connections:
                    connections[cid]["ice_gathering"] = p["state"]
                print(f"[ICE Gathering] [{cid}]: {p['state']}")
            
            elif method == "WebRTC.iceCandidatePairChanged":
                cid = p["connectionId"]
                pair = p.get("candidatePair", {})
                if cid in connections:
                    connections[cid].setdefault("pairs", []).append({
                        "state": pair.get("state"),
                        "time": datetime.now().isoformat()
                    })
                print(f"[ICE Pair] [{cid}]: {pair.get('state')}")
            
            elif method == "WebRTC.connectionClosed":
                cid = p["connectionId"]
                if cid in connections:
                    connections[cid]["closed"] = datetime.now().isoformat()
                print(f"[WebRTC] Connection closed: {cid}")
                    
        except asyncio.TimeoutError:
            continue
    return connections


def diagnose_ice_connections(connections):
    """Diagnose ICE connections"""
    for cid, info in connections.items():
        state = info.get("state", "unknown")
        pairs = info.get("pairs", [])
        succeeded = sum(1 for p in pairs if p["state"] == "succeeded")
        failed = sum(1 for p in pairs if p["state"] == "failed")
        status = "Healthy" if state in ("connected", "completed") else \
                 "Failed" if state == "failed" else "Warning"
        print(f"[{cid}] State: {state}, Pairs: {succeeded}OK/{failed}FAIL => {status}")
```

---

## Analyzing Data Channels

```python
async def monitor_data_channels(ws, session_id, duration=30):
    """Monitor WebRTC data channels"""
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
                print(f"[DataChannel] Created: {dc.get('label')}")
            
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

## Collecting WebRTC Statistics

```python
async def collect_connection_stats(ws, session_id, conn_id):
    """Collect WebRTC statistics"""
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
    """Periodically collect statistics"""
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        stats = await collect_connection_stats(ws, session_id, conn_id)
        inbound = stats.get("inbound-rtp", {})
        outbound = stats.get("outbound-rtp", {})
        for r in inbound.values():
            print(f"[Inbound] bytes={r.get('bytesReceived',0)} "
                  f"packets={r.get('packetsReceived',0)} "
                  f"lost={r.get('packetsLost',0)}")
        for r in outbound.values():
            print(f"[Outbound] bytes={r.get('bytesSent',0)}")
        await asyncio.sleep(3)
```

---

## Media Playback Control and Video Frame Capture

```python
async def control_playback(ws, session_id, action="toggle", index=0):
    """Control media playback"""
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
    """Capture video frame (Canvas approach)"""
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
    """Save video frame to file"""
    img = await capture_video_frame(ws, session_id, index)
    if img:
        with open(path, "wb") as f:
            f.write(img)
        print(f"Frame saved: {path} ({len(img)} bytes)")
        return True
    return False


async def inspect_media_element(ws, session_id, tag="video", index=0):
    """Inspect media element state"""
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

## Common Pitfalls & Best Practices

- **Enable order**: Call Media.enable and WebRTC.enable before navigation to avoid missing initial events
- **Black video frames**: Ensure the video is playing before capturing Canvas, otherwise you get a black frame
- **Cross-origin CORS**: Canvas toDataURL on cross-origin video throws a security error; bypass via Security.setIgnoreCertificateErrors
- **ICE event storm**: Batch-process ICE candidate pair events; avoid heavy processing in the event loop
- **Stats collection**: getStats requires a valid connectionId; call it after connectionCreated

| Consideration | Recommendation |
|---------------|----------------|
| Enable order | Enable Media/WebRTC before navigation |
| Video capture | Play first, wait, then capture to avoid black frames |
| Frame rate | Canvas capture interval >= 100ms |
| Resource cleanup | Close connections after testing |

---

## Complete Reference: CDP Media/WebRTC Debugger Class

```python
import asyncio, json, base64
from datetime import datetime


class CDPMediaDebugger:
    """CDP Media & WebRTC Debugger"""
    
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

**Usage Example:**

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
    print(f"Results: {debugger.summary()}")
```

---

> **Summary**: CDP's Media and WebRTC domains provide comprehensive programmatic interfaces for audio/video debugging. Monitor media player state, track WebRTC ICE connections, analyze data channels, collect statistics, and capture video frames using the Canvas approach.

---

*Previous: CDP Accessibility Guide: Automated Accessibility Testing with Python*

*Next up: CDP Worker Debug Guide: Debugging Web Workers with Python*