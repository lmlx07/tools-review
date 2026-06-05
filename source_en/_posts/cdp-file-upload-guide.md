---
lang: en
title: "CDP File Upload & Download: Handling File Operations with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Automation
  - File Upload
  - File Download
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to handling browser file upload and download operations using Chrome DevTools Protocol (CDP). Covers intercepting file chooser dialogs, bypassing file selectors to set file paths directly, listening to download events, configuring download behavior, monitoring download progress, and a complete FileHandler wrapper class.
---

> **Summary in one sentence**: CDP offers a far more elegant approach to file handling than traditional methods — you can bypass OS file dialogs to set upload paths directly, intercept and customize download behavior, and monitor download progress in real time, all at the browser protocol level.

---

## Table of Contents

1. [Why Use CDP for File Operations](#why-use-cdp-for-file-operations)
2. [Prerequisites: Connecting to Chrome](#prerequisites-connecting-to-chrome)
3. [File Upload: Intercepting Dialogs](#file-upload-intercepting-dialogs)
4. [File Upload: Bypassing the Selector](#file-upload-bypassing-the-selector)
5. [File Download: Configuring Behavior](#file-download-configuring-behavior)
6. [Monitoring Download Progress & Events](#monitoring-download-progress--events)
7. [Practical: Auto-Download & Save Files](#practical-auto-download--save-files)
8. [Practical: Batch File Upload](#practical-batch-file-upload)
9. [Complete Reference: CDP FileHandler Class](#complete-reference-cdp-filehandler-class)
10. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for File Operations

Traditional browser automation has many pain points when dealing with file uploads and downloads:

| Scenario | Selenium Approach | CDP Approach |
|----------|-------------------|--------------|
| File upload | Only via send_keys to input[type=file] | ✅ Works with ANY element-triggered upload |
| Custom upload button | ❌ Cannot handle | ✅ Intercept file dialog, provide files |
| Multi-file upload | ⚠️ Unstable | ✅ Reliable multi-file selector |
| Download path control | ⚠️ Depends on browser config | ✅ Set independently per session |
| Download progress | ❌ Not monitorable | ✅ downloadProgress events available |

CDP's unique advantage: you can intercept the file chooser before it appears, inject file paths into any element, and replace the OS file dialog entirely.

---

## Prerequisites: Connecting to Chrome

```python
import asyncio, json, os, websockets

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

async def attach_to_page(ws):
    """Attach to the first page target"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

---

## File Upload: Intercepting Dialogs

### Page.setInterceptFileChooserDialog

This is CDP's most powerful file upload feature — intercept any file chooser dialog triggered by the page, then programmatically provide file paths:

```python
async def enable_file_chooser_interception(ws, session_id, enabled=True):
    """Enable/disable file chooser dialog interception"""
    await cdp(ws, "Page.setInterceptFileChooserDialog", {
        "enabled": enabled
    }, session_id)

async def handle_file_chooser(ws, session_id, file_paths):
    """Handle the intercepted file chooser — provide file paths"""
    await cdp(ws, "Page.handleFileChooser", {
        "action": "accept",
        "files": file_paths if isinstance(file_paths, list) else [file_paths]
    }, session_id)
```

### Complete Upload Flow

```python
async def file_upload_via_intercept(ws, session_id, css_selector, file_paths):
    """Upload files by intercepting the file chooser"""
    # 1. Verify files exist
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    for fp in file_paths:
        if not os.path.exists(fp):
            raise FileNotFoundError(f"File not found: {fp}")
    
    abs_paths = [os.path.abspath(fp) for fp in file_paths]
    
    # 2. Enable file chooser interception
    await enable_file_chooser_interception(ws, session_id)
    
    # 3. Listen for file chooser event in the background
    chooser_future = asyncio.get_event_loop().create_future()
    
    async def event_listener():
        try:
            async with asyncio.timeout(10):
                async for msg in ws:
                    data = json.loads(msg)
                    if "id" in data:
                        continue
                    if data.get("method") == "Page.fileChooserOpened":
                        if not chooser_future.done():
                            chooser_future.set_result(data.get("params", {}))
                        break
        except asyncio.TimeoutError:
            if not chooser_future.done():
                chooser_future.set_exception(TimeoutError("File chooser dialog timeout"))
    
    listener_task = asyncio.create_task(event_listener())
    
    # 4. Trigger the upload action (click the upload button)
    await cdp(ws, "Runtime.evaluate", {
        "expression": f"document.querySelector('{css_selector}').click()"
    }, session_id)
    
    # 5. Wait for chooser event
    await chooser_future
    
    # 6. Provide file paths
    await handle_file_chooser(ws, session_id, abs_paths)
    
    # 7. Cleanup
    listener_task.cancel()
    await enable_file_chooser_interception(ws, session_id, enabled=False)
    
    print(f"Uploaded {len(abs_paths)} file(s):")
    for fp in abs_paths:
        print(f"  - {fp}")
```

### Live Demo

```python
async def demo_file_upload():
    """Demo: upload files to a file hosting site"""
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        
        await cdp(ws, "Page.navigate",
                  {"url": "https://example.com/upload"}, session_id)
        await asyncio.sleep(2)
        
        await file_upload_via_intercept(
            ws, session_id,
            "#upload-button",
            ["C:/test/report.pdf", "C:/test/data.csv"]
        )
```

---

## File Upload: Bypassing the Selector

### DOM.setFileInputFiles

If the page already has an `input[type="file"]` element, you can set files directly — no dialog needed:

```python
async def set_file_input(ws, session_id, css_selector, file_paths):
    """Set files on a file input element directly (bypasses dialog)"""
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    abs_paths = [os.path.abspath(fp) for fp in file_paths]
    
    # Get element via Runtime
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"document.querySelector('{css_selector}')",
        "objectGroup": "files"
    }, session_id)
    
    object_id = result.get("result", {}).get("objectId")
    if not object_id:
        raise ValueError(f"Element not found: {css_selector}")
    
    # Set files directly (bypassing all events)
    await cdp(ws, "DOM.setFileInputFiles", {
        "files": abs_paths,
        "objectId": object_id
    }, session_id)
    
    print(f"Set {len(abs_paths)} file(s): {[os.path.basename(f) for f in abs_paths]}")

# Using Runtime to obtain element reference
async def set_file_input_runtime(ws, session_id, css_selector, file_paths):
    """Obtain element via Runtime then set files"""
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    abs_paths = [os.path.abspath(fp) for fp in file_paths]
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"document.querySelector('{css_selector}')",
        "objectGroup": "files"
    }, session_id)
    
    object_id = result.get("result", {}).get("objectId")
    if not object_id:
        raise ValueError(f"Element not found: {css_selector}")
    
    await cdp(ws, "DOM.setFileInputFiles", {
        "files": abs_paths,
        "objectId": object_id
    }, session_id)
    
    print(f"Files set: {[os.path.basename(f) for f in abs_paths]}")
```

### Upload Method Comparison

| Method | Use Case | Pros | Cons |
|--------|----------|------|------|
| Dialog interception | Custom buttons, drag-drop zones | Covers ALL upload scenarios | Requires async dialog event handling |
| Direct file input | Standard `input[type=file]` | Simple and direct | Only works with standard file inputs |

---

## File Download: Configuring Behavior

### Browser.setDownloadBehavior

By default Chrome shows a download dialog. CDP lets you control this:

```python
async def set_download_behavior(ws, download_path, behavior="allow"):
    """Set download behavior (browser-level, no session_id needed)"""
    await cdp(ws, "Browser.setDownloadBehavior", {
        "behavior": behavior,  # "allow" | "deny" | "default"
        "downloadPath": download_path
    })

async def allow_all_downloads(ws, download_path=None):
    """Allow all downloads and set save directory"""
    if download_path is None:
        download_path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_path, exist_ok=True)
    
    await set_download_behavior(ws, download_path, "allow")
    print(f"Downloads enabled, saving to {os.path.abspath(download_path)}")
    return download_path

async def deny_all_downloads(ws):
    """Block all downloads"""
    await set_download_behavior(ws, "", "deny")
    print("Downloads blocked")
```

### Browser-Level Command Note

`Browser.setDownloadBehavior` is a **browser-level** command — send it without session_id:

```python
async def setup_download(path):
    """Set download path (complete example)"""
    async with websockets.connect(CDP_URL) as ws:
        # Browser-level — no session needed
        await cdp(ws, "Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": os.path.abspath(path)
        })
        print("Download behavior configured")
```

---

## Monitoring Download Progress & Events

### Page.downloadWillBegin

Fires when a page starts downloading:

```python
async def listen_download_events(ws, timeout=60):
    """Listen for download-related events"""
    events = []
    
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "Page.downloadWillBegin":
                    frame_id = params.get("frameId", "")
                    url = params.get("url", "")
                    suggested = params.get("suggestedFilename", "")
                    print(f"[Download Started]")
                    print(f"  URL: {url[:80]}")
                    print(f"  Filename: {suggested}")
                    events.append({
                        "type": "begin",
                        "url": url,
                        "filename": suggested
                    })
                
                elif method == "Page.downloadProgress":
                    state = params.get("state", "")
                    received = params.get("receivedBytes", 0)
                    total = params.get("totalBytes", 0)
                    percent = (received / total * 100) if total > 0 else 0
                    
                    if state == "inProgress":
                        print(f"[Downloading] {percent:.1f}% ({received}/{total} bytes)")
                    elif state == "completed":
                        print(f"[Download Complete] {total} bytes total")
                        events.append({"type": "completed", "bytes": total})
                    elif state == "canceled":
                        print(f"[Download Canceled] {received} bytes received")
                        events.append({"type": "canceled"})
                    
    except asyncio.TimeoutError:
        pass
    
    return events
```

### Complete Download Tracker

```python
class DownloadTracker:
    """Download progress tracker"""
    
    def __init__(self):
        self.downloads = {}
        self._current_id = 0
    
    def _next_id(self):
        self._current_id += 1
        return self._current_id
    
    async def handle_event(self, method, params):
        """Handle download events"""
        if method == "Page.downloadWillBegin":
            dl_id = self._next_id()
            self.downloads[dl_id] = {
                "url": params.get("url", ""),
                "filename": params.get("suggestedFilename", "unknown"),
                "state": "starting",
                "received_bytes": 0,
                "total_bytes": 0,
                "errors": []
            }
            print(f"[{dl_id}] Download started: {self.downloads[dl_id]['filename']}")
            return dl_id
        
        elif method == "Page.downloadProgress":
            guid = params.get("guid", "")
            state = params.get("state", "")
            received = params.get("receivedBytes", 0)
            total = params.get("totalBytes", 0)
            
            for dl_id in reversed(list(self.downloads.keys())):
                dl = self.downloads[dl_id]
                dl["received_bytes"] = received
                dl["total_bytes"] = total
                dl["state"] = state
                
                if state == "completed":
                    print(f"[{dl_id}] Complete: {dl['filename']} ({total} bytes)")
                elif state == "canceled":
                    print(f"[{dl_id}] Canceled")
                return dl_id
        
        return None
    
    def get_downloads(self):
        return dict(self.downloads)
    
    def get_completed(self):
        return {k: v for k, v in self.downloads.items()
                if v["state"] == "completed"}
```

---

## Practical: Auto-Download & Save Files

### Auto-Download from URL

```python
async def auto_download_file(ws, download_url, save_dir="./downloads"):
    """Automatically download a file and monitor progress"""
    save_dir = os.path.abspath(save_dir)
    os.makedirs(save_dir, exist_ok=True)
    
    # 1. Set download path
    await cdp(ws, "Browser.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": save_dir
    })
    
    # 2. Start download event listener
    tracker = DownloadTracker()
    listener_task = asyncio.create_task(
        listen_download_progress(ws, tracker)
    )
    
    # 3. Trigger download (create a tab and navigate to the URL)
    target = await cdp(ws, "Target.createTarget", {"url": download_url})
    target_id = target.get("targetId")
    print(f"Created temp tab to download: {download_url[:60]}...")
    
    # 4. Wait for completion
    await asyncio.sleep(5)
    
    # 5. Close temp tab
    if target_id:
        await cdp(ws, "Target.closeTarget", {"targetId": target_id})
    
    # 6. Return results
    listener_task.cancel()
    completed = tracker.get_completed()
    return completed


async def listen_download_progress(ws, tracker, timeout=30):
    """Continuously listen for download events"""
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                await tracker.handle_event(
                    data.get("method", ""),
                    data.get("params", {})
                )
    except asyncio.TimeoutError:
        pass
```

### Batch Download

```python
async def batch_download(ws, urls, save_dir="./batch_downloads"):
    """Download multiple files in batch"""
    save_dir = os.path.abspath(save_dir)
    os.makedirs(save_dir, exist_ok=True)
    
    await cdp(ws, "Browser.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": save_dir
    })
    
    tracker = DownloadTracker()
    listener = asyncio.create_task(
        listen_download_progress(ws, tracker, timeout=120)
    )
    
    for i, url in enumerate(urls):
        target = await cdp(ws, "Target.createTarget", {"url": url})
        tid = target.get("targetId")
        print(f"[{i+1}/{len(urls)}] Downloading: {url[:50]}...")
        await asyncio.sleep(3)
        if tid:
            await cdp(ws, "Target.closeTarget", {"targetId": tid})
    
    await asyncio.sleep(5)
    listener.cancel()
    
    completed = tracker.get_completed()
    print(f"Completed {len(completed)}/{len(urls)} downloads")
    return completed
```

---

## Practical: Batch File Upload

```python
async def batch_file_upload(ws, session_id, upload_button_selector, file_list):
    """Upload multiple files to the same upload control"""
    abs_files = [os.path.abspath(f) for f in file_list]
    
    for f in abs_files:
        if not os.path.exists(f):
            print(f"Warning: File not found {f}")
    
    existing = [f for f in abs_files if os.path.exists(f)]
    if not existing:
        raise FileNotFoundError("No files available for upload")
    
    print(f"Preparing to upload {len(existing)} file(s)...")
    
    try:
        await enable_file_chooser_interception(ws, session_id)
        
        chooser_event = asyncio.get_event_loop().create_future()
        
        async def wait_chooser():
            async for msg in ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                if data.get("method") == "Page.fileChooserOpened":
                    if not chooser_event.done():
                        chooser_event.set_result(True)
                    break
        
        listener = asyncio.create_task(wait_chooser())
        
        await cdp(ws, "Runtime.evaluate", {
            "expression": f"document.querySelector('{upload_button_selector}').click()"
        }, session_id)
        
        await asyncio.wait_for(chooser_event, timeout=10)
        await handle_file_chooser(ws, session_id, existing)
        
        listener.cancel()
        await enable_file_chooser_interception(ws, session_id, enabled=False)
        
        print("Batch upload complete!")
        
    except asyncio.TimeoutError:
        print("Timeout: file chooser dialog did not appear")
    except Exception as e:
        print(f"Upload error: {e}")
```

---

## Complete Reference: CDP FileHandler Class

```python
import asyncio
import json
import os
import websockets
from typing import List, Optional


class CDPFileHandler:
    """CDP File Handler (upload + download)"""
    
    def __init__(self, ws, session_id=None):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self._downloads = {}
    
    async def _cdp(self, method: str, params: dict = None,
                   session_id: str = None) -> dict:
        """Send CDP command"""
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method,
               "params": params or {}}
        sid = session_id or self.session_id
        if sid:
            msg["sessionId"] = sid
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    # ===== Upload =====
    
    async def enable_chooser_interception(self, enabled: bool = True):
        """Enable/disable file chooser interception"""
        await self._cdp("Page.setInterceptFileChooserDialog",
                       {"enabled": enabled})
    
    async def handle_chooser(self, file_paths: List[str]):
        """Handle file chooser dialog"""
        await self._cdp("Page.handleFileChooser", {
            "action": "accept",
            "files": file_paths
        })
    
    async def upload_via_intercept(self, css_selector: str,
                                   file_paths: List[str]) -> bool:
        """Upload files via dialog interception"""
        abs_paths = [os.path.abspath(f) for f in file_paths
                     if os.path.exists(f)]
        if not abs_paths:
            raise FileNotFoundError("No valid files to upload")
        
        await self.enable_chooser_interception(True)
        
        future = asyncio.get_event_loop().create_future()
        
        async def _wait_chooser():
            async for msg in self.ws:
                data = json.loads(msg)
                if "id" in data:
                    continue
                if data.get("method") == "Page.fileChooserOpened":
                    if not future.done():
                        future.set_result(True)
                    break
        
        listener = asyncio.create_task(_wait_chooser())
        
        await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}').click()"
        })
        
        try:
            await asyncio.wait_for(future, timeout=10)
            await self.handle_chooser(abs_paths)
            return True
        except asyncio.TimeoutError:
            return False
        finally:
            listener.cancel()
            await self.enable_chooser_interception(False)
    
    async def set_file_input(self, css_selector: str,
                             file_paths: List[str]):
        """Set files on a file input element directly"""
        abs_paths = [os.path.abspath(f) for f in file_paths
                     if os.path.exists(f)]
        
        result = await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}')",
            "objectGroup": "files"
        })
        
        object_id = result.get("result", {}).get("objectId")
        if not object_id:
            raise ValueError(f"Element not found: {css_selector}")
        
        await self._cdp("DOM.setFileInputFiles", {
            "files": abs_paths,
            "objectId": object_id
        })
        
        print(f"Files set: {[os.path.basename(f) for f in abs_paths]}")
    
    # ===== Download =====
    
    async def set_download_path(self, path: str, behavior: str = "allow"):
        """Set download path (browser-level command)"""
        os.makedirs(path, exist_ok=True)
        await self._cdp("Browser.setDownloadBehavior", {
            "behavior": behavior,
            "downloadPath": os.path.abspath(path)
        }, session_id=None)
        print(f"Download path: {os.path.abspath(path)}")
    
    async def download_url(self, url: str,
                          save_dir: str = "./downloads") -> Optional[dict]:
        """Download a URL and wait for completion"""
        save_dir = os.path.abspath(save_dir)
        await self.set_download_path(save_dir)
        
        result = await self._cdp("Target.createTarget", {"url": url},
                                session_id=None)
        target_id = result.get("targetId")
        if not target_id:
            return None
        
        await asyncio.sleep(3)
        
        await self._cdp("Target.closeTarget", {"targetId": target_id},
                       session_id=None)
        
        return {"targetId": target_id, "saveDir": save_dir}
    
    # ===== Event Monitoring =====
    
    async def listen_downloads(self, timeout: float = 30) -> List[dict]:
        """Listen for download events and return results"""
        events = []
        
        async def _handler(method: str, params: dict):
            nonlocal events
            if method == "Page.downloadWillBegin":
                events.append({
                    "type": "begin",
                    "url": params.get("url", ""),
                    "filename": params.get("suggestedFilename", "")
                })
                print(f"Download started: {params.get('suggestedFilename', '')}")
            
            elif method == "Page.downloadProgress":
                state = params.get("state", "")
                received = params.get("receivedBytes", 0)
                total = params.get("totalBytes", 0)
                
                if state == "completed":
                    events.append({
                        "type": "completed",
                        "received": received,
                        "total": total
                    })
                    print(f"Download complete: {total} bytes")
                elif state == "canceled":
                    events.append({"type": "canceled"})
                    print("Download canceled")
        
        try:
            async with asyncio.timeout(timeout):
                async for msg in self.ws:
                    data = json.loads(msg)
                    if "id" in data:
                        continue
                    await _handler(data.get("method", ""),
                                  data.get("params", {}))
        except asyncio.TimeoutError:
            pass
        
        return events
