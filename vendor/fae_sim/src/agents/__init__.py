"""体验保障 Agent — 基于 CrewAI 的对话式仿真编排层。

导出:
    - SessionBridge: Streamlit session_state 适配器
    - run_assurance_agent: 对话入口 (懒加载 crewai)
"""

from .session_bridge import SessionBridge, bind_bridge, get_bridge


def run_assurance_agent(query: str, bridge: "SessionBridge") -> str:
    """懒加载入口：避免 crewai 未安装时影响 app.py 导入。"""
    from .assurance_agent import run_assurance_agent as _run
    return _run(query, bridge)


__all__ = ["SessionBridge", "bind_bridge", "get_bridge", "run_assurance_agent"]
