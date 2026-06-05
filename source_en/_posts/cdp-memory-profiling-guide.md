---
lang: en
title: "CDP Memory Profiling Guide: Detecting Memory Leaks with Python"
date: "2026-06-05 19:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Memory
  - HeapProfiler
  - Profiling
  - Leak Detection
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to browser memory profiling using CDP's HeapProfiler and Performance domains. Learn to take heap snapshots, track object allocations, compare snapshots for leaks, trigger GC, and read memory metrics — all programmatically with Python.
---

> **Summary in one sentence**: CDP's HeapProfiler and Performance domains give you full programmatic control over browser memory analysis — you can capture heap snapshots, track object allocations, compare snapshots to find leaks, and collect memory metrics just like DevTools' Memory panel, but fully scriptable.

---

## Table of Contents

1. [Why Use CDP for Memory Profiling](#why-use-cdp-for-memory-profiling)
2. [Basics: Connection & Initialization](#basics-connection--initialization)
3. [Taking Heap Snapshots](#taking-heap-snapshots)
4. [Tracking Heap Object Allocations](#tracking-heap-object-allocations)
5. [Comparing Snapshots to Find Leaks](#comparing-snapshots-to-find-leaks)
6. [Querying Object Details by ID](#querying-object-details-by-id)
7. [Retrieving Memory Metrics](#retrieving-memory-metrics)
8. [Triggering Garbage Collection](#triggering-garbage-collection)
9. [Practical: Automated Leak Detection Script](#practical-automated-leak-detection-script)
10. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Memory Profiling

| Feature | DevTools Memory Panel | CDP HeapProfiler API |
|---------|----------------------|---------------------|
| Automation | Manual only | Fully scriptable, CI/CD ready |
| Snapshot diffing | Manual selection | Programmatic delta computation |
| Long-term monitoring | Not suitable | Hours of continuous tracking |
| Object tracking | Manual inspection | Precise start/stop control |
| Snapshot size | DevTools UI limited | Custom streaming processing |
| Batch analysis | One-by-one | Bulk page analysis |

---

## Basics: Connection & Initialization

### Unified CDP Helper

All examples use the unified CDP message pattern:

```python
import asyncio
import websockets
import json
import base64

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
    result = await cdp(ws, "Target.getTargets")
    target_id = result["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

### Enabling HeapProfiler

```python
async def enable_heap_profiler(ws, session_id):
    """Enable the heap profiler"""
    await cdp(ws, "HeapProfiler.enable", session_id=session_id)
    print("HeapProfiler enabled")


async def enable_performance(ws, session_id):
    """Enable the Performance domain"""
    await cdp(ws, "Performance.enable", session_id=session_id)
    print("Performance enabled")
```

---

## Taking Heap Snapshots

A heap snapshot captures all JS heap objects and their reference relationships at a given moment.

### Using the Native HeapProfiler API

```python
async def take_heap_snapshot(ws, session_id):
    """
    Take a heap snapshot of the current page
    Returns the parsed snapshot data
    """
    chunks = []
    
    # Register data callback
    async def collect_chunk():
        async for resp in ws:
            data = json.loads(resp)
            method = data.get("method", "")
            if method == "HeapProfiler.addHeapSnapshotChunk":
                chunk = data["params"]["chunk"]
                chunks.append(chunk)
            elif data.get("id") == snapshot_id:
                return data.get("result", {})
    
    # Trigger snapshot
    CMD_ID[0] += 1
    snapshot_id = CMD_ID[0]
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": snapshot_id,
        "method": "HeapProfiler.takeHeapSnapshot",
        "params": {}
    }))
    
    # Wait for snapshot to complete
    await collect_chunk()
    
    # Merge all chunks
    raw_data = "".join(chunks)
    snapshot = json.loads(raw_data)
    
    print(f"Heap snapshot complete: {len(snapshot.get('nodes', [])) // 6} nodes, "
          f"{len(snapshot.get('edges', [])) // 3} edges")
    print(f"Snapshot size: {len(raw_data) / 1024:.1f} KB")
    return snapshot


async def save_snapshot_to_file(ws, session_id, filepath):
    """Take a heap snapshot and save it to a file"""
    chunks = []
    snapshot_done = asyncio.Event()
    
    async def collector():
        nonlocal chunks
        async for resp in ws:
            data = json.loads(resp)
            method = data.get("method", "")
            if method == "HeapProfiler.addHeapSnapshotChunk":
                chunks.append(data["params"]["chunk"])
            elif data.get("id") == cmd_id:
                snapshot_done.set()
                return
    
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": cmd_id,
        "method": "HeapProfiler.takeHeapSnapshot",
        "params": {"reportProgress": False}
    }))
    
    await asyncio.wait_for(snapshot_done.wait(), timeout=60)
    
    raw = "".join(chunks)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(raw)
    print(f"Heap snapshot saved to: {filepath} ({len(raw) / 1024:.1f} KB)")
    return filepath
```

---

## Tracking Heap Object Allocations

Sometimes you need to monitor object allocation in real time rather than just taking static snapshots.

### Start/Stop Tracking Allocations

```python
async def start_tracking_heap_objects(ws, session_id):
    """Start tracking heap object allocations"""
    await cdp(ws, "HeapProfiler.startTrackingHeapObjects", {
        "trackAllocations": True
    }, session_id=session_id)
    print("Started tracking heap object allocations...")


async def stop_tracking_heap_objects(ws, session_id):
    """
    Stop tracking and retrieve allocation data
    Returns a report containing all newly allocated objects
    """
    report = {}
    report_done = asyncio.Event()
    
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": cmd_id,
        "method": "HeapProfiler.stopTrackingHeapObjects",
        "params": {"reportProgress": True, "treatGlobalObjectsAsRoot": True}
    }))
    
    async for resp in ws:
        data = json.loads(resp)
        if data.get("id") == cmd_id:
            report_done.set()
            break
    
    await report_done.wait()
    print("Heap object tracking stopped, report generated")
    return report


async def track_operation(ws, session_id, action_coro):
    """
    Track heap allocations during a specific operation:
    1. Start tracking
    2. Execute the operation
    3. Stop tracking and retrieve the report
    """
    await start_tracking_heap_objects(ws, session_id)
    await action_coro
    report = await stop_tracking_heap_objects(ws, session_id)
    return report
```

### Sampled Allocation Tracking

```python
async def start_sampled_allocation(ws, session_id, sampling_interval=1024*64):
    """
    Start allocation sampling with a specified interval (bytes)
    Larger interval = lower precision but less performance overhead
    """
    await cdp(ws, "HeapProfiler.startSampling", {
        "samplingInterval": sampling_interval,
        "includeObjectsCollectedByMajorGC": True,
        "includeObjectsCollectedByMinorGC": True
    }, session_id=session_id)
    print(f"Started sampled allocation (interval: {sampling_interval / 1024:.0f} KB)")


async def stop_sampled_allocation(ws, session_id):
    """Stop sampling and retrieve the profile"""
    result = await cdp(ws, "HeapProfiler.stopSampling", session_id=session_id)
    profile = result.get("profile", {})
    samples = profile.get("samples", [])
    print(f"Sampling complete: {len(samples)} samples collected")
    return profile
```

---

## Comparing Snapshots to Find Leaks

The most common leak detection approach: **snapshot before operation → execute operation → snapshot after → compare the difference**.

```python
async def compare_snapshots(snapshot_a, snapshot_b):
    """
    Compare two heap snapshots and find newly added objects
    Returns a leak report grouped by type
    """
    nodes_a = snapshot_a.get("nodes", [])
    strings_a = snapshot_a.get("strings", [])
    nodes_b = snapshot_b.get("nodes", [])
    strings_b = snapshot_b.get("strings", [])
    
    # Heap snapshot node format: [type, name_index, id, self_size, edge_count, trace_node_id]
    def extract_type_stats(nodes, strings):
        stats = {}
        for i in range(0, len(nodes), 6):
            node_type = nodes[i]
            name_index = nodes[i + 1]
            self_size = nodes[i + 3]
            
            type_name = strings[name_index] if name_index < len(strings) else f"type_{node_type}"
            stats[type_name] = stats.get(type_name, 0) + self_size
        return stats
    
    stats_a = extract_type_stats(nodes_a, strings_a)
    stats_b = extract_type_stats(nodes_b, strings_b)
    
    # Compute deltas
    all_types = set(list(stats_a.keys()) + list(stats_b.keys()))
    delta_report = {}
    
    for t in sorted(all_types):
        size_a = stats_a.get(t, 0)
        size_b = stats_b.get(t, 0)
        delta = size_b - size_a
        if delta > 1024:  # Only report types with >1KB delta
            delta_report[t] = {
                "before": size_a,
                "after": size_b,
                "delta": delta,
                "delta_kb": delta / 1024
            }
    
    return delta_report


