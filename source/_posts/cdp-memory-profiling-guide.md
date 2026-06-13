---
title: CDP 内存分析指南：用 Python 检测内存泄漏
date: 2026-06-05 19:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Memory
  - HeapProfiler
  - Profiling
  - Leak Detection
categories:
  - CDP 进阶
  - Python 实战
description: 全面讲解如何用 CDP 的 HeapProfiler 和 Performance 域进行浏览器内存分析。涵盖获取堆快照、跟踪堆对象分配、对比快照找泄漏、触发 GC、读取内存指标等实用技术。
---

> **一句话总结**：CDP 的 HeapProfiler 和 Performance 域提供了完整的浏览器内存分析能力——你可以编程地获取堆快照、跟踪对象分配、通过快照对比定位内存泄漏，就像在 DevTools Memory 面板中操作一样。

---

## 目录

1. [为什么用 CDP 做内存分析](#为什么用-cdp-做内存分析)
2. [基础：连接与初始化](#基础连接与初始化)
3. [获取堆快照](#获取堆快照)
4. [跟踪堆对象分配](#跟踪堆对象分配)
5. [快照对比定位泄漏](#快照对比定位泄漏)
6. [通过对象 ID 查询详情](#通过对象-id-查询详情)
7. [获取内存统计指标](#获取内存统计指标)
8. [手动触发垃圾回收](#手动触发垃圾回收)
9. [实战：自动泄漏检测脚本](#实战自动泄漏检测脚本)
10. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 做内存分析

| 功能 | DevTools Memory 面板 | CDP HeapProfiler API |
|------|---------------------|---------------------|
| 自动化 | 手动操作 | 全脚本化，可集成 CI/CD |
| 快照对比 | 手动选择两个快照 | 编程对比，自动计算增量 |
| 长期监控 | 不适合长时间跟踪 | 可运行数小时持续监控 |
| 对象跟踪 | 开启记录后手动查看 | 精确控制开始/停止时机 |
| 堆快照大小 | 受 DevTools 界面限制 | 可自定义流式处理 |
| 批量分析 | 逐个手动操作 | 可批量分析多个页面 |

---

## 基础：连接与初始化

### 统一 CDP 辅助函数

所有示例使用统一的 CDP 消息模式：

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
    """附加到第一个可用的页面目标"""
    result = await cdp(ws, "Target.getTargets")
    target_id = result["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

### 启用 HeapProfiler

```python
async def enable_heap_profiler(ws, session_id):
    """启用堆分析器"""
    await cdp(ws, "HeapProfiler.enable", session_id=session_id)
    print("HeapProfiler 已启用")


async def enable_performance(ws, session_id):
    """启用 Performance 域"""
    await cdp(ws, "Performance.enable", session_id=session_id)
    print("Performance 已启用")
```

---

## 获取堆快照

堆快照是内存分析的基石。它记录某一时刻 JS 堆中所有对象及其引用关系。

### 原生 HeapProfiler API

```python
async def take_heap_snapshot(ws, session_id):
    """
    获取当前页面的堆快照
    返回解析后的堆快照数据
    """
    chunks = []
    
    # 注册数据回调
    async def collect_chunk():
        async for resp in ws:
            data = json.loads(resp)
            method = data.get("method", "")
            if method == "HeapProfiler.addHeapSnapshotChunk":
                chunk = data["params"]["chunk"]
                chunks.append(chunk)
            elif data.get("id") == snapshot_id:
                return data.get("result", {})
    
    # 触发快照
    CMD_ID[0] += 1
    snapshot_id = CMD_ID[0]
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": snapshot_id,
        "method": "HeapProfiler.takeHeapSnapshot",
        "params": {}
    }))
    
    # 等待快照完成
    await collect_chunk()
    
    # 合并所有分块
    raw_data = "".join(chunks)
    snapshot = json.loads(raw_data)
    
    print(f"堆快照完成: {len(snapshot.get('nodes', [])) // 6} 个节点, "
          f"{len(snapshot.get('edges', [])) // 3} 条边")
    print(f"快照大小: {len(raw_data) / 1024:.1f} KB")
    return snapshot


async def save_snapshot_to_file(ws, session_id, filepath):
    """获取堆快照并保存到文件"""
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
    print(f"堆快照已保存到: {filepath} ({len(raw) / 1024:.1f} KB)")
    return filepath
```

---

## 跟踪堆对象分配

有时你需要实时监控对象分配过程，而不是仅仅拍摄静态快照。

### 开始/停止跟踪分配

```python
async def start_tracking_heap_objects(ws, session_id):
    """开始跟踪堆对象分配"""
    await cdp(ws, "HeapProfiler.startTrackingHeapObjects", {
        "trackAllocations": True
    }, session_id=session_id)
    print("开始跟踪堆对象分配...")


async def stop_tracking_heap_objects(ws, session_id):
    """
    停止跟踪并获取分配数据
    返回包含所有新分配对象的报告
    """
    report = {}
    report_done = asyncio.Event()
    
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    
    # 监听 reportHeapSnapshotProgress 和最后的 addHeapSnapshotChunk
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
    print("堆对象跟踪已停止，报告已生成")
    return report


async def track_operation(ws, session_id, action_coro):
    """
    跟踪特定操作期间的堆分配：
    1. 开始跟踪
    2. 执行操作
    3. 停止跟踪并获取分配报告
    """
    await start_tracking_heap_objects(ws, session_id)
    
    # 执行目标操作
    await action_coro
    
    # 停止跟踪
    report = await stop_tracking_heap_objects(ws, session_id)
    return report
```

### 跟踪带采样

```python
async def start_sampled_allocation(ws, session_id, sampling_interval=1024*64):
    """
    以指定的采样间隔（字节）跟踪分配
    更大的间隔 = 更低的精度但更小的性能开销
    """
    await cdp(ws, "HeapProfiler.startSampling", {
        "samplingInterval": sampling_interval,
        "includeObjectsCollectedByMajorGC": True,
        "includeObjectsCollectedByMinorGC": True
    }, session_id=session_id)
    print(f"开始采样分配（间隔: {sampling_interval / 1024:.0f} KB）")


async def stop_sampled_allocation(ws, session_id):
    """停止采样并获取采样数据"""
    result = await cdp(ws, "HeapProfiler.stopSampling", session_id=session_id)
    profile = result.get("profile", {})
    samples = profile.get("samples", [])
    print(f"采样完成: 共 {len(samples)} 个样本")
    return profile
```

---

## 快照对比定位泄漏

内存泄漏最常见的检测方法是：**操作前拍一张快照 → 执行操作 → 操作后再拍一张 → 对比两张快照的差异**。

```python
async def compare_snapshots(snapshot_a, snapshot_b):
    """
    对比两张堆快照，找出新增的对象
    返回按类型归类的泄漏报告
    """
    nodes_a = snapshot_a.get("nodes", [])
    strings_a = snapshot_a.get("strings", [])
    nodes_b = snapshot_b.get("nodes", [])
    strings_b = snapshot_b.get("strings", [])
    
    # 提取每个快照的节点类型和大小
    # 堆快照节点格式: [type, name_index, id, self_size, edge_count, trace_node_id]
    
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
    
    # 计算增量
    all_types = set(list(stats_a.keys()) + list(stats_b.keys()))
    delta_report = {}
    
    for t in sorted(all_types):
        size_a = stats_a.get(t, 0)
        size_b = stats_b.get(t, 0)
        delta = size_b - size_a
        if delta > 1024:  # 只报告增量超过 1KB 的类型
            delta_report[t] = {
                "before": size_a,
                "after": size_b,
                "delta": delta,
                "delta_kb": delta / 1024
            }
    
    return delta_report


async def detect_leak(ws, session_id, action_coro, threshold_kb=50):
    """
    完整的内存泄漏检测流程：
    快照A → 执行可疑操作 → 快照B → 对比
    """
    print("=== 开始内存泄漏检测 ===")
    
    # 1. 操作前快照
    print("[1/4] 拍摄操作前快照...")
    snapshot_before = await take_heap_snapshot(ws, session_id)
    
    # 2. 执行操作
    print("[2/4] 执行目标操作...")
    await action_coro
    
    # 3. 触发 GC 清除杂音
    print("[3/4] 触发垃圾回收...")
    await trigger_gc(ws, session_id)
    await asyncio.sleep(1)
    
    # 4. 操作后快照
    print("[4/4] 拍摄操作后快照...")
    snapshot_after = await take_heap_snapshot(ws, session_id)
    
    # 对比
    delta = await compare_snapshots(snapshot_before, snapshot_after)
    
    print("\n=== 泄漏检测报告 ===")
    if not delta:
        print("✅ 未检测到明显泄漏")
    else:
        print(f"⚠️ 发现 {len(delta)} 个可能存在泄漏的类型:")
        for type_name, info in sorted(
            delta.items(), key=lambda x: -x[1]["delta"]
        )[:10]:
            print(f"  {type_name}: +{info['delta_kb']:.1f} KB "
                  f"({info['before']/1024:.1f} → {info['after']/1024:.1f} KB)")
    
    return delta
```

---

## 通过对象 ID 查询详情

当快照中发现可疑对象时，可以通过对象 ID 获取更多信息。

```python
async def get_heap_object_id(ws, session_id, object_group_id):
    """
    根据 JS 对象获取其在堆中的唯一 ID
    先用 Runtime.evaluate 获取对象的 RemoteObject
    然后通过 HeapProfiler.getHeapObjectId 获取堆 ID
    """
    # 先获取 Object 的 RemoteObject
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"objects[{object_group_id}]",
        "objectGroup": "leak_detection"
    }, session_id=session_id)
    
    obj = result.get("result", {})
    object_id = obj.get("objectId")
    if not object_id:
        print("无法获取对象 ID")
        return None
    
    # 获取堆对象 ID
    heap_result = await cdp(ws, "HeapProfiler.getHeapObjectId", {
        "objectId": object_id
    }, session_id=session_id)
    
    heap_id = heap_result.get("heapSnapshotObjectId")
    print(f"对象堆 ID: {heap_id}")
    return heap_id


async def get_object_by_heap_id(ws, session_id, heap_object_id):
    """
    通过堆快照中的对象 ID 获取 JS RemoteObject
    可用于在 DevTools 中查看对象详情
    """
    result = await cdp(ws, "HeapProfiler.getObjectByHeapObjectId", {
        "objectId": heap_object_id,
        "objectGroup": "inspection"
    }, session_id=session_id)
    
    obj = result.get("result", {})
    print(f"对象类型: {obj.get('type')}")
    print(f"对象类名: {obj.get('className', 'N/A')}")
    if "description" in obj:
        print(f"对象描述: {obj['description']}")
    
    return obj
```

---

## 获取内存统计指标

Performance 域提供了低开销的内存使用量指标，适合长期监控。

```python
async def get_memory_metrics(ws, session_id):
    """
    获取页面内存相关性能指标
    返回所有 metrics 的字典
    """
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
    """以可读格式打印内存统计"""
    metrics = await get_memory_metrics(ws, session_id)
    
    print("=== 页面内存统计 ===")
    for name, value in metrics.items():
        if "size" in name.lower():
            print(f"  {name}: {value / 1024 / 1024:.2f} MB")
        elif "count" in name.lower():
            print(f"  {name}: {int(value)}")
        else:
            print(f"  {name}: {value}")


async def monitor_memory(ws, session_id, interval=2, duration=60):
    """
    持续监控内存使用量
    - interval: 采样间隔（秒）
    - duration: 监控持续时间（秒）
    返回采样数据列表
    """
    samples = []
    start = asyncio.get_event_loop().time()
    
    print(f"开始内存监控（间隔: {interval}s, 持续时间: {duration}s）")
    
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
        
        print(f"  [{elapsed:5.1f}s] JS 堆: {sample['js_heap_size']/1024/1024:.1f} MB "
              f"/ {sample['js_heap_total']/1024/1024:.1f} MB, "
              f"DOM 节点: {sample['dom_nodes']}")
        
        await asyncio.sleep(interval)
    
    # 分析趋势
    if len(samples) >= 2:
        first = samples[0]["js_heap_size"]
        last = samples[-1]["js_heap_size"]
        growth = last - first
        print(f"\n监控结束: JS 堆变化 {first/1024/1024:.1f} → {last/1024/1024:.1f} MB "
              f"({'增长' if growth > 0 else '减少'}{abs(growth)/1024/1024:.1f} MB)")
    
    return samples
```

---

## 手动触发垃圾回收

在快照对比前手动触发 GC 可以减少"噪音"，让结果更清晰。

```python
async def trigger_gc(ws, session_id):
    """手动触发 JavaScript 垃圾回收"""
    await cdp(ws, "HeapProfiler.collectGarbage", session_id=session_id)
    print("GC 已触发")


async def trigger_gc_and_wait(ws, session_id, wait=2):
    """
    触发 GC 并等待完成
    推荐在拍摄基准快照前使用
    """
    await trigger_gc(ws, session_id)
    
    # 等待 GC 完成并让堆稳定
    await asyncio.sleep(wait)
    
    # 验证效果
    result = await cdp(ws, "Performance.getMetrics", session_id=session_id)
    metrics = {m["name"]: m["value"] for m in result.get("metrics", [])}
    heap_used = metrics.get("JSHeapUsedSize", 0)
    print(f"GC 后 JS 堆大小: {heap_used / 1024 / 1024:.1f} MB")
    return heap_used


async def gc_and_snapshot(ws, session_id):
    """触发 GC 后立即拍摄堆快照"""
    await trigger_gc_and_wait(ws, session_id)
    snapshot = await take_heap_snapshot(ws, session_id)
    print("GC 后快照已完成")
    return snapshot
```

---

## 实战：自动泄漏检测脚本

结合以上所有技术，编写一个完整的泄漏检测脚本：

```python
async def full_leak_detection(ws, session_id, url, repeat_actions, repeat_count=5):
    """
    完整的自动泄漏检测流程
    
    参数:
        url: 目标页面 URL
        repeat_actions: 每次重复时要执行的协程函数
        repeat_count: 重复次数
    """
    # 导航到页面
    await cdp(ws, "Page.enable", session_id=session_id)
    await cdp(ws, "Page.navigate", {"url": url}, session_id=session_id)
    await asyncio.sleep(3)
    
    # 启用所需域
    await enable_heap_profiler(ws, session_id)
    await enable_performance(ws, session_id)
    
    snapshots = []
    metrics_log = []
    
    for i in range(repeat_count + 1):  # 额外多一次初始快照
        # GC 清理
        await trigger_gc(ws, session_id)
        await asyncio.sleep(1)
        
        # 拍摄快照
        print(f"\n--- 第 {i} 次快照 ---")
        snap = await take_heap_snapshot(ws, session_id)
        snapshots.append(snap)
        
        # 记录性能指标
        mem = await print_memory_stats(ws, session_id)
        
        # 执行操作（初始快照后不执行）
        if i < repeat_count:
            print(f"\n执行操作（第 {i + 1}/{repeat_count} 轮）...")
            await repeat_actions(ws, session_id)
    
    # 分析所有快照之间的变化
    print("\n" + "=" * 50)
    print("=== 泄漏分析报告 ===")
    print("=" * 50)
    
    for i in range(len(snapshots) - 1):
        delta = await compare_snapshots(snapshots[i], snapshots[i + 1])
        
        total_delta = sum(v["delta"] for v in delta.values())
        print(f"\n快照 {i} → {i + 1}: 总变化 {total_delta / 1024:.1f} KB")
        
        if total_delta > 100 * 1024:  # 超过 100KB
            print(f"  ⚠️ 可疑！第 {i + 1} 次操作后堆增长显著")
            for type_name, info in sorted(
                delta.items(), key=lambda x: -x[1]["delta"]
            )[:5]:
                print(f"    类型: {type_name}, +{info['delta_kb']:.1f} KB")
    
    return snapshots, metrics_log


async def example_leak_scenario(ws, session_id):
    """示例：模拟一个常见的内存泄漏场景-DOM 节点引用未释放"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            // 模拟内存泄漏：不断创建 DOM 节点并持有引用
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
    print(f"已创建泄漏节点: {count}")


# 运行完整检测
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

## 常见踩坑与最佳实践

### 踩坑 1：快照大小控制

堆快照可能非常庞大（大型页面可达 100MB+），需注意：

```python
# 大快照的处理策略
# 1. 使用流式处理（addHeapSnapshotChunk 事件）
# 2. 避免在内存中保留多个快照
# 3. 适时释放快照引用

# 比较完后及时释放
snapshot_a = await take_heap_snapshot(ws, session_id)
# ... 使用 ...
snapshot_a = None  # 显式释放
```

### 踩坑 2：GC 时机很关键

```python
# ❌ 直接对比可能包含很多 GC 可回收的"噪音"
snap1 = await take_heap_snapshot(ws, session_id)
await some_operation(ws, session_id)
snap2 = await take_heap_snapshot(ws, session_id)

# ✅ 在快照前主动触发 GC
await trigger_gc(ws, session_id)
snap1 = await take_heap_snapshot(ws, session_id)
await some_operation(ws, session_id)
await trigger_gc(ws, session_id)
snap2 = await take_heap_snapshot(ws, session_id)
```

### 踩坑 3：HeapProfiler.getHeapObjectId 需要对象先被追踪

```python
# HeapProfiler.getHeapObjectId 只在追踪期间有效
# 确认先调用了 startTrackingHeapObjects 或 takeHeapSnapshot
```

### 踩坑 4：Performance.getMetrics 的局限性

```python
# 注意：Performance.getMetrics 返回的是粗略值
# 精确分析仍需 HeapProfiler 快照
# 适合趋势监控而不是精确诊断
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 快照内存 | 大页面快照可达 100MB+，注意内存管理 |
| GC 时机 | 快照对比前务必先触发 GC |
| 重复次数 | 至少执行 3-5 次操作取趋势，避免偶然性 |
| 采样间隔 | startSampling 的间隔设 64KB 以上减少开销 |
| 对象组 | 使用 objectGroup 管理临时对象，用完释放 |
| 对比基准 | 首次结果可能偏高（加载开销），以后续对比为准 |

---

## 完整参考：CDP 内存分析管理类

```python
class CDPMemoryProfiler:
    """CDP 内存分析管理器"""
    
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
        """启用所有内存分析相关域"""
        await self._cmd("HeapProfiler.enable")
        await self._cmd("Performance.enable")
        print("内存分析器已就绪")
    
    async def snapshot(self, filepath=None):
        """拍摄堆快照"""
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

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    profiler = CDPMemoryProfiler(ws, session_id)
    
    await profiler.enable()
    await profiler.gc()
    
    # 拍摄基准快照
    baseline = await profiler.snapshot()
    
    # ... 执行操作 ...
    
    # 再次拍摄并对比
    current = await profiler.snapshot()
    delta = await compare_snapshots(baseline, current)
    
    # 查看内存指标
    stats = await profiler.get_metrics()
```

---

> **总结**：CDP 的 HeapProfiler 和 Performance 域提供了强大的内存分析能力。通过堆快照、对象跟踪、快照对比和 GC 控制，你可以构建自动化的内存泄漏检测工具。关键在于合理利用 GC 清理噪音、通过快照对比定位问题，以及结合 Performance 指标做趋势监控。

---

*上一篇回顾：CDP CI/CD 集成指南：用 Docker 部署浏览器自动化。*

*下一篇预告：CDP 剪贴板操作指南：用 Python 读写系统剪贴板。*