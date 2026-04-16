"""WiFi 有效吞吐量模型（v2）。

建模链路: SNR(含多径衰落) → MCS(含编码率) → 物理层速率 → 空口折损(MU-MIMO/GI/竞争)
"""

from __future__ import annotations

import math
from ..params.schema import SimParams


# ── 完整 MCS 查表 ──
# {standard: [(snr_min_dB, base_rate_Mbps_per_stream_80MHz), ...]}
# base_rate 基于 80MHz 单流、编码率 5/6
_MCS_TABLE: dict[str, list[tuple[float, float]]] = {
    "wifi4": [
        # 802.11n — HT, 基准按 40MHz×2 近似到 80MHz 单流
        (5, 6.5), (8, 13.0), (11, 19.5), (14, 26.0),
        (17, 39.0), (20, 52.0), (23, 58.5), (26, 65.0),
    ],
    "wifi5": [
        # 802.11ac — VHT MCS0-9
        (5, 7.2), (8, 14.4), (11, 21.7), (14, 28.9),
        (17, 43.3), (20, 57.8), (23, 65.0), (26, 72.2),
        (30, 86.7), (33, 96.3),
    ],
    "wifi6": [
        # 802.11ax — HE MCS0-11
        (5, 8.1), (8, 16.3), (11, 24.4), (14, 32.5),
        (17, 48.8), (20, 65.0), (23, 73.1), (26, 81.3),
        (29, 97.5), (32, 108.3), (35, 120.1), (38, 143.4),
    ],
    "wifi6e": [
        # 同 WiFi6 HE，6GHz 频段
        (5, 8.1), (8, 16.3), (11, 24.4), (14, 32.5),
        (17, 48.8), (20, 65.0), (23, 73.1), (26, 81.3),
        (29, 97.5), (32, 108.3), (35, 120.1), (38, 143.4),
    ],
    "wifi7": [
        # 802.11be — EHT MCS0-13, 4096-QAM
        (5, 8.6), (8, 17.2), (11, 25.8), (14, 34.4),
        (17, 51.6), (20, 68.8), (23, 77.4), (26, 86.0),
        (29, 103.2), (32, 114.7), (35, 137.6), (38, 172.1),
        (41, 189.3), (44, 206.5),
    ],
}

# 频宽缩放因子（相对于 80 MHz 基准）
_BW_SCALE: dict[int, float] = {20: 0.25, 40: 0.5, 80: 1.0, 160: 2.0}

# 编码率效率系数
_CODE_RATE_EFF: dict[str, float] = {
    "1/2": 0.50, "2/3": 0.667, "3/4": 0.75, "5/6": 0.833,
}

# 协议空口效率系数 {standard: (mimo_off, mimo_on)}
_AIRTIME_EFFICIENCY: dict[str, tuple[float, float]] = {
    "wifi4": (0.55, 0.55),    # WiFi4 无 MU-MIMO
    "wifi5": (0.65, 0.70),
    "wifi6": (0.78, 0.83),
    "wifi6e": (0.80, 0.85),
    "wifi7": (0.82, 0.88),
}

# 竞争退避 α 系数 {standard: alpha}
_CONTENTION_ALPHA: dict[str, float] = {
    "wifi4": 0.30,
    "wifi5": 0.30,
    "wifi6": 0.15,   # OFDMA
    "wifi6e": 0.15,
    "wifi7": 0.15,
}


class WifiThroughputModel:
    """计算 WiFi 侧有效吞吐量 (Mbps)。"""

    def snr(self, params: SimParams) -> float:
        """SNR (dB)，含多径衰落修正。"""
        multipath_penalty = 10.0 * math.log10(1.0 + params.wifi_multipath_fading)
        return params.wifi_rssi - params.wifi_noise_floor - multipath_penalty

    def phy_rate(self, params: SimParams) -> float:
        """单空间流物理层速率 (Mbps)，按频宽和编码率缩放。"""
        snr_db = self.snr(params)
        table = _MCS_TABLE.get(params.wifi_standard, _MCS_TABLE["wifi6"])

        rate = table[0][1]  # 最低 MCS 兜底
        for snr_min, r in table:
            if snr_db >= snr_min:
                rate = r
            else:
                break

        bw_factor = _BW_SCALE.get(params.wifi_bandwidth, 1.0)
        # MCS 表按 5/6 编码率标定，按实际编码率修正
        cr_ratio = _CODE_RATE_EFF.get(params.wifi_code_rate, 0.833) / 0.833
        return rate * bw_factor * cr_ratio

    def airtime_efficiency(self, params: SimParams) -> float:
        """空口效率系数，区分 MU-MIMO 状态。"""
        pair = _AIRTIME_EFFICIENCY.get(params.wifi_standard, (0.70, 0.75))
        return pair[1] if params.wifi_mu_mimo_enabled else pair[0]

    def contention_factor(self, params: SimParams) -> float:
        """多 STA 竞争退避因子 (≥1.0)，区分协议与 GI。"""
        alpha = _CONTENTION_ALPHA.get(params.wifi_standard, 0.20)
        n = max(params.sta_count, 1)
        factor = 1.0 + alpha * math.log(n)
        # GI 修正：长 GI(800ns) ×1.05, 短 GI(400ns) ×0.95
        gi_mod = 1.05 if params.wifi_gi == 800 else 0.95
        return factor * gi_mod

    def calculate(self, params: SimParams) -> float:
        """返回 WiFi 有效吞吐量 (Mbps)。"""
        rate = self.phy_rate(params) * params.sta_spatial_streams
        eff = self.airtime_efficiency(params)
        interference = 1.0 - params.wifi_interference_ratio / 100.0
        retry = 1.0 - params.wifi_retry_rate / 100.0
        contention = self.contention_factor(params)
        cr_eff = _CODE_RATE_EFF.get(params.wifi_code_rate, 0.833)

        throughput = rate * eff * interference * retry / contention * cr_eff
        return max(throughput, 0.0)
