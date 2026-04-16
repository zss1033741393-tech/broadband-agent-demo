"""WiFi信道优化 — 切换到干扰最小的信道。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class WifiChannelOptimization(Measure):
    name = "wifi_channel_opt"
    description = "WiFi信道优化 — 切换至干扰最小信道"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.wifi_interference_ratio = max(3.0, p.wifi_interference_ratio * 0.15)
        p.wifi_noise_floor -= 2.0
        p.wifi_multipath_fading *= 0.8
        p.wifi_up_tcp_retrans_rate *= 0.3
        p.wifi_up_jitter *= 0.3
        p.wifi_up_latency *= 0.5
        return p
