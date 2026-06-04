---
lang: en
title: "CDP Performance Tracking and Lighthouse Integration: Measuring Web Vitals and Automating Performance Auditing with Python"
date: "2026-06-04 17:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Performance Optimization
  - Lighthouse
  - Web Vitals
categories:
  - CDP Basics
  - Python Practice
description: Use CDP's Performance domain and Tracing domain to collect core indicators such as LCP/FCP/CLS/TTFB, integrate Lighthouse for automated performance auditing, and build a performance monitoring and alarm system.
---

> **Summary in one sentence**: CDP can not only control the browser, but also go deep into Chrome's performance analysis engine to obtain Core Web Vitals indicators such as LCP, FCP, CLS, etc., and can even integrate Lighthouse for fully automated performance audits.

---

## Why use CDP for performance analysis?

Traditional front-end performance collection methods have limitations:

| Solution | Advantages | Disadvantages |
|------|------|------|
| **Performance API** (`window.performance`) | Browser native, simple | Only JS layer data can be obtained, Tracing information cannot be collected |
| **Web Vitals Library** (web-vitals) | Standardized indicators | Rely on user access, unable to do automated testing |
| **Lighthouse CLI** | Comprehensive reporting | Can only be run independently and difficult to integrate into automated processes |
| **Chrome DevTools manual operation** | Visually friendly | Cannot be batched or automated |
| **CDP Performance / Tracing Domain** | Engine-level data, programmable | Requires understanding of CDP protocol |

Advantages of CDP solution:

- **Engine-level data**: Directly collect raw data from the Chrome performance tracking engine
- **Programmable**: fully automated, suitable for CI/CD
- **NO INTRUSION**: No need to inject JavaScript into the page
- **Comprehensive indicators**: from LCP to Tracing events, covering all levels

---

## Performance domain: quickly obtain basic indicators

The Performance domain provides the simplest way to obtain performance data. It corresponds to the data of the DevTools Performance panel.

### Enable and collect

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

### Description of key indicators

Metrics returned by `Performance.getMetrics` include:

| Indicator name | Meaning | Description |
|---------|------|------|
| `Timestamp` | timestamp | time of collection moment |
| `Documents` | Number of DOMs | Number of document objects |
| `Frames` | Number of frames | Number of frames rendered |
| `JSEventListeners` | JS event listeners | Number of registered event listeners |
| `Nodes` | Number of DOM nodes | Number of DOM elements in the page |
| `LayoutCount` | Number of layouts | Number of triggered reflows |
| `RecalcStyleCount` | The number of style recalculations | The number of style recalculations |
| `LayoutDuration` | Layout duration | Sum of all layout durations |
| `RecalcStyleDuration` | Style recalculation time | Sum of all style recalculation time |
| `ScriptDuration` | Script execution time | Total JavaScript execution time |
| `TaskDuration` | Task duration | Sum of all task durations |
| `JSHeapUsedSize` | JS heap usage | JavaScript used heap memory |
| `JSHeapTotalSize` | Total JS heap size | Total JavaScript heap memory |

**Note**: These refer to **aggregated data** for the entire process of page load, not fine-grained time points for each event.

---

## Practice 1: Collecting Core Web Vitals

Core Web Vitals are three core user experience indicators defined by Google: LCP, FID/INP, and CLS. CDP does not have a direct API to return these metrics, but they can be collected by intercepting PerformanceEntry.

### Option 1: Read through Runtime.evaluate

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

### Option 2: Monitor through PerformanceObserver

For LCP (Largest Contentful Paint) and CLS (Cumulative Layout Shift), PerformanceObserver needs to be used to monitor:

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

### Determine performance level

Google recommended performance thresholds:

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

## Practical Combat 2: Performance Tracking Tracing

Tracing is CDP’s most powerful performance analysis function. It collects complete tracking data at the Chrome engine level, including JS execution, rendering, layout, drawing, GPU and other information.

### Start and stop Tracing

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

### Analyze tracking events

The amount of data collected by Tracing is usually large (tens to hundreds of thousands of events). Key event types:

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

### Calculate LCP from Tracing data

Tracing data contains LCP events, and the LCP time can be accurately obtained from the `largestContentfulPaint::Candidate` event:

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

## Practice 3: Lighthouse automated auditing

Lighthouse is a website quality audit tool officially produced by Google. While it typically runs as a standalone CLI, it can also be integrated into automated processes via CDP.

### Option 1: Call the Lighthouse protocol through CDP

Newer versions of Chrome have built-in Lighthouse support, which can be called via CDP:

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

> **Note**: The `Lighthouse.start` protocol method may vary depending on Chrome version. If it is not available, you can use option 2.

### Option 2: Call Lighthouse + CDP port through the command line

A more general approach is to use the Node.js Lighthouse CLI with the CDP port:

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

But since we are using Python, we can call it directly with subprocess:

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

### Option 3: Pure Python Lighthouse analysis

If you don’t want to rely on Node.js, you can also use CDP data to calculate indicators like Lighthouse yourself:

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

## Practical Combat 4: Performance Monitoring and Alarm System

Integrate the above techniques into a scheduled monitoring system:

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

## Practice 5: Performance regression testing CI integration

Integrate performance checks in CI/CD to prevent performance degradation:

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

## Pitfall records and best practices

### 1. Tracing data is huge

A 10-second Tracing may generate 100,000+ events, which takes up a lot of memory. suggestion:

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

### 2. Performance.getMetrics time point

`Performance.getMetrics` returns the cumulative value at the time of calling, not the value when the page is loaded. To get it after the page is fully loaded:

```python
# ❌ 错误：导航后立即获取
cmd(ws, 'Page.navigate', {'url': url})
metrics = cmd(ws, 'Performance.getMetrics')  # 还没加载完

# ✅ 正确：等待加载完成
cmd(ws, 'Page.navigate', {'url': url})
wait_for_page_loaded(ws)  # 等待 load 事件
metrics = cmd(ws, 'Performance.getMetrics')
```

How to determine when the page is loaded:

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

### 3. Lighthouse version compatibility

Different Chrome versions have different built-in Lighthouse versions, and the generated report formats may be different. It is recommended to lock the Chrome version or explicitly specify the Lighthouse CLI version in CI.

### 4. Network condition simulation

When testing performance, network conditions need to be controlled to ensure repeatable results:

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

### 5. Take the average multiple times

A single performance test fluctuates greatly (affected by CPU, memory, etc.). It is recommended to take the median of multiple tests:

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

## Summarize

CDP’s performance analysis capabilities cover the complete chain from simple indicator collection to in-depth Tracing:

- **Performance domain**: Quickly obtain basic indicators (number of DOM, JS heap, layout times, etc.)
- **Web Vitals Collection**: Capture LCP/CLS/FID via PerformanceObserver
- **Tracing domain**: Collect engine-level tracking data and analyze issues such as long tasks, layout jitter, etc.
- **Lighthouse Integration**: Get full performance scores and optimization recommendations
- **Monitoring Alerts**: Integrate performance checks into CI/CD pipelines

**Performance analysis solution selection:**

| Requirements | Recommended solutions |
|------|---------|
| Quickly understand page health | `Performance.getMetrics` + Web Vitals |
| Locating performance bottlenecks | Tracing analysis |
| Generate optimization report | Lighthouse |
| Continuous monitoring | Scheduled monitoring + regression testing |
| CI/CD Quality Access Control | Regression Test + Threshold Alarm |

