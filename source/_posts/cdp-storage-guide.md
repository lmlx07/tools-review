---
title: CDP 存储操作指南：用 Python 管理 LocalStorage、IndexedDB 与缓存
date: 2026-06-05 19:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Storage
  - IndexedDB
  - LocalStorage
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）操作浏览器存储。涵盖读取/写入 LocalStorage 和 SessionStorage、操作 IndexedDB 数据库、管理 CacheStorage、清空站点数据，以及在不同存储域之间迁移数据。
---

> **一句话总结**：CDP 的 Storage 和 IndexedDB 域提供了完整的浏览器存储管理能力——你可以像操作 DevTools 的 Application 面板一样编程地管理所有客户端存储。

---

## 目录

1. [为什么用 CDP 管理存储](#为什么用-cdp-管理存储)
2. [操作 LocalStorage 和 SessionStorage](#操作-localstorage-和-sessionstorage)
3. [操作 IndexedDB](#操作-indexeddb)
4. [管理 CacheStorage](#管理-cachestorage)
5. [清空站点数据](#清空站点数据)
6. [实战：存储状态迁移](#实战存储状态迁移)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 管理存储

| 功能 | JavaScript API | CDP Storage API |
|------|---------------|-----------------|
| 跨域读取存储 | ❌ 同源限制 | ✅ 可操作任意域 |
| IndexedDB 枚举 | ⚠️ 需遍历数据库 | ✅ 一步获取所有库/表 |
| 清空所有存储 | ❌ 逐个 API 清理 | ✅ `Storage.clearDataForOrigin` |
| Storage 配额 | ❌ 仅可估计 | ✅ 精确的用量和配额 |
| 跟踪存储变化 | ❌ 需自行订阅 | ✅ 内置事件通知 |

---

## 操作 LocalStorage 和 SessionStorage

### 通过 Runtime.evaluate 操作

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


async def get_local_storage(ws, session_id):
    """获取当前页面的所有 LocalStorage 数据"""
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "JSON.stringify(window.localStorage)"
    })
    return json.loads(result["result"]["value"])


async def set_local_storage_item(ws, session_id, key, value):
    """设置 LocalStorage 项"""
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"window.localStorage.setItem('{key}', '{value}')"
    })


async def remove_local_storage_item(ws, session_id, key):
    """删除 LocalStorage 项"""
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"window.localStorage.removeItem('{key}')"
    })


async def clear_local_storage(ws, session_id):
    """清空 LocalStorage"""
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "window.localStorage.clear()"
    })


async def get_session_storage(ws, session_id):
    """获取 SessionStorage"""
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "JSON.stringify(window.sessionStorage)"
    })
    return json.loads(result["result"]["value"])
```

### 通过 Storage 域操作（跨域）

比 Runtime.evaluate 更强大——可以访问任意域名的存储：

```python
async def get_storage_for_origin(ws, session_id, origin):
    """获取指定域名的 LocalStorage"""
    return await cdp(ws, session_id, "DOMStorage.getDOMStorageItems", {
        "storageId": {
            "securityOrigin": origin,
            "isLocalStorage": True
        }
    })


async def set_storage_item(ws, session_id, origin, key, value):
    """设置指定域名的存储项"""
    await cdp(ws, session_id, "DOMStorage.setDOMStorageItem", {
        "storageId": {
            "securityOrigin": origin,
            "isLocalStorage": True
        },
        "key": key,
        "value": value
    })


async def remove_storage_item(ws, session_id, origin, key):
    """删除指定域名的存储项"""
    await cdp(ws, session_id, "DOMStorage.removeDOMStorageItem", {
        "storageId": {
            "securityOrigin": origin,
            "isLocalStorage": True
        },
        "key": key
    })
```

### 监听存储变化

```python
async def enable_storage_tracking(ws, session_id):
    """启用存储变化跟踪"""
    await cdp(ws, session_id, "DOMStorage.enable")


