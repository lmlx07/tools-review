---
title: CDP 移动设备模拟指南：用 Python 调试移动端页面
date: 2026-06-05 16:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 移动端调试
  - 触摸事件
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）模拟移动设备，涵盖设置设备指标（分辨率/DPR/视口）、模拟触摸事件、伪造地理位置、模拟设备方向，以及完整的移动端测试自动化流程。
---

> **一句话总结**：CDP 的 `Emulation` 域可以让你把桌面 Chrome 伪装成任何移动设备——iPhone、iPad、Android 手机——包括触摸事件、地理位置和屏幕方向。

---

## 目录

1. [为什么用 CDP 做移动端模拟](#为什么用-cdp-做移动端模拟)
2. [设置设备指标](#设置设备指标)
3. [模拟触摸事件](#模拟触摸事件)
4. [伪造地理位置](#伪造地理位置)
5. [模拟设备方向](#模拟设备方向)
6. [实战：自动化移动端兼容性测试](#实战自动化移动端兼容性测试)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 做移动端模拟

相比 Chrome DevTools 的"Toggle Device Toolbar"（手动模式），CDP 的 Emulation 域支持脚本化控制：

| 功能 | DevTools 手动模式 | CDP Emulation |
|------|------------------|---------------|
| 设备分辨率 | ✅ 手动选择 | ✅ 任意自定义 |
| DPR 缩放 | ✅ 预设 | ✅ 精确控制 |
| 触摸事件 | ✅ 自动切换 | ✅ 强制启用/禁用 |
| 地理位置伪造 | ⚠️ 需 Sensors 面板手动设 | ✅ 命令级设置 |
| 方向模拟 | ❌ 仅 portrait/landscape | ✅ 任意 alpha/beta/gamma |
| 自动化集成 | ❌ 无法脚本化 | ✅ 完全可编程 |
| 多设备轮换 | ❌ 手动切换 | ✅ 脚本循环 |

**核心场景**：
- CI/CD 中自动化移动端布局测试
- 模拟用户在不同设备上的操作路径
- 测试地理位置相关的功能（如地图、签到）
- 调试移动端特有的触摸事件和手势

---

## 设置设备指标

### 基础：覆盖设备 metrics

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
    """
    设置设备指标
    - width/height: 视口尺寸（CSS 像素）
    - device_scale_factor: DPR（如 iPhone 的 2 或 3）
    - mobile: 是否启用移动端视口
    """
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
    """清除设备指标覆盖，恢复桌面视图"""
    return await cdp(ws, session_id,
                     "Emulation.clearDeviceMetricsOverride")
```

### 预置设备配置

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
        "scale": 3, "mobile": True,
        "screen_width": 360, "screen_height": 780
    },
    "desktop_hd": {
        "width": 1920, "height": 1080,
        "scale": 1, "mobile": False
    }
}


async def emulate_device(ws, session_id, device_name):
    """模拟指定设备"""
    if device_name not in DEVICE_PRESETS:
        raise ValueError(f"未知设备: {device_name}")
    
    cfg = DEVICE_PRESETS[device_name]
    return await set_device_metrics(
        ws, session_id,
        width=cfg["width"],
        height=cfg["height"],
        device_scale_factor=cfg["scale"],
        mobile=cfg["mobile"],
        screen_width=cfg.get("screen_width"),
        screen_height=cfg.get("screen_height")
    )
```

### 设置用户代理

设备模拟通常需要配合 User-Agent 覆盖：

```python
async def set_user_agent(ws, session_id, ua, platform=None):
    """设置 User-Agent"""
    params = {"userAgent": ua}
    if platform:
        params["platform"] = platform
    return await cdp(ws, session_id,
                     "Emulation.setUserAgentOverride", params)


# iPhone 14 Pro 的 UA
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) "
             "Version/17.0 Mobile/15E148 Safari/604.1")

# Pixel 7 的 UA
PIXEL_UA = ("Mozilla/5.0 (Linux; Android 14; Pixel 7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.6099.144 Mobile Safari/537.36")


async def setup_mobile_device(ws, session_id, device_name):
    """完整设置移动设备模拟（metrics + UA）"""
    if device_name == "iphone_14_pro":
        await emulate_device(ws, session_id, "iphone_14_pro")
        await set_user_agent(ws, session_id, IPHONE_UA, "iPhone")
    elif device_name == "pixel_7":
        await emulate_device(ws, session_id, "pixel_7")
        await set_user_agent(ws, session_id, PIXEL_UA, "Android")
    else:
        await emulate_device(ws, session_id, device_name)
    
    print(f"已模拟设备: {device_name}")
```

---

## 模拟触摸事件

### 启用触摸模拟

```python
async def enable_touch(ws, session_id, enabled=True, max_touch_points=5):
    """启用或禁用触摸事件模拟"""
    return await cdp(ws, session_id,
                     "Emulation.setTouchEmulationEnabled", {
        "enabled": enabled,
        "maxTouchPoints": max_touch_points
    })


async def setup_touch_device(ws, session_id):
    """配置完整的触摸设备环境"""
    # 设置移动端视口（移动模式自动启用触摸）
    await set_device_metrics(ws, session_id, 390, 844, 3, mobile=True)
    # 确保触摸已启用
    await enable_touch(ws, session_id, enabled=True, max_touch_points=5)
    # 设置 UA
    await set_user_agent(ws, session_id, IPHONE_UA, "iPhone")
```

### 模拟触摸手势

CDP 的 `Input.dispatchTouchEvent` 可以模拟触摸事件：

```python
async def touch_tap(ws, session_id, x, y):
    """模拟触摸点击"""
    # 触摸开始
    await cdp(ws, session_id, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{
            "x": x, "y": y,
            "radiusX": 10, "radiusY": 10,
            "force": 1
        }]
    })
    await asyncio.sleep(0.05)
    # 触摸结束
    await cdp(ws, session_id, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": []
    })


async def touch_swipe(ws, session_id, start_x, start_y, end_x, end_y, steps=10):
    """模拟触摸滑动"""
    import math
    
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
            "type": event_type,
            "touchPoints": touch_points
        })
        await asyncio.sleep(0.01)


async def touch_pinch(ws, session_id, center_x, center_y, scale):
    """模拟双指缩放"""
    base_distance = 50
    target_distance = base_distance * scale
    
    # 两指开始
    for phase in ["touchStart", "touchMove", "touchEnd"]:
        distance = base_distance if phase == "touchStart" else target_distance
        if phase == "touchEnd":
            distance = target_distance
        
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

## 伪造地理位置

### 设置经纬度

```python
async def set_geolocation(ws, session_id, latitude, longitude, accuracy=100):
    """伪造地理位置"""
    return await cdp(ws, session_id,
                     "Emulation.setGeolocationOverride", {
        "latitude": latitude,
        "longitude": longitude,
        "accuracy": accuracy
    })


async def clear_geolocation(ws, session_id):
    """清除地理位置覆盖"""
    return await cdp(ws, session_id,
                     "Emulation.clearGeolocationOverride")


# 常用位置预设
LOCATIONS = {
    "beijing": {"lat": 39.9042, "lng": 116.4074},
    "shanghai": {"lat": 31.2304, "lng": 121.4737},
    "new_york": {"lat": 40.7128, "lng": -74.0060},
    "london": {"lat": 51.5074, "lng": -0.1278},
    "tokyo": {"lat": 35.6762, "lng": 139.6503},
}


async def test_location_based_features(ws, session_id, url):
    """测试基于位置的功能"""
    for city, coord in LOCATIONS.items():
        print(f"测试位置: {city}")
        await set_geolocation(ws, session_id, coord["lat"], coord["lng"])
        
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(3)
        
        # 截图保存
        screenshot = await cdp(ws, session_id, "Page.captureScreenshot", {
            "format": "jpeg"
        })
        print(f"  {city} 截图完成")
    
    await clear_geolocation(ws, session_id)
```

### 设置权限（允许位置访问）

伪造位置后，还需要授予页面定位权限：

```python
async def grant_geolocation_permission(ws, session_id):
    """授予页面定位权限"""
    # 通过 Browser.setPermission 授予
    await cdp(ws, session_id, "Browser.setPermission", {
        "permission": {"name": "geolocation"},
        "setting": "granted"
    })
```

---

## 模拟设备方向

```python
async def set_device_orientation(ws, session_id, alpha, beta, gamma):
    """
    设置设备方向
    - alpha: 绕 Z 轴旋转（指南针方向，0-360）
    - beta: 绕 X 轴旋转（前后倾斜，-180 到 180）
    - gamma: 绕 Y 轴旋转（左右倾斜，-90 到 90）
    """
    return await cdp(ws, session_id,
                     "Emulation.setDeviceOrientationOverride", {
        "alpha": alpha,
        "beta": beta,
        "gamma": gamma
    })


async def clear_device_orientation(ws, session_id):
    """清除方向覆盖"""
    return await cdp(ws, session_id,
                     "Emulation.clearDeviceOrientationOverride")


# 常用方向
ORIENTATIONS = {
    "portrait": {"alpha": 0, "beta": 0, "gamma": 0},
    "landscape_left": {"alpha": 0, "beta": 0, "gamma": 90},
    "landscape_right": {"alpha": 0, "beta": 0, "gamma": -90},
    "tilt_forward": {"alpha": 0, "beta": 45, "gamma": 0},
    "tilt_backward": {"alpha": 0, "beta": -45, "gamma": 0},
}


async def test_orientations(ws, session_id, url):
    """测试页面在不同方向下的表现"""
    for name, orient in ORIENTATIONS.items():
        print(f"方向: {name}")
        await set_device_orientation(
            ws, session_id, **orient
        )
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(2)
        # 截图
        await cdp(ws, session_id, "Page.captureScreenshot", {
            "format": "jpeg"
        })
    
    await clear_device_orientation(ws, session_id)
```

---

## 实战：自动化移动端兼容性测试

综合运用以上所有技术，实现一个自动化移动端兼容性测试脚本：

```python
async def mobile_compatibility_test(ws, session_id, url):
    """自动化移动端兼容性测试"""
    results = {}
    
    devices_to_test = ["iphone_14_pro", "pixel_7", "ipad_pro_12.9"]
    
    for device in devices_to_test:
        print(f"\n{'='*50}")
        print(f"测试设备: {device}")
        print(f"{'='*50}")
        
        # 1. 模拟设备
        await setup_mobile_device(ws, session_id, device)
        
        # 2. 如果是指定设备，设置地理和方向
        if device == "iphone_14_pro":
            await set_geolocation(ws, session_id, 39.9042, 116.4074)
            await grant_geolocation_permission(ws, session_id)
        
        # 3. 收集性能指标
        await cdp(ws, session_id, "Performance.enable")
        
        # 4. 导航
        start = asyncio.get_event_loop().time()
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        
        # 5. 等待渲染完成
        await asyncio.sleep(3)
        await cdp(ws, session_id, "Page.loadEventFired")
        load_time = asyncio.get_event_loop().time() - start
        
        # 6. 截图
        screenshot = await cdp(ws, session_id, "Page.captureScreenshot", {
            "format": "jpeg"
        })
        
        # 7. 获取指标
        perf = await cdp(ws, session_id, "Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in perf.get("metrics", [])}
        
        results[device] = {
            "load_time": round(load_time, 2),
            "metrics": metrics,
            "screenshot": screenshot.get("data", "")[:50] + "..."
        }
        
        print(f"  加载时间: {load_time:.2f}s")
        
        # 8. 清理
        await clear_geolocation(ws, session_id)
    
    # 恢复桌面视图
    await clear_device_metrics(ws, session_id)
    await cdp(ws, session_id, "Emulation.setUserAgentOverride", {
        "userAgent": ""
    })
    
    # 输出对比
    print(f"\n{'='*50}")
    print("兼容性测试结果对比")
    print(f"{'='*50}")
    for device, data in results.items():
        print(f"{device:20s}: {data['load_time']:>5.2f}s 加载")
    
    return results
```

---

## 常见踩坑与最佳实践

### 踩坑 1：设置顺序很重要

必须先设置设备指标，再导航到页面：

```python
# ❌ 错误：导航后再设设备指标
await cdp(ws, session_id, "Page.navigate", {"url": url})
await set_device_metrics(ws, session_id, 390, 844, 3)  # 已加载的页面不会重排

# ✅ 正确：先设设备指标，再导航
await set_device_metrics(ws, session_id, 390, 844, 3)
await cdp(ws, session_id, "Page.navigate", {"url": url})
```

### 踩坑 2：触摸和鼠标事件的关系

启用触摸模拟后，部分鼠标事件可能不会触发：

```python
# 做了触摸模拟后
await enable_touch(ws, session_id, enabled=True)

# 某些页面依赖的 mouseenter/mouseleave 可能不触发
# 可以通过 Input.dispatchMouseEvent 手动补发
await cdp(ws, session_id, "Input.dispatchMouseEvent", {
    "type": "mousePressed",
    "x": 100, "y": 200,
    "button": "left",
    "clickCount": 1
})
```

### 踩坑 3：地理位置需要 HTTPS

大多数浏览器只允许 HTTPS 页面访问地理位置 API：

```python
# ❌ HTTP 页面无法获取位置
await set_geolocation(ws, session_id, 39.9, 116.4)
# 但页面 navigator.geolocation.getCurrentPosition() 可能仍会失败

# ✅ 确保在 HTTPS 页面上测试
await cdp(ws, session_id, "Page.navigate", {
    "url": "https://example.com/map"
})
```

### 踩坑 4：`Emulation.setUserAgentOverride` 影响所有后续请求

```python
# 设置 UA 后，所有后续请求（包括子资源）都会使用覆盖的 UA
await set_user_agent(ws, session_id, IPHONE_UA)

# 要在新页面生效，需要在导航前设置
# 要清除，传空字符串
await cdp(ws, session_id, "Emulation.setUserAgentOverride", {
    "userAgent": ""
})
```

### 踩坑 5：screenWidth/screenHeight 与实际尺寸

`Emulation.setDeviceMetricsOverride` 的 `width/height` 是视口尺寸，`screenWidth/screenHeight` 是屏幕物理尺寸。两者可以不同：

```python
# 模拟 iPhone 14 Pro
await set_device_metrics(ws, session_id,
    width=390, height=844,     # 逻辑视口
    device_scale_factor=3,
    screen_width=1170,         # 物理分辨率 390*3=1170
    screen_height=2532,        # 物理分辨率 844*3=2532
    mobile=True
)
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 设置顺序 | **先设设备指标，再导航** |
| 触摸事件 | 启用触摸后某些鼠标事件可能不触发 |
| 地理位置 | 确保测试页面使用 HTTPS |
| UA 覆盖 | 设置后影响所有请求，导航前设好 |
| 视口 vs 物理尺寸 | 理解 width/height 和 screenWidth/screenHeight 的区别 |
| 清理 | 测试完调用 `clearDeviceMetricsOverride` 恢复 |

---

## 完整参考：CDP 移动端模拟类

```python
import asyncio
import json
import websockets


class CDPMobileEmulator:
    """CDP 移动设备模拟器"""
    
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

**使用示例：**

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

> **总结**：CDP 的 Emulation 域提供了完整的移动设备模拟能力——从分辨率、DPR、触摸事件到地理位置和方向传感器。这让 CI/CD 中的移动端自动化测试变得简单可靠，无需维护真实的设备农场。

---

*上一篇回顾：CDP 网络条件模拟指南：用 Python 控制带宽、延迟与离线状态。*

*下一篇预告：CDP 截图与 PDF 导出指南：用 Python 生成精确页面快照。*