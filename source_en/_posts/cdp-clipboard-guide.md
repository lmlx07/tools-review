---
lang: en
title: "CDP Clipboard Operations Guide: Reading & Writing Clipboard with Python"
date: "2026-06-05 19:30:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Clipboard
  - Automation
  - Permissions
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to browser clipboard operations using CDP. Learn to read/write clipboard text via Runtime.evaluate with navigator.clipboard, handle clipboard permissions, use Browser.grantPermissions for silent authorization, automate copy/paste workflows, and process clipboard files with DOM.setFileInputFiles.
---

> **Summary in one sentence**: By combining CDP's Runtime.evaluate and Browser.grantPermissions, you can fully automate clipboard read/write operations — no user-clicked permission dialogs needed, with full programmatic control over copy, paste, and file uploads.

---

## Table of Contents

1. [Why Use CDP for Clipboard Operations](#why-use-cdp-for-clipboard-operations)
2. [Basics: Connection & Permissions](#basics-connection--permissions)
3. [Reading Clipboard Text](#reading-clipboard-text)
4. [Writing Clipboard Text](#writing-clipboard-text)
5. [Permission Handling in Detail](#permission-handling-in-detail)
6. [Automated Copy & Paste](#automated-copy--paste)
7. [Handling Files with DOM.setFileInputFiles](#handling-files-with-domsetfileinputfiles)
8. [Practical: Cross-Page Data Transfer](#practical-cross-page-data-transfer)
9. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Clipboard Operations

Browser clipboard API (`navigator.clipboard`) faces strict security restrictions:

| Restriction | Regular JavaScript | CDP + Python |
|-------------|-------------------|--------------|
| HTTPS required | Must be on HTTPS | No limit (HTTP/localhost too) |
| User gesture required | Must be in user event | No user interaction needed |
| Permission prompt | `clipboard-read` needs approval | `Browser.grantPermissions` silently |
| Document focus | Page must be focused | CDP works in background |
| Cross-origin | Current domain only | Navigate to any domain |
| File clipboard | Limited API support | Full control with DOM operations |

---

## Basics: Connection & Permissions

### Unified CDP Helper

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
    result = await cdp(ws, "Target.getTargets")
    target_id = result["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]
```

### Enable Required Domains

```python
async def enable_domains(ws, session_id):
    """Enable all CDP domains needed for clipboard operations"""
    await cdp(ws, "Page.enable", session_id=session_id)
    await cdp(ws, "Runtime.enable", session_id=session_id)
    print("All required domains enabled")
```

### Grant Clipboard Permissions in One Call

This is the key to CDP clipboard control — granting permissions without a dialog:

```python
async def grant_clipboard_permissions(ws, session_id, origin=None):
    """
    Silently grant clipboard access via CDP
    No user click on "Allow" needed
    """
    params = {
        "permissions": [
            {"name": "clipboard-read"},
            {"name": "clipboard-write"}
        ]
    }
    if origin:
        params["origin"] = origin
    
    await cdp(ws, "Browser.grantPermissions", params, session_id=session_id)
    print(f"Clipboard permissions granted (origin: {origin or 'current page'})")
    return True


async def revoke_clipboard_permissions(ws, session_id, origin=None):
    """Revoke previously granted clipboard permissions"""
    params = {
        "permissions": [
            {"name": "clipboard-read"},
            {"name": "clipboard-write"}
        ]
    }
    if origin:
        params["origin"] = origin
    
    await cdp(ws, "Browser.resetPermissions", params, session_id=session_id)
    print("Clipboard permissions revoked")
```

---

## Reading Clipboard Text

Use `Runtime.evaluate` to call `navigator.clipboard.readText()`:

```python
async def read_clipboard_text(ws, session_id):
    """
    Read text from the system clipboard
    Requires clipboard-read permission before calling
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (async () => {
                try {
                    const text = await navigator.clipboard.readText();
                    return { success: true, data: text };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            })()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        clipboard_text = outcome["data"]
        print(f"Clipboard read: {clipboard_text[:100]}{'...' if len(clipboard_text) > 100 else ''}")
        return clipboard_text
    else:
        error = outcome.get("error", "Unknown error")
        print(f"Clipboard read failed: {error}")
        return None


async def read_clipboard_html(ws, session_id):
    """
    Read HTML content from the clipboard
    Note: may not be supported on all browsers/systems
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": """
            (async () => {
                try {
                    const items = await navigator.clipboard.read();
                    const results = [];
                    for (const item of items) {
                        const entry = { types: item.types };
                        for (const type of item.types) {
                            const blob = await item.getType(type);
                            entry[type] = await blob.text();
                        }
                        results.push(entry);
                    }
                    return { success: true, data: results };
                } catch (e) {
                    return { success: false, error: e.message };
                }
            })()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        items = outcome["data"]
        for i, item in enumerate(items):
            print(f"Clipboard item {i + 1}: types = {item.get('types', [])}")
        return items
    else:
        print(f"Clipboard HTML read failed: {outcome.get('error', '')}")
        return None
```

---

## Writing Clipboard Text

Use `navigator.clipboard.writeText()` to write to the system clipboard:

```python
async def write_clipboard_text(ws, session_id, text):
    """
    Write text to the system clipboard
    Requires clipboard-write permission before calling
    """
    escaped_text = json.dumps(text)
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (async () => {{
                try {{
                    await navigator.clipboard.writeText({escaped_text});
                    return {{ success: true }};
                }} catch (e) {{
                    return {{ success: false, error: e.message }};
                }}
            }})()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        print(f"Text written to clipboard ({len(text)} chars)")
        return True
    else:
        print(f"Clipboard write failed: {outcome.get('error', '')}")
        return False


async def write_clipboard_with_format(ws, session_id, text, html=None):
    """
    Write formatted content to clipboard (both plain text and HTML)
    Target applications will auto-select the best format on paste
    """
    escaped_text = json.dumps(text)
    escaped_html = json.dumps(html or text)
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (async () => {{
                try {{
                    const blob_text = new Blob(
                        [{escaped_text}], {{ type: 'text/plain' }}
                    );
                    const blob_html = new Blob(
                        [{escaped_html}], {{ type: 'text/html' }}
                    );
                    await navigator.clipboard.write([
                        new ClipboardItem({{
                            'text/plain': blob_text,
                            'text/html': blob_html
                        }})
                    ]);
                    return {{ success: true }};
                }} catch (e) {{
                    return {{ success: false, error: e.message }};
                }}
            }})()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        print(f"Formatted content written to clipboard "
              f"(text: {len(text)} chars, HTML: {len(html or text)} chars)")
        return True
    else:
        print(f"Formatted clipboard write failed: {outcome.get('error', '')}")
        return False
```

---

## Permission Handling in Detail

### Check Current Permission State

```python
async def check_clipboard_permission(ws, session_id, perm_name="clipboard-read"):
    """
    Check if the current page has the specified clipboard permission
    perm_name: clipboard-read or clipboard-write
    """
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (async () => {{
                try {{
                    const status = await navigator.permissions.query({{ name: '{perm_name}' }});
                    return {{
                        state: status.state,
                        name: status.name
                    }};
                }} catch (e) {{
                    return {{ state: 'error', error: e.message }};
                }}
            }})()
        """,
        "awaitPromise": True
    }, session_id=session_id)
    
    status = result.get("result", {}).get("value", {})
    state = status.get("state", "unknown")
    
    state_labels = {
        "granted": " Granted",
        "prompt": " Needs user confirmation",
        "denied": " Denied"
    }
    
    print(f"Permission '{perm_name}': {state_labels.get(state, state)}")
    return status


async def check_all_clipboard_permissions(ws, session_id):
    """Check all clipboard-related permissions"""
    for perm in ["clipboard-read", "clipboard-write"]:
        await check_clipboard_permission(ws, session_id, perm)


async def ensure_clipboard_access(ws, session_id):
    """
    Ensure clipboard is accessible — grant then verify
    Warns if permission state is not correct after granting
    """
    await grant_clipboard_permissions(ws, session_id)
    await asyncio.sleep(0.5)
    
    read_status = await check_clipboard_permission(ws, session_id, "clipboard-read")
    
    if read_status.get("state") != "granted":
        print("Warning: clipboard-read permission not active, "
              "retrying with explicit origin...")
        # Fallback: get current origin and re-grant
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": "window.location.origin"
        }, session_id=session_id)
        origin = result.get("result", {}).get("value", "")
        if origin:
            await grant_clipboard_permissions(ws, session_id, origin)
```

### Permission Isolation Between Origins

```python
async def grant_for_specific_origin(ws, target_url):
    """Grant clipboard permissions for a specific origin"""
    session_id = None
    
    async with websockets.connect(CDP_URL) as ws:
        result = await cdp(ws, "Target.getTargets")
        target_id = result["targetInfos"][0]["targetId"]
        session = await cdp(ws, "Target.attachToTarget", {
            "targetId": target_id, "flatten": True
        })
        session_id = session["sessionId"]
        
        await cdp(ws, "Page.enable", session_id=session_id)
        await cdp(ws, "Page.navigate", {"url": target_url}, session_id=session_id)
        await asyncio.sleep(2)
        
        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        
        await grant_clipboard_permissions(ws, session_id, origin)
        
        return session_id
```

---

## Automated Copy & Paste

### Complete Copy-Paste Pipeline

```python
async def auto_copy(ws, session_id, selector=None, js_expression=None):
    """
    Automated copy operation:
    - Via selector: copy text from a page element
    - Via JS expression: copy computed data
    
    Returns the copied content
    """
    if selector:
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    try {{
                        const el = document.querySelector('{selector}');
                        if (!el) return {{ success: false, error: 'Element not found' }};
                        const text = el.textContent || el.value || el.innerText;
                        await navigator.clipboard.writeText(text);
                        el.style.outline = '2px solid #4CAF50';
                        return {{ success: true, data: text }};
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }})()
            """,
            "awaitPromise": True
        }, session_id=session_id)
    elif js_expression:
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    try {{
                        const data = {js_expression};
                        const text = typeof data === 'string' ? data : JSON.stringify(data, null, 2);
                        await navigator.clipboard.writeText(text);
                        return {{ success: true, data: text }};
                    }} catch (e) {{
                        return {{ success: false, error: e.message }};
                    }}
                }})()
            """,
            "awaitPromise": True
        }, session_id=session_id)
    else:
        raise ValueError("Must provide selector or js_expression")
    
    outcome = result.get("result", {}).get("value", {})
    
    if outcome.get("success"):
        copied = outcome["data"]
        print(f" Copy successful: {copied[:100]}{'...' if len(copied) > 100 else ''}")
        return copied
    else:
        print(f" Copy failed: {outcome.get('error', '')}")
        return None


async def auto_paste(ws, session_id, target_selector=None):
    """
    Automated paste operation:
    - With target_selector: paste clipboard content into element
    - Without: just read clipboard content
    """
    clipboard_text = await read_clipboard_text(ws, session_id)
    
    if clipboard_text is None:
        print("Clipboard is empty or unreadable")
        return None
    
    if target_selector:
        escaped_text = json.dumps(clipboard_text)
        result = await cdp(ws, "Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const el = document.querySelector('{target_selector}');
                    if (!el) return {{ success: false, error: 'Element not found' }};
                    
                    el.focus();
                    const start = el.selectionStart || 0;
                    const end = el.selectionEnd || 0;
                    const currentValue = el.value || el.textContent || '';
                    el.value = currentValue.substring(0, start) + 
                                {escaped_text} + 
                                currentValue.substring(end);
                    
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    
                    return {{ success: true, pasted_length: {escaped_text}.length }};
                }})()
            """
        }, session_id=session_id)
        
        paste_result = result.get("result", {}).get("value", {})
        if paste_result.get("success"):
            print(f" Pasted to element '{target_selector}' "
                  f"({paste_result['pasted_length']} chars)")
            return clipboard_text
        else:
            print(f" Paste failed: {paste_result.get('error', '')}")
            return None
    
    return clipboard_text
```

### Monitoring Clipboard Changes

```python
async def monitor_clipboard_changes(ws, session_id, interval=1, max_checks=10):
    """
    Poll for clipboard content changes
    Useful for detecting if page operations modified the clipboard
    """
    last_content = await read_clipboard_text(ws, session_id)
    print(f"Initial clipboard: {last_content[:50] if last_content else 'empty'}")
    
    for i in range(max_checks):
        await asyncio.sleep(interval)
        
        current = await read_clipboard_text(ws, session_id)
        
        if current != last_content:
            print(f"[Check {i + 1}] Clipboard content changed!")
            print(f"  Old: {str(last_content)[:100]}")
            print(f"  New: {str(current)[:100]}")
            last_content = current
        else:
            print(f"[Check {i + 1}] No change")
    
    return last_content
```

---

## Handling Files with DOM.setFileInputFiles

For clipboard file handling, `DOM.setFileInputFiles` is the more practical approach:

```python
async def set_file_input(ws, session_id, selector, file_paths):
    """
    Set files on a file input element via CDP's DOM.setFileInputFiles
    
    Unlike navigator.clipboard, this directly operates on file input
    elements and doesn't need clipboard permissions
    """
    # Step 1: Get element RemoteObject via Runtime.evaluate
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el) return null;
                return el;
            }})()
        """,
        "objectGroup": "file_input"
    }, session_id=session_id)
    
    remote_obj = result.get("result", {})
    object_id = remote_obj.get("objectId")
    
    if not object_id:
        print(f" Cannot get element reference for '{selector}'")
        return False
    
    # Step 2: Get node ID via DOM domain
    dom_result = await cdp(ws, "DOM.requestNode", {
        "objectId": object_id
    }, session_id=session_id)
    
    node_id = dom_result.get("nodeId")
    
    if not node_id:
        print(" Cannot resolve node ID")
        return False
    
    # Step 3: Set the file
    await cdp(ws, "DOM.setFileInputFiles", {
        "nodeId": node_id,
        "files": file_paths if isinstance(file_paths, list) else [file_paths]
    }, session_id=session_id)
    
    # Verify
    verify = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{selector}');
                if (!el || !el.files) return 0;
                return el.files.length;
            }})()
        """
    }, session_id=session_id)
    
    file_count = verify.get("result", {}).get("value", 0)
    print(f" Set {file_count} file(s) on input element")
    return file_count > 0


