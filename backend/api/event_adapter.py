"""agno 原始事件 → 前端 SSE 事件适配器。

依据 docs/frontend-backend-integration-analysis.md 第 2 节的映射规则实现。

每次 yield 一个 (SSE字符串, MessageAggregate) 元组，调用方可实时读到最新聚合状态。

M2 范围：thinking / text / done / error
M3 范围：step_start / sub_step / step_end（已实现，与 M2 共存）
M4 补充：render（含 insight / image 两类）
M5 说明：InsightAgent assistant 文本中的 <!--event:xxx--> 阶段标记
         由后端原样透传为 `thinking(stepId="insight")` 事件，
         不在后端做结构化解析——前端自行识别 marker。
         图表/报告仍由脚本 stdout 生成独立 `render` 事件（渐进式）。
"""

from __future__ import annotations

import json as _json
import shutil
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any, AsyncGenerator, Optional

from loguru import logger

from api.sse import format_sse

if TYPE_CHECKING:
    from core.observability.tracer import Tracer

# 图片持久化目录 — 与 api/routes/images.py 的 _IMAGES_DIR 指向同一处
# 事件适配层拷贝 skill 产物到这里，images 路由按 imageId 直接 FileResponse
_IMAGES_DIR = Path(__file__).resolve().parents[1] / "data" / "images"


# ─── 聚合对象 ─────────────────────────────────────────────────────────────────

@dataclass
class StepAggregate:
    step_id: str
    title: str
    # 有序渲染块：thinking / sub_step / text，流式过程中实时 append，落库后原样返回给前端。
    # 前端 rebuildBlocks 直接用这个数组，无需从 subSteps 重建，历史回放与流式展示完全一致。
    items: list = field(default_factory=list)
    # subSteps 保留用于向后兼容（旧前端降级渲染 / 前端计数显示）
    sub_steps: list = field(default_factory=list)
    # SubAgent 本身输出的 assistant content（如 InsightAgent 的阶段 marker 文本）
    text_content: str = ""
    # ToolCallStarted 前积累的 text 缓冲（InsightAgent 在 Skill 调用间输出中间文本）
    # 与 pending_thinking 同步 flush 进 items，保证 text→thinking→sub_step 顺序
    pending_text: str = ""
    # 当前 subStep 启动前积累的 thinking 缓冲；ToolCallStarted 时 flush 进 items，然后重置
    pending_thinking: str = ""


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
#
# member_id 归一化：configs/agents.yaml 里 agent key 已统一为 kebab-case（provisioning-wifi），
# 但 agno 不同版本 delegate_task_to_member / event.agent_id 可能带下划线回退写法。
# adapter 统一把潜在的下划线形式改为短横线，下游 SSE stepId 对齐 docs/sse-interface-spec.md
# 的 kebab-case 规范。

_MEMBER_DISPLAY_NAMES: dict[str, str] = {
    "planning": "PlanningAgent",
    "insight": "InsightAgent",
    "provisioning-wifi": "ProvisioningAgent (WIFI 仿真)",
    "provisioning-delivery": "ProvisioningAgent (差异化承载)",
    "provisioning-cei-chain": "ProvisioningAgent (体验保障链)",
}


def _canonical_member_id(raw: Optional[str]) -> str:
    """把 agno 原始 member_id / agent_id 归一化为 SSE 协议里的 kebab-case。"""
    if not raw:
        return ""
    return str(raw).replace("_", "-")


# ─── 核心适配器 ───────────────────────────────────────────────────────────────

