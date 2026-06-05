---
title: CDP 无障碍树指南：用 Python 做自动化可访问性测试
date: 2026-06-05 16:00:00
tags:
  - Chrome DevTools Protocol
  - CDP
  - Python
  - 无障碍
  - Accessibility
  - a11y
  - 浏览器自动化
categories:
  - CDP 进阶
  - Python 实战
description: 详解如何用 Chrome DevTools Protocol（CDP）进行自动化可访问性测试。涵盖 Accessibility.enable、getFullAXTree/getPartialAXTree、AXNode 属性分析、自动审计缺失标签、焦点顺序验证，以及生成无障碍报告的最佳实践。
---

> **一句话总结**：CDP 的 `Accessibility` 域暴露了浏览器完整的无障碍树（Accessibility Tree），让我们可以用 Python 编程式地检查页面无障碍问题——标签缺失、ARIA 属性错误、焦点顺序异常等，替代昂贵的手动审核。

---

## 目录

1. [可访问性测试与 CDP](#可访问性测试与-cdp)
2. [基础：Accessibility.enable 与无障碍树](#基础accessibilityenable-与无障碍树)
3. [getFullAXTree：全量无障碍树](#getfullaxtree全量无障碍树)
4. [getPartialAXTree：部分无障碍树](#getpartialaxtree部分无障碍树)
5. [自动化可访问性审计](#自动化可访问性审计)
6. [焦点顺序验证](#焦点顺序验证)
7. [实战：无障碍报告生成器](#实战无障碍报告生成器)
8. [常见踩坑与最佳实践](#常见踩坑与最佳实践)

---

## 可访问性测试与 CDP

### 为什么用 CDP 做无障碍测试

网页无障碍（a11y，Accessibility）测试传统上依赖 axe-core、Lighthouse 等工具，或手动测试。CDP 的 `Accessibility` 域直接暴露了浏览器内部的无障碍树：

| 方法 | 优势 | 局限 |
|------|------|------|
| 手动测试 | 全面但成本高 | 耗时、需要专业知识 |
| axe-core | 规则全面 | 无法定制深层分析 |
| Lighthouse a11y | 一键报告 | 无法实时/编程式 |
| CDP Accessibility 域 | 原生无障碍树、可编程、可定制 | 需自行实现审计规则 |

### CDP Accessibility 域的关键方法

- `Accessibility.enable` — 启用无障碍事件（会触发 `AXTreeChange` 等通知）
- `Accessibility.disable` — 禁用
- `Accessibility.getFullAXTree` — 获取完整无障碍树（返回所有节点）
- `Accessibility.getPartialAXTree` — 获取特定 DOM 节点关联的部分无障碍树
- `Accessibility.queryAXTree` — 根据条件查询无障碍节点
- `Accessibility.onLoadComplete` — 无障碍树加载完成事件
- `Accessibility.onNodesLost` — 节点失联事件
- `Accessibility.onAXTreeChange` — 无障碍树变更事件

### AXNode 属性详解

```python
# AXNode 的常见属性
AX_NODE_PROPERTIES = {
    "role": "角色（button, link, heading, text 等）",
    "name": "可访问名称（由 aria-label、内容文本等计算）",
    "description": "详细描述",
    "value": "当前值（如输入框内容）",
    "disabled": "是否禁用",
    "focused": "是否聚焦",
    "hidden": "是否隐藏",
    "invalid": "是否无效（配合 aria-invalid）",
    "keyshortcuts": "快捷键绑定",
    "roledescription": "角色自定义描述",
    "valuetext": "值的文本描述",
    "checked": "复选框/单选框选中状态",
    "pressed": "按钮按下状态",
    "expanded": "展开状态",
    "level": "标题层级（h1-h6）",
    "hierarchicalLevel": "层次级别",
    "posInSet": "在集合中的位置",
    "setSize": "集合大小",
    "flowto": "焦点流向",
    "actions": "支持的动作",
}
```

---

## 基础：Accessibility.enable 与无障碍树

### 启用无障碍功能并获取基础结构

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
    """附加到第一个页面目标"""
    targets = await cdp(ws, "Target.getTargets")
    for target in targets["targetInfos"]:
        if target["type"] == "page":
            session = await cdp(ws, "Target.attachToTarget", {
                "targetId": target["targetId"], "flatten": True
            })
            return session["sessionId"], target["targetId"]
    raise Exception("未找到页面目标")


async def enable_accessibility(ws, session_id):
    """启用无障碍监听"""
    result = await cdp(ws, "Accessibility.enable", {}, session_id)
    print("Accessibility 已启用")
    return result


async def listen_axtree_events(ws, session_id, duration=30):
    """监听无障碍树变更事件"""
    await enable_accessibility(ws, session_id)
    print(f"开始监听AX树事件（{duration}秒）...")
    
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
                print(f"[AX树变更] 影响 {len(nodes)} 个节点")
                for node in nodes[:3]:
                    role_data = self._find_ax_property(node, "role")
                    name_data = self._find_ax_property(node, "name")
                    role = role_data.get("value", "unknown") if role_data else "unknown"
                    name = name_data.get("value", "") if name_data else ""
                    print(f"  role={role}, name={name[:50]}")
            
            elif method == "Accessibility.onLoadComplete":
                print("[AX树加载完成]")
                events.append({"type": "load_complete"})
            
            elif method == "Accessibility.onNodesLost":
                ids = data["params"].get("nodeIds", [])
                print(f"[AX节点失联] {len(ids)} 个节点")
                events.append({"type": "nodes_lost", "count": len(ids)})
        
        except asyncio.TimeoutError:
            pass
    
    print(f"共收到 {len(events)} 个无障碍事件")
    return events


def _find_ax_property(node, prop_name):
    """在 AXNode 的属性列表中查找指定属性"""
    properties = node.get("properties", [])
    for prop in properties:
        if prop.get("name") == prop_name:
            return prop
    return None
```

---

## getFullAXTree：全量无障碍树

### 获取完整树结构

`getFullAXTree` 返回当前页面完整的无障碍树，适合全面的审计：

```python
async def get_full_axtree(ws, session_id):
    """
    获取当前页面的完整无障碍树
    返回所有 AXNode 的列表
    """
    result = await cdp(ws, "Accessibility.getFullAXTree", {
        "max_depth": 0  # 0 表示完整深度
    }, session_id)
    
    nodes = result.get("nodes", [])
    print(f"无障碍树节点总数: {len(nodes)}")
    return nodes


def flatten_axtree(nodes):
    """
    将无障碍树展平为易于分析的格式
    """
    flat = []
    for node in nodes:
        item = {"nodeId": node.get("nodeId"), "backendNodeId": node.get("backendNodeId")}
        
        # 提取属性
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
        
        # 提取子节点关系
        child_ids = node.get("childIds", [])
        item["childCount"] = len(child_ids)
        item["childIds"] = child_ids
        
        flat.append(item)
    
    return flat


async def analyze_axtree_structure(ws, session_id):
    """
    分析无障碍树的结构组成
    """
    nodes = await get_full_axtree(ws, session_id)
    flat_nodes = flatten_axtree(nodes)
    
    print("\n===== 无障碍树结构分析 =====")
    print(f"总节点数: {len(flat_nodes)}")
    
    # 按角色统计
    role_counts = {}
    for node in flat_nodes:
        role = node.get("role", "unknown")
        role_counts[role] = role_counts.get(role, 0) + 1
    
    print("\n角色分布:")
    for role, count in sorted(role_counts.items(), key=lambda x: -x[1]):
        print(f"  {role}: {count}")
    
    # 检查标题层级
    headings = [n for n in flat_nodes if n.get("role") == "heading"]
    if headings:
        print(f"\n标题元素: {len(headings)} 个")
        levels = {}
        for h in headings:
            lvl = h.get("level", h.get("hierarchicalLevel", "?"))
            levels[lvl] = levels.get(lvl, 0) + 1
        for lvl, count in sorted(levels.items()):
            print(f"  h{lv if isinstance(lvl, str) else lvl}: {count}")
    
    # 检查可交互元素
    interactive_roles = {"button", "link", "checkbox", "radio",
                         "combobox", "menuitem", "tab", "textbox"}
    interactive = [n for n in flat_nodes if n.get("role") in interactive_roles]
    print(f"\n交互式元素: {len(interactive)} 个")
    
    return {
        "total_nodes": len(flat_nodes),
        "role_counts": role_counts,
        "interactive_count": len(interactive),
        "headings": headings
    }
```

### 提取特定角色的节点

```python
async def get_nodes_by_role(ws, session_id, target_role):
    """
    获取无障碍树中特定角色的所有节点
    """
    nodes = await get_full_axtree(ws, session_id)
    flat = flatten_axtree(nodes)
    
    matched = [n for n in flat if n.get("role") == target_role]
    
    print(f"角色「{target_role}」的节点: {len(matched)} 个")
    for node in matched:
        name = node.get("name", "(无名称)")
        desc = node.get("description", "")
        print(f"  - {name}" + (f" ({desc})" if desc else ""))
    
    return matched


async def list_all_buttons(ws, session_id):
    """列出所有按钮及其可访问名称"""
    buttons = await get_nodes_by_role(ws, session_id, "button")
    
    # 检查缺少可访问名称的按钮
    unnamed = [b for b in buttons if not b.get("name")]
    if unnamed:
        print(f"\n⚠️ {len(unnamed)} 个按钮缺少可访问名称:")
        for btn in unnamed[:5]:
            print(f"   nodeId: {btn.get('nodeId')}")
    
    return buttons


async def list_all_images(ws, session_id):
    """列出所有图片及其 alt 文本"""
    images = await get_nodes_by_role(ws, session_id, "img")
    
    missing_alt = [img for img in images if not img.get("name")]
    print(f"图片总数: {len(images)}")
    print(f"缺少 alt 文本: {len(missing_alt)}")
    
    return {"total": len(images), "missing_alt": len(missing_alt)}
```

---

## getPartialAXTree：部分无障碍树

当只需要分析特定 DOM 元素时，使用 `getPartialAXTree` 更高效：

```python
async def get_partial_axtree(ws, session_id, node_id=None, backend_node_id=None):
    """
    获取特定 DOM 节点的无障碍信息
    可通过 nodeId 或 backendNodeId 指定
    """
    params = {}
    if node_id:
        params["nodeId"] = node_id
    if backend_node_id:
        params["backendNodeId"] = backend_node_id
    
    # 还需要提供 fetchRelatives 来指定返回哪些关联节点
    params["fetchRelatives"] = True
    
    result = await cdp(ws, "Accessibility.getPartialAXTree", params, session_id)
    nodes = result.get("nodes", [])
    
    print(f"部分无障碍树节点数: {len(nodes)}")
    
    # 格式化显示
    for node in nodes:
        role_data = _find_ax_property(node, "role")
        name_data = _find_ax_property(node, "name")
        desc_data = _find_ax_property(node, "description")
        
        role = role_data.get("value", "?") if role_data else "?"
        name = name_data.get("value", "") if name_data else ""
        desc = desc_data.get("value", "") if desc_data else ""
        
        print(f"  role: {role}")
        print(f"  name: {name}")
        if desc:
            print(f"  description: {desc}")
        
        # 列出其他属性
        for prop in node.get("properties", []):
            pname = prop.get("name", "")
            if pname not in ("role", "name", "description"):
                pval = prop.get("value", {})
                actual = pval.get("value", pval.get("type", ""))
                print(f"  {pname}: {actual}")
        print()
    
    return nodes


async def inspect_element_a11y(ws, session_id, css_selector):
    """
    检查特定 CSS 选择器元素的完整无障碍信息
    """
    # 1. 先用 DOM API 找到元素
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
                    textContent: (el.textContent || '').trim().slice(0, 100),
                    innerHTML: el.innerHTML.length > 200 ?
                        el.innerHTML.slice(0, 200) + '...' : el.innerHTML
                }});
            }})()
        """,
        "sessionId": session_id,
        "returnByValue": True
    }, session_id)
    
    import json as pyjson
    dom_info = pyjson.loads(result["result"]["value"])
    
    if not dom_info:
        print(f"未找到元素: {css_selector}")
        return None
    
    print(f"===== DOM 信息: {css_selector} =====")
    for key, val in dom_info.items():
        if val:
            print(f"  {key}: {val}")
    
    # 2. 获取该元素的无障碍节点
    a11y_result = await cdp(ws, "Accessibility.getPartialAXTree", {
        "nodeId": 0,  # 实际使用时应传入 int nodeId
        "fetchRelatives": True
    }, session_id)
    
    # 替代方案：通过 queryAXTree
    query_result = await cdp(ws, "Accessibility.queryAXTree", {
        "accessibleName": dom_info.get("ariaLabel") or dom_info.get("textContent", ""),
        "role": dom_info.get("role") or "",
    }, session_id)
    
    if query_result.get("nodes"):
        print(f"\n===== 无障碍树信息 =====")
        for node in query_result["nodes"]:
            for prop in node.get("properties", []):
                pname = prop.get("name", "")
                pval = prop.get("value", {})
                actual = pval.get("value", pval.get("type", ""))
                print(f"  {pname}: {actual}")
    
    return {"dom": dom_info, "a11y": query_result}
```

### queryAXTree：按条件查询无障碍节点

```python
async def query_axtree(ws, session_id, **filters):
    """
    根据条件查询无障碍节点
    支持: role, accessibleName, accessibleNameSource 等
    """
    params = {"fetchRelatives": True}
    params.update(filters)
    
    result = await cdp(ws, "Accessibility.queryAXTree", params, session_id)
    nodes = result.get("nodes", [])
    
    print(f"查询结果: {len(nodes)} 个节点")
    for node in nodes:
        name_data = _find_ax_property(node, "name")
        role_data = _find_ax_property(node, "role")
        name = name_data.get("value", "") if name_data else ""
        role = role_data.get("value", "") if role_data else ""
        print(f"  role={role}, name={name}")
    
    return nodes


async def find_elements_without_names(ws, session_id):
    """
    查找所有缺少可访问名称的交互式元素
    """
    full_tree = await get_full_axtree(ws, session_id)
    flat = flatten_axtree(full_tree)
    
    # 交互式角色
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
                    "issue": "缺少可访问名称"
                })
    
    print(f"\n===== 无障碍问题：缺少名称的交互元素 =====")
    print(f"发现 {len(issues)} 个问题")
    for issue in issues:
        print(f"  [{issue['role']}] nodeId={issue['nodeId']} - {issue['issue']}")
    
    return issues
```

---

## 自动化可访问性审计

### 完整的审计规则引擎

```python
class AccessibilityAuditor:
    """无障碍自动审计器"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.issues = []
    
    async def run_full_audit(self):
        """运行完整的无障碍审计"""
        print("开始完整无障碍审计...\n")
        
        # 获取完整树
        nodes = await get_full_axtree(self.ws, self.session_id)
        flat = flatten_axtree(nodes)
        
        # 运行各项检查
        self.check_button_names(flat)
        self.check_image_alts(flat)
        self.check_heading_structure(flat)
        self.check_form_labels(flat)
        self.check_aria_roles(flat)
        self.check_focusable_elements(flat)
        self.check_color_contrast_issues(flat)
        self.check_landmarks(flat)
        
        # 生成报告
        self.generate_report()
        
        return self.issues
    
    def check_button_names(self, flat):
        """检查按钮是否有可访问名称"""
        buttons = [n for n in flat if n.get("role") == "button"]
        missing_name = [b for b in buttons if not b.get("name")]
        
        for btn in missing_name:
            self.issues.append({
                "type": "error",
                "rule": "button-name",
                "severity": "high",
                "message": "按钮缺少可访问名称",
                "nodeId": btn.get("nodeId"),
                "wcag": "4.1.2"
            })
        
        print(f"[按钮名称] {len(missing_name)}/{len(buttons)} 个按钮有问题")
    
    def check_image_alts(self, flat):
        """检查图片是否有 alt 文本"""
        images = [n for n in flat if n.get("role") == "img"]
        missing_alt = [img for img in images if not img.get("name")]
        
        for img in missing_alt:
            self.issues.append({
                "type": "error",
                "rule": "image-alt",
                "severity": "high",
                "message": "图片缺少替代文本",
                "nodeId": img.get("nodeId"),
                "wcag": "1.1.1"
            })
        
        print(f"[图片替代文本] {len(missing_alt)}/{len(images)} 张图片有问题")
    
    def check_heading_structure(self, flat):
        """检查标题结构是否合理"""
        headings = [n for n in flat if n.get("role") == "heading"]
        
        # 检查是否跳级（如 h1 → h3）
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
                    "message": f"标题层级跳级: h{levels[i-1]} → h{levels[i]}",
                    "wcag": "2.4.6"
                })
        
        if not headings:
            self.issues.append({
                "type": "warning",
                "rule": "page-has-heading",
                "severity": "medium",
                "message": "页面缺少标题元素",
                "wcag": "2.4.6"
            })
        
        print(f"[标题结构] 共 {len(headings)} 个标题")
    
    def check_form_labels(self, flat):
        """检查表单元素是否有标签"""
        form_roles = {"textbox", "combobox", "listbox", "slider",
                       "spinbutton", "checkbox", "radio"}
        form_elements = [n for n in flat if n.get("role") in form_roles]
        missing_label = [f for f in form_elements if not f.get("name")]
        
        for fe in missing_label:
            self.issues.append({
                "type": "error",
                "rule": "form-label",
                "severity": "high",
                "message": f"{fe.get('role', '表单元素')} 缺少关联标签",
                "nodeId": fe.get("nodeId"),
                "wcag": "1.3.1"
            })
        
        print(f"[表单标签] {len(missing_label)}/{len(form_elements)} 个表单元素有问题")
    
    def check_aria_roles(self, flat):
        """检查 ARIA 角色使用是否有效"""
        for node in flat:
            role = node.get("role", "")
            
            # 检查无效的角色值（简化示例）
            known_roles = {"button", "link", "heading", "img", "text", "textbox",
                          "checkbox", "radio", "list", "listitem", "navigation",
                          "banner", "main", "complementary", "contentinfo",
                          "form", "search", "tab", "tablist", "tabpanel",
                          "menuitem", "menu", "dialog", "alertdialog"}
            
            if role and role not in known_roles and role != "GenericContainer":
                self.issues.append({
                    "type": "warning",
                    "rule": "valid-aria-role",
                    "severity": "low",
                    "message": f"可能无效的 ARIA 角色: {role}",
                    "nodeId": node.get("nodeId"),
                    "wcag": "4.1.2"
                })
        
        print(f"[ARIA 角色] 角色检查完成")
    
    def check_focusable_elements(self, flat):
        """检查可聚焦元素是否可访问"""
        for node in flat:
            role = node.get("role", "")
            actions = node.get("actions", "")
            
            if role in ("button", "link", "checkbox", "radio"):
                disabled = node.get("disabled", False)
                if not disabled:
                    # 检查是否可以通过键盘聚焦
                    has_focus_action = "focus" in str(actions)
                    if not has_focus_action and role != "link":
                        self.issues.append({
                            "type": "warning",
                            "rule": "focusable",
                            "severity": "medium",
                            "message": f"{role} 可能无法通过键盘聚焦",
                            "nodeId": node.get("nodeId"),
                            "wcag": "2.1.1"
                        })
        
        print(f"[焦点可访问性] 检查完成")
    
    def check_landmarks(self, flat):
        """检查页面 landmark 结构"""
        landmark_roles = {"navigation", "banner", "main",
                          "complementary", "contentinfo", "search", "form"}
        landmarks = [n for n in flat if n.get("role") in landmark_roles]
        
        landmark_counts = {}
        for lm in landmarks:
            role = lm.get("role", "")
            landmark_counts[role] = landmark_counts.get(role, 0) + 1
        
        print(f"[Landmark 结构] 共 {len(landmarks)} 个 landmark:")
        for role, count in sorted(landmark_counts.items()):
            print(f"  {role}: {count}")
        
        # 检查是否缺少关键 landmarks
        required = {"main"}
        existing = set(landmark_counts.keys())
        missing = required - existing
        if missing:
            self.issues.append({
                "type": "warning",
                "rule": "landmark",
                "severity": "medium",
                "message": f"页面缺少关键 landmark: {', '.join(missing)}",
                "wcag": "1.3.1"
            })
    
    def check_color_contrast_issues(self, flat):
        """标记潜在的颜色对比度问题（基于文本节点）"""
        texts = [n for n in flat if n.get("role") == "text"]
        print(f"[颜色对比度] 共 {len(texts)} 个文本节点（需配合截图验证）")
    
    def generate_report(self):
        """生成审计报告"""
        print("\n" + "=" * 60)
        print("            无障碍审计报告")
        print("=" * 60)
        
        severity_count = {"high": 0, "medium": 0, "low": 0}
        rule_count = {}
        
        for issue in self.issues:
            severity_count[issue["severity"]] = \
                severity_count.get(issue["severity"], 0) + 1
            rule_count[issue["rule"]] = \
                rule_count.get(issue["rule"], 0) + 1
        
        print(f"\n问题总数: {len(self.issues)}")
        print(f"  高优先级: {severity_count.get('high', 0)}")
        print(f"  中优先级: {severity_count.get('medium', 0)}")
        print(f"  低优先级: {severity_count.get('low', 0)}")
        
        print(f"\n按规则分类:")
        for rule, count in sorted(rule_count.items(), key=lambda x: -x[1]):
            print(f"  {rule}: {count}")
        
        # WCAG 合规总结
        wcag_refs = set()
        for issue in self.issues:
            if "wcag" in issue:
                wcag_refs.add(issue["wcag"])
        
        print(f"\n涉及 WCAG 标准:")
        for ref in sorted(wcag_refs):
            print(f"  WCAG {ref}")
        
        print("=" * 60)
        return self.issues


