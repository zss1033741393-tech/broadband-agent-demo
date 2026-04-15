#!/usr/bin/env python3
"""Home WiFi Simulator Skill (Self-Contained).

封装 WiFi 环境仿真的三个核心能力：
1. 输入户型和 AP 数量，输出信号热力图 PNG（400x400 高密度）。
2. 基于信号热力图，输出 RTMP 卡顿率栅格图 PNG（400x400 点状）。
3. 自动 AP 补点推荐并输出补点前后的对比 PNG。

matplotlib 已配置中文字体。所有依赖模型和引擎逻辑均已内嵌到本文件中，无需引用外部文件。
"""

from __future__ import annotations

import copy as _copy
import math
from dataclasses import dataclass, field, fields, asdict
from pathlib import Path
from typing import Tuple, Literal
from abc import ABC, abstractmethod

import matplotlib
import matplotlib.pyplot as plt
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
#  matplotlib 中文字体配置
# ═══════════════════════════════════════════════════════════════════════


def _setup_chinese_font() -> str | None:
    from matplotlib import font_manager

    candidates = [
        "PingFang SC",
        "Heiti SC",
        "SimHei",
        "WenQuanYi Micro Hei",
        "Noto Sans CJK SC",
        "Source Han Sans SC",
        "Microsoft YaHei",
        "Arial Unicode MS",
    ]
    fm = font_manager.FontManager()
    available = {f.name for f in fm.ttflist}
    for font in candidates:
        if font in available:
            matplotlib.rcParams["font.family"] = [font, "sans-serif"]
            matplotlib.rcParams["axes.unicode_minus"] = False
            return font
    matplotlib.rcParams["axes.unicode_minus"] = False
    return None


_FONT_NAME = _setup_chinese_font()

# ─── 暗色主题 rcParams（与前端深色背景风格保持一致）─────────────────────────
_DARK_RC: dict = {
    "figure.facecolor": "#111827",   # 深灰蓝背景（Tailwind gray-900）
    "axes.facecolor":   "#1f2937",   # 数据区域略浅（gray-800）
    "text.color":       "#f9fafb",   # 近白色文字（gray-50）
    "axes.labelcolor":  "#f9fafb",
    "axes.titlecolor":  "#f9fafb",
    "xtick.color":      "#9ca3af",   # 刻度（gray-400）
    "ytick.color":      "#9ca3af",
    "axes.edgecolor":   "#374151",   # 坐标轴边框（gray-700）
    "legend.facecolor": "#1f2937",
    "legend.edgecolor": "#374151",
}


# ═══════════════════════════════════════════════════════════════════════
#  SimParams
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class SimParams:
    """仿真全部输入参数。"""

    # WiFi 物理层 (17 项)
    wifi_channel: int = 36
    wifi_bandwidth: int = 80
    wifi_rssi: float = -50.0
    wifi_noise_floor: float = -90.0
    wifi_interference_ratio: float = 45.0
    sta_count: int = 15
    wifi_standard: str = "wifi6"
    sta_spatial_streams: int = 2
    wifi_retry_rate: float = 5.0
    wifi_multipath_fading: float = 0.2
    wifi_mu_mimo_enabled: bool = True
    wifi_gi: int = 800
    wifi_code_rate: str = "5/6"
    wifi_up_retry_rate: float = 5.0
    wifi_up_tcp_retrans_rate: float = 2.0
    wifi_up_latency: float = 10.0
    wifi_up_jitter: float = 5.0

    # PON 光路物理层 (17 项)
    pon_uplink_bw: float = 50.0
    pon_downlink_bw: float = 1000.0
    pon_bip_error_rate: float = 1e-7
    pon_fec_pre_error_rate: float = 1e-4
    pon_fec_post_error_rate: float = 1e-9
    pon_rx_power: float = -15.0
    pon_split_ratio: int = 64
    pon_up_load_ratio: float = 50.0
    pon_down_load_ratio: float = 40.0
    pon_optical_attenuation: float = 10.0
    pon_dba_cycle: float = 2.0
    pon_burst_collision: float = 0.01
    pon_es: float = 5.0
    user_priority_weight: float = 1.0
    pon_tx_power: float = -10.0
    pon_up_tcp_retrans_rate: float = 2.0
    pon_up_latency: float = 20.0
    pon_up_jitter: float = 10.0

    # RTMP 推流应用层 (9 项)
    rtmp_bitrate: float = 20.0
    rtmp_buffer_ms: int = 200
    video_frame_interval: float = 33.0
    video_frame_avg_size: int = 16384
    rtmp_chunk_size: int = 4096
    tcp_retrans_threshold: float = 5.0
    rtmp_heartbeat_timeout: int = 3000
    t_step: int = 5
    sim_duration: int = 300

    # 仿真控制
    random_seed: int | None = None
    extra: dict = field(default_factory=dict)

    @property
    def total_steps(self) -> int:
        return self.sim_duration * 1000 // self.t_step

    @property
    def buffer_max_size(self) -> float:
        return self.rtmp_buffer_ms * self.rtmp_bitrate * 1024 * 1024 / 8 / 1000

    def validate(self) -> list[str]:
        errors: list[str] = []
        valid_standards = {"wifi4", "wifi5", "wifi6", "wifi6e", "wifi7"}
        if self.wifi_standard not in valid_standards:
            errors.append(f"wifi_standard 必须是 {valid_standards} 之一")
        valid_code_rates = {"1/2", "2/3", "3/4", "5/6"}
        if self.wifi_code_rate not in valid_code_rates:
            errors.append(f"wifi_code_rate 必须是 {valid_code_rates} 之一")
        valid_bandwidths = [20, 40, 80, 160]
        if self.wifi_bandwidth not in valid_bandwidths:
            errors.append(f"wifi_bandwidth 必须是 {valid_bandwidths} 之一")
        valid_gi = [400, 800]
        if self.wifi_gi not in valid_gi:
            errors.append(f"wifi_gi 必须是 {valid_gi} 之一")

        _range_checks: list[tuple[str, float | int, tuple[float, float]]] = [
            ("wifi_rssi", self.wifi_rssi, (-90, -20)),
            ("wifi_noise_floor", self.wifi_noise_floor, (-100, -60)),
            ("wifi_interference_ratio", self.wifi_interference_ratio, (0, 100)),
            ("sta_count", self.sta_count, (1, 64)),
            ("sta_spatial_streams", self.sta_spatial_streams, (1, 4)),
            ("wifi_retry_rate", self.wifi_retry_rate, (0, 50)),
            ("wifi_multipath_fading", self.wifi_multipath_fading, (0, 1)),
            ("wifi_up_retry_rate", self.wifi_up_retry_rate, (0, 50)),
            ("wifi_up_tcp_retrans_rate", self.wifi_up_tcp_retrans_rate, (0, 20)),
            ("wifi_up_latency", self.wifi_up_latency, (1, 100)),
            ("wifi_up_jitter", self.wifi_up_jitter, (1, 50)),
            ("pon_uplink_bw", self.pon_uplink_bw, (0, 2500)),
            ("pon_downlink_bw", self.pon_downlink_bw, (0, 2500)),
            ("pon_bip_error_rate", self.pon_bip_error_rate, (0, 1e-3)),
            ("pon_fec_pre_error_rate", self.pon_fec_pre_error_rate, (0, 1e-2)),
            ("pon_fec_post_error_rate", self.pon_fec_post_error_rate, (0, 1e-6)),
            ("pon_rx_power", self.pon_rx_power, (-28, -8)),
            ("pon_split_ratio", self.pon_split_ratio, (16, 128)),
            ("pon_up_load_ratio", self.pon_up_load_ratio, (0, 100)),
            ("pon_down_load_ratio", self.pon_down_load_ratio, (0, 100)),
            ("pon_optical_attenuation", self.pon_optical_attenuation, (0, 25)),
            ("pon_dba_cycle", self.pon_dba_cycle, (1, 10)),
            ("pon_burst_collision", self.pon_burst_collision, (0, 0.1)),
            ("pon_es", self.pon_es, (0, 100)),
            ("user_priority_weight", self.user_priority_weight, (0, 1)),
            ("pon_tx_power", self.pon_tx_power, (-15, -5)),
            ("pon_up_tcp_retrans_rate", self.pon_up_tcp_retrans_rate, (0, 20)),
            ("pon_up_latency", self.pon_up_latency, (5, 200)),
            ("pon_up_jitter", self.pon_up_jitter, (1, 100)),
            ("rtmp_bitrate", self.rtmp_bitrate, (2, 20)),
            ("rtmp_buffer_ms", self.rtmp_buffer_ms, (0, 300)),
            ("video_frame_interval", self.video_frame_interval, (8.3, 66)),
            ("video_frame_avg_size", self.video_frame_avg_size, (4096, 65536)),
            ("rtmp_chunk_size", self.rtmp_chunk_size, (1024, 8192)),
            ("tcp_retrans_threshold", self.tcp_retrans_threshold, (1, 10)),
            ("rtmp_heartbeat_timeout", self.rtmp_heartbeat_timeout, (2000, 5000)),
            ("sim_duration", self.sim_duration, (10, float("inf"))),
        ]
        for name, value, (lo, hi) in _range_checks:
            if not (lo <= value <= hi):
                errors.append(f"{name} 超出范围 [{lo}, {hi}], 当前: {value}")
        if self.t_step != 5:
            errors.append(f"t_step 固定为 5 ms, 不可修改")
        valid_2g = set(range(1, 14))
        valid_5g = set(range(36, 166))
        if self.wifi_channel not in valid_2g | valid_5g:
            errors.append("wifi_channel 必须在 1-13 或 36-165 范围内")
        return errors

    def copy(self) -> SimParams:
        return _copy.deepcopy(self)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SimParams:
        known = {f.name for f in fields(cls)}
        init_kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        params = cls(**init_kwargs)
        params.extra.update(extra)
        return params


