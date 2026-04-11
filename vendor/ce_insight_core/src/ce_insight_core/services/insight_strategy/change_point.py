"""
多尺度变点检测：结合多个窗口大小的检测结果，支持多变点。
去掉 CUSUM 双 Y 轴，改为前后均值对比线段。
"""

import logging

import numpy as np
import pandas as pd
from scipy import stats

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy

logger = logging.getLogger(__name__)


class ChangePointStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        value_columns: list[str] = kwargs["value_columns"]
        group_column: str = kwargs.get("group_column", "")
        col = value_columns[0]

        df = self._df.sort_values(group_column).dropna(subset=[col]).copy()
        values = df[col].values.astype(float)
        n = len(values)

        if n < 3:
            self._description = "数据点不足（<3），无法进行变点检测"
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 近零值放大
        max_abs = np.max(np.abs(values))
        scale = 1
        if 0 < max_abs < 0.01:
            scale = 10000 if max_abs < 0.001 else 1000
            work = values * scale
        else:
            work = values.copy()

        # ---- 多尺度检测 ----
        windows = self._pick_windows(n)
        all_hits: dict[int, float] = {}  # position → max_confidence

        for w in windows:
            hits = self._detect_with_window(work, w, n)
            for pos, conf in hits.items():
                all_hits[pos] = max(all_hits.get(pos, 0), conf)

        # 邻点对比（window=1，小数据量也能用）
        adj_hits = self._adjacent_detect(work)
        for pos, conf in adj_hits.items():
            all_hits[pos] = max(all_hits.get(pos, 0), conf)

        # 过滤低置信度 + 去重相邻点
        change_points = self._filter_and_dedup(all_hits, n, threshold=0.5)

        if not change_points:
            # 兜底：CUSUM 找最显著的 1 个
            cusum = np.cumsum(work - np.mean(work))
            best = int(np.argmax(np.abs(cusum)))
            if 0 < best < n - 1:
                change_points = [best]

        # ---- 构建结果 ----
        time_labels = df[group_column].astype(str).tolist()

        if not change_points:
            self._filter_data = pd.DataFrame()
            self._significance_score = 0.0
            self._description = {"summary": f"{col} 未检测到明显变点", "change_points": []}
            self._build_chart(col, time_labels, values, [])
            return

        # 计算每个变点的前后均值
        cp_details = []
        for cp in sorted(change_points):
            before = float(np.mean(values[:cp]))
            after = float(np.mean(values[cp:]))
            diff = after - before
            cp_details.append(
                {
                    "index": cp,
                    "time": time_labels[cp],
                    "before_mean": round(before, 2),
                    "after_mean": round(after, 2),
                    "diff": round(diff, 2),
                    "direction": "上升" if diff > 0 else "下降",
                }
            )

        # 最显著变点
        best_cp = max(cp_details, key=lambda c: abs(c["diff"]))

        self._filter_data = df.iloc[change_points].copy()

        # 显著性
        std_val = np.std(values)
        max_ratio = max(abs(c["diff"]) / std_val for c in cp_details) if std_val > 0 else 0
        self._significance_score = float(np.clip(max_ratio / 3, 0, 1))

        time_summary = ", ".join(
            f"{c['time']}({c['direction']}{abs(c['diff']):.2f})" for c in cp_details[:3]
        )
        self._description = {
            "change_points": cp_details,
            "best": best_cp,
            "count": len(cp_details),
            "summary": f"{col} 检测到 {len(cp_details)} 个变点：{time_summary}"
            + (f"…等{len(cp_details)}个" if len(cp_details) > 3 else ""),
        }

        self._build_chart(col, time_labels, values, cp_details)

    # ==================== 多尺度检测 ====================

    @staticmethod
    def _pick_windows(n: int) -> list[int]:
        candidates = [2, 3, 5, 7]
        return [w for w in candidates if n >= w * 3]

    def _detect_with_window(self, y: np.ndarray, w: int, n: int) -> dict[int, float]:
        """滑动窗口 t-test 检测"""
        hits = {}
        for i in range(w, n - w):
            left = y[i - w : i]
            right = y[i : i + w]
            if np.std(left) < 1e-10 and np.std(right) < 1e-10:
                continue
            try:
                _, p = stats.ttest_ind(left, right, equal_var=False)
                if p < 0.05:
                    hits[i] = 1 - p
            except Exception:
                pass
        return hits

    @staticmethod
    def _adjacent_detect(y: np.ndarray) -> dict[int, float]:
        """邻点变化率检测"""
        hits = {}
        n = len(y)
        threshold = 0.3 if n <= 10 else 0.5 if n <= 50 else 0.8
        for i in range(1, n):
            if y[i - 1] != 0:
                rate = abs((y[i] - y[i - 1]) / y[i - 1])
            else:
                rate = float("inf") if y[i] != 0 else 0
            if rate > threshold:
                conf = min(0.99, 1 / (1 + 1 / (rate + 1e-10)))
                hits[i] = conf
        return hits

    @staticmethod
    def _filter_and_dedup(hits: dict[int, float], n: int, threshold: float = 0.5) -> list[int]:
        """过滤低置信度 + 相邻点去重（保留置信度最高的）"""
        filtered = sorted(
            [(pos, conf) for pos, conf in hits.items() if conf >= threshold], key=lambda x: -x[1]
        )
        result = []
        min_gap = max(2, n // 10)
        for pos, _ in filtered:
            if all(abs(pos - p) >= min_gap for p in result):
                result.append(pos)
        return sorted(result)

    # ==================== 图表 ====================

    def _build_chart(self, col: str, time_labels: list, values: np.ndarray, cp_details: list):
        from ce_insight_core.services.insight_strategy.chart_style import (
            BLUE,
            GREEN,
            HIGHLIGHT_RED,
            ORANGE,
            base_title,
            base_tooltip,
            rotated_axis_label,
            truncate_labels,
        )

        labels = truncate_labels(time_labels, 12)
        n = len(labels)

        # 主折线
        main_series = {
            "name": col,
            "type": "line",
            "smooth": True,
            "data": [round(float(v), 2) for v in values],
            "itemStyle": {"color": BLUE},
            "lineStyle": {"color": BLUE},
            "symbolSize": 5,
        }

        # 变点红色竖线 + 区域高亮
        if cp_details:
            main_series["markLine"] = {
                "data": [{"xAxis": c["index"]} for c in cp_details],
                "lineStyle": {"color": HIGHLIGHT_RED, "width": 2, "type": "solid"},
                "label": {"formatter": "变点", "fontSize": 10, "color": HIGHLIGHT_RED},
                "symbol": "none",
            }
            # 高亮区域
            area_data = []
            for c in cp_details:
                idx = c["index"]
                area_data.append(
                    [
                        {
                            "xAxis": max(0, idx - 1),
                            "itemStyle": {"color": "rgba(231,111,111,0.08)"},
                        },
                        {"xAxis": min(n - 1, idx + 1)},
                    ]
                )
            main_series["markArea"] = {"silent": True, "data": area_data}

        series = [main_series]

        # 前后均值线段（每个变点画 before 和 after 水平虚线）
        if cp_details:
            before_data = [None] * n
            after_data = [None] * n
            for c in cp_details:
                idx = c["index"]
                # before: 从开头或上一个变点到当前变点
                for i in range(max(0, idx - max(3, n // 5)), idx):
                    before_data[i] = c["before_mean"]
                # after: 从变点到末尾或下一个变点
                for i in range(idx, min(n, idx + max(3, n // 5))):
                    after_data[i] = c["after_mean"]

            series.append(
                {
                    "name": "变点前均值",
                    "type": "line",
                    "data": before_data,
                    "lineStyle": {"type": "dashed", "color": ORANGE, "width": 2},
                    "itemStyle": {"color": ORANGE},
                    "symbol": "none",
                    "connectNulls": False,
                }
            )
            series.append(
                {
                    "name": "变点后均值",
                    "type": "line",
                    "data": after_data,
                    "lineStyle": {"type": "dashed", "color": GREEN, "width": 2},
                    "itemStyle": {"color": GREEN},
                    "symbol": "none",
                    "connectNulls": False,
                }
            )

        cp_count = len(cp_details)
        title = f"{col} 变点检测" + (f" ({cp_count}个变点)" if cp_count else " (无变点)")

        self._chart_configs = {
            "chart_type": "line",
            "title": base_title(title),
            "tooltip": base_tooltip("axis"),
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11}},
            "grid": {"left": "10%", "right": "6%", "bottom": "18%", "top": "16%"},
            "xAxis": {
                "type": "category",
                "data": labels,
                "axisLabel": rotated_axis_label(30) if n > 8 else {"fontSize": 11},
            },
            "yAxis": {"type": "value", "name": col, "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }
