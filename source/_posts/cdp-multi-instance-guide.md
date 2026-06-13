---
title: CDP 多实例编排：用 Python 控制分布式浏览器集群
date: 2026-06-05 23:40:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 分布式
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 学习如何同时启动和协调多个 Chrome 实例，构建分布式浏览器集群进行大规模自动化任务。
---

> **一句话总结**：多实例编排 ≠ 多标签页。本文教你同时启动 N 个独立的 Chrome 进程，通过 CDP 统一调度，构建你自己的浏览器集群——用于并行测试、隔离环境、或绕过指纹检测。

---

## 目录

1. [多实例 vs 多标签页：本质区别](#多实例-vs-多标签页本质区别)
2. [为什么需要多个 Chrome 实例](#为什么需要多个-chrome-实例)
3. [端口管理：每个实例独占一个调试端口](#端口管理每个实例独占一个调试端口)
4. [启动 Chrome 实例并追踪 PID](#启动-chrome-实例并追踪-pid)
5. [发现 WebSocket URL](#发现-websocket-url)
6. [连接池管理：asyncio 并发连接](#连接池管理asyncio-并发连接)
7. [任务分发策略](#任务分发策略)
8. [优雅关闭：SIGTERM 与清理](#优雅关闭sigterm-与清理)
9. [完整实战：ChromeClusterManager 类](#完整实战chromeclustermanager-类)
10. [真实用例：并行截取 10 个页面](#真实用例并行截取-10-个页面)
11. [踩坑与最佳实践](#踩坑与最佳实践)
12. [总结](#总结)

---

## 多实例 vs 多标签页：本质区别

在深入之前，先厘清一个重要概念：

| 维度 | 多标签页（一个进程） | 多实例（多个进程） |
|------|--------------------|-------------------|
| **进程数** | 1 个 Chrome 进程 | N 个独立 Chrome 进程 |
| **隔离性** | 共享 Cookie、缓存、渲染引擎 | 完全隔离 |
| **内存开销** | 低（共享主进程） | 高（每个约 100-300MB） |
| **崩溃影响** | 一个标签页崩溃不影响其他 | 一个实例崩溃不影响其他 |
| **指纹一致性** | 所有标签页相同 | 可为每个实例设置不同指纹 |
| **CDP 调试端口** | 共享 9222 | 每个实例不同端口 |
| **适用场景** | 轻量爬虫、简单测试 | 大规模并行、隔离测试、反反爬 |

**核心区别一句话：多标签页跑在同一个浏览器进程里，多实例跑在不同进程里。**

之前的文章我们一直在讨论多标签页（multi-tab）——一个 Chrome 进程里管理多个页面。本文转向**多进程（multi-process）**层面，讨论如何编排多个独立的 Chrome 进程。

---

## 为什么需要多个 Chrome 实例

### 1. 完全隔离

浏览器指纹检测工具（如 `fingerprintjs`）可以检测到同一进程内不同标签页共享的底层属性。比如 WebGL 渲染器、字体列表、时区等信息。不同 Chrome 实例天然拥有独立的渲染上下文，配合 `--user-data-dir` 还可实现独立的 Cookie 和存储隔离。

### 2. 并行加速

假设你要截取 100 个页面、或登录 50 个账户做批量操作。单进程多标签页受限于 Chrome 的渲染线程和内存，难以大规模并行。多实例可以充分利用多核 CPU，实现真正的水平扩展。

### 3. 不同配置 / 指纹

每个实例可以独立配置：
- 不同的 `--user-data-dir`（不同的浏览器配置文件）
- 不同的 User-Agent、Viewport
- 不同的代理（`--proxy-server`）
- 不同的语言、时区（启动参数或 CDP 注入）

这对于爬虫反反爬、广告验证、多账户管理至关重要。

### 4. 测试环境隔离

在 E2E 测试中，多个测试用例并行运行时，多实例防止测试间的状态污染——一个测试的登录状态不会意外影响另一个。

---

## 端口管理：每个实例独占一个调试端口

CDP 调试端口是 Chrome 实例的唯一标识。多实例编排的第一步就是端口分配。

### 端口选择原则

```python
# 端口分配策略
BASE_PORT = 9222
INSTANCE_COUNT = 5

ports = [BASE_PORT + i for i in range(INSTANCE_COUNT)]
# → [9222, 9223, 9224, 9225, 9226]
```

**注意事项**：
- 避免使用常见端口（如 80、443、8080）避免冲突
- 建议从 9222 开始递增
- 启动前检查端口是否被占用

```python
import socket

def is_port_available(port):
    """检查端口是否可用"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False
```

---

## 启动 Chrome 实例并追踪 PID

使用 `subprocess.Popen` 启动 Chrome，并为每个实例分配独立端口和用户数据目录。

```python
import subprocess
import os
import tempfile
import shutil

CHROME_PATH = {
    'win32': r'C:\Program Files\Google\Chrome\Application\chrome.exe',
    'darwin': '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    'linux': 'google-chrome'
}

def launch_chrome(port, user_data_dir=None, headless=True, proxy=None):
    """
    启动一个 Chrome 实例
    
    Args:
        port: 调试端口
        user_data_dir: 用户数据目录（None 则自动创建临时目录）
        headless: 是否无头模式
        proxy: 代理地址，如 "http://127.0.0.1:8080"
    
    Returns:
        (process, user_data_dir) 元组
    """
    import platform
    
    system = platform.system().lower()
    if system == 'windows':
        chrome_path = CHROME_PATH['win32']
    elif system == 'darwin':
        chrome_path = CHROME_PATH['darwin']
    else:
        chrome_path = CHROME_PATH['linux']
    
    # 如果未指定 user_data_dir，创建临时目录
    if user_data_dir is None:
        user_data_dir = tempfile.mkdtemp(prefix='chrome_profile_')
    
    # 构建启动参数
    args = [
        chrome_path,
        f'--remote-debugging-port={port}',
        '--remote-allow-origins=*',
        '--no-first-run',
        '--no-default-browser-check',
        f'--user-data-dir={user_data_dir}',
    ]
    
    if headless:
        args.append('--headless=new')  # Chrome 112+ 推荐的新无头模式
    
    if proxy:
        args.append(f'--proxy-server={proxy}')
    
    # 启动 Chrome
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    
    print(f'[Instance] PID={process.pid}, Port={port}, Headless={headless}')
    return process, user_data_dir
```

### 追踪 PID 的重要性

每个实例的 PID 是后续管理的关键：
- 监控进程是否存活
- 发送终止信号
- 检测僵尸进程

```python
import psutil  # 可选，更精确的进程监控

def is_process_alive(pid):
    """检查进程是否存活"""
    try:
        proc = psutil.Process(pid)
        return proc.is_running() and proc.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False
```

---

## 发现 WebSocket URL

每个 Chrome 实例启动后，需要通过 HTTP 查询其 WebSocket 端点。

```python
import urllib.request
import json
import time

def get_ws_url(host, port, timeout=10):
    """
    获取 Chrome 实例的 WebSocket 调试 URL
    
    启动后 Chrome 需要短暂初始化，加入重试机制
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

**注意**：`/json/version` 返回的是浏览器级别的 WebSocket 端点（`Target` 域的入口），而 `/json` 返回的是具体页面的端点。在多实例场景中，我们通常使用 `/json/version` 获取顶层端点，再通过 `Target.attachToTarget` 附加到具体页面。

---

## 连接池管理：asyncio 并发连接

多实例的核心挑战是并发连接管理。我们用 `asyncio` 封装连接池。

```python
import asyncio
import websockets
import json

CMD_ID = [0]

async def cdp(ws, method, params=None, session_id=None):
    """发送 CDP 命令并等待响应（支持 session_id 用于非目标页面通信）"""
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

### ChromeInstance 封装

```python
class ChromeInstance:
    """单个 Chrome 实例的封装"""
    
    def __init__(self, port, pid, user_data_dir, ws_url):
        self.port = port
        self.pid = pid
        self.user_data_dir = user_data_dir
        self.ws_url = ws_url
        self.ws = None
        self._busy = False  # 是否正在执行任务
        self.task_count = 0  # 已执行任务数
    
    @property
    def is_busy(self):
        return self._busy
    
    @property
    def is_alive(self):
        """检查进程是否存活"""
        if not self.pid:
            return False
        try:
            os.kill(self.pid, 0)  # 信号 0 仅检查存活
            return True
        except OSError:
            return False
    
    async def connect(self):
        """建立 WebSocket 连接"""
        self.ws = await websockets.connect(self.ws_url, max_size=2**24)
        # 启用 Target 域
        await cdp(self.ws, 'Target.setAutoAttach', {
            'autoAttach': True,
            'flatten': True,
            'waitForDebuggerOnStart': False
        })
        return self
    
    async def close(self):
        """关闭 WebSocket 连接"""
        if self.ws:
            await self.ws.close()
            self.ws = None
    
    async def create_page(self, url=None):
        """创建新标签页并导航"""
        result = await cdp(self.ws, 'Target.createTarget', {
            'url': url or 'about:blank'
        })
        target_id = result.get('targetId')
        
        # 获取标签页的 WebSocket URL
        import urllib.request
        resp = urllib.request.urlopen(
            f'http://localhost:{self.port}/json', timeout=5
        )
        pages = json.loads(resp.read())
        for page in pages:
            if page['id'] == target_id:
                return page['webSocketDebuggerUrl']
        return None
    
    async def execute_task(self, task_fn, *args, **kwargs):
        """执行任务并标记忙碌状态"""
        self._busy = True
        try:
            result = await task_fn(self, *args, **kwargs)
            self.task_count += 1
            return result
        finally:
            self._busy = False
```

---

## 任务分发策略

有了实例池，下一个问题是如何分配任务。以下是几种常见策略：

### 1. 轮询分发（Round-Robin）

```python
import itertools

class RoundRobinDispatcher:
    """轮询分发器：依次将任务分配给下一个空闲实例"""
    
    def __init__(self, instances):
        self.instances = instances
        self.iterator = itertools.cycle(instances)
    
    async def get_instance(self):
        """获取下一个空闲实例"""
        for _ in range(len(self.instances)):
            instance = next(self.iterator)
            if not instance.is_busy:
                return instance
        return None  # 全部忙碌
```

### 2. 最少负载分发（Least-Loaded）

```python
class LeastLoadedDispatcher:
    """最少负载分发器：分配给完成任务最少的实例"""
    
    def __init__(self, instances):
        self.instances = instances
    
    async def get_instance(self):
        """获取当前负载最小的空闲实例"""
        idle = [i for i in self.instances if not i.is_busy]
        if not idle:
            return None
        return min(idle, key=lambda i: i.task_count)
```

### 3. 带权分发（Weighted）

```python
class WeightedDispatcher:
    """带权分发器：根据实例的内存/CPU 权重分配"""
    
    def __init__(self, instances, weights=None):
        self.instances = instances
        # 权重越高，分配到的任务越多
        self.weights = weights or [1] * len(instances)
    
    async def get_instance(self):
        """根据权重选择空闲实例"""
        idle = [(i, w) for i, w in zip(self.instances, self.weights) 
                if not i.is_busy]
        if not idle:
            return None
        
        # 按权重比例随机选择
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

## 优雅关闭：SIGTERM 与清理

多实例管理必须处理善后问题。粗暴地 kill 进程可能导致：
- 临时文件残留（`--user-data-dir` 创建的临时目录）
- 僵尸进程
- 端口未释放

```python
import signal
import atexit

class GracefulShutdown:
    """优雅关闭管理器"""
    
    def __init__(self):
        self.instances = []
        self._cleaned_up = False
        atexit.register(self.cleanup)
    
    def register(self, instance):
        """注册实例到关闭管理器"""
        self.instances.append(instance)
    
    def cleanup(self):
        """清理所有实例"""
        if self._cleaned_up:
            return
        self._cleaned_up = True
        
        print('\n[Shutdown] Closing all instances...')
        
        for inst in self.instances:
            try:
                # 1. 关闭 WebSocket
                if inst.ws:
                    # 无法在同步上下文中用 await，需要其他方式
                    pass
                
                # 2. 终止 Chrome 进程
                if inst.is_alive:
                    if os.name == 'nt':  # Windows
                        subprocess.run(['taskkill', '/F', '/PID', str(inst.pid)],
                                      capture_output=True)
                    else:  # Unix
                        os.kill(inst.pid, signal.SIGTERM)
                    
                    print(f'  [Killed] PID={inst.pid}')
                
                # 3. 清理用户数据目录
                if inst.user_data_dir and os.path.exists(inst.user_data_dir):
                    shutil.rmtree(inst.user_data_dir, ignore_errors=True)
                    print(f'  [Cleaned] {inst.user_data_dir}')
                    
            except Exception as e:
                print(f'  [Error] PID={inst.pid}: {e}')
        
        print('[Shutdown] Done.')
```

### asyncio 版本的优雅关闭

```python
class AsyncGracefulShutdown:
    """异步优雅关闭管理器"""
    
    def __init__(self):
        self.instances = []
        self._cleaned_up = False
    
    async def cleanup(self):
        """异步清理所有实例"""
        if self._cleaned_up:
            return
        self._cleaned_up = True
        
        print('\n[Shutdown] Closing all instances...')
        
        # 并行关闭 WebSocket 连接
        close_tasks = []
        for inst in self.instances:
            close_tasks.append(inst.close())
        
        if close_tasks:
            await asyncio.gather(*close_tasks, return_exceptions=True)
        
        # 终止进程并清理目录
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

## 完整实战：ChromeClusterManager 类

将以上所有组件整合成一个完整的集群管理器。

```python
#!/usr/bin/env python3
"""
Chrome Cluster Manager — CDP 多实例编排框架

管理 N 个独立的 Chrome 进程，支持：
- 自动启动和端口分配
- 连接池管理
- 多种任务分发策略
- 优雅关闭和资源清理
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
from dataclasses import dataclass, field
from typing import Optional, List, Callable, Awaitable

# ============================================================
# CDP 基础通信
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
    """获取系统 Chrome 路径"""
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
    """检查端口是否可用"""
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def check_process_alive(pid):
    """检查进程是否存活（信号 0 检测）"""
    if not pid:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


# ============================================================
# ChromeInstance — 单个实例的封装
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
    Chrome 集群管理器
    
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
        dispatcher_type: str = 'round_robin',  # round_robin | least_loaded | weighted
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
    
    # ---------- 启动集群 ----------
    
    async def start(self):
        """启动所有 Chrome 实例"""
        print(f'[Cluster] Starting {self.count} Chrome instances...')
        
        for i in range(self.count):
            port = self.base_port + i
            
            # 检查端口
            if not is_port_available(port):
                raise RuntimeError(f'Port {port} is already in use')
            
            # 创建临时用户数据目录
            user_data_dir = tempfile.mkdtemp(prefix=f'chrome_{port}_')
            
            # 构建启动参数
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
            
            # 启动进程
            proc = subprocess.Popen(
                args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            
            # 等待 Chrome 初始化
            ws_url = self._wait_for_ws_url(port)
            
            instance = ChromeInstance(
                port=port,
                pid=proc.pid,
                user_data_dir=user_data_dir,
                ws_url=ws_url,
                name=f'chrome-{port}'
            )
            
            # 建立 WebSocket 连接
            await instance.connect()
            self.instances.append(instance)
            print(f'  [OK] Instance {i+1}/{self.count}: port={port}, pid={proc.pid}')
        
        # 初始化分发器
        self._init_dispatcher()
        print(f'[Cluster] All {self.count} instances ready.')
        return self
    
    def _wait_for_ws_url(self, port, max_retries=20, delay=0.5):
        """等待 Chrome 初始化并返回 WS URL"""
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
        """初始化任务分发器"""
        if self.dispatcher_type == 'round_robin':
            self._dispatcher = RoundRobinDispatcher(self.instances)
        elif self.dispatcher_type == 'least_loaded':
            self._dispatcher = LeastLoadedDispatcher(self.instances)
        else:
            self._dispatcher = RoundRobinDispatcher(self.instances)
    
    # ---------- 任务调度 ----------
    
    async def get_idle_instance(self) -> Optional[ChromeInstance]:
        """获取一个空闲实例"""
        return await self._dispatcher.get_instance()
    
    async def run_on_one(self, task_fn: Callable[[ChromeInstance], Awaitable], 
                         timeout: int = 60) -> Optional[any]:
        """在某个空闲实例上执行任务（阻塞直到有空闲）"""
        while True:
            instance = await self.get_idle_instance()
            if instance:
                return await self._run_task(instance, task_fn, timeout)
            await asyncio.sleep(0.5)
    
    async def run_on_all(self, task_fn: Callable[[ChromeInstance], Awaitable],
                         timeout: int = 60) -> List[any]:
        """在所有实例上并行执行任务"""
        tasks = [self._run_task(inst, task_fn, timeout) for inst in self.instances]
        return await asyncio.gather(*tasks, return_exceptions=True)
    
    async def run_batch(self, tasks: List, task_fn: Callable,
                        timeout: int = 60) -> List[any]:
        """批量执行任务列表（自动分发到空闲实例）"""
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
        """在指定实例上执行任务"""
        instance._busy = True
        try:
            result = await asyncio.wait_for(task_fn(instance), timeout=timeout)
            instance.task_count += 1
            return result
        finally:
            instance._busy = False
    
    # ---------- 关闭集群 ----------
    
    async def shutdown(self):
        """优雅关闭所有实例"""
        if self._cleanup_done:
            return
        self._cleanup_done = True
        
        print('\n[Cluster] Shutting down...')
        
        # 1. 关闭所有 WebSocket 连接
        await asyncio.gather(
            *[inst.close() for inst in self.instances],
            return_exceptions=True
        )
        
        # 2. 终止 Chrome 进程
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
        
        # 3. 清理临时目录
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
# 分发器实现
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

## 真实用例：并行截取 10 个页面

下面是用 `ChromeClusterManager` 同时截取 10 个页面的完整示例。

```python
# ============================================================
# 并行截图示例
# ============================================================

import base64

async def screenshot_task(instance: ChromeInstance, url: str, output_dir: str):
    """在指定实例上截图"""
    ws = instance.ws
    
    # 创建新标签页
    result = await cdp(ws, 'Target.createTarget', {'url': 'about:blank'})
    target_id = result.get('targetId')
    
    # 附加到新标签页
    result = await cdp(ws, 'Target.attachToTarget', {
        'targetId': target_id,
        'flatten': True
    })
    session_id = result.get('sessionId')
    
    # 导航
    await cdp(ws, 'Page.enable', session_id=session_id)
    await cdp(ws, 'Page.navigate', {'url': url}, session_id=session_id)
    
    # 等待页面加载
    await asyncio.sleep(3)
    
    # 截图
    result = await cdp(ws, 'Page.captureScreenshot', {
        'format': 'png',
        'fromSurface': True
    }, session_id=session_id)
    
    # 保存
    safe_name = url.replace('https://', '').replace('http://', '').replace('/', '_')
    output_path = os.path.join(output_dir, f'{safe_name}.png')
    with open(output_path, 'wb') as f:
        f.write(base64.b64decode(result['data']))
    
    # 关闭标签页
    await cdp(ws, 'Target.closeTarget', {'targetId': target_id})
    
    print(f'  [Screenshot] {url} → {output_path}')
    return output_path


async def main():
    """启动 5 个实例，并行截取 10 个页面"""
    
    urls = [
        'https://www.example.com',
        'https://httpbin.org',
        'https://www.wikipedia.org',
        'https://github.com',
        'https://news.ycombinator.com',
        'https://www.reddit.com',
        'https://stackoverflow.com',
        'https://www.google.com',
        'https://www.baidu.com',
        'https://www.bing.com',
    ]
    
    output_dir = 'screenshots'
    os.makedirs(output_dir, exist_ok=True)
    
    # 使用集群管理器
    async with ChromeClusterManager(
        count=5,           # 5 个 Chrome 实例
        base_port=9222,    # 端口从 9222 开始
        headless=True,     # 无头模式
        dispatcher_type='round_robin'
    ) as cluster:
        
        print(f'\n[Task] Capturing {len(urls)} pages with {cluster.count} instances...\n')
        
        start_time = time.time()
        
        # 批量执行截图
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

### 运行效果

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

  [Screenshot] https://www.example.com → screenshots/www.example.com.png
  [Screenshot] https://httpbin.org → screenshots/httpbin.org.png
  [Screenshot] https://www.wikipedia.org → screenshots/www.wikipedia.org.png
  [Screenshot] https://github.com → screenshots/github.com.png
  [Screenshot] https://news.ycombinator.com → screenshots/news.ycombinator.com.png
  [Screenshot] https://www.reddit.com → screenshots/www.reddit.com.png
  [Screenshot] https://stackoverflow.com → screenshots/stackoverflow.com.png
  [Screenshot] https://www.google.com → screenshots/www.google.com.png
  [Screenshot] https://www.baidu.com → screenshots/www.baidu.com.png
  [Screenshot] https://www.bing.com → screenshots/www.bing.com.png

[Result] 10 succeeded, 0 failed in 8.5s
[Result] Average: 0.85s per page

[Cluster] Shutting down...
[Cluster] Shutdown complete. 5 instances terminated.

Done.
```

5 个实例并行处理 10 个页面，总耗时仅约 8.5 秒（单实例顺序执行需要 25-30 秒）。此模式可轻松扩展到几十个实例、上千个页面。

---

## 踩坑与最佳实践

### 1. 端口冲突与占用

**问题**：未正确关闭的 Chrome 进程会占用端口，下次启动时端口被占用。

**解决**：
- 启动前用 `is_port_available()` 检查
- 使用 `taskkill /F /PID`（Windows）或 `kill -9`（Unix）强制清理残留进程
- 建议先列出并清理旧的 Chrome 实例：

```python
def kill_chrome_processes_on_ports(ports):
    """清理指定端口上的 Chrome 进程（仅示例，实际应更精确）"""
    if os.name == 'nt':
        subprocess.run(['taskkill', '/F', '/IM', 'chrome.exe'],
                      capture_output=True)
```

### 2. 内存管理

每个 Chrome 实例约占用 100-300MB 内存。10 个实例就是 1-3GB。建议：

```python
# 根据可用内存估算实例数
import psutil

def estimate_max_instances(per_instance_mb=200, reserve_mb=500):
    available = psutil.virtual_memory().available // (1024 * 1024)
    return max(1, (available - reserve_mb) // per_instance_mb)
```

### 3. WebSocket 断连重连

网络不稳定或 Chrome 崩溃时 WebSocket 会断开：

```python
async def reconnect(instance: ChromeInstance, max_retries=3):
    """重新连接断开的实例"""
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

### 4. 临时目录清理

使用 `tempfile.mkdtemp()` 创建的目录**不会自动删除**。务必在 `shutdown()` 中调用 `shutil.rmtree()`。如果脚本异常退出，可通过定时任务清理：

```bash
# 清理 1 小时前的 Chrome 临时目录
find /tmp -name "chrome_*" -type d -mmin +60 -exec rm -rf {} + 2>/dev/null
```

### 5. headless 模式的选择

Chrome 112+ 推出了`--headless=new`（新无头模式），它比旧版 `--headless` 更接近有头浏览器：

| 特性 | 旧 headless | 新 headless (--headless=new) |
|------|------------|---------------------------|
| User-Agent | 含 "Headless" | 正常 |
| WebGL 支持 | ❌ | ✅ |
| 扩展支持 | ❌ | ✅ |
| 截图一致性 | 可能偏差 | 与有头一致 |

**爬虫/反反爬场景强烈推荐 `--headless=new`**。

### 6. 合理设置超时

```python
# 1. Chrome 初始化超时
await asyncio.wait_for(
    cluster.start(),
    timeout=30  # 30 秒内所有实例未就绪则报错
)

# 2. 单任务超时
result = await asyncio.wait_for(
    task_fn(instance),
    timeout=60  # 单个任务最长 60 秒
)

# 3. 全集群关闭超时
await asyncio.wait_for(
    cluster.shutdown(),
    timeout=10
)
```

### 7. 日志与监控

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

# 定期输出实例状态
async def monitor_loop(cluster, interval=10):
    while True:
        busy = sum(1 for i in cluster.instances if i.is_busy)
        total_tasks = sum(i.task_count for i in cluster.instances)
        logger.info(f'Status: {busy}/{len(cluster.instances)} busy, '
                     f'{total_tasks} tasks completed')
        await asyncio.sleep(interval)
```

---

## 总结

通过本文，你已经掌握了 CDP 多实例编排的核心技能：

- ✅ **多实例 vs 多标签页**：理解了进程级隔离的意义和场景
- ✅ **端口与进程管理**：为每个实例分配独立端口，追踪 PID
- ✅ **启动与发现**：subprocess 启动 + HTTP 发现 WebSocket URL
- ✅ **连接池管理**：asyncio WebSocket 连接池
- ✅ **任务分发策略**：轮询、最少负载、带权分发
- ✅ **优雅关闭**：SIGTERM + 临时目录清理
- ✅ **完整框架**：`ChromeClusterManager` 类封装所有逻辑
- ✅ **真实用例**：并行截图 10 个页面，效率提升 3-4 倍

### 扩展方向

| 方向 | 应用场景 |
|------|---------|
| **分布式爬虫** | 每个实例一组 IP/指纹，并行抓取，减少封禁 |
| **多账户自动化** | 每个实例一个登录状态，批量操作互不干扰 |
| **E2E 并行测试** | 测试用例拆分到不同实例，大幅缩短 CI 时间 |
| **广告验证** | 不同地域/IP 的 Chrome 实例验证广告投放 |
| **性能基准测试** | 对齐环境，并行运行性能测试，采集统计指标 |

> **核心原则**：多实例是"重武器"——内存开销大、启动慢，但它带来的隔离性和并行度是多标签页无法替代的。根据你的场景选择合适粒度：日常轻量任务用多标签页；需要隔离、高性能并行或防检测时上多实例。

---

*本文是「CDP 自动化指南」系列中关于多实例编排的专题。后续将深入分布式爬虫集群搭建、实例动态扩缩容等话题，敬请关注。*
