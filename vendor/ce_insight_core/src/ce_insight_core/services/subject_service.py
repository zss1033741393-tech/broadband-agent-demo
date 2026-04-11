"""
三元组数据查询服务。
外网使用 cei_query_mock，内网部署时只需改两行 import。
"""

import logging

import numpy as np
import pandas as pd

# --- 外网/内网切换点：改这两行即可 ---
from ce_insight_core.cei_query_mock.api import query_subject_from_single_table
from ce_insight_core.cei_query_mock.query.models import InsightSubspaceApiModel

# 内网部署时换为：
# from cei_query.api import query_subject_from_single_table
# from cei_query.query.models import InsightSubspace as InsightSubspaceApiModel

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
    """自动将可能的时间戳数值列转换为 datetime"""
    for col in df.columns:
        if col in ("date", "timestamp", "time", "create_time"):
            if not pd.api.types.is_datetime64_any_dtype(df[col]):
                try:
                    sample = df[col].dropna().iloc[0] if len(df[col].dropna()) > 0 else None
                    if sample is not None and isinstance(sample, (int, float, np.integer)):
                        if sample > 1e15:
                            df[col] = pd.to_datetime(df[col], unit="us")
                        elif sample > 1e12:
                            df[col] = pd.to_datetime(df[col], unit="ms")
                        elif sample > 1e9:
                            df[col] = pd.to_datetime(df[col], unit="s")
                except Exception:
                    pass
    return df
