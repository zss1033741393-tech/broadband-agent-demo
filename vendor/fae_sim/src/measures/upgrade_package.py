"""套餐升级提升上行带宽。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class UpgradePackage(Measure):
    name = "upgrade_package"
    description = "套餐升级 — 提升上行带宽"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.pon_uplink_bw = min(p.pon_uplink_bw * 3.0, 2500.0)
        p.pon_up_load_ratio *= 0.5
        p.pon_up_tcp_retrans_rate *= 0.3
        p.pon_up_latency *= 0.5
        return p
