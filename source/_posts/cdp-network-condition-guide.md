---
title: CDP 网络条件模拟指南：用 Python 控制带宽、延迟与离线状态
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 网络模拟
  - 浏览器自动化
  - 性能测试
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）模拟各种网络条件。涵盖限速模拟（2G/3G/4G/WiFi）、网络延迟注入、离线模式测试、以及自定义网络配置文件，帮助你测试应用在不同网络环境下的表现。
---

> **一句话总结**：CDP 的 `Network.emulateNetworkConditions` 让你可以精确控制浏览器的网络行为——模拟从离线到高速 WiFi 的全部场景，无需任何外部工具。

---

## 目录

1. [为什么用 CDP 模拟网络条件](#为什么用-cdp-模拟网络条件)
2. [基础用法：Network.emulateNetworkConditions](#基础用法networkemulatenetworkconditions)
3. [预置网络配置文件](#预置网络配置文件)
4. [高级：自定义网络条件](#高级自定义网络条件)
5. [离线模式测试](#离线模式测试)
6. [实战：网络切换对 SPA 的影响测试](#实战网络切换对-spa-的影响测试)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 模拟网络条件

前端性能测试中，模拟不同网络环境是必备技能。传统做法需要借助 Fiddler、Charles 等代理工具，配置繁琐。CDP 内置的网络模拟功能无需任何外部依赖：

| 功能 | Charles/Fiddler | CDP `Network.emulateNetworkConditions` |
|------|----------------|--------------------------------------|
| 带宽限制 | ✅ 需配置代理 | ✅ 原生支持 |
| 延迟注入 | ✅ 需配置 | ✅ 原生支持 |
| 丢包模拟 | ✅ 支持 | ❌ 不支持（需额外工具） |
| 离线测试 | ✅ 需断网 | ✅ 浏览器级离线 |
| HTTPS 拦截 | ⚠️ 需装证书 | ✅ 原生支持无需证书 |
| 动态切换 | ❌ 需重启代理 | ✅ 命令级即时切换 |

**适合场景**：
- 测试页面在弱网下的加载表现
- 验证应用的离线降级策略
- 模拟 API 请求超时场景
- 竞品性能分析（模拟对方用户网络）

---

## 基础用法：Network.emulateNetworkConditions

### 连接 Chrome 并发送命令

```python
import asyncio
import websockets
import json

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."
CMD_ID = [0]  # 用列表实现可变闭包

async def cdp(ws, session_id, method, params=None):
    """发送 CDP 命令"""
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
    """连接页面"""
    targets = await cdp(ws, None, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, None, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

### 设置网络条件

`Network.emulateNetworkConditions` 接受以下参数：

```python
async def set_network_conditions(ws, session_id, offline=False,
                                  latency=0, download_throughput=-1,
                                  upload_throughput=-1,
                                  connection_type="none"):
    """
    设置网络条件
    - offline: 是否模拟离线
    - latency: 延迟（毫秒）
    - download_throughput: 下载带宽（bps），-1 表示不限速
    - upload_throughput: 上传带宽（bps），-1 表示不限速
    - connection_type: 连接类型（none/wifi/cellular/ethernet/other）
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
    """恢复为正常网络"""
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

## 预置网络配置文件

将常见的网络条件封装为预设配置：

```python
# 预置网络配置（带宽单位：bps）
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
    """应用预置网络配置"""
    if preset_name not in NETWORK_PRESETS:
        raise ValueError(f"未知网络配置: {preset_name}，可选：{list(NETWORK_PRESETS.keys())}")
    
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

## 高级：自定义网络条件

### 模拟 API 超时

通过"极低带宽 + 高延迟"组合来模拟超时：

```python
async def simulate_api_timeout(ws, session_id):
    """模拟 API 请求超时场景"""
    await set_network_conditions(
        ws, session_id,
        offline=False,
        latency=10000,          # 10 秒延迟
        download_throughput=100, # 100 bps（几乎无速度）
        upload_throughput=100,
        connection_type="cellular"
    )


async def test_timeout_behavior(ws, session_id):
    """测试页面在超时下的表现"""
    # 设置超时网络
    await simulate_api_timeout(ws, session_id)
    
    # 导航到目标页面
    await cdp(ws, session_id, "Page.navigate", {
        "url": "https://example.com/dashboard"
    })
    
    # 等待几秒，观察页面降级行为
    await asyncio.sleep(5)
    
    # 截图保存
    result = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "jpeg", "quality": 80
    })
    
    # 恢复正常网络
    await disable_network_emulation(ws, session_id)
    
    return result.get("data")
```

### 按请求类型区分限速

更精细的策略：只限制 API 请求，不限制静态资源：

```python
async def throttle_api_only(ws, session_id):
    """只对 API 请求限速，静态资源正常加载"""
    # 通过 Fetch 域拦截 API 请求并延迟响应
    await cdp(ws, session_id, "Fetch.enable", {
        "patterns": [{
            "urlPattern": "*/api/*",
            "requestStage": "Response"
        }]
    })
    
    async def handle_api_delay(ws, session_id, delay_ms=3000):
        """延迟 API 响应"""
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                if data.get("method") == "Fetch.requestPaused":
                    req_id = data["params"]["requestId"]
                    # 延迟后继续
                    await asyncio.sleep(delay_ms / 1000)
                    await cdp(ws, session_id, "Fetch.continueRequest", {
                        "requestId": req_id
                    })
            except asyncio.TimeoutError:
                break
```

### 模拟网络抖动

在正常网络和弱网之间切换，模拟真实世界中不稳定的连接：

```python
async def simulate_jitter(ws, session_id, interval=3):
    """模拟网络抖动：每隔 interval 秒在正常和弱网间切换"""
    import random
    
    for i in range(5):  # 抖动 5 次
        print(f"[抖动 {i+1}] 切换为弱网...")
        await set_network_conditions(
            ws, session_id,
            latency=random.randint(500, 2000),
            download_throughput=random.randint(50 * 1024, 500 * 1024),
            upload_throughput=random.randint(20 * 1024, 100 * 1024),
            connection_type="cellular"
        )
        await asyncio.sleep(interval)
        
        print(f"[抖动 {i+1}] 恢复为正常网络...")
        await disable_network_emulation(ws, session_id)
        await asyncio.sleep(interval)
```

---

## 离线模式测试

### 模拟离线并验证降级

```python
async def test_offline_mode(ws, session_id, url):
    """测试页面的离线降级行为"""
    # 1. 先在线加载页面（缓存资源）
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    # 2. 切到离线
    print("切到离线模式...")
    await set_network_conditions(
        ws, session_id, offline=True
    )
    
    # 3. 尝试导航（应该触发离线页面或错误页）
    result = await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(2)
    
    # 4. 截图检查离线表现
    screenshot = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "jpeg"
    })
    
    # 5. 恢复在线
    await disable_network_emulation(ws, session_id)
    
    print("离线测试完成")
    return screenshot.get("data")
```

### 监听网络状态变化

当网络条件改变时，浏览器会触发 `Network.willSendRequest` 和 `Network.loadingFailed` 等事件。结合离线模拟可以验证：

```python
async def monitor_offline_requests(ws, session_id):
    """监听离线模式下的请求失败情况"""
    # 启用网络事件
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
                    print(f"[网络事件] {method}")
            except asyncio.TimeoutError:
                break
    
    # 先启用网络域
    await cdp(ws, session_id, "Network.enable")
    
    # 模拟离线
    await set_network_conditions(ws, session_id, offline=True)
    
    # 收集一段时间的事件
    collector = asyncio.create_task(collect_events())
    await asyncio.sleep(5)
    collector.cancel()
    
    return net_events
```

---

## 实战：网络切换对 SPA 的影响测试

综合运用以上技术，测试单页应用在不同网络下的行为：

```python
async def test_spa_network_impact(ws, session_id, url, actions_callback):
    """
    测试 SPA 在不同网络下的表现
    actions_callback: 在每种网络下执行的操作（如点击、滚动）
    """
    results = {}
    
    # 要测试的网络场景
    scenarios = ["4g", "3g", "2g", "slow_wifi"]
    
    for scenario in scenarios:
        print(f"\n=== 测试网络: {scenario} ===")
        
        # 应用网络条件
        await apply_network_preset(ws, session_id, scenario)
        
        # 开始性能指标收集
        await cdp(ws, session_id, "Performance.enable")
        await cdp(ws, session_id, "Network.enable")
        
        # 记录页面加载时间
        start_time = asyncio.get_event_loop().time()
        
        # 导航到页面
        await cdp(ws, session_id, "Page.navigate", {"url": url})
        await asyncio.sleep(1)
        
        # 等待页面加载完成
        await cdp(ws, session_id, "Page.loadEventFired")
        
        load_time = asyncio.get_event_loop().time() - start_time
        print(f"页面加载时间: {load_time:.2f}s")
        
        # 执行操作（如点击导航等）
        if actions_callback:
            await actions_callback(ws, session_id)
        
        # 获取性能指标
        perf_metrics = await cdp(ws, session_id, "Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in perf_metrics.get("metrics", [])}
        
        results[scenario] = {
            "load_time": load_time,
            "metrics": metrics
        }
    
    # 恢复网络
    await disable_network_emulation(ws, session_id)
    
    # 输出对比
    print("\n=== 网络场景对比 ===")
    for scenario, data in results.items():
        print(f"{scenario}: 加载时间 {data['load_time']:.2f}s, "
              f"JS 堆 {data['metrics'].get('JSHeapUsedSize', 0) / 1024 / 1024:.1f}MB")
    
    return results
```

---

## 常见踩坑与最佳实践

### 踩坑 1：带宽单位是 bps 不是 KB/s

`downloadThroughput` 和 `uploadThroughput` 的单位是 **bits per second**（bps），不是字节/秒：

```python
# ❌ 错误：以为是 KB/s
params = {"downloadThroughput": 750}  # 实际只有 750 bps，约 93 字节/秒

# ✅ 正确：手动换算
params = {"downloadThroughput": 750 * 1024}  # 750 Kbps = 768000 bps
```

常见换算速查：

| 目标速度 | bps 值 |
|---------|--------|
| 56 Kbps (拨号) | `56 * 1024` |
| 256 Kbps | `256 * 1024` |
| 1 Mbps | `1 * 1024 * 1024` |
| 10 Mbps | `10 * 1024 * 1024` |

### 踩坑 2：模拟离线不影响已缓存的请求

即使设置了 `offline: True`，浏览器仍然可能从 HTTP 缓存中响应已缓存资源：

```python
# 设置离线前先禁用缓存（可选）
await cdp(ws, session_id, "Network.setCacheDisabled", {"cacheDisabled": True})
```

### 踩坑 3：网络设置是浏览器级，不是标签页级

`Network.emulateNetworkConditions` 影响的是整个浏览器实例，所有标签页共享同一网络条件：

```python
# ❌ 不能只让标签页 A 限速而标签页 B 正常
# 一个浏览器只有一个网络栈

# ✅ 可以通过切换到不同浏览器实例来实现隔离
# 或者用不同 --user-data-dir 启动多个浏览器
```

### 踩坑 4：connection_type 只是标签，不影响实际带宽

`connectionType` 参数只是标识性的，不改变带宽行为。实际限速取决于 `downloadThroughput` 和 `uploadThroughput`：

```python
# ❌ 以为设了 cellular 就自动限速
params = {"connectionType": "cellular", "downloadThroughput": -1}
# 实际上 -1 表示不限速，即使 connectionType=cellular 也不限速

# ✅ 需要明确设带宽值
params = {"connectionType": "cellular", "downloadThroughput": 750 * 1024}
```

### 踩坑 5：关闭模拟后需等几秒恢复

禁用网络模拟后，带宽不会立刻恢复，建议加一小段延时：

```python
# 关闭模拟
await disable_network_emulation(ws, session_id)
await asyncio.sleep(1)  # 等待网络栈恢复
# 然后继续操作
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 带宽单位 | 使用 bps（位/秒），不是字节/秒 |
| 离线测试 | 离线不影响已缓存文件，可配合 `setCacheDisabled` |
| 生效范围 | 浏览器级，所有标签页共享 |
| connectionType | 仅标识，不限制带宽 |
| 恢复延时 | 关闭模拟后等 1-2 秒再操作 |
| 预置配置 | 封装常用场景避免硬编码 |

---

## 完整参考：CDP 网络模拟类

```python
import asyncio
import json
import websockets


class CDPNetworkCondition:
    """CDP 网络条件控制器"""
    
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

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    net = CDPNetworkCondition(ws, session_id)
    
    print("可用预置:", net.list_presets())
    
    # 模拟 3G 网络
    await net.apply("3g")
    
    # 测试页面加载
    await cdp(ws, session_id, "Page.navigate", {
        "url": "https://example.com"
    })
    await asyncio.sleep(5)
    
    # 恢复网络
    await net.reset()
```

---

> **总结**：CDP 的网络条件模拟可以精确控制浏览器的带宽、延迟和在线/离线状态。结合性能指标采集和截图功能，你可以自动化测试应用在各种网络环境下的表现，发现弱网下的 UI 异常和性能瓶颈。

---

*上一篇回顾：CDP DOM 操作完全指南：用 Python 实时监听与操纵页面元素。*

*下一篇预告：CDP 移动设备模拟指南：用 Python 调试移动端页面。*