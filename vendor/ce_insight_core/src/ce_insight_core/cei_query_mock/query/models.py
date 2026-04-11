"""
Mock 版 InsightSubspace API Model，与内网 cei_query.query.models 接口一致。
"""

from pydantic import BaseModel


class InsightSubspaceApiModel(BaseModel):
    """三元组查询结构，与内网 cei_query.query.models.InsightSubspace 一致"""

    dimensions: list[list] = [[]]
    breakdown: dict = {}
    measures: list[dict] = []