async def adapt(
    conv_id: str,
    raw_stream: AsyncGenerator[Any, None],
    tracer: Optional["Tracer"] = None,
    db_session_id: Optional[int] = None,
    user_msg_id: Optional[int] = None,
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """消费 agno 原始事件流，yield (SSE字符串, 当前聚合状态) 元组。

    外层壳：负责创建 MessageAggregate 并注入 msg_id 日志上下文；
    主循环委派给 `_adapt_body`，便于用 `with contextualize` 正确包裹。

    Args:
        conv_id: 业务会话 ID
        raw_stream: agno team.arun 原始事件流
        tracer: observability Tracer（缺省时不写 trace，向下兼容旧调用）
        db_session_id: observability DB sessions 表的主键，用于关联 messages/tool_calls
        user_msg_id: observability DB messages 表的 user 消息主键，用于关联 tool_calls
    """
    agg = MessageAggregate(
        message_id=str(uuid.uuid4()),
        conversation_id=conv_id,
    )
    # logger.bind() 替代 logger.contextualize()，规避 Windows asyncio GeneratorExit
    # 在不同 Task Context 触发时 ContextVar.reset() 抛 ValueError 的问题。
    api_log = logger.bind(channel="api", msg_id=agg.message_id)
    api_log.info(f"adapt() 启动 msg_id={agg.message_id}")
    try:
        async for item in _adapt_body(
            conv_id, raw_stream, agg, tracer, db_session_id, user_msg_id
        ):
            yield item
    finally:
        api_log.info(
            f"adapt() 结束 status={agg.status} "
            f"content_len={len(agg.content)} thinking_len={len(agg.thinking_content)} "
            f"steps={len(agg.steps)} renders={len(agg.render_blocks)}"
        )


def _source_id(event: Any, leader: bool) -> Optional[str]:
    """从 agno 事件提取发言者标识。leader 用 team_id/team_name；member 用 agent_id/agent_name。"""
    if leader:
        for attr in ("team_id", "team_name"):
            v = getattr(event, attr, None)
            if v:
                return str(v)
        return None
    for attr in ("agent_id", "agent_name"):
        v = getattr(event, attr, None)
        if v:
            return str(v)
    return None


def _ensure_json_str(data: Any) -> str:
    """序列化为 JSON 字符串（ensure_ascii=False），用于 sessions.db.tool_calls 落盘。"""
    if not data:
        return ""
    if isinstance(data, str):
        try:
            parsed = _json.loads(data)
            return _json.dumps(parsed, ensure_ascii=False, default=str)
        except (_json.JSONDecodeError, TypeError):
            return data
    return _json.dumps(data, ensure_ascii=False, default=str)


async def _adapt_body(
    conv_id: str,
    raw_stream: AsyncGenerator[Any, None],
    agg: MessageAggregate,
    tracer: Optional["Tracer"] = None,
    db_session_id: Optional[int] = None,
    user_msg_id: Optional[int] = None,
) -> AsyncGenerator[tuple[str, MessageAggregate], None]:
    """adapt() 的原始主循环。所有 yield 的 SSE 事件由 format_sse 写 sse.log。

    `tracer` / `db_session_id` / `user_msg_id` 用于把事件流同步落到
    `data/sessions.db` 的 traces / tool_calls / messages 表（与 Gradio 路径一致）；
    任何 trace 调用失败都已被 Tracer/db 内部 try/except 吞掉，不影响 SSE 主流程。
    """

    thinking_start: Optional[float] = None
    thinking_end: Optional[float] = None
    skill_start_times: dict[str, list] = {}
    skill_start_args: dict[str, list] = {}   # key -> [call_args, ...]

    # ── step 路由注册表 ─────────────────────────────────────────────────────
    # agno Team coordinate 模式下，Orchestrator 可能连发多个 delegate_task_to_member
    # 的 ToolCallStarted 事件，之后 member 事件交织到达。单变量 active_step 会
    # 被覆盖，导致 member 事件归属错位（全部被挂到最后一个 step）。
    # 改用 agent_id → StepAggregate 注册表，每个 member 事件用它自己的 agent_id
    # 查对应 step，事件顺序无关。
    steps_by_id: dict[str, StepAggregate] = {}

    def _step_for_event(event: Any, leader: bool) -> Optional[StepAggregate]:
        """根据事件的 agent 标识找对应 step；leader 事件返回 None（归属顶层）。

        agno Agent(name=...) 只设 name，agent_id 由 agno 默认给 UUID。
        不同事件类型对 event.agent_id / event.agent_name 的赋值并不统一，
        例如 ToolCall 类事件往往带 name，而 ReasoningContentDelta /
        RunContent 可能只带 UUID。此处**同时尝试 name 与 id 两个属性**，
        任意一个归一化后能在 steps_by_id 命中即采用，消除属性不一致导致
        的 stepId 丢失（表现为 3 张卡片里没有 thinking / 过程文字）。
        """
        if leader:
            return None
        for attr in ("agent_name", "agent_id"):
            v = getattr(event, attr, None)
            if not v:
                continue
            step = steps_by_id.get(_canonical_member_id(str(v)))
            if step is not None:
                return step
        return None

    # ── trace 段级化状态 ────────────────────────────────────────────────────
    # thinking 与 member content 都按 token 流式到达；按段（source 切换 / 工具
    # 调用 / 流结束）一次性 flush 到 trace，避免 traces 表被 token 级写满。
    reasoning_buffer = ""
    reasoning_source: Optional[str] = None
    reasoning_is_leader = False
    member_text_buffers: dict[str, str] = {}

    # 延迟导入，保证旧的不带 tracer 的调用（如冒烟测试）不会因 core 依赖失败
    _db = None
    if db_session_id is not None:
        try:
            from core.observability.db import db as _db  # noqa: PLC0415
        except Exception:
            _db = None

    def _flush_reasoning() -> None:
        nonlocal reasoning_buffer, reasoning_source, reasoning_is_leader
        if reasoning_buffer and tracer is not None:
            tracer.thinking(
                reasoning_buffer,
                agent=reasoning_source or "unknown",
                is_leader=reasoning_is_leader,
            )
        reasoning_buffer = ""
        reasoning_source = None
        reasoning_is_leader = False

    def _flush_member_text(member_id: str) -> None:
        text = member_text_buffers.pop(member_id, "")
        if not text or tracer is None:
            return
        tracer.member_content(member_id, text)
        if _db is not None and db_session_id is not None:
            _db.insert_message(
                db_session_id, "assistant", text, parent_msg_id=user_msg_id
            )

    try:
        async for event in raw_stream:
            leader = _is_leader(event)
            etype = _event_type(event)
            tname = _tool_name(event)
            sid = _source_id(event, leader)
            agent_name = "orchestrator" if leader else (sid or "unknown")

            # ── thinking ──────────────────────────────────────────────────
            if etype == "ReasoningContentDelta":
                delta = getattr(event, "reasoning_content", "") or ""
                if delta:
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    thinking_end = time.monotonic()
                    agg.thinking_content += delta
                    step_for_evt = _step_for_event(event, leader)
                    if step_for_evt is not None:
                        step_for_evt.pending_thinking += delta
                        payload: dict = {"delta": delta, "stepId": step_for_evt.step_id}
                    else:
                        payload = {"delta": delta}
                    yield format_sse("thinking", payload), agg
                    # source 切换 → 旧段先 flush 再开新段
                    if sid and sid != reasoning_source:
                        _flush_reasoning()
                        reasoning_source = sid
                        reasoning_is_leader = leader
                    reasoning_buffer += delta
                continue

            if etype == "RunContent":
                r_delta = getattr(event, "reasoning_content", None)
                if r_delta:
                    if thinking_start is None:
                        thinking_start = time.monotonic()
                    thinking_end = time.monotonic()
                    agg.thinking_content += r_delta
                    step_for_evt = _step_for_event(event, leader)
                    if step_for_evt is not None:
                        step_for_evt.pending_thinking += r_delta
                        payload = {"delta": r_delta, "stepId": step_for_evt.step_id}
                    else:
                        payload = {"delta": r_delta}
                    yield format_sse("thinking", payload), agg
                    if sid and sid != reasoning_source:
                        _flush_reasoning()
                        reasoning_source = sid
                        reasoning_is_leader = leader
                    reasoning_buffer += r_delta

            # ── text（仅 leader）─────────────────────────────────────────
            if etype == "RunContent" and leader:
                c_delta = getattr(event, "content", None)
                if c_delta:
                    # leader 文本进入说明思考段已结束，flush 旧 thinking 段
                    if reasoning_buffer:
                        _flush_reasoning()
                    agg.content += str(c_delta)
                    yield format_sse("text", {"delta": str(c_delta)}), agg
                continue

            # ── member content：非 leader member 的最终答复 ──────────────────
            #
            # 方案 C（2026-04 · 统一走 text 通道 + stepId 路由）：
            #   所有非 leader member（insight / planning / 3 × provisioning）的
            #   RunContent.content 都走 `text { delta, stepId }`。前端 text 分支
            #   识别到 payload.stepId 存在时按 stepId 路由到对应 StepCard 的
            #   "答复区"（非折叠），无 stepId 时 fallback 顶层正文（leader 总结）。
            #
            #   - thinking 通道现在只承载真正的"思考" token（ReasoningContentDelta
            #     与 RunContent.reasoning_content），不再被 member 的最终答复污染
            #   - InsightEventParser 仍挂在 text 分支，按 stepId="insight" 激活 +
            #     解析 <!--event:xxx--> marker，保持原行为
            #   - agg.content 只累加 leader content（顶层总结）；member content
            #     累加到 step.text_content（随 step 一起落业务库）+
            #     member_text_buffers（observability 层独立记录）
            if etype == "RunContent" and not leader:
                step_for_evt = _step_for_event(event, leader)
                if step_for_evt is not None:
                    c_delta = getattr(event, "content", None)
                    if c_delta:
                        text_delta = str(c_delta)
                        step_for_evt.text_content += text_delta
                        # pending_text 缓冲：ToolCallStarted 时按位置 flush 进 items
                        step_for_evt.pending_text += text_delta
                        # observability 层独立记录每个 member 的 content
                        member_text_buffers[step_for_evt.step_id] = (
                            member_text_buffers.get(step_for_evt.step_id, "")
                            + text_delta
                        )
                        # 答复进入说明该 member 的思考段已结束，flush 旧 thinking 段
                        if reasoning_buffer and reasoning_source == sid:
                            _flush_reasoning()
                        yield format_sse(
                            "text",
                            {"delta": text_delta, "stepId": step_for_evt.step_id},
                        ), agg
                    continue

            # ── step_start ────────────────────────────────────────────────
            # agno coordinate 模式下，leader 可能连发多个 delegate 的 ToolCallStarted，
            # 每一个单独建 StepAggregate 并注册到 steps_by_id，互不覆盖。
            if etype == "ToolCallStarted" and leader and tname == "delegate_task_to_member":
                args = _tool_args(event)
                canonical = _canonical_member_id(args.get("member_id", ""))
                if canonical not in _MEMBER_DISPLAY_NAMES:
                    continue
                if canonical in steps_by_id:
                    # 同一 member 被重复派发（极少见），沿用已有 step 即可
                    continue
                title = _MEMBER_DISPLAY_NAMES[canonical]
                step = StepAggregate(step_id=canonical, title=title)
                steps_by_id[canonical] = step
                agg.steps.append(step)
                yield format_sse("step_start", {"stepId": canonical, "title": title}), agg
                continue

            # ── sub_step 计时开始 ─────────────────────────────────────────
            if etype == "ToolCallStarted" and not leader and tname == "get_skill_script":
                # 工具调用进入说明 thinking 段结束，flush 段级 trace
                if reasoning_buffer:
                    _flush_reasoning()

                args = _tool_args(event)
                skill_name = args.get("skill_name", "unknown")
                agent_id = getattr(event, "agent_id", "") or ""
                # key 用原始 agent_id，避免不同 member 的相同 skill 互相踩
                key = f"{agent_id}:{skill_name}"
                skill_start_times.setdefault(key, [])
                skill_start_times[key].append(time.monotonic())
                # 缓存调用参数，供 ToolCallCompleted 时发给前端
                skill_start_args.setdefault(key, [])
                skill_start_args[key].append({
                    "scriptPath": args.get("script_path", ""),
                    "callArgs": args.get("args", []),
                })
                # ── UUID 注册：把 agent_id(UUID) → step 映射写入 steps_by_id ──────
                # ReasoningContentDelta 事件只带 agent_id(UUID)，不带 agent_name；
                # 在此首次见到真实 agent_id 时补注册，之后 thinking 事件才能正确归属。
                step_for_evt_start = _step_for_event(event, leader=False)
                if step_for_evt_start is not None and agent_id and agent_id not in steps_by_id:
                    steps_by_id[agent_id] = step_for_evt_start

                # ── flush：先 pending_text，再 pending_thinking，保证顺序 ──────────
                if step_for_evt_start is not None:
                    if step_for_evt_start.pending_text:
                        step_for_evt_start.items.append({
                            "type": "text",
                            "content": step_for_evt_start.pending_text,
                        })
                        step_for_evt_start.pending_text = ""
                    if step_for_evt_start.pending_thinking:
                        step_for_evt_start.items.append({
                            "type": "thinking",
                            "content": step_for_evt_start.pending_thinking,
                            "startedAt": 0,
                            "endedAt": 0,
                        })
                        step_for_evt_start.pending_thinking = ""

                # ── trace: tool_invoke ────────────────────────────────
                if tracer is not None:
                    tracer.tool_invoke(
                        skill_name, args, agent=agent_name, is_leader=False
                    )
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

                # 用 _step_for_event 查对应 step（同时尝试 agent_name / agent_id），
                # fallback 也优先用 agent_name 归一化，避免 agent_id 是 UUID 时跑偏
                step_for_evt = _step_for_event(event, leader=False)
                if step_for_evt is not None:
                    step_id = step_for_evt.step_id
                else:
                    raw_name = getattr(event, "agent_name", None) or agent_id
                    step_id = _canonical_member_id(str(raw_name))
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
                if step_for_evt is not None:
                    step_for_evt.sub_steps.append(sub)
                    # sub_step 块追加到有序 items 数组
                    step_for_evt.items.append({"type": "sub_step", "data": sub})

                yield format_sse("sub_step", {"stepId": step_id, **sub}), agg

                # ── trace: tool_result + sessions.db.tool_calls ──────
                if tracer is not None:
                    tracer.tool_result(
                        skill_name,
                        result_raw,
                        latency_ms=duration_ms,
                        agent=agent_name,
                        is_leader=False,
                    )
                if _db is not None and db_session_id is not None:
                    _db.insert_tool_call(
                        db_session_id,
                        skill_name=skill_name,
                        inputs_json=_ensure_json_str(call_info.get("callArgs", [])),
                        outputs_json=_ensure_json_str(result_raw),
                        latency_ms=duration_ms,
                        status="ok",
                        message_id=user_msg_id,
                    )

                # wifi_simulation 单独通道：解析 image_paths，拷贝到 data/images/
                # 每张图发一个独立的 renderType="image" 事件（按 docs/sse-interface-spec.md:216）
                if skill_name == "wifi_simulation":
                    for rb in _emit_wifi_image_renders(agg.message_id, result_raw):
                        agg.render_blocks.append(rb)
                        yield format_sse("render", rb), agg

                # insight 场景：每次 insight_query / insight_report 完成时，同时
                # 下发 `report` 和 `render` 两条 SSE 事件，payload 完全一致。
                # 职责划分：
                #   - `report` 主通道：前端产品流程渲染用（insight 的 charts + markdown）
                #   - `render` debug 通道：保留旧事件名 + 相同 payload，供前端对比 /
                #     过渡期消费；未来 render 将专供图片类可视化
                # 前端自主选择消费其中一条通道（消费两条会重复渲染）。
                # 持久化只写一份到 render_blocks，避免历史回放出现两倍内容。
                if step_for_evt is not None and step_for_evt.step_id == "insight":
                    for rb in _emit_insight_render(skill_name, result_raw, sub_step_id):
                        agg.render_blocks.append(rb)              # 持久化一次
                        yield format_sse("report", rb), agg       # 主通道
                        yield format_sse("render", rb), agg       # debug 冗余

                continue

            # ── step_end ──────────────────────────────────────────────────
            if etype == "ToolCallCompleted" and leader and tname == "delegate_task_to_member":
                args = _tool_args(event)
                canonical = _canonical_member_id(args.get("member_id", ""))
                if canonical not in _MEMBER_DISPLAY_NAMES:
                    continue

                # 不从 steps_by_id 移除：后续可能还有 trailing 的 member 事件；
                # step_end 只是标记前端 UI 的完成态
                yield format_sse("step_end", {"stepId": canonical}), agg
                continue

            # ── member RunCompleted：flush member text + trace.member_completed ──
            if etype == "RunCompleted" and not leader:
                if reasoning_buffer:
                    _flush_reasoning()
                if sid:
                    _flush_member_text(sid)
                final_content = getattr(event, "content", None)
                if tracer is not None:
                    tracer.member_completed(
                        sid or "unknown",
                        content=str(final_content) if final_content else "",
                    )
                continue

            # ── done ──────────────────────────────────────────────────────
            if etype == "RunCompleted" and leader:
                if reasoning_buffer:
                    _flush_reasoning()
                # leader 终结 → trace.response + sessions.db.messages 落 assistant
                if tracer is not None and agg.content:
                    tracer.response(agg.content)
                if _db is not None and db_session_id is not None and agg.content:
                    _db.insert_message(db_session_id, "assistant", agg.content)

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
                if tracer is not None:
                    tracer.error(msg)
                yield format_sse("error", {"message": msg}), agg
                return

    except Exception as exc:
        logger.exception("event_adapter 异常")
        agg.status = "error"
        agg.error_message = str(exc)
        if tracer is not None:
            tracer.error(str(exc))
        yield format_sse("error", {"message": f"Agent 执行失败：{exc}"}), agg
        return
    finally:
        # 兜底 flush：thinking buffer 与所有 member text buffer
        if reasoning_buffer:
            _flush_reasoning()
        for _mid in list(member_text_buffers.keys()):
            _flush_member_text(_mid)

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


def _emit_insight_render(
    skill_name: str,
    result_raw: Any,
    sub_step_id: str,
) -> list[dict]:
    """为 insight step 内某个 skill 调用产出 renderBlock 列表（0 或 1 条）。

    渐进式推送规则（与 docs/sse-interface-spec.md §render 对齐）：
      - insight_query  → 从 stdout.chart_configs 取 ECharts option，包成单图 render
      - insight_report → 从 stdout 取 Markdown，包成仅含 markdownReport 的 render
      - 其它 skill     → 返回空列表
    """
    parsed = _parse_stdout(result_raw)
    if parsed is None:
        return []

    if skill_name == "insight_query" and isinstance(parsed, dict):
        echarts = parsed.get("chart_configs")
        if not echarts:
            return []
        description = parsed.get("description", "")
        significance = parsed.get("significance", 0.0)
        title = ""
        ec_title = echarts.get("title", {}) if isinstance(echarts, dict) else {}
        if isinstance(ec_title, dict):
            title = ec_title.get("text", "")
        if not title:
            title = str(parsed.get("insight_type", "洞察分析"))
        conclusion = _build_insight_conclusion(description, significance)
        chart_item = {
            "chartId": f"{sub_step_id}_{int(time.time() * 1000) % 1000000}",
            "title": title,
            "conclusion": conclusion,
            "echartsOption": echarts,
        }
        # 附带 phase_id / step_id / phase_name / step_name 供前端分组与可读标签
        # 字段全部可选（insight_query 脚本按需透传），前端不消费时无影响
        phase_id = parsed.get("phase_id")
        step_id = parsed.get("step_id")
        phase_name = parsed.get("phase_name")
        step_name = parsed.get("step_name")
        if phase_id is not None:
            chart_item["phaseId"] = phase_id
        if step_id is not None:
            chart_item["stepId"] = step_id
        if phase_name:
            chart_item["phaseName"] = str(phase_name)
        if step_name:
            chart_item["stepName"] = str(step_name)
        return [{
            "renderType": "insight",
            "renderData": {
                "charts": [chart_item],
                "markdownReport": "",
            },
        }]

    if skill_name == "insight_report":
        markdown = parsed if isinstance(parsed, str) else str(parsed)
        if not markdown.strip():
            return []
        return [{
            "renderType": "insight",
            "renderData": {
                "charts": [],
                "markdownReport": markdown,
            },
        }]

    return []


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
