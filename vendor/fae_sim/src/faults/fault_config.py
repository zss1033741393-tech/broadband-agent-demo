"""故障配置定义与校验。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

import numpy as np


# 故障目录：id → (名称, 等级, 绑定措施列表)
FAULT_CATALOG = {
    1: {"name": "频繁WiFi漫游",   "severity": "严重", "bound_measures": ["wifi_roaming_opt"]},
    2: {"name": "WiFi干扰严重",    "severity": "中度", "bound_measures": ["wifi_channel_opt", "wifi_band_opt"]},
    3: {"name": "WiFi覆盖弱",      "severity": "严重", "bound_measures": ["wifi_add_ap"]},
    4: {"name": "上行带宽不足",    "severity": "中度", "bound_measures": ["pon_expansion", "upgrade_package"]},
    5: {"name": "PON口拥塞",       "severity": "中度", "bound_measures": ["pon_traffic_limit"]},
    6: {"name": "多STA竞争",       "severity": "轻度", "bound_measures": ["wifi_timeslot"]},
    7: {"name": "PON光纤中断",     "severity": "严重", "bound_measures": ["pon_fiber_repair"]},
}


@dataclass
class FaultConfig:
    """故障注入全局配置。"""
    enabled_faults: list[int] = field(default_factory=list)
    fault_start_step: int = 1000
    fault_duration_step: int = 40000      # -1 表示持续至仿真结束
    fault_recover_flag: bool = False
    recovery_measures: list[str] | None = None  # 用户选择的恢复措施；None=使用绑定措施
    # 双模式支持
    fault_inject_mode: Literal["fixed", "random"] = "fixed"
    random_fault_count: int = 5           # 随机模式：故障片段数
    random_fault_max_duration: int = 2000  # 随机模式：单片段最大持续步数
    # 预生成的随机故障片段列表 [(start, duration), ...]
    _random_segments: list[tuple[int, int]] = field(
        default_factory=list, repr=False,
    )

    def validate(self, total_steps: int) -> list[str]:
        """校验配置合法性。"""
        errors: list[str] = []
        for fid in self.enabled_faults:
            if fid not in FAULT_CATALOG:
                errors.append(f"无效故障ID: {fid}")
        if self.fault_inject_mode not in ("fixed", "random"):
            errors.append(f"fault_inject_mode 必须为 'fixed' 或 'random'，当前: {self.fault_inject_mode}")
        if self.fault_inject_mode == "fixed":
            if self.fault_start_step < 1:
                errors.append("fault_start_step 必须 >= 1")
            if self.fault_start_step > total_steps:
                errors.append(f"fault_start_step({self.fault_start_step}) 超过总步数({total_steps})")
            if self.fault_duration_step != -1 and self.fault_duration_step < 1:
                errors.append("fault_duration_step 必须 >= 1 或 -1")
        else:  # random
            if self.random_fault_count < 1:
                errors.append("random_fault_count 必须 >= 1")
            if self.random_fault_max_duration < 1:
                errors.append("random_fault_max_duration 必须 >= 1")
            if self.random_fault_max_duration > total_steps:
                errors.append(
                    f"random_fault_max_duration({self.random_fault_max_duration}) "
                    f"超过总步数({total_steps})")
        return errors

    @property
    def is_active(self) -> bool:
        return len(self.enabled_faults) > 0

    def fault_end_step(self, total_steps: int) -> int:
        """fixed 模式的故障结束步。random 模式下返回最后一个片段的结束步。"""
        if self.fault_inject_mode == "random":
            if not self._random_segments:
                return 0
            return max(s + d for s, d in self._random_segments)
        if self.fault_duration_step == -1:
            return total_steps
        return min(self.fault_start_step + self.fault_duration_step, total_steps)

    def generate_random_segments(self, total_steps: int,
                                 rng: np.random.Generator) -> None:
        """基于随机种子预生成故障片段列表。仅 random 模式调用。"""
        segments: list[tuple[int, int]] = []
        for _ in range(self.random_fault_count):
            start = int(rng.integers(1, total_steps + 1))
            duration = int(rng.integers(1, self.random_fault_max_duration + 1))
            segments.append((start, duration))
        segments.sort(key=lambda s: s[0])
        self._random_segments = segments

    def is_fault_active_at(self, step: int, total_steps: int) -> bool:
        """判断时间步 step 是否处于故障注入窗口内。"""
        if self.fault_inject_mode == "fixed":
            start = self.fault_start_step
            end = self.fault_end_step(total_steps)
            return start <= step <= end
        # random 模式：检查是否落在任一片段内
        for seg_start, seg_dur in self._random_segments:
            if seg_start <= step <= seg_start + seg_dur:
                return True
        return False

    def is_recovery_active_at(self, step: int, total_steps: int) -> bool:
        """判断时间步 step 是否处于故障恢复阶段。"""
        if not self.fault_recover_flag:
            return False
        if self.fault_inject_mode == "fixed":
            return step > self.fault_end_step(total_steps)
        # random 模式：不在任何故障片段内，但在最后一个片段结束后
        if self.is_fault_active_at(step, total_steps):
            return False
        return step > self.fault_end_step(total_steps)
