---
title: CDP 剪贴板操作指南：用 Python 读写系统剪贴板
date: 2026-06-05 19:30:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Clipboard
  - Automation
  - Permissions
categories:
  - CDP 进阶
  - Python 实战
description: 全面讲解如何用 CDP 操作浏览器剪贴板。涵盖通过 Runtime.evaluate 调用 navigator.clipboard 读写文本、处理剪贴板权限、使用 Browser.grantPermissions 一键授权、自动化复制粘贴操作，以及通过 DOM.setFileInputFiles 处理剪贴板文件。
---

> **一句话总结**：结合 CDP 的 Runtime.evaluate 和 Browser.grantPermissions，你可以完全自动化浏览器的剪贴板读写操作——无需人工点击授权弹窗，可编程地进行复制、粘贴和文件上传。

---

## 目录

1. [为什么用 CDP 操作剪贴板](#为什么用-cdp-操作剪贴板)
2. [基础：连接与权限设置](#基础连接与权限设置)
3. [读取剪贴板文本](#读取剪贴板文本)
4. [写入剪贴板文本](#写入剪贴板文本)
5. [权限处理详解](#权限处理详解)
6. [自动化复制粘贴操作](#自动化复制粘贴操作)
7. [通过 DOM.setFileInputFiles 处理文件](#通过-domsetfileinputfiles-处理文件)
8. [实战：跨页面数据搬运](#实战跨页面数据搬运)
9. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 操作剪贴板

浏览器剪贴板 API（`navigator.clipboard`）受到严格的安全限制：

| 限制 | 常规 JavaScript | CDP + Python |
|------|----------------|--------------|
| HTTPS 要求 | 必须在 HTTPS 页面 | 无限制（包括 HTTP/localhost） |
| 用户手势要求 | 必须在用户事件中调用 | 无需用户交互 |
| 权限弹窗 | `clipboard-read` 需用户批准 | `Browser.grantPermissions` 静默授权 |
| 文档焦点要求 | 页面必须处于焦点状态 | CDP 可后台操作 |
| 跨域访问 | 仅当前域名 | 可导航到任意域名操作 |
| 文件剪贴板 | API 支持有限 | 结合 DOM 操作可完全控制 |

---

## 基础：连接与权限设置

### 统一 CDP 辅助函数

```python
import asyncio
import websockets
import json
import base64

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

### 启用所需域

```python
async def enable_domains(ws, session_id):
    """启用操作剪贴板所需的所有 CDP 域"""
    await cdp(ws, "Page.enable", session_id=session_id)
    await cdp(ws, "Runtime.enable", session_id=session_id)
    print("所有必要域已启用")
```

### 一键授权剪贴板权限

这是 CDP 操作剪贴板的关键——可以在不弹出权限对话框的情况下授予权限：

```python
async def grant_clipboard_permissions(ws, session_id, origin=None):
    """
    通过 CDP 静默授权剪贴板访问权限
    无需用户手动点击"允许"按钮
    """
    params = {
        "permissions": [
            {"name": "clipboard-read"},
            {"name": "clipboard-write"}
        ]
    }
    if origin:
        params["origin"] = origin
    
    await cdp(ws, "Browser.grantPermissions", params, session_id=session_id)
    print(f"剪贴板权限已授予（origin: {origin or '当前页面'}）")
    return True


async def revoke_clipboard_permissions(ws, session_id, origin=None):
    """撤销已授予的剪贴板权限"""
    params = {
        "permissions": [
            {"name": "clipboard-read"},
            {"name": "clipboard-write"}
        ]
    }
    if origin:
        params["origin"] = origin
    
    await cdp(ws, "Browser.resetPermissions", params, session_id=session_id)
    print("剪贴板权限已撤销")
```

---

## 读取剪贴板文本

通过 `Runtime.evaluate` 调用 `navigator.clipboard.readText()` 读取系统剪贴板：

```python
async def read_clipboard_text(ws, session_id):
    """
    读取系统剪贴板中的文本内容
    需要在调用前先授予 clipboard-read 权限
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (async () => {
                try {
                    const text = await navigator.clipboard.readText();
                    return { success: true, data: text };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            })()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        clipboard_text = outcome["data"]
        print(f"剪贴板内容读取成功: {clipboard_text[:100]}{'...' if len(clipboard_text) > 100 else ''}")
        return clipboard_text
    else:
        error = outcome.get("error", "未知错误")
        print(f"读取剪贴板失败: {error}")
        return None


async def read_clipboard_html(ws, session_id):
    """
    读取剪贴板中的 HTML 内容
    注意：部分浏览器/系统可能不支持
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (async () => {
                try {
                    const items = await navigator.clipboard.read();
                    const results = [];
                    for (const item of items) {
                        const entry = { types: item.types };
                        for (const type of item.types) {
                            const blob = await item.getType(type);
                            entry[type] = await blob.text();
                        }
                        results.push(entry);
                    }
                    return { success: true, data: results };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            })()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        items = outcome["data"]
        for i, item in enumerate(items):
            print(f"剪贴板条目 {i + 1}: 类型 = {item.get('types', [])}")
            for content_type, content in item.items():
                if content_type != "types" and content:
                    print(f"  {content_type}: {str(content)[:200]}")
        return items
    else:
        print(f"读取剪贴板 HTML 失败: {outcome.get('error', '')}")
        return None
```

---

## 写入剪贴板文本

通过 `navigator.clipboard.writeText()` 将内容写入系统剪贴板：

```python
async def write_clipboard_text(ws, session_id, text):
    """
    将指定文本写入系统剪贴板
    需要在调用前先授予 clipboard-write 权限
    """
    escaped_text = json.dumps(text)
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (async () => {{
                try {{
                    await navigator.clipboard.writeText({escaped_text});
                    return {{ success: true }};
                }} catch (e) {{
                    return {{ success: false, error: e.message }};
                }}
            }})()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        print(f"文本已写入剪贴板（{len(text)} 字符）")
        return True
    else:
        print(f"写入剪贴板失败: {outcome.get('error', '')}")
        return False


async def write_clipboard_with_format(ws, session_id, text, html=None):
    """
    将格式化内容写入剪贴板（同时提供纯文本和 HTML 版本）
    粘贴时目标应用会自动选择最合适的格式
    """
    escaped_text = json.dumps(text)
    escaped_html = json.dumps(html or text)
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (async () => {{
                try {{
                    const blob_text = new Blob(
                        [{escaped_text}], {{ type: 'text/plain' }}
                    );
                    const blob_html = new Blob(
                        [{escaped_html}], {{ type: 'text/html' }}
                    );
                    await navigator.clipboard.write([
                        new ClipboardItem({{
                            'text/plain': blob_text,
                            'text/html': blob_html
                        }})
                    ]);
                    return {{ success: true }};
                }} catch (e) {{
                    return {{ success: false, error: e.message }};
                }}
            }})()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        print(f"格式化内容已写入剪贴板（文本: {len(text)} 字符, HTML: {len(html or text)} 字符）")
        return True
    else:
        print(f"写入格式化剪贴板失败: {outcome.get('error', '')}")
        return False
```

---

## 权限处理详解

### 检查当前页面的权限状态

```python
async def check_clipboard_permission(ws, session_id, perm_name="clipboard-read"):
    """
    检查当前页面是否拥有指定的剪贴板权限
    perm_name: clipboard-read 或 clipboard-write
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (async () => {{
                try {{
                    const status = await navigator.permissions.query({{ name: '{perm_name}' }});
                    return {{
                        state: status.state,
                        name: status.name
                    }};
                }} catch (e) {{
                    return {{ state: 'error', error: e.message }};
                }}
            }})()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    status = result.get("result", {}).get("value", {})
    state = status.get("state", "unknown")
    
    state_labels = {
        "granted": "✅ 已授予",
        "prompt": "⏳ 需要用户确认",
        "denied": "❌ 已拒绝"
    }
    
    print(f"权限 '{perm_name}': {state_labels.get(state, state)}")
    return status


async def check_all_clipboard_permissions(ws, session_id):
    """检查所有剪贴板相关权限的状态"""
    for perm in ["clipboard-read", "clipboard-write"]:
        await check_clipboard_permission(ws, session_id, perm)


async def ensure_clipboard_access(ws, session_id):
    """
    确保剪贴板可访问——先授权再检查
    如果授权后权限状态不对，输出警告
    """
    await grant_clipboard_permissions(ws, session_id)
    await asyncio.sleep(0.5)
    
    read_status = await check_clipboard_permission(ws, session_id, "clipboard-read")
    
    if read_status.get("state") != "granted":
        print("⚠️ 警告: clipboard-read 权限未生效，尝试使用 Browser.grantPermissions 指定 origin")
        # 回退方案：通过 Runtime.evaluate 获取当前 origin 后再次授权
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.origin"
        }, session_id=session_id)
        origin = result.get("result", {}).get("value", "")
        if origin:
            await grant_clipboard_permissions(ws, session_id, origin)
```

### 不同 origin 的权限隔离

```python
async def grant_for_specific_origin(ws, target_url):
    """
    授权特定 origin 的剪贴板权限
    适用于需要在多个页面之间切换的场景
    """
    session_id = None
    
    async with websockets.connect(CDP_URL) as ws:
        # 导航到目标页面
        result = await cdp(ws, "Target.getTargets")
        target_id = result["targetInfos"][0]["targetId"]
        session = await cdp(ws, "Target.attachToTarget", {
            "targetId": target_id, "flatten": True
        })
        session_id = session["sessionId"]
        
        # 导航并等待
        await cdp(ws, "Page.enable", session_id=session_id)
        await cdp(ws, "Page.navigate", {"url": target_url}, session_id=session_id)
        await asyncio.sleep(2)
        
        # 从 URL 提取 origin
        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        
        # 授权
        await grant_clipboard_permissions(ws, session_id, origin)
        
        return session_id
```

---

## 自动化复制粘贴操作

### 完整的复制-粘贴流水线

```python
async def auto_copy(ws, session_id, selector=None, js_expression=None):
    """
    自动化复制操作：
    - 方式一：通过选择器复制某个元素的文本
    - 方式二：通过 JS 表达式复制数据
    
    返回复制的内容
    """
    if selector:
        # 从页面元素复制
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    try {{
                        const el = document.querySelector('{selector}');
                        if (!el) return {{ success: false, error: '元素未找到' }};
                        const text = el.textContent || el.value || el.innerText;
                        
                        // 先写入剪贴板
                        await navigator.clipboard.writeText(text);
                        
                        // 标记被复制元素
                        el.style.outline = '2px solid #4CAF50';
                        return {{ success: true, data: text }};
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }})()
            """,
            "awaitPromise": True
        }, session_id=session_id)
    elif js_expression:
        # 通过表达式复制
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    try {{
                        const data = {js_expression};
                        const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
                        await navigator.clipboard.writeText(text);
                        return {{ success: true, data: text }};
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }})()
            """,
            "awaitPromise": True
        }, session_id=session_id)
    else:
        raise ValueError("必须提供 selector 或 js_expression")
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        copied = outcome["data"]
        print(f"✅ 复制成功: {copied[:100]}{'...' if len(copied) > 100 else ''}")
        return copied
    else:
        print(f"❌ 复制失败: {outcome.get('error', '')}")
        return None


async def auto_paste(ws, session_id, target_selector=None):
    """
    自动化粘贴操作：
    - 如果指定 target_selector，将剪贴板内容粘贴到目标元素
    - 如果不指定，仅读取剪贴板内容
    """
    # 先读取剪贴板
    clipboard_text = await read_clipboard_text(ws, session_id)
    
    if clipboard_text is None:
        print("剪贴板为空或无法读取")
        return None
    
    if target_selector:
        # 粘贴到指定元素
        escaped_text = json.dumps(clipboard_text)
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const el = document.querySelector('{target_selector}');
                    if (!el) return {{ success: false, error: '元素未找到' }};
                    
                    // 模拟粘贴
                    el.focus();
                    
                    const start = el.selectionStart || 0;
                    const end = el.selectionEnd || 0;
                    const currentValue = el.value || el.textContent || '';
                    el.value = currentValue.substring(0, start) + 
                                {escaped_text} + 
                                currentValue.substring(end);
                    
                    // 触发 input 事件
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    
                    return {{ success: true, pasted_length: {escaped_text}.length }};
                }})()
            """
        }, session_id=session_id)
        
        paste_result = result.get("result", {}).get("value", {})
        if paste_result.get("success"):
            print(f"✅ 已粘贴到元素 '{target_selector}'（{paste_result['pasted_length']} 字符）")
            return clipboard_text
        else:
            print(f"❌ 粘贴失败: {paste_result.get('error', '')}")
            return None
    
    return clipboard_text


async def copy_element_by_text(ws, session_id, text_contains):
    """
    通过文本内容查找元素并复制其内容
    适用于复制表格数据、代码块等
    """
    expression = f"""
        (() => {{
            const elements = document.querySelectorAll('*');
            for (const el of elements) {{
                if (el.children.length === 0 && 
                    el.textContent.trim().includes('{text_contains}')) {{
                    return el.textContent.trim();
                }}
            }}
            // 也查找包含该文本的父元素
            for (const el of elements) {{
                if (el.textContent.includes('{text_contains}') && 
                    el.textContent.length < 5000) {{
                    return el.textContent.trim();
                }}
            }}
            return null;
        }})()
    """
    
    return await auto_copy(ws, session_id, js_expression=expression)
```

### 监听剪贴板变化

```python
async def monitor_clipboard_changes(ws, session_id, interval=1, max_checks=10):
    """
    轮询监视剪贴板内容变化
    适用于检测页面操作是否修改了剪贴板
    """
    last_content = await read_clipboard_text(ws, session_id)
    print(f"初始剪贴板: {last_content[:50] if last_content else '空'}")
    
    for i in range(max_checks):
        await asyncio.sleep(interval)
        
        current = await read_clipboard_text(ws, session_id)
        
        if current != last_content:
            print(f"[第 {i + 1} 次检查] 剪贴板内容已变化!")
            print(f"  旧: {str(last_content)[:100]}")
            print(f"  新: {str(current)[:100]}")
            last_content = current
        else:
            print(f"[第 {i + 1} 次检查] 无变化")
    
    return last_content
```

---

## 通过 DOM.setFileInputFiles 处理文件

对于剪贴板中的文件处理，使用 `DOM.setFileInputFiles` 是更实际的方式：

```python
async def get_file_input_element(ws, session_id, selector):
    """
    通过选择器获取文件输入元素的 DOM 节点 ID
    需要在 Page.enable 状态下使用
    """
    # 先通过 Runtime 获取节点
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el) return {{ found: false }};
                return {{ found: true, tag: el.tagName, type: el.type }};
            }})()
        """
    }, session_id=session_id)
    
    info = result.get("result", {}).get("value", {})
    
    if info.get("found"):
        print(f"找到文件输入元素: <{info['tag']} type='{info['type']}'>")
        return True
    else:
        print(f"未找到选择器 '{selector}' 对应的元素")
        return False


async def set_file_input(ws, session_id, selector, file_paths):
    """
    通过 CDP 的 DOM.setFileInputFiles 设置文件输入
    
    与 navigator.clipboard 不同，这个方法直接操作文件输入元素，
    不需要剪贴板权限，但页面必须在焦点状态
    """
    # 第一步：通过 Runtime.evaluate 获取文件的 RemoteObject
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el) return null;
                return el;
            }})()
        """,
        "objectGroup": "file_input"
    }, session_id=session_id)
    
    remote_obj = result.get("result", {})
    object_id = remote_obj.get("objectId")
    
    if not object_id:
        print(f"❌ 无法获取元素 '{selector}' 的引用")
        return False
    
    # 第二步：通过 DOM 域获取节点描述
    dom_result = await cdp(ws, "DOM.requestNode", {
        "objectId": object_id
    }, session_id=session_id)
    
    node_id = dom_result.get("nodeId")
    
    if not node_id:
        print("❌ 无法解析节点 ID")
        return False
    
    # 第三步：设置文件
    await cdp(ws, "DOM.setFileInputFiles", {
        "nodeId": node_id,
        "files": file_paths if isinstance(file_paths, list) else [file_paths]
    }, session_id=session_id)
    
    # 验证
    verify = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el || !el.files) return 0;
                return el.files.length;
            }})()
        """
    }, session_id=session_id)
    
    file_count = verify.get("result", {}).get("value", 0)
    print(f"✅ 已设置 {file_count} 个文件到输入元素")
    return file_count > 0


async def simulate_paste_event(ws, session_id, target_selector, text):
    """
    模拟在目标元素上触发 paste 事件
    这是一个备用方案，当 navigator.clipboard 不可用时使用
    """
    escaped = json.dumps(text)
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{target_selector}');
                if (!el) return false;
                
                const dt = new DataTransfer();
                dt.setData('text/plain', {escaped});
                
                const event = new ClipboardEvent('paste', {{
                    clipboardData: dt,
                    bubbles: true,
                    cancelable: true
                }});
                
                el.dispatchEvent(event);
                return true;
            }})()
        """
    }, session_id=session_id)
    
    success = result.get("result", {}).get("value", False)
    print(f"{'✅' if success else '❌'} paste 事件模拟: {'成功' if success else '失败'}")
    return success
