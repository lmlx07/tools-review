---
lang: en
title: "CDP Frame Management Guide: Handle iframes & Cross-Origin Frames with Python"
date: "2026-06-05 21:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Frame
  - iframe
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to managing browser frames using Chrome DevTools Protocol (CDP). Learn to get the frame tree, execute JavaScript in iframes, handle cross-origin frames, listen to frame lifecycle events, and extract content across all frames.
---

> **Summary in one sentence**: CDP's Page domain provides complete frame management — you can get the full frame tree, execute code in any iframe (including cross-origin), and listen to frame load/detach events.

---

## Table of Contents

1. [Why Use CDP for Frame Management](#why-use-cdp-for-frame-management)
2. [Getting the Frame Tree](#getting-the-frame-tree)
3. [Executing Code in iframes](#executing-code-in-iframes)
4. [Listening to Frame Events](#listening-to-frame-events)
5. [Cross-Origin Frames](#cross-origin-frames)
6. [Practical: Extract All iframe Content](#practical-extract-all-iframe-content)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Frame Management

| Feature | Selenium | CDP |
|---------|----------|-----|
| Get all iframes | ❌ Must traverse | ✅ One-step frame tree |
| Execute JS in iframe | ✅ After switchTo | ✅ Direct frameId targeting |
| Cross-origin iframes | ⚠️ Same-origin limit | ✅ No restrictions |
| Frame lifecycle | ❌ Must poll | ✅ Native events |
| Parent-child relations | ⚠️ Implicit | ✅ Explicit tree structure |

---

## Getting the Frame Tree

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


async def get_frame_tree(ws, session_id):
    result = await cdp(ws, session_id, "Page.getFrameTree")
    return result.get("frameTree", {})


def print_frame_tree(frame_tree, indent=0):
    frame = frame_tree.get("frame", {})
    prefix = "  " * indent
    print(f"{prefix}Frame: {frame.get('id', '')}")
    print(f"{prefix}  URL: {frame.get('url', '')}")
    print(f"{prefix}  Name: {frame.get('name', '(unnamed)')}")
    for child in frame_tree.get("childFrames", []):
        print_frame_tree(child, indent + 1)


def list_frames(tree):
    frames = []
    def walk(node, parent_id=None):
        f = node.get("frame", {})
        frames.append({
            "id": f.get("id"), "url": f.get("url"),
            "name": f.get("name", ""), "parent_id": parent_id
        })
        for child in node.get("childFrames", []):
            walk(child, f.get("id"))
    walk(tree)
    return frames
```

---

## Executing Code in iframes

```python
async def evaluate_in_frame(ws, session_id, frame_id, expression):
    return await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": expression,
        "uniqueContextId": frame_id
    })


async def execute_in_all_frames(ws, session_id, expression):
    tree = await get_frame_tree(ws, session_id)
    results = {}
    
    def walk_and_exec(node):
        f = node.get("frame", {})
        fid = f.get("id")
        if fid:
            try:
                r = await cdp(ws, session_id, "Runtime.evaluate", {
                    "expression": expression, "uniqueContextId": fid
                })
                results[fid] = {"url": f.get("url"), "result": r.get("result", {})}
            except Exception as e:
                results[fid] = {"url": f.get("url"), "error": str(e)}
        for child in node.get("childFrames", []):
            walk_and_exec(child)
    
    walk_and_exec(tree)
    return results


async def get_all_titles(ws, session_id):
    results = await execute_in_all_frames(ws, session_id, "document.title")
    for fid, data in results.items():
        if "result" in data:
            print(f"[{data['url']}] Title: {data['result'].get('value', '')}")
    return results


async def find_frame_by_name(ws, session_id, name):
    tree = await get_frame_tree(ws, session_id)
    def search(node):
        f = node.get("frame", {})
        if f.get("name") == name:
            return f
        for child in node.get("childFrames", []):
            result = search(child)
            if result:
                return result
        return None
    return search(tree)
```

---

## Listening to Frame Events

```python
async def monitor_frames(ws, session_id, duration=30):
    events = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            
            if method.startswith("Page.frame"):
                events.append({"method": method, "params": data.get("params", {})})
                
                if method == "Page.frameAttached":
                    p = data["params"]
                    print(f"[Frame Attached] {p.get('frameId','')}")
                elif method == "Page.frameNavigated":
                    p = data["params"]
                    print(f"[Frame Navigated] {p.get('frame',{}).get('url','')}")
                elif method == "Page.frameDetached":
                    print(f"[Frame Detached]")
                    
        except asyncio.TimeoutError:
            continue
    
    return events
```

---

## Cross-Origin Frames

```python
async def access_cross_origin_frame(ws, session_id, frame_id):
    """CDP has no same-origin restriction for frames"""
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "document.body.innerText.substring(0, 200)",
        "uniqueContextId": frame_id
    })
    return result.get("result", {}).get("value", "")


async def extract_cross_origin_content(ws, session_id):
    tree = await get_frame_tree(ws, session_id)
    contents = {}
    
    def extract(node):
        f = node.get("frame", {})
        fid = f.get("id")
        if fid:
            try:
                r = await cdp(ws, session_id, "Runtime.evaluate", {
                    "expression": "document.body?.innerText || ''",
                    "uniqueContextId": fid
                })
                contents[fid] = {
                    "url": f.get("url"),
                    "content": (r.get("result", {}).get("value", "")[:200])
                }
            except Exception as e:
                contents[fid] = {"url": f.get("url"), "error": str(e)}
        for child in node.get("childFrames", []):
            extract(child)
    
    extract(tree)
    return contents
```

---

## Practical: Extract All Frame Content

```python
async def scrape_all_frames(ws, session_id, url):
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    tree = await get_frame_tree(ws, session_id)
    frames = list_frames(tree)
    
    print(f"Found {len(frames)} frames")
    
    data = {}
    for f in frames:
        fid = f["id"]
        try:
            title_r = await cdp(ws, session_id, "Runtime.evaluate", {
                "expression": "document.title", "uniqueContextId": fid
            })
            links_r = await cdp(ws, session_id, "Runtime.evaluate", {
                "expression": "Array.from(document.querySelectorAll('a')).map(a => a.href)",
                "uniqueContextId": fid, "returnByValue": True
            })
            data[fid] = {
                "url": f["url"],
                "title": title_r.get("result", {}).get("value", ""),
                "links_count": len(links_r.get("result", {}).get("value", [])),
            }
        except Exception as e:
            data[fid] = {"url": f["url"], "error": str(e)}
    
    return data
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: uniqueContextId vs frameId

```python
# In most cases, frameId works directly as uniqueContextId
# But for reliability, re-fetch the frame tree after navigation
```

### Pitfall 2: Stale Frame References

```python
# After iframe navigates, re-fetch frame tree
await cdp(ws, session_id, "Page.navigate", {"url": url})
await asyncio.sleep(2)
tree = await get_frame_tree(ws, session_id)  # Refresh
```

### Pitfall 3: SPA Navigation

```python
# SPA route changes fire navigatedWithinDocument, not frameNavigated
# Frame tree stays the same
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Frame tree | Re-fetch after navigation |
| Execution | frameId works as uniqueContextId in most cases |
| Events | Use frameNavigated/frameStoppedLoading for timing |
| Cross-origin | CDP has no same-origin restrictions |
| Nested frames | Frame tree supports multi-level nesting |

---

## Complete Reference: CDP Frame Manager Class

```python
class CDPFrameManager:
    def __init__(self, ws, session_id):
        self.ws = ws; self.session_id = session_id; self._cmd_id = 0
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        await self.ws.send(json.dumps({
            "sessionId": self.session_id, "id": self._cmd_id,
            "method": method, "params": params or {}
        }))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def get_tree(self):
        return (await self._cmd("Page.getFrameTree")).get("frameTree", {})
    
    def flatten(self, tree=None):
        if tree is None:
            tree = self.get_tree()
        frames = []
        def walk(node, parent=None):
            f = node.get("frame", {})
            frames.append({"id": f.get("id"), "url": f.get("url"),
                          "name": f.get("name"), "parent_id": parent})
            for child in node.get("childFrames", []):
                walk(child, f.get("id"))
        walk(tree)
        return frames
    
    async def eval_in_frame(self, frame_id, expression):
        return await self._cmd("Runtime.evaluate", {
            "expression": expression, "uniqueContextId": frame_id
        })
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    fm = CDPFrameManager(ws, session_id)
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(3)
    frames = fm.flatten()
    results = await fm.eval_all("document.title")
```

---

> **Summary**: CDP's Frame API gives you complete control over browser frames — get the full frame tree, execute JavaScript in any iframe including cross-origin, and listen to frame lifecycle events. This makes multi-frame page automation straightforward.

---

*Previous: CDP Dialog Handling Guide — auto-process alert/confirm/prompt with Python.*

*Next up: CDP Security & Certificate Handling — managing browser security policies and certificates.*
