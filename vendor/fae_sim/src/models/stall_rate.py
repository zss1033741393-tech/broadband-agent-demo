"""直播卡顿率仿真模型（v2）。

优化：5ms 时间步、VBR 码率波动、预加载阈值、卡顿分级。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..params.schema import SimParams
from .e2e_quality import E2EQualityModel, E2EMetrics


@dataclass
class StallEvent:
    """单次卡顿事件。"""
    start_time: float   # 秒
    duration: float      # 秒
    grade: str           # 轻微/中度/重度/严重


@dataclass
class StallResult:
    """卡顿仿真结果。"""
    stall_rate: float               # % (卡顿总时长 / 仿真时长)
    stall_count: int                # 卡顿事件次数
    avg_stall_duration: float       # 平均每次卡顿时长 (秒)
    first_stall_time: float         # 首次卡顿时刻 (秒), -1 表示无卡顿
    effective_throughput: float     # 平均有效吞吐量 (Mbps)
    bottleneck: str                 # 瓶颈位置
    bottleneck_factor: float        # 瓶颈严重程度
    buffer_trace: np.ndarray        # 缓冲区水位时序 (秒)
    stall_events: list[StallEvent] = field(default_factory=list)
    # 卡顿分级统计
    grade_counts: dict[str, int] = field(default_factory=lambda: {
        "轻微": 0, "中度": 0, "重度": 0, "严重": 0
    })


def _classify_stall(duration: float, stall_rate: float) -> str:
    """卡顿等级判定。"""
    if stall_rate >= 60.0:
        return "严重"
    if duration >= 3.0 or stall_rate >= 30.0:
        return "重度"
    if duration >= 1.0 or stall_rate >= 10.0:
        return "中度"
    return "轻微"


class StallRateModel:
    """离散事件缓冲区卡顿仿真。"""

    def __init__(self):
        self.e2e_model = E2EQualityModel()

    def simulate(self, params: SimParams) -> StallResult:
        rng = np.random.default_rng(params.random_seed)
        e2e = self.e2e_model.calculate(params)

        dt = params.time_step  # 5ms
        total_steps = int(params.sim_duration / dt)

        # 预计算吞吐量和码率序列
        tp_series = self._generate_throughput_series(e2e, params, total_steps, rng)
        br_series = self._generate_bitrate_series(params, total_steps, rng)

        # 缓冲区仿真
        buffer_sec = params.buffer_duration
        buffer_trace = np.zeros(total_steps)
        stall_events: list[StallEvent] = []
        stall_total = 0.0
        in_stall = False
        current_stall_start = 0.0

        bitrate_base = params.stream_bitrate

        for i in range(total_steps):
            rx_bits = tp_series[i] * dt
            consume_bits = br_series[i] * dt if not in_stall else 0.0

            buffer_sec += (rx_bits - consume_bits) / bitrate_base
            buffer_sec = min(max(buffer_sec, 0.0), params.buffer_duration)
            buffer_trace[i] = buffer_sec

            if not in_stall:
                if buffer_sec <= 0.0:
                    in_stall = True
                    current_stall_start = i * dt
            else:
                stall_total += dt
                if buffer_sec >= params.buffer_preload_threshold:
                    in_stall = False
                    dur = i * dt - current_stall_start
                    stall_events.append(StallEvent(
                        start_time=round(current_stall_start, 4),
                        duration=round(dur, 4),
                        grade="",  # 稍后分级
                    ))

        # 处理仿真结束时仍在卡顿的情况
        if in_stall:
            dur = params.sim_duration - current_stall_start
            stall_events.append(StallEvent(
                start_time=round(current_stall_start, 4),
                duration=round(dur, 4),
                grade="",
            ))

        stall_rate = (stall_total / params.sim_duration) * 100.0
        stall_count = len(stall_events)
        avg_dur = stall_total / stall_count if stall_count > 0 else 0.0
        first_stall = stall_events[0].start_time if stall_events else -1.0

        # 卡顿分级
        grade_counts = {"轻微": 0, "中度": 0, "重度": 0, "严重": 0}
        for ev in stall_events:
            ev.grade = _classify_stall(ev.duration, stall_rate)
            grade_counts[ev.grade] += 1

        return StallResult(
            stall_rate=round(stall_rate, 4),
            stall_count=stall_count,
            avg_stall_duration=round(avg_dur, 4),
            first_stall_time=round(first_stall, 4),
            effective_throughput=round(e2e.effective_throughput, 4),
            bottleneck=e2e.bottleneck,
            bottleneck_factor=e2e.bottleneck_factor,
            buffer_trace=buffer_trace,
            stall_events=stall_events,
            grade_counts=grade_counts,
        )

    def _generate_throughput_series(
        self, e2e: E2EMetrics, params: SimParams,
        n_steps: int, rng: np.random.Generator,
    ) -> np.ndarray:
        """带随机抖动的瞬时吞吐量序列。"""
        mean_tp = e2e.effective_throughput
        jitter_std = e2e.jitter * mean_tp / 100.0

        series = rng.normal(loc=mean_tp, scale=max(jitter_std, 0.01), size=n_steps)

        # 慢衰落
        t = np.arange(n_steps) * params.time_step
        slow_fade = 1.0 + 0.1 * np.sin(2 * np.pi * t / 12.0)
        series *= slow_fade

        # DBA 带宽波动（PON 侧）
        dba_fluct = 0.1 * params.pon_dba_cycle
        dba_wave = 1.0 + dba_fluct * np.sin(2 * np.pi * t / (params.pon_dba_cycle / 1000.0 + 0.1))
        series *= dba_wave

        # 丢包导致的瞬时归零
        loss_mask = rng.random(n_steps) > e2e.packet_loss
        series *= loss_mask

        np.clip(series, 0.0, None, out=series)
        return series

    def _generate_bitrate_series(
        self, params: SimParams, n_steps: int, rng: np.random.Generator,
    ) -> np.ndarray:
        """码率序列：CBR 恒定，VBR 有波动。"""
        base = params.stream_bitrate
        if params.stream_bitrate_type == "VBR":
            # VBR: 均值=base, 标准差=20%base, 带突峰
            series = rng.normal(loc=base, scale=base * 0.2, size=n_steps)
            # I 帧突峰（每 2 秒一次, 持续 50ms）
            iframe_interval = int(2.0 / params.time_step)
            iframe_dur = int(0.05 / params.time_step)
            for start in range(0, n_steps, iframe_interval):
                end = min(start + iframe_dur, n_steps)
                series[start:end] *= 2.5
            np.clip(series, base * 0.3, base * 4.0, out=series)
            return series
        else:
            return np.full(n_steps, base)