async def simulate_paste_event(ws, session_id, target_selector, text):
    """
    Simulate a paste event on a target element
    Fallback when navigator.clipboard is unavailable
    """
    escaped = json.dumps(text)
    
    result = await cdp(ws, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{target_selector}');
                if (!el) return false;
                
                const dt = new DataTransfer();
                dt.setData('text/plain', {escaped});
                
                const event = new ClipboardEvent('paste', {{
                    clipboardData: dt,
                    bubbles: true,
                    cancelable: true
                }});
                
                el.dispatchEvent(event);
                return true;
            }})()
        """
    }, session_id=session_id)
    
    success = result.get("result", {}).get("value", False)
    print(f"{' Success' if success else ' Failed'} paste event simulation")
    return success
```

---

## Practical: Cross-Page Data Transfer

A real-world scenario: extract data from page A and transfer via clipboard to page B:

```python
async def cross_page_clipboard_transfer(ws, source_url, target_url, extract_js, target_selector):
    """
    Complete data transfer workflow:
    1. Navigate to source page, extract data
    2. Write to clipboard
    3. Navigate to target page
    4. Paste into target element
    
    Args:
        source_url: Source data page
        target_url: Target page
        extract_js: JS expression to extract data (returns string)
        target_selector: CSS selector for destination element
    """
    result = await cdp(ws, "Target.getTargets")
    target_id = result["targetInfos"][0]["targetId"]
    session = await cdp(ws, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    session_id = session["sessionId"]
    
    # Enable domains
    await cdp(ws, "Page.enable", session_id=session_id)
    await cdp(ws, "Runtime.enable", session_id=session_id)
    
    # ----- Step 1: Source page → extract data -----
    print("=" * 50)
    print("Step 1: Extract source data")
    print("=" * 50)
    
    await cdp(ws, "Page.navigate", {"url": source_url}, session_id=session_id)
    await asyncio.sleep(3)
    
    # Grant clipboard write permission
    await grant_clipboard_permissions(ws, session_id)
    
    # Extract and write to clipboard
    extracted = await auto_copy(ws, session_id, js_expression=extract_js)
    
    if not extracted:
        print("Data extraction failed")
        return False
    
    print(f"Extracted {len(extracted)} chars of data")
    
    # ----- Step 2: Navigate to target page and paste -----
    print("=" * 50)
    print("Step 2: Transfer to target page")
    print("=" * 50)
    
    await cdp(ws, "Page.navigate", {"url": target_url}, session_id=session_id)
    await asyncio.sleep(3)
    
    # Re-grant permissions (cross-origin resets them)
    await grant_clipboard_permissions(ws, session_id)
    
    # Verify clipboard survived navigation
    verify = await read_clipboard_text(ws, session_id)
    if verify != extracted:
        print("Clipboard content changed across pages, rewriting...")
        await write_clipboard_text(ws, session_id, extracted)
    
    # Paste into target
    pasted = await auto_paste(ws, session_id, target_selector)
    
    if pasted:
        print(f"Data transfer complete! {source_url} → {target_url}")
        return True
    else:
        print("Paste failed")
        return False


async def run_transfer_example():
    """Run a cross-page data transfer example"""
    source = "https://example.com/source-page"
    target = "https://example.com/target-page"
    
    # Extract all table data from the page
    extract_js = """
        (() => {
            const tables = document.querySelectorAll('table');
            let result = '';
            tables.forEach((table, i) => {
                result += `=== Table ${i + 1} ===\\n`;
                const rows = table.querySelectorAll('tr');
                rows.forEach(row => {
                    const cells = row.querySelectorAll('td, th');
                    result += Array.from(cells).map(c => c.textContent.trim()).join('\\t') + '\\n';
                });
                result += '\\n';
            });
            return result || document.body.innerText;
        })()
    """
    
    async with websockets.connect(CDP_URL) as ws:
        await cross_page_clipboard_transfer(
            ws,
            source_url=source,
            target_url=target,
            extract_js=extract_js,
            target_selector="textarea, [contenteditable='true'], .editor"
        )

# asyncio.run(run_transfer_example())
```

### Batch Data Export to Clipboard

```python
async def export_data_via_clipboard(ws, session_id, data_list, field_names):
    """
    Export structured data as TSV to clipboard
    User can paste directly into Excel/Google Sheets
    """
    # Build TSV
    header = "\t".join(field_names)
    rows = [header]
    
    for item in data_list:
        row = "\t".join(str(item.get(f, "")) for f in field_names)
        rows.append(row)
    
    tsv_content = "\n".join(rows)
    
    # Build HTML table version
    html_rows = ["<table><tr>" + "".join(f"<th>{f}</th>" for f in field_names) + "</tr>"]
    for item in data_list:
        html_rows.append(
            "<tr>" + "".join(f"<td>{item.get(f, '')}</td>" for f in field_names) + "</tr>"
        )
    html_rows.append("</table>")
    html_content = "\n".join(html_rows)
    
    success = await write_clipboard_with_format(ws, session_id, tsv_content, html_content)
    
    if success:
        print(f"Exported {len(data_list)} rows to clipboard (ready for Excel paste)")
    
    return success
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: Grant Permissions Before API Calls

```python
# Wrong order
await read_clipboard_text(ws, session_id)  # Read first → fails
await grant_clipboard_permissions(ws, session_id)  # Grant too late

# Correct order
await grant_clipboard_permissions(ws, session_id)  # Grant first
await asyncio.sleep(0.3)  # Wait for propagation
await read_clipboard_text(ws, session_id)  # Now read → succeeds
```

### Pitfall 2: Permissions Reset on Cross-Origin Navigation

```python
# Page A granted → navigate to Page B → clipboard-read resets to "prompt"
# Must grant on each page separately

await grant_clipboard_permissions(ws, session_id)  # For page A
await cdp(ws, "Page.navigate", {"url": "https://other-domain.com"}, session_id=session_id)
await grant_clipboard_permissions(ws, session_id)  # Must re-grant for page B
```

### Pitfall 3: Clipboard API Needs Active Page

```python
# If page is hidden or unfocused, clipboard API may fail
# Ensure the page is visible or use CDP reliably
```

### Pitfall 4: Some Inputs Don't Support ClipboardEvent

```python
# Fallbacks for ClipboardEvent-unsupported elements:
# 1. DOM.setFileInputFiles for file inputs
# 2. Direct value setting + input event dispatch
# 3. innerText setting for contentEditable elements
```

### Best Practices Checklist

| Note | Recommendation |
|------|---------------|
| Permission order | Always grantPermissions before read/write |
| Cross-origin reset | Re-grant after each domain navigation |
| Error handling | Wrap every clipboard API call in try-catch |
| Page focus | Ensure target page is visible |
| Permission scope | Permissions are per-origin, not per-page |
| File handling | Use DOM.setFileInputFiles, not clipboard API |
| Verification | Read back immediately after write to verify |

---

## Complete Reference: CDP Clipboard Manager Class

```python
class CDPClipboardManager:
    """CDP Clipboard Operations Manager"""
    
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
    
    async def grant_permissions(self, origin=None):
        """Grant clipboard read/write permissions"""
        params = {"permissions": [
            {"name": "clipboard-read"},
            {"name": "clipboard-write"}
        ]}
        if origin:
            params["origin"] = origin
        await self._cmd("Browser.grantPermissions", params)
        print("Clipboard permissions granted")
    
    async def read_text(self):
        """Read clipboard text"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": """
                (async () => {
                    try {
                        const t = await navigator.clipboard.readText();
                        return { ok: true, text: t };
                    } catch (e) {
                        return { ok: false, error: e.message };
                    }
                })()
            """,
            "awaitPromise": True
        })
        v = result.get("result", {}).get("value", {})
        return v.get("text") if v.get("ok") else None
    
    async def write_text(self, text):
        """Write text to clipboard"""
        escaped = json.dumps(text)
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    try {{
                        await navigator.clipboard.writeText({escaped});
                        return {{ ok: true }};
                    }} catch (e) {{
                        return {{ ok: false, error: e.message }};
                    }}
                }})()
            """,
            "awaitPromise": True
        })
        v = result.get("result", {}).get("value", {})
        return v.get("ok", False)
    
    async def copy_from_element(self, selector):
        """Copy text from a page element"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                (async () => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return {{ ok: false }};
                    const text = el.textContent || el.value || '';
                    await navigator.clipboard.writeText(text);
                    return {{ ok: true, text: text }};
                }})()
            """,
            "awaitPromise": True
        })
        v = result.get("result", {}).get("value", {})
        return v.get("text") if v.get("ok") else None
    
    async def paste_to_element(self, selector, text):
        """Paste text into a target element"""
        escaped = json.dumps(text)
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                (() => {{
                    const el = document.querySelector('{selector}');
                    if (!el) return false;
                    el.focus();
                    const start = el.selectionStart || 0;
                    const val = el.value || el.textContent || '';
                    el.value = val.slice(0, start) + {escaped} + val.slice(el.selectionEnd || 0);
                    el.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    return true;
                }})()
            """
        })
        return result.get("result", {}).get("value", False)
    
    async def set_files(self, selector, file_paths):
        """Set files via DOM.setFileInputFiles"""
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                document.querySelector('{selector}');
            """,
            "objectGroup": "file_input"
        })
        obj_id = result.get("result", {}).get("objectId")
        if not obj_id:
            return False
        dom = await self._cmd("DOM.requestNode", {"objectId": obj_id})
        node_id = dom.get("nodeId")
        if not node_id:
            return False
        await self._cmd("DOM.setFileInputFiles", {
            "nodeId": node_id,
            "files": [file_paths] if isinstance(file_paths, str) else file_paths
        })
        return True
```

**Usage Example:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    clip = CDPClipboardManager(ws, session_id)
    
    # Grant → read → write → paste in one flow
    await clip.grant_permissions()
    
    text = await clip.read_text()
    print(f"Clipboard: {text}")
    
    await clip.write_text("New content")
    await clip.paste_to_element("textarea#editor", "Pasted text")
```

---

> **Summary**: CDP combined with `Browser.grantPermissions` and `Runtime.evaluate` enables fully automated clipboard operations without any user interaction. The key points are: always grant clipboard-read and clipboard-write permissions on the target page first, handle permission resets after cross-origin navigation, and combine the navigator.clipboard API with DOM.setFileInputFiles for a complete clipboard automation solution.

---

*Previous: CDP Memory Profiling Guide: Detecting Memory Leaks with Python*

*Next up: CDP Browser History Management: Controlling Page Navigation with Python*