# ═══════════════════════════════════════════════════════════════════════
#  StateRecorder
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class StallEvent:
    start_step: int
    end_step: int
    duration_ms: float
    stall_type: str


@dataclass
class SimulationSummary:
    total_steps: int = 0
    sim_duration_ms: float = 0.0
    rtmp_stall_rate: float = 0.0
    stall_steps: int = 0
    stall_count: int = 0
    avg_stall_duration_ms: float = 0.0
    stall_type_distribution: dict = field(default_factory=dict)
    buffer_empty_ratio: float = 0.0
    avg_buffer_watermark: float = 0.0
    tcp_block_ratio: float = 0.0
    avg_tcp_retrans_rate: float = 0.0
    reconnect_count: int = 0
    avg_effective_throughput: float = 0.0
    bandwidth_meet_rate: float = 0.0
    avg_up_latency: float = 0.0
    avg_up_jitter: float = 0.0
    stall_events: list = field(default_factory=list)
    bottleneck: str = ""
    abnormal_params: list = field(default_factory=list)


class StateRecorder:
    def __init__(self, t_step: int = 5):
        self.t_step = t_step
        self.records: list[dict] = []

    def record(self, state: dict):
        self.records.append(state)

    def summarize(self, params) -> SimulationSummary:
        summary = SimulationSummary()
        n = len(self.records)
        if n == 0:
            return summary
        summary.total_steps = n
        summary.sim_duration_ms = n * self.t_step

        stall_steps = 0
        buffer_empty_steps = 0
        tcp_block_steps = 0
        reconnect_count = 0
        total_buffer = 0.0
        total_tcp_retrans = 0.0
        total_throughput = 0.0
        total_latency = 0.0
        total_jitter = 0.0
        bandwidth_meet_steps = 0

        stall_type_counts = {
            "buffer_empty": 0,
            "frame_timeout": 0,
            "tcp_block": 0,
            "reconnect": 0,
        }

        in_stall = False
        stall_start = 0
        current_stall_type = ""
        stall_events: list[StallEvent] = []

        for rec in self.records:
            if rec.get("stall_active", False):
                stall_steps += 1
                ptype = rec.get("primary_stall_type", "")
                if ptype in stall_type_counts:
                    stall_type_counts[ptype] += 1
                if not in_stall:
                    in_stall = True
                    stall_start = rec["step"]
                    current_stall_type = ptype
            else:
                if in_stall:
                    stall_events.append(
                        StallEvent(
                            start_step=stall_start,
                            end_step=rec["step"] - 1,
                            duration_ms=(rec["step"] - stall_start) * self.t_step,
                            stall_type=current_stall_type,
                        )
                    )
                    in_stall = False

            if rec.get("buffer_empty_flag", 0) == 1:
                buffer_empty_steps += 1
            if rec.get("tcp_block_flag", 0) == 1:
                tcp_block_steps += 1
            if rec.get("reconnect_flag", 0) == 1:
                reconnect_count += 1

            total_buffer += rec.get("buffer_watermark", 0.0)
            total_tcp_retrans += rec.get("tcp_retrans_rate", 0.0)
            total_throughput += rec.get("effective_up_throughput", 0.0)
            total_latency += rec.get("up_latency", 0.0)
            total_jitter += rec.get("up_jitter", 0.0)

            if rec.get("effective_up_throughput", 0.0) >= params.rtmp_bitrate:
                bandwidth_meet_steps += 1

        if in_stall:
            stall_events.append(
                StallEvent(
                    start_step=stall_start,
                    end_step=self.records[-1]["step"],
                    duration_ms=(self.records[-1]["step"] - stall_start + 1)
                    * self.t_step,
                    stall_type=current_stall_type,
                )
            )

        summary.stall_steps = stall_steps
        summary.rtmp_stall_rate = (stall_steps / n) * 100.0 if n > 0 else 0.0
        summary.stall_count = len(stall_events)
        summary.avg_stall_duration_ms = (
            sum(e.duration_ms for e in stall_events) / len(stall_events)
            if stall_events
            else 0.0
        )
        summary.stall_type_distribution = stall_type_counts
        summary.buffer_empty_ratio = (buffer_empty_steps / n) * 100.0
        summary.avg_buffer_watermark = total_buffer / n
        summary.tcp_block_ratio = (tcp_block_steps / n) * 100.0
        summary.avg_tcp_retrans_rate = total_tcp_retrans / n
        summary.reconnect_count = reconnect_count
        summary.avg_effective_throughput = total_throughput / n
        summary.bandwidth_meet_rate = (bandwidth_meet_steps / n) * 100.0
        summary.avg_up_latency = total_latency / n
        summary.avg_up_jitter = total_jitter / n
        summary.stall_events = stall_events

        avg_wifi = sum(r.get("wifi_throughput", 0) for r in self.records) / n
        avg_pon = sum(r.get("pon_up_effective_bw", 0) for r in self.records) / n
        if avg_wifi < avg_pon * 0.9:
            summary.bottleneck = "WiFi上行"
        elif avg_pon < avg_wifi * 0.9:
            summary.bottleneck = "PON上行"
        else:
            summary.bottleneck = "WiFi上行+PON上行"

        abnormals = []
        if summary.avg_tcp_retrans_rate * 100 >= 5:
            abnormals.append(
                {
                    "param": "tcp_retrans_rate",
                    "avg_value": round(summary.avg_tcp_retrans_rate * 100, 1),
                }
            )
        if summary.avg_up_latency >= 50:
            abnormals.append(
                {"param": "up_latency", "avg_value": round(summary.avg_up_latency, 1)}
            )
        if summary.avg_up_jitter >= 30:
            abnormals.append(
                {"param": "up_jitter", "avg_value": round(summary.avg_up_jitter, 1)}
            )
        if summary.buffer_empty_ratio >= 10:
            abnormals.append(
                {
                    "param": "buffer_empty_ratio",
                    "avg_value": round(summary.buffer_empty_ratio, 1),
                }
            )
        summary.abnormal_params = abnormals

        return summary

    def get_timeseries(self, keys: list[str] | None = None) -> dict[str, list]:
        if keys is None:
            keys = [
                "effective_up_throughput",
                "buffer_watermark",
                "stall_active",
                "primary_stall_type",
                "tcp_retrans_rate",
                "up_latency",
                "up_jitter",
                "frame_gen_flag",
                "frame_drop_flag",
            ]
        result: dict[str, list] = {k: [] for k in keys}
        result["time_ms"] = []
        result["step"] = []
        for rec in self.records:
            result["time_ms"].append(rec.get("time_ms", 0))
            result["step"].append(rec.get("step", 0))
            for k in keys:
                result[k].append(rec.get(k, 0))
        return result

    def reset(self):
        self.records = []


# ═══════════════════════════════════════════════════════════════════════
#  Models
# ═══════════════════════════════════════════════════════════════════════


