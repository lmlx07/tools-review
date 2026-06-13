---
title: CDP Frame 管理指南：用 Python 处理 iframe 与跨域框架
date: 2026-06-05 21:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Frame
  - iframe
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）管理浏览器框架（Frame）。涵盖获取 Frame 树、在 iframe 中执行 JavaScript、处理跨域框架、监听 Frame 生命周期事件，以及跨框架数据提取。
---

> **一句话总结**：CDP 的 Page 域提供了完整的 Frame 管理能力——你可以获取整个 Frame 树、在任意 iframe 中执行代码、监听 Frame 的加载和销毁事件，无论它们是否跨域。

---

## 目录

1. [为什么用 CDP 管理 Frame](#为什么用-cdp-管理-frame)
2. [获取 Frame 树](#获取-frame-树)
3. [在 iframe 中执行代码](#在-iframe-中执行代码)
4. [监听 Frame 事件](#监听-frame-事件)
5. [处理跨域 Frame](#处理跨域-frame)
6. [实战：提取所有 iframe 内容](#实战提取所有-iframe-内容)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 管理 Frame

在传统自动化中，处理 iframe 非常繁琐——需要先 switchTo 才能操作。CDP 的方式更直接：

| 功能 | Selenium | CDP |
|------|----------|-----|
| 获取所有 iframe | ❌ 需遍历 | ✅ 一步获取 Frame 树 |
| 在 iframe 中执行 JS | ✅ switchTo 后 | ✅ 直接指定 frameId |
| 跨域 iframe | ⚠️ 同源限制 | ✅ 无限制 |
| Frame 生命周期 | ❌ 需轮询 | ✅ 原生事件 |
| 主 Frame 与子 Frame 关系 | ⚠️ 隐式 | ✅ 显式树形结构 |

---

## 获取 Frame 树

### 基础：获取页面 Frame 树

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


async def get_frame_tree(ws, session_id):
    """获取页面的完整 Frame 树"""
    result = await cdp(ws, session_id, "Page.getFrameTree")
    return result.get("frameTree", {})


def print_frame_tree(frame_tree, indent=0):
    """递归打印 Frame 树"""
    if not frame_tree:
        return
    
    frame = frame_tree.get("frame", {})
    prefix = "  " * indent
    
    print(f"{prefix}Frame: {frame.get('id', '')}")
    print(f"{prefix}  URL: {frame.get('url', '')}")
    print(f"{prefix}  Name: {frame.get('name', '(unnamed)')}")
    print(f"{prefix}  Security Origin: {frame.get('securityOrigin', '')}")
    
    for child in frame_tree.get("childFrames", []):
        print_frame_tree(child, indent + 1)


# 使用示例
async def example():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        await cdp(ws, session_id, "Page.navigate", {
            "url": "https://example.com"
        })
        await asyncio.sleep(3)
        
        tree = await get_frame_tree(ws, session_id)
        print_frame_tree(tree)
```

### 获取当前页面的所有 Frame URL

```python
async def get_all_frame_urls(ws, session_id):
    """获取页面中所有 Frame 的 URL"""
    def extract_urls(frame_tree):
        urls = {}
        frame = frame_tree.get("frame", {})
        fid = frame.get("id", "")
        if fid:
            urls[fid] = {
                "url": frame.get("url", ""),
                "name": frame.get("name", ""),
                "origin": frame.get("securityOrigin", ""),
            }
        for child in frame_tree.get("childFrames", []):
            urls.update(extract_urls(child))
        return urls
    
    tree = await get_frame_tree(ws, session_id)
    return extract_urls(tree)


def list_frames(ws, session_id, tree):
    """列出所有 Frame 信息"""
    frames = []
    
    def walk(node, parent_id=None):
        frame = node.get("frame", {})
        info = {
            "id": frame.get("id"),
            "url": frame.get("url"),
            "name": frame.get("name", ""),
            "parent_id": parent_id,
        }
        frames.append(info)
        for child in node.get("childFrames", []):
            walk(child, info["id"])
    
    walk(tree)
    return frames
```

---

## 在 iframe 中执行代码

### 通过 frameId 执行 JavaScript

```python
async def evaluate_in_frame(ws, session_id, frame_id, expression):
    """在指定 Frame 中执行 JavaScript"""
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": expression,
        "contextId": frame_id  # 注意：实际需要用 ExecutionContextId
    })
    return result


async def get_frame_execution_context(ws, session_id, frame_id):
    """获取指定 Frame 的执行上下文 ID"""
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "1+1",
        "uniqueContextId": frame_id
    })
    return result.get("executionContextId")
```

### 遍历所有 Frame 并执行

```python
async def execute_in_all_frames(ws, session_id, expression):
    """在所有 Frame 中执行 JavaScript 并收集结果"""
    tree = await get_frame_tree(ws, session_id)
    results = {}
    
    def walk_and_exec(node):
        frame = node.get("frame", {})
        fid = frame.get("id")
        if fid:
            try:
                result = await cdp(ws, session_id, "Runtime.evaluate", {
                    "expression": expression,
                    "uniqueContextId": fid
                })
                results[fid] = {
                    "url": frame.get("url"),
                    "result": result.get("result", {})
                }
            except Exception as e:
                results[fid] = {"url": frame.get("url"), "error": str(e)}
        
        for child in node.get("childFrames", []):
            walk_and_exec(child)
    
    walk_and_exec(tree)
    return results


# 使用示例：在所有 Frame 中获取标题
async def get_all_titles(ws, session_id):
    """获取所有 Frame 的页面标题"""
    results = await execute_in_all_frames(
        ws, session_id, "document.title"
    )
    
    for fid, data in results.items():
        if "result" in data:
            title = data["result"].get("value", "")
            print(f"[{data['url']}] 标题: {title}")
    
    return results
```

### 查找特定 iframe 并操作

```python
async def find_frame_by_selector(ws, session_id, css_selector):
    """通过 CSS 选择器找到 iframe 的 frameId"""
    # 先获取 iframe 元素
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"""
            (function() {{
                const el = document.querySelector('{css_selector}');
                return el ? el.contentWindow?.frameElement?.ownerDocument?.defaultView?.frameElement?.id || el.id : null;
            }})()
        """
    })
    return result.get("result", {}).get("value")


