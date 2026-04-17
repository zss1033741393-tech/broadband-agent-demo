"""闭环措施抽象基类与注册中心。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

import yaml

from ..params.schema import SimParams


class Measure(ABC):
    """闭环措施抽象基类。

    子类需实现 apply()，将措施效果映射为对 SimParams 的修正。
    """

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def apply(self, params: SimParams) -> SimParams:
        """应用措施，返回修正后的参数副本（不修改原始参数）。"""
        ...


class YamlMeasure(Measure):
    """从 YAML 配置文件加载的通用措施。"""

    def __init__(self, config: dict):
        self.name = config["name"]
        self.description = config.get("description", "")
        self.effects: list[dict] = config.get("effects", [])

    def apply(self, params: SimParams) -> SimParams:
        p = params.copy()
        for effect in self.effects:
            param_name = effect["param"]
            op = effect.get("operation", "set")
            value = effect["value"]

            # 检查条件
            if not self._check_condition(p, effect.get("condition")):
                continue

            current = getattr(p, param_name, p.extra.get(param_name))
            if current is None:
                continue

            if op == "set":
                new_val = value
            elif op == "add":
                new_val = current + value
            elif op == "multiply":
                new_val = current * value
            else:
                continue

            if hasattr(p, param_name):
                setattr(p, param_name, new_val)
            else:
                p.extra[param_name] = new_val
        return p

    @staticmethod
    def _check_condition(params: SimParams, condition: dict | None) -> bool:
        if condition is None:
            return True
        for key, threshold in condition.items():
            # 支持 param_lt / param_gt / param_eq 后缀
            if key.endswith("_lt"):
                field = key[:-3]
                val = getattr(params, field, params.extra.get(field))
                if val is None or val >= threshold:
                    return False
            elif key.endswith("_gt"):
                field = key[:-3]
                val = getattr(params, field, params.extra.get(field))
                if val is None or val <= threshold:
                    return False
            elif key.endswith("_eq"):
                field = key[:-3]
                val = getattr(params, field, params.extra.get(field))
                if val != threshold:
                    return False
        return True


class MeasureRegistry:
    """措施注册中心，管理所有可用的闭环措施。"""

    def __init__(self):
        self._measures: dict[str, Measure] = {}

    def register(self, measure: Measure) -> None:
        self._measures[measure.name] = measure

    def get(self, name: str) -> Measure | None:
        return self._measures.get(name)

    def list_names(self) -> list[str]:
        return list(self._measures.keys())

    def list_all(self) -> list[Measure]:
        return list(self._measures.values())

    def load_yaml_dir(self, directory: str | Path) -> int:
        """从目录加载所有 YAML 措施配置，返回加载数量。"""
        d = Path(directory)
        if not d.is_dir():
            return 0
        count = 0
        for f in sorted(d.glob("*.yaml")):
            with open(f, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh)
            if config and "name" in config:
                self.register(YamlMeasure(config))
                count += 1
        for f in sorted(d.glob("*.yml")):
            with open(f, "r", encoding="utf-8") as fh:
                config = yaml.safe_load(fh)
            if config and "name" in config:
                self.register(YamlMeasure(config))
                count += 1
        return count


def create_default_registry() -> MeasureRegistry:
    """创建包含所有内置措施的注册中心。"""
    from .wifi_channel_opt import WifiChannelOptimization
    from .wifi_band_opt import WifiBandOptimization
    from .wifi_roaming_opt import WifiRoamingOptimization
    from .pon_expansion import PonExpansion
    from .wifi_timeslot import WifiTimeslotGuarantee
    from .pon_traffic_limit import PonTrafficLimit
    from .wifi_add_ap import WifiAddAp
    from .upgrade_package import UpgradePackage
    from .pon_fiber_repair import PonFiberRepair

    registry = MeasureRegistry()
    for cls in [
        WifiChannelOptimization,
        WifiBandOptimization,
        WifiRoamingOptimization,
        PonExpansion,
        WifiTimeslotGuarantee,
        PonTrafficLimit,
        WifiAddAp,
        UpgradePackage,
        PonFiberRepair,
    ]:
        registry.register(cls())
    return registry