class WifiUpThroughputModel:
    """WiFi上行吞吐量模型。"""

    _MCS_TABLE_WIFI6_80MHZ = [
        (35, 11, 143.4),
        (30, 9, 120.1),
        (25, 7, 97.5),
        (20, 5, 65.0),
        (15, 3, 39.0),
        (10, 1, 16.3),
        (float("-inf"), 0, 8.1),
    ]
    _STANDARD_SCALE = {
        "wifi4": 0.55,
        "wifi5": 0.78,
        "wifi6": 1.0,
        "wifi6e": 1.0,
        "wifi7": 1.15,
    }
    _AIRTIME_EFF = {
        "wifi4": (0.55, 0.55),
        "wifi5": (0.65, 0.70),
        "wifi6": (0.78, 0.83),
        "wifi6e": (0.78, 0.83),
        "wifi7": (0.82, 0.88),
    }
    _CODE_RATE_EFF = {
        "1/2": 0.50,
        "2/3": 0.67,
        "3/4": 0.75,
        "5/6": 0.83,
    }

    def calculate(self, params) -> float:
        snr = self._calc_snr(params)
        phy_rate = self._lookup_phy_rate(snr, params)
        throughput = self._calc_throughput(phy_rate, snr, params)
        return max(throughput, 0.0)

    @staticmethod
    def _calc_snr(params) -> float:
        fading_loss = 10.0 * math.log10(1.0 + params.wifi_multipath_fading)
        return params.wifi_rssi - params.wifi_noise_floor - fading_loss

    def _lookup_phy_rate(self, snr: float, params) -> float:
        base_rate = 8.1
        for snr_thresh, mcs, rate in self._MCS_TABLE_WIFI6_80MHZ:
            if snr >= snr_thresh:
                base_rate = rate
                break
        bw_scale = params.wifi_bandwidth / 80.0
        std_scale = self._STANDARD_SCALE.get(params.wifi_standard, 1.0)
        return base_rate * bw_scale * std_scale

    def _calc_throughput(self, phy_rate: float, snr: float, params) -> float:
        streams = params.sta_spatial_streams
        std = params.wifi_standard
        eff_pair = self._AIRTIME_EFF.get(std, (0.70, 0.75))
        airtime_eff = eff_pair[1] if params.wifi_mu_mimo_enabled else eff_pair[0]
        contention = self._contention_factor(
            params.sta_count, params.wifi_standard, params.wifi_gi
        )
        code_eff = self._CODE_RATE_EFF.get(params.wifi_code_rate, 0.75)
        throughput = (
            phy_rate
            * streams
            * (1.0 - params.wifi_interference_ratio / 100.0)
            * (1.0 - params.wifi_retry_rate / 100.0)
            * airtime_eff
            / contention
            * code_eff
        )
        return throughput

    @staticmethod
    def _contention_factor(sta_count: int, standard: str, gi: int) -> float:
        n = max(sta_count, 1)
        alpha = 0.15 if standard in ("wifi6", "wifi6e", "wifi7") else 0.3
        factor = 1.0 + alpha * math.log(n)
        if gi >= 800:
            factor *= 1.05
        else:
            factor *= 0.95
        return max(factor, 1.0)


class PonUpThroughputModel:
    """PON吞吐量模型。"""

    def calculate_up(self, params) -> float:
        base = self._up_base_bw(params)
        effective = self._dba_up_effective(base, params)
        return max(effective, 0.0)

    @staticmethod
    def _optical_attenuation_factor(attenuation: float) -> float:
        if attenuation <= 18:
            return 1.0
        elif attenuation <= 22:
            return 0.85
        else:
            return 0.65

    @staticmethod
    def _tx_power_factor(tx_power: float) -> float:
        if -15.0 <= tx_power <= -5.0:
            return 1.0
        elif tx_power < -15.0:
            return max(1.0 + (tx_power + 15.0) * 0.1, 0.1)
        else:
            return max(1.0 - (tx_power + 5.0) * 0.1, 0.1)

    def _up_base_bw(self, params) -> float:
        retrans_overhead = 1.3
        oaf = self._optical_attenuation_factor(params.pon_optical_attenuation)
        tpf = self._tx_power_factor(getattr(params, "pon_tx_power", -10.0))
        bw = (
            params.pon_uplink_bw
            * (1.0 - params.pon_fec_post_error_rate)
            * (1.0 - params.pon_bip_error_rate * retrans_overhead)
            * oaf
            * tpf
        )
        return max(bw, 0.0)

    @staticmethod
    def _dba_up_effective(base_bw: float, params) -> float:
        load = params.pon_up_load_ratio
        pool = base_bw * (1.0 - load / 100.0)
        allocated = pool * params.user_priority_weight
        fluctuation = 0.1 * params.pon_dba_cycle + params.pon_burst_collision * 0.5
        effective = allocated * (1.0 - fluctuation)
        if load >= 70:
            congestion_loss = 0.01 * (load - 70)
            effective *= 1.0 - congestion_loss
        return effective


class E2EUpQualityModel:
    """端到端上行传输质量模型。"""

    def calculate(
        self, wifi_throughput: float, pon_up_effective_bw: float, params
    ) -> dict:
        effective_up_throughput = min(wifi_throughput, pon_up_effective_bw)
        effective_up_throughput = max(effective_up_throughput, 0.001)

        wifi_tcp = params.wifi_up_tcp_retrans_rate / 100.0
        pon_tcp = params.pon_up_tcp_retrans_rate / 100.0
        tcp_retrans_rate = 1.0 - (1.0 - wifi_tcp) * (1.0 - pon_tcp)

        up_latency = (
            params.wifi_up_latency + params.pon_up_latency + tcp_retrans_rate * 100.0
        )
        up_jitter = (
            params.wifi_up_jitter + params.pon_up_jitter + 0.2 * params.pon_dba_cycle
        )
        chunk_trans_latency = (
            (params.rtmp_chunk_size * 8)
            / (effective_up_throughput * 1024 * 1024)
            * 1000
        )
        frame_trans_latency = (
            (params.video_frame_avg_size * 8)
            / (effective_up_throughput * 1024 * 1024)
            * 1000
        )
        rtt = 2.0 * up_latency

        return {
            "effective_up_throughput": effective_up_throughput,
            "tcp_retrans_rate": tcp_retrans_rate,
            "up_latency": up_latency,
            "up_jitter": up_jitter,
            "chunk_trans_latency": chunk_trans_latency,
            "frame_trans_latency": frame_trans_latency,
            "rtt": rtt,
        }


class RtmpCoreModel:
    """RTMP推流核心过程模型。"""

    def compute_rtmp_kpi(self, step: int, params, trans_kpi: dict) -> dict:
        time_ms = step * params.t_step

        frame_gen_flag = 0
        if params.video_frame_interval > 0:
            t_start = (step - 1) * params.t_step if step > 0 else 0
            t_end = step * params.t_step
            frame_idx_start = math.ceil(t_start / params.video_frame_interval)
            frame_idx_end = math.ceil(t_end / params.video_frame_interval)
            if t_end > 0 and frame_idx_start < frame_idx_end:
                frame_gen_flag = 1

        chunk_num = 0
        if frame_gen_flag == 1:
            chunk_num = math.ceil(params.video_frame_avg_size / params.rtmp_chunk_size)

        tcp_retrans_rate_pct = trans_kpi["tcp_retrans_rate"] * 100.0
        tcp_block_flag = 1 if tcp_retrans_rate_pct > params.tcp_retrans_threshold else 0

        heartbeat_check_flag = 0
        if time_ms > 0 and time_ms % 1000 == 0:
            heartbeat_check_flag = 1

        reconnect_flag = 0
        if (
            heartbeat_check_flag == 1
            and trans_kpi["rtt"] > params.rtmp_heartbeat_timeout
        ):
            reconnect_flag = 1

        return {
            "frame_gen_flag": frame_gen_flag,
            "chunk_num": chunk_num,
            "tcp_block_flag": tcp_block_flag,
            "heartbeat_check_flag": heartbeat_check_flag,
            "reconnect_flag": reconnect_flag,
        }

    def compute_buffer_kpi(
        self,
        params,
        prev_buffer_watermark: float,
        buffer_max_size: float,
        rtmp_kpi: dict,
        trans_kpi: dict,
    ) -> dict:
        in_size = params.rtmp_bitrate * 1024 * 1024 / 8 * params.t_step / 1000

        if rtmp_kpi["tcp_block_flag"] == 1 or rtmp_kpi["reconnect_flag"] == 1:
            out_size = 0.0
        else:
            out_size = (
                trans_kpi["effective_up_throughput"]
                * 1024
                * 1024
                / 8
                * params.t_step
                / 1000
            )

        new_watermark = prev_buffer_watermark + in_size - out_size

        frame_drop_flag = 0
        if new_watermark > buffer_max_size:
            frame_drop_flag = 1
            new_watermark = buffer_max_size

        buffer_watermark = max(0.0, new_watermark)
        buffer_empty_flag = 1 if buffer_watermark <= 0 else 0

        return {
            "buffer_watermark": buffer_watermark,
            "buffer_empty_flag": buffer_empty_flag,
            "frame_drop_flag": frame_drop_flag,
            "in_size": in_size,
            "out_size": out_size,
        }