async def detect_leak(ws, session_id, action_coro, threshold_kb=50):
    """
    Complete memory leak detection workflow:
    Snapshot A → Execute action → Snapshot B → Compare
    """
    print("=== Starting Memory Leak Detection ===")
    
    # 1. Baseline snapshot
    print("[1/4] Taking baseline snapshot...")
    snapshot_before = await take_heap_snapshot(ws, session_id)
    
    # 2. Execute the operation
    print("[2/4] Executing target operation...")
    await action_coro
    
    # 3. Trigger GC to reduce noise
    print("[3/4] Triggering garbage collection...")
    await trigger_gc(ws, session_id)
    await asyncio.sleep(1)
    
    # 4. After-operation snapshot
    print("[4/4] Taking post-operation snapshot...")
    snapshot_after = await take_heap_snapshot(ws, session_id)
    
    # Compare
    delta = await compare_snapshots(snapshot_before, snapshot_after)
    
    print("\n=== Leak Detection Report ===")
    if not delta:
        print(" No significant leak detected")
    else:
        print(f" Found {len(delta)} potentially leaking types:")
        for type_name, info in sorted(
            delta.items(), key=lambda x: -x[1]["delta"]
        )[:10]:
            print(f"  {type_name}: +{info['delta_kb']:.1f} KB "
                  f"({info['before']/1024:.1f} → {info['after']/1024:.1f} KB)")
    
    return delta
