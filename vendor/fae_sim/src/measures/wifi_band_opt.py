"""WiFi频段优化 — 将STA从2.4G引导至5G频段。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class WifiBandOptimization(Measure):
    name = "wifi_band_opt"
    description = "WiFi频段优化 — 引导至5G/6G频段"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        if p.wifi_channel <= 13:
            p.wifi_channel = 36
            if p.wifi_bandwidth < 80:
                p.wifi_bandwidth = 80
            p.wifi_interference_ratio *= 0.15
            p.wifi_rssi -= 4.0
            p.wifi_up_tcp_retrans_rate *= 0.15
            p.wifi_up_jitter *= 0.2
            p.wifi_up_latency *= 0.3
            if p.wifi_multipath_fading < 0.4:
                p.wifi_gi = 400
            p.wifi_mu_mimo_enabled = True
        return p
