"""
聚类分析：对多指标数据做 KMeans 聚类，识别不同特征群体。
"""

import numpy as np

from ce_insight_core.services.insight_strategy.base_insight import InsightStrategy


class ClusteringStrategy(InsightStrategy):
    def execute(self, **kwargs) -> None:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        value_columns: list[str] = kwargs["value_columns"]

        df = self._df.dropna(subset=value_columns).copy()

        if len(df) < 3:
            self._description = "数据量不足（<3），无法进行聚类分析"
            self._significance_score = 0.0
            self._filter_data = df
            return

        # 标准化
        scaler = StandardScaler()
        features = scaler.fit_transform(df[value_columns].values)

        # 自动选择 k（2~5 中轮廓系数最高的）
        from sklearn.metrics import silhouette_score

        best_k, best_score = 2, -1
        max_k = min(5, len(df) - 1)
        for k in range(2, max_k + 1):
            km = KMeans(n_clusters=k, n_init=10, random_state=42)
            labels = km.fit_predict(features)
            score = silhouette_score(features, labels)
            if score > best_score:
                best_k, best_score = k, score

        km = KMeans(n_clusters=best_k, n_init=10, random_state=42)
        df["cluster"] = km.fit_predict(features)

        # 各簇统计
        cluster_stats = df.groupby("cluster")[value_columns].mean().round(2)

        self._filter_data = df
        self._description = {
            "n_clusters": best_k,
            "silhouette_score": round(float(best_score), 4),
            "cluster_centers": cluster_stats.to_dict(),
            "summary": f"聚为 {best_k} 类，轮廓系数 {best_score:.4f}",
        }
        self._significance_score = float(np.clip(best_score, 0, 1))

        from ce_insight_core.services.insight_strategy.chart_style import (
            PALETTE,
            base_title,
            base_tooltip,
        )

        x_col = value_columns[0]
        y_col = value_columns[1] if len(value_columns) > 1 else value_columns[0]
        series = []
        for c in range(best_k):
            mask = df["cluster"] == c
            count = int(mask.sum())
            series.append(
                {
                    "name": f"簇{c} ({count}个)",
                    "type": "scatter",
                    "data": list(
                        zip(
                            df.loc[mask, x_col].round(2).tolist(),
                            df.loc[mask, y_col].round(2).tolist(),
                        )
                    ),
                    "itemStyle": {"color": PALETTE[c % len(PALETTE)], "opacity": 0.7},
                    "symbolSize": 6,
                }
            )

        self._chart_configs = {
            "chart_type": "scatter",
            "title": base_title(f"聚类分析 (k={best_k}, 轮廓系数={best_score:.3f})"),
            "tooltip": base_tooltip("item"),
            "legend": {"bottom": 0, "textStyle": {"fontSize": 11}},
            "grid": {"left": "12%", "right": "6%", "bottom": "18%", "top": "16%"},
            "xAxis": {"type": "value", "name": x_col, "nameTextStyle": {"fontSize": 11}},
            "yAxis": {"type": "value", "name": y_col, "nameTextStyle": {"fontSize": 11}},
            "series": series,
        }
