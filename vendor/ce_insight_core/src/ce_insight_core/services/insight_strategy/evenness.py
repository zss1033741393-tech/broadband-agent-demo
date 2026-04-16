"""
均匀度分析：评估指标在各分组中分布的均匀程度（基于基尼系数）。
"""

import numpy as np

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy

_DEFAULT_TOP_K = 20  # filter_data / chart 最多保留行数（按指标值降序）


class EvennessStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        grouped = self._df.groupby(group_column)[col].mean().dropna()

        if len(grouped) < 2:
            self._description = "分组数不足，无法进行均匀度分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        values = grouped.values.astype(float)

        # 计算基尼系数
        gini = self._gini_coefficient(values)

        # 变异系数
        cv = float(np.std(values) / np.mean(values)) if np.mean(values) > 0 else 0

        result_df = grouped.reset_index()
        result_df.columns = [group_column, col]
        result_df = result_df.sort_values(col, ascending=False)
        self._filter_data = result_df.head(_DEFAULT_TOP_K)

        if gini < 0.2:
            level = "分布较均匀"
        elif gini < 0.4:
            level = "分布有一定差异"
        else:
            level = "分布很不均匀"

        self._description = {
            "gini": round(gini, 4),
            "cv": round(cv, 4),
            "level": level,
            "summary": f"{col} 在各 {group_column} 间{level}，"
            f"基尼系数 {gini:.4f}，变异系数 {cv:.4f}",
        }
        self._significance_score = float(np.clip(gini, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            ORANGE,
            base_grid,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        display_df = result_df.head(_DEFAULT_TOP_K)
        display_labels = truncate_labels(display_df[group_column].astype(str).tolist())
        mean_val = round(float(np.mean(values)), 2)
        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{col} 均匀度分析（基尼={gini:.3f}）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "xAxis": {
                "type": "category",
                "data": display_labels,
                "axisLabel": rotated_axis_label(30)
                if len(display_labels) > 8
                else {"fontSize": 11},
            },
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": [
                {
                    "type": "bar",
                    "name": col,
                    "data": display_df[col].round(2).tolist(),
                    "itemStyle": {"color": BLUE},
                    "barMaxWidth": 40,
                    "markLine": {
                        "data": [{"yAxis": mean_val, "name": "均值"}],
                        "lineStyle": {"color": ORANGE, "type": "dashed", "width": 2},
                        "label": {"formatter": f"均值: {mean_val}", "fontSize": 10},
                        "symbol": "none",
                    },
                }
            ],
        }

    @staticmethod
    def _gini_coefficient(values: np.ndarray) -> float:
        """计算基尼系数"""
        sorted_vals = np.sort(values)
        n = len(sorted_vals)
        index = np.arange(1, n + 1)
        return float((2 * np.sum(index * sorted_vals) / (n * np.sum(sorted_vals))) - (n + 1) / n)
