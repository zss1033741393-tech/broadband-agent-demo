"""仿真引擎 — 时间步级RTMP推流仿真主循环。"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

from .params.schema import SimParams
from .models.wifi_up_throughput import WifiUpThroughputModel
from .models.pon_up_throughput import PonUpThroughputModel
from .models.e2e_up_quality import E2EUpQualityModel
from .models.rtmp_core import RtmpCoreModel
from .models.rtmp_stall_detect import RtmpStallDetector
from .models.state_recorder import StateRecorder, SimulationSummary
from .measures.base import Measure, MeasureRegistry, create_default_registry
from .faults import FaultConfig, inject_faults, recover_faults


@dataclass
class MeasureResult:
    """单个措施的评估结果。"""
    measure_name: str
    description: str
    summary: SimulationSummary
    improvement: float          # 卡顿率改善百分比（负值表示改善）
    timeseries: dict | None = None


@dataclass
class SimulationReport:
    """完整仿真报告。"""
    params: SimParams
    baseline_summary: SimulationSummary
    baseline_timeseries: dict | None = None
    measure_results: list[MeasureResult] = field(default_factory=list)
    combined_result: MeasureResult | None = None


class SimulationEngine:
    """时间步级RTMP推流仿真引擎。

    核心循环：对每个时间步n=1..N:
        1. WiFi上行吞吐量
        2. PON上行吞吐量
        3. 端到端上行传输质量
        4. RTMP层KPI（帧生成/TCP阻塞/心跳）
        5. 缓冲区动态调度
        6. 实时卡顿判定
        7. 状态归档
    """

    def __init__(
        self,
        registry: MeasureRegistry | None = None,
        extra_measures_dir: str | Path | None = None,
    ):
        self.registry = registry or create_default_registry()
        if extra_measures_dir:
            self.registry.load_yaml_dir(extra_measures_dir)

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
        """运行完整时间步仿真。

        Args:
            params: 仿真参数
            collect_timeseries: 是否收集时序数据
            rng: 随机数生成器（用于瞬时指标波动）
            fault_config: 故障注入配置
            initial_prev: 续接用的初始状态（None 则从默认满缓冲区开始）
            step_offset: 全局步号偏移（续接时使用）

        Returns:
            (summary, timeseries_or_None, final_prev)
        """
        if rng is None:
            seed = params.random_seed if params.random_seed is not None else 42
            rng = np.random.default_rng(seed)

        t_step = params.t_step
        total_steps = params.total_steps
        buffer_max_size = params.buffer_max_size

        # ── 随机模式故障片段预生成 ──
        if (fault_config and fault_config.is_active
                and fault_config.fault_inject_mode == "random"):
            fault_config.generate_random_segments(total_steps, rng)

        recorder = StateRecorder(t_step=t_step)

        # ── 初始状态 ──
        if initial_prev is not None:
            prev = dict(initial_prev)
        else:
            prev = {
                "buffer_watermark": buffer_max_size,
                "c1": 0, "c2": 0, "c3": 0, "c4": 0,
                "s1": 0, "s2": 0, "s3": 0, "s4": 0,
            }

        # ── 生成瞬时波动序列（批量高效） ──
        # WiFi RSSI 慢衰落 + 快衰落
        rssi_slow = self._slow_fading(total_steps, sigma=2.0, rng=rng)
        rssi_fast = rng.normal(0, 1.0, total_steps)
        # WiFi 干扰波动
        interf_noise = rng.normal(0, 2.0, total_steps)
        # PON 上行负载波动
        pon_load_noise = rng.normal(0, 3.0, total_steps)
        # WiFi/PON 时延抖动波动
        wifi_latency_noise = rng.normal(0, 1.0, total_steps)
        pon_latency_noise = rng.normal(0, 2.0, total_steps)
        wifi_jitter_noise = rng.exponential(1.0, total_steps)
        pon_jitter_noise = rng.exponential(1.5, total_steps)
        # TCP重传率波动
        wifi_tcp_noise = rng.exponential(0.5, total_steps)
        pon_tcp_noise = rng.exponential(0.3, total_steps)

        # ── 时间步循环 ──
        for n in range(1, total_steps + 1):
            idx = n - 1
            global_step = step_offset + n
            time_ms = global_step * t_step

            # 构建瞬时参数（带波动）
            inst = params.copy()
            inst.wifi_rssi = params.wifi_rssi + rssi_slow[idx] + rssi_fast[idx]
            inst.wifi_interference_ratio = max(0, min(100,
                params.wifi_interference_ratio + interf_noise[idx]))
            inst.pon_up_load_ratio = max(0, min(100,
                params.pon_up_load_ratio + pon_load_noise[idx]))
            inst.wifi_up_latency = max(1, params.wifi_up_latency + wifi_latency_noise[idx])
            inst.pon_up_latency = max(5, params.pon_up_latency + pon_latency_noise[idx])
            inst.wifi_up_jitter = max(1, params.wifi_up_jitter + wifi_jitter_noise[idx])
            inst.pon_up_jitter = max(1, params.pon_up_jitter + pon_jitter_noise[idx])
            inst.wifi_up_tcp_retrans_rate = max(0, min(20,
                params.wifi_up_tcp_retrans_rate + wifi_tcp_noise[idx]))
            inst.pon_up_tcp_retrans_rate = max(0, min(20,
                params.pon_up_tcp_retrans_rate + pon_tcp_noise[idx]))

            # 故障注入（在故障窗口内修改参数）
            if fault_config and fault_config.is_active:
                inst = inject_faults(inst, n, fault_config, total_steps, rng=rng)
                # 故障自愈（故障窗口结束后应用绑定措施修复）
                if fault_config.is_recovery_active_at(n, total_steps):
                    inst = recover_faults(inst, fault_config, self.registry)

            # Step 1: WiFi上行吞吐量
            wifi_tp = self.wifi_model.calculate(inst)

            # Step 2: PON上行吞吐量
            pon_up_bw = self.pon_model.calculate_up(inst)

            # Step 3: 端到端上行传输质量
            trans_kpi = self.e2e_model.calculate(wifi_tp, pon_up_bw, inst)

            # Step 4: RTMP层KPI
            rtmp_kpi = self.rtmp_model.compute_rtmp_kpi(n, inst, trans_kpi)

            # Step 5: 缓冲区动态调度
            buffer_kpi = self.rtmp_model.compute_buffer_kpi(
                inst,
                prev["buffer_watermark"],
                buffer_max_size,
                rtmp_kpi,
                trans_kpi,
            )

            # Step 6: 实时卡顿判定
            stall_kpi = self.stall_detector.detect(
                buffer_kpi, rtmp_kpi, trans_kpi, inst,
                prev["c1"], prev["c2"], prev["c3"], prev["c4"],
                prev["s1"], prev["s2"], prev["s3"], prev["s4"],
            )

            # Step 7: 归档 State(n)
            state = {
                "step": global_step,
                "time_ms": time_ms,
                # 传输层
                "wifi_throughput": wifi_tp,
                "pon_up_effective_bw": pon_up_bw,
                **trans_kpi,
                # RTMP层
                **rtmp_kpi,
                # 缓冲区
                **buffer_kpi,
                # 卡顿
                **stall_kpi,
            }
            recorder.record(state)

            # 更新 prev 状态（延续到下一步）
            prev["buffer_watermark"] = buffer_kpi["buffer_watermark"]
            prev["c1"] = stall_kpi["c1"]
            prev["c2"] = stall_kpi["c2"]
            prev["c3"] = stall_kpi["c3"]
            prev["c4"] = stall_kpi["c4"]
            prev["s1"] = stall_kpi["s1"]
            prev["s2"] = stall_kpi["s2"]
            prev["s3"] = stall_kpi["s3"]
            prev["s4"] = stall_kpi["s4"]

        # ── 统计汇总 ──
        summary = recorder.summarize(params)
        timeseries = recorder.get_timeseries() if collect_timeseries else None

        return summary, timeseries, prev

    def run_baseline(
        self,
        params: SimParams,
        *,
        collect_timeseries: bool = True,
    ) -> tuple[SimulationSummary, dict | None]:
        """运行基线仿真。"""
        summary, ts, _ = self.simulate(params, collect_timeseries=collect_timeseries)
        return summary, ts

    def run_single_measure(
        self,
        params: SimParams,
        measure: Measure,
        baseline_stall_rate: float,
        *,
        collect_timeseries: bool = False,
    ) -> MeasureResult:
        """运行单措施仿真。"""
        modified = measure.apply(params)
        summary, ts, _ = self.simulate(modified, collect_timeseries=collect_timeseries)
        if baseline_stall_rate > 0:
            improvement = ((summary.rtmp_stall_rate - baseline_stall_rate)
                           / baseline_stall_rate * 100.0)
        else:
            improvement = 0.0
        return MeasureResult(
            measure_name=measure.name,
            description=measure.description,
            summary=summary,
            improvement=round(improvement, 2),
            timeseries=ts,
        )

    def run_combined(
        self,
        params: SimParams,
        measure_names: list[str],
        baseline_stall_rate: float,
        *,
        collect_timeseries: bool = False,
    ) -> MeasureResult:
        """叠加多个措施后仿真。"""
        p = params.copy()
        for name in measure_names:
            m = self.registry.get(name)
            if m:
                p = m.apply(p)
        # 校验叠加后参数合法性
        errors = p.validate()
        if errors:
            # 自动修正越界参数
            p = self._clamp_params(p)

        summary, ts, _ = self.simulate(p, collect_timeseries=collect_timeseries)
        if baseline_stall_rate > 0:
            improvement = ((summary.rtmp_stall_rate - baseline_stall_rate)
                           / baseline_stall_rate * 100.0)
        else:
            improvement = 0.0
        return MeasureResult(
            measure_name="combined",
            description="所有措施叠加",
            summary=summary,
            improvement=round(improvement, 2),
            timeseries=ts,
        )

    def run_full(
        self,
        params: SimParams,
        measure_names: list[str] | None = None,
        *,
        collect_timeseries: bool = True,
    ) -> SimulationReport:
        """完整仿真：基线 + 逐措施 + 组合。"""
        errors = params.validate()
        if errors:
            raise ValueError(f"参数校验失败: {'; '.join(errors)}")

        # 基线
        baseline_summary, baseline_ts = self.run_baseline(
            params, collect_timeseries=collect_timeseries
        )
        report = SimulationReport(
            params=params,
            baseline_summary=baseline_summary,
            baseline_timeseries=baseline_ts,
        )

        names = measure_names or self.registry.list_names()
        active_names: list[str] = []

        for name in names:
            m = self.registry.get(name)
            if m is None:
                continue
            active_names.append(name)
            mr = self.run_single_measure(
                params, m, baseline_summary.rtmp_stall_rate,
                collect_timeseries=collect_timeseries,
            )
            report.measure_results.append(mr)

        if len(active_names) > 1:
            report.combined_result = self.run_combined(
                params, active_names, baseline_summary.rtmp_stall_rate,
                collect_timeseries=collect_timeseries,
            )

        return report

    @staticmethod
    def _slow_fading(n: int, sigma: float, rng: np.random.Generator) -> np.ndarray:
        """生成慢衰落序列（低通滤波随机游走）。"""
        raw = rng.normal(0, sigma, n)
        # 简单一阶低通滤波
        alpha = 0.005
        out = np.zeros(n)
        out[0] = raw[0]
        for i in range(1, n):
            out[i] = out[i - 1] * (1 - alpha) + raw[i] * alpha
        return out

    @staticmethod
    def _clamp_params(p: SimParams) -> SimParams:
        """将参数限制在合法范围内。"""
        p.wifi_rssi = max(-90, min(-20, p.wifi_rssi))
        p.wifi_interference_ratio = max(0, min(100, p.wifi_interference_ratio))
        p.wifi_up_tcp_retrans_rate = max(0, min(20, p.wifi_up_tcp_retrans_rate))
        p.wifi_up_latency = max(1, min(100, p.wifi_up_latency))
        p.wifi_up_jitter = max(1, min(50, p.wifi_up_jitter))
        p.pon_up_load_ratio = max(0, min(100, p.pon_up_load_ratio))
        p.pon_down_load_ratio = max(0, min(100, p.pon_down_load_ratio))
        p.pon_up_tcp_retrans_rate = max(0, min(20, p.pon_up_tcp_retrans_rate))
        p.pon_up_latency = max(5, min(200, p.pon_up_latency))
        p.pon_up_jitter = max(1, min(100, p.pon_up_jitter))
        p.pon_uplink_bw = max(0, min(2500, p.pon_uplink_bw))
        return p
