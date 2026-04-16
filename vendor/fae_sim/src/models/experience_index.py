"""家宽体验指数计算模块。

基于 8 个维度的滚动时间窗 KPI 异常占比，加权求和计算 1-100 分体验指数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..params.schema import SimParams


@dataclass
class ExperienceWindow:
    """单个滚动时间窗的体验指数结果。"""
    center_step: int
    total_score: float
    dimension_scores: dict[str, float] = field(default_factory=dict)


# ── 维度权重 ──
DIMENSION_WEIGHTS = {
    "业务质量": 0.30,
    "速率": 0.20,
    "稳定性": 0.10,
    "OLT": 0.08,
    "PON": 0.10,
    "网关": 0.02,
    "终端": 0.02,
    "WIFI": 0.18,
}


def _abnormal_ratio(arr, condition_fn, start: int, end: int) -> float:
    """计算 arr[start:end] 中满足条件的比例。"""
    window = arr[start:end]
    if len(window) == 0:
        return 0.0
    count = sum(1 for v in window if condition_fn(v))
    return count / len(window)


def _dim_score_business_quality(ts: dict, start: int, end: int) -> float:
    """业务质量维度：卡顿率。"""
    ratio = _abnormal_ratio(ts["stall_active"], lambda v: v == 1, start, end)
    return 100.0 * (1.0 - ratio)


def _dim_score_speed(ts: dict, params: SimParams, start: int, end: int) -> float:
    """速率维度：带宽达标 + PON 上行/下行负载率。"""
    r1 = _abnormal_ratio(ts["effective_up_throughput"],
                         lambda v: v < params.rtmp_bitrate, start, end)
    r2 = _abnormal_ratio(ts["inst_pon_up_load_ratio"],
                         lambda v: v >= 70, start, end)
    r3 = _abnormal_ratio(ts["inst_pon_down_load_ratio"],
                         lambda v: v >= 70, start, end)
    avg_ratio = (r1 + r2 + r3) / 3.0
    return 100.0 * (1.0 - avg_ratio)


def _dim_score_stability(ts: dict, start: int, end: int) -> float:
    """稳定性维度：业务中断（reconnect）占比。"""
    if "reconnect_flag" not in ts:
        return 100.0
    ratio = _abnormal_ratio(ts["reconnect_flag"], lambda v: v == 1, start, end)
    return 100.0 * (1.0 - ratio)


def _dim_score_olt(params: SimParams) -> float:
    """OLT 维度：静态参数判定。"""
    checks = [
        params.pon_rx_power < -25,
        params.pon_split_ratio >= 128,
        params.pon_optical_attenuation >= 20,
        params.pon_tx_power < -13 or params.pon_tx_power > -7,
    ]
    abnormal_count = sum(1 for c in checks if c)
    return 100.0 * (1.0 - abnormal_count / len(checks))


def _dim_score_pon(ts: dict, params: SimParams, start: int, end: int) -> float:
    """PON 维度：静态参数 + 动态指标。"""
    static_checks = [
        params.pon_fec_pre_error_rate >= 1e-3,
        params.pon_fec_post_error_rate >= 1e-7,
        params.pon_bip_error_rate >= 1e-5,
        params.pon_dba_cycle >= 8,
        params.pon_burst_collision >= 0.05,
        params.pon_es >= 30,
        params.user_priority_weight < 0.5,
    ]
    static_ratio = sum(1 for c in static_checks if c) / max(len(static_checks), 1)

    dynamic_ratios = [
        _abnormal_ratio(ts["inst_pon_up_tcp_retrans_rate"],
                        lambda v: v >= 5, start, end),
        _abnormal_ratio(ts["inst_pon_up_latency"],
                        lambda v: v >= 80, start, end),
        _abnormal_ratio(ts["inst_pon_up_jitter"],
                        lambda v: v >= 50, start, end),
    ]
    avg_dynamic = sum(dynamic_ratios) / len(dynamic_ratios)

    total_count = len(static_checks) + len(dynamic_ratios)
    weighted = (static_ratio * len(static_checks) + avg_dynamic * len(dynamic_ratios)) / total_count
    return 100.0 * (1.0 - weighted)


def _dim_score_wifi(ts: dict, start: int, end: int) -> float:
    """WIFI 维度：动态瞬时指标。"""
    ratios = [
        _abnormal_ratio(ts["inst_wifi_rssi"], lambda v: v < -70, start, end),
        _abnormal_ratio(ts["inst_wifi_noise_floor"], lambda v: v > -70, start, end),
        _abnormal_ratio(ts["inst_wifi_interference_ratio"], lambda v: v >= 30, start, end),
        _abnormal_ratio(ts["inst_sta_count"], lambda v: v >= 15, start, end),
        _abnormal_ratio(ts["inst_wifi_up_retry_rate"], lambda v: v >= 15, start, end),
        _abnormal_ratio(ts["inst_wifi_up_tcp_retrans_rate"], lambda v: v >= 5, start, end),
        _abnormal_ratio(ts["inst_wifi_up_latency"], lambda v: v >= 50, start, end),
        _abnormal_ratio(ts["inst_wifi_up_jitter"], lambda v: v >= 30, start, end),
    ]
    avg_ratio = sum(ratios) / len(ratios)
    return 100.0 * (1.0 - avg_ratio)


def compute_experience_index(
    timeseries: dict,
    params: SimParams,
    window_size: int = 100,
    slide_step: int = 10,
) -> list[ExperienceWindow]:
    """计算滚动窗口体验指数。

    Args:
        timeseries: 仿真时序数据 dict（含 inst_* 瞬时参数）
        params: 仿真参数（静态值用于 OLT/PON 维度）
        window_size: 窗口大小（时间步数），默认 100 步
        slide_step: 滚动步长，默认 10 步

    Returns:
        每个窗口位置的 ExperienceWindow 列表
    """
    n = len(timeseries.get("stall_active", []))
    if n == 0:
        return []

    olt_score = _dim_score_olt(params)
    results: list[ExperienceWindow] = []

    for win_start in range(0, max(n - window_size + 1, 1), slide_step):
        win_end = min(win_start + window_size, n)
        center = (win_start + win_end) // 2

        scores = {
            "业务质量": _dim_score_business_quality(timeseries, win_start, win_end),
            "速率": _dim_score_speed(timeseries, params, win_start, win_end),
            "稳定性": _dim_score_stability(timeseries, win_start, win_end),
            "OLT": olt_score,
            "PON": _dim_score_pon(timeseries, params, win_start, win_end),
            "网关": 100.0,
            "终端": 100.0,
            "WIFI": _dim_score_wifi(timeseries, win_start, win_end),
        }

        total = sum(scores[d] * DIMENSION_WEIGHTS[d] for d in DIMENSION_WEIGHTS)
        total = max(1.0, min(100.0, total))

        results.append(ExperienceWindow(
            center_step=center,
            total_score=round(total, 1),
            dimension_scores={k: round(v, 1) for k, v in scores.items()},
        ))

    return results
