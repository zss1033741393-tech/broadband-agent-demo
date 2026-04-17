"""时间步状态记录模块 — 归档全时间步State(n)并生成统计指标。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class StallEvent:
    """单次卡顿事件。"""
    start_step: int
    end_step: int
    duration_ms: float
    stall_type: str


@dataclass
class SimulationSummary:
    """仿真结束后的统计汇总。"""
    total_steps: int = 0
    sim_duration_ms: float = 0.0

    # 卡顿率
    rtmp_stall_rate: float = 0.0           # %
    stall_steps: int = 0                   # 卡顿时间步数
    stall_count: int = 0                   # 卡顿事件数
    avg_stall_duration_ms: float = 0.0     # 平均卡顿时长

    # 卡顿类型分布
    stall_type_distribution: dict = field(default_factory=dict)

    # 缓冲区统计
    buffer_empty_ratio: float = 0.0        # 缓冲区耗尽比例 %
    avg_buffer_watermark: float = 0.0      # 平均缓冲区水位

    # TCP统计
    tcp_block_ratio: float = 0.0           # TCP阻塞比例 %
    avg_tcp_retrans_rate: float = 0.0      # 平均TCP重传率

    # 断连统计
    reconnect_count: int = 0

    # 带宽统计
    avg_effective_throughput: float = 0.0   # 平均上行有效吞吐量
    bandwidth_meet_rate: float = 0.0        # 带宽达标率 %

    # 时延统计
    avg_up_latency: float = 0.0
    avg_up_jitter: float = 0.0

    # 卡顿事件列表
    stall_events: list = field(default_factory=list)

    # 瓶颈
    bottleneck: str = ""

    # 异常指标
    abnormal_params: list = field(default_factory=list)


class StateRecorder:
    """状态记录器：归档全时间步数据并生成统计。"""

    def __init__(self, t_step: int = 5):
        self.t_step = t_step
        self.records: list[dict] = []

    def record(self, state: dict):
        """归档单个时间步的完整状态。"""
        self.records.append(state)

    def summarize(self, params) -> SimulationSummary:
        """基于所有时间步State(1)~State(N)，统计核心卡顿指标。"""
        summary = SimulationSummary()
        n = len(self.records)
        if n == 0:
            return summary

        summary.total_steps = n
        summary.sim_duration_ms = n * self.t_step

        # 统计各项指标
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

        # 卡顿事件追踪
        in_stall = False
        stall_start = 0
        current_stall_type = ""
        stall_events: list[StallEvent] = []

        for rec in self.records:
            # 卡顿统计
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
                    # 卡顿结束
                    stall_events.append(StallEvent(
                        start_step=stall_start,
                        end_step=rec["step"] - 1,
                        duration_ms=(rec["step"] - stall_start) * self.t_step,
                        stall_type=current_stall_type,
                    ))
                    in_stall = False

            # 缓冲区空
            if rec.get("buffer_empty_flag", 0) == 1:
                buffer_empty_steps += 1

            # TCP阻塞
            if rec.get("tcp_block_flag", 0) == 1:
                tcp_block_steps += 1

            # 断连
            if rec.get("reconnect_flag", 0) == 1:
                reconnect_count += 1

            # 累计值
            total_buffer += rec.get("buffer_watermark", 0.0)
            total_tcp_retrans += rec.get("tcp_retrans_rate", 0.0)
            total_throughput += rec.get("effective_up_throughput", 0.0)
            total_latency += rec.get("up_latency", 0.0)
            total_jitter += rec.get("up_jitter", 0.0)

            # 带宽达标
            if rec.get("effective_up_throughput", 0.0) >= params.rtmp_bitrate:
                bandwidth_meet_steps += 1

        # 处理仿真结束时仍在卡顿的事件
        if in_stall:
            stall_events.append(StallEvent(
                start_step=stall_start,
                end_step=self.records[-1]["step"],
                duration_ms=(self.records[-1]["step"] - stall_start + 1) * self.t_step,
                stall_type=current_stall_type,
            ))

        # 填充汇总
        summary.stall_steps = stall_steps
        summary.rtmp_stall_rate = (stall_steps / n) * 100.0 if n > 0 else 0.0
        summary.stall_count = len(stall_events)
        summary.avg_stall_duration_ms = (
            sum(e.duration_ms for e in stall_events) / len(stall_events)
            if stall_events else 0.0
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

        # 瓶颈判定
        avg_wifi = sum(r.get("wifi_throughput", 0) for r in self.records) / n
        avg_pon = sum(r.get("pon_up_effective_bw", 0) for r in self.records) / n
        if avg_wifi < avg_pon * 0.9:
            summary.bottleneck = "WiFi上行"
        elif avg_pon < avg_wifi * 0.9:
            summary.bottleneck = "PON上行"
        else:
            summary.bottleneck = "WiFi上行+PON上行"

        # 异常指标检测
        abnormals = []
        if summary.avg_tcp_retrans_rate * 100 >= 5:
            abnormals.append({"param": "tcp_retrans_rate", "avg_value": round(summary.avg_tcp_retrans_rate * 100, 1)})
        if summary.avg_up_latency >= 50:
            abnormals.append({"param": "up_latency", "avg_value": round(summary.avg_up_latency, 1)})
        if summary.avg_up_jitter >= 30:
            abnormals.append({"param": "up_jitter", "avg_value": round(summary.avg_up_jitter, 1)})
        if summary.buffer_empty_ratio >= 10:
            abnormals.append({"param": "buffer_empty_ratio", "avg_value": round(summary.buffer_empty_ratio, 1)})
        summary.abnormal_params = abnormals

        return summary

    def get_timeseries(self, keys: list[str] | None = None) -> dict[str, list]:
        """提取指定KPI的时间序列数据。"""
        if keys is None:
            keys = [
                "effective_up_throughput", "buffer_watermark",
                "stall_active", "primary_stall_type",
                "tcp_retrans_rate", "up_latency", "up_jitter",
                "frame_gen_flag", "frame_drop_flag",
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
        """重置记录。"""
        self.records = []
