"""
突出最大值：
- 单 measure + 分组：找哪个 group 的该指标最高（_execute_single）
- 多 measure + 无/单 group：找哪个 measure 整体均值最高（_execute_measure_compare）
- 多 measure + 多 group（矩阵模式）：每个 group 输出各自最突出的 measure（_execute_matrix）
"""

from collections import Counter

import numpy as np
import pandas as pd

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class OutstandingMaxStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")

        if len(value_columns) == 1:
            self._execute_single(value_columns[0], group_column)
            return

        n_groups = (
            self._df[group_column].nunique()
            if group_column and group_column in self._df.columns
            else 0
        )
        if n_groups >= 2:
            self._execute_matrix(value_columns, group_column)
        else:
            self._execute_measure_compare(value_columns, group_column)

    # ------------------------------------------------------------------
    # 单 measure：哪个 group 的该指标最高
    # ------------------------------------------------------------------
    def _execute_single(self, col: str, group_column: str) -> None:
        grouped = self._df.groupby(group_column)[col].mean().dropna()

        if len(grouped) < 2:
            self._description = "分组数不足"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        sorted_vals = grouped.sort_values(ascending=False)
        max_group = sorted_vals.index[0]
        max_val = float(sorted_vals.iloc[0])
        second_val = float(sorted_vals.iloc[1])
        overall_mean = float(grouped.mean())
        std_val = float(grouped.std())

        gap = max_val - second_val
        z_score = (max_val - overall_mean) / std_val if std_val > 0 else 0

        result_df = sorted_vals.reset_index()
        result_df.columns = [group_column, col]
        self._filter_data = result_df

        self._description = {
            "max_group": str(max_group),
            "max_value": round(max_val, 2),
            "second_value": round(second_val, 2),
            "gap": round(gap, 2),
            "z_score": round(float(z_score), 4),
            "summary": f"{col} 最大值出现在 {max_group}（{max_val:.2f}），"
            f"高出第二名 {gap:.2f}，z-score={z_score:.2f}",
        }
        self._significance_score = float(np.clip(abs(z_score) / 3, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            HIGHLIGHT_RED,
            base_grid,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        top_n = 10
        display_df = result_df.head(top_n)
        display_labels = truncate_labels(display_df[group_column].astype(str).tolist())
        display_vals = display_df[col].round(2).tolist()
        colors = [HIGHLIGHT_RED if i == 0 else BLUE for i in range(len(display_vals))]
        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{col} 最大值分析 (Top{min(top_n, len(result_df))})"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "xAxis": {
                "type": "category",
                "data": display_labels,
                "axisLabel": rotated_axis_label(30),
            },
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": [
                {
                    "type": "bar",
                    "data": [
                        {"value": v, "itemStyle": {"color": c}}
                        for v, c in zip(display_vals, colors)
                    ],
                    "barMaxWidth": 40,
                }
            ],
        }

    # ------------------------------------------------------------------
    # 多 measure + 无/单 group：哪个 measure 整体均值最高（横向维度对比）
    # ------------------------------------------------------------------
    def _execute_measure_compare(self, value_columns: list[str], group_column: str) -> None:
        from ce_insight_core.services.insight_strategy.chart_style import (
            HIGHLIGHT_RED,
            PALETTE,
            base_grid,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        if group_column and group_column in self._df.columns:
            agg_df = self._df.groupby(group_column)[value_columns].mean().dropna(how="all")
        else:
            agg_df = self._df[value_columns].mean().to_frame().T
            agg_df.index = ["all"]

        if len(agg_df) == 0:
            self._description = "聚合后数据为空"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        measure_means = agg_df.mean()
        max_measure = str(measure_means.idxmax())
        max_val = float(measure_means.max())

        std_across = float(measure_means.std())
        overall_mean_of_measures = float(measure_means.mean())
        z_score = (max_val - overall_mean_of_measures) / std_across if std_across > 0 else 0

        result_df = agg_df.reset_index()
        self._filter_data = result_df

        self._description = {
            "max_measure": max_measure,
            "max_value": round(max_val, 2),
            "measure_means": {m: round(float(v), 2) for m, v in measure_means.items()},
            "z_score": round(float(z_score), 4),
            "summary": (
                f"在 {len(value_columns)} 个指标中，{max_measure} 均值最高（{max_val:.2f}），"
                f"z-score={z_score:.2f}，是最突出的异常维度"
            ),
        }
        self._significance_score = float(np.clip(abs(z_score) / 3, 0, 1))

        groups = truncate_labels(agg_df.index.astype(str).tolist())
        colors = PALETTE[: len(value_columns)]

        series = []
        for i, col in enumerate(value_columns):
            if col not in agg_df.columns:
                continue
            color = HIGHLIGHT_RED if col == max_measure else colors[i % len(colors)]
            series.append(
                {
                    "name": col,
                    "type": "bar",
                    "data": [
                        round(float(v), 2) if not pd.isna(v) else 0 for v in agg_df[col].tolist()
                    ],
                    "itemStyle": {"color": color},
                    "barMaxWidth": 30,
                }
            )

        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"各指标对比（最高: {max_measure}）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "legend": {"show": True, "top": 30, "textStyle": {"fontSize": 10}},
            "xAxis": {"type": "category", "data": groups, "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }

    # ------------------------------------------------------------------
    # 多 measure + 多 group：每个 group 各自最突出的 measure（矩阵模式）
    # ------------------------------------------------------------------
    def _execute_matrix(self, value_columns: list[str], group_column: str) -> None:
        from ce_insight_core.services.insight_strategy.chart_style import (
            HIGHLIGHT_RED,
            PALETTE,
            base_grid,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        agg_df = self._df.groupby(group_column)[value_columns].mean().dropna(how="all")

        if len(agg_df) == 0:
            self._description = "聚合后数据为空"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        per_group_best: dict[str, dict] = {}
        best_measures: list[str] = []
        group_labels: list[str] = []

        for group_key, row in agg_df.iterrows():
            row_clean = row.dropna()
            if row_clean.empty:
                continue
            best_col = str(row_clean.idxmax())
            best_val = float(row_clean.max())
            group_str = str(group_key)
            per_group_best[group_str] = {
                "measure": best_col,
                "value": round(best_val, 4),
            }
            group_labels.append(group_str)
            best_measures.append(best_col)

        if not per_group_best:
            self._description = "无有效数据可分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        # filter_data：每个 group 一行
        rows = []
        for group_key, row in agg_df.iterrows():
            row_dict: dict = {group_column: str(group_key)}
            best_info = per_group_best.get(str(group_key))
            if best_info:
                row_dict["best_measure"] = best_info["measure"]
                row_dict["best_value"] = best_info["value"]
            for col in value_columns:
                if col in agg_df.columns:
                    v = row.get(col)
                    row_dict[col] = round(float(v), 4) if pd.notna(v) else None
            rows.append(row_dict)

        result_df = pd.DataFrame(rows)
        self._filter_data = result_df

        counter = Counter(best_measures)
        most_common_best, most_common_count = counter.most_common(1)[0]
        n_groups = len(per_group_best)
        concentration = most_common_count / n_groups

        self._significance_score = float(np.clip(concentration, 0.3, 1.0))

        summary_lines = [
            f"对 {n_groups} 个 {group_column} 做多指标对比，每个分组的最突出维度如下："
        ]
        for g, info in list(per_group_best.items())[:8]:
            summary_lines.append(f"- {g}: {info['measure']} = {info['value']}")
        if most_common_count >= 2:
            summary_lines.append(
                f"其中 {most_common_count}/{n_groups} 个分组的最突出维度都是 {most_common_best}，"
                f"是共同的异常维度。"
            )
        else:
            summary_lines.append("各分组的最突出维度各不相同，无共同异常。")

        self._description = {
            "mode": "matrix",
            "per_group_best": per_group_best,
            "most_common_best": most_common_best,
            "most_common_count": most_common_count,
            "n_groups": n_groups,
            "summary": "\n".join(summary_lines),
        }

        # 图表：每个 group 各自最高 cell 标红
        groups = truncate_labels(group_labels)
        colors = PALETTE

        series = []
        for i, col in enumerate(value_columns):
            if col not in agg_df.columns:
                continue
            base_color = colors[i % len(colors)]
            data_points = []
            for group_key in group_labels:
                v = agg_df.loc[group_key, col] if group_key in agg_df.index else None
                val = round(float(v), 4) if pd.notna(v) else 0
                is_best = per_group_best.get(group_key, {}).get("measure") == col
                data_points.append(
                    {
                        "value": val,
                        "itemStyle": {"color": HIGHLIGHT_RED if is_best else base_color},
                    }
                )
            series.append(
                {
                    "name": col,
                    "type": "bar",
                    "data": data_points,
                    "barMaxWidth": 30,
                }
            )

        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"各 {group_column} 的维度对比（各自最高标红）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "legend": {"show": True, "top": 30, "textStyle": {"fontSize": 10}},
            "xAxis": {"type": "category", "data": groups, "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }
