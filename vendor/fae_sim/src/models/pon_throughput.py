"""PON 光路有效吞吐量模型（v2）。

新增光路衰减修正、DBA 调度模型、拥塞建模含突发冲突。
"""

from __future__ import annotations

from ..params.schema import SimParams


_RETRANSMISSION_OVERHEAD = 1.5


def _optical_attenuation_factor(attenuation_db: float) -> float:
    """光路衰减系数：≤18dB=1.0, 18~22dB=0.85, ≥22dB=0.65。"""
    if attenuation_db <= 18.0:
        return 1.0
    elif attenuation_db <= 22.0:
        # 18~22 线性插值
        return 1.0 - 0.15 * (attenuation_db - 18.0) / 4.0
    else:
        return 0.65


class PonThroughputModel:
    """计算 PON 侧有效吞吐量、排队时延和丢包率。"""

    def base_effective_bandwidth(self, params: SimParams) -> float:
        """基础有效下行带宽 (Mbps)，含光路衰减修正。"""
        bw = params.pon_downlink_bw
        fec_loss = 1.0 - params.pon_fec_post_error_rate
        bip_loss = 1.0 - params.pon_bip_error_rate * _RETRANSMISSION_OVERHEAD
        opt_factor = _optical_attenuation_factor(params.pon_optical_attenuation)
        return max(bw * fec_loss * bip_loss * opt_factor, 0.0)

    def dba_bandwidth(self, params: SimParams) -> float:
        """DBA 调度后的上行分配带宽 (Mbps)。"""
        available = params.pon_uplink_bw * (1.0 - params.pon_load_ratio / 100.0)
        return max(available, 0.0)

    def dba_fluctuation(self, params: SimParams) -> float:
        """DBA 带宽波动幅度 (0~1)。调度周期越长，波动越大。"""
        return 0.1 * params.pon_dba_cycle

    def congestion_loss_ratio(self, params: SimParams) -> float:
        """拥塞导致的吞吐量折损比例。负载 ≥70% 时生效。"""
        if params.pon_load_ratio < 70.0:
            return 0.0
        return 0.01 * (params.pon_load_ratio - 70.0)

    def queue_delay(self, params: SimParams) -> float:
        """PON 排队时延 (ms)，M/D/1 队列 + 突发冲突修正。"""
        rho = params.pon_load_ratio / 100.0
        if rho >= 0.99:
            return 500.0
        base_delay = rho / (2.0 * (1.0 - rho)) * 10.0
        collision_delay = params.pon_burst_collision * 10.0
        return base_delay + collision_delay

    def packet_loss(self, params: SimParams) -> float:
        """PON 侧丢包率。"""
        fec_residual = params.pon_fec_post_error_rate
        bip_overflow = max(params.pon_bip_error_rate - 1e-5, 0) * 0.1
        # 误码秒贡献：ES 越高，稳定性越差
        es_loss = params.pon_es / 3600.0 * 0.01
        return min(fec_residual + bip_overflow + es_loss, 1.0)

    def calculate(self, params: SimParams) -> float:
        """返回 PON 有效下行吞吐量 (Mbps)，含拥塞折损。"""
        base_bw = self.base_effective_bandwidth(params)
        cong = self.congestion_loss_ratio(params)
        return max(base_bw * (1.0 - cong), 0.0)
