"""折叠思考/工具调用的消息渲染逻辑。

将 agno Team 的流式事件映射为 Gradio ChatMessage 格式。
"""

import base64
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

# ─── Agent 中文显示名（用于徽章标题） ───
_AGENT_DISPLAY_NAMES = {
    "home-broadband-team": "Orchestrator",
    "planning": "PlanningAgent",
    "insight": "InsightAgent",
    "provisioning_wifi": "ProvisioningAgent (WIFI 仿真)",
    "provisioning_delivery": "ProvisioningAgent (差异化承载)",
    "provisioning_cei_chain": "ProvisioningAgent (体验保障链)",
}

# InsightAgent 输出协议标记正则 — 仅匹配标记头
_EVENT_MARKER_HEAD_RE = re.compile(r"<!--event:(\w+)-->\s*\n?")


def _display_agent(name: str) -> str:
    return _AGENT_DISPLAY_NAMES.get(name, name)


def render_member_badge(member_name: str) -> Dict[str, Any]:
    """渲染一个 SubAgent 徽章，提示"当前发言者是谁"。"""
    display = _display_agent(member_name)
    return {
        "role": "assistant",
        "metadata": {"title": f"👤 {display}"},
        "content": f"由 **{display}** 接手处理",
    }


def render_thinking(content: str, member: Optional[str] = None) -> Dict[str, Any]:
    """渲染思考过程为折叠块。

    Args:
        content: 思考内容文本
        member: 发言 SubAgent 名字 (如 "provisioning_wifi"), 非空时标题会带上
            中文显示名,便于并行执行时区分不同 member 的思考块。
    """
    title = "💭 思考"
    if member:
        title = f"💭 [{_display_agent(member)}] 思考"
    return {
        "role": "assistant",
        "metadata": {"title": title},
        "content": content,
    }


