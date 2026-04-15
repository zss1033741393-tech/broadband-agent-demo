"""
三元组修复模块。
执行每个步骤前必须先修复三元组，处理 LLM 生成的常见错误。
"""

import logging
import re
from copy import deepcopy

logger = logging.getLogger(__name__)

# 合法的离散分组字段
VALID_BREAKDOWN_FIELDS = {"portUuid", "date", "time_id", "gatewayMac"}

# 不合法的操作符映射
OPER_FIX_MAP = {
    "EQUALS": "IN",
    "EQUAL": "IN",
    "EQ": "IN",
    "NOT_EQUALS": "NOT_IN",
    "NOT_EQUAL": "NOT_IN",
    "NEQ": "NOT_IN",
}

# 需要移除的聚合后缀（LLM 偶尔会把 aggr 方式拼到字段名末尾）
# ⚠️ 不要盲目剥除——天表有 count_mean/count_max 等真实字段末尾也会匹配到这些后缀
# 统一走 schema 白名单：_strip_aggr_suffix_if_needed 只在"原名不存在且剥后存在"时才剥
_AGGR_SUFFIX_CANDIDATES = re.compile(r"_(avg|sum|count|min|max|mean)$", re.IGNORECASE)
# 留一份仅用于 breakdown 字段（breakdown 字段极少与业务字段重名，可以放心剥）
AGGR_SUFFIXES = re.compile(r"_(avg|sum)$", re.IGNORECASE)


def _strip_aggr_suffix_if_needed(name: str, valid_fields: set[str] | None) -> str:
    """
    智能剥离聚合后缀：
    - 如果不知道合法字段集合（valid_fields is None），保守只剥 _avg/_sum
    - 如果知道：原名在 schema 中 → 原样返回；不在但剥后在 → 返回剥后的
    """
    if valid_fields is None:
        return AGGR_SUFFIXES.sub("", name)
    if name in valid_fields:
        return name
    stripped = _AGGR_SUFFIX_CANDIDATES.sub("", name)
    if stripped != name and stripped in valid_fields:
        return stripped
    # 再试一次 _avg/_sum 的保守剥除
    stripped2 = AGGR_SUFFIXES.sub("", name)
    if stripped2 != name and stripped2 in valid_fields:
        return stripped2
    return name  # 都不匹配就原样返回，后续会告警


# 分钟表字段关键词→合法字段的模糊匹配映射
# 当 LLM 编造不存在的字段名时，用关键词匹配最接近的合法字段
# 按关键词长度降序排列，长关键词优先匹配（避免 "rate" 误匹配 negotiationRate 类字段）
MINUTE_FIELD_KEYWORDS = {
    # 长关键词（优先匹配）
    "negotiationrxrate": ["zeroNegotiationRxRateCnt", "avgNegotiationRxRate"],
    "negotiationtxrate": ["avgNegotiationTxRate"],
    "negotiation": ["avgNegotiationTxRate", "avgNegotiationRxRate", "zeroNegotiationRxRateCnt"],
    "achievablerate": ["avgAchievableRate", "zeroAchievableRateCnt"],
    "highinterference": ["highCnt"],
    "interference": ["midCnt", "highCnt", "lowCnt"],
    "rxpower": ["RxPower", "oltRxPowerHigh"],
    "oltrxpower": ["RxPower", "oltRxPowerHigh", "oltRxWeakLight"],
    "weaklight": ["oltRxWeakLight", "RxPower"],
    "latency": ["avgDiagAvgTime", "maxDiagMaxTime"],
    "retrans": ["avgDiagLossRate"],
    "traffic": ["maxTxTraffic", "meanRxTraffic"],
    "memory": ["homeRamMax", "apRamMax"],
    "device": ["totalDevices", "numSTA"],
    "packet": ["avgDiagLossRate", "diagLossHigh"],
    "signal": ["avgWifiSignal", "avgSnr"],
    # 短关键词（后匹配）
    "interfer": ["midCnt", "highCnt", "lowCnt"],
    "loss": ["avgDiagLossRate", "maxDiagLossRate", "diagLossHigh"],
    "delay": ["avgDiagAvgTime", "maxDiagMaxTime", "diagTimeDelayHigh"],
    "cpu": ["homeCpuMax", "apCpuMax"],
    "ram": ["homeRamMax", "apRamMax"],
    "rate": ["peakRxRate", "avgAchievableRate", "avgNegotiationTxRate"],
    "power": ["RxPower"],
    "light": ["RxPower", "oltRxPowerHigh"],
    "bip": ["bipHigh", "ontDownstreamBipErrors"],
    "fec": ["fecHigh", "ontRxFecErrors"],
    "roam": ["roamDelayHigh"],
    "wifi": ["avgWifiSignal", "avgSnr", "apWifiCnt"],
    "plr": ["G10UpPlr", "G1UpPlr", "portUpPlr"],
    "noise": ["avgNoise", "avgSnr"],
    "snr": ["avgSnr"],
    "alarm": ["alarmCount", "unclearedAlarmCount_A"],
}


