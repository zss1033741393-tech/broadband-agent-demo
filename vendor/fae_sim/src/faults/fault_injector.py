"""故障注入核心函数 — 在指定时间步动态修改网络参数。"""

from __future__ import annotations

import numpy as np

from ..params.schema import SimParams
from .fault_config import FaultConfig


def inject_faults(params: SimParams, step: int, config: FaultConfig,
                  total_steps: int,
                  rng: np.random.Generator | None = None) -> SimParams:
    """根据故障配置，在指定时间步修改参数。

    支持 fixed（连续区间）和 random（多片段）两种注入模式。
    部分故障参数在每个时间步随机取值（贴合现网波动特性）。
    """
    if not config.is_active:
        return params

    if not config.is_fault_active_at(step, total_steps):
        return params

    if rng is None:
        rng = np.random.default_rng()

    p = params.copy()
    for fid in config.enabled_faults:
        p = _apply_fault(p, fid, rng)
    return p


def _apply_fault(p: SimParams, fault_id: int,
                 rng: np.random.Generator) -> SimParams:
    """对单个故障ID应用参数修改。"""
    if fault_id == 1:
        return _fault_wifi_roaming(p, rng)
    elif fault_id == 2:
        return _fault_wifi_interference(p, rng)
    elif fault_id == 3:
        return _fault_wifi_weak_coverage(p)
    elif fault_id == 4:
        return _fault_insufficient_uplink(p)
    elif fault_id == 5:
        return _fault_pon_congestion(p)
    elif fault_id == 6:
        return _fault_multi_sta(p)
    elif fault_id == 7:
        return _fault_pon_fiber_break(p)
    return p


def _fault_wifi_roaming(p: SimParams,
                        rng: np.random.Generator) -> SimParams:
    """故障1: 频繁WiFi漫游 — 弱信号+高重传+断连。"""
    p.wifi_rssi = float(rng.uniform(-85, -75))
    p.wifi_up_retry_rate = float(rng.uniform(30, 40))
    p.wifi_up_latency = 80.0
    p.wifi_up_tcp_retrans_rate = 15.0
    return p


def _fault_wifi_interference(p: SimParams,
                             rng: np.random.Generator) -> SimParams:
    """故障2: WiFi干扰严重 — 高干扰+底噪抬升。"""
    p.wifi_interference_ratio = float(rng.uniform(40, 60))
    p.wifi_noise_floor = float(rng.uniform(-70, -60))
    p.wifi_up_tcp_retrans_rate = 10.0
    p.wifi_up_jitter = float(rng.uniform(35, 45))
    return p


def _fault_wifi_weak_coverage(p: SimParams) -> SimParams:
    """故障3: WiFi覆盖弱 — 深度弱覆盖。"""
    p.wifi_rssi = -88.0
    p.wifi_multipath_fading = 0.9
    p.wifi_up_retry_rate = 50.0
    return p


def _fault_insufficient_uplink(p: SimParams) -> SimParams:
    """故障4: 上行带宽不足 — 带宽严重受限+TCP阻塞。"""
    p.pon_uplink_bw = 3.0
    p.pon_up_load_ratio = max(p.pon_up_load_ratio, 80.0)
    p.pon_up_tcp_retrans_rate = max(p.pon_up_tcp_retrans_rate, 8.0)
    p.pon_up_latency = max(p.pon_up_latency, 80.0)
    return p


def _fault_pon_congestion(p: SimParams) -> SimParams:
    """故障5: PON口拥塞。"""
    p.pon_up_load_ratio = 95.0
    p.pon_burst_collision = 0.08
    p.pon_up_latency = 120.0
    p.pon_up_jitter = 80.0
    return p


def _fault_multi_sta(p: SimParams) -> SimParams:
    """故障6: 多STA竞争。"""
    p.sta_count = 60
    p.wifi_mu_mimo_enabled = False
    return p


def _fault_pon_fiber_break(p: SimParams) -> SimParams:
    """故障7: PON光纤中断 — 光路衰减极大。"""
    p.pon_optical_attenuation = 25.0
    return p
