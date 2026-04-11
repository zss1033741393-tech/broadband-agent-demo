"""
洞察函数基类，所有洞察策略必须继承此类。
"""

from abc import ABC, abstractmethod

import pandas as pd


class InsightStrategy(ABC):
    """洞察分析策略基类"""

    def __init__(self, df: pd.DataFrame):
        self._df = df.copy()
        self._filter_data: pd.DataFrame = pd.DataFrame()
        self._description: str | dict = ""
        self._significance_score: float = 0.0
        self._chart_configs: dict = {}

    @abstractmethod
    def execute(self, **kwargs) -> None:
        """
        执行洞察分析。

        固定参数:
            value_columns: list[str]  - 分析的指标列名
            group_column: str         - 分组/时间列名
        """
        ...

    @property
    def filter_data(self) -> pd.DataFrame:
        """分析结果数据"""
        return self._filter_data

    @property
    def description(self) -> str | dict:
        """文字描述"""
        return self._description

    @property
    def significance_score(self) -> float:
        """显著性得分 [0, 1]"""
        return self._significance_score

    @property
    def chart_configs(self) -> dict:
        """ECharts 图表配置字典"""
        return self._chart_configs
