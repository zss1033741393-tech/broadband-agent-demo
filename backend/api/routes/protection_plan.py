"""保障方案 REST API。

提供当前保障方案的读取接口，供前端展示「当天该用户的保障方案」卡片。
方案写入由 plan_store Skill 脚本在 Agent 流程中完成，不走 HTTP 接口。
"""

from __future__ import annotations

import re
from typing import List, Union

from fastapi import APIRouter
from loguru import logger

from api import repository as repo
from api.models import (
    ApiResponse,
    ProtectionPlanData,
    ProtectionPlanGroup,
    ProtectionPlanItem,
    ok,
)

router = APIRouter(prefix="/protection-plan", tags=["protection-plan"])

# ─── 默认方案（DB 无记录时返回，匹配前端原有硬编码值） ───────────────────────

_DEFAULT_GROUPS: List[ProtectionPlanGroup] = [
    ProtectionPlanGroup(title="AP补点推荐", items=[
        ProtectionPlanItem(label="WIFI信号仿真", value=False),
        ProtectionPlanItem(label="应用卡顿仿真", value=False),
        ProtectionPlanItem(label="AP补点推荐", value=False),
    ]),
    ProtectionPlanGroup(title="CEI体验感知", items=[
        ProtectionPlanItem(label="CEI模型", value="普通"),
        ProtectionPlanItem(label="CEI粒度", value="天级"),
        ProtectionPlanItem(label="CEI阈值", value="70分"),
    ]),
    ProtectionPlanGroup(title="故障诊断", items=[
        ProtectionPlanItem(label="诊断场景", value="上网慢 | 无法上网 | 游戏卡顿 | 直播卡顿"),
        ProtectionPlanItem(label="偶发卡顿定界", value=False),
    ]),
    ProtectionPlanGroup(title="远程优化", items=[
        ProtectionPlanItem(label="远程优化触发时间", value="定时"),
        ProtectionPlanItem(label="远程WIFI信道切换", value=True),
        ProtectionPlanItem(label="远程网关重启", value=True),
        ProtectionPlanItem(label="远程WIFI功率调优", value=True),
    ]),
    ProtectionPlanGroup(title="差异化承载", items=[
        ProtectionPlanItem(label="差异化承载", value=False),
    ]),
]

_DEFAULT_PLAN_TEXT = (
    "AP补点推荐：\n"
    "    WIFI信号仿真：False\n"
    "    应用卡顿仿真：False\n"
    "    AP补点推荐：False\n"
    "\n"
    "CEI体验感知：\n"
    "    CEI模型：普通\n"
    "    CEI粒度：天级\n"
    "    CEI阈值：70分\n"
    "\n"
    "故障诊断：\n"
    "    诊断场景：上网慢 | 无法上网 | 游戏卡顿 | 直播卡顿\n"
    "    偶发卡顿定界：False\n"
    "\n"
    "远程优化：\n"
    "    远程优化触发时间：定时\n"
    "    远程WIFI信道切换：True\n"
    "    远程网关重启：True\n"
    "    远程WIFI功率调优：True\n"
    "\n"
    "差异化承载：\n"
    "    差异化承载：False\n"
)


# ─── 方案文本 → 结构化 JSON 解析 ──────────────────────────────────────────────

_TITLE_RE = re.compile(r"^(.+?)\s*[：:]$")
_FIELD_RE = re.compile(r"^\s{4}(.+?)\s*[：:]\s*(.+)$")


def _parse_value(raw: str) -> Union[str, bool]:
    """将字段值字符串转为 bool 或保留为 str。"""
    stripped = raw.strip()
    if stripped == "True":
        return True
    if stripped == "False":
        return False
    return stripped


def parse_plan_text(text: str) -> List[ProtectionPlanGroup]:
    """解析 5 段式方案文本为结构化 Group 列表。"""
    groups: List[ProtectionPlanGroup] = []
    current_title: str | None = None
    current_items: List[ProtectionPlanItem] = []

    for line in text.splitlines():
        if not line.strip() or line.strip().startswith("#"):
            continue
        title_m = _TITLE_RE.match(line)
        if title_m:
            if current_title is not None:
                groups.append(ProtectionPlanGroup(title=current_title, items=current_items))
            current_title = title_m.group(1)
            current_items = []
            continue
        field_m = _FIELD_RE.match(line)
        if field_m and current_title is not None:
            current_items.append(ProtectionPlanItem(
                label=field_m.group(1),
                value=_parse_value(field_m.group(2)),
            ))

    if current_title is not None:
        groups.append(ProtectionPlanGroup(title=current_title, items=current_items))

    return groups


# ─── Routes ───────────────────────────────────────────────────────────────────

@router.get("")
async def get_protection_plan() -> ApiResponse:
    """获取当前保障方案，无记录时返回默认方案。"""
    record = await repo.get_protection_plan()
    if record is None:
        data = ProtectionPlanData(
            groups=_DEFAULT_GROUPS,
            planText=_DEFAULT_PLAN_TEXT,
            updatedAt="",
        )
    else:
        data = ProtectionPlanData(
            groups=parse_plan_text(record["planText"]),
            planText=record["planText"],
            updatedAt=record["updatedAt"],
        )
    return ok(data.model_dump())
