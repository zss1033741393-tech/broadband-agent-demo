"""从 YAML 配置构造 agno Team + 5 个 SubAgent 实例。

架构：
    OrchestratorTeam (leader, coordinate 模式)
      ├─ PlanningAgent         (goal_parsing + plan_design + plan_review)
      ├─ InsightAgent          (insight_plan + insight_decompose + insight_query
      │                         + insight_nl2code + insight_reflect + insight_report)
      ├─ ProvisioningWifiAgent (wifi_simulation)
      ├─ ProvisioningDeliveryAgent (differentiated_delivery)
      └─ ProvisioningCeiChainAgent (cei_pipeline + fault_diagnosis + remote_optimization)

3 个 Provisioning 实例共享 provisioning.md prompt，各自挂载不同的 Skills 子集。
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from agno.agent import Agent
from agno.db.sqlite.sqlite import SqliteDb
from agno.skills import Skills
from agno.skills.loaders.local import LocalSkills
from agno.team import Team
from agno.team.team import TeamMode
from loguru import logger

from core.model_loader import create_model

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_AGENTS_CONFIG_PATH = _PROJECT_ROOT / "configs" / "agents.yaml"
_SKILLS_DIR = _PROJECT_ROOT / "skills"


def _load_agents_config(config_path: Path = _AGENTS_CONFIG_PATH) -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    logger.info(
        f"Team 配置加载成功: team={cfg.get('team', {}).get('name')}, "
        f"agents={list((cfg.get('agents') or {}).keys())}"
    )
    return cfg


def _load_prompt(relative_path: str) -> str:
    prompt_path = _PROJECT_ROOT / relative_path
    if prompt_path.exists():
        content = prompt_path.read_text(encoding="utf-8")
        logger.debug(f"Prompt 加载: {prompt_path} ({len(content)} chars)")
        return content
    logger.warning(f"Prompt 文件不存在: {prompt_path}")
    return ""


def _load_all_skills() -> Dict[str, Any]:
    """一次性加载全部 Skill 对象，返回 name → Skill 的映射。"""
    if not _SKILLS_DIR.exists():
        logger.warning(f"Skills 目录不存在: {_SKILLS_DIR}")
        return {}
    try:
        loader = LocalSkills(str(_SKILLS_DIR), validate=False)
        skills_list = loader.load()
        mapping = {s.name: s for s in skills_list}
        logger.info(f"全部 Skills 加载成功: {sorted(mapping.keys())}")
        return mapping
    except Exception:
        logger.exception("Skills 加载失败")
        return {}


def _build_subset_skills(all_skills: Dict[str, Any], names: List[str]) -> Optional[Skills]:
    """按 Skill 名列表构造 Skills 子集实例，供单个 Agent 使用。"""
    if not names:
        return None

    selected = [all_skills[n] for n in names if n in all_skills]
    missing = [n for n in names if n not in all_skills]
    if missing:
        logger.warning(f"以下 Skills 未找到，将被忽略: {missing}")
    if not selected:
        return None

    class _StaticLoader:
        def __init__(self, items):
            self._items = items

        def load(self):
            return self._items

    return Skills(loaders=[_StaticLoader(selected)])


def _append_skills_snippet(prompt: str, skills_obj: Optional[Skills]) -> str:
    """将 Skills 元数据追加到 prompt，使 LLM 能感知可用 Skill。

    原因: agno Agent 以 system_message= 显式传入时，会跳过内部的
    `skills.get_system_prompt_snippet()` 注入，需要手动补注。
    """
    if skills_obj is None or not prompt:
        return prompt
    try:
        snippet = skills_obj.get_system_prompt_snippet()
        if snippet:
            return f"{prompt}\n\n{snippet}"
    except Exception:
        logger.warning("Skills snippet 获取失败，prompt 将不含 Skills 描述")
    return prompt


def _create_shared_db() -> SqliteDb:
    db_path = _PROJECT_ROOT / "data" / "agent_sessions.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return SqliteDb(db_file=str(db_path))


def _build_agent(
    *,
    name: str,
    cfg: Dict[str, Any],
    all_skills: Dict[str, Any],
    shared_db: SqliteDb,
    session_id: Optional[str],
) -> Agent:
    prompt = _load_prompt(cfg.get("prompt", ""))
    skills_obj = _build_subset_skills(all_skills, cfg.get("skills", []) or [])
    system_message = _append_skills_snippet(prompt, skills_obj)

    agent = Agent(
        name=name,
        model=create_model(),
        description=cfg.get("description"),
        system_message=system_message if system_message else None,
        skills=skills_obj,
        session_id=session_id,
        db=shared_db,
        add_history_to_context=True,
        num_history_runs=cfg.get("memory", {}).get("max_turns", 10),
        markdown=True,
    )
    logger.info(
        f"SubAgent 创建: {name}, skills={cfg.get('skills', [])}, "
        f"description={(cfg.get('description') or '')[:40]}..."
    )
    return agent


def create_team(session_id: Optional[str] = None) -> Team:
    """从 configs/agents.yaml 创建一个 agno Team (含 1 leader + 5 member)。

    Args:
        session_id: 会话标识符，作为 agno session_id 用于 memory 隔离

    Returns:
        配置好的 agno Team 实例
    """
    cfg = _load_agents_config()
    team_cfg = cfg.get("team", {}) or {}
    agents_cfg = cfg.get("agents", {}) or {}

    all_skills = _load_all_skills()
    shared_db = _create_shared_db()

    # 构造 5 个 SubAgent (member)
    members: List[Agent] = []
    for name in (
        "planning",
        "insight",
        "provisioning_wifi",
        "provisioning_delivery",
        "provisioning_cei_chain",
    ):
        sub_cfg = agents_cfg.get(name)
        if sub_cfg is None:
            logger.warning(f"agents.yaml 中缺少 {name} 配置，跳过")
            continue
        members.append(
            _build_agent(
                name=name,
                cfg=sub_cfg,
                all_skills=all_skills,
                shared_db=shared_db,
                session_id=session_id,
            )
        )

    # 构造 Team leader (Orchestrator)
    team_prompt = _load_prompt(team_cfg.get("prompt", "prompts/orchestrator.md"))
    mode_value = team_cfg.get("mode", "coordinate")
    try:
        team_mode = TeamMode(mode_value)
    except ValueError:
        logger.warning(f"未知的 team mode={mode_value}, 回退到 coordinate")
        team_mode = TeamMode.coordinate

    team = Team(
        name=team_cfg.get("name", "home-broadband-team"),
        members=members,
        mode=team_mode,
        model=create_model(),
        description=team_cfg.get("description"),
        system_message=team_prompt if team_prompt else None,
        session_id=session_id,
        db=shared_db,
        add_history_to_context=True,
        num_history_runs=team_cfg.get("memory", {}).get("max_turns", 30),
        markdown=True,
        stream_member_events=True,
        store_member_responses=True,
    )

    logger.info(
        f"Team 创建成功: name={team.name}, mode={mode_value}, "
        f"members={len(members)}, session_id={session_id}"
    )
    return team
