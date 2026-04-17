"""
归因分析：计算贡献度，找出主要贡献因素。

支持两种模式（由 value_columns 数量自动切换）：

- **单 measure 模式** (1 个 value_column)：
  分析不同 group 对**某个指标**的偏差贡献（哪些 group 拉低/拉高了整体均值）。
  典型场景："哪些 PON 口拉低了 CEI_score 的均值？"

- **多 measure 模式** (≥2 个 value_columns)：
  把数据聚合（多行取均值或单行直接用）成"一个主体"，分析这个主体里
  **哪个 measure 占主导**。典型场景：已经定位到 1~几个 PON 口后，
  想看"对它的总分而言，8 个维度里哪个最关键"。
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy

_MIN_ATTRIBUTION_THRESHOLD = 0.5  # 多 measure 模式下，主导贡献者的判定阈值
_DEFAULT_TOP_K = 20  # filter_data / chart 最多保留行数（贡献度绝对值最大优先）


class AttributionStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")

        if not value_columns:
            self._description = {"summary": "未提供任何 value_columns，无法进行归因分析"}
            self._significance_score = 0.0
            self._filter_data = pd.DataFrame()
            return

        if len(value_columns) == 1:
            self._execute_single(value_columns[0], group_column)
        else:
            self._execute_multi_measure(value_columns, group_column)

    # ------------------------------------------------------------------
    # 单 measure 模式：跨 group 的偏差贡献分析
    # ------------------------------------------------------------------
    def _execute_single(self, col: str, group_column: str) -> None:
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
        # 截取贡献度绝对值最大的前 K 行（负向在前，正向在后）
        self._filter_data = grouped.head(_DEFAULT_TOP_K)

        # 找到贡献最大的负向因素
        top_neg = grouped[grouped["contribution"] < 0].head(3)
        if not top_neg.empty:
            neg_names = top_neg[group_column].astype(str).tolist()
            neg_pcts = [round(float(v), 2) for v in top_neg["contribution_pct"].tolist()]
            self._description = {
                "mode": "single_measure",
                "top_neg_groups": neg_names,
                "top_neg_pcts": neg_pcts,
                "max_neg_contribution_pct": neg_pcts[0],
                "summary": f"对 {col} 拉低作用最大的分组: {', '.join(neg_names)}",
            }
        else:
            self._description = {
                "mode": "single_measure",
                "top_neg_groups": [],
                "top_neg_pcts": [],
                "max_neg_contribution_pct": 0.0,
                "summary": f"{col} 在各分组间无明显负向差异",
            }

        # 显著性：最大贡献占比的绝对值
        max_contrib = grouped["contribution_pct"].abs().max()
        self._significance_score = float(np.clip(max_contrib / 100, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            HIGHLIGHT_GREEN,
            HIGHLIGHT_RED,
            base_title,
            base_tooltip,
            truncate_labels,
        )

        display_grouped = grouped.head(_DEFAULT_TOP_K)
        labels = truncate_labels(display_grouped[group_column].astype(str).tolist())
        pct_vals = display_grouped["contribution_pct"].tolist()
        # 柱状图颜色：负贡献红色（拉低均值），正贡献绿色（拉高均值）
        bar_colors = [HIGHLIGHT_RED if v < 0 else HIGHLIGHT_GREEN for v in display_grouped["contribution_pct"]]

        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{col} 归因分析"),
            "tooltip": base_tooltip("item"),
            "grid": {"left": "15%", "right": "10%", "bottom": "14%", "top": "16%"},
            "xAxis": {
                "type": "value",
                "name": "贡献度(%)",
                "nameTextStyle": {"fontSize": 11},
            },
            "yAxis": {
                "type": "category",
                "data": labels,
                "inverse": True,
                "axisLabel": {"fontSize": 10},
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
                    "label": {
                        "show": True,
                        "position": "right",
                        "fontSize": 10,
                        "formatter": "{c}%",
                    },
                },
            ],
        }

    # ------------------------------------------------------------------
    # 多 measure 模式：聚合后看每个指标的占比
    # ------------------------------------------------------------------
    def _execute_multi_measure(self, value_columns: list[str], group_column: str) -> None:
        df = self._df.copy()

        if len(df) == 0:
            self._description = {
                "mode": "multi_measure",
                "summary": "无有效数据进行多指标归因分析",
            }
            self._significance_score = 0.0
            self._filter_data = pd.DataFrame()
            return

        # 聚合策略：多行取均值，单行直接用
        if len(df) > 1:
            row_data = df[value_columns].mean()
            if group_column and group_column in df.columns:
                group_label = f"{group_column} 聚合 ({len(df)} 行)"
            else:
                group_label = f"全局聚合 ({len(df)} 行)"
        else:
            row_data = df[value_columns].iloc[0]
            if group_column and group_column in df.columns:
                group_label = str(df[group_column].iloc[0])
            else:
                group_label = "单行数据"

        total = float(row_data.sum())

        if total == 0:
            result_df = pd.DataFrame(
                [
                    {"measure": col, "value": 0.0, "contribution": 0.0, "contribution_pct": 0.0}
                    for col in value_columns
                ]
            )
            self._filter_data = result_df
            self._description = {
                "mode": "multi_measure",
                "group_label": group_label,
                "n_measures": len(value_columns),
                "total": 0.0,
                "summary": f"{group_label}: 总分为 0，无法计算各指标贡献占比",
            }
            self._significance_score = 0.0
            return

        # 计算每个 measure 的贡献度
        rows = []
        for col in value_columns:
            v = float(row_data[col])
            contribution = v / total
            rows.append(
                {
                    "measure": col,
                    "value": round(v, 4),
                    "contribution": round(contribution, 4),
                    "contribution_pct": round(contribution * 100, 2),
                }
            )

        # 按 |贡献度| 降序排
        result_df = pd.DataFrame(rows)
        result_df["_abs"] = result_df["contribution"].abs()
        result_df = result_df.sort_values("_abs", ascending=False).reset_index(drop=True)
        result_df = result_df.drop(columns=["_abs"])

        self._filter_data = result_df

        # 显著性：最大 |贡献度| 通过 norm.cdf 映射到 [0.5, 1)
        max_contribution = float(result_df["contribution"].abs().max())
        self._significance_score = float(norm.cdf(max_contribution))

        # 主要贡献者
        top_row = result_df.iloc[0]
        top_measure = str(top_row["measure"])
        top_value = float(top_row["value"])
        top_pct = float(top_row["contribution_pct"])
        is_significant = max_contribution >= _MIN_ATTRIBUTION_THRESHOLD

        if is_significant:
            summary = (
                f"{group_label}: {len(value_columns)} 个指标中 {top_measure} 贡献最大 "
                f"({top_pct:.1f}%, 值={top_value:.2f})，是主要贡献因素"
            )
        else:
            summary = (
                f"{group_label}: {len(value_columns)} 个指标中最大贡献为 {top_measure} "
                f"({top_pct:.1f}%)，未达到主导阈值 {_MIN_ATTRIBUTION_THRESHOLD * 100:.0f}%，"
                f"各指标贡献较为均衡"
            )

        self._description = {
            "mode": "multi_measure",
            "group_label": group_label,
            "n_measures": len(value_columns),
            "total": round(total, 2),
            "top_measure": top_measure,
            "top_value": round(top_value, 2),
            "top_contribution_pct": round(top_pct, 2),
            "is_significant": is_significant,
            "summary": summary,
        }

        self._build_multi_measure_chart(result_df, group_label, top_measure)

    def _build_multi_measure_chart(
        self, result_df: pd.DataFrame, group_label: str, top_measure: str
    ) -> None:
        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            HIGHLIGHT_RED,
            base_title,
            base_tooltip,
            truncate_labels,
        )

        measure_labels = truncate_labels(result_df["measure"].astype(str).tolist())
        pct_vals = result_df["contribution_pct"].tolist()
        # 主要贡献者红色高亮，其他蓝色
        bar_colors = [
            HIGHLIGHT_RED if str(m) == top_measure else BLUE for m in result_df["measure"]
        ]

        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{group_label} 多指标归因"),
            "tooltip": base_tooltip("item"),
            "grid": {"left": "20%", "right": "10%", "bottom": "10%", "top": "16%"},
            "xAxis": {
                "type": "value",
                "name": "贡献度(%)",
                "nameTextStyle": {"fontSize": 11},
            },
            "yAxis": {
                "type": "category",
                "data": measure_labels,
                "inverse": True,
                "axisLabel": {"fontSize": 10},
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
                    "label": {
                        "show": True,
                        "position": "right",
                        "fontSize": 10,
                        "formatter": "{c}%",
                    },
                },
            ],
        }
