"""PON上行/下行吞吐量模型（时间步级瞬时化）。

上行：基础带宽 → DBA调度 → 优先级分配 → 波动 → 拥塞修正
下行：基础带宽 → 负载分段拥塞修正
"""

from __future__ import annotations


class PonUpThroughputModel:
    """PON吞吐量模型。"""

    def calculate_up(self, params) -> float:
        """计算PON上行有效吞吐量 (Mbps)。"""
        # Step 1: 基础上行带宽
        base = self._up_base_bw(params)

        # Step 3: DBA调度后的实际上行吞吐量
        effective = self._dba_up_effective(base, params)

        return max(effective, 0.0)

    def calculate_down(self, params) -> float:
        """计算PON下行有效吞吐量 (Mbps)。"""
        base = self._down_base_bw(params)
        effective = self._down_effective(base, params)
        return max(effective, 0.0)

    @staticmethod
    def _optical_attenuation_factor(attenuation: float) -> float:
        """光路衰减系数: ≤18dB=1.0, 18~22dB=0.85, ≥22dB=0.65"""
        if attenuation <= 18:
            return 1.0
        elif attenuation <= 22:
            return 0.85
        else:
            return 0.65

    @staticmethod
    def _tx_power_factor(tx_power: float) -> float:
        """ONU上行发射光功率系数: -15~-5dBm=1.0, 否则线性折损。"""
        if -15.0 <= tx_power <= -5.0:
            return 1.0
        elif tx_power < -15.0:
            # 每低1dB折损0.1，最低0.1
            return max(1.0 + (tx_power + 15.0) * 0.1, 0.1)
        else:
            # 每高1dB折损0.1，最低0.1
            return max(1.0 - (tx_power + 5.0) * 0.1, 0.1)

    def _up_base_bw(self, params) -> float:
        """PON基础上行带宽。"""
        retrans_overhead = 1.3
        oaf = self._optical_attenuation_factor(params.pon_optical_attenuation)
        tpf = self._tx_power_factor(getattr(params, 'pon_tx_power', -10.0))

        bw = (
            params.pon_uplink_bw
            * (1.0 - params.pon_fec_post_error_rate)
            * (1.0 - params.pon_bip_error_rate * retrans_overhead)
            * oaf
            * tpf
        )
        return max(bw, 0.0)

    def _down_base_bw(self, params) -> float:
        """PON基础下行带宽。"""
        oaf = self._optical_attenuation_factor(params.pon_optical_attenuation)
        bw = (
            params.pon_downlink_bw
            * (1.0 - params.pon_fec_post_error_rate)
            * (1.0 - params.pon_bip_error_rate * 0.5)
            * oaf
        )
        return max(bw, 0.0)

    @staticmethod
    def _dba_up_effective(base_bw: float, params) -> float:
        """DBA调度后的PON上行实际吞吐量。"""
        load = params.pon_up_load_ratio

        # 1. DBA上行可分配带宽池
        pool = base_bw * (1.0 - load / 100.0)

        # 2. 优先级分配
        allocated = pool * params.user_priority_weight

        # 3. 带宽波动
        fluctuation = 0.1 * params.pon_dba_cycle + params.pon_burst_collision * 0.5
        effective = allocated * (1.0 - fluctuation)

        # 4. 重载拥塞修正 (≥70%)
        if load >= 70:
            congestion_loss = 0.01 * (load - 70)
            effective *= (1.0 - congestion_loss)

        return effective

    @staticmethod
    def _down_effective(base_bw: float, params) -> float:
        """PON下行实际吞吐量。"""
        load = params.pon_down_load_ratio

        if load < 70:
            return base_bw
        elif load < 80:
            congestion_loss = 0.005 * (load - 70)
            return base_bw * (1.0 - congestion_loss)
        else:
            congestion_loss = 0.005 * 10 + 0.02 * (load - 80)
            denom = 1.0 - load / 100.0
            if denom <= 0:
                denom = 0.001
            queue_loss = load / (2.0 * 1000.0 * denom)
            return max(base_bw * (1.0 - congestion_loss - queue_loss), 0.0)
