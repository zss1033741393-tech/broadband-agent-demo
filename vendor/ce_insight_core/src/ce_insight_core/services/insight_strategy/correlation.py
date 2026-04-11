"""
相关性分析：计算两个指标之间的 Pearson 相关系数，含 p-value 和零方差检测。
"""

import logging

import numpy as np
import pandas as pd
from scipy import stats

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy

logger = logging.getLogger(__name__)


class CorrelationStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]

        if len(value_columns) < 2:
            self._description = "需要至少两个指标列才能进行相关性分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        col_x, col_y = value_columns[0], value_columns[1]
        df = self._df.dropna(subset=[col_x, col_y]).copy()

        if len(df) < 3:
            self._description = "数据量不足（至少需要3行），无法计算相关系数"
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 零方差检测
        std_x, std_y = df[col_x].std(), df[col_y].std()
        if pd.isna(std_x) or std_x < 1e-10 or pd.isna(std_y) or std_y < 1e-10:
            zero_cols = []
            if pd.isna(std_x) or std_x < 1e-10:
                zero_cols.append(col_x)
            if pd.isna(std_y) or std_y < 1e-10:
                zero_cols.append(col_y)
            self._description = {
                "error": "指标方差为0（所有值相同），无法计算相关系数",
                "zero_variance_columns": zero_cols,
                "summary": f"{'、'.join(zero_cols)} 的方差为0，无法计算相关系数",
            }
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 使用 scipy 计算 pearsonr，获得 p-value
        corr, p_value = stats.pearsonr(df[col_x], df[col_y])
        abs_corr = abs(corr)

        # 4级强度分类
        if abs_corr >= 0.7:
            strength = "强"
        elif abs_corr >= 0.5:
            strength = "中等"
        elif abs_corr >= 0.3:
            strength = "弱"
        else:
            strength = "极弱"
        direction = "正" if corr > 0 else "负"

        self._filter_data = df
        self._description = {
            "correlation": round(float(corr), 4),
            "p_value": round(float(p_value), 6),
            "strength": strength,
            "direction": direction,
            "summary": f"{col_x} 与 {col_y} 呈{strength}{direction}相关（r={corr:.4f}, p={p_value:.4f}）",
        }
        self._significance_score = float(np.clip(abs_corr, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            PINK,
            base_title,
            base_tooltip,
        )

        x_vals = df[col_x].values.astype(float)
        y_vals = df[col_y].values.astype(float)
        # 趋势线
        slope_c, intercept_c = np.polyfit(x_vals, y_vals, 1)
        x_min, x_max = float(x_vals.min()), float(x_vals.max())

        self._chart_configs = {
            "chart_type": "scatter",
            "title": base_title(f"{col_x} vs {col_y} (r={corr:.3f}, p={p_value:.4f})"),
            "tooltip": base_tooltip("item"),
            "grid": {"left": "12%", "right": "6%", "bottom": "14%", "top": "16%"},
            "xAxis": {"type": "value", "name": col_x, "nameTextStyle": {"fontSize": 11}},
            "yAxis": {"type": "value", "name": col_y, "nameTextStyle": {"fontSize": 11}},
            "series": [
                {
                    "name": "数据点",
                    "type": "scatter",
                    "data": list(zip(df[col_x].round(2).tolist(), df[col_y].round(2).tolist())),
                    "itemStyle": {"color": BLUE, "opacity": 0.6},
                    "symbolSize": 6,
                },
                {
                    "name": f"趋势线 r={corr:.3f}",
                    "type": "line",
                    "data": [
                        [round(x_min, 2), round(slope_c * x_min + intercept_c, 2)],
                        [round(x_max, 2), round(slope_c * x_max + intercept_c, 2)],
                    ],
                    "lineStyle": {"color": PINK, "type": "dashed", "width": 2},
                    "symbol": "none",
                },
            ],
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11}},
        }
