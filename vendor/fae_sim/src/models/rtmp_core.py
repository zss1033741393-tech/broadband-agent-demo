"""RTMP推流核心过程模型：帧生成→Chunk封装→缓冲区动态调度。"""

from __future__ import annotations

import math


class RtmpCoreModel:
    """RTMP推流端缓冲区动态仿真，字节级粒度。"""

    def compute_rtmp_kpi(self, step: int, params, trans_kpi: dict) -> dict:
        """计算时间步n的RTMP层瞬时KPI (KPI_RTMP)。

        Args:
            step: 当前时间步编号
            params: SimParams 实例
            trans_kpi: 传输层KPI字典（含 tcp_retrans_rate, rtt 等）

        Returns:
            frame_gen_flag: 帧生成标记 0/1
            chunk_num: 新帧拆分的Chunk数
            tcp_block_flag: TCP阻塞标记 0/1
            heartbeat_check_flag: 心跳检查标记 0/1
            reconnect_flag: 断连重推标记 0/1
        """
        time_ms = step * params.t_step

        # 帧生成标记：当前时间是否为帧间隔的整数倍
        frame_gen_flag = 0
        if params.video_frame_interval > 0:
            # 容差判断：当前时间步覆盖的区间内是否包含帧生成时刻
            t_start = (step - 1) * params.t_step if step > 0 else 0
            t_end = step * params.t_step
            # 检查 [t_start, t_end) 内是否有帧生成点
            frame_idx_start = math.ceil(t_start / params.video_frame_interval)
            frame_idx_end = math.ceil(t_end / params.video_frame_interval)
            if t_end > 0 and frame_idx_start < frame_idx_end:
                frame_gen_flag = 1

        # Chunk数
        chunk_num = 0
        if frame_gen_flag == 1:
            chunk_num = math.ceil(
                params.video_frame_avg_size / params.rtmp_chunk_size
            )

        # TCP阻塞标记
        tcp_retrans_rate_pct = trans_kpi["tcp_retrans_rate"] * 100.0
        tcp_block_flag = 1 if tcp_retrans_rate_pct > params.tcp_retrans_threshold else 0

        # 心跳检查标记：每1000ms检查一次
        heartbeat_check_flag = 0
        if time_ms > 0 and time_ms % 1000 == 0:
            heartbeat_check_flag = 1

        # 断连重推标记
        reconnect_flag = 0
        if heartbeat_check_flag == 1 and trans_kpi["rtt"] > params.rtmp_heartbeat_timeout:
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
        """计算时间步n的缓冲区状态KPI (KPI_Buffer)。

        入队采用码率驱动的持续流模型（in_size = rtmp_bitrate × dt），
        保证帧数据速率与声明码率一致，避免 video_frame_avg_size/fps 与
        rtmp_bitrate 不一致时缓冲区行为失真。

        Args:
            params: SimParams 实例
            prev_buffer_watermark: 上一步缓冲区水位 (Bytes)
            buffer_max_size: 缓冲区最大字节数
            rtmp_kpi: RTMP层KPI字典
            trans_kpi: 传输层KPI字典

        Returns:
            buffer_watermark: 当前缓冲区水位 Bytes
            buffer_empty_flag: 缓冲区空标记 0/1
            frame_drop_flag: 缓冲区溢出/帧丢弃标记 0/1
            in_size: 实际入队字节数
            out_size: 出队字节数
        """
        # 入队字节数 — 按声明码率持续入流（替代帧脉冲模式）
        in_size = (
            params.rtmp_bitrate
            * 1024 * 1024 / 8   # Mbps → Bytes/s
            * params.t_step / 1000  # ms → s
        )

        # 出队字节数
        if rtmp_kpi["tcp_block_flag"] == 1 or rtmp_kpi["reconnect_flag"] == 1:
            out_size = 0.0
        else:
            out_size = (
                trans_kpi["effective_up_throughput"]
                * 1024 * 1024 / 8  # Mbps → Bytes/s
                * params.t_step / 1000  # ms → s
            )

        # 更新缓冲区水位（先算净变化，再判溢出/耗尽）
        new_watermark = prev_buffer_watermark + in_size - out_size

        # 缓冲区溢出：净入量超过最大容量 → 帧丢弃（throughput < bitrate 的持续标志）
        frame_drop_flag = 0
        if new_watermark > buffer_max_size:
            frame_drop_flag = 1
            new_watermark = buffer_max_size

        buffer_watermark = max(0.0, new_watermark)

        # 缓冲区空标记
        buffer_empty_flag = 1 if buffer_watermark <= 0 else 0

        return {
            "buffer_watermark": buffer_watermark,
            "buffer_empty_flag": buffer_empty_flag,
            "frame_drop_flag": frame_drop_flag,
            "in_size": in_size,
            "out_size": out_size,
        }
