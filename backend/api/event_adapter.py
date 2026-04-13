"""agno 原始事件 → 前端 SSE 事件适配器。

依据 docs/frontend-backend-integration-analysis.md 第 2 节的映射规则实现。

每次 yield 一个 (SSE字符串, MessageAggregate) 元组，调用方可实时读到最新聚合状态。

M2 范围：thinking / text / done / error
M3 范围：step_start / sub_step / step_end（已实现，与 M2 共存）
M4 补充：render
"""

from __future__ import annotations

import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

from loguru import logger

from api.sse import format_sse


# 图片持久化目录 — 与 api/routes/images.py 的 _IMAGES_DIR 指向同一处
# 事件适配层拷贝 skill 产物到这里，images 路由按 imageId 直接 FileResponse
_IMAGES_DIR = Path(__file__).resolve().parents[1] / "data" / "images"


# ─── 聚合对象 ─────────────────────────────────────────────────────────────────

@dataclass
class StepAggregate:
    step_id: str
    title: str
    sub_steps: list = field(default_factory=list)


@dataclass
class InsightAccumulator:
    """在 insight step 内累积图表和报告，step_end 时一次性发 render。"""
    charts: list = field(default_factory=list)   # List[ChartItem dict]
    markdown_report: str = ""


@dataclass
class MessageAggregate:
    message_id: str
    conversation_id: str
    content: str = ""
    thinking_content: str = ""
    thinking_duration_sec: int = 0
    steps: list[StepAggregate] = field(default_factory=list)
    render_blocks: list = field(default_factory=list)
    status: str = "streaming"
    error_message: str = ""


# ─── 事件判断工具 ─────────────────────────────────────────────────────────────

def _is_leader(event: Any) -> bool:
    raw = getattr(event, "event", "") or ""
    return raw.startswith("Team")


def _event_type(event: Any) -> str:
    raw = getattr(event, "event", "") or ""
    return raw[4:] if raw.startswith("Team") else raw


def _tool_name(event: Any) -> str:
    tool = getattr(event, "tool", None)
    if tool is None:
        return ""
    return getattr(tool, "tool_name", "") or getattr(tool, "function_name", "") or ""


def _tool_args(event: Any) -> dict:
    tool = getattr(event, "tool", None)
    if tool is None:
        return {}
    return getattr(tool, "tool_args", {}) or {}


# ─── SubAgent 中文名映射 ───────────────────────────────────────────────────────

_MEMBER_DISPLAY_NAMES: dict[str, str] = {
    "planning": "PlanningAgent",
    "insight": "InsightAgent",
    "provisioning-wifi": "ProvisioningAgent (WIFI 仿真)",
    "provisioning-delivery": "ProvisioningAgent (差异化承载)",
    "provisioning-cei-chain": "ProvisioningAgent (体验保障链)",
}


# ─── 核心适配器 ───────────────────────────────────────────────────────────────

