"""
周期性分析：检测时序数据中的周期模式（基于 FFT）。
"""

import numpy as np

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class SeasonalityStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        df = self._df.sort_values(group_column).dropna(subset=[col]).copy()
        values = df[col].values.astype(float)

        if len(values) < 6:
            self._description = "数据点不足（<6），无法进行周期性分析"
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 去趋势
        x = np.arange(len(values), dtype=float)
        slope, intercept = np.polyfit(x, values, 1)
        detrended = values - (slope * x + intercept)

        # FFT
        fft_vals = np.fft.rfft(detrended)
        power = np.abs(fft_vals) ** 2
        freqs = np.fft.rfftfreq(len(detrended))

        # 忽略直流分量（freq=0）
        if len(power) > 1:
            power[0] = 0
            dominant_idx = np.argmax(power)
            dominant_freq = freqs[dominant_idx]
            dominant_period = round(1.0 / dominant_freq, 1) if dominant_freq > 0 else 0
            dominant_power = float(power[dominant_idx])
            total_power = float(power.sum())
            power_ratio = dominant_power / total_power if total_power > 0 else 0
        else:
            dominant_period = 0
            power_ratio = 0

        self._filter_data = df
        self._description = {
            "dominant_period": dominant_period,
            "power_ratio": round(power_ratio, 4),
            "summary": f"{col} 主周期约 {dominant_period} 个时间单位，"
            f"周期能量占比 {power_ratio:.1%}",
        }
        self._significance_score = float(np.clip(power_ratio, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            GREEN,
            ORANGE,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        time_labels = truncate_labels(df[group_column].astype(str).tolist(), 12)
        # 三条线：原始值、趋势线、季节性（去趋势）
        trend_line = (slope * x + intercept).round(2).tolist()
        self._chart_configs = {
            "chart_type": "line",
            "title": base_title(f"{col} 周期性分析（主周期 ≈ {dominant_period}）"),
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
                    "name": "原始值",
                    "type": "line",
                    "data": [round(float(v), 2) for v in values],
                    "itemStyle": {"color": BLUE},
                    "lineStyle": {"color": BLUE},
                },
                {
                    "name": "趋势",
                    "type": "line",
                    "data": trend_line,
                    "lineStyle": {"type": "dashed", "color": ORANGE},
                    "itemStyle": {"color": ORANGE},
                    "symbol": "none",
                },
                {
                    "name": "季节性（去趋势）",
                    "type": "line",
                    "data": detrended.round(2).tolist(),
                    "lineStyle": {"color": GREEN, "width": 1},
                    "itemStyle": {"color": GREEN},
                    "areaStyle": {"opacity": 0.1},
                },
            ],
        }
