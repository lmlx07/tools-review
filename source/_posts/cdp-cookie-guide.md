---
title: CDP 操作 Cookie 完全指南：用 Python 实现增删改查与自动化登录
date: 2026-06-05 10:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 浏览器自动化
  - Cookie
  - 爬虫
categories:
  - CDP 基础
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）操作浏览器 Cookie，涵盖读取所有 Cookie、按域名筛选、新增/修改 Cookie、删除指定 Cookie、清空所有 Cookie，以及两个实战场景：Cookie 注入实现免登录和导出 Cookie 供 requests 复用。
---

> **一句话总结**：CDP 提供了比 JavaScript `document.cookie` 更强大的 Cookie 操作 API，你可以读取任意域名的 Cookie、设置带各种标志位的 Cookie、精确删除指定 Cookie，甚至清空整个浏览器的所有 Cookie。

---

## 目录

1. [为什么用 CDP 操作 Cookie](#为什么用-cdp-操作-cookie)
2. [前置准备：连接 Chrome](#前置准备连接-chrome)
3. [读取 Cookie](#读取-cookie)
4. [新增 Cookie](#新增-cookie)
5. [删除 Cookie](#删除-cookie)
6. [修改 Cookie](#修改-cookie)
7. [实战一：Cookie 注入实现免登录](#实战一cookie-注入实现免登录)
8. [实战二：导出 Cookie 供 requests 复用](#实战二导出-cookie-供-requests-复用)
9. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 操作 Cookie

在前端，操作 Cookie 最常用的方法是 `document.cookie`，但它有诸多限制：

| 功能 | `document.cookie` | CDP Cookie API |
|------|-------------------|----------------|
| 读取所有 Cookie | ✅ 仅当前域名 | ✅ **任意域名**（整个浏览器） |
| 设置 HttpOnly Cookie | ❌ 无法设置 | ✅ 完全支持 |
| 设置 SameSite 属性 | ⚠️ 有限支持 | ✅ 完整支持 |
| 读取 Secure 标志 | ❌ 无法读取 | ✅ 完全读取 |
| 按域名筛选 | ❌ 需自己解析 | ✅ 直接指定域名 |
| 跨域操作 | ❌ 同源限制 | ✅ 无限制 |
| 清空所有 Cookie | ❌ 只能逐条删 | ✅ 一键清空 |

简单说：**CDP 的 Cookie API 相当于浏览器的"管理员模式"**，没有同源策略限制，可以操作任意 Cookie。

---

## 前置准备：连接 Chrome

首先用 Python 连接 Chrome 的 CDP 端口：

```python
import asyncio
import websockets
import json

# CDP 连接地址（Chrome 需要 --remote-debugging-port=9222 启动）
CDP_URL = "ws://127.0.0.1:9222/devtools/browser/1a6114ab-..."

async def send_cdp_command(ws, cmd_id, method, params=None):
    """发送 CDP 命令并等待返回"""
    if params is None:
        params = {}
    await ws.send(json.dumps({"id": cmd_id, "method": method, "params": params}))
    async for msg in ws:
        resp = json.loads(msg)
        if resp.get("id") == cmd_id:
            return resp.get("result", {})


async def wait_response(ws, cmd_id):
    """等待指定 ID 的 CDP 响应"""
    async for msg in ws:
        resp = json.loads(msg)
        if resp.get("id") == cmd_id:
            return resp.get("result", {})

async def main():
    async with websockets.connect(CDP_URL) as ws:
        # 获取一个页面目标
        targets = await send_cdp_command(ws, 1, "Target.getTargets")
        target_id = targets["targetInfos"][0]["targetId"]
        
        # 附加到该页面
        session = await send_cdp_command(ws, 2, "Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = session["sessionId"]
        
        # 现在可以通过 sessionId 发命令了
        print(f"已连接到页面: {target_id}")
        
        # 接下来所有操作都经过这个 session
        # 格式：在命令参数中加 sessionId
        await ws.send(json.dumps({
            "sessionId": session_id,
            "id": 3,
            "method": "Network.getCookies",
            "params": {}
        }))

asyncio.run(main())
```

> 💡 **实用技巧**：如果你用的是 CloakBrowser 或自建 CDP 连接，建议封装一个 `CDPClient` 类，自动管理 sessionId 和命令 ID，后续例子会用这个简化写法。

---

## 读取 Cookie

### 读取所有 Cookie

```python
async def get_all_cookies(ws, session_id):
    """获取当前页面所有 Cookie"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 10,
        "method": "Network.getAllCookies",
        "params": {}
    }))
    resp = await wait_response(ws, 10)
    return resp.get("cookies", [])
```

返回示例：

```json
[
  {
    "name": "session_id",
    "value": "abc123xyz",
    "domain": ".example.com",
    "path": "/",
    "expires": 1776000000,
    "size": 24,
    "httpOnly": true,
    "secure": true,
    "session": false,
    "sameSite": "Lax",
    "priority": "Medium"
  }
]
```

### 按 URL 筛选 Cookie

只读取特定 URL 相关的 Cookie（更精确）：

```python
async def get_cookies_for_url(ws, session_id, urls):
    """获取指定 URL 的 Cookie（可传多个 URL）"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 11,
        "method": "Network.getCookies",
        "params": {"urls": urls}
    }))
    resp = await wait_response(ws, 11)
    return resp.get("cookies", [])

# 使用示例
cookies = await get_cookies_for_url(ws, session_id, 
    ["https://example.com", "https://api.example.com"]
)
```

### 使用 Storage 域读取

`Storage` 域也提供了类似方法，适合需要精确控制存储域的场景：

```python
async def get_cookies_storage(ws, session_id):
    """使用 Storage 域获取 Cookie"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 12,
        "method": "Storage.getCookies",
        "params": {}
    }))
    resp = await wait_response(ws, 12)
    return resp.get("cookies", [])
```

> **`Network` vs `Storage` 域的区别**：`Network.getCookies` 主要用于网络请求相关的 Cookie 读取，会带上浏览器当前的 Cookie 状态；`Storage.getCookies` 偏向存储层面。大部分场景用 `Network.getCookies` 就够了。

---

## 新增 Cookie

### 设置单个 Cookie

```python
async def set_cookie(ws, session_id, name, value, domain="", 
                      path="/", http_only=False, secure=False,
                      same_site="Lax", expires=None):
    """设置一个 Cookie"""
    params = {
        "name": name,
        "value": value,
        "domain": domain,
        "path": path,
        "httpOnly": http_only,
        "secure": secure,
        "sameSite": same_site,
    }
    if expires:
        params["expires"] = expires
    
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 20,
        "method": "Network.setCookie",
        "params": params
    }))
    resp = await wait_response(ws, 20)
    return resp.get("success", False)

# 使用示例
# 设置普通 Cookie
await set_cookie(ws, session_id, "user_pref", "dark_mode",
                 domain=".example.com")

# 设置 HttpOnly + Secure 的会话 Cookie
await set_cookie(ws, session_id, "session_id", "abc123",
                 domain=".example.com", http_only=True, 
                 secure=True, same_site="Strict")
```

### 批量设置 Cookie

```python
async def set_cookies_bulk(ws, session_id, cookies):
    """批量设置多个 Cookie"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 21,
        "method": "Network.setCookies",
        "params": {"cookies": cookies}
    }))
    resp = await wait_response(ws, 21)
    return resp  # 成功返回空对象 {}

# 使用示例
await set_cookies_bulk(ws, session_id, [
    {
        "name": "token",
        "value": "eyJhbGciOiJIUzI1NiJ9...",
        "domain": ".example.com",
        "path": "/",
        "httpOnly": True,
        "secure": True
    },
    {
        "name": "user_id",
        "value": "12345",
        "domain": ".example.com", 
        "path": "/"
    }
])
```

---

## 删除 Cookie

### 删除指定 Cookie

```python
async def delete_cookie(ws, session_id, name, domain="", path="/"):
    """删除指定的 Cookie"""
    params = {"name": name}
    if domain:
        params["domain"] = domain
    if path:
        params["path"] = path
    
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 30,
        "method": "Network.deleteCookies",
        "params": params
    }))
    return await wait_response(ws, 30)

# 删除指定 Cookie
await delete_cookie(ws, session_id, "session_id", 
                    domain=".example.com")
```

### 清空所有 Cookie

```python
async def clear_all_cookies(ws, session_id):
    """清空浏览器的所有 Cookie"""
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 31,
        "method": "Network.clearBrowserCookies",
        "params": {}
    }))
    return await wait_response(ws, 31)
```

> ⚠️ **注意**：`clearBrowserCookies` 会清空整个浏览器的所有 Cookie，不仅仅是当前标签页！生产脚本慎用。

---

## 修改 Cookie

CDP **没有**专门的"修改 Cookie"命令。实现修改的策略是：**删除旧 Cookie + 新增新 Cookie**。

```python
async def update_cookie(ws, session_id, old_name, new_name, new_value,
                         domain="", path="/"):
    """修改 Cookie（删除旧 + 创建新）"""
    # 1. 删除旧的
    params = {"name": old_name}
    if domain:
        params["domain"] = domain
    if path:
        params["path"] = path
    
    await ws.send(json.dumps({
        "sessionId": session_id, 
        "id": 40,
        "method": "Network.deleteCookies",
        "params": params
    }))
    await wait_response(ws, 40)
    
    # 2. 创建新的
    set_params = {
        "name": new_name,
        "value": new_value,
        "domain": domain or ".example.com",
        "path": path or "/"
    }
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": 41,
        "method": "Network.setCookie",
        "params": set_params
    }))
    return await wait_response(ws, 41)
```

---

## 实战一：Cookie 注入实现免登录

最实用的场景：从浏览器 A 导出登录态，注入到浏览器 B，实现免登录。

```python
async def export_login_state(ws_source, session_id_source):
    """导出登录态（所有 Cookie）"""
    cookies = await get_all_cookies(ws_source, session_id_source)
    # 过滤出关键登录 Cookie（不过滤也行，全部导出）
    login_cookies = [
        c for c in cookies 
        if c.get("name") in ("session_id", "token", "auth", "sid")
    ]
    return login_cookies or cookies  # 没找到指定名称就全量导出


async def import_login_state(ws_target, session_id_target, cookies):
    """导入登录态"""
    await set_cookies_bulk(ws_target, session_id_target, cookies)
    print(f"已注入 {len(cookies)} 个 Cookie")


async def cookie_login_flow():
    """完整的 Cookie 注入免登录流程"""
    # 源浏览器（已登录）
    async with websockets.connect("ws://127.0.0.1:9222/devtools/browser/...") as ws_a:
        session_a = await attach_to_page(ws_a)
        
        # 导航到目标网站
        await ws_a.send(json.dumps({
            "sessionId": session_a,
            "id": 100,
            "method": "Page.navigate",
            "params": {"url": "https://example.com/dashboard"}
        }))
        await wait_response(ws_a, 100)
        await asyncio.sleep(2)  # 等页面加载
        
        # 导出 Cookie
        cookies = await export_login_state(ws_a, session_a)
        print(f"导出 {len(cookies)} 个 Cookie")
    
    # 目标浏览器（新浏览器/未登录）
    async with websockets.connect("ws://127.0.0.1:9223/devtools/browser/...") as ws_b:
        session_b = await attach_to_page(ws_b)
        
        # 先注入 Cookie
        await import_login_state(ws_b, session_b, cookies)
        
        # 再导航（注入后再导航，Cookie 会自动带上）
        await ws_b.send(json.dumps({
            "sessionId": session_b,
            "id": 200,
            "method": "Page.navigate",
            "params": {"url": "https://example.com/dashboard"}
        }))
        await wait_response(ws_b, 200)
        
        # 此时页面已经处于登录状态！
        print("免登录成功！")
```

**执行顺序很关键**：必须先注入 Cookie，再导航到目标页面。如果先导航再注入，页面可能已经重定向到登录页了。

---

## 实战二：导出 Cookie 供 requests 复用

有时候我们想用 Python 的 `requests` 库来抓取数据，但目标网站有复杂的登录验证。可以用 CDP 先把 Cookie 导出来，喂给 requests：

```python
import requests

def cdp_cookies_to_requests_session(cdp_cookies):
    """将 CDP Cookie 格式转为 requests Session 可用格式"""
    session = requests.Session()
    for c in cdp_cookies:
        session.cookies.set(
            c["name"],
            c["value"],
            domain=c.get("domain", ""),
            path=c.get("path", "/")
        )
    return session


async def fetch_with_browser_cookies():
    """用浏览器 Cookie 发起 requests 请求"""
    # 1. 从浏览器获取 Cookie
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        cookies = await get_all_cookies(ws, session_id)
    
    # 2. 转换为 requests session
    session = cdp_cookies_to_requests_session(cookies)
    
    # 3. 用 session 发请求（自动带上 Cookie）
    resp = session.get("https://example.com/api/user/profile")
    print(f"状态码: {resp.status_code}")
    print(f"响应内容: {resp.text[:200]}")
```

这个模式特别适合：
- 需要登录后才能访问的 API 数据抓取
- 浏览器环境复杂（JS 渲染、验签等），但数据传输用 requests 更高效
- 不想在 Python 里重写整套登录逻辑的场景

---

## 常见踩坑与最佳实践

### 踩坑 1：Cookie 注入后不生效

```python
# ❌ 错误顺序：先导航，后注入
await navigate(ws, session_id, "https://example.com")
await set_cookies(ws, session_id, cookies)  # 页面已加载，注入太晚了

# ✅ 正确顺序：先注入，后导航
await set_cookies(ws, session_id, cookies)
await navigate(ws, session_id, "https://example.com")
```

### 踩坑 2：域名不匹配

CDP 设置 Cookie 时，`domain` 参数必须**以点开头**才能跨子域生效：

```python
# ❌ domain 写错了
await set_cookie(ws, session_id, "token", "xxx", domain="example.com")

# ✅ 正确的写法（点号前缀）
await set_cookie(ws, session_id, "token", "xxx", domain=".example.com")

# 带子域名
await set_cookie(ws, session_id, "token", "xxx", domain=".api.example.com")
```

### 踩坑 3：Secure 标志

通过 CDP 设置带 `secure: true` 的 Cookie 时，必须同时指定 URL 使用 HTTPS 协议。如果不在意协议，就不要设 `secure: true`：

```python
# ❌ HTTPS 页面设置 Secure Cookie 时 URL 没指定协议
# ✅ 非 HTTPS 场景别设 secure
await set_cookie(ws, session_id, "token", "xxx", 
                 domain=".example.com", secure=False)
```

### 踩坑 4：SameSite 策略

新版本的 Chrome 默认 SameSite=Lax。如果你需要在跨站请求中携带 Cookie，手动指定：

```python
# 跨站需要
await set_cookie(ws, session_id, "token", "xxx", 
                 same_site="None", secure=True)  # SameSite=None 必须配合 Secure

# 同站默认
await set_cookie(ws, session_id, "token", "xxx", 
                 same_site="Lax")  # 默认值，可不写
```

### 踩坑 5：批量设置时的过期时间

`expires` 字段是 Unix 时间戳（秒），注意不要用毫秒：

```python
import time

# ✅ 正确：秒级时间戳
expires_correct = int(time.time()) + 86400 * 30  # 30 天后过期

# ❌ 错误：毫秒级时间戳
expires_wrong = int(time.time() * 1000) + 86400 * 30 * 1000
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 注入顺序 | **先注入 Cookie，再导航到目标页面** |
| 域名格式 | 用 `.example.com`（点号开头）跨子域生效 |
| Secure 标志 | 非 HTTPS 页面不要设 `secure: true` |
| HttpOnly | CDP 可以读写 HttpOnly Cookie，这是 JS 做不到的 |
| 清空范围 | `clearBrowserCookies` 是全浏览器范围，慎用 |
| 调试 | 设置后用 `Network.getAllCookies` 确认写入成功 |

---

## 完整参考：CDP Cookie 操作类

为了方便复用，这里提供封装好的类，集成了本文所有操作：

```python
import asyncio
import json
import websockets


class CDPCookieManager:
    """CDP Cookie 管理器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
    async def _send(self, method, params=None):
        self._cmd_id += 1
        msg = {
            "sessionId": self.session_id,
            "id": self._cmd_id,
            "method": method,
            "params": params or {}
        }
        await self.ws.send(json.dumps(msg))
        # 等待响应
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def get_all(self):
        return (await self._send("Network.getAllCookies")).get("cookies", [])
    
    async def get_by_url(self, urls):
        return (await self._send("Network.getCookies", {"urls": urls})).get("cookies", [])
    
    async def set(self, name, value, **kwargs):
        params = {"name": name, "value": value, **kwargs}
        return (await self._send("Network.setCookie", params)).get("success", False)
    
    async def set_many(self, cookies):
        await self._send("Network.setCookies", {"cookies": cookies})
    
    async def delete(self, name, **kwargs):
        await self._send("Network.deleteCookies", {"name": name, **kwargs})
    
    async def clear_all(self):
        await self._send("Network.clearBrowserCookies")
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await attach_to_page(ws)
    mgr = CDPCookieManager(ws, session_id)
    
    # 读取所有 Cookie
    cookies = await mgr.get_all()
    print(f"当前有 {len(cookies)} 个 Cookie")
    
    # 新增
    await mgr.set("test_cookie", "hello_cdp", domain=".example.com")
    
    # 删除
    await mgr.delete("test_cookie", domain=".example.com")
```

---

> **总结**：CDP 的 Cookie API 让你拥有了浏览器级的管理权限——没有同源限制，支持 HttpOnly/Secure/SameSite 等完整属性，可以精确控制每个 Cookie 的生命周期。结合前几篇文章学的网络拦截和页面控制，你已经可以用 CDP 做出非常强大的浏览器自动化工具了。

---

*下一篇预告：CDP 监听 DOM 变化——实时追踪页面元素的新增、删除和修改。*
