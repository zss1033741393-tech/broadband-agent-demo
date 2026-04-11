"""
突出最小值：
- 单 measure + 分组：找哪个 group 的该指标最低（_execute_single）
- 多 measure + 无/单 group：找哪个 measure 整体均值最低（_execute_measure_compare）
- 多 measure + 多 group（矩阵模式）：每个 group 输出各自最差的 measure（_execute_matrix）
"""

from collections import Counter

import numpy as np
import pandas as pd

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class OutstandingMinStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")

        if len(value_columns) == 1:
            self._execute_single(value_columns[0], group_column)
            return

        # 多 measure 场景
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
    # 单 measure：哪个 group 的该指标最低
    # ------------------------------------------------------------------
    def _execute_single(self, col: str, group_column: str) -> None:
        grouped = self._df.groupby(group_column)[col].mean().dropna()

        if len(grouped) < 2:
            self._description = "分组数不足"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        sorted_vals = grouped.sort_values(ascending=True)
        min_group = sorted_vals.index[0]
        min_val = float(sorted_vals.iloc[0])
        second_val = float(sorted_vals.iloc[1])
        overall_mean = float(grouped.mean())
        std_val = float(grouped.std())

        gap = second_val - min_val
        z_score = (overall_mean - min_val) / std_val if std_val > 0 else 0

        result_df = sorted_vals.reset_index()
        result_df.columns = [group_column, col]
        self._filter_data = result_df

        self._description = {
            "min_group": str(min_group),
            "min_value": round(min_val, 2),
            "second_value": round(second_val, 2),
            "gap": round(gap, 2),
            "z_score": round(float(z_score), 4),
            "summary": f"{col} 最小值出现在 {min_group}（{min_val:.2f}），"
            f"低于第二名 {gap:.2f}，z-score={z_score:.2f}",
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
            "title": base_title(f"{col} 最小值分析 (Top{min(top_n, len(result_df))})"),
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
    # 多 measure + 无/单 group：哪个 measure 整体均值最低（横向维度对比）
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

        # 按 group 聚合（无 group 时退化为全表聚合）
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

        # 每个 measure 的全局均值（跨所有 group）
        measure_means = agg_df.mean()
        min_measure = str(measure_means.idxmin())
        min_val = float(measure_means.min())

        std_across = float(measure_means.std())
        overall_mean_of_measures = float(measure_means.mean())
        z_score = (overall_mean_of_measures - min_val) / std_across if std_across > 0 else 0

        result_df = agg_df.reset_index()
        self._filter_data = result_df

        self._description = {
            "min_measure": min_measure,
            "min_value": round(min_val, 2),
            "measure_means": {m: round(float(v), 2) for m, v in measure_means.items()},
            "z_score": round(float(z_score), 4),
            "summary": (
                f"在 {len(value_columns)} 个指标中，{min_measure} 均值最低（{min_val:.2f}），"
                f"z-score={z_score:.2f}，是拖低得分的关键维度"
            ),
        }
        self._significance_score = float(np.clip(abs(z_score) / 3, 0, 1))

        # 图表：分组柱状图（x=group，每个 measure 一个系列）
        groups = truncate_labels(agg_df.index.astype(str).tolist())
        colors = PALETTE[: len(value_columns)]

        series = []
        for i, col in enumerate(value_columns):
            if col not in agg_df.columns:
                continue
            color = HIGHLIGHT_RED if col == min_measure else colors[i % len(colors)]
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
            "title": base_title(f"各指标对比（最低: {min_measure}）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "legend": {"show": True, "top": 30, "textStyle": {"fontSize": 10}},
            "xAxis": {"type": "category", "data": groups, "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }

    # ------------------------------------------------------------------
    # 多 measure + 多 group：每个 group 各自最差的 measure（矩阵模式）
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

        # 每个 group 找出它的最差 measure
        per_group_worst: dict[str, dict] = {}
        worst_measures: list[str] = []
        worst_values: list[float] = []
        group_labels: list[str] = []

        for group_key, row in agg_df.iterrows():
            row_clean = row.dropna()
            if row_clean.empty:
                continue
            worst_col = str(row_clean.idxmin())
            worst_val = float(row_clean.min())
            group_str = str(group_key)
            per_group_worst[group_str] = {
                "measure": worst_col,
                "value": round(worst_val, 4),
            }
            group_labels.append(group_str)
            worst_measures.append(worst_col)
            worst_values.append(worst_val)

        if not per_group_worst:
            self._description = "无有效数据可分析"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        # 构造 filter_data：每个 group 一行，包含 worst_measure + 所有 measure 值
        # 注意：故意不用 min_group/max_group 等 top-level key，避免污染 _extract_entities
        # _extract_entities 会从 row[group_column] 提取 group 值作为下钻实体
        rows = []
        for group_key, row in agg_df.iterrows():
            row_dict: dict = {group_column: str(group_key)}
            worst_info = per_group_worst.get(str(group_key))
            if worst_info:
                row_dict["worst_measure"] = worst_info["measure"]
                row_dict["worst_value"] = worst_info["value"]
            for col in value_columns:
                if col in agg_df.columns:
                    v = row.get(col)
                    row_dict[col] = round(float(v), 4) if pd.notna(v) else None
            rows.append(row_dict)

        result_df = pd.DataFrame(rows)
        self._filter_data = result_df

        # 集中度：最差 measure 出现频次最高者
        counter = Counter(worst_measures)
        most_common_worst, most_common_count = counter.most_common(1)[0]
        n_groups = len(per_group_worst)
        concentration = most_common_count / n_groups  # [1/n, 1]

        # 显著性：集中度越高（共同短板越明显），显著性越高
        self._significance_score = float(np.clip(concentration, 0.3, 1.0))

        summary_lines = [f"对 {n_groups} 个 {group_column} 做多指标对比，每个分组的最差维度如下："]
        for g, info in list(per_group_worst.items())[:8]:  # 最多展示 8 个
            summary_lines.append(f"- {g}: {info['measure']} = {info['value']}")
        if most_common_count >= 2:
            summary_lines.append(
                f"其中 {most_common_count}/{n_groups} 个分组的最差维度都是 {most_common_worst}，"
                f"是共同的短板维度。"
            )
        else:
            summary_lines.append("各分组的最差维度各不相同，无共同短板。")

        self._description = {
            "mode": "matrix",
            "per_group_worst": per_group_worst,
            "most_common_worst": most_common_worst,
            "most_common_count": most_common_count,
            "n_groups": n_groups,
            "summary": "\n".join(summary_lines),
        }

        # 图表：分组柱状图（x=group，每个 measure 一个系列）
        # 对每个 group 各自的 worst cell 使用 HIGHLIGHT_RED，其他用 PALETTE
        groups = truncate_labels(group_labels)
        colors = PALETTE

        series = []
        for i, col in enumerate(value_columns):
            if col not in agg_df.columns:
                continue
            base_color = colors[i % len(colors)]
            data_points = []
            for j, group_key in enumerate(group_labels):
                v = agg_df.loc[group_key, col] if group_key in agg_df.index else None
                val = round(float(v), 4) if pd.notna(v) else 0
                # 如果这个 cell 是该 group 的 worst，标红
                is_worst = per_group_worst.get(group_key, {}).get("measure") == col
                data_points.append(
                    {
                        "value": val,
                        "itemStyle": {"color": HIGHLIGHT_RED if is_worst else base_color},
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
            "title": base_title(f"各 {group_column} 的维度对比（各自最低标红）"),
            "tooltip": base_tooltip("axis"),
            "grid": base_grid(),
            "legend": {"show": True, "top": 30, "textStyle": {"fontSize": 10}},
            "xAxis": {"type": "category", "data": groups, "axisLabel": rotated_axis_label(30)},
            "yAxis": {"type": "value", "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }
