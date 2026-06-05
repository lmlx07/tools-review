---
lang: en
title: "CDP Network Condition Emulation Guide: Control Bandwidth, Latency & Offline with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Network Emulation
  - Browser Automation
  - Performance Testing
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to emulating network conditions using Chrome DevTools Protocol (CDP). Learn how to simulate throttling (2G/3G/4G/WiFi), inject latency, test offline mode, and create custom network profiles — all without external proxy tools.
---

> **Summary in one sentence**: CDP's `Network.emulateNetworkConditions` gives you precise control over the browser's network behavior — simulating everything from offline to high-speed WiFi with zero external dependencies.

---

## Table of Contents

1. [Why Use CDP for Network Emulation](#why-use-cdp-for-network-emulation)
2. [Basics: Network.emulateNetworkConditions](#basics-networkemulatenetworkconditions)
3. [Preset Network Profiles](#preset-network-profiles)
4. [Advanced: Custom Network Conditions](#advanced-custom-network-conditions)
5. [Offline Mode Testing](#offline-mode-testing)
6. [Practical: Network Impact on SPA](#practical-network-impact-on-spa)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Network Emulation

Simulating different network environments is essential for front-end performance testing. Traditional proxy tools like Fiddler or Charles require complex setup. CDP's built-in network emulation needs no external dependencies:

| Feature | Charles/Fiddler | CDP `Network.emulateNetworkConditions` |
|---------|----------------|--------------------------------------|
| Bandwidth throttling | ✅ Proxy-based | ✅ Native |
| Latency injection | ✅ Requires config | ✅ Native |
| Packet loss | ✅ Supported | ❌ Not supported |
| Offline testing | ✅ Disconnect network | ✅ Browser-level offline |
| HTTPS interception | ⚠️ Needs certificate | ✅ Native, no cert needed |
| Dynamic switching | ❌ Restart proxy | ✅ Command-level instant |

**Best for**:
- Testing page load behavior on slow networks
- Verifying offline fallback strategies
- Simulating API request timeouts
- Competitor performance analysis

---

## Basics: Network.emulateNetworkConditions

### Connect and Send Commands

```python
import asyncio
import websockets
import json

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
```

### Setting Network Conditions

`Network.emulateNetworkConditions` accepts these parameters:

```python
async def set_network_conditions(ws, session_id, offline=False,
                                  latency=0, download_throughput=-1,
                                  upload_throughput=-1,
                                  connection_type="none"):
    """
    Set network conditions
    - offline: whether to simulate offline mode
    - latency: latency in milliseconds
    - download_throughput: download bandwidth (bps), -1 = unlimited
    - upload_throughput: upload bandwidth (bps), -1 = unlimited
    - connection_type: connection type (none/wifi/cellular/ethernet/other)
    """
    params = {
        "offline": offline,
        "latency": latency,
        "downloadThroughput": download_throughput,
        "uploadThroughput": upload_throughput,
        "connectionType": connection_type
    }
    return await cdp(ws, session_id, 
                     "Network.emulateNetworkConditions", params)


async def disable_network_emulation(ws, session_id):
    """Restore normal network conditions"""
    return await cdp(ws, session_id,
                     "Network.emulateNetworkConditions", {
        "offline": False,
        "latency": 0,
        "downloadThroughput": -1,
        "uploadThroughput": -1,
        "connectionType": "wifi"
    })
```

---

## Preset Network Profiles

Package common network conditions into reusable presets:

```python
NETWORK_PRESETS = {
    "offline": {
        "offline": True,
        "latency": 0,
        "download_throughput": 0,
        "upload_throughput": 0,
        "connection_type": "none"
    },
    "slow_2g": {
        "offline": False,
        "latency": 2000,
        "download_throughput": 50 * 1024,      # 50 Kbps
        "upload_throughput": 20 * 1024,         # 20 Kbps
        "connection_type": "cellular"
    },
    "2g": {
        "offline": False,
        "latency": 800,
        "download_throughput": 250 * 1024,      # 250 Kbps
        "upload_throughput": 50 * 1024,         # 50 Kbps
        "connection_type": "cellular"
    },
    "3g": {
        "offline": False,
        "latency": 200,
        "download_throughput": 750 * 1024,      # 750 Kbps
        "upload_throughput": 250 * 1024,        # 250 Kbps
        "connection_type": "cellular"
    },
    "4g": {
        "offline": False,
        "latency": 80,
        "download_throughput": 4 * 1024 * 1024,  # 4 Mbps
        "upload_throughput": 3 * 1024 * 1024,    # 3 Mbps
        "connection_type": "cellular"
    },
    "wifi": {
        "offline": False,
        "latency": 5,
        "download_throughput": 30 * 1024 * 1024, # 30 Mbps
        "upload_throughput": 15 * 1024 * 1024,   # 15 Mbps
        "connection_type": "wifi"
    },
    "slow_wifi": {
        "offline": False,
        "latency": 50,
        "download_throughput": 5 * 1024 * 1024,  # 5 Mbps
        "upload_throughput": 2 * 1024 * 1024,    # 2 Mbps
        "connection_type": "wifi"
    }
}


async def apply_network_preset(ws, session_id, preset_name):
    if preset_name not in NETWORK_PRESETS:
        raise ValueError(f"Unknown preset: {preset_name}, "
                         f"options: {list(NETWORK_PRESETS.keys())}")
    
    config = NETWORK_PRESETS[preset_name]
    return await set_network_conditions(
        ws, session_id,
        offline=config["offline"],
        latency=config["latency"],
        download_throughput=config["download_throughput"],
        upload_throughput=config["upload_throughput"],
        connection_type=config["connection_type"]
    )
```

---

## Advanced: Custom Network Conditions

### Simulating API Timeouts

Combine extreme latency with minimal bandwidth:

```python
async def simulate_api_timeout(ws, session_id):
    await set_network_conditions(
        ws, session_id,
        offline=False,
        latency=10000,          # 10 second delay
        download_throughput=100, # 100 bps (near-zero)
        upload_throughput=100,
        connection_type="cellular"
    )


async def test_timeout_behavior(ws, session_id):
    await simulate_api_timeout(ws, session_id)
    
    await cdp(ws, session_id, "Page.navigate", {
        "url": "https://example.com/dashboard"
    })
    
    await asyncio.sleep(5)
    
    result = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "jpeg", "quality": 80
    })
    
    await disable_network_emulation(ws, session_id)
    return result.get("data")
```

### Throttle API Requests Only

A more refined approach — limit API calls while loading static assets normally:

```python
async def throttle_api_only(ws, session_id):
    await cdp(ws, session_id, "Fetch.enable", {
        "patterns": [{
            "urlPattern": "*/api/*",
            "requestStage": "Response"
        }]
    })
    
    async def handle_api_delay(ws, session_id, delay_ms=3000):
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                if data.get("method") == "Fetch.requestPaused":
                    req_id = data["params"]["requestId"]
                    await asyncio.sleep(delay_ms / 1000)
                    await cdp(ws, session_id, "Fetch.continueRequest", {
                        "requestId": req_id
                    })
            except asyncio.TimeoutError:
                break
```

### Simulating Network Jitter

Toggle between normal and slow networks to simulate real-world instability:

```python
async def simulate_jitter(ws, session_id, interval=3):
    import random
    
    for i in range(5):
        print(f"[Jitter {i+1}] Switching to slow network...")
        await set_network_conditions(
            ws, session_id,
            latency=random.randint(500, 2000),
            download_throughput=random.randint(50 * 1024, 500 * 1024),
            upload_throughput=random.randint(20 * 1024, 100 * 1024),
            connection_type="cellular"
        )
        await asyncio.sleep(interval)
        
        print(f"[Jitter {i+1}] Restoring normal network...")
        await disable_network_emulation(ws, session_id)
        await asyncio.sleep(interval)
```

---

## Offline Mode Testing

### Simulating Offline and Verifying

```python
async def test_offline_mode(ws, session_id, url):
    """Test the page's offline fallback behavior"""
    # 1. Load the page online first (cache resources)
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    # 2. Switch to offline
    print("Switching to offline mode...")
    await set_network_conditions(ws, session_id, offline=True)
    
    # 3. Try navigating (should trigger offline/error page)
    result = await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(2)
    
    # 4. Screenshot to check offline appearance
    screenshot = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "jpeg"
    })
    
    # 5. Restore online
    await disable_network_emulation(ws, session_id)
    
    print("Offline test complete")
    return screenshot.get("data")
```

### Monitoring Network Events During Offline

```python
async def monitor_offline_requests(ws, session_id):
    """Listen for failed requests during offline mode"""
    net_events = []
    
    async def collect_events():
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                method = data.get("method", "")
                if method in ("Network.loadingFailed", "Network.requestServedFromCache"):
                    net_events.append({
                        "method": method,
                        "params": data.get("params", {})
                    })
                    print(f"[Network Event] {method}")
            except asyncio.TimeoutError:
                break
    
    await cdp(ws, session_id, "Network.enable")
    await set_network_conditions(ws, session_id, offline=True)
    
    collector = asyncio.create_task(collect_events())
    await asyncio.sleep(5)
    collector.cancel()
    
    return net_events
```

---

## Practical: Network Impact on SPA

A comprehensive test that measures SPA behavior under different network conditions:

```python
async def test_spa_network_impact(ws, session_id, url, actions_callback=None):
    results = {}
    scenarios = ["4g", "3g", "2g", "slow_wifi"]
    
    for scenario in scenarios:
        print(f"\n=== Testing network: {scenario} ===")
        
        await apply_network_preset(ws, session_id, scenario)
        await cdp(ws, session_id, "Performance.enable")
        await cdp(ws, session_id, "Network.enable")
        
        start_time = asyncio.get_event_loop().time()
        
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(1)
        
        await cdp(ws, session_id, "Page.loadEventFired")
        
        load_time = asyncio.get_event_loop().time() - start_time
        print(f"Page load time: {load_time:.2f}s")
        
        if actions_callback:
            await actions_callback(ws, session_id)
        
        perf_metrics = await cdp(ws, session_id, "Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in perf_metrics.get("metrics", [])}
        
        results[scenario] = {"load_time": load_time, "metrics": metrics}
    
    await disable_network_emulation(ws, session_id)
    
    print("\n=== Network Scenario Comparison ===")
    for scenario, data in results.items():
        print(f"{scenario}: load {data['load_time']:.2f}s, "
              f"JS heap {data['metrics'].get('JSHeapUsedSize', 0) / 1024 / 1024:.1f}MB")
    
    return results
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Bandwidth Unit Is bps, Not KB/s

`downloadThroughput` and `uploadThroughput` use **bits per second**, not bytes/second:

```python
# ❌ Wrong: treating as KB/s
params = {"downloadThroughput": 750}  # Actually 750 bps ~ 93 bytes/s

# ✅ Correct: manual conversion
params = {"downloadThroughput": 750 * 1024}  # 750 Kbps = 768000 bps
```

Quick reference:

| Target | bps value |
|--------|-----------|
| 56 Kbps (dial-up) | `56 * 1024` |
| 256 Kbps | `256 * 1024` |
| 1 Mbps | `1 * 1024 * 1024` |
| 10 Mbps | `10 * 1024 * 1024` |

### Pitfall 2: Offline Mode Doesn't Affect Cached Requests

Even with `offline: True`, the browser may serve cached resources from HTTP cache:

```python
# Disable cache before going offline (optional)
await cdp(ws, session_id, "Network.setCacheDisabled", {"cacheDisabled": True})
```

### Pitfall 3: Network Setting Is Browser-Wide

`Network.emulateNetworkConditions` affects the entire browser instance — all tabs share the same network conditions:

```python
# ❌ Cannot throttle tab A while tab B is normal
# One browser has one network stack

# ✅ Use separate browser instances with different --user-data-dir
```

### Pitfall 4: connectionType Is a Label, Not a Bandwidth Control

The `connectionType` parameter is informational and does not affect bandwidth:

```python
# ❌ Expecting cellular to auto-throttle
params = {"connectionType": "cellular", "downloadThroughput": -1}
# -1 means unlimited, regardless of connectionType

# ✅ Must set bandwidth explicitly
params = {"connectionType": "cellular", "downloadThroughput": 750 * 1024}
```

### Pitfall 5: Delay After Disabling Emulation

Bandwidth doesn't restore instantly after disabling emulation. Add a short delay:

```python
await disable_network_emulation(ws, session_id)
await asyncio.sleep(1)  # Wait for network stack recovery
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Bandwidth unit | Use bps (bits/sec), not bytes/sec |
| Offline testing | Combine with `setCacheDisabled` for full offline test |
| Scope | Browser-wide — all tabs share the same network |
| connectionType | Informational only, does not throttle |
| Recovery delay | Wait 1-2s after disabling emulation |
| Presets | Package common scenarios to avoid hard-coded values |

---

## Complete Reference: CDP Network Emulation Class

```python
import asyncio
import json
import websockets


class CDPNetworkCondition:
    """CDP Network Condition Controller"""
    
    PRESETS = {
        "offline": {"offline": True, "latency": 0, "download": 0, "upload": 0},
        "slow_2g": {"latency": 2000, "download": 50 * 1024, "upload": 20 * 1024},
        "2g": {"latency": 800, "download": 250 * 1024, "upload": 50 * 1024},
        "3g": {"latency": 200, "download": 750 * 1024, "upload": 250 * 1024},
        "4g": {"latency": 80, "download": 4 * 1024 * 1024, "upload": 3 * 1024 * 1024},
        "wifi": {"latency": 5, "download": 30 * 1024 * 1024, "upload": 15 * 1024 * 1024},
        "slow_wifi": {"latency": 50, "download": 5 * 1024 * 1024, "upload": 2 * 1024 * 1024},
    }
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
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
    
    async def apply(self, name):
        if name not in self.PRESETS:
            raise ValueError(f"Unknown preset: {name}")
        cfg = self.PRESETS[name]
        await self._cmd("Network.emulateNetworkConditions", {
            "offline": cfg.get("offline", False),
            "latency": cfg["latency"],
            "downloadThroughput": cfg["download"],
            "uploadThroughput": cfg["upload"],
            "connectionType": "wifi" if "wifi" in name else "cellular"
        })
    
    async def custom(self, offline=False, latency=0, download=-1, upload=-1, conn="wifi"):
        await self._cmd("Network.emulateNetworkConditions", {
            "offline": offline, "latency": latency,
            "downloadThroughput": download, "uploadThroughput": upload,
            "connectionType": conn
        })
    
    async def reset(self):
        await self.custom()
    
    def list_presets(self):
        return list(self.PRESETS.keys())
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    net = CDPNetworkCondition(ws, session_id)
    
    print("Available presets:", net.list_presets())
    
    await net.apply("3g")
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(5)
    
    await net.reset()
```

---

> **Summary**: CDP's network condition emulation gives you precise control over the browser's bandwidth, latency, and online/offline state. Combined with performance metrics and screenshot capture, you can automate testing of application behavior under any network scenario.

---

*Previous: The Complete Guide to CDP DOM Operations — real-time observation & manipulation with Python.*

*Next up: CDP Mobile Device Emulation — debugging mobile pages, simulating touch events and geolocation.*
