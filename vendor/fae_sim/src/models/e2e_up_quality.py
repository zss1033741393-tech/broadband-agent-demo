"""端到端上行传输质量模型（时间步级瞬时KPI）。"""

from __future__ import annotations

import math


class E2EUpQualityModel:
    """基于WiFi和PON上行瞬时指标，计算端到端上行传输质量KPI。"""

    def calculate(
        self,
        wifi_throughput: float,
        pon_up_effective_bw: float,
        params,
    ) -> dict:
        """计算时间步n的端到端上行传输质量KPI。

        返回字典包含:
            effective_up_throughput: 上行有效吞吐量 Mbps
            tcp_retrans_rate: 上行TCP重传率 (0~1)
            up_latency: 上行总时延 ms
            up_jitter: 上行总抖动 ms
            chunk_trans_latency: RTMP Chunk传输时延 ms
            frame_trans_latency: 视频帧传输时延 ms
            rtt: RTMP心跳往返时延 ms
        """
        # 上行有效吞吐量（瓶颈取最小值）
        effective_up_throughput = min(wifi_throughput, pon_up_effective_bw)
        effective_up_throughput = max(effective_up_throughput, 0.001)  # 防除零

        # 上行TCP重传率（级联）
        wifi_tcp = params.wifi_up_tcp_retrans_rate / 100.0
        pon_tcp = params.pon_up_tcp_retrans_rate / 100.0
        tcp_retrans_rate = 1.0 - (1.0 - wifi_tcp) * (1.0 - pon_tcp)

        # 上行总时延（多段级联）
        up_latency = (
            params.wifi_up_latency
            + params.pon_up_latency
            + tcp_retrans_rate * 100.0
        )

        # 上行总抖动
        up_jitter = (
            params.wifi_up_jitter
            + params.pon_up_jitter
            + 0.2 * params.pon_dba_cycle
        )

        # RTMP Chunk 传输时延 (ms)
        chunk_trans_latency = (
            (params.rtmp_chunk_size * 8)
            / (effective_up_throughput * 1024 * 1024)
            * 1000
        )

        # 视频帧传输时延 (ms)
        frame_trans_latency = (
            (params.video_frame_avg_size * 8)
            / (effective_up_throughput * 1024 * 1024)
            * 1000
        )

        # RTMP 心跳往返时延
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