class RtmpStallDetector:
    """RTMP实时卡顿判定器。"""

    T1_TH = 10
    T2_TH = 8
    T3_TH = 20
    T4_TH = 1
    STALL_TYPES = ["reconnect", "buffer_empty", "tcp_block", "frame_timeout"]

    def detect(
        self,
        buffer_kpi: dict,
        rtmp_kpi: dict,
        trans_kpi: dict,
        params,
        prev_c1: int,
        prev_c2: int,
        prev_c3: int,
        prev_c4: int,
        prev_s1: int,
        prev_s2: int,
        prev_s3: int,
        prev_s4: int,
    ) -> dict:
        p1 = buffer_kpi["frame_drop_flag"]
        p2 = (
            1
            if trans_kpi["frame_trans_latency"] > params.video_frame_interval * 2
            else 0
        )
        p3 = rtmp_kpi["tcp_block_flag"]
        p4 = rtmp_kpi["reconnect_flag"]

        c1 = (prev_c1 + 1) if p1 == 1 else 0
        c2 = (prev_c2 + 1) if p2 == 1 else 0
        c3 = (prev_c3 + 1) if p3 == 1 else 0
        c4 = (prev_c4 + 1) if p4 == 1 else 0

        s1 = self._judge_state(p1, c1, self.T1_TH, prev_s1)
        s2 = self._judge_state(p2, c2, self.T2_TH, prev_s2)
        s3 = self._judge_state(p3, c3, self.T3_TH, prev_s3)
        if p4 == 1:
            s4 = 1
        elif prev_s4 == 1:
            s4 = 2
        else:
            s4 = 0

        stall_active = any(s == 1 for s in [s1, s2, s3, s4])
        primary_stall_type = ""
        if stall_active:
            states = [s4, s1, s3, s2]
            for i, s in enumerate(states):
                if s == 1:
                    primary_stall_type = self.STALL_TYPES[i]
                    break

        return {
            "p1": p1,
            "p2": p2,
            "p3": p3,
            "p4": p4,
            "c1": c1,
            "c2": c2,
            "c3": c3,
            "c4": c4,
            "s1": s1,
            "s2": s2,
            "s3": s3,
            "s4": s4,
            "stall_active": stall_active,
            "primary_stall_type": primary_stall_type,
        }

    @staticmethod
    def _judge_state(p: int, c: int, threshold: int, prev_s: int) -> int:
        if p == 1 and c >= threshold:
            return 1
        elif p == 0 and prev_s == 1:
            return 2
        else:
            return 0


# ═══════════════════════════════════════════════════════════════════════
#  Faults
# ═══════════════════════════════════════════════════════════════════════


FAULT_CATALOG = {
    1: {
        "name": "频繁WiFi漫游",
        "severity": "严重",
        "bound_measures": ["wifi_roaming_opt"],
    },
    2: {
        "name": "WiFi干扰严重",
        "severity": "中度",
        "bound_measures": ["wifi_channel_opt", "wifi_band_opt"],
    },
    3: {"name": "WiFi覆盖弱", "severity": "严重", "bound_measures": ["wifi_add_ap"]},
    4: {
        "name": "上行带宽不足",
        "severity": "中度",
        "bound_measures": ["pon_expansion", "upgrade_package"],
    },
    5: {
        "name": "PON口拥塞",
        "severity": "中度",
        "bound_measures": ["pon_traffic_limit"],
    },
    6: {"name": "多STA竞争", "severity": "轻度", "bound_measures": ["wifi_timeslot"]},
    7: {
        "name": "PON光纤中断",
        "severity": "严重",
        "bound_measures": ["pon_fiber_repair"],
    },
}


@dataclass
class FaultConfig:
    enabled_faults: list[int] = field(default_factory=list)
    fault_start_step: int = 1000
    fault_duration_step: int = 40000
    fault_recover_flag: bool = False
    recovery_measures: list[str] | None = None
    fault_inject_mode: Literal["fixed", "random"] = "fixed"
    random_fault_count: int = 5
    random_fault_max_duration: int = 2000
    _random_segments: list[tuple[int, int]] = field(default_factory=list, repr=False)

    @property
    def is_active(self) -> bool:
        return len(self.enabled_faults) > 0

    def fault_end_step(self, total_steps: int) -> int:
        if self.fault_inject_mode == "random":
            if not self._random_segments:
                return 0
            return max(s + d for s, d in self._random_segments)
        if self.fault_duration_step == -1:
            return total_steps
        return min(self.fault_start_step + self.fault_duration_step, total_steps)

    def generate_random_segments(
        self, total_steps: int, rng: np.random.Generator
    ) -> None:
        segments: list[tuple[int, int]] = []
        for _ in range(self.random_fault_count):
            start = int(rng.integers(1, total_steps + 1))
            duration = int(rng.integers(1, self.random_fault_max_duration + 1))
            segments.append((start, duration))
        segments.sort(key=lambda s: s[0])
        self._random_segments = segments

    def is_fault_active_at(self, step: int, total_steps: int) -> bool:
        if self.fault_inject_mode == "fixed":
            start = self.fault_start_step
            end = self.fault_end_step(total_steps)
            return start <= step <= end
        for seg_start, seg_dur in self._random_segments:
            if seg_start <= step <= seg_start + seg_dur:
                return True
        return False

    def is_recovery_active_at(self, step: int, total_steps: int) -> bool:
        if not self.fault_recover_flag:
            return False
        if self.fault_inject_mode == "fixed":
            return step > self.fault_end_step(total_steps)
        if self.is_fault_active_at(step, total_steps):
            return False
        return step > self.fault_end_step(total_steps)


def inject_faults(
    params: SimParams,
    step: int,
    config: FaultConfig,
    total_steps: int,
    rng: np.random.Generator | None = None,
) -> SimParams:
    if not config.is_active:
        return params
    if not config.is_fault_active_at(step, total_steps):
        return params
    if rng is None:
        rng = np.random.default_rng()
    p = params.copy()
    for fid in config.enabled_faults:
        if fid == 1:
            p.wifi_rssi = float(rng.uniform(-85, -75))
            p.wifi_up_retry_rate = float(rng.uniform(30, 40))
            p.wifi_up_latency = 80.0
            p.wifi_up_tcp_retrans_rate = 15.0
        elif fid == 2:
            p.wifi_interference_ratio = float(rng.uniform(40, 60))
            p.wifi_noise_floor = float(rng.uniform(-70, -60))
            p.wifi_up_tcp_retrans_rate = 10.0
            p.wifi_up_jitter = float(rng.uniform(35, 45))
        elif fid == 3:
            p.wifi_rssi = -88.0
            p.wifi_multipath_fading = 0.9
            p.wifi_up_retry_rate = 50.0
        elif fid == 4:
            p.pon_uplink_bw = 3.0
            p.pon_up_load_ratio = max(p.pon_up_load_ratio, 80.0)
            p.pon_up_tcp_retrans_rate = max(p.pon_up_tcp_retrans_rate, 8.0)
            p.pon_up_latency = max(p.pon_up_latency, 80.0)
        elif fid == 5:
            p.pon_up_load_ratio = 95.0
            p.pon_burst_collision = 0.08
            p.pon_up_latency = 120.0
            p.pon_up_jitter = 80.0
        elif fid == 6:
            p.sta_count = 60
            p.wifi_mu_mimo_enabled = False
        elif fid == 7:
            p.pon_optical_attenuation = 25.0
    return p


# ═══════════════════════════════════════════════════════════════════════
#  SimulationEngine (self-contained)
# ═══════════════════════════════════════════════════════════════════════


class SimulationEngine:
    """简化版仿真引擎，内嵌所有模型，无需外部 measures/faults 依赖。"""

    def __init__(self):
        self.wifi_model = WifiUpThroughputModel()
        self.pon_model = PonUpThroughputModel()
        self.e2e_model = E2EUpQualityModel()
        self.rtmp_model = RtmpCoreModel()
        self.stall_detector = RtmpStallDetector()

    def simulate(
        self,
        params: SimParams,
        *,
        collect_timeseries: bool = True,
        rng: np.random.Generator | None = None,
        fault_config: FaultConfig | None = None,
        initial_prev: dict | None = None,
        step_offset: int = 0,
    ) -> tuple[SimulationSummary, dict | None, dict]:
        if rng is None:
            seed = params.random_seed if params.random_seed is not None else 42
            rng = np.random.default_rng(seed)

        t_step = params.t_step
        total_steps = params.total_steps
        buffer_max_size = params.buffer_max_size

        if (
            fault_config
            and fault_config.is_active
            and fault_config.fault_inject_mode == "random"
        ):
            fault_config.generate_random_segments(total_steps, rng)

        recorder = StateRecorder(t_step=t_step)

        if initial_prev is not None:
            prev = dict(initial_prev)
        else:
            prev = {
                "buffer_watermark": buffer_max_size,
                "c1": 0,
                "c2": 0,
                "c3": 0,
                "c4": 0,
                "s1": 0,
                "s2": 0,
                "s3": 0,
                "s4": 0,
            }

        rssi_slow = self._slow_fading(total_steps, sigma=2.0, rng=rng)
        rssi_fast = rng.normal(0, 1.0, total_steps)
        interf_noise = rng.normal(0, 2.0, total_steps)
        pon_load_noise = rng.normal(0, 3.0, total_steps)
        wifi_latency_noise = rng.normal(0, 1.0, total_steps)
        pon_latency_noise = rng.normal(0, 2.0, total_steps)
        wifi_jitter_noise = rng.exponential(1.0, total_steps)
        pon_jitter_noise = rng.exponential(1.5, total_steps)
        wifi_tcp_noise = rng.exponential(0.5, total_steps)
        pon_tcp_noise = rng.exponential(0.3, total_steps)

        for n in range(1, total_steps + 1):
            idx = n - 1
            global_step = step_offset + n

            inst = params.copy()
            inst.wifi_rssi = params.wifi_rssi + rssi_slow[idx] + rssi_fast[idx]
            inst.wifi_interference_ratio = max(
                0, min(100, params.wifi_interference_ratio + interf_noise[idx])
            )
            inst.pon_up_load_ratio = max(
                0, min(100, params.pon_up_load_ratio + pon_load_noise[idx])
            )
            inst.wifi_up_latency = max(
                1, params.wifi_up_latency + wifi_latency_noise[idx]
            )
            inst.pon_up_latency = max(5, params.pon_up_latency + pon_latency_noise[idx])
            inst.wifi_up_jitter = max(1, params.wifi_up_jitter + wifi_jitter_noise[idx])
            inst.pon_up_jitter = max(1, params.pon_up_jitter + pon_jitter_noise[idx])
            inst.wifi_up_tcp_retrans_rate = max(
                0, min(20, params.wifi_up_tcp_retrans_rate + wifi_tcp_noise[idx])
            )
            inst.pon_up_tcp_retrans_rate = max(
                0, min(20, params.pon_up_tcp_retrans_rate + pon_tcp_noise[idx])
            )

            if fault_config and fault_config.is_active:
                inst = inject_faults(inst, n, fault_config, total_steps, rng=rng)

            wifi_tp = self.wifi_model.calculate(inst)
            pon_up_bw = self.pon_model.calculate_up(inst)
            trans_kpi = self.e2e_model.calculate(wifi_tp, pon_up_bw, inst)
            rtmp_kpi = self.rtmp_model.compute_rtmp_kpi(n, inst, trans_kpi)
            buffer_kpi = self.rtmp_model.compute_buffer_kpi(
                inst, prev["buffer_watermark"], buffer_max_size, rtmp_kpi, trans_kpi
            )
            stall_kpi = self.stall_detector.detect(
                buffer_kpi,
                rtmp_kpi,
                trans_kpi,
                inst,
                prev["c1"],
                prev["c2"],
                prev["c3"],
                prev["c4"],
                prev["s1"],
                prev["s2"],
                prev["s3"],
                prev["s4"],
            )

            state = {
                "step": global_step,
                "time_ms": global_step * t_step,
                "wifi_throughput": wifi_tp,
                "pon_up_effective_bw": pon_up_bw,
                **trans_kpi,
                **rtmp_kpi,
                **buffer_kpi,
                **stall_kpi,
            }
            recorder.record(state)

            prev["buffer_watermark"] = buffer_kpi["buffer_watermark"]
            prev["c1"] = stall_kpi["c1"]
            prev["c2"] = stall_kpi["c2"]
            prev["c3"] = stall_kpi["c3"]
            prev["c4"] = stall_kpi["c4"]
            prev["s1"] = stall_kpi["s1"]
            prev["s2"] = stall_kpi["s2"]
            prev["s3"] = stall_kpi["s3"]
            prev["s4"] = stall_kpi["s4"]

        summary = recorder.summarize(params)
        timeseries = recorder.get_timeseries() if collect_timeseries else None
        return summary, timeseries, prev

    @staticmethod
    def _slow_fading(n: int, sigma: float, rng: np.random.Generator) -> np.ndarray:
        raw = rng.normal(0, sigma, n)
        alpha = 0.005
        out = np.zeros(n)
        out[0] = raw[0]
        for i in range(1, n):
            out[i] = out[i - 1] * (1 - alpha) + raw[i] * alpha
        return out


# ═══════════════════════════════════════════════════════════════════════
#  Home Environment
# ═══════════════════════════════════════════════════════════════════════


GRID_SIZE = 40


@dataclass
class Wall:
    x1: float
    y1: float
    x2: float
    y2: float
    attenuation_db: float = 6.0
    label: str = ""


@dataclass
class Room:
    name: str
    x: float
    y: float
    w: float
    h: float


@dataclass
class Door:
    x1: float
    y1: float
    x2: float
    y2: float
    label: str = ""


@dataclass
class AP:
    x: float
    y: float
    tx_power_dbm: float = 10.0
    label: str = "AP"


@dataclass
class STA:
    x: float
    y: float
    label: str = "STA"


@dataclass
class FloorPlan:
    name: str
    width: float
    height: float
    rooms: list[Room] = field(default_factory=list)
    walls: list[Wall] = field(default_factory=list)
    doors: list[Door] = field(default_factory=list)
    aps: list[AP] = field(default_factory=list)
    stas: list[STA] = field(default_factory=list)


def create_one_bedroom() -> FloorPlan:
    fp = FloorPlan(name="一居室", width=8, height=6)
    fp.rooms = [
        Room("客厅", 0, 0, 5, 6),
        Room("卧室", 5, 3, 3, 3),
        Room("厨卫", 5, 0, 3, 3),
    ]
    fp.walls = [
        Wall(0, 0, 8, 0, 10, "南外墙"),
        Wall(8, 0, 8, 6, 10, "东外墙"),
        Wall(8, 6, 0, 6, 10, "北外墙"),
        Wall(0, 6, 0, 0, 10, "西外墙"),
        Wall(5, 0, 5, 6, 6, "客厅-东墙"),
        Wall(5, 3, 8, 3, 4, "卧室-厨卫隔墙"),
    ]
    fp.aps = [AP(2.5, 3.0, label="AP1")]
    return fp


def create_two_bedroom() -> FloorPlan:
    fp = FloorPlan(name="两居室", width=10, height=8)
    fp.rooms = [
        Room("客厅", 0, 0, 6, 5),
        Room("厨房", 6, 0, 4, 3),
        Room("卫生间", 6, 3, 4, 2),
        Room("主卧", 0, 5, 5, 3),
        Room("次卧", 5, 5, 5, 3),
    ]
    fp.walls = [
        Wall(0, 0, 10, 0, 10, ""),
        Wall(10, 0, 10, 8, 10, ""),
        Wall(10, 8, 0, 8, 10, ""),
        Wall(0, 8, 0, 0, 10, ""),
        Wall(6, 0, 6, 5, 6, "客厅-厨房"),
        Wall(6, 3, 10, 3, 4, "厨房-卫生间"),
        Wall(0, 5, 10, 5, 6, "南-北隔墙"),
        Wall(5, 5, 5, 8, 6, "主卧-次卧"),
    ]
    fp.aps = [AP(3.0, 2.5, label="AP1")]
    return fp


def create_three_bedroom() -> FloorPlan:
    fp = FloorPlan(name="三居室", width=12, height=10)
    fp.rooms = [
        Room("客厅", 0, 0, 7, 5),
        Room("厨房", 7, 0, 5, 3),
        Room("卫生间", 7, 3, 5, 2),
        Room("主卧", 0, 5, 4, 5),
        Room("次卧1", 4, 5, 4, 5),
        Room("次卧2", 8, 5, 4, 5),
    ]
    fp.walls = [
        Wall(0, 0, 12, 0, 10, ""),
        Wall(12, 0, 12, 10, 10, ""),
        Wall(12, 10, 0, 10, 10, ""),
        Wall(0, 10, 0, 0, 10, ""),
        Wall(7, 0, 7, 5, 6, ""),
        Wall(7, 3, 12, 3, 4, ""),
        Wall(0, 5, 12, 5, 6, ""),
        Wall(4, 5, 4, 10, 6, ""),
        Wall(8, 5, 8, 10, 6, ""),
    ]
    fp.aps = [AP(3.5, 2.5, label="AP1")]
    return fp


def create_large_flat() -> FloorPlan:
    """大平层 ~180m²: 开放客餐厅+主卧套+次卧×2+书房+厨房+卫×2。"""
    fp = FloorPlan(name="大平层", width=15, height=12)
    fp.rooms = [
        Room("客餐厅", 0, 0, 9, 6),
        Room("厨房", 9, 0, 6, 4),
        Room("卫生间1", 9, 4, 3, 2),
        Room("书房", 12, 4, 3, 2),
        Room("主卧", 0, 6, 5, 6),
        Room("主卫", 5, 6, 3, 3),
        Room("次卧1", 5, 9, 5, 3),
        Room("次卧2", 10, 6, 5, 6),
    ]
    fp.walls = [
        Wall(0, 0, 15, 0, 10, ""),
        Wall(15, 0, 15, 12, 10, ""),
        Wall(15, 12, 0, 12, 10, ""),
        Wall(0, 12, 0, 0, 10, ""),
        Wall(9, 0, 9, 6, 6, ""),
        Wall(9, 4, 15, 4, 4, ""),
        Wall(12, 4, 12, 6, 4, ""),
        Wall(0, 6, 15, 6, 6, ""),
        Wall(5, 6, 5, 12, 6, ""),
        Wall(5, 9, 10, 9, 4, ""),
        Wall(10, 6, 10, 12, 6, ""),
    ]
    fp.aps = [AP(4.5, 3.0, label="AP1")]
    return fp


PRESETS: dict[str, callable] = {
    "一居室": create_one_bedroom,
    "两居室": create_two_bedroom,
    "三居室": create_three_bedroom,
    "大平层": create_large_flat,
}


def _apply_doors_to_large_flat(fp: FloorPlan) -> None:
    """大平层精细化墙体：以分段 Wall 表达门洞空缺，并设置 doors 列表。"""
    fp.walls = [
        Wall(0, 0, 3, 0, 10, ""),
        Wall(4.5, 0, 15, 0, 10, ""),
        Wall(15, 0, 15, 12, 10, ""),
        Wall(15, 12, 0, 12, 10, ""),
        Wall(0, 12, 0, 0, 10, ""),
        Wall(9, 0, 9, 1.5, 6, ""),
        Wall(9, 3.5, 9, 6, 6, ""),
        Wall(9, 4, 10, 4, 4, ""),
        Wall(11.5, 4, 13, 4, 4, ""),
        Wall(14, 4, 15, 4, 4, ""),
        Wall(12, 4, 12, 6, 4, ""),
        Wall(0, 6, 1.5, 6, 6, ""),
        Wall(3.5, 6, 13, 6, 6, ""),
        Wall(14, 6, 15, 6, 6, ""),
        Wall(5, 6, 5, 7, 6, ""),
        Wall(5, 8, 5, 12, 6, ""),
        Wall(5, 9, 10, 9, 4, ""),
        Wall(10, 6, 10, 10, 6, ""),
        Wall(10, 11, 10, 12, 6, ""),
    ]
    fp.doors = [
        Door(3, 0, 4.5, 0, "客餐厅门"),
        Door(9, 1.5, 9, 3.5, "厨房门"),
        Door(10, 4, 11.5, 4, "卫生间1门"),
        Door(13, 4, 14, 4, "书房门"),
        Door(1.5, 6, 3.5, 6, "主卧门"),
        Door(5, 7, 5, 8, "主卫门"),
        Door(13, 6, 14, 6, "次卧2门"),
        Door(10, 10, 10, 11, "次卧1门"),
    ]


def _segments_intersect(
    ax1: float,
    ay1: float,
    ax2: float,
    ay2: float,
    bx1: float,
    by1: float,
    bx2: float,
    by2: float,
) -> bool:
    def ccw(ox: float, oy: float, px: float, py: float, qx: float, qy: float) -> float:
        return (px - ox) * (qy - oy) - (py - oy) * (qx - ox)

    def on_segment(
        px: float, py: float, x1: float, y1: float, x2: float, y2: float
    ) -> bool:
        eps = 1e-9
        return (
            min(x1, x2) - eps <= px <= max(x1, x2) + eps
            and min(y1, y2) - eps <= py <= max(y1, y2) + eps
        )

    c1 = ccw(ax1, ay1, ax2, ay2, bx1, by1)
    c2 = ccw(ax1, ay1, ax2, ay2, bx2, by2)
    c3 = ccw(bx1, by1, bx2, by2, ax1, ay1)
    c4 = ccw(bx1, by1, bx2, by2, ax2, ay2)

    if (c1 * c2 < 0) and (c3 * c4 < 0):
        return True

    if c1 == 0.0 and on_segment(bx1, by1, ax1, ay1, ax2, ay2):
        return True
    if c2 == 0.0 and on_segment(bx2, by2, ax1, ay1, ax2, ay2):
        return True
    if c3 == 0.0 and on_segment(ax1, ay1, bx1, by1, bx2, by2):
        return True
    if c4 == 0.0 and on_segment(ax2, ay2, bx1, by1, bx2, by2):
        return True

    return False


def count_wall_crossings(
    fp: FloorPlan, x1: float, y1: float, x2: float, y2: float
) -> list[Wall]:
    crossed = []
    for w in fp.walls:
        if _segments_intersect(x1, y1, x2, y2, w.x1, w.y1, w.x2, w.y2):
            crossed.append(w)
    return crossed


def signal_strength_at(
    fp: FloorPlan, ap: AP, x: float, y: float, freq_ghz: float = 5.0
) -> float:
    dist = math.hypot(x - ap.x, y - ap.y)
    fspl_raw = (
        20 * math.log10(max(dist, 1e-6)) + 20 * math.log10(freq_ghz * 1e9) - 147.55
    )
    fspl = max(fspl_raw, 0.0)
    walls = count_wall_crossings(fp, ap.x, ap.y, x, y)
    wall_loss = sum(w.attenuation_db for w in walls)
    return ap.tx_power_dbm - fspl - wall_loss - 10.0


def compute_heatmap(fp: FloorPlan, freq_ghz: float = 5.0, grid_size: int = GRID_SIZE):
    nx = ny = grid_size
    xs = np.linspace(0, fp.width, nx)
    ys = np.linspace(0, fp.height, ny)
    X, Y = np.meshgrid(xs, ys)
    rssi = np.full_like(X, -120.0)

    for ap in fp.aps:
        for j in range(ny):
            for i in range(nx):
                s = signal_strength_at(fp, ap, xs[i], ys[j], freq_ghz)
                rssi[j, i] = max(rssi[j, i], s)

    return X, Y, rssi


def average_rssi(fp: FloorPlan, freq_ghz: float = 5.0) -> float:
    _, _, rssi = compute_heatmap(fp, freq_ghz=freq_ghz)
    return float(np.mean(rssi))


def rssi_at_sta(fp: FloorPlan, sta: STA, freq_ghz: float = 5.0) -> float:
    best = -120.0
    for ap in fp.aps:
        s = signal_strength_at(fp, ap, sta.x, sta.y, freq_ghz)
        best = max(best, s)
    return best


def compute_stall_heatmap(
    fp: FloorPlan,
    base_params,
    engine,
    freq_ghz: float = 5.0,
    progress_cb=None,
    grid_size: int = GRID_SIZE,
):
    nx = ny = grid_size
    xs = np.linspace(0, fp.width, nx)
    ys = np.linspace(0, fp.height, ny)
    X, Y = np.meshgrid(xs, ys)
    stall = np.zeros((ny, nx))

    quick_p = _copy.deepcopy(base_params)
    quick_p.sim_duration = 10

    _cache: dict[float, float] = {}
    total = nx * ny
    done = 0

    for j in range(ny):
        for i in range(nx):
            best = -120.0
            for ap in fp.aps:
                s = signal_strength_at(fp, ap, float(xs[i]), float(ys[j]), freq_ghz)
                best = max(best, s)
            rssi_key = round(float(np.clip(best, -90.0, -20.0)) * 2) / 2.0

            if rssi_key not in _cache:
                p = _copy.copy(quick_p)
                p.wifi_rssi = rssi_key
                summary, _, _ = engine.simulate(p, collect_timeseries=False)
                _cache[rssi_key] = summary.rtmp_stall_rate / 100.0

            stall[j, i] = _cache[rssi_key]
            done += 1
            if progress_cb is not None:
                progress_cb(done, total)

    return X, Y, stall