async def get_frame_by_name(ws, session_id, name):
    """通过 name 属性查找 Frame"""
    tree = await get_frame_tree(ws, session_id)
    
    def search(node):
        frame = node.get("frame", {})
        if frame.get("name") == name:
            return frame
        for child in node.get("childFrames", []):
            result = search(child)
            if result:
                return result
        return None
    
    return search(tree)
```

---

## 监听 Frame 事件

### Frame 生命周期事件

```python
async def enable_frame_events(ws, session_id):
    """监听 Frame 相关事件"""
    # Frame 事件不需要专门的 enable，Page 域默认启用
    
    # 常用 Frame 事件：
    # Page.frameAttached      - 新 Frame 被添加
    # Page.frameDetached      - Frame 被移除
    # Page.frameNavigated     - Frame 导航完成
    # Page.frameStartedLoading - Frame 开始加载
    # Page.frameStoppedLoading - Frame 停止加载
    # Page.navigatedWithinDocument - 同文档导航
    pass


async def monitor_frames(ws, session_id, duration=30):
    """监控所有 Frame 事件"""
    events = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < duration:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            
            if method.startswith("Page.frame"):
                events.append({
                    "method": method,
                    "params": data.get("params", {})
                })
                
                if method == "Page.frameAttached":
                    p = data["params"]
                    print(f"[Frame 添加] {p.get('frameId', '')} -> "
                          f"父 Frame: {p.get('parentFrameId', '')}")
                
                elif method == "Page.frameNavigated":
                    p = data["params"]
                    frame = p.get("frame", {})
                    print(f"[Frame 导航] {frame.get('id', '')}: "
                          f"{frame.get('url', '')}")
                
                elif method == "Page.frameDetached":
                    p = data["params"]
                    print(f"[Frame 移除] {p.get('frameId', '')}")
                    
        except asyncio.TimeoutError:
            continue
    
    return events
