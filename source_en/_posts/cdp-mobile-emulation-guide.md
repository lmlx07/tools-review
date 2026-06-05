---
lang: en
title: "CDP Mobile Device Emulation Guide: Debug Mobile Pages with Python"
date: "2026-06-05 16:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Mobile Debugging
  - Touch Events
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to emulating mobile devices using Chrome DevTools Protocol (CDP). Learn how to set device metrics (resolution/DPR/viewport), simulate touch events, spoof geolocation, emulate device orientation, and automate mobile compatibility testing.
---

> **Summary in one sentence**: CDP's `Emulation` domain can turn desktop Chrome into any mobile device — iPhone, iPad, Android phone — complete with touch events, geolocation, and screen orientation.

---

## Table of Contents

1. [Why Use CDP for Mobile Emulation](#why-use-cdp-for-mobile-emulation)
2. [Setting Device Metrics](#setting-device-metrics)
3. [Simulating Touch Events](#simulating-touch-events)
4. [Spoofing Geolocation](#spoofing-geolocation)
5. [Emulating Device Orientation](#emulating-device-orientation)
6. [Practical: Automated Mobile Compatibility Testing](#practical-automated-mobile-compatibility-testing)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Mobile Emulation

Unlike Chrome DevTools' "Toggle Device Toolbar" (manual mode), CDP's Emulation domain supports scripted control:

| Feature | DevTools Manual | CDP Emulation |
|---------|----------------|---------------|
| Device resolution | ✅ Pick from list | ✅ Any custom value |
| DPR scaling | ✅ Preset values | ✅ Exact control |
| Touch events | ✅ Auto-switch | ✅ Force on/off |
| Geolocation spoofing | ⚠️ Sensors panel manual | ✅ Command-level |
| Orientation | ❌ Portrait/landscape only | ✅ Arbitrary alpha/beta/gamma |
| Automation | ❌ No scripting | ✅ Fully programmable |
| Multi-device rotation | ❌ Manual switch | ✅ Script loop |

**Key use cases**:
- Automated mobile layout testing in CI/CD
- Simulating user flows on different devices
- Testing location-based features (maps, check-ins)
- Debugging mobile-specific touch events and gestures

---

## Setting Device Metrics

### Basic: Override Device Metrics

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


async def set_device_metrics(ws, session_id, width, height,
                              device_scale_factor=2,
                              mobile=True, screen_width=None,
                              screen_height=None):
    params = {
        "width": width,
        "height": height,
        "deviceScaleFactor": device_scale_factor,
        "mobile": mobile
    }
    if screen_width:
        params["screenWidth"] = screen_width
    if screen_height:
        params["screenHeight"] = screen_height
    
    return await cdp(ws, session_id,
                     "Emulation.setDeviceMetricsOverride", params)


async def clear_device_metrics(ws, session_id):
    return await cdp(ws, session_id,
                     "Emulation.clearDeviceMetricsOverride")
```

### Device Presets

```python
DEVICE_PRESETS = {
    "iphone_14_pro": {
        "width": 390, "height": 844,
        "scale": 3, "mobile": True,
        "screen_width": 390, "screen_height": 844
    },
    "iphone_se": {
        "width": 375, "height": 667,
        "scale": 2, "mobile": True,
        "screen_width": 375, "screen_height": 667
    },
    "ipad_pro_12.9": {
        "width": 1024, "height": 1366,
        "scale": 2, "mobile": True,
        "screen_width": 1024, "screen_height": 1366
    },
    "pixel_7": {
        "width": 412, "height": 915,
        "scale": 2.625, "mobile": True,
        "screen_width": 412, "screen_height": 915
    },
    "galaxy_s22": {
        "width": 360, "height": 780,
        "scale": 3, "mobile": True
    },
    "desktop_hd": {
        "width": 1920, "height": 1080,
        "scale": 1, "mobile": False
    }
}


async def emulate_device(ws, session_id, device_name):
    if device_name not in DEVICE_PRESETS:
        raise ValueError(f"Unknown device: {device_name}")
    cfg = DEVICE_PRESETS[device_name]
    return await set_device_metrics(
        ws, session_id,
        width=cfg["width"], height=cfg["height"],
        device_scale_factor=cfg["scale"], mobile=cfg["mobile"],
        screen_width=cfg.get("screen_width"),
        screen_height=cfg.get("screen_height")
    )
```

### Setting User Agent

Device emulation usually needs a matching User-Agent:

```python
async def set_user_agent(ws, session_id, ua, platform=None):
    params = {"userAgent": ua}
    if platform:
        params["platform"] = platform
    return await cdp(ws, session_id,
                     "Emulation.setUserAgentOverride", params)


IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.0 Mobile/15E148 Safari/604.1")

PIXEL_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.6099.144 Mobile Safari/537.36")


async def setup_mobile_device(ws, session_id, device_name):
    if device_name == "iphone_14_pro":
        await emulate_device(ws, session_id, "iphone_14_pro")
        await set_user_agent(ws, session_id, IPHONE_UA, "iPhone")
    elif device_name == "pixel_7":
        await emulate_device(ws, session_id, "pixel_7")
        await set_user_agent(ws, session_id, PIXEL_UA, "Android")
    else:
        await emulate_device(ws, session_id, device_name)
    print(f"Emulated device: {device_name}")
```

---

## Simulating Touch Events

### Enabling Touch Emulation

```python
async def enable_touch(ws, session_id, enabled=True, max_touch_points=5):
    return await cdp(ws, session_id,
                     "Emulation.setTouchEmulationEnabled", {
        "enabled": enabled,
        "maxTouchPoints": max_touch_points
    })


async def setup_touch_device(ws, session_id):
    await set_device_metrics(ws, session_id, 390, 844, 3, mobile=True)
    await enable_touch(ws, session_id, enabled=True, max_touch_points=5)
    await set_user_agent(ws, session_id, IPHONE_UA, "iPhone")
```

### Simulating Touch Gestures

CDP's `Input.dispatchTouchEvent` can simulate any touch interaction:

```python
async def touch_tap(ws, session_id, x, y):
    await cdp(ws, session_id, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{
            "x": x, "y": y,
            "radiusX": 10, "radiusY": 10, "force": 1
        }]
    })
    await asyncio.sleep(0.05)
    await cdp(ws, session_id, "Input.dispatchTouchEvent", {
        "type": "touchEnd", "touchPoints": []
    })


async def touch_swipe(ws, session_id, start_x, start_y, end_x, end_y, steps=10):
    for i in range(steps + 1):
        t = i / steps
        x = start_x + (end_x - start_x) * t
        y = start_y + (end_y - start_y) * t
        event_type = "touchMove" if 0 < t < 1 else (
            "touchStart" if t == 0 else "touchEnd"
        )
        touch_points = [{"x": x, "y": y, "radiusX": 10, "radiusY": 10}] \
                       if event_type != "touchEnd" else []
        await cdp(ws, session_id, "Input.dispatchTouchEvent", {
            "type": event_type, "touchPoints": touch_points
        })
        await asyncio.sleep(0.01)


async def touch_pinch(ws, session_id, center_x, center_y, scale):
    base_distance = 50
    target_distance = base_distance * scale
    
    for phase in ["touchStart", "touchMove", "touchEnd"]:
        distance = base_distance if phase == "touchStart" else target_distance
        await cdp(ws, session_id, "Input.dispatchTouchEvent", {
            "type": phase,
            "touchPoints": [
                {"x": center_x - distance / 2, "y": center_y,
                 "radiusX": 10, "radiusY": 10},
                {"x": center_x + distance / 2, "y": center_y,
                 "radiusX": 10, "radiusY": 10}
            ]
        })
        await asyncio.sleep(0.05)
```

---

## Spoofing Geolocation

### Setting Latitude/Longitude

```python
async def set_geolocation(ws, session_id, latitude, longitude, accuracy=100):
    return await cdp(ws, session_id,
                     "Emulation.setGeolocationOverride", {
        "latitude": latitude, "longitude": longitude, "accuracy": accuracy
    })


async def clear_geolocation(ws, session_id):
    return await cdp(ws, session_id,
                     "Emulation.clearGeolocationOverride")


LOCATIONS = {
    "beijing": {"lat": 39.9042, "lng": 116.4074},
    "shanghai": {"lat": 31.2304, "lng": 121.4737},
    "new_york": {"lat": 40.7128, "lng": -74.0060},
    "london": {"lat": 51.5074, "lng": -0.1278},
    "tokyo": {"lat": 35.6762, "lng": 139.6503},
}


async def test_location_based_features(ws, session_id, url):
    for city, coord in LOCATIONS.items():
        print(f"Testing location: {city}")
        await set_geolocation(ws, session_id, coord["lat"], coord["lng"])
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(3)
        await cdp(ws, session_id, "Page.captureScreenshot", {"format": "jpeg"})
        print(f"  {city} screenshot captured")
    await clear_geolocation(ws, session_id)
```

### Granting Geolocation Permission

```python
async def grant_geolocation_permission(ws, session_id):
    await cdp(ws, session_id, "Browser.setPermission", {
        "permission": {"name": "geolocation"},
        "setting": "granted"
    })
```

---

## Emulating Device Orientation

```python
async def set_device_orientation(ws, session_id, alpha, beta, gamma):
    return await cdp(ws, session_id,
                     "Emulation.setDeviceOrientationOverride", {
        "alpha": alpha, "beta": beta, "gamma": gamma
    })


async def clear_device_orientation(ws, session_id):
    return await cdp(ws, session_id,
                     "Emulation.clearDeviceOrientationOverride")


ORIENTATIONS = {
    "portrait": {"alpha": 0, "beta": 0, "gamma": 0},
    "landscape_left": {"alpha": 0, "beta": 0, "gamma": 90},
    "landscape_right": {"alpha": 0, "beta": 0, "gamma": -90},
    "tilt_forward": {"alpha": 0, "beta": 45, "gamma": 0},
    "tilt_backward": {"alpha": 0, "beta": -45, "gamma": 0},
}


async def test_orientations(ws, session_id, url):
    for name, orient in ORIENTATIONS.items():
        print(f"Orientation: {name}")
        await set_device_orientation(ws, session_id, **orient)
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(2)
        await cdp(ws, session_id, "Page.captureScreenshot", {"format": "jpeg"})
    await clear_device_orientation(ws, session_id)
```

---

## Practical: Automated Mobile Compatibility Testing

A comprehensive script that tests a page across multiple devices:

```python
async def mobile_compatibility_test(ws, session_id, url):
    results = {}
    devices_to_test = ["iphone_14_pro", "pixel_7", "ipad_pro_12.9"]
    
    for device in devices_to_test:
        print(f"\n{'='*50}")
        print(f"Testing device: {device}")
        print(f"{'='*50}")
        
        await setup_mobile_device(ws, session_id, device)
        
        if device == "iphone_14_pro":
            await set_geolocation(ws, session_id, 39.9042, 116.4074)
            await grant_geolocation_permission(ws, session_id)
        
        await cdp(ws, session_id, "Performance.enable")
        
        start = asyncio.get_event_loop().time()
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(3)
        await cdp(ws, session_id, "Page.loadEventFired")
        load_time = asyncio.get_event_loop().time() - start
        
        await cdp(ws, session_id, "Page.captureScreenshot", {"format": "jpeg"})
        
        perf = await cdp(ws, session_id, "Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in perf.get("metrics", [])}
        
        results[device] = {
            "load_time": round(load_time, 2),
            "metrics": metrics
        }
        print(f"  Load time: {load_time:.2f}s")
        await clear_geolocation(ws, session_id)
    
    await clear_device_metrics(ws, session_id)
    await cdp(ws, session_id, "Emulation.setUserAgentOverride", {"userAgent": ""})
    
    print(f"\n{'='*50}")
    print("Compatibility Test Results")
    print(f"{'='*50}")
    for device, data in results.items():
        print(f"{device:20s}: {data['load_time']:>5.2f}s load")
    
    return results
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Order Matters

Device metrics must be set BEFORE navigating:

```python
# ❌ Wrong: navigate then set metrics
await cdp(ws, session_id, "Page.navigate", {"url": url})
await set_device_metrics(ws, session_id, 390, 844, 3)  # Already loaded, won't reflow

# ✅ Correct: set metrics first
await set_device_metrics(ws, session_id, 390, 844, 3)
await cdp(ws, session_id, "Page.navigate", {"url": url})
```

### Pitfall 2: Touch vs. Mouse Events

When touch emulation is enabled, some mouse events may not fire:

```python
await enable_touch(ws, session_id, enabled=True)
# mouseenter/mouseleave may not trigger on some pages
# Manually dispatch mouse events if needed:
await cdp(ws, session_id, "Input.dispatchMouseEvent", {
    "type": "mousePressed", "x": 100, "y": 200,
    "button": "left", "clickCount": 1
})
```

### Pitfall 3: Geolocation Requires HTTPS

Most browsers only allow geolocation API on HTTPS pages:

```python
# ❌ HTTP pages may fail to get location
await set_geolocation(ws, session_id, 39.9, 116.4)
# navigator.geolocation.getCurrentPosition() may still fail

# ✅ Always test on HTTPS
await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com/map"})
```

### Pitfall 4: UA Override Affects All Requests

```python
# Once set, all subresource requests use the overridden UA
await set_user_agent(ws, session_id, IPHONE_UA)

# Must set before navigation for the main request to use it
# Clear by passing empty string:
await cdp(ws, session_id, "Emulation.setUserAgentOverride", {"userAgent": ""})
```

### Pitfall 5: Viewport vs. Physical Screen Size

`width/height` = logical viewport, `screenWidth/screenHeight` = physical pixels:

```python
# iPhone 14 Pro example
await set_device_metrics(ws, session_id,
    width=390, height=844,      # Logical viewport
    device_scale_factor=3,
    screen_width=1170,          # 390 * 3 = 1170
    screen_height=2532,         # 844 * 3 = 2532
    mobile=True
)
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Set order | **Set metrics first, then navigate** |
| Touch events | Some mouse events won't fire — dispatch manually if needed |
| Geolocation | Test on HTTPS pages only |
| UA override | Affects all requests — set before navigation |
| Viewport vs physical | Know the difference between logical and physical pixels |
| Cleanup | Call `clearDeviceMetricsOverride` after testing |

---

## Complete Reference: CDP Mobile Emulator Class

```python
import asyncio
import json
import websockets


class CDPMobileEmulator:
    DEVICES = {
        "iphone_14_pro": (390, 844, 3, True, 1170, 2532),
        "iphone_se": (375, 667, 2, True, 750, 1334),
        "pixel_7": (412, 915, 2.625, True, 1080, 2400),
        "galaxy_s22": (360, 780, 3, True, 1080, 2340),
        "ipad_pro": (1024, 1366, 2, True, 2048, 2732),
    }
    USER_AGENTS = {
        "iphone_14_pro": ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148"),
        "pixel_7": ("Mozilla/5.0 (Linux; Android 14; Pixel 7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.6099.144 Mobile"),
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
    
    async def emulate(self, device_name):
        if device_name not in self.DEVICES:
            raise ValueError(f"Unknown device: {device_name}")
        w, h, scale, mobile, sw, sh = self.DEVICES[device_name]
        await self._cmd("Emulation.setDeviceMetricsOverride", {
            "width": w, "height": h, "deviceScaleFactor": scale,
            "mobile": mobile, "screenWidth": sw, "screenHeight": sh
        })
        if device_name in self.USER_AGENTS:
            await self._cmd("Emulation.setUserAgentOverride", {
                "userAgent": self.USER_AGENTS[device_name]
            })
        print(f"Emulated: {device_name}")
    
    async def set_geo(self, lat, lng, accuracy=100):
        await self._cmd("Emulation.setGeolocationOverride", {
            "latitude": lat, "longitude": lng, "accuracy": accuracy
        })
    
    async def set_orientation(self, alpha=0, beta=0, gamma=0):
        await self._cmd("Emulation.setDeviceOrientationOverride", {
            "alpha": alpha, "beta": beta, "gamma": gamma
        })
    
    async def reset(self):
        await self._cmd("Emulation.clearDeviceMetricsOverride")
        await self._cmd("Emulation.setUserAgentOverride", {"userAgent": ""})
        await self._cmd("Emulation.clearGeolocationOverride")
        await self._cmd("Emulation.clearDeviceOrientationOverride")
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    mobile = CDPMobileEmulator(ws, session_id)
    
    await mobile.emulate("iphone_14_pro")
    await mobile.set_geo(39.9042, 116.4074)
    
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(3)
    
    await mobile.reset()
```

---

> **Summary**: CDP's Emulation domain provides complete mobile device emulation — from resolution and DPR to touch events, geolocation, and orientation sensors. This makes automated mobile testing in CI/CD simple and reliable without maintaining a real device farm.

---

*Previous: CDP Network Condition Emulation Guide — control bandwidth, latency & offline with Python.*

*Next up: CDP Screenshot & PDF Export — generating precise page screenshots and PDF reports in Python.*
