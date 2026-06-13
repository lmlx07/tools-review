---
lang: en
title: "CDP Input Automation Guide: Simulating Mouse & Keyboard with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Automation
  - Input Simulation
  - Mouse Events
  - Keyboard Events
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to simulating user input using the Chrome DevTools Protocol (CDP) Input domain. Covers mouse clicks and movement, keyboard input, text insertion, drag-and-drop operations, touch events, coordinate system fundamentals, and a complete InputSimulator wrapper class.
---

> **Summary in one sentence**: CDP's Input domain lets you simulate mouse clicks, keyboard input, text insertion, and touch operations directly at the browser engine level — more precise than Selenium, with the ability to mimic human-like timing patterns.

---

## Table of Contents

1. [Why Use CDP for Input Simulation](#why-use-cdp-for-input-simulation)
2. [Prerequisites: Connecting to Chrome](#prerequisites-connecting-to-chrome)
3. [Understanding CDP Coordinates](#understanding-cdp-coordinates)
4. [Simulating Mouse Clicks](#simulating-mouse-clicks)
5. [Mouse Movement & Drag-and-Drop](#mouse-movement--drag-and-drop)
6. [Simulating Keyboard Input](#simulating-keyboard-input)
7. [Text Insertion](#text-insertion)
8. [Touch Event Simulation](#touch-event-simulation)
9. [Complete Reference: CDP InputSimulator Class](#complete-reference-cdp-inputsimulator-class)
10. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Input Simulation

Compared to Selenium/Playwright's `click()` and `send_keys()`, CDP input simulation offers unique advantages:

| Feature | Selenium | CDP Input |
|---------|----------|-----------|
| Separate press/release | ❌ Only click() | ✅ Exact mousePressed/mouseReleased control |
| Multi-key combinations | ⚠️ Complex ActionChains | ✅ Arbitrary key combos |
| Drag operations | ⚠️ Unstable drag_and_drop | ✅ Pixel-level control |
| Touch events | ❌ Requires TouchAction | ✅ Native touch events |
| Text insertion | ✅ send_keys | ✅ insertText (bypasses event listeners) |
| Hover states | ✅ move_to | ✅ Precise mouseMoved positioning |

Key difference: CDP input simulation injects events directly into the browser's input event stream, bypassing any JavaScript event wrapper:
- Simulated clicks cannot be caught by `event.isTrusted` checks (significant for anti-bot purposes)
- Supports precise timing control
- Can simulate "virtual keys" that don't exist on physical keyboards

---

## Prerequisites: Connecting to Chrome

```python
import asyncio, json, websockets

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

## Understanding CDP Coordinates

CDP uses **viewport coordinates** — pixel positions relative to the top-left corner of the browser's content area, excluding toolbars and tab bars.

```python
# Getting element layout information for positioning
async def get_element_bounds(ws, session_id, css_selector):
    """Get element position and size in the viewport"""
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

### Coordinate & Button Value Reference

| Concept | CDP Parameter Value |
|---------|---------------------|
| Viewport top-left | (0, 0) |
| Scrolled page | Viewport coords unchanged, page moves relative |
| Left mouse button | `button: 0` |
| Middle mouse button | `button: 1` |
| Right mouse button | `button: 2` |
| Click count | `clickCount: 1` (single), `2` (double) |
| Modifier keys | `modifiers: 0` (none), `1` (Alt), `2` (Ctrl), `4` (Meta), `8` (Shift) |

### Modifier Bitmask Calculation

```python
def compute_modifiers(alt=False, ctrl=False, meta=False, shift=False):
    """Calculate modifier key bitmask"""
    mask = 0
    if alt:   mask |= 1
    if ctrl:  mask |= 2
    if meta:  mask |= 4
    if shift: mask |= 8
    return mask
```

---

## Simulating Mouse Clicks

### Input.dispatchMouseEvent

A basic click requires three steps: press, optionally move, then release.

```python
async def mouse_click(ws, session_id, x, y, button="left", click_count=1):
    """Simulate a mouse click at specified coordinates"""
    button_map = {"left": 0, "middle": 1, "right": 2}
    btn = button_map.get(button, 0)
    
    # 1. Move to target position
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseMoved",
        "x": x, "y": y,
        "button": btn,
        "buttons": 0,
        "clickCount": click_count
    }, session_id)
    
    # 2. Mouse press
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": x, "y": y,
        "button": btn,
        "buttons": 1,
        "clickCount": click_count
    }, session_id)
    
    # 3. Brief delay then release
    await asyncio.sleep(0.05)
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": x, "y": y,
        "button": btn,
        "buttons": 0,
        "clickCount": click_count
    }, session_id)

# Usage
async def demo_click():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        await cdp(ws, "Page.navigate",
                  {"url": "https://www.baidu.com"}, session_id)
        await asyncio.sleep(2)
        
        # Click near the center of the page
        await mouse_click(ws, session_id, 500, 300)
```

### Left Click, Right Click, Double Click

```python
async def right_click(ws, session_id, x, y):
    """Right-click (opens context menu)"""
    await mouse_click(ws, session_id, x, y, button="right")

async def double_click(ws, session_id, x, y):
    """Double-click"""
    # First click
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
    
    # Second click (clickCount=2)
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

### Click with Modifier Keys

```python
async def ctrl_click(ws, session_id, x, y):
    """Ctrl+Click (opens link in new tab, etc.)"""
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

## Mouse Movement & Drag-and-Drop

### Smooth Mouse Movement

```python
async def mouse_move(ws, session_id, x, y, steps=10):
    """Smoothly move the mouse to a target position"""
    start_x, start_y = 0, 0
    
    for i in range(1, steps + 1):
        current_x = start_x + (x - start_x) * i // steps
        current_y = start_y + (y - start_y) * i // steps
        
        # Add small random jitter to simulate human movement
        import random
        jitter_x = current_x + (0 if i == steps else random.randint(-2, 2))
        jitter_y = current_y + (0 if i == steps else random.randint(-2, 2))
        
        await cdp(ws, "Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": jitter_x,
            "y": jitter_y,
            "button": 0,
            "buttons": 0
        }, session_id)
        
        await asyncio.sleep(0.01)
```

### Drag-and-Drop

Drag = mousePressed → multiple mouseMoved (while held) → mouseReleased:

```python
async def drag_and_drop(ws, session_id, start_x, start_y, end_x, end_y, steps=20):
    """Drag from start to end position"""
    # 1. Move to start position
    await mouse_move(ws, session_id, start_x, start_y)
    
    # 2. Press left button at start
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mousePressed",
        "x": start_x, "y": start_y,
        "button": 0,
        "buttons": 1,
        "clickCount": 1
    }, session_id)
    
    # 3. Drag step by step (keep buttons=1 for held state)
    for i in range(1, steps + 1):
        current_x = start_x + (end_x - start_x) * i // steps
        current_y = start_y + (end_y - start_y) * i // steps
        
        await cdp(ws, "Input.dispatchMouseEvent", {
            "type": "mouseMoved",
            "x": current_x, "y": current_y,
            "button": 0,
            "buttons": 1,
            "clickCount": 1
        }, session_id)
        await asyncio.sleep(0.015)
    
    # 4. Release
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseReleased",
        "x": end_x, "y": end_y,
        "button": 0,
        "buttons": 0,
        "clickCount": 1
    }, session_id)

# Demo: drag an element
async def demo_drag():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        
        await cdp(ws, "Page.navigate",
                  {"url": "https://sortablejs.github.io/Sortable/"}, session_id)
        await asyncio.sleep(3)
        
        bounds = await get_element_bounds(ws, session_id, ".item:first-child")
        if bounds:
            start = (int(bounds["centerX"]), int(bounds["centerY"]))
            end = (start[0], start[1] + 200)
            await drag_and_drop(ws, session_id, start[0], start[1], end[0], end[1])
```

### Scroll Wheel

```python
async def scroll_page(ws, session_id, delta_x=0, delta_y=300):
    """Simulate mouse wheel scroll"""
    await cdp(ws, "Input.dispatchMouseEvent", {
        "type": "mouseWheel",
        "x": 400, "y": 400,
        "deltaX": delta_x,
        "deltaY": delta_y
    }, session_id)

async def smooth_scroll_to(ws, session_id, target_y, step=100):
    """Smooth scroll to a target Y position"""
    import random
    current = 0
    while current < target_y:
        step_size = min(step + random.randint(-20, 20), target_y - current)
        await scroll_page(ws, session_id, delta_y=step_size)
        current += step_size
        await asyncio.sleep(0.05)
```

---

## Simulating Keyboard Input

### Input.dispatchKeyEvent

Keyboard events follow the pattern: keyDown → (optional char) → keyUp:

```python
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
    """Simulate a single key press"""
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "keyDown",
        "key": key_text
    }, session_id)
    await asyncio.sleep(0.05)
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "keyUp",
        "key": key_text
    }, session_id)

async def type_text(ws, session_id, text, delay=0.05):
    """Simulate keyboard typing character by character"""
    for char in text:
        await cdp(ws, "Input.dispatchKeyEvent", {
            "type": "keyDown",
            "key": char,
            "text": char
        }, session_id)
        
        await cdp(ws, "Input.dispatchKeyEvent", {
            "type": "char",
            "key": char,
            "text": char
        }, session_id)
        
        await cdp(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp",
            "key": char,
            "text": char
        }, session_id)
        
        await asyncio.sleep(delay)
```

### Key Combinations

```python
async def select_all_and_copy(ws, session_id):
    """Select all then copy (Ctrl+A, Ctrl+C)"""
    modifiers = compute_modifiers(ctrl=True)
    
    # Ctrl+A
    await cdp(ws, "Input.dispatchKeyEvent", {
        "type": "rawKeyDown",
        "windowsVirtualKeyCode": 65,
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
        "windowsVirtualKeyCode": 67,
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

## Text Insertion

### Input.insertText

Unlike character-by-character keyboard simulation, `Input.insertText` directly inserts text into the focused element, bypassing the keyboard event pipeline:

```python
async def insert_text(ws, session_id, text):
    """Directly insert text into the focused element (bypasses keyboard events)"""
    await cdp(ws, "Input.insertText", {
        "text": text
    }, session_id)

# Usage: focus an input, then insert text directly
async def fast_text_input(ws, session_id, css_selector, text):
    """Quickly fill text into an input box"""
    js = f"document.querySelector('{css_selector}').focus();"
    await cdp(ws, "Runtime.evaluate",
        {"expression": js}, session_id)
    
    await asyncio.sleep(0.2)
    await insert_text(ws, session_id, text)
```

### insertText vs dispatchKeyEvent Comparison

| Method | Keyboard Events | Speed | Use Case |
|--------|-----------------|-------|----------|
| dispatchKeyEvent | ✅ Fires all events | Slow (per character) | Simulating real typing |
| insertText | ❌ No keyboard events | Very fast | Quick form filling |
| Direct DOM set | ❌ No events at all | Fastest | Background data injection |

---

## Touch Event Simulation

### Input.dispatchTouchEvent

Mobile emulation or touchscreen scenarios require touch events:

```python
async def touch_tap(ws, session_id, x, y):
    """Simulate a touch tap"""
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{"x": x, "y": y}],
        "modifiers": 0
    }, session_id)
    
    await asyncio.sleep(0.05)
    
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": [],
        "modifiers": 0
    }, session_id)

async def touch_scroll(ws, session_id, start_x, start_y, end_x, end_y, steps=10):
    """Simulate touch scroll (swipe)"""
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [{"x": start_x, "y": start_y}],
        "modifiers": 0
    }, session_id)
    
    for i in range(1, steps + 1):
        current_x = start_x + (end_x - start_x) * i // steps
        current_y = start_y + (end_y - start_y) * i // steps
        
        await cdp(ws, "Input.dispatchTouchEvent", {
            "type": "touchMove",
            "touchPoints": [{"x": current_x, "y": current_y}],
            "modifiers": 0
        }, session_id)
        await asyncio.sleep(0.01)
    
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": [],
        "modifiers": 0
    }, session_id)

async def touch_pinch(ws, session_id, center_x, center_y, start_radius, end_radius):
    """Simulate two-finger pinch zoom"""
    # touchStart (two touch points)
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchStart",
        "touchPoints": [
            {"x": center_x - start_radius, "y": center_y},
            {"x": center_x + start_radius, "y": center_y}
        ],
        "modifiers": 0
    }, session_id)
    
    # touchMove gradually moving both points
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
    
    await cdp(ws, "Input.dispatchTouchEvent", {
        "type": "touchEnd",
        "touchPoints": [],
        "modifiers": 0
    }, session_id)
```

---

## Complete Reference: CDP InputSimulator Class

```python
import asyncio
import json
import random
import websockets


class CDPInputSimulator:
    """CDP Input Simulator"""
    
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
    
    # ===== Mouse Operations =====
    
    async def click(self, x: int, y: int, button: str = "left",
                    click_count: int = 1, modifiers: int = 0):
        """Click at specified coordinates"""
        btn = {"left": 0, "middle": 1, "right": 2}.get(button, 0)
        
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseMoved", "x": x, "y": y,
            "button": btn, "buttons": 0, "clickCount": click_count,
            "modifiers": modifiers
        })
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": x, "y": y,
            "button": btn, "buttons": 1, "clickCount": click_count,
            "modifiers": modifiers
        })
        await asyncio.sleep(0.05)
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": x, "y": y,
            "button": btn, "buttons": 0, "clickCount": click_count,
            "modifiers": modifiers
        })
    
    async def double_click(self, x: int, y: int):
        """Double-click"""
        await self.click(x, y, click_count=1)
        await asyncio.sleep(0.1)
        await self.click(x, y, click_count=2)
    
    async def right_click(self, x: int, y: int):
        """Right-click"""
        await self.click(x, y, button="right")
    
    async def move_mouse(self, x: int, y: int, steps: int = 10):
        """Smooth mouse movement"""
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
        """Drag operation"""
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mousePressed", "x": start_x, "y": start_y,
            "button": 0, "buttons": 1, "clickCount": 1
        })
        for i in range(1, steps + 1):
            cx = start_x + (end_x - start_x) * i // steps
            cy = start_y + (end_y - start_y) * i // steps
            await self._cdp("Input.dispatchMouseEvent", {
                "type": "mouseMoved", "x": cx, "y": cy,
                "button": 0, "buttons": 1, "clickCount": 1
            })
            await asyncio.sleep(0.015)
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseReleased", "x": end_x, "y": end_y,
            "button": 0, "buttons": 0, "clickCount": 1
        })
    
    async def scroll(self, delta_x: int = 0, delta_y: int = 300,
                     x: int = 400, y: int = 400):
        """Mouse wheel"""
        await self._cdp("Input.dispatchMouseEvent", {
            "type": "mouseWheel", "x": x, "y": y,
            "deltaX": delta_x, "deltaY": delta_y
        })
    
    # ===== Keyboard Operations =====
    
    async def press_key(self, key: str):
        """Press and release a key"""
        await self._cdp("Input.dispatchKeyEvent", {
            "type": "keyDown", "key": key
        })
        await asyncio.sleep(0.05)
        await self._cdp("Input.dispatchKeyEvent", {
            "type": "keyUp", "key": key
        })
    
    async def type_text(self, text: str, delay: float = 0.05):
        """Type text character by character"""
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
        """Directly insert text (bypasses keyboard events)"""
        await self._cdp("Input.insertText", {"text": text})
    
    async def hotkey(self, *keys):
        """Key combination: hotkey('Control', 'a') → Ctrl+A"""
        modifiers = 0
        mod_map = {"Control": 2, "Alt": 1, "Shift": 8, "Meta": 4}
        
        for k in keys[:-1]:
            if k in mod_map:
                modifiers |= mod_map[k]
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "keyDown", "key": k
            })
        
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
        
        for k in reversed(keys[:-1]):
            await self._cdp("Input.dispatchKeyEvent", {
                "type": "keyUp", "key": k
            })
    
    # ===== Touch Operations =====
    
    async def touch_tap(self, x: int, y: int):
        """Touch tap"""
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
        """Touch swipe"""
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
    
    # ===== Helper Methods =====
    
    async def focus_element(self, css_selector: str):
        """Focus an element"""
        await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}').focus()"
        })
    
    async def click_element(self, css_selector: str):
        """Click element via JS (no mouse simulation)"""
        await self._cdp("Runtime.evaluate", {
            "expression": f"document.querySelector('{css_selector}').click()"
        })

    async def human_like_typing(self, text: str, target_wpm: int = 120):
        """Simulate human-like typing with random delay variation"""
        # 120 WPM ≈ 80-120ms per character
        base_delay = 60.0 / (target_wpm * 5)
        for char in text:
            delay = base_delay * random.uniform(0.5, 1.8)
            await self.type_text(char, 0)
            await asyncio.sleep(delay)
