---
lang: en
title: "CDP Multi-Instance Orchestration: Controlling Distributed Browser Clusters with Python"
date: "2026-06-05 23:40:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Distributed
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: Learn how to launch and coordinate multiple Chrome instances simultaneously to build a distributed browser cluster for large-scale automation tasks.
---

> **Summary in one sentence**: Multi-instance orchestration is NOT multi-tab. This article teaches you how to launch N independent Chrome processes simultaneously, orchestrate them all via CDP, and build your own browser cluster for parallel testing, environment isolation, or fingerprint bypass.

---

## Table of Contents

1. [Multi-Instance vs Multi-Tab: The Fundamental Difference](#multi-instance-vs-multi-tab-the-fundamental-difference)
2. [Why You Need Multiple Chrome Instances](#why-you-need-multiple-chrome-instances)
3. [Port Management: One Debug Port Per Instance](#port-management-one-debug-port-per-instance)
4. [Launching Chrome Instances and Tracking PIDs](#launching-chrome-instances-and-tracking-pids)
5. [Discovering WebSocket URLs](#discovering-websocket-urls)
6. [Connection Pooling: asyncio Connection Management](#connection-pooling-asyncio-connection-management)
7. [Task Distribution Strategies](#task-distribution-strategies)
8. [Graceful Shutdown: SIGTERM and Cleanup](#graceful-shutdown-sigterm-and-cleanup)
9. [Complete Reference: ChromeClusterManager Class](#complete-reference-chromeclustermanager-class)
10. [Real Use Case: Parallel Screenshots of 10 Pages](#real-use-case-parallel-screenshots-of-10-pages)
11. [Pitfalls and Best Practices](#pitfalls-and-best-practices)
12. [Summary](#summary)

---

## Multi-Instance vs Multi-Tab: The Fundamental Difference

Before diving in, let's clarify an important distinction:

| Aspect | Multi-Tab (One Process) | Multi-Instance (Multiple Processes) |
|--------|------------------------|-------------------------------------|
| **Processes** | 1 Chrome process | N independent Chrome processes |
| **Isolation** | Shared cookies, cache, renderer | Fully isolated |
| **Memory cost** | Low (shared main process) | High (~100-300MB each) |
| **Crash impact** | One tab crash doesn't affect others | One instance crash doesn't affect others |
| **Fingerprint** | All tabs share the same fingerprint | Each instance can have a unique fingerprint |
| **CDP debug port** | Shared (e.g., 9222) | Unique port per instance |
| **Use cases** | Light crawlers, simple tests | Large-scale parallel, isolation testing, anti-bot |

**One sentence difference: Multi-tab runs inside one browser process; multi-instance runs across separate processes.**

Our previous articles covered multi-tab scenarios — managing multiple pages within a single Chrome process. This article shifts to the **multi-process** level, discussing how to orchestrate multiple independent Chrome processes.

---

## Why You Need Multiple Chrome Instances

### 1. Complete Isolation

Browser fingerprinting tools (like `fingerprintjs`) can detect shared underlying properties across tabs within the same process — WebGL renderer, font list, timezone data, etc. Different Chrome instances naturally have independent rendering contexts. Combined with separate `--user-data-dir` directories, you also get fully isolated cookies and storage.

### 2. Parallel Speedup

Suppose you need to capture 100 pages or log into 50 accounts for batch operations. A single-process multi-tab approach is constrained by Chrome's rendering thread and memory, making large-scale parallelism difficult. Multi-instance orchestration lets you fully utilize multi-core CPUs for true horizontal scaling.

### 3. Different Configurations / Fingerprints

Each instance can be independently configured with:
- Different `--user-data-dir` (separate browser profiles)
- Different User-Agent, viewport
- Different proxy (`--proxy-server`)
- Different language, timezone (startup flags or CDP injection)

This is critical for anti-bot crawling, ad verification, and multi-account management.

### 4. Test Environment Isolation

In E2E testing, when multiple test cases run in parallel, multi-instance prevents cross-test state contamination — one test's login state won't accidentally affect another.

---

## Port Management: One Debug Port Per Instance

The CDP debug port is the unique identifier for each Chrome instance. Port assignment is the first step in multi-instance orchestration.

### Port Selection Strategy

```python
# Port allocation strategy
BASE_PORT = 9222
INSTANCE_COUNT = 5

ports = [BASE_PORT + i for i in range(INSTANCE_COUNT)]
# -> [9222, 9223, 9224, 9225, 9226]
```

**Guidelines**:
- Avoid common ports (80, 443, 8080) to prevent conflicts
- Start from 9222 and increment
- Check port availability before launching

```python
import socket

def is_port_available(port):
    """Check if a port is available"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False
```

---

## Launching Chrome Instances and Tracking PIDs

Use `subprocess.Popen` to launch Chrome, assigning an independent port and user data directory to each instance.

```python
import subprocess
import os
import tempfile
import shutil
import platform

CHROME_PATH = {
    'win32': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    'darwin': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    'linux': 'google-chrome'
}

def launch_chrome(port, user_data_dir=None, headless=True, proxy=None):
    """
    Launch a Chrome instance.

    Args:
        port: Debugging port
        user_data_dir: User data directory (auto-creates temp dir if None)
        headless: Whether to use headless mode
        proxy: Proxy address, e.g. "http://127.0.0.1:8080"

    Returns:
        (process, user_data_dir) tuple
    """
    system = platform.system().lower()
    if system == 'windows':
        chrome_path = CHROME_PATH['win32']
    elif system == 'darwin':
        chrome_path = CHROME_PATH['darwin']
    else:
        chrome_path = CHROME_PATH['linux']

    # Create temp directory if none specified
    if user_data_dir is None:
        user_data_dir = tempfile.mkdtemp(prefix='chrome_profile_')

    # Build launch arguments
    args = [
        chrome_path,
        f'--remote-debugging-port={port}',
        '--remote-allow-origins=*',
        '--no-first-run',
        '--no-default-browser-check',
        f'--user-data-dir={user_data_dir}',
    ]

    if headless:
        args.append('--headless=new')  # New headless mode (Chrome 112+)

    if proxy:
        args.append(f'--proxy-server={proxy}')

    # Launch Chrome
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )

    print(f'[Instance] PID={process.pid}, Port={port}, Headless={headless}')
    return process, user_data_dir
```

### Why Tracking PIDs Matters

Each instance's PID is critical for management:
- Monitoring whether the process is alive
- Sending termination signals
- Detecting zombie processes

```python
def is_process_alive(pid):
    """Check if a process is alive using signal 0"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False
```

---

## Discovering WebSocket URLs

After launching, each Chrome instance needs its WebSocket endpoint discovered via HTTP.

```python
import urllib.request
import json
import time

def get_ws_url(host, port, timeout=10):
    """
    Get the WebSocket debug URL for a Chrome instance.
    
    Chrome needs a brief initialization period after launch,
    so we add a retry mechanism.
    """
    url = f'http://{host}:{port}/json/version'

    for attempt in range(timeout):
        try:
            resp = urllib.request.urlopen(url, timeout=2)
            data = json.loads(resp.read())
            ws_url = data['webSocketDebuggerUrl']
            return ws_url
        except Exception as e:
            if attempt < timeout - 1:
                time.sleep(1)
                continue
            raise RuntimeError(f'Failed to get WS URL on port {port}: {e}')

    return None
```

**Note**: `/json/version` returns the browser-level WebSocket endpoint (the `Target` domain entry point), while `/json` returns endpoints for individual pages. In multi-instance scenarios, we typically use `/json/version` to get the top-level endpoint, then use `Target.attachToTarget` to attach to specific pages.

---

## Connection Pooling: asyncio Connection Management

The core challenge of multi-instance orchestration is concurrent connection management. We encapsulate it with `asyncio`.

```python
import asyncio
import websockets
import json

CMD_ID = [0]

async def cdp(ws, method, params=None, session_id=None):
    """Send CDP command and wait for response (supports session_id for page-level communication)"""
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

### ChromeInstance Wrapper

```python
class ChromeInstance:
    """Wrapper for a single Chrome instance"""

    def __init__(self, port, pid, user_data_dir, ws_url):
        self.port = port
        self.pid = pid
        self.user_data_dir = user_data_dir
        self.ws_url = ws_url
        self.ws = None
        self._busy = False
        self.task_count = 0

    @property
    def is_busy(self):
        return self._busy

    @property
    def is_alive(self):
        if not self.pid:
            return False
        try:
            os.kill(self.pid, 0)
            return True
        except OSError:
            return False

    async def connect(self):
        """Establish WebSocket connection"""
        self.ws = await websockets.connect(self.ws_url, max_size=2**24)
        await cdp(self.ws, 'Target.setAutoAttach', {
            'autoAttach': True,
            'flatten': True,
            'waitForDebuggerOnStart': False
        })
        return self

    async def close(self):
        """Close WebSocket connection"""
        if self.ws:
            await self.ws.close()
            self.ws = None

    async def execute_task(self, task_fn, *args, **kwargs):
        """Execute a task and mark busy state"""
        self._busy = True
        try:
            result = await task_fn(self, *args, **kwargs)
            self.task_count += 1
            return result
        finally:
            self._busy = False
```

---

## Task Distribution Strategies

With a pool of instances, the next question is how to assign tasks. Here are several common strategies:

### 1. Round-Robin Distribution

```python
import itertools

class RoundRobinDispatcher:
    """Round-robin dispatcher: assign tasks to instances in sequence"""

    def __init__(self, instances):
        self.instances = instances
        self.iterator = itertools.cycle(instances)

    async def get_instance(self):
        """Get the next idle instance"""
        for _ in range(len(self.instances)):
            instance = next(self.iterator)
            if not instance.is_busy:
                return instance
        return None  # All busy
```

### 2. Least-Loaded Distribution

```python
class LeastLoadedDispatcher:
    """Least-loaded dispatcher: assign to the instance with fewest completed tasks"""

    def __init__(self, instances):
        self.instances = instances

    async def get_instance(self):
        idle = [i for i in self.instances if not i.is_busy]
        if not idle:
            return None
        return min(idle, key=lambda i: i.task_count)
```

### 3. Weighted Distribution

```python
class WeightedDispatcher:
    """Weighted dispatcher: assign tasks based on instance capacity weights"""

    def __init__(self, instances, weights=None):
        self.instances = instances
        self.weights = weights or [1] * len(instances)

    async def get_instance(self):
        idle = [(i, w) for i, w in zip(self.instances, self.weights)
                if not i.is_busy]
        if not idle:
            return None

        import random
        instances, weights = zip(*idle)
        total = sum(weights)
        r = random.uniform(0, total)
        upto = 0
        for inst, w in zip(instances, weights):
            upto += w
            if r <= upto:
                return inst
        return instances[-1]
```

---

## Graceful Shutdown: SIGTERM and Cleanup

Multi-instance management must handle cleanup. Killing processes abruptly can cause:
- Temporary file residue (from `--user-data-dir` temp directories)
- Zombie processes
- Unreleased ports

```python
import signal
import atexit

class GracefulShutdown:
    """Graceful shutdown manager"""

    def __init__(self):
        self.instances = []
        self._cleaned_up = False
        atexit.register(self.cleanup)

    def register(self, instance):
        self.instances.append(instance)

    def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True

        print('\n[Shutdown] Closing all instances...')

        for inst in self.instances:
            try:
                if inst.is_alive:
                    if os.name == 'nt':  # Windows
                        subprocess.run(['taskkill', '/F', '/PID', str(inst.pid)],
                                       capture_output=True)
                    else:  # Unix
                        os.kill(inst.pid, signal.SIGTERM)
                    print(f'  [Killed] PID={inst.pid}')

                # Clean up user data directory
                if inst.user_data_dir and os.path.exists(inst.user_data_dir):
                    shutil.rmtree(inst.user_data_dir, ignore_errors=True)
                    print(f'  [Cleaned] {inst.user_data_dir}')
            except Exception as e:
                print(f'  [Error] PID={inst.pid}: {e}')

        print('[Shutdown] Done.')
```

### Async Version of Graceful Shutdown

```python
class AsyncGracefulShutdown:
    """Async graceful shutdown manager"""

    def __init__(self):
        self.instances = []
        self._cleaned_up = False

    async def cleanup(self):
        if self._cleaned_up:
            return
        self._cleaned_up = True

        print('\n[Shutdown] Closing all instances...')

        # Close WebSocket connections in parallel
        close_tasks = [inst.close() for inst in self.instances]
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)

        # Terminate processes and clean directories
        for inst in self.instances:
            try:
                if inst.is_alive:
                    if os.name == 'nt':
                        subprocess.run(['taskkill', '/F', '/PID', str(inst.pid)],
                                       capture_output=True)
                    else:
                        os.kill(inst.pid, signal.SIGTERM)

                if inst.user_data_dir and os.path.exists(inst.user_data_dir):
                    shutil.rmtree(inst.user_data_dir, ignore_errors=True)
            except Exception as e:
                print(f'  [Error] PID={inst.pid}: {e}')

        print('[Shutdown] Done.')
```

---

## Complete Reference: ChromeClusterManager Class

Here is a complete cluster manager integrating all the components above.

```python
#!/usr/bin/env python3
"""
Chrome Cluster Manager — CDP Multi-Instance Orchestration Framework

Manages N independent Chrome processes with support for:
- Auto-launch and port allocation
- Connection pool management
- Multiple task distribution strategies
- Graceful shutdown and resource cleanup
"""
import asyncio
import json
import os
import platform
import signal
import subprocess
import tempfile
import shutil
import time
import urllib.request
import websockets
import itertools
from dataclasses import dataclass
from typing import Optional, List, Callable, Awaitable

# ============================================================
# CDP Core Communication
# ============================================================

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


def get_chrome_path():
    """Get system Chrome path"""
    system = platform.system().lower()
    paths = {
        'windows': [
            r'C:\Program Files\Google\Chrome\Application\chrome.exe',
            r'C:\Program Files (x86)\Google\Chrome\Application\chrome.exe',
        ],
        'darwin': ['/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'],
        'linux': ['google-chrome', 'chromium-browser', 'chromium'],
    }
    for p in paths.get(system, paths['linux']):
        if os.path.exists(p) or shutil.which(p):
            return p
    raise FileNotFoundError('Chrome not found. Install Google Chrome or Chromium.')


def is_port_available(port):
    """Check if a port is available"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def check_process_alive(pid):
    """Check if process is alive (signal 0 probe)"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ============================================================
# ChromeInstance — Single Instance Wrapper
# ============================================================

@dataclass
class ChromeInstance:
    port: int
    pid: int
    user_data_dir: str
    ws_url: str = ''
    ws: Optional[websockets.WebSocketClientProtocol] = None
    _busy: bool = False
    task_count: int = 0
    name: str = ''

    @property
    def is_busy(self):
        return self._busy

    @property
    def is_alive(self):
        return check_process_alive(self.pid)

    async def connect(self):
        self.ws = await websockets.connect(self.ws_url, max_size=2**24)
        await cdp(self.ws, 'Target.setAutoAttach', {
            'autoAttach': True, 'flatten': True,
            'waitForDebuggerOnStart': False
        })
        return self

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None


# ============================================================
# ChromeClusterManager
# ============================================================

class ChromeClusterManager:
    """
    Chrome Cluster Manager

    with ChromeClusterManager(count=4, headless=True) as cluster:
        await cluster.start()
        results = await cluster.run_on_all(some_task)
    """

    def __init__(
        self,
        count: int = 2,
        base_port: int = 9222,
        headless: bool = True,
        chrome_path: Optional[str] = None,
        proxy: Optional[str] = None,
        dispatcher_type: str = 'round_robin',
    ):
        self.count = count
        self.base_port = base_port
        self.headless = headless
        self.chrome_path = chrome_path or get_chrome_path()
        self.proxy = proxy
        self.dispatcher_type = dispatcher_type
        self.instances: List[ChromeInstance] = []
        self._dispatcher = None
        self._cleanup_done = False

    # ---------- Launch Cluster ----------

    async def start(self):
        """Launch all Chrome instances"""
        print(f'[Cluster] Starting {self.count} Chrome instances...')

        for i in range(self.count):
            port = self.base_port + i

            if not is_port_available(port):
                raise RuntimeError(f'Port {port} is already in use')

            user_data_dir = tempfile.mkdtemp(prefix=f'chrome_{port}_')

            args = [
                self.chrome_path,
                f'--remote-debugging-port={port}',
                '--remote-allow-origins=*',
                '--no-first-run',
                '--no-default-browser-check',
                f'--user-data-dir={user_data_dir}',
                '--disable-sync',
                '--disable-default-apps',
                '--disable-extensions',
            ]

            if self.headless:
                args.append('--headless=new')

            if self.proxy:
                args.append(f'--proxy-server={self.proxy}')

            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            ws_url = self._wait_for_ws_url(port)

            instance = ChromeInstance(
                port=port,
                pid=proc.pid,
                user_data_dir=user_data_dir,
                ws_url=ws_url,
                name=f'chrome-{port}'
            )

            await instance.connect()
            self.instances.append(instance)
            print(f'  [OK] Instance {i+1}/{self.count}: port={port}, pid={proc.pid}')

        self._init_dispatcher()
        print(f'[Cluster] All {self.count} instances ready.')
        return self

    def _wait_for_ws_url(self, port, max_retries=20, delay=0.5):
        for attempt in range(max_retries):
            try:
                resp = urllib.request.urlopen(
                    f'http://127.0.0.1:{port}/json/version', timeout=2
                )
                data = json.loads(resp.read())
                return data['webSocketDebuggerUrl']
            except Exception:
                if attempt < max_retries - 1:
                    time.sleep(delay)
                    continue
        raise RuntimeError(f'Chrome on port {port} failed to start')

    def _init_dispatcher(self):
        if self.dispatcher_type == 'round_robin':
            self._dispatcher = RoundRobinDispatcher(self.instances)
        elif self.dispatcher_type == 'least_loaded':
            self._dispatcher = LeastLoadedDispatcher(self.instances)
        else:
            self._dispatcher = RoundRobinDispatcher(self.instances)

    # ---------- Task Scheduling ----------

    async def get_idle_instance(self) -> Optional[ChromeInstance]:
        return await self._dispatcher.get_instance()

    async def run_on_one(self, task_fn: Callable[[ChromeInstance], Awaitable],
                         timeout: int = 60) -> Optional[any]:
        while True:
            instance = await self.get_idle_instance()
            if instance:
                return await self._run_task(instance, task_fn, timeout)
            await asyncio.sleep(0.5)

    async def run_on_all(self, task_fn: Callable[[ChromeInstance], Awaitable],
                         timeout: int = 60) -> List[any]:
        tasks = [self._run_task(inst, task_fn, timeout) for inst in self.instances]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def run_batch(self, tasks: List, task_fn: Callable,
                        timeout: int = 60) -> List[any]:
        """Execute a batch of tasks, auto-distributing to idle instances"""
        results = [None] * len(tasks)
        pending = list(enumerate(tasks))

        async def worker():
            while pending:
                idx, task = pending.pop(0)
                instance = await self.get_idle_instance()
                if instance:
                    results[idx] = await self._run_task(
                        instance, lambda inst: task_fn(inst, task), timeout
                    )
                else:
                    pending.append((idx, task))
                    await asyncio.sleep(0.3)

        workers = [worker() for _ in range(min(len(tasks), self.count))]
        await asyncio.gather(*workers)
        return results

    async def _run_task(self, instance: ChromeInstance,
                        task_fn: Callable, timeout: int):
        instance._busy = True
        try:
            result = await asyncio.wait_for(task_fn(instance), timeout=timeout)
            instance.task_count += 1
            return result
        finally:
            instance._busy = False

    # ---------- Shutdown Cluster ----------

    async def shutdown(self):
        """Gracefully shut down all instances"""
        if self._cleanup_done:
            return
        self._cleanup_done = True

        print('\n[Cluster] Shutting down...')

        await asyncio.gather(
            *[inst.close() for inst in self.instances],
            return_exceptions=True
        )

        for inst in self.instances:
            if inst.is_alive:
                try:
                    if os.name == 'nt':
                        subprocess.run(
                            ['taskkill', '/F', '/PID', str(inst.pid)],
                            capture_output=True, timeout=5
                        )
                    else:
                        os.kill(inst.pid, signal.SIGTERM)
                except Exception as e:
                    print(f'  [Warn] Failed to kill PID {inst.pid}: {e}')

        for inst in self.instances:
            if inst.user_data_dir and os.path.exists(inst.user_data_dir):
                try:
                    shutil.rmtree(inst.user_data_dir, ignore_errors=True)
                except Exception:
                    pass

        print(f'[Cluster] Shutdown complete. {self.count} instances terminated.')

    async def __aenter__(self):
        return await self.start()

    async def __aexit__(self, *args):
        await self.shutdown()


# ============================================================
# Dispatcher Implementations
# ============================================================

class RoundRobinDispatcher:
    def __init__(self, instances):
        self.instances = instances
        self.iterator = itertools.cycle(instances)

    async def get_instance(self):
        for _ in range(len(self.instances)):
            inst = next(self.iterator)
            if not inst._busy:
                return inst
        return None


class LeastLoadedDispatcher:
    def __init__(self, instances):
        self.instances = instances

    async def get_instance(self):
        idle = [i for i in self.instances if not i._busy]
        if not idle:
            return None
        return min(idle, key=lambda i: i.task_count)
```

---

## Real Use Case: Parallel Screenshots of 10 Pages

Here's a complete example using `ChromeClusterManager` to screenshot 10 pages simultaneously.

```python
# ============================================================
# Parallel Screenshot Example
# ============================================================

import base64

async def screenshot_task(instance: ChromeInstance, url: str, output_dir: str):
    """Take a screenshot on the given instance"""
    ws = instance.ws

    # Create a new tab
    result = await cdp(ws, 'Target.createTarget', {'url': 'about:blank'})
    target_id = result.get('targetId')

    # Attach to the new tab
    result = await cdp(ws, 'Target.attachToTarget', {
        'targetId': target_id,
        'flatten': True
    })
    session_id = result.get('sessionId')

    # Navigate
    await cdp(ws, 'Page.enable', session_id=session_id)
    await cdp(ws, 'Page.navigate', {'url': url}, session_id=session_id)

    # Wait for page load
    await asyncio.sleep(3)

    # Screenshot
    result = await cdp(ws, 'Page.captureScreenshot', {
        'format': 'png',
        'fromSurface': True
    }, session_id=session_id)

    # Save
    safe_name = url.replace('https://', '').replace('http://', '').replace('/', '_')
    output_path = os.path.join(output_dir, f'{safe_name}.png')
    with open(output_path, 'wb') as f:
        f.write(base64.b64decode(result['data']))

    # Close tab
    await cdp(ws, 'Target.closeTarget', {'targetId': target_id})

    print(f'  [Screenshot] {url} -> {output_path}')
    return output_path


async def main():
    """Launch 5 instances, screenshot 10 pages in parallel"""

    urls = [
        'https://www.example.com',
        'https://httpbin.org',
        'https://www.wikipedia.org',
        'https://github.com',
        'https://news.ycombinator.com',
        'https://www.reddit.com',
        'https://stackoverflow.com',
        'https://www.google.com',
        'https://www.bing.com',
        'https://www.yahoo.com',
    ]

    output_dir = 'screenshots'
    os.makedirs(output_dir, exist_ok=True)

    async with ChromeClusterManager(
        count=5,
        base_port=9222,
        headless=True,
        dispatcher_type='round_robin'
    ) as cluster:

        print(f'\n[Task] Capturing {len(urls)} pages with {cluster.count} instances...\n')

        start_time = time.time()

        results = await cluster.run_batch(
            tasks=urls,
            task_fn=lambda inst, url: screenshot_task(inst, url, output_dir),
            timeout=30
        )

        elapsed = time.time() - start_time
        success = sum(1 for r in results if isinstance(r, str))
        failed = sum(1 for r in results if isinstance(r, Exception))

        print(f'\n[Result] {success} succeeded, {failed} failed in {elapsed:.1f}s')
        print(f'[Result] Average: {elapsed / len(urls):.2f}s per page')

    print('\nDone.')


if __name__ == '__main__':
    asyncio.run(main())
```

### Sample Output

```bash
$ python cluster_screenshot.py

[Cluster] Starting 5 Chrome instances...
  [OK] Instance 1/5: port=9222, pid=12345
  [OK] Instance 2/5: port=9223, pid=12346
  [OK] Instance 3/5: port=9224, pid=12347
  [OK] Instance 4/5: port=9225, pid=12348
  [OK] Instance 5/5: port=9226, pid=12349
[Cluster] All 5 instances ready.

[Task] Capturing 10 pages with 5 instances...

  [Screenshot] https://www.example.com -> screenshots/www.example.com.png
  [Screenshot] https://httpbin.org -> screenshots/httpbin.org.png
  [Screenshot] https://www.wikipedia.org -> screenshots/www.wikipedia.org.png
  [Screenshot] https://github.com -> screenshots/github.com.png
  [Screenshot] https://news.ycombinator.com -> screenshots/news.ycombinator.com.png
  [Screenshot] https://www.reddit.com -> screenshots/www.reddit.com.png
  [Screenshot] https://stackoverflow.com -> screenshots/stackoverflow.com.png
  [Screenshot] https://www.google.com -> screenshots/www.google.com.png
  [Screenshot] https://www.bing.com -> screenshots/www.bing.com.png
  [Screenshot] https://www.yahoo.com -> screenshots/www.yahoo.com.png

[Result] 10 succeeded, 0 failed in 8.5s
[Result] Average: 0.85s per page

[Cluster] Shutting down...
[Cluster] Shutdown complete. 5 instances terminated.

Done.
```

With 5 instances processing 10 pages in parallel, the total time is about 8.5 seconds (sequential execution on a single instance would take 25-30 seconds). This pattern easily scales to dozens of instances and thousands of pages.

---

## Pitfalls and Best Practices

### 1. Port Conflicts

**Problem**: Improperly closed Chrome processes hold onto ports, causing conflicts on the next launch.

**Solution**:
- Check with `is_port_available()` before launching
- Force-kill residual processes with `taskkill /F /PID` (Windows) or `kill -9` (Unix)
- Consider cleaning up old Chrome instances first:

```python
def kill_chrome_processes_on_ports(ports):
    """Clean up Chrome processes on specified ports"""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'],
                      capture_output=True)
```

### 2. Memory Management

Each Chrome instance consumes roughly 100-300MB of RAM. Ten instances means 1-3GB. Recommendation:

```python
import psutil

def estimate_max_instances(per_instance_mb=200, reserve_mb=500):
    available = psutil.virtual_memory().available // (1024 * 1024)
    return max(1, (available - reserve_mb) // per_instance_mb)
```

### 3. WebSocket Reconnection

Network instability or Chrome crashes will drop WebSocket connections:

```python
async def reconnect(instance: ChromeInstance, max_retries=3):
    """Reconnect a disconnected instance"""
    for attempt in range(max_retries):
        try:
            instance.ws_url = get_ws_url('127.0.0.1', instance.port)
            await instance.connect()
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)
    return False
```

### 4. Temporary Directory Cleanup

Directories created with `tempfile.mkdtemp()` are **NOT automatically deleted**. Always call `shutil.rmtree()` in `shutdown()`. For crash recovery, set up a cron job or scheduled task:

```bash
# Clean up Chrome temp dirs older than 1 hour
find /tmp -name "chrome_*" -type d -mmin +60 -exec rm -rf {} + 2>/dev/null
```

### 5. Choosing the Right Headless Mode

Chrome 112+ introduced `--headless=new`, which is much closer to headed mode than the old `--headless`:

| Feature | Old headless | New headless (--headless=new) |
|---------|-------------|------------------------------|
| User-Agent | Contains "Headless" | Normal |
| WebGL support | No | Yes |
| Extension support | No | Yes |
| Screenshot accuracy | May differ | Matches headed mode |

**For crawling/anti-bot scenarios, strongly prefer `--headless=new`**.

### 6. Setting Proper Timeouts

```python
# 1. Cluster initialization timeout
await asyncio.wait_for(
    cluster.start(),
    timeout=30
)

# 2. Per-task timeout
result = await asyncio.wait_for(
    task_fn(instance),
    timeout=60
)

# 3. Full cluster shutdown timeout
await asyncio.wait_for(
    cluster.shutdown(),
    timeout=10
)
```

### 7. Logging and Monitoring

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('cluster.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('cluster')

async def monitor_loop(cluster, interval=10):
    while True:
        busy = sum(1 for i in cluster.instances if i.is_busy)
        total_tasks = sum(i.task_count for i in cluster.instances)
        logger.info(f'Status: {busy}/{len(cluster.instances)} busy, '
                     f'{total_tasks} tasks completed')
        await asyncio.sleep(interval)
```

---

## Summary

Through this article, you have mastered the core skills of CDP multi-instance orchestration:

- **Multi-instance vs multi-tab**: Understanding process-level isolation and when to use each
- **Port and process management**: Assigning unique ports and tracking PIDs
- **Launch and discovery**: subprocess launch + HTTP-based WebSocket URL discovery
- **Connection pooling**: asyncio WebSocket connection management
- **Task distribution strategies**: Round-robin, least-loaded, weighted
- **Graceful shutdown**: SIGTERM + temp directory cleanup
- **Complete framework**: `ChromeClusterManager` class encapsulating all logic
- **Real use case**: Parallel screenshot of 10 pages, 3-4x speedup

### Expansion Directions

| Direction | Application Scenarios |
|-----------|----------------------|
| **Distributed Crawler** | Per-instance IP/fingerprint, parallel scraping, reduced blocking |
| **Multi-Account Automation** | One login state per instance, interference-free batch operations |
| **E2E Parallel Testing** | Split test cases across instances, dramatically shorten CI time |
| **Ad Verification** | Chrome instances from different regions/IPs verifying ad delivery |
| **Performance Benchmarking** | Aligned environments, parallel benchmark runs, statistical aggregation |

> **Core principle**: Multi-instance is a "heavy weapon" — higher memory overhead and slower startup — but the isolation and parallelism it provides are impossible to achieve with multi-tab alone. Choose the right granularity for your scenario: use multi-tab for lightweight daily tasks; deploy multi-instance when you need isolation, high-performance parallelism, or anti-detection capabilities.

---

*This article is a special topic on multi-instance orchestration in the "CDP Automation Guide" series. Future topics will include distributed crawler cluster setup and dynamic instance scaling — stay tuned.*