def fix_query_config(query_config: dict, table_level: str = "day") -> tuple[dict, list[str]]:
    """
    修复 LLM 生成的三元组查询配置中的常见错误。
    返回 (修复后config, 警告列表)。

    修复项：
    1. breakdown 使用了连续数值字段 → 替换为 portUuid
    2. 操作符错误（EQUALS → IN 等）
    3. 字段名带聚合后缀（_avg, _sum 等）→ 移除
    4. breakdown 和 dimension 冲突 → 移除冲突的 dimension
    5. dimensions 格式错误 → 修正为 [[]]
    6. conditions 为空但保留了 dimension 结构 → 清理为 [[]]
    7. 分钟表阶段使用了天表字段（如 CEI_score）→ 替换为合法分钟表字段
    """
    config = deepcopy(query_config)

    # 修复 breakdown
    config["breakdown"] = _fix_breakdown(config.get("breakdown", {}))

    # 修复 measures（返回警告列表）
    config["measures"], fix_warnings = _fix_measures(config.get("measures", []), table_level)

    # 最终兜底：天表永远不允许 measures 被清空（day_schema 校验只做字段名修正，不做丢弃）
    # 分钟表可能合理地把不合法字段全部丢弃，所以只对天表生效
    original_measures = query_config.get("measures", [])
    if table_level == "day" and not config["measures"] and original_measures:
        logger.warning(
            "_fix_measures 意外清空了天表 measures，还原原始值: %s",
            [m.get("name") for m in original_measures if isinstance(m, dict)],
        )
        config["measures"] = deepcopy(original_measures)

    # 修复 dimensions
    config["dimensions"] = _fix_dimensions(
        config.get("dimensions", [[]]),
        config["breakdown"].get("name", ""),
    )

    return config, fix_warnings


def _fix_breakdown(breakdown: dict) -> dict:
    """修复 breakdown 字段"""
    if not breakdown:
        return {"name": "portUuid", "type": "UNORDERED"}

    name = breakdown.get("name", "portUuid")

    # 移除聚合后缀
    name = AGGR_SUFFIXES.sub("", name)

    # 如果不是合法的离散字段，替换为 portUuid
    if name not in VALID_BREAKDOWN_FIELDS:
        logger.warning("breakdown 字段 '%s' 不是离散字段，替换为 portUuid", name)
        name = "portUuid"
        breakdown["type"] = "UNORDERED"

    breakdown["name"] = name

    # 修复 type
    bd_type = breakdown.get("type", "UNORDERED")
    if name in ("date", "time_id"):
        bd_type = "ORDERED"
    elif bd_type not in ("ORDERED", "UNORDERED"):
        bd_type = "UNORDERED"
    breakdown["type"] = bd_type

    return breakdown


def _fuzzy_match_minute_field(name: str, valid_fields: set) -> str | None:
    """尝试用关键词匹配最接近的合法分钟表字段，长关键词优先"""
    name_lower = name.lower()
    # 按关键词长度降序，避免短关键词（如 "rate"）误匹配
    sorted_keywords = sorted(MINUTE_FIELD_KEYWORDS.items(), key=lambda x: -len(x[0]))
    for keyword, candidates in sorted_keywords:
        if keyword in name_lower:
            for c in candidates:
                if c in valid_fields:
                    return c
    return None


