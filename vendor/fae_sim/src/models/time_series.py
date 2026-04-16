"""时序仿真模块。

为 WiFi/PON 各指标生成带环境与时间波动的时间序列数据。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..params.schema import SimParams


@dataclass
class TimeSeriesData:
    """时间序列数据集。"""
    time: np.ndarray           # 时间轴 (秒)
    wifi_rssi: np.ndarray
    wifi_interference: np.ndarray
    wifi_retry_rate: np.ndarray
    wifi_throughput: np.ndarray
    pon_load_ratio: np.ndarray
    pon_throughput: np.ndarray
    effective_throughput: np.ndarray
    buffer_level: np.ndarray
    stall_mask: np.ndarray     # 1=卡顿, 0=正常


class TimeSeriesGenerator:
    """生成各指标的时间序列，模拟真实环境波动。"""

    def generate(self, params: SimParams) -> TimeSeriesData:
        rng = np.random.default_rng(params.random_seed)
        dt = params.time_step
        n = int(params.sim_duration / dt)
        t = np.arange(n) * dt

        # ── WiFi RSSI：慢衰落 + 快衰落 ──
        rssi_base = params.wifi_rssi
        # 慢衰落：人体遮挡，周期 10~30 秒
        slow = 3.0 * np.sin(2 * np.pi * t / 20.0) + 1.5 * np.sin(2 * np.pi * t / 7.0)
        # 快衰落：多径，高频小幅
        fast = rng.normal(0, 1.0, n)
        rssi_series = rssi_base + slow + fast
        np.clip(rssi_series, -95, -10, out=rssi_series)

        # ── WiFi 干扰占空比：邻居 AP 活动模式 ──
        interf_base = params.wifi_interference_ratio
        # 模拟邻居 AP 间歇性突发（周期 5~15 秒）
        interf_burst = interf_base * 0.5 * np.abs(np.sin(2 * np.pi * t / 8.0))
        interf_noise = rng.normal(0, interf_base * 0.1, n)
        interf_series = interf_base + interf_burst + interf_noise
        np.clip(interf_series, 0, 100, out=interf_series)

        # ── WiFi 重传率：随干扰波动 ──
        retry_base = params.wifi_retry_rate
        retry_series = retry_base + (interf_series - interf_base) * 0.3 + rng.normal(0, 1.0, n)
        np.clip(retry_series, 0, 50, out=retry_series)

        # ── PON 负载率：用户使用模式 ──
        load_base = params.pon_load_ratio
        # 日间峰值波动
        load_wave = load_base * 0.2 * np.sin(2 * np.pi * t / 60.0)  # 60秒大周期
        load_burst = np.zeros(n)
        # 随机突发高负载事件
        burst_starts = rng.choice(n, size=max(1, n // 6000), replace=False)
        burst_len = int(5.0 / dt)
        for s in burst_starts:
            e = min(s + burst_len, n)
            load_burst[s:e] = load_base * 0.3
        load_series = load_base + load_wave + load_burst + rng.normal(0, load_base * 0.05, n)
        np.clip(load_series, 0, 99, out=load_series)

        # ── 计算吞吐量序列 ──
        from .wifi_throughput import WifiThroughputModel
        from .pon_throughput import PonThroughputModel

        wifi_model = WifiThroughputModel()
        pon_model = PonThroughputModel()

        # 向量化近似计算（逐步更新参数）
        wifi_tp = np.zeros(n)
        pon_tp = np.zeros(n)

        # 采样计算（每 200 步计算一次，中间线性插值，平衡精度与性能）
        sample_interval = 200
        sample_indices = list(range(0, n, sample_interval)) + [n - 1]

        p = params.copy()
        wifi_samples = []
        pon_samples = []

        for idx in sample_indices:
            p.wifi_rssi = float(rssi_series[idx])
            p.wifi_interference_ratio = float(interf_series[idx])
            p.wifi_retry_rate = float(retry_series[idx])
            p.pon_load_ratio = float(load_series[idx])
            wifi_samples.append(wifi_model.calculate(p))
            pon_samples.append(pon_model.calculate(p))

        wifi_tp = np.interp(np.arange(n), sample_indices, wifi_samples)
        pon_tp = np.interp(np.arange(n), sample_indices, pon_samples)

        eff_tp = np.minimum(wifi_tp, pon_tp)

        # ── 缓冲区仿真 ──
        buffer_level = np.zeros(n)
        stall_mask = np.zeros(n)
        buf = params.buffer_duration
        in_stall = False
        bitrate = params.stream_bitrate

        for i in range(n):
            rx = eff_tp[i] * dt
            consume = bitrate * dt if not in_stall else 0.0
            buf += (rx - consume) / bitrate
            buf = min(max(buf, 0.0), params.buffer_duration)
            buffer_level[i] = buf

            if not in_stall:
                if buf <= 0.0:
                    in_stall = True
            else:
                stall_mask[i] = 1.0
                if buf >= params.buffer_preload_threshold:
                    in_stall = False

        return TimeSeriesData(
            time=t,
            wifi_rssi=rssi_series,
            wifi_interference=interf_series,
            wifi_retry_rate=retry_series,
            wifi_throughput=wifi_tp,
            pon_load_ratio=load_series,
            pon_throughput=pon_tp,
            effective_throughput=eff_tp,
            buffer_level=buffer_level,
            stall_mask=stall_mask,
        )
