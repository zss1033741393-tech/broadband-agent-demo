"""Gradio Web UI 入口 — 单用户多会话，驱动 agno Team。"""

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional

import gradio as gr
from loguru import logger

# 确保项目根目录在 sys.path
_PROJECT_ROOT = str(Path(__file__).resolve().parents[1])
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from core.observability.db import db
from core.observability.logger import setup_logger
from core.session_manager import session_manager
from ui.chat_renderer import (
    render_member_badge,
    render_member_content,
    render_response,
    render_thinking,
    render_tool_call,
)

# 初始化日志
setup_logger()


# ─── 事件解析工具 ──────────────────────────────────────────────────────
#
# agno 2.5.x Team 在 coordinate 模式下 (stream_member_events=True) 会把多个
# member 的事件通过 asyncio.Queue 随机交错地 merge 到主流 — 同一 member 的
# 连续 ReasoningContentDelta 之间可能被其他 member 的事件插入。
#
# 权威字段 (见 agno/run/agent.py:196-228, agno/run/team.py:190-228):
#   member 事件: agent_id / agent_name (原始事件名无前缀, 如 "ReasoningContentDelta")
#   leader 事件: team_id  / team_name  (原始事件名有前缀, 如 "TeamReasoningContentDelta")
# 注: agent_id / team_id 在 dataclass 里默认是 "" (str, 非 None), 要用 truthiness
# 检查而非 `is not None`。
def _is_team_leader_event(raw_event_type: str) -> bool:
    """原始事件名是否属于 Team leader (以 Team 开头)。"""
    return bool(raw_event_type) and raw_event_type.startswith("Team")


def _normalize_event_type(raw: str) -> str:
    """剥掉 Team 前缀,便于下游统一匹配 (Team 事件与 Agent 事件结构一致)。"""
    if not raw:
        return ""
    if raw.startswith("Team"):
        return raw[len("Team") :]
    return raw


def _extract_source_id(event: Any, is_leader: bool) -> Optional[str]:
    """从事件对象提取发言者的稳定标识。

    Args:
        event: agno 事件对象
        is_leader: 是否是 Team leader 事件 (来自 _is_team_leader_event 的结果)

    Returns:
        - leader 事件: event.team_id 或 team_name
        - member 事件: event.agent_id 或 agent_name
        - 两者都拿不到 → None (该事件无法归属到任何 source)
    """
    if is_leader:
        for attr in ("team_id", "team_name"):
            val = getattr(event, attr, None)
            if val:
                return str(val)
        return None

    for attr in ("agent_id", "agent_name"):
        val = getattr(event, attr, None)
        if val:
            return str(val)
    return None


def _ensure_json_str(data: Any) -> str:
    """将任意数据序列化为 JSON 字符串（ensure_ascii=False）。

    当 data 已是 JSON 字符串时（如 agno get_skill_script 返回值），
    先解析为 dict 再重新序列化，消除内部的 unicode 转义（\\uXXXX → 中文）。
    """
    if not data:
        return ""
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            return json.dumps(parsed, ensure_ascii=False, default=str)
        except (json.JSONDecodeError, TypeError):
            return data
    return json.dumps(data, ensure_ascii=False, default=str)


# agno 框架生命周期事件 — 正常流程的内部状态信号，不记入业务 trace。
# 覆盖 Agent 级和 Team 级（带 Team 前缀），_normalize_event_type 不在此处使用。
_AGNO_LIFECYCLE_EVENTS = frozenset({
    # Agent 级
    "RunStarted", "RunContentCompleted", "RunContinued",
    "ModelRequestStarted", "ModelRequestCompleted",
    "ReasoningStarted", "ReasoningCompleted",
    "MemoryUpdateStarted", "MemoryUpdateCompleted",
    "SessionSummaryStarted", "SessionSummaryCompleted",
    "CompressionStarted", "CompressionCompleted",
    "FollowupsStarted", "FollowupsCompleted",
    # Team 级 (带 Team 前缀)
    "TeamRunStarted", "TeamRunContentCompleted", "TeamRunContinued",
    "TeamModelRequestStarted", "TeamModelRequestCompleted",
    "TeamReasoningStarted", "TeamReasoningCompleted",
    "TeamCompressionStarted", "TeamCompressionCompleted",
    "TeamFollowupsStarted", "TeamFollowupsCompleted",
})


