"""
天表 Schema 管理模块
负责维护天表各维度的 schema 并根据 T0 结果进行剪枝
"""

import logging

logger = logging.getLogger(__name__)

from typing import Dict, Optional

DAY_DIMENSION_SCHEMAS = {
    "core": """
## 核心分组字段
- portUuid (string): PON口ID，示例 `"4fd36157-4758-4488-aa69-e5361ed93bb6"`,格式：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
- date (string): 日期，格式 `"YYYYMMDD"`，示例 `"20250413"`，ORDERED类型
- gatewayMac (string): ONT设备MAC地址,示例：`"14EB004BA0A0"`，格式：XXXXXXXXXXXX（12个十六进制字符）
""",
    "scores": """
## 天表总分字段
- CEI_score (float): 总体质量得分（8维度加权总分）
## 8个维度得分字段
- Stability_score (float): 稳定性得分
- ODN_score (float): ODN得分
- Rate_score (float): 速率得分
- Service_score (float): 业务得分
- OLT_score (float): OLT得分
- Gateway_score (float): 网关得分
- STA_score (float): 终端得分
- Wifi_score (float): WiFi得分
""",
    "Stability_score": """
## Stability 维度详细字段
| 指标名                                   | 含义                                       |
| count_mean                               | 除去周期DGI用户外的周期内告警平均次数扣分      |
| count_max                                | 除去周期DGI用户外的周期内天的告警最大次数扣分  |
| interruption_same_day_max                | 当天中断时长最大值扣分                         |
| interruption_same_day                    | 当天中断时长和扣分                             |
| interruption_week_ave                    | 周平均中断时长扣分                             |
| Stability_score                          | 稳定性维度得分                                 |
""",
    "Gateway_score": """
## Gateway 维度详细字段
| 指标名                                   | 含义                                       |
| apExceHighCnt                            | 从网关连接异常越限次数                         |
| apWifiHighCnt                            | AP连接方式为Wi-Fi越限次数                      |
| apLanHighCnt                             | AP连接方式为LAN越限次数                        |
| apPonHighCnt                             | AP连接方式为PON越限次数                        |
| homeRamHighCnt                           | 主网关内存异常次数                             |
| apRamHighCnt                             | 从网关内存异常次数                             |
| homeCpuMaxHighCnt                        | 主网关内存利用率越限次数                       |
| apCpuMaxHighCnt                          | AP网关CPU利用率越限次数                        |
| ramScore                                 | 内存异常（AP 90% 网关 90%）比例分数            |
| cpuMaxScore                              | CPU异常（AP 85%，网关 80%）比例分数            |
| apExceScore                              | 主从之间异常连接（非光纤连接）比例分数         |
| Gateway_score                            | nan                                            |
""",
    "ODN_score": """
## ODN 维度详细字段
| 指标名                                   | 含义                                       |
| oltRxPowerHighCnt                        | 弱光值异常次数                                 |
| oltRxPowerCnt                            | 弱光值次数                                     |
| bipHighCnt                               | BIP误码率越限次数                                 |
| bipCnt                                   | BIP误码率采集次数                                     |
| fecHighCnt                               | FEC错帧率越限次数                             |
| oltRxPowerPercent                        | OLT接收光功率越限占比                            |
| bipPercent                               | BIP误码率越限占比                                    |
| fecPercent                               | FEC错帧率越限占比                                    |
| oltRxPowerScore                          | OLT接收光功率越限占比扣分                        |
| bipScore                                 | BIP越限占比扣分                                |
| fecScore                                 | FEC越限占比扣分                                |
| ODN_score                                | ODN维度得分                                    |
""",
    "Rate_score": """
## Rate 维度详细字段
| 指标名                                   | 含义                                       |
| maxTxRateHighCnt                         | 下行速率异常次数                               |
| meanRxRateHighCnt                        | 上行速率异常次数                               |
| peakRxRateHighCnt                        | 峰值速率异常次数                               |
| rxTrafficHighCnt                         | 下行流量异常次数                               |
| isTxTrafficHighCnt                       | 上行流量 == 0 次数                             |
| isRxTrafficHighCnt                       | 下行流量 == 0 次数                             |
| isTxTrafficPercent                       | 上行流量 == 0 占比                             |
| isRxTrafficPercent                       | 下行流量 == 0 占比                             |
| isNegotiationRxRateHighCnt               | 协商的接收速率 == 0 次数                       |
| isNegotiationTxRatePercent               | 协商的发送速率 == 0 次数                       |
| isRateHighPercent                        | 异常次数比例                                   |
| isRateHighCnt                            | 上行口实时速率、协商速率以及端口类型的越限次数 |
| maxTxRateHighCntPercent                  | rxRate 异常比例                                |
| peakRxRatePercent                        | peakRxRate 异常比例                            |
| maxTxRatePercent                         | maxTxRate 异常比例                             |
| meanRxRatePercent                        | meanRxRate 异常比例                            |
| rxTrafficPercent                         | rxTraffic 异常比例                             |
| isTxTrafficScore                         | 传输速率大于最大传输速率占比扣分               |
| isRxTrafficScore                         | 接收速率大于最大接收速率占比扣分               |
| isNegotiationRxRateScore                 | 协商接收速率==0的比例扣分                      |
| isNegotiationTxRateScore                 | 协商发送速率==0的比例扣分                      |
| maxTxRateScore                           | 最大峰值速率 / 协商速率 > 80%的比例扣分        |
| meanRxRateScore                          | 平均速率 > 平均速率阈值 的比例扣分             |
| Rate_score                               | nan                                            |
""",
    "Service_score": """
## Service 维度详细字段
| 指标名                                   | 含义                                       |
| officeDepressionTimesPercent             | 办公大类质差时长占比                           |
| gameDepressionTimesPercent               | 游戏大类质差时长占比                           |
| videoCallDepressionTimesPercent          | 视频通话类质差时长占比                         |
| educationDepressionTimesPercent          | 教育类质差时长占比                             |
| liveVideoDepressionTimesPercent          | 直播类质差时长占比                             |
| anchorVideoDepressionTimesPercent        | 主播类质差时长占比                             |
| pointVideoDepressionTimesPercent         | 点播类质差时长占比                             |
| generalTcpDepressionTimesPercent         | 通用TCP类质差时长占比                          |
| Service_score                            | 服务质量维度得分                               |
""",
    "OLT_score": """
## OLT 维度详细字段
| 指标名                                   | 含义                                       |
| G10UpPlrHighCnt                          | 10GPON丢包率异常次数                           |
| G1UpPlrHighCnt                           | GPON丢包率异常次数                             |
| portUpPlrHighCnt                         | 端口发送丢包比例上报异常次数                   |
| G10UpPlrPercent                          | 10GPON丢包率异常占比                           |
| G1UpPlrPercent                           | GPON丢包率异常占比                             |
| portUpPlrPercent                         | 端口丢包率异常占比                             |
| portUpPlrScore                           | 端口丢包率异常（> 0.001）比例                  |
| G1UpPlrScore                             | GPON丢包率异常（> 0.001）比例                  |
| G10UpPlrScore                            | 10GPON丢包率异常（> 0.001）比例                |
| OLT_score                                | OLT维度得分                                    |
""",
    "STA_score": """
## STA 维度详细字段
| 指标名                                   | 含义                                       |
| allAntennaCnt                            | 有天线终端数量                                 |
| lowAntennaCnt                            | 低规格终端数量                                 |
| midSatisfactionStaCnt                    | 终端满意度为中的终端数量                       |
| allSatisfactionStaCnt                    | 可计算终端满意度的终端数量                     |
| lowSatisfactionStaCnt                    | 终端满意度为低的终端数量                       |
| isAchievableRateHighCnt                  | 可达速率为零异常次数                           |
| lowAntennaPercent                        | 低规格终端占比                                 |
| isAchievableRatePercent                  | 可达速率为零异常占比                           |
| lowSatisfactionStaScore                  | 低终端满意度比例                               |
| midSatisfactionStaScore                  | 中终端满意度比例                               |
| lowAntennaScore                          | 低规格天线终端比例                             |
| isAchievableRateScore                    | 可达速率为0的比例                              |
| STA_score                                | nan                                            |
""",
    "Wifi_score": """
## Wifi 维度详细字段
| 指标名                                   | 含义                                       |
| radioTypeCnt                             | Wi-Fi 使用数量                                 |
| radioTypeHighCnt                         | Wi-Fi 2.4G 使用数量                            |
| device5MinNumHighCnt                     | 五分钟下挂设备数量越限次数                     |
| diagLossHighCnt                          | Ping丢包率越限次数                             |
| diagTimeDelayHighCnt                     | Ping时延越限次数                               |
| deviceNumCnt                             | 五分钟下挂设备数量                             |
| roamDelayCnt                             | 漫游切换时延越限次数                           |
| emptyDelayCnt                            | 空口时延越限次数                               |
| midInterferencePercent                   | 干扰空占比中分箱区间占比                       |
| highInterferencePercent                  | 干扰空占比高分箱区间占比                       |
| lowInterferencePercent                   | 干扰空占比低分箱区间占比                       |
| diagTimePercent                          | Ping丢包率越限占比                             |
| radioTypePercent                         | Wi-Fi 2.4G 使用扣分                            |
| dBmPercent                               | 信号强度平均越限占比                           |
| device5MinPercent                        | 五分钟下挂设备数量越限占比                     |
| diagLossPercent                          | Ping丢包率越限占比                             |
| roamDelayPercent                         | 漫游时延越限占比                               |
| emptyDelayPercent                        | 空口时延越限占比                               |
| dBmScore                                 | 信号强度不足比例（2.4G < -80Db; 5G < -83Db ）  |
| emptyDelayScore                          | 空口时延异常比例（> 100ms）                    |
| roamDelayScore                           | 漫游时延异常比例（> 100ms）                    |
| lowInterferenceScore                     | 干扰占空比低区间比例                           |
| midInterferenceScore                     | 干扰占空比中区间比例                           |
| highInterferenceScore                    | 干扰占空比高区间比例                           |
| radioTypeScore                           | 2.4G比例                                       |
| diagLossScore                            | 五分钟下挂设备数量 > 16 比例                   |
| diagTimeDelayScore                       | Ping丢包率 > 60% 的比例                        |
| Wifi_score                               | nan                                            |
""",
}


