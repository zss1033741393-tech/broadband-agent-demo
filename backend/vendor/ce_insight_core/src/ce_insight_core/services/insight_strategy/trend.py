"""
趋势分析：对时序数据做线性回归，判断上升/下降趋势及显著性。
"""

import numpy as np

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class TrendStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        df = self._df.sort_values(group_column).copy()
        df = df.dropna(subset=[col, group_column])

        # 用序号做线性回归
        x = np.arange(len(df), dtype=float)
        y = df[col].values.astype(float)

        if len(x) < 3:
            self._description = "数据点不足，无法进行趋势分析"
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 最小二乘线性回归
        slope, intercept = np.polyfit(x, y, 1)
        y_pred = slope * x + intercept
        df["trend_line"] = y_pred

        # 计算 R²
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        self._filter_data = df

        direction = "上升" if slope > 0 else "下降"
        self._description = {
            "direction": direction,
            "slope": round(float(slope), 4),
            "r_squared": round(float(r_squared), 4),
            "summary": f"{col} 呈{direction}趋势，斜率 {slope:.4f}，R²={r_squared:.4f}",
        }

        # 显著性：R² 值直接作为显著性
        self._significance_score = float(np.clip(r_squared, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            HIGHLIGHT_RED,
            ORANGE,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        time_labels = truncate_labels(df[group_column].astype(str).tolist(), 12)

        # 检测突变点（相邻差值超过2倍标准差）
        diffs = np.abs(np.diff(y))
        diff_threshold = np.mean(diffs) + 2 * np.std(diffs) if len(diffs) > 1 else float("inf")
        mutation_points = [{"xAxis": int(i + 1)} for i, d in enumerate(diffs) if d > diff_threshold]

        self._chart_configs = {
            "chart_type": "line",
            "title": base_title(f"{col} 趋势分析 (R²={r_squared:.3f})"),
            "tooltip": base_tooltip("axis"),
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11}},
            "grid": {"left": "10%", "right": "6%", "bottom": "18%", "top": "16%"},
            "xAxis": {
                "type": "category",
                "data": time_labels,
                "axisLabel": rotated_axis_label(30) if len(time_labels) > 8 else {"fontSize": 11},
            },
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": [
                {
                    "name": "实际值",
                    "type": "line",
                    "smooth": True,
                    "data": [round(float(v), 2) for v in y],
                    "itemStyle": {"color": BLUE},
                    "lineStyle": {"color": BLUE},
                    "symbolSize": 6,
                    "markPoint": {
                        "data": mutation_points[:3],
                        "symbol": "pin",
                        "symbolSize": 30,
                        "itemStyle": {"color": ORANGE},
                    }
                    if mutation_points
                    else {},
                },
                {
                    "name": "趋势线",
                    "type": "line",
                    "data": y_pred.round(2).tolist(),
                    "lineStyle": {"type": "dashed", "color": HIGHLIGHT_RED},
                    "itemStyle": {"color": HIGHLIGHT_RED},
                    "symbol": "none",
                },
            ],
        }
