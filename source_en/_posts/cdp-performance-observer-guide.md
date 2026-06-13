---
lang: en
title: "CDP Performance Observer Guide: Monitoring Core Web Vitals with Python"
date: "2026-06-05 15:30:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Performance
  - Core Web Vitals
  - LCP
  - CLS
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to monitoring web page performance metrics using Chrome DevTools Protocol (CDP). Learn Performance.enable, getMetrics, injecting PerformanceObserver for LCP/CLS/INP/FID collection, and building automated performance testing pipelines.
---

> **Summary in one sentence**: CDP's `Performance` domain captures native browser performance metrics, and combined with injected PerformanceObservers via `Runtime.evaluate`, enables full lifecycle Core Web Vitals monitoring from navigation through user interaction — all automated with Python.

---

## Table of Contents

1. [Performance Monitoring and CDP](#performance-monitoring-and-cdp)
2. [Basics: Performance.enable and getMetrics](#basics-performanceenable-and-getmetrics)
3. [PerformanceObserver Event Stream](#performanceobserver-event-stream)
4. [Core Web Vitals: LCP, CLS, INP, FID](#core-web-vitals-lcp-cls-inp-fid)
5. [Full Page Lifecycle Performance Tracking](#full-page-lifecycle-performance-tracking)
6. [Practical: Automated Performance Reports](#practical-automated-performance-reports)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Performance Monitoring and CDP

### Why Use CDP for Performance Monitoring

Traditional web performance monitoring relies on the `PerformanceObserver` API running in-browser, or tools like Lighthouse. CDP offers a more flexible, programmable approach:

| Method | Advantage | Limitation |
|--------|-----------|------------|
| `window.performance` API | Native, no tools needed | Cannot automate cross-page collection |
| Lighthouse | Comprehensive reports | Slow, not real-time |
| CDP Performance domain | Real-time, programmable, low overhead | Requires custom data aggregation |
| CDP + PerformanceObserver | Native precision + CDP control | Requires script injection |

### Key Performance Domain Methods

- `Performance.enable` — Enable metric collection (supports `timeDomain`: `timeTicks` or `threadTicks`)
- `Performance.disable` — Disable collection
- `Performance.getMetrics` — Get cumulative metric snapshot
- `Performance.onMetrics` — Real-time metric events (periodic push)

### Core Web Vitals Quick Reference

| Metric | Full Name | What It Measures | Target |
|--------|-----------|-----------------|--------|
| **LCP** | Largest Contentful Paint | Largest element render time | < 2.5s |
| **CLS** | Cumulative Layout Shift | Layout shift cumulative score | < 0.1 |
| **INP** | Interaction to Next Paint | Interaction-to-paint delay | < 200ms |
| **FID** | First Input Delay | First input processing delay | < 100ms |
| **FCP** | First Contentful Paint | First content render | < 1.8s |
| **TTFB** | Time to First Byte | Server response time | < 800ms |

---

## Basics: Performance.enable and getMetrics

### Fetching Basic Performance Metrics

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
    """Attach to the first available page target"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets["targetInfos"]:
        if target["type"] == "page":
            session = await cdp(ws, "Target.attachToTarget", {
                "targetId": target["targetId"], "flatten": True
            })
            return session["sessionId"], target["targetId"]
    raise Exception("No page target found")


async def enable_performance(ws, session_id, time_domain="timeTicks"):
    """Enable performance monitoring"""
    result = await cdp(ws, "Performance.enable", {
        "timeDomain": time_domain
    }, session_id)
    print(f"Performance monitoring enabled (timeDomain: {time_domain})")
    return result


async def get_performance_metrics(ws, session_id):
    """Get current cumulative performance metrics"""
    result = await cdp(ws, "Performance.getMetrics", {}, session_id)
    metrics = result.get("metrics", [])
    print("\n===== Performance Metrics =====")
    parsed = {}
    for m in metrics:
        name = m["name"]
        value = m["value"]
        parsed[name] = value
        
        if name in ["Timestamp", "TaskDuration", "ScriptDuration",
                     "LayoutDuration", "RecalcStyleDuration"]:
            print(f"  {name}: {value:.2f} ms")
        elif name in ["JSHeapUsedSize", "JSHeapTotalSize", "DOMNodes",
                       "LayoutCount", "RecalcStyleCount"]:
            print(f"  {name}: {int(value)}")
        else:
            print(f"  {name}: {value}")
    return parsed


async def analyze_performance_metrics(ws, session_id):
    """Fetch and analyze performance metrics"""
    metrics = await get_performance_metrics(ws, session_id)
    
    print("\n===== Performance Analysis =====")
    
    script_dur = metrics.get("ScriptDuration", 0)
    total_task = metrics.get("TaskDuration", 1)
    script_ratio = script_dur / total_task * 100
    print(f"JavaScript ratio: {script_ratio:.1f}%")
    if script_ratio > 50:
        print("⚠️ Suggestion: JS execution time too high, consider code splitting")
    
    layout_dur = metrics.get("LayoutDuration", 0)
    layout_ratio = layout_dur / total_task * 100
    print(f"Layout ratio: {layout_ratio:.1f}%")
    if layout_ratio > 20:
        print("⚠️ Suggestion: Frequent layout reflows, reduce DOM manipulation")
    
    heap_used = metrics.get("JSHeapUsedSize", 0)
    heap_total = metrics.get("JSHeapTotalSize", 1)
    heap_ratio = heap_used / heap_total * 100
    print(f"Heap usage: {heap_used / 1024 / 1024:.1f} MB / {heap_total / 1024 / 1024:.1f} MB ({heap_ratio:.1f}%)")
    if heap_ratio > 90:
        print("⚠️ Suggestion: High memory usage, check for leaks")
    
    return metrics
```

---

## PerformanceObserver Event Stream

### Listening to Real-Time Performance Events

The `Performance.onMetrics` event periodically pushes metric snapshots:

```python
async def listen_performance_events(ws, session_id, duration=30):
    """Continuously listen for performance events"""
    await enable_performance(ws, session_id)
    print(f"Listening for performance events ({duration}s)...\n")
    
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
                
                print(f"[Event] {title}")
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
    
    print(f"Received {len(metrics_history)} performance events")
    return metrics_history
```

### Trend Analysis

```python
async def analyze_metrics_trend(metrics_history):
    """Analyze performance metric trends"""
    if len(metrics_history) < 3:
        print("Not enough data points for trend analysis")
        return
    
    print("\n===== Performance Trend Analysis =====")
    
    script_times = [m.get("ScriptDuration", 0) for m in metrics_history]
    print(f"ScriptDuration: "
          f"min={min(script_times):.2f}, "
          f"max={max(script_times):.2f}, "
          f"avg={sum(script_times)/len(script_times):.2f} ms")
    
    layout_times = [m.get("LayoutDuration", 0) for m in metrics_history]
    print(f"LayoutDuration: "
          f"min={min(layout_times):.2f}, "
          f"max={max(layout_times):.2f}, "
          f"avg={sum(layout_times)/len(layout_times):.2f} ms")
    
    heap_sizes = [m.get("JSHeapUsedSize", 0) for m in metrics_history]
    heap_kb = [h / 1024 for h in heap_sizes]
    print(f"JSHeapUsedSize: "
          f"min={min(heap_kb):.1f}, "
          f"max={max(heap_kb):.1f}, "
          f"avg={sum(heap_kb)/len(heap_kb):.1f} KB")
    
    if len(heap_sizes) >= 5:
        first_avg = sum(heap_sizes[:2]) / 2
        last_avg = sum(heap_sizes[-2:]) / 2
        growth_pct = (last_avg - first_avg) / first_avg * 100
        print(f"\nMemory trend: {growth_pct:+.1f}%")
        if growth_pct > 20:
            print("⚠️ Memory growing, potential leak detected")
        elif growth_pct < -10:
            print("✅ Memory is well-managed")
```

---

## Core Web Vitals: LCP, CLS, INP, FID

### Using PerformanceObserver via CDP

CDP does not natively expose Core Web Vitals APIs, but you can inject PerformanceObservers through `Runtime.evaluate`:

### LCP (Largest Contentful Paint)

```python
async def setup_lcp_observer(ws, session_id):
    """Inject an LCP observer into the page"""
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
    
    print("===== LCP Result =====")
    print(f"  Time: {lcp_data.get('startTime', 0):.2f} ms")
    print(f"  Element: {lcp_data.get('element', 'N/A')}")
    print(f"  Size: {lcp_data.get('size', 0)} pixels")
    if lcp_data.get('url'):
        print(f"  URL: {lcp_data['url']}")
    
    lcp_ms = lcp_data.get("startTime", 0)
    if lcp_ms < 2500:
        print(f"  ✅ LCP good ({lcp_ms:.0f}ms < 2500ms)")
    elif lcp_ms < 4000:
        print(f"  ⚠️ LCP needs improvement ({lcp_ms:.0f}ms)")
    else:
        print(f"  ❌ LCP poor ({lcp_ms:.0f}ms > 4000ms)")
    
    return lcp_data
```

### CLS (Cumulative Layout Shift)

```python
async def setup_cls_observer(ws, session_id):
    """Inject a CLS observer into the page"""
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
    print("===== CLS Result =====")
    print(f"  Score: {cls:.4f}")
    print(f"  Shifts: {cls_data.get('totalShifts', 0)}")
    
    if cls < 0.1:
        print(f"  ✅ CLS good ({cls:.4f} < 0.1)")
    elif cls < 0.25:
        print(f"  ⚠️ CLS needs improvement ({cls:.4f})")
    else:
        print(f"  ❌ CLS poor ({cls:.4f} > 0.25)")
    
    for i, record in enumerate(cls_data.get("records", [])[:5]):
        print(f"  Shift #{i+1}: value={record['value']:.4f}, "
              f"at {record['startTime']:.0f}ms")
    
    return cls_data
```

### INP (Interaction to Next Paint)

```python
async def setup_inp_observer(ws, session_id):
    """Inject an INP observer (requires user interaction)"""
    script = """
        new Promise((resolve) => {
            let interactions = [];
            const observer = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
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
    inp_data = pyjson.loads(result["result"]["value"])
    
    print("===== INP/FID Result =====")
    worst = inp_data.get("worstInteraction")
    if worst:
        inp_ms = worst.get("duration", 0)
        print(f"  Worst interaction: {worst.get('type', 'N/A')} - {inp_ms:.2f}ms")
        print(f"  At: {worst.get('startTime', 0):.0f}ms")
        
        if inp_ms < 200:
            print(f"  ✅ INP good ({inp_ms:.0f}ms < 200ms)")
        elif inp_ms < 500:
            print(f"  ⚠️ INP needs improvement ({inp_ms:.0f}ms)")
        else:
            print(f"  ❌ INP poor ({inp_ms:.0f}ms > 500ms)")
    else:
        print("  ⚠️ No user interaction detected")
    
    print(f"  Total interactions: {inp_data.get('totalInteractions', 0)}")
    
    return inp_data
```

### FID (First Input Delay)

```python
async def setup_fid_observer(ws, session_id):
    """Inject FID observer + simulate click via CDP"""
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
    
    await asyncio.sleep(2)
    await cdp(ws, "Runtime.evaluate", {
        "expression": "document.body.click()",
        "sessionId": session_id
    }, session_id)
    
    await asyncio.sleep(1)
    await cdp(ws, "Runtime.evaluate", {
        "expression": "document.querySelector('a, button, input')?.click()",
        "sessionId": session_id
    }, session_id)
    
    result = await wait_task
    import json as pyjson
    fid_data = pyjson.loads(result["result"]["value"])
    
    if fid_data:
        print("===== FID Result =====")
        delay = fid_data.get("delay", 0)
        print(f"  Input delay: {delay:.2f}ms")
        print(f"  Total time: {fid_data.get('duration', 0):.2f}ms")
        
        if delay < 100:
            print(f"  ✅ FID good ({delay:.0f}ms < 100ms)")
        else:
            print(f"  ❌ FID needs improvement ({delay:.0f}ms > 100ms)")
    else:
        print("  ⚠️ No first input detected")
    
    return fid_data
```

### FCP (First Contentful Paint)

```python
async def setup_fcp_observer(ws, session_id):
    """Inject an FCP observer"""
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
            print(f"  ✅ FCP good ({fcp_ms:.0f}ms < 1800ms)")
        elif fcp_ms < 3000:
            print(f"  ⚠️ FCP needs improvement ({fcp_ms:.0f}ms)")
        else:
            print(f"  ❌ FCP poor ({fcp_ms:.0f}ms > 3000ms)")
    
    return fcp_data
```

---

## Full Page Lifecycle Performance Tracking

### Collect All Core Web Vitals

```python
async def collect_all_web_vitals(ws, session_id):
    """Collect all Core Web Vitals in one pass"""
    observers = """
        (() => {
            const results = {};
            
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
            
            let clsScore = 0;
            const clsObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) clsScore += entry.value;
                }
            });
            clsObserver.observe({type: 'layout-shift', buffered: true});
            
            const paintObserver = new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.name === 'first-contentful-paint') {
                        results.fcp = entry.startTime;
                    }
                }
            });
            paintObserver.observe({type: 'paint', buffered: true});
            
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
    
    print("===== Core Web Vitals Report =====")
    print(f"FCP: {vitals.get('fcp', 'N/A')}")
    print(f"LCP: {vitals.get('lcp', {}).get('time', 'N/A')}")
    print(f"CLS: {vitals.get('cls', 0):.4f}")
    
    return vitals


async def full_page_lifecycle_performance(ws, session_id, url):
    """
    Complete page lifecycle performance tracking
    From navigation through fully loaded
    """
    print(f"Tracking page performance: {url}\n")
    
    await enable_performance(ws, session_id)
    
    # Inject PerformanceObservers
    await cdp(ws, "Runtime.evaluate", {
        "expression": """
            window.__vitals = {};
            new PerformanceObserver((list) => {
                const entries = list.getEntries();
                window.__vitals.lcp = entries[entries.length - 1].startTime;
            }).observe({type: 'largest-contentful-paint', buffered: true});
            window.__clsScore = 0;
            new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (!entry.hadRecentInput) window.__clsScore += entry.value;
                }
            }).observe({type: 'layout-shift', buffered: true});
            new PerformanceObserver((list) => {
                for (const entry of list.getEntries()) {
                    if (entry.name === 'first-contentful-paint')
                        window.__vitals.fcp = entry.startTime;
                }
            }).observe({type: 'paint', buffered: true});
        """,
        "sessionId": session_id
    }, session_id)
    
    nav_start = asyncio.get_event_loop().time()
    await cdp(ws, "Page.navigate", {"url": url}, session_id)
    await cdp(ws, "Page.loadEventFired", {}, session_id)
    load_time = asyncio.get_event_loop().time() - nav_start
    print(f"Page loaded in: {load_time:.2f}s")
    
    await asyncio.sleep(3)
    
    cdp_metrics = await get_performance_metrics(ws, session_id)
    
    vitals = await cdp(ws, "Runtime.evaluate", {
        "expression": "JSON.stringify({...window.__vitals, cls: window.__clsScore})",
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    web_vitals = pyjson.loads(vitals["result"]["value"])
    
    print(f"\n===== Full Performance Report =====")
    print(f"Navigation time: {load_time:.2f}s")
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

## Practical: Automated Performance Reports

### Batch Testing Multiple Pages

```python
class WebVitalsCollector:
    """Core Web Vitals collector"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.results = []
    
    async def enable(self):
        """Enable performance monitoring"""
        await enable_performance(self.ws, self.session_id)
    
    async def measure_page(self, url, wait_time=5):
        """Measure a single page's performance"""
        print(f"\nMeasuring: {url}")
        
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
        
        nav_start = asyncio.get_event_loop().time()
        await cdp(self.ws, "Page.navigate", {"url": url}, self.session_id)
        await cdp(self.ws, "Page.loadEventFired", {}, self.session_id)
        load_duration = asyncio.get_event_loop().time() - nav_start
        
        await asyncio.sleep(wait_time)
        
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
        print(f"  FCP: {result['fcp']:.0f}ms" if result['fcp'] else "  FCP: N/A")
        print(f"  LCP: {result['lcp']:.0f}ms" if result['lcp'] else "  LCP: N/A")
        print(f"  CLS: {result['cls']:.4f}" if result['cls'] is not None else "  CLS: N/A")
        print(f"  Load: {result['load_duration']:.2f}s")
    
    def generate_report(self):
        """Generate summary report"""
        print("\n" + "=" * 60)
        print("         Automated Performance Test Report")
        print("=" * 60)
        
        for i, r in enumerate(self.results, 1):
            print(f"\n--- Page {i}: {r['url']} ---")
            print(f"  Load time: {r['load_duration']:.2f}s")
            print(f"  FCP: {r['fcp']:.0f}ms" if r.get('fcp') else "  FCP: N/A")
            print(f"  LCP: {r['lcp']:.0f}ms" if r.get('lcp') else "  LCP: N/A")
            print(f"  CLS: {r['cls']:.4f}" if r.get('cls') is not None else "  CLS: N/A")
            print(f"  JS execution: {r['script_duration']:.2f}ms")
            print(f"  Layout: {r['layout_duration']:.2f}ms")
            print(f"  DOM nodes: {r['dom_nodes']}")
            mem_mb = r['heap_used'] / 1024 / 1024
            print(f"  Heap: {mem_mb:.1f} MB")
        
        print("=" * 60)
        return self.results


async def run_performance_test(pages):
    """Run performance test on multiple pages"""
    async with websockets.connect(CDP_URL) as ws:
        session_id, _ = await connect_page(ws)
        collector = WebVitalsCollector(ws, session_id)
        await collector.enable()
        
        for url in pages:
            await collector.measure_page(url)
        
        collector.generate_report()
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: timeDomain Parameter

```python
# Different timeDomain affects metric baselines
# "timeTicks" → based on performance timer (high precision, recommended)
await cdp(ws, "Performance.enable", {"timeDomain": "timeTicks"}, session_id)

# "threadTicks" → based on thread timer
await cdp(ws, "Performance.enable", {"timeDomain": "threadTicks"}, session_id)
```

### Pitfall 2: getMetrics Is Cumulative

```python
# getMetrics returns cumulative values since navigation, not deltas
# Manually compute diffs if you need deltas
metrics_1 = await get_performance_metrics(ws, session_id)
await asyncio.sleep(5)
metrics_2 = await get_performance_metrics(ws, session_id)

delta_script = metrics_2.get("ScriptDuration", 0) - metrics_1.get("ScriptDuration", 0)
print(f"Script delta: {delta_script:.2f}ms")
```

### Pitfall 3: LCP May Be Delayed

```python
# LCP is finalized only after the page is fully stable
await asyncio.sleep(5)  # Ensure LCP is determined
lcp = await setup_lcp_observer(ws, session_id)
```

### Pitfall 4: CLS Needs Long Observation

```python
# CLS can change throughout the page lifecycle
# Especially with lazy-loaded content and ads
# Observe for at least 5-10 seconds
```

### Pitfall 5: INP/FID Require Real Interaction

```python
# INP and FID must be triggered by user interaction
# When simulating clicks via CDP, ensure the page has interactive elements
await cdp(ws, "Runtime.evaluate", {
    "expression": "document.querySelector('button, a, input')?.click()",
    "sessionId": session_id
}, session_id)
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| timeDomain | Use default timeTicks |
| PerformanceObserver | Inject via Runtime.evaluate |
| LCP collection | Wait at least 5s after navigation |
| CLS collection | Use setTimeout to collect full results |
| INP/FID collection | Simulate user interaction via CDP |
| Multiple runs | Run each test 3 times, take median |
| Environment | Fix network conditions and device emulation |

---

## Complete Reference: CDP Web Vitals Collection Class

```python
import asyncio
import json


class CDPWebVitalsCollector:
    """CDP Web Vitals Collector Tool"""

    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
        self.metrics_history = []

    async def _cmd(self, method, params=None):
        """Send a CDP command"""
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
        """Enable performance monitoring"""
        return await self._cmd("Performance.enable", {
            "timeDomain": time_domain
        })

    async def get_metrics(self):
        """Get current performance metrics"""
        result = await self._cmd("Performance.getMetrics")
        metrics = {m["name"]: m["value"] for m in result.get("metrics", [])}
        self.metrics_history.append(metrics)
        return metrics

    async def inject_observers(self):
        """Inject all Web Vitals observers into the page"""
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
        """Get Web Vitals values"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": "JSON.stringify(window.__vitals)",
            "returnByValue": True
        })
        return json.loads(result["result"]["value"])

    async def measure(self, url, wait_after_load=5):
        """Measure a single page"""
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
        """Measure multiple pages"""
        results = []
        for url in urls:
            result = await self.measure(url, wait)
            results.append(result)
            print(f"[{url}] FCP: {result['web_vitals'].get('fcp')}, "
                  f"LCP: {result['web_vitals'].get('lcp')}, "
                  f"CLS: {result['web_vitals'].get('cls', 0):.4f}")
        return results

    async def listen_metrics_stream(self, duration=30):
        """Listen to real-time performance events"""
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
        """Analyze results and flag issues"""
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

            issues = []
            if page["lcp"] and page["lcp"] > 2500:
                issues.append("LCP exceeds 2.5s")
            if page["cls"] and page["cls"] > 0.1:
                issues.append("CLS exceeds 0.1")
            if page["fcp"] and page["fcp"] > 1800:
                issues.append("FCP exceeds 1.8s")

            page["issues"] = issues
            summary["pages"].append(page)

        return summary
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id, _ = await connect_page(ws)
    collector = CDPWebVitalsCollector(ws, session_id)

    await collector.enable()

    results = await collector.measure_multiple([
        "https://example.com",
        "https://example.com/page1"
    ])

    analysis = collector.analyze(results)
    for page in analysis["pages"]:
        print(f"\n{page['url']}:")
        if page["issues"]:
            for issue in page["issues"]:
                print(f"  ⚠️ {issue}")
        else:
            print("  ✅ All metrics good")

    events = await collector.listen_metrics_stream(duration=10)
    print(f"Received {len(events)} real-time performance events")
```

---

> **Summary**: CDP's `Performance` domain combined with injected PerformanceObservers via `Runtime.evaluate` provides a complete web performance monitoring solution. From basic metrics to precise Core Web Vitals (LCP, CLS, INP, FID) measurement, you can build automated performance testing pipelines that are essential for frontend performance optimization.

---

*Previous: CDP Service Worker Management: Debugging Offline Cache with Python*

*Next up: CDP Accessibility Guide: Automated Accessibility Testing with Python*