---
title: CDP DOM 操作完全指南：用 Python 实时监听与操纵页面元素
date: 2026-06-05 14:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - DOM
  - 浏览器自动化
  - MutationObserver
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）操作和监听 DOM 变化。涵盖获取文档完整 DOM 快照、用 CSS 选择器精准定位元素、修改元素属性和文本、以及实时监听 DOM 增删改——这一切都不需要加载 jQuery 或任何第三方库。
---

> **一句话总结**：CDP 提供了比 JavaScript `document.querySelector` 更强大的 DOM 操作能力——你可以获取完整的 DOM 快照（包括所有 iframe 内的节点）、用原生 CSS 选择器定位元素、修改任意节点属性，甚至实时监听整个页面的 DOM 变化。

---

## 目录

1. [为什么用 CDP 操作 DOM](#为什么用-cdp-操作-dom)
2. [前置准备：连接 Chrome](#前置准备连接-chrome)
3. [获取 DOM 快照](#获取-dom-快照)
4. [用 CSS 选择器定位元素](#用-css-选择器定位元素)
5. [修改元素内容](#修改元素内容)
6. [实时监听 DOM 变化](#实时监听-dom-变化)
7. [实战：自动等待并提取动态内容](#实战自动等待并提取动态内容)
8. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 操作 DOM

传统 Selenium/Playwright 操作 DOM 的方式是"模拟用户操作"，而 CDP 是直接与浏览器引擎对话：

| 功能 | JavaScript DOM API | CDP DOM API |
|------|-------------------|-------------|
| 获取完整 DOM | ❌ 需要递归遍历 | ✅ 一步获取完整快照 |
| 跨 iframe 元素 | ⚠️ 需先获取 iframe 引用 | ✅ 自动包含所有子 frame |
| 监听新节点出现 | ✅ MutationObserver | ✅ DOM.childNodeInserted 事件 |
| 修改伪类状态 | ❌ 无法直接操作 | ✅ 支持 `:hover` `:active` 强制 |
| 获取布局信息 | ⚠️ getBoundingClientRect | ✅ 精确的盒模型 + 滚动信息 |
| 脱离页面脚本执行 | ❌ 依赖页面上下文 | ✅ 独立于 JS 引擎 |

简单说：**CDP 的 DOM API 是"上帝视角"**，可以看到页面中每一个节点，包括 Shadow DOM 内的元素。

---

## 前置准备：连接 Chrome

```python
import asyncio
import websockets
import json

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."

async def send_cdp(ws, cmd_id, method, params=None):
    """发送 CDP 命令并等待返回"""
    if params is None:
        params = {}
    await ws.send(json.dumps({"id": cmd_id, "method": method, "params": params}))
    async for msg in ws:
        resp = json.loads(msg)
        if resp.get("id") == cmd_id:
            return resp.get("result", {})

async def connect_page(ws):
    """获取并附加到第一个页面"""
    targets = await send_cdp(ws, 1, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await send_cdp(ws, 2, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]

async def main():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        # ... 后续操作

asyncio.run(main())
```

---

## 获取 DOM 快照

### 方法一：用 `DOMSnapshot.getSnapshot` 获取结构化快照

这是最强大的方法——它一次性返回所有节点的布局信息、样式和文本：

```python
async def get_dom_snapshot(ws, session_id):
    """获取完整的 DOM 快照"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 10,
        "method": "DOMSnapshot.getSnapshot",
        "params": {
            "computedStyleWhitelist": [
                "color", "font-size", "display",
                "width", "height", "background-color"
            ],
            "includeEventListeners": True,
            "includePaintOrder": False,
            "includeUserAgentShadowTree": True
        }
    }))
    return await wait_response(ws, 10)

async def wait_response(ws, cmd_id):
    async for msg in ws:
        resp = json.loads(msg)
        if resp.get("id") == cmd_id:
            return resp.get("result", {})
```

返回的快照结构：

```json
{
  "domNodes": [
    {
      "nodeType": 1,
      "nodeName": "DIV",
      "nodeValue": "",
      "textValue": "Hello World",
      "backendNodeId": 42,
      "attributes": ["class", "container", "id", "main"],
      "inputValue": "",
      "inputChecked": false,
      "optionSelected": false,
      "childNodeIndexes": [1, 2],
      "pseudoType": ""
    }
  ],
  "layoutTreeNodes": [
    {
      "domNodeIndex": 0,
      "boundingBox": {
        "x": 100, "y": 200,
        "width": 800, "height": 600
      },
      "scrollOffsetX": 0,
      "scrollOffsetY": 0
    }
  ],
  "computedStyles": [
    {
      "properties": [
        {"name": "color", "value": "rgb(51, 51, 51)"},
        {"name": "font-size", "value": "16px"}
      ]
    }
  ]
}
```

### 方法二：用 `DOM.getDocument` 获取节点树

轻量级方案，只返回 DOM 树结构，不含布局信息：

```python
async def get_dom_tree(ws, session_id, depth=-1):
    """获取 DOM 树（-1 表示全部展开）"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 11,
        "method": "DOM.getDocument",
        "params": {"depth": depth, "pierce": True}
    }))
    resp = await wait_response(ws, 11)
    return resp.get("root", {})
```

`pierce: True` 是关键——它会穿透 Shadow DOM 和 iframe，获取所有子树。

### 方法三：获取特定节点的 outerHTML

```python
async def get_outer_html(ws, session_id, node_id):
    """获取指定节点的 outerHTML"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 12,
        "method": "DOM.getOuterHTML",
        "params": {"nodeId": node_id}
    }))
    resp = await wait_response(ws, 12)
    return resp.get("outerHTML", "")
```

---

## 用 CSS 选择器定位元素

### 通过 document.querySelector（Runtime 方式）

通过执行 JavaScript 获取元素，再转为 CDP nodeId：

```python
async def query_selector(ws, session_id, css_selector):
    """通过 CSS 选择器查找元素"""
    # 1. 先在页面中执行 querySelector
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 20,
        "method": "Runtime.evaluate",
        "params": {
            "expression": f"document.querySelector('{css_selector}')",
            "returnByValue": False
        }
    }))
    resp = await wait_response(ws, 20)
    remote_obj = resp.get("result", {})
    object_id = remote_obj.get("objectId")
    
    if not object_id:
        return None
    
    # 2. 通过 objectId 请求 DOM 节点信息
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 21,
        "method": "DOM.requestNode",
        "params": {"objectId": object_id}
    }))
    resp = await wait_response(ws, 21)
    return resp.get("nodeId")


async def query_selector_all(ws, session_id, css_selector):
    """通过 CSS 选择器查找所有匹配元素"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 22,
        "method": "Runtime.evaluate",
        "params": {
            "expression": f"document.querySelectorAll('{css_selector}')",
            "returnByValue": False
        }
    }))
    resp = await wait_response(ws, 22)
    remote_obj = resp.get("result", {})
    object_id = remote_obj.get("objectId")
    
    if not object_id:
        return []
    
    # 获取所有匹配的节点 ID
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 23,
        "method": "DOM.requestNode",
        "params": {"objectId": object_id}
    }))
    resp = await wait_response(ws, 23)
    
    # 实际使用中需要遍历 NodeList
    # 这里简化处理，展示思路
    return [resp.get("nodeId")]


# 使用示例
async def find_element_text(ws, session_id, css_selector):
    """查找元素并获取其文本内容"""
    node_id = await query_selector(ws, session_id, css_selector)
    if node_id is None:
        return None
    
    # 获取 outerHTML
    outer_html = await get_outer_html(ws, session_id, node_id)
    return outer_html
```

### 通过 DOM.querySelector（纯 CDP 方式）

CDP 也提供了直接的 DOM 查询命令，更高效：

```python
async def cdp_query_selector(ws, session_id, node_id, css_selector):
    """使用 CDP 原生命令查找元素"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 24,
        "method": "DOM.querySelector",
        "params": {
            "nodeId": node_id,
            "selector": css_selector
        }
    }))
    resp = await wait_response(ws, 24)
    return resp.get("nodeId")


async def cdp_query_selector_all(ws, session_id, node_id, css_selector):
    """使用 CDP 原生命令查找所有匹配元素"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 25,
        "method": "DOM.querySelectorAll",
        "params": {
            "nodeId": node_id,
            "selector": css_selector
        }
    }))
    resp = await wait_response(ws, 25)
    return resp.get("nodeIds", [])
```

**`Runtime.evaluate` vs `DOM.querySelector` 的取舍**：
- `DOM.querySelector` 更高效，少一次网络往返
- `Runtime.evaluate` 更灵活，可以执行任意 JS 表达式
- 大部分场景优先用 `DOM.querySelector`

---

## 修改元素内容

### 修改属性

```python
async def set_element_attribute(ws, session_id, node_id, name, value):
    """设置元素属性"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 30,
        "method": "DOM.setAttributeValue",
        "params": {
            "nodeId": node_id,
            "name": name,
            "value": value
        }
    }))
    return await wait_response(ws, 30)


async def remove_element_attribute(ws, session_id, node_id, name):
    """删除元素属性"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 31,
        "method": "DOM.removeAttribute",
        "params": {
            "nodeId": node_id,
            "name": name
        }
    }))
    return await wait_response(ws, 31)
```

### 修改文本内容

```python
async def set_element_text(ws, session_id, node_id, text):
    """设置元素的文本内容"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 32,
        "method": "DOM.setNodeValue",
        "params": {
            "nodeId": node_id,
            "value": text
        }
    }))
    return await wait_response(ws, 32)


async def set_inner_html(ws, session_id, node_id, html):
    """设置元素的 innerHTML"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 33,
        "method": "DOM.setOuterHTML",
        "params": {
            "nodeId": node_id,
            "outerHTML": html
        }
    }))
    return await wait_response(ws, 33)
```

### 强制伪类状态

这是 CDP 独有的能力——强制元素进入 `:hover`、`:active`、`:focus` 状态：

```python
async def force_pseudo_state(ws, session_id, node_id, pseudo_classes):
    """强制元素的伪类状态（不需要鼠标真实悬停）"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 34,
        "method": "DOM.forcePseudoState",
        "params": {
            "nodeId": node_id,
            "forcedPseudoClasses": pseudo_classes
        }
    }))
    return await wait_response(ws, 34)

# 使用示例
# 强制悬停状态（触发 CSS :hover 样式）
await force_pseudo_state(ws, session_id, node_id, ["hover"])

# 同时强制多种伪类
await force_pseudo_state(ws, session_id, node_id, ["hover", "active", "focus"])

# 清除强制状态
await force_pseudo_state(ws, session_id, node_id, [])
```

---

## 实时监听 DOM 变化

CDP 通过 `DOM.childNodeInserted`、`DOM.childNodeRemoved`、`DOM.attributeModified` 等事件实时通知 DOM 变化。

### 启用 DOM 事件

```python
async def enable_dom_events(ws, session_id):
    """启用 DOM 事件推送"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 40,
        "method": "DOM.enable",
        "params": {}
    }))
    return await wait_response(ws, 40)
```

### 监听子节点插入

```python
async def watch_dom_changes(ws, session_id, timeout=30):
    """监听 DOM 变化，返回检测到的事件"""
    # 先启用 DOM 事件
    await enable_dom_events(ws, session_id)
    
    events = []
    start = asyncio.get_event_loop().time()
    
    while (asyncio.get_event_loop().time() - start) < timeout:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            method = data.get("method", "")
            
            if method in (
                "DOM.childNodeInserted",
                "DOM.childNodeRemoved",
                "DOM.attributeModified",
                "DOM.attributeRemoved",
                "DOM.characterDataModified"
            ):
                events.append({
                    "method": method,
                    "params": data.get("params", {})
                })
                print(f"[DOM 变化] {method}: {data.get('params', {})}")
                
                # 如果收集到足够的事件就提前返回
                if len(events) >= 10:
                    break
                    
        except asyncio.TimeoutError:
            continue
        except (websockets.exceptions.ConnectionClosed, GeneratorExit):
            break
    
    return events
```

### 监听特定选择器的节点出现

更实用的场景——等待某个元素出现在 DOM 中：

```python
async def wait_for_element(ws, session_id, css_selector, timeout=30):
    """等待指定 CSS 选择器的元素出现在 DOM 中"""
    # 先检查是否已存在
    node_id = await cdp_query_selector(ws, session_id, 1, css_selector)
    if node_id and node_id != 0:
        return node_id
    
    # 启用 DOM 事件
    await enable_dom_events(ws, session_id)
    
    start = asyncio.get_event_loop().time()
    while (asyncio.get_event_loop().time() - start) < timeout:
        try:
            msg = await asyncio.wait_for(ws.__anext__(), timeout=1)
            data = json.loads(msg)
            
            if data.get("method") == "DOM.childNodeInserted":
                # 新节点插入了，检查是否匹配
                node_id = await cdp_query_selector(
                    ws, session_id, 1, css_selector
                )
                if node_id and node_id != 0:
                    print(f"目标元素已出现: {css_selector}")
                    return node_id
                    
        except asyncio.TimeoutError:
            continue
    
    return None
```

---

## 实战：自动等待并提取动态内容

综合运用以上技术，实现一个"等待页面动态加载内容并提取"的功能：

```python
async def wait_and_extract_dynamic(ws, session_id, url, container_selector,
                                    item_selector, wait_timeout=15):
    """导航到页面，等待动态内容加载，然后提取数据"""
    
    # 1. 先监听 DOM 事件
    await enable_dom_events(ws, session_id)
    
    # 2. 导航到页面
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 50,
        "method": "Page.navigate",
        "params": {"url": url}
    }))
    await wait_response(ws, 50)
    
    # 3. 等待容器出现或超时
    container_id = await wait_for_element(
        ws, session_id, container_selector, wait_timeout
    )
    
    if not container_id:
        print("未找到容器元素")
        return []
    
    print(f"容器已加载，开始提取数据...")
    
    # 4. 提取容器内所有匹配子元素
    item_ids = await cdp_query_selector_all(
        ws, session_id, container_id, item_selector
    )
    
    # 5. 获取每个元素的文本和属性
    results = []
    for item_id in item_ids:
        # 获取 outerHTML 来提取信息
        html = await get_outer_html(ws, session_id, item_id)
        results.append(html)
    
    print(f"提取到 {len(results)} 个元素")
    return results


# 使用示例：抓取动态加载的商品列表
async def scrape_dynamic_products():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        
        products = await wait_and_extract_dynamic(
            ws, session_id,
            url="https://example.com/products",
            container_selector="#product-list",
            item_selector=".product-item"
        )
        
        for i, product_html in enumerate(products[:5]):
            print(f"商品 {i+1}: {product_html[:100]}...")
```

---

## 常见踩坑与最佳实践

### 踩坑 1：nodeId 是会话级别的

`nodeId` 只在当前 CDP 会话（session）内有效，断开重连后旧 nodeId 全部失效：

```python
# ❌ 重连后使用旧 nodeId
session_a = await connect_page(ws_a)
node_id = await cdp_query_selector(ws, session_a, 1, "#main")
# ... 断线重连 ...
session_b = await connect_page(ws_b)
await get_outer_html(ws, session_b, node_id)  # ❌ 无效

# ✅ 重连后重新获取 nodeId
session_b = await connect_page(ws_b)
node_id = await cdp_query_selector(ws, session_b, 1, "#main")  # 重新查询
await get_outer_html(ws, session_b, node_id)  # ✅ 有效
```

### 踩坑 2：Shadow DOM 需要特殊处理

默认情况下 `DOM.querySelector` 不会穿透 Shadow DOM：

```python
# ❌ 无法查询到 Shadow DOM 内的元素
await cdp_query_selector(ws, session_id, node_id, ".shadow-button")

# ✅ 方法一：用 pierce 参数获取完整快照
snapshot = await get_dom_snapshot(ws, session_id)  # 设 includeUserAgentShadowTree=True

# ✅ 方法二：通过 JS 穿透
await ws.send(json.dumps({
    "sessionId": session_id,
    "id": 60,
    "method": "Runtime.evaluate",
    "params": {
        "expression": """document.querySelector('my-component').shadowRoot.querySelector('.shadow-button')"""
    }
}))
```

### 踩坑 3：DOM 事件需先 `DOM.enable`

```python
# ❌ 没启用就直接监听
msg = await receive_message(ws)  # 收不到 DOM 事件

# ✅ 先启用
await enable_dom_events(ws, session_id)
# 然后才能收到 DOM.childNodeInserted 等事件
```

### 踩坑 4：频繁 DOM 快照的性能开销

大型页面的 DOM 快照会消耗较多资源，建议按需获取：

```python
# ❌ 轮询获取完整快照（性能差）
for _ in range(100):
    snapshot = await get_dom_snapshot(ws, session_id)
    await asyncio.sleep(0.5)

# ✅ 用 DOM 事件监听变化（高效）
events = await watch_dom_changes(ws, session_id, timeout=30)
```

### 踩坑 5：`DOM.getDocument` 的 depth 参数

`depth` 默认为 1（只返回直接子节点）。如果要获取完整树结构，需要设为 -1 或较大的值：

```python
# ❌ depth 太小，获取不全
root = await get_dom_tree(ws, session_id, depth=1)  # 只有顶层

# ✅ depth=-1 获取完整树
root = await get_dom_tree(ws, session_id, depth=-1)  # 完整展开
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 优先用 CDP 原生命令 | `DOM.querySelector` 比 `Runtime.evaluate` 更高效 |
| Shadow DOM 穿透 | 设 `pierce: True` 或 `includeUserAgentShadowTree: True` |
| 监控变化用事件 | 不要轮询 DOM 快照，用 `DOM.childNodeInserted` 等事件 |
| nodeId 有效期 | nodeId 只在当前会话有效，重连后需重新获取 |
| 深度参数 | `DOM.getDocument` 的 depth 设 -1 获取完整树 |
| 强制伪类 | 调试 UI 状态时用 `DOM.forcePseudoState` 模拟悬停/焦点 |

---

## 完整参考：CDP DOM 操作类

```python
import asyncio
import json
import websockets


class CDPDOMClient:
    """CDP DOM 操作客户端"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 1000
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        msg = {
            "sessionId": self.session_id,
            "id": self._cmd_id,
            "method": method,
            "params": params or {}
        }
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    # DOM 快照
    async def get_snapshot(self):
        return await self._cmd("DOMSnapshot.getSnapshot", {
            "computedStyleWhitelist": [
                "color", "font-size", "display", "width", "height"
            ],
            "includeUserAgentShadowTree": True
        })
    
    # 查询
    async def query_selector(self, selector, node_id=1):
        return (await self._cmd("DOM.querySelector", {
            "nodeId": node_id, "selector": selector
        })).get("nodeId")
    
    async def query_selector_all(self, selector, node_id=1):
        return (await self._cmd("DOM.querySelectorAll", {
            "nodeId": node_id, "selector": selector
        })).get("nodeIds", [])
    
    # 修改
    async def set_attr(self, node_id, name, value):
        await self._cmd("DOM.setAttributeValue", {
            "nodeId": node_id, "name": name, "value": value
        })
    
    async def set_html(self, node_id, html):
        await self._cmd("DOM.setOuterHTML", {
            "nodeId": node_id, "outerHTML": html
        })
    
    async def force_pseudo(self, node_id, pseudo_classes):
        await self._cmd("DOM.forcePseudoState", {
            "nodeId": node_id,
            "forcedPseudoClasses": pseudo_classes
        })
    
    # 监听
    async def enable_events(self):
        await self._cmd("DOM.enable")
    
    async def wait_for_selector(self, selector, timeout=30):
        """等待元素出现"""
        node_id = await self.query_selector(selector)
        if node_id:
            return node_id
        await self.enable_events()
        start = asyncio.get_event_loop().time()
        while (asyncio.get_event_loop().time() - start) < timeout:
            try:
                msg = await asyncio.wait_for(
                    self.ws.__anext__(), timeout=1
                )
                data = json.loads(msg)
                if data.get("method") == "DOM.childNodeInserted":
                    node_id = await self.query_selector(selector)
                    if node_id:
                        return node_id
            except asyncio.TimeoutError:
                continue
        return None
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    dom = CDPDOMClient(ws, session_id)
    
    # 等待特定元素出现
    btn = await dom.wait_for_selector(".dynamic-button")
    if btn:
        # 强制悬停状态
        await dom.force_pseudo(btn, ["hover"])
        await asyncio.sleep(1)
        # 获取快照
        snapshot = await dom.get_snapshot()
        print(f"快照包含 {len(snapshot.get('domNodes', []))} 个节点")
```

---

> **总结**：CDP 的 DOM API 提供了浏览器引擎级别的操作能力——完整的 DOM 快照、高效的 CSS 选择器、灵活的元素修改、以及实时变化监听。结合前几篇文章的网络拦截和页面控制，你可以构建出比 Selenium/Playwright 更精细的自动化工具。

---

*上一篇回顾：CDP 操作 Cookie 完全指南——用 Python 实现增删改查与自动化登录。*

*下一篇预告：CDP 网络条件模拟——如何模拟 2G/3G/离线网络环境。*
