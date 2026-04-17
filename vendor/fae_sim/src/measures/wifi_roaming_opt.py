"""WiFi漫游优化 — 切换至信号最优AP。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class WifiRoamingOptimization(Measure):
    name = "wifi_roaming_opt"
    description = "WiFi漫游优化 — 自动切换至信号最优AP"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.wifi_rssi = max(p.wifi_rssi, -45.0)
        p.wifi_multipath_fading *= 0.7
        p.sta_count = max(1, p.sta_count - 2)
        p.wifi_up_tcp_retrans_rate *= 0.3
        p.wifi_up_latency *= 0.5
        p.wifi_up_jitter *= 0.5
        return p