async def chat_handler(
    message: str,
    history: List[Dict[str, Any]],
    session_state: Optional[Dict] = None,
) -> AsyncIterator[List[Dict[str, Any]]]:
    """Gradio chat handler — 异步流式输出 Team 事件。

    核心设计: 单 active reasoning buffer + source 切换时立即 flush。
    - reasoning_buffer 只归属 reasoning_source 一个 source
    - 收到其他 source 的 reasoning delta 时, 先 flush 旧 buffer 为 history 上
      的最终态 thinking 块 (带旧 source 的 display 名), 再为新 source 开 buffer
    - ToolCallStarted / ReasoningCompleted 仅在 source_id == reasoning_source
      时 flush, 防止误伤其他 member 的 in-flight buffer
    """
    if not message or not message.strip():
        yield history
        return

    # 获取或创建会话
    session_hash = (session_state or {}).get("session_hash", str(uuid.uuid4()))
    ctx = session_manager.get_or_create(session_hash)

    # Trace 用户请求
    ctx.tracer.request(message)
    user_msg_id: Optional[int] = None
    if ctx.db_session_id:
        user_msg_id = db.insert_message(ctx.db_session_id, "user", message)

    # 添加用户消息到历史
    history = history + [{"role": "user", "content": message}]
    yield history

    full_content = ""
    reasoning_buffer = ""
    reasoning_source: Optional[str] = None  # 当前 in-flight thinking 归属的 source_id
    current_member: Optional[str] = None  # 最近一次 member 事件的 source_id (非 leader)
    # 本轮已渲染过徽章的 member 集合 — 每个 SubAgent 只展示一次入场标记。
    seen_members: set = set()
    # per-member content 缓冲区 — 用于流式展示 SubAgent 的文本回复
    member_content_buffers: Dict[str, str] = {}
    # tool call 计时器 — ToolCallStarted 时记录，ToolCallCompleted 时计算延迟
    tool_start_times: Dict[str, float] = {}

    def _build_streaming_tail() -> List[Dict[str, Any]]:
        """构造流式 yield 时附加的全部 pending 内容（解决 member 内容闪烁问题）。

        每次 yield 时，除了 history 之外，还要附加所有 pending 的 member buffer
        和 leader content，避免某个 source 的 yield 覆盖其他 source 的内容导致闪烁。
        """
        tail: List[Dict[str, Any]] = []
        for mid, mc in member_content_buffers.items():
            if mc:
                tail.append(render_member_content(mc, member=mid))
        if full_content:
            tail.append(render_response(full_content))
        return tail

    def _agent_id(sid: Optional[str], leader: bool) -> str:
        """从 source_id + is_leader 推导 agent 标识符。"""
        if leader:
            return "orchestrator"
        return sid or "unknown"

    def _flush_reasoning(hist: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """把 reasoning_buffer 固化到 history 末尾, 清空 buffer。"""
        nonlocal reasoning_buffer, reasoning_source
        if reasoning_buffer:
            ctx.tracer.thinking(
                reasoning_buffer,
                agent=_agent_id(reasoning_source, False),
                is_leader=False,
            )
            hist = hist + [render_thinking(reasoning_buffer, member=reasoning_source)]
        reasoning_buffer = ""
        reasoning_source = None
        return hist

    try:
        response_stream = ctx.team.arun(
            message,
            session_id=session_hash,
            stream=True,
            stream_events=True,
        )

        async for event in response_stream:
            raw_event_type = getattr(event, "event", "")
            event_type = _normalize_event_type(raw_event_type)
            is_leader = _is_team_leader_event(raw_event_type)
            source_id = _extract_source_id(event, is_leader)
            agent = _agent_id(source_id, is_leader)

            # ---- Member 徽章(每个 member 一轮只渲染一次) ----
            if source_id and not is_leader:
                current_member = source_id
                if source_id not in seen_members:
                    seen_members.add(source_id)
                    # 出徽章前先把属于旧 source 的 buffer flush 固化,
                    # 保证徽章不会插到旧思考的中间
                    history = _flush_reasoning(history)
                    history = history + [render_member_badge(source_id)]
                    yield history + _build_streaming_tail()

            # ---- 思考/推理 (ReasoningContentDelta 事件) ----
            if event_type == "ReasoningContentDelta":
                delta = getattr(event, "reasoning_content", "") or ""
                if not delta:
                    continue
                # source 切换 → 先固化旧 buffer, 再为新 source 开 buffer
                if source_id and source_id != reasoning_source:
                    history = _flush_reasoning(history)
                    reasoning_source = source_id
                reasoning_buffer += delta
                yield (
                    history
                    + [render_thinking(reasoning_buffer, member=reasoning_source)]
                    + _build_streaming_tail()
                )

            elif event_type == "ReasoningCompleted":
                # 只 flush 匹配 source 的 buffer, 防止误伤其他 member 的 in-flight 思考
                if reasoning_buffer and source_id == reasoning_source:
                    history = _flush_reasoning(history)
                    yield history + _build_streaming_tail()

            # ---- 工具调用开始 ----
            elif event_type == "ToolCallStarted":
                if reasoning_buffer and source_id == reasoning_source:
                    history = _flush_reasoning(history)
                # 工具调用前，将该 member 已积累的文本固化到 history，
                # 实现 "content → tool → content → tool" 的时序交错渲染，
                # 避免所有 member content 堆积到 streaming tail 末尾。
                if source_id and not is_leader and source_id in member_content_buffers:
                    _mc = member_content_buffers.pop(source_id)
                    if _mc:
                        ctx.tracer.member_content(source_id, _mc)
                        history = history + [render_member_content(_mc, member=source_id)]
                        if ctx.db_session_id:
                            db.insert_message(
                                ctx.db_session_id, "assistant", _mc,
                                parent_msg_id=user_msg_id,
                            )
                tool = getattr(event, "tool", None)
                if tool:
                    tool_name = getattr(tool, "tool_name", "") or getattr(
                        tool, "function_name", "unknown"
                    )
                    tool_args = getattr(tool, "tool_args", None) or getattr(
                        tool, "function_args", None
                    )
                    # 记录工具调用开始时间，用于计算延迟
                    _tool_key = f"{source_id or ''}:{tool_name}"
                    tool_start_times[_tool_key] = time.monotonic()
                    ctx.tracer.tool_invoke(tool_name, tool_args, agent=agent, is_leader=is_leader)
                    tool_label_source = source_id if not is_leader else None
                    yield (
                        history
                        + render_tool_call(tool_name, inputs=tool_args, member=tool_label_source)
                        + _build_streaming_tail()
                    )

            # ---- 工具调用完成 ----
            elif event_type == "ToolCallCompleted":
                tool = getattr(event, "tool", None)
                if tool:
                    tool_name = getattr(tool, "tool_name", "") or getattr(
                        tool, "function_name", "unknown"
                    )
                    tool_args = getattr(tool, "tool_args", None) or getattr(
                        tool, "function_args", None
                    )
                    tool_result = getattr(tool, "result", None) or getattr(event, "content", None)
                    # 计算工具调用延迟
                    _tool_key = f"{source_id or ''}:{tool_name}"
                    _start = tool_start_times.pop(_tool_key, None)
                    _latency_ms = int((time.monotonic() - _start) * 1000) if _start else 0
                    ctx.tracer.tool_result(
                        tool_name,
                        tool_result,
                        latency_ms=_latency_ms,
                        agent=agent,
                        is_leader=is_leader,
                    )
                    if ctx.db_session_id:
                        _inputs_str = _ensure_json_str(tool_args)
                        _outputs_str = _ensure_json_str(tool_result)
                        db.insert_tool_call(
                            ctx.db_session_id,
                            skill_name=tool_name,
                            inputs_json=_inputs_str,
                            outputs_json=_outputs_str,
                            latency_ms=_latency_ms,
                            status="ok",
                            message_id=user_msg_id,
                        )
                    # delegate_task_to_member 去重: 如果 member content 已通过
                    # RunContent 展示, 则只显示摘要, 避免重复输出完整内容
                    _is_delegation = tool_name in (
                        "delegate_task_to_member",
                        "adelegate_task_to_member",
                        "delegate_task_to_members",
                    )
                    if _is_delegation:
                        # 从 tool_args 中提取 member_id
                        _member_id = ""
                        if isinstance(tool_args, dict):
                            _member_id = tool_args.get("member_id", "")
                        elif isinstance(tool_args, str):
                            try:
                                _member_id = json.loads(tool_args).get("member_id", "")
                            except (json.JSONDecodeError, TypeError, AttributeError):
                                pass
                        # 如果该 member 已有 content 展示, 仅显示 "委派完成" 摘要
                        if _member_id and _member_id in seen_members:
                            _result_len = len(str(tool_result)) if tool_result else 0
                            history = history + render_tool_call(
                                tool_name,
                                inputs=tool_args,
                                outputs=f"✅ {_member_id} 已完成 (返回 {_result_len} 字符，内容见上方 SubAgent 回复)",
                                member=None,
                            )
                            yield history + _build_streaming_tail()
                            continue
                    tool_label_source = source_id if not is_leader else None
                    history = history + render_tool_call(
                        tool_name,
                        inputs=tool_args,
                        outputs=tool_result,
                        member=tool_label_source,
                    )
                    yield history + _build_streaming_tail()

            # ---- 内容流 (RunContent) ----
            elif event_type == "RunContent":
                reasoning_delta = getattr(event, "reasoning_content", None)
                if reasoning_delta:
                    if source_id and source_id != reasoning_source:
                        history = _flush_reasoning(history)
                        reasoning_source = source_id
                    reasoning_buffer += reasoning_delta
                    yield (
                        history
                        + [render_thinking(reasoning_buffer, member=reasoning_source)]
                        + _build_streaming_tail()
                    )

                content_delta = getattr(event, "content", None)
                if content_delta is not None and reasoning_buffer and source_id == reasoning_source:
                    history = _flush_reasoning(history)

                if content_delta:
                    if is_leader:
                        full_content += str(content_delta)
                    elif source_id:
                        buf = member_content_buffers.get(source_id, "") + str(content_delta)
                        member_content_buffers[source_id] = buf
                    # 统一使用 _build_streaming_tail 渲染所有 pending 内容
                    yield history + _build_streaming_tail()

            # ---- 运行完成 ----
            elif event_type == "RunCompleted":
                if is_leader:
                    final = getattr(event, "content", None)
                    if final and str(final) != full_content:
                        full_content = str(final)
                else:
                    # SubAgent 运行完成 — 将 member content buffer 固化到 history
                    if source_id and source_id in member_content_buffers:
                        mc = member_content_buffers.pop(source_id)
                        if mc:
                            ctx.tracer.member_content(source_id, mc)
                            history = history + [render_member_content(mc, member=source_id)]
                            # 存储 member content 到 DB messages 表
                            if ctx.db_session_id:
                                db.insert_message(
                                    ctx.db_session_id,
                                    "assistant",
                                    mc,
                                    parent_msg_id=user_msg_id,
                                )
                            yield history + _build_streaming_tail()
                    final_content = getattr(event, "content", None)
                    ctx.tracer.member_completed(
                        source_id or "unknown",
                        content=str(final_content) if final_content else "",
                    )

            # ---- 工具/Agent 错误事件 — 向用户可见化 ----
            elif event_type in ("ToolCallError", "ToolCallFailed"):
                tool = getattr(event, "tool", None)
                error_content = getattr(event, "content", "") or getattr(event, "error", "")
                tool_name = getattr(tool, "tool_name", "unknown") if tool else "unknown"
                _error_str = str(error_content)
                # 语义 trace：工具调用错误（JSONL + SQLite traces 表）
                ctx.tracer.tool_result(
                    tool_name,
                    _error_str,
                    agent=agent,
                    is_leader=is_leader,
                )
                # 错误事件也写入 tool_calls 表，status=error（完整存储）
                if ctx.db_session_id:
                    db.insert_tool_call(
                        ctx.db_session_id,
                        skill_name=tool_name,
                        inputs_json="",
                        outputs_json=_error_str,
                        status="error",
                        message_id=user_msg_id,
                    )
                # UI 展示可截取摘要，完整错误已在 DB/trace 中
                _display_error = _error_str[:500] if len(_error_str) > 500 else _error_str
                history = history + [
                    {
                        "role": "assistant",
                        "metadata": {"title": f"⚠️ 工具执行失败: {tool_name}"},
                        "content": _display_error or "未知错误",
                    }
                ]
                yield history + _build_streaming_tail()

            # ---- 未识别事件 — 仅记录真正意外的事件类型 ----
            else:
                if raw_event_type and raw_event_type not in _AGNO_LIFECYCLE_EVENTS:
                    ctx.tracer.unhandled_event(
                        raw_event_type, source_id=agent, is_leader=is_leader
                    )
                    logger.debug(
                        f"未处理事件: {raw_event_type} (agent={agent}, leader={is_leader})"
                    )

        # ---- 流结束清理 ----
        # 残留的 reasoning buffer (例如最后一段思考没有 ReasoningCompleted) 也要固化
        if reasoning_buffer:
            history = _flush_reasoning(history)

        # 残留的 member content buffer — 可能 RunCompleted 未触发或缺失
        for mid, mc in member_content_buffers.items():
            if mc:
                ctx.tracer.member_content(mid, mc)
                history = history + [render_member_content(mc, member=mid)]
        member_content_buffers.clear()

        # 最终回答
        if full_content:
            history = history + [render_response(full_content)]
            ctx.tracer.response(full_content)
            if ctx.db_session_id:
                db.insert_message(ctx.db_session_id, "assistant", full_content)

        yield history

    except Exception as e:
        logger.exception("Team 运行异常")
        ctx.tracer.error(str(e))
        error_msg = f"⚠️ 抱歉，处理请求时出现错误：{str(e)}"
        history = history + [render_response(error_msg)]
        yield history


_EXAMPLE_MESSAGES = [
    "直播套餐卖场走播用户，18:00-22:00 保障抖音直播",
    "找出 CEI 分数较低的 PON 口并分析原因",
    "查看当前 WIFI 覆盖",
    "开通抖音应用切片",
    "立即进行网关重启",
    "用户卡顿，请定界",
]

_CSS = """
/* 统一正文字体，避免 CEI 等大写字母被渲染成衬线/花体 */
.gradio-container, .gradio-container * {
    font-family: "PingFang SC", "Microsoft YaHei", "Noto Sans SC",
                 "Helvetica Neue", Arial, sans-serif !important;
}
/* 示例消息按钮样式 */
.example-btn {
    font-size: 0.85em !important;
    padding: 4px 10px !important;
    border-radius: 14px !important;
    border: 1px solid #d0d7de !important;
    background: #f6f8fa !important;
    color: #24292f !important;
    cursor: pointer;
}
.example-btn:hover {
    background: #e9ecef !important;
    border-color: #b0b7c0 !important;
}
"""


async def _streaming_with_reenable(message, history, session_state):
    """包装 chat_handler，在流式结束时同步恢复输入框和按钮。"""
    last_history = history
    async for h in chat_handler(message, history, session_state):
        last_history = h
        yield h, gr.update(), gr.update()  # 流式过程中不改变输入框/按钮状态
    # 流结束后恢复交互
    yield last_history, gr.update(interactive=True), gr.update(interactive=True)


def create_app() -> gr.Blocks:
    """创建 Gradio 应用。"""
    with gr.Blocks(title="家宽网络调优助手") as app:
        gr.Markdown("# 🏠 家宽网络调优智能助手")
        gr.Markdown(
            "Team 架构：Orchestrator 路由 → PlanningAgent / InsightAgent / ProvisioningAgent × 3"
        )

        session_state = gr.State(value={"session_hash": str(uuid.uuid4())})
        pending_msg = gr.State("")

        chatbot = gr.Chatbot(
            height=550,
            buttons=["copy", "copy_all"],
        )

        gr.Markdown("**示例消息（点击发送）：**")
        example_btns: List[gr.Button] = []
        rows = [_EXAMPLE_MESSAGES[:3], _EXAMPLE_MESSAGES[3:]]
        for row_msgs in rows:
            with gr.Row():
                for msg in row_msgs:
                    example_btns.append(gr.Button(msg, elem_classes=["example-btn"], size="sm"))

        with gr.Row():
            msg_input = gr.Textbox(
                placeholder="输入消息，或点击上方示例...",
                show_label=False,
                scale=9,
                container=False,
            )
            send_btn = gr.Button("发送", variant="primary", scale=1)

        with gr.Row():
            clear_btn = gr.Button("🗑️ 清空对话")
            new_session_btn = gr.Button("🔄 新建会话")

        def _capture_msg(msg):
            """暂存消息、立即清空输入框、禁用发送按钮。"""
            return (
                msg,
                gr.update(value="", interactive=False),
                gr.update(interactive=False),
            )

        for btn in example_btns:
            btn.click(
                fn=_capture_msg,
                inputs=[btn],
                outputs=[pending_msg, msg_input, send_btn],
                queue=False,
            ).then(
                fn=_streaming_with_reenable,
                inputs=[pending_msg, chatbot, session_state],
                outputs=[chatbot, msg_input, send_btn],
            )

        send_btn.click(
            fn=_capture_msg,
            inputs=[msg_input],
            outputs=[pending_msg, msg_input, send_btn],
            queue=False,
        ).then(
            fn=_streaming_with_reenable,
            inputs=[pending_msg, chatbot, session_state],
            outputs=[chatbot, msg_input, send_btn],
        )

        msg_input.submit(
            fn=_capture_msg,
            inputs=[msg_input],
            outputs=[pending_msg, msg_input, send_btn],
            queue=False,
        ).then(
            fn=_streaming_with_reenable,
            inputs=[pending_msg, chatbot, session_state],
            outputs=[chatbot, msg_input, send_btn],
        )

        clear_btn.click(lambda: [], outputs=[chatbot])

        def new_session():
            new_hash = str(uuid.uuid4())
            return [], {"session_hash": new_hash}

        new_session_btn.click(fn=new_session, outputs=[chatbot, session_state])

        # Session 生命周期关闭 — 页面卸载时销毁所有非活跃会话。
        # Gradio 6.x unload() 不再支持 inputs 参数，无法从 State 中取具体的
        # session_hash；退而求其次，在此仅做日志记录，实际 ended_at 写入依赖
        # new_session_btn 点击时对旧会话的显式 destroy 调用。
        def _on_unload():
            logger.info("页面卸载 (Gradio 6.x: unload 无 State 输入，session cleanup 靠 GC)")

        app.unload(_on_unload)

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=True,
        theme=gr.themes.Soft(),
        css=_CSS,
    )
