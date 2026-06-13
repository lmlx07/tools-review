---
lang: en
title: "The Complete Guide to CDP Cookie Operations: CRUD with Python & Auto-Login"
date: "2026-06-05 10:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Browser Automation
  - Cookie
  - Web Scraping
categories:
  - CDP Basics
  - Python Practice
description: A comprehensive guide to manipulating browser cookies using Chrome DevTools Protocol (CDP). Learn how to read all cookies, filter by domain, set new cookies, delete specific cookies, clear all cookies, inject cookies for auto-login, and export cookies for use with the Python requests library.
---

> **Summary in one sentence**: CDP provides a much more powerful Cookie API than JavaScript's `document.cookie` — you can read cookies from any domain, set cookies with full flag support, precisely delete individual cookies, and even clear the entire browser's cookie jar at once.

---

## Table of Contents

1. [Why Use CDP for Cookie Operations](#why-use-cdp-for-cookie-operations)
2. [Prerequisites: Connecting to Chrome](#prerequisites-connecting-to-chrome)
3. [Reading Cookies](#reading-cookies)
4. [Setting Cookies](#setting-cookies)
5. [Deleting Cookies](#deleting-cookies)
6. [Modifying Cookies](#modifying-cookies)
7. [Practical Example 1: Cookie Injection for Auto-Login](#practical-example-1-cookie-injection-for-auto-login)
8. [Practical Example 2: Exporting Cookies for requests](#practical-example-2-exporting-cookies-for-requests)
9. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Cookie Operations

In frontend JavaScript, the most common way to handle cookies is via `document.cookie`, but it has many limitations:

| Feature | `document.cookie` | CDP Cookie API |
|---------|-------------------|----------------|
| Read all cookies | ✅ Current domain only | ✅ **Any domain** (entire browser) |
| Set HttpOnly cookies | ❌ Cannot set | ✅ Full support |
| Set SameSite attribute | ⚠️ Limited support | ✅ Full support |
| Read Secure flag | ❌ Cannot read | ✅ Full read |
| Filter by domain | ❌ Must parse manually | ✅ Direct domain parameter |
| Cross-origin access | ❌ Same-origin only | ✅ No restrictions |
| Clear all cookies | ❌ Must delete one by one | ✅ One-shot clear |

In short: **CDP's Cookie API is the browser's "admin mode"** — no same-origin policy restrictions, full access to all cookies.

---

## Prerequisites: Connecting to Chrome

First, connect to Chrome's CDP port using Python:

```python
import asyncio, json, websockets

# CDP connection URL (Chrome must start with --remote-debugging-port=9222)
CDP_URL = "ws://127.0.0.1:9222/devtools/browser/1a6114ab-..."

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    """Send CDP command and wait for result"""
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
    """Connect to a page target and return session_id"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id,
        "flatten": True
    })
    return session["sessionId"]

async def main():
    async with websockets.connect(CDP_URL) as ws:
        # Get a page target
        targets = await cdp(ws, "Target.getTargets")
        target_id = targets["targetInfos"][0]["targetId"]
        
        # Attach to the page
        session = await cdp(ws, "Target.attachToTarget", {
            "targetId": target_id,
            "flatten": True
        })
        session_id = session["sessionId"]
        
        # Now we can send commands through this session
        print(f"Connected to page: {target_id}")
        
        # All subsequent operations go through this session
        cookies = await cdp(ws, "Network.getCookies", session_id=session_id)
        print(f"Found {len(cookies.get('cookies', []))} cookies")

asyncio.run(main())
```

> 💡 **Pro tip**: If you're using CloakBrowser or your own CDP setup, consider wrapping a `CDPClient` class to manage sessionId and command IDs automatically. The following examples use a simplified notation.

---

## Reading Cookies

### Read All Cookies

```python
async def get_all_cookies(ws, session_id):
    """Get all cookies from the current page"""
    resp = await cdp(ws, "Network.getAllCookies", session_id=session_id)
    return resp.get("cookies", [])
```

Sample response:

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

### Filter Cookies by URL

Read cookies specific to certain URLs:

```python
async def get_cookies_for_url(ws, session_id, urls):
    """Get cookies for specific URLs (can pass multiple URLs)"""
    resp = await cdp(ws, "Network.getCookies", {"urls": urls}, session_id)
    return resp.get("cookies", [])

# Usage
cookies = await get_cookies_for_url(ws, session_id, 
    ["https://example.com", "https://api.example.com"]
)
```

### Using the Storage Domain

The `Storage` domain also provides cookie access, useful when you need more precise storage control:

```python
async def get_cookies_storage(ws, session_id):
    """Get cookies using the Storage domain"""
    resp = await cdp(ws, "Storage.getCookies", session_id=session_id)
    return resp.get("cookies", [])
```

> **`Network` vs `Storage` domain**: `Network.getCookies` reads cookies related to network requests (the browser's current cookie state); `Storage.getCookies` is storage-layer oriented. For most use cases, `Network.getCookies` is sufficient.

---

## Setting Cookies

### Set a Single Cookie

```python
async def set_cookie(ws, session_id, name, value, domain="",
                      path="/", http_only=False, secure=False,
                      same_site="Lax", expires=None):
    """Set a single cookie"""
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
    
    resp = await cdp(ws, "Network.setCookie", params, session_id)
    return resp.get("success", False)

# Usage examples
# Normal cookie
await set_cookie(ws, session_id, "user_pref", "dark_mode",
                 domain=".example.com")

# HttpOnly + Secure session cookie
await set_cookie(ws, session_id, "session_id", "abc123",
                 domain=".example.com", http_only=True,
                 secure=True, same_site="Strict")
```

### Set Multiple Cookies at Once

```python
async def set_cookies_bulk(ws, session_id, cookies):
    """Set multiple cookies in one call"""
    resp = await cdp(ws, "Network.setCookies", {"cookies": cookies}, session_id)
    return resp  # Returns empty object {} on success

# Usage
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

## Deleting Cookies

### Delete a Specific Cookie

```python
async def delete_cookie(ws, session_id, name, domain="", path="/"):
    """Delete a specific cookie by name"""
    params = {"name": name}
    if domain:
        params["domain"] = domain
    if path:
        params["path"] = path
    
    return await cdp(ws, "Network.deleteCookies", params, session_id)

# Delete a specific cookie
await delete_cookie(ws, session_id, "session_id",
                    domain=".example.com")
```

### Clear All Cookies

```python
async def clear_all_cookies(ws, session_id):
    """Clear ALL browser cookies"""
    return await cdp(ws, "Network.clearBrowserCookies", session_id=session_id)
```

> ⚠️ **Warning**: `clearBrowserCookies` clears ALL cookies in the entire browser, not just the current tab! Use with caution in production scripts.

---

## Modifying Cookies

CDP does **not** have a dedicated "modify cookie" command. The strategy is: **delete old cookie + create new cookie**.

```python
async def update_cookie(ws, session_id, old_name, new_name, new_value,
                         domain="", path="/"):
    """Update a cookie (delete old + create new)"""
    # 1. Delete the old one
    params = {"name": old_name}
    if domain:
        params["domain"] = domain
    if path:
        params["path"] = path
    
    await cdp(ws, "Network.deleteCookies", params, session_id)
    
    # 2. Create the new one
    set_params = {
        "name": new_name,
        "value": new_value,
        "domain": domain or ".example.com",
        "path": path or "/"
    }
    return await cdp(ws, "Network.setCookie", set_params, session_id)
```

---

## Practical Example 1: Cookie Injection for Auto-Login

The most practical scenario: export login state from browser A and inject it into browser B for auto-login.

```python
async def export_login_state(ws_source, session_id_source):
    """Export login state (all cookies)"""
    cookies = await get_all_cookies(ws_source, session_id_source)
    # Filter for login-related cookies (or export all if not found)
    login_cookies = [
        c for c in cookies
        if c.get("name") in ("session_id", "token", "auth", "sid")
    ]
    return login_cookies or cookies


async def import_login_state(ws_target, session_id_target, cookies):
    """Import cookies into another browser"""
    await set_cookies_bulk(ws_target, session_id_target, cookies)
    print(f"Injected {len(cookies)} cookies")


async def cookie_login_flow():
    """Complete cookie injection auto-login flow"""
    # Source browser (already logged in)
    async with websockets.connect("ws://127.0.0.1:9222/devtools/browser/...") as ws_a:
        session_a = await attach_to_page(ws_a)
        
        # Navigate to target site
        await cdp(ws_a, "Page.navigate", {"url": "https://example.com/dashboard"}, session_a)
        await asyncio.sleep(2)  # Wait for page load
        
        # Export cookies
        cookies = await export_login_state(ws_a, session_a)
        print(f"Exported {len(cookies)} cookies")
    
    # Target browser (new browser / not logged in)
    async with websockets.connect("ws://127.0.0.1:9223/devtools/browser/...") as ws_b:
        session_b = await attach_to_page(ws_b)
        
        # Inject cookies FIRST
        await import_login_state(ws_b, session_b, cookies)
        
        # Then navigate (cookies are automatically sent with the request)
        await cdp(ws_b, "Page.navigate", {"url": "https://example.com/dashboard"}, session_b)
        
        # The page is now logged in!
        print("Auto-login successful!")
```

**Order matters**: You must inject cookies **before** navigating to the target page. If you navigate first and inject later, the page may have already redirected to the login page.

---

## Practical Example 2: Exporting Cookies for requests

Sometimes you want to use Python's `requests` library for data fetching, but the target site has complex authentication. Use CDP to export cookies and feed them to requests:

```python
import requests

def cdp_cookies_to_requests_session(cdp_cookies):
    """Convert CDP cookie format to a requests Session"""
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
    """Make requests using browser cookies"""
    # 1. Get cookies from browser
    async with websockets.connect(CDP_URL) as ws:
        session_id = await attach_to_page(ws)
        cookies = await get_all_cookies(ws, session_id)
    
    # 2. Convert to requests session
    session = cdp_cookies_to_requests_session(cookies)
    
    # 3. Make requests (cookies are sent automatically)
    resp = session.get("https://example.com/api/user/profile")
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.text[:200]}")
```

This pattern is especially useful for:
- Scraping APIs that require login
- Scenarios where the browser handles complex JS rendering/signing, but you want to use requests for efficient data extraction
- Avoiding re-implementing the entire login flow in Python

---

## Common Pitfalls & Best Practices

### Pitfall 1: Cookie Injection Order

```python
# ❌ Wrong: navigate first, then inject
await navigate(ws, session_id, "https://example.com")
await set_cookies(ws, session_id, cookies)  # Page already loaded, too late

# ✅ Correct: inject first, then navigate
await set_cookies(ws, session_id, cookies)
await navigate(ws, session_id, "https://example.com")
```

### Pitfall 2: Domain Mismatch

When setting cookies via CDP, the `domain` parameter must start with a **dot** to work across subdomains:

```python
# ❌ Wrong domain format
await set_cookie(ws, session_id, "token", "xxx", domain="example.com")

# ✅ Correct format (dot prefix)
await set_cookie(ws, session_id, "token", "xxx", domain=".example.com")

# With subdomain
await set_cookie(ws, session_id, "token", "xxx", domain=".api.example.com")
```

### Pitfall 3: Secure Flag

When setting a cookie with `secure: true` via CDP, you must be on an HTTPS page. If protocol doesn't matter, don't set `secure: true`:

```python
# Non-HTTPS scenario: don't set secure
await set_cookie(ws, session_id, "token", "xxx",
                 domain=".example.com", secure=False)
```

### Pitfall 4: SameSite Policy

Modern Chrome defaults to SameSite=Lax. If you need cross-site cookie delivery, be explicit:

```python
# Cross-site needs
await set_cookie(ws, session_id, "token", "xxx",
                 same_site="None", secure=True)  # SameSite=None requires Secure

# Same-site default  
await set_cookie(ws, session_id, "token", "xxx",
                 same_site="Lax")  # Default, can omit
```

### Pitfall 5: Expiry Timestamp Format

The `expires` field uses Unix timestamp in **seconds**, not milliseconds:

```python
import time

# ✅ Correct: seconds
expires_correct = int(time.time()) + 86400 * 30  # 30 days from now

# ❌ Wrong: milliseconds
expires_wrong = int(time.time() * 1000) + 86400 * 30 * 1000
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|---------------|
| Injection order | **Inject cookies first, then navigate** |
| Domain format | Use `.example.com` (dot prefix) for cross-subdomain |
| Secure flag | Don't set `secure: true` on non-HTTPS pages |
| HttpOnly | CDP can read/write HttpOnly cookies (unlike JS) |
| Clear scope | `clearBrowserCookies` is browser-wide — use with caution |
| Debugging | Verify with `Network.getAllCookies` after setting |

---

## Complete Reference: CDP Cookie Manager Class

Here's a reusable class that bundles all operations from this article:

```python
import asyncio
import json
import websockets


class CDPCookieManager:
    """CDP Cookie Manager"""
    
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

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await attach_to_page(ws)
    mgr = CDPCookieManager(ws, session_id)
    
    # Read all cookies
    cookies = await mgr.get_all()
    print(f"Found {len(cookies)} cookies")
    
    # Set a new cookie
    await mgr.set("test_cookie", "hello_cdp", domain=".example.com")
    
    # Delete
    await mgr.delete("test_cookie", domain=".example.com")
```

---

> **Summary**: CDP's Cookie API gives you browser-level admin privileges — no same-origin restrictions, full support for HttpOnly/Secure/SameSite attributes, and precise control over each cookie's lifecycle. Combined with the network interception and page control techniques from previous articles, you now have the building blocks for extremely powerful browser automation tools.

---





*Previous: CDP Performance Tracking and Lighthouse Integration: Measuring Web Vitals and Automating Performance Auditing with Python*

*Next up: The Complete Guide to CDP DOM Operations: Real-Time Observation & Manipulation with Python*