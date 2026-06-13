---
title: CDP 文件上传与下载：用 Python 处理文件操作
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 浏览器自动化
  - 文件上传
  - 文件下载
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）处理浏览器文件上传和下载。涵盖拦截文件选择对话框、绕过文件选择器直接设置文件路径、监听下载开始事件、设置下载行为、监控下载进度，以及完整的 FileHandler 封装类。
---

> **一句话总结**：CDP 提供了比传统方法更优雅的文件处理方案——你可以绕过操作系统文件对话框直接设置上传文件、拦截并定制下载行为、实时监控下载进度，所有操作都在浏览器协议层面完成。

---

## 目录

1. [为什么用 CDP 处理文件操作](#为什么用-cdp-处理文件操作)
2. [前置准备：连接 Chrome](#前置准备连接-chrome)
3. [文件上传：拦截对话框方式](#文件上传拦截对话框方式)
4. [文件上传：绕过选择器直接设置](#文件上传绕过选择器直接设置)
5. [文件下载：设置下载行为](#文件下载设置下载行为)
6. [监控下载进度与事件](#监控下载进度与事件)
7. [实战：自动下载文件并保存](#实战自动下载文件并保存)
8. [实战：批量文件上传](#实战批量文件上传)
9. [完整参考：CDP FileHandler 类](#完整参考cdp-filehandler-类)
10. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 处理文件操作

传统浏览器自动化在处理文件上传和下载时有很多痛点：

| 场景 | Selenium 方案 | CDP 方案 |
|------|-------------|---------|
| 文件上传 | 只能用 send_keys 到 input[type=file] | ✅ 任何元素触发的上传都能处理 |
| 自定义上传按钮 | ❌ 无法操作（不是文件输入框） | ✅ 拦截文件对话框，指定文件 |
| 多文件上传 | ⚠️ 不稳定 | ✅ 可靠的多文件选择器设置 |
| 下载路径控制 | ⚠️ 依赖浏览器配置 | ✅ 每次会话可独立设置 |
| 下载进度监控 | ❌ 无法监控 | ✅ 收到 downloadProgress 事件 |

CDP 的独特优势：你可以在不上传文件的情况下拦截文件选择器、为任意元素注入文件路径、甚至在用户点击上传按钮时代替操作系统对话框。

---

## 前置准备：连接 Chrome

```python
import asyncio, json, os, websockets

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    """发送 CDP 命令并等待返回"""
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
    """连接到页面目标并返回 session_id"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

---

## 文件上传：拦截对话框方式

### Page.setInterceptFileChooserDialog

这是 CDP 最强大的文件上传功能——拦截任何由页面触发的文件选择对话框，然后程序化地提供文件路径：

```python
async def enable_file_chooser_interception(ws, session_id, enabled=True):
    """启用/禁用文件选择对话框拦截"""
    await cdp(ws, "Page.setInterceptFileChooserDialog", {
        "enabled": enabled
    }, session_id)

async def handle_file_chooser(ws, session_id, file_paths):
    """处理拦截到的文件选择对话框——提供文件路径"""
    await cdp(ws, "Page.handleFileChooser", {
        "action": "accept",
        "files": file_paths if isinstance(file_paths, list) else [file_paths]
    }, session_id)
```

### 完整的上传流程

```python
async def file_upload_via_intercept(ws, session_id, css_selector, file_paths):
    """通过拦截文件对话框上传文件"""
    # 1. 确保文件存在
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    for fp in file_paths:
        if not os.path.exists(fp):
            raise FileNotFoundError(f"文件不存在: {fp}")
    
    abs_paths = [os.path.abspath(fp) for fp in file_paths]
    
    # 2. 启用文件选择拦截
    await enable_file_chooser_interception(ws, session_id)
    
    # 3. 在后台监听文件选择对话框事件
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
                chooser_future.set_exception(TimeoutError("等待文件对话框超时"))
    
    listener_task = asyncio.create_task(event_listener())
    
    # 4. 触发上传操作（点击上传按钮）
    await cdp(ws, "Runtime.evaluate", {
        "expression": f"document.querySelector('{css_selector}').click()"
    }, session_id)
    
    # 5. 等待对话框事件
    await chooser_future
    
    # 6. 提供文件路径
    await handle_file_chooser(ws, session_id, abs_paths)
    
    # 7. 清理
    listener_task.cancel()
    await enable_file_chooser_interception(ws, session_id, enabled=False)
    
    print(f"已上传 {len(abs_paths)} 个文件:")
    for fp in abs_paths:
        print(f"  - {fp}")
```

### 实际演示

```python
async def demo_file_upload():
    """演示：上传文件到文件托管网站"""
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        
        # 导航到文件上传页面
        await cdp(ws, "Page.navigate",
                  {"url": "https://example.com/upload"}, session_id)
        await asyncio.sleep(2)
        
        # 上传本地文件
        await file_upload_via_intercept(
            ws, session_id,
            "#upload-button",
            ["C:/test/report.pdf", "C:/test/data.csv"]
        )
```

---

## 文件上传：绕过选择器直接设置

### DOM.setFileInputFiles

如果页面上已经有 `input[type="file"]` 元素，可以直接设置文件，完全不需要文件对话框：

```python
async def set_file_input(ws, session_id, css_selector, file_paths):
    """直接给文件输入框设置文件（绕过对话框）"""
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    abs_paths = [os.path.abspath(fp) for fp in file_paths]
    
    # 首先获取元素节点
    js = f"document.querySelector('{css_selector}')"
    result = await cdp(ws, "DOM.querySelector", {
        "nodeId": 1,  # 文档根节点 ID 通常为 1
        "selector": css_selector
    }, session_id)
    
    # 如果 DOM.querySelector 在 session 中不可用，尝试 Runtime 方式
    await cdp(ws, "DOM.setFileInputFiles", {
        "files": abs_paths,
        "nodeId": None,  # 不传 nodeId 将使用另一种方式
        "objectId": None
    }, session_id)
```

### 使用 Runtime 获取元素后设置

```python
async def set_file_input_runtime(ws, session_id, css_selector, file_paths):
    """通过 Runtime 获取元素后再设置文件"""
    if isinstance(file_paths, str):
        file_paths = [file_paths]
    abs_paths = [os.path.abspath(fp) for fp in file_paths]
    
    # 1. 获取文件输入元素的引用
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"document.querySelector('{css_selector}')",
        "objectGroup": "files"
    }, session_id)
    
    object_id = result.get("result", {}).get("objectId")
    if not object_id:
        raise ValueError(f"未找到元素: {css_selector}")
    
    # 2. 直接设置文件（绕过所有事件）
    await cdp(ws, "DOM.setFileInputFiles", {
        "files": abs_paths,
        "objectId": object_id
    }, session_id)
    
    print(f"已设置 {len(abs_paths)} 个文件: {[os.path.basename(f) for f in abs_paths]}")

# 更简化的版本（使用 JS 直接设置）
async def set_file_input_js(ws, session_id, css_selector, file_paths):
    """使用 JavaScript 间接设置文件"""
    # 注意：JavaScript 不能直接设置 FileList，此方法仅作参考
    # 实际推荐使用 DOM.setFileInputFiles
    paths_json = json.dumps(file_paths)
    js = f"""
    (() => {{
        const input = document.querySelector('{css_selector}');
        if (!input) throw new Error('找不到文件输入框');
        // 这里仅做验证——实际设置仍需 CDP
        return '找到输入框: ' + input.id;
    }})()
    """
    result = await cdp(ws, "Runtime.evaluate",
        {"expression": js}, session_id)
    print(result.get("result", {}).get("value", ""))
    
    # 然后用 DOM.setFileInputFiles
    await set_file_input_runtime(ws, session_id, css_selector, file_paths)
```

### 两种上传方式对比

| 方式 | 适用场景 | 优点 | 缺点 |
|------|---------|------|------|
| 拦截对话框 | 自定义上传按钮、拖拽上传区 | 覆盖所有上传场景 | 需要异步处理对话框事件 |
| 直接设置 | 有 `input[type=file]` 元素 | 简单直接 | 仅对标准文件输入框有效 |

---

## 文件下载：设置下载行为

### Browser.setDownloadBehavior

默认情况下，Chrome 会弹出下载对话框询问用户。CDP 可以控制这个行为：

```python
async def set_download_behavior(ws, download_path, behavior="allow"):
    """设置下载行为（浏览器级，不需要 session_id）"""
    await cdp(ws, "Browser.setDownloadBehavior", {
        "behavior": behavior,  # "allow" | "deny" | "default"
        "downloadPath": download_path
    })

async def allow_all_downloads(ws, download_path=None):
    """允许所有下载并指定保存目录"""
    if download_path is None:
        download_path = os.path.join(os.getcwd(), "downloads")
    os.makedirs(download_path, exist_ok=True)
    
    await set_download_behavior(ws, download_path, "allow")
    print(f"下载已启用，保存到 {os.path.abspath(download_path)}")
    return download_path

async def deny_all_downloads(ws):
    """阻止所有下载"""
    await set_download_behavior(ws, "", "deny")
    print("下载已阻止")
```

### 浏览器级命令说明

`Browser.setDownloadBehavior` 是**浏览器级别**的命令，需要在 CDP 根连接上发送（不带 session_id）：

```python
async def setup_download(path):
    """设置下载路径（完整示例）"""
    async with websockets.connect(CDP_URL) as ws:
        # 浏览器级别设置——不需要 session
        await cdp(ws, "Browser.setDownloadBehavior", {
            "behavior": "allow",
            "downloadPath": os.path.abspath(path)
        })
        print("下载行为设置成功")
```

### 设置多个下载目录

```python
async def setup_site_specific_downloads(ws, download_map):
    """为不同网站设置不同的下载路径"""
    # 注意：Browser.setDownloadBehavior 最近一次调用覆盖之前
    # 需要通过监听下载事件后动态切换
    for url_pattern, path in download_map.items():
        os.makedirs(path, exist_ok=True)
        print(f"  {url_pattern} → {os.path.abspath(path)}")
```

---

## 监控下载进度与事件

### Page.downloadWillBegin

当页面开始下载时会触发此事件：

```python
async def listen_download_events(ws, timeout=60):
    """监听下载相关事件"""
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
                    print(f"[下载开始]")
                    print(f"  URL: {url[:80]}")
                    print(f"  推荐文件名: {suggested}")
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
                        print(f"[下载中] {percent:.1f}% ({received}/{total} bytes)")
                    elif state == "completed":
                        print(f"[下载完成] 共 {total} bytes")
                        events.append({"type": "completed", "bytes": total})
                    elif state == "canceled":
                        print(f"[下载取消] 已接收 {received} bytes")
                        events.append({"type": "canceled"})
                    
    except asyncio.TimeoutError:
        pass
    
    return events
```

### 完整的下载管理器

```python
class DownloadTracker:
    """下载进度跟踪器"""
    
    def __init__(self):
        self.downloads = {}
        self._current_id = 0
    
    def _next_id(self):
        self._current_id += 1
        return self._current_id
    
    async def handle_event(self, method, params):
        """处理下载事件"""
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
            print(f"[{dl_id}] 开始下载: {self.downloads[dl_id]['filename']}")
            return dl_id
        
        elif method == "Page.downloadProgress":
            guid = params.get("guid", "")
            state = params.get("state", "")
            received = params.get("receivedBytes", 0)
            total = params.get("totalBytes", 0)
            
            # 查找最近的下载
            for dl_id in reversed(list(self.downloads.keys())):
                dl = self.downloads[dl_id]
                dl["received_bytes"] = received
                dl["total_bytes"] = total
                dl["state"] = state
                
                if state == "completed":
                    print(f"[{dl_id}] 下载完成: {dl['filename']} ({total} bytes)")
                elif state == "canceled":
                    print(f"[{dl_id}] 下载被取消")
                return dl_id
        
        return None
    
    def get_downloads(self):
        """获取所有下载记录"""
        return dict(self.downloads)
    
    def get_completed(self):
        """获取已完成的下载"""
        return {k: v for k, v in self.downloads.items()
                if v["state"] == "completed"}
```

---

## 实战：自动下载文件并保存

### 下载链接自动保存

```python
async def auto_download_file(ws, download_url, save_dir="./downloads"):
    """自动下载文件并监控进度"""
    save_dir = os.path.abspath(save_dir)
    os.makedirs(save_dir, exist_ok=True)
    
    # 1. 设置下载路径
    await cdp(ws, "Browser.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": save_dir
    })
    
    # 2. 启动下载事件监听
    tracker = DownloadTracker()
    listener_task = asyncio.create_task(
        listen_download_progress(ws, tracker)
    )
    
    # 3. 触发下载（创建标签页并导航到下载链接）
    # 方法一：直接导航到文件 URL
    target = await cdp(ws, "Target.createTarget", {"url": download_url})
    target_id = target.get("targetId")
    print(f"创建临时标签页下载: {download_url[:60]}...")
    
    # 4. 等待下载完成
    await asyncio.sleep(5)
    
    # 5. 关闭临时标签页
    if target_id:
        await cdp(ws, "Target.closeTarget", {"targetId": target_id})
    
    # 6. 返回结果
    listener_task.cancel()
    completed = tracker.get_completed()
    return completed


async def listen_download_progress(ws, tracker, timeout=30):
    """持续监听下载事件"""
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

### 批量下载

```python
async def batch_download(ws, urls, save_dir="./batch_downloads"):
    """批量下载文件"""
    save_dir = os.path.abspath(save_dir)
    os.makedirs(save_dir, exist_ok=True)
    
    # 设置下载路径
    await cdp(ws, "Browser.setDownloadBehavior", {
        "behavior": "allow",
        "downloadPath": save_dir
    })
    
    # 启动监听
    tracker = DownloadTracker()
    listener = asyncio.create_task(
        listen_download_progress(ws, tracker, timeout=120)
    )
    
    # 逐个触发下载
    for i, url in enumerate(urls):
        target = await cdp(ws, "Target.createTarget", {"url": url})
        tid = target.get("targetId")
        print(f"[{i+1}/{len(urls)}] 下载: {url[:50]}...")
        await asyncio.sleep(3)  # 等待下载开始
        if tid:
            await cdp(ws, "Target.closeTarget", {"targetId": tid})
    
    await asyncio.sleep(5)  # 等待所有下载完成
    listener.cancel()
    
    completed = tracker.get_completed()
    print(f"完成 {len(completed)}/{len(urls)} 个下载")
    return completed
```

---

## 实战：批量文件上传

```python
async def batch_file_upload(ws, session_id, upload_button_selector, file_list):
    """批量上传多个文件到同一个上传控件"""
    abs_files = [os.path.abspath(f) for f in file_list]
    
    # 验证所有文件都存在
    for f in abs_files:
        if not os.path.exists(f):
            print(f"警告: 文件不存在 {f}")
    
    existing = [f for f in abs_files if os.path.exists(f)]
    if not existing:
        raise FileNotFoundError("没有可上传的文件")
    
    print(f"准备上传 {len(existing)} 个文件...")
    
    try:
        # 启用拦截
        await enable_file_chooser_interception(ws, session_id)
        
        # 准备监听文件对话框
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
        
        # 点击上传按钮
        await cdp(ws, "Runtime.evaluate", {
            "expression": f"document.querySelector('{upload_button_selector}').click()"
        }, session_id)
        
        # 等待文件对话框事件
        await asyncio.wait_for(chooser_event, timeout=10)
        
        # 提供文件
        await handle_file_chooser(ws, session_id, existing)
        
        # 清理
        listener.cancel()
        await enable_file_chooser_interception(ws, session_id, enabled=False)
        
        print("批量上传完成！")
        
    except asyncio.TimeoutError:
        print("超时：文件对话框未出现")
    except Exception as e:
        print(f"上传出错: {e}")
```

---

## 完整参考：CDP FileHandler 类

```python
import asyncio
import json
import os
import websockets
from typing import List, Optional


class CDPFileHandler:
    """CDP 文件处理器（上传 + 下载）"""
    
    def __init__(self, ws, session_id=None):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self._downloads = {}
    
    async def _cdp(self, method: str, params: dict = None,
                   session_id: str = None) -> dict:
        """发送 CDP 命令"""
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
    
    # ===== 上传 =====
    
    async def enable_chooser_interception(self, enabled: bool = True):
        """启用/禁用文件选择拦截"""
        await self._cdp("Page.setInterceptFileChooserDialog",
                       {"enabled": enabled})
    
    async def handle_chooser(self, file_paths: List[str]):
        """处理文件选择对话框"""
        await self._cdp("Page.handleFileChooser", {
            "action": "accept",
            "files": file_paths
        })
    
    async def upload_via_intercept(self, css_selector: str,
                                   file_paths: List[str]) -> bool:
        """通过拦截文件对话框上传"""
        abs_paths = [os.path.abspath(f) for f in file_paths
                     if os.path.exists(f)]
        if not abs_paths:
            raise FileNotFoundError("没有可用的文件")
        
        await self.enable_chooser_interception(True)
        
        # 等待文件对话框事件
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
        
        # 触发上传
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
        """直接给文件输入框设置文件"""
        abs_paths = [os.path.abspath(f) for f in file_paths
                     if os.path.exists(f)]
        
        # 获取元素对象引用
        result = await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}')",
            "objectGroup": "files"
        })
        
        object_id = result.get("result", {}).get("objectId")
        if not object_id:
            raise ValueError(f"元素未找到: {css_selector}")
        
        await self._cdp("DOM.setFileInputFiles", {
            "files": abs_paths,
            "objectId": object_id
        })
        
        print(f"已设置文件: {[os.path.basename(f) for f in abs_paths]}")
    
    # ===== 下载 =====
    
    async def set_download_path(self, path: str, behavior: str = "allow"):
        """设置下载路径（浏览器级命令）"""
        os.makedirs(path, exist_ok=True)
        await self._cdp("Browser.setDownloadBehavior", {
            "behavior": behavior,
            "downloadPath": os.path.abspath(path)
        }, session_id=None)  # 浏览器级命令不需要 session
        print(f"下载路径: {os.path.abspath(path)}")
    
    async def download_url(self, url: str,
                          save_dir: str = "./downloads") -> Optional[dict]:
        """下载一个 URL 并等待完成"""
        save_dir = os.path.abspath(save_dir)
        await self.set_download_path(save_dir)
        
        # 创建临时标签页下载
        result = await self._cdp("Target.createTarget", {"url": url},
                                session_id=None)
        target_id = result.get("targetId")
        if not target_id:
            return None
        
        # 等待下载启动
        await asyncio.sleep(3)
        
        # 关闭标签页
        await self._cdp("Target.closeTarget", {"targetId": target_id},
                       session_id=None)
        
        return {"targetId": target_id, "saveDir": save_dir}
    
    # ===== 事件监听 =====
    
    async def listen_downloads(self, timeout: float = 30) -> List[dict]:
        """监听下载事件并返回结果"""
        events = []
        
        async def _handler(method: str, params: dict):
            nonlocal events
            if method == "Page.downloadWillBegin":
                events.append({
                    "type": "begin",
                    "url": params.get("url", ""),
                    "filename": params.get("suggestedFilename", "")
                })
                print(f"下载开始: {params.get('suggestedFilename', '')}")
            
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
                    print(f"下载完成: {total} bytes")
                elif state == "canceled":
                    events.append({"type": "canceled"})
                    print("下载取消")
        
        # 简化：直接监听 WebSocket
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

**使用示例：**

```python
async def demo_file_handler():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        fh = CDPFileHandler(ws, session_id)
        
        # === 上传示例 ===
        # 方式 1：拦截对话框上传
        success = await fh.upload_via_intercept(
            "#upload-btn",
            ["C:/test/report.pdf", "C:/test/photo.jpg"]
        )
        print(f"上传{'成功' if success else '失败'}")
        
        # 方式 2：直接设置文件输入框
        await fh.set_file_input(
            "input[type='file']",
            ["C:/test/document.docx"]
        )
        
        # === 下载示例 ===
        # 设置下载路径
        await fh.set_download_path("./my_downloads")
        
        # 触发下载
        result = await fh.download_url(
            "https://example.com/file.pdf"
        )
        print(f"下载结果: {result}")
```

---

## 常见踩坑与最佳实践

### 踩坑 1：FileChooser 事件可能丢失

```python
# ❌ 先点按钮，再启用拦截——对话框事件已经发出
await cdp(ws, "Runtime.evaluate", {"expression": "uploadBtn.click()"}, session_id)
await cdp(ws, "Page.setInterceptFileChooserDialog", {"enabled": True}, session_id)

# ✅ 先启用拦截，再触发上传
await cdp(ws, "Page.setInterceptFileChooserDialog", {"enabled": True}, session_id)
# 然后启动事件监听...
await cdp(ws, "Runtime.evaluate", {"expression": "uploadBtn.click()"}, session_id)
```

### 踩坑 2：文件路径格式

```python
# ❌ Windows 反斜杠可能在某些场景出问题
await set_file_input(ws, session_id, "C:\\Users\\test\\file.txt")

# ✅ 使用正规化后的路径
import os
path = os.path.normpath("C:/Users/test/file.txt")
path = os.path.abspath(path)
await set_file_input(ws, session_id, path)

# 或使用正斜杠
await set_file_input(ws, session_id, "C:/Users/test/file.txt")
```

### 踩坑 3：DOM.setFileInputFiles 需要 Document 域启用

```python
# ❌ DOM 域未启用，setFileInputFiles 失败
await cdp(ws, "DOM.setFileInputFiles", {...}, session_id)

# ✅ 先启用 DOM 域
await cdp(ws, "DOM.enable", session_id=session_id)
await cdp(ws, "DOM.setFileInputFiles", {...}, session_id)
```

### 踩坑 4：下载路径必须是已经存在的目录

```python
# ❌ 目录不存在，下载会失败
await cdp(ws, "Browser.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": "/nonexistent/path"
})

# ✅ 先创建目录
import os
path = os.path.abspath("./downloads")
os.makedirs(path, exist_ok=True)
await cdp(ws, "Browser.setDownloadBehavior", {
    "behavior": "allow",
    "downloadPath": path
})
```

### 踩坑 5：浏览器级 vs 页面级命令

```python
# ❌ 浏览器级命令带上了 session_id（无效）
await cdp(ws, "Browser.setDownloadBehavior", {...}, session_id="XXX")

# ✅ 浏览器级命令不带 session_id
await cdp(ws, "Browser.setDownloadBehavior", {...})  # 没有 session_id

# ✅ 页面级命令带上 session_id
await cdp(ws, "Page.setInterceptFileChooserDialog", {"enabled": True}, session_id)
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 上传事件顺序 | 先启用拦截 → 监听器就绪 → 触发点击 |
| 文件路径 | 使用绝对路径 + os.path.normpath 正规化 |
| DOM 域 | 使用 DOM.setFileInputFiles 前先启用 DOM.enable |
| 下载目录 | 执行下载前确保目录已创建 |
| 命令级别 | 浏览器级不带 session_id，页面级须带 |
| 异步处理 | 文件对话框需要异步等事件，不要用 sleep 猜测 |
| 资源清理 | 用完关闭临时标签页、恢复拦截设置 |

---

> **总结**：CDP 的文件处理 API 提供了远胜传统自动化工具的上传和下载控制能力。通过拦截文件选择对话框，你可以处理任意形式的上传界面；通过设置下载行为，你可以静默保存任何文件。结合 FileHandler 封装类，文件操作在自动化流程中将不再是瓶颈。

*上一篇回顾：CDP 输入自动化指南：用 Python 模拟鼠标键盘。*

*下一篇预告：CDP Service Worker 管理：用 Python 调试离线缓存。*