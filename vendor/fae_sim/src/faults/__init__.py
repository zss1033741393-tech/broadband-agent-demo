"""故障注入模块 — 7类典型故障场景的时间步级参数动态注入。"""

from .fault_config import FaultConfig, FAULT_CATALOG
from .fault_injector import inject_faults
from .fault_recovery import recover_faults

__all__ = [
    "FaultConfig",
    "FAULT_CATALOG",
    "inject_faults",
    "recover_faults",
]
