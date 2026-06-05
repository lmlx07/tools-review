---
title: CloakBrowser 指南：开源指纹保护浏览器与 CDP 自动化集成
date: 2026-06-05 23:50:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - CloakBrowser
  - 浏览器指纹
  - 反检测
categories:
  - CDP 进阶
  - Python 实战
description: 详解 CloakBrowser——一个开源指纹保护浏览器，以及如何通过 CDP 协议与其集成实现自动化测试。
---

> **一句话总结**：CloakBrowser 是一款开源的 Chromium 指纹保护浏览器，通过修改指纹参数让每个实例看起来都像真实用户，结合 CDP 可构建强大的自动化测试基础设施。

---

## 目录

1. [什么是 CloakBrowser](#什么是-cloakbrowser)
2. [启动并开启远程调试](#启动并开启远程调试)
3. [获取 WebSocket URL](#获取-websocket-url)
4. [CDP 连接](#cdp-连接)
5. [实战：截屏](#实战截屏)
6. [实战：指纹对比](#实战指纹对比)
7. [实战：浏览器池](#实战浏览器池)
8. [CloakBrowserManager 参考类](#cloakbrowsermanager-参考类)
9. [最佳实践](#最佳实践)
10. [总结](#总结)

---

## 什么是 CloakBrowser

[CloakBrowser](https://github.com/CloakHQ/CloakBrowser) 是基于 Chromium 的开源指纹保护浏览器。核心定位：**让每个浏览器实例看起来都像真实的普通用户**，而非自动化工具。

### 为什么需要指纹保护

网站通过浏览器指纹（WebGL、Canvas、AudioContext、字体等）区分"真人"和"脚本"。指纹保护在以下场景至关重要：

- **自动化测试**：避免被 WebDriver 检测/Cloudflare 拦截，提高测试覆盖
- **网页采集**：绕开反爬系统的设备指纹识别
- **多账号管理**：在一台机器上创建多个独立浏览器身份

### 对比普通 Chrome

| 特性 | 普通 Chrome | CloakBrowser |
|------|------------|--------------|
| `navigator.webdriver` | `true`（自动化时） | `false` |
| WebGL 供应商 | 真实显卡 | 随机 |
| Canvas 指纹 | 设备唯一 | 每次随机 |
| WebRTC 泄露 | 可能 | 自动封锁 |
| 时区/语言 | 手动 | 自动匹配 |
| 开源 | 否 | 是 |

### 内置指纹保护

- **硬件**：WebGL 修改 `UNMASKED_VENDOR`/`UNMASKED_RENDERER`；Canvas 添加噪声；AudioContext 引入偏移；限制 `hardwareConcurrency`/`deviceMemory`
- **软件**：自动匹配 UA/平台/语言/时区；自定义字体集和分辨率
- **网络**：WebRTC 封锁 STUN；可配置 DoH；限制 JA3 可识别性

---

## 启动并开启远程调试

核心参数是 `--remote-debugging-port`：

```bash
"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe" ^
  --remote-debugging-port=9222 --remote-allow-origins=* ^
  --no-first-run --no-default-browser-check ^
  --user-data-dir="C:\Users\Lenovo\.cloakbrowser\user-data"
```

参数速查：

| 参数 | 作用 |
|------|------|
| `--remote-debugging-port=9222` | 开启 CDP 调试端口 |
| `--remote-allow-origins=*` | 允许所有来源连接 |
| `--no-first-run` | 跳过首次运行引导 |
| `--user-data-dir=...` | 持久化用户数据 |

### Python 启动

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

跨平台路径：

```python
def get_chrome():
    if sys.platform == "win32":
        return r"C:\Users\Lenovo\.cloakbrowser\chromium-146.0.7680.177.5\chrome.exe"
    if sys.platform == "darwin":
        return "/Applications/CloakBrowser.app/Contents/MacOS/CloakBrowser"
    return "/opt/cloakbrowser/chrome"
```

---

## 获取 WebSocket URL

```python
import json, urllib.request

def get_ws_url(host="127.0.0.1", port=9222):
    url = f"http://{host}:{port}/json/version"
    with urllib.request.urlopen(url, timeout=5) as r:
        return json.loads(r.read().decode())["webSocketDebuggerUrl"]
# => ws://127.0.0.1:9222/devtools/browser/...
```

端点对比：

| 端点 | 用途 |
|------|------|
| `/json/version` | 浏览器版本 + Browser WS URL |
| `/json` | 所有页面列表 + 各自 WS URL |
| `/json/new?url=about:blank` | 创建新标签页 |

多标签场景：

```python
def get_page_ws(host="127.0.0.1", port=9222):
    pages = json.loads(urllib.request.urlopen(f"http://{host}:{port}/json").read())
    return pages[0]["webSocketDebuggerUrl"] if pages else None
```

---

## CDP 连接

统一辅助函数，后续所有示例共用：

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

**session_id**：操作 iframe 时通过 `Target.attachToTarget` 获取，在后续命令中带上它。

---

## 实战：截屏

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

截图参数：`format` 支持 `png` 无损或 `jpeg` 有损；`quality` 仅 jpeg 有效；`fromSurface` 控制窗口/DOM；`clip` 可选区域 {x,y,width,height,scale}。

---

## 实战：指纹对比

通过 `Runtime.evaluate` 读取指纹，对比普通 Chrome 与 CloakBrowser：

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
    
    cw = await _c(9223); kw = await _c(9222)  # Chrome:9223, Cloak:9222
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

预期输出差异（`<<` 标注）：

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

CloakBrowser 隐藏了 `webdriver`，限制了硬件参数，伪装了 WebGL 和 Canvas。

---

## 实战：浏览器池

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

## CloakBrowserManager 参考类

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
                  "webgl_vendor":"Intel Inc.", "webgl_renderer":"Intel Iris",
                  "hardware_concurrency":8, "device_memory":4}
    
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

## 最佳实践

**持久化数据**：始终指定独立的 `--user-data-dir`，保留 Cookie 和缓存。

**端口管理**：多实例不能共用端口，用 socket 检测可用端口：

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

**进程清理**：异常退出后子进程可能残留，定期清理：

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

**指纹一致性**：同一目标每次用相同指纹，频繁变化反而触发风控：

```python
_reg = {}
def fp_for(domain):
    if domain not in _reg:
        import random
        _reg[domain] = {"seed": random.randint(1,10000)}
    return _reg[domain]
```

**连接重试**：CDP 可能断开，加入重试机制：

```python
async def retry(func, n=3, d=2):
    for i in range(n):
        try: return await func()
        except (websockets.ConnectionClosed, ConnectionError) as e:
            if i == n-1: raise
            await asyncio.sleep(d*(i+1))
```

---

## 总结

| 需求 | 实现方案 |
|------|---------|
| 隐藏 `navigator.webdriver` | CDP 注入 + CloakBrowser 内置 |
| 修改 WebGL/Canvas/音频指纹 | `Page.addScriptToEvaluateOnNewDocument` |
| 视口/屏幕参数 | `Emulation.setDeviceMetricsOverride` |
| 时区匹配 | `Emulation.setTimezoneOverride` |
| 多实例并发 | CloakBrowserManager 池 |
| 进程清理 | 信号处理 + psutil |

> **总结**：CloakBrowser 通过内置的 WebGL/Canvas/Audio 指纹修改、navigator.webdriver 隐藏、CDP 注入等机制组合来实现指纹保护，所有功能均在应用层用 Python + asyncio 实现，无需修改 Chromium 源码或依赖商业反检测产品。

**注意事项**：CloakBrowser 无法修改 TLS 层 JA3 指纹；启动路径需根据实际安装调整；生产环境建议配合 Docker 获得更好隔离。
