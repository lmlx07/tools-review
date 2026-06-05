---
lang: en
title: "CDP Headless Browser Deployment: Server-Side Automation Setup"
date: "2026-06-05 23:30:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Headless
  - Browser Automation
  - Deployment
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to deploying Headless Chrome on servers and controlling it via CDP, covering startup configuration, process management, virtual display, and containerized deployment.
---

> **Summary in one sentence**: Deploying Headless Chrome on a server boils down to understanding headless mode differences, configuring startup flags correctly, managing process lifecycles, simulating a display with Xvfb, and containerizing with Docker — once these layers are in place, your Python CDP client can drive the browser remotely via WebSocket.

---

## Table of Contents

1. [Headless Mode Deep Dive](#headless-mode-deep-dive)
2. [Complete Server Startup Flags](#complete-server-startup-flags)
3. [Process Lifecycle Management](#process-lifecycle-management)
4. [Xvfb Virtual Display](#xvfb-virtual-display)
5. [Docker Containerization](#docker-containerization)
6. [Docker Compose Orchestration](#docker-compose-orchestration)
7. [Health Checks & Auto-Restart](#health-checks--auto-restart)
8. [Multi-Instance Management & Resource Limits](#multi-instance-management--resource-limits)
9. [Security Hardening](#security-hardening)
10. [Complete Reference: HeadlessChromeManager Class](#complete-reference-headlesschromemanager-class)

---

## Headless Mode Deep Dive

Chrome offers three distinct headless running modes, each with different rendering capabilities. Understanding these differences is the first step in server-side deployment.

### The Three Modes

```python
# CDP helper utility (used throughout this article)
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

| Mode | Flag | Rendering | GPU Accel | Extensions | Screenshot | Detectable |
|------|------|-----------|-----------|------------|------------|------------|
| Old Headless | `--headless` | Limited headless path | Minimal | No | Fair | Easy |
| New Headless | `--headless=new` | Full Blink renderer | Yes | Yes | Full | Hard |
| True Headless | `--headless=chrome` | Full Chrome renderer | No | Yes | Full | Hard |

### Mode Selection Guide

- `--headless` (old mode): Default before Chrome 96. Incomplete rendering. Suitable for simple DOM operations and data scraping.
- `--headless=new` (recommended): Default since Chrome 112. Uses the full rendering pipeline. Screenshot quality matches headed mode. Best for most scenarios.
- `--headless=chrome`: Introduced in Chrome 120. Further aligns with headed behavior. Choose this when you need maximum proximity to a real browser environment.
- Omit `--headless`: Requires a real display (or Xvfb). Use when you need full browser capabilities like WebRTC or extensions.

```python
def resolve_headless_mode(mode="new"):
    """Resolve headless mode flag"""
    if mode == "old":
        return ["--headless"]
    elif mode == "new":
        return ["--headless=new"]
    elif mode == "chrome":
        return ["--headless=chrome"]
    elif mode == "none":
        return []  # Headed mode, requires Xvfb
    else:
        raise ValueError(f"Unknown mode: {mode}")
```

---

## Complete Server Startup Flags

Running Chrome on a server requires a specific set of startup flags hardened through years of production experience.

### Core Flag Set

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
    """Build Chrome startup arguments"""
    args = [
        find_chrome_path(),
        f"--remote-debugging-port={port}",
        "--remote-allow-origins=*",
        "--no-first-run",
        "--no-default-browser-check",
        f"--user-data-dir={user_data_dir}",
        f"--window-size={window_size}",
    ]

    # Headless mode
    args.extend(resolve_headless_mode(headless_mode))

    # Server-mandatory flags
    if disable_sandbox:
        args.append("--no-sandbox")
    if disable_shm:
        args.append("--disable-dev-shm-usage")
    if disable_gpu:
        args.append("--disable-gpu")

    # Stability flags
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

### Flag Reference

| Flag | Purpose | Why It's Needed |
|------|---------|-----------------|
| `--no-sandbox` | Disable sandbox | Sandboxing unavailable in Docker/containers |
| `--disable-dev-shm-usage` | Bypass `/dev/shm` | Container shared memory is only 64MB by default |
| `--disable-gpu` | Disable GPU acceleration | Servers typically have no GPU |
| `--remote-debugging-port` | Enable CDP port | The sole entry point for remote Chrome control |
| `--remote-allow-origins=*` | Allow any origin | Cross-container access within Docker network |
| `--no-first-run` | Skip first-run wizard | Prevents dialog blocking startup |
| `--disable-background-networking` | Kill background traffic | Reduces unnecessary network requests |
| `--mute-audio` | Mute audio output | No audio output needed on servers |
| `--disable-component-update` | Block component updates | Prevents unexpected restarts from auto-updates |

### Locating the Chrome Binary

```python
import os


def find_chrome_path():
    """Cross-platform Chrome/Chromium path discovery"""
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

    # Environment variable takes priority
    env_path = os.environ.get("CHROME_PATH")
    if env_path and os.path.exists(env_path):
        return env_path

    for path in candidates:
        expanded = os.path.expanduser(path)
        if os.path.exists(expanded):
            return expanded

    # Last resort: let the system resolve it
    chrome_bin = os.environ.get("CHROME_PATH", "google-chrome")
    print(f"Warning: Chrome not found, falling back to '{chrome_bin}'")
    return chrome_bin
```

---

## Process Lifecycle Management

Server-resident Chrome instances require careful process management including startup, PID tracking, graceful shutdown, and crash recovery.

### Startup & PID Tracking

```python
import subprocess
import time
import os
import signal
import json
import urllib.request
from typing import Optional


class ChromeProcess:
    """Chrome process wrapper"""

    def __init__(self, port=9222, args=None):
        self.port = port
        self.args = args or []
        self.proc: Optional[subprocess.Popen] = None
        self.pid: Optional[int] = None
        self.start_time: Optional[float] = None

    def start(self):
        """Launch Chrome process"""
        args = [find_chrome_path()] + self.args
        print(f"Starting Chrome: {' '.join(args)}")

        self.proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,  # Process group isolation
        )
        self.pid = self.proc.pid
        self.start_time = time.time()
        print(f"Chrome started (PID: {self.pid})")
        return self.pid

    def is_running(self):
        """Check if process is alive"""
        if self.proc is None:
            return False
        return self.proc.poll() is None

    def wait_for_ready(self, timeout=30):
        """Wait for Chrome's remote debugging port to be ready"""
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(
                    f"http://127.0.0.1:{self.port}/json/version", timeout=5
                )
                if resp.status == 200:
                    data = json.loads(resp.read())
                    print(f"Chrome ready: {data.get('Browser', '?')}")
                    return True
            except Exception:
                pass
            time.sleep(1)
        raise TimeoutError(f"Chrome not ready within {timeout}s (PID: {self.pid})")

    def get_uptime(self):
        """Get process uptime in seconds"""
        if self.start_time is None:
            return 0
        return time.time() - self.start_time
```

### Graceful Shutdown

```python
def graceful_shutdown(proc: subprocess.Popen, timeout=10):
    """Gracefully shut down a Chrome process"""
    if proc is None or proc.poll() is not None:
        return

    pid = proc.pid
    print(f"Shutting down Chrome (PID: {pid})...")

    try:
        # Step 1: Send SIGTERM (Linux/macOS)
        if os.name != "nt":
            os.killpg(os.getpgid(pid), signal.SIGTERM)
        else:
            proc.terminate()

        # Wait for graceful exit
        proc.wait(timeout=timeout)
        print(f"Chrome gracefully shut down (PID: {pid})")
    except subprocess.TimeoutExpired:
        # Force kill on timeout
        print(f"Graceful shutdown timed out, force killing (PID: {pid})")
        if os.name != "nt":
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        else:
            proc.kill()
        proc.wait(timeout=5)
        print(f"Chrome force killed (PID: {pid})")


def cleanup_chrome_processes(port=None):
    """Clean up lingering Chrome processes"""
    import psutil  # Optional dependency

    cleaned = 0
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            name = proc.info.get("name") or ""
            is_chrome = "chrome" in name.lower() or "chromium" in name.lower()

            if is_chrome and "--remote-debugging-port" in str(cmdline):
                if port and f"--remote-debugging-port={port}" not in str(cmdline):
                    continue
                print(f"Cleaning up leftover Chrome (PID: {proc.info['pid']})")
                proc.terminate()
                cleaned += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    print(f"Cleaned up {cleaned} leftover processes")
    return cleaned
```

### Crash Detection

```python
import asyncio


async def monitor_process(proc: subprocess.Popen, on_crash):
    """Monitor Chrome process, trigger callback on crash"""
    while True:
        ret = proc.poll()
        if ret is not None:
            print(f"Chrome exited with code: {ret}")
            await on_crash(ret)
            break
        await asyncio.sleep(1)
```

---

## Xvfb Virtual Display

When you need headed (Headful) mode on a headless server, Xvfb (X Virtual Framebuffer) is the standard solution.

### Installing Xvfb

```bash
# Debian/Ubuntu
apt-get update && apt-get install -y xvfb x11-utils

# CentOS/RHEL/Fedora
yum install -y xorg-x11-server-Xvfb

# Alpine
apk add xvfb
```

### Xvfb Manager

```python
import subprocess
import time
import os


class XvfbManager:
    """Xvfb Virtual Display Manager"""

    def __init__(self, display=":99", resolution="1920x1080x24"):
        self.display = display
        self.resolution = resolution
        self.proc: subprocess.Popen = None

    def start(self):
        """Start Xvfb"""
        if self.proc and self.proc.poll() is None:
            print(f"Xvfb {self.display} already running")
            return

        cmd = ["Xvfb", self.display, "-screen", "0", self.resolution, "-ac"]
        print(f"Starting Xvfb: {' '.join(cmd)}")
        self.proc = subprocess.Popen(
            cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        time.sleep(1)  # Wait for readiness
        os.environ["DISPLAY"] = self.display
        print(f"Xvfb started: {self.display}")

    def stop(self):
        """Stop Xvfb"""
        if self.proc is None:
            return

        print(f"Stopping Xvfb: {self.display}")
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
            print("Xvfb stopped")
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait(timeout=3)
            print("Xvfb force killed")

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
```

### Combined Usage: Headful + Xvfb

```python
def start_headful_chrome(port=9222, display=":99"):
    """Start headed Chrome through Xvfb"""
    # 1. Start Xvfb
    xvfb = XvfbManager(display=display)
    xvfb.start()

    # 2. Start Chrome in virtual display (no --headless)
    args = build_chrome_args(
        port=port,
        headless_mode="none",  # Headed mode
    )
    os.environ["DISPLAY"] = display

    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(f"Headed Chrome started (PID: {proc.pid}, DISPLAY: {display})")
    return xvfb, proc
```

---

## Docker Containerization

### Dockerfile Design

```dockerfile
# Dockerfile.chrome-cdp
FROM python:3.11-slim

# 1. Install Chrome and dependencies
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    gnupg \
    xvfb \
    x11vnc \
    fonts-noto \
    fonts-freefont-ttf \
    procps \
    # Chrome installation
    && wget -q -O - https://dl-ssl.google.com/linux/linux_signing_key.pub \
       | gpg --dearmor -o /usr/share/keyrings/google-chrome.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google-chrome.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google-chrome.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && rm -rf /var/lib/apt/lists/*

# 2. Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copy application code
COPY src/ ./src/
COPY scripts/ ./scripts/

# 4. Create required directories
RUN mkdir -p /tmp/chrome-data /tmp/xvfb /app/screenshots /app/reports

# 5. Environment variables
ENV CHROME_PATH=/usr/bin/google-chrome-stable \
    CHROME_PORT=9222 \
    CHROME_HEADLESS_MODE=new \
    CHROME_NO_SANDBOX=true \
    DISPLAY=:99 \
    CDP_AUTH_TOKEN="" \
    CDP_MAX_SESSIONS=5

# 6. Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -s http://127.0.0.1:${CHROME_PORT}/json/version > /dev/null || exit 1

# 7. Entry point
ENTRYPOINT ["python", "-m", "scripts.runner"]
```

### Slim Dockerfile (Alpine)

```dockerfile
# Dockerfile.chrome-cdp-alpine
FROM python:3.11-alpine

# Install Chromium (available directly from Alpine repos)
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

### Dependencies

```text
# requirements.txt
websockets>=12.0
aiohttp>=3.9.0
Pillow>=10.0.0
psutil>=5.9.0
```

### Docker Entrypoint Script

```python
# scripts/runner.py - Docker entrypoint
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
    """Set up Xvfb (only when needed)"""
    global xvfb_proc
    if HEADLESS_MODE.lower() in ("none", "false", "0"):
        cmd = ["Xvfb", DISPLAY, "-screen", "0", "1920x1080x24", "-ac"]
        xvfb_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.environ["DISPLAY"] = DISPLAY
        time.sleep(1)
        print(f"Xvfb started: {DISPLAY}")


def start_chrome():
    """Start Chrome"""
    global chrome_proc

    args = [CHROME_PATH]

    if HEADLESS_MODE.lower() in ("new", "old", "chrome"):
        args.append(f"--headless={HEADLESS_MODE}")
    elif HEADLESS_MODE.lower() == "true":
        args.append("--headless=new")  # Backward compatibility

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
    print(f"Chrome started (PID: {chrome_proc.pid})")


def wait_chrome(timeout=30):
    """Wait for Chrome to be ready"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = urllib.request.urlopen(f"http://127.0.0.1:{CHROME_PORT}/json/version", timeout=5)
            if r.status == 200:
                data = json.loads(r.read())
                print(f"Chrome ready: {data.get('Browser', '?')}")
                return True
        except Exception:
            pass
        time.sleep(1)
    raise RuntimeError(f"Chrome failed to start within {timeout}s")


def cleanup(signum=None, frame=None):
    """Clean up resources"""
    print("Cleaning up resources...")
    for proc in [chrome_proc, xvfb_proc]:
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=3)
    print("Resource cleanup complete")


# Register signal handlers
signal.signal(signal.SIGTERM, cleanup)
signal.signal(signal.SIGINT, cleanup)

if __name__ == "__main__":
    try:
        setup_xvfb()
        start_chrome()
        wait_chrome()
        print("Chrome CDP service ready", flush=True)

        # Keep container running
        while True:
            time.sleep(10)
            if chrome_proc.poll() is not None:
                print(f"Chrome exited unexpectedly (code: {chrome_proc.returncode})", flush=True)
                break
    except Exception as e:
        print(f"Startup failed: {e}", flush=True)
        cleanup()
        sys.exit(1)
    except KeyboardInterrupt:
        cleanup()
```

---

## Docker Compose Orchestration

```yaml
# docker-compose.yml
version: "3.8"

services:
  # Primary CDP service instance
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

  # Second CDP instance (different host port)
  cdp-chrome-2:
    build:
      context: .
      dockerfile: Dockerfile.chrome-cdp
    container_name: cdp-chrome-2
    ports:
      - "9223:9222"  # Map to a different host port
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

## Health Checks & Auto-Restart

### HTTP-Level Health Check

```python
import urllib.request
import json
import time


class HealthChecker:
    """CDP service health checker"""

    def __init__(self, port=9222, host="127.0.0.1"):
        self.port = port
        self.host = host
        self.version_url = f"http://{host}:{port}/json/version"
        self.list_url = f"http://{host}:{port}/json"
        self.last_check = 0
        self.consecutive_failures = 0

    def check_basic(self):
        """Basic health check: verify /json/version endpoint"""
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
        """Deep health check: verify WebSocket connectivity"""
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
                "ws_endpoints": ws_urls[:3],  # Return at most 3
            }

        except Exception as e:
            return False, f"Deep check failed: {e}"

    def get_stats(self):
        """Get Chrome runtime statistics"""
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

### Auto-Restart Controller

```python
import asyncio
import subprocess


class AutoRestartController:
    """Auto-restart controller for Chrome instances"""

    def __init__(self, port=9222, max_retries=3, check_interval=30):
        self.port = port
        self.max_retries = max_retries
        self.check_interval = check_interval
        self.checker = HealthChecker(port)
        self.restart_count = 0
        self._running = False

    async def start_monitoring(self, start_func, stop_func):
        """Start the monitoring loop"""
        self._running = True
        consecutive_errors = 0

        while self._running:
            await asyncio.sleep(self.check_interval)

            ok, info = self.checker.check_basic()
            if ok:
                consecutive_errors = 0
                continue

            consecutive_errors += 1
            print(f"Health check failed ({consecutive_errors}): {info}")

            if consecutive_errors >= 3:
                print(f"{consecutive_errors} consecutive failures, restarting...")
                await self._restart(start_func, stop_func)
                consecutive_errors = 0

    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self._running = False

    async def _restart(self, start_func, stop_func):
        """Execute the restart flow"""
        self.restart_count += 1

        if self.restart_count > self.max_retries:
            print(f"Max retries exceeded ({self.max_retries}), giving up")
            self._running = False
            return

        print(f"Restart #{self.restart_count}...")

        # Stop old instance
        await stop_func()
        await asyncio.sleep(2)

        # Clean up port
        self._cleanup_port()

        # Start new instance
        await start_func()
        print("Restart complete")
```

---

## Multi-Instance Management & Resource Limits

### Dynamic Port Allocator

```python
import socket


class PortAllocator:
    """Dynamic port allocator"""

    def __init__(self, base_port=9222, max_attempts=100):
        self.base_port = base_port
        self.max_attempts = max_attempts
        self._allocated = set()

    def find_free_port(self):
        """Find an available port"""
        for offset in range(self.max_attempts):
            port = self.base_port + offset
            if port in self._allocated:
                continue
            if self._is_port_free(port):
                self._allocated.add(port)
                return port
        raise RuntimeError(
            f"No free port found in range {self.base_port}-{self.base_port + self.max_attempts}"
        )

    def release_port(self, port):
        """Release a port back to the pool"""
        self._allocated.discard(port)

    @staticmethod
    def _is_port_free(port):
        """Check if a port is free"""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex(("127.0.0.1", port)) != 0
```

### Multi-Instance Manager

```python
class InstanceManager:
    """Multi-instance Chrome manager"""

    def __init__(self, max_instances=5):
        self.max_instances = max_instances
        self.instances: dict[int, ChromeProcess] = {}  # port -> ChromeProcess
        self.allocator = PortAllocator()

    async def spawn_instance(self, headless_mode="new"):
        """Create a new Chrome instance"""
        if len(self.instances) >= self.max_instances:
            raise RuntimeError(f"Instance limit reached ({self.max_instances})")

        port = self.allocator.find_free_port()
        args = build_chrome_args(port=port, headless_mode=headless_mode)

        proc = ChromeProcess(port=port, args=args)
        proc.start()
        proc.wait_for_ready(timeout=30)

        self.instances[port] = proc
        print(f"Instance created (port: {port}, PID: {proc.pid})")
        return port

    async def kill_instance(self, port):
        """Terminate a specific instance"""
        proc = self.instances.pop(port, None)
        if proc is None:
            print(f"No instance found on port {port}")
            return

        graceful_shutdown(proc.proc)
        self.allocator.release_port(port)
        print(f"Instance terminated (port: {port})")

    async def kill_all(self):
        """Terminate all instances"""
        for port in list(self.instances.keys()):
            await self.kill_instance(port)
        print("All instances terminated")

    def get_stats(self):
        """Get statistics for all instances"""
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

### Resource Limit Configuration

```python
import resource  # Unix only


def apply_resource_limits(cpu_limit=2, memory_mb=4096):
    """Set process resource limits (Linux only)"""
    if os.name == "nt":
        print("Windows does not support the resource module")
        return

    try:
        # CPU time limit (seconds)
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_limit * 3600, cpu_limit * 3600))

        # Memory limit (bytes)
        memory_bytes = memory_mb * 1024 * 1024
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

        # File descriptor limit
        resource.setrlimit(resource.RLIMIT_NOFILE, (4096, 4096))

        print(f"Resource limits applied: CPU={cpu_limit}h, Memory={memory_mb}MB")
    except Exception as e:
        print(f"Failed to set resource limits: {e}")
```

---

## Security Hardening

When exposing Chrome CDP services over a network, the following security measures are essential.

### Authentication Token

```python
import hmac


class CDPAuthMiddleware:
    """CDP authentication middleware"""

    def __init__(self, token: str):
        self.token = token

    def generate_auth_url(self, ws_url: str) -> str:
        """Append auth token to WebSocket URL"""
        if "?" in ws_url:
            return f"{ws_url}&token={self.token}"
        return f"{ws_url}?token={self.token}"

    def verify_token(self, received_token: str) -> bool:
        """Verify a received token"""
        return hmac.compare_digest(received_token, self.token)

    @staticmethod
    def generate_token(length=32):
        """Generate a random token"""
        import secrets
        return secrets.token_hex(length)


class CDPProxy:
    """CDP proxy: protects the underlying CDP port"""

    def __init__(self, listen_port=9443, target_port=9222, auth_token=None):
        self.listen_port = listen_port
        self.target_port = target_port
        self.auth_token = auth_token or CDPAuthMiddleware.generate_token()
        self._server = None

    async def start(self):
        """Start the authenticated CDP proxy"""
        # Real implementation would use aiohttp or websockets library
        # Flow: validate token on connection, then proxy to real CDP port
        print(f"CDP proxy started: 0.0.0.0:{self.listen_port} -> 127.0.0.1:{self.target_port}")
        print(f"Auth token: {self.auth_token}")
```

### Firewall Rules

```bash
# Allow only local loopback to access the CDP port
iptables -A INPUT -p tcp --dport 9222 -s 127.0.0.1 -j ACCEPT
iptables -A INPUT -p tcp --dport 9222 -j DROP

# If using proxy port (e.g., 9443), allow only your application servers
iptables -A INPUT -p tcp --dport 9443 -s 10.0.0.0/8 -j ACCEPT
iptables -A INPUT -p tcp --dport 9443 -s 172.16.0.0/12 -j ACCEPT
iptables -A INPUT -p tcp --dport 9443 -j DROP
```

### Network Security Checklist

| Item | Measure | Notes |
|------|---------|-------|
| CDP port exposure | Listen on 127.0.0.1 only | Must use a proxy for external access |
| Authentication | Token-based auth | At least 32-byte random token |
| Transport encryption | HTTPS/WSS | Mandatory for production |
| Network isolation | Internal VPC only | Never expose to the public internet |
| Audit logging | Log all CDP connections | Track anomalous activity |
| Rate limiting | Per-IP connection limits | Prevent abuse |
| Idle timeout | Auto-disconnect idle connections | Default 300 seconds |

---

## Complete Reference: HeadlessChromeManager Class

```python
"""
headless_chrome_manager.py
Complete Headless Chrome manager covering start, stop, restart, health check,
and multi-instance management.

Dependencies: pip install websockets psutil
"""

import asyncio
import json
import os
import signal
import subprocess
import time
import urllib.request
from dataclasses import dataclass
from typing import Optional


@dataclass
class ChromeInstance:
    """State of a single Chrome instance"""
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
    Headless Chrome Manager

    Features:
    - Start/stop Chrome instances (supports all headless modes)
    - Automatic health checks with restart
    - Multi-instance management with port allocation
    - Resource usage tracking
    - Xvfb support for headed mode
    """

    # CDP helper method
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

        # Ensure data directory exists
        os.makedirs(user_data_dir, exist_ok=True)

    def _build_args(self, port: int, instance_dir: str) -> list:
        """Build startup arguments for a single instance"""
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

        # Headless mode
        if self.headless_mode and self.headless_mode.lower() != "none":
            args.append(f"--headless={self.headless_mode}")

        # Sandbox
        if os.environ.get("CHROME_NO_SANDBOX", "true").lower() in ("1", "true"):
            args.append("--no-sandbox")

        return args

    async def start_instance(self, port: Optional[int] = None, xvfb: bool = False) -> int:
        """Start a new Chrome instance"""
        if len(self.instances) >= self.max_instances:
            raise RuntimeError(f"Maximum instances reached ({self.max_instances})")

        port = port or self._find_free_port()
        instance_dir = os.path.join(self.user_data_dir, f"instance-{port}")

        xvfb_proc = None
        if xvfb and self.headless_mode.lower() == "none":
            # Start Xvfb
            display = f":{port - self.base_port + 99}"
            xvfb_proc = subprocess.Popen(
                ["Xvfb", display, "-screen", "0", "1920x1080x24", "-ac"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            os.environ["DISPLAY"] = display
            await asyncio.sleep(1)

        # Start Chrome
        args = self._build_args(port, instance_dir)
        proc = subprocess.Popen(
            args,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            preexec_fn=os.setsid if os.name != "nt" else None,
        )

        # Wait for readiness
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
        print(f"[{port}] Instance started (PID: {proc.pid})")
        return port

    async def stop_instance(self, port: int):
        """Stop a specific instance"""
        instance = self.instances.pop(port, None)
        if not instance:
            print(f"[{port}] Instance not found")
            return

        # Shut down Chrome
        self._graceful_kill(instance.process)

        # Shut down Xvfb
        if instance.xvfb_process:
            self._graceful_kill(instance.xvfb_process)

        print(f"[{port}] Instance stopped (uptime: {time.time() - instance.start_time:.1f}s)")

    async def stop_all(self):
        """Stop all instances"""
        for port in list(self.instances.keys()):
            await self.stop_instance(port)
        print("All instances stopped")

    async def restart_instance(self, port: int, xvfb: bool = False):
        """Restart a specific instance"""
        print(f"[{port}] Restarting...")
        await self.stop_instance(port)
        await asyncio.sleep(2)
        await self.start_instance(port=port, xvfb=xvfb)
        print(f"[{port}] Restart complete")

    async def health_check(self, port: int) -> bool:
        """Check health of a single instance"""
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
        """Start background health monitoring"""
        self._running = True
        retries = {}

        while self._running:
            await asyncio.sleep(self.check_interval)

            for port in list(self.instances.keys()):
                if not await self.health_check(port):
                    retries[port] = retries.get(port, 0) + 1
                    print(f"[{port}] Health check failed ({retries[port]}/{self.max_retries})")

                    if retries[port] >= self.max_retries:
                        print(f"[{port}] Max retries reached, auto-restarting")
                        await self.restart_instance(port)
                        retries[port] = 0
                else:
                    retries[port] = 0

    def stop_monitoring(self):
        """Stop health monitoring"""
        self._running = False

    def get_stats(self) -> dict:
        """Get statistics for all instances"""
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
        """Find a free port"""
        import socket
        for offset in range(100):
            port = self.base_port + offset
            if port not in self.instances:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    if s.connect_ex(("127.0.0.1", port)) != 0:
                        return port
        raise RuntimeError("Could not find a free port")

    @staticmethod
    async def _wait_for_port(port: int, timeout: int = 30):
        """Wait for a port to be ready"""
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
        raise TimeoutError(f"Port {port} not ready within {timeout}s")

    @staticmethod
    def _count_sessions(port: int) -> int:
        """Count current sessions"""
        try:
            resp = urllib.request.urlopen(f"http://127.0.0.1:{port}/json", timeout=3)
            return len(json.loads(resp.read()))
        except Exception:
            return 0

    @staticmethod
    def _graceful_kill(proc: subprocess.Popen):
        """Gracefully kill a process"""
        if proc is None or proc.poll() is not None:
            return

        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)

    async def __aenter__(self):
        """Context manager entry"""
        return self

    async def __aexit__(self, *args):
        """Context manager exit"""
        self.stop_monitoring()
        await self.stop_all()
```

### Usage Example

```python
async def main():
    """Complete example using HeadlessChromeManager"""
    async with HeadlessChromeManager(
        headless_mode="new",
        base_port=9222,
        max_instances=3,
        check_interval=30,
    ) as manager:

        # Start two instances
        port1 = await manager.start_instance()
        port2 = await manager.start_instance()

        print(f"Instance ports: {port1}, {port2}")

        # Get statistics
        stats = manager.get_stats()
        print(f"Active instances: {stats['total_instances']}")

        # Start health monitoring
        monitor = asyncio.create_task(manager.start_monitoring())

        # ... business logic ...
        await asyncio.sleep(60)

        # Stop monitoring
        manager.stop_monitoring()
        monitor.cancel()

        # Cleanup happens in __aexit__
        print("Cleanup complete")


# asyncio.run(main())
```

---

> **Summary**: Deploying Headless Chrome CDP services on a server requires systematic handling of headless mode selection, startup flag configuration, process lifecycle management, virtual displays, containerized deployment, health checks with auto-restart, multi-instance resource management, and security hardening. The `HeadlessChromeManager` class provides a complete solution covering everything from single-instance management to multi-instance pooling. Combined with Docker containerization, this infrastructure can support production-grade browser automation services.
