"""
洞察函数统一调用入口。
根据 insight_type 字符串分发到对应的 InsightStrategy 子类执行。
"""

import logging

import pandas as pd

from ce_insight_core.services.insight_strategy import (
    AttributionStrategy,
    ChangePointStrategy,
    ClusteringStrategy,
    CorrelationStrategy,
    CrossMeasureCorrelationStrategy,
    EvennessStrategy,
    OutlierDetectionStrategy,
    OutstandingMaxStrategy,
    OutstandingMinStrategy,
    OutstandingTop2Strategy,
    SeasonalityStrategy,
    TrendStrategy,
)

logger = logging.getLogger(__name__)

INSIGHT_MAP = {
    "Attribution": AttributionStrategy,
    "Trend": TrendStrategy,
    "Clustering": ClusteringStrategy,
    "OutlierDetection": OutlierDetectionStrategy,
    "Correlation": CorrelationStrategy,
    "Seasonality": SeasonalityStrategy,
    "ChangePoint": ChangePointStrategy,
    "Evenness": EvennessStrategy,
    "OutstandingMax": OutstandingMaxStrategy,
    "OutstandingMin": OutstandingMinStrategy,
    "OutstandingTop2": OutstandingTop2Strategy,
    "CrossMeasureCorrelation": CrossMeasureCorrelationStrategy,
}


def run_insight(
    insight_type: str,
    df: pd.DataFrame,
    value_columns: list[str],
    group_column: str = "",
) -> dict:
    """
    统一调用入口，执行指定类型的洞察分析。

    参数:
        insight_type: 洞察类型字符串，必须是 INSIGHT_MAP 中的 key
        df: 待分析的 DataFrame
        value_columns: 分析的指标列名列表
        group_column: 分组/时间列名（部分洞察类型不需要）

    返回:
        {
            "insight_type": str,
            "significance": float,
            "description": str | dict,
            "filter_data": list[dict],
            "chart_configs": dict,
        }
    """
    if insight_type not in INSIGHT_MAP:
        available = ", ".join(sorted(INSIGHT_MAP.keys()))
        raise ValueError(f"未知的洞察类型: {insight_type}，可用类型: {available}")

    cls = INSIGHT_MAP[insight_type]
    strategy = cls(df)

    # 需要 group_column 的类型，如果没传则返回错误
    NEEDS_GROUP = {
        "Attribution",
        "Evenness",
        "OutstandingMax",
        "OutstandingMin",
        "OutstandingTop2",
        "Trend",
        "Seasonality",
        "ChangePoint",
    }
    if insight_type in NEEDS_GROUP and (not group_column or group_column not in df.columns):
        return {
            "insight_type": insight_type,
            "significance": 0.0,
            "description": f"{insight_type} 需要 group_column（分组/时间列），但未提供或不存在",
            "filter_data": [],
            "chart_configs": {},
        }

    # 构造 kwargs，只传非空参数
    kwargs: dict = {"value_columns": value_columns}
    if group_column:
        kwargs["group_column"] = group_column

    # 校验列名存在
    missing = [c for c in value_columns if c not in df.columns]
    if missing:
        logger.warning(
            "%s: 列 %s 不在 df 中（可用: %s）", insight_type, missing, list(df.columns)[:8]
        )
        return {
            "insight_type": insight_type,
            "significance": 0.0,
            "description": f"列 {missing} 不在数据中",
            "filter_data": [],
            "chart_configs": {},
        }

    try:
        strategy.execute(**kwargs)
    except Exception as e:
        logger.error("洞察函数 %s 执行失败: %s", insight_type, e, exc_info=True)
        return {
            "insight_type": insight_type,
            "significance": 0.0,
            "description": f"执行失败: {e}",
            "filter_data": [],
            "chart_configs": {},
        }

    # 安全序列化 filter_data
    try:
        filter_records = strategy.filter_data.to_dict(orient="records")
    except Exception:
        filter_records = []

    return {
        "insight_type": insight_type,
        "significance": strategy.significance_score,
        "description": strategy.description,
        "filter_data": filter_records,
        "chart_configs": strategy.chart_configs,
    }


def list_insight_types() -> list[str]:
    """返回所有可用的洞察类型名称"""
    return sorted(INSIGHT_MAP.keys())