async def adapt(
    conv_id: str,
    raw_stream: AsyncGenerator[Any, None],
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """消费 agno 原始事件流，yield (SSE字符串, 当前聚合状态) 元组。

    外层壳：负责创建 MessageAggregate 并注入 msg_id 日志上下文；
    主循环委派给 `_adapt_body`，便于用 `with contextualize` 正确包裹。
    """
    agg = MessageAggregate(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
    )
    api_log = logger.bind(channel="api")
    with logger.contextualize(msg_id=agg.message_id):
        api_log.info(f"adapt() 启动 msg_id={agg.message_id}")
        try:
            async for item in _adapt_body(conv_id, raw_stream, agg):
                yield item
        finally:
            api_log.info(
                f"adapt() 结束 status={agg.status} "
                f"content_len={len(agg.content)} thinking_len={len(agg.thinking_content)} "
                f"steps={len(agg.steps)} renders={len(agg.render_blocks)}"
            )


async def _adapt_body(
    conv_id: str,
    raw_stream: AsyncGenerator[Any, None],
    agg: MessageAggregate,
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """adapt() 的原始主循环。所有 yield 的 SSE 事件由 format_sse 写 sse.log。"""

    thinking_start: Optional[float] = None
    thinking_end: Optional[float] = None
    skill_start_times: dict[str, list] = {}
    skill_start_args: dict[str, list] = {}   # key -> [call_args, ...]
    active_step: Optional[StepAggregate] = None
    insight_acc: Optional[InsightAccumulator] = None  # 仅 insight step 期间非 None

    try:
        async for event in raw_stream:
            leader = _is_leader(event)
            etype = _event_type(event)
            tname = _tool_name(event)

            # ── thinking ──────────────────────────────────────────────────
            if etype == "ReasoningContentDelta":
                delta = getattr(event, "reasoning_content", "") or ""
                if delta:
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    thinking_end = time.monotonic()
                    agg.thinking_content += delta
                    payload: dict = {"delta": delta}
                    if active_step:
                        payload["stepId"] = active_step.step_id
                    yield format_sse("thinking", payload), agg
                continue

            if etype == "RunContent":
                r_delta = getattr(event, "reasoning_content", None)
                if r_delta:
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    thinking_end = time.monotonic()
                    agg.thinking_content += r_delta
                    payload = {"delta": r_delta}
                    if active_step:
                        payload["stepId"] = active_step.step_id
                    yield format_sse("thinking", payload), agg

            # ── text（仅 leader）─────────────────────────────────────────
            if etype == "RunContent" and leader:
                c_delta = getattr(event, "content", None)
                if c_delta:
                    agg.content += str(c_delta)
                    yield format_sse("text", {"delta": str(c_delta)}), agg
                continue

            # ── step_start ────────────────────────────────────────────────
            if etype == "ToolCallStarted" and leader and tname == "delegate_task_to_member":
                args = _tool_args(event)
                member_id = args.get("member_id", "")
                if member_id not in _MEMBER_DISPLAY_NAMES:
                    continue
                title = _MEMBER_DISPLAY_NAMES[member_id]
                active_step = StepAggregate(step_id=member_id, title=title)
                agg.steps.append(active_step)
                # insight step 开始时初始化累积器
                if member_id == "insight":
                    insight_acc = InsightAccumulator()
                yield format_sse("step_start", {"stepId": member_id, "title": title}), agg
                continue

            # ── sub_step 计时开始 ─────────────────────────────────────────
            if etype == "ToolCallStarted" and not leader and tname == "get_skill_script":
                args = _tool_args(event)
                skill_name = args.get("skill_name", "unknown")
                agent_id = getattr(event, "agent_id", "") or ""
                key = f"{agent_id}:{skill_name}"
                skill_start_times.setdefault(key, [])
                skill_start_times[key].append(time.monotonic())
                # 缓存调用参数，供 ToolCallCompleted 时发给前端
                skill_start_args.setdefault(key, [])
                skill_start_args[key].append({
                    "scriptPath": args.get("script_path", ""),
                    "callArgs": args.get("args", []),
                })
                continue

            # ── sub_step 完成 ─────────────────────────────────────────────
            if etype == "ToolCallCompleted" and not leader and tname == "get_skill_script":
                args = _tool_args(event)
                skill_name = args.get("skill_name", "unknown")
                agent_id = getattr(event, "agent_id", "") or ""
                key = f"{agent_id}:{skill_name}"
                times_list = skill_start_times.get(key, [])
                t0 = times_list.pop(0) if times_list else None
                if not times_list:
                    skill_start_times.pop(key, None)
                duration_ms = int((time.monotonic() - t0) * 1000) if t0 else 0

                # 取出对应的调用参数
                args_list = skill_start_args.get(key, [])
                call_info = args_list.pop(0) if args_list else {}
                if not args_list:
                    skill_start_args.pop(key, None)

                tool = getattr(event, "tool", None)
                result_raw = getattr(tool, "result", None) or ""
                stdout, stderr = _extract_stdout_stderr(result_raw)

                step_id = active_step.step_id if active_step else agent_id
                sub_step_id = f"{step_id}_{skill_name}"
                completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

                sub = {
                    "subStepId": sub_step_id,
                    "name": skill_name,
                    "scriptPath": call_info.get("scriptPath", ""),
                    "callArgs": call_info.get("callArgs", []),
                    "stdout": stdout[:500],
                    "stderr": stderr[:500],
                    "completedAt": completed_at,
                    "durationMs": duration_ms,
                }
                if active_step:
                    active_step.sub_steps.append(sub)

                # M4：insight 场景累积图表/报告
                if insight_acc is not None:
                    _accumulate_insight(insight_acc, skill_name, result_raw, sub_step_id)

                yield format_sse("sub_step", {"stepId": step_id, **sub}), agg

                # wifi_simulation 单独通道：解析 image_paths，拷贝到 data/images/
                # 每张图发一个独立的 renderType="image" 事件（按 docs/sse-interface-spec.md:216）
                if skill_name == "wifi_simulation":
                    for rb in _emit_wifi_image_renders(agg.message_id, result_raw):
                        agg.render_blocks.append(rb)
                        yield format_sse("render", rb), agg

                continue

            # ── step_end ──────────────────────────────────────────────────
            if etype == "ToolCallCompleted" and leader and tname == "delegate_task_to_member":
                args = _tool_args(event)
                member_id = args.get("member_id", "")
                if member_id not in _MEMBER_DISPLAY_NAMES:
                    continue

                # M4：insight step 结束时，若有累积数据则发 render
                if member_id == "insight" and insight_acc is not None:
                    render_data = _build_insight_render(insight_acc)
                    if render_data:
                        rb = {"renderType": "insight", "renderData": render_data}
                        agg.render_blocks.append(rb)
                        yield format_sse("render", rb), agg
                    insight_acc = None

                active_step = None
                yield format_sse("step_end", {"stepId": member_id}), agg
                continue

            # ── done ──────────────────────────────────────────────────────
            if etype == "RunCompleted" and leader:
                if thinking_start and thinking_end:
                    agg.thinking_duration_sec = int(thinking_end - thinking_start)
                agg.status = "done"
                yield format_sse("done", {
                    "messageId": agg.message_id,
                    "thinkingDurationSec": agg.thinking_duration_sec,
                }), agg
                return

            # ── error ─────────────────────────────────────────────────────
            if etype in ("RunError", "Error"):
                # agno RunErrorEvent 的真实错误可能在 additional_data 或 error_type 里
                content = getattr(event, "content", "") or ""
                error_type = getattr(event, "error_type", "") or ""
                additional_data = getattr(event, "additional_data", None)
                msg = content or error_type or (str(additional_data) if additional_data else "") or str(event)
                logger.error(f"Agent RunError: type={error_type} content={content!r} additional_data={additional_data} full={event}")
                agg.status = "error"
                agg.error_message = msg
                yield format_sse("error", {"message": msg}), agg
                return

    except Exception as exc:
        logger.exception("event_adapter 异常")
        agg.status = "error"
        agg.error_message = str(exc)
        yield format_sse("error", {"message": f"Agent 执行失败：{exc}"}), agg
        return

    # 兜底 done
    if agg.status == "streaming":
        if thinking_start and thinking_end:
            agg.thinking_duration_sec = int(thinking_end - thinking_start)
        agg.status = "done"
        yield format_sse("done", {
            "messageId": agg.message_id,
            "thinkingDurationSec": agg.thinking_duration_sec,
        }), agg


# ─── 辅助 ────────────────────────────────────────────────────────────────────

def _extract_stdout_stderr(raw: Any) -> tuple[str, str]:
    """从 skill tool result 中分别提取 stdout 和 stderr。"""
    import json as _json
    parsed: dict = {}
    if isinstance(raw, dict):
        parsed = raw
    elif isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
        except Exception:
            return raw, ""
    stdout = str(parsed.get("stdout", "")).strip()
    stderr = str(parsed.get("stderr", "")).strip()
    return stdout, stderr


def _parse_stdout(raw: Any) -> Any:
    """从 tool result 中提取 stdout 并 JSON 解析。"""
    import json as _json
    stdout = ""
    if isinstance(raw, dict):
        stdout = raw.get("stdout", "")
    elif isinstance(raw, str):
        try:
            parsed = _json.loads(raw)
            stdout = parsed.get("stdout", "")
        except Exception:
            stdout = raw
    if not stdout:
        return None
    try:
        return _json.loads(stdout)
    except Exception:
        return stdout  # 返回原始字符串（如 Markdown）


def _accumulate_insight(
    acc: InsightAccumulator,
    skill_name: str,
    result_raw: Any,
    sub_step_id: str,
) -> None:
    """解析 skill stdout，将图表或报告累积到 InsightAccumulator。

    新 InsightAgent 使用的 skill 名：
      - insight_query   → JSON stdout，含 chart_configs（ECharts option）
      - insight_report  → Markdown stdout
    其余 skill（insight_plan / insight_decompose / insight_nl2code / insight_reflect）
    不产出可视化内容，跳过。
    """
    parsed = _parse_stdout(result_raw)
    if parsed is None:
        return

    if skill_name == "insight_query" and isinstance(parsed, dict):
        echarts = parsed.get("chart_configs")
        if not echarts:
            return

        description = parsed.get("description", "")
        significance = parsed.get("significance", 0.0)

        # title 优先取 chart_configs.title.text
        title = ""
        ec_title = echarts.get("title", {})
        if isinstance(ec_title, dict):
            title = ec_title.get("text", "")
        if not title:
            title = str(parsed.get("insight_type", "洞察分析"))

        conclusion = _build_insight_conclusion(description, significance)

        acc.charts.append({
            "chartId": f"{sub_step_id}_{len(acc.charts) + 1}",
            "title": title,
            "conclusion": conclusion,
            "echartsOption": echarts,
        })

    elif skill_name == "insight_report":
        # stdout 是纯 Markdown 文本
        if isinstance(parsed, str):
            acc.markdown_report = parsed
        elif isinstance(parsed, dict):
            acc.markdown_report = str(parsed)


def _build_insight_conclusion(description: Any, significance: float) -> str:
    """从 insight_query 结果生成图表结论文字。"""
    desc_str = ""
    if isinstance(description, str):
        desc_str = description.strip()
    elif isinstance(description, dict):
        desc_str = description.get("summary", str(description))
    sig_text = f"显著性 {significance:.2f}" if significance > 0 else ""
    parts = [p for p in [desc_str, sig_text] if p]
    return "；".join(parts) if parts else "洞察分析完成"


def _build_insight_render(acc: InsightAccumulator) -> dict | None:
    """将 InsightAccumulator 转为 render event 的 renderData。"""
    if not acc.charts and not acc.markdown_report:
        return None
    return {
        "charts": acc.charts,
        "markdownReport": acc.markdown_report,
    }


# ─── wifi_simulation 图片持久化 ───────────────────────────────────────────────

def _emit_wifi_image_renders(msg_id: str, result_raw: Any) -> list[dict]:
    """从 wifi_simulation 的 stdout 解析 image_paths，拷贝到 data/images/ 并
    返回 render_blocks 列表（每张图一个 renderType="image" 条目）。

    命名策略：`{msg_id}_{idx}.{ext}`，便于历史回看按消息 ID 反查 / 清理。

    容错：源文件不存在或拷贝失败时打 warning 跳过，不阻断主流程。
    skill 脚本自己的工作区（skills/wifi_simulation/data/run_<uuid>/）可随时清理，
    本函数拷贝到 `data/images/` 的副本是持久化副本。
    """
    parsed = _parse_stdout(result_raw)
    if not isinstance(parsed, dict):
        return []
    images = parsed.get("image_paths") or []
    if not isinstance(images, list) or not images:
        return []

    api_log = logger.bind(channel="api")
    render_blocks: list[dict] = []

    try:
        _IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    except Exception:
        api_log.exception(f"创建图片持久化目录失败: {_IMAGES_DIR}")
        return []

    for idx, item in enumerate(images):
        if not isinstance(item, dict):
            continue
        src = item.get("path") or ""
        label = item.get("label") or f"图片 {idx + 1}"
        if not src:
            continue

        src_path = Path(src)
        if not src_path.exists():
            api_log.warning(f"wifi image 源文件不存在: {src}")
            continue

        ext = (src_path.suffix.lstrip(".") or "png").lower()
        image_id = f"{msg_id}_{idx}"
        dest = _IMAGES_DIR / f"{image_id}.{ext}"

        try:
            shutil.copy2(src_path, dest)
        except Exception:
            api_log.exception(f"拷贝 wifi image 失败: {src} → {dest}")
            continue

        render_blocks.append({
            "renderType": "image",
            "renderData": {
                "imageId": image_id,
                "imageUrl": f"/api/images/{image_id}",
                "title": label,
                "conclusion": "",
            },
        })
        api_log.info(f"wifi image 持久化 → {dest.name} (label={label!r})")

    return render_blocks
