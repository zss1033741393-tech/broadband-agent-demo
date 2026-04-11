"""
归因分析：计算各分组对整体指标的贡献度，找出主要贡献因素。
"""

import numpy as np

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class AttributionStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        grouped = self._df.groupby(group_column)[col].agg(["mean", "sum", "count"])
        overall_mean = self._df[col].mean()

        # 每组对整体均值的偏差贡献 = (组均值 - 总均值) * 组样本占比
        total_count = grouped["count"].sum()
        grouped["weight"] = grouped["count"] / total_count
        grouped["deviation"] = grouped["mean"] - overall_mean
        grouped["contribution"] = grouped["deviation"] * grouped["weight"]

        # 归一化贡献度为百分比
        abs_sum = grouped["contribution"].abs().sum()
        if abs_sum > 0:
            grouped["contribution_pct"] = (grouped["contribution"] / abs_sum * 100).round(2)
        else:
            grouped["contribution_pct"] = 0.0

        grouped = grouped.sort_values("contribution").reset_index()
        self._filter_data = grouped

        # 找到贡献最大的负向因素
        top_neg = grouped[grouped["contribution"] < 0].head(3)
        if not top_neg.empty:
            names = ", ".join(top_neg[group_column].astype(str).tolist())
            self._description = f"对 {col} 拉低作用最大的分组: {names}"
        else:
            self._description = f"{col} 在各分组间无明显负向差异"

        # 显著性：最大贡献占比的绝对值
        max_contrib = grouped["contribution_pct"].abs().max()
        self._significance_score = float(np.clip(max_contrib / 100, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            HIGHLIGHT_GREEN,
            HIGHLIGHT_RED,
            PALETTE,
            base_title,
            base_tooltip,
            truncate_labels,
        )

        labels = truncate_labels(grouped[group_column].astype(str).tolist())
        pct_vals = grouped["contribution_pct"].tolist()
        # 柱状图颜色：负贡献红色，正贡献绿色
        bar_colors = [HIGHLIGHT_RED if v < 0 else HIGHLIGHT_GREEN for v in pct_vals]
        # 饼图数据：取绝对值
        pie_data = [
            {"name": l, "value": round(abs(v), 2)} for l, v in zip(labels, pct_vals) if abs(v) >= 1
        ]

        self._chart_configs = {
            "chart_type": "attribution",
            "title": base_title(f"{col} 归因分析"),
            "tooltip": base_tooltip("item"),
            "grid": {"left": "5%", "right": "55%", "bottom": "14%", "top": "16%"},
            "xAxis": {
                "type": "value",
                "name": "贡献度(%)",
                "nameTextStyle": {"fontSize": 11},
                "gridIndex": 0,
            },
            "yAxis": {
                "type": "category",
                "data": labels,
                "inverse": True,
                "axisLabel": {"fontSize": 10},
                "gridIndex": 0,
            },
            "series": [
                {
                    "name": "贡献度",
                    "type": "bar",
                    "data": [
                        {"value": round(v, 2), "itemStyle": {"color": c}}
                        for v, c in zip(pct_vals, bar_colors)
                    ],
                    "barMaxWidth": 24,
                    "xAxisIndex": 0,
                    "yAxisIndex": 0,
                    "label": {
                        "show": True,
                        "position": "right",
                        "fontSize": 10,
                        "formatter": "{c}%",
                    },
                },
                {
                    "name": "占比",
                    "type": "pie",
                    "radius": ["30%", "55%"],
                    "center": ["75%", "50%"],
                    "data": pie_data[:8],
                    "label": {"fontSize": 10, "formatter": "{b}\n{d}%"},
                    "itemStyle": {"borderRadius": 4, "borderWidth": 1, "borderColor": "#fff"},
                    "color": PALETTE,
                },
            ],
        }
