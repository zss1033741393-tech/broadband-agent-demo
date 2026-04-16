"""WiFi上行吞吐量模型（时间步级瞬时化）。

SNR(n) → MCS查表 → 空口效率折损 → wifi_throughput(n)
"""

from __future__ import annotations

import math

# ── MCS 查表（WiFi6, 80MHz, 单流速率 Mbps） ──
_MCS_TABLE_WIFI6_80MHZ = [
    (35, 11, 143.4),
    (30, 9, 120.1),
    (25, 7, 97.5),
    (20, 5, 65.0),
    (15, 3, 39.0),
    (10, 1, 16.3),
    (float("-inf"), 0, 8.1),
]

# WiFi 标准相对 WiFi6 的速率缩放系数
_STANDARD_SCALE = {
    "wifi4": 0.55,
    "wifi5": 0.78,
    "wifi6": 1.0,
    "wifi6e": 1.0,
    "wifi7": 1.15,
}

# 空口效率系数
_AIRTIME_EFF = {
    "wifi4": (0.55, 0.55),      # (MU-MIMO off, on) — WiFi4无MU-MIMO
    "wifi5": (0.65, 0.70),
    "wifi6": (0.78, 0.83),
    "wifi6e": (0.78, 0.83),
    "wifi7": (0.82, 0.88),
}

# 编码率效率
_CODE_RATE_EFF = {
    "1/2": 0.50,
    "2/3": 0.67,
    "3/4": 0.75,
    "5/6": 0.83,
}


class WifiUpThroughputModel:
    """WiFi上行吞吐量模型。"""

    def calculate(self, params) -> float:
        """计算时间步n的WiFi上行瞬时吞吐量 (Mbps)。"""

        # Step 1: SNR 计算
        snr = self._calc_snr(params)

        # Step 2: PHY速率查表
        phy_rate = self._lookup_phy_rate(snr, params)

        # Step 3: 空口效率折损 → 吞吐量
        throughput = self._calc_throughput(phy_rate, snr, params)

        return max(throughput, 0.0)

    @staticmethod
    def _calc_snr(params) -> float:
        """SNR(n) = RSSI - noise_floor - 10*log10(1 + multipath_fading)"""
        fading_loss = 10.0 * math.log10(1.0 + params.wifi_multipath_fading)
        return params.wifi_rssi - params.wifi_noise_floor - fading_loss

    @staticmethod
    def _lookup_phy_rate(snr: float, params) -> float:
        """根据SNR查MCS表获取PHY速率。"""
        # WiFi6 80MHz 基础速率
        base_rate = 8.1  # MCS0 fallback
        for snr_thresh, mcs, rate in _MCS_TABLE_WIFI6_80MHZ:
            if snr >= snr_thresh:
                base_rate = rate
                break

        # 频宽缩放（以80MHz为基准）
        bw_scale = params.wifi_bandwidth / 80.0

        # 协议标准缩放
        std_scale = _STANDARD_SCALE.get(params.wifi_standard, 1.0)

        return base_rate * bw_scale * std_scale

    @staticmethod
    def _calc_throughput(phy_rate: float, snr: float, params) -> float:
        """空口效率折损后的吞吐量。"""
        # 空间流
        streams = params.sta_spatial_streams

        # 空口效率
        std = params.wifi_standard
        eff_pair = _AIRTIME_EFF.get(std, (0.70, 0.75))
        airtime_eff = eff_pair[1] if params.wifi_mu_mimo_enabled else eff_pair[0]

        # 竞争因子
        contention = _contention_factor(
            params.sta_count, params.wifi_standard, params.wifi_gi
        )

        # 编码率效率
        code_eff = _CODE_RATE_EFF.get(params.wifi_code_rate, 0.75)

        # cwnd_factor（默认1.0，满窗口）
        cwnd_factor = 1.0

        # 综合吞吐量
        throughput = (
            phy_rate
            * streams
            * (1.0 - params.wifi_interference_ratio / 100.0)
            * (1.0 - params.wifi_retry_rate / 100.0)
            * airtime_eff
            / contention
            * code_eff
            * cwnd_factor
        )
        return throughput


def _contention_factor(sta_count: int, standard: str, gi: int) -> float:
    """多STA竞争退避因子。

    WiFi4/5 (CSMA/CA): 1 + 0.3 * ln(sta_count)
    WiFi6/7 (OFDMA):   1 + 0.15 * ln(sta_count)
    长GI(800ns): ×1.05
    短GI(400ns): ×0.95
    """
    n = max(sta_count, 1)
    if standard in ("wifi6", "wifi6e", "wifi7"):
        alpha = 0.15
    else:
        alpha = 0.3

    factor = 1.0 + alpha * math.log(n)

    # GI 修正
    if gi >= 800:
        factor *= 1.05
    else:
        factor *= 0.95

    return max(factor, 1.0)
