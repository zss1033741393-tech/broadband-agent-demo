"""端到端传输质量模型（v2）。

优化：瓶颈识别、丢包分类、抖动细化、业务适配。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..params.schema import SimParams
from .wifi_throughput import WifiThroughputModel
from .pon_throughput import PonThroughputModel


@dataclass
class E2EMetrics:
    """端到端传输质量指标。"""
    effective_throughput: float   # Mbps
    packet_loss: float           # 0~1
    jitter: float                # ms
    wifi_throughput: float       # Mbps
    pon_throughput: float        # Mbps
    bottleneck: str              # "WiFi空口" / "PON光路"
    bottleneck_factor: float     # 瓶颈严重程度 (>1)


class E2EQualityModel:
    """端到端质量模型：瓶颈识别 + 级联丢包 + 合成抖动。"""

    def __init__(self):
        self.wifi_model = WifiThroughputModel()
        self.pon_model = PonThroughputModel()

    def calculate(self, params: SimParams) -> E2EMetrics:
        wifi_tp = self.wifi_model.calculate(params)
        pon_tp = self.pon_model.calculate(params)

        # 瓶颈吞吐量
        base_tp = min(wifi_tp, pon_tp)

        # 瓶颈识别
        if wifi_tp < pon_tp:
            bottleneck = "WiFi空口"
            bottleneck_factor = pon_tp / wifi_tp if wifi_tp > 0 else 999.0
        else:
            bottleneck = "PON光路"
            bottleneck_factor = wifi_tp / pon_tp if pon_tp > 0 else 999.0

        # 业务适配修正
        throughput_adj = params.stream_bitrate / 6.0
        effective_tp = base_tp * (1.0 + 0.1 * (throughput_adj - 1.0))
        effective_tp = max(effective_tp, 0.0)

        # 级联丢包
        wifi_loss = self._wifi_packet_loss(params)
        pon_loss = self.pon_model.packet_loss(params)
        overlap = min(wifi_loss * pon_loss * 0.5, 0.05)  # 重叠系数
        e2e_loss = 1.0 - (1.0 - wifi_loss) * (1.0 - pon_loss) - overlap
        e2e_loss = max(min(e2e_loss, 1.0), 0.0)

        # 合成抖动
        jitter = self._combined_jitter(params)

        return E2EMetrics(
            effective_throughput=effective_tp,
            packet_loss=e2e_loss,
            jitter=jitter,
            wifi_throughput=wifi_tp,
            pon_throughput=pon_tp,
            bottleneck=bottleneck,
            bottleneck_factor=round(bottleneck_factor, 2),
        )

    def _wifi_packet_loss(self, params: SimParams) -> float:
        """WiFi 侧丢包率：重传耗尽。"""
        p_fail = params.wifi_retry_rate / 100.0
        max_retries = 7
        return p_fail ** max_retries

    def _combined_jitter(self, params: SimParams) -> float:
        """合成抖动 (ms)，WiFi 占 60%, PON 占 40%。"""
        # WiFi 竞争抖动
        wifi_jitter = (
            5.0 * (params.sta_count / 10.0)
            * (params.wifi_interference_ratio / 100.0)
            + 1.0
        )
        # PON 排队抖动（含 DBA 周期影响）
        pon_jitter = (
            2.0 * (params.pon_load_ratio / 100.0)
            * params.pon_dba_cycle
            + 0.5
        )
        # 加权合成 + 随机基底
        return wifi_jitter * 0.6 + pon_jitter * 0.4 + 0.25
