"""
异常检测：IQR + Z-score 双方法，支持近零值自动放大处理。
"""

import logging

import numpy as np
import pandas as pd

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy

logger = logging.getLogger(__name__)


class OutlierDetectionStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        col = value_columns[0]
        group_column: str = kwargs.get("group_column", "")

        series = self._df[col].dropna()
        if len(series) < 3:
            self._description = "数据量不足（<3），无法进行异常检测"
            self._significance_score = 0.0
            self._filter_data = self._df
            return

        df = self._df.copy()

        # 近零值检测与放大
        max_abs = series.abs().max()
        scale_factor = 1
        is_near_zero = False
        if 0 < max_abs < 0.01:
            is_near_zero = True
            if max_abs < 0.001:
                scale_factor = 100000
            elif max_abs < 0.01:
                scale_factor = 10000
            logger.info("近零值数据，放大 %d 倍处理", scale_factor)
            work_series = series * scale_factor
        else:
            work_series = series

        # ---- IQR 方法 ----
        q1 = work_series.quantile(0.25)
        q3 = work_series.quantile(0.75)
        iqr = q3 - q1
        if iqr > 0:
            iqr_lower = q1 - 1.5 * iqr
            iqr_upper = q3 + 1.5 * iqr
            iqr_mask = (work_series < iqr_lower) | (work_series > iqr_upper)
        else:
            # IQR=0 时用众数偏离检测
            mode_val = (
                work_series.mode().iloc[0] if not work_series.mode().empty else work_series.median()
            )
            iqr_mask = work_series != mode_val
            iqr_lower = float(mode_val)
            iqr_upper = float(mode_val)

        # ---- Z-score 方法 ----
        mean_val = work_series.mean()
        std_val = work_series.std()
        if std_val > 1e-10:
            z_threshold = 2 if is_near_zero else 3
            z_mask = (work_series > mean_val + z_threshold * std_val) | (
                work_series < mean_val - z_threshold * std_val
            )
        else:
            z_mask = abs(work_series - mean_val) > 1e-10

        # 合并两种方法（取并集）
        combined_mask = iqr_mask | z_mask
        # 还原到原始索引
        full_mask = pd.Series(False, index=df.index)
        full_mask.loc[series.index] = combined_mask.values

        df["is_outlier"] = full_mask
        df["detect_method"] = ""
        df.loc[full_mask & iqr_mask.reindex(df.index, fill_value=False), "detect_method"] += "IQR "
        df.loc[full_mask & z_mask.reindex(df.index, fill_value=False), "detect_method"] += "Z-score"

        outliers = df[df["is_outlier"]].copy()
        outlier_ratio = len(outliers) / len(df) if len(df) > 0 else 0

        # 统计列
        if not outliers.empty and std_val > 0:
            outliers["标准化偏差"] = abs(outliers[col] - series.mean()) / (
                series.std() if series.std() > 0 else 1
            )
            outliers = outliers.sort_values("标准化偏差", ascending=False)

        self._filter_data = outliers

        # 还原 bounds 到原始尺度
        real_lower = iqr_lower / scale_factor if is_near_zero else iqr_lower
        real_upper = iqr_upper / scale_factor if is_near_zero else iqr_upper

        # 零值统计
        zero_count = int((series == 0).sum())
        zero_ratio = zero_count / len(series) if len(series) > 0 else 0

        self._description = {
            "total": len(df),
            "outlier_count": len(outliers),
            "outlier_ratio": round(outlier_ratio, 4),
            "iqr_outliers": int(iqr_mask.sum()),
            "zscore_outliers": int(z_mask.sum()),
            "lower_bound": round(float(real_lower), 4),
            "upper_bound": round(float(real_upper), 4),
            "zero_count": zero_count,
            "zero_ratio": round(zero_ratio, 4),
            "is_near_zero": is_near_zero,
            "summary": f"{col} 检测到 {len(outliers)} 个异常值（{outlier_ratio:.1%}），"
            f"IQR法{int(iqr_mask.sum())}个 + Z-score法{int(z_mask.sum())}个"
            + (f"，零值占比{zero_ratio:.1%}" if zero_ratio > 0.5 else ""),
        }

        # 显著性：综合异常比例和最大偏差
        if not outliers.empty and "标准化偏差" in outliers.columns:
            max_z = float(outliers["标准化偏差"].max())
            self._significance_score = float(np.clip(max(outlier_ratio * 5, max_z / 6), 0, 1))
        else:
            self._significance_score = float(np.clip(outlier_ratio * 5, 0, 1))

        # ---- 图表 ----
        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            HIGHLIGHT_RED,
            ORANGE,
            base_title,
            base_tooltip,
            truncate_labels,
        )

        # 用 group_column 做 x 轴标签（如果有），否则用序号
        if group_column and group_column in df.columns:
            labels = truncate_labels(df[group_column].astype(str).tolist())
            x_axis = {
                "type": "category",
                "data": labels,
                "axisLabel": {"fontSize": 10, "rotate": 30},
            }
            normal_data = [
                {"value": [labels[i], round(float(v), 2)]}
                for i, (v, o) in enumerate(zip(df[col], df["is_outlier"]))
                if not o
            ]
            outlier_data_chart = [
                {"value": [labels[i], round(float(v), 2)]}
                for i, (v, o) in enumerate(zip(df[col], df["is_outlier"]))
                if o
            ]
        else:
            x_axis = {"type": "value", "name": "序号", "nameTextStyle": {"fontSize": 11}}
            normal_data = [
                [i, round(float(v), 2)]
                for i, (v, o) in enumerate(zip(df[col], df["is_outlier"]))
                if not o
            ]
            outlier_data_chart = [
                [i, round(float(v), 2)]
                for i, (v, o) in enumerate(zip(df[col], df["is_outlier"]))
                if o
            ]

        self._chart_configs = {
            "chart_type": "scatter",
            "title": base_title(f"{col} 异常检测 (IQR+Z-score, 异常率 {outlier_ratio:.1%})"),
            "tooltip": base_tooltip("item"),
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11}},
            "grid": {"left": "10%", "right": "6%", "bottom": "18%", "top": "16%"},
            "xAxis": x_axis,
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": [
                {
                    "name": "正常值",
                    "type": "scatter",
                    "data": normal_data,
                    "itemStyle": {"color": BLUE, "opacity": 0.4},
                    "symbolSize": 5,
                    "markLine": {
                        "data": [
                            {"yAxis": round(float(real_upper), 4), "name": "上限"},
                            {"yAxis": round(float(real_lower), 4), "name": "下限"},
                        ],
                        "lineStyle": {"type": "dashed", "color": ORANGE, "width": 1.5},
                        "label": {"show": True, "formatter": "{b}: {c}", "fontSize": 10},
                        "symbol": "none",
                        "silent": True,
                    },
                },
                {
                    "name": f"异常点 ({len(outliers)})",
                    "type": "scatter",
                    "data": outlier_data_chart,
                    "itemStyle": {"color": HIGHLIGHT_RED},
                    "symbolSize": 8,
                },
            ],
        }