```

**Usage example:**

```python
async def demo_file_handler():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        fh = CDPFileHandler(ws, session_id)
        
        # === Upload examples ===
        # Method 1: Dialog interception
        success = await fh.upload_via_intercept(
            "#upload-btn",
            ["C:/test/report.pdf", "C:/test/photo.jpg"]
        )
        print(f"Upload {'succeeded' if success else 'failed'}")
        
        # Method 2: Direct file input setting
        await fh.set_file_input(
            "input[type='file']",
            ["C:/test/document.docx"]
        )
        
        # === Download examples ===
        await fh.set_download_path("./my_downloads")
        
        result = await fh.download_url(
            "https://example.com/file.pdf"
        )
        print(f"Download result: {result}")
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Missing FileChooser Events

```python
# ❌ Click first, then enable interception — dialog event already fired
await cdp(ws, "Runtime.evaluate", {"expression": "uploadBtn.click()"}, session_id)
await cdp(ws, "Page.setInterceptFileChooserDialog", {"enabled": True}, session_id)

# ✅ Enable interception first, then trigger upload
await cdp(ws, "Page.setInterceptFileChooserDialog", {"enabled": True}, session_id)
# Start event listener...
await cdp(ws, "Runtime.evaluate", {"expression": "uploadBtn.click()"}, session_id)
```

