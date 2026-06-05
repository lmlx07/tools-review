---
title: CDP Service Worker 管理：用 Python 调试离线缓存
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Service Worker
  - PWA
  - 离线缓存
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）管理 Service Worker。涵盖注册/注销事件监听、生命周期状态追踪、推送通知模拟、CacheStorage 缓存操作以及离线调试技巧。
---

> **一句话总结**：CDP 的 `ServiceWorker` 域让你能完全控制浏览器的 Service Worker 生命周期——注册、调试、推送通知、操作缓存、强制更新和注销，是 PWA 离线调试的利器。

---

## 目录

1. [Service Worker 与 CDP](#service-worker-与-cdp)
2. [基础：监听 Service Worker 事件](#基础监听-service-worker-事件)
3. [生命周期追踪：installing → activated → redundant](#生命周期追踪installing--activated--redundant)
4. [推送通知](#推送通知)
5. [CacheStorage 缓存操作](#cachestorage-缓存操作)
6. [实战：离线缓存状态监控](#实战离线缓存状态监控)
7. [Service Worker 强制更新与跳过等待](#service-worker-强制更新与跳过等待)
8. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## Service Worker 与 CDP

### 为什么用 CDP 管理 Service Worker

Service Worker 在浏览器沙箱中运行，开发者工具虽然提供了 Application 面板的可视化界面，但无法做到自动化。CDP 的 `ServiceWorker` 域提供了编程式控制能力：

| 操作 | Application 面板 | CDP |
|------|-------------------|-----|
| 监听注册/注销事件 | ❌ 需手动刷新 | ✅ `ServiceWorker.onWorkerRegistrationUpdated` |
| 追踪生命周期 | ❌ 仅显示当前状态 | ✅ `ServiceWorker.onWorkerVersionUpdated` |
| 推送通知 | ❌ 无法触发 | ✅ `ServiceWorker.dispatchSyncEvent` |
| CacheStorage 操作 | ✅ 可手动浏览 | ✅ `CacheStorage.*` 全 API |
| 跳过等待 | ❌ 需点击按钮 | ✅ `ServiceWorker.skipWaiting` |
| 批量管理 | ❌ 手动操作 | ✅ 完全自动化 |

### CDP 中的 ServiceWorker 域

关键方法：
- `ServiceWorker.enable` — 启用 SW 事件监听
- `ServiceWorker.disable` — 禁用监听
- `ServiceWorker.skipWaiting` — 跳过等待阶段
- `ServiceWorker.unregister` — 注销 Service Worker
- `ServiceWorker.dispatchSyncEvent` — 触发后台同步事件
- `ServiceWorker.dispatchPeriodicSyncEvent` — 触发定期同步事件
- `ServiceWorker.inspectWorker` — 打开 Worker 调试面板

关键事件：
- `ServiceWorker.onWorkerRegistrationUpdated` — 注册信息变更
- `ServiceWorker.onWorkerVersionUpdated` — Worker 版本状态变更
- `ServiceWorker.onWorkerErrorReported` — Worker 错误报告

---

## 基础：监听 Service Worker 事件

### 启动监听

```python
import asyncio
import websockets
import json

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
    """附加到第一个可用的页面目标"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets["targetInfos"]:
        if target["type"] == "page":
            session = await cdp(ws, "Target.attachToTarget", {
                "targetId": target["targetId"], "flatten": True
            })
            return session["sessionId"], target["targetId"]
    raise Exception("未找到页面目标")


async def enable_service_worker(ws):
    """启用 Service Worker 监听（浏览器级别，无需 sessionId）"""
    result = await cdp(ws, "ServiceWorker.enable")
    print("Service Worker 监听已启用")
    return result


async def monitor_sw_events(ws, duration=30):
    """持续监听 Service Worker 事件"""
    await enable_service_worker(ws)
    print(f"开始监听 Service Worker 事件（{duration}秒）...")
    
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < duration:
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
            data = json.loads(resp)
            method = data.get("method", "")
            
            if method == "ServiceWorker.onWorkerRegistrationUpdated":
                registrations = data["params"]["registrations"]
                for reg in registrations:
                    print(f"[注册更新] ID: {reg['registrationId']}")
                    print(f"  作用域: {reg.get('scopeURL', 'N/A')}")
                    print(f"  是否注册: {reg.get('isRegistered', False)}")
            
            elif method == "ServiceWorker.onWorkerVersionUpdated":
                versions = data["params"]["versions"]
                for ver in versions:
                    print(f"[版本更新] ID: {ver['versionId']}")
                    print(f"  状态: {ver.get('status', 'unknown')}")
                    print(f"  脚本: {ver.get('scriptURL', 'N/A')}")
                    running = ver.get("runningStatus", "unknown")
                    print(f"  运行状态: {running}")
            
            elif method == "ServiceWorker.onWorkerErrorReported":
                err = data["params"]["errorMessage"]
                print(f"[Worker 错误] {err.get('errorMessage', '')}")
                print(f"  行号: {err.get('lineNumber', 0)}, 列号: {err.get('columnNumber', 0)}")
        
        except asyncio.TimeoutError:
            pass


# 使用示例
async def example_monitor():
    async with websockets.connect(CDP_URL) as ws:
        await enable_service_worker(ws)
        await monitor_sw_events(ws, duration=20)
```

### Browser Scope vs Page Scope

注意 `ServiceWorker.enable` 是**浏览器级别**的方法，直接对整个浏览器调用，不需要 `sessionId`：

```python
# ✅ 正确：无需 sessionId
await cdp(ws, "ServiceWorker.enable")

# 导航到一个使用 Service Worker 的页面
session_id, _ = await connect_page(ws)
await cdp(ws, "Page.navigate", {"url": "https://example-pwa.com"}, session_id)
await asyncio.sleep(3)
```

---

## 生命周期追踪：installing → activated → redundant

### 理解 Service Worker 生命周期

Service Worker 的状态变化通过 `ServiceWorker.onWorkerVersionUpdated` 事件暴露：

| 状态 | 含义 | 触发时机 |
|------|------|---------|
| `installing` | 正在安装 | 浏览器下载并执行 install 事件 |
| `installed` | 安装完成，等待激活 | install 事件成功完成 |
| `activating` | 正在激活 | activate 事件开始执行 |
| `activated` | 已激活，可控制页面 | activate 事件完成 |
| `redundant` | 已废弃 | 新版本替换或手动注销 |

### 追踪生命周期状态

```python
class SWLifecycleTracker:
    """Service Worker 生命周期追踪器"""
    
    def __init__(self):
        self.versions = {}       # versionId → 版本信息
        self.registrations = {}  # registrationId → 注册信息
        self.state_history = []  # 状态变更历史
    
    async def start(self, ws, duration=60):
        await enable_service_worker(ws)
        print("开始追踪 Service Worker 生命周期...\n")
        
        start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - start < duration:
            try:
                resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
                data = json.loads(resp)
                method = data.get("method", "")
                
                if method == "ServiceWorker.onWorkerVersionUpdated":
                    for ver in data["params"]["versions"]:
                        vid = ver["versionId"]
                        old_status = self.versions.get(vid, {}).get("status", "none")
                        new_status = ver.get("status", "unknown")
                        
                        if old_status != new_status:
                            event = {
                                "time": asyncio.get_event_loop().time(),
                                "version_id": vid,
                                "from": old_status,
                                "to": new_status,
                                "script": ver.get("scriptURL", "")
                            }
                            self.state_history.append(event)
                            print(f"[状态变更] {vid}: {old_status} → {new_status}")
                            print(f"  脚本: {event['script']}")
                        
                        self.versions[vid] = ver
                
                elif method == "ServiceWorker.onWorkerRegistrationUpdated":
                    for reg in data["params"]["registrations"]:
                        rid = reg["registrationId"]
                        self.registrations[rid] = reg
                        is_reg = reg.get("isRegistered", False)
                        print(f"[注册] {rid} → {'已注册' if is_reg else '已注销'}")
                        print(f"  作用域: {reg.get('scopeURL', 'N/A')}")
            
            except asyncio.TimeoutError:
                pass
        
        return self._report()
    
    def _report(self):
        """生成生命周期报告"""
        print("\n===== 生命周期追踪报告 =====")
        print(f"追踪到的版本数: {len(self.versions)}")
        print(f"追踪到的注册数: {len(self.registrations)}")
        print(f"状态变更次数: {len(self.state_history)}")
        
        for event in self.state_history:
            print(f"  [{event['from']} → {event['to']}] {event['version_id']}")
        
        active = [v for v in self.versions.values()
                  if v.get("status") == "activated"]
        print(f"\n当前活跃 Worker: {len(active)} 个")
        for v in active:
            print(f"  - {v['versionId']}: {v.get('scriptURL', 'N/A')}")
        
        return {
            "versions": self.versions,
            "registrations": self.registrations,
            "state_history": self.state_history
        }


# 使用示例
async def track_lifecycle():
    async with websockets.connect(CDP_URL) as ws:
        tracker = SWLifecycleTracker()
        await tracker.start(ws, duration=30)
```

---

## 推送通知

### 模拟推送事件

虽然 CDP 不直接提供 `ServiceWorker.dispatchPushEvent`，但可以通过组合命令模拟推送通知的调试流程：

```python
async def simulate_push_event(ws, session_id, payload="Test Push"):
    """
    模拟推送通知（通过 Runtime.evaluate 触发 Service Worker 中的 push 事件）
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            navigator.serviceWorker.ready.then(reg => {{
                reg.active.postMessage({{
                    type: 'SIMULATE_PUSH',
                    payload: '{payload}'
                }});
            }});
        """,
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)  # Note: session_id is passed both as param and kwarg
    
    # 或者直接在 SW 内部模拟
    await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            // 在页面上下文中模拟推送
            const mockPush = new PushEvent('push', {{
                data: new Blob(['{payload}'], {{type: 'text/plain'}})
            }});
            // 需要在 Service Worker 上下文中执行
            console.log('Push event simulated:', mockPush);
        """,
        "sessionId": session_id
    }, session_id)
    
    print(f"推送事件已模拟: {payload}")


async def inspect_service_worker(ws, version_id):
    """打开 Service Worker 的调试会话"""
    result = await cdp(ws, "ServiceWorker.inspectWorker", {
        "versionId": version_id
    })
    print(f"Worker 调试 URL: {result.get('url', 'N/A')}")
    return result
```

### 后台同步事件

```python
async def dispatch_sync_event(ws, tag="sync-data"):
    """
    触发 Service Worker 的后台同步事件
    """
    result = await cdp(ws, "ServiceWorker.dispatchSyncEvent", {
        "tag": tag,
        "lastChance": False
    })
    print(f"后台同步事件已触发: tag={tag}")
    return result


async def dispatch_periodic_sync_event(ws, tag="periodic-update"):
    """
    触发定期后台同步事件
    """
    result = await cdp(ws, "ServiceWorker.dispatchPeriodicSyncEvent", {
        "tag": tag
    })
    print(f"定期同步事件已触发: tag={tag}")
    return result
```

---

## CacheStorage 缓存操作

### 通过 CDP 操作 CacheStorage

`CacheStorage` 域属于页面级别操作，需要 `sessionId`：

```python
async def cache_storage_request(ws, session_id, method, params=None):
    """
    发送 CacheStorage 请求（需要 sessionId）
    """
    return await cdp(ws, method, params, session_id)


async def list_caches(ws, session_id, origin=None):
    """
    列出指定 origin 下的所有缓存
    若不指定 origin，使用当前页面 origin
    """
    result = await cache_storage_request(ws, session_id, "CacheStorage.requestCacheNames", {
        "securityOrigin": origin or ""
    })
    caches = result.get("caches", [])
    print(f"找到 {len(caches)} 个缓存:")
    for c in caches:
        print(f"  - {c['cacheName']} (ID: {c['cacheId']})")
    return caches


async def read_cache_entries(ws, session_id, cache_id, skip_count=0, page_size=50):
    """
    读取缓存中的条目
    """
    result = await cache_storage_request(ws, session_id, "CacheStorage.requestEntries", {
        "cacheId": cache_id,
        "skipCount": skip_count,
        "pageSize": page_size
    })
    entries = result.get("cacheDataEntries", [])
    print(f"缓存条目: {len(entries)} 个")
    for entry in entries[:10]:  # 只显示前 10 个
        print(f"  URL: {entry.get('requestURL', 'N/A')}")
        print(f"  请求方法: {entry.get('requestMethod', 'GET')}")
        print(f"  响应状态: {entry.get('responseStatus', 0)}")
        headers = entry.get("responseHeaders", [])
        print(f"  响应头: {len(headers)} 个")
        print()
    return entries


async def delete_cache_entry(ws, session_id, cache_id, request_url):
    """
    删除缓存中的特定条目
    """
    result = await cache_storage_request(ws, session_id, "CacheStorage.deleteEntry", {
        "cacheId": cache_id,
        "request": request_url
    })
    print(f"已删除缓存条目: {request_url}")
    return result


async def delete_cache(ws, session_id, cache_name):
    """
    删除整个缓存
    """
    result = await cache_storage_request(ws, session_id, "CacheStorage.deleteCache", {
        "cacheName": cache_name
    })
    print(f"已删除缓存: {cache_name}")
    return result
```

### 缓存操作完整示例

```python
async def cache_inspection_demo(ws, session_id):
    """缓存检查完整演示"""
    # 1. 导航到 PWA 页面
    await cdp(ws, "Page.navigate", {
        "url": "https://your-pwa-site.com"
    }, session_id)
    await asyncio.sleep(5)  # 等待 SW 和缓存就绪
    
    # 2. 列出所有缓存
    caches = await list_caches(ws, session_id)
    if not caches:
        print("未找到缓存")
        return
    
    # 3. 检查每个缓存的内容
    total_entries = 0
    total_size = 0
    
    for cache in caches:
        print(f"\n--- 缓存: {cache['cacheName']} ---")
        entries = await read_cache_entries(ws, session_id, cache["cacheId"])
        total_entries += len(entries)
        
        for entry in entries:
            headers = {h["name"]: h["value"] for h in entry.get("responseHeaders", [])}
            content_length = int(headers.get("content-length", 0))
            total_size += content_length
    
    print(f"\n===== 缓存摘要 =====")
    print(f"缓存数: {len(caches)}")
    print(f"总条目数: {total_entries}")
    print(f"总大小: {total_size / 1024:.1f} KB")
```

---

## 实战：离线缓存状态监控

综合运用 Service Worker 和 CacheStorage API，构建离线缓存健康监控系统：

```python
class OfflineCacheMonitor:
    """离线缓存状态监控器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.sw_versions = {}
        self.caches = {}
    
    async def enable(self):
        """启用所有监听"""
        await cdp(self.ws, "ServiceWorker.enable")
        print("Service Worker 监控已启用")
    
    async def take_snapshot(self):
        """采集当前缓存快照"""
        snapshot = {
            "sw_status": await self._get_sw_status(),
            "cache_status": await self._get_cache_status(),
            "offline_readiness": await self._check_offline_readiness(),
            "timestamp": asyncio.get_event_loop().time()
        }
        return snapshot
    
    async def _get_sw_status(self):
        """获取 Service Worker 状态"""
        await cdp(self.ws, "ServiceWorker.enable")
        
        # 通过页面获取 SW 注册信息
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": """
                navigator.serviceWorker.getRegistration().then(reg => {
                    if (!reg) return JSON.stringify({registered: false});
                    return JSON.stringify({
                        registered: true,
                        scope: reg.scope,
                        active: reg.active ? reg.active.state : null,
                        waiting: reg.waiting ? reg.waiting.state : null,
                        installing: reg.installing ? reg.installing.state : null
                    });
                })
            """,
            "sessionId": self.session_id,
            "awaitPromise": True,
            "returnByValue": True
        }, self.session_id)
        
        import json as pyjson
        return pyjson.loads(result["result"]["value"])
    
    async def _get_cache_status(self):
        """获取缓存状态"""
        caches_result = await cdp(self.ws, "CacheStorage.requestCacheNames", {
            "securityOrigin": ""
        }, self.session_id)
        
        cache_list = caches_result.get("caches", [])
        cache_details = []
        
        for cache in cache_list:
            entries = await cdp(self.ws, "CacheStorage.requestEntries", {
                "cacheId": cache["cacheId"],
                "skipCount": 0,
                "pageSize": 1000
            }, self.session_id)
            
            entry_list = entries.get("cacheDataEntries", [])
            total_size = 0
            urls = []
            
            for entry in entry_list:
                urls.append(entry.get("requestURL", ""))
                headers = {h["name"]: h["value"]
                          for h in entry.get("responseHeaders", [])}
                total_size += int(headers.get("content-length", 0))
            
            cache_details.append({
                "name": cache["cacheName"],
                "entry_count": len(entry_list),
                "total_size_bytes": total_size,
                "urls": urls[:20]  # 仅前 20 个
            })
        
        return cache_details
    
    async def _check_offline_readiness(self):
        """检查离线就绪程度"""
        check = await cdp(self.ws, "Runtime.evaluate", {
            "expression": """
                (async () => {
                    const results = {
                        hasSW: false,
                        swState: null,
                        cacheNames: [],
                        cachesReady: false
                    };
                    
                    if ('serviceWorker' in navigator) {
                        const reg = await navigator.serviceWorker.getRegistration();
                        if (reg) {
                            results.hasSW = true;
                            results.swState = reg.active ? reg.active.state : 'none';
                        }
                    }
                    
                    if ('caches' in window) {
                        const keys = await caches.keys();
                        results.cacheNames = keys;
                        results.cachesReady = keys.length > 0;
                    }
                    
                    return JSON.stringify(results);
                })()
            """,
            "sessionId": self.session_id,
            "awaitPromise": True,
            "returnByValue": True
        }, self.session_id)
        
        import json as pyjson
        return pyjson.loads(check["result"]["value"])


# 使用示例
async def run_monitor():
    async with websockets.connect(CDP_URL) as ws:
        session_id, _ = await connect_page(ws)
        
        # 导航到目标页面
        await cdp(ws, "Page.navigate", {
            "url": "https://your-pwa-site.com"
        }, session_id)
        await asyncio.sleep(5)
        
        # 启动监控
        monitor = OfflineCacheMonitor(ws, session_id)
        await monitor.enable()
        
        # 每 10 秒采集一次快照，共 3 次
        for i in range(3):
            print(f"\n===== 快照 {i+1} =====")
            snapshot = await monitor.take_snapshot()
            print(f"SW 状态: {snapshot['sw_status']}")
            print(f"离线就绪: {snapshot['offline_readiness']}")
            
            cache_total = sum(
                c["entry_count"] for c in snapshot["cache_status"]
            )
            print(f"缓存条目总数: {cache_total}")
            
            await asyncio.sleep(10)
```

---

## Service Worker 强制更新与跳过等待

### Skip Waiting

当有新版本的 Service Worker 在等待时，可以使用 `skipWaiting` 强制激活：

```python
async def skip_waiting_and_reload(ws, session_id):
    """
    跳过 waiting 状态，立即激活新版本的 Service Worker
    """
    # 1. 获取当前版本信息
    await cdp(ws, "ServiceWorker.enable")
    
    # 2. 调用 skipWaiting
    await cdp(ws, "ServiceWorker.skipWaiting", {
        "scopeURL": ""  # 空字符串表示所有 scope
    })
    print("skipWaiting 已触发")
    
    # 3. 或者通过页面上下文执行
    await cdp(ws, "Runtime.evaluate", {
        "expression": """
            navigator.serviceWorker.getRegistration().then(reg => {
                if (reg && reg.waiting) {
                    reg.waiting.postMessage({action: 'SKIP_WAITING'});
                }
            });
        """,
        "sessionId": session_id
    }, session_id)
    
    # 4. 等待新版本激活
    await asyncio.sleep(2)
    
    # 5. 刷新页面使新 SW 接管
    await cdp(ws, "Page.reload", {}, session_id)
    await asyncio.sleep(2)
    print("页面已刷新，新 Service Worker 已接管")


async def unregister_service_worker(ws, registration_id):
    """
    注销指定 registrationId 的 Service Worker
    """
    result = await cdp(ws, "ServiceWorker.unregister", {
        "scopeURL": registration_id
    })
    print(f"Service Worker 注销结果: {result.get('success', False)}")
    return result.get("success", False)


async def force_update_service_worker(ws, session_id):
    """
    强制更新 Service Worker（通过页面上下文触发）
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            navigator.serviceWorker.getRegistration().then(reg => {
                if (reg) {
                    reg.update().then(() => {
                        console.log('Service Worker 强制更新完成');
                    });
                }
            });
        """,
        "sessionId": session_id,
        "awaitPromise": True
    }, session_id)
    print("Service Worker 强制更新已触发")
    return result
```

### 批量管理多个 Worker

```python
async def cleanup_all_workers(ws, keep_scope=None):
    """
    清理所有 Service Worker，可选择保留指定 scope
    """
    await cdp(ws, "ServiceWorker.enable")
    
    # 通过页面获取所有注册信息的方式较为有限，
    # 最佳方式是通过 CDP 事件收集
    print("开始清理 Service Worker...")
    
    # 通过 JavaScript 在页面中批量注销
    # 注意：这需要在每个页面上下文中执行
    cleanup_script = """
        (async () => {
            const registrations = await navigator.serviceWorker.getRegistrations();
            let count = 0;
            for (const reg of registrations) {
                const scope = reg.scope;
                const keep = %s;
                if (keep && scope.includes(keep)) {
                    console.log('保留:', scope);
                    continue;
                }
                await reg.unregister();
                count++;
            }
            return count;
        })()
    """ % (f"'{keep_scope}'" if keep_scope else "null")
    
    return cleanup_script


# 使用示例
async def example_sw_management():
    async with websockets.connect(CDP_URL) as ws:
        session_id, _ = await connect_page(ws)
        
        # 导航到页面
        await cdp(ws, "Page.navigate", {
            "url": "https://example-pwa.com"
        }, session_id)
        await asyncio.sleep(3)
        
        # 注册监听
        await enable_service_worker(ws)
        
        # 强制更新
        await force_update_service_worker(ws, session_id)
        await asyncio.sleep(3)
        
        # 如果存在 waiting 版本，跳过等待
        await skip_waiting_and_reload(ws, session_id)
```

---

## 常见踩坑与最佳实践

### 踩坑 1：ServiceWorker.enable 不需要 sessionId

`ServiceWorker` 域的多数方法是浏览器级别的，不需要 `sessionId`：

```python
# ❌ 错误：传了 sessionId
await cdp(ws, "ServiceWorker.enable", {}, session_id)

# ✅ 正确：浏览器级别，不传 sessionId
await cdp(ws, "ServiceWorker.enable")
```

### 踩坑 2：CacheStorage 需要 sessionId

与 `ServiceWorker` 不同，`CacheStorage` 域是页面级别的：

```python
# ❌ 错误：不传 sessionId
await cdp(ws, "CacheStorage.requestCacheNames", {"securityOrigin": ""})

# ✅ 正确：需要 sessionId
await cdp(ws, "CacheStorage.requestCacheNames", {
    "securityOrigin": ""
}, session_id)
```

### 踩坑 3：导航后需要等待 SW 激活

```python
# ❌ 导航后立即检查缓存（SW 可能还没拦截请求）
await cdp(ws, "Page.navigate", {"url": url}, session_id)
await list_caches(ws, session_id)  # 可能为空

# ✅ 等待 SW 完全激活后再检查
await cdp(ws, "Page.navigate", {"url": url}, session_id)
await asyncio.sleep(5)
await list_caches(ws, session_id)
```

### 踩坑 4：安全上下文要求

Service Worker 只能在 HTTPS 或 localhost 下注册。如果导航到 HTTP 页面，SW API 不可用：

```python
# ❌ HTTP 页面无法注册 SW
await cdp(ws, "Page.navigate", {
    "url": "http://example.com"
}, session_id)
# navigator.serviceWorker 为 undefined

# ✅ HTTPS 或 localhost
await cdp(ws, "Page.navigate", {
    "url": "https://example.com"
}, session_id)
```

### 踩坑 5：作用域限制

Service Worker 只能控制其所在路径及其子路径：

```python
# Worker 注册在 /app/sw.js 只能控制 /app/* 路径
# CDP 的 unregister 需要传入正确的 scopeURL
# 错误的 scopeURL 会导致注销失败
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| ServiceWorker 域 | 浏览器级别，不需要 sessionId |
| CacheStorage 域 | 页面级别，需要 sessionId |
| 等待激活 | 导航后等待 3-5 秒再操作缓存 |
| 安全上下文 | 使用 HTTPS 或 localhost |
| 作用域管理 | 注销时传入正确的 scopeURL |
| 版本追踪 | 利用 onWorkerVersionUpdated 事件 |
| 缓存清理 | 测试前后清理缓存确保环境一致 |

---

## 完整参考：CDP Service Worker 管理类

```python
import asyncio
import json
import base64


class CDPServiceWorkerManager:
    """CDP Service Worker 管理器"""

    def __init__(self, ws):
        self.ws = ws
        self._cmd_id = 0
        self.versions = {}
        self.registrations = {}
        self.error_log = []

    async def _cmd(self, method, params=None):
        """发送 CDP 命令（浏览器级别）"""
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})

    async def _cmd_session(self, method, params, session_id):
        """发送 CDP 命令（页面级别，带 sessionId）"""
        self._cmd_id += 1
        msg = {
            "id": self._cmd_id, "method": method,
            "params": params or {}, "sessionId": session_id
        }
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})

    async def enable(self):
        """启用 Service Worker 监听"""
        return await self._cmd("ServiceWorker.enable")

    async def disable(self):
        """禁用 Service Worker 监听"""
        return await self._cmd("ServiceWorker.disable")

    async def skip_waiting(self, scope_url=""):
        """跳过等待，激活新版本"""
        return await self._cmd("ServiceWorker.skipWaiting", {
            "scopeURL": scope_url
        })

    async def unregister(self, scope_url):
        """注销 Service Worker"""
        return await self._cmd("ServiceWorker.unregister", {
            "scopeURL": scope_url
        })

    async def dispatch_sync(self, tag, last_chance=False):
        """触发后台同步事件"""
        return await self._cmd("ServiceWorker.dispatchSyncEvent", {
            "tag": tag, "lastChance": last_chance
        })

    async def dispatch_periodic_sync(self, tag):
        """触发定期后台同步事件"""
        return await self._cmd("ServiceWorker.dispatchPeriodicSyncEvent", {
            "tag": tag
        })

    async def inspect_worker(self, version_id):
        """获取 Worker 调试 URL"""
        return await self._cmd("ServiceWorker.inspectWorker", {
            "versionId": version_id
        })

    async def list_caches(self, session_id, origin=""):
        """列出缓存（需要 sessionId）"""
        return await self._cmd_session(
            "CacheStorage.requestCacheNames",
            {"securityOrigin": origin}, session_id
        )

    async def read_cache_entries(self, session_id, cache_id,
                                  skip=0, page_size=50):
        """读取缓存条目（需要 sessionId）"""
        return await self._cmd_session(
            "CacheStorage.requestEntries",
            {"cacheId": cache_id, "skipCount": skip, "pageSize": page_size},
            session_id
        )

    async def delete_cache(self, session_id, cache_name):
        """删除缓存（需要 sessionId）"""
        return await self._cmd_session(
            "CacheStorage.deleteCache",
            {"cacheName": cache_name}, session_id
        )

    async def delete_cache_entry(self, session_id, cache_id, request_url):
        """删除缓存条目（需要 sessionId）"""
        return await self._cmd_session(
            "CacheStorage.deleteEntry",
            {"cacheId": cache_id, "request": request_url}, session_id
        )

    async def collect_events(self, duration=30):
        """收集一段时间内的 Service Worker 事件"""
        await self.enable()
        events = []
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < duration:
            try:
                resp = await asyncio.wait_for(
                    self.ws.recv(), timeout=1.0
                )
                data = json.loads(resp)
                method = data.get("method", "")

                if method.startswith("ServiceWorker."):
                    events.append({
                        "method": method,
                        "params": data.get("params", {}),
                        "time": asyncio.get_event_loop().time()
                    })

                    if method == "ServiceWorker.onWorkerVersionUpdated":
                        for v in data["params"]["versions"]:
                            self.versions[v["versionId"]] = v

                    elif method == "ServiceWorker.onWorkerRegistrationUpdated":
                        for r in data["params"]["registrations"]:
                            self.registrations[r["registrationId"]] = r

                    elif method == "ServiceWorker.onWorkerErrorReported":
                        self.error_log.append(
                            data["params"]["errorMessage"]
                        )
            except asyncio.TimeoutError:
                pass

        return events
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    # 连接页面
    targets = await cdp(ws, "Target.getTargets")
    page_target = next(t for t in targets["targetInfos"]
                       if t["type"] == "page")
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": page_target["targetId"], "flatten": True
    })
    session_id = session["sessionId"]

    # 创建管理器
    sw_mgr = CDPServiceWorkerManager(ws)
    await sw_mgr.enable()

    # 导航到 PWA 页面
    await cdp(ws, "Page.navigate", {
        "url": "https://your-pwa-site.com"
    }, session_id)
    await asyncio.sleep(5)

    # 收集事件
    events = await sw_mgr.collect_events(duration=15)
    print(f"收集到 {len(events)} 个 Service Worker 事件")

    # 检查缓存
    caches = await sw_mgr.list_caches(session_id)
    print(f"缓存数: {len(caches.get('caches', []))}")

    # 注销
    for reg_id in sw_mgr.registrations:
        await sw_mgr.unregister(reg_id)
```

---

> **总结**：CDP 的 `ServiceWorker` 域提供了浏览器级别的 Service Worker 生命周期管理能力，配合 `CacheStorage` 域的缓存操作，可以完全自动化 PWA 的离线缓存调试、推送通知触发和缓存健康监控。在开发 PWA 应用或进行离线功能测试时，这些 API 是不可或缺的工具。

---

*上一篇回顾：CDP 文件上传与下载：用 Python 处理文件操作。*

*下一篇预告：CDP 性能观察者指南：用 Python 监控 Core Web Vitals。*