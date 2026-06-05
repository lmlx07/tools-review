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
CMD_ID = [0]
async def cdp(ws, method, params=None):
    """Send CDP command and wait for result"""
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    request = {'id': cmd_id, 'method': method, 'params': params or {}}
    await ws.send(json.dumps(request))
    async for msg in ws:
        response = json.loads(msg)
        if response.get('id') == cmd_id:
            return response.get('result', {})

async def collect_performance_metrics(ws):
    """Capture page performance metrics"""
    
    # Enable Performance Domain
    await cdp(ws, 'Performance.enable')
    
    # Navigate to the destination page
    await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
    await asyncio.sleep(5) # Wait for the page to fully load
    
    # Get performance metrics
    result = await cdp(ws, 'Performance.getMetrics')
    metrics = result.get('metrics', [])
    
    # Parse into dictionary
    data = {}
    for m in metrics:
        data[m['name']] = m['value']
    
    return data


# Recall
metrics = await collect_performance_metrics(ws)
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
async def collect_web_vitals_js(ws):
    """Capture Web Vitals via JS"""
    
    result = await cdp(ws, 'Runtime.evaluate', {
        'expression': '''
        (() => {
            const entries = performance.getEntriesByType('paint');
            const result = {};
            
            entries.forEach(e => {
                result[e.name] = e.startTime;
            });
            
            // LCP: Get from PerformanceObserver
            // But note: the LCP may need the page to fully load before it can stabilize
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

# output example
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
async def capture_lcp_and_cls(ws, timeout=10):
    """Capture LCP and CLS via PerformanceObserver"""
    
    # Inject PerformanceObserver Listening Script first
    await cdp(ws, 'Runtime.evaluate', {
        'expression': '''
        window.__webVitals = {};
        
        // Listen to LCP
        new PerformanceObserver((list) => {
            const entries = list.getEntries();
            if (entries.length > 0) {
                window.__webVitals['LCP'] = entries[entries.length - 1].startTime;
                window.__webVitals['LCP_Element'] = entries[entries.length - 1].element?.tagName || '';
            }
        }).observe({type: 'largest-contentful-paint', buffered: true});
        
        // Monitor CLS
        let clsValue = 0;
        new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                if (!entry.hadRecentInput) {
                    clsValue += entry.value;
                }
            }
            window.__webVitals['CLS'] = clsValue;
        }).observe({type: 'layout-shift', buffered: true});
        
        // Listen for fid (First Input Delay)
        new PerformanceObserver((list) => {
            for (const entry of list.getEntries()) {
                window.__webVitals['FID'] = entry.processingStart - entry.startTime;
                break;
            }
        }).observe({type: 'first-input', buffered: true});
        '''
    })
    
    # Navigate to the page
    await cdp(ws, 'Page.navigate', {'url': 'https://example.com'})
    
    # Wait for the page to load
    await asyncio.sleep(timeout)
    
    # Collect results
    result = await cdp(ws, 'Runtime.evaluate', {
        'expression': 'JSON.stringify(window.__webVitals)',
        'returnByValue': True
    })
    
    return json.loads(result['result']['value'])

# Output format
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
    """Rating based on Web Vitals value"""
    
    grades = {}
    
    # LCP: ≤ 2500ms good, ≤ 4000ms to be improved, > 4000ms poor
    lcp = vitals.get('LCP', 0)
    if lcp <= 2500:
        grades['LCP'] = ('✅ Good', lcp)
    elif lcp <= 4000:
        grades['LCP'] = ('⚠️ Needs Improvement', lcp)
    else:
        grades['LCP'] = ('❌ Poor', lcp)
    
    # CLS: ≤ 0.1 is good, ≤ 0.25 needs improvement, > 0.25 is poor
    cls = vitals.get('CLS', 0)
    if cls <= 0.1:
        grades['CLS'] = ('✅ Good', cls)
    elif cls <= 0.25:
        grades['CLS'] = ('⚠️ Needs Improvement', cls)
    else:
        grades['CLS'] = ('❌ Poor', cls)
    
    # TTFB: ≤ 800ms good, ≤ 1800ms to be improved, > 1800ms poor
    ttfb = vitals.get('TTFB', 0)
    if ttfb <= 800:
        grades['TTFB'] = ('✅ Good', ttfb)
    elif ttfb <= 1800:
        grades['TTFB'] = ('⚠️ Needs Improvement', ttfb)
    else:
        grades['TTFB'] = ('❌ Poor', ttfb)
    
    # Fid: ≤ 100ms good, ≤ 300ms to be improved, > 300ms poor
    fid = vitals.get('FID', 0)
    if fid <= 100:
        grades['FID'] = ('✅ Good', fid)
    elif fid <= 300:
        grades['FID'] = ('⚠️ Needs Improvement', fid)
    else:
        grades['FID'] = ('❌ Poor', fid)
    
    return grades

# Use
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
async def trace_page(ws, url, categories=None, timeout=10):
    """
    Trace page performance
    
    Args:
        ws: CDP WebSocket connection
        url: Target URL
        categories: Tracing categories, defaults to common ones
        timeout: Collection duration
    Returns:
        List of trace events
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
    
    # Start Tracing (use default transfer mode so data arrives via Tracing.dataCollected events)
    await cdp(ws, 'Tracing.start', {
        'categories': ','.join(categories),
        'options': 'sampling-frequency=10000', # 10kHz sampling
    })
    
    # Navigate to the destination page
    await cdp(ws, 'Page.navigate', {'url': url})
    
    # Wait, then stop tracing
    await asyncio.sleep(timeout)
    await cdp(ws, 'Tracing.end')
    
    # Collect data from Tracing.dataCollected events
    events = []
    try:
        async with asyncio.timeout(5):
            async for msg in ws:
                data = json.loads(msg)
                method = data.get('method', '')
                
                if method == 'Tracing.tracingComplete':
                    break
                
                if method == 'Tracing.dataCollected':
                    collected = data['params'].get('value', [])
                    events.extend(collected)
    except (asyncio.TimeoutError, Exception):
        pass
    
    return events


```

### Analyze tracking events

The amount of data collected by Tracing is usually large (tens to hundreds of thousands of events). Key event types:

```python
def analyze_trace_events(events):
    """Analyze tracked events to extract key performance data"""
    
    analysis = {
        'script_compile': [],
        'script_evaluate': [],
        'layout': [],
        'paint': [],
        'parse_html': [],
        'resource_loading': [],
        'long_tasks': [], # Tasks longer than 50ms
    }
    
    for event in events:
        name = event.get('name', '')
        cat = event.get('cat', '')
        dur = event.get('dur', 0) / 1000 # Convert to milliseconds
        args = event.get('args', {})
        
        # JS Compilation
        if name == 'v8.compile' or 'V8.Compile' in name:
            analysis['script_compile'].append({
                'duration_ms': dur,
                'url': args.get('data', {}).get('url', 'unknown')
            })
        
        # Layout
        if name == 'Layout':
            analysis['layout'].append({
                'duration_ms': dur,
                'dirty_objects': args.get('dirtyObjects', 0),
                'partial_layout': args.get('partialLayout', False)
            })
        
        # Paint
        if name == 'Paint':
            analysis['paint'].append({
                'duration_ms': dur
            })
        
        # Long tasks (more than 50ms)
        if dur > 50:
            analysis['long_tasks'].append({
                'name': name,
                'duration_ms': dur,
                'cat': cat
            })
    
    return analysis


def print_analysis(analysis):
    """Print Analysis Report"""
    
    print('=== Performance Trace Analysis Report ===')
    print()
    
    # JS Compilation
    compile_time = sum(t['duration_ms'] for t in analysis['script_compile'])
    print(f'📜 JS Compilation: {compile_time:.1f}ms')
    for t in sorted(analysis['script_compile'], key=lambda x: -x['duration_ms'])[:5]:
        print(f'   - {t["url"][:60]}: {t["duration_ms"]:.1f}ms')
    
    # Layout
    layout_count = len(analysis['layout'])
    layout_time = sum(t['duration_ms'] for t in analysis['layout'])
    print(f'\n📐 Layouts: {layout_count}, Duration: {layout_time:.1f}ms')
    
    # Paint
    paint_count = len(analysis['paint'])
    paint_time = sum(t['duration_ms'] for t in analysis['paint'])
    print(f'🎨 Paints: {paint_count}, Duration: {paint_time:.1f}ms')
    
    # Long Tasks
    long_tasks = analysis['long_tasks']
    print(f'\n⚠️  Long tasks (>50ms): {len(long_tasks)}')
    for t in sorted(long_tasks, key=lambda x: -x['duration_ms'])[:10]:
        print(f'   - {t["name"]}: {t["duration_ms"]:.1f}ms')


```

### Calculate LCP from Tracing data

Tracing data contains LCP events, and the LCP time can be accurately obtained from the `largestContentfulPaint::Candidate` event:

```python
def extract_lcp_from_trace(events):
    """Extract precise LCP time from Tracing events"""
    
    lcp_events = []
    for event in events:
        name = event.get('name', '')
        if 'largestContentfulPaint' in name or 'LCP' in name:
            lcp_events.append({
                'time': event.get('ts', 0) / 1000, # Microseconds to milliseconds
                'dur': event.get('dur', 0) / 1000,
                'args': event.get('args', {})
            })
    
    return lcp_events


```

---

## Practice 3: Lighthouse automated auditing

Lighthouse is a website quality audit tool officially produced by Google. While it typically runs as a standalone CLI, it can also be integrated into automated processes via CDP.

> **Important**: CDP does **not** have a `Lighthouse` domain, so it is not possible to call Lighthouse directly via CDP commands. `Lighthouse.start` is NOT a standard CDP protocol method.
>
> The following are the two verified correct approaches:

### Option 1: Call Lighthouse + CDP port through the command line

A more general approach is to use the Node.js Lighthouse CLI with the CDP port:

```bash
# Installation
npm install -g lighthouse

# Audit with Open Browser (CDP Port Multiplexed)
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
    """Run Lighthouse Audit"""
    
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
        
        # Extract key metrics
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


# Use
report = run_lighthouse('https://example.com')
if 'scores' in report:
    for category, score in report['scores'].items():
        print(f'{category}: {score:.0f}/100')
    print(f'LCP: {report["metrics"]["lcp"]:.0f}ms')
    print(f'CLS: {report["metrics"]["cls"]:.3f}')

```

### Option 2: Pure Python Lighthouse analysis

If you don’t want to rely on Node.js, you can also use CDP data to calculate indicators like Lighthouse yourself:

```python
def compute_performance_score(metrics):
    """Calculate class Lighthouse scores based on metrics collected by CDP"""
    
    scores = {}
    
    # FCP Score (First Content Rendering)
    fcp = metrics.get('first-contentful-paint', 3000)
    if fcp <= 1800:
        scores['fcp'] = 100 - (fcp / 1800) * 30
    elif fcp <= 3000:
        scores['fcp'] = 70 - ((fcp - 1800) / 1200) * 40
    else:
        scores['fcp'] = max(0, 30 - ((fcp - 3000) / 1000) * 30)
    
    # Simple scoring (the actual Lighthouse scoring algorithm is more complex)
    scores['overall'] = sum(scores.values()) / len(scores) if scores else 0
    
    return scores

```

---

## Practical Combat 4: Performance Monitoring and Alarm System

Integrate the above techniques into a scheduled monitoring system:

```python
import asyncio, json, urllib.request, websockets, os
from datetime import datetime

class CDPPerformanceMonitor:
    """CDP Performance Monitor"""
    
    THRESHOLDS = {
        'LCP': 2500,         # ms
        'FCP': 1800,         # ms
        'CLS': 0.1, # Unitless
        'TTFB': 800,         # ms
        'JSHeapUsedSize': 50000000,  # bytes (50MB)
    }
    
    def __init__(self, host='localhost:9222', log_dir='./perf_logs'):
        self.host = host
        self.log_dir = log_dir
        self.ws = None
        os.makedirs(log_dir, exist_ok=True)
    
    async def _connect(self):
        data = json.loads(
            urllib.request.urlopen(f'http://{self.host}/json', timeout=5).read()
        )
        ws_url = data[0]['webSocketDebuggerUrl']
        self.ws = await websockets.connect(ws_url, max_size=2**24)
        await self.cdp('Page.enable')
        await self.cdp('Performance.enable')
    
    async def cdp(self, method, params=None):
        return await cdp(self.ws, method, params)
    
    async def check_url(self, url, label=''):
        """Check the performance of a single URL"""
        
        await self._connect()
        
        # Navigate and wait for loading
        print(f'🔍 Checking {label or url}...')
        await self.cdp('Page.navigate', {'url': url})
        await asyncio.sleep(5)
        
        # Get performance metrics
        result = await self.cdp('Performance.getMetrics')
        metrics = {m['name']: m['value'] for m in result.get('metrics', [])}
        
        # Get Web Vitals
        vitals_result = await self.cdp('Runtime.evaluate', {
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
        
        # Merge data
        report = {
            'url': url,
            'label': label,
            'timestamp': datetime.now().isoformat(),
            'metrics': {**metrics, **vitals}
        }
        
        # Check for alarms
        alerts = []
        for metric, threshold in self.THRESHOLDS.items():
            value = report['metrics'].get(metric, 0)
            if value > threshold:
                alerts.append(f'⚠️ {metric}: {value:.1f} (threshold: {threshold})')
        
        if alerts:
            print('  ALERTS:')
            for alert in alerts:
                print(f'    {alert}')
        else:
            print('  ✅ All metrics within thresholds')
        
        # Save Logs
        log_file = os.path.join(
            self.log_dir,
            f'{label or url.replace("://", "_").replace("/", "_")}.json'
        )
        with open(log_file, 'w') as f:
            json.dump(report, f, indent=2)
        
        await self.ws.close()
        return report, alerts
    
    async def check_multiple(self, urls):
        """Batch check multiple URLs"""
        
        all_reports = []
        all_alerts = {}
        
        for url, label in urls:
            try:
                report, alerts = await self.check_url(url, label)
                all_reports.append(report)
                if alerts:
                    all_alerts[label or url] = alerts
            except Exception as e:
                print(f'❌ Error checking {url}: {e}')
        
        # Total
        print(f'\n{"="*40}')
        print(f'📊 Check complete: {len(all_reports)}/{len(urls)} success')
        
        if all_alerts:
            print(f'⚠️  {len(all_alerts)} pages triggered alerts:')
            for page, alerts in all_alerts.items():
                for alert in alerts:
                    print(f'  {page}: {alert}')
        else:
            print('✅ All pages normal')
        
        return all_reports


# ====== Usage Example ======
async def demo():
    monitor = CDPPerformanceMonitor()
    await monitor.check_multiple([
        ('https://cdp.autify.cc', 'Home'),
        ('https://cdp.autify.cc/cdp-python-automation-guide/', 'CDP Complete Guide'),
        ('https://cdp.autify.cc/cdp-network-intercept-guide/', 'Network Intercept Guide'),
    ])

asyncio.run(demo())


```

---

## Practice 5: Performance regression testing CI integration

Integrate performance checks in CI/CD to prevent performance degradation:

```python
async def performance_regression_check(url, baseline_file='baseline.json'):
    """
    Performance regression test: compare current results with baseline
    
    Args:
        url: URL to test
        baseline_file: Baseline data file
    Returns:
        (passed, changes): Whether passed and change details
    """
    
    # Read baseline
    baseline = {}
    if os.path.exists(baseline_file):
        with open(baseline_file, 'r') as f:
            baseline = json.load(f)
    
    # Current Test
    monitor = CDPPerformanceMonitor()
    report, _ = await monitor.check_url(url)
    
    changes = {}
    passed = True
    
    # Compare key metrics
    KEY_METRICS = {
        'ScriptDuration': 0.2, # Allow 20% degradation
        'LayoutCount': 0.2,
        'JSHeapUsedSize': 0.15, # Allow 15% growth
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
    
    # Update baseline
    with open(baseline_file, 'w') as f:
        json.dump(report['metrics'], f, indent=2)
    
    return passed, changes


# Used in CI (wrap with asyncio.run)
passed, changes = await performance_regression_check('https://cdp.autify.cc/')
if not passed:
    print('❌ Performance regression test failed')
    for metric, info in changes.items():
        if info['status'] == 'FAIL':
            print(f'  {metric}: {info["change_pct"]}% regression')
    exit(1) # Let CI fail
else:
    print('✅ Performance regression test passed')


```

---

## Pitfall records and best practices

### 1. Tracing data is huge

A 10-second Tracing may generate 100,000+ events, which takes up a lot of memory. suggestion:

```python
# Limit Tracing Duration
TRACING_TIMEOUT = 5 # Second

# Using default transfer mode (data arrives via Tracing.dataCollected events in batches)
# For extremely large data, switch to ReturnAsStream + IO.read
await cdp(ws, 'Tracing.start', {
    'categories': 'devtools.timeline',
    # 'transferMode': 'ReturnAsStream' # Optional: use stream mode for very large data
})


```

### 2. Performance.getMetrics time point

`Performance.getMetrics` returns the cumulative value at the time of calling, not the value when the page is loaded. To get it after the page is fully loaded:

```python
# ❌ Error: Get it immediately after navigating
await cdp(ws, 'Page.navigate', {'url': url})
metrics = await cdp(ws, 'Performance.getMetrics') # Not loaded yet

# ✅ Correct: Wait for loading to complete
await cdp(ws, 'Page.navigate', {'url': url})
await wait_for_page_loaded(ws) # Wait for load event
metrics = await cdp(ws, 'Performance.getMetrics')



```

How to determine when the page is loaded:

```python
async def wait_for_page_loaded(ws, timeout=15):
    """Wait for page load event"""
    try:
        async with asyncio.timeout(timeout):
            async for msg in ws:
                data = json.loads(msg)
                if data.get('method') == 'Page.loadEventFired':
                    return True
    except (asyncio.TimeoutError, Exception):
        pass
    return False

```

### 3. Lighthouse version compatibility

Different Chrome versions have different built-in Lighthouse versions, and the generated report formats may be different. It is recommended to lock the Chrome version or explicitly specify the Lighthouse CLI version in CI.

### 4. Network condition simulation

When testing performance, network conditions need to be controlled to ensure repeatable results:

```python
# Simulate 3G network
await cdp(ws, 'Network.emulateNetworkConditions', {
    'offline': False,
    'latency': 150, # Delay 150ms
    'downloadThroughput': 750 * 1024 / 8,   # 750kbps
    'uploadThroughput': 250 * 1024 / 8,     # 250kbps
    'connectionType': 'cellular3g'
})


```

### 5. Take the average multiple times

A single performance test fluctuates greatly (affected by CPU, memory, etc.). It is recommended to take the median of multiple tests:

```python
async def median_performance(url, n=5):
    """Run n performance tests and take the median"""
    
    results = []
    for i in range(n):
        print(f'  Run {i+1}/{n}...')
        monitor = CDPPerformanceMonitor()
        report, _ = await monitor.check_url(url)
        results.append(report['metrics'].get('ScriptDuration', 0))
    
    # Take the median
    results.sort()
    median = results[len(results) // 2]
    print(f'  ScriptDuration median: {median:.1f}ms ({n} runs)')
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

---

*Previous: CDP browser fingerprinting and anti-detection practice — using Python to modify fingerprints to bypass automated detection.*

*Next up: The Complete Guide to CDP Cookie Operations — CRUD with Python & Auto-Login.*

