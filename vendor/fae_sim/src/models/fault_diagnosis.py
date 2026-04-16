"""故障诊断模块 — 基于诊断树的定界定位 + 措施推荐。

诊断基于仿真实际产生的 KPI 数据（summary 均值 + timeseries 瞬时参数均值），
而非用户输入的基础参数，确保故障注入后的异常能被正确检测。
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..params.schema import SimParams
from .state_recorder import SimulationSummary
from ..faults.fault_config import FAULT_CATALOG


@dataclass
class FaultCandidate:
    fault_id: int
    fault_name: str
    severity: str
    confidence: str
    confidence_score: int
    evidence: list[str]
    measures: list[str]


@dataclass
class DiagnosisResult:
    has_issue: bool
    domain: str
    fault_candidates: list[FaultCandidate] = field(default_factory=list)
    summary_text: str = ""


def _avg(ts: dict, key: str) -> float:
    """取 timeseries 中某字段的均值。"""
    arr = ts.get(key, [])
    if not arr:
        return 0.0
    return float(np.mean(arr))


def _check_wifi_roaming(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    avg_rssi = _avg(ts, "inst_wifi_rssi")
    if avg_rssi < -70:
        ev.append(f"WiFi信号弱 (平均RSSI={avg_rssi:.0f}dBm < -70)")
    if s.avg_up_latency >= 50:
        ev.append(f"上行时延高 ({s.avg_up_latency:.0f}ms >= 50)")
    if s.reconnect_count > 0:
        ev.append(f"发生断连重推 ({s.reconnect_count}次)")
    return ev


def _check_pon_fiber_break(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    # 光路衰减用基础参数（静态配置，不随时间步变化）
    if p.pon_optical_attenuation >= 20:
        ev.append(f"光路衰减极大 ({p.pon_optical_attenuation:.0f}dB >= 20)")
    if s.reconnect_count > 0:
        ev.append(f"发生断连重推 ({s.reconnect_count}次)")
    if s.avg_effective_throughput < 1.0:
        ev.append(f"有效吞吐量极低 ({s.avg_effective_throughput:.1f}Mbps)")
    return ev


def _check_insufficient_uplink(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    avg_load = _avg(ts, "inst_pon_up_load_ratio")
    avg_tcp = _avg(ts, "inst_pon_up_tcp_retrans_rate")
    if s.avg_effective_throughput < p.rtmp_bitrate:
        ev.append(f"有效吞吐量({s.avg_effective_throughput:.1f}Mbps) < 码率({p.rtmp_bitrate}Mbps)")
    if s.bandwidth_meet_rate < 80:
        ev.append(f"带宽达标率低 ({s.bandwidth_meet_rate:.0f}%)")
    if avg_tcp >= 5:
        ev.append(f"PON TCP重传率高 (平均{avg_tcp:.1f}%)")
    if avg_load >= 70:
        ev.append(f"PON上行负载高 (平均{avg_load:.0f}%)")
    if s.buffer_empty_ratio >= 10:
        ev.append(f"缓冲区耗尽占比高 ({s.buffer_empty_ratio:.0f}%)")
    return ev


def _check_pon_congestion(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    avg_load = _avg(ts, "inst_pon_up_load_ratio")
    avg_latency = _avg(ts, "inst_pon_up_latency")
    avg_jitter = _avg(ts, "inst_pon_up_jitter")
    if avg_load >= 70:
        ev.append(f"PON上行负载高 (平均{avg_load:.0f}%)")
    if avg_latency >= 50:
        ev.append(f"PON上行时延高 (平均{avg_latency:.0f}ms)")
    if avg_jitter >= 30:
        ev.append(f"PON上行抖动高 (平均{avg_jitter:.0f}ms)")
    if p.pon_burst_collision >= 0.05:
        ev.append(f"突发冲突概率高 ({p.pon_burst_collision:.3f})")
    return ev


def _check_wifi_weak_coverage(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    avg_rssi = _avg(ts, "inst_wifi_rssi")
    avg_retry = _avg(ts, "inst_wifi_up_retry_rate")
    if avg_rssi < -70:
        ev.append(f"WiFi信号弱 (平均RSSI={avg_rssi:.0f}dBm)")
    if avg_retry >= 15:
        ev.append(f"WiFi上行重传率高 (平均{avg_retry:.0f}%)")
    if s.tcp_block_ratio >= 5:
        ev.append(f"TCP阻塞占比高 ({s.tcp_block_ratio:.0f}%)")
    return ev


def _check_wifi_interference(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    avg_interf = _avg(ts, "inst_wifi_interference_ratio")
    avg_jitter = _avg(ts, "inst_wifi_up_jitter")
    avg_nf = _avg(ts, "inst_wifi_noise_floor")
    if avg_interf >= 30:
        ev.append(f"WiFi干扰占空比高 (平均{avg_interf:.0f}%)")
    if avg_jitter >= 20:
        ev.append(f"WiFi上行抖动高 (平均{avg_jitter:.0f}ms)")
    if avg_nf > -70:
        ev.append(f"底噪偏高 (平均{avg_nf:.0f}dBm)")
    return ev


def _check_multi_sta(s: SimulationSummary, ts: dict, p: SimParams) -> list[str]:
    ev = []
    avg_sta = _avg(ts, "inst_sta_count")
    if avg_sta >= 15:
        ev.append(f"STA并发数高 (平均{avg_sta:.0f})")
    # MU-MIMO 状态来自时序中的瞬时值或基础参数
    if not p.wifi_mu_mimo_enabled:
        ev.append("MU-MIMO未开启")
    if s.avg_up_jitter >= 15:
        ev.append(f"上行抖动偏高 ({s.avg_up_jitter:.0f}ms)")
    return ev


# (检查函数, 故障ID, 最低证据数, 基础置信度)
_RULES = [
    (_check_wifi_roaming,        1, 2, "高"),
    (_check_pon_fiber_break,     7, 1, "高"),
    (_check_insufficient_uplink, 4, 2, "高"),
    (_check_pon_congestion,      5, 2, "中"),
    (_check_wifi_weak_coverage,  3, 2, "中"),
    (_check_wifi_interference,   2, 2, "高"),
    (_check_multi_sta,           6, 1, "中"),
]

_CONF_SCORE = {"高": 3, "中": 2, "低": 1}


def diagnose(summary: SimulationSummary, params: SimParams,
             timeseries: dict | None = None) -> DiagnosisResult:
    """基于诊断树进行故障定界定位。

    Args:
        summary: 仿真汇总（含均值 KPI）
        params: 基础仿真参数（静态配置值）
        timeseries: 仿真时序数据（含 inst_* 瞬时参数，用于计算实际均值）
    """
    if timeseries is None:
        timeseries = {}

    if summary.rtmp_stall_rate < 1.0:
        return DiagnosisResult(
            has_issue=False, domain="正常",
            summary_text="网络运行正常，未检测到显著卡顿问题。")

    # 定界
    domain = summary.bottleneck
    if "WiFi" in domain and "PON" in domain:
        domain = "WiFi+PON"
    elif "WiFi" in domain:
        domain = "WiFi"
    elif "PON" in domain:
        domain = "PON"
    else:
        domain = "WiFi+PON"

    # 定位
    candidates: list[FaultCandidate] = []
    for check_fn, fault_id, min_ev, conf in _RULES:
        evidence = check_fn(summary, timeseries, params)
        if len(evidence) >= min_ev:
            info = FAULT_CATALOG[fault_id]
            candidates.append(FaultCandidate(
                fault_id=fault_id,
                fault_name=info["name"],
                severity=info["severity"],
                confidence=conf,
                confidence_score=_CONF_SCORE[conf],
                evidence=evidence,
                measures=info["bound_measures"],
            ))

    candidates.sort(key=lambda c: (c.confidence_score, len(c.evidence)), reverse=True)
    candidates = candidates[:3]

    if not candidates:
        text = (f"检测到卡顿率 {summary.rtmp_stall_rate:.1f}%，"
                f"瓶颈位于{summary.bottleneck}，但未匹配到具体故障模式。"
                f"建议检查网络参数配置。")
    else:
        top = candidates[0]
        text = (f"诊断定界：{domain}域问题。"
                f"主要故障：{top.fault_name}（{top.severity}，置信度{top.confidence}）。"
                f"证据：{'；'.join(top.evidence)}。"
                f"推荐措施：{'、'.join(top.measures)}。")
        if len(candidates) > 1:
            others = "、".join(c.fault_name for c in candidates[1:])
            text += f" 其他可能故障：{others}。"

    return DiagnosisResult(
        has_issue=True, domain=domain,
        fault_candidates=candidates,
        summary_text=text)
