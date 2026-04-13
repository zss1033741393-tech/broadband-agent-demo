"""SSE 格式编码工具。

符合 EventSource 规范：
    event: <type>
    data: <json>

    (空行分隔)

日志策略：
  所有 SSE 事件经 `format_sse` 出口时，自动写入 `sse.log`（channel="sse"）。
  调用方通过 `logger.contextualize(conv_id=..., msg_id=...)` 注入上下文，
  日志即可关联到具体会话与消息，无需修改 30+ 处 yield 语句。
"""

import json
from typing import Any

from loguru import logger


# 预览长度上限（超长 data 截断，避免 sse.log 爆炸）
_PREVIEW_MAX = 800


def _preview(payload: str) -> str:
    """对超长 payload 做尾部截断，保留头部可读内容。"""
    if len(payload) <= _PREVIEW_MAX:
        return payload
    return payload[:_PREVIEW_MAX] + f"...<truncated {len(payload) - _PREVIEW_MAX} chars>"


def format_sse(event: str, data: Any) -> str:
    """将事件类型和数据编码为 SSE 字符串，并记录到 sse.log。"""
    payload = json.dumps(data, ensure_ascii=False)

    # 高频事件（thinking/text delta）降级到 DEBUG；里程碑事件走 INFO
    milestone = event in {"step_start", "step_end", "sub_step", "render", "done", "error"}
    level = "INFO" if milestone else "DEBUG"
    logger.bind(channel="sse").log(level, f"→ {event} {_preview(payload)}")

    return f"event: {event}\ndata: {payload}\n\n"
