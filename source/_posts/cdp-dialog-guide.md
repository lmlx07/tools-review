---
title: CDP 对话框处理指南：用 Python 自动处理 alert/confirm/prompt
date: 2026-06-05 20:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 对话框
  - 浏览器自动化
  - 弹窗处理
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）自动处理浏览器对话框。涵盖自动关闭 alert、自动确认 confirm、自动填写 prompt、处理 beforeunload 事件，以及在不中断自动化流程的情况下处理弹窗。
---

> **一句话总结**：CDP 的 `Page.javascriptDialogOpening` 事件可以让你拦截所有浏览器弹窗——alert、confirm、prompt、beforeunload——然后编程决定接受、拒绝或输入文本。

---

## 目录

1. [为什么用 CDP 处理对话框](#为什么用-cdp-处理对话框)
2. [监听对话框事件](#监听对话框事件)
3. [自动处理弹窗](#自动处理弹窗)
4. [处理 beforeunload](#处理-beforeunload)
5. [实战：无中断自动化测试](#实战无中断自动化测试)
6. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 处理对话框

在自动化测试中，弹窗是常见的"绊脚石"——它们会阻塞脚本执行：

| 方法 | Selenium | CDP |
|------|----------|-----|
| alert 处理 | ✅ switchTo().alert() | ✅ Page.javascriptDialogOpening 事件 |
| confirm 处理 | ✅ 同上 | ✅ 可选择接受/拒绝 |
| prompt 输入文本 | ✅ sendKeys() | ✅ 可预设文本 |
| beforeunload | ⚠️ 难以处理 | ✅ 原生支持 |
| 不阻塞流程 | ❌ 弹窗会阻塞操作 | ✅ 事件方式不阻塞 |
| 弹窗内容获取 | ✅ 可获取文本 | ✅ 可获取消息+类型 |

---

## 监听对话框事件

### 基础：监听 `Page.javascriptDialogOpening`

```python
import asyncio
import websockets
import json

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
    """监听所有对话框事件"""
    dialogs = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "Page.javascriptDialogOpening":
                params = data["params"]
                dialog = {
                    "type": params.get("type"),      # alert, confirm, prompt, beforeunload
                    "message": params.get("message", ""),
                    "default_prompt": params.get("defaultPrompt", ""),
                    "has_browser_handler": params.get("hasBrowserHandler", False)
                }
                dialogs.append(dialog)
                print(f"[对话框] {dialog['type']}: {dialog['message'][:50]}")
                    
        except asyncio.TimeoutError:
            continue
    
    return dialogs
```

---

## 自动处理弹窗

### 自动接受所有弹窗

```python
async def auto_accept_dialogs(ws, session_id):
    """自动接受所有弹窗"""
    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
        "accept": True
    })
```

### 按类型智能处理

```python
async def smart_handle_dialogs(ws, session_id, duration=30):
    """智能处理弹窗：alert 接受，confirm 接受，prompt 填文本"""
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "Page.javascriptDialogOpening":
                params = data["params"]
                dialog_type = params.get("type")
                message = params.get("message", "")
                
                print(f"检测到弹窗: [{dialog_type}] {message[:50]}")
                
                if dialog_type == "alert":
                    # alert: 直接接受
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                        "accept": True
                    })
                    print("  → 已接受")
                    
                elif dialog_type == "confirm":
                    # confirm: 根据条件决定
                    if "delete" in message.lower():
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": False  # 删除类确认拒绝
                        })
                        print("  → 已拒绝")
                    else:
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True
                        })
                        print("  → 已接受")
                
                elif dialog_type == "prompt":
                    # prompt: 填写预设文本
                    default = params.get("defaultPrompt", "")
                    prompt_text = "auto_filled_value"
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                        "accept": True,
                        "promptText": prompt_text
                    })
                    print(f"  → 已填写: {prompt_text}")
                
                elif dialog_type == "beforeunload":
                    # beforeunload: 接受离开
                    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                        "accept": True
                    })
                    print("  → 已确认离开")
                    
        except asyncio.TimeoutError:
            continue
```

### 弹窗处理器的完整实现

```python
async def handle_dialog(ws, session_id, accept=True, prompt_text=None):
    """
    处理当前对话框
    - accept: True=接受/确定, False=拒绝/取消
    - prompt_text: 仅 prompt 对话框需要
    """
    params = {"accept": accept}
    if prompt_text is not None:
        params["promptText"] = prompt_text
    
    return await cdp(ws, session_id, "Page.handleJavaScriptDialog", params)


class DialogHandler:
    """对话框处理器——自动处理弹窗"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self.dialogs_log = []
    
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
        """接受所有弹窗"""
        async for msg in self.ws:
            data = json.loads(msg)
            if data.get("method") == "Page.javascriptDialogOpening":
                params = data["params"]
                self.dialogs_log.append({
                    "type": params.get("type"),
                    "message": params.get("message")
                })
                await self._cmd("Page.handleJavaScriptDialog", {"accept": True})
    
    async def accept_alert(self):
        """处理单个 alert"""
        await self._cmd("Page.handleJavaScriptDialog", {"accept": True})
    
    async def dismiss_confirm(self):
        """拒绝 confirm"""
        await self._cmd("Page.handleJavaScriptDialog", {"accept": False})
    
    async def fill_prompt(self, text):
        """填写 prompt"""
        await self._cmd("Page.handleJavaScriptDialog", {
            "accept": True, "promptText": text
        })
    
    def get_log(self):
        return self.dialogs_log
```

---

## 处理 beforeunload

### beforeunload 的特殊性

`beforeunload` 弹窗和其他对话框不同——它是页面即将关闭时触发的。CDP 提供了更优雅的处理方式：

```python
async def handle_beforeunload(ws, session_id, accept=True):
    """处理 beforeunload 弹窗"""
    return await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
        "accept": accept
    })


async def navigate_ignore_beforeunload(ws, session_id, url):
    """
    导航到新 URL，忽略 beforeunload
    通过 Page.navigate 的 handleBeforeUnload 参数控制
    """
    # 方法一：通过 CDP 导航参数（推荐）
    result = await cdp(ws, session_id, "Page.navigate", {
        "url": url,
        "handleBeforeUnload": True  # 自动处理 beforeunload
    })
    return result


async def close_page_ignore_beforeunload(ws, session_id, target_id):
    """
    关闭页面，忽略 beforeunload
    """
    await cdp(ws, session_id, "Target.closeTarget", {
        "targetId": target_id
    })
```

---

## 实战：无中断自动化测试

结合页面操作和对话框处理，实现不中断的自动化测试：

```python
async def automated_test_with_dialogs(ws, session_id, url):
    """
    自动化测试流程——自动处理所有弹窗
    """
    # 1. 启动对话框监听任务（后台运行）
    async def dialog_watcher():
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                
                if data.get("method") == "Page.javascriptDialogOpening":
                    params = data["params"]
                    dtype = params.get("type")
                    
                    print(f"[弹窗] {dtype}: {params.get('message', '')[:60]}")
                    
                    # 自动处理
                    if dtype == "beforeunload":
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True
                        })
                    elif dtype == "prompt":
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True,
                            "promptText": "test_value"
                        })
                    else:
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True
                        })
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    # 2. 启动导航
    watcher = asyncio.create_task(dialog_watcher())
    
    # 3. 导航到页面
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(5)
    
    # 4. 执行一些可能触发弹窗的操作
    # 例如点击删除按钮
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": """
            document.querySelector('.delete-btn')?.click();
        """
    })
    await asyncio.sleep(2)
    
    # 5. 停止监听
    watcher.cancel()
    
    print("测试完成（所有弹窗已自动处理）")


async def test_form_with_prompt(ws, session_id, url):
    """测试包含 prompt 弹窗的表单"""
    logger = []
    
    async def dialog_listener():
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                if data.get("method") == "Page.javascriptDialogOpening":
                    params = data["params"]
                    logger.append(params)
                    
                    # 给 prompt 填写随机用户名
                    if params.get("type") == "prompt":
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True,
                            "promptText": f"user_{int(asyncio.get_event_loop().time())}"
                        })
                    else:
                        await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
                            "accept": True
                        })
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    listener = asyncio.create_task(dialog_listener())
    
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    # 模拟操作
    await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "document.querySelector('#create-btn')?.click()"
    })
    await asyncio.sleep(2)
    
    listener.cancel()
    
    print(f"测试中出现了 {len(logger)} 个弹窗")
    return logger
```

---

## 常见踩坑与最佳实践

### 踩坑 1：必须在对话框打开后尽快处理

```python
# ❌ 等待时间过长
msg = await ws.__anext__()  # 收到 dialogOpening 事件
await asyncio.sleep(5)  # 等太久！
await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": True})
# 可能超时或页面已等待用户操作超时

# ✅ 收到事件后立即处理
if data.get("method") == "Page.javascriptDialogOpening":
    # 立即处理，不要等
    await cdp(ws, session_id, "Page.handleJavaScriptDialog", {"accept": True})
```

### 踩坑 2：对话框会阻塞 CDP 命令

当弹窗打开时，某些 CDP 命令可能不会返回，直到弹窗被处理：

```python
# 弹窗打开时，Page.navigate 可能不返回
# 必须先处理弹窗，再发送其他命令
```

### 踩坑 3：promptText 只在 accept=True 时有效

```python
# ❌ 拒绝时发送 promptText 无意义
await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
    "accept": False,
    "promptText": "something"  # 被忽略
})

# ✅ 只在 accept=True 时使用 promptText
await cdp(ws, session_id, "Page.handleJavaScriptDialog", {
    "accept": True,
    "promptText": "user_input"
})
```

### 踩坑 4：beforeunload 的行为差异

```python
# beforeunload 弹窗在 CDP 中显示为 type="beforeunload"
# 接受（accept=True）等同于"离开页面"
# 拒绝（accept=False）等同于"留在页面"

# 建议：大多数自动化场景应该接受 beforeunload
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 及时处理 | 收到 dialogOpening 事件后立即处理 |
| 后台监听 | 用 asyncio.create_task 后台处理弹窗 |
| prompt 文本 | 只在 accept=True 时传 promptText |
| beforeunload | 自动化测试中一般接受 |
| 日志记录 | 记录弹窗类型和消息便于排查 |
| 超时处理 | 对话框有超时机制，不要延迟处理 |

---

## 完整参考：CDP 对话框处理类

```python
class CDPDialogHandler:
    """CDP 对话框自动处理器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self.dialogs = []
    
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
        """启动后台自动接受所有弹窗"""
        while True:
            try:
                msg = await asyncio.wait_for(ws.__anext__(), timeout=0.5)
                data = json.loads(msg)
                if data.get("method") == "Page.javascriptDialogOpening":
                    p = data["params"]
                    self.dialogs.append(p)
                    await self._cmd("Page.handleJavaScriptDialog", {"accept": True})
            except asyncio.TimeoutError:
                continue
            except Exception:
                break
    
    async def accept(self, prompt_text=None):
        params = {"accept": True}
        if prompt_text:
            params["promptText"] = prompt_text
        await self._cmd("Page.handleJavaScriptDialog", params)
    
    async def dismiss(self):
        await self._cmd("Page.handleJavaScriptDialog", {"accept": False})
    
    def get_dialogs(self):
        return self.dialogs
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    dialogs = CDPDialogHandler(ws, session_id)
    
    # 后台自动处理弹窗
    handler = asyncio.create_task(dialogs.start_auto_accept())
    
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(5)
    
    handler.cancel()
    print(f"自动处理了 {len(dialogs.get_dialogs())} 个弹窗")
```

---

> **总结**：CDP 的对话框事件让你可以优雅地处理页面弹窗——alert 自动关闭、confirm 按需选择、prompt 自动填写、beforeunload 妥善处理——确保自动化流程不会被弹窗中断。

---

*上一篇回顾：CDP 存储操作指南：用 Python 管理 LocalStorage、IndexedDB 与缓存。*

*下一篇预告：CDP Frame 管理指南：用 Python 处理 iframe 与跨域框架。*