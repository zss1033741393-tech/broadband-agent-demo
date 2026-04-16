"""PON光纤修复措施 — 修复光纤中断，恢复光路衰减。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class PonFiberRepair(Measure):
    name = "pon_fiber_repair"
    description = "PON光纤修复 — 修复光纤中断恢复光路质量"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.pon_optical_attenuation = min(p.pon_optical_attenuation, 8.0)
        p.pon_up_tcp_retrans_rate *= 0.3
        p.pon_up_latency *= 0.5
        return p
