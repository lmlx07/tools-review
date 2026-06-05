---
title: CDP 多标签页管理：用 Python 控制多个页面
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 浏览器自动化
  - 多标签页
  - Target
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）管理浏览器多标签页。涵盖获取所有目标、创建新标签页、连接到指定页面、在标签页间切换、监听标签页变化事件、隔离各标签页的 Session，以及完整的 TargetManager 封装类。
---

> **一句话总结**：CDP 的 Target 域让你像浏览器窗口管理器一样控制所有标签页——你可以列出所有打开的页面、创建新标签页、连接并切换到任意页面、监听标签页的创建与关闭，每个连接都有独立的 Session 上下文。

---

## 目录

1. [为什么需要多标签页管理](#为什么需要多标签页管理)
2. [前置准备：连接 Chrome](#前置准备连接-chrome)
3. [获取所有目标标签页](#获取所有目标标签页)
4. [创建新标签页](#创建新标签页)
5. [连接到指定标签页](#连接到指定标签页)
6. [在多个标签页间切换](#在多个标签页间切换)
7. [监听标签页变化](#监听标签页变化)
8. [关闭标签页](#关闭标签页)
9. [完整参考：CDP TargetManager 类](#完整参考cdp-targetmanager-类)
10. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么需要多标签页管理

在实际的浏览器自动化中，单页面操作往往不够用：

| 场景 | 说明 |
|------|------|
| 多任务并行 | 同时监控多个页面，如对比两个电商网站价格 |
| 页面隔离 | 主页面处理登录，新标签页执行敏感操作 |
| 爬虫加速 | 多个标签页并发请求，提升数据采集效率 |
| 窗口管理 | 自动打开/关闭推广链接，保持浏览器整洁 |
| 反检测策略 | 多个标签页使用不同指纹或上下文 |

CDP 的 Target 域提供了完整的标签页生命周期管理能力。与浏览器不同概念对应：

| CDP 概念 | 浏览器对应 |
|----------|-----------|
| Target | 标签页、iframe、Service Worker 等 |
| TargetID | 每个标签页的唯一标识符 |
| Session | 与特定标签页建立的通信通道 |
| Browser Context | 隔离的浏览器上下文（类似无痕窗口） |

---

## 前置准备：连接 Chrome

使用标准的 CDP 连接模式：

```python
import asyncio, json, websockets

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
```

> **注意**：连接 URL 需要使用 `devtools/browser` 路径（而非某个标签页的 WebSocket URL），这样 `Target` 域才能管理所有标签页。

---

## 获取所有目标标签页

### Target.getTargets

最基本的操作——列出浏览器中所有可见的目标：

```python
async def list_all_targets(ws):
    """列出所有标签页信息"""
    result = await cdp(ws, "Target.getTargets")
    targets = result.get("targetInfos", [])
    
    for t in targets:
        print(f"ID: {t['targetId'][:12]}...")
        print(f"  标题: {t.get('title', '')}")
        print(f"  URL: {t.get('url', '')[:60]}")
        print(f"  类型: {t.get('type', '')}")
        print(f"  附加状态: {'已连接' if t.get('attached') else '未连接'}")
        print()
    return targets

# 使用
async def demo_list_targets():
    async with websockets.connect(CDP_URL) as ws:
        targets = await list_all_targets(ws)
        print(f"共 {len(targets)} 个目标")
```

输出示例：

```
ID: 3A1B2C3D4E5F...
  标题: 百度一下，你就知道
  URL: https://www.baidu.com/
  类型: page
  附加状态: 未连接

ID: 6G7H8I9J0K1L...
  标题: 新标签页
  URL: chrome://new-tab-page/
  类型: page
  附加状态: 未连接
```

### 筛选特定类型的目标

`targetInfo` 中的 `type` 字段用于区分目标类型：

```python
async def get_pages_only(ws):
    """只获取 page 类型的标签页"""
    result = await cdp(ws, "Target.getTargets")
    pages = [t for t in result.get("targetInfos", [])
             if t.get("type") == "page"]
    return pages

async def get_active_page(ws):
    """获取活动标签页（通常为第一个 page）"""
    pages = await get_pages_only(ws)
    return pages[0] if pages else None
```

---

## 创建新标签页

### Target.createTarget

打开全新的空白标签页或指定 URL：

```python
async def create_new_tab(ws, url="about:blank", width=None, height=None):
    """创建新标签页"""
    params = {"url": url}
    if width and height:
        params["width"] = width
        params["height"] = height
    
    result = await cdp(ws, "Target.createTarget", params)
    target_id = result.get("targetId")
    print(f"新标签页创建成功，ID: {target_id}")
    return target_id

# 使用
async def demo_create_tab():
    async with websockets.connect(CDP_URL) as ws:
        # 创建空白页
        blank_id = await create_new_tab(ws)
        print(f"空白标签页: {blank_id}")
        
        # 打开指定 URL
        url_id = await create_new_tab(ws, "https://example.com")
        print(f"导航标签页: {url_id}")
        
        # 创建指定尺寸的窗口
        sized_id = await create_new_tab(ws, "about:blank", 800, 600)
```

### 在新窗口打开

通过设置 `newWindow=True` 可在新窗口（而非新标签页）中打开目标：

```python
async def create_new_window(ws, url="about:blank"):
    """在新窗口中创建目标"""
    result = await cdp(ws, "Target.createTarget", {
        "url": url,
        "newWindow": True
    })
    target_id = result.get("targetId")
    print(f"新窗口目标创建成功，ID: {target_id}")
    return target_id
```

---

## 连接到指定标签页

### Target.attachToTarget

创建新标签页后，需要建立 Session 连接才能操作它：

```python
async def attach_to_target(ws, target_id):
    """连接到指定标签页"""
    result = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id,
        "flatten": True  # 推荐启用 flatten
    })
    session_id = result.get("sessionId")
    print(f"已连接到目标 {target_id[:12]}..., Session: {session_id[:12]}...")
    return session_id
```

### flatten 模式说明

`flatten: True` 意味着所有命令通过同一个 WebSocket 发送（带上 `sessionId`），而非为每个会话建立独立 WebSocket。这是更推荐的模式：

```python
# flatten=True（推荐）：单 WS + sessionId 路由
async def operate_via_flatten(ws, session_id):
    await cdp(ws, "Page.navigate",
              {"url": "https://example.com"}, session_id=session_id)
    result = await cdp(ws, "Runtime.evaluate",
              {"expression": "document.title"}, session_id=session_id)
    return result.get("result", {}).get("value")

# flatten=False（不推荐）：返回独立的 WebSocket URL
# 需要在每个目标建立独立连接，管理更复杂
```

### 获取目标页面的 WebSocket URL（非 flatten 方式）

```python
async def get_target_ws_url(ws, target_id):
    """获取目标 WebSocket URL（用于非 flatten 连接）"""
    # 先确保获取到最新目标信息
    targets = await cdp(ws, "Target.getTargets")
    for t in targets.get("targetInfos", []):
        if t["targetId"] == target_id:
            # 每个 page target 都有独立的 devtools URL
            return t.get("devtoolsFrontendUrl", "")
    return None
```

---

## 在多个标签页间切换

### 多标签页操作实战

```python
async def demo_multi_tab():
    async with websockets.connect(CDP_URL) as ws:
        # 1. 创建三个标签页
        target_a = await create_new_tab(ws, "https://news.ycombinator.com")
        target_b = await create_new_tab(ws, "https://www.reddit.com")
        target_c = await create_new_tab(ws, "https://github.com")
        
        # 2. 为每个标签页建立 Session
        session_a = await attach_to_target(ws, target_a)
        session_b = await attach_to_target(ws, target_b)
        session_c = await attach_to_target(ws, target_c)
        
        # 3. 分别在三个页面中执行操作
        # 页面 A：获取标题
        result_a = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_a)
        title_a = result_a.get("result", {}).get("value", "")
        print(f"标签页 A 标题: {title_a}")
        
        # 页面 B：获取标题
        result_b = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_b)
        title_b = result_b.get("result", {}).get("value", "")
        print(f"标签页 B 标题: {title_b}")
        
        # 页面 C：获取标题
        result_c = await cdp(ws, "Runtime.evaluate", {
            "expression": "document.title"
        }, session_c)
        title_c = result_c.get("result", {}).get("value", "")
        print(f"标签页 C 标题: {title_c}")
```

### 按 URL 模式搜索目标

在多个标签页中查找特定目标：

```python
async def find_target_by_url(ws, url_pattern):
    """按 URL 模式查找匹配的标签页"""
    result = await cdp(ws, "Target.getTargets")
    for t in result.get("targetInfos", []):
        if url_pattern in t.get("url", ""):
            print(f"找到匹配: {t.get('title')} @ {t.get('url')[:60]}")
            return t
    return None

async def find_target_by_title(ws, title_pattern):
    """按标题模式查找匹配的标签页"""
    result = await cdp(ws, "Target.getTargets")
    for t in result.get("targetInfos", []):
        if title_pattern.lower() in t.get("title", "").lower():
            return t
    return None
```

### 并行操作多个标签页

使用 `asyncio.gather` 并行处理多个标签页：

```python
async def get_page_title(ws, session_id):
    """获取单个标签页标题"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": "document.title"
    }, session_id)
    return result.get("result", {}).get("value", "N/A")

async def parallel_tab_operation(ws, sessions_and_urls):
    """并行获取多个标签页的信息"""
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

## 监听标签页变化

### Target.setDiscoverTargets

启用后可以实时收到标签页的创建、关闭、更新事件：

```python
async def target_event_listener(ws, timeout=60):
    """监听标签页变化事件"""
    # 启用目标发现
    await cdp(ws, "Target.setDiscoverTargets", {"discover": True})
    
    print("开始监听标签页变化...")
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
                    print(f"[创建] 新标签页: {info.get('title', '')}")
                    print(f"       URL: {info.get('url', '')[:60]}")
                    print(f"       类型: {info.get('type', '')}")
                    print(f"       ID: {info.get('targetId', '')[:16]}...")
                
                elif method == "Target.targetDestroyed":
                    tid = params.get("targetId", "")
                    print(f"[关闭] 标签页 {tid[:16]}...")
                
                elif method == "Target.targetInfoChanged":
                    info = params.get("targetInfo", {})
                    print(f"[更新] {info.get('title', '')} - {info.get('url', '')[:50]}")
    except asyncio.TimeoutError:
        print("监听结束")
```

### 使用事件监听管理标签页

```python
async def demo_target_watcher():
    """演示：监听标签页变化 + 自动操作"""
    async with websockets.connect(CDP_URL) as ws:
        # 先启动监听器（后台任务）
        listener = asyncio.create_task(
            target_event_listener(ws, timeout=20)
        )
        
        await asyncio.sleep(1)  # 确保监听器就绪
        
        # 创建新标签页（会触发 targetCreated）
        tid = await create_new_tab(ws, "https://example.com")
        print(f"手动创建了标签页: {tid[:12]}...")
        
        await asyncio.sleep(2)
        
        # 关闭标签页（会触发 targetDestroyed）
        await cdp(ws, "Target.closeTarget", {"targetId": tid})
        print(f"手动关闭了标签页: {tid[:12]}...")
        
        await listener
```

---

## 关闭标签页

### Target.closeTarget

```python
async def close_target(ws, target_id):
    """关闭指定标签页"""
    try:
        result = await cdp(ws, "Target.closeTarget", {"targetId": target_id})
        success = result.get("success", False)
        if success:
            print(f"标签页 {target_id[:12]}... 已关闭")
        else:
            print(f"关闭失败: {target_id[:12]}...")
        return success
    except Exception as e:
        print(f"关闭异常: {e}")
        return False

async def close_all_targets(ws, exclude_current=True):
    """关闭所有标签页（可选排除当前）"""
    result = await cdp(ws, "Target.getTargets")
    targets = result.get("targetInfos", [])
    current_id = None
    
    # 如果需要排除当前标签页，先获取它
    if exclude_current and targets:
        # 通常第一个 page 被认为是当前页
        current_id = targets[0].get("targetId") if targets else None
    
    closed = 0
    for t in targets:
        tid = t.get("targetId")
        if exclude_current and tid == current_id:
            continue
        if await close_target(ws, tid):
            closed += 1
    
    print(f"共关闭 {closed} 个标签页")
    return closed
```

### 按类型批量关闭

```python
async def close_targets_by_type(ws, target_type="page"):
    """按类型批量关闭目标"""
    result = await cdp(ws, "Target.getTargets")
    targets = [t for t in result.get("targetInfos", [])
               if t.get("type") == target_type]
    
    count = 0
    for t in targets:
        if await close_target(ws, t["targetId"]):
            count += 1
    
    print(f"已关闭 {count} 个 {target_type} 类型的目标")
    return count
```

---

## 完整参考：CDP TargetManager 类

```python
import asyncio
import json
import websockets
from typing import Optional, List, Dict, Callable


class CDPTargetManager:
    """CDP 多标签页管理器"""
    
    def __init__(self, ws_url: str):
        self.ws_url = ws_url
        self.ws = None
        self._sessions: Dict[str, str] = {}  # targetId → sessionId
        self._cmd_id = 0
    
    async def connect(self):
        """建立 WebSocket 连接"""
        self.ws = await websockets.connect(self.ws_url)
        return self
    
    async def disconnect(self):
        """关闭连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
    
    async def _cdp(self, method: str, params: dict = None,
                   session_id: str = None) -> dict:
        """发送 CDP 命令"""
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
        """列出所有目标，可选按类型筛选"""
        result = await self._cdp("Target.getTargets")
        targets = result.get("targetInfos", [])
        if target_type:
            targets = [t for t in targets if t.get("type") == target_type]
        return targets
    
    async def create_target(self, url: str = "about:blank",
                           width: int = None, height: int = None,
                           new_window: bool = False) -> str:
        """创建新标签页，返回 targetId"""
        params = {"url": url}
        if width and height:
            params["width"] = width
            params["height"] = height
        if new_window:
            params["newWindow"] = True
        result = await self._cdp("Target.createTarget", params)
        return result.get("targetId")
    
    async def attach(self, target_id: str) -> str:
        """附加到指定目标，返回 sessionId"""
        result = await self._cdp("Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = result.get("sessionId")
        self._sessions[target_id] = session_id
        return session_id
    
    async def detach(self, target_id: str):
        """从目标分离"""
        session_id = self._sessions.get(target_id)
        if session_id:
            await self._cdp("Target.detachFromTarget",
                          {"sessionId": session_id})
            self._sessions.pop(target_id, None)
    
    async def close_target(self, target_id: str) -> bool:
        """关闭目标"""
        result = await self._cdp("Target.closeTarget",
                                {"targetId": target_id})
        self._sessions.pop(target_id, None)
        return result.get("success", False)
    
    async def navigate(self, target_id: str, url: str) -> dict:
        """在指定标签页中导航"""
        session_id = self._sessions.get(target_id)
        if not session_id:
            raise ValueError(f"未连接到目标 {target_id}")
        return await self._cdp("Page.navigate",
                              {"url": url}, session_id)
    
    async def evaluate(self, target_id: str, expression: str) -> dict:
        """在指定标签页中执行 JS"""
        session_id = self._sessions.get(target_id)
        if not session_id:
            raise ValueError(f"未连接到目标 {target_id}")
        return await self._cdp("Runtime.evaluate",
                              {"expression": expression}, session_id)
    
    async def activate_target(self, target_id: str):
        """激活（前置）指定标签页"""
        await self._cdp("Target.activateTarget",
                       {"targetId": target_id})
    
    async def find_target(self, url_pattern: str = None,
                         title_pattern: str = None) -> Optional[dict]:
        """按 URL 或标题查找目标"""
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
        """启用/停用目标发现"""
        await self._cdp("Target.setDiscoverTargets",
                       {"discover": discover})
    
    async def get_session(self, target_id: str) -> Optional[str]:
        """获取指定目标的 sessionId"""
        return self._sessions.get(target_id)
    
    def get_attached_targets(self) -> List[str]:
        """获取所有已附加的目标 ID"""
        return list(self._sessions.keys())
    
    # ----- 高级方法 -----
    
    async def create_with_attach(self, url: str = "about:blank") -> tuple:
        """创建标签页并自动附加，返回 (targetId, sessionId)"""
        target_id = await self.create_target(url)
        session_id = await self.attach(target_id)
        return target_id, session_id
    
    async def close_all_pages(self, exclude_ids: List[str] = None):
        """关闭所有 page 类型目标"""
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
        """获取所有已附加标签页的标题"""
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

**使用示例：**

```python
async def demo_target_manager():
    mgr = CDPTargetManager(CDP_URL)
    await mgr.connect()
    
    # 列出当前所有标签页
    targets = await mgr.list_targets("page")
    print(f"当前有 {len(targets)} 个标签页")
    
    # 创建三个新标签页
    urls = [
        "https://news.ycombinator.com",
        "https://www.reddit.com",
        "https://github.com"
    ]
    target_ids = []
    for url in urls:
        tid, sid = await mgr.create_with_attach(url)
        target_ids.append(tid)
        print(f"创建并附加: {tid[:12]}...")
    
    await asyncio.sleep(3)  # 等待加载
    
    # 获取所有标题
    titles = await mgr.snapshot_all_titles()
    for tid, title in titles.items():
        print(f"  [{tid[:12]}...] {title}")
    
    # 激活特定标签页
    await mgr.activate_target(target_ids[0])
    
    # 关闭所有新建标签页
    for tid in target_ids:
        await mgr.close_target(tid)
    
    await mgr.disconnect()
```

---

## 常见踩坑与最佳实践

### 踩坑 1：WebSocket URL 选择错误

连接到浏览器的 WebSocket URL 有两种：

```python
# ❌ 连接到单个标签页的 WS URL（无法管理其他标签页）
page_ws_url = "ws://127.0.0.1:9222/devtools/page/3A1B2C..."
async with websockets.connect(page_ws_url) as ws:
    # Target.getTargets 在这里不可用！

# ✅ 连接到浏览器的 WS URL（可以管理所有标签页）
browser_ws_url = "ws://127.0.0.1:9222/devtools/browser/6G7H8I..."
async with websockets.connect(browser_ws_url) as ws:
    result = await cdp(ws, "Target.getTargets")  # ✅ 正常工作
```

### 踩坑 2：忘记启用必要域

```python
# ❌ 直接导航，没有启用 Page 域
await mgr.navigate(target_id, "https://example.com")

# ✅ 必须先启用需要的域
session_id = mgr.get_session(target_id)
await mgr._cdp("Page.enable", session_id=session_id)
await mgr._cdp("Network.enable", session_id=session_id)
await mgr.navigate(target_id, "https://example.com")
```

### 踩坑 3：Session 隔离

每个标签页的 Session 是独立的，不要混用：

```python
# ❌ 错误：用 session_a 去操作 target_b
result = await cdp(ws, "Runtime.evaluate",
    {"expression": "document.title"}, session_id=session_a)  # 但 target_b 需要 session_b

# ✅ 正确：每个 target 对应自己的 session
result = await cdp(ws, "Runtime.evaluate",
    {"expression": "document.title"}, session_id=session_b)
```

### 踩坑 4：关闭后操作已销毁的目标

```python
# ❌ 关闭后继续发送命令
await mgr.close_target(target_id)
await mgr.navigate(target_id, "https://example.com")  # 报错！

# ✅ 关闭后清理引用
await mgr.close_target(target_id)
assert target_id not in mgr.get_attached_targets()
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 连接 URL | 始终使用 `devtools/browser/` 路径 |
| flatten 模式 | 推荐启用，简化连接管理 |
| Session 映射 | 维护 targetId → sessionId 字典 |
| 资源清理 | 使用完后 detach/close，避免泄漏 |
| 并发控制 | 用 semaphore 限制并行操作数 |
| 错误处理 | 每个标签页操作单独 try/except |

---

> **总结**：CDP 的 Target 域提供了完整的浏览器多标签页管理能力。通过 TargetManager 封装类，你可以轻松实现创建、连接、切换、关闭标签页的完整生命周期管理，并且每个标签页拥有独立的 Session 上下文，互不干扰。

*上一篇回顾：CDP 事件系统指南：用 Python 监听浏览器事件。*

*下一篇预告：CDP 输入自动化指南：用 Python 模拟鼠标键盘。*