"""SessionBridge — 把 Streamlit st.session_state 暴露给 CrewAI 工具。

设计要点：
    - 工具函数是模块级函数，没有 self，无法直接持有 session。
    - 用 contextvar + contextmanager 在每次 Agent 调用期间绑定一个 bridge，
      工具通过 get_bridge() 取当前上下文的 bridge，获得对 session_state 的访问。
    - 这样 Agent 的写操作只是往 session_state 里追加"待执行动作"(agent_pending_actions)，
      由 Streamlit 主流程在 rerun 后调用现有的 _run_segment() 真正执行，
      避免在 callback 里直接 st.rerun()。
"""

from __future__ import annotations

import contextvars
from contextlib import contextmanager
from typing import Any

_current: contextvars.ContextVar["SessionBridge | None"] = contextvars.ContextVar(
    "assurance_agent_bridge", default=None
)


class SessionBridge:
    """Streamlit 会话适配器，被 Agent 工具用来读写当前仿真状态。"""

    def __init__(self, session_state: Any, engine: Any):
        self.ss = session_state          # st.session_state（或 dict 用于测试）
        self.engine = engine             # SimulationEngine 实例

    # ── 读操作 ──────────────────────────────────────────────────
    def user_params(self) -> dict:
        return dict(self.ss.get("user_params", {}))

    def latest_summary(self):
        summaries = self.ss.get("sim_summaries") or []
        return summaries[-1] if summaries else None

    def latest_timeseries(self):
        """返回全部分段合并后的时序数据（供诊断/体验指数使用）。"""
        segments = self.ss.get("sim_segments") or []
        if not segments:
            return None
        merged: dict = {}
        for ts, _ in segments:
            if ts is None:
                continue
            for key, values in ts.items():
                if key not in merged:
                    merged[key] = list(values)
                else:
                    merged[key].extend(values)
        return merged if merged else None

    def all_summaries(self) -> list:
        return list(self.ss.get("sim_summaries") or [])

    def all_segments(self) -> list:
        return list(self.ss.get("sim_segments") or [])

    # ── 写操作 ──────────────────────────────────────────────────
    def update_user_params(self, updates: dict) -> dict:
        up = dict(self.ss.get("user_params", {}))
        up.update(updates)
        self.ss["user_params"] = up
        return up

    def queue_action(self, action: dict) -> None:
        actions = list(self.ss.get("agent_pending_actions") or [])
        actions.append(action)
        self.ss["agent_pending_actions"] = actions

    def clear_actions(self) -> None:
        self.ss["agent_pending_actions"] = []

    def pending_actions(self) -> list[dict]:
        return list(self.ss.get("agent_pending_actions") or [])


@contextmanager
def bind_bridge(bridge: SessionBridge):
    """在 with 块内把 bridge 绑定到当前 contextvar，工具函数通过 get_bridge() 访问。"""
    token = _current.set(bridge)
    try:
        yield bridge
    finally:
        _current.reset(token)


def get_bridge() -> SessionBridge:
    """在已绑定的 context 中返回当前 bridge；未绑定则抛 RuntimeError。"""
    b = _current.get()
    if b is None:
        raise RuntimeError(
            "SessionBridge 未绑定。请在 bind_bridge(bridge) 上下文中调用工具函数。"
        )
    return b