def get_full_day_schema() -> str:
    """
    获取完整的天表 schema（所有维度）

    Returns:
        完整的 schema markdown 字符串
    """
    schema_parts = [DAY_DIMENSION_SCHEMAS["core"], DAY_DIMENSION_SCHEMAS["scores"]]

    for dim in [
        "Stability_score",
        "Gateway_score",
        "ODN_score",
        "Rate_score",
        "Service_score",
        "OLT_score",
        "STA_score",
        "Wifi_score",
    ]:
        schema_parts.append(DAY_DIMENSION_SCHEMAS[dim])

    return "\n".join(schema_parts)


_ALL_DAY_FIELDS_CACHE: set[str] | None = None


def get_all_day_fields() -> set[str]:
    """
    从 DAY_DIMENSION_SCHEMAS 提取所有天表合法字段名。
    解析 markdown 表格的首列和 core 段的 `- xxx (type)` 格式。
    结果缓存到模块级变量。
    """
    global _ALL_DAY_FIELDS_CACHE
    if _ALL_DAY_FIELDS_CACHE is not None:
        return _ALL_DAY_FIELDS_CACHE

    import re

    fields: set[str] = set()
    # 匹配 markdown 表格行: | fieldName | desc |
    table_row_re = re.compile(r"^\|\s*([A-Za-z][A-Za-z0-9_]*)\s*\|")
    # 匹配 core/scores 段的 bullet: - fieldName (type):
    bullet_re = re.compile(r"^-\s*([A-Za-z][A-Za-z0-9_]*)\s*\(")

    for section in DAY_DIMENSION_SCHEMAS.values():
        for line in section.splitlines():
            stripped = line.strip()
            m = table_row_re.match(stripped)
            if m:
                name = m.group(1)
                # 过滤表头标识（"指标名" 等字眼实际不会匹配英文正则）
                fields.add(name)
                continue
            m = bullet_re.match(stripped)
            if m:
                fields.add(m.group(1))

    _ALL_DAY_FIELDS_CACHE = fields
    return fields


def get_pruned_day_schema(t0_result: Optional[Dict]) -> str:
    """
    根据 T0 结果获取剪枝后的天表 schema

    策略：
    - 始终包含：core + scores
    - 如果 T0 有问题维度列表：包含所有问题维度的详细字段
    - 如果 T0 没有问题维度或匹配失败：返回完整 schema
    """
    schema_parts = [
        DAY_DIMENSION_SCHEMAS["core"],
        DAY_DIMENSION_SCHEMAS["scores"],
    ]

    if not t0_result:
        logger.warning("⚠️ 没有 T0 结果，使用完整天表 schema")
        return get_full_day_schema()

    problem_dimensions = t0_result.get("问题维度列表", [])

    if not problem_dimensions:
        logger.warning("⚠️ T0 结果中没有问题维度，使用完整天表 schema")
        return get_full_day_schema()

    matched_dimensions = []
    for problem_dimension in problem_dimensions:
        dimension_key = _find_dimension_key(problem_dimension)

        if dimension_key:
            schema_parts.append(DAY_DIMENSION_SCHEMAS[dimension_key])
            matched_dimensions.append(dimension_key)
        else:
            logger.warning(f"⚠️ 无法匹配问题维度 '{problem_dimension}'")

    if not matched_dimensions:
        logger.warning("⚠️ 所有问题维度都无法匹配，使用完整天表 schema")
        return get_full_day_schema()

    pruned_schema = "\n".join(schema_parts)

    full_schema_len = len(get_full_day_schema())
    pruned_schema_len = len(pruned_schema)
    saved_ratio = (1 - pruned_schema_len / full_schema_len) * 100

    logger.info(
        f"✅ 天表 Schema 剪枝完成：聚焦于 {matched_dimensions}，节省 {saved_ratio:.1f}% token"
    )

    return pruned_schema