def _fix_measures(measures: list[dict], table_level: str = "day") -> tuple[list[dict], list[str]]:
    """修复 measures 中的字段名，分钟表阶段校验字段合法性。返回 (修复后measures, 警告列表)"""
    warnings: list[str] = []
    if not measures:
        return [], warnings
    # 天表 / 分钟表合法字段集合（延迟导入避免循环依赖）
    minute_valid = None
    day_valid = None
    if table_level == "minute":
        try:
            from ce_insight_core.services.minute_schema_manager import get_all_minute_fields

            minute_valid = get_all_minute_fields()
        except ImportError:
            minute_valid = None
    else:
        try:
            from ce_insight_core.services.day_schema_manager import get_all_day_fields

            day_valid = get_all_day_fields()
        except ImportError:
            day_valid = None

    fixed = []
    seen_names = set()  # 避免模糊匹配产生重复字段
    for m in measures:
        # 跳过 None 或非 dict 项（LLM 输出 null 或其他类型时兜底）
        if not isinstance(m, dict):
            logger.warning("跳过非 dict 的 measure 项: %r", m)
            continue
        name = m.get("name", "")
        if not name:
            continue
        # 智能剥离聚合后缀：先查 schema，存在则保留原名，不存在才尝试剥除
        valid_set = day_valid if table_level != "minute" else minute_valid
        original_name = name
        name = _strip_aggr_suffix_if_needed(name, valid_set)
        if name != original_name:
            logger.info("measure 字段后缀剥除: '%s' → '%s'", original_name, name)
        aggr = m.get("aggr", "AVG") or "AVG"
        # 修复大小写
        aggr = aggr.upper() if isinstance(aggr, str) else "AVG"
        if aggr not in ("SUM", "AVG", "COUNT", "MIN", "MAX"):
            aggr = "AVG"

        # 分钟表字段校验
        if minute_valid is not None and name not in minute_valid:
            # 先尝试模糊匹配
            matched = _fuzzy_match_minute_field(name, minute_valid)
            if matched:
                warn_msg = f"字段替换: '{name}'(天表) → '{matched}'(分钟表)"
                logger.warning(warn_msg)
                warnings.append(warn_msg)
                name = matched
            else:
                warn_msg = f"分钟表不支持字段 '{name}'，已丢弃"
                logger.warning(warn_msg)
                warnings.append(warn_msg)
                continue

        # 去重
        if name in seen_names:
            logger.info("跳过重复字段 '%s'", name)
            continue
        seen_names.add(name)

        fixed.append({"name": name, "aggr": aggr})

    # 如果分钟表校验后所有 measures 都被丢弃，根据上下文选择合理的兜底字段
    if not fixed and table_level == "minute":
        fallback = _pick_minute_fallback(measures)
        logger.warning("分钟表 measures 全部无效，使用 %s 兜底", fallback)
        warnings.append(f"所有字段均无效，已使用 {fallback} 兜底")
        fixed.append({"name": fallback, "aggr": "AVG"})

    return fixed, warnings


def _pick_minute_fallback(original_measures: list[dict]) -> str:
    """根据原始 measures 的语义，选择最相关的分钟表字段兜底"""
    # 从原始字段名中提取关键词（跳过 None/非 dict）
    names = " ".join(m.get("name", "") for m in original_measures if isinstance(m, dict)).lower()
    # 按业务语义匹配
    if any(kw in names for kw in ("stability", "alarm", "interrupt", "count", "flap")):
        return "alarmCount"
    if any(kw in names for kw in ("odn", "power", "light", "bip", "fec", "rx")):
        return "RxPower"
    if any(kw in names for kw in ("rate", "negotiation", "achievable", "speed")):
        return "peakRxRate"
    if any(kw in names for kw in ("wifi", "signal", "noise", "snr", "interfer")):
        return "avgWifiSignal"
    if any(kw in names for kw in ("gateway", "cpu", "ram", "memory")):
        return "homeCpuMax"
    if any(kw in names for kw in ("loss", "delay", "latency", "diag")):
        return "avgDiagLossRate"
    if any(kw in names for kw in ("sta", "device", "terminal")):
        return "numSTA"
    return "alarmCount"  # 最终兜底


