"""会话隔离与生命周期管理。

每个 Gradio session_hash → 独立 Team 实例 + Tracer。
Team 由 1 leader (Orchestrator) + 5 member SubAgent 组成。
"""

from dataclasses import dataclass
from typing import Dict, Optional

from agno.team import Team
from loguru import logger

from core.agent_factory import create_team
from core.model_loader import inject_dynamic_seed, inject_prompt_tracer, load_model_config
from core.observability.db import db
from core.observability.tracer import Tracer


@dataclass
class SessionContext:
    """一个会话的完整上下文。"""

    session_hash: str
    team: Team
    tracer: Tracer
    db_session_id: Optional[int] = None
    task_type: Optional[str] = None  # comprehensive / specific / insight


class SessionManager:
    """管理所有活跃会话。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, SessionContext] = {}
        logger.info("SessionManager 初始化完成")

    def get_or_create(self, session_hash: str) -> SessionContext:
        """获取或创建会话上下文。"""
        if session_hash in self._sessions:
            return self._sessions[session_hash]

        # 创建 DB 记录（失败时重试一次，仍失败则回退查询已有记录）
        db_sid = db.create_session(session_hash)
        if db_sid is None:
            logger.warning(f"create_session 首次失败，重试: {session_hash[:8]}...")
            db_sid = db.create_session(session_hash)
        if db_sid is None:
            # 最终兜底：可能 DB 可读但写入异常，尝试查询已有记录
            db_sid = db.get_session_id(session_hash)
            if db_sid:
                logger.info(f"create_session 回退到已有记录: {session_hash[:8]}..., db_sid={db_sid}")
        if db_sid is None:
            logger.error(f"create_session 最终失败: {session_hash[:8]}... — DB traces 将被跳过")

        # 创建 Team (leader + 5 members)
        team = create_team(session_id=session_hash)

        # 创建 Tracer，向 Team leader 与所有 member 的 model 注入 prompt tracer
        tracer = Tracer(session_hash, db_session_id=db_sid)

        # 是否启用动态 seed（由 model.yaml dynamic_seed: true 控制）
        _dynamic_seed_enabled = bool(load_model_config().get("dynamic_seed", False))

        try:
            if getattr(team, "model", None) is not None:
                inject_prompt_tracer(team.model, tracer.llm_prompt, agent_name="orchestrator")
                # seed 注入必须在 tracer 之后：seed_wrapper → tracer_wrapper → class method
                if _dynamic_seed_enabled:
                    inject_dynamic_seed(team.model)
        except Exception:
            logger.warning("inject_prompt_tracer 失败 (team leader)")

        for member in getattr(team, "members", []) or []:
            member_name = getattr(member, "name", "unknown")
            try:
                if getattr(member, "model", None) is not None:
                    inject_prompt_tracer(member.model, tracer.llm_prompt, agent_name=member_name)
                    # seed 注入必须在 tracer 之后
                    if _dynamic_seed_enabled:
                        inject_dynamic_seed(member.model)
            except Exception:
                logger.warning(f"inject_prompt_tracer 失败 (member={member_name})")

        ctx = SessionContext(
            session_hash=session_hash,
            team=team,
            tracer=tracer,
            db_session_id=db_sid,
        )
        self._sessions[session_hash] = ctx
        logger.info(f"会话 {session_hash[:8]}... 创建成功")
        return ctx

    def destroy(self, session_hash: str) -> None:
        """销毁会话并持久化元数据。"""
        ctx = self._sessions.pop(session_hash, None)
        if ctx:
            db.end_session(session_hash, task_type=ctx.task_type or "")
            logger.info(f"会话 {session_hash[:8]}... 销毁")

    def get(self, session_hash: str) -> Optional[SessionContext]:
        return self._sessions.get(session_hash)

    @property
    def active_count(self) -> int:
        return len(self._sessions)


# 全局单例
session_manager = SessionManager()
