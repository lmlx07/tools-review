---
title: CDP 协议扩展指南：自定义 CDP 域与 Chrome 扩展
date: 2026-06-05 15:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Chrome 扩展
  - 协议扩展
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 深入探讨 CDP 的可扩展性架构——如何通过 Chrome 扩展集成 CDP、注入自定义命令、构建中间件模式以及设计自定义事件分发系统。
---

> **一句话总结**：CDP 的架构天然支持扩展——你可以通过 Chrome 扩展的 `chrome.debugger` API 接入 CDP，利用 `Runtime.evaluate` 注入自定义行为，并通过中间件模式构建强大的拦截与事件系统。

---

## 目录

1. [CDP 的可扩展性架构](#cdp-的可扩展性架构)
2. [Chrome 扩展中的 CDP 集成](#chrome-扩展中的-cdp-集成)
3. [通过 Runtime.evaluate 注入自定义命令](#通过runtimeevaluate-注入自定义命令)
4. [中间件模式：拦截与修改 CDP 流量](#中间件模式拦截与修改-cdp-流量)
5. [自定义事件分发系统](#自定义事件分发系统)
6. [SessionObserver：监控多个会话](#sessionobserver监控多个会话)
7. [最佳实践与架构建议](#最佳实践与架构建议)

---

## CDP 的可扩展性架构

CDP 的设计并非封闭的——它基于 JSON-RPC 2.0 协议，天然支持扩展。理解 CDP 的可扩展性，首先需要理解其核心架构层次：

| 层次 | 说明 | 扩展方式 |
|------|------|----------|
| 传输层 | WebSocket 连接 | 可代理、拦截、修改 |
| 消息层 | JSON-RPC 2.0 消息 | 可注入自定义方法/事件 |
| 域层 | 按功能划分的域（Domain） | 可使用现有域组合或扩展 |
| 执行层 | V8 引擎中的 JavaScript | 通过 Runtime.evaluate 注入 |

CDP 的每个域本质上是一组方法（commands）和事件（events）的集合。虽然你不能直接在 Chrome 中注册新的 CDP 域，但你可以：

1. **通过 Chrome 扩展的 `chrome.debugger` API**——获得 CDP 会话授权
2. **通过 `Runtime.evaluate` 注入**——在页面上下文中执行任意 JS 代码以模拟新功能
3. **通过代理/中间件模式**——在 CDP 消息传输过程中拦截并修改
4. **通过自定义事件分发**——在注入的代码中使用 `CustomEvent` 模拟 CDP 事件流

这种多层次的可扩展性使 CDP 远超简单的自动化工具，成为一个可编程的浏览器控制平台。

---

## Chrome 扩展中的 CDP 集成

### chrome.debugger API 基础

Chrome 扩展可以通过 `chrome.debugger` API 连接到任意标签页并获取其 CDP 会话。这是原生扩展集成 CDP 的标准方式：

```python
# 以下代码演示了用 Python 模拟 Chrome 扩展 CDP 集成的概念
# 实际扩展中使用的是 JavaScript 的 chrome.debugger API

import asyncio
import websockets
import json

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


async def attach_to_target(ws, url_pattern=None):
    """通过 Target 域附加到页面模拟扩展行为"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets.get("targetInfos", []):
        if target["type"] == "page":
            if url_pattern is None or url_pattern in target.get("url", ""):
                result = await cdp(ws, "Target.attachToTarget", {
                    "targetId": target["targetId"],
                    "flatten": True
                })
                return result["sessionId"], target["targetId"]
    return None, None
```

### 扩展 CDP 模式：扩展权限模型

Chrome 扩展中的 `chrome.debugger` API 提供了比远程 CDP 更丰富的权限控制：

```python
async def simulate_extension_debugger_pattern(ws):
    """模拟 Chrome 扩展的 debugger 权限模式"""
    # 扩展可以附加到特定标签页（而不是浏览器的所有页面）
    targets = await cdp(ws, "Target.getTargets")
    
    # 扩展典型地选择当前活动标签
    for target in targets.get("targetInfos", []):
        if target["type"] == "page" and target.get("attached") is False:
            session_id, _ = attach_to_target_simple(ws, target["targetId"])
            
            # 扩展可以限定域权限
            # chrome.debugger.attach({tabId: tabId}, "1.3", callback)
            await cdp(ws, "Network.enable", {}, session_id)
            await cdp(ws, "Runtime.enable", {}, session_id)
            
            # 以下域在某些扩展场景中需要特别权限
            # - Page.enable: 需要 tabs 权限
            # - Debugger.enable: 需要 debugger 权限
            # - Target.attachToTarget: 需要目标页面访问权限
            break


def attach_to_target_simple(ws, target_id):
    """附加到指定目标"""
    # 使用 flatten 模式获得扁平化会话
    return target_id
```

### 扩展 CDP 的消息拦截

扩展可以在 CDP 消息到达 Chrome 之前或之后进行拦截处理，这是实现自定义行为的关键模式：

```python
class CDPMessageInterceptor:
    """CDP 消息拦截器——模拟扩展的 onMessage 回调"""
    
    def __init__(self):
        self.handlers = {}
        self.command_interceptors = []
        self.event_interceptors = []
    
    def on_command(self, method):
        """注册命令拦截器"""
        def decorator(handler):
            self.command_interceptors.append((method, handler))
            return handler
        return decorator
    
    def on_event(self, event_name):
        """注册事件拦截器"""
        def decorator(handler):
            self.event_interceptors.append((event_name, handler))
            return handler
        return decorator
    
    async def intercept_send(self, ws, method, params, session_id=None):
        """发送前拦截"""
        modified_method = method
        modified_params = params
        
        for pattern, handler in self.command_interceptors:
            if pattern in method:
                result = await handler(method, params, session_id)
                if result:
                    modified_method = result.get("method", modified_method)
                    modified_params = result.get("params", modified_params)
        
        await cdp(ws, modified_method, modified_params, session_id)
    
    async def intercept_receive(self, data):
        """接收后拦截"""
        for pattern, handler in self.event_interceptors:
            if pattern in data.get("method", ""):
                await handler(data)
        return data
```

---

## 通过 Runtime.evaluate 注入自定义命令

### 注入模式基础

`Runtime.evaluate` 是在页面中执行任意 JavaScript 的最强大方式。通过它，你可以构建出"自定义 CDP 命令"的效果：

```python
class CustomCDPCommands:
    """通过 Runtime.evaluate 模拟自定义 CDP 命令"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
    
    async def evaluate(self, expression):
        """执行 JS 表达式"""
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": expression,
            "returnByValue": True
        }, self.session_id)
        return result.get("result", {})
    
    async def inject_get_all_network_requests(self):
        """注入自定义命令：获取所有网络请求"""
        js = """
        (() => {
            if (window.__cdp_network_requests) {
                return JSON.stringify(window.__cdp_network_requests);
            }
            window.__cdp_network_requests = [];
            const originalOpen = XMLHttpRequest.prototype.open;
            XMLHttpRequest.prototype.open = function(...args) {
                window.__cdp_network_requests.push({
                    type: 'xhr',
                    method: args[0],
                    url: args[1],
                    timestamp: Date.now()
                });
                return originalOpen.apply(this, args);
            };
            
            // 拦截 fetch
            const originalFetch = window.fetch;
            window.fetch = function(...args) {
                window.__cdp_network_requests.push({
                    type: 'fetch',
                    url: typeof args[0] === 'string' ? args[0] : args[0].url,
                    timestamp: Date.now()
                });
                return originalFetch.apply(this, args);
            };
            
            return JSON.stringify([]);
        })()
        """
        return await self.evaluate(js)
    
    async def get_custom_storage_usage(self):
        """注入自定义命令：获取详细存储使用情况"""
        js = """
        (async () => {
            const estimates = await navigator.storage.estimate();
            const cookies = document.cookie;
            const localStorageKeys = Object.keys(localStorage);
            const sessionStorageKeys = Object.keys(sessionStorage);
            const cacheNames = await caches.keys();
            
            return JSON.stringify({
                storage: {
                    usage: estimates.usage,
                    quota: estimates.quota,
                    usagePercent: ((estimates.usage / estimates.quota) * 100).toFixed(2)
                },
                cookies: cookies ? cookies.split(';').length : 0,
                localStorageKeys: localStorageKeys.length,
                sessionStorageKeys: sessionStorageKeys.length,
                cacheStorageNames: cacheNames
            });
        })()
        """
        return await self.evaluate(js)
```

### 构建自定义监控域

通过组合多个 `Runtime.evaluate` 调用，你可以构建出类似原生 CDP 域的监控能力：

```python
class CustomMonitorDomain:
    """自定义监控域——完全通过 Runtime.evaluate 实现"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._event_callbacks = {}
    
    async def enable(self):
        """启用自定义监控——注入 JS 挎钩"""
        js = """
        (() => {
            window.__cdp_monitor = window.__cdp_monitor || {
                listeners: {},
                events: [],
                
                // 注册自定义事件
                addCustomListener: function(name, callback) {
                    if (!this.listeners[name]) this.listeners[name] = [];
                    this.listeners[name].push(callback);
                },
                
                // 分发自定义事件
                dispatchCustomEvent: function(name, data) {
                    this.events.push({name, data, time: Date.now()});
                    if (this.listeners[name]) {
                        this.listeners[name].forEach(cb => cb(data));
                    }
                },
                
                // 监控 DOM 变化
                startDOMMonitor: function() {
                    const observer = new MutationObserver((mutations) => {
                        this.dispatchCustomEvent('domMutation', {
                            count: mutations.length,
                            timestamp: Date.now()
                        });
                    });
                    observer.observe(document.body, {
                        childList: true,
                        subtree: true,
                        attributes: true
                    });
                    return 'DOM monitor started';
                },
                
                // 监控控制台调用
                startConsoleMonitor: function() {
                    const methods = ['log', 'warn', 'error', 'info', 'debug'];
                    methods.forEach(method => {
                        const original = console[method];
                        console[method] = function(...args) {
                            this.dispatchCustomEvent('consoleCall', {
                                method: method,
                                args: args.map(a => {
                                    try { return JSON.stringify(a); }
                                    catch(e) { return String(a); }
                                }),
                                timestamp: Date.now()
                            });
                            return original.apply(this, args);
                        };
                    });
                    return 'Console monitor started';
                }
            };
            return 'Custom monitor domain enabled';
        })()
        """
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
        return result
    
    async def start_dom_monitor(self):
        """启动 DOM 变化监控"""
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": "window.__cdp_monitor.startDOMMonitor()",
            "returnByValue": True
        }, self.session_id)
    
    async def start_console_monitor(self):
        """启动控制台监控"""
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": "window.__cdp_monitor.startConsoleMonitor()",
            "returnByValue": True
        }, self.session_id)
    
    async def get_events(self, clear=False):
        """获取累积的自定义事件"""
        js = """
        (() => {
            const events = window.__cdp_monitor.events;
            if (clear) window.__cdp_monitor.events = [];
            return JSON.stringify(events);
        })()
        """
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
        return json.loads(result.get("result", {}).get("value", "[]"))
```

---

## 中间件模式：拦截与修改 CDP 流量

### CDP 代理架构

构建一个 CDP 代理服务器是最强大的扩展方式。代理位于客户端和 Chrome 之间，可以拦截、修改、记录所有 CDP 消息：

```python
import asyncio
import json
import websockets
from datetime import datetime

class CDPProxy:
    """CDP 代理服务器——拦截并修改 CDP 流量"""
    
    def __init__(self, target_cdp_url, listen_port=9223):
        self.target_cdp_url = target_cdp_url
        self.listen_port = listen_port
        self.middleware = []
        self.command_log = []
        self.event_log = []
    
    def use(self, middleware_fn):
        """注册中间件函数"""
        self.middleware.append(middleware_fn)
    
    async def handle_client(self, client_ws):
        """处理客户端连接"""
        async with websockets.connect(self.target_cdp_url) as chrome_ws:
            async def forward_to_chrome():
                """转发客户端消息到 Chrome"""
                async for message in client_ws:
                    modified = message
                    for mw in self.middleware:
                        modified = await mw("request", modified)
                    
                    parsed = json.loads(modified)
                    self.command_log.append({
                        "time": datetime.now().isoformat(),
                        "method": parsed.get("method", "(unknown)"),
                        "id": parsed.get("id")
                    })
                    
                    await chrome_ws.send(modified)
            
            async def forward_to_client():
                """转发 Chrome 消息到客户端"""
                async for message in chrome_ws:
                    modified = message
                    for mw in self.middleware:
                        modified = await mw("response", modified)
                    
                    parsed = json.loads(modified)
                    if "method" in parsed:
                        self.event_log.append({
                            "time": datetime.now().isoformat(),
                            "method": parsed["method"],
                            "params": parsed.get("params", {})
                        })
                    
                    await client_ws.send(modified)
            
            await asyncio.gather(
                forward_to_chrome(),
                forward_to_client()
            )
    
    async def start(self):
        """启动代理服务器"""
        print(f"CDP 代理启动: ws://127.0.0.1:{self.listen_port}")
        print(f"目标 Chrome: {self.target_cdp_url}")
        async with websockets.serve(self.handle_client, "127.0.0.1", self.listen_port):
            await asyncio.Future()
```

### 实用的 CDP 中间件示例

```python
# 日志中间件
async def logging_middleware(direction, message):
    parsed = json.loads(message)
    if direction == "request":
        method = parsed.get("method", "")
        if not method.startswith("Target."):  # 过滤频繁的轮询
            print(f"[请求] {method} id={parsed.get('id')}")
    else:
        if "method" in parsed:
            print(f"[事件] {parsed['method']}")
        elif "id" in parsed:
            pass  # 命令响应
    return message


# 敏感信息过滤中间件
async def sanitize_middleware(direction, message):
    """过滤敏感信息"""
    parsed = json.loads(message)
    
    if direction == "response":
        # 在页面源码中隐藏敏感信息
        if parsed.get("method") == "Page.getResourceContent":
            params = parsed.get("params", {})
            content = params.get("content", "")
            # 替换敏感模式
            content = content.replace("API_KEY=", "API_KEY=[REDACTED]")
            content = content.replace("password=", "password=[REDACTED]")
            parsed["params"]["content"] = content
            return json.dumps(parsed)
        
        # 过滤网络请求中的 token
        if parsed.get("method") == "Network.requestWillBeSent":
            request = parsed.get("params", {}).get("request", {})
            headers = request.get("headers", {})
            if "Authorization" in headers:
                headers["Authorization"] = "[REDACTED]"
            return json.dumps(parsed)
    
    return message


# 网络拦截中间件
def create_block_middleware(block_patterns=None):
    """创建请求阻止中间件"""
    block_patterns = block_patterns or []
    
    async def block_middleware(direction, message):
        if direction != "request":
            return message
        
        parsed = json.loads(message)
        method = parsed.get("method", "")
        
        # 阻止特定 CDP 方法
        if method in block_patterns:
            # 返回一个空结果而不是转发
            response = {"id": parsed["id"], "result": {}}
            print(f"[拦截] 阻止了 {method} 请求")
            return json.dumps(response)
        
        return message
    
    return block_middleware


# 使用示例
async def demo_proxy():
    proxy = CDPProxy("ws://127.0.0.1:9222/devtools/browser/a1b2c3d4")
    proxy.use(logging_middleware)
    proxy.use(sanitize_middleware)
    proxy.use(create_block_middleware(["Target.setDiscoverTargets"]))
    await proxy.start()


# asyncio.run(demo_proxy())
```

---

## 自定义事件分发系统

### 在页面中建立 CDP 风格的事件系统

CDP 的事件机制本质上是从浏览器到客户端的一次性推送。通过 `Runtime.evaluate` 加上 JavaScript 的 `CustomEvent`，你可以在页面中建立你自己的事件分发系统：

```python
class CustomEventDispatcher:
    """自定义 CDP 风格事件分发系统"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.event_bus = {}
    
    async def create_event_domain(self, domain_name):
        """在页面中创建一个自定义事件域"""
        js = f"""
        (() => {{
            const domain = window.__cdp_custom_domains = window.__cdp_custom_domains || {{}};
            
            domain['{domain_name}'] = {{
                listeners: {{}},
                history: [],
                
                // 注册事件监听
                on(event, callback) {{
                    if (!this.listeners[event]) this.listeners[event] = [];
                    this.listeners[event].push(callback);
                }},
                
                // 触发事件
                dispatch(event, data) {{
                    const entry = {{event, data, timestamp: Date.now()}};
                    this.history.push(entry);
                    
                    if (this.listeners[event]) {{
                        this.listeners[event].forEach(cb => cb(entry));
                    }}
                    
                    // 通过 DOM CustomEvent 传递
                    document.dispatchEvent(new CustomEvent('cdp:' + '{domain_name}.' + event, {{
                        detail: data,
                        bubbles: true
                    }}));
                    
                    return entry;
                }},
                
                // 启用域
                enable() {{
                    this.enabled = true;
                    return 'Domain {domain_name} enabled';
                }},
                
                // 禁用域
                disable() {{
                    this.enabled = false;
                    return 'Domain {domain_name} disabled';
                }},
                
                // 获取历史
                getHistory() {{
                    return this.history.slice();
                }}
            }};
            
            return 'Custom domain {domain_name} created';
        }})()
        """
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
    
    async def create_network_analyzer_domain(self):
        """创建自定义网络分析域"""
        await self.create_event_domain("NetworkAnalyzer")
        
        js = """
        (() => {
            const domain = window.__cdp_custom_domains['NetworkAnalyzer'];
            
            // 监控资源加载时间
            const observer = new PerformanceObserver((list) => {
                list.getEntries().forEach(entry => {
                    domain.dispatch('resourceTiming', {
                        name: entry.name,
                        duration: entry.duration,
                        startTime: entry.startTime,
                        transferSize: entry.transferSize || 0,
                        type: entry.entryType
                    });
                });
            });
            
            observer.observe({ entryTypes: ['resource', 'navigation'] });
            
            // 监控连接变化
            const connection = navigator.connection;
            if (connection) {
                connection.addEventListener('change', () => {
                    domain.dispatch('connectionChange', {
                        effectiveType: connection.effectiveType,
                        downlink: connection.downlink,
                        rtt: connection.rtt
                    });
                });
            }
            
            return 'NetworkAnalyzer domain active with observers';
        })()
        """
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
    
    async def dispatch_custom_event(self, domain, event, data):
        """从外部触发自定义事件"""
        js = f"""
        window.__cdp_custom_domains['{domain}'].dispatch('{event}', {json.dumps(data)});
        """
        return await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
    
    async def poll_custom_events(self, domain, clear=True):
        """轮询收集自定义事件"""
        js = f"""
        (() => {{
            const history = window.__cdp_custom_domains['{domain}'].history;
            const result = JSON.parse(JSON.stringify(history));
            if ({str(clear).lower()}) {{
                history.length = 0;
            }}
            return result;
        }})()
        """
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": js,
            "returnByValue": True
        }, self.session_id)
        return json.loads(result.get("result", {}).get("value", "[]"))
```

---

## SessionObserver：监控多个会话

### 多标签页观测架构

CDP 最强大的扩展模式之一是在多个目标（标签页、iframe、worker）之间建立统一的观测层：

```python
class CDPSessionObserver:
    """多会话观测器——同时监控多个 CDP 会话"""
    
    def __init__(self, ws):
        self.ws = ws
        self.sessions = {}
        self.global_event_handlers = {}
    
    async def discover_and_attach_all(self):
        """发现并附加到所有可用的目标"""
        targets = await cdp(self.ws, "Target.getTargets")
        attached = []
        
        for target in targets.get("targetInfos", []):
            if target["type"] in ("page", "iframe", "worker", "service_worker"):
                result = await cdp(self.ws, "Target.attachToTarget", {
                    "targetId": target["targetId"],
                    "flatten": True
                })
                session_id = result["sessionId"]
                self.sessions[target["targetId"]] = {
                    "session_id": session_id,
                    "target": target,
                    "event_buffer": []
                }
                attached.append(target)
        
        return attached
    
    def on(self, method_pattern):
        """注册全局事件处理器"""
        def decorator(handler):
            self.global_event_handlers[method_pattern] = handler
            return handler
        return decorator
    
    async def listen_all(self, duration=60):
        """同时监听所有会话的事件"""
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                session_id = data.get("sessionId")
                
                # 定位来源会话
                source_target = None
                for tid, info in self.sessions.items():
                    if info["session_id"] == session_id:
                        source_target = tid
                        break
                
                # 缓冲事件
                if source_target:
                    self.sessions[source_target]["event_buffer"].append({
                        "method": method,
                        "params": data.get("params", {}),
                        "time": datetime.now().isoformat()
                    })
                
                # 触发全局处理器
                for pattern, handler in self.global_event_handlers.items():
                    if pattern in method:
                        await handler(data, source_target)
                        
            except asyncio.TimeoutError:
                continue
    
    def get_session_events(self, target_id, clear=True):
        """获取特定会话的缓冲事件"""
        if target_id not in self.sessions:
            return []
        events = self.sessions[target_id]["event_buffer"]
        if clear:
            self.sessions[target_id]["event_buffer"] = []
        return events
    
    async def execute_on_all(self, method, params=None):
        """在所有会话上执行同一命令"""
        results = {}
        for tid, info in self.sessions.items():
            result = await cdp(self.ws, method, params, info["session_id"])
            results[tid] = result
        return results
    
    async def enable_domain_on_all(self, domain_method):
        """在所有会话上启用某个域"""
        await self.execute_on_all(domain_method)
    
    async def detach_all(self):
        """分离所有会话"""
        for tid in list(self.sessions.keys()):
            await cdp(self.ws, "Target.detachFromTarget", {
                "targetId": tid
            })
        self.sessions.clear()


# 实战示例：跨标签页监控
async def cross_tab_monitor_demo():
    async with websockets.connect(CDP_URL) as ws:
        observer = CDPSessionObserver(ws)
        
        # 发现并附加所有页面
        targets = await observer.discover_and_attach_all()
        print(f"已附加 {len(targets)} 个目标")
        
        # 在所有页面上启用 Runtime
        await observer.enable_domain_on_all("Runtime.enable")
        
        # 注册全局处理
        @observer.on("Runtime.exceptionThrown")
        async def on_exception(data, source):
            print(f"[异常] 来自 {source}: {data['params']['exceptionDetails']['text']}")
        
        # 监听 30 秒
        await observer.listen_all(30)
        
        # 收集结果
        for tid, info in observer.sessions.items():
            events = observer.get_session_events(tid)
            target = info["target"]
            url = target.get("url", "(unknown)")
            print(f"标签页 {url}: {len(events)} 个事件")
        
        await observer.detach_all()


# asyncio.run(cross_tab_monitor_demo())
```

---

## 最佳实践与架构建议

### 扩展模式选择指南

| 场景 | 推荐模式 | 理由 |
|------|----------|------|
| 需要原生浏览器功能 | chrome.debugger 扩展 | 权限更高、生命周期管理更好 |
| 快速原型验证 | Runtime.evaluate 注入 | 零配置、即写即用 |
| 生产级拦截 | CDP 代理中间件 | 可审计、可回滚、性能透明 |
| 大量标签页管理 | SessionObserver 模式 | 统一会话管理、避免资源泄漏 |
| 自定义指标收集 | 自定义事件域 + 轮询 | 灵活、与 CDP 事件流解耦 |

### 安全注意事项

```python
class CDPExtensionSecurity:
    """CDP 扩展的安全最佳实践"""
    
    @staticmethod
    async def validate_command_source(ws, session_id, command):
        """验证命令来源——防止未授权注入"""
        # 在代理层验证命令白名单
        ALLOWED_COMMANDS = {
            "Runtime.evaluate",
            "Runtime.runScript",
            "Page.navigate",
            "Network.enable",
        }
        
        method = command.get("method", "")
        if method not in ALLOWED_COMMANDS:
            print(f"[安全] 阻止未授权命令: {method}")
            return False
        return True
    
    @staticmethod
    async def sanitize_evaluate_expression(expression):
        """清理 Runtime.evaluate 的表达式——防止 XSS"""
        dangerous_patterns = [
            "document.cookie",
            "localStorage.",
            "new Function(",
            "eval(",
            "import(",
        ]
        for pattern in dangerous_patterns:
            if pattern in expression:
                print(f"[安全] 表达式中包含危险模式: {pattern}")
                return False
        return True
    
    @staticmethod
    def isolate_extension_context():
        """隔离扩展上下文的最佳实践"""
        return {
            "use_isolated_world": True,       # Runtime.evaluate 使用 contextId
            "sandbox_iframes": True,           # 在 iframe 中隔离
            "limit_session_scope": True,       # 仅附加需要的目标
            "audit_message_log": True,         # 记录所有 CDP 通信
        }
```

### 错误处理与恢复

```python
class RobustExtensionPattern:
    """健壮的扩展模式——处理断线重连和错误恢复"""
    
    def __init__(self, cdp_url):
        self.cdp_url = cdp_url
        self.ws = None
        self.sessions = {}
        self.reconnect_attempts = 0
        self.max_reconnect = 5
    
    async def connect_with_retry(self):
        """带重连机制的连接"""
        while self.reconnect_attempts < self.max_reconnect:
            try:
                self.ws = await websockets.connect(self.cdp_url)
                self.reconnect_attempts = 0
                print(f"[连接] 已连接到 {self.cdp_url}")
                return True
            except (ConnectionRefusedError, websockets.ConnectionClosed):
                self.reconnect_attempts += 1
                wait = 2 ** self.reconnect_attempts
                print(f"[重连] 第 {self.reconnect_attempts} 次尝试，等待 {wait} 秒")
                await asyncio.sleep(wait)
        return False
    
    async def ensure_session_alive(self, target_id):
        """确保会话存活——断线后自动重建"""
        if target_id not in self.sessions:
            return False
        
        # 检查会话是否仍然有效
        try:
            await cdp(self.ws, "Runtime.evaluate", {
                "expression": "1+1"
            }, self.sessions[target_id])
            return True
        except Exception:
            # 重新附加
            result = await cdp(self.ws, "Target.attachToTarget", {
                "targetId": target_id,
                "flatten": True
            })
            self.sessions[target_id] = result["sessionId"]
            return True
```

---

> **扩展思考**：CDP 的架构本质上是 Web 浏览器能力的"反射层"。理解了它的扩展模式，你就掌握了将任何浏览器能力以编程方式暴露给外部系统的能力——从自动化测试到安全审计，从性能监控到自定义调试器。下一章我们将深入 CDP 的错误追踪能力，用 Python 构建生产级的 JS 异常监控系统。

*上一篇回顾：CDP 浏览器历史管理：用 Python 控制页面导航历史。*

*下一篇预告：CDP 错误追踪指南：用 Python 捕获页面异常。*