### Pitfall 2: File Path Format

```python
# ❌ Windows backslashes may cause issues in some contexts
await set_file_input(ws, session_id, "C:\\Users\\test\\file.txt")

# ✅ Use normalized paths
import os
path = os.path.normpath("C:/Users/test/file.txt")
path = os.path.abspath(path)
await set_file_input(ws, session_id, path)

# Or use forward slashes
await set_file_input(ws, session_id, "C:/Users/test/file.txt")
```

### Pitfall 3: DOM.setFileInputFiles Requires DOM Domain

```python
# ❌ DOM domain not enabled, setFileInputFiles fails
await cdp(ws, "DOM.setFileInputFiles", {...}, session_id)

# ✅ Enable DOM domain first
await cdp(ws, "DOM.enable", session_id=session_id)
await cdp(ws, "DOM.setFileInputFiles", {...}, session_id)
```

### Pitfall 4: Download Path Must Exist

```python
# ❌ Directory doesn't exist, download fails silently
await cdp(ws, "Browser.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": "/nonexistent/path"
})

# ✅ Create directory first
import os
path = os.path.abspath("./downloads")
os.makedirs(path, exist_ok=True)
await cdp(ws, "Browser.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": path
})
```

### Pitfall 5: Browser-Level vs Page-Level Commands