```

---

## Querying Object Details by ID

When a suspicious object is found in a snapshot, you can get more details using its object ID.

```python
async def get_heap_object_id(ws, session_id, object_group_id):
    """
    Get the heap ID of a JS object
    First gets the RemoteObject via Runtime.evaluate,
    then uses HeapProfiler.getHeapObjectId
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"objects[{object_group_id}]",
        "objectGroup": "leak_detection"
    }, session_id=session_id)
    
    obj = result.get("result", {})
    object_id = obj.get("objectId")
    if not object_id:
        print("Could not get object ID")
        return None
    
    heap_result = await cdp(ws, "HeapProfiler.getHeapObjectId", {
        "objectId": object_id
    }, session_id=session_id)
    
    heap_id = heap_result.get("heapSnapshotObjectId")
    print(f"Object heap ID: {heap_id}")
    return heap_id


async def get_object_by_heap_id(ws, session_id, heap_object_id):
    """
    Get a JS RemoteObject by its heap snapshot object ID
    Useful for inspecting object details in DevTools
    """
    result = await cdp(ws, "HeapProfiler.getObjectByHeapObjectId", {
        "objectId": heap_object_id,
        "objectGroup": "inspection"
    }, session_id=session_id)
    
    obj = result.get("result", {})
    print(f"Object type: {obj.get('type')}")
    print(f"Object class: {obj.get('className', 'N/A')}")
    if "description" in obj:
        print(f"Object description: {obj['description']}")
    
    return obj
```

---

## Retrieving Memory Metrics

The Performance domain provides low-overhead memory usage indicators suitable for long-term monitoring.

```python
async def get_memory_metrics(ws, session_id):
    """Get page memory-related performance metrics"""
    result = await cdp(ws, "Performance.getMetrics", session_id=session_id)
    metrics = result.get("metrics", [])
    
    memory_metrics = {}
    for m in metrics:
        name = m["name"]
        value = m["value"]
        if "heap" in name.lower() or "memory" in name.lower():
            memory_metrics[name] = value
    
    return memory_metrics


async def print_memory_stats(ws, session_id):
    """Print memory statistics in human-readable format"""
    metrics = await get_memory_metrics(ws, session_id)
    
    print("=== Page Memory Statistics ===")
    for name, value in metrics.items():
        if "size" in name.lower():
            print(f"  {name}: {value / 1024 / 1024:.2f} MB")
        elif "count" in name.lower():
            print(f"  {name}: {int(value)}")
        else:
            print(f"  {name}: {value}")


async def monitor_memory(ws, session_id, interval=2, duration=60):
    """
    Continuously monitor memory usage
    - interval: sampling interval in seconds
    - duration: monitoring duration in seconds
    Returns a list of sample data points
    """
    samples = []
    start = asyncio.get_event_loop().time()
    
    print(f"Starting memory monitoring (interval: {interval}s, duration: {duration}s)")
    
    while True:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed > duration:
            break
        
        result = await cdp(ws, "Performance.getMetrics", session_id=session_id)
        metrics = {m["name"]: m["value"] for m in result.get("metrics", [])}
        
        sample = {
            "timestamp": elapsed,
            "js_heap_size": metrics.get("JSHeapUsedSize", 0),
            "js_heap_total": metrics.get("JSHeapTotalSize", 0),
            "dom_nodes": metrics.get("DomCount", 0)
        }
        samples.append(sample)
        
        print(f"  [{elapsed:5.1f}s] JS heap: {sample['js_heap_size']/1024/1024:.1f} MB "
              f"/ {sample['js_heap_total']/1024/1024:.1f} MB, "
              f"DOM nodes: {sample['dom_nodes']}")
        
        await asyncio.sleep(interval)
    
    # Trend analysis
    if len(samples) >= 2:
        first = samples[0]["js_heap_size"]
        last = samples[-1]["js_heap_size"]
        growth = last - first
        print(f"\nMonitoring complete: JS heap {first/1024/1024:.1f} → {last/1024/1024:.1f} MB "
              f"({'grew' if growth > 0 else 'shrunk'} {abs(growth)/1024/1024:.1f} MB)")
    
    return samples
```

---

## Triggering Garbage Collection

Manually triggering GC before snapshot comparison reduces noise for clearer results.

```python
async def trigger_gc(ws, session_id):
    """Manually trigger JavaScript garbage collection"""
    await cdp(ws, "HeapProfiler.collectGarbage", session_id=session_id)
    print("GC triggered")


async def trigger_gc_and_wait(ws, session_id, wait=2):
    """
    Trigger GC and wait for completion
    Recommended before taking a baseline snapshot
    """
    await trigger_gc(ws, session_id)
    await asyncio.sleep(wait)
    
    # Verify the effect
    result = await cdp(ws, "Performance.getMetrics", session_id=session_id)
    metrics = {m["name"]: m["value"] for m in result.get("metrics", [])}
    heap_used = metrics.get("JSHeapUsedSize", 0)
    print(f"Post-GC JS heap size: {heap_used / 1024 / 1024:.1f} MB")
    return heap_used


async def gc_and_snapshot(ws, session_id):
    """Trigger GC then immediately take a heap snapshot"""
    await trigger_gc_and_wait(ws, session_id)
    snapshot = await take_heap_snapshot(ws, session_id)
    print("Post-GC snapshot complete")
    return snapshot
```

---

## Practical: Automated Leak Detection Script

Combine all the above techniques into a complete leak detection script:

```python
async def full_leak_detection(ws, session_id, url, repeat_actions, repeat_count=5):
    """
    Complete automated leak detection workflow
    
    Args:
        url: Target page URL
        repeat_actions: Async function to execute each iteration
        repeat_count: Number of iterations
    """
    # Navigate to page
    await cdp(ws, "Page.enable", session_id=session_id)
    await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
    await asyncio.sleep(3)
    
    # Enable required domains
    await enable_heap_profiler(ws, session_id)
    await enable_performance(ws, session_id)
    
    snapshots = []
    metrics_log = []
    
    for i in range(repeat_count + 1):
        # GC cleanup
        await trigger_gc(ws, session_id)
        await asyncio.sleep(1)
        
        # Take snapshot
        print(f"\n--- Snapshot {i} ---")
        snap = await take_heap_snapshot(ws, session_id)
        snapshots.append(snap)
        await print_memory_stats(ws, session_id)
        
        # Execute action (skip after initial snapshot)
        if i < repeat_count:
            print(f"\nExecuting operation (round {i + 1}/{repeat_count})...")
            await repeat_actions(ws, session_id)
    
    # Analyze changes between all snapshots
    print("\n" + "=" * 50)
    print("=== Leak Analysis Report ===")
    print("=" * 50)
    
    for i in range(len(snapshots) - 1):
        delta = await compare_snapshots(snapshots[i], snapshots[i + 1])
        
        total_delta = sum(v["delta"] for v in delta.values())
        print(f"\nSnapshot {i} → {i + 1}: total change {total_delta / 1024:.1f} KB")
        
        if total_delta > 100 * 1024:  # Over 100KB
            print(f"  ⚠️ Suspicious! Significant heap growth after round {i + 1}")
            for type_name, info in sorted(
                delta.items(), key=lambda x: -x[1]["delta"]
            )[:5]:
                print(f"    Type: {type_name}, +{info['delta_kb']:.1f} KB")
    
    return snapshots, metrics_log


async def example_leak_scenario(ws, session_id):
    """Example: simulate a common leak - DOM node references not released"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            if (!window.leakedNodes) window.leakedNodes = [];
            for (let i = 0; i < 100; i++) {
                let div = document.createElement('div');
                div.innerHTML = 'leaked ' + i;
                document.body.appendChild(div);
                window.leakedNodes.push(div);
            }
            window.leakedNodes.length
        """
    }, session_id=session_id)
    count = result.get("result", {}).get("value", 0)
    print(f"Leaked nodes created: {count}")


async def run_leak_detection():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        await full_leak_detection(
            ws, session_id,
            url="about:blank",
            repeat_actions=example_leak_scenario,
            repeat_count=3
        )

# asyncio.run(run_leak_detection())
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Snapshot Size Control

Heap snapshots can be very large (100MB+ for big pages):

```python
# Handling large snapshots
# 1. Use streaming via addHeapSnapshotChunk events
# 2. Avoid keeping multiple snapshots in memory
# 3. Release snapshot references promptly

snapshot_a = await take_heap_snapshot(ws, session_id)
# ... use it ...
snapshot_a = None  # Explicitly release
```

### Pitfall 2: GC Timing is Critical

```python
# ❌ Direct comparison includes GC-reclaimable noise
snap1 = await take_heap_snapshot(ws, session_id)
await some_operation(ws, session_id)
snap2 = await take_heap_snapshot(ws, session_id)

# ✅ Trigger GC before each snapshot
await trigger_gc(ws, session_id)
snap1 = await take_heap_snapshot(ws, session_id)
await some_operation(ws, session_id)
await trigger_gc(ws, session_id)
snap2 = await take_heap_snapshot(ws, session_id)
```

### Pitfall 3: HeapProfiler.getHeapObjectId Requires Prior Tracking

```python
# getHeapObjectId only works during active tracking
# Ensure startTrackingHeapObjects or takeHeapSnapshot was called first
```

### Pitfall 4: Performance.getMetrics Limitations

```python
# Performance.getMetrics returns approximate values
# Use HeapProfiler snapshots for precise analysis
# Suitable for trend monitoring, not exact diagnostics
```

### Best Practices Checklist

| Note | Recommendation |
|------|---------------|
| Snapshot memory | Large pages can produce 100MB+ snapshots, manage memory |
| GC timing | Always trigger GC before snapshot comparison |
| Iterations | Run 3-5 cycles for trend analysis, avoid one-off flukes |
| Sampling interval | Set startSampling interval to 64KB+ to reduce overhead |
| Object groups | Use objectGroup for temporary objects, release when done |
| Baseline | First result may be inflated (load overhead), trust subsequent comparisons |

---

## Complete Reference: CDP Memory Profiler Class

```python
class CDPMemoryProfiler:
    """CDP Memory Analysis Manager"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
    async def _cmd(self, method, params=None):
        self._cmd_id += 1
        msg = {"id": self._cmd_id, "method": method, "params": params or {}}
        if self.session_id:
            msg["sessionId"] = self.session_id
        await self.ws.send(json.dumps(msg))
        async for resp in self.ws:
            data = json.loads(resp)
            if data.get("id") == self._cmd_id:
                return data.get("result", {})
    
    async def enable(self):
        """Enable all memory profiling domains"""
        await self._cmd("HeapProfiler.enable")
        await self._cmd("Performance.enable")
        print("Memory profiler ready")
    
    async def snapshot(self, filepath=None):
        """Take a heap snapshot"""
        chunks, done = [], asyncio.Event()
        
        self._cmd_id += 1
        cid = self._cmd_id
        await self.ws.send(json.dumps({
            "sessionId": self.session_id, "id": cid,
            "method": "HeapProfiler.takeHeapSnapshot",
            "params": {}
        }))
        
        async for msg in self.ws:
            data = json.loads(msg)
            if data.get("method") == "HeapProfiler.addHeapSnapshotChunk":
                chunks.append(data["params"]["chunk"])
            elif data.get("id") == cid:
                done.set()
                break
        
        await done.wait()
        raw = "".join(chunks)
        
        if filepath:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(raw)
        
        return json.loads(raw) if not filepath else filepath
    
    async def start_tracking(self):
        await self._cmd("HeapProfiler.startTrackingHeapObjects",
                        {"trackAllocations": True})
    
    async def stop_tracking(self):
        await self._cmd("HeapProfiler.stopTrackingHeapObjects",
                        {"reportProgress": True})
    
    async def gc(self):
        await self._cmd("HeapProfiler.collectGarbage")
    
    async def get_metrics(self):
        result = await self._cmd("Performance.getMetrics")
        metrics = {}
        for m in result.get("metrics", []):
            if "heap" in m["name"].lower():
                metrics[m["name"]] = m["value"]
        return metrics
```

**Usage Example:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    profiler = CDPMemoryProfiler(ws, session_id)
    
    await profiler.enable()
    await profiler.gc()
    
    # Take a baseline snapshot
    baseline = await profiler.snapshot()
    
    # ... execute operations ...
    
    # Take another snapshot and compare
    current = await profiler.snapshot()
    delta = await compare_snapshots(baseline, current)
    
    # Check memory metrics
    stats = await profiler.get_metrics()
```

---

> **Summary**: CDP's HeapProfiler and Performance domains provide powerful memory analysis capabilities. By combining heap snapshots, object tracking, snapshot comparison, and GC control, you can build automated memory leak detection tools. The key is to properly use GC to reduce noise, compare snapshots to pinpoint problems, and use Performance metrics for trend monitoring.

---

*Previous: CDP CI/CD Integration Guide: Deploying Browser Automation with Docker*

*Next up: CDP Clipboard Operations Guide: Reading & Writing Clipboard with Python*