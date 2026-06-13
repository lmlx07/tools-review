---
title: CDP 无头浏览器部署：服务器端自动化环境搭建
date: 2026-06-05 23:30:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Headless
  - 浏览器自动化
  - 部署
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何在服务器上部署 Headless Chrome 并通过 CDP 协议进行远程控制，涵盖启动配置、进程管理、虚拟显示与容器化部署。
---

> **一句话总结**：服务器端部署 Headless Chrome 的关键在于理解无头模式差异、合理配置启动参数、管理进程生命周期、通过 Xvfb 模拟显示环境，以及使用 Docker 实现容器化——所有这些基础设施就绪后，Python CDP 客户端就可以通过 WebSocket 远程操控浏览器。

---

## 目录

1. [无头模式详解](#无头模式详解)
2. [服务端启动参数全解析](#服务端启动参数全解析)
3. [进程生命周期管理](#进程生命周期管理)
4. [Xvfb 虚拟显示](#xvfb-虚拟显示)
5. [Docker 容器化部署](#docker-容器化部署)
6. [Docker Compose 编排](#docker-compose-编排)
7. [健康检查与自动重启](#健康检查与自动重启)
8. [多实例管理与资源限制](#多实例管理与资源限制)
9. [安全加固](#安全加固)
10. [完整参考：HeadlessChromeManager 类](#完整参考headlesschromemanager-类)

---

## 无头模式详解

Chrome 提供了三种无头运行模式，理解它们的差异是服务器端部署的第一步。

### 三种模式对比

```python
# CDP 工具函数（全文通用）
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
```

| 模式 | 启动参数 | 渲染引擎 | GPU 支持 | 扩展支持 | 截图质量 | 可检测性 |
|------|---------|---------|---------|---------|---------|---------|
| 旧无头 | `--headless` (旧版) | 无头渲染路径 | 有限 | 无 | 一般 | 易检测 |
| 新无头 | `--headless=new` | 完整 Blink 渲染 | 有 | 有 | 完整 | 难检测 |
| 真无头 | `--headless=chrome` | 完整 Chrome 渲染 | 无 | 有 | 完整 | 难检测 |

### 模式选择建议

- `--headless`（旧模式）：Chrome 96 之前的默认行为，渲染不完全，适合简单的 DOM 操作和数据抓取
- `--headless=new`（推荐）：Chrome 112+ 默认，使用完整渲染管线，截图质量与有头模式一致，适合大多数场景
- `--headless=chrome`：Chrome 120+ 引入，进一步对齐有头模式行为，适合需要最大限度接近真实浏览器的场景
- 不传 `--headless`：需要有头模式（需 Xvfb），适合需要完整浏览器功能（如 WebRTC、插件）的场景

```python
def resolve_headless_mode(mode="new"):
    """解析无头模式参数"""
    if mode == "old":
        return ["--headless"]
    elif mode == "new":
        return ["--headless=new"]
    elif mode == "chrome":
        return ["--headless=chrome"]
    elif mode == "none":
        return []  # 有头模式，需要 Xvfb
    else:
        raise ValueError(f"未知模式: {mode}")
```

---

## 服务端启动参数全解析

在服务器上运行 Chrome 需要一组特定的启动参数。以下是经过大量实践验证的参数组合。

### 核心参数集合

```python
def build_chrome_args(
    port=9222,
    headless_mode="new",
    user_data_dir="/tmp/chrome-data",
    window_size="1920,1080",
    disable_sandbox=True,
    disable_shm=True,
    disable_gpu=True,
    extra_args=None,
):
    """构建 Chrome 启动参数"""
    args = [
        find_chrome_path(),
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={window_size}",
    ]

    # 无头模式
    args.extend(resolve_headless_mode(headless_mode))

    # 服务器环境必须参数
    if disable_sandbox:
        args.append("--no-sandbox")
    if disable_shm:
        args.append("--disable-dev-shm-usage")
    if disable_gpu:
        args.append("--disable-gpu")

    # 稳定性参数
    args.extend([
        "--disable-background-networking",
        "--disable-background-timer-throttling",
        "--disable-backgrounding-occluded-windows",
        "--disable-breakpad",
        "--disable-component-update",
        "--disable-domain-reliability",
        "--disable-features=TranslateUI,ChromeWhatsNew",
        "--disable-hang-monitor",
        "--disable-ipc-flooding-protection",
        "--disable-popup-blocking",
        "--disable-prompt-on-repost",
        "--disable-sync",
        "--enable-features=NetworkService,NetworkServiceInProcess",
        "--force-color-profile=srgb",
        "--metrics-recording-only",
        "--mute-audio",
    ])

    if extra_args:
        args.extend(extra_args)

    return args
```

### 参数详解

| 参数 | 作用 | 为什么需要 |
|------|------|-----------|
| `--no-sandbox` | 关闭沙箱 | Docker/容器中无法使用沙箱 |
| `--disable-dev-shm-usage` | 禁用 `/dev/shm` | 容器默认共享内存仅 64MB |
| `--disable-gpu` | 禁用 GPU 加速 | 服务器通常无 GPU |
| `--remote-debugging-port` | 开启 CDP 端口 | 远程控制 Chrome 的唯一入口 |
| `--remote-allow-origins=*` | 允许任意来源连接 | 容器内跨容器访问 |
| `--no-first-run` | 跳过首次运行向导 | 避免弹窗阻塞启动 |
| `--disable-background-networking` | 禁用后台网络 | 减少不必要的流量 |
| `--mute-audio` | 静音音频 | 服务器无需音频输出 |
| `--disable-component-update` | 禁止组件更新 | 避免更新导致的意外重启 |

### 查找 Chrome 二进制文件

```python
import os


def find_chrome_path():
    """跨平台查找 Chrome/Chromium 路径"""
    candidates = [
        # Linux
        "/usr/bin/google-chrome",
        "/usr/bin/google-chrome-stable",
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser",
        "/snap/bin/chromium",
        # macOS
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        # Windows
        "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
        "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    ]

    # 环境变量优先
    env_path = os.environ.get("CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    for path in candidates:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            return expanded

    # 最后手段：让系统查找
    chrome_bin = os.environ.get("CHROME_PATH", "google-chrome")
    print(f"警告：未找到 Chrome，使用 '{chrome_bin}'")
    return chrome_bin
```

---

## 进程生命周期管理

服务器上 Chrome 实例需要精细的进程管理，包括启动、PID 追踪、优雅关闭和崩溃恢复。

### 启动与 PID 追踪

```python
import subprocess
import time
import os
import signal
import json
import urllib.request
from typing import Optional


class ChromeProcess:
    """Chrome 进程包装器"""

    def __init__(self, port=9222, args=None):
        self.port = port
        self.args = args or []
        self.proc: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.start_time: Optional[float] = None

    def start(self):
        """启动 Chrome 进程"""
        args = [find_chrome_path()] + self.args
        print(f"启动 Chrome: {' '.join(args)}")

        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,  # 进程组隔离
        )
        self.pid = self.proc.pid
        self.start_time = time.time()
        print(f"Chrome 已启动 (PID: {self.pid})")
        return self.pid

    def is_running(self):
        """检查进程是否存活"""
        if self.proc is None:
            return False
        return self.proc.poll() is None

    def wait_for_ready(self, timeout=30):
        """等待 Chrome 远程调试端口就绪"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/version", timeout=5
                )
                if resp.status == 200:
                    data = json.loads(resp.read())
                    print(f"Chrome 就绪: {data.get('Browser', '?')}")
                    return True
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError(f"Chrome 未在 {timeout} 秒内就绪 (PID: {self.pid})")

    def get_uptime(self):
        """获取运行时长（秒）"""
        if self.start_time is None:
            return 0
        return time.time() - self.start_time
```

### 优雅关闭

```python
def graceful_shutdown(proc: subprocess.Popen, timeout=10):
    """优雅关闭 Chrome 进程"""
    if proc is None or proc.poll() is not None:
        return

    pid = proc.pid
    print(f"关闭 Chrome (PID: {pid})...")

    try:
        # 第一步：发送 SIGTERM（Linux/macOS）
        if os.name != "nt":
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        else:
            proc.terminate()

        # 等待进程退出
        proc.wait(timeout=timeout)
        print(f"Chrome 已优雅关闭 (PID: {pid})")
    except subprocess.TimeoutExpired:
        # 超时后强制杀死
        print(f"优雅关闭超时，强制杀死 (PID: {pid})")
        if os.name != "nt":
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=5)
        print(f"Chrome 已强制关闭 (PID: {pid})")


def cleanup_chrome_processes(port=None):
    """清理残留的 Chrome 进程"""
    import psutil  # 可选依赖

    cleaned = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            name = proc.info.get("name") or ""
            is_chrome = "chrome" in name.lower() or "chromium" in name.lower()

            if is_chrome and "--remote-debugging-port" in str(cmdline):
                if port and f"--remote-debugging-port={port}" not in str(cmdline):
                    continue
                print(f"清理残留 Chrome (PID: {proc.info['pid']})")
                proc.terminate()
                cleaned += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(f"共清理 {cleaned} 个残留进程")
    return cleaned
```

### 子进程崩溃检测

```python
import asyncio


async def monitor_process(proc: subprocess.Popen, on_crash):
    """监控 Chrome 进程状态，崩溃时触发回调"""
    while True:
        ret = proc.poll()
        if ret is not None:
            print(f"Chrome 已退出，返回码: {ret}")
            await on_crash(ret)
            break
        await asyncio.sleep(1)
```

---

## Xvfb 虚拟显示

当需要使用有头模式（Headful）在无显示器的服务器上运行 Chrome 时，Xvfb（X Virtual Framebuffer）是标准解决方案。

### 安装 Xvfb

```bash
# Debian/Ubuntu
apt-get update && apt-get install -y xvfb x11-utils

# CentOS/RHEL/Fedora
yum install -y xorg-x11-server-Xvfb

# Alpine
apk add xvfb
```

### Xvfb 管理器

```python
import subprocess
import time
import os


class XvfbManager:
    """Xvfb 虚拟显示管理器"""

    def __init__(self, display=":99", resolution="1920x1080x24"):
        self.display = display
        self.resolution = resolution
        self.proc: subprocess.Popen = None

    def start(self):
        """启动 Xvfb"""
        if self.proc and self.proc.poll() is None:
            print(f"Xvfb {self.display} 已在运行")
            return

        cmd = ["Xvfb", self.display, "-screen", "0", self.resolution, "-ac"]
        print(f"启动 Xvfb: {' '.join(cmd)}")
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1)  # 等待就绪
        os.environ["DISPLAY"] = self.display
        print(f"Xvfb 已启动: {self.display}")

    def stop(self):
        """停止 Xvfb"""
        if self.proc is None:
            return

        print(f"关闭 Xvfb: {self.display}")
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
            print("Xvfb 已关闭")
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
            print("Xvfb 已强制关闭")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
```

### 组合使用：有头模式 + Xvfb

```python
def start_headful_chrome(port=9222, display=":99"):
    """通过 Xvfb 启动有头 Chrome"""
    # 1. 启动 Xvfb
    xvfb = XvfbManager(display=display)
    xvfb.start()

    # 2. 在虚拟显示中启动 Chrome（不传 --headless）
    args = build_chrome_args(
        port=port,
        headless_mode="none",  # 有头模式
    )
    os.environ["DISPLAY"] = display

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"有头 Chrome 已启动 (PID: {proc.pid}, DISPLAY: {display})")
    return xvfb, proc
```

---

## Docker 容器化部署

### Dockerfile 设计

```dockerfile
# Dockerfile.chrome-cdp
FROM python:3.11-slim

# 1. 安装 Chrome 和依赖
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    xvfb \
    x11vnc \
    fonts-noto \
    fonts-freefont-ttf \
    procps \
    # Chrome 安装
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 2. 安装 Python 依赖
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. 复制应用代码
COPY src/ ./src/
COPY scripts/ ./scripts/

# 4. 创建必要目录
RUN mkdir -p /tmp/chrome-data /tmp/xvfb /app/screenshots /app/reports

# 5. 环境变量
ENV CHROME_PATH=/usr/bin/google-chrome-stable \
    CHROME_PORT=9222 \
    CHROME_HEADLESS_MODE=new \
    CHROME_NO_SANDBOX=true \
    DISPLAY=:99 \
    CDP_AUTH_TOKEN="" \
    CDP_MAX_SESSIONS=5

# 6. 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -s http://127.0.0.1:${CHROME_PORT}/json/version > /dev/null || exit 1

# 7. 入口点
ENTRYPOINT ["python", "-m", "scripts.runner"]
```

### 精简版 Dockerfile（Alpine）

```dockerfile
# Dockerfile.chrome-cdp-alpine
FROM python:3.11-alpine

# 安装 Chromium（Alpine 仓库直接提供）
RUN apk add --no-cache \
    chromium \
    chromium-chromedriver \
    xvfb \
    xvfb-run \
    font-noto \
    curl \
    procps

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/ ./src/

ENV CHROME_PATH=/usr/bin/chromium-browser \
    CHROME_PORT=9222 \
    CHROME_HEADLESS_MODE=new \
    CHROME_NO_SANDBOX=true \
    DISPLAY=:99

HEALTHCHECK CMD curl -s http://127.0.0.1:9222/json/version || exit 1
CMD ["python", "-m", "src.server"]
```

### 依赖文件

```text
# requirements.txt
websockets>=12.0
aiohttp>=3.9.0
Pillow>=10.0.0
psutil>=5.9.0
```

### Docker Entrypoint 脚本

```python
# scripts/runner.py - Docker 入口
import os
import sys
import subprocess
import time
import signal
import json
import urllib.request

CHROME_PORT = int(os.environ.get("CHROME_PORT", "9222"))
HEADLESS_MODE = os.environ.get("CHROME_HEADLESS_MODE", "new")
NO_SANDBOX = os.environ.get("CHROME_NO_SANDBOX", "true").lower() in ("1", "true")
DISPLAY = os.environ.get("DISPLAY", ":99")
CHROME_PATH = os.environ.get("CHROME_PATH", "/usr/bin/google-chrome-stable")

xvfb_proc = None
chrome_proc = None


def setup_xvfb():
    """配置 Xvfb（仅在需要时）"""
    global xvfb_proc
    if HEADLESS_MODE.lower() in ("none", "false", "0"):
        cmd = ["Xvfb", DISPLAY, "-screen", "0", "1920x1080x24", "-ac"]
        xvfb_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ["DISPLAY"] = DISPLAY
        time.sleep(1)
        print(f"Xvfb 已启动: {DISPLAY}")


def start_chrome():
    """启动 Chrome"""
    global chrome_proc

    args = [CHROME_PATH]

    if HEADLESS_MODE.lower() in ("new", "old", "chrome"):
        args.append(f"--headless={HEADLESS_MODE}")
    elif HEADLESS_MODE.lower() == "true":
        args.append("--headless=new")  # 兼容旧配置

    args.extend([
        f"--remote-debugging-port={CHROME_PORT}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1920,1080",
        "--user-data-dir=/tmp/chrome-data",
    ])

    if NO_SANDBOX:
        args.append("--no-sandbox")

    chrome_proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Chrome 已启动 (PID: {chrome_proc.pid})")


def wait_chrome(timeout=30):
    """等待 Chrome 就绪"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{CHROME_PORT}/json/version", timeout=5)
            if r.status == 200:
                data = json.loads(r.read())
                print(f"Chrome 就绪: {data.get('Browser', '?')}")
                return True
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Chrome 未能在 {timeout} 秒内就绪")


def cleanup(signum=None, frame=None):
    """清理资源"""
    print("正在清理资源...")
    for proc in [chrome_proc, xvfb_proc]:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
    print("资源清理完成")


# 注册信号处理
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

if __name__ == "__main__":
    try:
        setup_xvfb()
        start_chrome()
        wait_chrome()
        print("Chrome CDP 服务已就绪", flush=True)

        # 保持容器运行
        while True:
            time.sleep(10)
            if chrome_proc.poll() is not None:
                print(f"Chrome 意外退出 (返回码: {chrome_proc.returncode})", flush=True)
                break
    except Exception as e:
        print(f"启动失败: {e}", flush=True)
        cleanup()
        sys.exit(1)
    except KeyboardInterrupt:
        cleanup()
```

---

## Docker Compose 编排

```yaml
# docker-compose.yml
version: "3.8"

services:
  # 主 CDP 服务实例
  cdp-chrome-1:
    build:
      context: .
      dockerfile: Dockerfile.chrome-cdp
    container_name: cdp-chrome-1
    ports:
      - "9222:9222"
    environment:
      - CHROME_HEADLESS_MODE=new
      - CHROME_PORT=9222
      - CHROME_NO_SANDBOX=true
      - CDP_AUTH_TOKEN=your-secret-token-here
      - CDP_MAX_SESSIONS=5
      - CDP_SESSION_TIMEOUT=300
    volumes:
      - chrome-data-1:/tmp/chrome-data
      - ./reports:/app/reports
      - ./screenshots:/app/screenshots
    shm_size: "2gb"
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: "4g"
        reservations:
          cpus: "1"
          memory: "2g"
    healthcheck:
      test: ["CMD", "curl", "-s", "http://127.0.0.1:9222/json/version"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 15s
    restart: unless-stopped
    logging:
      driver: "json-file"
      options:
        max-size: "10m"
        max-file: "3"

  # 第二 CDP 实例（不同端口）
  cdp-chrome-2:
    build:
      context: .
      dockerfile: Dockerfile.chrome-cdp
    container_name: cdp-chrome-2
    ports:
      - "9223:9222"  # 映射到不同主机端口
    environment:
      - CHROME_HEADLESS_MODE=new
      - CHROME_PORT=9222
      - CHROME_NO_SANDBOX=true
      - CDP_AUTH_TOKEN=your-secret-token-here
    volumes:
      - chrome-data-2:/tmp/chrome-data
    shm_size: "2gb"
    deploy:
      resources:
        limits:
          cpus: "2"
          memory: "4g"
    healthcheck:
      test: ["CMD", "curl", "-s", "http://127.0.0.1:9222/json/version"]
      interval: 30s
      timeout: 10s
      retries: 5
      start_period: 15s
    restart: unless-stopped

volumes:
  chrome-data-1:
  chrome-data-2:
```

---

## 健康检查与自动重启

### HTTP 层健康检查

```python
import urllib.request
import json
import time


class HealthChecker:
    """CDP 服务健康检查器"""

    def __init__(self, port=9222, host="127.0.0.1"):
        self.port = port
        self.host = host
        self.version_url = f"http://{host}:{port}/json/version"
        self.list_url = f"http://{host}:{port}/json"
        self.last_check = 0
        self.consecutive_failures = 0

    def check_basic(self):
        """基础健康检查：验证 /json/version 端点"""
        try:
            resp = urllib.request.urlopen(self.version_url, timeout=5)
            if resp.status != 200:
                return False, f"HTTP {resp.status}"

            data = json.loads(resp.read())
            browser = data.get("Browser", "?")
            protocol = data.get("Protocol-Version", "?")
            self.consecutive_failures = 0
            return True, {"browser": browser, "protocol": protocol}

        except Exception as e:
            self.consecutive_failures += 1
            return False, str(e)

    def check_deep(self):
        """深度健康检查：验证 WebSocket 可连接"""
        ok, info = self.check_basic()
        if not ok:
            return False, info

        try:
            resp = urllib.request.urlopen(self.list_url, timeout=5)
            targets = json.loads(resp.read())

            ws_urls = []
            for t in targets:
                if t.get("type") == "page" and t.get("webSocketDebuggerUrl"):
                    ws_urls.append(t["webSocketDebuggerUrl"])

            return True, {
                "browser": info["browser"],
                "targets": len(targets),
                "pages": len(ws_urls),
                "ws_endpoints": ws_urls[:3],  # 最多返回3个
            }

        except Exception as e:
            return False, f"深度检查失败: {e}"

    def get_stats(self):
        """获取 Chrome 运行统计"""
        try:
            resp = urllib.request.urlopen(self.list_url, timeout=5)
            targets = json.loads(resp.read())
            return {
                "total_targets": len(targets),
                "pages": sum(1 for t in targets if t.get("type") == "page"),
                "service_workers": sum(1 for t in targets if t.get("type") == "service_worker"),
                "connections": sum(1 for t in targets if t.get("type") == "shared_worker"),
                "uptime": time.time() - getattr(self, "_start_time", time.time()),
            }
        except Exception:
            return {}
```

### 自动重启控制器

```python
import asyncio
import subprocess


class AutoRestartController:
    """自动重启控制器"""

    def __init__(self, port=9222, max_retries=3, check_interval=30):
        self.port = port
        self.max_retries = max_retries
        self.check_interval = check_interval
        self.checker = HealthChecker(port)
        self.restart_count = 0
        self._running = False

    async def start_monitoring(self, start_func, stop_func):
        """开始监控循环"""
        self._running = True
        consecutive_errors = 0

        while self._running:
            await asyncio.sleep(self.check_interval)

            ok, info = self.checker.check_basic()
            if ok:
                consecutive_errors = 0
                continue

            consecutive_errors += 1
            print(f"健康检查失败 ({consecutive_errors}): {info}")

            if consecutive_errors >= 3:
                print(f"连续 {consecutive_errors} 次失败，执行重启...")
                await self._restart(start_func, stop_func)
                consecutive_errors = 0

    def stop_monitoring(self):
        """停止监控"""
        self._running = False

    async def _restart(self, start_func, stop_func):
        """执行重启流程"""
        self.restart_count += 1

        if self.restart_count > self.max_retries:
            print(f"重启次数超过上限 ({self.max_retries})，停止尝试")
            self._running = False
            return

        print(f"重启 #{self.restart_count}...")

        # 停止旧实例
        await stop_func()
        await asyncio.sleep(2)

        # 清理端口
        self._cleanup_port()

        # 启动新实例
        await start_func()
        print("重启完成")
```

---

## 多实例管理与资源限制

### 多实例端口分配器

```python
import socket


class PortAllocator:
    """动态端口分配器"""

    def __init__(self, base_port=9222, max_attempts=100):
        self.base_port = base_port
        self.max_attempts = max_attempts
        self._allocated = set()

    def find_free_port(self):
        """查找可用端口"""
        for offset in range(self.max_attempts):
            port = self.base_port + offset
            if port in self._allocated:
                continue
            if self._is_port_free(port):
                self._allocated.add(port)
                return port
        raise RuntimeError(f"无法在 {self.base_port}-{self.base_port + self.max_attempts} 范围内找到可用端口")

    def release_port(self, port):
        """释放端口"""
        self._allocated.discard(port)

    @staticmethod
    def _is_port_free(port):
        """检查端口是否可用"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) != 0
```

### 多实例管理器

```python
class InstanceManager:
    """多 Chrome 实例管理器"""

    def __init__(self, max_instances=5):
        self.max_instances = max_instances
        self.instances: dict[int, ChromeProcess] = {}  # port -> ChromeProcess
        self.allocator = PortAllocator()

    async def spawn_instance(self, headless_mode="new"):
        """创建新 Chrome 实例"""
        if len(self.instances) >= self.max_instances:
            raise RuntimeError(f"实例数已达上限 ({self.max_instances})")

        port = self.allocator.find_free_port()
        args = build_chrome_args(port=port, headless_mode=headless_mode)

        proc = ChromeProcess(port=port, args=args)
        proc.start()
        proc.wait_for_ready(timeout=30)

        self.instances[port] = proc
        print(f"实例已创建 (端口: {port}, PID: {proc.pid})")
        return port

    async def kill_instance(self, port):
        """终止指定实例"""
        proc = self.instances.pop(port, None)
        if proc is None:
            print(f"未找到端口 {port} 的实例")
            return

        graceful_shutdown(proc.proc)
        self.allocator.release_port(port)
        print(f"实例已终止 (端口: {port})")

    async def kill_all(self):
        """终止所有实例"""
        for port in list(self.instances.keys()):
            await self.kill_instance(port)
        print("所有实例已终止")

    def get_stats(self):
        """获取所有实例统计"""
        return {
            "total": len(self.instances),
            "max": self.max_instances,
            "instances": [
                {
                    "port": port,
                    "pid": proc.pid,
                    "uptime": proc.get_uptime(),
                    "running": proc.is_running(),
                }
                for port, proc in self.instances.items()
            ],
        }
```

### 资源限制配置

```python
import resource  # Unix only


def apply_resource_limits(cpu_limit=2, memory_mb=4096):
    """设置进程资源限制（仅 Linux）"""
    if os.name == "nt":
        print("Windows 不支持 resource 模块")
        return

    try:
        # CPU 时间限制（秒）
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit * 3600, cpu_limit * 3600))

        # 内存限制（字节）
        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

        # 文件描述符限制
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))

        print(f"资源限制已应用: CPU={cpu_limit}h, 内存={memory_mb}MB")
    except Exception as e:
        print(f"设置资源限制失败: {e}")
```

---

## 安全加固

将 Chrome CDP 服务暴露在网络上时，必须考虑以下安全措施。

### 认证令牌

```python
import hashlib
import hmac
import time


class CDPAuthMiddleware:
    """CDP 认证中间件"""

    def __init__(self, token: str):
        self.token = token

    def generate_auth_url(self, ws_url: str) -> str:
        """在 WebSocket URL 后附加认证令牌"""
        if "?" in ws_url:
            return f"{ws_url}&token={self.token}"
        return f"{ws_url}?token={self.token}"

    def verify_token(self, received_token: str) -> bool:
        """验证令牌"""
        return hmac.compare_digest(received_token, self.token)

    @staticmethod
    def generate_token(length=32):
        """生成随机令牌"""
        import secrets
        return secrets.token_hex(length)


class CDPProxy:
    """CDP 代理：保护底层 CDP 端口"""

    def __init__(self, listen_port=9443, target_port=9222, auth_token=None):
        self.listen_port = listen_port
        self.target_port = target_port
        self.auth_token = auth_token or CDPAuthMiddleware.generate_token()
        self._server = None

    async def start(self):
        """启动 CDP 代理（带认证）"""
        # 实际实现可使用 aiohttp 或 websockets 库
        # 示例：收到请求后验证 token，然后转发到真实 CDP 端口
        print(f"CDP 代理已启动: 0.0.0.0:{self.listen_port} -> 127.0.0.1:{self.target_port}")
        print(f"认证令牌: {self.auth_token}")
```

### 防火墙配置建议

```bash
# 仅允许本地回环访问 CDP 端口
iptables -A INPUT -p tcp --dport 9222 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 9222 -j DROP

# 如果使用代理端口（如 9443），仅允许应用服务器 IP
iptables -A INPUT -p tcp --dport 9443 -s 10.0.0.0/8 -j ACCEPT
iptables -A INPUT -p tcp --dport 9443 -s 172.16.0.0/12 -j ACCEPT
iptables -A INPUT -p tcp --dport 9443 -j DROP
```

### 网络安全清单

| 项目 | 措施 | 备注 |
|------|------|------|
| CDP 端口暴露 | 仅监听 127.0.0.1 | 必须通过代理暴露 |
| 认证机制 | 令牌认证 | 至少 32 字节随机令牌 |
| 传输加密 | HTTPS/WSS | 生产环境必须启用 |
| 网络隔离 | 内网 VPC | 勿暴露公网 |
| 日志审计 | 记录所有 CDP 连接 | 便于追踪异常 |
| 连接限制 | 单 IP 连接数限制 | 防止滥用 |
| 超时断开 | 空闲连接自动断开 | 默认 300 秒 |

---

## 完整参考：HeadlessChromeManager 类

```python
"""
headless_chrome_manager.py
完整的 Headless Chrome 管理器，覆盖启动、停止、重启、健康检查、多实例管理。

依赖：pip install websockets psutil
"""

import asyncio
import json
import os
import signal
import subprocess
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, Optional


@dataclass
class ChromeInstance:
    """单个 Chrome 实例的状态"""
    port: int
    pid: int
    process: subprocess.Popen
    start_time: float
    headless_mode: str
    xvfb_process: Optional[subprocess.Popen] = None
    session_count: int = 0
    last_health_check: float = 0.0
    healthy: bool = True


class HeadlessChromeManager:
    """
    Headless Chrome 管理器

    功能：
    - 启动/停止 Chrome 实例（支持多种无头模式）
    - 自动健康检查与重启
    - 多实例管理与端口分配
    - 资源使用追踪
    - 支持 Xvfb 有头模式
    """

    # CDP 工具方法
    CMD_ID = [0]

    @staticmethod
    async def cdp(ws, method, params=None, session_id=None):
        HeadlessChromeManager.CMD_ID[0] += 1
        msg = {"id": HeadlessChromeManager.CMD_ID[0], "method": method, "params": params or {}}
        if session_id:
            msg["sessionId"] = session_id
        await ws.send(json.dumps(msg))
        async for resp in ws:
            data = json.loads(resp)
            if data.get("id") == HeadlessChromeManager.CMD_ID[0]:
                return data.get("result", {})

    def __init__(
        self,
        headless_mode: str = "new",
        base_port: int = 9222,
        max_instances: int = 3,
        check_interval: int = 30,
        max_retries: int = 3,
        chrome_path: Optional[str] = None,
        auth_token: Optional[str] = None,
        user_data_dir: str = "/tmp/chrome-cdp-data",
    ):
        self.headless_mode = headless_mode
        self.base_port = base_port
        self.max_instances = max_instances
        self.check_interval = check_interval
        self.max_retries = max_retries
        self.chrome_path = chrome_path or find_chrome_path()
        self.auth_token = auth_token or ""
        self.user_data_dir = user_data_dir

        self.instances: dict[int, ChromeInstance] = {}
        self._running = False
        self._monitor_task: Optional[asyncio.Task] = None

        # 确保数据目录存在
        os.makedirs(user_data_dir, exist_ok=True)

    def _build_args(self, port: int, instance_dir: str) -> list:
        """构建单实例启动参数"""
        args = [
            self.chrome_path,
            f"--remote-debugging-port={port}",
            "--remote-allow-origins=*",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            f"--window-size=1920,1080",
            f"--user-data-dir={instance_dir}",
            "--disable-background-networking",
            "--disable-background-timer-throttling",
            "--disable-breakpad",
            "--disable-component-update",
            "--disable-sync",
            "--mute-audio",
            "--force-color-profile=srgb",
        ]

        # 无头模式
        if self.headless_mode and self.headless_mode.lower() != "none":
            args.append(f"--headless={self.headless_mode}")

        # 沙箱
        if os.environ.get("CHROME_NO_SANDBOX", "true").lower() in ("1", "true"):
            args.append("--no-sandbox")

        return args

    async def start_instance(self, port: Optional[int] = None, xvfb: bool = False) -> int:
        """启动一个新的 Chrome 实例"""
        if len(self.instances) >= self.max_instances:
            raise RuntimeError(f"已达到最大实例数 ({self.max_instances})")

        port = port or self._find_free_port()
        instance_dir = os.path.join(self.user_data_dir, f"instance-{port}")

        xvfb_proc = None
        if xvfb and self.headless_mode.lower() == "none":
            # 启动 Xvfb
            display = f":{port - self.base_port + 99}"
            xvfb_proc = subprocess.Popen(
                ["Xvfb", display, "-screen", "0", "1920x1080x24", "-ac"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = display
            await asyncio.sleep(1)

        # 启动 Chrome
        args = self._build_args(port, instance_dir)
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )

        # 等待就绪
        await self._wait_for_port(port)

        instance = ChromeInstance(
            port=port,
            pid=proc.pid,
            process=proc,
            start_time=time.time(),
            headless_mode=self.headless_mode,
            xvfb_process=xvfb_proc,
        )
        self.instances[port] = instance
        print(f"[{port}] 实例已启动 (PID: {proc.pid})")
        return port

    async def stop_instance(self, port: int):
        """停止指定实例"""
        instance = self.instances.pop(port, None)
        if not instance:
            print(f"[{port}] 实例不存在")
            return

        # 关闭 Chrome
        self._graceful_kill(instance.process)

        # 关闭 Xvfb
        if instance.xvfb_process:
            self._graceful_kill(instance.xvfb_process)

        print(f"[{port}] 实例已停止 (运行时长: {time.time() - instance.start_time:.1f}s)")

    async def stop_all(self):
        """停止所有实例"""
        for port in list(self.instances.keys()):
            await self.stop_instance(port)
        print("所有实例已停止")

    async def restart_instance(self, port: int, xvfb: bool = False):
        """重启指定实例"""
        print(f"[{port}] 正在重启...")
        await self.stop_instance(port)
        await asyncio.sleep(2)
        await self.start_instance(port=port, xvfb=xvfb)
        print(f"[{port}] 重启完成")

    async def health_check(self, port: int) -> bool:
        """检查单个实例健康状态"""
        instance = self.instances.get(port)
        if not instance:
            return False

        try:
            resp = urllib.request.urlopen(
                f"http://127.0.0.1:{port}/json/version", timeout=5
            )
            if resp.status == 200:
                data = json.loads(resp.read())
                instance.healthy = True
                instance.last_health_check = time.time()
                instance.session_count = self._count_sessions(port)
                return True
        except Exception:
            pass

        instance.healthy = False
        return False

    async def start_monitoring(self):
        """启动后台健康监控"""
        self._running = True
        retries = {}

        while self._running:
            await asyncio.sleep(self.check_interval)

            for port in list(self.instances.keys()):
                if not await self.health_check(port):
                    retries[port] = retries.get(port, 0) + 1
                    print(f"[{port}] 健康检查失败 ({retries[port]}/{self.max_retries})")

                    if retries[port] >= self.max_retries:
                        print(f"[{port}] 达到最大重试次数，自动重启")
                        await self.restart_instance(port)
                        retries[port] = 0
                else:
                    retries[port] = 0

    def stop_monitoring(self):
        """停止健康监控"""
        self._running = False

    def get_stats(self) -> dict:
        """获取所有实例的统计信息"""
        return {
            "total_instances": len(self.instances),
            "max_instances": self.max_instances,
            "headless_mode": self.headless_mode,
            "chrome_path": self.chrome_path,
            "auth_enabled": bool(self.auth_token),
            "instances": [
                {
                    "port": inst.port,
                    "pid": inst.pid,
                    "uptime": time.time() - inst.start_time,
                    "healthy": inst.healthy,
                    "sessions": inst.session_count,
                    "xvfb": inst.xvfb_process is not None,
                }
                for inst in sorted(self.instances.values(), key=lambda i: i.port)
            ],
        }

    def _find_free_port(self) -> int:
        """查找可用端口"""
        import socket
        for offset in range(100):
            port = self.base_port + offset
            if port not in self.instances:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("127.0.0.1", port)) != 0:
                        return port
        raise RuntimeError("无法找到可用端口")

    @staticmethod
    async def _wait_for_port(port: int, timeout: int = 30):
        """等待端口就绪"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{port}/json/version", timeout=5
                )
                if resp.status == 200:
                    return
            except Exception:
                pass
            await asyncio.sleep(1)
        raise TimeoutError(f"端口 {port} 未在 {timeout} 秒内就绪")

    @staticmethod
    def _count_sessions(port: int) -> int:
        """统计当前会话数"""
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3)
            return len(json.loads(resp.read()))
        except Exception:
            return 0

    @staticmethod
    def _graceful_kill(proc: subprocess.Popen):
        """优雅杀死进程"""
        if proc is None or proc.poll() is not None:
            return

        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    async def __aenter__(self):
        """上下文管理器入口"""
        return self

    async def __aexit__(self, *args):
        """上下文管理器退出"""
        self.stop_monitoring()
        await self.stop_all()
```

### 使用示例

```python
async def main():
    """使用 HeadlessChromeManager 的完整示例"""
    async with HeadlessChromeManager(
        headless_mode="new",
        base_port=9222,
        max_instances=3,
        check_interval=30,
    ) as manager:

        # 启动两个实例
        port1 = await manager.start_instance()
        port2 = await manager.start_instance()

        print("启动的实例端口:", port1, port2)

        # 获取统计
        stats = manager.get_stats()
        print(f"实例数: {stats['total_instances']}")

        # 启动健康监控
        monitor = asyncio.create_task(manager.start_monitoring())

        # ... 执行业务逻辑 ...
        await asyncio.sleep(60)

        # 停止监控
        manager.stop_monitoring()
        monitor.cancel()

        # 自动清理在 __aexit__ 中完成
        print("清理完成")


# asyncio.run(main())
```

---

> **总结**：在服务器上部署 Headless Chrome CDP 服务需要系统化地处理无头模式选择、启动参数配置、进程生命周期管理、虚拟显示、容器化部署、健康检查与自动重启、多实例资源管理以及安全加固等多个方面。`HeadlessChromeManager` 类提供了一个完整的解决方案，涵盖了从单实例管理到多实例池的全部需求。结合 Docker 容器化部署，这套基础设施可以支撑生产级的浏览器自动化服务。
