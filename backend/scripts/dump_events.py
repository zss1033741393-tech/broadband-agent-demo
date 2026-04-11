"""诊断脚本：打印 agno Team 的原始事件流，用于映射 SSE 事件。

用法：
    cd backend
    python scripts/dump_events.py [消息内容]

默认消息："查看当前 WIFI 覆盖"（触发 ProvisioningWifiAgent，事件流相对简单）
"""

import asyncio
import sys
from pathlib import Path

# 确保项目根目录在 sys.path
_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from core.observability.logger import setup_logger
from core.agent_factory import create_team

setup_logger()

_SEP = "─" * 72


def _dump_event(idx: int, event) -> None:
    raw_type = getattr(event, "event", "<no event attr>")
    print(f"\n[{idx:03d}] event={raw_type}")

    # 关键字段逐一打印
    for attr in (
        "team_id", "team_name",
        "agent_id", "agent_name",
        "content", "reasoning_content",
    ):
        val = getattr(event, attr, _MISSING := object())
        if val is not _MISSING and val:
            # 长文本截断
            s = str(val)
            print(f"      {attr}: {s[:120]}{'...' if len(s) > 120 else ''}")

    # tool 字段展开
    tool = getattr(event, "tool", None)
    if tool:
        tool_name = getattr(tool, "tool_name", None) or getattr(tool, "function_name", None)
        tool_args = getattr(tool, "tool_args", None) or getattr(tool, "function_args", None)
        tool_result = getattr(tool, "result", None)
        print(f"      tool.tool_name: {tool_name}")
        if tool_args:
            s = str(tool_args)
            print(f"      tool.tool_args: {s[:200]}{'...' if len(s) > 200 else ''}")
        if tool_result:
            s = str(tool_result)
            print(f"      tool.result: {s[:200]}{'...' if len(s) > 200 else ''}")


async def main():
    message = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else "查看当前 WIFI 覆盖"
    print(_SEP)
    print(f"发送消息: {message}")
    print(_SEP)

    team = create_team(session_id="dump-events-test")

    idx = 0
    async for event in team.arun(
        message,
        stream=True,
        stream_events=True,
    ):
        _dump_event(idx, event)
        idx += 1

    print(f"\n{_SEP}")
    print(f"共收到 {idx} 个事件")
    print(_SEP)


if __name__ == "__main__":
    asyncio.run(main())
