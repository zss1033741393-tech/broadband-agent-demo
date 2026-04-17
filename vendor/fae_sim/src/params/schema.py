"""仿真参数 Schema 定义与校验。

完整的 RTMP 直播网络仿真参数，覆盖 WiFi 物理层(17项)、PON 光路(17项)、
RTMP 推流应用(9项) 以及仿真控制字段。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, fields, asdict


@dataclass
class SimParams:
    """仿真全部输入参数。"""

    # ══════════════════════════════════════════════════════════════════════
    #  WiFi 物理层 (17 项)
    # ══════════════════════════════════════════════════════════════════════
    wifi_channel: int = 36                        # 信道编号: 1-13(2.4G), 36-165(5G)
    wifi_bandwidth: int = 80                      # MHz: 20/40/80/160
    wifi_rssi: float = -50.0                      # dBm, 接收信号强度
    wifi_noise_floor: float = -90.0               # dBm, 底噪
    wifi_interference_ratio: float = 45.0         # %, 同频干扰占比
    sta_count: int = 15                           # 终端数量, 1-64
    wifi_standard: str = "wifi6"                  # wifi4/wifi5/wifi6/wifi6e/wifi7
    sta_spatial_streams: int = 2                  # 空间流数, 1-4
    wifi_retry_rate: float = 5.0                  # %, 空口重传率
    wifi_multipath_fading: float = 0.2            # 0-1, 多径衰落系数
    wifi_mu_mimo_enabled: bool = True             # MU-MIMO 开启
    wifi_gi: int = 800                            # 保护间隔 ns: 400/800
    wifi_code_rate: str = "5/6"                   # 信道编码率: 1/2, 2/3, 3/4, 5/6
    wifi_up_retry_rate: float = 5.0               # %, 上行重传率 (>=15 异常)
    wifi_up_tcp_retrans_rate: float = 2.0         # %, 上行 TCP 重传率 (>=5 异常)
    wifi_up_latency: float = 10.0                 # ms, 上行时延 (>=50 异常)
    wifi_up_jitter: float = 5.0                   # ms, 上行抖动 (>=30 异常)

    # ══════════════════════════════════════════════════════════════════════
    #  PON 光路物理层 (17 项)
    # ══════════════════════════════════════════════════════════════════════
    pon_uplink_bw: float = 50.0                   # Mbps, 上行带宽
    pon_downlink_bw: float = 1000.0               # Mbps, 下行带宽
    pon_bip_error_rate: float = 1e-7              # BIP 误码率, 0 ~ 1e-3
    pon_fec_pre_error_rate: float = 1e-4          # FEC 纠错前误码率, 0 ~ 1e-2
    pon_fec_post_error_rate: float = 1e-9         # FEC 纠错后误码率, 0 ~ 1e-6
    pon_rx_power: float = -15.0                   # dBm, 光接收功率
    pon_split_ratio: int = 64                     # 分光比 1:N, 16-128
    pon_up_load_ratio: float = 50.0               # %, 上行负载率
    pon_down_load_ratio: float = 40.0             # %, 下行负载率
    pon_optical_attenuation: float = 10.0         # dB, 光路衰减
    pon_dba_cycle: float = 2.0                    # ms, DBA 调度周期
    pon_burst_collision: float = 0.01             # 0-0.1, 上行突发冲突概率
    pon_es: float = 5.0                           # 秒/小时, 误码秒
    user_priority_weight: float = 1.0             # 用户优先级权重: 0.3=普通, 0.5=FTTR, 1.0=直播/VIP
    pon_tx_power: float = -10.0                   # dBm, ONU上行发射光功率 (-15~-5)
    pon_up_tcp_retrans_rate: float = 2.0          # %, PON 上行 TCP 重传率 (>=5 异常)
    pon_up_latency: float = 20.0                  # ms, PON 上行时延 (>=80 异常)
    pon_up_jitter: float = 10.0                   # ms, PON 上行抖动 (>=50 异常)

    # ══════════════════════════════════════════════════════════════════════
    #  RTMP 推流应用层 (9 项)
    # ══════════════════════════════════════════════════════════════════════
    rtmp_bitrate: float = 20.0                    # Mbps, 推流码率 (4=标清/8=高清/16=4K)
    rtmp_buffer_ms: int = 200                     # ms, 缓冲区时长
    video_frame_interval: float = 33.0            # ms, 帧间隔 (33≈30fps, 16.7≈60fps)
    video_frame_avg_size: int = 16384             # Bytes, 平均帧大小 (由 bitrate/fps 计算)
    rtmp_chunk_size: int = 4096                   # Bytes, RTMP 分块大小
    tcp_retrans_threshold: float = 5.0            # %, TCP 重传告警阈值
    rtmp_heartbeat_timeout: int = 3000            # ms, 心跳超时
    t_step: int = 5                               # ms, 仿真步长 (固定值，不可配置)
    sim_duration: int = 300                       # 秒, 仿真总时长 (>=10)

    # ══════════════════════════════════════════════════════════════════════
    #  仿真控制
    # ══════════════════════════════════════════════════════════════════════
    random_seed: int | None = None                # 随机种子, None 表示不固定
    extra: dict = field(default_factory=dict)     # 动态扩展字段 (YAML 注入)

    # ================================================================== #
    #  属性
    # ================================================================== #

    @property
    def total_steps(self) -> int:
        """仿真总步数 = sim_duration * 1000 // t_step。"""
        return self.sim_duration * 1000 // self.t_step

    @property
    def buffer_max_size(self) -> float:
        """缓冲区最大容量(Bytes) = rtmp_buffer_ms * rtmp_bitrate * 1024 * 1024 / 8 / 1000。"""
        return self.rtmp_buffer_ms * self.rtmp_bitrate * 1024 * 1024 / 8 / 1000

    # ================================================================== #
    #  校验
    # ================================================================== #

    def validate(self) -> list[str]:
        """校验参数合法性，返回错误列表（空列表表示通过）。"""
        errors: list[str] = []

        # ── 枚举值校验 ──
        valid_standards = {"wifi4", "wifi5", "wifi6", "wifi6e", "wifi7"}
        if self.wifi_standard not in valid_standards:
            errors.append(
                f"wifi_standard 必须是 {valid_standards} 之一, 当前: {self.wifi_standard}"
            )

        valid_code_rates = {"1/2", "2/3", "3/4", "5/6"}
        if self.wifi_code_rate not in valid_code_rates:
            errors.append(
                f"wifi_code_rate 必须是 {valid_code_rates} 之一, 当前: {self.wifi_code_rate}"
            )

        valid_bandwidths = [20, 40, 80, 160]
        if self.wifi_bandwidth not in valid_bandwidths:
            errors.append(
                f"wifi_bandwidth 必须是 {valid_bandwidths} 之一, 当前: {self.wifi_bandwidth}"
            )

        valid_gi = [400, 800]
        if self.wifi_gi not in valid_gi:
            errors.append(
                f"wifi_gi 必须是 {valid_gi} 之一, 当前: {self.wifi_gi}"
            )

        # ── 范围校验 ──
        _range_checks: list[tuple[str, float | int, tuple[float, float]]] = [
            # WiFi 物理层
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

            # PON 光路
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

            # RTMP 推流应用
            ("rtmp_bitrate", self.rtmp_bitrate, (2, 20)),
            ("rtmp_buffer_ms", self.rtmp_buffer_ms, (0, 300)),
            ("video_frame_interval", self.video_frame_interval, (8.3, 66)),
            ("video_frame_avg_size", self.video_frame_avg_size, (4096, 65536)),
            ("rtmp_chunk_size", self.rtmp_chunk_size, (1024, 8192)),
            ("tcp_retrans_threshold", self.tcp_retrans_threshold, (1, 10)),
            ("rtmp_heartbeat_timeout", self.rtmp_heartbeat_timeout, (2000, 5000)),

            # 仿真控制
            ("sim_duration", self.sim_duration, (10, float("inf"))),
        ]

        for name, value, (lo, hi) in _range_checks:
            if not (lo <= value <= hi):
                errors.append(f"{name} 超出范围 [{lo}, {hi}], 当前: {value}")

        # t_step 固定为 5ms，不允许修改
        if self.t_step != 5:
            errors.append(f"t_step 固定为 5 ms, 不可修改, 当前: {self.t_step}")

        # wifi_channel 合法值: 2.4G 频段 1-13, 5G 频段 36-165
        valid_2g = set(range(1, 14))
        valid_5g = set(range(36, 166))
        if self.wifi_channel not in valid_2g | valid_5g:
            errors.append(
                f"wifi_channel 必须在 1-13(2.4G) 或 36-165(5G) 范围内, 当前: {self.wifi_channel}"
            )

        return errors

    # ================================================================== #
    #  序列化与拷贝
    # ================================================================== #

    def copy(self) -> SimParams:
        """深拷贝。"""
        return copy.deepcopy(self)

    def to_dict(self) -> dict:
        """转为字典。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> SimParams:
        """从字典构造，未知字段放入 extra。"""
        known = {f.name for f in fields(cls)}
        init_kwargs = {k: v for k, v in data.items() if k in known}
        extra = {k: v for k, v in data.items() if k not in known}
        params = cls(**init_kwargs)
        params.extra.update(extra)
        return params
