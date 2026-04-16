"""WiFi时隙切片保障 — 预留专属空口时隙。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class WifiTimeslotGuarantee(Measure):
    name = "wifi_timeslot"
    description = "WiFi时隙切片保障 — 预留专属空口时隙"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.sta_count = 1
        p.wifi_retry_rate *= 0.2
        p.wifi_interference_ratio *= 0.3
        p.wifi_up_tcp_retrans_rate *= 0.15
        p.wifi_up_jitter *= 0.15
        p.wifi_up_latency *= 0.3
        return p