```python
# ❌ Browser-level command with session_id (has no effect)
await cdp(ws, "Browser.setDownloadBehavior", {...}, session_id="XXX")

# ✅ Browser-level command without session_id
await cdp(ws, "Browser.setDownloadBehavior", {...})  # No session_id

# ✅ Page-level command with session_id
await cdp(ws, "Page.setInterceptFileChooserDialog", {"enabled": True}, session_id)
```

### Best Practices Checklist

| Note | Recommendation |
|------|----------------|
| Upload event order | Enable interception first, then trigger click |
| File paths | Use absolute paths + os.path.normpath |
| DOM domain | Enable DOM.enable before setFileInputFiles |
| Download directory | Ensure directory exists before download |
| Command scope | Browser-level: no session_id, Page-level: with session_id |
| Async handling | File dialog requires async event waiting, not sleep-based guessing |
| Resource cleanup | Close temp tabs and restore interception settings after use |

---

> **Summary**: CDP's file handling API provides far superior upload and download control compared to traditional automation tools. By intercepting file chooser dialogs, you can handle any upload interface; by configuring download behavior, you can silently save any file. Combined with the FileHandler wrapper class, file operations will no longer be a bottleneck in your automation workflows.

*Previous: CDP Input Automation Guide: Simulating Mouse & Keyboard with Python*

*Next up: CDP Service Worker Management: Debugging Offline Cache with Python*