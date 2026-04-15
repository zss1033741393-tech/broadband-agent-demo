"""
三元组数据查询服务。
使用内网 cei_query 接口；cei_query_mock 保留供离线 / 无内网环境回退。
"""

import logging

import numpy as np
import pandas as pd

from cei_query.api import query_subject_from_single_table
from cei_query.query.models import InsightSubspace as InsightSubspaceApiModel

# 外网/离线回退（保留，不删除）：
# from ce_insight_core.cei_query_mock.api import query_subject_from_single_table
# from ce_insight_core.cei_query_mock.query.models import InsightSubspaceApiModel

logger = logging.getLogger(__name__)


def query_subject_pandas(
    query_config: dict,
    data_path: str,
    auto_convert_timestamp: bool = True,
) -> list[pd.DataFrame]:
    """
    通过三元组查询数据，返回 DataFrame 列表。

    参数:
        query_config: 三元组配置 {"dimensions", "breakdown", "measures"}
        data_path: parquet 文件路径
        auto_convert_timestamp: 是否自动转换时间戳列

    返回:
        DataFrame 列表（通常只有 1 个）
    """
    # 将 dict 转换为 InsightSubspace 对象，与内网接口保持一致
    converted_input = InsightSubspaceApiModel.model_validate(query_config)

    result = query_subject_from_single_table(data_path, converted_input, use_pandas=True)

    if auto_convert_timestamp:
        result = [_auto_convert_timestamps(df) for df in result]

    result = [_clean_column_names(df) for df in result]

    logger.info(
        "查询完成，返回 %d 个 DataFrame，首个形状: %s",
        len(result),
        result[0].shape if result else "空",
    )
    return result


def summarize_dataframe(df: pd.DataFrame, description: str, max_rows: int = 5) -> str:
    """
    将 DataFrame 转换为文字摘要，供下一 Phase 的 LLM 参考。

    包含：行数、列名、数值列的统计（最大值、最小值、均值）、前N行数据。
    """
    if df is None or df.empty:
        return f"[{description}] 结果为空"

    summary_parts = [f"[{description}]"]
    summary_parts.append(f"- 数据行数：{len(df)}")
    summary_parts.append(f"- 列名：{list(df.columns)}")

    # 数值列统计
    numeric_cols = df.select_dtypes(include="number").columns
    for col in numeric_cols[:5]:
        summary_parts.append(
            f"- {col}：最大={df[col].max():.3f}, 最小={df[col].min():.3f}, 均值={df[col].mean():.3f}"
        )

    # 独特值统计（非数值列）
    str_cols = df.select_dtypes(exclude="number").columns
    for col in str_cols[:3]:
        # 跳过含 dict/list 等 unhashable 的列（NL2Code 结果经常有）
        try:
            unique_count = df[col].nunique()
        except TypeError:
            summary_parts.append(f"- {col}：含嵌套结构（dict/list），跳过唯一值统计")
            continue
        summary_parts.append(f"- {col}：{unique_count} 个唯一值")
        if unique_count <= 5:
            try:
                summary_parts.append(f"  值：{df[col].unique().tolist()}")
            except TypeError:
                pass

    # 前N行
    summary_parts.append(f"- 前{min(max_rows, len(df))}行数据：")
    try:
        summary_parts.append(df.head(max_rows).to_string(index=False))
    except Exception:
        summary_parts.append("（无法格式化，含嵌套结构）")

    return "\n".join(summary_parts)


def _clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
    """去掉内网查询返回的聚合后缀（_avg、_sum、_min、_max、_count）"""
    import re

    rename_map = {}
    for col in df.columns:
        cleaned = re.sub(r"_(avg|sum|min|max|count)$", "", col, flags=re.IGNORECASE)
        if cleaned != col:
            rename_map[col] = cleaned
    if rename_map:
        logger.info("清理列名后缀: %s", rename_map)
        df = df.rename(columns=rename_map)
    return df


def _auto_convert_timestamps(df: pd.DataFrame) -> pd.DataFrame:
    """
    自动检测疑似时间戳的数值列并就地转换为 datetime。

    检测策略（值域驱动，不依赖列名）：
    1. 必须是数值类型
    2. **整列**的 min 和 max 都落在合法时间戳区间内（2000-01-01 ~ 2100-01-01）
    3. 自动识别 s / ms / us 三档单位
    4. 转换后年份再做一次 sanity check（必须落在 2000-2100）

    这种策略对列名零依赖，`time_id` / `create_time_ms` / `event_ts` / `hour_id`
    等任意命名都能识别；同时业务字段如 `CEI_score`（1-100）、`bipHighCnt`（小数值）
    因数值范围不在时间戳区间内而被跳过，不会误伤。

    向后兼容性：转换是 **就地替换**，序列化时 datetime 会通过 `_json_default` 的
    `isoformat()` 转为 ISO 字符串（如 "2025-04-16T13:05:00"），前端拿到的是
    可读时间字符串而非整数毫秒，请确认前端不依赖整数时间戳做数值运算。
    """
    # 时间戳合法范围：2000-01-01 (946684800) ~ 2100-01-01 (4102444800)
    S_MIN, S_MAX = 946684800, 4102444800
    MS_MIN, MS_MAX = S_MIN * 1000, S_MAX * 1000
    US_MIN, US_MAX = S_MIN * 1_000_000, S_MAX * 1_000_000

    for col in df.columns:
        # 跳过已是 datetime 的列
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            continue
        # 必须是数值列
        if not pd.api.types.is_numeric_dtype(df[col]):
            continue

        non_null = df[col].dropna()
        if non_null.empty:
            continue

        try:
            min_val = float(non_null.min())
            max_val = float(non_null.max())
        except (TypeError, ValueError):
            continue

        # 判断单位（min 和 max 必须都在同一档范围内才认）
        if S_MIN <= min_val and max_val <= S_MAX:
            unit = "s"
        elif MS_MIN <= min_val and max_val <= MS_MAX:
            unit = "ms"
        elif US_MIN <= min_val and max_val <= US_MAX:
            unit = "us"
        else:
            continue

        # 尝试转换
        try:
            converted = pd.to_datetime(df[col], unit=unit, errors="coerce")
        except (ValueError, OverflowError) as e:
            logger.debug("时间戳列 %s 转换失败: %s", col, e)
            continue

        # 二次年份 sanity check
        years = converted.dt.year.dropna()
        if years.empty or int(years.min()) < 2000 or int(years.max()) > 2100:
            continue

        df[col] = converted
        logger.info(
            "时间戳列已转换: %s (unit=%s, 范围 %s ~ %s)",
            col,
            unit,
            converted.min(),
            converted.max(),
        )

    return df