def _fix_dimensions(dimensions: list, breakdown_name: str) -> list:
    """修复 dimensions"""
    if not dimensions:
        return [[]]

    # 如果 dimensions 不是 list[list] 格式，尝试修正
    if dimensions and not isinstance(dimensions[0], list):
        # 可能是 [{"dimension":...}] 而不是 [[{"dimension":...}]]
        dimensions = [dimensions]

    fixed_outer = []
    for dim_group in dimensions:
        if not dim_group or not isinstance(dim_group, list):
            fixed_outer.append([])
            continue

        fixed_group = []
        for dim_cond in dim_group:
            if not isinstance(dim_cond, dict):
                continue

            # 修复 conditions 为空/None 的情况（LLM 输出 "conditions": null 时 .get 返回 None 而非 []）
            conditions = dim_cond.get("conditions") or []
            if not isinstance(conditions, list):
                logger.warning("跳过 conditions 非列表的 dimension: %s", dim_cond)
                continue
            if not conditions:
                logger.warning("跳过 conditions 为空的 dimension: %s", dim_cond)
                continue

            # 修复操作符
            fixed_conditions = []
            for cond in conditions:
                if not isinstance(cond, dict):
                    continue
                oper = cond.get("oper", "IN")
                oper = OPER_FIX_MAP.get(oper, oper)
                cond["oper"] = oper

                # IN/NOT_IN 的 values 必须是非空列表（空 values 的 IN 等价于无意义过滤，丢弃）
                values = cond.get("values", [])
                if oper in ("IN", "NOT_IN"):
                    if not isinstance(values, list):
                        values = [values]
                        cond["values"] = values
                    if not values:
                        logger.warning("跳过 %s 但 values 为空的条件: %s", oper, cond)
                        continue

                fixed_conditions.append(cond)

            # 🔴 关键：空 conditions 的 dim_cond 语义非法（Pydantic DimensionCondition.conditions: list[DimensionFilter]
            # 允许空 list 不报错，但下游 cei_query 无法处理——"不过滤"应表达为 dimensions: [[]]）
            # 如果 fixed_conditions 已空，整个 dim_cond 必须丢弃，不能 append 到 fixed_group
            if not fixed_conditions:
                logger.warning("修复后 conditions 为空，丢弃整个 dim_cond: %s", dim_cond)
                continue

            dim_cond["conditions"] = fixed_conditions

            # 修复 dimension 中的字段名
            dim_info = dim_cond.get("dimension") or {}
            if not isinstance(dim_info, dict):
                logger.warning("跳过 dimension 字段不是 dict 的 dim_cond: %s", dim_cond)
                continue
            dim_name = dim_info.get("name", "")
            dim_name = AGGR_SUFFIXES.sub("", dim_name)
            if not dim_name:
                logger.warning("跳过 dimension.name 为空的 dim_cond: %s", dim_cond)
                continue
            dim_info["name"] = dim_name

            # breakdown 和 dimension 冲突检查
            # 当过滤字段和 breakdown 字段相同时（如 portUuid IN [...] + breakdown by portUuid）
            # 不能直接丢弃过滤条件！只在确实无意义时才跳过
            if dim_name == breakdown_name:
                # 检查 values 数量：如果只过滤 1-2 个值且 breakdown 也按此字段分组，
                # 则结果只有 1-2 行，OutstandingMin 等函数会报"分组数不足"
                in_values = []
                for cond in fixed_conditions:
                    if cond.get("oper") == "IN":
                        in_values = cond.get("values", [])
                if len(in_values) <= 2:
                    # 少量值按同一字段分组无意义，保留过滤但不丢弃
                    # 让 query 正常带着 filter 执行，少量分组洞察函数会自己处理
                    logger.info(
                        "dimension '%s' 与 breakdown 相同且过滤值较少（%d个），保留过滤条件",
                        dim_name,
                        len(in_values),
                    )
                else:
                    # 多值过滤+同字段分组是合理的（筛选出一批设备，然后对比它们）
                    logger.info(
                        "dimension '%s' 与 breakdown 相同但过滤值较多（%d个），保留",
                        dim_name,
                        len(in_values),
                    )

            dim_cond["dimension"] = dim_info
            fixed_group.append(dim_cond)

        fixed_outer.append(fixed_group)

    # 如果修复后所有 group 都空了，返回 [[]]
    if not fixed_outer or all(not g for g in fixed_outer):
        return [[]]

    return fixed_outer
