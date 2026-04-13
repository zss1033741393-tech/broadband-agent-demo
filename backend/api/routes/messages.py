"""GET /api/conversations/:id/messages（历史查询）
POST /api/conversations/:id/messages（SSE 流式响应）
"""

from __future__ import annotations

import time
from typing import AsyncGenerator

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from api.models import (
    ApiResponse,
    MessageListData,
    SendMessageRequest,
    ok,
    err,
)
from api import repository as repo
from api.agent_bridge import get_event_stream
from api.event_adapter import adapt, MessageAggregate

router = APIRouter(prefix="/conversations/{conv_id}/messages", tags=["messages"])

_api_log = logger.bind(channel="api")


@router.get("", response_model=ApiResponse)
async def list_messages(conv_id: str):
    conv = await repo.get_conversation(conv_id)
    if conv is None:
        _api_log.warning(f"list_messages: 会话不存在 conv_id={conv_id}")
        return err(1002, "会话不存在")
    msgs = await repo.list_messages(conv_id)
    _api_log.bind(conv_id=conv_id).info(f"list_messages → {len(msgs)} 条")
    return ok(MessageListData(list=msgs))


@router.post("")
async def send_message(conv_id: str, body: SendMessageRequest):
    conv = await repo.get_conversation(conv_id)
    if conv is None:
        _api_log.warning(f"send_message: 会话不存在 conv_id={conv_id}")
        raise HTTPException(status_code=404, detail="会话不存在")

    # 先落库用户消息
    await repo.insert_user_message(conv_id, body.content)
    _api_log.bind(conv_id=conv_id).info(
        f"send_message ← user_content_len={len(body.content)} preview={body.content[:80]!r}"
    )

    # 启动 agno 流
    raw_stream = await get_event_stream(conv_id, body.content)

    # 包装成 SSE 生成器，完成后落库 assistant 消息
    async def sse_generator() -> AsyncGenerator[str, None]:
        agg: MessageAggregate | None = None
        adapter = adapt(conv_id, raw_stream)
        started_at = time.monotonic()
        chunk_count = 0
        # conv_id 上下文贯穿整个 SSE 流（event_adapter 内再叠加 msg_id）
        with logger.contextualize(conv_id=conv_id):
            try:
                async for chunk, current_agg in adapter:
                    agg = current_agg
                    chunk_count += 1
                    yield chunk
            except Exception as exc:
                _api_log.exception("SSE 生成异常")
                from api.sse import format_sse
                yield format_sse("error", {"message": f"服务器内部错误：{exc}"})

            elapsed_ms = int((time.monotonic() - started_at) * 1000)
            msg_id = agg.message_id if agg else "-"
            status = agg.status if agg else "unknown"
            _api_log.bind(conv_id=conv_id, msg_id=msg_id).info(
                f"send_message → SSE 流结束 chunks={chunk_count} "
                f"elapsed_ms={elapsed_ms} status={status}"
            )

            # 落库 assistant 消息
            if agg is not None:
                try:
                    steps_data = [
                        {
                            "stepId": s.step_id,
                            "title": s.title,
                            "subSteps": s.sub_steps,
                        }
                        for s in agg.steps
                    ]
                    await repo.insert_assistant_message(
                        conv_id=conv_id,
                        content=agg.content,
                        thinking_content=agg.thinking_content,
                        thinking_duration_sec=agg.thinking_duration_sec,
                        steps=steps_data,
                        render_blocks=agg.render_blocks,
                        status=agg.status,
                    )
                    _api_log.bind(conv_id=conv_id, msg_id=agg.message_id).info(
                        f"assistant 消息已落库 content_len={len(agg.content)} steps={len(steps_data)}"
                    )
                except Exception:
                    _api_log.exception("assistant 消息落库失败")

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