```

---

## 实战：跨页面数据搬运

一个实际的场景：从页面 A 提取数据，通过剪贴板搬运到页面 B：

```python
async def cross_page_clipboard_transfer(ws, source_url, target_url, extract_js, target_selector):
    """
    完整的数据搬运流程：
    1. 导航到源页面，提取数据
    2. 写入剪贴板
    3. 导航到目标页面
    4. 粘贴到目标元素
    
    参数:
        source_url: 源数据页面
        target_url: 目标页面
        extract_js: 提取数据的 JS 表达式（返回字符串）
        target_selector: 目标页面的粘贴位置 CSS 选择器
    """
    result = await cdp(ws, "Target.getTargets")
    target_id = result["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    session_id = session["sessionId"]
    
    # 启用域
    await cdp(ws, "Page.enable", session_id=session_id)
    await cdp(ws, "Runtime.enable", session_id=session_id)
    
    # ----- 步骤 1: 导航到源页面，提取数据 -----
    print("=" * 50)
    print("步骤 1: 提取源数据")
    print("=" * 50)
    
    await cdp(ws, "Page.navigate", {"url": source_url}, session_id=session_id)
    await asyncio.sleep(3)
    
    # 授权剪贴板写入
    await grant_clipboard_permissions(ws, session_id)
    
    # 提取数据并写入剪贴板
    extracted = await auto_copy(ws, session_id, js_expression=extract_js)
    
    if not extracted:
        print("❌ 数据提取失败")
        return False
    
    print(f"已提取 {len(extracted)} 字符的数据")
    
    # ----- 步骤 2: 导航到目标页面，粘贴 -----
    print("=" * 50)
    print("步骤 2: 搬运到目标页面")
    print("=" * 50)
    
    await cdp(ws, "Page.navigate", {"url": target_url}, session_id=session_id)
    await asyncio.sleep(3)
    
    # 在新页面重新授权（跨域后权限可能重置）
    await grant_clipboard_permissions(ws, session_id)
    
    # 现在先读取验证剪贴板是否还在
    verify = await read_clipboard_text(ws, session_id)
    if verify != extracted:
        print("⚠️ 剪贴板内容跨页后发生变化，重新写入...")
        await write_clipboard_text(ws, session_id, extracted)
    
    # 粘贴到目标
    pasted = await auto_paste(ws, session_id, target_selector)
    
    if pasted:
        print(f"✅ 数据搬运完成！从 {source_url} → {target_url}")
        return True
    else:
        print("❌ 粘贴失败")
        return False


async def run_transfer_example():
    """运行跨页数据搬运示例"""
    source = "https://example.com/source-page"
    target = "https://example.com/target-page"
    
    # 提取页面中所有表格数据
    extract_js = """
        (() => {
            const tables = document.querySelectorAll('table');
            let result = '';
            tables.forEach((table, i) => {
                result += `=== 表 ${i + 1} ===\\n`;
                const rows = table.querySelectorAll('tr');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td, th');
                    result += Array.from(cells).map(c => c.textContent.trim()).join('\\t') + '\\n';
                });
                result += '\\n';
            });
            return result || document.body.innerText;
        })()
    """
    
    async with websockets.connect(CDP_URL) as ws:
        await cross_page_clipboard_transfer(
            ws,
            source_url=source,
            target_url=target,
            extract_js=extract_js,
            target_selector="textarea, [contenteditable='true'], .editor"
        )

# asyncio.run(run_transfer_example())
```

### 批量数据导出到剪贴板

```python
async def export_data_via_clipboard(ws, session_id, data_list, field_names):
    """
    将结构化数据列表导出为 TSV 格式并写入剪贴板
    用户可直接粘贴到 Excel/Google Sheets 中
    """
    # 构建 TSV
    header = "\t".join(field_names)
    rows = [header]
    
    for item in data_list:
        row = "\t".join(str(item.get(f, "")) for f in field_names)
        rows.append(row)
    
    tsv_content = "\n".join(rows)
    
    # 写入剪贴板（同时提供纯文本和 HTML 表格格式）
    html_rows = ["<table><tr>" + "".join(f"<th>{f}</th>" for f in field_names) + "</tr>"]
    for item in data_list:
        html_rows.append(
            "<tr>" + "".join(f"<td>{item.get(f, '')}</td>" for f in field_names) + "</tr>"
        )
    html_rows.append("</table>")
    html_content = "\n".join(html_rows)
    
    success = await write_clipboard_with_format(ws, session_id, tsv_content, html_content)
    
    if success:
        print(f"已导出 {len(data_list)} 行数据到剪贴板（Excel 可直接粘贴）")
    
    return success
```

---

## 常见踩坑与最佳实践

### 踩坑 1：权限必须在调用剪贴板 API 之前授予

```python
# ❌ 错误的调用顺序
await read_clipboard_text(ws, session_id)  # 先读取 → 失败
await grant_clipboard_permissions(ws, session_id)  # 后授权

# ✅ 正确的调用顺序
await grant_clipboard_permissions(ws, session_id)  # 先授权
await asyncio.sleep(0.3)  # 等待权限生效
await read_clipboard_text(ws, session_id)  # 再读取 → 成功
```

### 踩坑 2：跨域导航后权限会重置

```python
# 页面 A 已授权 → 导航到页面 B → clipboard-read 权限重置为 prompt
# 需要在每个页面单独授权

await grant_clipboard_permissions(ws, session_id)  # 页面 A 授权
await cdp(ws, "Page.navigate", {"url": "https://other-domain.com"}, session_id=session_id)
await grant_clipboard_permissions(ws, session_id)  # 页面 B 需要重新授权
```

### 踩坑 3：剪贴板 API 需要页面处于 active 状态

```python
# 如果页面被隐藏或失去焦点，clipboard API 可能失败
# 确保页面可见或使用 Page.bringToFront

# 方法：将页面带到前台
# 注意：CDP 不支持 bringToFront，但可以通过创建新窗口等方式
```

### 踩坑 4：某些 PDF/iframe 中的输入框不支持 ClipboardEvent

```python
# 对于不支持 ClipboardEvent 的元素，回退到：
# 1. 使用 DOM.setFileInputFiles（文件输入）
# 2. 使用 value 直接设置 + 触发 input 事件
# 3. 使用 ContentEditable 元素的 innerText 设置
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 权限顺序 | 读取/写入前必须先 grantPermissions |
| 跨域重置 | 每次导航到新域名后重新授权 |
| 错误处理 | 每个 clipboard API 调用都要加 try-catch |
| 页面焦点 | 确保目标页面在前台或可见状态 |
| 权限范围 | 权限是 per-origin 的，不是 per-page |
| 文件处理 | 使用 DOM.setFileInputFiles 而非 clipboard API |
| 验证机制 | 写入后立即读取验证 |

---

## 完整参考：CDP 剪贴板管理器类

```python
class CDPClipboardManager:
    """CDP 剪贴板操作管理器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
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
    
    async def grant_permissions(self, origin=None):
        """授予剪贴板读写权限"""
        params = {"permissions": [
            {"name": "clipboard-read"},
            {"name": "clipboard-write"}
        ]}
        if origin:
            params["origin"] = origin
        await self._cmd("Browser.grantPermissions", params)
        print("Clipboard permissions granted")
    
    async def read_text(self):
        """读取剪贴板文本"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": """
                (async () => {
                    try {
                        const t = await navigator.clipboard.readText();
                        return { ok: true, text: t };
                    } catch (e) {
                        return { ok: false, error: e.message };
                    }
                })()
            """,
            "awaitPromise": True
        })
        v = result.get("result", {}).get("value", {})
        return v.get("text") if v.get("ok") else None
    
    async def write_text(self, text):
        """写入文本到剪贴板"""
        escaped = json.dumps(text)
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    try {{
                        await navigator.clipboard.writeText({escaped});
                        return {{ ok: true }};
                    }} catch (e) {{
                        return {{ ok: false, error: e.message }};
                    }}
                }})()
            """,
            "awaitPromise": True
        })
        v = result.get("result", {}).get("value", {})
        return v.get("ok", False)
    
    async def copy_from_element(self, selector):
        """从页面元素复制文本"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return {{ ok: false }};
                    const text = el.textContent || el.value || '';
                    await navigator.clipboard.writeText(text);
                    return {{ ok: true, text: text }};
                }})()
            """,
            "awaitPromise": True
        })
        v = result.get("result", {}).get("value", {})
        return v.get("text") if v.get("ok") else None
    
    async def paste_to_element(self, selector, text):
        """将文本粘贴到目标元素"""
        escaped = json.dumps(text)
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return false;
                    el.focus();
                    const start = el.selectionStart || 0;
                    const val = el.value || el.textContent || '';
                    el.value = val.slice(0, start) + {escaped} + val.slice(el.selectionEnd || 0);
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }})()
            """
        })
        return result.get("result", {}).get("value", False)
    
    async def set_files(self, selector, file_paths):
        """通过 DOM.setFileInputFiles 设置文件"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                document.querySelector('{selector}');
            """,
            "objectGroup": "file_input"
        })
        obj_id = result.get("result", {}).get("objectId")
        if not obj_id:
            return False
        dom = await self._cmd("DOM.requestNode", {"objectId": obj_id})
        node_id = dom.get("nodeId")
        if not node_id:
            return False
        await self._cmd("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [file_paths] if isinstance(file_paths, str) else file_paths
        })
        return True
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    clip = CDPClipboardManager(ws, session_id)
    
    # 一键授权 → 读取 → 改写 → 粘贴
    await clip.grant_permissions()
    
    text = await clip.read_text()
    print(f"从剪贴板读取: {text}")
    
    await clip.write_text("新内容")
    
    await clip.paste_to_element("textarea#editor", "粘贴内容")
```

---

> **总结**：CDP 结合 `Browser.grantPermissions` 和 `Runtime.evaluate`，可以全自动操作浏览器剪贴板，无需用户交互。关键点在于：始终先在目标页面授予 clipboard-read 和 clipboard-write 权限、处理跨域导航后的权限重置、以及通过组合 navigator.clipboard API 和 DOM.setFileInputFiles 实现完整的剪贴板自动化方案。

---

*上一篇回顾：CDP 内存分析指南：用 Python 检测内存泄漏。*

*下一篇预告：CDP 浏览器历史管理：用 Python 控制页面导航历史。*