async def run_a11y_audit(ws, session_id, url):
    """对指定 URL 运行完整无障碍审计"""
    await cdp(ws, "Page.navigate", {"url": url}, session_id)
    await cdp(ws, "Page.loadEventFired", {}, session_id)
    await asyncio.sleep(2)
    
    auditor = AccessibilityAuditor(ws, session_id)
    issues = await auditor.run_full_audit()
    
    return issues
```

---

## 焦点顺序验证

### 确保 Tab 键导航顺序正确

```python
async def verify_tab_order(ws, session_id):
    """
    验证页面的 Tab 键导航顺序
    通过获取所有可聚焦元素并检查它们的 tabIndex 和 DOM 顺序
    """
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
    
    print(f"\n===== Tab 焦点顺序 =====")
    print(f"可聚焦元素总数: {len(focusable)}")
    
    issues = []
    for el in focusable:
        tab_idx = el.get("tabIndex", "0")
        text = el.get("text", "").strip() or f"<{el['tag']}>"
        print(f"  #{el['index']}: {text} (tabIndex={tab_idx})")
        
        # 检查 tabIndex > 0（可能导致混乱的顺序）
        if tab_idx and tab_idx != "0":
            try:
                if int(tab_idx) > 0:
                    issues.append({
                        "type": "warning",
                        "rule": "tab-order",
                        "severity": "medium",
                        "message": f"正数 tabIndex={tab_idx} 可能导致混乱的焦点顺序",
                        "element": text,
                        "wcag": "2.4.3"
                    })
            except ValueError:
                pass
    
    if issues:
        print(f"\n⚠️ 发现 {len(issues)} 个焦点顺序问题:")
        for issue in issues:
            print(f"  - {issue['message']}")
    
    return {"focusable_elements": focusable, "issues": issues}


