"""
多指标交叉相关性：计算多个度量指标之间的相关矩阵，找出强相关对。
含 p-value、零方差检测、兜底放宽阈值策略。需要至少3个 measures。
"""

import logging

import numpy as np
import pandas as pd
from scipy import stats

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy

logger = logging.getLogger(__name__)


def _get_correlation_strength(abs_corr: float) -> str:
    """4级相关强度分类"""
    if abs_corr >= 0.7:
        return "强相关"
    elif abs_corr >= 0.5:
        return "中等相关"
    elif abs_corr >= 0.3:
        return "弱相关"
    else:
        return "极弱相关"


def _calculate_correlations(
    df: pd.DataFrame,
    columns: list[str],
    threshold: float = 0.5,
    p_threshold: float | None = 0.05,
) -> list[dict]:
    """逐对计算 pearsonr，返回满足阈值的相关对"""
    pairs = []
    for i, c1 in enumerate(columns):
        for j, c2 in enumerate(columns):
            if i >= j:
                continue
            try:
                corr, p_value = stats.pearsonr(df[c1], df[c2])
                if abs(corr) >= threshold and (p_threshold is None or p_value < p_threshold):
                    pairs.append(
                        {
                            "变量1": c1,
                            "变量2": c2,
                            "相关系数": round(float(corr), 4),
                            "相关强度": _get_correlation_strength(abs(corr)),
                            "相关方向": "正相关" if corr > 0 else "负相关",
                            "绝对值": round(abs(float(corr)), 4),
                            "p_value": round(float(p_value), 6),
                        }
                    )
            except Exception as e:
                logger.warning("计算 %s 和 %s 相关性时出错: %s", c1, c2, e)
    return pairs


class CrossMeasureCorrelationStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]

        if len(value_columns) < 3:
            self._description = {
                "error": "需要至少3个指标列才能进行交叉相关分析（2个指标请使用 Correlation）",
                "summary": "需要至少3个指标列才能进行交叉相关分析",
                "provided_count": len(value_columns),
            }
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        df = self._df[value_columns].dropna()

        if len(df) < 3:
            self._description = {
                "error": f"数据量不足（仅有 {len(df)} 行），至少需要3行才能计算相关性",
                "summary": "数据量不足，无法计算相关矩阵",
            }
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 零方差列检测
        low_variance_cols = []
        for col in value_columns:
            col_std = df[col].std()
            if pd.isna(col_std) or col_std < 1e-10:
                low_variance_cols.append(col)

        valid_columns = [c for c in value_columns if c not in low_variance_cols]

        if low_variance_cols:
            logger.info("零方差列已移除: %s，剩余有效列: %s", low_variance_cols, valid_columns)

        if len(valid_columns) < 2:
            self._description = {
                "error": "有效列不足（方差为0的列已移除），至少需要2个有变化的列",
                "summary": "有效列不足，无法计算相关矩阵",
                "low_variance_columns": low_variance_cols,
                "valid_columns": valid_columns,
            }
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 逐级放宽阈值计算相关性
        pairs = _calculate_correlations(df, valid_columns, threshold=0.5, p_threshold=0.05)
        is_fallback = False

        if not pairs:
            logger.info("未找到强相关（|r|>=0.5, p<0.05），放宽阈值到 |r|>=0.2")
            pairs = _calculate_correlations(df, valid_columns, threshold=0.2, p_threshold=None)

        if not pairs:
            logger.info("仍未找到相关性，显示所有相关系数")
            pairs = _calculate_correlations(df, valid_columns, threshold=0, p_threshold=None)
            is_fallback = True

        if not pairs:
            self._description = {
                "error": "无法计算任何相关性，可能数据存在问题",
                "summary": "无法计算相关性",
                "analyzed_columns": valid_columns,
            }
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 按绝对值排序
        pairs.sort(key=lambda p: p["绝对值"], reverse=True)
        result_df = pd.DataFrame(pairs)
        self._filter_data = result_df

        max_abs_corr = pairs[0]["绝对值"] if pairs else 0
        self._significance_score = float(np.clip(max_abs_corr, 0, 1))

        # 按强度统计
        count_map: dict[str, int] = {}
        for p in pairs:
            s = p["相关强度"]
            count_map[s] = count_map.get(s, 0) + 1

        self._description = {
            "variable_count": len(valid_columns),
            "significant_pairs": len(pairs),
            "strong_pairs": count_map.get("强相关", 0),
            "medium_pairs": count_map.get("中等相关", 0),
            "weak_pairs": count_map.get("弱相关", 0),
            "very_weak_pairs": count_map.get("极弱相关", 0),
            "top_pairs": pairs[:5],
            "matched_columns": value_columns,
            "summary": f"发现 {len(pairs)} 对相关指标，最强: {pairs[0]['变量1']} vs {pairs[0]['变量2']} (r={pairs[0]['相关系数']})",
        }

        if low_variance_cols:
            self._description["removed_low_variance"] = low_variance_cols

        if is_fallback:
            self._description["message"] = (
                "未找到统计显著的相关性（p<0.05），显示所有相关系数供参考"
            )
            self._description["is_fallback"] = True

        # 热力图：|r|<=0.3 的格子数值设为 None（灰色），着重显示强相关
        from ce_insight_core.services.insight_strategy.chart_style import (
            base_title,
            base_tooltip,
            truncate_labels,
        )

        corr_matrix = df[valid_columns].corr()
        display_labels = truncate_labels(valid_columns, 12)
        data_colored = []  # |r|>0.3 的有效数据
        data_gray = []  # |r|<=0.3 的灰色数据
        for i, c1 in enumerate(valid_columns):
            for j, c2 in enumerate(valid_columns):
                r = round(float(corr_matrix.loc[c1, c2]), 3)
                if i == j or abs(r) > 0.3:
                    data_colored.append([i, j, r])
                else:
                    data_gray.append([i, j, r])

        self._chart_configs = {
            "chart_type": "heatmap",
            "title": base_title("多指标交叉相关矩阵"),
            "tooltip": base_tooltip("item"),
            "grid": {"left": "18%", "right": "10%", "bottom": "18%", "top": "12%"},
            "xAxis": {
                "type": "category",
                "data": display_labels,
                "axisLabel": {"rotate": 45, "fontSize": 10},
            },
            "yAxis": {"type": "category", "data": display_labels, "axisLabel": {"fontSize": 10}},
            "visualMap": {
                "min": -1,
                "max": 1,
                "calculable": True,
                "inRange": {"color": ["#f2918c", "#ffffff", "#7eb8da"]},
                "textStyle": {"fontSize": 10},
                "seriesIndex": 0,
            },
            "series": [
                {
                    "name": "|r|>0.3",
                    "type": "heatmap",
                    "data": data_colored,
                    "label": {"show": True, "fontSize": 10},
                },
                {
                    "name": "|r|≤0.3",
                    "type": "heatmap",
                    "data": data_gray,
                    "label": {"show": True, "fontSize": 9, "color": "#bfbfbf"},
                    "itemStyle": {"color": "#f5f5f5"},
                },
            ],
        }