async def track_storage_changes(ws, session_id, duration=10):
    """跟踪存储变化事件"""
    await enable_storage_tracking(ws, session_id)
    
    changes = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "DOMStorage.domStorageItemAdded":
                changes.append(("added", data["params"]))
            elif data.get("method") == "DOMStorage.domStorageItemRemoved":
                changes.append(("removed", data["params"]))
            elif data.get("method") == "DOMStorage.domStorageItemUpdated":
                changes.append(("updated", data["params"]))
                    
        except asyncio.TimeoutError:
            continue
    
    return changes
```

---

## 操作 IndexedDB

### 枚举数据库

```python
async def list_indexeddb_databases(ws, session_id, origin):
    """列出指定域名下的所有 IndexedDB 数据库"""
    result = await cdp(ws, session_id, "IndexedDB.requestDatabaseNames", {
        "securityOrigin": origin
    })
    return result.get("databaseNames", [])


async def inspect_database(ws, session_id, origin, db_name):
    """查看 IndexedDB 数据库详情（包含所有 object stores）"""
    result = await cdp(ws, session_id, "IndexedDB.requestDatabase", {
        "securityOrigin": origin,
        "databaseName": db_name
    })
    return result.get("database", {})
```

### 读取数据

```python
async def get_indexeddb_data(ws, session_id, origin, db_name,
                              store_name, skip_count=0, page_size=100):
    """从 IndexedDB object store 读取数据"""
    result = await cdp(ws, session_id, "IndexedDB.requestData", {
        "securityOrigin": origin,
        "databaseName": db_name,
        "objectStoreName": store_name,
        "skipCount": skip_count,
        "pageSize": page_size
    })
    return {
        "entries": result.get("entries", []),
        "has_more": result.get("hasMore", False)
    }


async def clear_indexeddb(ws, session_id, origin, db_name, store_name):
    """清空 IndexedDB object store"""
    await cdp(ws, session_id, "IndexedDB.clearObjectStore", {
        "securityOrigin": origin,
        "databaseName": db_name,
        "objectStoreName": store_name
    })
```

### 完整示例：导出 IndexedDB 数据

```python
async def export_indexeddb(ws, session_id, origin):
    """导出指定域名下的所有 IndexedDB 数据"""
    export = {}
    
    # 1. 获取所有数据库名
    db_names = await list_indexeddb_databases(ws, session_id, origin)
    print(f"发现 {len(db_names)} 个 IndexedDB 数据库")
    
    for db_name in db_names:
        # 2. 检查数据库结构
        db_info = await inspect_database(ws, session_id, origin, db_name)
        stores = db_info.get("objectStores", [])
        
        db_data = {}
        for store in stores:
            store_name = store["name"]
            # 3. 读取数据
            result = await get_indexeddb_data(
                ws, session_id, origin, db_name, store_name
            )
            db_data[store_name] = result["entries"]
            print(f"  库 '{db_name}' / 表 '{store_name}': {len(result['entries'])} 条")
        
        export[db_name] = db_data
    
    return export
```

---

## 管理 CacheStorage

```python
async def list_caches(ws, session_id, origin):
    """列出指定域名下的所有 Cache API 缓存"""
    result = await cdp(ws, session_id, "CacheStorage.requestCacheNames", {
        "securityOrigin": origin
    })
    return result.get("caches", [])


async def get_cache_entries(ws, session_id, cache_id, skip=0, page_size=100):
    """获取缓存中的条目"""
    result = await cdp(ws, session_id, "CacheStorage.requestEntries", {
        "cacheId": cache_id,
        "skipCount": skip,
        "pageSize": page_size
    })
    return result.get("entries", [])


async def delete_cache_entry(ws, session_id, cache_id, request_url):
    """删除缓存中的指定条目"""
    await cdp(ws, session_id, "CacheStorage.deleteEntry", {
        "cacheId": cache_id,
        "request": request_url
    })


