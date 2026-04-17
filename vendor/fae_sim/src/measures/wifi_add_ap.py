"""WiFi新增AP提升覆盖。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class WifiAddAp(Measure):
    name = "wifi_add_ap"
    description = "WiFi新增AP — 提升家庭WiFi覆盖"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.wifi_rssi = min(p.wifi_rssi + 20.0, -25.0)
        p.wifi_up_latency *= 0.6
        p.wifi_up_jitter *= 0.5
        p.wifi_up_tcp_retrans_rate *= 0.3
        p.wifi_multipath_fading *= 0.5
        return p
