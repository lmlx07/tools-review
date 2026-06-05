---
lang: en
title: "CDP Screenshot & PDF Export Guide: Generate Precise Page Snapshots with Python"
date: "2026-06-05 17:00:00"
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - Screenshot
  - PDF
  - Browser Automation
categories:
  - CDP Advanced
  - Python Practice
description: A comprehensive guide to generating page screenshots and PDF documents using Chrome DevTools Protocol (CDP). Learn viewport screenshots, full-page capture, element-level cropping, PDF export with custom paper/margins/headers, and batch report generation.
---

> **Summary in one sentence**: CDP's `Page.captureScreenshot` and `Page.printToPDF` deliver browser-engine-level screenshot and PDF generation — more accurate and reliable than html2canvas, wkhtmltopdf, or other third-party approaches.

---

## Table of Contents

1. [Why Use CDP for Screenshots & PDF](#why-use-cdp-for-screenshots--pdf)
2. [Basic Screenshot: Page.captureScreenshot](#basic-screenshot-pagecapturescreenshot)
3. [Full-Page Screenshots](#full-page-screenshots)
4. [Element-Level Screenshots](#element-level-screenshots)
5. [PDF Export](#pdf-export)
6. [Practical: Batch Report Generation](#practical-batch-report-generation)
7. [Common Pitfalls & Best Practices](#common-pitfalls--best-practices)

---

## Why Use CDP for Screenshots & PDF

| Feature | html2canvas / puppeteer | CDP Native API |
|---------|------------------------|----------------|
| Rendering accuracy | ⚠️ Re-renders, may differ | ✅ Browser engine direct output |
| Full-page capture | ⚠️ Needs scroll-stitch | ✅ Native support |
| WebGL/Canvas | ❌ Cannot capture | ✅ Full capture |
| PDF with headers/footers | ❌ Needs extra processing | ✅ Native support |
| Selective element hiding | ✅ Can inject CSS | ✅ `captureBeyondViewport` control |
| Specific element capture | ⚠️ Needs clip calculation | ✅ Precise with DOM API |

**Key use cases**:
- Automated page snapshots for test reports
- Batch exporting pages to PDF for archiving
- Visual regression testing
- Generating long page screenshots for sharing

---

## Basic Screenshot: Page.captureScreenshot

### Simplest Screenshot

```python
import asyncio
import websockets
import json

CDP_URL = "ws://127.0.0.1:9222/devtools/browser/..."
CMD_ID = [0]

async def cdp(ws, session_id, method, params=None):
    CMD_ID[0] += 1
    cmd_id = CMD_ID[0]
    await ws.send(json.dumps({
        "sessionId": session_id,
        "id": cmd_id,
        "method": method,
        "params": params or {}
    }))
    async for msg in ws:
        resp = json.loads(msg)
        if resp.get("id") == cmd_id:
            return resp.get("result", {})

async def connect_page(ws):
    targets = await cdp(ws, None, "Target.getTargets")
    target_id = targets["targetInfos"][0]["targetId"]
    session = await cdp(ws, None, "Target.attachToTarget", {
        "targetId": target_id, "flatten": True
    })
    return session["sessionId"]


async def take_screenshot(ws, session_id, file_path, format="png", quality=None):
    params = {"format": format}
    if quality and format == "jpeg":
        params["quality"] = quality
    
    result = await cdp(ws, session_id, "Page.captureScreenshot", params)
    
    import base64
    image_data = base64.b64decode(result.get("data", ""))
    with open(file_path, "wb") as f:
        f.write(image_data)
    
    print(f"Screenshot saved: {file_path} ({len(image_data) / 1024:.1f} KB)")
    return file_path
```

### JPEG vs PNG

```python
# PNG: lossless, best for text/UI screenshots
await take_screenshot(ws, session_id, "ui.png", format="png")

# JPEG: lossy compression, smaller files, best for image-heavy pages
await take_screenshot(ws, session_id, "photo.jpg", format="jpeg", quality=80)

# Quality comparison
await take_screenshot(ws, session_id, "high.jpg", format="jpeg", quality=100)
await take_screenshot(ws, session_id, "medium.jpg", format="jpeg", quality=60)
await take_screenshot(ws, session_id, "low.jpg", format="jpeg", quality=20)
```

---

## Full-Page Screenshots

### Method: Get Page Size, Then Capture

```python
async def get_content_size(ws, session_id):
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "JSON.stringify({width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight})",
        "returnByValue": True
    })
    import json as pyjson
    return pyjson.loads(result["result"]["value"])


async def take_fullpage_screenshot(ws, session_id, file_path):
    size = await get_content_size(ws, session_id)
    print(f"Page size: {size['width']}x{size['height']}")
    
    await cdp(ws, session_id, "Emulation.setDeviceMetricsOverride", {
        "width": size["width"], "height": size["height"],
        "deviceScaleFactor": 1, "mobile": False
    })
    await asyncio.sleep(0.5)
    
    result = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "png",
        "captureBeyondViewport": True
    })
    
    await cdp(ws, session_id, "Emulation.clearDeviceMetricsOverride")
    
    import base64
    image_data = base64.b64decode(result.get("data", ""))
    with open(file_path, "wb") as f:
        f.write(image_data)
    
    print(f"Full-page screenshot saved: {file_path}")
    return file_path
```

### Segmented Capture for Extra-Long Pages

```python
async def take_fullpage_screenshot_segmented(ws, session_id, file_path, segment_height=4096):
    import base64
    from PIL import Image
    import io
    
    size = await get_content_size(ws, session_id)
    total_height = size["height"]
    viewport_width = size["width"]
    
    print(f"Total height: {total_height}px, segment: {segment_height}px")
    
    segments = []
    y_offset = 0
    
    while y_offset < total_height:
        current_height = min(segment_height, total_height - y_offset)
        
        await cdp(ws, session_id, "Runtime.evaluate", {
            "expression": f"window.scrollTo(0, {y_offset})"
        })
        await asyncio.sleep(0.3)
        
        result = await cdp(ws, session_id, "Page.captureScreenshot", {"format": "png"})
        segments.append(result.get("data", ""))
        print(f"  Segment {len(segments)}: y={y_offset}, h={current_height}")
        y_offset += current_height
    
    images = [Image.open(io.BytesIO(base64.b64decode(s))) for s in segments]
    combined = Image.new("RGB", (viewport_width, total_height))
    
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height
    
    combined.save(file_path, "PNG")
    print(f"Stitched screenshot saved: {file_path}")
    return file_path
```

---

## Element-Level Screenshots

```python
async def take_element_screenshot(ws, session_id, css_selector, file_path):
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": f"""
            (() => {{
                const el = document.querySelector('{css_selector}');
                if (!el) return null;
                const rect = el.getBoundingClientRect();
                return JSON.stringify({{
                    x: rect.x, y: rect.y,
                    width: rect.width, height: rect.height
                }});
            }})()
        """,
        "returnByValue": True
    })
    
    import json as pyjson
    rect_data = pyjson.loads(result["result"]["value"])
    if not rect_data:
        print(f"Element not found: {css_selector}")
        return None
    
    result = await cdp(ws, session_id, "Page.captureScreenshot", {"format": "png"})
    
    import base64
    from PIL import Image
    import io
    
    img = Image.open(io.BytesIO(base64.b64decode(result.get("data", ""))))
    cropped = img.crop((
        rect_data["x"], rect_data["y"],
        rect_data["x"] + rect_data["width"],
        rect_data["y"] + rect_data["height"]
    ))
    cropped.save(file_path, "PNG")
    print(f"Element screenshot saved: {file_path}")
    return file_path


async def screenshot_all_images(ws, session_id, output_dir):
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": """
            Array.from(document.querySelectorAll('img')).map((img, i) => ({
                index: i,
                src: img.src,
                rect: img.getBoundingClientRect()
            })).filter(item => item.rect.width > 0 && item.rect.height > 0)
        """,
        "returnByValue": True
    })
    
    images = result["result"]["value"]
    print(f"Found {len(images)} visible images")
    
    for img_info in images:
        selector = f"img:nth-of-type({img_info['index'] + 1})"
        fname = f"img_{img_info['index']}_{os.path.basename(img_info['src'])[:30]}.png"
        await take_element_screenshot(ws, session_id, selector, os.path.join(output_dir, fname))
```

---

## PDF Export

### Basic PDF Export

```python
async def export_pdf(ws, session_id, file_path, **kwargs):
    """
    Export the page as PDF
    Parameters:
    - paperWidth / paperHeight: paper size (inches, default 8.5x11)
    - marginTop/Bottom/Left/Right: margins (inches, default 1cm ~ 0.4in)
    - printBackground: print background graphics (default False)
    - displayHeaderFooter: show header/footer (default False)
    - headerTemplate / footerTemplate: custom header/footer HTML
    - landscape: landscape orientation (default False)
    - scale: scaling factor (default 1)
    """
    params = {"printBackground": True, "displayHeaderFooter": False, **kwargs}
    result = await cdp(ws, session_id, "Page.printToPDF", params)
    
    import base64
    pdf_data = base64.b64decode(result.get("data", ""))
    with open(file_path, "wb") as f:
        f.write(pdf_data)
    
    print(f"PDF saved: {file_path} ({len(pdf_data) / 1024:.1f} KB)")
    return file_path


async def example_pdf():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
        await asyncio.sleep(3)
        
        # Default
        await export_pdf(ws, session_id, "default.pdf")
        
        # Custom A4 with headers
        await export_pdf(ws, session_id, "report.pdf",
            paperWidth=8.27, paperHeight=11.69,
            landscape=False,
            marginTop=0.5, marginBottom=0.5,
            marginLeft=0.5, marginRight=0.5,
            printBackground=True,
            displayHeaderFooter=True,
            headerTemplate="<div style='font-size:10px;text-align:center;'>Report</div>",
            footerTemplate=(
                "<div style='font-size:10px;text-align:center;'>"
                "Page <span class='pageNumber'></span> of "
                "<span class='totalPages'></span></div>"
            ),
            scale=0.8
        )
```

### Header/Footer Templates

```python
# Supported variables in header/footer:
# <span class="pageNumber"></span>  → Current page number
# <span class="totalPages"></span>  → Total pages
# <span class="title"></span>       → Document title
# <span class="url"></span>         → Page URL
# <span class="date"></span>        → Current date

FOOTER_TEMPLATE = """
<div style="
    font-size: 9px;
    color: #666;
    text-align: center;
    width: 100%;
    border-top: 1px solid #ddd;
    padding-top: 5px;
    margin: 0 20px;
">
    Page <span class="pageNumber"></span> of <span class="totalPages"></span>
    &nbsp;|&nbsp; Generated on <span class="date"></span>
</div>
"""
```

---

## Practical: Batch Report Generation

```python
async def batch_report(pages, output_dir, format="pdf"):
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        
        for page in pages:
            print(f"\nProcessing: {page['name']} ({page['url']})")
            await cdp(ws, session_id, "Page.navigate", {"url": page["url"]})
            await asyncio.sleep(3)
            
            fname = f"{page['name'].replace(' ', '_')}.{format}"
            fpath = os.path.join(output_dir, fname)
            
            if format == "pdf":
                await export_pdf(ws, session_id, fpath,
                    paperWidth=8.27, paperHeight=11.69,
                    printBackground=True,
                    displayHeaderFooter=True,
                    footerTemplate=FOOTER_TEMPLATE
                )
            else:
                await take_fullpage_screenshot(ws, session_id, fpath)
            
            print(f"  Done: {fpath}")
    
    print(f"\nBatch report complete! Output: {output_dir}")


async def visual_regression_test(ws, session_id, url, baseline_path, output_path):
    from PIL import Image
    import io
    import base64
    
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    current = await cdp(ws, session_id, "Page.captureScreenshot", {"format": "png"})
    current_img = Image.open(io.BytesIO(base64.b64decode(current.get("data", ""))))
    
    try:
        baseline_img = Image.open(baseline_path)
    except FileNotFoundError:
        current_img.save(baseline_path)
        return {"match": True, "message": "Baseline created"}
    
    diff = Image.new("RGB", current_img.size)
    changed_pixels = 0
    
    for x in range(current_img.width):
        for y in range(current_img.height):
            p1 = current_img.getpixel((x, y))
            p2 = baseline_img.getpixel((x, y))
            if p1 != p2:
                diff.putpixel((x, y), (255, 0, 0))
                changed_pixels += 1
            else:
                diff.putpixel((x, y), p1)
    
    total_pixels = current_img.width * current_img.height
    change_ratio = changed_pixels / total_pixels
    diff.save(output_path)
    
    result = {
        "match": change_ratio < 0.01,
        "changed_pixels": changed_pixels,
        "change_ratio": round(change_ratio * 100, 2),
        "diff_path": output_path
    }
    print(f"Visual diff: {result['change_ratio']}% changed")
    return result
```

---

## Common Pitfalls & Best Practices

### Pitfall 1: quality Is JPEG-Only

```python
# ❌ quality ignored for PNG
await cdp(ws, session_id, "Page.captureScreenshot", {
    "format": "png", "quality": 80
})

# ✅ quality works for JPEG
await cdp(ws, session_id, "Page.captureScreenshot", {
    "format": "jpeg", "quality": 80
})
```

### Pitfall 2: GPU Texture Limits

```python
# ❌ Pages over ~16384px may fail
if total_height > 16384:
    await take_fullpage_screenshot_segmented(ws, session_id, file_path)
```

### Pitfall 3: PDF CSS Limitations

```python
# ❌ May not render in PDF:
# - backdrop-filter
# - position: sticky (partial)
# - CSS animations
# - Some web fonts

# ✅ Use inline styles for header/footer templates
header = "<div style='font-size:10px;color:#333;'>Title</div>"
```

### Pitfall 4: Wait for Page Load

```python
# ❌ Screenshot immediately may be blank
await cdp(ws, session_id, "Page.navigate", {"url": url})
await take_screenshot(ws, session_id, "shot.png")

# ✅ Wait for load event + async rendering
await cdp(ws, session_id, "Page.navigate", {"url": url})
await cdp(ws, session_id, "Page.loadEventFired")
await asyncio.sleep(1)
await take_screenshot(ws, session_id, "shot.png")
```

### Best Practices Checklist

| Consideration | Recommendation |
|---------------|----------------|
| Format | PNG for text/UI, JPEG for image-heavy pages |
| quality | JPEG only |
| Full-page | Use segmented capture for very long pages |
| PDF CSS | Avoid complex CSS effects |
| Load state | Wait for load event before capture |
| Templates | Inline styles only for header/footer |
| File size | Balance quality and file size |

---

## Complete Reference: CDP Screenshot & PDF Class

```python
import asyncio
import json
import base64
import os
from PIL import Image
import io


class CDPScreenshotPDF:
    """CDP Screenshot & PDF Tool"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0
    
    async def _cmd(self, method, params=None):
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
    
    async def screenshot(self, path, format="png", quality=None):
        params = {"format": format, "captureBeyondViewport": True}
        if quality and format == "jpeg":
            params["quality"] = quality
        result = await self._cmd("Page.captureScreenshot", params)
        data = base64.b64decode(result["data"])
        with open(path, "wb") as f:
            f.write(data)
        return path
    
    async def fullpage_screenshot(self, path):
        result = await self._cmd("Runtime.evaluate", {
            "expression": "JSON.stringify({w: document.documentElement.scrollWidth, h: document.documentElement.scrollHeight})",
            "returnByValue": True
        })
        size = json.loads(result["result"]["value"])
        await self._cmd("Emulation.setDeviceMetricsOverride", {
            "width": size["w"], "height": size["h"],
            "deviceScaleFactor": 1, "mobile": False
        })
        await asyncio.sleep(0.5)
        result = await self._cmd("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": True
        })
        await self._cmd("Emulation.clearDeviceMetricsOverride")
        data = base64.b64decode(result["data"])
        with open(path, "wb") as f:
            f.write(data)
        return path
    
    async def element_screenshot(self, selector, path):
        result = await self._cmd("Runtime.evaluate", {
            "expression": f"""
                JSON.stringify(
                    (el => el ? {x: el.getBoundingClientRect().x, y: el.getBoundingClientRect().y, w: el.offsetWidth, h: el.offsetHeight} : null)
                    (document.querySelector('{selector}'))
                )
            """,
            "returnByValue": True
        })
        rect = json.loads(result["result"]["value"])
        if not rect:
            return None
        shot = await self._cmd("Page.captureScreenshot", {"format": "png"})
        img = Image.open(io.BytesIO(base64.b64decode(shot["data"])))
        cropped = img.crop((rect["x"], rect["y"], rect["x"] + rect["w"], rect["y"] + rect["h"]))
        cropped.save(path)
        return path
    
    async def pdf(self, path, **kwargs):
        params = {"printBackground": True, **kwargs}
        result = await self._cmd("Page.printToPDF", params)
        data = base64.b64decode(result["data"])
        with open(path, "wb") as f:
            f.write(data)
        return path
```

**Usage:**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id = await connect_page(ws)
    media = CDPScreenshotPDF(ws, session_id)
    
    await cdp(ws, session_id, "Page.navigate", {"url": "https://example.com"})
    await cdp(ws, session_id, "Page.loadEventFired")
    await asyncio.sleep(1)
    
    await media.screenshot("page.png")
    await media.fullpage_screenshot("fullpage.png")
    await media.element_screenshot("h1", "heading.png")
    await media.pdf("page.pdf", paperWidth=8.27, paperHeight=11.69)
```

---

> **Summary**: CDP's screenshot and PDF APIs deliver browser-engine-level output precision — more reliable than third-party tools. Full-page captures, element cropping, and PDF with custom headers/footers make automated web reporting simple and efficient.

---

*Previous: CDP Mobile Device Emulation Guide: Debug Mobile Pages with Python*

*Next up: CDP Console Debugging Guide: Capture Page Logs & Exceptions with Python*