def recommend_ap_positions(
    fp: FloorPlan,
    rssi_grid: np.ndarray,
    stall_grid: np.ndarray,
    n_recommend: int = 2,
    rssi_threshold: float = -70.0,
    stall_threshold: float = 0.05,
    min_dist: float | None = None,
) -> list[dict]:
    if min_dist is None:
        min_dist = min(fp.width, fp.height) * 0.35

    ny, nx = stall_grid.shape
    xs = np.linspace(0, fp.width, nx)
    ys = np.linspace(0, fp.height, ny)

    if rssi_grid.shape != stall_grid.shape:
        rny, rnx = rssi_grid.shape
        rssi_ref = np.zeros((ny, nx))
        for j in range(ny):
            for i in range(nx):
                ri = int(round(float(xs[i]) / fp.width * (rnx - 1)))
                rj = int(round(float(ys[j]) / fp.height * (rny - 1)))
                rssi_ref[j, i] = rssi_grid[
                    max(0, min(rny - 1, rj)), max(0, min(rnx - 1, ri))
                ]
    else:
        rssi_ref = rssi_grid

    rssi_score = np.clip((-rssi_ref + rssi_threshold) / 20.0, 0.0, 1.0)
    stall_score = np.clip(stall_grid / max(stall_threshold * 4, 0.20), 0.0, 1.0)

    high_stall_mask = stall_grid > 0.10
    weight_stall = np.where(high_stall_mask, 0.7, 0.5)
    weight_rssi = 1.0 - weight_stall
    badness = rssi_score * weight_rssi + stall_score * weight_stall

    margin = max(min_dist * 0.5, 1.5)
    for j in range(ny):
        for i in range(nx):
            x_ = float(xs[i])
            y_ = float(ys[j])
            if (
                x_ < margin
                or x_ > fp.width - margin
                or y_ < margin
                or y_ > fp.height - margin
            ):
                badness[j, i] = 0.0

    existing = [(ap.x, ap.y) for ap in fp.aps]
    recs: list[dict] = []

    for k in range(n_recommend):
        b = badness.copy()
        for bx, by_ in existing + [(r["x"], r["y"]) for r in recs]:
            for j in range(ny):
                for i in range(nx):
                    if (
                        math.sqrt((float(xs[i]) - bx) ** 2 + (float(ys[j]) - by_) ** 2)
                        < min_dist
                    ):
                        b[j, i] = 0.0

        if float(b.max()) < 0.02:
            break

        j_best, i_best = np.unravel_index(int(b.argmax()), b.shape)

        window = 3
        j0 = max(0, j_best - window // 2)
        j1 = min(ny, j_best + window // 2 + 1)
        i0 = max(0, i_best - window // 2)
        i1 = min(nx, i_best + window // 2 + 1)
        sub_b = b[j0:j1, i0:i1]
        total_weight = float(sub_b.sum())
        if total_weight > 0:
            ii = np.arange(i0, i1)
            jj = np.arange(j0, j1)
            I, J = np.meshgrid(ii, jj)
            i_best = int(round(float((I * sub_b).sum()) / total_weight))
            j_best = int(round(float((J * sub_b).sum()) / total_weight))
            i_best = max(0, min(nx - 1, i_best))
            j_best = max(0, min(ny - 1, j_best))

        recs.append(
            {
                "x": float(xs[i_best]),
                "y": float(ys[j_best]),
                "rssi": float(rssi_ref[j_best, i_best]),
                "stall_rate": float(stall_grid[j_best, i_best]),
                "score": float(badness[j_best, i_best]),
                "label": f"推荐AP{k + 1}",
            }
        )

        for j in range(ny):
            for i in range(nx):
                if (
                    math.sqrt(
                        (float(xs[i]) - recs[-1]["x"]) ** 2
                        + (float(ys[j]) - recs[-1]["y"]) ** 2
                    )
                    < min_dist
                ):
                    badness[j, i] = 0.0

    return recs


# ═══════════════════════════════════════════════════════════════════════
#  Visualization helpers
# ═══════════════════════════════════════════════════════════════════════


def _layout_aps(fp, ap_count: int):
    if ap_count <= 0:
        fp.aps = []
        return

    if ap_count == len(fp.aps):
        return

    base_positions = {
        1: [(0.5, 0.5)],
        2: [(0.25, 0.5), (0.75, 0.5)],
        3: [(0.25, 0.5), (0.75, 0.5), (0.5, 0.25)],
        4: [(0.25, 0.25), (0.75, 0.25), (0.25, 0.75), (0.75, 0.75)],
    }

    if ap_count in base_positions:
        coords = base_positions[ap_count]
    else:
        cols = math.ceil(math.sqrt(ap_count))
        rows = math.ceil(ap_count / cols)
        coords = []
        for i in range(ap_count):
            c = i % cols
            r = i // cols
            x = (c + 0.5) / cols
            y = (r + 0.5) / rows
            coords.append((x, y))

    fp.aps = [
        AP(fp.width * x, fp.height * y, tx_power_dbm=10.0, label=f"AP{idx + 1}")
        for idx, (x, y) in enumerate(coords)
    ]


def _rssi_to_rgb(rssi: float) -> Tuple[float, float, float]:
    t = max(0.0, min(1.0, (rssi + 90.0) / 60.0))
    if t > 0.5:
        r = 1.0 * (1.0 - (t - 0.5) * 2)
        g = 1.0
        b = 0.0
    else:
        r = 1.0
        g = t * 2.0
        b = 0.0
    return r, g, b


def _rssi_cmap():
    from matplotlib.colors import LinearSegmentedColormap

    colors = [
        (1.0, 0.0, 0.0),
        (1.0, 1.0, 0.0),
        (0.0, 1.0, 0.0),
    ]
    return LinearSegmentedColormap.from_list("rssi", colors)


def _draw_doors(ax, fp):
    # 门仅表现为墙体空缺，此处不绘制任何额外图形
    pass


def _draw_floorplan(ax, fp, show_doors: bool = False):
    for room in fp.rooms:
        rect = plt.Rectangle(
            (room.x, room.y),
            room.w,
            room.h,
            linewidth=1,
            edgecolor="gray",
            facecolor="none",
            alpha=0.5,
        )
        ax.add_patch(rect)
        ax.text(
            room.x + room.w / 2,
            room.y + room.h / 2,
            room.name,
            ha="center",
            va="center",
            fontsize=9,
            color="gray",
            alpha=0.7,
        )

    for wall in fp.walls:
        lw = 3.5 if wall.attenuation_db < 8 else 7.0
        color = "#a0a0a0" if wall.attenuation_db < 8 else "#e8e8e8"
        ax.plot(
            [wall.x1, wall.x2],
            [wall.y1, wall.y2],
            color=color,
            linewidth=lw,
            solid_capstyle="round",
        )

    for ap in fp.aps:
        ax.plot(
            ap.x,
            ap.y,
            "o",
            markersize=14,
            color="#4fc3f7",
            markeredgecolor="#0288d1",
            markeredgewidth=2,
        )
        ax.text(
            ap.x,
            ap.y,
            ap.label.replace("AP", ""),
            ha="center",
            va="center",
            fontsize=8,
            color="white",
            fontweight="bold",
        )

    if show_doors:
        _draw_doors(ax, fp)

    ax.set_xlim(-0.5, fp.width + 0.5)
    ax.set_ylim(-0.5, fp.height + 0.5)
    ax.set_aspect("equal")


# ═══════════════════════════════════════════════════════════════════════
#  Capabilities
# ═══════════════════════════════════════════════════════════════════════


def generate_rssi_heatmap(
    preset_name: str,
    ap_count: int,
    output_path: str,
    grid_size: int = GRID_SIZE,
    show_doors: bool = False,
):
    fp = PRESETS[preset_name]()
    if preset_name == "大平层" and show_doors:
        _apply_doors_to_large_flat(fp)
    _layout_aps(fp, ap_count)

    X, Y, rssi = compute_heatmap(fp, grid_size=grid_size)

    with matplotlib.rc_context(_DARK_RC):
        fig, ax = plt.subplots(figsize=(10, 8))
        im = ax.pcolormesh(
            X, Y, rssi, cmap=_rssi_cmap(), shading="auto", vmin=-90, vmax=-30
        )
        cbar = fig.colorbar(im, ax=ax)
        cbar.set_label("RSSI (dBm)")

        _draw_floorplan(ax, fp, show_doors=show_doors)

        avg_rssi = float(np.mean(_inner(rssi)))
        worst_rssi = float(np.min(_inner(rssi)))
        title = (
            f"{fp.name} 信号热力图 | AP={ap_count} | 分辨率 {grid_size}x{grid_size}\n"
            f"平均 RSSI: {avg_rssi:.1f} dBm | 最差 RSSI: {worst_rssi:.1f} dBm"
        )
        ax.set_title(title)
        ax.set_xlabel("宽度 (m)")
        ax.set_ylabel("高度 (m)")

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)


def generate_stall_grid(
    preset_name: str,
    ap_count: int,
    output_path: str,
    grid_size: int = GRID_SIZE,
    show_doors: bool = False,
):
    fp = PRESETS[preset_name]()
    if preset_name == "大平层" and show_doors:
        _apply_doors_to_large_flat(fp)
    _layout_aps(fp, ap_count)

    engine = SimulationEngine()
    base_params = SimParams()

    X, Y, stall = compute_stall_heatmap(fp, base_params, engine, grid_size=grid_size)
    stall_pct = stall * 100.0
    inner_stall = _inner(stall_pct)
    max_rate = float(inner_stall.max()) if inner_stall.max() > 1e-6 else 1.0

    with matplotlib.rc_context(_DARK_RC):
        fig, ax = plt.subplots(figsize=(10, 8))

        x_flat = X.ravel()
        y_flat = Y.ravel()
        s_flat = stall_pct.ravel()

        sizes = np.full(s_flat.shape, 30.0)

        sc = ax.scatter(
            x_flat,
            y_flat,
            c=s_flat,
            cmap="RdYlGn_r",
            s=sizes,
            vmin=0,
            vmax=max(max_rate, 10.0),
            edgecolors="none",
        )
        cbar = fig.colorbar(sc, ax=ax)
        cbar.set_label("卡顿率 (%)")

        _draw_floorplan(ax, fp, show_doors=show_doors)

        title = (
            f"{fp.name} RTMP 卡顿率栅格图 | AP={ap_count} | 分辨率 {grid_size}x{grid_size}\n"
            f"平均卡顿率: {inner_stall.mean():.2f}% | 峰值: {inner_stall.max():.2f}%"
        )
        ax.set_title(title)
        ax.set_xlabel("宽度 (m)")
        ax.set_ylabel("高度 (m)")

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)


def _inner(matrix: np.ndarray) -> np.ndarray:
    return matrix[1:-1, 1:-1]


def _save_matrix_npy(path: Path, matrix: np.ndarray):
    np.save(path, matrix.astype(np.float32))


def _save_matrix_json(
    path: Path,
    matrix: np.ndarray,
    preset_name: str,
    ap_count: int,
    metric: str,
):
    inner = _inner(matrix)
    if metric == "rssi":
        summary = {
            "mean_rssi": float(np.mean(inner)),
            "worst_rssi": float(np.min(inner)),
        }
    else:
        summary = {
            "mean_stall_rate": float(np.mean(inner)),
            "max_stall_rate": float(np.max(inner)),
        }
    payload = {
        "preset_name": preset_name,
        "ap_count": ap_count,
        "shape": list(matrix.shape),
        **summary,
        "data": matrix.tolist(),
    }
    import json

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)


def generate_ap_optimization_comparison(
    preset_name: str,
    current_ap_count: int,
    target_ap_count: int,
    output_dir: str,
    grid_size: int = GRID_SIZE,
    show_doors: bool = False,
):
    if target_ap_count <= current_ap_count:
        raise ValueError("target_ap_count 必须大于 current_ap_count")

    fp_before = PRESETS[preset_name]()
    if preset_name == "大平层" and show_doors:
        _apply_doors_to_large_flat(fp_before)
    _layout_aps(fp_before, current_ap_count)

    fp_after = _copy.deepcopy(fp_before)

    engine = SimulationEngine()
    base_params = SimParams()

    Xs, Ys, rssi_before = compute_heatmap(fp_before, grid_size=grid_size)
    Xg, Yg, stall_before = compute_stall_heatmap(
        fp_before, base_params, engine, grid_size=grid_size
    )

    n_recommend = target_ap_count - current_ap_count
    recs = recommend_ap_positions(
        fp_after, rssi_before, stall_before, n_recommend=n_recommend
    )

    for r in recs:
        fp_after.aps.append(AP(r["x"], r["y"], tx_power_dbm=10.0, label=r["label"]))

    _, _, rssi_after = compute_heatmap(fp_after, grid_size=grid_size)
    _, _, stall_after = compute_stall_heatmap(
        fp_after, base_params, engine, grid_size=grid_size
    )

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    paths = {}

    with matplotlib.rc_context(_DARK_RC):
        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        for ax, fp, rssi, label in [
            (axes[0], fp_before, rssi_before, f"补点前 (AP={current_ap_count})"),
            (axes[1], fp_after, rssi_after, f"补点后 (AP={current_ap_count + len(recs)})"),
        ]:
            im = ax.pcolormesh(
                Xs, Ys, rssi, cmap=_rssi_cmap(), shading="auto", vmin=-90, vmax=-30
            )
            fig.colorbar(im, ax=ax, label="RSSI (dBm)")
            _draw_floorplan(ax, fp, show_doors=show_doors)
            inner_rssi = _inner(rssi)
            avg = float(np.mean(inner_rssi))
            worst = float(np.min(inner_rssi))
            ax.set_title(f"{label}\n平均 RSSI: {avg:.1f} dBm | 最差: {worst:.1f} dBm")
            ax.set_xlabel("宽度 (m)")
            ax.set_ylabel("高度 (m)")

        plt.tight_layout()
        rssi_cmp_path = output_dir / f"{preset_name}_rssi_comparison.png"
        plt.savefig(rssi_cmp_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
    paths["rssi_comparison"] = str(rssi_cmp_path)

    with matplotlib.rc_context(_DARK_RC):
        fig, axes = plt.subplots(1, 2, figsize=(16, 7))
        for ax, fp, stall, label in [
            (axes[0], fp_before, stall_before, f"补点前 (AP={current_ap_count})"),
            (axes[1], fp_after, stall_after, f"补点后 (AP={current_ap_count + len(recs)})"),
        ]:
            stall_pct = stall * 100.0
            inner_stall = _inner(stall_pct)
            max_rate = float(inner_stall.max()) if inner_stall.max() > 1e-6 else 1.0
            x_flat = Xg.ravel()
            y_flat = Yg.ravel()
            s_flat = stall_pct.ravel()
            sizes = np.full(s_flat.shape, 30.0)
            sc = ax.scatter(
                x_flat,
                y_flat,
                c=s_flat,
                cmap="RdYlGn_r",
                s=sizes,
                vmin=0,
                vmax=max(max_rate, 10.0),
                edgecolors="none",
            )
            fig.colorbar(sc, ax=ax, label="卡顿率 (%)")
            _draw_floorplan(ax, fp, show_doors=show_doors)
            ax.set_title(
                f"{label}\n平均: {inner_stall.mean():.2f}% | 峰值: {inner_stall.max():.2f}%"
            )
            ax.set_xlabel("宽度 (m)")
            ax.set_ylabel("高度 (m)")

        plt.tight_layout()
        stall_cmp_path = output_dir / f"{preset_name}_stall_comparison.png"
        plt.savefig(stall_cmp_path, dpi=150, bbox_inches="tight", facecolor=fig.get_facecolor())
        plt.close(fig)
    paths["stall_comparison"] = str(stall_cmp_path)

    rssi_before_npy = output_dir / f"{preset_name}_rssi_before.npy"
    rssi_after_npy = output_dir / f"{preset_name}_rssi_after.npy"
    stall_before_npy = output_dir / f"{preset_name}_stall_before.npy"
    stall_after_npy = output_dir / f"{preset_name}_stall_after.npy"

    _save_matrix_npy(rssi_before_npy, rssi_before)
    _save_matrix_npy(rssi_after_npy, rssi_after)
    _save_matrix_npy(stall_before_npy, stall_before)
    _save_matrix_npy(stall_after_npy, stall_after)

    paths["rssi_before_npy"] = str(rssi_before_npy)
    paths["rssi_after_npy"] = str(rssi_after_npy)
    paths["stall_before_npy"] = str(stall_before_npy)
    paths["stall_after_npy"] = str(stall_after_npy)

    rssi_before_json = output_dir / f"{preset_name}_rssi_before.json"
    rssi_after_json = output_dir / f"{preset_name}_rssi_after.json"
    stall_before_json = output_dir / f"{preset_name}_stall_before.json"
    stall_after_json = output_dir / f"{preset_name}_stall_after.json"

    _save_matrix_json(
        rssi_before_json, rssi_before, preset_name, current_ap_count, "rssi"
    )
    _save_matrix_json(
        rssi_after_json, rssi_after, preset_name, current_ap_count + len(recs), "rssi"
    )
    _save_matrix_json(
        stall_before_json, stall_before, preset_name, current_ap_count, "stall"
    )
    _save_matrix_json(
        stall_after_json,
        stall_after,
        preset_name,
        current_ap_count + len(recs),
        "stall",
    )

    paths["rssi_before_json"] = str(rssi_before_json)
    paths["rssi_after_json"] = str(rssi_after_json)
    paths["stall_before_json"] = str(stall_before_json)
    paths["stall_after_json"] = str(stall_after_json)

    return paths


def run_all(
    preset_name: str,
    ap_count: int,
    output_dir: str,
    grid_size: int = GRID_SIZE,
):
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    generate_rssi_heatmap(
        preset_name,
        ap_count,
        str(out / f"{preset_name}_rssi_ap{ap_count}.png"),
        grid_size=grid_size,
    )
    generate_stall_grid(
        preset_name,
        ap_count,
        str(out / f"{preset_name}_stall_ap{ap_count}.png"),
        grid_size=grid_size,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Home WiFi Simulator Skill")
    parser.add_argument("--preset", default="大平层", help="户型名")
    parser.add_argument("--ap", type=int, default=1, help="AP 数量")
    parser.add_argument("--out-dir", default="./output", help="输出目录")
    parser.add_argument("--compare", action="store_true", help="同时生成 AP 补点对比")
    parser.add_argument("--target-ap", type=int, default=3, help="补点目标 AP 数")
    parser.add_argument(
        "--grid-size", type=int, default=GRID_SIZE, help="栅格分辨率（NxN）"
    )
    args = parser.parse_args()

    if args.compare:
        result = generate_ap_optimization_comparison(
            args.preset, args.ap, args.target_ap, args.out_dir, grid_size=args.grid_size
        )
        print("对比图:")
        print("  RSSI:", result["rssi_comparison"])
        print("  Stall:", result["stall_comparison"])
        print("矩阵数据 (.npy):")
        print("  RSSI before :", result["rssi_before_npy"])
        print("  RSSI after  :", result["rssi_after_npy"])
        print("  Stall before:", result["stall_before_npy"])
        print("  Stall after :", result["stall_after_npy"])
        print("矩阵数据 (.json):")
        print("  RSSI before :", result["rssi_before_json"])
        print("  RSSI after  :", result["rssi_after_json"])
        print("  Stall before:", result["stall_before_json"])
        print("  Stall after :", result["stall_after_json"])
    else:
        run_all(args.preset, args.ap, args.out_dir, grid_size=args.grid_size)
        print(f"输出完成，请查看 {args.out_dir}")
