---
title: CDP 输入自动化指南：用 Python 模拟鼠标键盘
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 浏览器自动化
  - 输入模拟
  - 鼠标事件
  - 键盘事件
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）的 Input 域模拟用户输入操作。涵盖鼠标点击与移动、键盘按键输入、文本插入、拖拽操作、触摸事件模拟、坐标系统理解，以及完整的 InputSimulator 封装类。
---

> **一句话总结**：CDP 的 Input 域让你在浏览器层面直接模拟鼠标点击、键盘输入、文本插入和触摸操作，比 Selenium 更底层、更精确，甚至能模拟出真人操作的时间痕迹。

---

## 目录

1. [为什么用 CDP 模拟输入](#为什么用-cdp-模拟输入)
2. [前置准备：连接 Chrome](#前置准备连接-chrome)
3. [理解 CDP 坐标系统](#理解-cdp-坐标系统)
4. [鼠标点击模拟](#鼠标点击模拟)
5. [鼠标移动与拖拽](#鼠标移动与拖拽)
6. [键盘输入模拟](#键盘输入模拟)
7. [文本插入](#文本插入)
8. [触摸事件模拟](#触摸事件模拟)
9. [完整参考：CDP InputSimulator 类](#完整参考cdp-inputsimulator-类)
10. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 模拟输入

相比 Selenium/Playwright 的 `click()` 和 `send_keys()`，CDP 的输入模拟有几个独特优势：

| 特性 | Selenium | CDP Input |
|------|----------|-----------|
| 鼠标按下/释放分离 | ❌ 只有 click() | ✅ 精确控制 mousePressed/mouseReleased |
| 多按键组合 | ⚠️ ActionChains 复杂 | ✅ 任意组合键 |
| 拖拽操作 | ⚠️ drag_and_drop 不稳定 | ✅ 像素级控制 |
| 触摸事件 | ❌ 需要 TouchAction | ✅ 原生触摸事件 |
| 插入文本 | ✅ send_keys | ✅ insertText（绕过事件监听） |
| 悬停状态 | ✅ move_to | ✅ mouseMoved 精确定位 |

关键区别：CDP 的输入模拟直接注入到浏览器的输入事件流中，不经过任何 JS 事件包装层。这意味着：
- 模拟的点击不会被 `event.isTrusted` 检测发现（对反爬有重大意义）
- 支持更精确的时间控制
- 可以模拟键盘上没有的"虚拟键"

---

## 前置准备：连接 Chrome

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

## 理解 CDP 坐标系统

CDP 使用**视口坐标**（viewport coordinates）——即相对于浏览器内容区域左上角的像素坐标，不包含浏览器工具栏和标签栏。

```python
# 获取页面布局信息（帮助定位）
async def get_element_bounds(ws, session_id, css_selector):
    """获取元素在视口中的位置和尺寸"""
    js = f"""
    (() => {{
        const el = document.querySelector('{css_selector}');
        if (!el) return null;
        const rect = el.getBoundingClientRect();
        return {{
            x: rect.x, y: rect.y,
            width: rect.width, height: rect.height,
            centerX: rect.x + rect.width / 2,
            centerY: rect.y + rect.height / 2
        }};
    }})()
    """
    result = await cdp(ws, "Runtime.evaluate",
        {"expression": js}, session_id)
    return result.get("result", {}).get("value")
```

### 坐标与按钮值对照

| 概念 | CDP 参数值 |
|------|-----------|
| 视口左上角 | (0, 0) |
| 滚动的页面 | 视口坐标不变，页面相对移动 |
| 鼠标左键 | `button: 0` |
| 鼠标中键 | `button: 1` |
| 鼠标右键 | `button: 2` |
| 点击次数 | `clickCount: 1`（单击），`2`（双击） |
| 修饰键 | `modifiers: 0`（无），`1`（Alt），`2`（Ctrl），`4`（Meta），`8`（Shift） |

### 修饰键位掩码计算

```python
def compute_modifiers(alt=False, ctrl=False, meta=False, shift=False):
    """计算修饰键掩码"""
    mask = 0
    if alt:   mask |= 1
    if ctrl:  mask |= 2
    if meta:  mask |= 4
    if shift: mask |= 8
    return mask
```

---

## 鼠标点击模拟

### Input.dispatchMouseEvent

基础的鼠标点击需要三个步骤：按下（mousePressed）、释放（mouseReleased），中间可选移动。

```python
async def mouse_click(ws, session_id, x, y, button="left", click_count=1):
    """在指定坐标模拟鼠标点击"""
    button_map = {"left": 0, "middle": 1, "right": 2}
    btn = button_map.get(button, 0)
    
    # 1. 先移动到目标位置
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x, "y": y,
        "button": btn,
        "buttons": 0,
        "clickCount": click_count
    }, session_id)
    
    # 2. 鼠标按下
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x, "y": y,
        "button": btn,
        "buttons": 1,
        "clickCount": click_count
    }, session_id)
    
    # 3. 短暂延迟后释放
    await asyncio.sleep(0.05)
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x, "y": y,
        "button": btn,
        "buttons": 0,
        "clickCount": click_count
    }, session_id)

# 使用
async def demo_click():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        # 先导航到百度
        await cdp(ws, "Page.navigate",
                  {"url": "https://www.baidu.com"}, session_id)
        await asyncio.sleep(2)
        
        # 点击搜索框位置（假设在页面中心附近）
        await mouse_click(ws, session_id, 500, 300)
```

### 左键、右键、双击

```python
async def right_click(ws, session_id, x, y):
    """右键点击（弹出上下文菜单）"""
    await mouse_click(ws, session_id, x, y, button="right")

async def double_click(ws, session_id, x, y):
    """双击"""
    # 第一次点击
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x, "y": y,
        "button": 0,
        "buttons": 1,
        "clickCount": 1
    }, session_id)
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x, "y": y,
        "button": 0,
        "buttons": 0,
        "clickCount": 1
    }, session_id)
    
    await asyncio.sleep(0.1)
    
    # 第二次点击（clickCount=2）
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x, "y": y,
        "button": 0,
        "buttons": 1,
        "clickCount": 2
    }, session_id)
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x, "y": y,
        "button": 0,
        "buttons": 0,
        "clickCount": 2
    }, session_id)
```

### 带修饰键的点击

```python
async def ctrl_click(ws, session_id, x, y):
    """按住 Ctrl 再点击（打开新标签页等）"""
    modifiers = compute_modifiers(ctrl=True)
    
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x, "y": y,
        "button": 0,
        "buttons": 1,
        "clickCount": 1,
        "modifiers": modifiers
    }, session_id)
    
    await asyncio.sleep(0.05)
    
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x, "y": y,
        "button": 0,
        "buttons": 0,
        "clickCount": 1,
        "modifiers": modifiers
    }, session_id)
```

---

## 鼠标移动与拖拽

### Input.dispatchMouseEvent (mouseMoved)

```python
async def mouse_move(ws, session_id, x, y, steps=10):
    """将鼠标平滑移动到目标位置（模拟真实轨迹）"""
    # 先获取当前位置（CDP 不直接提供当前位置，用 JS 获取）
    pos_result = await cdp(ws, "Runtime.evaluate", {
        "expression": "({x: 0, y: 0})"  # 简化：从 (0,0) 开始
    }, session_id)
    
    start_x, start_y = 0, 0
    
    for i in range(1, steps + 1):
        current_x = start_x + (x - start_x) * i // steps
        current_y = start_y + (y - start_y) * i // steps
        
        # 加入微小随机抖动，模拟真人鼠标
        jitter_x = current_x + (0 if i == steps else __import__('random').randint(-2, 2))
        jitter_y = current_y + (0 if i == steps else __import__('random').randint(-2, 2))
        
        await cdp(ws, "Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": jitter_x,
            "y": jitter_y,
            "button": 0,
            "buttons": 0
        }, session_id)
        
        await asyncio.sleep(0.01)  # 每步延迟 10ms
```

### 拖拽操作

拖拽 = mousePressed → 多次 mouseMoved → mouseReleased：

```python
async def drag_and_drop(ws, session_id, start_x, start_y, end_x, end_y, steps=20):
    """从起点拖拽到终点"""
    # 1. 移动到起点
    await mouse_move(ws, session_id, start_x, start_y)
    
    # 2. 在起点按下鼠标左键
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": start_x, "y": start_y,
        "button": 0,
        "buttons": 1,
        "clickCount": 1
    }, session_id)
    
    # 3. 逐步拖拽到终点（保持 buttons=1 表示按住）
    for i in range(1, steps + 1):
        current_x = start_x + (end_x - start_x) * i // steps
        current_y = start_y + (end_y - start_y) * i // steps
        
        await cdp(ws, "Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": current_x, "y": current_y,
            "button": 0,
            "buttons": 1,  # 保持按住
            "clickCount": 1
        }, session_id)
        await asyncio.sleep(0.015)
    
    # 4. 释放鼠标
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": end_x, "y": end_y,
        "button": 0,
        "buttons": 0,
        "clickCount": 1
    }, session_id)

# 演示：页面内元素拖拽
async def demo_drag():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        
        # 打开一个支持拖拽的页面（如 sortable 示例）
        await cdp(ws, "Page.navigate",
                  {"url": "https://sortablejs.github.io/Sortable/"}, session_id)
        await asyncio.sleep(3)
        
        # 获取第一个可拖拽元素的位置
        bounds = await get_element_bounds(ws, session_id, ".item:first-child")
        if bounds:
            start = (int(bounds["centerX"]), int(bounds["centerY"]))
            end = (start[0], start[1] + 200)  # 向下拖 200px
            await drag_and_drop(ws, session_id, start[0], start[1], end[0], end[1])
```

### 滚轮操作

```python
async def scroll_page(ws, session_id, delta_x=0, delta_y=300):
    """模拟鼠标滚轮滚动"""
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseWheel",
        "x": 400, "y": 400,
        "deltaX": delta_x,
        "deltaY": delta_y
    }, session_id)

# 平滑滚动到指定位置
async def smooth_scroll_to(ws, session_id, target_y, step=100):
    """平滑滚动到目标 Y 位置"""
    import random
    current = 0
    while current < target_y:
        step_size = min(step + random.randint(-20, 20), target_y - current)
        await scroll_page(ws, session_id, delta_y=step_size)
        current += step_size
        await asyncio.sleep(0.05)
```

---

## 键盘输入模拟

### Input.dispatchKeyEvent

键盘事件分为 keyDown 和 keyUp，文本输入用 keyDown(key) → char → keyUp(key) 模式：

```python
# 常用键的虚拟键码
KEY_MAP = {
    "Enter": "Enter",
    "Tab": "Tab",
    "Backspace": "Backspace",
    "Delete": "Delete",
    "Escape": "Escape",
    "ArrowUp": "ArrowUp",
    "ArrowDown": "ArrowDown",
    "ArrowLeft": "ArrowLeft",
    "ArrowRight": "ArrowRight",
    "Home": "Home",
    "End": "End",
    "PageUp": "PageUp",
    "PageDown": "PageDown",
    "Shift": "Shift",
    "Control": "Control",
    "Alt": "Alt",
    "Meta": "Meta",
    "Space": " ",
}

async def key_press(ws, session_id, key_text):
    """模拟单个按键"""
    # 键按下
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "keyDown",
        "key": key_text
    }, session_id)
    
    await asyncio.sleep(0.05)
    
    # 键释放
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": key_text
    }, session_id)


async def type_text(ws, session_id, text, delay=0.05):
    """模拟键盘逐字输入文本"""
    for char in text:
        # keyDown
        await cdp(ws, "Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": char,
            "text": char
        }, session_id)
        
        # char（可选，用于字符输入）
        await cdp(ws, "Input.dispatchKeyEvent", {
            "type": "char",
            "key": char,
            "text": char
        }, session_id)
        
        # keyUp
        await cdp(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": char,
            "text": char
        }, session_id)
        
        # 每字符之间的延迟——模拟真实打字速度
        await asyncio.sleep(delay)
```

### 组合键

```python
async def key_combination(ws, session_id, modifiers, main_key):
    """模拟组合键（如 Ctrl+A, Ctrl+C, Ctrl+V）"""
    # 按下修饰键
    for mod_key in modifiers:
        await key_press(ws, session_id, mod_key)  # 只按下不释放
        # 正确做法应该单独 dispatch keyDown
    
    # 按下主键
    await key_press(ws, session_id, main_key)
    
    # 释放修饰键（省略细化，完整示意见 InputSimulator 类）

async def select_all_and_copy(ws, session_id):
    """全选然后复制"""
    modifiers = compute_modifiers(ctrl=True)
    
    # Ctrl+A
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "rawKeyDown",
        "windowsVirtualKeyCode": 65,  # A
        "key": "a",
        "code": "KeyA",
        "modifiers": modifiers
    }, session_id)
    await asyncio.sleep(0.05)
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": "a",
        "modifiers": modifiers
    }, session_id)
    
    await asyncio.sleep(0.1)
    
    # Ctrl+C
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "rawKeyDown",
        "windowsVirtualKeyCode": 67,  # C
        "key": "c",
        "code": "KeyC",
        "modifiers": modifiers
    }, session_id)
    await asyncio.sleep(0.05)
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": "c",
        "modifiers": modifiers
    }, session_id)
```

---

## 文本插入

### Input.insertText

与逐字模拟键盘不同，`Input.insertText` 直接向焦点元素插入文本，不经过键盘事件流：

```python
async def insert_text(ws, session_id, text):
    """直接向焦点元素插入文本（绕过键盘事件）"""
    await cdp(ws, "Input.insertText", {
        "text": text
    }, session_id)

# 使用：先聚焦输入框，然后直接插入文本
async def fast_text_input(ws, session_id, css_selector, text):
    """快速在输入框中填入文本"""
    # 先聚焦元素
    js = f"document.querySelector('{css_selector}').focus();"
    await cdp(ws, "Runtime.evaluate",
        {"expression": js}, session_id)
    
    await asyncio.sleep(0.2)
    
    # 清空已有内容（全选后删除）
    # ... 此处可用组合键 Ctrl+A, Delete
    
    # 直接插入文本（比逐字键盘输入快得多）
    await insert_text(ws, session_id, text)
```

### insertText vs dispatchKeyEvent 对比

| 方式 | 触发键盘事件 | 速度 | 适用场景 |
|------|-------------|------|---------|
| dispatchKeyEvent | ✅ 触发全部事件 | 慢（逐字符） | 需要模拟真人打字 |
| insertText | ❌ 不触发键盘事件 | 极快 | 快速填充表单 |
| DOM 直接设置 | ❌ 不触发任何事件 | 最快 | 后台数据注入 |

---

## 触摸事件模拟

### Input.dispatchTouchEvent

移动端模拟或触摸屏场景需要触摸事件：

```python
async def touch_tap(ws, session_id, x, y):
    """模拟触摸点击"""
    # touchStart
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{
            "x": x, "y": y
        }],
        "modifiers": 0
    }, session_id)
    
    await asyncio.sleep(0.05)
    
    # touchEnd
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": [],
        "modifiers": 0
    }, session_id)

async def touch_scroll(ws, session_id, start_x, start_y, end_x, end_y, steps=10):
    """模拟触摸滚动（滑动操作）"""
    # touchStart
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{"x": start_x, "y": start_y}],
        "modifiers": 0
    }, session_id)
    
    # touchMove 多次
    for i in range(1, steps + 1):
        current_x = start_x + (end_x - start_x) * i // steps
        current_y = start_y + (end_y - start_y) * i // steps
        
        await cdp(ws, "Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{"x": current_x, "y": current_y}],
            "modifiers": 0
        }, session_id)
        await asyncio.sleep(0.01)
    
    # touchEnd
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": [],
        "modifiers": 0
    }, session_id)

async def touch_pinch(ws, session_id, center_x, center_y, start_radius, end_radius):
    """模拟双指捏合缩放"""
    # touchStart（两个触点）
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [
            {"x": center_x - start_radius, "y": center_y},
            {"x": center_x + start_radius, "y": center_y}
        ],
        "modifiers": 0
    }, session_id)
    
    # touchMove 逐步移动两个触点
    for i in range(1, 11):
        r = start_radius + (end_radius - start_radius) * i // 10
        await cdp(ws, "Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [
                {"x": center_x - r, "y": center_y},
                {"x": center_x + r, "y": center_y}
            ],
            "modifiers": 0
        }, session_id)
        await asyncio.sleep(0.01)
    
    # touchEnd
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": [],
        "modifiers": 0
    }, session_id)
```

---

## 完整参考：CDP InputSimulator 类

```python
import asyncio
import json
import random
import websockets


class CDPInputSimulator:
    """CDP 输入模拟器"""
    
    KEY_MAP = {
        "Enter": "Enter", "Tab": "Tab",
        "Backspace": "Backspace", "Delete": "Delete",
        "Escape": "Escape",
        "ArrowUp": "ArrowUp", "ArrowDown": "ArrowDown",
        "ArrowLeft": "ArrowLeft", "ArrowRight": "ArrowRight",
        "Home": "Home", "End": "End",
        "PageUp": "PageUp", "PageDown": "PageDown",
        "Shift": "Shift", "Control": "Control",
        "Alt": "Alt", "Meta": "Meta",
        "Space": " ",
    }
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
    async def _cdp(self, method, params=None):
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method,
               "params": params or {}}
        if self.session_id:
            msg["sessionId"] = self.session_id
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    def _modifiers(self, alt=False, ctrl=False, meta=False, shift=False):
        mask = 0
        if alt:   mask |= 1
        if ctrl:  mask |= 2
        if meta:  mask |= 4
        if shift: mask |= 8
        return mask
    
    # ===== 鼠标操作 =====
    
    async def click(self, x: int, y: int, button: str = "left",
                    click_count: int = 1, modifiers: int = 0):
        """在指定坐标点击"""
        btn = {"left": 0, "middle": 1, "right": 2}.get(button, 0)
        
        # 移动
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
            "button": btn, "buttons": 0, "clickCount": click_count,
            "modifiers": modifiers
        })
        
        # 按下
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": btn, "buttons": 1, "clickCount": click_count,
            "modifiers": modifiers
        })
        
        await asyncio.sleep(0.05)
        
        # 释放
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": btn, "buttons": 0, "clickCount": click_count,
            "modifiers": modifiers
        })
    
    async def double_click(self, x: int, y: int):
        """双击"""
        await self.click(x, y, click_count=1)
        await asyncio.sleep(0.1)
        await self.click(x, y, click_count=2)
    
    async def right_click(self, x: int, y: int):
        """右键点击"""
        await self.click(x, y, button="right")
    
    async def move_mouse(self, x: int, y: int, steps: int = 10):
        """平滑移动鼠标"""
        start_x, start_y = 0, 0
        for i in range(1, steps + 1):
            cx = start_x + (x - start_x) * i // steps
            cy = start_y + (y - start_y) * i // steps
            if i < steps:
                cx += random.randint(-2, 2)
                cy += random.randint(-2, 2)
            await self._cdp("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": cx, "y": cy,
                "button": 0, "buttons": 0, "clickCount": 1
            })
            await asyncio.sleep(0.01)
    
    async def drag(self, start_x: int, start_y: int,
                   end_x: int, end_y: int, steps: int = 20):
        """拖拽操作"""
        # Press
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": start_x, "y": start_y,
            "button": 0, "buttons": 1, "clickCount": 1
        })
        # Move while holding
        for i in range(1, steps + 1):
            cx = start_x + (end_x - start_x) * i // steps
            cy = start_y + (end_y - start_y) * i // steps
            await self._cdp("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": cx, "y": cy,
                "button": 0, "buttons": 1, "clickCount": 1
            })
            await asyncio.sleep(0.015)
        # Release
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": end_x, "y": end_y,
            "button": 0, "buttons": 0, "clickCount": 1
        })
    
    async def scroll(self, delta_x: int = 0, delta_y: int = 300,
                     x: int = 400, y: int = 400):
        """鼠标滚轮"""
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y,
            "deltaX": delta_x, "deltaY": delta_y
        })
    
    # ===== 键盘操作 =====
    
    async def press_key(self, key: str):
        """按下一个键并释放"""
        await self._cdp("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": key
        })
        await asyncio.sleep(0.05)
        await self._cdp("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": key
        })
    
    async def type_text(self, text: str, delay: float = 0.05):
        """逐字输入文本"""
        for char in text:
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": char, "text": char
            })
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "char", "key": char, "text": char
            })
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": char, "text": char
            })
            await asyncio.sleep(delay)
    
    async def insert_text(self, text: str):
        """直接插入文本（绕过键盘事件）"""
        await self._cdp("Input.insertText", {"text": text})
    
    async def hotkey(self, *keys):
        """组合键：hotkey('Control', 'a') → Ctrl+A"""
        modifiers = 0
        mod_map = {"Control": 2, "Alt": 1, "Shift": 8, "Meta": 4}
        
        # 按下所有修饰键
        for k in keys[:-1]:
            if k in mod_map:
                modifiers |= mod_map[k]
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": k
            })
        
        # 按下主键
        main_key = keys[-1]
        await self._cdp("Input.dispatchKeyEvent", {
            "type": "rawKeyDown",
            "key": main_key,
            "modifiers": modifiers
        })
        await asyncio.sleep(0.05)
        await self._cdp("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": main_key,
            "modifiers": modifiers
        })
        
        # 释放修饰键
        for k in reversed(keys[:-1]):
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": k
            })
    
    # ===== 触摸操作 =====
    
    async def touch_tap(self, x: int, y: int):
        """触摸点击"""
        await self._cdp("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": x, "y": y}],
            "modifiers": 0
        })
        await asyncio.sleep(0.05)
        await self._cdp("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [],
            "modifiers": 0
        })
    
    async def touch_swipe(self, start_x: int, start_y: int,
                          end_x: int, end_y: int, steps: int = 15):
        """触摸滑动"""
        await self._cdp("Input.dispatchTouchEvent", {
            "type": "touchStart",
            "touchPoints": [{"x": start_x, "y": start_y}],
            "modifiers": 0
        })
        for i in range(1, steps + 1):
            cx = start_x + (end_x - start_x) * i // steps
            cy = start_y + (end_y - start_y) * i // steps
            await self._cdp("Input.dispatchTouchEvent", {
                "type": "touchMove",
                "touchPoints": [{"x": cx, "y": cy}],
                "modifiers": 0
            })
            await asyncio.sleep(0.01)
        await self._cdp("Input.dispatchTouchEvent", {
            "type": "touchEnd",
            "touchPoints": [],
            "modifiers": 0
        })
    
    # ===== 辅助方法 =====
    
    async def focus_element(self, css_selector: str):
        """聚焦元素"""
        await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}').focus()"
        })
    
    async def click_element(self, css_selector: str):
        """通过 JS 直接点击元素（不模拟鼠标）"""
        await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}').click()"
        })


    async def human_like_typing(self, text: str, target_wpm: int = 120):
        """模拟真人打字（带随机延迟变化）"""
        # 120 WPM ≈ 每字符 80-120ms
        base_delay = 60.0 / (target_wpm * 5)
        for char in text:
            delay = base_delay * random.uniform(0.5, 1.8)
            await self.type_text(char, 0)
            await asyncio.sleep(delay)
```

**使用示例：**

```python
async def demo_input_simulator():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        sim = CDPInputSimulator(ws, session_id)
        
        # 导航到百度
        await sim._cdp("Page.navigate", {"url": "https://www.baidu.com"})
        await asyncio.sleep(2)
        
        # 聚焦搜索框
        await sim.focus_element("#kw")
        await asyncio.sleep(0.5)
        
        # 输入搜索关键词（模拟真人打字速度）
        await sim.human_like_typing("Python CDP 教程", target_wpm=100)
        await asyncio.sleep(1)
        
        # 点击"百度一下"按钮
        await sim.click_element("#su")
```

---

## 常见踩坑与最佳实践

### 踩坑 1：坐标是视口坐标，不是页面坐标

```python
# ❌ 页面滚动了，元素坐标变了
scroll_y = 500
await mouse_click(ws, session_id, 100, scroll_y)  # 点到了错误位置

# ✅ 使用 getBoundingClientRect 获取当前视口坐标
bounds = await get_element_bounds(ws, session_id, "#my-button")
await mouse_click(ws, session_id, bounds["centerX"], bounds["centerY"])
```

### 踩坑 2：input[type="file"] 不能被 click

```python
# ❌ 文件输入框不能用 CDP click 模拟点击
await mouse_click(ws, session_id, x, y)  # 不会弹出文件选择器

# ✅ 应该用 DOM.setFileInputFiles 或 Page.setInterceptFileChooserDialog
```

### 踩坑 3：按键事件缺少必要参数

```python
# ❌ 缺少 code 字段可能导致某些应用不识别
await cdp(ws, "Input.dispatchKeyEvent", {
    "type": "keyDown", "key": "a"
}, session_id)

# ✅ 提供完整参数
await cdp(ws, "Input.dispatchKeyEvent", {
    "type": "keyDown",
    "key": "a",
    "code": "KeyA",
    "text": "a",
    "windowsVirtualKeyCode": 65
}, session_id)
```

### 踩坑 4：insertText 需要先聚焦

```python
# ❌ 没有焦点元素，文本不知道插到哪
await insert_text(ws, session_id, "hello")

# ✅ 先聚焦目标元素
await sim.focus_element("#input-box")
await asyncio.sleep(0.2)
await insert_text(ws, session_id, "hello")
```

### 踩坑 5：Chrome 输入法拦截问题

某些情况下 Chrome 的输入法会拦截 insertText，需要使用更底层的 IME 命令：

```python
async def ime_set_composition(ws, session_id, text, selection_start, selection_end):
    """设置输入法组合文本"""
    await cdp(ws, "Input.imeSetComposition", {
        "text": text,
        "selectionStart": selection_start,
        "selectionEnd": selection_end
    }, session_id)
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 坐标获取 | 用 `getBoundingClientRect()` 动态获取 |
| 模拟真实性 | 加入随机延迟和鼠标抖动 |
| 事件顺序 | 始终为 mousePressed → ... → mouseReleased |
| 按键完整 | 提供 key + code + windowsVirtualKeyCode |
| 触摸模拟 | 移动端页面必须用触摸事件 |
| 聚焦前提 | insertText/键盘输入前确保元素已聚焦 |

---

> **总结**：CDP 的 Input 域提供了从鼠标点击到键盘输入、从拖拽到触摸事件的完整输入模拟能力。通过 InputSimulator 封装类，你可以模拟出几乎任何用户操作，甚至能控制到像素级别的时间延迟，实现高仿真的人机交互自动化。

*上一篇回顾：CDP 多标签页管理：用 Python 控制多个页面。*

*下一篇预告：CDP 文件上传与下载：用 Python 处理文件操作。*