def render_tool_call(
    skill_name: str,
    inputs: Any = None,
    outputs: Any = None,
    member: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """渲染工具调用事件为一个或两个 Gradio ChatMessage。

    对 Skill 脚本执行结果（outputs 为 dict 且含 `stdout` 键），会**拆成两条**：

    1. **折叠块**（带 ``metadata.title``）：输入参数 / script_path / returncode /
       stderr — 审计信息，默认折叠。
    2. **展开块**（无 ``metadata.title``）：stdout 正文 — 默认可见，用户无需点击；
       Agent 因此可以省去"在 assistant 文本里复述 stdout"的开销，节省 token 并
       避免改写风险。

    其他情况（inputs-only 进行中、outputs 非 Skill 格式）返回单条折叠块。

    Returns:
        List[ChatMessage] — 调用方用 ``history + render_tool_call(...)`` 追加，
        **不要**再用 ``[render_tool_call(...)]`` 二次包裹。
    """
    meta_parts: List[str] = []
    if inputs is not None:
        meta_parts.append(f"**输入参数**:\n```json\n{_format_json(inputs)}\n```")

    stdout_body: Optional[str] = None  # 非空则追加展开块
    stdout_is_markdown = False

    if outputs is not None:
        # agno 在不同版本下可能把 Skill 脚本返回值序列化为 JSON 字符串后
        # 再放入 ToolCallCompleted.tool.result,这里统一先尝试解析成 dict,
        # 避免走到下面的 "返回结果" 兜底分支、丢失 skill 格式拆分能力。
        parsed = outputs
        if isinstance(parsed, str):
            try:
                parsed = json.loads(parsed)
            except (json.JSONDecodeError, TypeError):
                pass  # 非 JSON 字符串,保持原样交给兜底分支展示

        if isinstance(parsed, dict) and "stdout" in parsed:
            script_path = parsed.get("script_path", "")
            returncode = parsed.get("returncode", 0)
            stdout = (parsed.get("stdout") or "").strip()
            stderr = (parsed.get("stderr") or "").strip()
            status = "✅" if returncode == 0 else "❌"
            meta_parts.append(f"{status} `{script_path}` (returncode={returncode})")
            if stderr:
                meta_parts.append(f"**stderr**:\n```\n{stderr}\n```")
            if stdout:
                # 检查 stdout 是否含 image_paths（如 wifi_simulation 产出）
                _stdout_json = None
                try:
                    _stdout_json = json.loads(stdout)
                except (json.JSONDecodeError, TypeError):
                    pass

                if isinstance(_stdout_json, dict) and _stdout_json.get("image_paths"):
                    # 图片模式: 渲染 summary + 步骤状态 + base64 图片
                    _steps_info = []
                    for _st in _stdout_json.get("steps", []):
                        _icon = "✅" if _st.get("status") == "success" else "❌"
                        _st_name = _st.get("name", "")
                        _steps_info.append(f"{_icon} Step {_st.get('step')}: {_st_name}")
                    if _steps_info:
                        meta_parts.append("**执行步骤**:\n" + "\n".join(_steps_info))

                    _summary = _stdout_json.get("summary", "")
                    _image_md = _render_images_base64(_stdout_json["image_paths"])
                    stdout_parts = []
                    if _summary:
                        stdout_parts.append(f"**{_summary}**")
                    if _image_md:
                        stdout_parts.append(_image_md)
                    stdout_body = "\n\n".join(stdout_parts)
                    stdout_is_markdown = True
                else:
                    # 对 JSON stdout 做 unicode 归一化：解析后以 ensure_ascii=False
                    # 重新序列化，将 \uXXXX 转义还原为中文（防御脚本或框架层
                    # 使用 ensure_ascii=True 导致的可读性问题）。
                    if _stdout_json is not None:
                        stdout_body = json.dumps(
                            _stdout_json,
                            ensure_ascii=False,
                            indent=2,
                            default=str,
                        )
                    else:
                        stdout_body = stdout
                    stdout_is_markdown = stdout.startswith("#")
        else:
            meta_parts.append(f"**返回结果**:\n```json\n{_format_json(outputs)}\n```")

    meta_content = "\n\n".join(meta_parts) if meta_parts else "调用中..."

    title_prefix = f"🔧 调用 {skill_name}"
    if member:
        title_prefix = f"🔧 [{_display_agent(member)}] 调用 {skill_name}"

    messages: List[Dict[str, Any]] = [
        {
            "role": "assistant",
            "metadata": {"title": title_prefix},
            "content": meta_content,
        }
    ]

    if stdout_body:
        if stdout_is_markdown:
            body_text = stdout_body
        else:
            body_text = f"```json\n{stdout_body}\n```"

        header = f"**{skill_name} 产出**"
        if member:
            header = f"**[{_display_agent(member)}] {skill_name} 产出**"

        messages.append(
            {
                "role": "assistant",
                "content": f"{header}\n\n{body_text}",
            }
        )

    return messages


def _render_event_plan(data: dict) -> str:
    """将 <!--event:plan--> JSON 渲染为 Markdown 表格。"""
    goal = data.get("goal", "")
    phases = data.get("phases", [])
    if not phases:
        return ""
    rows = ["| 阶段 | 层级 | 目标 | 数据粒度 |", "|------|------|------|----------|"]
    for p in phases:
        pid = p.get("phase_id", "?")
        name = p.get("name", "")
        milestone = p.get("milestone", "")
        table_level = p.get("table_level", "")
        rows.append(f"| **Phase {pid}** | {name} | {milestone} | {table_level} |")
    return f"**📊 分析规划** — {goal}\n\n" + "\n".join(rows)


def _render_event_phase_start(data: dict) -> str:
    """将 <!--event:phase_start--> JSON 渲染为状态行。"""
    pid = data.get("phase_id", "?")
    name = data.get("name", "")
    status = data.get("status", "running")
    icon = "▶️" if status == "running" else "✅"
    return f"{icon} **Phase {pid}**: {name}"


def _render_event_step_result(data: dict) -> str:
    """将 <!--event:step_result--> JSON 渲染为结果摘要。"""
    pid = data.get("phase_id", "?")
    sid = data.get("step_id", "?")
    insight_type = data.get("insight_type", "")
    summary = data.get("summary", "")
    sig = data.get("significance", "")
    sig_str = f" (significance={sig})" if sig else ""
    return f"  📌 P{pid}-S{sid} `{insight_type}`{sig_str}: {summary}"


def _render_event_reflect(data: dict) -> str:
    """将 <!--event:reflect--> JSON 渲染为反思决策。"""
    pid = data.get("phase_id", "?")
    choice = data.get("choice", "?")
    reason = data.get("reason", "")
    return f"  🔄 Phase {pid} 反思: **{choice}** — {reason}"


def _render_event_decompose_result(data: dict) -> str:
    """将 <!--event:decompose_result--> JSON 渲染为步骤分解摘要表。"""
    pid = data.get("phase_id", "?")
    total = data.get("total_steps", 0)
    steps = data.get("steps", [])
    if not steps:
        return f"📋 Phase {pid} 分解完成 ({total} 步)"
    rows = ["| 步骤 | 洞察类型 | 目的 |", "|------|----------|------|"]
    for s in steps:
        sid = s.get("step", "?")
        types = ", ".join(s.get("insight_types", []))
        rationale = s.get("rationale", "")
        rows.append(f"| Step {sid} | `{types}` | {rationale} |")
    return f"📋 **Phase {pid} 分解** ({total} 步)\n\n" + "\n".join(rows)


def _render_event_done(data: dict) -> str:
    total_phases = data.get("total_phases", "?")
    total_steps = data.get("total_steps", "?")
    return f"✅ 洞察分析完成 (共 {total_phases} 阶段, {total_steps} 步)"


# 事件类型 → 渲染函数映射
_EVENT_RENDERERS = {
    "plan": _render_event_plan,
    "decompose_result": _render_event_decompose_result,
    "phase_start": _render_event_phase_start,
    "step_result": _render_event_step_result,
    "reflect": _render_event_reflect,
    "done": _render_event_done,
}


def _parse_member_content(raw: str) -> str:
    """解析 InsightAgent 协议标记，将 <!--event:xxx-->+JSON 替换为结构化 Markdown。

    使用 json.JSONDecoder.raw_decode 精确定位 JSON 边界，
    支持任意深度嵌套的 JSON 对象。普通 Markdown 文本保持原样。

    流式容错：当 content_delta 切断 JSON 导致 raw_decode 失败时，
    保留标记头和残片作为 pending 文本（不丢弃），等下次拼接后重新解析。
    """
    decoder = json.JSONDecoder()
    parts: list[str] = []
    pos = 0

    for m in _EVENT_MARKER_HEAD_RE.finditer(raw):
        # 保留标记之前的普通文本
        before = raw[pos : m.start()]
        if before.strip():
            parts.append(before)

        event_type = m.group(1)
        json_start = m.end()

        # 跳过标记后的空白，找到 JSON 对象起始
        json_scan = json_start
        while json_scan < len(raw) and raw[json_scan] in " \t\n\r":
            json_scan += 1

        rendered = ""
        json_end = json_scan
        if json_scan < len(raw) and raw[json_scan] == "{":
            try:
                data, end_idx = decoder.raw_decode(raw, json_scan)
                json_end = end_idx  # raw_decode 返回的是绝对位置
                renderer = _EVENT_RENDERERS.get(event_type)
                if renderer:
                    rendered = renderer(data)
                else:
                    # 未知事件类型：保留为可读提示而非静默吞没
                    rendered = f"📎 `{event_type}`: {json.dumps(data, ensure_ascii=False)[:200]}"
            except (json.JSONDecodeError, TypeError):
                # 流式 delta 可能切断 JSON — 保留标记头+残片，
                # 等下次 _parse_member_content 被调用时（拼接更多 delta 后）重新解析。
                # 不消费任何内容，pos 保持在标记之前。
                parts.append(raw[m.start() :])
                pos = len(raw)
                break

        if rendered:
            parts.append(rendered)
        pos = json_end

    # 追加剩余文本
    if pos < len(raw):
        tail = raw[pos:]
        if tail.strip():
            parts.append(tail)

    result = "\n\n".join(parts)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def render_member_content(content: str, member: Optional[str] = None) -> Dict[str, Any]:
    """渲染 SubAgent 的文本回复内容。

    自动识别 InsightAgent 的 <!--event:xxx--> 协议标记并结构化渲染。
    普通 Markdown 内容保持原样。

    InsightAgent 的核心内容（plan 表格、phase 进度、step 结果）用户最想直接看到，
    因此 member == "insight" 时**不添加 metadata.title**，内容默认展开。

    Args:
        content: SubAgent 生成的文本内容
        member: SubAgent 名字（如 "insight"），用于标题显示
    """
    # 解析协议标记
    rendered = _parse_member_content(content)
    if not rendered:
        rendered = "(处理中...)"

    # InsightAgent 内容不折叠 — 用户需要直接看到分析进展
    if member == "insight":
        return {
            "role": "assistant",
            "content": rendered,
        }

    title = "📝 SubAgent 回复"
    if member:
        title = f"📝 [{_display_agent(member)}] 回复"

    return {
        "role": "assistant",
        "metadata": {"title": title},
        "content": rendered,
    }


def render_response(content: str) -> Dict[str, Any]:
    """渲染最终回答。"""
    return {
        "role": "assistant",
        "content": content,
    }


def _render_images_base64(image_paths: List[Dict[str, str]]) -> str:
    """将 image_paths 列表中的图片读取后转为 base64 内嵌 Markdown。

    每张图渲染为: **标签** + ``<img>`` base64 标签。
    """
    parts: List[str] = []
    _MIME_MAP = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
    }
    for img_info in image_paths:
        label = img_info.get("label", "")
        path_str = img_info.get("path", "")
        if not path_str:
            continue
        p = Path(path_str)
        if not p.exists():
            parts.append(f"⚠️ 图片未找到: `{path_str}`")
            continue
        try:
            raw = p.read_bytes()
            b64 = base64.b64encode(raw).decode("utf-8")
            mime = _MIME_MAP.get(p.suffix.lower(), "image/png")
            if label:
                parts.append(f"**{label}**")
            parts.append(
                f'<img src="data:{mime};base64,{b64}" '
                f'alt="{label}" style="max-width:100%;border-radius:8px;" />'
            )
        except OSError:
            parts.append(f"⚠️ 读取图片失败: `{path_str}`")
    return "\n\n".join(parts)


def _format_json(data: Any) -> str:
    """将数据格式化为 JSON 字符串。"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except (json.JSONDecodeError, TypeError):
            return str(data)
    try:
        return json.dumps(data, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError):
        return str(data)
