---
title: CDP 性能观察者指南：用 Python 监控 Core Web Vitals
date: 2026-06-05 15:30:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Performance
  - Core Web Vitals
  - LCP
  - CLS
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）监控 Web 页面性能指标。涵盖 Performance.enable、Performance.getMetrics、PerformanceObserver 事件流、LCP/CLS/INP/FID 等 Core Web Vitals 的采集与分析，以及页面加载生命周期中的性能数据收集。
---

> **一句话总结**：CDP 的 `Performance` 域能捕获浏览器原生性能指标数据，结合 `Runtime.evaluate` 注入 PerformanceObserver，可实现从导航开始到页面交互全生命周期的 Core Web Vitals 自动化监控。

---

## 目录

1. [性能监控与 CDP](#性能监控与-cdp)
2. [基础：Performance.enable 与 getMetrics](#基础performanceenable-与-getmetrics)
3. [PerformanceObserver 事件流](#performanceobserver-事件流)
4. [Core Web Vitals 采集：LCP、CLS、INP、FID](#core-web-vitals-采集lcplinpclsfid)
5. [页面加载完整性能追踪](#页面加载完整性能追踪)
6. [实战：自动化性能报告生成](#实战自动化性能报告生成)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 性能监控与 CDP

### 为什么用 CDP 监控性能

网页性能监控传统上依赖 `PerformanceObserver` API 在浏览器端收集数据，或者使用 Lighthouse 等工具。CDP 提供了更灵活的方式：

| 方法 | 优势 | 局限 |
|------|------|------|
| `window.performance` API | 浏览器原生，无需工具 | 无法自动化跨页面采集 |
| Lighthouse | 全面报告 | 运行时间长，不可实时 |
| CDP Performance 域 | 实时、可编程、低开销 | 需自行处理数据聚合 |
| CDP + PerformanceObserver | 原生精度 + CDP 控制 | 需要注入脚本 |

### CDP Performance 域的关键方法

- `Performance.enable` — 启用性能指标收集（支持 `timeDomain` 参数：`timeTicks` 或 `threadTicks`）
- `Performance.disable` — 禁用收集
- `Performance.getMetrics` — 获取当前累计指标快照
- `Performance.onMetrics` — 实时指标事件（周期性推送）

### Core Web Vitals 速览

| 指标 | 全称 | 衡量内容 | 目标值 |
|------|------|---------|--------|
| **LCP** | Largest Contentful Paint | 最大内容元素渲染时间 | < 2.5s |
| **CLS** | Cumulative Layout Shift | 布局偏移累积分数 | < 0.1 |
| **INP** | Interaction to Next Paint | 交互到下一次绘制延迟 | < 200ms |
| **FID** | First Input Delay | 首次输入延迟 | < 100ms |
| **FCP** | First Contentful Paint | 首次内容绘制 | < 1.8s |
| **TTFB** | Time to First Byte | 首字节时间 | < 800ms |

---

## 基础：Performance.enable 与 getMetrics

### 获取基础性能指标

```python
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

async def connect_page(ws):
    """附加到第一个页面目标"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets["targetInfos"]:
        if target["type"] == "page":
            session = await cdp(ws, "Target.attachToTarget", {
                "targetId": target["targetId"], "flatten": True
            })
            return session["sessionId"], target["targetId"]
    raise Exception("未找到页面目标")


async def enable_performance(ws, session_id, time_domain="timeTicks"):
    """
    启用性能监控
    time_domain: "timeTicks"（默认）或 "threadTicks"
    """
    result = await cdp(ws, "Performance.enable", {
        "timeDomain": time_domain
    }, session_id)
    print(f"性能监控已启用（timeDomain: {time_domain}）")
    return result


async def get_performance_metrics(ws, session_id):
    """获取当前累计性能指标"""
    result = await cdp(ws, "Performance.getMetrics", {}, session_id)
    metrics = result.get("metrics", [])
    print("\n===== 性能指标 =====")
    parsed = {}
    for m in metrics:
        name = m["name"]
        value = m["value"]
        parsed[name] = value
        # 格式化显示关键指标
        if name in ["Timestamp", "TaskDuration", "ScriptDuration",
                     "LayoutDuration", "RecalcStyleDuration"]:
            print(f"  {name}: {value:.2f} ms")
        elif name in ["JSHeapUsedSize", "JSHeapTotalSize", "DOMNodes",
                       "LayoutCount", "RecalcStyleCount"]:
            print(f"  {name}: {int(value)}")
        else:
            print(f"  {name}: {value}")
    return parsed


async def demo_get_metrics():
    """演示获取性能指标"""
    async with websockets.connect(CDP_URL) as ws:
        session_id, _ = await connect_page(ws)
        await enable_performance(ws, session_id)
        
        # 导航到页面
        await cdp(ws, "Page.navigate", {
            "url": "https://example.com"
        }, session_id)
        await cdp(ws, "Page.loadEventFired", {}, session_id)
        
        # 获取指标
        metrics = await get_performance_metrics(ws, session_id)
        
        return metrics
```

### Performance Metrics 字段详解

```python
# Performance.getMetrics 返回的常见指标
METRICS_DESCRIPTION = {
    "Timestamp": "自从导航开始的时间戳（ms）",
    "TaskDuration": "所有任务的总耗时（ms）",
    "ScriptDuration": "JavaScript 执行总耗时（ms）",
    "LayoutDuration": "布局计算总耗时（ms）",
    "RecalcStyleDuration": "样式重算总耗时（ms）",
    "JSHeapUsedSize": "JavaScript 堆已用大小（字节）",
    "JSHeapTotalSize": "JavaScript 堆总大小（字节）",
    "DOMNodes": "DOM 节点总数",
    "LayoutCount": "布局发生次数",
    "RecalcStyleCount": "样式重算次数",
    "Nodes": "DOM 节点数",
    "Documents": "文档数",
    "Frames": "Frame 数量",
}


async def analyze_performance_metrics(ws, session_id):
    """
    获取并分析性能指标，生成建议
    """
    metrics = await get_performance_metrics(ws, session_id)
    
    print("\n===== 性能分析 =====")
    
    # 分析脚本执行时间
    script_dur = metrics.get("ScriptDuration", 0)
    total_task = metrics.get("TaskDuration", 1)
    script_ratio = script_dur / total_task * 100
    print(f"JavaScript 占比: {script_ratio:.1f}%")
    if script_ratio > 50:
        print("⚠️ 建议：JS 执行时间过长，考虑代码拆分或懒加载")
    
    # 分析布局
    layout_dur = metrics.get("LayoutDuration", 0)
    layout_ratio = layout_dur / total_task * 100
    print(f"布局计算占比: {layout_ratio:.1f}%")
    if layout_ratio > 20:
        print("⚠️ 建议：频繁布局重排，考虑减少 DOM 操作")
    
    # 分析堆内存
    heap_used = metrics.get("JSHeapUsedSize", 0)
    heap_total = metrics.get("JSHeapTotalSize", 1)
    heap_ratio = heap_used / heap_total * 100
    print(f"堆内存使用: {heap_used / 1024 / 1024:.1f} MB / {heap_total / 1024 / 1024:.1f} MB ({heap_ratio:.1f}%)")
    if heap_ratio > 90:
        print("⚠️ 建议：内存使用率过高，检查是否存在内存泄漏")
    
    return metrics
```

---

## PerformanceObserver 事件流

### 监听实时性能事件

`Performance.onMetrics` 事件会定期推送当前的指标快照：

```python
async def listen_performance_events(ws, session_id, duration=30):
    """持续监听 Performance 事件"""
    await enable_performance(ws, session_id)
    print(f"开始监听性能事件（{duration}秒）...\n")
    
    metrics_history = []
    start = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start < duration:
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
            data = json.loads(resp)
            
            if data.get("method") == "Performance.onMetrics":
                params = data.get("params", {})
                metrics = {m["name"]: m["value"]
                          for m in params.get("metrics", [])}
                title = params.get("title", "unknown")
                
                metrics["_timestamp"] = asyncio.get_event_loop().time()
                metrics["_title"] = title
                metrics_history.append(metrics)
                
                print(f"[性能事件] {title}")
                for key in ["ScriptDuration", "LayoutDuration",
                            "JSHeapUsedSize"]:
                    if key in metrics:
                        if "Size" in key:
                            print(f"  {key}: {metrics[key] / 1024:.1f} KB")
                        else:
                            print(f"  {key}: {metrics[key]:.2f} ms")
                print()
        
        except asyncio.TimeoutError:
            pass
    
    print(f"收到 {len(metrics_history)} 个性能事件")
    return metrics_history


async def demo_event_listener():
    """性能事件监听演示"""
    async with websockets.connect(CDP_URL) as ws:
        session_id, target_id = await connect_page(ws)
        
        # 启动后台事件监听
        listen_task = asyncio.create_task(
            listen_performance_events(ws, session_id, duration=20)
        )
        
        # 同时导航页面
        await cdp(ws, "Page.navigate", {
            "url": "https://example.com"
        }, session_id)
        
        # 等待监听完成
        events = await listen_task
        
        # 分析趋势
        if len(events) >= 2:
            first_heap = events[0].get("JSHeapUsedSize", 0)
            last_heap = events[-1].get("JSHeapUsedSize", 0)
            heap_growth = last_heap - first_heap
            print(f"\n堆内存变化: {first_heap / 1024:.1f} KB → "
                  f"{last_heap / 1024:.1f} KB ({heap_growth / 1024:+.1f} KB)")
        
        return events
```

### 指标趋势分析

```python
async def analyze_metrics_trend(metrics_history):
    """分析性能指标趋势"""
    if len(metrics_history) < 3:
        print("数据点不足，无法分析趋势")
        return
    
    print("\n===== 性能趋势分析 =====")
    
    # 脚本执行时间趋势
    script_times = [m.get("ScriptDuration", 0)
                    for m in metrics_history]
    print(f"ScriptDuration: "
          f"min={min(script_times):.2f}, "
          f"max={max(script_times):.2f}, "
          f"avg={sum(script_times)/len(script_times):.2f} ms")
    
    # 布局时间趋势
    layout_times = [m.get("LayoutDuration", 0)
                    for m in metrics_history]
    print(f"LayoutDuration: "
          f"min={min(layout_times):.2f}, "
          f"max={max(layout_times):.2f}, "
          f"avg={sum(layout_times)/len(layout_times):.2f} ms")
    
    # 内存趋势
    heap_sizes = [m.get("JSHeapUsedSize", 0)
                  for m in metrics_history]
    heap_kb = [h / 1024 for h in heap_sizes]
    print(f"JSHeapUsedSize: "
          f"min={min(heap_kb):.1f}, "
          f"max={max(heap_kb):.1f}, "
          f"avg={sum(heap_kb)/len(heap_kb):.1f} KB")
    
    # 检测内存泄漏
    if len(heap_sizes) >= 5:
        first_avg = sum(heap_sizes[:2]) / 2
        last_avg = sum(heap_sizes[-2:]) / 2
        growth_pct = (last_avg - first_avg) / first_avg * 100
        print(f"\n内存变化趋势: {growth_pct:+.1f}%")
        if growth_pct > 20:
            print("⚠️ 内存持续增长，可能存在泄漏")
        elif growth_pct < -10:
            print("✅ 内存回收良好")
```

---

## Core Web Vitals 采集：LCP、CLS、INP、FID

### 通过 PerformanceObserver 采集

CDP 原生不直接暴露 Core Web Vitals API，但可以通过 `Runtime.evaluate` 注入 PerformanceObserver：

### LCP（Largest Contentful Paint）

```python
async def setup_lcp_observer(ws, session_id):
    """
    在页面中注入 LCP 观察者
    通过 CDP 事件获取 LCP 值
    """
    script = """
        new Promise((resolve) => {
            let lcpValue = null;
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const lastEntry = entries[entries.length - 1];
                lcpValue = {
                    startTime: lastEntry.startTime,
                    renderTime: lastEntry.renderTime || 0,
                    loadTime: lastEntry.loadTime || 0,
                    size: lastEntry.size || 0,
                    id: lastEntry.id || '',
                    url: lastEntry.url || '',
                    element: lastEntry.element ? 
                        (lastEntry.element.tagName + 
                         (lastEntry.element.id ? '#' + lastEntry.element.id : '') +
                         (lastEntry.element.className ? '.' + lastEntry.element.className.split(' ')[0] : ''))
                        : ''
                };
            });
            observer.observe({type: 'largest-contentful-paint', buffered: true});
            
            // LCP 在页面完全加载后最终确定
            setTimeout(() => {
                observer.disconnect();
                resolve(JSON.stringify(lcpValue));
            }, 5000);
        });
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": script,
        "sessionId": session_id,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    lcp_data = pyjson.loads(result["result"]["value"])
    
    print("===== LCP 结果 =====")
    print(f"  时间: {lcp_data.get('startTime', 0):.2f} ms")
    print(f"  元素: {lcp_data.get('element', 'N/A')}")
    print(f"  大小: {lcp_data.get('size', 0)} 像素")
    if lcp_data.get('url'):
        print(f"  URL: {lcp_data['url']}")
    
    # 评估
    lcp_ms = lcp_data.get("startTime", 0)
    if lcp_ms < 2500:
        print(f"  ✅ LCP 良好（{lcp_ms:.0f}ms < 2500ms）")
    elif lcp_ms < 4000:
        print(f"  ⚠️ LCP 需要改进（{lcp_ms:.0f}ms）")
    else:
        print(f"  ❌ LCP 差（{lcp_ms:.0f}ms > 4000ms）")
    
    return lcp_data
```

### CLS（Cumulative Layout Shift）

```python
async def setup_cls_observer(ws, session_id):
    """
    注入 CLS 观察者
    """
    script = """
        new Promise((resolve) => {
            let clsValue = 0;
            let clsRecords = [];
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) {
                        clsValue += entry.value;
                        clsRecords.push({
                            value: entry.value,
                            startTime: entry.startTime,
                            sources: entry.sources.map(s => ({
                                node: s.node ? 
                                    s.node.tagName + 
                                    (s.node.id ? '#' + s.node.id : '') : 'unknown',
                                currentRect: {
                                    x: s.currentRect.x, y: s.currentRect.y,
                                    w: s.currentRect.width, h: s.currentRect.height
                                }
                            }))
                        });
                    }
                }
            });
            observer.observe({type: 'layout-shift', buffered: true});
            
            setTimeout(() => {
                observer.disconnect();
                resolve(JSON.stringify({
                    cls: clsValue,
                    records: clsRecords.slice(0, 10),
                    totalShifts: clsRecords.length
                }));
            }, 5000);
        });
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": script,
        "sessionId": session_id,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    cls_data = pyjson.loads(result["result"]["value"])
    
    cls = cls_data.get("cls", 0)
    print("===== CLS 结果 =====")
    print(f"  总分: {cls:.4f}")
    print(f"  偏移次数: {cls_data.get('totalShifts', 0)}")
    
    if cls < 0.1:
        print(f"  ✅ CLS 良好（{cls:.4f} < 0.1）")
    elif cls < 0.25:
        print(f"  ⚠️ CLS 需要改进（{cls:.4f}）")
    else:
        print(f"  ❌ CLS 差（{cls:.4f} > 0.25）")
    
    # 显示具体偏移
    for i, record in enumerate(cls_data.get("records", [])[:5]):
        print(f"  偏移 #{i+1}: value={record['value']:.4f}, "
              f"于 {record['startTime']:.0f}ms")
    
    return cls_data
```

### INP（Interaction to Next Paint）

```python
async def setup_inp_observer(ws, session_id):
    """
    注入 INP 观察者（需要用户交互才能触发）
    """
    script = """
        new Promise((resolve) => {
            let inpValue = null;
            let interactions = [];
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    inpValue = entry;
                    interactions.push({
                        type: entry.name,
                        startTime: entry.startTime,
                        duration: entry.duration,
                        interactionType: entry.entryType
                    });
                }
            });
            observer.observe({type: 'first-input', buffered: true});
            observer.observe({type: 'event', durationThreshold: 16});
            
            setTimeout(() => {
                observer.disconnect();
                // 取最长的交互作为 INP
                let worstInteraction = null;
                if (interactions.length > 0) {
                    worstInteraction = interactions.reduce(
                        (a, b) => a.duration > b.duration ? a : b
                    );
                }
                resolve(JSON.stringify({
                    interactions: interactions,
                    worstInteraction: worstInteraction,
                    totalInteractions: interactions.length
                }));
            }, 10000);  // 给足够时间收集交互
        });
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": script,
        "sessionId": session_id,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    inp_data = pyjson.loads(result["result"]["value"])
    
    print("===== INP/FID 结果 =====")
    worst = inp_data.get("worstInteraction")
    if worst:
        inp_ms = worst.get("duration", 0)
        print(f"  最差交互: {worst.get('type', 'N/A')} - {inp_ms:.2f}ms")
        print(f"  发生时间: {worst.get('startTime', 0):.0f}ms")
        
        if inp_ms < 200:
            print(f"  ✅ INP 良好（{inp_ms:.0f}ms < 200ms）")
        elif inp_ms < 500:
            print(f"  ⚠️ INP 需要改进（{inp_ms:.0f}ms）")
        else:
            print(f"  ❌ INP 差（{inp_ms:.0f}ms > 500ms）")
    else:
        print("  ⚠️ 未检测到用户交互")
    
    print(f"  总交互数: {inp_data.get('totalInteractions', 0)}")
    
    return inp_data
```

### FID（First Input Delay）

```python
async def setup_fid_observer(ws, session_id):
    """
    注入 FID 观察者
    注意：FID 需要真实的用户交互，可通过 CDP 模拟点击触发
    """
    # 1. 设置观察者
    script = """
        new Promise((resolve) => {
            let fidValue = null;
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    fidValue = {
                        name: entry.name,
                        startTime: entry.startTime,
                        duration: entry.duration,
                        processingStart: entry.processingStart,
                        processingEnd: entry.processingEnd,
                        delay: entry.processingStart - entry.startTime
                    };
                }
            });
            observer.observe({type: 'first-input', buffered: true});
            
            // 在脚本中等待最多 8 秒
            let elapsed = 0;
            const interval = setInterval(() => {
                elapsed += 1000;
                if (fidValue || elapsed >= 8000) {
                    clearInterval(interval);
                    observer.disconnect();
                    resolve(JSON.stringify(fidValue));
                }
            }, 1000);
        });
    """
    
    wait_task = asyncio.create_task(
        cdp(ws, "Runtime.evaluate", {
            "expression": script,
            "sessionId": session_id,
            "awaitPromise": True,
            "returnByValue": True
        }, session_id)
    )
    
    # 2. 通过 CDP 点击页面来触发输入事件
    await asyncio.sleep(2)
    
    # 模拟点击
    await cdp(ws, "Runtime.evaluate", {
        "expression": "document.body.click()",
        "sessionId": session_id
    }, session_id)
    
    await asyncio.sleep(1)
    await cdp(ws, "Runtime.evaluate", {
        "expression": "document.querySelector('a, button, input')?.click()",
        "sessionId": session_id
    }, session_id)
    
    # 3. 获取结果
    result = await wait_task
    import json as pyjson
    fid_data = pyjson.loads(result["result"]["value"])
    
    if fid_data:
        print("===== FID 结果 =====")
        delay = fid_data.get("delay", 0)
        print(f"  输入延迟: {delay:.2f}ms")
        print(f"  总耗时: {fid_data.get('duration', 0):.2f}ms")
        
        if delay < 100:
            print(f"  ✅ FID 良好（{delay:.0f}ms < 100ms）")
        else:
            print(f"  ❌ FID 需要改进（{delay:.0f}ms > 100ms）")
    else:
        print("  ⚠️ 未检测到首次输入")
    
    return fid_data
```

### FCP（First Contentful Paint）

```python
async def setup_fcp_observer(ws, session_id):
    """
    注入 FCP 观察者
    """
    script = """
        new Promise((resolve) => {
            const observer = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                if (entries.length > 0) {
                    const fcp = entries[0];
                    observer.disconnect();
                    resolve(JSON.stringify({
                        startTime: fcp.startTime,
                        name: fcp.name
                    }));
                }
            });
            observer.observe({type: 'paint', buffered: true});
            
            setTimeout(() => {
                observer.disconnect();
                resolve('{}');
            }, 10000);
        });
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": script,
        "sessionId": session_id,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    fcp_data = pyjson.loads(result["result"]["value"])
    
    if fcp_data:
        fcp_ms = fcp_data.get("startTime", 0)
        print(f"FCP: {fcp_ms:.2f}ms")
        if fcp_ms < 1800:
            print(f"  ✅ FCP 良好（{fcp_ms:.0f}ms < 1800ms）")
        elif fcp_ms < 3000:
            print(f"  ⚠️ FCP 需要改进（{fcp_ms:.0f}ms）")
        else:
            print(f"  ❌ FCP 差（{fcp_ms:.0f}ms > 3000ms）")
    
    return fcp_data
```

---

## 页面加载完整性能追踪

### 综合采集所有指标

```python
async def collect_all_web_vitals(ws, session_id):
    """
    一次性采集所有 Core Web Vitals
    """
    # 注入所有观察者
    observers = """
        (() => {
            const results = {};
            
            // LCP
            const lcpObserver = new PerformanceObserver((list) => {
                const entries = list.getEntries();
                const last = entries[entries.length - 1];
                results.lcp = {
                    time: last.startTime,
                    size: last.size,
                    element: last.element?.tagName || '',
                    url: last.url || ''
                };
            });
            lcpObserver.observe({type: 'largest-contentful-paint', buffered: true});
            
            // CLS
            let clsScore = 0;
            const clsObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) clsScore += entry.value;
                }
            });
            clsObserver.observe({type: 'layout-shift', buffered: true});
            
            // FCP
            const paintObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.name === 'first-contentful-paint') {
                        results.fcp = entry.startTime;
                    }
                }
            });
            paintObserver.observe({type: 'paint', buffered: true});
            
            // 5 秒后断开并收集
            return new Promise((resolve) => {
                setTimeout(() => {
                    lcpObserver.disconnect();
                    clsObserver.disconnect();
                    paintObserver.disconnect();
                    results.cls = clsScore;
                    resolve(JSON.stringify(results));
                }, 5000);
            });
        })();
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": observers,
        "sessionId": session_id,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    vitals = pyjson.loads(result["result"]["value"])
    
    print("===== Core Web Vitals 综合报告 =====")
    print(f"FCP: {vitals.get('fcp', 'N/A')}")
    print(f"LCP: {vitals.get('lcp', {}).get('time', 'N/A')}")
    print(f"CLS: {vitals.get('cls', 0):.4f}")
    
    return vitals


async def full_page_lifecycle_performance(ws, session_id, url):
    """
    完整页面生命周期性能追踪
    从导航开始到加载完成的全部指标
    """
    print(f"开始追踪页面性能: {url}\n")
    
    # 1. 启用性能监控
    await enable_performance(ws, session_id)
    
    # 2. 注入 PerformanceObserver
    await cdp(ws, "Runtime.evaluate", {
        "expression": """
            window.__vitals = {};
            // LCP observer
            new PerformanceObserver((list) => {
                const entries = list.getEntries();
                window.__vitals.lcp = entries[entries.length - 1].startTime;
            }).observe({type: 'largest-contentful-paint', buffered: true});
            
            // CLS observer
            window.__clsScore = 0;
            new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) window.__clsScore += entry.value;
                }
            }).observe({type: 'layout-shift', buffered: true});
            
            // FCP observer
            new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.name === 'first-contentful-paint')
                        window.__vitals.fcp = entry.startTime;
                }
            }).observe({type: 'paint', buffered: true});
        """,
        "sessionId": session_id
    }, session_id)
    
    # 3. 导航
    nav_start = asyncio.get_event_loop().time()
    await cdp(ws, "Page.navigate", {"url": url}, session_id)
    
    # 4. 等待 load 事件
    await cdp(ws, "Page.loadEventFired", {}, session_id)
    load_time = asyncio.get_event_loop().time() - nav_start
    print(f"页面加载完成: {load_time:.2f}s")
    
    # 5. 等待额外渲染
    await asyncio.sleep(3)
    
    # 6. 获取指标
    cdp_metrics = await get_performance_metrics(ws, session_id)
    
    # 7. 获取 Web Vitals
    vitals = await cdp(ws, "Runtime.evaluate", {
        "expression": "JSON.stringify({...window.__vitals, cls: window.__clsScore})",
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    web_vitals = pyjson.loads(vitals["result"]["value"])
    
    print(f"\n===== 完整性能报告 =====")
    print(f"导航耗时: {load_time:.2f}s")
    print(f"FCP: {web_vitals.get('fcp', 'N/A')}")
    print(f"LCP: {web_vitals.get('lcp', 'N/A')}")
    print(f"CLS: {web_vitals.get('cls', 'N/A')}")
    
    return {
        "load_time": load_time,
        "cdp_metrics": cdp_metrics,
        "web_vitals": web_vitals
    }
```

---

## 实战：自动化性能报告生成

### 批量测试多个页面

```python
class WebVitalsCollector:
    """Core Web Vitals 采集器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.results = []
    
    async def enable(self):
        """启用性能监控"""
        await enable_performance(self.ws, self.session_id)
    
    async def measure_page(self, url, wait_time=5):
        """测量单个页面的性能指标"""
        print(f"\n测量: {url}")
        
        # 注入观察者
        await cdp(self.ws, "Runtime.evaluate", {
            "expression": """
                window.__perfData = {};
                window.__clsValue = 0;
                
                new PerformanceObserver((l) => {
                    const e = l.getEntries();
                    window.__perfData.lcp = e[e.length-1].startTime;
                }).observe({type:'largest-contentful-paint', buffered:true});
                
                new PerformanceObserver((l) => {
                    for (const e of l.getEntries()) {
                        if (!e.hadRecentInput) window.__clsValue += e.value;
                    }
                }).observe({type:'layout-shift', buffered:true});
                
                new PerformanceObserver((l) => {
                    for (const e of l.getEntries()) {
                        if (e.name==='first-contentful-paint')
                            window.__perfData.fcp = e.startTime;
                    }
                }).observe({type:'paint', buffered:true});
            """,
            "sessionId": self.session_id
        }, self.session_id)
        
        # 导航
        nav_start = asyncio.get_event_loop().time()
        await cdp(self.ws, "Page.navigate", {"url": url}, self.session_id)
        await cdp(self.ws, "Page.loadEventFired", {}, self.session_id)
        load_duration = asyncio.get_event_loop().time() - nav_start
        
        await asyncio.sleep(wait_time)
        
        # 采集
        cdp_metrics = await get_performance_metrics(self.ws, self.session_id)
        
        vitals = await cdp(self.ws, "Runtime.evaluate", {
            "expression": "JSON.stringify({...window.__perfData, cls: window.__clsValue})",
            "sessionId": self.session_id,
            "returnByValue": True
        }, self.session_id)
        
        import json as pyjson
        web_vitals = pyjson.loads(vitals["result"]["value"])
        
        result = {
            "url": url,
            "load_duration": load_duration,
            "fcp": web_vitals.get("fcp"),
            "lcp": web_vitals.get("lcp"),
            "cls": web_vitals.get("cls"),
            "script_duration": cdp_metrics.get("ScriptDuration", 0),
            "layout_duration": cdp_metrics.get("LayoutDuration", 0),
            "heap_used": cdp_metrics.get("JSHeapUsedSize", 0),
            "dom_nodes": cdp_metrics.get("DOMNodes", 0)
        }
        
        self.results.append(result)
        self._print_result(result)
        return result
    
    def _print_result(self, result):
        """打印单页结果"""
        print(f"  FCP: {result['fcp']:.0f}ms" if result['fcp'] else "  FCP: N/A")
        print(f"  LCP: {result['lcp']:.0f}ms" if result['lcp'] else "  LCP: N/A")
        print(f"  CLS: {result['cls']:.4f}" if result['cls'] else "  CLS: N/A")
        print(f"  加载: {result['load_duration']:.2f}s")
    
    def generate_report(self):
        """生成汇总报告"""
        print("\n" + "=" * 60)
        print("             自动化性能测试报告")
        print("=" * 60)
        
        for i, r in enumerate(self.results, 1):
            print(f"\n--- 页面 {i}: {r['url']} ---")
            print(f"  加载耗时: {r['load_duration']:.2f}s")
            print(f"  FCP: {r['fcp']:.0f}ms" if r.get('fcp') else "  FCP: N/A")
            print(f"  LCP: {r['lcp']:.0f}ms" if r.get('lcp') else "  LCP: N/A")
            print(f"  CLS: {r['cls']:.4f}" if r.get('cls') is not None else "  CLS: N/A")
            print(f"  JS 执行: {r['script_duration']:.2f}ms")
            print(f"  布局计算: {r['layout_duration']:.2f}ms")
            print(f"  DOM 节点: {r['dom_nodes']}")
            mem_mb = r['heap_used'] / 1024 / 1024
            print(f"  堆内存: {mem_mb:.1f} MB")
        
        print("=" * 60)
        return self.results


async def run_performance_test(pages):
    """运行性能测试"""
    async with websockets.connect(CDP_URL) as ws:
        session_id, _ = await connect_page(ws)
        collector = WebVitalsCollector(ws, session_id)
        await collector.enable()
        
        for url in pages:
            await collector.measure_page(url)
        
        collector.generate_report()


# 使用示例
async def example_test():
    pages = [
        "https://example.com",
        "https://example.com/page1",
        "https://example.com/page2",
    ]
    await run_performance_test(pages)
```

---

## 常见踩坑与最佳实践

### 踩坑 1：timeDomain 参数影响

```python
# 不同 timeDomain 影响返回值的基准
# "timeTicks" → 基于性能计时器（高精度，推荐）
await cdp(ws, "Performance.enable", {"timeDomain": "timeTicks"}, session_id)

# "threadTicks" → 基于线程计时器
await cdp(ws, "Performance.enable", {"timeDomain": "threadTicks"}, session_id)
```

### 踩坑 2：Performance.getMetrics 是快照而非增量

```python
# getMetrics 返回的是自导航开始的累计值，不是增量
# 如果需要增量值，需要手动计算差值
metrics_1 = await get_performance_metrics(ws, session_id)
await asyncio.sleep(5)
metrics_2 = await get_performance_metrics(ws, session_id)

# 手动计算增量
delta_script = metrics_2.get("ScriptDuration", 0) - metrics_1.get("ScriptDuration", 0)
print(f"脚本执行增量: {delta_script:.2f}ms")
```

### 踩坑 3：LCP 可能延迟报告

```python
# LCP 在页面完全稳定后才确定
# 设置足够长的超时时间
await asyncio.sleep(5)  # 确保 LCP 已判定
lcp = await setup_lcp_observer(ws, session_id)
```

### 踩坑 4：CLS 需要长时间观察

```python
# CLS 在整个页面生命周期内都可能变化
# 特别是懒加载内容、广告插入等场景
# 建议观察至少 5-10 秒
```

### 踩坑 5：INP/FID 需要实际交互

```python
# INP 和 FID 必须由用户交互触发
# 通过 CDP 模拟点击时，确保页面有可交互元素
await cdp(ws, "Runtime.evaluate", {
    "expression": "document.querySelector('button, a, input')?.click()",
    "sessionId": session_id
}, session_id)
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| timeDomain | 使用默认的 timeTicks |
| PerformanceObserver | 配合 Runtime.evaluate 注入脚本 |
| LCP 采集 | 导航后等待至少 5 秒 |
| CLS 采集 | 配合 setTimeout 收集完整结果 |
| INP/FID 采集 | 通过 CDP 模拟用户交互 |
| 多次测试 | 每个测试至少运行 3 次取中位数 |
| 环境一致性 | 固定网络条件和设备模拟 |

---

## 完整参考：CDP Web Vitals 采集类

```python
import asyncio
import json


class CDPWebVitalsCollector:
    """CDP Web Vitals 采集工具类"""

    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self.metrics_history = []

    async def _cmd(self, method, params=None):
        """发送 CDP 命令"""
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

    async def enable(self, time_domain="timeTicks"):
        """启用性能监控"""
        return await self._cmd("Performance.enable", {
            "timeDomain": time_domain
        })

    async def get_metrics(self):
        """获取当前性能指标"""
        result = await self._cmd("Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in result.get("metrics", [])}
        self.metrics_history.append(metrics)
        return metrics

    async def inject_observers(self):
        """注入所有 Web Vitals 观察者"""
        script = """
            window.__vitals = { lcp: null, fcp: null, cls: 0 };

            new PerformanceObserver((list) => {
                const entries = list.getEntries();
                window.__vitals.lcp = entries[entries.length - 1].startTime;
            }).observe({type: 'largest-contentful-paint', buffered: true});

            new PerformanceObserver((list) => {
                for (const e of list.getEntries()) {
                    if (!e.hadRecentInput) window.__vitals.cls += e.value;
                }
            }).observe({type: 'layout-shift', buffered: true});

            new PerformanceObserver((list) => {
                for (const e of list.getEntries()) {
                    if (e.name === 'first-contentful-paint')
                        window.__vitals.fcp = e.startTime;
                }
            }).observe({type: 'paint', buffered: true});
        """
        return await self._cmd("Runtime.evaluate", {
            "expression": script
        })

    async def get_web_vitals(self):
        """获取 Web Vitals 值"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": "JSON.stringify(window.__vitals)",
            "returnByValue": True
        })
        return json.loads(result["result"]["value"])

    async def measure(self, url, wait_after_load=5):
        """测量单个页面"""
        await self.inject_observers()
        await self._cmd("Page.navigate", {"url": url})
        await self._cmd("Page.loadEventFired")
        await asyncio.sleep(wait_after_load)

        cdp_metrics = await self.get_metrics()
        web_vitals = await self.get_web_vitals()

        return {
            "url": url,
            "web_vitals": web_vitals,
            "cdp_metrics": cdp_metrics
        }

    async def measure_multiple(self, urls, wait=5):
        """测量多个页面"""
        results = []
        for url in urls:
            result = await self.measure(url, wait)
            results.append(result)
            print(f"[{url}] FCP: {result['web_vitals'].get('fcp')}, "
                  f"LCP: {result['web_vitals'].get('lcp')}, "
                  f"CLS: {result['web_vitals'].get('cls', 0):.4f}")
        return results

    async def listen_metrics_stream(self, duration=30):
        """监听实时性能事件流"""
        events = []
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < duration:
            try:
                resp = await asyncio.wait_for(self.ws.recv(), timeout=1.0)
                data = json.loads(resp)
                if data.get("method") == "Performance.onMetrics":
                    metrics = {
                        m["name"]: m["value"]
                        for m in data["params"].get("metrics", [])
                    }
                    events.append(metrics)
            except asyncio.TimeoutError:
                pass

        return events

    def analyze(self, results):
        """分析结果"""
        summary = {"pages": []}
        for r in results:
            vitals = r["web_vitals"]
            metrics = r["cdp_metrics"]

            page = {
                "url": r["url"],
                "fcp": vitals.get("fcp"),
                "lcp": vitals.get("lcp"),
                "cls": vitals.get("cls", 0),
                "script_ms": metrics.get("ScriptDuration", 0),
                "layout_ms": metrics.get("LayoutDuration", 0),
                "heap_mb": metrics.get("JSHeapUsedSize", 0) / 1024 / 1024,
                "dom_nodes": metrics.get("DOMNodes", 0)
            }

            # 评估
            issues = []
            if page["lcp"] and page["lcp"] > 2500:
                issues.append("LCP 超过 2.5s")
            if page["cls"] and page["cls"] > 0.1:
                issues.append("CLS 超过 0.1")
            if page["fcp"] and page["fcp"] > 1800:
                issues.append("FCP 超过 1.8s")

            page["issues"] = issues
            summary["pages"].append(page)

        return summary
```

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id, _ = await connect_page(ws)
    collector = CDPWebVitalsCollector(ws, session_id)

    # 启用性能监控
    await collector.enable()

    # 测试多个页面
    results = await collector.measure_multiple([
        "https://example.com",
        "https://example.com/page1"
    ])

    # 分析结果
    analysis = collector.analyze(results)
    for page in analysis["pages"]:
        print(f"\n{page['url']}:")
        if page["issues"]:
            for issue in page["issues"]:
                print(f"  ⚠️ {issue}")
        else:
            print("  ✅ 所有指标良好")

    # 监听实时指标流
    events = await collector.listen_metrics_stream(duration=10)
    print(f"收到 {len(events)} 个实时性能事件")
```

---

> **总结**：CDP 的 `Performance` 域配合 `Runtime.evaluate` 注入的 PerformanceObserver，提供了完整的 Web 性能监控方案。从基础指标采集到 Core Web Vitals（LCP、CLS、INP、FID）的精确测量，可以构建自动化的性能测试体系，在前端性能优化中发挥关键作用。

---

*上一篇回顾：CDP Service Worker 管理：用 Python 调试离线缓存。*

*下一篇预告：CDP 无障碍树指南：用 Python 做自动化可访问性测试。*