```

---

## 处理跨域 Frame

### CDP 处理跨域 iframe 的优势

与 JavaScript 不同，CDP 不受同源策略限制——可以直接操作跨域 iframe：

```python
async def access_cross_origin_frame(ws, session_id, frame_id):
    """访问跨域 Frame 的内容"""
    # CDP 可以直接在跨域 iframe 中执行代码
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "document.body.innerText.substring(0, 200)",
        "uniqueContextId": frame_id
    })
    return result.get("result", {}).get("value", "")


async def extract_cross_origin_content(ws, session_id):
    """提取所有 Frame（包括跨域）的内容"""
    tree = await get_frame_tree(ws, session_id)
    contents = {}
    
    def extract(node):
        frame = node.get("frame", {})
        fid = frame.get("id")
        if fid:
            try:
                result = await cdp(ws, session_id, "Runtime.evaluate", {
                    "expression": "document.body?.innerText || ''",
                    "uniqueContextId": fid
                })
                contents[fid] = {
                    "url": frame.get("url"),
                    "origin": frame.get("securityOrigin"),
                    "content": (result.get("result", {}).get("value", "")[:200])
                }
            except Exception as e:
                contents[fid] = {"url": frame.get("url"), "error": str(e)}
        
        for child in node.get("childFrames", []):
            extract(child)
    
    extract(tree)
    return contents
```

---

## 实战：提取所有 iframe 内容

综合运用以上技术，构建一个跨框架内容提取器：

```python
async def scrape_all_frames(ws, session_id, url):
    """导航到页面并提取所有 Frame 的内容"""
    print(f"导航到: {url}")
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    # 1. 获取 Frame 树
    tree = await get_frame_tree(ws, session_id)
    frames = list_frames(ws, session_id, tree)
    
    print(f"发现 {len(frames)} 个 Frame:")
    for f in frames:
        print(f"  [{f['id'][:12]}...] {f['name'] or '(unnamed)'} - {f['url'][:60]}")
    
    # 2. 提取每个 Frame 的关键信息
    data = {}
    for f in frames:
        fid = f["id"]
        try:
            # 获取标题
            title_result = await cdp(ws, session_id, "Runtime.evaluate", {
                "expression": "document.title",
                "uniqueContextId": fid
            })
            title = title_result.get("result", {}).get("value", "")
            
            # 获取所有链接
            links_result = await cdp(ws, session_id, "Runtime.evaluate", {
                "expression": "Array.from(document.querySelectorAll('a')).map(a => ({href: a.href, text: a.textContent.trim().substring(0, 50)}))",
                "uniqueContextId": fid,
                "returnByValue": True
            })
            links = links_result.get("result", {}).get("value", [])
            
            data[fid] = {
                "url": f["url"],
                "title": title,
                "links_count": len(links),
                "links": links[:10]  # 只保存前 10 个
            }
        except Exception as e:
            data[fid] = {"url": f["url"], "error": str(e)}
    
    return data


async def wait_for_iframe(ws, session_id, selector, timeout=15):
    """等待特定 iframe 加载完成"""
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < timeout:
        # 检查 iframe 是否存在
        result = await cdp(ws, session_id, "Runtime.evaluate", {
            "expression": f"!!document.querySelector('{selector}')",
            "returnByValue": True
        })
        
        if result.get("result", {}).get("value"):
            # iframe 存在，获取 Frame 树
            tree = await get_frame_tree(ws, session_id)
            frames = list_frames(ws, session_id, tree)
            
            # 这里假设第二个 Frame 是我们的目标
            # 实际使用中需要更精确的匹配
            if len(frames) > 1:
                print(f"iframe 已加载，共 {len(frames)} 个 Frame")
                return frames[1]
        
        await asyncio.sleep(1)
    
    print(f"超时：未找到 iframe ({selector})")
    return None