async def inspect_cache(ws, session_id, origin):
    """检查指定域名的所有缓存内容"""
    caches = await list_caches(ws, session_id, origin)
    print(f"发现 {len(caches)} 个缓存")
    
    for cache in caches:
        cache_name = cache["cacheName"]
        cache_id = cache["cacheId"]
        entries = await get_cache_entries(ws, session_id, cache_id)
        print(f"  缓存 '{cache_name}': {len(entries)} 条")
        
        for entry in entries[:5]:  # 只显示前 5 条
            print(f"    {entry.get('requestURL', '')}")
```

---

## 清空站点数据

### 精确清理特定类型的数据

```python
async def clear_site_data(ws, session_id, origin, storage_types=None):
    """
    清空指定域名的存储数据
    storage_types 可选值:
    - cookies, localStorage, indexeddb, cache_storage, service_workers,
      web_sql, file_systems, local_storage
    """
    if storage_types is None:
        storage_types = ["local_storage", "indexeddb", "cache_storage", "cookies"]
    
    for st in storage_types:
        await cdp(ws, session_id, "Storage.clearDataForOrigin", {
            "origin": origin,
            "storageTypes": st
        })
        print(f"已清理 {origin} 的 {st}")


async def clear_all_site_data(ws, session_id, origin):
    """清空指定域名的所有存储"""
    await cdp(ws, session_id, "Storage.clearDataForOrigin", {
        "origin": origin,
        "storageTypes": "all"
    })
    print(f"已清空 {origin} 的所有存储")


# 多个类型可以逗号分隔一次调用
async def clear_multiple_types(ws, session_id, origin):
    """一次调用清理多种存储类型"""
    await cdp(ws, session_id, "Storage.clearDataForOrigin", {
        "origin": origin,
        "storageTypes": "local_storage,indexeddb,cache_storage,service_workers"
    })
```

### 获取存储用量

```python
async def get_storage_usage(ws, session_id, origin):
    """获取指定域名的存储使用量"""
    result = await cdp(ws, session_id, "Storage.getUsageAndQuota", {
        "origin": origin
    })
    
    usage = result.get("usage", 0)
    quota = result.get("quota", 0)
    
    print(f"存储报告 for {origin}")
    print(f"  使用量: {usage / 1024 / 1024:.2f} MB")
    print(f"  配额:   {quota / 1024 / 1024:.2f} MB")
    print(f"  使用率: {usage / quota * 100:.1f}%")
    
    # 各类型用量明细
    for item in result.get("usageBreakdown", []):
        stype = item["storageType"]
        stype_usage = item["usage"]
        print(f"    {stype}: {stype_usage / 1024:.1f} KB")
    
    return result
```

---

## 实战：存储状态迁移

在浏览器 A 中导出的存储状态注入到浏览器 B：

```python
async def export_all_storage(ws, session_id, origin):
    """导出指定域名的所有客户端存储"""
    print(f"导出 {origin} 的存储状态...")
    
    state = {"origin": origin, "localStorage": {}, "sessionStorage": {}}
    
    # 1. LocalStorage
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"""
            (function() {{
                const data = {{}};
                for (let i = 0; i < window.localStorage.length; i++) {{
                    const k = window.localStorage.key(i);
                    data[k] = window.localStorage.getItem(k);
                }}
                return JSON.stringify(data);
            }})()
        """
    })
    state["localStorage"] = json.loads(result["result"]["value"])
    
    # 2. SessionStorage
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"""
            (function() {{
                const data = {{}};
                for (let i = 0; i < window.sessionStorage.length; i++) {{
                    const k = window.sessionStorage.key(i);
                    data[k] = window.sessionStorage.getItem(k);
                }}
                return JSON.stringify(data);
            }})()
        """
    })
    state["sessionStorage"] = json.loads(result["result"]["value"])
    
    # 3. IndexedDB（如果有）
    db_names = await list_indexeddb_databases(ws, session_id, origin)
    if db_names:
        state["indexedDB"] = await export_indexeddb(ws, session_id, origin)
    
    print(f"导出完成: {len(state['localStorage'])} 个 LS 项, "
          f"{len(state['sessionStorage'])} 个 SS 项")
    return state


async def import_storage_state(ws, session_id, state):
    """导入存储状态到浏览器"""
    origin = state["origin"]
    print(f"导入存储状态到 {origin}...")
    
    # 1. 先导航到该域名
    await cdp(ws, session_id, "Page.navigate", {"url": f"https://{origin}"})
    await asyncio.sleep(2)
    
    # 2. 恢复 LocalStorage
    for key, value in state.get("localStorage", {}).items():
        await cdp(ws, session_id, "Runtime.evaluate", {
            "expression": f"window.localStorage.setItem('{key}', {json.dumps(value)})"
        })
    print(f"  已恢复 {len(state.get('localStorage', {}))} 个 LS 项")
    
    # 3. 恢复 SessionStorage
    for key, value in state.get("sessionStorage", {}).items():
        await cdp(ws, session_id, "Runtime.evaluate", {
            "expression": f"window.sessionStorage.setItem('{key}', {json.dumps(value)})"
        })
    print(f"  已恢复 {len(state.get('sessionStorage', {}))} 个 SS 项")
```

---

## 常见踩坑与最佳实践

### 踩坑 1：IndexedDB 数据需序列化

IndexedDB 可能存储非 JSON 数据类型（如 ArrayBuffer、Date），导出时需特别注意：

```python
# IndexedDB.requestData 返回的 entries 中 value 是 object 类型
# 可能需要按类型转换
for entry in result.get("entries", []):
    value = entry.get("value", {})
    # value 可能是 object、string、number 等
```

### 踩坑 2：`clearDataForOrigin` 的 origin 格式

```python
# ❌ origin 格式错误
await cdp(ws, session_id, "Storage.clearDataForOrigin", {
    "origin": "example.com"  # 缺少协议
})

# ✅ 正确格式
await cdp(ws, session_id, "Storage.clearDataForOrigin", {
    "origin": "https://example.com"
})
```

### 踩坑 3：CacheStorage 的 cacheId 有时效性

```python
# cacheId 在某些操作后可能会失效（如缓存更新）
# 每次操作前建议重新 list_caches 获取最新的 cacheId
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| origin 格式 | 必须包含协议（https://） |
| 存储清理 | 支持逗号分隔多类型或使用 "all" |
| IndexedDB | 导出时注意特殊数据类型 |
| CacheStorage | cacheId 有时效，定期刷新 |
| 跨域存储 | DOMStorage 域支持跨域操作 |
| 存储迁移 | 先导航到域名再写入 |

---

## 完整参考：CDP 存储管理类

```python
class CDPStorageManager:
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        msg = {"sessionId": self.session_id, "id": self._cmd_id,
               "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def ls_get(self, origin):
        r = await self._cmd("DOMStorage.getDOMStorageItems", {
            "storageId": {"securityOrigin": origin, "isLocalStorage": True}
        })
        return dict(r.get("entries", []))
    
    async def ls_set(self, origin, key, value):
        await self._cmd("DOMStorage.setDOMStorageItem", {
            "storageId": {"securityOrigin": origin, "isLocalStorage": True},
            "key": key, "value": value
        })
    
    async def clear_origin(self, origin, types="all"):
        await self._cmd("Storage.clearDataForOrigin", {
            "origin": origin, "storageTypes": types
        })
    
    async def get_usage(self, origin):
        return await self._cmd("Storage.getUsageAndQuota", {
            "origin": origin
        })
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    store = CDPStorageManager(ws, session_id)
    
    # 查看存储用量
    usage = await store.get_usage("https://example.com")
    
    # 清空所有存储
    await store.clear_origin("https://example.com")
```

---

> **总结**：CDP 的 Storage 和 IndexedDB API 提供了完整的浏览器存储管理能力——从 LocalStorage 到 IndexedDB 到 CacheStorage，以及跨域访问和精确清理。这在自动化测试和存储状态迁移场景中非常实用。

---

*上一篇回顾：CDP Console 调试指南：用 Python 捕获页面日志与异常。*

*下一篇预告：CDP 对话框处理指南：用 Python 自动处理 alert/confirm/prompt。*