```

**Usage example:**

```python
async def demo_input_simulator():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        sim = CDPInputSimulator(ws, session_id)
        
        await sim._cdp("Page.navigate", {"url": "https://www.baidu.com"})
        await asyncio.sleep(2)
        
        # Focus search box
        await sim.focus_element("#kw")
        await asyncio.sleep(0.5)
        
        # Type with human-like speed
        await sim.human_like_typing("Python CDP tutorial", target_wpm=100)
        await asyncio.sleep(1)
        
        # Click the search button via JS
        await sim.click_element("#su")
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Viewport vs Page Coordinates

```python
# ❌ Page scrolled, element coordinates have shifted
scroll_y = 500
await mouse_click(ws, session_id, 100, scroll_y)  # Hits wrong location!

# ✅ Use getBoundingClientRect to get current viewport coordinates
bounds = await get_element_bounds(ws, session_id, "#my-button")
await mouse_click(ws, session_id, bounds["centerX"], bounds["centerY"])
```

### Pitfall 2: File Input Elements Can't Be Clicked

```python
# ❌ File inputs cannot be activated via CDP click
await mouse_click(ws, session_id, x, y)  # Won't open file chooser

# ✅ Use DOM.setFileInputFiles or Page.setInterceptFileChooserDialog instead
```

