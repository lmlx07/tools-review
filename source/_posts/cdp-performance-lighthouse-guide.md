---
title: CDP 性能追踪与 Lighthouse 集成：用 Python 测量 Web Vitals 与自动化性能审计
date: 2026-06-04 17:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 性能优化
  - Lighthouse
  - Web Vitals
categories:
  - CDP 基础
  - Python 实战
description: 使用 CDP 的 Performance 域和 Tracing 域采集 LCP/FCP/CLS/TTFB 等核心指标，集成 Lighthouse 做自动化性能审计，搭建性能监控告警系统。
---

> **一句话总结**：CDP 不仅能控制浏览器，还能深入 Chrome 的性能分析引擎，拿到 LCP、FCP、CLS 等 Core Web Vitals 指标，甚至可以集成 Lighthouse 做全自动化的性能审计。

---

## 目录

1. [为什么用 CDP 做性能分析](#为什么用-cdp-做性能分析)
2. [Performance 域：快速获取基础指标](#performance-域快速获取基础指标)
3. [实战一：采集 Core Web Vitals](#实战一采集-core-web-vitals)
4. [实战二：性能追踪 Tracing](#实战二性能追踪-tracing)
5. [实战三：Lighthouse 自动化审计](#实战三lighthouse-自动化审计)
6. [实战四：性能监控告警系统](#实战四性能监控告警系统)
7. [实战五：性能回归测试 CI 集成](#实战五性能回归测试-ci-集成)
8. [踩坑记录与最佳实践](#踩坑记录与最佳实践)

---

## 为什么用 CDP 做性能分析

传统前端性能采集方式各有局限：

| 方案 | 优点 | 缺点 |
|------|------|------|
| **Performance API** (`window.performance`) | 浏览器原生、简单 | 只能拿到 JS 层数据，无法采集 Tracing 信息 |
| **Web Vitals 库** (web-vitals) | 标准化指标 | 依赖用户访问、无法做自动化测试 |
| **Lighthouse CLI** | 报告全面 | 只能独立运行、难以集成到自动化流程 |
| **Chrome DevTools 手动操作** | 可视化友好 | 不能批量、不能自动化 |
| **CDP Performance / Tracing 域** | 引擎级数据、可编程 | 需要理解 CDP 协议 |

CDP 方案的优势：

- **引擎级数据**：直接采集 Chrome 性能追踪引擎的原始数据
- **可编程**：完全自动化，适合 CI/CD
- **无侵入**：不需要在页面中注入 JavaScript
- **指标全面**：从 LCP 到 Tracing 事件，覆盖所有层面

---

## Performance 域：快速获取基础指标

Performance 域提供了最简单的性能数据获取方式。它对应的是 DevTools Performance 面板的数据。

### 启用和采集

```python
def collect_performance_metrics(ws):
    """采集页面性能指标"""
    
    # 启用 Performance 域
    cmd(ws, 'Performance.enable')
    
    # 导航到目标页面
    cmd(ws, 'Page.navigate', {'url': 'https://example.com'})
    time.sleep(5)  # 等待页面完全加载
    
    # 获取性能指标
    result = cmd(ws, 'Performance.getMetrics')
    metrics = result.get('metrics', [])
    
    # 解析成字典
    data = {}
    for m in metrics:
        data[m['name']] = m['value']
    
    return data


# 调用
metrics = collect_performance_metrics(ws)
for name, value in sorted(metrics.items()):
    print(f'{name}: {value}')
```

### 关键指标说明

`Performance.getMetrics` 返回的指标包括：

| 指标名称 | 含义 | 说明 |
|---------|------|------|
| `Timestamp` | 时间戳 | 采集时刻的时间 |
| `Documents` | DOM 数量 | 文档对象数量 |
| `Frames` | 帧数 | 已渲染的帧数 |
| `JSEventListeners` | JS 事件监听器 | 注册的事件监听器数量 |
| `Nodes` | DOM 节点数 | 页面中的 DOM 元素数量 |
| `LayoutCount` | 布局次数 | 触发的回流次数 |
| `RecalcStyleCount` | 样式重算次数 | 样式重新计算的次数 |
| `LayoutDuration` | 布局耗时 | 所有布局耗时总和 |
| `RecalcStyleDuration` | 样式重算耗时 | 所有样式重算耗时总和 |
| `ScriptDuration` | 脚本执行耗时 | JavaScript 执行总耗时 |
| `TaskDuration` | 任务耗时 | 所有任务耗时总和 |
| `JSHeapUsedSize` | JS 堆使用量 | JavaScript 已用堆内存 |
| `JSHeapTotalSize` | JS 堆总量 | JavaScript 总堆内存 |

**注意**：这些是指页面加载整个过程的**汇总数据**，而不是每个事件的细粒度时间点。

---

## 实战一：采集 Core Web Vitals

Core Web Vitals 是 Google 定义的三个核心用户体验指标：LCP、FID/INP、CLS。CDP 没有直接的 API 返回这些指标，但可以通过拦截 PerformanceEntry 来采集。

### 方案一：通过 Runtime.evaluate 读取

```python
def collect_web_vitals_js(ws):
    """通过 JS 采集 Web Vitals"""
    
    result = cmd(ws, 'Runtime.evaluate', {
        'expression': '''
        (() => {
            const entries = performance.getEntriesByType('paint');
            const result = {};
            
            entries.forEach(e => {
                result[e.name] = e.startTime;
            });
            
            // LCP: 从 PerformanceObserver 获取
            // 但注意：LCP 可能需要页面完全加载后才稳定
            const nav = performance.getEntriesByType('navigation')[0];
            if (nav) {
                result['TTFB'] = nav.responseStart - nav.requestStart;
                result['DOMContentLoaded'] = nav.domContentLoadedEventEnd;
                result['Load'] = nav.loadEventEnd;
                result['DomInteractive'] = nav.domInteractive;
            }
            
            return JSON.stringify(result);
        })()
        ''',
        'returnByValue': True
    })
    
    return json.loads(result['result']['value'])

# 输出示例
# {
#   "first-paint": 234.5,
#   "first-contentful-paint": 234.5,
#   "TTFB": 85.2,
#   "DOMContentLoaded": 420.1,
#   "Load": 1250.3,
#   "DomInteractive": 380.7
# }
```

### 方案二：通过 PerformanceObserver 监听

对于 LCP（Largest Contentful Paint）和 CLS（Cumulative Layout Shift），需要用 PerformanceObserver 来监听：

```python
def capture_lcp_and_cls(ws, timeout=10):
    """通过 PerformanceObserver 捕获 LCP 和 CLS"""
    
    # 先注入 PerformanceObserver 监听脚本
    cmd(ws, 'Runtime.evaluate', {
        'expression': '''
        window.__webVitals = {};
        
        // 监听 LCP
        new PerformanceObserver((list) => {
            const entries = list.getEntries();
            if (entries.length > 0) {
                window.__webVitals['LCP'] = entries[entries.length - 1].startTime;
                window.__webVitals['LCP_Element'] = entries[entries.length - 1].element?.tagName || '';
            }
        }).observe({type: 'largest-contentful-paint', buffered: true});
        
        // 监听 CLS
        let clsValue = 0;
        new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (!entry.hadRecentInput) {
                    clsValue += entry.value;
                }
            }
            window.__webVitals['CLS'] = clsValue;
        }).observe({type: 'layout-shift', buffered: true});
        
        // 监听 FID (First Input Delay)
        new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                window.__webVitals['FID'] = entry.processingStart - entry.startTime;
                break;
            }
        }).observe({type: 'first-input', buffered: true});
        '''
    })
    
    # 导航到页面
    cmd(ws, 'Page.navigate', {'url': 'https://example.com'})
    
    # 等待页面加载完成
    time.sleep(timeout)
    
    # 采集结果
    result = cmd(ws, 'Runtime.evaluate', {
        'expression': 'JSON.stringify(window.__webVitals)',
        'returnByValue': True
    })
    
    return json.loads(result['result']['value'])

# 输出
# {
#   "LCP": 1250.4,
#   "LCP_Element": "IMG",
#   "CLS": 0.08,
#   "FID": 12.3
# }
```

### 判断性能等级

Google 建议的性能阈值：

```python
def grade_web_vitals(vitals):
    """根据 Web Vitals 值给出评级"""
    
    grades = {}
    
    # LCP：≤ 2500ms 好，≤ 4000ms 需改进，> 4000ms 差
    lcp = vitals.get('LCP', 0)
    if lcp <= 2500:
        grades['LCP'] = ('✅ 良好', lcp)
    elif lcp <= 4000:
        grades['LCP'] = ('⚠️ 需改进', lcp)
    else:
        grades['LCP'] = ('❌ 较差', lcp)
    
    # CLS：≤ 0.1 好，≤ 0.25 需改进，> 0.25 差
    cls = vitals.get('CLS', 0)
    if cls <= 0.1:
        grades['CLS'] = ('✅ 良好', cls)
    elif cls <= 0.25:
        grades['CLS'] = ('⚠️ 需改进', cls)
    else:
        grades['CLS'] = ('❌ 较差', cls)
    
    # TTFB：≤ 800ms 好，≤ 1800ms 需改进，> 1800ms 差
    ttfb = vitals.get('TTFB', 0)
    if ttfb <= 800:
        grades['TTFB'] = ('✅ 良好', ttfb)
    elif ttfb <= 1800:
        grades['TTFB'] = ('⚠️ 需改进', ttfb)
    else:
        grades['TTFB'] = ('❌ 较差', ttfb)
    
    # FID：≤ 100ms 好，≤ 300ms 需改进，> 300ms 差
    fid = vitals.get('FID', 0)
    if fid <= 100:
        grades['FID'] = ('✅ 良好', fid)
    elif fid <= 300:
        grades['FID'] = ('⚠️ 需改进', fid)
    else:
        grades['FID'] = ('❌ 较差', fid)
    
    return grades

# 使用
vitals = capture_lcp_and_cls(ws)
grades = grade_web_vitals(vitals)
for metric, (grade, value) in grades.items():
    print(f'{metric}: {grade} ({value:.1f})')
```

---

## 实战二：性能追踪 Tracing

Tracing 是 CDP 最强大的性能分析功能。它采集 Chrome 引擎层面的完整追踪数据，包括 JS 执行、渲染、布局、绘制、GPU 等所有信息。

### 启动和停止 Tracing

```python
def trace_page(ws, url, categories=None, timeout=10):
    """
    对页面进行性能追踪
    
    Args:
        ws: CDP WebSocket 连接
        url: 目标 URL
        categories: 追踪类别，默认使用常用类别
        timeout: 采集时长
    Returns:
        追踪事件列表
    """
    
    if categories is None:
        categories = [
            'devtools.timeline',
            'disabled-by-default-devtools.timeline',
            'disabled-by-default-devtools.timeline.frame',
            'disabled-by-default-devtools.timeline.stack',
            'disabled-by-default-v8.cpu_profile',
            'disabled-by-default-v8.cpu_profiler',
            'disabled-by-default-v8.compile',
            'toplevel',
            'blink.console',
            'blink.user_timing',
            'latencyInfo',
            'loading',
            'navigation',
        ]
    
    # 启动 Tracing
    cmd(ws, 'Tracing.start', {
        'categories': ','.join(categories),
        'options': 'sampling-frequency=10000',  # 10kHz 采样
        'transferMode': 'ReturnAsStream'  # 用流返回，避免单次数据过大
    })
    
    # 导航到目标页面
    cmd(ws, 'Page.navigate', {'url': url})
    
    # 等待并采集追踪数据
    events = []
    start = time.time()
    stream_handle = None
    
    while time.time() - start < timeout:
        try:
            ws.settimeout(0.3)
            msg = json.loads(ws.recv())
            
            method = msg.get('method', '')
            
            if method == 'Tracing.tracingComplete':
                stream_handle = msg['params']['stream']
                break
            
            if method == 'Tracing.dataCollected':
                collected = msg['params'].get('value', [])
                events.extend(collected)
                
        except websocket.TimeoutError:
            continue
    
    # 停止 Tracing
    cmd(ws, 'Tracing.end')
    
    return events
```

### 分析追踪事件

Tracing 采集的数据量通常很大（几万到几十万条事件）。关键的事件类型：

```python
def analyze_trace_events(events):
    """分析追踪事件，提取关键性能数据"""
    
    analysis = {
        'script_compile': [],
        'script_evaluate': [],
        'layout': [],
        'paint': [],
        'parse_html': [],
        'resource_loading': [],
        'long_tasks': [],  # 超过 50ms 的任务
    }
    
    for event in events:
        name = event.get('name', '')
        cat = event.get('cat', '')
        dur = event.get('dur', 0) / 1000  # 转换为毫秒
        args = event.get('args', {})
        
        # JS 编译
        if name == 'v8.compile' or 'V8.Compile' in name:
            analysis['script_compile'].append({
                'duration_ms': dur,
                'url': args.get('data', {}).get('url', 'unknown')
            })
        
        # 布局
        if name == 'Layout':
            analysis['layout'].append({
                'duration_ms': dur,
                'dirty_objects': args.get('dirtyObjects', 0),
                'partial_layout': args.get('partialLayout', False)
            })
        
        # 绘制
        if name == 'Paint':
            analysis['paint'].append({
                'duration_ms': dur
            })
        
        # 长任务（超过 50ms）
        if dur > 50:
            analysis['long_tasks'].append({
                'name': name,
                'duration_ms': dur,
                'cat': cat
            })
    
    return analysis


def print_analysis(analysis):
    """打印分析报告"""
    
    print('=== 性能追踪分析报告 ===')
    print()
    
    # JS 编译
    compile_time = sum(t['duration_ms'] for t in analysis['script_compile'])
    print(f'📜 JS 编译总耗时: {compile_time:.1f}ms')
    for t in sorted(analysis['script_compile'], key=lambda x: -x['duration_ms'])[:5]:
        print(f'   - {t["url"][:60]}: {t["duration_ms"]:.1f}ms')
    
    # 布局
    layout_count = len(analysis['layout'])
    layout_time = sum(t['duration_ms'] for t in analysis['layout'])
    print(f'\n📐 布局次数: {layout_count}, 总耗时: {layout_time:.1f}ms')
    
    # 绘制
    paint_count = len(analysis['paint'])
    paint_time = sum(t['duration_ms'] for t in analysis['paint'])
    print(f'🎨 绘制次数: {paint_count}, 总耗时: {paint_time:.1f}ms')
    
    # 长任务
    long_tasks = analysis['long_tasks']
    print(f'\n⚠️  长任务(>50ms): {len(long_tasks)} 个')
    for t in sorted(long_tasks, key=lambda x: -x['duration_ms'])[:10]:
        print(f'   - {t["name"]}: {t["duration_ms"]:.1f}ms')
```

### 从 Tracing 数据计算 LCP

Tracing 数据中包含了 LCP 事件，可以从 `largestContentfulPaint::Candidate` 事件中准确获取 LCP 时间：

```python
def extract_lcp_from_trace(events):
    """从 Tracing 事件中提取精确的 LCP 时间"""
    
    lcp_events = []
    for event in events:
        name = event.get('name', '')
        if 'largestContentfulPaint' in name or 'LCP' in name:
            lcp_events.append({
                'time': event.get('ts', 0) / 1000,  # 微秒转毫秒
                'dur': event.get('dur', 0) / 1000,
                'args': event.get('args', {})
            })
    
    return lcp_events
```

---

## 实战三：Lighthouse 自动化审计

Lighthouse 是 Google 官方出品的网站质量审计工具。虽然它通常作为独立 CLI 运行，但也可以通过 CDP 集成到自动化流程中。

### 方案一：通过 CDP 调用 Lighthouse 协议

较新版本的 Chrome 内置了 Lighthouse 支持，可以通过 CDP 调用：

```python
def run_lighthouse_audit(ws):
    """通过 CDP 运行 Lighthouse 审计"""
    
    # 启用所需的域
    cmd(ws, 'Page.enable')
    
    # 启动 Lighthouse 审计
    # 注意：这需要 Chrome 内置了 Lighthouse 支持
    result = cmd(ws, 'Lighthouse.start', {
        'config': {
            'categories': ['performance', 'accessibility', 'best-practices', 'seo'],
            'formFactor': 'desktop',
            'throttling': {
                'cpuSlowdownMultiplier': 1,
                'downloadThroughputKbps': 10000,
                'uploadThroughputKbps': 5000,
                'rttMs': 40
            }
        }
    })
    
    return result
```

> **注意**：`Lighthouse.start` 协议方法可能因 Chrome 版本而异。如果不可用，可以用方案二。

### 方案二：通过命令行调用 Lighthouse + CDP 端口

更通用的方式是用 Node.js Lighthouse CLI 配合 CDP 端口：

```bash
# 安装
npm install -g lighthouse

# 使用已打开的浏览器进行审计（复用 CDP 端口）
lighthouse https://example.com \
  --chrome-flags="--remote-debugging-port=9222" \
  --output=json \
  --output-path=./lighthouse-report.json \
  --preset=desktop \
  --quiet
```

但既然我们用的是 Python，可以直接用 subprocess 调用：

```python
import subprocess, json

def run_lighthouse(url, output_path='lighthouse-report.json', port=9222):
    """运行 Lighthouse 审计"""
    
    cmd = [
        'npx', 'lighthouse', url,
        '--chrome-flags', f'--remote-debugging-port={port}',
        '--output', 'json',
        '--output-path', output_path,
        '--preset', 'desktop',
        '--quiet'
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    
    if result.returncode == 0:
        with open(output_path, 'r') as f:
            report = json.load(f)
        
        # 提取关键指标
        categories = report.get('categories', {})
        audits = report.get('audits', {})
        
        return {
            'scores': {
                name: data['score'] * 100
                for name, data in categories.items()
            },
            'metrics': {
                'lcp': audits.get('largest-contentful-paint', {}).get('numericValue', 0),
                'fcp': audits.get('first-contentful-paint', {}).get('numericValue', 0),
                'cls': audits.get('cumulative-layout-shift', {}).get('numericValue', 0),
                'tbt': audits.get('total-blocking-time', {}).get('numericValue', 0),
                'si': audits.get('speed-index', {}).get('numericValue', 0),
                'ttfb': audits.get('server-response-time', {}).get('numericValue', 0),
            }
        }
    else:
        return {'error': result.stderr}


# 使用
report = run_lighthouse('https://example.com')
if 'scores' in report:
    for category, score in report['scores'].items():
        print(f'{category}: {score:.0f}/100')
    print(f'LCP: {report["metrics"]["lcp"]:.0f}ms')
    print(f'CLS: {report["metrics"]["cls"]:.3f}')
```

### 方案三：纯 Python Lighthouse 解析

如果不想依赖 Node.js，也可以完全用 CDP 数据自行计算类似 Lighthouse 的指标：

```python
def compute_performance_score(metrics):
    """根据 CDP 采集的指标计算类 Lighthouse 分数"""
    
    scores = {}
    
    # FCP 评分（首次内容绘制）
    fcp = metrics.get('first-contentful-paint', 3000)
    if fcp <= 1800:
        scores['fcp'] = 100 - (fcp / 1800) * 30
    elif fcp <= 3000:
        scores['fcp'] = 70 - ((fcp - 1800) / 1200) * 40
    else:
        scores['fcp'] = max(0, 30 - ((fcp - 3000) / 1000) * 30)
    
    # 简易评分（实际 Lighthouse 评分算法更复杂）
    scores['overall'] = sum(scores.values()) / len(scores) if scores else 0
    
    return scores
```

---

## 实战四：性能监控告警系统

将以上技巧整合成一个定时监控系统：

```python
import json, urllib.request, websocket, time, os
from datetime import datetime

class CDPPerformanceMonitor:
    """CDP 性能监控器"""
    
    THRESHOLDS = {
        'LCP': 2500,         # ms
        'FCP': 1800,         # ms
        'CLS': 0.1,          # 无单位
        'TTFB': 800,         # ms
        'JSHeapUsedSize': 50000000,  # bytes (50MB)
    }
    
    def __init__(self, host='localhost:9222', log_dir='./perf_logs'):
        self.host = host
        self.log_dir = log_dir
        self.ws = None
        self._id = 1
        os.makedirs(log_dir, exist_ok=True)
    
    def _connect(self):
        data = json.loads(
            urllib.request.urlopen(f'http://{self.host}/json', timeout=5).read()
        )
        ws_url = data[0]['webSocketDebuggerUrl']
        self.ws = websocket.create_connection(ws_url, timeout=30)
        self._cmd('Page.enable')
        self._cmd('Performance.enable')
    
    def _cmd(self, method, params=None):
        if params is None: params = {}
        self._id += 1
        self.ws.send(json.dumps({'id': self._id, 'method': method, 'params': params}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get('id') == self._id: return r.get('result', {})
    
    def check_url(self, url, label=''):
        """检查单个 URL 的性能"""
        
        self._connect()
        
        # 导航并等待加载
        print(f'🔍 Checking {label or url}...')
        cmd(ws, 'Page.navigate', {'url': url})
        time.sleep(5)
        
        # 获取性能指标
        result = self._cmd('Performance.getMetrics')
        metrics = {m['name']: m['value'] for m in result.get('metrics', [])}
        
        # 获取 Web Vitals
        vitals_result = self._cmd('Runtime.evaluate', {
            'expression': '''
            (() => {
                const nav = performance.getEntriesByType('navigation')[0];
                const paint = performance.getEntriesByType('paint');
                const fcp = paint.find(e => e.name === 'first-contentful-paint');
                return JSON.stringify({
                    TTFB: nav ? nav.responseStart - nav.requestStart : 0,
                    FCP: fcp ? fcp.startTime : 0,
                    DomContentLoaded: nav ? nav.domContentLoadedEventEnd : 0
                });
            })()
            ''',
            'returnByValue': True
        })
        
        vitals = json.loads(vitals_result['result']['value'])
        
        # 合并数据
        report = {
            'url': url,
            'label': label,
            'timestamp': datetime.now().isoformat(),
            'metrics': {**metrics, **vitals}
        }
        
        # 检查告警
        alerts = []
        for metric, threshold in self.THRESHOLDS.items():
            value = report['metrics'].get(metric, 0)
            if value > threshold:
                alerts.append(f'⚠️ {metric}: {value:.1f} (阈值: {threshold})')
        
        if alerts:
            print('  ALERTS:')
            for alert in alerts:
                print(f'    {alert}')
        else:
            print('  ✅ All metrics within thresholds')
        
        # 保存日志
        log_file = os.path.join(
            self.log_dir,
            f'{label or url.replace("://", "_").replace("/", "_")}.json'
        )
        with open(log_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        self.ws.close()
        return report, alerts
    
    def check_multiple(self, urls):
        """批量检查多个 URL"""
        
        all_reports = []
        all_alerts = {}
        
        for url, label in urls:
            try:
                report, alerts = self.check_url(url, label)
                all_reports.append(report)
                if alerts:
                    all_alerts[label or url] = alerts
            except Exception as e:
                print(f'❌ Error checking {url}: {e}')
        
        # 汇总
        print(f'\n{"="*40}')
        print(f'📊 检查完成: {len(all_reports)}/{len(urls)} 成功')
        
        if all_alerts:
            print(f'⚠️  {len(all_alerts)} 个页面触发告警:')
            for page, alerts in all_alerts.items():
                for alert in alerts:
                    print(f'  {page}: {alert}')
        else:
            print('✅ 所有页面正常')
        
        return all_reports


# 使用示例：监控你的 CDP 教程站
monitor = CDPPerformanceMonitor()

monitor.check_multiple([
    ('https://cdp.autify.cc', '首页'),
    ('https://cdp.autify.cc/cdp-python-automation-guide/', 'CDP 完全指南'),
    ('https://cdp.autify.cc/cdp-network-intercept-guide/', '网络拦截篇'),
])
```

---

## 实战五：性能回归测试 CI 集成

在 CI/CD 中集成性能检查，防止性能退化：

```python
def performance_regression_check(url, baseline_file='baseline.json'):
    """
    性能回归测试：对比当前结果与基线
    
    Args:
        url: 要测试的 URL
        baseline_file: 基线数据文件
    Returns:
        (passed, changes): 是否通过和变更详情
    """
    
    # 读取基线
    baseline = {}
    if os.path.exists(baseline_file):
        with open(baseline_file, 'r') as f:
            baseline = json.load(f)
    
    # 当前测试
    monitor = CDPPerformanceMonitor()
    report, _ = monitor.check_url(url)
    
    changes = {}
    passed = True
    
    # 对比关键指标
    KEY_METRICS = {
        'ScriptDuration': 0.2,    # 允许 20% 退化
        'LayoutCount': 0.2,
        'JSHeapUsedSize': 0.15,   # 允许 15% 增长
    }
    
    for metric, tolerance in KEY_METRICS.items():
        current = report['metrics'].get(metric, 0)
        base_val = baseline.get(metric, current)
        
        if base_val > 0:
            change = (current - base_val) / base_val
            if change > tolerance:
                changes[metric] = {
                    'baseline': base_val,
                    'current': current,
                    'change_pct': round(change * 100, 1),
                    'status': 'FAIL'
                }
                passed = False
            elif change < -tolerance:
                changes[metric] = {
                    'baseline': base_val,
                    'current': current,
                    'change_pct': round(change * 100, 1),
                    'status': 'IMPROVED'
                }
            else:
                changes[metric] = {
                    'baseline': base_val,
                    'current': current,
                    'change_pct': round(change * 100, 1),
                    'status': 'OK'
                }
    
    # 更新基线
    with open(baseline_file, 'w') as f:
        json.dump(report['metrics'], f, indent=2)
    
    return passed, changes


# 在 CI 中使用
passed, changes = performance_regression_check('https://cdp.autify.cc/')
if not passed:
    print('❌ 性能回归测试未通过')
    for metric, info in changes.items():
        if info['status'] == 'FAIL':
            print(f'  {metric}: {info["change_pct"]}% 退化')
    exit(1)  # 让 CI 失败
else:
    print('✅ 性能回归测试通过')
```

---

## 踩坑记录与最佳实践

### 1. Tracing 数据量巨大

一次 10 秒的 Tracing 可能产生 10 万+ 条事件，内存占用很大。建议：

```python
# 限制 Tracing 时长
TRACING_TIMEOUT = 5  # 秒

# 使用流模式传输（transferMode=ReturnAsStream）
# 而不是默认的逐个事件发送
cmd(ws, 'Tracing.start', {
    'categories': 'devtools.timeline',
    'transferMode': 'ReturnAsStream'  # 推荐
})
```

### 2. Performance.getMetrics 的时间点

`Performance.getMetrics` 返回的是**调用时刻**的累计值，不是页面加载完成时的值。要在**页面完全加载后**再获取：

```python
# ❌ 错误：导航后立即获取
cmd(ws, 'Page.navigate', {'url': url})
metrics = cmd(ws, 'Performance.getMetrics')  # 还没加载完

# ✅ 正确：等待加载完成
cmd(ws, 'Page.navigate', {'url': url})
wait_for_page_loaded(ws)  # 等待 load 事件
metrics = cmd(ws, 'Performance.getMetrics')
```

判断页面加载完成的方法：

```python
def wait_for_page_loaded(ws, timeout=15):
    """等待页面 load 事件"""
    start = time.time()
    while time.time() - start < timeout:
        try:
            ws.settimeout(0.3)
            msg = json.loads(ws.recv())
            if msg.get('method') == 'Page.loadEventFired':
                return True
        except:
            continue
    return False
```

### 3. Lighthouse 版本兼容性

不同 Chrome 版本内置的 Lighthouse 版本不同，生成的报告格式可能有差异。建议锁定 Chrome 版本，或者在 CI 中显式指定 Lighthouse CLI 版本。

### 4. 网络条件模拟

测试性能时，需要控制网络条件以保证结果可重复：

```python
# 模拟 3G 网络
cmd(ws, 'Network.emulateNetworkConditions', {
    'offline': False,
    'latency': 150,            # 延迟 150ms
    'downloadThroughput': 750 * 1024 / 8,   # 750kbps
    'uploadThroughput': 250 * 1024 / 8,     # 250kbps
    'connectionType': 'cellular3g'
})
```

### 5. 多次取平均值

单次性能测试的波动很大（受 CPU、内存等影响），建议多次测试取中位数：

```python
def median_performance(url, n=5):
    """运行 n 次性能测试，取中位数"""
    
    results = []
    for i in range(n):
        print(f'  第 {i+1}/{n} 次...')
        monitor = CDPPerformanceMonitor()
        report, _ = monitor.check_url(url)
        results.append(report['metrics'].get('ScriptDuration', 0))
    
    # 取中位数
    results.sort()
    median = results[len(results) // 2]
    print(f'  ScriptDuration 中位数: {median:.1f}ms ({n} 次)')
    return median
```

---

## 总结

CDP 的性能分析能力覆盖了从简单指标采集到深度 Tracing 的完整链条：

- **Performance 域**：快速获取基础指标（DOM 数量、JS 堆、布局次数等）
- **Web Vitals 采集**：通过 PerformanceObserver 捕获 LCP / CLS / FID
- **Tracing 域**：采集引擎级追踪数据，分析长任务、布局抖动等问题
- **Lighthouse 集成**：获取完整的性能评分和优化建议
- **监控告警**：将性能检查集成到 CI/CD 流水线中

**性能分析方案选择：**

| 需求 | 推荐方案 |
|------|---------|
| 快速了解页面健康度 | `Performance.getMetrics` + Web Vitals |
| 定位性能瓶颈 | Tracing 分析 |
| 生成优化报告 | Lighthouse |
| 持续监控 | 定时监控 + 回归测试 |
| CI/CD 质量门禁 | 回归测试 + 阈值告警 |

