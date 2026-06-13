---
lang: en
title: "CDP Target Management: Controlling Multiple Pages with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Automation
  - Multi-Tab
  - Target
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to managing multiple browser tabs using Chrome DevTools Protocol (CDP). Learn how to list all targets, create new tabs, attach to specific pages, switch between tabs, listen for target lifecycle events, isolate sessions per tab, and a complete TargetManager wrapper class.
---

> **Summary in one sentence**: CDP's Target domain lets you control all browser tabs like a window manager — you can list every open page, create new tabs, attach and switch to any page, listen for tab creation and destruction events, and each connection gets its own isolated Session context.

---

## Table of Contents

1. [Why Multi-Tab Management Matters](#why-multi-tab-management-matters)
2. [Prerequisites: Connecting to Chrome](#prerequisites-connecting-to-chrome)
3. [Listing All Targets](#listing-all-targets)
4. [Creating New Tabs](#creating-new-tabs)
5. [Attaching to Specific Targets](#attaching-to-specific-targets)
6. [Switching Between Tabs](#switching-between-tabs)
7. [Monitoring Target Changes](#monitoring-target-changes)
8. [Closing Tabs](#closing-tabs)
9. [Complete Reference: CDP TargetManager Class](#complete-reference-cdp-targetmanager-class)
10. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Multi-Tab Management Matters

Single-page automation often falls short in real-world scenarios:

| Scenario | Description |
|----------|-------------|
| Multi-tasking | Monitor multiple pages simultaneously, e.g., compare prices across two e-commerce sites |
| Page isolation | Main tab handles login, a new tab performs sensitive operations |
| Crawler acceleration | Concurrent requests across multiple tabs to boost data collection |
| Window management | Automatically open/close promotional links to keep the browser tidy |
| Anti-detection | Different tabs using different fingerprints or contexts |

CDP's Target domain provides complete lifecycle management for browser tabs. CDP concepts vs browser equivalents:

| CDP Concept | Browser Equivalent |
|-------------|-------------------|
| Target | Tab, iframe, Service Worker, etc. |
| TargetID | Unique identifier for each tab |
| Session | Communication channel to a specific tab |
| Browser Context | Isolated browsing context (like incognito window) |

---

## Prerequisites: Connecting to Chrome

Using the standard CDP connection pattern:

```python
import asyncio, json, websockets

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    """Send a CDP command and wait for its response"""
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id:
        msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]:
            return data.get("result", {})
```

> **Note**: You must use the `devtools/browser` endpoint (not a single page's WebSocket URL) for `Target` domain commands to work across all tabs.

---

## Listing All Targets

### Target.getTargets

The most basic operation — listing all visible targets in the browser:

```python
async def list_all_targets(ws):
    """List all target information"""
    result = await cdp(ws, "Target.getTargets")
    targets = result.get("targetInfos", [])
    
    for t in targets:
        print(f"ID: {t['targetId'][:12]}...")
        print(f"  Title: {t.get('title', '')}")
        print(f"  URL: {t.get('url', '')[:60]}")
        print(f"  Type: {t.get('type', '')}")
        print(f"  Attached: {'Yes' if t.get('attached') else 'No'}")
        print()
    return targets

# Usage
async def demo_list_targets():
    async with websockets.connect(CDP_URL) as ws:
        targets = await list_all_targets(ws)
        print(f"Total {len(targets)} targets")
```

Sample output:

```
ID: 3A1B2C3D4E5F...
  Title: Hacker News
  URL: https://news.ycombinator.com/
  Type: page
  Attached: No

ID: 6G7H8I9J0K1L...
  Title: New Tab
  URL: chrome://new-tab-page/
  Type: page
  Attached: No
```

### Filtering by Target Type

The `type` field in `targetInfo` distinguishes different target kinds:

```python
async def get_pages_only(ws):
    """Get only page-type targets"""
    result = await cdp(ws, "Target.getTargets")
    pages = [t for t in result.get("targetInfos", [])
             if t.get("type") == "page"]
    return pages

async def get_active_page(ws):
    """Get the active tab (usually the first page)"""
    pages = await get_pages_only(ws)
    return pages[0] if pages else None
```

---

## Creating New Tabs

### Target.createTarget

Open a blank new tab or navigate to a specific URL:

```python
async def create_new_tab(ws, url="about:blank", width=None, height=None):
    """Create a new tab"""
    params = {"url": url}
    if width and height:
        params["width"] = width
        params["height"] = height
    
    result = await cdp(ws, "Target.createTarget", params)
    target_id = result.get("targetId")
    print(f"New tab created, ID: {target_id}")
    return target_id

# Usage
async def demo_create_tab():
    async with websockets.connect(CDP_URL) as ws:
        # Create blank page
        blank_id = await create_new_tab(ws)
        print(f"Blank tab: {blank_id}")
        
        # Open specific URL
        url_id = await create_new_tab(ws, "https://example.com")
        print(f"Navigated tab: {url_id}")
        
        # Create with custom size
        sized_id = await create_new_tab(ws, "about:blank", 800, 600)
```

### Opening in a New Window

Set `newWindow=True` to open the target in a new window instead:

```python
async def create_new_window(ws, url="about:blank"):
    """Create a target in a new window"""
    result = await cdp(ws, "Target.createTarget", {
        "url": url,
        "newWindow": True
    })
    target_id = result.get("targetId")
    print(f"New window target created, ID: {target_id}")
    return target_id
```

---

## Attaching to Specific Targets

### Target.attachToTarget

After creating a new tab, you need to establish a Session before you can control it:

```python
async def attach_to_target(ws, target_id):
    """Attach to a specific target"""
    result = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id,
        "flatten": True  # flatten mode is recommended
    })
    session_id = result.get("sessionId")
    print(f"Attached to {target_id[:12]}..., Session: {session_id[:12]}...")
    return session_id
```

### Understanding flatten Mode

With `flatten: True`, all commands go through a single WebSocket with `sessionId` routing, instead of creating separate WebSockets for each session:

```python
# flatten=True (recommended): single WS + sessionId routing
async def operate_via_flatten(ws, session_id):
    await cdp(ws, "Page.navigate",
              {"url": "https://example.com"}, session_id=session_id)
    result = await cdp(ws, "Runtime.evaluate",
              {"expression": "document.title"}, session_id=session_id)
    return result.get("result", {}).get("value")

# flatten=False (not recommended): returns a separate WebSocket URL
# Requires opening independent connections per target
```

---

## Switching Between Tabs

### Practical Multi-Tab Demo

```python
async def demo_multi_tab():
    async with websockets.connect(CDP_URL) as ws:
        # 1. Create three tabs
        target_a = await create_new_tab(ws, "https://news.ycombinator.com")
        target_b = await create_new_tab(ws, "https://www.reddit.com")
        target_c = await create_new_tab(ws, "https://github.com")
        
        # 2. Establish sessions for each tab
        session_a = await attach_to_target(ws, target_a)
        session_b = await attach_to_target(ws, target_b)
        session_c = await attach_to_target(ws, target_c)
        
        # 3. Operate on each page independently
        # Page A: get title
        result_a = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_a)
        title_a = result_a.get("result", {}).get("value", "")
        print(f"Tab A title: {title_a}")
        
        # Page B: get title
        result_b = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_b)
        title_b = result_b.get("result", {}).get("value", "")
        print(f"Tab B title: {title_b}")
        
        # Page C: get title
        result_c = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_c)
        title_c = result_c.get("result", {}).get("value", "")
        print(f"Tab C title: {title_c}")
```

### Finding Targets by URL Pattern

Search for specific targets across multiple tabs:

```python
async def find_target_by_url(ws, url_pattern):
    """Find a target matching a URL pattern"""
    result = await cdp(ws, "Target.getTargets")
    for t in result.get("targetInfos", []):
        if url_pattern in t.get("url", ""):
            print(f"Found match: {t.get('title')} @ {t.get('url')[:60]}")
            return t
    return None

async def find_target_by_title(ws, title_pattern):
    """Find a target matching a title pattern"""
    result = await cdp(ws, "Target.getTargets")
    for t in result.get("targetInfos", []):
        if title_pattern.lower() in t.get("title", "").lower():
            return t
    return None
```

### Parallel Operations Across Tabs

Use `asyncio.gather` for concurrent tab operations:

```python
async def get_page_title(ws, session_id):
    """Get a single tab's title"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": "document.title"
    }, session_id)
    return result.get("result", {}).get("value", "N/A")

async def parallel_tab_operation(ws, sessions_and_urls):
    """Fetch info from multiple tabs in parallel"""
    tasks = []
    for session_id, url in sessions_and_urls:
        task = asyncio.create_task(get_page_title(ws, session_id))
        tasks.append(task)
    
    titles = await asyncio.gather(*tasks)
    for (session_id, url), title in zip(sessions_and_urls, titles):
        print(f"[{url[:30]}...] → {title}")
    return titles
```

---

## Monitoring Target Changes

### Target.setDiscoverTargets

Enable real-time monitoring of tab creation, destruction, and updates:

```python
async def target_event_listener(ws, timeout=60):
    """Listen for target lifecycle events"""
    await cdp(ws, "Target.setDiscoverTargets", {"discover": True})
    
    print("Listening for target changes...")
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Target.targetCreated":
                    info = params.get("targetInfo", {})
                    print(f"[Created] New tab: {info.get('title', '')}")
                    print(f"          URL: {info.get('url', '')[:60]}")
                    print(f"          Type: {info.get('type', '')}")
                    print(f"          ID: {info.get('targetId', '')[:16]}...")
                
                elif method == "Target.targetDestroyed":
                    tid = params.get("targetId", "")
                    print(f"[Destroyed] Tab {tid[:16]}...")
                
                elif method == "Target.targetInfoChanged":
                    info = params.get("targetInfo", {})
                    print(f"[Updated] {info.get('title', '')} - {info.get('url', '')[:50]}")
    except asyncio.TimeoutError:
        print("Listening finished")
```

### Using Events for Tab Management

```python
async def demo_target_watcher():
    """Demo: listen for target changes + auto-operate"""
    async with websockets.connect(CDP_URL) as ws:
        # Start listener in background
        listener = asyncio.create_task(
            target_event_listener(ws, timeout=20)
        )
        
        await asyncio.sleep(1)  # Ensure listener is ready
        
        # Create new tab (triggers targetCreated)
        tid = await create_new_tab(ws, "https://example.com")
        print(f"Manually created tab: {tid[:12]}...")
        
        await asyncio.sleep(2)
        
        # Close tab (triggers targetDestroyed)
        await cdp(ws, "Target.closeTarget", {"targetId": tid})
        print(f"Manually closed tab: {tid[:12]}...")
        
        await listener
```

---

## Closing Tabs

### Target.closeTarget

```python
async def close_target(ws, target_id):
    """Close a specific tab"""
    try:
        result = await cdp(ws, "Target.closeTarget", {"targetId": target_id})
        success = result.get("success", False)
        if success:
            print(f"Tab {target_id[:12]}... closed")
        else:
            print(f"Failed to close: {target_id[:12]}...")
        return success
    except Exception as e:
        print(f"Close exception: {e}")
        return False

async def close_all_targets(ws, exclude_current=True):
    """Close all tabs (optionally excluding the current one)"""
    result = await cdp(ws, "Target.getTargets")
    targets = result.get("targetInfos", [])
    current_id = None
    
    if exclude_current and targets:
        current_id = targets[0].get("targetId") if targets else None
    
    closed = 0
    for t in targets:
        tid = t.get("targetId")
        if exclude_current and tid == current_id:
            continue
        if await close_target(ws, tid):
            closed += 1
    
    print(f"Closed {closed} tabs total")
    return closed
```

### Batch Close by Type

```python
async def close_targets_by_type(ws, target_type="page"):
    """Batch close targets by type"""
    result = await cdp(ws, "Target.getTargets")
    targets = [t for t in result.get("targetInfos", [])
               if t.get("type") == target_type]
    
    count = 0
    for t in targets:
        if await close_target(ws, t["targetId"]):
            count += 1
    
    print(f"Closed {count} targets of type '{target_type}'")
    return count
```

---

## Complete Reference: CDP TargetManager Class

```python
import asyncio
import json
import websockets
from typing import Optional, List, Dict, Callable


class CDPTargetManager:
    """CDP Multi-Tab Manager"""
    
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._sessions: Dict[str, str] = {}  # targetId → sessionId
        self._cmd_id = 0
    
    async def connect(self):
        """Establish WebSocket connection"""
        self.ws = await websockets.connect(self.ws_url)
        return self
    
    async def disconnect(self):
        """Close connection"""
        if self.ws:
            await self.ws.close()
            self.ws = None
    
    async def _cdp(self, method: str, params: dict = None,
                   session_id: str = None) -> dict:
        """Send CDP command"""
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method,
               "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def list_targets(self, target_type: str = None) -> List[dict]:
        """List all targets, optionally filter by type"""
        result = await self._cdp("Target.getTargets")
        targets = result.get("targetInfos", [])
        if target_type:
            targets = [t for t in targets if t.get("type") == target_type]
        return targets
    
    async def create_target(self, url: str = "about:blank",
                           width: int = None, height: int = None,
                           new_window: bool = False) -> str:
        """Create a new target, returns targetId"""
        params = {"url": url}
        if width and height:
            params["width"] = width
            params["height"] = height
        if new_window:
            params["newWindow"] = True
        result = await self._cdp("Target.createTarget", params)
        return result.get("targetId")
    
    async def attach(self, target_id: str) -> str:
        """Attach to a target, returns sessionId"""
        result = await self._cdp("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = result.get("sessionId")
        self._sessions[target_id] = session_id
        return session_id
    
    async def detach(self, target_id: str):
        """Detach from a target"""
        session_id = self._sessions.get(target_id)
        if session_id:
            await self._cdp("Target.detachFromTarget",
                          {"sessionId": session_id})
            self._sessions.pop(target_id, None)
    
    async def close_target(self, target_id: str) -> bool:
        """Close a target"""
        result = await self._cdp("Target.closeTarget",
                                {"targetId": target_id})
        self._sessions.pop(target_id, None)
        return result.get("success", False)
    
    async def navigate(self, target_id: str, url: str) -> dict:
        """Navigate in a specific tab"""
        session_id = self._sessions.get(target_id)
        if not session_id:
            raise ValueError(f"Not attached to target {target_id}")
        return await self._cdp("Page.navigate",
                              {"url": url}, session_id)
    
    async def evaluate(self, target_id: str, expression: str) -> dict:
        """Execute JS in a specific tab"""
        session_id = self._sessions.get(target_id)
        if not session_id:
            raise ValueError(f"Not attached to target {target_id}")
        return await self._cdp("Runtime.evaluate",
                              {"expression": expression}, session_id)
    
    async def activate_target(self, target_id: str):
        """Bring a target to the foreground"""
        await self._cdp("Target.activateTarget",
                       {"targetId": target_id})
    
    async def find_target(self, url_pattern: str = None,
                         title_pattern: str = None) -> Optional[dict]:
        """Find a target by URL or title pattern"""
        targets = await self.list_targets()
        for t in targets:
            url = t.get("url", "")
            title = t.get("title", "")
            if url_pattern and url_pattern in url:
                return t
            if title_pattern and title_pattern.lower() in title.lower():
                return t
        return None
    
    async def set_discover_targets(self, discover: bool = True):
        """Enable/disable target discovery"""
        await self._cdp("Target.setDiscoverTargets",
                       {"discover": discover})
    
    async def get_session(self, target_id: str) -> Optional[str]:
        """Get sessionId for a target"""
        return self._sessions.get(target_id)
    
    def get_attached_targets(self) -> List[str]:
        """Get all attached target IDs"""
        return list(self._sessions.keys())
    
    # ----- Advanced Methods -----
    
    async def create_with_attach(self, url: str = "about:blank") -> tuple:
        """Create a tab and auto-attach, returns (targetId, sessionId)"""
        target_id = await self.create_target(url)
        session_id = await self.attach(target_id)
        return target_id, session_id
    
    async def close_all_pages(self, exclude_ids: List[str] = None):
        """Close all page-type targets"""
        exclude = set(exclude_ids or [])
        targets = await self.list_targets("page")
        count = 0
        for t in targets:
            tid = t["targetId"]
            if tid not in exclude:
                if await self.close_target(tid):
                    count += 1
        return count
    
    async def snapshot_all_titles(self) -> Dict[str, str]:
        """Get titles of all attached targets"""
        results = {}
        tasks = []
        for tid in self._sessions:
            tasks.append(self.evaluate(tid, "document.title"))
        
        if tasks:
            titles = await asyncio.gather(*tasks, return_exceptions=True)
            for tid, title_result in zip(self._sessions.keys(), titles):
                if isinstance(title_result, Exception):
                    results[tid] = f"Error: {title_result}"
                else:
                    val = title_result.get("result", {}).get("value", "")
                    results[tid] = val
        return results
```

**Usage example:**

```python
async def demo_target_manager():
    mgr = CDPTargetManager(CDP_URL)
    await mgr.connect()
    
    # List all current tabs
    targets = await mgr.list_targets("page")
    print(f"Currently {len(targets)} tabs")
    
    # Create three tabs
    urls = [
        "https://news.ycombinator.com",
        "https://www.reddit.com",
        "https://github.com"
    ]
    target_ids = []
    for url in urls:
        tid, sid = await mgr.create_with_attach(url)
        target_ids.append(tid)
        print(f"Created and attached: {tid[:12]}...")
    
    await asyncio.sleep(3)  # Wait for load
    
    # Get all titles
    titles = await mgr.snapshot_all_titles()
    for tid, title in titles.items():
        print(f"  [{tid[:12]}...] {title}")
    
    # Activate a specific tab
    await mgr.activate_target(target_ids[0])
    
    # Close all new tabs
    for tid in target_ids:
        await mgr.close_target(tid)
    
    await mgr.disconnect()
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Wrong WebSocket URL

There are two types of WebSocket URLs:

```python
# ❌ Single-page WS URL (cannot manage other tabs)
page_ws_url = "ws://127.0.0.1:9222/devtools/page/3A1B2C..."
async with websockets.connect(page_ws_url) as ws:
    # Target.getTargets will NOT work here!

# ✅ Browser-level WS URL (manages ALL tabs)
browser_ws_url = "ws://127.0.0.1:9222/devtools/browser/6G7H8I..."
async with websockets.connect(browser_ws_url) as ws:
    result = await cdp(ws, "Target.getTargets")  # ✅ Works
```

### Pitfall 2: Forgetting to Enable Required Domains

```python
# ❌ Navigate without enabling the Page domain
await mgr.navigate(target_id, "https://example.com")

# ✅ Must enable required domains first
session_id = mgr.get_session(target_id)
await mgr._cdp("Page.enable", session_id=session_id)
await mgr._cdp("Network.enable", session_id=session_id)
await mgr.navigate(target_id, "https://example.com")
```

### Pitfall 3: Session Isolation

Each tab's session is independent — never mix them:

```python
# ❌ Wrong: using session_a to operate target_b
result = await cdp(ws, "Runtime.evaluate",
    {"expression": "document.title"}, session_id=session_a)  # But target_b needs session_b

# ✅ Correct: each target has its own session
result = await cdp(ws, "Runtime.evaluate",
    {"expression": "document.title"}, session_id=session_b)
```

### Pitfall 4: Operating on Destroyed Targets

```python
# ❌ Continue sending commands after closing
await mgr.close_target(target_id)
await mgr.navigate(target_id, "https://example.com")  # Error!

# ✅ Clean up references after closing
await mgr.close_target(target_id)
assert target_id not in mgr.get_attached_targets()
```

### Best Practices Checklist

| Note | Recommendation |
|------|----------------|
| Connection URL | Always use `devtools/browser/` path |
| flatten mode | Recommended, simplifies connection management |
| Session mapping | Maintain a targetId → sessionId dictionary |
| Resource cleanup | Detach/close after use to prevent leaks |
| Concurrency control | Use semaphores to limit parallel operations |
| Error handling | Wrap each tab operation in individual try/except |

---

> **Summary**: CDP's Target domain provides complete multi-tab management capabilities for browser automation. With the TargetManager wrapper class, you can easily handle the full lifecycle of tab creation, attachment, switching, and closing — with each tab maintaining its own isolated Session context.

*Previous: CDP Event System Guide: Listening to Browser Events with Python*

*Next up: CDP Input Automation Guide: Simulating Mouse & Keyboard with Python*