def _find_dimension_key(problem_dimension: str) -> Optional[str]:
    """
    智能匹配维度 key（通用逻辑）

    匹配规则（按优先级）：
    1. 精确匹配：problem_dimension 直接在字典中
    2. 添加后缀：problem_dimension + "_score"
    3. 去除后缀：problem_dimension 去掉 "_score"
    4. 模糊匹配：problem_dimension 的核心词在 key 中

    Args:
        problem_dimension: T0 返回的问题维度，如 "Rate", "Rate_score", "rate", "RATE_SCORE"

    Returns:
        匹配到的 key，如果匹配失败返回 None
    """
    problem_dimension = problem_dimension.strip()

    if problem_dimension in DAY_DIMENSION_SCHEMAS:
        logger.info(f"✅ 精确匹配: '{problem_dimension}'")
        return problem_dimension

    with_suffix = f"{problem_dimension}_score"
    if with_suffix in DAY_DIMENSION_SCHEMAS:
        logger.info(f"✅ 添加后缀匹配: '{problem_dimension}' → '{with_suffix}'")
        return with_suffix

    without_suffix = problem_dimension.replace("_score", "")
    if without_suffix in DAY_DIMENSION_SCHEMAS:
        logger.info(f"✅ 去除后缀匹配: '{problem_dimension}' → '{without_suffix}'")
        return without_suffix

    problem_lower = problem_dimension.lower().replace("_score", "")

    for key in DAY_DIMENSION_SCHEMAS:
        if key in ["core", "scores"]:
            continue

        key_lower = key.lower().replace("_score", "")

        if problem_lower in key_lower or key_lower in problem_lower:
            logger.info(f"✅ 模糊匹配: '{problem_dimension}' → '{key}'")
            return key

    logger.error(f"❌ 匹配失败: '{problem_dimension}'")
    logger.error(
        f"   可用的维度 keys: {[k for k in DAY_DIMENSION_SCHEMAS if k not in ['core', 'scores']]}"
    )
    return None


def get_pruned_schema(focus_dimensions: list[str]) -> str:
    """
    根据 Phase 的 focus_dimensions 获取剪枝后的天表 schema。
    这是 2.0 新增的接口，供 planner/decomposer 使用。

    参数:
        focus_dimensions: 重点关注的维度列表，如 ["ODN", "Service", "Wifi"]

    返回:
        core + scores + 指定维度详细字段的 schema 字符串
    """
    schema_parts = [
        DAY_DIMENSION_SCHEMAS["core"],
        DAY_DIMENSION_SCHEMAS["scores"],
    ]

    if not focus_dimensions:
        return get_full_day_schema()

    matched = []
    for dim in focus_dimensions:
        key = _find_dimension_key(dim)
        if key and key not in matched:
            schema_parts.append(DAY_DIMENSION_SCHEMAS[key])
            matched.append(key)

    if not matched:
        return get_full_day_schema()

    full_len = len(get_full_day_schema())
    pruned_len = len("\n".join(schema_parts))
    saved = (1 - pruned_len / full_len) * 100
    logger.info(f"Schema 剪枝：聚焦 {matched}，节省 {saved:.1f}% token")

    return "\n".join(schema_parts)
