"""agno Team 与 API 层之间的唯一接缝。

仅此文件依赖 core/，其余 api/ 模块通过此文件间接使用 agno。
若后端团队修改 core/ 接口，只需改这一个文件。
"""

from __future__ import annotations

from typing import Any, AsyncGenerator

from core.session_manager import SessionContext, SessionManager

# API 层独立的 SessionManager 实例，与 Gradio 的全局单例隔离
_api_session_manager = SessionManager()


def get_session_context(conv_id: str) -> SessionContext:
    """获取或创建该会话的 SessionContext（含 team / tracer / db_session_id）。

    暴露给 api 层：让 messages 路由能拿到 tracer 与 observability DB session_id，
    把 FastAPI 路径接入与 Gradio 路径一致的 trace 通道。
    """
    return _api_session_manager.get_or_create(conv_id)


async def get_event_stream(
    conv_id: str, message: str
) -> AsyncGenerator[Any, None]:
    """获取指定会话的 agno 原始事件流。

    Args:
        conv_id: 会话 ID，用作 agno session_id
        message: 用户消息

    Returns:
        agno 原始事件的异步生成器
    """
    ctx = _api_session_manager.get_or_create(conv_id)
    return ctx.team.arun(
        message,
        session_id=conv_id,
        stream=True,
        stream_events=True,
    )
