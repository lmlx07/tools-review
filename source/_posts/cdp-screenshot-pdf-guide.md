---
title: CDP 截图与 PDF 导出指南：用 Python 生成精确页面快照
date: 2026-06-05 17:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 截图
  - PDF
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）生成页面截图和 PDF 文档。涵盖视口截图、全页截图、元素级截图、PDF 导出配置（纸张大小/页边距/页眉页脚），以及批量生成报告的最佳实践。
---

> **一句话总结**：CDP 的 `Page.captureScreenshot` 和 `Page.printToPDF` 提供了浏览器引擎级别的截图和 PDF 生成能力，比 html2canvas、wkhtmltopdf 等方法更精确、更可靠。

---

## 目录

1. [为什么用 CDP 做截图和 PDF](#为什么用-cdp-做截图和-pdf)
2. [基础截图：Page.captureScreenshot](#基础截图pagecapturescreenshot)
3. [全页截图](#全页截图)
4. [元素级截图](#元素级截图)
5. [PDF 导出](#pdf-导出)
6. [实战：批量生成网页报告](#实战批量生成网页报告)
7. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 为什么用 CDP 做截图和 PDF

| 功能 | html2canvas / puppeteer | CDP 原生 API |
|------|------------------------|-------------|
| 渲染精度 | ⚠️ 重新绘制，可能偏差 | ✅ 浏览器引擎直接输出 |
| 全页截图 | ⚠️ 需要滚动拼接 | ✅ 原生支持 |
| WebGL/Canvas | ❌ 无法捕获 | ✅ 完整捕获 |
| PDF 带页眉页脚 | ❌ 需额外处理 | ✅ 原生支持 |
| 选择性隐藏元素 | ✅ 可注入 CSS | ✅ `captureBeyondViewport` 控制 |
| 截取特定元素 | ⚠️ 需计算裁剪区域 | ✅ 结合 DOM API 精确裁剪 |

**核心场景**：
- 自动化生成网页快照用于测试报告
- 批量导出页面为 PDF 存档
- 视觉回归测试（Visual Regression Testing）
- 生成网页长截图用于分享

---

## 基础截图：Page.captureScreenshot

### 最简单的截图

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
    """
    截取当前视口的截图并保存到文件
    - format: "png" 或 "jpeg"
    - quality: JPEG 质量（1-100），仅 format="jpeg" 时有效
    """
    params = {"format": format}
    if quality and format == "jpeg":
        params["quality"] = quality
    
    result = await cdp(ws, session_id, "Page.captureScreenshot", params)
    
    import base64
    image_data = base64.b64decode(result.get("data", ""))
    with open(file_path, "wb") as f:
        f.write(image_data)
    
    print(f"截图已保存: {file_path} ({len(image_data) / 1024:.1f} KB)")
    return file_path


# 使用示例
async def example_basic():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        await cdp(ws, session_id, "Page.navigate", {
            "url": "https://example.com"
        })
        await asyncio.sleep(3)
        await take_screenshot(ws, session_id, "screenshot.png")
```

### JPEG vs PNG 选择

```python
# PNG：无损，适合文字/UI 截图
await take_screenshot(ws, session_id, "ui.png", format="png")

# JPEG：有损压缩，文件更小，适合富图页面
await take_screenshot(ws, session_id, "photo.jpg", format="jpeg", quality=80)

# JPEG 质量对比
await take_screenshot(ws, session_id, "high.jpg", format="jpeg", quality=100)  # 高质量，文件大
await take_screenshot(ws, session_id, "medium.jpg", format="jpeg", quality=60)  # 平衡
await take_screenshot(ws, session_id, "low.jpg", format="jpeg", quality=20)     # 小文件，有损
```

---

## 全页截图

### 方法：先获取页面尺寸，再截图

```python
async def get_content_size(ws, session_id):
    """获取页面完整内容尺寸"""
    result = await cdp(ws, session_id, "Runtime.evaluate", {
        "expression": "JSON.stringify({width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight})",
        "returnByValue": True
    })
    import json as pyjson
    return pyjson.loads(result["result"]["value"])


async def take_fullpage_screenshot(ws, session_id, file_path):
    """截取完整页面长截图"""
    # 1. 获取完整内容尺寸
    size = await get_content_size(ws, session_id)
    print(f"页面尺寸: {size['width']}x{size['height']}")
    
    # 2. 设置视口为完整页面大小
    await cdp(ws, session_id, "Emulation.setDeviceMetricsOverride", {
        "width": size["width"],
        "height": size["height"],
        "deviceScaleFactor": 1,
        "mobile": False
    })
    
    await asyncio.sleep(0.5)  # 等待重排
    
    # 3. 截图（captureBeyondViewport 控制是否截取视口外内容）
    result = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "png",
        "captureBeyondViewport": True  # 截取完整页面内容
    })
    
    # 4. 恢复视口
    await cdp(ws, session_id, "Emulation.clearDeviceMetricsOverride")
    
    # 5. 保存
    import base64
    image_data = base64.b64decode(result.get("data", ""))
    with open(file_path, "wb") as f:
        f.write(image_data)
    
    print(f"全页截图已保存: {file_path} ({len(image_data) / 1024:.1f} KB)")
    return file_path
```

### 处理超长页面（分段截图）

对于极其长的页面，一次截图可能超出 GPU 限制。此时可以采用分段策略：

```python
async def take_fullpage_screenshot_segmented(ws, session_id, file_path, segment_height=4096):
    """
    分段截取长页面（应对 GPU 纹理大小限制）
    """
    import base64
    from PIL import Image
    import io
    
    # 1. 获取页面完整高度
    size = await get_content_size(ws, session_id)
    total_height = size["height"]
    viewport_width = size["width"]
    
    print(f"页面总高度: {total_height}px, 分段高度: {segment_height}px")
    
    segments = []
    y_offset = 0
    
    while y_offset < total_height:
        current_height = min(segment_height, total_height - y_offset)
        
        # 滚动到当前位置
        await cdp(ws, session_id, "Runtime.evaluate", {
            "expression": f"window.scrollTo(0, {y_offset})"
        })
        await asyncio.sleep(0.3)
        
        # 截图当前段落
        result = await cdp(ws, session_id, "Page.captureScreenshot", {
            "format": "png"
        })
        segments.append(result.get("data", ""))
        
        print(f"  段落 {len(segments)}: y={y_offset}, 高度={current_height}")
        y_offset += current_height
    
    # 拼接
    images = []
    for seg_base64 in segments:
        img = Image.open(io.BytesIO(base64.b64decode(seg_base64)))
        images.append(img)
    
    # 创建拼接画布
    combined = Image.new("RGB", (viewport_width, total_height))
    y = 0
    for img in images:
        combined.paste(img, (0, y))
        y += img.height
    
    combined.save(file_path, "PNG")
    print(f"拼接后的全页截图: {file_path}")
    return file_path
```

---

## 元素级截图

结合 DOM 定位，截取特定元素：

```python
async def take_element_screenshot(ws, session_id, css_selector, file_path):
    """
    截取指定 CSS 选择器匹配的元素的截图
    """
    # 1. 获取元素的位置和尺寸
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
        print(f"未找到元素: {css_selector}")
        return None
    
    print(f"元素位置: x={rect_data['x']}, y={rect_data['y']}, "
          f"w={rect_data['width']}, h={rect_data['height']}")
    
    # 2. 截图整个视口
    result = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "png"
    })
    
    # 3. 裁剪出元素区域
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
    print(f"元素截图已保存: {file_path}")
    return file_path


# 使用示例：截取页面中所有图片
async def screenshot_all_images(ws, session_id, output_dir):
    """截取页面中所有可见图片"""
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    # 获取所有图片元素的位置
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
    print(f"找到 {len(images)} 张可见图片")
    
    for img_info in images:
        selector = f"img:nth-of-type({img_info['index'] + 1})"
        file_name = f"img_{img_info['index']}_{os.path.basename(img_info['src'])[:30]}.png"
        file_path = os.path.join(output_dir, file_name)
        await take_element_screenshot(ws, session_id, selector, file_path)
```

---

## PDF 导出

### 基础 PDF 导出

```python
async def export_pdf(ws, session_id, file_path, **kwargs):
    """
    导出页面为 PDF
    可选参数：
    - paperWidth / paperHeight: 纸张尺寸（英寸，默认 8.5x11）
    - marginTop / marginBottom / marginLeft / marginRight: 页边距（英寸，默认 1cm）
    - printBackground: 是否打印背景（默认 False）
    - displayHeaderFooter: 是否显示页眉页脚（默认 False）
    - headerTemplate / footerTemplate: 自定义页眉页脚 HTML
    - landscape: 横向打印（默认 False）
    - scale: 缩放比例（默认 1）
    """
    params = {
        "printBackground": True,
        "displayHeaderFooter": False,
        **kwargs
    }
    
    result = await cdp(ws, session_id, "Page.printToPDF", params)
    
    import base64
    pdf_data = base64.b64decode(result.get("data", ""))
    with open(file_path, "wb") as f:
        f.write(pdf_data)
    
    print(f"PDF 已保存: {file_path} ({len(pdf_data) / 1024:.1f} KB)")
    return file_path


# 使用示例
async def example_pdf():
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        await cdp(ws, session_id, "Page.navigate", {
            "url": "https://example.com"
        })
        await asyncio.sleep(3)
        
        # 默认 A4 纸张
        await export_pdf(ws, session_id, "default.pdf")
        
        # 自定义 A4 横向 + 页眉页脚
        await export_pdf(ws, session_id, "report.pdf",
            paperWidth=8.27, paperHeight=11.69,  # A4
            landscape=False,
            marginTop=0.5, marginBottom=0.5,
            marginLeft=0.5, marginRight=0.5,
            printBackground=True,
            displayHeaderFooter=True,
            headerTemplate="<div style='font-size:10px;text-align:center;'>Report</div>",
            footerTemplate=("<div style='font-size:10px;text-align:center;'>"
                           "Page <span class='pageNumber'></span> of "
                           "<span class='totalPages'></span></div>"),
            scale=0.8  # 缩小以容纳更多内容
        )
```

### PDF 页眉页脚模板

页眉页脚使用 HTML 模板，支持特殊变量：

```python
# 页眉模板示例
HEADER_TEMPLATE = """
<div style="
    font-size: 9px;
    color: #666;
    text-align: center;
    width: 100%;
    border-bottom: 1px solid #ddd;
    padding-bottom: 5px;
    margin: 0 20px;
">
    <span class="title"></span>
</div>
"""

# 页脚模板示例
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

# ⚠️ 注意：页眉页脚中的特殊变量
# <span class="pageNumber"></span>  → 当前页码
# <span class="totalPages"></span> → 总页数
# <span class="title"></span>      → 文档标题
# <span class="url"></span>        → 页面 URL
# <span class="date"></span>       → 当前日期
```

---

## 实战：批量生成网页报告

综合运用截图和 PDF，批量生成多个页面的报告：

```python
async def batch_report(pages, output_dir, format="pdf"):
    """
    批量生成网页报告
    pages: [{"name": "Page1", "url": "https://..."}, ...]
    """
    import os
    os.makedirs(output_dir, exist_ok=True)
    
    async with websockets.connect(CDP_URL) as ws:
        session_id = await connect_page(ws)
        
        for page in pages:
            print(f"\n处理: {page['name']} ({page['url']})")
            
            # 导航
            await cdp(ws, session_id, "Page.navigate", {"url": page["url"]})
            await asyncio.sleep(3)
            
            if format == "pdf":
                file_name = f"{page['name'].replace(' ', '_')}.pdf"
                file_path = os.path.join(output_dir, file_name)
                
                await export_pdf(ws, session_id, file_path,
                    paperWidth=8.27, paperHeight=11.69,
                    printBackground=True,
                    displayHeaderFooter=True,
                    headerTemplate=HEADER_TEMPLATE,
                    footerTemplate=FOOTER_TEMPLATE
                )
            else:
                # 截图模式
                file_name = f"{page['name'].replace(' ', '_')}.png"
                file_path = os.path.join(output_dir, file_name)
                
                await take_fullpage_screenshot(ws, session_id, file_path)
            
            print(f"  完成: {file_path}")
    
    print(f"\n批量报告生成完毕！输出目录: {output_dir}")


# 使用示例
async def generate_test_report():
    pages = [
        {"name": "Dashboard", "url": "https://example.com/dashboard"},
        {"name": "Settings", "url": "https://example.com/settings"},
        {"name": "User Profile", "url": "https://example.com/profile"},
    ]
    
    await batch_report(pages, "./reports", format="pdf")
```

### 视觉回归测试

使用截图进行自动化视觉对比：

```python
async def visual_regression_test(ws, session_id, url, baseline_path, output_path):
    """
    视觉回归测试：截取当前页面并与基线对比
    """
    from PIL import Image
    import io
    import base64
    
    # 1. 截取当前页面
    await cdp(ws, session_id, "Page.navigate", {"url": url})
    await asyncio.sleep(3)
    
    current = await cdp(ws, session_id, "Page.captureScreenshot", {
        "format": "png"
    })
    current_img = Image.open(
        io.BytesIO(base64.b64decode(current.get("data", "")))
    )
    
    # 2. 加载基线截图
    try:
        baseline_img = Image.open(baseline_path)
    except FileNotFoundError:
        # 没有基线，保存当前截图作为基线
        current_img.save(baseline_path)
        print("基线已创建")
        return {"match": True, "message": "基线已创建"}
    
    # 3. 对比
    diff = Image.new("RGB", current_img.size)
    changed_pixels = 0
    
    for x in range(current_img.width):
        for y in range(current_img.height):
            p1 = current_img.getpixel((x, y))
            p2 = baseline_img.getpixel((x, y))
            if p1 != p2:
                diff.putpixel((x, y), (255, 0, 0))  # 红色标记差异
                changed_pixels += 1
            else:
                diff.putpixel((x, y), p1)
    
    total_pixels = current_img.width * current_img.height
    change_ratio = changed_pixels / total_pixels
    
    diff.save(output_path)
    
    result = {
        "match": change_ratio < 0.01,  # 差异 < 1% 认为匹配
        "changed_pixels": changed_pixels,
        "change_ratio": round(change_ratio * 100, 2),
        "diff_path": output_path
    }
    
    print(f"视觉对比: {result['change_ratio']}% 变化")
    return result
```

---

## 常见踩坑与最佳实践

### 踩坑 1：JPEG 独有 quality 参数

`quality` 参数**仅对 JPEG 格式有效**，PNG 会忽略此参数：

```python
# ❌ PNG 下设 quality 无效
await cdp(ws, session_id, "Page.captureScreenshot", {
    "format": "png", "quality": 80  # quality 被忽略
})

# ✅ JPEG 下 quality 生效
await cdp(ws, session_id, "Page.captureScreenshot", {
    "format": "jpeg", "quality": 80
})
```

### 踩坑 2：全页截图受 GPU 限制

极长的页面（超过 16384px）可能导致截图失败：

```python
# ❌ 超长页面可能截取失败
if total_height > 16384:
    # 某些 GPU 不支持超过 16384px 的纹理
    await take_fullpage_screenshot_segmented(ws, session_id, file_path)
```

### 踩坑 3：PDF 不支持所有 CSS 特性

`printToPDF` 基于浏览器的打印渲染引擎，部分 CSS 特性可能不生效：

```python
# ❌ PDF 中可能不生效的特性：
# - backdrop-filter
# - position: sticky（部分支持）
# - CSS animations
# - 某些 Web Fonts（需要加载时间）

# ✅ 建议：
# - 截图转 PDF（更准确但文件更大）
# - PDF 模式下避免使用复杂 CSS 效果
```

### 踩坑 4：截图前确保页面已完全加载

```python
# ❌ 导航后立即截图（页面可能未完全渲染）
await cdp(ws, session_id, "Page.navigate", {"url": url})
await take_screenshot(ws, session_id, "shot.png")  # 可能空白

# ✅ 等 load 事件
await cdp(ws, session_id, "Page.navigate", {"url": url})
await cdp(ws, session_id, "Page.loadEventFired")
await asyncio.sleep(1)  # 额外等待异步渲染
await take_screenshot(ws, session_id, "shot.png")
```

### 踩坑 5：PDF 页眉页脚 HTML 限制

页眉页脚模板只支持有限的 HTML 和内联样式：

```python
# ❌ 不支持外部样式、JavaScript、图片
header = "<link rel='stylesheet' href='style.css'>..."  # 不会加载

# ✅ 只使用内联样式
header = "<div style='font-size:10px;color:#333;'>Title</div>"
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 截图格式 | 文字/UI 用 PNG，富图页面用 JPEG |
| quality 参数 | 仅 JPEG 有效 |
| 全页截图 | 超长页面分段截取并拼接 |
| PDF 兼容性 | 避免使用复杂 CSS 效果 |
| 加载状态 | 等 load 事件后再截图/导出 |
| 页眉页脚 | 只使用内联样式 |
| 文件管理 | 截图画质和文件大小需平衡 |

---

## 完整参考：CDP 截图与 PDF 工具类

```python
import asyncio
import json
import base64
import os
from PIL import Image
import io


class CDPScreenshotPDF:
    """CDP 截图与 PDF 工具"""
    
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
        # Get full page size
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
                    (el => el ? {{x: el.getBoundingClientRect().x, y: el.getBoundingClientRect().y, w: el.offsetWidth, h: el.offsetHeight}} : null)
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

**使用示例：**

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

> **总结**：CDP 的截图和 PDF API 提供了浏览器引擎级别的精确输出能力，比第三方工具更可靠。全页截图、元素裁剪、PDF 配置页眉页脚等功能，让自动化生成网页报告变得简单高效。

---

*上一篇回顾：CDP 移动设备模拟指南——用 Python 调试移动端页面。*

*下一篇预告：CDP Console 调试与日志——如何捕获页面控制台消息和运行时异常。*