async def check_focus_trap(ws, session_id):
    """
    检查是否存在焦点陷阱（无法通过 Tab 离开的元素）
    """
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
                    const hasTrap = focusable.length > 0;
                    issues.push({
                        index: i,
                        tag: modal.tagName,
                        id: modal.id,
                        hasTrap: hasTrap,
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
    
    print(f"\n===== 焦点陷阱检查 =====")
    print(f"找到 {len(modals)} 个对话框/模态框")
    for m in modals:
        print(f"  {m['tag']}#{m['id']}: "
              f"可聚焦元素={m['focusableCount']}, "
              f"aria-modal={m.get('ariaModal', 'N/A')}")
    
    return modals
```

---

## 实战：无障碍报告生成器

### 综合测试工具

```python
class A11yTestSuite:
    """无障碍测试套件"""
    
    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self.auditor = AccessibilityAuditor(ws, session_id)
        self.results = {}
    
    async def test_page(self, url):
        """测试单个页面的无障碍状况"""
        print(f"\n{'='*60}")
        print(f"测试页面: {url}")
        print(f"{'='*60}")
        
        # 导航
        await cdp(self.ws, "Page.navigate", {"url": url}, self.session_id)
        await cdp(self.ws, "Page.loadEventFired", {}, self.session_id)
        await asyncio.sleep(2)
        
        # 审计
        issues = await self.auditor.run_full_audit()
        
        # 焦点顺序
        tab_info = await verify_tab_order(self.ws, self.session_id)
        
        # 结构分析
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
        """测试多个页面"""
        for url in urls:
            await self.test_page(url)
        
        self.summary_report()
        return self.results
    
    def summary_report(self):
        """生成汇总报告"""
        print("\n" + "=" * 70)
        print("             多页面无障碍测试汇总报告")
        print("=" * 70)
        print(f"{'页面':<40} {'结果':<10} {'问题数':<10} {'高危':<10}")
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
        print(f"共测试 {total_pages} 个页面，发现 {total_issues} 个问题"
              f"（{total_high} 个高危）")
        print("=" * 70)
    
    def export_json(self, file_path):
        """导出结果为 JSON"""
        import json as pyjson
        with open(file_path, "w", encoding="utf-8") as f:
            pyjson.dump(self.results, f, ensure_ascii=False, indent=2)
        print(f"报告已导出: {file_path}")


async def example_a11y_test():
    """运行示例无障碍测试"""
    async with websockets.connect(CDP_URL) as ws:
        session_id, _ = await connect_page(ws)
        test_suite = A11yTestSuite(ws, session_id)
        
        urls = [
            "https://example.com",
            "https://example.com/form-page",
        ]
        
        await test_suite.test_multiple(urls)
```

---

## 常见踩坑与最佳实践

### 踩坑 1：Accessibility.enable 的作用

```python
# Accessibility.enable 主要用于接收 AXTreeChange 等事件
# 获取树本身不需要先 enable
await cdp(ws, "Accessibility.enable", {}, session_id)

# 但 getFullAXTree 不依赖 enable
nodes = await cdp(ws, "Accessibility.getFullAXTree", {}, session_id)
```

### 踩坑 2：max_depth 参数

```python
# max_depth = 0 返回完整树（所有层级）
result = await cdp(ws, "Accessibility.getFullAXTree", {"max_depth": 0}, session_id)

# 限制深度可以加快响应（例如只获取前 3 层）
result = await cdp(ws, "Accessibility.getFullAXTree", {"max_depth": 3}, session_id)
```

### 踩坑 3：部分元素可能不在无障碍树中

```python
# 某些元素（如纯装饰性的 <div>）可能不在无障碍树中
# 这意味着 getFullAXTree 的节点数可能少于 DOM 节点数
# 这是正常行为——浏览器会自动过滤掉无意义元素
```

### 踩坑 4：动态内容需要重置/等待

```python
# 对于 SPA 或动态加载的内容，无障碍树可能不会立即更新
await cdp(ws, "Runtime.evaluate", {
    "expression": "// 触发动态内容加载",
    "sessionId": session_id
}, session_id)
await asyncio.sleep(1)  # 等待无障碍树更新

# 获取更新后的树
nodes = await get_full_axtree(ws, session_id)
```

### 最佳实践清单

| 注意点 | 建议 |
|--------|------|
| 树的范围 | getFullAXTree 用于全面审计，getPartialAXTree 用于定点检查 |
| 动态内容 | 内容变更后等待无障碍树更新 |
| 角色验证 | 检查自定义组件是否使用了正确的 ARIA 角色 |
| 名称计算 | 理解浏览器如何从 aria-label、内容文本等计算可访问名称 |
| 焦点顺序 | tabIndex 应该为 0 或 -1，避免正数 |
| WCAG 参考 | 每个审计规则关联对应的 WCAG 标准 |

---

## 完整参考：CDP 无障碍测试类

```python
import asyncio
import json


class CDPAccessibilityTester:
    """CDP 无障碍测试工具类"""

    def __init__(self, ws, session_id):
        self.ws = ws
        self.session_id = session_id
        self._cmd_id = 0

    async def _cmd(self, method, params=None):
        """发送 CDP 命令"""
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
        """启用无障碍监听"""
        return await self._cmd("Accessibility.enable")

    async def disable(self):
        """禁用无障碍监听"""
        return await self._cmd("Accessibility.disable")

    async def get_full_tree(self, max_depth=0):
        """获取完整无障碍树"""
        return await self._cmd("Accessibility.getFullAXTree", {
            "max_depth": max_depth
        })

    async def get_partial_tree(self, node_id=None, backend_node_id=None,
                                fetch_relatives=True):
        """获取部分无障碍树"""
        params = {"fetchRelatives": fetch_relatives}
        if node_id:
            params["nodeId"] = node_id
        if backend_node_id:
            params["backendNodeId"] = backend_node_id
        return await self._cmd("Accessibility.getPartialAXTree", params)

    async def query_tree(self, **filters):
        """查询无障碍节点"""
        params = {"fetchRelatives": True, **filters}
        return await self._cmd("Accessibility.queryAXTree", params)

    def extract_node_info(self, node):
        """提取 AXNode 的关键信息"""
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
        """展平无障碍树"""
        return [self.extract_node_info(n) for n in nodes]

    async def audit(self):
        """运行基本无障碍审计"""
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

**使用示例：**

```python
async with websockets.connect(CDP_URL) as ws:
    session_id, _ = await connect_page(ws)
    tester = CDPAccessibilityTester(ws, session_id)

    # 导航到目标页面
    await cdp(ws, "Page.navigate", {"url": "https://example.com"}, session_id)
    await cdp(ws, "Page.loadEventFired", {}, session_id)
    await asyncio.sleep(2)

    # 运行审计
    summary = await tester.audit()
    print(f"节点总数: {summary['total_nodes']}")
    print(f"发现问题: {summary['total_issues']} "
          f"(高危: {summary['high_priority']}, "
          f"中危: {summary['medium_priority']})")

    for issue in summary["issues"]:
        print(f"  [{issue['severity'].upper()}] {issue['message']}")

    # 查询特定元素
    buttons = await tester.query_tree(role="button")
    print(f"\n按钮数量: {len(buttons.get('nodes', []))}")

    # 导出完整树
    tree = await tester.get_full_tree()
    flat = tester.flatten_tree(tree.get("nodes", []))
```

---

> **总结**：CDP 的 `Accessibility` 域提供浏览器原生的无障碍树访问能力，比传统的 DOM 分析更准确——因为无障碍树包含了浏览器经过语义计算后的最终可访问性信息。结合 `getFullAXTree`、`queryAXTree` 等方法和自定义审计规则，你可以构建强大的自动化无障碍测试管线，在开发流程中早期发现问题。

---

*上一篇回顾：CDP 性能观察者指南：用 Python 监控 Core Web Vitals。*

*下一篇预告：CDP 媒体与 WebRTC 调试：用 Python 控制音视频。*