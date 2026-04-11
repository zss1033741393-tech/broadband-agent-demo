"""SSE 格式编码工具。

符合 EventSource 规范：
    event: <type>
    data: <json>

    (空行分隔)
"""

import json
from typing import Any


def format_sse(event: str, data: Any) -> str:
    """将事件类型和数据编码为 SSE 字符串。"""
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"
