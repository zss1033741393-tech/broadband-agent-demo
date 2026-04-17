"""时间步管理模块。"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimeStepState:
    """单个时间步的完整状态 State(n)。"""
    step: int                          # 时间步编号 n
    time_ms: float                     # 仿真时间戳 n * t_step (ms)

    # 传输层 KPI
    wifi_throughput: float = 0.0       # WiFi上行吞吐量 Mbps
    pon_up_effective_bw: float = 0.0   # PON上行有效带宽 Mbps
    effective_up_throughput: float = 0.0  # 端到端上行有效吞吐量 Mbps
    tcp_retrans_rate: float = 0.0      # 上行TCP重传率
    up_latency: float = 0.0           # 上行总时延 ms
    up_jitter: float = 0.0            # 上行总抖动 ms
    chunk_trans_latency: float = 0.0   # RTMP Chunk传输时延 ms
    frame_trans_latency: float = 0.0   # 视频帧传输时延 ms
    rtt: float = 0.0                   # RTMP心跳往返时延 ms

    # RTMP层 KPI
    frame_gen_flag: int = 0            # 帧生成标记 0/1
    chunk_num: int = 0                 # 新生成帧的Chunk数
    tcp_block_flag: int = 0            # TCP阻塞标记 0/1
    heartbeat_check_flag: int = 0      # 心跳检查标记 0/1
    reconnect_flag: int = 0            # 断连重推标记 0/1

    # 缓冲区 KPI
    buffer_watermark: float = 0.0      # 缓冲区水位 Bytes
    buffer_empty_flag: int = 0         # 缓冲区空标记 0/1
    frame_drop_flag: int = 0           # 帧丢弃标记 0/1
    in_size: float = 0.0              # 入队字节数
    out_size: float = 0.0             # 出队字节数

    # 卡顿判定
    p1: int = 0  # 缓冲区耗尽前置条件
    p2: int = 0  # 帧传输超时前置条件
    p3: int = 0  # TCP重传阻塞前置条件
    p4: int = 0  # 断连重推前置条件
    c1: int = 0  # 缓冲区耗尽持续计数器
    c2: int = 0  # 帧传输超时持续计数器
    c3: int = 0  # TCP重传阻塞持续计数器
    c4: int = 0  # 断连重推计数器(unused, instant trigger)
    s1: int = 0  # 缓冲区耗尽卡顿状态 0=无/1=持续/2=结束
    s2: int = 0  # 帧传输超时卡顿状态
    s3: int = 0  # TCP重传阻塞卡顿状态
    s4: int = 0  # 断连重推卡顿状态
    stall_active: bool = False         # 整体卡顿状态
    primary_stall_type: str = ""       # 主卡顿类型


class TimeStepManager:
    """时间步管理器：管理仿真循环、状态延续。"""

    def __init__(self, t_step: int = 5, sim_duration: int = 300):
        self.t_step = t_step           # 固定5ms
        self.sim_duration = sim_duration  # 仿真时长(秒)
        self.total_steps = sim_duration * 1000 // t_step
        self.current_step = 0
        self.states: list[TimeStepState] = []

    def create_initial_state(self, buffer_max_size: float) -> TimeStepState:
        """创建初始状态 State(0)：缓冲区满水位，计数器清零。"""
        state = TimeStepState(step=0, time_ms=0.0)
        state.buffer_watermark = buffer_max_size
        return state

    def create_step_state(self, step: int, prev_state: TimeStepState) -> TimeStepState:
        """创建新时间步状态，继承上一步的计数器和缓冲区。"""
        state = TimeStepState(step=step, time_ms=step * self.t_step)
        # 继承缓冲区水位
        state.buffer_watermark = prev_state.buffer_watermark
        # 继承卡顿计数器
        state.c1 = prev_state.c1
        state.c2 = prev_state.c2
        state.c3 = prev_state.c3
        state.c4 = prev_state.c4
        # 继承卡顿状态（用于判定"结束"）
        state.s1 = prev_state.s1
        state.s2 = prev_state.s2
        state.s3 = prev_state.s3
        state.s4 = prev_state.s4
        return state

    def record_state(self, state: TimeStepState):
        """归档时间步状态。"""
        self.states.append(state)
        self.current_step = state.step

    def is_complete(self) -> bool:
        """仿真是否完成。"""
        return self.current_step >= self.total_steps

    def reset(self):
        """重置仿真状态。"""
        self.current_step = 0
        self.states = []
