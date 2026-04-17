"""PON口大流量限流 — 限制其它ONU大流量用户。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class PonTrafficLimit(Measure):
    name = "pon_traffic_limit"
    description = "PON口大流量限流 — 限制其它ONU大流量用户"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.pon_up_load_ratio = min(p.pon_up_load_ratio * 0.4, 40.0)
        p.pon_uplink_bw *= 1.2
        p.pon_burst_collision = min(p.pon_burst_collision, 0.02)
        p.pon_up_tcp_retrans_rate *= 0.3
        p.pon_up_latency *= 0.5
        p.pon_up_jitter *= 0.5
        return p
