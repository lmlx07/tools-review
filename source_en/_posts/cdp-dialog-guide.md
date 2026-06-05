---
lang: en
title: "CDP Dialog Handling Guide: Auto-Process alert/confirm/prompt with Python"
date: "2026-06-05 20:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Dialog
  - Browser Automation
  - Popup Handling
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to handling browser dialogs with Chrome DevTools Protocol (CDP). Learn to auto-dismiss alerts, accept/decline confirms, fill prompt inputs, handle beforeunload events, and keep automation flows running without interruption.
---

> **Summary in one sentence**: CDP's `Page.javascriptDialogOpening` event lets you intercept all browser dialogs — alert, confirm, prompt, beforeunload — and programmatically decide to accept, dismiss, or input text.

---

## Table of Contents

1. [Why Use CDP for Dialog Handling](#why-use-cdp-for-dialog-handling)
2. [Listening for Dialog Events](#listening-for-dialog-events)
3. [Auto-Processing Dialogs](#auto-processing-dialogs)
4. [Handling beforeunload](#handling-beforeunload)
5. [Practical: Interruption-Free Automation](#practical-interruption-free-automation)
6. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Dialog Handling

| Feature | Selenium | CDP |
|---------|----------|-----|
| alert handling | ✅ switchTo().alert() | ✅ Page.javascriptDialogOpening event |
| confirm handling | ✅ Same | ✅ Choose accept/dismiss |
| prompt text input | ✅ sendKeys() | ✅ Preset prompt text |
| beforeunload | ⚠️ Difficult | ✅ Native support |
| Non-blocking flow | ❌ Blocks execution | ✅ Event-driven, non-blocking |
| Dialog content | ✅ Get text | ✅ Get type + message |

---

## Listening for Dialog Events

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


async def listen_for_dialogs(ws, session_id, duration=10):
    dialogs = []
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            if data.get("method") == "Page.javascriptDialogOpening":
                params = data["params"]
                dialogs.append({
                    "type": params.get("type"),
                    "message": params.get("message", ""),
                    "default_prompt": params.get("defaultPrompt", "")
                })
                print(f"[Dialog] {params.get('type')}: {params.get('message', '')[:50]}")
        except asyncio.TimeoutError:
            continue
    return dialogs
```

---

## Auto-Processing Dialogs

```python
async def smart_handle_dialogs(ws, session_id, duration=30):
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "Page.javascriptDialogOpening":
                params = data["params"]
                dtype = params.get("type")
                
                if dtype == "alert":
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": True})
                    
                elif dtype == "confirm":
                    accept = "delete" not in params.get("message", "").lower()
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": accept})
                
                elif dtype == "prompt":
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                        "accept": True, "promptText": "auto_filled_value"
                    })
                
                elif dtype == "beforeunload":
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": True})
                    
        except asyncio.TimeoutError:
            continue


class DialogHandler:
    def __init__(self, ws, session_id):
        self.ws = ws; self.session_id = session_id
        self._cmd_id = 0; self.dialogs_log = []
    
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
    
    async def accept_all(self):
        async for msg in self.ws:
            data = json.loads(msg)
            if data.get("method") == "Page.javascriptDialogOpening":
                self.dialogs_log.append(data["params"])
                await self._cmd("Page.handleJavaScriptDialog", {"accept": True})
    
    async def fill_prompt(self, text):
        await self._cmd("Page.handleJavaScriptDialog", {
            "accept": True, "promptText": text
        })
```

---

## Handling beforeunload

```python
async def handle_beforeunload(ws, session_id, accept=True):
    return await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
        "accept": accept
    })

async def navigate_ignore_beforeunload(ws, session_id, url):
    return await cdp(ws, session_id, "Page.navigate", {
        "url": url,
        "handleBeforeUnload": True
    })
```

---

## Practical: Interruption-Free Automation

```python
async def automated_test_with_dialogs(ws, session_id, url):
    async def dialog_watcher():
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                if data.get("method") == "Page.javascriptDialogOpening":
                    p = data["params"]
                    print(f"[Dialog] {p.get('type')}: {p.get('message', '')[:60]}")
                    if p.get("type") == "prompt":
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True, "promptText": "test_value"
                        })
                    else:
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True
                        })
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    watcher = asyncio.create_task(dialog_watcher())
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(5)
    watcher.cancel()
    print("Test complete — all dialogs handled automatically")
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Handle Dialogs Immediately

```python
# ❌ Too slow — dialog may timeout
if data.get("method") == "Page.javascriptDialogOpening":
    await asyncio.sleep(5)  # Dialog may auto-dismiss or block
    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": True})

# ✅ Handle immediately
if data.get("method") == "Page.javascriptDialogOpening":
    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": True})
```

### Pitfall 2: promptText Only with accept=True

```python
# ❌ promptText ignored when accept=False
await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
    "accept": False, "promptText": "text"  # Ignored
})

# ✅ promptText only with accept=True
await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
    "accept": True, "promptText": "text"
})
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Handle promptly | Process dialogOpening event immediately |
| Background listener | Use asyncio.create_task for dialog watching |
| promptText | Only use with accept=True |
| beforeunload | Accept in automation scenarios |
| Logging | Record dialog type and message |
| Timeout | Dialogs may have browser-level timeout |

---

## Complete Reference: CDP Dialog Handler Class

```python
class CDPDialogHandler:
    def __init__(self, ws, session_id):
        self.ws = ws; self.session_id = session_id
        self._cmd_id = 0; self.dialogs = []
    
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
    
    async def start_auto_accept(self):
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                if data.get("method") == "Page.javascriptDialogOpening":
                    self.dialogs.append(data["params"])
                    await self._cmd("Page.handleJavaScriptDialog", {"accept": True})
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    async def accept(self, prompt_text=None):
        params = {"accept": True}
        if prompt_text: params["promptText"] = prompt_text
        await self._cmd("Page.handleJavaScriptDialog", params)
    
    async def dismiss(self):
        await self._cmd("Page.handleJavaScriptDialog", {"accept": False})
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    dlg = CDPDialogHandler(ws, session_id)
    handler = asyncio.create_task(dlg.start_auto_accept())
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(5)
    handler.cancel()
```

---

> **Summary**: CDP's dialog events give you elegant control over page popups — auto-dismiss alerts, selectively accept confirms, fill prompts with preset text, and handle beforeunload cleanly — keeping automation flows interruption-free.

---

*Previous: CDP Storage Operations Guide — manage LocalStorage, IndexedDB & Cache with Python.*

*Next up: CDP Frame Management — navigating iframes and cross-origin frames.*
