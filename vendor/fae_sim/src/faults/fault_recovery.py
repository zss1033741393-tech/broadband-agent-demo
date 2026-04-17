"""故障自愈核心函数 — 应用绑定措施回滚参数至正常范围。"""

from __future__ import annotations

from ..params.schema import SimParams
from ..measures.base import MeasureRegistry
from .fault_config import FaultConfig, FAULT_CATALOG


def recover_faults(params: SimParams, config: FaultConfig,
                   registry: MeasureRegistry) -> SimParams:
    """基于闭环措施，回滚参数至正常范围。

    当 config.recovery_measures 非空时，应用用户选择的措施；
    否则应用故障目录中绑定的默认措施。
    """
    if not config.is_active or not config.fault_recover_flag:
        return params

    p = params.copy()
    applied: set[str] = set()

    if config.recovery_measures is not None:
        # 用户显式选择的措施列表
        for measure_name in config.recovery_measures:
            if measure_name in applied:
                continue
            m = registry.get(measure_name)
            if m:
                p = m.apply(p)
                applied.add(measure_name)
    else:
        # 默认：应用故障绑定的措施
        for fid in config.enabled_faults:
            info = FAULT_CATALOG.get(fid)
            if not info:
                continue
            for measure_name in info["bound_measures"]:
                if measure_name in applied:
                    continue
                m = registry.get(measure_name)
                if m:
                    p = m.apply(p)
                    applied.add(measure_name)
    return p
