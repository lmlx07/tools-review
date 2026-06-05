---
title: CDP 浏览器历史管理：用 Python 控制页面导航历史
date: 2026-06-05 20:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Navigation
  - Page History
  - Browser Automation
categories:
  - CDP 进阶
  - Python 实战
description: 全面讲解如何用 CDP 控制浏览器的页面导航历史。涵盖 Page.navigate 的前进/后退、Page.navigateToHistoryEntry 跳转到指定历史条目、处理 JavaScript 弹窗、监听导航事件、hash 导航与全导航的区别等实用技术。
---

> **一句话总结**：CDP 的 Page 域提供了完整的导航历史控制能力——你可以编程地执行浏览器前进/后退、跳转到任意历史条目、监听导航事件、自动处理弹窗，就像用户在操作浏览器的前进/后退按钮一样。

---

## 目录

1. [为什么用 CDP 管理浏览器历史](#为什么用-cdp-管理浏览器历史)
2. [基础：连接与页面启用](#基础连接与页面启用)
3. [基础导航：前进和后退](#基础导航前进和后退)
4. [跳转到指定历史条目](#跳转到指定历史条目)
5. [监听导航与历史事件](#监听导航与历史事件)
6. [处理 JavaScript 弹窗](#处理-javascript-弹窗)
7. [Hash 导航 vs 全导航](#hash-导航-vs-全导航)
8. [实战：自动回溯测试流程](#实战自动回溯测试流程)
9. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 管理浏览器历史

| 功能 | Selenium/Playwright | CDP Page API |
|------|-------------------|-------------|
| 前进/后退 | `driver.back()` / `driver.forward()` | `Page.navigate` 直接控制 |
| 跳转指定条目 | ❌ 不支持 | `Page.navigateToHistoryEntry` 支持 |
| 历史条目枚举 | ❌ 不可见 | 可获取所有历史条目 ID |
| 导航事件 | 有限的 wait 机制 | 完整的事件流（开始/完成/失败） |
| JS 弹窗处理 | 可能阻塞 | 精确控制弹窗行为 |
| hash 变化 | 视为导航 | 清晰区分布局/全导航 |
| 历史记录清理 | ❌ 不支持 | 可间接控制 |

---

## 基础：连接与页面启用

### 统一 CDP 辅助函数

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
    result = await cdp(ws, "Target.getTargets")
    target_id = result["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

### 启用 Page 域

导航相关功能需要先启用 Page 域：

```python
async def enable_page(ws, session_id):
    """
    启用 Page 域以接收导航事件
    必须在调用导航相关命令前调用
    """
    await cdp(ws, "Page.enable", session_id=session_id)
    print("Page 域已启用，导航事件已就绪")
```

---

## 基础导航：前进和后退

通过 `Page.navigate` 的 `transitionType` 和 URL 控制来实现浏览器前进和后退效果。

### 基本导航操作

```python
async def navigate_to(ws, session_id, url, wait_seconds=2):
    """导航到指定 URL 并等待页面加载"""
    result = await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
    
    error_text = result.get("errorText")
    frame_id = result.get("frameId")
    
    if error_text:
        print(f"❌ 导航失败: {error_text}")
        return False
    
    print(f"✅ 已导航到: {url} (frame: {frame_id[:12] if frame_id else 'N/A'}...)")
    
    if wait_seconds > 0:
        await asyncio.sleep(wait_seconds)
    
    return True


async def navigate_back(ws, session_id):
    """
    模拟浏览器后退按钮
    使用 Page.navigate 配合 history.back()
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (() => {
                if (window.history.length > 1) {
                    window.history.back();
                    return { canGoBack: true, historyLength: window.history.length };
                }
                return { canGoBack: false, historyLength: window.history.length };
            })()
        """
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("canGoBack"):
        print(f"⬅️ 后退成功（历史长度: {outcome['historyLength']}）")
        await asyncio.sleep(2)
        return True
    else:
        print("⛔ 无法后退：没有历史记录")
        return False


async def navigate_forward(ws, session_id):
    """
    模拟浏览器前进按钮
    使用 Page.navigate 配合 history.forward()
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (() => {
                try {
                    window.history.forward();
                    return { success: true };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            })()
        """
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        print("➡️ 前进成功")
        await asyncio.sleep(2)
        return True
    else:
        print("⛔ 无法前进")
        return False
```

### 使用 CDP 原生导航控制

`Page.navigate` 支持直接指定导航的类型：

```python
async def navigate_back_cdp(ws, session_id):
    """使用 CDP 原生方式执行后退"""
    result = await cdp(ws, "Page.navigate", {
        "url": "javascript:void(0)",
        "transitionType": "back_forward"
    }, session_id=session_id)
    
    # 再通过 JavaScript 触发后退
    await cdp(ws, "Runtime.evaluate", {
        "expression": "window.history.back()"
    }, session_id=session_id)
    await asyncio.sleep(2)
    
    # 获取当前 URL 验证
    url_result = await cdp(ws, "Runtime.evaluate", {
        "expression": "window.location.href"
    }, session_id=session_id)
    
    current_url = url_result.get("result", {}).get("value", "")
    print(f"后退后当前页面: {current_url}")
    return current_url
```

---

## 跳转到指定历史条目

CDP 的一个独特功能：可以直接跳转到历史记录中的任意条目，而不只是一次一步地前进后退。

### 获取历史条目

```python
async def get_navigation_history(ws, session_id):
    """
    获取当前页面的导航历史信息
    返回包含历史条目和当前索引的字典
    """
    result = await cdp(ws, "Page.getNavigationHistory", session_id=session_id)
    
    current_index = result.get("currentIndex", -1)
    entries = result.get("entries", [])
    
    print(f"导航历史: 共 {len(entries)} 个条目，当前在第 {current_index + 1} 个")
    
    for i, entry in enumerate(entries):
        marker = "◀ 当前" if i == current_index else "   "
        print(f"  [{i}] {marker} {entry.get('url', '')[:80]} "
              f"(ID: {entry.get('id', 'N/A')}, "
              f"类型: {entry.get('transitionType', 'N/A')})")
    
    return {
        "current_index": current_index,
        "entries": entries
    }


async def print_history_summary(ws, session_id):
    """打印简洁的历史记录摘要"""
    history = await get_navigation_history(ws, session_id)
    
    if not history["entries"]:
        print("导航历史为空")
        return history
    
    domains = {}
    for entry in history["entries"]:
        url = entry.get("url", "")
        if "://" in url:
            domain = url.split("/")[2]
            domains[domain] = domains.get(domain, 0) + 1
    
    print(f"\n访问过的域名: {len(domains)} 个")
    for domain, count in sorted(domains.items(), key=lambda x: -x[1]):
        print(f"  {domain}: {count} 次")
    
    return history
```

### 跳转到具体条目

```python
async def navigate_to_history_entry(ws, session_id, entry_id):
    """
    跳转到历史记录中的指定条目
    
    参数:
        entry_id: 历史条目的 ID（从 getNavigationHistory 获取）
    """
    result = await cdp(ws, "Page.navigateToHistoryEntry", {
        "entryId": entry_id
    }, session_id=session_id)
    
    await asyncio.sleep(2)
    
    # 验证跳转后的 URL
    url_result = await cdp(ws, "Runtime.evaluate", {
        "expression": "window.location.href"
    }, session_id=session_id)
    
    current_url = url_result.get("result", {}).get("value", "")
    print(f"🔄 已跳转到历史条目 {entry_id}: {current_url}")
    
    return current_url


async def jump_in_history(ws, session_id, steps):
    """
    在历史记录中跳转指定的步数
    正数 = 前进，负数 = 后退
    
    参数:
        steps: 要跳转的步数（例如 -3 表示后退 3 步）
    """
    history = await get_navigation_history(ws, session_id)
    current = history["current_index"]
    entries = history["entries"]
    
    target = current + steps
    if target < 0 or target >= len(entries):
        print(f"⛔ 目标索引 {target} 超出范围 (0-{len(entries) - 1})")
        return None
    
    target_entry = entries[target]
    entry_id = target_entry["id"]
    
    print(f"🔄 跳转: 索引 {current} → {target} ({'前进' if steps > 0 else '后退'}{abs(steps)} 步)")
    print(f"   目标: {target_entry.get('url', '')[:80]}")
    
    return await navigate_to_history_entry(ws, session_id, entry_id)


async def go_to_first_entry(ws, session_id):
    """跳转到历史记录的第一个条目"""
    return await jump_in_history(ws, session_id, -999)


async def go_to_last_entry(ws, session_id):
    """跳转到历史记录的最后一个条目"""
    return await jump_in_history(ws, session_id, 999)
```

---

## 监听导航与历史事件

### 事件监听器基类

```python
class NavigationListener:
    """导航事件监听器，用于收集导航过程中的所有事件"""
    
    def __init__(self, ws):
        self.ws = ws
        self.events = []
        self._listening = False
        self._task = None
    
    async def _listen(self):
        """后台监听导航相关事件"""
        async for resp in self.ws:
            if not self._listening:
                break
            data = json.loads(resp)
            method = data.get("method", "")
            
            if method.startswith("Page."):
                self.events.append({
                    "timestamp": asyncio.get_event_loop().time(),
                    "method": method,
                    "params": data.get("params", {})
                })
                
                # 打印关键事件
                params = data.get("params", {})
                if method == "Page.frameStartedLoading":
                    print(f"  📥 框架开始加载: {params.get('frameId', '')[:12]}...")
                elif method == "Page.frameStoppedLoading":
                    print(f"  ✅ 框架加载完成: {params.get('frameId', '')[:12]}...")
                elif method == "Page.frameNavigated":
                    frame = params.get("frame", {})
                    print(f"  🧭 框架导航: {frame.get('url', '')[:80]}")
                elif method == "Page.javascriptDialogOpening":
                    print(f"  💬 JS 弹窗: {params.get('message', '')[:60]}")
    
    async def start(self):
        """开始监听导航事件"""
        self._listening = True
        self._task = asyncio.create_task(self._listen())
        print("开始监听导航事件...")
    
    async def stop(self):
        """停止监听导航事件"""
        self._listening = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        print(f"导航事件监听停止，共收集 {len(self.events)} 个事件")
    
    def get_events_by_type(self, method_name):
        """按事件类型过滤"""
        return [e for e in self.events if e["method"] == method_name]
    
    def get_navigations(self):
        """获取所有导航事件"""
        return self.get_events_by_type("Page.frameNavigated")
    
    def get_dialogs(self):
        """获取所有弹窗事件"""
        return self.get_events_by_type("Page.javascriptDialogOpening")
```

### 等待特定导航完成

```python
async def wait_for_navigation(ws, session_id, timeout=10):
    """
    等待页面导航完成
    监听 frameStoppedLoading 事件
    """
    navigated = asyncio.Event()
    
    async def waiter():
        async for resp in ws:
            data = json.loads(resp)
            if data.get("method") == "Page.frameStoppedLoading":
                navigated.set()
                break
    
    waiter_task = asyncio.create_task(waiter())
    
    try:
        await asyncio.wait_for(navigated.wait(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        print(f"⏰ 等待导航超时（{timeout}s）")
        return False
    finally:
        waiter_task.cancel()
        try:
            await waiter_task
        except asyncio.CancelledError:
            pass


async def navigate_and_wait(ws, session_id, url, timeout=10):
    """导航并等待加载完成"""
    print(f"导航到: {url}")
    
    # 同时启动导航和等待
    nav_result = await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
    
    error = nav_result.get("errorText")
    if error:
        print(f"导航错误: {error}")
        return False
    
    loaded = await wait_for_navigation(ws, session_id, timeout)
    
    if loaded:
        # 获取最终 URL
        url_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.href"
        }, session_id=session_id)
        final_url = url_result.get("result", {}).get("value", "")
        print(f"加载完成: {final_url}")
    
    return loaded
```

### 完整事件收集示例

```python
async def trace_navigation(ws, session_id, url):
    """
    追踪一次完整导航的所有事件
    返回事件时间线
    """
    listener = NavigationListener(ws)
    await listener.start()
    
    # 执行导航
    await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
    await asyncio.sleep(3)
    
    await listener.stop()
    
    print("\n=== 导航事件时间线 ===")
    for event in listener.events:
        method = event["method"]
        params = event["params"]
        
        if method == "Page.frameStartedLoading":
            print(f"  ⏱  {method}")
        elif method == "Page.frameNavigated":
            print(f"  ⏱  {method} → {params.get('frame', {}).get('url', '')[:70]}")
        elif method == "Page.frameStoppedLoading":
            print(f"  ⏱  {method}")
        else:
            print(f"  ⏱  {method}")
    
    return listener.events
```

---

## 处理 JavaScript 弹窗

导航过程中经常会遇到 JavaScript 弹窗（alert/confirm/prompt），它们会阻塞导航流程。CDP 提供了完整的弹窗处理机制。

### 自动处理弹窗

```python
async def handle_javascript_dialog(ws, session_id, accept=True, prompt_text=None):
    """
    处理 JavaScript 弹窗（alert/confirm/prompt）
    
    参数:
        accept: True 表示确认，False 表示取消
        prompt_text: prompt 对话框输入的文本（可选）
    """
    params = {"accept": accept}
    if prompt_text is not None:
        params["promptText"] = prompt_text
    
    await cdp(ws, "Page.handleJavaScriptDialog", params, session_id=session_id)
    
    action = "确认" if accept else "取消"
    print(f"弹窗已处理: {action}")


async def auto_dismiss_dialogs(ws, session_id, auto_accept=True):
    """
    自动处理所有 JavaScript 弹窗
    启用后，页面上出现的所有弹窗都会被自动处理
    """
    async def dialog_handler():
        async for resp in ws:
            data = json.loads(resp)
            if data.get("method") == "Page.javascriptDialogOpening":
                dialog_type = data["params"].get("type", "unknown")
                message = data["params"].get("message", "")
                print(f"📋 自动处理弹窗 [{dialog_type}]: {message[:60]}")
                
                await handle_javascript_dialog(
                    ws, session_id,
                    accept=auto_accept
                )
    
    handler_task = asyncio.create_task(dialog_handler())
    print(f"自动弹窗处理器已启动（{'确认' if auto_accept else '取消'}所有弹窗）")
    return handler_task


async def handle_dialog_with_prompt(ws, session_id, prompt_response):
    """
    处理 prompt 对话框并输入指定文本
    """
    await handle_javascript_dialog(
        ws, session_id,
        accept=True,
        prompt_text=prompt_response
    )


async def navigate_with_dialog_handling(ws, session_id, url, auto_accept=True):
    """
    带自动弹窗处理的导航
    导航过程中如果出现弹窗，自动按指定方式处理
    """
    # 启动自动弹窗处理器
    dialog_task = await auto_dismiss_dialogs(ws, session_id, auto_accept)
    
    # 执行导航
    result = await navigate_to(ws, session_id, url)
    
    # 停止自动处理
    dialog_task.cancel()
    try:
        await dialog_task
    except asyncio.CancelledError:
        pass
    
    return result
```

### 复杂场景：带弹窗的导航流程

```python
async def navigate_through_site(ws, session_id, urls):
    """
    遍历一组 URL，自动处理每个页面可能出现的弹窗
    
    参数:
        urls: 要访问的 URL 列表
    """
    dialog_handler_task = None
    
    for i, url in enumerate(urls):
        print(f"\n--- 访问页面 {i + 1}/{len(urls)}: {url} ---")
        
        # 每个页面启动独立的弹窗处理器
        dialog_handler_task = await auto_dismiss_dialogs(ws, session_id)
        
        # 导航
        await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
        await asyncio.sleep(3)
        
        # 停止弹窗处理器
        if dialog_handler_task:
            dialog_handler_task.cancel()
            try:
                await dialog_handler_task
            except asyncio.CancelledError:
                pass
        
        # 记录当前 URL
        url_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.href"
        }, session_id=session_id)
        current = url_result.get("result", {}).get("value", "")
        print(f"当前页面: {current}")
    
    print("\n所有页面访问完成")
```

---

## Hash 导航 vs 全导航

理解 hash 变化和完整页面导航的区别对历史管理至关重要。

### 检测导航类型

```python
async def detect_navigation_type(ws, session_id, url, hash_only=False):
    """
    执行导航并检测导航类型
    返回：'full'（全页导航）或 'hash'（哈希变化）
    """
    if hash_only:
        # Hash 导航：只改变 # 后面的部分
        # 获取当前基础 URL
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.href.split('#')[0]"
        }, session_id=session_id)
        base = result.get("result", {}).get("value", "")
        
        # 执行 hash 导航
        nav_result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"window.location.hash = '{url.lstrip('#')}'"
        }, session_id=session_id)
        await asyncio.sleep(1)
        
        print(f"📍 Hash 导航: {base}#{url.lstrip('#')}")
        return "hash"
    else:
        # 全页导航
        listener = NavigationListener(ws)
        await listener.start()
        
        await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
        await asyncio.sleep(2)
        
        await listener.stop()
        
        # 检查是否有 frameNavigated 事件
        navigations = listener.get_navigations()
        if any("frameNavigated" in e["method"] for e in listener.events):
            print(f"🌐 全页导航: {url}")
            return "full"
        else:
            print(f"📌 可能是 hash 导航或未变化: {url}")
            return "unknown"
```

### Hash 导航历史管理

```python
async def hash_navigation_sequence(ws, session_id, base_url, hash_list):
    """
    执行一系列的 hash 导航，并在每个步骤记录历史状态
    
    参数:
        base_url: 基础页面 URL
        hash_list: hash 值列表，如 ['#section1', '#section2', '#section3']
    """
    # 先导航到基础页面
    await navigate_to(ws, session_id, base_url)
    await asyncio.sleep(1)
    
    for h in hash_list:
        # 执行 hash 导航
        await cdp(ws, "Runtime.evaluate", {
            "expression": f"window.location.hash = '{h.lstrip('#')}'"
        }, session_id=session_id)
        await asyncio.sleep(1)
        
        # 查看历史
        hist_result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"window.history.length"
        }, session_id=session_id)
        hist_len = hist_result.get("result", {}).get("value", 0)
        
        print(f"  Hash: {h}, 历史长度: {hist_len}")
    
    # 验证可以使用 history.back() 回溯
    print("\n回溯 hash 导航历史:")
    for i in range(len(hash_list)):
        if i == 0:
            continue  # 跳过第一个，开始后退
        await navigate_back(ws, session_id)
        url_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.href"
        }, session_id=session_id)
        current = url_result.get("result", {}).get("value", "")
        print(f"  后退 {i}: {current}")
```

### 完整的导航历史日志

```python
async def log_navigation_history(ws, session_id, label=""):
    """记录当前的导航历史状态并输出详细日志"""
    history = await get_navigation_history(ws, session_id)
    
    print(f"\n{'=' * 50}")
    print(f"导航历史快照 {label}")
    print(f"{'=' * 50}")
    
    current = history["current_index"]
    entries = history["entries"]
    
    if not entries:
        print("（空）")
        return history
    
    for i, entry in enumerate(entries):
        url = entry.get("url", "")
        title = entry.get("title", "")
        trans_type = entry.get("transitionType", "")
        entry_id = entry.get("id", "")
        
        marker = "◀ 当前位置" if i == current else ""
        is_hash = " # " if "#" in url else ""
        
        print(f"  [{i}] {marker} [ID:{entry_id}] {url[:90]}")
        if title:
            print(f"      标题: {title[:50]}")
        print(f"      类型: {trans_type}{is_hash}")
    
    print(f"{'=' * 50}\n")
    return history
```

---

## 实战：自动回溯测试流程

一个完整的测试流程：访问一系列页面 → 记录历史 → 逐步回溯 → 验证每个历史条目：

```python
async def automated_history_test(ws, session_id, test_urls):
    """
    完整的自动回溯测试流程
    
    测试步骤:
    1. 依次访问 test_urls 中的每个 URL
    2. 在每个页面执行操作（可选）
    3. 记录导航历史
    4. 逐步回溯并验证每个页面
    5. 再次前进并验证
    """
    print("=" * 60)
    print("🚀 开始自动回溯测试")
    print("=" * 60)
    
    # ----- 阶段 1: 浏览页面 -----
    print("\n📌 阶段 1: 浏览页面")
    
    for i, url in enumerate(test_urls):
        print(f"\n  [{i + 1}/{len(test_urls)}] 访问: {url}")
        await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
        await asyncio.sleep(2)
        
        # 获取页面标题
        title_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_id=session_id)
        title = title_result.get("result", {}).get("value", "N/A")
        print(f"  页面标题: {title}")
    
    initial_history = await get_navigation_history(ws, session_id)
    
    # ----- 阶段 2: 记录快照 -----
    print("\n📌 阶段 2: 历史记录快照")
    total_entries = len(initial_history["entries"])
    print(f"共访问了 {total_entries} 个页面")
    
    visited_urls = []
    for entry in initial_history["entries"]:
        visited_urls.append(entry.get("url", ""))
    
    # ----- 阶段 3: 逐步回溯 -----
    print("\n📌 阶段 3: 逐步回溯")
    
    back_steps = min(len(test_urls) - 1, total_entries - 1)
    
    for i in range(back_steps):
        print(f"\n  回溯步骤 {i + 1}/{back_steps}")
        
        # 执行后退
        success = await navigate_back(ws, session_id)
        if not success:
            print("  ⛔ 无法继续后退")
            break
        
        # 验证当前页面是之前访问过的
        url_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.href"
        }, session_id=session_id)
        current_url = url_result.get("result", {}).get("value", "")
        
        expected_url = visited_urls[-(i + 2)] if (i + 2) <= len(visited_urls) else None
        if expected_url and current_url == expected_url:
            print(f"  ✅ 验证通过: {current_url[:70]}")
        else:
            print(f"  ⚠️ URL 不匹配: 当前={current_url[:50]}, 期望={str(expected_url)[:50]}")
    
    # ----- 阶段 4: 再次前进 -----
    print("\n📌 阶段 4: 逐步前进")
    
    for i in range(back_steps):
        print(f"\n  前进步骤 {i + 1}/{back_steps}")
        
        success = await navigate_forward(ws, session_id)
        if not success:
            print("  ⛔ 无法继续前进")
            break
        
        url_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.href"
        }, session_id=session_id)
        print(f"  当前: {url_result.get('result', {}).get('value', '')[:70]}")
    
    # ----- 阶段 5: 结果报告 -----
    print("\n" + "=" * 60)
    print("📊 测试结果报告")
    print("=" * 60)
    print(f"  ✅ 页面访问: {len(test_urls)} 个")
    print(f"  ✅ 回溯步骤: {back_steps} 步")
    print(f"  ✅ 前进步骤: {back_steps} 步")
    print(f"  ✅ 历史验证: 完成")
    print("=" * 60)


async def run_history_test():
    """运行历史回溯测试示例"""
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        await enable_page(ws, session_id)
        
        test_pages = [
            "https://example.com",
            "https://example.com/about",
            "https://example.com/services",
            "https://example.com/contact"
        ]
        
        await automated_history_test(ws, session_id, test_pages)

# asyncio.run(run_history_test())
```

### 监控跨页面跳转的数据

```python
async def monitor_navigation_data(ws, session_id, urls):
    """
    监控跨页面导航时页面数据的变化
    在每个页面记录关键指标
    """
    reports = []
    
    for url in urls:
        await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
        await asyncio.sleep(2)
        
        # 收集页面指标
        metrics_result = await cdp(ws, "Performance.getMetrics", session_id=session_id)
        title_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_id=session_id)
        links_result = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.querySelectorAll('a').length"
        }, session_id=session_id)
        
        reports.append({
            "url": url,
            "title": title_result.get("result", {}).get("value", ""),
            "links": links_result.get("result", {}).get("value", 0),
            "metrics": {m["name"]: m["value"] for m in metrics_result.get("metrics", [])}
        })
    
    # 输出报告
    print(f"\n{'=' * 60}")
    print(f"跨页面导航报告 ({len(reports)} 个页面)")
    print(f"{'=' * 60}")
    
    for r in reports:
        print(f"\n  URL: {r['url'][:60]}")
        print(f"  标题: {r['title'][:40]}")
        print(f"  链接数: {r['links']}")
        js_heap = r['metrics'].get('JSHeapUsedSize', 0)
        print(f"  JS 堆: {js_heap / 1024 / 1024:.1f} MB")
    
    return reports
```

---

## 常见踩坑与最佳实践

### 踩坑 1：Page.enable 必须在导航前调用

```python
# ❌ 错误的顺序
await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
await cdp(ws, "Page.enable", session_id=session_id)  # 导航事件已错过

# ✅ 正确的顺序
await cdp(ws, "Page.enable", session_id=session_id)  # 先启用
await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
```

### 踩坑 2：getNavigationHistory 的条目 ID 有时效性

```python
# 导航后历史条目的 ID 可能变化
# 如果需要多次使用，每次重新获取

# 第一次获取
history1 = await get_navigation_history(ws, session_id)
entry_id = history1["entries"][0]["id"]

# ... 执行一些导航 ...

# 旧的 entry_id 可能已失效
# 需要重新获取
history2 = await get_navigation_history(ws, session_id)
```

### 踩坑 3：history.length 不包含初始页面

```python
# 导航到 example.com → 此时 history.length = 1
# 导航到 example.com/about → history.length = 2
# 导航到 example.com/contact → history.length = 3
# 后退 → history.length 不变（仍为 3）
```

### 踩坑 4：javascript: 导航不会产生历史条目

```python
# navigate("javascript:void(0)") 不会加入历史
# hash 导航（location.hash = '#x'）会产生历史
# 全页导航会产生历史
```

### 踩坑 5：弹窗阻塞导航后的恢复

```python
# 如果弹窗出现后没有处理，后续 CDP 命令可能不响应
# 解决方案：始终监听 javascriptDialogOpening 事件并及时处理

# 推荐的统一处理方式
async def safe_navigate(ws, session_id, url):
    handler = await auto_dismiss_dialogs(ws, session_id)
    try:
        await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
        await asyncio.sleep(3)
    finally:
        handler.cancel()
        try:
            await handler
        except asyncio.CancelledError:
            pass
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| Page.enable | 在第一次导航前必须启用 |
| 弹窗处理 | 始终启动 auto_dismiss_dialogs 避免阻塞 |
| 历史条目 ID | 每次使用前重新获取，有有效期 |
| hash vs 全页 | hash 导航不触发 frameNavigated 重载事件 |
| 导航等待 | 使用 frameStoppedLoading 事件而非固定 sleep |
| CDP 连接 | 导航期间不要中断 WebSocket 连接 |
| 错误处理 | 检查 Page.navigate 返回的 errorText 字段 |

---

## 完整参考：CDP 导航历史管理类

```python
class CDPNavigationManager:
    """CDP 页面导航历史管理器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self._dialog_handler = None
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method, "params": params or {}}
        if self.session_id:
            msg["sessionId"] = self.session_id
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def enable(self):
        """启用导航管理"""
        await self._cmd("Page.enable")
        print("导航管理器已启用")
    
    async def go(self, url):
        """导航到 URL"""
        result = await self._cmd("Page.navigate", {"url": url})
        error = result.get("errorText")
        if error:
            print(f"导航失败: {error}")
            return False
        await asyncio.sleep(2)
        return True
    
    async def back(self):
        """后退"""
        await self._cmd("Runtime.evaluate",
                       {"expression": "window.history.back()"})
        await asyncio.sleep(2)
    
    async def forward(self):
        """前进"""
        await self._cmd("Runtime.evaluate",
                       {"expression": "window.history.forward()"})
        await asyncio.sleep(2)
    
    async def get_history(self):
        """获取导航历史"""
        result = await self._cmd("Page.getNavigationHistory")
        return result.get("entries", []), result.get("currentIndex", -1)
    
    async def go_to_entry(self, entry_id):
        """跳转到指定历史条目"""
        await self._cmd("Page.navigateToHistoryEntry", {"entryId": entry_id})
        await asyncio.sleep(2)
        result = await self._cmd("Runtime.evaluate",
                                {"expression": "window.location.href"})
        return result.get("result", {}).get("value", "")
    
    async def jump(self, steps):
        """在历史中跳转步数"""
        entries, current = await self.get_history()
        target = current + steps
        if 0 <= target < len(entries):
            return await self.go_to_entry(entries[target]["id"])
        print(f"无法跳转: 目标索引 {target} 超出范围")
        return None
    
    async def enable_auto_dialog(self, accept=True):
        """启用自动弹窗处理"""
        async def handler():
            async for resp in self.ws:
                data = json.loads(resp)
                if data.get("method") == "Page.javascriptDialogOpening":
                    await self._cmd("Page.handleJavaScriptDialog",
                                   {"accept": accept})
        self._dialog_handler = asyncio.create_task(handler())
    
    async def disable_auto_dialog(self):
        """禁用自动弹窗处理"""
        if self._dialog_handler:
            self._dialog_handler.cancel()
            try:
                await self._dialog_handler
            except asyncio.CancelledError:
                pass
            self._dialog_handler = None
    
    async def print_history(self):
        """打印当前历史记录"""
        entries, current = await self.get_history()
        print(f"\n导航历史 ({len(entries)} 条):")
        for i, e in enumerate(entries):
            marker = " ◀" if i == current else ""
            print(f"  [{i}]{marker} {e.get('url', '')[:80]}")
        return entries
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    nav = CDPNavigationManager(ws, session_id)
    
    await nav.enable()
    await nav.enable_auto_dialog()
    
    # 浏览
    await nav.go("https://example.com")
    await nav.go("https://example.com/about")
    await nav.go("https://example.com/contact")
    
    # 查看历史
    await nav.print_history()
    
    # 后退到首页
    await nav.jump(-2)
    
    # 禁用弹窗自动处理
    await nav.disable_auto_dialog()
```

---

> **总结**：CDP 的 Page 域提供了完整的浏览器导航历史管理能力。通过 `Page.getNavigationHistory` 获取历史条目、`Page.navigateToHistoryEntry` 跳转到任意条目、结合 `Page.handleJavaScriptDialog` 处理弹窗，以及监听 `frameNavigated` 等事件，你可以构建比 Selenium 更精细的导航控制方案。关键在于区分 hash 导航和全页导航的区别，以及始终在导航前启用 Page.enable。

---

*上一篇回顾：CDP 剪贴板操作指南：用 Python 读写系统剪贴板。*

*下一篇预告：CDP 协议扩展指南：自定义 CDP 域与 Chrome 扩展。*