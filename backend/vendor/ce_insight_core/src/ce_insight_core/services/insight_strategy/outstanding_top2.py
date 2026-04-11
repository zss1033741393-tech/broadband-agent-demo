"""
Top2 突出分析：
- 单 measure + 分组：前两名 group 与其余的差距（_execute_single）
- 多 measure + 无/单 group：找均值最高的前两个 measure（_execute_measure_compare）
- 多 measure + 多 group（矩阵模式）：每个 group 输出各自的 top2 measures（_execute_matrix）
"""

from collections import Counter

import numpy as np
import pandas as pd

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class OutstandingTop2Strategy(InsightStrategy):
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
    # 单 measure：前两名 group 与其余的差距
    # ------------------------------------------------------------------
    def _execute_single(self, col: str, group_column: str) -> None:
        grouped = self._df.groupby(group_column)[col].mean().dropna()

        if len(grouped) < 2:
            self._description = "分组数不足（<2），无法进行 Top2 分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        sorted_vals = grouped.sort_values(ascending=False)
        top2 = sorted_vals.iloc[:2]
        rest = sorted_vals.iloc[2:]

        top2_mean = float(top2.mean())
        rest_mean = float(rest.mean()) if len(rest) > 0 else top2_mean
        gap = top2_mean - rest_mean

        total = float(grouped.sum())
        top2_share = float(top2.sum()) / total if total > 0 else 0

        result_df = sorted_vals.reset_index()
        result_df.columns = [group_column, col]
        result_df["is_top2"] = [True, True] + [False] * max(0, len(sorted_vals) - 2)
        self._filter_data = result_df

        top2_names = ", ".join(top2.index.astype(str).tolist())
        self._description = {
            "top1_group": str(top2.index[0]),
            "top2_group": str(top2.index[1]),
            "top2_groups": top2.index.tolist(),
            "top2_mean": round(top2_mean, 2),
            "rest_mean": round(rest_mean, 2),
            "gap": round(gap, 2),
            "top2_share": round(top2_share, 4),
            "summary": f"前两名 ({top2_names}) 均值 {top2_mean:.2f}，"
            f"领先其余 {gap:.2f}，占总量 {top2_share:.1%}",
        }
        self._significance_score = float(np.clip(top2_share, 0, 1))

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
        colors = [HIGHLIGHT_RED if t else BLUE for t in display_df["is_top2"]]
        self._chart_configs = {
            "chart_type": "bar",
            "title": base_title(f"{col} Top2 突出分析"),
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
                        {"value": round(v, 2), "itemStyle": {"color": c}}
                        for v, c in zip(display_df[col].tolist(), colors)
                    ],
                    "barMaxWidth": 40,
                }
            ],
        }

    # ------------------------------------------------------------------
    # 多 measure + 无/单 group：均值最高的前两个 measure（最突出的两个异常维度）
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

        measure_means = agg_df.mean().sort_values(ascending=False)
        top2_measures = measure_means.iloc[:2]
        rest_measures = measure_means.iloc[2:]

        top2_avg = float(top2_measures.mean())
        rest_avg = float(rest_measures.mean()) if len(rest_measures) > 0 else top2_avg
        gap = top2_avg - rest_avg

        top2_names = top2_measures.index.tolist()
        result_df = agg_df.reset_index()
        self._filter_data = result_df

        # 注意：故意不用 top1_group/top2_group 作为 top-level key，
        # 因为这是 measure 名，不是 group 值，会污染 _extract_entities
        self._description = {
            "top2_measures": top2_names,
            "top2_avg": round(top2_avg, 2),
            "rest_avg": round(rest_avg, 2),
            "gap": round(gap, 2),
            "measure_means": {m: round(float(v), 2) for m, v in measure_means.items()},
            "summary": (
                f"最突出的两个指标：{', '.join(top2_names)}，"
                f"均值（{top2_avg:.2f}）高出其余指标均值 {gap:.2f}"
            ),
        }

        total = float(measure_means.sum())
        top2_share = float(top2_measures.sum()) / total if total > 0 else 0
        self._significance_score = float(np.clip(top2_share, 0, 1))

        groups = truncate_labels(agg_df.index.astype(str).tolist())
        colors = PALETTE[: len(value_columns)]

        series = []
        for i, col in enumerate(value_columns):
            if col not in agg_df.columns:
                continue
            color = HIGHLIGHT_RED if col in top2_names else colors[i % len(colors)]
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
            "title": base_title(f"各指标对比（Top2: {', '.join(top2_names)}）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "legend": {"show": True, "top": 30, "textStyle": {"fontSize": 10}},
            "xAxis": {"type": "category", "data": groups, "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }

    # ------------------------------------------------------------------
    # 多 measure + 多 group：每个 group 各自的 top2 measures（矩阵模式）
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

        per_group_top2: dict[str, dict] = {}
        top1_measures: list[str] = []
        top2_measures: list[str] = []
        group_labels: list[str] = []

        for group_key, row in agg_df.iterrows():
            row_clean = row.dropna()
            if row_clean.empty:
                continue
            sorted_row = row_clean.sort_values(ascending=False)
            top1_col = str(sorted_row.index[0])
            top1_val = float(sorted_row.iloc[0])
            top2_col = str(sorted_row.index[1]) if len(sorted_row) >= 2 else ""
            top2_val = float(sorted_row.iloc[1]) if len(sorted_row) >= 2 else float("nan")

            group_str = str(group_key)
            per_group_top2[group_str] = {
                "top1_measure": top1_col,
                "top1_value": round(top1_val, 4),
                "top2_measure": top2_col,
                "top2_value": round(top2_val, 4) if not pd.isna(top2_val) else None,
            }
            group_labels.append(group_str)
            top1_measures.append(top1_col)
            if top2_col:
                top2_measures.append(top2_col)

        if not per_group_top2:
            self._description = "无有效数据可分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        # filter_data：每个 group 一行
        rows = []
        for group_key, row in agg_df.iterrows():
            row_dict: dict = {group_column: str(group_key)}
            info = per_group_top2.get(str(group_key))
            if info:
                row_dict["top1_measure"] = info["top1_measure"]
                row_dict["top1_value"] = info["top1_value"]
                row_dict["top2_measure"] = info["top2_measure"]
                row_dict["top2_value"] = info["top2_value"]
            for col in value_columns:
                if col in agg_df.columns:
                    v = row.get(col)
                    row_dict[col] = round(float(v), 4) if pd.notna(v) else None
            rows.append(row_dict)

        result_df = pd.DataFrame(rows)
        self._filter_data = result_df

        # 集中度：用 top1 出现频率
        counter = Counter(top1_measures)
        most_common_top1, most_common_count = counter.most_common(1)[0]
        n_groups = len(per_group_top2)
        concentration = most_common_count / n_groups

        self._significance_score = float(np.clip(concentration, 0.3, 1.0))

        summary_lines = [
            f"对 {n_groups} 个 {group_column} 做多指标对比，每个分组的 Top2 指标如下："
        ]
        for g, info in list(per_group_top2.items())[:8]:
            t1 = f"{info['top1_measure']}={info['top1_value']}"
            t2 = f", {info['top2_measure']}={info['top2_value']}" if info["top2_measure"] else ""
            summary_lines.append(f"- {g}: {t1}{t2}")
        if most_common_count >= 2:
            summary_lines.append(
                f"其中 {most_common_count}/{n_groups} 个分组的第一名都是 {most_common_top1}。"
            )

        self._description = {
            "mode": "matrix",
            "per_group_top2": per_group_top2,
            "most_common_top1": most_common_top1,
            "most_common_count": most_common_count,
            "n_groups": n_groups,
            "summary": "\n".join(summary_lines),
        }

        # 图表：每个 group 的 top1 和 top2 cell 都标红（top1 深红，top2 柔红）
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
                info = per_group_top2.get(group_key, {})
                if info.get("top1_measure") == col:
                    cell_color = HIGHLIGHT_RED
                elif info.get("top2_measure") == col:
                    cell_color = "#f2918c"  # 珊瑚粉（次高亮）
                else:
                    cell_color = base_color
                data_points.append(
                    {
                        "value": val,
                        "itemStyle": {"color": cell_color},
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
            "title": base_title(f"各 {group_column} 的 Top2 维度（各自前两名高亮）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "legend": {"show": True, "top": 30, "textStyle": {"fontSize": 10}},
            "xAxis": {"type": "category", "data": groups, "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }
