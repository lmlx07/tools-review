---
lang: en
title: "CDP Storage Operations Guide: Manage LocalStorage, IndexedDB & Cache with Python"
date: "2026-06-05 19:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Storage
  - IndexedDB
  - LocalStorage
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to managing browser storage using Chrome DevTools Protocol (CDP). Learn to read/write LocalStorage and SessionStorage, operate IndexedDB databases, manage CacheStorage, clear site data, and migrate storage state between browsers.
---

> **Summary in one sentence**: CDP's Storage and IndexedDB domains provide complete browser storage management — you can programmatically control all client-side storage just like DevTools' Application panel, but fully scriptable.

---

## Table of Contents

1. [Why Use CDP for Storage Management](#why-use-cdp-for-storage-management)
2. [LocalStorage & SessionStorage](#localstorage--sessionstorage)
3. [IndexedDB Operations](#indexeddb-operations)
4. [CacheStorage Management](#cachestorage-management)
5. [Clearing Site Data](#clearing-site-data)
6. [Practical: Storage State Migration](#practical-storage-state-migration)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Storage Management

| Feature | JavaScript API | CDP Storage API |
|---------|---------------|-----------------|
| Cross-origin storage | ❌ Same-origin only | ✅ Any origin |
| IndexedDB enumeration | ⚠️ Must traverse | ✅ One-shot DB/store listing |
| Clear all storage | ❌ Per-API clearing | ✅ `Storage.clearDataForOrigin` |
| Storage quota | ❌ Estimate only | ✅ Exact usage and quota |
| Change tracking | ❌ Manual subscription | ✅ Built-in events |

---

## LocalStorage & SessionStorage

### Via Runtime.evaluate

```python
import asyncio, websockets, json

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


async def get_local_storage(ws, session_id):
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "JSON.stringify(window.localStorage)"
    })
    return json.loads(result["result"]["value"])

async def set_local_storage_item(ws, session_id, key, value):
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"window.localStorage.setItem('{key}', '{value}')"
    })

async def clear_local_storage(ws, session_id):
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "window.localStorage.clear()"
    })
```

### Via DOMStorage Domain (Cross-Origin)

```python
async def get_storage_for_origin(ws, session_id, origin):
    return await cdp(ws, session_id, "DOMStorage.getDOMStorageItems", {
        "storageId": {"securityOrigin": origin, "isLocalStorage": True}
    })

async def set_storage_item(ws, session_id, origin, key, value):
    await cdp(ws, session_id, "DOMStorage.setDOMStorageItem", {
        "storageId": {"securityOrigin": origin, "isLocalStorage": True},
        "key": key, "value": value
    })
```

### Tracking Storage Changes

```python
async def track_storage_changes(ws, session_id, duration=10):
    await cdp(ws, session_id, "DOMStorage.enable")
    changes = []
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            m = data.get("method", "")
            if m in ("DOMStorage.domStorageItemAdded", "DOMStorage.domStorageItemRemoved", "DOMStorage.domStorageItemUpdated"):
                changes.append((m, data["params"]))
        except asyncio.TimeoutError:
            continue
    return changes
```

---

## IndexedDB Operations

```python
async def list_indexeddb_databases(ws, session_id, origin):
    result = await cdp(ws, session_id, "IndexedDB.requestDatabaseNames", {
        "securityOrigin": origin
    })
    return result.get("databaseNames", [])


async def inspect_database(ws, session_id, origin, db_name):
    result = await cdp(ws, session_id, "IndexedDB.requestDatabase", {
        "securityOrigin": origin, "databaseName": db_name
    })
    return result.get("database", {})


async def get_indexeddb_data(ws, session_id, origin, db_name, store_name, page_size=100):
    result = await cdp(ws, session_id, "IndexedDB.requestData", {
        "securityOrigin": origin, "databaseName": db_name,
        "objectStoreName": store_name,
        "skipCount": 0, "pageSize": page_size
    })
    return result.get("entries", [])


async def export_indexeddb(ws, session_id, origin):
    export = {}
    db_names = await list_indexeddb_databases(ws, session_id, origin)
    for db_name in db_names:
        db_info = await inspect_database(ws, session_id, origin, db_name)
        db_data = {}
        for store in db_info.get("objectStores", []):
            entries = await get_indexeddb_data(ws, session_id, origin, db_name, store["name"])
            db_data[store["name"]] = entries
        export[db_name] = db_data
    return export
```

---

## CacheStorage Management

```python
async def list_caches(ws, session_id, origin):
    result = await cdp(ws, session_id, "CacheStorage.requestCacheNames", {
        "securityOrigin": origin
    })
    return result.get("caches", [])

async def get_cache_entries(ws, session_id, cache_id, page_size=100):
    result = await cdp(ws, session_id, "CacheStorage.requestEntries", {
        "cacheId": cache_id, "skipCount": 0, "pageSize": page_size
    })
    return result.get("entries", [])

async def delete_cache_entry(ws, session_id, cache_id, request_url):
    await cdp(ws, session_id, "CacheStorage.deleteEntry", {
        "cacheId": cache_id, "request": request_url
    })
```

---

## Clearing Site Data

```python
async def clear_site_data(ws, session_id, origin, storage_types=None):
    if storage_types is None:
        storage_types = ["local_storage", "indexeddb", "cache_storage"]
    for st in storage_types:
        await cdp(ws, session_id, "Storage.clearDataForOrigin", {
            "origin": origin, "storageTypes": st
        })

async def clear_all_site_data(ws, session_id, origin):
    await cdp(ws, session_id, "Storage.clearDataForOrigin", {
        "origin": origin, "storageTypes": "all"
    })

async def get_storage_usage(ws, session_id, origin):
    result = await cdp(ws, session_id, "Storage.getUsageAndQuota", {
        "origin": origin
    })
    usage = result.get("usage", 0)
    quota = result.get("quota", 0)
    print(f"Usage: {usage/1024/1024:.2f}MB / {quota/1024/1024:.2f}MB "
          f"({usage/quota*100:.1f}%)")
    return result
```

---

## Practical: Storage State Migration

```python
async def export_all_storage(ws, session_id, origin):
    state = {"origin": origin, "localStorage": {}}
    
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": """
            (function() {
                const data = {};
                for (let i = 0; i < window.localStorage.length; i++) {
                    const k = window.localStorage.key(i);
                    data[k] = window.localStorage.getItem(k);
                }
                return JSON.stringify(data);
            })()
        """
    })
    state["localStorage"] = json.loads(result["result"]["value"])
    
    db_names = await list_indexeddb_databases(ws, session_id, origin)
    if db_names:
        state["indexedDB"] = await export_indexeddb(ws, session_id, origin)
    
    return state


async def import_storage_state(ws, session_id, state):
    origin = state["origin"]
    await cdp(ws, session_id, "Page.navigate", {"url": f"https://{origin}"})
    await asyncio.sleep(2)
    
    for key, value in state.get("localStorage", {}).items():
        await cdp(ws, session_id, "Runtime.evaluate", {
            "expression": f"window.localStorage.setItem('{key}', {json.dumps(value)})"
        })
    print(f"Restored {len(state.get('localStorage', {}))} localStorage items")
```

---

## Common Pitfalls & Best Practices

| Pitfall | Solution |
|---------|----------|
| origin missing protocol | Always include `https://` prefix |
| IndexedDB non-JSON types | Handle ArrayBuffer, Date types during export |
| CacheStorage cacheId staleness | Re-list caches before each operation |
| Storage clearing scope | Supports comma-separated types or `"all"` |

---

## Complete Reference: CDP Storage Class

```python
class CDPStorageManager:
    def __init__(self, ws, session_id):
        self.ws = ws; self.session_id = session_id; self._cmd_id = 0
    
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
        return await self._cmd("Storage.getUsageAndQuota", {"origin": origin})
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    store = CDPStorageManager(ws, session_id)
    usage = await store.get_usage("https://example.com")
    await store.clear_origin("https://example.com")
```

---

> **Summary**: CDP's Storage and IndexedDB APIs give you complete browser storage control — from LocalStorage to IndexedDB to CacheStorage — with cross-origin access and precise clearing. This is invaluable for automated testing and storage state migration.

---

*Previous: CDP Console Debugging Guide — capture page logs & exceptions with Python.*

*Next up: CDP Dialog Handling — auto-dismissing alert/confirm/prompt dialogs.*
