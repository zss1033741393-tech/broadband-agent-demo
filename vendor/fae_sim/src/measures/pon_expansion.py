"""PON口扩容 — 迁移至低负载PON口或升级速率。"""

from __future__ import annotations

from ..params.schema import SimParams
from .base import Measure


class PonExpansion(Measure):
    name = "pon_expansion"
    description = "PON口扩容 — 迁移至低负载PON口或升级速率"

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        p.pon_up_load_ratio = min(p.pon_up_load_ratio * 0.3, 30.0)
        p.pon_down_load_ratio *= 0.5
        p.pon_dba_cycle = min(p.pon_dba_cycle, 3.0)
        p.pon_up_tcp_retrans_rate *= 0.2
        p.pon_up_latency *= 0.3
        p.pon_up_jitter *= 0.4
        return p
