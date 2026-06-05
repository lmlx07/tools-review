---
lang: en
title: "CloakBrowser Guide: Open-Source Fingerprint Protection Browser & CDP Integration"
date: "2026-06-05 23:50:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - CloakBrowser
  - Browser Fingerprinting
  - Anti-Detection
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to CloakBrowser — an open-source fingerprint protection browser, and how to integrate it with CDP for automated testing.
---

> **One sentence summary**: CloakBrowser is an open-source Chromium-based browser focused on fingerprint protection. Combined with the CDP protocol, you can build powerful automated testing and web scraping infrastructure that looks like real user traffic.

---

## Table of Contents

1. [What is CloakBrowser](#what-is-cloakbrowser)
2. [Starting with Remote Debugging](#starting-with-remote-debugging)
3. [Getting the WebSocket URL](#getting-the-websocket-url)
4. [CDP Connection](#cdp-connection)
5. [Tutorial: Screenshot](#tutorial-screenshot)
6. [Tutorial: Fingerprint Comparison](#tutorial-fingerprint-comparison)
7. [Tutorial: Browser Pool](#tutorial-browser-pool)
8. [CloakBrowserManager Reference Class](#cloakbrowsermanager-reference-class)
9. [Best Practices](#best-practices)
10. [Summary](#summary)

---

## What is CloakBrowser

[CloakBrowser](https://github.com/CloakHQ/CloakBrowser) is an open-source Chromium-based browser for **fingerprint protection** and **anti-detection**. Core mission: **making every browser instance look like a real normal user**, not an automation tool.

### Why It Matters

Websites use fingerprints (WebGL, Canvas, AudioContext, fonts, etc.) to distinguish humans from bots. Fingerprint protection is critical for:

- **Automated testing**: Avoid WebDriver detection and Cloudflare blocks
- **Web scraping**: Bypass anti-bot device fingerprinting
- **Multi-account management**: Create independent browser identities on one machine

### vs Regular Chrome

| Feature | Regular Chrome | CloakBrowser |
|---------|---------------|--------------|
| `navigator.webdriver` | `true` (automated) | `false` |
| WebGL vendor | Real GPU | Randomized |
| Canvas fingerprint | Device-unique | Random per session |
| WebRTC leak | May leak | Blocked |
| Timezone/language | Manual | Auto-matched |
| Open source | No | Yes |

### Protection Mechanisms

- **Hardware**: WebGL spoofs `UNMASKED_VENDOR`/`UNMASKED_RENDERER`; Canvas adds noise; AudioContext offsets; capped `hardwareConcurrency`/`deviceMemory`
- **Software**: Auto-matched UA/platform/language/timezone; custom fonts and resolution
- **Network**: WebRTC STUN blocking; configurable DoH; limited JA3 variability

---

## Starting with Remote Debugging

Launch with `--remote-debugging-port` to enable CDP:

```bash
"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe" ^
  --remote-debugging-port=9222 --remote-allow-origins=* ^
  --no-first-run --no-default-browser-check ^
  --user-data-dir="C:\Users\Lenovo\.cloakbrowser\user-data"
```

| Parameter | Purpose |
|-----------|---------|
| `--remote-debugging-port=9222` | Opens CDP debug port |
| `--remote-allow-origins=*` | Allows any origin |
| `--no-first-run` | Skips first-run wizard |
| `--user-data-dir=...` | Persists user data |

### Python Launcher

```python
import subprocess, time, sys

def start_cloak(port=9222, data_dir=None):
    chrome = r"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"
    if not data_dir:
        data_dir = r"C:\Users\Lenovo\.cloakbrowser\user-data"
    proc = subprocess.Popen([
        chrome, f"--remote-debugging-port={port}",
        "--remote-allow-origins=*", "--no-first-run",
        "--no-default-browser-check", f"--user-data-dir={data_dir}",
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(2)
    return proc
```

Cross-platform paths:

```python
def get_chrome():
    if sys.platform == "win32":
        return r"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"
    if sys.platform == "darwin":
        return "/Applications/CloakBrowser.app/Contents/MacOS/CloakBrowser"
    return "/opt/cloakbrowser/chrome"
```

---

## Getting the WebSocket URL

```python
import json, urllib.request

def get_ws_url(host="127.0.0.1", port=9222):
    url = f"http://{host}:{port}/json/version"
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode())["webSocketDebuggerUrl"]
# => ws://127.0.0.1:9222/devtools/browser/...
```

| Endpoint | Purpose |
|----------|---------|
| `/json/version` | Browser version + WS URL |
| `/json` | All pages + their WS URLs |
| `/json/new?url=about:blank` | Create new tab |

For multi-tab:

```python
def get_page_ws(host="127.0.0.1", port=9222):
    pages = json.loads(urllib.request.urlopen(f"http://{host}:{port}/json").read())
    return pages[0]["webSocketDebuggerUrl"] if pages else None
```

---

## CDP Connection

Unified helper, shared by all examples below:

```python
import asyncio, json, websockets

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

async def connect_cloak(host="127.0.0.1", port=9222):
    ws = await websockets.connect(get_ws_url(host, port), max_size=2**24)
    await cdp(ws, "Page.enable")
    await cdp(ws, "Runtime.enable")
    return ws

async def main():
    ws = await connect_cloak()
    ver = await cdp(ws, "Browser.getVersion")
    print(f"Browser: {ver.get('product')}")
    await ws.close()

asyncio.run(main())
```

**session_id**: For iframe interactions, obtain via `Target.attachToTarget` and include in subsequent commands.

---

## Tutorial: Screenshot

```python
import asyncio, json, base64, urllib.request, websockets

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1
    msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id: msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]: return data.get("result", {})

async def screenshot_demo():
    ws_url = json.loads(urllib.request.urlopen(
        "http://127.0.0.1:9222/json/version").read())["webSocketDebuggerUrl"]
    ws = await websockets.connect(ws_url, max_size=2**24)
    await cdp(ws, "Page.enable")
    await cdp(ws, "Page.navigate", {"url": "https://example.com"})
    await asyncio.sleep(3)
    result = await cdp(ws, "Page.captureScreenshot", {"format": "png"})
    with open("cloak_screenshot.png", "wb") as f:
        f.write(base64.b64decode(result["data"]))
    await ws.close()

asyncio.run(screenshot_demo())
```

Parameters: `format` = `png` (lossless) or `jpeg` (lossy); `quality` for jpeg (0-100); `fromSurface` for window vs DOM; `clip` for region {x,y,width,height,scale}.

---

## Tutorial: Fingerprint Comparison

Read fingerprint properties via `Runtime.evaluate` to compare Chrome vs CloakBrowser:

```python
async def js(ws, expr):
    r = await cdp(ws, "Runtime.evaluate",
        {"expression": expr, "returnByValue": True})
    return r.get("result", {}).get("value")

async def compare():
    def _c(port):
        d = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{port}/json/version").read())
        return websockets.connect(d["webSocketDebuggerUrl"], max_size=2**24)
    
    cw = await _c(9223); kw = await _c(9222)
    for w in (cw, kw):
        await cdp(w, "Page.enable")
        await cdp(w, "Page.navigate", {"url": "about:blank"})
    await asyncio.sleep(1)
    
    props = {
        "webdriver":"navigator.webdriver",
        "platform":"navigator.platform",
        "hwConcurrency":"navigator.hardwareConcurrency",
        "deviceMemory":"navigator.deviceMemory",
        "plugins.len":"navigator.plugins.length",
        "WebGL":"(()=>{const c=document.createElement('canvas');"
                "const g=c.getContext('webgl')||c.getContext('experimental-webgl');"
                "const e=g.getExtension('WEBGL_debug_renderer_info');"
                "return e?g.getParameter(e.UNMASKED_VENDOR_WEBGL):'N/A';})()",
        "Canvas":"(()=>{const c=document.createElement('canvas');c.width=200;c.height=50;"
                 "const x=c.getContext('2d');x.textBaseline='top';x.font='14px Arial';"
                 "x.fillText('CDP',2,2);return c.toDataURL().substring(0,80);})()",
    }
    print(f"{'Key':<16} {'Chrome':<35} {'CloakBrowser':<35}")
    print("-"*86)
    for k, e in props.items():
        cv, kv = str(await js(cw, e))[:32], str(await js(kw, e))[:32]
        d = " <<" if cv != kv else ""
        print(f"{k:<16} {cv:<35} {kv:<35}{d}")
    await cw.close(); await kw.close()

asyncio.run(compare())
```

Expected output (`<<` marks differences):

```
Key              Chrome                            CloakBrowser
------------------------------------------------------------------------------------------
webdriver        true                              false                             <<
platform         Win32                             Win32
hwConcurrency    12                                8                                 <<
deviceMemory     8                                 4                                 <<
plugins.len      0                                 3                                 <<
WebGL            Intel(R) Iris(R) Xe               Intel Inc.                        <<
Canvas           data:image/png;base64,A           data:image/png;base64,B           <<
```

CloakBrowser hides `webdriver`, caps hardware params, and spoofs WebGL/Canvas.

---

## Tutorial: Browser Pool

```python
import asyncio, subprocess, time, urllib.request, websockets, json, base64

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1; msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id: msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]: return data.get("result", {})

class CloakInstance:
    def __init__(self, port, profile, chrome):
        self.port, self.profile, self.chrome = port, profile, chrome
        self.proc, self.ws = None, None
    
    def start(self):
        self.proc = subprocess.Popen([
            self.chrome, f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*", "--no-first-run",
            "--no-default-browser-check", f"--user-data-dir={self.profile}",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        return self
    
    async def connect(self):
        d = json.loads(urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/json/version").read())
        self.ws = await websockets.connect(d["webSocketDebuggerUrl"], max_size=2**24)
        await cdp(self.ws, "Page.enable")
        return self
    
    async def snap(self, url, path):
        await cdp(self.ws, "Page.navigate", {"url": url})
        await asyncio.sleep(3)
        r = await cdp(self.ws, "Page.captureScreenshot", {"format": "png"})
        with open(path, "wb") as f: f.write(base64.b64decode(r["data"]))
        print(f"[{self.port}] {path}")
    
    async def close(self):
        if self.ws: await self.ws.close()
        if self.proc:
            self.proc.terminate(); self.proc.wait(timeout=5)

async def pool_demo():
    chrome = r"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"
    pool = [CloakInstance(9222+i, rf"C:\Users\Lenovo\.cloakbrowser\p{i}", chrome) for i in range(3)]
    for p in pool: p.start(); await p.connect()
    await asyncio.gather(*[p.snap("https://example.com",f"s{i}.png") for i,p in enumerate(pool)])
    for p in pool: await p.close()

asyncio.run(pool_demo())
```

---

## CloakBrowserManager Reference Class

```python
import asyncio, json, subprocess, time, urllib.request, base64, os, signal, sys, websockets

CMD_ID = [0]
async def cdp(ws, method, params=None, session_id=None):
    CMD_ID[0] += 1; msg = {"id": CMD_ID[0], "method": method, "params": params or {}}
    if session_id: msg["sessionId"] = session_id
    await ws.send(json.dumps(msg))
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == CMD_ID[0]: return data.get("result", {})

class CloakBrowserManager:
    """Complete CloakBrowser manager: launch, pool, fingerprint, cleanup."""
    
    PATHS = {"win32": [r"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"],
             "darwin": ["/Applications/CloakBrowser.app/Contents/MacOS/CloakBrowser"],
             "linux": ["/opt/cloakbrowser/chrome"]}
    
    DEFAULT_FP = {"viewport": {"width":1920,"height":1080,"scale":1},
                  "timezone":"Asia/Shanghai","locale":"zh-CN",
                  "webgl_vendor":"Intel Inc.","webgl_renderer":"Intel Iris",
                  "hardware_concurrency":8,"device_memory":4}
    
    def __init__(self, chrome_path=None, base_port=9222):
        self.chrome = chrome_path or self._find()
        self.instances = {}; self._next = base_port
    
    def _find(self):
        for p in self.PATHS.get(sys.platform, []):
            if os.path.exists(p): return p
        raise FileNotFoundError("CloakBrowser not found")
    
    async def spawn(self, name=None, fp=None):
        port = self._next; self._next += 1
        name = name or f"p{port}"
        dp = os.path.join(os.path.dirname(self.chrome), "profiles", name)
        os.makedirs(dp, exist_ok=True)
        proc = subprocess.Popen([
            self.chrome, f"--remote-debugging-port={port}",
            "--remote-allow-origins=*","--no-first-run","--no-default-browser-check",
            f"--user-data-dir={dp}","--disable-sync","--disable-background-networking",
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
        ws = await websockets.connect(
            json.loads(urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version").read())["webSocketDebuggerUrl"],
            max_size=2**24)
        await cdp(ws, "Page.enable"); await cdp(ws, "Runtime.enable")
        await self._apply_fp(ws, fp or self.DEFAULT_FP)
        self.instances[port] = {"proc": proc, "ws": ws}
        print(f"[Mgr] Spawned {port} ({name})")
        return ws, port
    
    async def _apply_fp(self, ws, fp):
        vp = fp.get("viewport", {})
        await cdp(ws, "Emulation.setDeviceMetricsOverride",
            {"width":vp.get("width",1920),"height":vp.get("height",1080),
             "deviceScaleFactor":vp.get("scale",1),"mobile":False,
             "screenWidth":vp.get("width",1920),"screenHeight":vp.get("height",1080)})
        if "timezone" in fp:
            await cdp(ws, "Emulation.setTimezoneOverride", {"timezoneId":fp["timezone"]})
        if "user_agent" in fp:
            await cdp(ws, "Emulation.setUserAgentOverride",
                {"userAgent":fp["user_agent"],"platform":fp.get("platform","Win32")})
        loc = fp.get("locale","zh-CN")
        await cdp(ws, "Page.addScriptToEvaluateOnNewDocument", {"source":f"""
            Object.defineProperty(navigator,'webdriver',{{get:()=>undefined}});
            Object.defineProperties(navigator,{{language:{{get:()=>'{loc}'}},
                languages:{{get:()=>['{loc}','en','en-US']}},
                hardwareConcurrency:{{get:()=>{fp.get('hardware_concurrency',8)}}},
                deviceMemory:{{get:()=>{fp.get('device_memory',4)}}}}});
            if(WebGLRenderingContext){{const _p=WebGLRenderingContext.prototype.getParameter;
                WebGLRenderingContext.prototype.getParameter=function(p){{
                if(p===0x9245)return'{fp.get("webgl_vendor","Intel Inc.")}';
                if(p===0x9246)return'{fp.get("webgl_renderer","Intel Iris")}';
                if(p===0x1F00)return'WebKit';if(p===0x1F01)return'WebKit WebGL';
                return _p.call(this,p);}};}}
            if(navigator.plugins.length===0){{const p=[
                {{name:'Chrome PDF Plugin',filename:'internal-pdf-viewer'}},
                {{name:'Chrome PDF Viewer',filename:'mhjfbmdgcfjbbpaeojofohoefgiehjai'}},
                {{name:'Native Client',filename:'internal-nacl-plugin'}}];
                p.item=i=>p[i];p.namedItem=n=>p.find(x=>x.name===n);
                Object.defineProperty(navigator,'plugins',{{get:()=>p}});}}
        """})
    
    async def snap(self, ws, path):
        r = await cdp(ws, "Page.captureScreenshot", {"format":"png"})
        with open(path, "wb") as f: f.write(base64.b64decode(r["data"]))
    
    async def kill(self, port=None):
        targets = [port] if port else list(self.instances.keys())
        for p in targets:
            inst = self.instances.pop(p, None)
            if not inst: continue
            try: await inst["ws"].close()
            except: pass
            if inst["proc"]:
                try:
                    inst["proc"].terminate(); inst["proc"].wait(timeout=5)
                except: inst["proc"].kill(); inst["proc"].wait()
            print(f"[Mgr] Killed {p}")
    
    @property
    def count(self): return len(self.instances)
    
    async def __aenter__(self): return self
    async def __aexit__(self, *a): await self.kill()


async def demo():
    async with CloakBrowserManager() as mgr:
        w1, _ = await mgr.spawn("demo-1", {
            "viewport":{"width":1920,"height":1080},"timezone":"Asia/Shanghai",
            "locale":"zh-CN","platform":"Win32","webgl_vendor":"Intel Inc.",
            "user_agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"})
        w2, _ = await mgr.spawn("demo-2", {
            "viewport":{"width":1440,"height":900,"scale":2},"timezone":"America/New_York",
            "locale":"en-US","platform":"MacIntel","webgl_vendor":"Apple Inc.",
            "user_agent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"})
        print(f"Active: {mgr.count}")
        for w, u, fn in [(w1,"https://www.baidu.com","baidu.png"),
                          (w2,"https://www.google.com","google.png")]:
            await cdp(w, "Page.navigate", {"url": u}); await asyncio.sleep(2)
            await mgr.snap(w, fn)

asyncio.run(demo())
```

---

## Best Practices

**Persistent data**: Always set a dedicated `--user-data-dir` to preserve cookies and cache.

**Port management**: Instances can't share ports. Scan for free ones:

```python
import socket
def free_ports(base=9222, n=1):
    ports, p = [], base
    while len(ports) < n:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", p)): ports.append(p)
        p += 1
    return ports
```

**Process cleanup**: Zombie child processes may remain after crashes:

```python
import psutil
def cleanup():
    for p in psutil.process_iter(["pid","name","cmdline"]):
        try:
            c = " ".join(p.info.get("cmdline") or [])
            if "cloakbrowser" in c.lower() or (
                "chrome" in p.info.get("name","").lower()
                and "--remote-debugging-port" in c):
                p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied): pass
```

**Fingerprint consistency**: Same target, same fingerprint. Changes trigger risk alerts:

```python
_reg = {}
def fp_for(domain):
    if domain not in _reg:
        import random
        _reg[domain] = {"seed": random.randint(1,10000)}
    return _reg[domain]
```

**Connection retry**: CDP connections can drop. Add retry:

```python
async def retry(func, n=3, d=2):
    for i in range(n):
        try: return await func()
        except (websockets.ConnectionClosed, ConnectionError) as e:
            if i == n-1: raise
            await asyncio.sleep(d*(i+1))
```

---

## Summary

| Requirement | Solution |
|-------------|----------|
| Hide `navigator.webdriver` | CDP injection + CloakBrowser built-in |
| Modify WebGL/Canvas/Audio fingerprints | `Page.addScriptToEvaluateOnNewDocument` |
| Viewport/screen parameters | `Emulation.setDeviceMetricsOverride` |
| Timezone matching | `Emulation.setTimezoneOverride` |
| Multi-instance concurrency | CloakBrowserManager pool |
| Process cleanup | Signal handling + psutil |

> **Summary**: CloakBrowser combines built-in WebGL/Canvas/Audio fingerprint spoofing, navigator.webdriver hiding, and CDP injection to deliver fingerprint protection. All functionality is implemented at the application layer with Python + asyncio, without requiring Chromium source modifications or commercial anti-detection products.

**Caveats**: CloakBrowser cannot modify TLS-layer JA3 fingerprints; paths need adjustment for your installation; use Docker for better isolation in production.
