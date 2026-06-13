---
lang: en
title: "CDP Background Services Guide: Managing Background Sync & Fetch with Python"
date: "2026-06-05 15:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Background Sync
  - Background Fetch
  - Service Worker
  - Offline Capabilities
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to debugging browser background services using CDP's BackgroundService domain — covering Background Sync, Background Fetch, Service Worker offline capabilities, and recording/replaying background events.
---

> **Summary in one sentence**: CDP's `BackgroundService` domain provides complete debugging capabilities for browser background services — you can capture Background Sync and Background Fetch events, record their parameter details, simulate offline scenarios, and gain full visibility into Service Worker background operations.

---

## Table of Contents

1. [BackgroundService Domain Overview](#backgroundservice-domain-overview)
2. [Enabling Background Service Monitoring](#enabling-background-service-monitoring)
3. [Capturing Background Sync Events](#capturing-background-sync-events)
4. [Capturing Background Fetch Events](#capturing-background-fetch-events)
5. [Background Event Parameter Reference](#background-event-parameter-reference)
6. [Recording and Replaying Background Events](#recording-and-replaying-background-events)
7. [Practical: Service Worker Offline Debugging](#practical-service-worker-offline-debugging)
8. [Best Practices and Considerations](#best-practices-and-considerations)

---

## BackgroundService Domain Overview

BackgroundService is the CDP domain specifically designed for debugging browser background services. It provides transparent access to the following background services:

| Service Name | Description | Typical Use Case |
|-------------|-------------|------------------|
| `backgroundSync` | Background Sync | Queue requests offline, auto-retry when online |
| `backgroundFetch` | Background Fetch | Manage large file/resource downloads in the background |
| `periodicBackgroundSync` | Periodic Background Sync | Periodically update cached content |
| `pushMessaging` | Push Messaging | Receive server push notifications |
| `notifications` | Notifications | Display and interact with notifications |
| `paymentHandler` | Payment Handling | Debug Web Payment API calls |

Through the `BackgroundService` domain, you can:

1. **Listen for events** — capture every event triggered by background services
2. **Record details** — get all parameters and timestamps of each event
3. **Record/Replay** — record background event sequences for later replay analysis
4. **Clear recordings** — clear recorded events when needed

---

## Enabling Background Service Monitoring

### Basic Connection and Domain Enablement

```python
import asyncio
import websockets
import json
from datetime import datetime

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


async def connect_and_enable_background_services(ws):
    """Connect to a page and enable background service monitoring"""
    targets = await cdp(ws, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    result = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    session_id = result["sessionId"]
    
    await cdp(ws, "BackgroundService.startObserving", {
        "service": "backgroundSync"
    }, session_id)
    
    await cdp(ws, "BackgroundService.startObserving", {
        "service": "backgroundFetch"
    }, session_id)
    
    print(f"[Background Services] Monitoring started, session: {session_id[:8]}...")
    return session_id
```

### Monitoring All Background Services

```python
class BackgroundServiceMonitor:
    """Background service monitor — unified management of background service listeners"""
    
    SERVICE_NAMES = [
        "backgroundSync",
        "backgroundFetch",
        "periodicBackgroundSync",
        "pushMessaging",
        "notifications",
        "paymentHandler",
    ]
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.events = {name: [] for name in self.SERVICE_NAMES}
        self._callbacks = {}
    
    async def enable_all(self):
        """Enable monitoring for all background services"""
        for service in self.SERVICE_NAMES:
            try:
                await cdp(self.ws, "BackgroundService.startObserving", {
                    "service": service
                }, self.session_id)
                print(f"  [Enabled] {service}")
            except Exception as e:
                print(f"  [Failed] {service}: {e}")
            await asyncio.sleep(0.1)
        print(f"[Background Services] Enabled {len(self.SERVICE_NAMES)} services")
    
    async def enable(self, service_name):
        """Enable monitoring for a specific background service"""
        if service_name not in self.SERVICE_NAMES:
            raise ValueError(f"Unknown background service: {service_name}")
        
        await cdp(self.ws, "BackgroundService.startObserving", {
            "service": service_name
        }, self.session_id)
        print(f"[Enabled] {service_name}")
    
    async def disable(self, service_name):
        """Stop monitoring a specific background service"""
        await cdp(self.ws, "BackgroundService.stopObserving", {
            "service": service_name
        }, self.session_id)
        print(f"[Stopped] {service_name}")
    
    async def disable_all(self):
        """Stop monitoring all background services"""
        for service in self.SERVICE_NAMES:
            await self.disable(service)
    
    def on_event(self, service_name=None):
        """Register an event callback"""
        def decorator(handler):
            if service_name:
                if service_name not in self._callbacks:
                    self._callbacks[service_name] = []
                self._callbacks[service_name].append(handler)
            else:
                for name in self.SERVICE_NAMES:
                    if name not in self._callbacks:
                        self._callbacks[name] = []
                    self._callbacks[name].append(handler)
            return handler
        return decorator
    
    async def listen(self, duration=60):
        """Listen for background service events"""
        start = asyncio.get_event_loop().time()
        event_count = 0
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                method = data.get("method", "")
                params = data.get("params", {})
                
                if method == "BackgroundService.backgroundServiceEventReceived":
                    event = params.get("backgroundServiceEvent", {})
                    service = event.get("serviceName", "")
                    
                    if service in self.events:
                        self.events[service].append(event)
                        event_count += 1
                        
                        if service in self._callbacks:
                            for callback in self._callbacks[service]:
                                await callback(event)
                        
                        if None in self._callbacks:
                            for callback in self._callbacks[None]:
                                await callback(event)
                        
            except asyncio.TimeoutError:
                continue
        
        return event_count
    
    def get_events(self, service_name=None, clear=False):
        """Get recorded events"""
        if service_name:
            events = self.events.get(service_name, [])
            if clear:
                self.events[service_name] = []
            return events
        
        result = {}
        for name in self.SERVICE_NAMES:
            result[name] = list(self.events[name])
            if clear:
                self.events[name] = []
        return result
    
    async def clear_events(self, service_name=None):
        """Clear background service event records"""
        if service_name:
            await cdp(self.ws, "BackgroundService.clearEvents", {
                "service": service_name
            }, self.session_id)
            self.events[service_name] = []
        else:
            for service in self.SERVICE_NAMES:
                await cdp(self.ws, "BackgroundService.clearEvents", {
                    "service": service
                }, self.session_id)
                self.events[service] = []
```

---

## Capturing Background Sync Events

### Understanding Background Sync

Background Sync allows a Service Worker to defer actions when the user is offline and retry them when connectivity is restored. This is essential for improving PWA offline experiences.

```python
class BackgroundSyncTracker:
    """Background Sync event tracker"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.sync_events = []
    
    async def enable(self):
        """Enable Background Sync monitoring"""
        await cdp(self.ws, "BackgroundService.startObserving", {
            "service": "backgroundSync"
        }, self.session_id)
        print("[Background Sync] Monitoring enabled")
    
    async def track_sync_events(self, duration=60):
        """Track Background Sync events"""
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                
                if data.get("method") == "BackgroundService.backgroundServiceEventReceived":
                    event = data["params"].get("backgroundServiceEvent", {})
                    
                    if event.get("serviceName") == "backgroundSync":
                        self._process_sync_event(event)
                        
            except asyncio.TimeoutError:
                continue
        
        return self._generate_report()
    
    def _process_sync_event(self, event):
        """Process a single sync event"""
        event_name = event.get("eventName", "")
        instance_id = event.get("instanceId", "")
        timestamp = event.get("timestamp", 0)
        origin = event.get("origin", "")
        
        metadata = {}
        for entry in event.get("eventMetadata", []):
            metadata[entry.get("key", "")] = entry.get("value", "")
        
        sync_event = {
            "name": event_name,
            "instance_id": instance_id,
            "timestamp": datetime.fromtimestamp(timestamp / 1000).isoformat(),
            "origin": origin,
            "metadata": metadata,
        }
        
        self.sync_events.append(sync_event)
        
        tag = metadata.get("tag", "(unknown)")
        print(f"[Sync] {event_name} | tag: {tag} | origin: {origin}")
        
        if event_name == "SyncRegistered":
            print(f"       Sync registered: {tag}")
        elif event_name == "SyncFired":
            print(f"       Sync fired: {tag}")
        elif event_name == "SyncCompleted":
            outcome = metadata.get("outcome", "unknown")
            print(f"       Sync completed: {tag} | outcome: {outcome}")
        elif event_name == "SyncFailed":
            reason = metadata.get("failureReason", "unknown")
            print(f"       Sync failed: {tag} | reason: {reason}")
    
    def _generate_report(self):
        """Generate tracking report"""
        by_name = {}
        for event in self.sync_events:
            name = event["name"]
            if name not in by_name:
                by_name[name] = {"count": 0, "instances": set()}
            by_name[name]["count"] += 1
            by_name[name]["instances"].add(event["instance_id"])
        
        return {
            "total_events": len(self.sync_events),
            "by_event_name": {k: {"count": v["count"], "unique_instances": len(v["instances"])}
                              for k, v in by_name.items()},
            "events": self.sync_events,
            "sync_tags": list(set(
                e["metadata"].get("tag", "")
                for e in self.sync_events
                if "tag" in e.get("metadata", {})
            ))
        }
```

### Simulating Background Sync Scenarios

```python
async def simulate_and_capture_background_sync(ws, session_id):
    """Simulate Background Sync and capture events"""
    sw_js = """
    if ('serviceWorker' in navigator && 'SyncManager' in window) {
        try {
            const registration = await navigator.serviceWorker.ready;
            
            await registration.sync.register('sync-posts');
            console.log('[Sync] Registered: sync-posts');
            
            await registration.sync.register('sync-messages');
            console.log('[Sync] Registered: sync-messages');
            
            await registration.sync.register('sync-analytics-v1');
            console.log('[Sync] Registered: sync-analytics-v1');
            
            return 'Registered 3 sync events';
        } catch (err) {
            return 'Sync registration failed: ' + err.message;
        }
    }
    return 'SyncManager not available';
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"({sw_js})()",
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    print(f"[Simulate] {result.get('result', {}).get('value', '')}")
    await asyncio.sleep(2)
    
    trigger_sync_handler = """
    navigator.serviceWorker.ready.then(reg => {
        console.log('[Sync] Service Worker ready, waiting for sync events...');
    });
    """
    
    await cdp(ws, "Runtime.evaluate", {
        "expression": trigger_sync_handler,
        "returnByValue": True
    }, session_id)
```

---

## Capturing Background Fetch Events

### Understanding Background Fetch

Background Fetch allows large file downloads (videos, PDFs, etc.) to continue even after the user closes the page. It manages download progress through a Service Worker and supports pausing and resuming.

```python
class BackgroundFetchTracker:
    """Background Fetch event tracker"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.fetch_events = []
    
    async def enable(self):
        """Enable Background Fetch monitoring"""
        await cdp(self.ws, "BackgroundService.startObserving", {
            "service": "backgroundFetch"
        }, self.session_id)
        print("[Background Fetch] Monitoring enabled")
    
    async def track_fetch_events(self, duration=60):
        """Track Background Fetch events"""
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                
                if data.get("method") == "BackgroundService.backgroundServiceEventReceived":
                    event = data["params"].get("backgroundServiceEvent", {})
                    
                    if event.get("serviceName") == "backgroundFetch":
                        self._process_fetch_event(event)
                        
            except asyncio.TimeoutError:
                continue
        
        return self._generate_fetch_report()
    
    def _process_fetch_event(self, event):
        """Process a single fetch event"""
        event_name = event.get("eventName", "")
        instance_id = event.get("instanceId", "")
        timestamp = event.get("timestamp", 0)
        origin = event.get("origin", "")
        
        metadata = {}
        for entry in event.get("eventMetadata", []):
            metadata[entry.get("key", "")] = entry.get("value", "")
        
        fetch_event = {
            "name": event_name,
            "instance_id": instance_id,
            "timestamp": datetime.fromtimestamp(timestamp / 1000).isoformat(),
            "origin": origin,
            "metadata": metadata,
        }
        
        self.fetch_events.append(fetch_event)
        
        tag = metadata.get("tag", metadata.get("uniqueId", "(unknown)"))
        
        if event_name == "FetchRegistered":
            url = metadata.get("url", "")
            total = metadata.get("totalDownloadSize", "0")
            print(f"[Fetch] Registered | tag: {tag} | URL: {url[:80]}")
            print(f"        Total size: {total} bytes")
        
        elif event_name == "FetchFired":
            print(f"[Fetch] Fired | tag: {tag}")
        
        elif event_name == "FetchProgress":
            downloaded = metadata.get("downloadedSize", "0")
            total = metadata.get("totalDownloadSize", "0")
            pct = metadata.get("percentComplete", "0")
            print(f"[Fetch] Progress | tag: {tag} | {downloaded}/{total} ({pct}%)")
        
        elif event_name == "FetchCompleted":
            print(f"[Fetch] Completed | tag: {tag}")
        
        elif event_name == "FetchFailed":
            reason = metadata.get("failureReason", "unknown")
            print(f"[Fetch] Failed | tag: {tag} | reason: {reason}")
        
        elif event_name == "FetchAborted":
            print(f"[Fetch] Aborted | tag: {tag}")
        
        elif event_name == "FetchPaused":
            print(f"[Fetch] Paused | tag: {tag}")
        
        elif event_name == "FetchResumed":
            print(f"[Fetch] Resumed | tag: {tag}")
    
    def _generate_fetch_report(self):
        """Generate fetch tracking report"""
        by_name = {}
        total_downloaded = 0
        
        for event in self.fetch_events:
            name = event["name"]
            if name not in by_name:
                by_name[name] = 0
            by_name[name] += 1
            
            if "downloadedSize" in event.get("metadata", {}):
                try:
                    total_downloaded += int(event["metadata"]["downloadedSize"])
                except ValueError:
                    pass
        
        instances = set(e["instance_id"] for e in self.fetch_events)
        
        return {
            "total_events": len(self.fetch_events),
            "unique_instances": len(instances),
            "by_event_name": by_name,
            "events": self.fetch_events,
            "total_downloaded_bytes": total_downloaded,
        }
```

### Simulating Background Fetch Scenarios

```python
async def simulate_and_capture_background_fetch(ws, session_id):
    """Simulate Background Fetch and capture events"""
    fetch_js = """
    (async () => {
        if (!('serviceWorker' in navigator) || !('BackgroundFetchManager' in window)) {
            return 'BackgroundFetchManager not available';
        }
        
        try {
            const registration = await navigator.serviceWorker.ready;
            
            const fetch = await registration.backgroundFetch.fetch(
                'download-manual-v2',
                ['/api/data.json', '/api/image.png'],
                {
                    title: 'Manual Download',
                    icons: [],
                    downloadTotal: 1000000
                }
            );
            
            console.log('[Fetch] Background fetch registered:', fetch);
            return 'Background fetch registered: download-manual-v2';
        } catch (err) {
            return 'Background fetch failed: ' + err.message;
        }
    })();
    """
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": fetch_js,
        "awaitPromise": True,
        "returnByValue": True
    }, session_id)
    
    print(f"[Simulate] {result.get('result', {}).get('value', '')}")
    await asyncio.sleep(2)
```

---

## Background Event Parameter Reference

### BackgroundServiceEvent Structure

Understanding the complete structure of `BackgroundServiceEvent` is key to accurately parsing background events:

```python
class BackgroundServiceEventParser:
    """BackgroundServiceEvent parser — extract all event fields"""
    
    @staticmethod
    def parse(event):
        """Parse a complete background service event"""
        if not event:
            return {}
        
        return {
            "service_name": event.get("serviceName", ""),
            "event_name": event.get("eventName", ""),
            "instance_id": event.get("instanceId", ""),
            "origin": event.get("origin", ""),
            "timestamp": BackgroundServiceEventParser.parse_timestamp(
                event.get("timestamp", 0)
            ),
            "event_metadata": BackgroundServiceEventParser.parse_metadata(
                event.get("eventMetadata", [])
            ),
            "from_log": event.get("fromLog", False),
        }
    
    @staticmethod
    def parse_timestamp(timestamp_ms):
        """Parse timestamp (milliseconds -> ISO format)"""
        if not timestamp_ms:
            return {"raw": 0, "iso": "unknown"}
        
        try:
            dt = datetime.fromtimestamp(timestamp_ms / 1000)
            return {
                "raw": timestamp_ms,
                "iso": dt.isoformat(),
                "readable": dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            }
        except (OSError, ValueError, OverflowError):
            return {"raw": timestamp_ms, "iso": "invalid_timestamp"}
    
    @staticmethod
    def parse_metadata(metadata_list):
        """Parse event metadata list"""
        parsed = {}
        for entry in metadata_list:
            key = entry.get("key", "")
            value = entry.get("value", "")
            parsed[key] = BackgroundServiceEventParser.infer_value(value)
        return parsed
    
    @staticmethod
    def infer_value(raw_value):
        """Infer the value type of metadata"""
        try:
            if "." in raw_value:
                return {"raw": raw_value, "parsed": float(raw_value), "type": "number"}
            return {"raw": raw_value, "parsed": int(raw_value), "type": "integer"}
        except (ValueError, TypeError):
            pass
        
        if raw_value.lower() in ("true", "false"):
            return {"raw": raw_value, "parsed": raw_value.lower() == "true", "type": "boolean"}
        
        if raw_value.startswith(("{", "[")):
            try:
                return {"raw": raw_value, "parsed": json.loads(raw_value), "type": "json"}
            except json.JSONDecodeError:
                pass
        
        return {"raw": raw_value, "parsed": raw_value, "type": "string"}
    
    @staticmethod
    def format_event_readable(parsed_event):
        """Format event as a readable string"""
        lines = []
        lines.append("=" * 60)
        lines.append(f"Background Service Event | {parsed_event['service_name']} | {parsed_event['event_name']}")
        lines.append("=" * 60)
        lines.append(f"  Instance ID: {parsed_event['instance_id']}")
        lines.append(f"  Origin: {parsed_event['origin']}")
        lines.append(f"  Time: {parsed_event['timestamp']['readable']}")
        lines.append(f"  From Log: {parsed_event['from_log']}")
        
        if parsed_event['event_metadata']:
            lines.append("")
            lines.append("  Metadata:")
            for key, value_info in parsed_event['event_metadata'].items():
                vtype = value_info['type']
                vparsed = value_info['parsed']
                if vtype in ("integer", "number"):
                    lines.append(f"    {key}: {vparsed} ({vtype})")
                elif vtype == "boolean":
                    lines.append(f"    {key}: {vparsed}")
                elif vtype == "json":
                    lines.append(f"    {key}: {json.dumps(vparsed, indent=2)}")
                else:
                    lines.append(f"    {key}: {value_info['raw']}")
        
        lines.append("=" * 60)
        return "\n".join(lines)
```

### Event Name Reference by Service

```python
class BackgroundServiceEventsReference:
    """Background service event name reference"""
    
    SYNC_EVENTS = {
        "SyncRegistered": "Background sync registered",
        "SyncFired": "Sync event triggered",
        "SyncCompleted": "Sync completed successfully",
        "SyncFailed": "Sync execution failed",
    }
    
    FETCH_EVENTS = {
        "FetchRegistered": "Background fetch registered",
        "FetchFired": "Fetch event triggered",
        "FetchProgress": "Download progress update",
        "FetchCompleted": "Download completed successfully",
        "FetchFailed": "Download failed",
        "FetchAborted": "Download aborted",
        "FetchPaused": "Download paused",
        "FetchResumed": "Download resumed",
    }
    
    PERIODIC_SYNC_EVENTS = {
        "PeriodicSyncRegistered": "Periodic sync registered",
        "PeriodicSyncFired": "Periodic sync triggered",
        "PeriodicSyncCompleted": "Periodic sync completed",
        "PeriodicSyncFailed": "Periodic sync failed",
    }
    
    PUSH_EVENTS = {
        "PushMessageQueued": "Push message queued",
        "PushMessageSent": "Push message sent",
        "PushMessageReceived": "Push message received",
        "PushNotificationShown": "Push notification shown",
        "PushNotificationClicked": "Push notification clicked",
        "PushNotificationDismissed": "Push notification dismissed",
    }
    
    @classmethod
    def get_event_description(cls, service_name, event_name):
        """Get event description"""
        mapping = {
            "backgroundSync": cls.SYNC_EVENTS,
            "backgroundFetch": cls.FETCH_EVENTS,
            "periodicBackgroundSync": cls.PERIODIC_SYNC_EVENTS,
            "pushMessaging": cls.PUSH_EVENTS,
        }
        service_events = mapping.get(service_name, {})
        return service_events.get(event_name, event_name)
```

---

## Recording and Replaying Background Events

### Event Recording System

```python
import json
import os
from datetime import datetime

class BackgroundEventRecorder:
    """Background service event recorder — record event sequences for replay analysis"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.recording = False
        self.recorded_events = []
        self.current_session_id = None
    
    async def start_recording(self, service_names=None):
        """Start recording background events"""
        if service_names is None:
            service_names = BackgroundServiceMonitor.SERVICE_NAMES
        
        for service in service_names:
            await cdp(self.ws, "BackgroundService.startObserving", {
                "service": service
            }, self.session_id)
        
        self.recording = True
        self.recorded_events = []
        self.current_session_id = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        print(f"[Record] Started recording background events (session: {self.current_session_id})")
        return self.current_session_id
    
    async def record(self, duration=60):
        """Record events for the specified duration"""
        if not self.recording:
            raise RuntimeError("Call start_recording() first")
        
        start = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start) < duration:
            try:
                msg = await asyncio.wait_for(self.ws.__anext__(), timeout=1)
                data = json.loads(msg)
                
                if data.get("method") == "BackgroundService.backgroundServiceEventReceived":
                    event = data["params"].get("backgroundServiceEvent", {})
                    
                    recorded = {
                        "capture_time": datetime.now().isoformat(),
                        "event": BackgroundServiceEventParser.parse(event)
                    }
                    
                    self.recorded_events.append(recorded)
                    service = event.get("serviceName", "?")
                    ename = event.get("eventName", "?")
                    print(f"[Record] {service}.{ename} #{len(self.recorded_events)}")
                    
            except asyncio.TimeoutError:
                continue
        
        print(f"[Record] Recording complete, {len(self.recorded_events)} events")
        return self.recorded_events
    
    def stop_recording(self):
        """Stop recording"""
        self.recording = False
        print(f"[Record] Stopped")
    
    def save_recording(self, filepath):
        """Save recording to file"""
        recording_data = {
            "session_id": self.current_session_id,
            "recorded_at": datetime.now().isoformat(),
            "total_events": len(self.recorded_events),
            "events": self.recorded_events,
        }
        
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(recording_data, f, indent=2)
        
        print(f"[Record] Saved to {filepath} ({len(self.recorded_events)} events)")
        return filepath
    
    @staticmethod
    def load_recording(filepath):
        """Load a recording file"""
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        print(f"[Replay] Loaded recording: {data['session_id']} ({data['total_events']} events)")
        return data
```

### Event Replay Analyzer

```python
class BackgroundEventReplayAnalyzer:
    """Background event replay analyzer — analyze recorded event sequences"""
    
    def __init__(self, recording_data):
        self.events = recording_data.get("events", [])
        self.session_id = recording_data.get("session_id", "")
    
    def analyze_sequence(self):
        """Analyze event sequence"""
        by_service = {}
        by_event = {}
        timeline = []
        
        for recorded in self.events:
            event = recorded["event"]
            service = event["service_name"]
            event_name = event["event_name"]
            
            if service not in by_service:
                by_service[service] = 0
            by_service[service] += 1
            
            key = f"{service}.{event_name}"
            if key not in by_event:
                by_event[key] = 0
            by_event[key] += 1
            
            timeline.append({
                "time": recorded["capture_time"],
                "service": service,
                "event": event_name,
                "instance": event["instance_id"][:12],
            })
        
        return {
            "session_id": self.session_id,
            "total_events": len(self.events),
            "by_service": by_service,
            "by_event": by_event,
            "timeline": timeline
        }
    
    def find_instance_lifecycle(self, instance_id):
        """Find the full lifecycle of a specific instance"""
        lifecycle = []
        
        for recorded in self.events:
            event = recorded["event"]
            if event["instance_id"] == instance_id or event["instance_id"].startswith(instance_id):
                lifecycle.append({
                    "time": recorded["capture_time"],
                    "event": event["event_name"],
                    "metadata": event["event_metadata"]
                })
        
        return lifecycle
    
    def generate_report(self):
        """Generate analysis report"""
        analysis = self.analyze_sequence()
        
        report_lines = []
        report_lines.append("=" * 60)
        report_lines.append("Background Event Replay Analysis Report")
        report_lines.append("=" * 60)
        report_lines.append(f"Session: {analysis['session_id']}")
        report_lines.append(f"Total Events: {analysis['total_events']}")
        report_lines.append("")
        
        report_lines.append("By Service:")
        for service, count in sorted(analysis["by_service"].items(), key=lambda x: -x[1]):
            report_lines.append(f"  {service}: {count}")
        
        report_lines.append("")
        report_lines.append("By Event:")
        for key, count in sorted(analysis["by_event"].items(), key=lambda x: -x[1]):
            report_lines.append(f"  {key}: {count}")
        
        report_lines.append("")
        report_lines.append("Event Timeline:")
        for entry in analysis["timeline"]:
            report_lines.append(f"  [{entry['time']}] {entry['service']}.{entry['event']} ({entry['instance']})")
        
        report_lines.append("=" * 60)
        return "\n".join(report_lines)
```

---

## Practical: Service Worker Offline Debugging

### Complete Debugging Workflow

```python
class ServiceWorkerOfflineDebugger:
    """Service Worker offline debugger — combining Network and BackgroundService domains"""
    
    def __init__(self, ws):
        self.ws = ws
        self.session_id = None
        self.bg_monitor = None
    
    async def initialize(self):
        """Initialize the debugging environment"""
        targets = await cdp(self.ws, "Target.getTargets")
        
        sw_target = None
        page_target = None
        
        for target in targets.get("targetInfos", []):
            if target["type"] == "service_worker":
                sw_target = target
            elif target["type"] == "page" and not page_target:
                page_target = target
        
        if page_target:
            result = await cdp(self.ws, "Target.attachToTarget", {
                "targetId": page_target["targetId"],
                "flatten": True
            })
            self.session_id = result["sessionId"]
        
        if sw_target:
            sw_result = await cdp(self.ws, "Target.attachToTarget", {
                "targetId": sw_target["targetId"],
                "flatten": True
            })
            self.sw_session_id = sw_result["sessionId"]
            print(f"[Debug] Attached to Service Worker: {sw_target.get('url', '')[:60]}")
        
        await cdp(self.ws, "Page.enable", {}, self.session_id)
        await cdp(self.ws, "Runtime.enable", {}, self.session_id)
        await cdp(self.ws, "Network.enable", {}, self.session_id)
        
        self.bg_monitor = BackgroundServiceMonitor(self.ws, self.session_id)
        await self.bg_monitor.enable_all()
        
        return self.session_id
    
    async def simulate_offline_scenario(self):
        """Simulate an offline scenario and observe background behavior"""
        print("\n" + "=" * 60)
        print("Simulating Offline Scenario")
        print("=" * 60)
        
        print("\n[Step 1] Registering background sync...")
        register_sync = """
        (async () => {
            if ('serviceWorker' in navigator) {
                const reg = await navigator.serviceWorker.ready;
                await reg.sync.register('offline-data-sync');
                return 'Sync registered: offline-data-sync';
            }
            return 'Service Worker not available';
        })();
        """
        
        result = await cdp(self.ws, "Runtime.evaluate", {
            "expression": register_sync,
            "awaitPromise": True,
            "returnByValue": True
        }, self.session_id)
        print(f"  {result.get('result', {}).get('value', '')}")
        await asyncio.sleep(1)
        
        print("\n[Step 2] Simulating offline...")
        await cdp(self.ws, "Network.emulateNetworkConditions", {
            "offline": True,
            "latency": 0,
            "downloadThroughput": 0,
            "uploadThroughput": 0
        }, self.session_id)
        print("  Network status: Offline")
        await asyncio.sleep(1)
        
        print("\n[Step 3] Making request while offline...")
        make_request = """
        fetch('/api/data.json')
            .then(r => r.json())
            .then(d => console.log('[Online] Data received:', d))
            .catch(e => console.log('[Offline] Fetch failed (expected):', e.message));
        """
        
        await cdp(self.ws, "Runtime.evaluate", {
            "expression": make_request,
            "returnByValue": True
        }, self.session_id)
        await asyncio.sleep(2)
        
        print("\n[Step 4] Restoring online...")
        await cdp(self.ws, "Network.emulateNetworkConditions", {
            "offline": False,
            "latency": 0,
            "downloadThroughput": -1,
            "uploadThroughput": -1
        }, self.session_id)
        print("  Network status: Online")
        
        print("\nWaiting for background sync events...")
        await asyncio.sleep(5)
        
        print("\n[Step 5] Collecting background events...")
        events = self.bg_monitor.get_events("backgroundSync")
        print(f"  Captured {len(events)} Background Sync events:")
        for event in events:
            ename = event.get("eventName", "?")
            meta = {
                e.get("key", ""): e.get("value", "")
                for e in event.get("eventMetadata", [])
            }
            print(f"    - {ename}: {meta}")
        
        return events
    
    async def cleanup(self):
        """Clean up the debugging environment"""
        if self.bg_monitor:
            await self.bg_monitor.disable_all()
        
        await cdp(self.ws, "Network.emulateNetworkConditions", {
            "offline": False,
            "latency": 0,
            "downloadThroughput": -1,
            "uploadThroughput": -1
        }, self.session_id)
        
        print("[Debug] Environment cleaned up")
```

### Complete Usage Example

```python
async def background_service_debugging_workflow():
    """Complete BackgroundService debugging workflow"""
    async with websockets.connect(CDP_URL) as ws:
        debugger = ServiceWorkerOfflineDebugger(ws)
        await debugger.initialize()
        
        events = await debugger.simulate_offline_scenario()
        
        recorder = BackgroundEventRecorder(ws, debugger.session_id)
        await recorder.start_recording()
        
        print("\nRecording background events (10 seconds)...")
        recorded = await recorder.record(10)
        
        recording_file = f"bg_recording_{recorder.current_session_id}.json"
        recorder.save_recording(recording_file)
        
        recording_data = BackgroundEventRecorder.load_recording(recording_file)
        analyzer = BackgroundEventReplayAnalyzer(recording_data)
        report = analyzer.generate_report()
        print("\n" + report)
        
        await debugger.cleanup()
        
        return {
            "events_captured": len(events),
            "recorded_events": len(recorded),
            "recording_file": recording_file
        }


# asyncio.run(background_service_debugging_workflow())
```

---

## Best Practices and Considerations

### Background Service Debugging Tips

| Scenario | Recommendation | Explanation |
|----------|----------------|-------------|
| First enablement | Enable services one by one | Enabling all at once may flood with events |
| Long monitoring | Use event buffering and paged storage | Prevent memory overflow |
| Offline testing | Combine with Network.emulateNetworkConditions | Simulate real network transitions |
| Event analysis | Group by instanceId | Track full lifecycle of a single task |
| Production debugging | Use record/replay mode | Record first, analyze offline later |

### Common Issues

```python
class BackgroundServiceTroubleshooting:
    """Background service debugging common issues"""
    
    @staticmethod
    def sw_not_registered():
        """Service Worker not registered"""
        # Check if Service Worker is registered
        # Use Runtime.evaluate to check navigator.serviceWorker.controller
        pass
    
    @staticmethod
    def sync_manager_unavailable():
        """SyncManager unavailable"""
        # Check:
        # 1. Page loaded over HTTPS
        # 2. Service Worker installed correctly
        # 3. Browser supports SyncManager
        pass
    
    @staticmethod
    def events_not_received():
        """Events not received"""
        # Check:
        # 1. BackgroundService.startObserving called correctly
        # 2. Session ID is correct
        # 3. Background service may require user gesture
        pass
    
    @staticmethod
    def cross_origin_limitations():
        """Cross-origin limitations"""
        # BackgroundService events only come from the page's origin
        # Cross-origin iframe background events will not be captured
        pass
```

### Key Metadata Field Reference

```python
# Background Sync event metadata fields
SYNC_METADATA_FIELDS = {
    "tag": "Sync tag identifier",
    "outcome": "Sync outcome (Success/Failure)",
    "failureReason": "Reason for failure",
    "lastAttemptTime": "Last attempt timestamp",
    "numberOfAttempts": "Number of attempts made",
    "maxAttempts": "Maximum number of attempts",
}

# Background Fetch event metadata fields
FETCH_METADATA_FIELDS = {
    "tag": "Download tag identifier",
    "uniqueId": "Unique identifier",
    "title": "Download title",
    "url": "Download URL",
    "totalDownloadSize": "Total download size in bytes",
    "downloadedSize": "Downloaded size in bytes",
    "percentComplete": "Completion percentage",
    "failureReason": "Reason for failure",
    "result": "Final result",
}
```

---

> **Extended Thinking**: The BackgroundService domain fills the last gap in debugging browser background behaviors. Combined with the Network, Runtime, and Storage domains you've learned previously, you now have programmatic control over the complete browser lifecycle — from frontend JS execution to network requests, storage management, and background services. This comprehensive visibility is the foundation for building advanced browser automation tools and PWA debuggers.

*Previous: CDP Error Tracking Guide: Capturing Page Exceptions with Python*