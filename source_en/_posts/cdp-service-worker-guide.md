---
lang: en
title: "CDP Service Worker Management: Debugging Offline Cache with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Service Worker
  - PWA
  - Offline Cache
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to managing Service Workers via Chrome DevTools Protocol (CDP). Covers registration/unregistration monitoring, lifecycle tracking, push notification simulation, CacheStorage operations, and offline debugging automation with Python.
---

> **Summary in one sentence**: CDP's `ServiceWorker` domain gives you full programmatic control over the browser's Service Worker lifecycle — registering, debugging, pushing notifications, manipulating caches, force-updating, and unregistering — making it an essential tool for PWA offline debugging.

---

## Table of Contents

1. [Service Workers and CDP](#service-workers-and-cdp)
2. [Basics: Listening to Service Worker Events](#basics-listening-to-service-worker-events)
3. [Lifecycle Tracking: installing → activated → redundant](#lifecycle-tracking-installing--activated--redundant)
4. [Push Notifications](#push-notifications)
5. [CacheStorage Operations](#cachestorage-operations)
6. [Practical: Offline Cache Health Monitor](#practical-offline-cache-health-monitor)
7. [Force Update and Skip Waiting](#force-update-and-skip-waiting)
8. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Service Workers and CDP

### Why Use CDP for Service Worker Management

Service Workers run in a browser sandbox. While DevTools provides a visual Application panel, CDP's `ServiceWorker` domain offers full programmatic control:

| Operation | Application Panel | CDP |
|-----------|-------------------|-----|
| Watch registration/unregistration | ❌ Manual refresh needed | ✅ `ServiceWorker.onWorkerRegistrationUpdated` |
| Lifecycle tracking | ❌ Shows current state only | ✅ `ServiceWorker.onWorkerVersionUpdated` |
| Push notifications | ❌ Cannot trigger | ✅ `ServiceWorker.dispatchSyncEvent` |
| CacheStorage | ✅ Manual browsing | ✅ Full `CacheStorage.*` API |
| Skip waiting | ❌ Manual button click | ✅ `ServiceWorker.skipWaiting` |
| Batch management | ❌ Manual | ✅ Fully automated |

### Key ServiceWorker Domain Methods

- `ServiceWorker.enable` — Enable SW event monitoring
- `ServiceWorker.disable` — Disable monitoring
- `ServiceWorker.skipWaiting` — Force activate waiting worker
- `ServiceWorker.unregister` — Unregister a Service Worker
- `ServiceWorker.dispatchSyncEvent` — Trigger a background sync event
- `ServiceWorker.dispatchPeriodicSyncEvent` — Trigger a periodic sync event
- `ServiceWorker.inspectWorker` — Open Worker inspector panel

---

## Basics: Listening to Service Worker Events

### Enabling Monitoring

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
    """Attach to the first available page target"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets["targetInfos"]:
        if target["type"] == "page":
            session = await cdp(ws, "Target.attachToTarget", {
                "targetId": target["targetId"], "flatten": True
            })
            return session["sessionId"], target["targetId"]
    raise Exception("No page target found")


async def enable_service_worker(ws):
    """Enable Service Worker monitoring (browser-level, no sessionId needed)"""
    result = await cdp(ws, "ServiceWorker.enable")
    print(f"Service Worker monitoring enabled")
    return result


async def monitor_sw_events(ws, duration=30):
    """Continuously monitor Service Worker events"""
    await enable_service_worker(ws)
    print(f"Monitoring Service Worker events for {duration}s ...")
    
    start = asyncio.get_event_loop().time()
    while asyncio.get_event_loop().time() - start < duration:
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
            data = json.loads(resp)
            method = data.get("method", "")
            
            if method == "ServiceWorker.onWorkerRegistrationUpdated":
                registrations = data["params"]["registrations"]
                for reg in registrations:
                    print(f"[Registration] ID: {reg['registrationId']}")
                    print(f"  Scope: {reg.get('scopeURL', 'N/A')}")
                    print(f"  Is registered: {reg.get('isRegistered', False)}")
            
            elif method == "ServiceWorker.onWorkerVersionUpdated":
                versions = data["params"]["versions"]
                for ver in versions:
                    print(f"[Version] ID: {ver['versionId']}")
                    print(f"  Status: {ver.get('status', 'unknown')}")
                    print(f"  Script: {ver.get('scriptURL', 'N/A')}")
                    running = ver.get("runningStatus", "unknown")
                    print(f"  Running: {running}")
            
            elif method == "ServiceWorker.onWorkerErrorReported":
                err = data["params"]["errorMessage"]
                print(f"[Worker Error] {err.get('errorMessage', '')}")
                print(f"  Line: {err.get('lineNumber', 0)}")
        
        except asyncio.TimeoutError:
            pass


# Usage example
async def example_monitor():
    async with websockets.connect(CDP_URL) as ws:
        await enable_service_worker(ws)
        await monitor_sw_events(ws, duration=20)
```

### Browser Scope vs Page Scope

`ServiceWorker.enable` is a **browser-level** method — it does not need a `sessionId`:

```python
# ✅ Correct: no sessionId needed
await cdp(ws, "ServiceWorker.enable")

# Navigate to a page that uses Service Workers
session_id, _ = await connect_page(ws)
await cdp(ws, "Page.navigate", {
    "url": "https://example-pwa.com"
}, session_id)
await asyncio.sleep(3)
```

---

## Lifecycle Tracking: installing -> activated -> redundant

### Understanding the Service Worker Lifecycle

The worker's state transitions are exposed through `ServiceWorker.onWorkerVersionUpdated`:

| State | Meaning | Trigger |
|-------|---------|---------|
| `installing` | Being installed | Browser downloads and runs the install event |
| `installed` | Installed, waiting to activate | install event completed successfully |
| `activating` | Being activated | activate event started |
| `activated` | Active, can control pages | activate event completed |
| `redundant` | Replaced | New version replaced or manual unregistration |

### Tracking Lifecycle State

```python
class SWLifecycleTracker:
    """Service Worker lifecycle tracker"""
    
    def __init__(self):
        self.versions = {}
        self.registrations = {}
        self.state_history = []
    
    async def start(self, ws, duration=60):
        await enable_service_worker(ws)
        print("Tracking Service Worker lifecycle...\n")
        
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
                            print(f"[Transition] {vid}: {old_status} → {new_status}")
                            print(f"  Script: {event['script']}")
                        
                        self.versions[vid] = ver
                
                elif method == "ServiceWorker.onWorkerRegistrationUpdated":
                    for reg in data["params"]["registrations"]:
                        rid = reg["registrationId"]
                        self.registrations[rid] = reg
                        status = "registered" if reg.get("isRegistered", False) else "unregistered"
                        print(f"[Registration] {rid} → {status}")
                        print(f"  Scope: {reg.get('scopeURL', 'N/A')}")
            
            except asyncio.TimeoutError:
                pass
        
        return self._report()
    
    def _report(self):
        """Generate lifecycle report"""
        print("\n===== Lifecycle Report =====")
        print(f"Versions tracked: {len(self.versions)}")
        print(f"Registrations tracked: {len(self.registrations)}")
        print(f"State transitions: {len(self.state_history)}")
        
        for event in self.state_history:
            print(f"  [{event['from']} → {event['to']}] {event['version_id']}")
        
        active = [v for v in self.versions.values()
                  if v.get("status") == "activated"]
        print(f"\nActive Workers: {len(active)}")
        for v in active:
            print(f"  - {v['versionId']}: {v.get('scriptURL', 'N/A')}")
        
        return {
            "versions": self.versions,
            "registrations": self.registrations,
            "state_history": self.state_history
        }
```

---

## Push Notifications

### Simulating Push Events

While CDP does not directly expose `ServiceWorker.dispatchPushEvent`, you can simulate push notification flows using combined commands:

```python
async def simulate_push_event(ws, session_id, payload="Test Push"):
    """Simulate a push notification via Runtime.evaluate in the page context"""
    await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            navigator.serviceWorker.ready.then(reg => {{
                reg.active.postMessage({{
                    type: 'SIMULATE_PUSH',
                    payload: '{payload}'
                }});
            }});
        """,
        "sessionId": session_id
    }, session_id)
    
    print(f"Push event simulated: {payload}")


async def inspect_service_worker(ws, version_id):
    """Open a Service Worker inspector session"""
    result = await cdp(ws, "ServiceWorker.inspectWorker", {
        "versionId": version_id
    })
    print(f"Worker inspector URL: {result.get('url', 'N/A')}")
    return result
```

### Background Sync Events

```python
async def dispatch_sync_event(ws, tag="sync-data"):
    """Dispatch a background sync event"""
    result = await cdp(ws, "ServiceWorker.dispatchSyncEvent", {
        "tag": tag,
        "lastChance": False
    })
    print(f"Sync event dispatched: tag={tag}")
    return result


async def dispatch_periodic_sync_event(ws, tag="periodic-update"):
    """Dispatch a periodic background sync event"""
    result = await cdp(ws, "ServiceWorker.dispatchPeriodicSyncEvent", {
        "tag": tag
    })
    print(f"Periodic sync event dispatched: tag={tag}")
    return result
```

---

## CacheStorage Operations

### Manipulating Cache via CDP

The `CacheStorage` domain is page-level and requires a `sessionId`:

```python
async def list_caches(ws, session_id, origin=None):
    """List all caches for the given origin"""
    result = await cdp(ws, "CacheStorage.requestCacheNames", {
        "securityOrigin": origin or ""
    }, session_id)
    caches = result.get("caches", [])
    print(f"Found {len(caches)} cache(s):")
    for c in caches:
        print(f"  - {c['cacheName']} (ID: {c['cacheId']})")
    return caches


async def read_cache_entries(ws, session_id, cache_id,
                              skip_count=0, page_size=50):
    """Read entries from a specific cache"""
    result = await cdp(ws, "CacheStorage.requestEntries", {
        "cacheId": cache_id,
        "skipCount": skip_count,
        "pageSize": page_size
    }, session_id)
    entries = result.get("cacheDataEntries", [])
    print(f"Cache entries: {len(entries)}")
    for entry in entries[:10]:
        print(f"  URL: {entry.get('requestURL', 'N/A')}")
        print(f"  Method: {entry.get('requestMethod', 'GET')}")
        print(f"  Status: {entry.get('responseStatus', 0)}")
        headers = entry.get("responseHeaders", [])
        print(f"  Response headers: {len(headers)}")
        print()
    return entries


async def delete_cache_entry(ws, session_id, cache_id, request_url):
    """Delete a specific cache entry"""
    result = await cdp(ws, "CacheStorage.deleteEntry", {
        "cacheId": cache_id,
        "request": request_url
    }, session_id)
    print(f"Deleted cache entry: {request_url}")
    return result


async def delete_cache(ws, session_id, cache_name):
    """Delete an entire cache"""
    result = await cdp(ws, "CacheStorage.deleteCache", {
        "cacheName": cache_name
    }, session_id)
    print(f"Deleted cache: {cache_name}")
    return result
```

### Cache Inspection Demo

```python
async def cache_inspection_demo(ws, session_id):
    """Full cache inspection walkthrough"""
    await cdp(ws, "Page.navigate", {
        "url": "https://your-pwa-site.com"
    }, session_id)
    await asyncio.sleep(5)
    
    caches = await list_caches(ws, session_id)
    if not caches:
        print("No caches found")
        return
    
    total_entries = 0
    total_size = 0
    
    for cache in caches:
        print(f"\n--- Cache: {cache['cacheName']} ---")
        entries = await read_cache_entries(ws, session_id, cache["cacheId"])
        total_entries += len(entries)
        
        for entry in entries:
            headers = {h["name"]: h["value"]
                      for h in entry.get("responseHeaders", [])}
            total_size += int(headers.get("content-length", 0))
    
    print(f"\n===== Cache Summary =====")
    print(f"Caches: {len(caches)}")
    print(f"Total entries: {total_entries}")
    print(f"Total size: {total_size / 1024:.1f} KB")
```

---

## Practical: Offline Cache Health Monitor

Build an offline cache health monitoring system using Service Worker and CacheStorage APIs:

```python
class OfflineCacheMonitor:
    """Offline cache health monitor"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.sw_versions = {}
        self.caches = {}
    
    async def enable(self):
        """Enable all monitoring"""
        await cdp(self.ws, "ServiceWorker.enable")
        print("Service Worker monitoring enabled")
    
    async def take_snapshot(self):
        """Capture current cache snapshot"""
        snapshot = {
            "sw_status": await self._get_sw_status(),
            "cache_status": await self._get_cache_status(),
            "offline_readiness": await self._check_offline_readiness(),
            "timestamp": asyncio.get_event_loop().time()
        }
        return snapshot
    
    async def _get_sw_status(self):
        """Get Service Worker registration status"""
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
        """Get detailed cache status"""
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
                "urls": urls[:20]
            })
        
        return cache_details
    
    async def _check_offline_readiness(self):
        """Check if the app is ready for offline use"""
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
```

---

## Force Update and Skip Waiting

### Skip Waiting

When a new Service Worker version is waiting, use `skipWaiting` to force activation:

```python
async def skip_waiting_and_reload(ws, session_id):
    """Skip the waiting state and activate the new Service Worker immediately"""
    await cdp(ws, "ServiceWorker.enable")
    await cdp(ws, "ServiceWorker.skipWaiting", {"scopeURL": ""})
    print("skipWaiting triggered")
    
    await asyncio.sleep(2)
    await cdp(ws, "Page.reload", {}, session_id)
    await asyncio.sleep(2)
    print("Page reloaded, new Service Worker is now active")


async def unregister_service_worker(ws, registration_id):
    """Unregister a Service Worker by its registration ID"""
    result = await cdp(ws, "ServiceWorker.unregister", {
        "scopeURL": registration_id
    })
    print(f"Unregister result: {result.get('success', False)}")
    return result.get("success", False)


async def force_update_service_worker(ws, session_id):
    """Force update the Service Worker via page context"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            navigator.serviceWorker.getRegistration().then(reg => {
                if (reg) {
                    reg.update().then(() => {
                        console.log('Service Worker force update complete');
                    });
                }
            });
        """,
        "sessionId": session_id,
        "awaitPromise": True
    }, session_id)
    print("Service Worker force update triggered")
    return result
```

### Batch Management

```python
async def cleanup_all_workers(ws, session_id, keep_scope=None):
    """Unregister all Service Workers except the one at keep_scope"""
    cleanup_script = """
        (async () => {
            const registrations = await navigator.serviceWorker.getRegistrations();
            let count = 0;
            for (const reg of registrations) {
                const scope = reg.scope;
                const keep = %s;
                if (keep && scope.includes(keep)) continue;
                await reg.unregister();
                count++;
            }
            return count;
        })()
    """ % (f"'{keep_scope}'" if keep_scope else "null")
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": cleanup_script,
        "sessionId": session_id,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    unregistered = result["result"]["value"]
    print(f"Unregistered {unregistered} Service Worker(s)")
    return unregistered
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: ServiceWorker.enable Needs No sessionId

```python
# ❌ Wrong: passing sessionId
await cdp(ws, "ServiceWorker.enable", {}, session_id)

# ✅ Correct: browser-level, no sessionId
await cdp(ws, "ServiceWorker.enable")
```

### Pitfall 2: CacheStorage Requires sessionId

```python
# ❌ Wrong: no sessionId
await cdp(ws, "CacheStorage.requestCacheNames", {"securityOrigin": ""})

# ✅ Correct: page-level, needs sessionId
await cdp(ws, "CacheStorage.requestCacheNames", {
    "securityOrigin": ""
}, session_id)
```

### Pitfall 3: Wait for SW Activation After Navigation

```python
# ❌ Checking cache immediately (SW may not have intercepted requests)
await cdp(ws, "Page.navigate", {"url": url}, session_id)
await list_caches(ws, session_id)  # May be empty

# ✅ Wait for activation
await cdp(ws, "Page.navigate", {"url": url}, session_id)
await asyncio.sleep(5)
await list_caches(ws, session_id)
```

### Pitfall 4: Secure Context Requirement

Service Workers only work on HTTPS or localhost:

```python
# ❌ HTTP pages cannot register SW
await cdp(ws, "Page.navigate", {"url": "http://example.com"}, session_id)

# ✅ HTTPS or localhost
await cdp(ws, "Page.navigate", {"url": "https://example.com"}, session_id)
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| ServiceWorker domain | Browser-level, no sessionId needed |
| CacheStorage domain | Page-level, sessionId required |
| Wait for activation | Wait 3-5 seconds after navigation |
| Secure context | Use HTTPS or localhost |
| Scope management | Use correct scopeURL for unregister |
| Version tracking | Listen to onWorkerVersionUpdated |
| Cache cleanup | Clear caches between tests for consistency |

---

## Complete Reference: CDP Service Worker Manager Class

```python
import asyncio
import json


class CDPServiceWorkerManager:
    """CDP Service Worker Manager"""

    def __init__(self, ws):
        self.ws = ws
        self._cmd_id = 0
        self.versions = {}
        self.registrations = {}
        self.error_log = []

    async def _cmd(self, method, params=None):
        """Send a browser-level CDP command"""
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})

    async def _cmd_session(self, method, params, session_id):
        """Send a page-level CDP command with sessionId"""
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
        """Enable Service Worker monitoring"""
        return await self._cmd("ServiceWorker.enable")

    async def disable(self):
        """Disable Service Worker monitoring"""
        return await self._cmd("ServiceWorker.disable")

    async def skip_waiting(self, scope_url=""):
        """Skip waiting, activate new version"""
        return await self._cmd("ServiceWorker.skipWaiting", {
            "scopeURL": scope_url
        })

    async def unregister(self, scope_url):
        """Unregister a Service Worker"""
        return await self._cmd("ServiceWorker.unregister", {
            "scopeURL": scope_url
        })

    async def dispatch_sync(self, tag, last_chance=False):
        """Trigger a background sync event"""
        return await self._cmd("ServiceWorker.dispatchSyncEvent", {
            "tag": tag, "lastChance": last_chance
        })

    async def dispatch_periodic_sync(self, tag):
        """Trigger a periodic sync event"""
        return await self._cmd("ServiceWorker.dispatchPeriodicSyncEvent", {
            "tag": tag
        })

    async def inspect_worker(self, version_id):
        """Get the Worker inspector URL"""
        return await self._cmd("ServiceWorker.inspectWorker", {
            "versionId": version_id
        })

    async def list_caches(self, session_id, origin=""):
        """List caches (requires sessionId)"""
        return await self._cmd_session(
            "CacheStorage.requestCacheNames",
            {"securityOrigin": origin}, session_id
        )

    async def read_cache_entries(self, session_id, cache_id,
                                  skip=0, page_size=50):
        """Read cache entries (requires sessionId)"""
        return await self._cmd_session(
            "CacheStorage.requestEntries",
            {"cacheId": cache_id, "skipCount": skip, "pageSize": page_size},
            session_id
        )

    async def delete_cache(self, session_id, cache_name):
        """Delete a cache (requires sessionId)"""
        return await self._cmd_session(
            "CacheStorage.deleteCache",
            {"cacheName": cache_name}, session_id
        )

    async def delete_cache_entry(self, session_id, cache_id, request_url):
        """Delete a cache entry (requires sessionId)"""
        return await self._cmd_session(
            "CacheStorage.deleteEntry",
            {"cacheId": cache_id, "request": request_url}, session_id
        )

    async def collect_events(self, duration=30):
        """Collect Service Worker events over a time period"""
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

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    targets = await cdp(ws, "Target.getTargets")
    page_target = next(t for t in targets["targetInfos"]
                       if t["type"] == "page")
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": page_target["targetId"], "flatten": True
    })
    session_id = session["sessionId"]

    sw_mgr = CDPServiceWorkerManager(ws)
    await sw_mgr.enable()

    await cdp(ws, "Page.navigate", {
        "url": "https://your-pwa-site.com"
    }, session_id)
    await asyncio.sleep(5)

    events = await sw_mgr.collect_events(duration=15)
    print(f"Collected {len(events)} Service Worker events")

    caches = await sw_mgr.list_caches(session_id)
    print(f"Cache count: {len(caches.get('caches', []))}")

    for reg_id in sw_mgr.registrations:
        await sw_mgr.unregister(reg_id)
```

---

> **Summary**: CDP's `ServiceWorker` domain provides browser-level lifecycle management for Service Workers, while the `CacheStorage` domain handles programmatic cache operations. Together they enable fully automated PWA offline debugging, push notification testing, and cache health monitoring.

---

*Previous: CDP File Upload & Download: Handling File Operations with Python*

*Next up: CDP Performance Observer Guide: Monitoring Core Web Vitals with Python*