### Pitfall 3: Missing Key Event Parameters

```python
# ❌ Missing code field — some apps may not recognize the key
await cdp(ws, "Input.dispatchKeyEvent", {
    "type": "keyDown", "key": "a"
}, session_id)

# ✅ Provide complete parameters
await cdp(ws, "Input.dispatchKeyEvent", {
    "type": "keyDown",
    "key": "a",
    "code": "KeyA",
    "text": "a",
    "windowsVirtualKeyCode": 65
}, session_id)
```

### Pitfall 4: insertText Requires Focus

```python
# ❌ No element focused, text has nowhere to go
await insert_text(ws, session_id, "hello")

# ✅ Focus the target element first
await sim.focus_element("#input-box")
await asyncio.sleep(0.2)
await insert_text(ws, session_id, "hello")
```

### Pitfall 5: IME Interference

In some cases, Chrome's input method editor intercepts insertText. Use the IME command instead:

```python
async def ime_set_composition(ws, session_id, text, selection_start, selection_end):
    """Set IME composition text"""
    await cdp(ws, "Input.imeSetComposition", {
        "text": text,
        "selectionStart": selection_start,
        "selectionEnd": selection_end
    }, session_id)
```

### Best Practices Checklist

| Note | Recommendation |
|------|----------------|
| Coordinates | Use `getBoundingClientRect()` dynamically |
| Realism | Add random delays and mouse jitter |
| Event order | Always mousePressed → ... → mouseReleased |
| Key completeness | Provide key + code + windowsVirtualKeyCode |
| Touch simulation | Mobile pages must use touch events |
| Focus prerequisite | Ensure element is focused before insertText/keyboard input |

---

> **Summary**: CDP's Input domain provides complete input simulation capabilities — from mouse clicks and keyboard input to drag-and-drop and touch events. With the InputSimulator wrapper class, you can simulate virtually any user operation down to the pixel-level timing, achieving highly realistic human-computer interaction automation.

*Previous: CDP Target Management: Controlling Multiple Pages with Python*

*Next up: CDP File Upload & Download: Handling File Operations with Python*