```

---

## 常见踩坑与最佳实践

### 踩坑 1：uniqueContextId 与 frameId 的关系

```python
# ❌ 直接用 frameId 作为 uniqueContextId
result = await cdp(ws, session_id, "Runtime.evaluate", {
    "expression": "document.title",
    "uniqueContextId": frame_id  # 可能不匹配
})

# ✅ 需要通过 frameId 获取 ExecutionContext
# 实际上 uniqueContextId = frameId 在大多数情况下有效
# 但更可靠的方式是先用 Runtime.evaluate 获取 contextId
```

### 踩坑 2：Frame 导航后旧的引用失效

```python
# iframe 重新导航后，之前的 frameId 可能仍然有效
# 但执行上下文可能已变化

# ✅ 导航后重新获取 Frame 树
await cdp(ws, session_id, "Page.navigate", {"url": url})
await asyncio.sleep(2)
tree = await get_frame_tree(ws, session_id)  # 重新获取
```

### 踩坑 3：iframe 未加载完成时操作

```python
# ❌ iframe 还未加载就执行代码
frame_id = "..."  # 刚获取的 frameId
result = await cdp(ws, session_id, "Runtime.evaluate", {
    "expression": "document.body.textContent",
    "uniqueContextId": frame_id  # 可能失败
})

# ✅ 等 frameStoppedLoading 事件后再操作
# 或等一段时间让 iframe 完成加载
```

### 踩坑 4：同文档导航不产生新 Frame

```python
# SPA 中的路由切换不会触发 frameNavigated
# 而是触发 navigatedWithinDocument
# Frame 树结构不变，但页面内容变了
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| Frame 树 | 每次导航后重新获取 |
| 执行上下文 | frameId 大多可直接当 uniqueContextId 用 |
| 事件驱动 | 用 frameNavigated/frameStoppedLoading 确定加载完成 |
| 跨域 Frame | CDP 不受同源限制 |
| iframe 等待 | 结合 Frame 事件和轮询 |
| 嵌套 Frame | Frame 树支持多层嵌套 |

---

## 完整参考：CDP Frame 管理类

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
        """将 Frame 树展平为列表"""
        if tree is None:
            tree = self.get_tree()
        frames = []
        def walk(node, parent=None):
            f = node.get("frame", {})
            info = {"id": f.get("id"), "url": f.get("url"),
                    "name": f.get("name"), "parent_id": parent}
            frames.append(info)
            for child in node.get("childFrames", []):
                walk(child, info["id"])
        walk(tree)
        return frames
    
    async def eval_in_frame(self, frame_id, expression):
        return await self._cmd("Runtime.evaluate", {
            "expression": expression, "uniqueContextId": frame_id
        })
    
    async def eval_all(self, expression):
        results = {}
        frames = self.flatten()
        for f in frames:
            try:
                r = await self.eval_in_frame(f["id"], expression)
                results[f["id"]] = r
            except Exception as e:
                results[f["id"]] = {"error": str(e)}
        return results
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    fm = CDPFrameManager(ws, session_id)
    
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(3)
    
    frames = fm.flatten()
    print(f"共 {len(frames)} 个 Frame")
    
    results = await fm.eval_all("document.title")
```

---

> **总结**：CDP 的 Frame 管理 API 提供了完整的框架操作能力——获取 Frame 树、在任意 iframe（包括跨域）中执行 JavaScript、监听 Frame 生命周期。这让复杂的多框架页面自动化变得简单直接。

---

*上一篇回顾：CDP 对话框处理指南：用 Python 自动处理 alert/confirm/prompt。*

*下一篇预告：CDP 安全与证书处理指南：用 Python 管理浏览器安全策略。*