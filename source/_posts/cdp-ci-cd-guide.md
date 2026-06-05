---
title: CDP CI/CD 集成指南：用 Docker 部署浏览器自动化
date: 2026-06-05 20:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - CI/CD
  - Docker
  - GitHub Actions
  - 自动化测试
  - DevOps
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何将 CDP 浏览器自动化集成到 CI/CD 流程中。涵盖 Docker 化 Chrome/Chromium 配置、docker-compose 编排、GitHub Actions 集成、XVFB 虚拟显示、资源管理以及 Headless 与 Headful 模式选择。
---

> **一句话总结**：将 CDP 浏览器自动化部署到 CI/CD 环境的核心挑战是配置无头 Chrome、管理 Docker 资源、处理虚拟显示，而一旦这些基础设施就位，Python CDP 脚本就可以在流水线中无缝运行。

---

## 目录

1. [CI/CD 环境挑战总览](#cicd-环境挑战总览)
2. [Headless Chrome 配置](#headless-chrome-配置)
3. [Docker 化部署](#docker-化部署)
4. [Docker Compose 编排](#docker-compose-编排)
5. [GitHub Actions 集成](#github-actions-集成)
6. [XVFB 虚拟显示](#xvfb-虚拟显示)
7. [Headless vs Headful 模式](#headless-vs-headful-模式)
8. [健康检查与资源管理](#健康检查与资源管理)
9. [常见踩坑与最佳实践](#常见踩坑与最佳实践)
10. [完整参考：CDP CI/CD 部署类](#完整参考cdp-cicd-部署类)

---

## CI/CD 环境挑战总览

| 挑战 | 说明 | 解决方案 |
|------|------|---------|
| 无图形界面 | CI 无显示器 | Headless 模式或 XVFB |
| 浏览器安装 | 需要 Chromium 二进制 | Docker 容器化 |
| 资源限制 | CI 内存/CPU 有限 | 连接池与资源限制 |
| 稳定性 | 浏览器可能崩溃 | 健康检查与自动重启 |
| 并行性 | 多任务需隔离 | 每个会话独立容器 |

---

## Headless Chrome 配置

```python
import subprocess, time, json, os, asyncio, websockets, urllib.request

CDP_URL_TEMPLATE = "ws://127.0.0.1:{port}/devtools/browser/..."
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
    targets = await cdp(ws, "Target.getTargets")
    tid = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {"targetId": tid, "flatten": True})
    return session["sessionId"]


def find_chrome():
    """查找 Chrome/Chromium 可执行文件"""
    for p in ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/usr/bin/google-chrome-stable", "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"]:
        if os.path.exists(p):
            return p
    return os.environ.get("CHROME_PATH", "google-chrome")


def start_headless_chrome(port=9222):
    """启动 Headless Chrome"""
    args = [
        find_chrome(),
        "--headless=new", f"--remote-debugging-port={port}",
        "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check",
        "--disable-dev-shm-usage", "--disable-gpu", "--window-size=1920,1080",
        "--user-data-dir=/tmp/chrome-cdp-ci",
    ]
    if os.environ.get("CDP_NO_SANDBOX", "true").lower() in ("1","true"):
        args.append("--no-sandbox")
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return proc


def wait_for_chrome(port=9222, timeout=30):
    """等待 Chrome 远程调试端口就绪"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version", timeout=5)
            if resp.status == 200:
                data = json.loads(resp.read())
                print(f"Chrome 就绪: {data.get('Browser', 'unknown')}")
                return True
        except Exception:
            pass
        time.sleep(1)
    raise TimeoutError(f"Chrome 未在 {timeout} 秒内就绪")


async def setup_cdp(port=9222):
    """启动 Chrome 并返回 WebSocket 连接"""
    proc = start_headless_chrome(port)
    wait_for_chrome(port)
    resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json/version")
    cdp_url = json.loads(resp.read())["webSocketDebuggerUrl"]
    ws = await websockets.connect(cdp_url)
    session_id = await connect_page(ws)
    return proc, ws, session_id
```

---

## Docker 化部署

```dockerfile
# Dockerfile.cdp-automation
FROM python:3.11-slim
RUN apt-get update && apt-get install -y \
    chromium chromium-driver xvfb x11vnc \
    fonts-noto fonts-freefont-ttf curl procps \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scripts/ ./scripts/
RUN mkdir -p /tmp/chrome-data /tmp/screenshots /tmp/reports
ENV CHROME_HEADLESS=true CHROME_PORT=9222 CHROME_NO_SANDBOX=true DISPLAY=:99
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -s http://127.0.0.1:9222/json/version > /dev/null || exit 1
ENTRYPOINT ["python", "-m", "scripts.runner"]
```

```text
# requirements.txt
websockets>=12.0
aiohttp>=3.9.0
Pillow>=10.0.0
pytest>=7.0.0
pytest-asyncio>=0.21.0
```

### Entrypoint 脚本

```python
# scripts/runner.py - Docker 入口
import os, subprocess, time, json, signal, sys
CHROME_PORT, HEADLESS, DISP = int(os.environ.get("CHROME_PORT","9222")), \
    os.environ.get("CHROME_HEADLESS","true").lower()=="true", os.environ.get("DISPLAY",":99")

def start_xvfb():
    if not HEADLESS:
        p = subprocess.Popen(["Xvfb", DISP, "-screen", "0", "1920x1080x24", "-ac"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1); os.environ["DISPLAY"] = DISP; print(f"XVFB 已启动 ({DISP})"); return p

def start_chrome():
    args = [os.environ.get("CHROME_PATH","/usr/bin/chromium"),
            f"--remote-debugging-port={CHROME_PORT}", "--remote-allow-origins=*",
            "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage"]
    if HEADLESS: args.append("--headless=new")
    if os.environ.get("CHROME_NO_SANDBOX","true").lower() in ("1","true"): args.append("--no-sandbox")
    p = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Chrome 已启动 (PID:{p.pid})"); return p

# 主流程：启动 XVFB + Chrome，健康检查，信号处理
```

---

## Docker Compose 编排

```yaml
# docker-compose.yml
version: "3.8"
services:
  cdp-runner:
    build: {context: ., dockerfile: Dockerfile.cdp-automation}
    ports: ["9222:9222"]
    environment:
      - CHROME_HEADLESS=true
      - CHROME_PORT=9222
      - CHROME_NO_SANDBOX=true
      - CDP_MAX_SESSIONS=5
      - CDP_DEFAULT_TIMEOUT=30
      - TARGET_URL=https://example.com
    volumes:
      - ./reports:/app/reports
      - ./screenshots:/tmp/screenshots
    shm_size: "2gb"   # 共享内存，对 Chrome 至关重要
    deploy:
      resources: {limits: {cpus: "2", memory: "4g"}, reservations: {cpus: "1", memory: "2g"}}
    healthcheck:
      test: ["CMD", "curl", "-s", "http://127.0.0.1:9222/json/version"]
      interval: 30s; timeout: 10s; retries: 5; start_period: 10s

  cdp-worker:
    build: {context: ., dockerfile: Dockerfile.cdp-automation}
    depends_on: [cdp-runner]
    environment:
      - CDP_MASTER_URL=ws://cdp-runner:9222/devtools/browser/...
      - WORKER_ID=worker-1
    volumes: [./reports:/app/reports]
    deploy: {replicas: 3, resources: {limits: {cpus: "1", memory: "1g"}}}
```

---

## GitHub Actions 集成

```yaml
# .github/workflows/cdp-tests.yml
name: CDP Browser Automation Tests
on:
  push: {branches: [main, develop]}
  pull_request: {branches: [main]}
  schedule: [{cron: "0 6 * * *"}]

jobs:
  cdp-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: {python-version: "3.11", cache: "pip"}
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          sudo apt-get update && sudo apt-get install -y chromium-browser
      - name: Start Chrome
        run: python scripts/start_chrome.py & sleep 3
      - name: Verify Chrome
        run: curl -s http://127.0.0.1:9222/json/version
      - name: Run CDP tests
        env: {CHROME_PORT: 9222, CDP_DEFAULT_TIMEOUT: 60, TARGET_URL: "https://staging.example.com"}
        run: pytest tests/ --junitxml=reports/test-results.xml -v
      - name: Upload screenshots
        if: always()
        uses: actions/upload-artifact@v4
        with: {name: screenshots, path: /tmp/screenshots/}
      - name: Upload test reports
        if: always()
        uses: actions/upload-artifact@v4
        with: {name: test-reports, path: reports/}
      - name: Cleanup
        if: always()
        run: pkill -f chrome || true; pkill -f chromium || true
```

### Docker Compose 在 CI 中使用

```yaml
# .github/workflows/cdp-docker-tests.yml (片段)
jobs:
  docker-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - run: docker build -f Dockerfile.cdp-automation -t cdp-runner .
      - run: docker compose up -d
      - run: |
          for i in $(seq 1 10); do
            curl -s http://127.0.0.1:9222/json/version && break; sleep 3
          done
      - run: docker compose exec -T cdp-runner python -m pytest tests/ -v
      - if: always()
        run: docker compose down
```

---

## XVFB 虚拟显示

需要 Headful 模式（截图/视频录制）时在 Docker 中使用 XVFB：

```python
class XVFBManager:
    """XVFB 虚拟显示管理器"""
    def __init__(self, display=":99", resolution="1920x1080x24"):
        self.display, self.resolution = display, resolution
        self.process = None
    
    def start(self):
        import subprocess, time, os
        cmd = ["Xvfb", self.display, "-screen", "0", self.resolution, "-ac"]
        self.process = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ["DISPLAY"] = self.display
        time.sleep(1)
        print(f"XVFB 已启动: {self.display}")
    
    def stop(self):
        if self.process:
            self.process.terminate()
            try: self.process.wait(timeout=5)
            except: self.process.kill()
```

---

## Headless vs Headful 模式

| 模式 | 速度 | 内存 | 截图 | 视频 | 渲染 | 可检测 |
|------|------|------|------|------|------|--------|
| headless（旧） | 快 | 低 | 支持 | 不支持 | 部分 | 易检测 |
| headless=new（新） | 快 | 低 | 支持 | 不支持 | 完整 | 难检测 |
| headful + XVFB | 中等 | 中等 | 支持 | 支持 | 完整 | 不可检测 |

推荐选择：API 测试 / 数据提取 -> headless；视觉回归 / E2E -> new_headless；视频测试 / WebRTC -> headful

---

## 健康检查与资源管理

```python
class CDPHealthCheck:
    """CDP 浏览器健康检查"""
    def __init__(self, port=9222):
        self.port = port
        self.http_url = f"http://127.0.0.1:{port}"
    
    def check(self):
        """完整健康检查"""
        import urllib.request, json
        try:
            resp = urllib.request.urlopen(f"{self.http_url}/json/version", timeout=5)
            if resp.status == 200:
                data = json.loads(resp.read())
                print(f"浏览器: {data.get('Browser','?')}, 协议: {data.get('Protocol-Version','?')}")
                return True
        except Exception as e:
            print(f"健康检查失败: {e}")
        return False
    
    def wait_until_ready(self, timeout=30):
        """等待浏览器就绪"""
        import time
        start = time.time()
        while time.time() - start < timeout:
            if self.check():
                return True
            time.sleep(2)
        raise TimeoutError("浏览器未就绪")
```

### 自动重启机制

```python
async def auto_restart(port=9222, check_interval=30, max_retries=3):
    """健康检查失败时自动重启 Chrome"""
    import subprocess
    retries = 0
    check = CDPHealthCheck(port)
    while retries < max_retries:
        if check.check():
            retries = 0
        else:
            retries += 1
            print(f"重启 Chrome ({retries}/{max_retries})...")
            subprocess.run(["pkill","-f","chrome"], capture_output=True)
            subprocess.run(["pkill","-f","chromium"], capture_output=True)
            time.sleep(2)
            start_chrome()
            check.wait_until_ready()
            print("Chrome 已重启")
        await asyncio.sleep(check_interval)
```

---

## 常见踩坑与最佳实践

- **--disable-dev-shm-usage**：Docker 中 /dev/shm 默认仅 64MB，必须加此参数或在 compose 中设置 shm_size: 2gb
- **CI 磁盘清理**：Chrome 每次运行生成大量临时文件，测试完成后必须 `pkill -f chrome` + 清理 /tmp
- **GitHub Actions 资源限制**：免费运行器仅 2 核 / 7GB，不要单实例启动多个 Chrome
- **Headless 检测**：部分页面拒绝 Headless 访问，可用 --headless=new + 注入脚本绕过
- **XVFB 仅在需要时使用**：截图/视频才用 Headful，否则使用 Headless 节省资源

| 注意点 | 建议 |
|--------|------|
| 共享内存 | Docker 设置 shm_size: 2gb 或 --disable-dev-shm-usage |
| 资源清理 | 测试后杀进程、清临时目录 |
| 超时管理 | CDP 超时设 30-60 秒 |
| 重试机制 | 连接失败自动重试（最多 3 次）|
| 日志收集 | CDP 通信日志输出到 CI artifacts |

---

## 完整参考：CDP CI/CD 部署类

```python
import asyncio, json, os, subprocess, time, urllib.request, websockets


class CDPCIDeployer:
    """CDP CI/CD 部署管理器"""
    
    def __init__(self, port=9222, headless=True):
        self.port, self.headless = port, headless
        self.chrome_proc, self.xvfb_proc = None, None
        self.ws, self.sid = None, None
        self._cid = 0
    
    async def _cdp(self, method, params=None, sid=None):
        self._cid += 1
        msg = {"id": self._cid, "method": method, "params": params or {}}
        if sid or self.sid: msg["sessionId"] = sid or self.sid
        await self.ws.send(json.dumps(msg))
        async for r in self.ws:
            d = json.loads(r)
            if d.get("id") == self._cid:
                return d.get("result", {})
    
    def setup(self):
        if not self.headless:
            self.xvfb_proc = subprocess.Popen(
                ["Xvfb", ":99", "-screen", "0", "1920x1080x24", "-ac"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            os.environ["DISPLAY"] = ":99"
            time.sleep(1)
        
        args = [find_chrome(), f"--remote-debugging-port={self.port}",
                "--remote-allow-origins=*", "--no-first-run",
                "--no-default-browser-check", "--disable-dev-shm-usage"]
        if self.headless: args.append("--headless=new")
        if os.environ.get("CDP_NO_SANDBOX","true") in ("1","true"): args.append("--no-sandbox")
        
        self.chrome_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        start = time.time()
        while time.time() - start < 30:
            try:
                r = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version", timeout=5)
                if r.status == 200: break
            except: pass
            time.sleep(1)
    
    async def connect(self):
        r = urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json/version")
        url = json.loads(r.read())["webSocketDebuggerUrl"]
        self.ws = await websockets.connect(url)
        t = await self._cdp("Target.getTargets")
        s = await self._cdp("Target.attachToTarget", {"targetId": t["targetInfos"][0]["targetId"], "flatten": True})
        self.sid = s["sessionId"]
        print(f"已连接 CDP: {url}")
    
    async def run_test(self, url, test_func):
        await self._cdp("Page.navigate", {"url": url})
        await asyncio.sleep(2)
        return await test_func(self)
    
    async def screenshot(self, path=None):
        path = path or f"/tmp/screenshots/ss_{int(time.time())}.png"
        r = await self._cdp("Page.captureScreenshot", {"format": "png"})
        import base64
        with open(path, "wb") as f: f.write(base64.b64decode(r["data"]))
        return path
    
    def cleanup(self):
        if self.ws: asyncio.run_coroutine_threadsafe(self.ws.close(), asyncio.get_event_loop())
        for p in [self.chrome_proc, self.xvfb_proc]:
            if p:
                p.terminate()
                try: p.wait(timeout=5)
                except: p.kill()
        print("资源已清理")
    
    async def __aenter__(self):
        self.setup(); await self.connect(); return self
    
    async def __aexit__(self, *a): self.cleanup()
```

**使用示例：**

```python
async def my_test(deployer):
    r = await deployer._cdp("Runtime.evaluate", {"expression": "document.title", "returnByValue": True})
    title = r.get("result",{}).get("value","")
    await deployer.screenshot("result.png")
    return {"title": title, "success": True}

async def main():
    async with CDPCIDeployer() as d:
        result = await d.run_test("https://example.com", my_test)
        print(f"测试结果: {result}")

asyncio.run(main())
```

---

> **总结**：将 CDP 浏览器自动化集成到 CI/CD 需要综合考虑 Docker 容器化、Headless 模式配置、资源管理、健康检查和并行策略。通过合理的 Dockerfile 设计、docker-compose 编排和 GitHub Actions 配置，Python CDP 脚本可以在持续集成流水线中稳定运行。

---

*上一篇回顾：CDP Worker 调试指南：用 Python 调试 Web Workers。*

*下一篇预告：CDP 内存分析指南：用 Python 检测内存泄漏。*