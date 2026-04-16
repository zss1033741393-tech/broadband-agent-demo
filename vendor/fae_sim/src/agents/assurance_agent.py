"""基于 CrewAI 的体验保障 Agent 入口。

懒导入 crewai：模块顶层只引用 tools.py / prompts.py / session_bridge.py；
crewai 相关的 import 全放在 _build_crew() 内部，确保当 crewai 未安装时，
整个 src.agents 包仍可被导入（app.py 只在点击 chat_input 时才触发这里）。

LLM 后端：默认 GLM-5.1（通过 OpenRouter 中转，走 CrewAI 内置的 LiteLLM 通道），
读取 OPENROUTER_API_KEY。支持通过环境变量 FAE_AGENT_MODEL 覆盖模型 slug。
"""

from __future__ import annotations

import io
import os
import sys
import traceback
from typing import Callable

from .prompts import ASSURANCE_AGENT_BACKSTORY, USER_TASK_TEMPLATE
from .session_bridge import SessionBridge, bind_bridge
from . import tools as _tools


DEFAULT_MODEL = os.environ.get("FAE_AGENT_MODEL", "openrouter/z-ai/glm-5.1")
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _wrap_tools(tool_decorator: Callable) -> list:
    """把 tools.py 里的纯函数用 CrewAI 的 @tool 装饰器包装成 BaseTool。"""
    wrapped = []
    for fn in _tools.ALL_TOOLS:
        # 用函数自己的 docstring 作为工具 description，函数名作为工具 name
        wrapped_tool = tool_decorator(fn.__name__)(fn)
        wrapped.append(wrapped_tool)
    return wrapped


def _build_crew():
    """组装 CrewAI Agent + Task + Crew。仅在此处 import crewai。"""
    from crewai import Agent, Task, Crew, Process
    from crewai.tools import tool as crew_tool
    try:
        from crewai import LLM  # CrewAI >= 0.51
    except ImportError:
        from crewai.llm import LLM  # type: ignore

    # OpenRouter 走 OpenAI 兼容接口，LiteLLM 通过 "openrouter/" 前缀识别 provider。
    # 显式传 api_key / base_url 以防某些 LiteLLM 版本不自动读取 OPENROUTER_API_KEY。
    llm_kwargs: dict = {"model": DEFAULT_MODEL, "temperature": 0.2}
    if DEFAULT_MODEL.startswith("openrouter/"):
        llm_kwargs["api_key"] = os.environ.get("OPENROUTER_API_KEY")
        llm_kwargs["base_url"] = OPENROUTER_BASE_URL
    llm = LLM(**llm_kwargs)

    agent_tools = _wrap_tools(crew_tool)

    agent = Agent(
        role="家宽体验保障工程师",
        goal=(
            "基于仿真数据回答用户问题、按指令调整参数/注入故障/应用闭环措施，"
            "并对故障执行自动诊断+修复+效果评估。"
        ),
        backstory=ASSURANCE_AGENT_BACKSTORY,
        tools=agent_tools,
        llm=llm,
        verbose=False,
        allow_delegation=False,
        max_iter=8,
    )
    return Agent, Task, Crew, Process, agent


def run_assurance_agent(query: str, bridge: SessionBridge) -> str:
    """对话入口：执行一次 Agent 调用并返回字符串回复。

    所有异常（缺包 / 缺 key / API 错误 / 工具错误）都被捕获并以友好提示返回，
    避免 Streamlit 页面整体崩溃。
    """
    # 预检：关键环境变量
    if DEFAULT_MODEL.startswith("openrouter/") and not os.environ.get("OPENROUTER_API_KEY"):
        return (
            "⚠️ 未检测到 OPENROUTER_API_KEY 环境变量。\n"
            "请设置后重试：`setx OPENROUTER_API_KEY sk-or-...` (Windows cmd/PowerShell)，"
            "或 `export OPENROUTER_API_KEY=sk-or-...` (bash)，然后**重开终端**再启动 streamlit。"
        )
    if DEFAULT_MODEL.startswith("anthropic/") and not os.environ.get("ANTHROPIC_API_KEY"):
        return (
            "⚠️ 未检测到 ANTHROPIC_API_KEY 环境变量。\n"
            "请设置后重试：`setx ANTHROPIC_API_KEY sk-ant-...` (Windows) "
            "或 `export ANTHROPIC_API_KEY=sk-ant-...` (bash)，然后重启 streamlit。"
        )

    try:
        Agent, Task, Crew, Process, agent = _build_crew()
    except ImportError as e:
        return (
            f"⚠️ 未能加载 CrewAI 相关依赖：{e}\n"
            "请在当前 Python 环境执行：`pip install -e \".[agent]\"`"
        )
    except Exception as e:
        return f"⚠️ 构建 Agent 失败：{type(e).__name__}: {e}"

    task = Task(
        description=USER_TASK_TEMPLATE.format(query=query),
        expected_output=(
            "简洁中文回答。若执行了写操作，必须说明已排队的动作；"
            "若执行了故障修复，必须附带修复前/后核心指标对比。"
        ),
        agent=agent,
    )
    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=True,
    )

    try:
        # 捕获 CrewAI 的 verbose 输出作为"思考过程"
        _captured = io.StringIO()
        _old_stdout = sys.stdout
        sys.stdout = _captured
        try:
            with bind_bridge(bridge):
                result = crew.kickoff()
        finally:
            sys.stdout = _old_stdout
        thinking = _captured.getvalue().strip()
        return _pack_result(str(result), thinking)
    except Exception as e:
        tb = traceback.format_exc(limit=3)
        return f"⚠️ Agent 执行出错：{type(e).__name__}: {e}\n\n```\n{tb}\n```"


# ── 思考过程 / 最终回答打包 ──────────────────────────────────
_SEP = "\n===THINKING_SEP===\n"

def _pack_result(answer: str, thinking: str) -> str:
    """把 answer + thinking 打包成单字符串，app.py 端解包。"""
    return f"{answer}{_SEP}{thinking}" if thinking else answer

def unpack_result(packed: str) -> tuple[str, str]:
    """解包为 (answer, thinking)。"""
    if _SEP in packed:
        parts = packed.split(_SEP, 1)
        return parts[0].strip(), parts[1].strip()
    return packed.strip(), ""
