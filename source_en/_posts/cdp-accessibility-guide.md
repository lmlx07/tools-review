---
lang: en
title: "CDP Accessibility Guide: Automated Accessibility Testing with Python"
date: "2026-06-05 16:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Accessibility
  - a11y
  - WCAG
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to automated accessibility testing using Chrome DevTools Protocol (CDP). Learn Accessibility.enable, getFullAXTree/getPartialAXTree, AXNode property analysis, automated audit rules for missing labels, focus order verification, and generating a11y reports.
---

> **Summary in one sentence**: CDP's `Accessibility` domain exposes the browser's native accessibility tree, allowing you to programmatically audit pages for a11y issues — missing labels, incorrect ARIA attributes, broken focus order, and more — replacing expensive manual reviews with automated Python scripts.

---

## Table of Contents

1. [Accessibility Testing and CDP](#accessibility-testing-and-cdp)
2. [Basics: Accessibility.enable and the Accessibility Tree](#basics-accessibilityenable-and-the-accessibility-tree)
3. [getFullAXTree: The Complete Accessibility Tree](#getfullaxtree-the-complete-accessibility-tree)
4. [getPartialAXTree: Partial Accessibility Tree](#getpartialaxtree-partial-accessibility-tree)
5. [Automated Accessibility Auditing](#automated-accessibility-auditing)
6. [Focus Order Verification](#focus-order-verification)
7. [Practical: A11y Report Generator](#practical-a11y-report-generator)
8. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Accessibility Testing and CDP

### Why Use CDP for Accessibility Testing

Web accessibility (a11y) testing traditionally relies on tools like axe-core, Lighthouse, or manual testing. CDP's `Accessibility` domain exposes the browser's internal accessibility tree directly:

| Method | Advantage | Limitation |
|--------|-----------|------------|
| Manual testing | Thorough | Expensive, requires expertise |
| axe-core | Comprehensive rules | Cannot customize deep analysis |
| Lighthouse a11y | One-click report | Not real-time or programmable |
| CDP Accessibility domain | Native a11y tree, programmable, customizable | Requires custom audit rules |

### Key Accessibility Domain Methods

- `Accessibility.enable` — Enable a11y events (triggers `AXTreeChange` notifications)
- `Accessibility.disable` — Disable
- `Accessibility.getFullAXTree` — Get the complete accessibility tree
- `Accessibility.getPartialAXTree` — Get a11y info for specific DOM nodes
- `Accessibility.queryAXTree` — Query a11y nodes by criteria
- `Accessibility.onLoadComplete` — Tree load complete event
- `Accessibility.onNodesLost` — Nodes lost event
- `Accessibility.onAXTreeChange` — Tree change event

### AXNode Properties Reference

| Property | Description |
|----------|-------------|
| `role` | Role (button, link, heading, text, etc.) |
| `name` | Accessible name (from aria-label, content text, etc.) |
| `description` | Extended description |
| `value` | Current value (e.g., input content) |
| `disabled` | Whether the element is disabled |
| `focused` | Whether the element is focused |
| `hidden` | Whether the element is hidden |
| `invalid` | Whether the input is invalid (aria-invalid) |
| `keyshortcuts` | Keyboard shortcut bindings |
| `checked` | Checkbox/radio checked state |
| `pressed` | Button pressed state |
| `expanded` | Expanded/collapsed state |
| `level` | Heading level (h1-h6) |
| `posInSet` | Position within a set |
| `setSize` | Size of the containing set |
| `actions` | Supported actions (focus, click, etc.) |

---

## Basics: Accessibility.enable and the Accessibility Tree

### Enabling Accessibility and Getting Basic Structure

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


async def enable_accessibility(ws, session_id):
    """Enable accessibility monitoring"""
    result = await cdp(ws, "Accessibility.enable", {}, session_id)
    print("Accessibility enabled")
    return result


def find_ax_property(node, prop_name):
    """Find a property in an AXNode's properties list"""
    properties = node.get("properties", [])
    for prop in properties:
        if prop.get("name") == prop_name:
            return prop
    return None


async def listen_axtree_events(ws, session_id, duration=30):
    """Listen for accessibility tree change events"""
    await enable_accessibility(ws, session_id)
    print(f"Listening for AX tree events ({duration}s)...")
    
    events = []
    start = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start < duration:
        try:
            resp = await asyncio.wait_for(ws.recv(), timeout=1.0)
            data = json.loads(resp)
            method = data.get("method", "")
            
            if method == "Accessibility.onAXTreeChange":
                nodes = data["params"].get("nodes", [])
                events.append({"type": "tree_change", "count": len(nodes)})
                print(f"[AX Tree Change] {len(nodes)} nodes affected")
                for node in nodes[:3]:
                    role_data = find_ax_property(node, "role")
                    name_data = find_ax_property(node, "name")
                    role = role_data.get("value", "unknown") if role_data else "unknown"
                    name = name_data.get("value", "") if name_data else ""
                    print(f"  role={role}, name={name[:50]}")
            
            elif method == "Accessibility.onLoadComplete":
                print("[AX Tree Load Complete]")
                events.append({"type": "load_complete"})
            
            elif method == "Accessibility.onNodesLost":
                ids = data["params"].get("nodeIds", [])
                print(f"[Nodes Lost] {len(ids)} nodes")
                events.append({"type": "nodes_lost", "count": len(ids)})
        
        except asyncio.TimeoutError:
            pass
    
    print(f"Total a11y events received: {len(events)}")
    return events
```

---

## getFullAXTree: The Complete Accessibility Tree

### Fetching the Full Tree

`getFullAXTree` returns the complete accessibility tree — ideal for comprehensive audits:

```python
async def get_full_axtree(ws, session_id):
    """Get the complete accessibility tree for the current page"""
    result = await cdp(ws, "Accessibility.getFullAXTree", {
        "max_depth": 0  # 0 means full depth
    }, session_id)
    
    nodes = result.get("nodes", [])
    print(f"Total AX tree nodes: {len(nodes)}")
    return nodes


def flatten_axtree(nodes):
    """Flatten the AX tree into an easy-to-analyze format"""
    flat = []
    for node in nodes:
        item = {"nodeId": node.get("nodeId"), "backendNodeId": node.get("backendNodeId")}
        
        for prop in node.get("properties", []):
            name = prop.get("name", "")
            value = prop.get("value", {})
            
            if isinstance(value, dict):
                if "value" in value:
                    item[name] = value["value"]
                elif "type" in value:
                    item[name] = value["type"]
            else:
                item[name] = str(value)
        
        child_ids = node.get("childIds", [])
        item["childCount"] = len(child_ids)
        item["childIds"] = child_ids
        
        flat.append(item)
    
    return flat


async def analyze_axtree_structure(ws, session_id):
    """Analyze the composition of the accessibility tree"""
    nodes = await get_full_axtree(ws, session_id)
    flat_nodes = flatten_axtree(nodes)
    
    print("\n===== Accessibility Tree Structure Analysis =====")
    print(f"Total nodes: {len(flat_nodes)}")
    
    role_counts = {}
    for node in flat_nodes:
        role = node.get("role", "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    
    print("\nRole distribution:")
    for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
        print(f"  {role}: {count}")
    
    headings = [n for n in flat_nodes if n.get("role") == "heading"]
    if headings:
        print(f"\nHeadings: {len(headings)}")
        levels = {}
        for h in headings:
            lvl = h.get("level", h.get("hierarchicalLevel", "?"))
            levels[lvl] = levels.get(lvl, 0) + 1
        for lvl, count in sorted(levels.items()):
            print(f"  h{lvl}: {count}")
    
    interactive_roles = {"button", "link", "checkbox", "radio",
                         "combobox", "menuitem", "tab", "textbox"}
    interactive = [n for n in flat_nodes if n.get("role") in interactive_roles]
    print(f"\nInteractive elements: {len(interactive)}")
    
    return {
        "total_nodes": len(flat_nodes),
        "role_counts": role_counts,
        "interactive_count": len(interactive),
        "headings": headings
    }
```

### Fetching Nodes by Role

```python
async def get_nodes_by_role(ws, session_id, target_role):
    """Get all AX tree nodes with a specific role"""
    nodes = await get_full_axtree(ws, session_id)
    flat = flatten_axtree(nodes)
    
    matched = [n for n in flat if n.get("role") == target_role]
    
    print(f"Nodes with role '{target_role}': {len(matched)}")
    for node in matched:
        name = node.get("name", "(no name)")
        desc = node.get("description", "")
        print(f"  - {name}" + (f" ({desc})" if desc else ""))
    
    return matched


async def list_all_buttons(ws, session_id):
    """List all buttons and their accessible names"""
    buttons = await get_nodes_by_role(ws, session_id, "button")
    
    unnamed = [b for b in buttons if not b.get("name")]
    if unnamed:
        print(f"\n⚠️ {len(unnamed)} buttons missing accessible names:")
        for btn in unnamed[:5]:
            print(f"   nodeId: {btn.get('nodeId')}")
    
    return buttons


async def list_all_images(ws, session_id):
    """List all images and their alt text"""
    images = await get_nodes_by_role(ws, session_id, "img")
    
    missing_alt = [img for img in images if not img.get("name")]
    print(f"Total images: {len(images)}")
    print(f"Missing alt text: {len(missing_alt)}")
    
    return {"total": len(images), "missing_alt": len(missing_alt)}
```

---

## getPartialAXTree: Partial Accessibility Tree

Use `getPartialAXTree` when you only need a11y info for specific DOM elements:

```python
async def get_partial_axtree(ws, session_id, node_id=None, backend_node_id=None):
    """Get accessibility info for specific DOM node(s)"""
    params = {"fetchRelatives": True}
    if node_id:
        params["nodeId"] = node_id
    if backend_node_id:
        params["backendNodeId"] = backend_node_id
    
    result = await cdp(ws, "Accessibility.getPartialAXTree", params, session_id)
    nodes = result.get("nodes", [])
    
    print(f"Partial AX tree nodes: {len(nodes)}")
    
    for node in nodes:
        role_data = find_ax_property(node, "role")
        name_data = find_ax_property(node, "name")
        desc_data = find_ax_property(node, "description")
        
        role = role_data.get("value", "?") if role_data else "?"
        name = name_data.get("value", "") if name_data else ""
        desc = desc_data.get("value", "") if desc_data else ""
        
        print(f"  role: {role}")
        print(f"  name: {name}")
        if desc:
            print(f"  description: {desc}")
        
        for prop in node.get("properties", []):
            pname = prop.get("name", "")
            if pname not in ("role", "name", "description"):
                pval = prop.get("value", {})
                actual = pval.get("value", pval.get("type", ""))
                print(f"  {pname}: {actual}")
        print()
    
    return nodes


async def inspect_element_a11y(ws, session_id, css_selector):
    """Inspect the full a11y information for a specific CSS selector"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{css_selector}');
                if (!el) return null;
                return JSON.stringify({{
                    tag: el.tagName,
                    id: el.id,
                    className: el.className,
                    ariaLabel: el.getAttribute('aria-label'),
                    ariaLabelledby: el.getAttribute('aria-labelledby'),
                    role: el.getAttribute('role'),
                    tabIndex: el.tabIndex,
                    textContent: (el.textContent || '').trim().slice(0, 100)
                }});
            }})()
        """,
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    dom_info = pyjson.loads(result["result"]["value"])
    
    if not dom_info:
        print(f"Element not found: {css_selector}")
        return None
    
    print(f"===== DOM Info: {css_selector} =====")
    for key, val in dom_info.items():
        if val:
            print(f"  {key}: {val}")
    
    query_result = await cdp(ws, "Accessibility.queryAXTree", {
        "accessibleName": dom_info.get("ariaLabel") or dom_info.get("textContent", ""),
        "role": dom_info.get("role") or "",
    }, session_id)
    
    if query_result.get("nodes"):
        print(f"\n===== AX Tree Info =====")
        for node in query_result["nodes"]:
            for prop in node.get("properties", []):
                pname = prop.get("name", "")
                pval = prop.get("value", {})
                actual = pval.get("value", pval.get("type", ""))
                print(f"  {pname}: {actual}")
    
    return {"dom": dom_info, "a11y": query_result}
```

### queryAXTree: Query by Criteria

```python
async def query_axtree(ws, session_id, **filters):
    """Query accessibility nodes by criteria"""
    params = {"fetchRelatives": True}
    params.update(filters)
    
    result = await cdp(ws, "Accessibility.queryAXTree", params, session_id)
    nodes = result.get("nodes", [])
    
    print(f"Query results: {len(nodes)} nodes")
    for node in nodes:
        name_data = find_ax_property(node, "name")
        role_data = find_ax_property(node, "role")
        name = name_data.get("value", "") if name_data else ""
        role = role_data.get("value", "") if role_data else ""
        print(f"  role={role}, name={name}")
    
    return nodes


async def find_elements_without_names(ws, session_id):
    """Find all interactive elements missing accessible names"""
    full_tree = await get_full_axtree(ws, session_id)
    flat = flatten_axtree(full_tree)
    
    interactive_roles = {"button", "link", "checkbox", "radio",
                         "combobox", "menuitem", "tab"}
    
    issues = []
    for node in flat:
        role = node.get("role", "")
        if role in interactive_roles:
            name = node.get("name", "")
            if not name:
                issues.append({
                    "nodeId": node.get("nodeId"),
                    "backendNodeId": node.get("backendNodeId"),
                    "role": role,
                    "issue": "Missing accessible name"
                })
    
    print(f"\n===== A11y Issues: Interactive Elements Missing Names =====")
    print(f"Found {len(issues)} issues")
    for issue in issues:
        print(f"  [{issue['role']}] nodeId={issue['nodeId']} - {issue['issue']}")
    
    return issues
```

---

## Automated Accessibility Auditing

### A Complete Audit Rule Engine

```python
class AccessibilityAuditor:
    """Automated accessibility auditor"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.issues = []
    
    async def run_full_audit(self):
        """Run a complete accessibility audit"""
        print("Starting full accessibility audit...\n")
        
        nodes = await get_full_axtree(self.ws, self.session_id)
        flat = flatten_axtree(nodes)
        
        self.check_button_names(flat)
        self.check_image_alts(flat)
        self.check_heading_structure(flat)
        self.check_form_labels(flat)
        self.check_aria_roles(flat)
        self.check_focusable_elements(flat)
        self.check_landmarks(flat)
        
        self.generate_report()
        
        return self.issues
    
    def check_button_names(self, flat):
        buttons = [n for n in flat if n.get("role") == "button"]
        missing_name = [b for b in buttons if not b.get("name")]
        
        for btn in missing_name:
            self.issues.append({
                "type": "error",
                "rule": "button-name",
                "severity": "high",
                "message": "Button missing accessible name",
                "nodeId": btn.get("nodeId"),
                "wcag": "4.1.2"
            })
        
        print(f"[Button names] {len(missing_name)}/{len(buttons)} have issues")
    
    def check_image_alts(self, flat):
        images = [n for n in flat if n.get("role") == "img"]
        missing_alt = [img for img in images if not img.get("name")]
        
        for img in missing_alt:
            self.issues.append({
                "type": "error",
                "rule": "image-alt",
                "severity": "high",
                "message": "Image missing alternative text",
                "nodeId": img.get("nodeId"),
                "wcag": "1.1.1"
            })
        
        print(f"[Image alt text] {len(missing_alt)}/{len(images)} have issues")
    
    def check_heading_structure(self, flat):
        headings = [n for n in flat if n.get("role") == "heading"]
        
        levels = []
        for h in headings:
            lvl = h.get("level", h.get("hierarchicalLevel"))
            if lvl:
                try:
                    levels.append(int(str(lvl)))
                except (ValueError, TypeError):
                    pass
        
        for i in range(1, len(levels)):
            if levels[i] > levels[i-1] + 1:
                self.issues.append({
                    "type": "warning",
                    "rule": "heading-order",
                    "severity": "medium",
                    "message": f"Heading level skip: h{levels[i-1]} -> h{levels[i]}",
                    "wcag": "2.4.6"
                })
        
        if not headings:
            self.issues.append({
                "type": "warning",
                "rule": "page-has-heading",
                "severity": "medium",
                "message": "Page has no headings",
                "wcag": "2.4.6"
            })
        
        print(f"[Heading structure] {len(headings)} headings found")
    
    def check_form_labels(self, flat):
        form_roles = {"textbox", "combobox", "listbox", "slider",
                       "spinbutton", "checkbox", "radio"}
        form_elements = [n for n in flat if n.get("role") in form_roles]
        missing_label = [f for f in form_elements if not f.get("name")]
        
        for fe in missing_label:
            self.issues.append({
                "type": "error",
                "rule": "form-label",
                "severity": "high",
                "message": f"{fe.get('role', 'Form element')} missing associated label",
                "nodeId": fe.get("nodeId"),
                "wcag": "1.3.1"
            })
        
        print(f"[Form labels] {len(missing_label)}/{len(form_elements)} have issues")
    
    def check_aria_roles(self, flat):
        known_roles = {"button", "link", "heading", "img", "text", "textbox",
                      "checkbox", "radio", "list", "listitem", "navigation",
                      "banner", "main", "complementary", "contentinfo",
                      "form", "search", "tab", "tablist", "tabpanel",
                      "menuitem", "menu", "dialog", "alertdialog"}
        
        for node in flat:
            role = node.get("role", "")
            if role and role not in known_roles and role != "GenericContainer":
                self.issues.append({
                    "type": "warning",
                    "rule": "valid-aria-role",
                    "severity": "low",
                    "message": f"Potentially invalid ARIA role: {role}",
                    "nodeId": node.get("nodeId"),
                    "wcag": "4.1.2"
                })
        
        print(f"[ARIA roles] Role validation complete")
    
    def check_focusable_elements(self, flat):
        for node in flat:
            role = node.get("role", "")
            if role in ("button", "link", "checkbox", "radio"):
                disabled = node.get("disabled", False)
                if not disabled and role != "link":
                    actions = node.get("actions", "")
                    has_focus = "focus" in str(actions)
                    if not has_focus:
                        self.issues.append({
                            "type": "warning",
                            "rule": "focusable",
                            "severity": "medium",
                            "message": f"{role} may not be keyboard-focusable",
                            "nodeId": node.get("nodeId"),
                            "wcag": "2.1.1"
                        })
        
        print(f"[Focus accessibility] Check complete")
    
    def check_landmarks(self, flat):
        landmark_roles = {"navigation", "banner", "main",
                          "complementary", "contentinfo", "search", "form"}
        landmarks = [n for n in flat if n.get("role") in landmark_roles]
        
        landmark_counts = {}
        for lm in landmarks:
            role = lm.get("role", "")
            landmark_counts[role] = landmark_counts.get(role, 0) + 1
        
        print(f"[Landmarks] {len(landmarks)} landmarks found:")
        for role, count in sorted(landmark_counts.items()):
            print(f"  {role}: {count}")
        
        required = {"main"}
        existing = set(landmark_counts.keys())
        missing = required - existing
        if missing:
            self.issues.append({
                "type": "warning",
                "rule": "landmark",
                "severity": "medium",
                "message": f"Page missing required landmark(s): {', '.join(missing)}",
                "wcag": "1.3.1"
            })
    
    def generate_report(self):
        print("\n" + "=" * 60)
        print("            Accessibility Audit Report")
        print("=" * 60)
        
        severity_count = {"high": 0, "medium": 0, "low": 0}
        rule_count = {}
        
        for issue in self.issues:
            severity_count[issue["severity"]] = \
                severity_count.get(issue["severity"], 0) + 1
            rule_count[issue["rule"]] = \
                rule_count.get(issue["rule"], 0) + 1
        
        print(f"\nTotal issues: {len(self.issues)}")
        print(f"  High priority: {severity_count.get('high', 0)}")
        print(f"  Medium priority: {severity_count.get('medium', 0)}")
        print(f"  Low priority: {severity_count.get('low', 0)}")
        
        print(f"\nBy rule:")
        for rule, count in sorted(rule_count.items(), key=lambda x: -x[1]):
            print(f"  {rule}: {count}")
        
        wcag_refs = set()
        for issue in self.issues:
            if "wcag" in issue:
                wcag_refs.add(issue["wcag"])
        
        print(f"\nWCAG standards referenced:")
        for ref in sorted(wcag_refs):
            print(f"  WCAG {ref}")
        
        print("=" * 60)
        return self.issues
```

---

## Focus Order Verification

### Ensuring Correct Tab Navigation Order

```python
async def verify_tab_order(ws, session_id):
    """Verify the page's Tab navigation order"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (() => {
                const focusable = document.querySelectorAll(
                    'a[href], button:not([disabled]), input:not([disabled]), ' +
                    'select:not([disabled]), textarea:not([disabled]), ' +
                    '[tabindex]:not([tabindex="-1"])'
                );
                return JSON.stringify(Array.from(focusable).map((el, i) => ({
                    index: i,
                    tag: el.tagName,
                    id: el.id,
                    tabIndex: el.getAttribute('tabindex') || '0',
                    text: (el.textContent || '').trim().slice(0, 50),
                    className: el.className
                })));
            })()
        """,
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    focusable = pyjson.loads(result["result"]["value"])
    
    print(f"\n===== Tab Focus Order =====")
    print(f"Total focusable elements: {len(focusable)}")
    
    issues = []
    for el in focusable:
        tab_idx = el.get("tabIndex", "0")
        text = el.get("text", "").strip() or f"<{el['tag']}>"
        print(f"  #{el['index']}: {text} (tabIndex={tab_idx})")
        
        if tab_idx and tab_idx != "0":
            try:
                if int(tab_idx) > 0:
                    issues.append({
                        "type": "warning",
                        "rule": "tab-order",
                        "severity": "medium",
                        "message": f"Positive tabIndex={tab_idx} may cause confusing order",
                        "element": text,
                        "wcag": "2.4.3"
                    })
            except ValueError:
                pass
    
    if issues:
        print(f"\n⚠️ Found {len(issues)} focus order issues:")
        for issue in issues:
            print(f"  - {issue['message']}")
    
    return {"focusable_elements": focusable, "issues": issues}


async def check_focus_trap(ws, session_id):
    """Check for focus traps (elements you can't Tab away from)"""
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (() => {
                const issues = [];
                const modals = document.querySelectorAll(
                    '[role="dialog"], [role="alertdialog"], .modal, [aria-modal="true"]'
                );
                
                modals.forEach((modal, i) => {
                    const focusable = modal.querySelectorAll(
                        'a[href], button, input, select, textarea, [tabindex]'
                    );
                    issues.push({
                        index: i,
                        tag: modal.tagName,
                        id: modal.id,
                        focusableCount: focusable.length,
                        ariaModal: modal.getAttribute('aria-modal')
                    });
                });
                
                return JSON.stringify(issues);
            })()
        """,
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    modals = pyjson.loads(result["result"]["value"])
    
    print(f"\n===== Focus Trap Check =====")
    print(f"Found {len(modals)} dialogs/modals")
    for m in modals:
        print(f"  {m['tag']}#{m['id']}: "
              f"focusable elements={m['focusableCount']}, "
              f"aria-modal={m.get('ariaModal', 'N/A')}")
    
    return modals
```

---

## Practical: A11y Report Generator

### Comprehensive Testing Tool

```python
class A11yTestSuite:
    """Accessibility test suite"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.auditor = AccessibilityAuditor(ws, session_id)
        self.results = {}
    
    async def test_page(self, url):
        """Test a single page's accessibility"""
        print(f"\n{'='*60}")
        print(f"Testing: {url}")
        print(f"{'='*60}")
        
        await cdp(self.ws, "Page.navigate", {"url": url}, self.session_id)
        await cdp(self.ws, "Page.loadEventFired", {}, self.session_id)
        await asyncio.sleep(2)
        
        issues = await self.auditor.run_full_audit()
        tab_info = await verify_tab_order(self.ws, self.session_id)
        structure = await analyze_axtree_structure(self.ws, self.session_id)
        
        self.results[url] = {
            "issues": issues,
            "tab_order": tab_info,
            "structure": structure,
            "passed": len([i for i in issues if i["severity"] == "high"]) == 0,
            "issue_count": len(issues),
            "high_count": len([i for i in issues if i["severity"] == "high"])
        }
        
        return self.results[url]
    
    async def test_multiple(self, urls):
        """Test multiple pages"""
        for url in urls:
            await self.test_page(url)
        
        self.summary_report()
        return self.results
    
    def summary_report(self):
        print("\n" + "=" * 70)
        print("             Multi-Page A11y Test Summary")
        print("=" * 70)
        print(f"{'Page':<40} {'Result':<10} {'Issues':<10} {'High':<10}")
        print("-" * 70)
        
        passed_all = True
        for url, result in self.results.items():
            status = "✅ PASS" if result["passed"] else "❌ FAIL"
            passed_all = passed_all and result["passed"]
            short_url = url[:38] + ".." if len(url) > 40 else url
            print(f"{short_url:<40} {status:<10} "
                  f"{result['issue_count']:<10} {result['high_count']:<10}")
        
        print("-" * 70)
        total_pages = len(self.results)
        total_issues = sum(r["issue_count"] for r in self.results.values())
        total_high = sum(r["high_count"] for r in self.results.values())
        print(f"Tested {total_pages} page(s), found {total_issues} issues "
              f"({total_high} high priority)")
        print("=" * 70)
    
    def export_json(self, file_path):
        import json as pyjson
        with open(file_path, "w", encoding="utf-8") as f:
            pyjson.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"Report exported: {file_path}")
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Accessibility.enable Is Optional for Tree Queries

```python
# Accessibility.enable is mainly for receiving AXTreeChange events
# Getting the tree itself does not require prior enable()
await cdp(ws, "Accessibility.enable", {}, session_id)

# But getFullAXTree works without enable()
nodes = await cdp(ws, "Accessibility.getFullAXTree", {}, session_id)
```

### Pitfall 2: max_depth Parameter

```python
# max_depth = 0 returns the full tree (all levels)
result = await cdp(ws, "Accessibility.getFullAXTree", {"max_depth": 0}, session_id)

# Limiting depth speeds up response
result = await cdp(ws, "Accessibility.getFullAXTree", {"max_depth": 3}, session_id)
```

### Pitfall 3: Not All DOM Elements Are in the AX Tree

```python
# Purely decorative <div> elements may not appear in the AX tree
# This means getFullAXTree node count may be less than DOM node count
# This is normal — the browser filters out semantically meaningless elements
```

### Pitfall 4: Dynamic Content Needs Waiting

```python
# For SPAs or dynamically loaded content, the AX tree may not update immediately
await cdp(ws, "Runtime.evaluate", {
    "expression": "// trigger dynamic content loading",
    "sessionId": session_id
}, session_id)
await asyncio.sleep(1)  # Wait for AX tree update

# Now fetch the updated tree
nodes = await get_full_axtree(ws, session_id)
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Tree scope | Use getFullAXTree for full audits, getPartialAXTree for spot checks |
| Dynamic content | Wait for AX tree updates after content changes |
| Role validation | Check custom components use valid ARIA roles |
| Name computation | Understand how browsers compute accessible names |
| Focus order | tabIndex should be 0 or -1, avoid positive values |
| WCAG reference | Link each audit rule to the corresponding WCAG criterion |

---

## Complete Reference: CDP Accessibility Test Class

```python
import asyncio
import json


class CDPAccessibilityTester:
    """CDP Accessibility Testing Tool"""

    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0

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

    async def enable(self):
        """Enable accessibility monitoring"""
        return await self._cmd("Accessibility.enable")

    async def disable(self):
        """Disable accessibility monitoring"""
        return await self._cmd("Accessibility.disable")

    async def get_full_tree(self, max_depth=0):
        """Get the complete accessibility tree"""
        return await self._cmd("Accessibility.getFullAXTree", {
            "max_depth": max_depth
        })

    async def get_partial_tree(self, node_id=None, backend_node_id=None,
                                fetch_relatives=True):
        """Get a partial accessibility tree"""
        params = {"fetchRelatives": fetch_relatives}
        if node_id:
            params["nodeId"] = node_id
        if backend_node_id:
            params["backendNodeId"] = backend_node_id
        return await self._cmd("Accessibility.getPartialAXTree", params)

    async def query_tree(self, **filters):
        """Query accessibility nodes"""
        params = {"fetchRelatives": True, **filters}
        return await self._cmd("Accessibility.queryAXTree", params)

    def extract_node_info(self, node):
        """Extract key information from an AXNode"""
        info = {"nodeId": node.get("nodeId")}
        for prop in node.get("properties", []):
            name = prop.get("name", "")
            value = prop.get("value", {})
            if isinstance(value, dict):
                info[name] = value.get("value", value.get("type", ""))
            else:
                info[name] = str(value)
        return info

    def flatten_tree(self, nodes):
        """Flatten the accessibility tree"""
        return [self.extract_node_info(n) for n in nodes]

    async def audit(self):
        """Run a basic accessibility audit"""
        result = await self.get_full_tree()
        nodes = result.get("nodes", [])
        flat = self.flatten_tree(nodes)

        issues = []

        # 1. Check button labels
        for n in flat:
            if n.get("role") == "button" and not n.get("name"):
                issues.append({
                    "rule": "button-name",
                    "severity": "high",
                    "message": "Button without accessible name",
                    "nodeId": n.get("nodeId")
                })

        # 2. Check image alt text
        for n in flat:
            if n.get("role") == "img" and not n.get("name"):
                issues.append({
                    "rule": "image-alt",
                    "severity": "high",
                    "message": "Image without alt text",
                    "nodeId": n.get("nodeId")
                })

        # 3. Check form labels
        form_roles = {"textbox", "combobox", "checkbox", "radio"}
        for n in flat:
            if n.get("role") in form_roles and not n.get("name"):
                issues.append({
                    "rule": "form-label",
                    "severity": "high",
                    "message": f"Form element ({n.get('role')}) without label",
                    "nodeId": n.get("nodeId")
                })

        # 4. Check heading order
        headings = [(i, n) for i, n in enumerate(flat)
                     if n.get("role") == "heading"]
        for i in range(1, len(headings)):
            prev_level = headings[i-1][1].get("level", 0)
            curr_level = headings[i][1].get("level", 0)
            if curr_level and prev_level:
                try:
                    if int(curr_level) > int(prev_level) + 1:
                        issues.append({
                            "rule": "heading-order",
                            "severity": "medium",
                            "message": f"Heading level skip: "
                                      f"h{prev_level} -> h{curr_level}"
                        })
                except (ValueError, TypeError):
                    pass

        summary = {
            "total_nodes": len(nodes),
            "total_issues": len(issues),
            "high_priority": sum(1 for i in issues
                                 if i["severity"] == "high"),
            "medium_priority": sum(1 for i in issues
                                   if i["severity"] == "medium"),
            "issues": issues
        }

        return summary
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id, _ = await connect_page(ws)
    tester = CDPAccessibilityTester(ws, session_id)

    # Navigate
    await cdp(ws, "Page.navigate", {"url": "https://example.com"}, session_id)
    await cdp(ws, "Page.loadEventFired", {}, session_id)
    await asyncio.sleep(2)

    # Run audit
    summary = await tester.audit()
    print(f"Total nodes: {summary['total_nodes']}")
    print(f"Issues found: {summary['total_issues']} "
          f"(high: {summary['high_priority']}, "
          f"medium: {summary['medium_priority']})")

    for issue in summary["issues"]:
        print(f"  [{issue['severity'].upper()}] {issue['message']}")

    # Query specific elements
    buttons = await tester.query_tree(role="button")
    print(f"\nButton count: {len(buttons.get('nodes', []))}")

    # Export full tree
    tree = await tester.get_full_tree()
    flat = tester.flatten_tree(tree.get("nodes", []))
```

---

> **Summary**: CDP's `Accessibility` domain provides native access to the browser's accessibility tree — more accurate than DOM-based analysis because it reflects the browser's final computed semantic information. Combined with `getFullAXTree`, `queryAXTree`, and custom audit rules, you can build powerful automated accessibility testing pipelines that catch issues early in the development workflow.

---

*Previous: CDP Performance Observer Guide: Monitoring Core Web Vitals with Python*

*Next up: CDP Media & WebRTC Debugging: Controlling Audio/Video with Python*