"""前端协议数据模型。

所有字段名使用 camelCase 以匹配前端 TypeScript 接口定义。
"""

from __future__ import annotations

from typing import Any, List, Literal, Optional, Union
from pydantic import BaseModel, ConfigDict


# ─── 通用响应包装 ──────────────────────────────────────────────────────────────

class ApiResponse(BaseModel):
    code: int = 0
    message: str = "success"
    data: Any = None


def ok(data: Any = None) -> ApiResponse:
    return ApiResponse(code=0, message="success", data=data)


def err(code: int, message: str) -> ApiResponse:
    return ApiResponse(code=code, message=message, data=None)


# ─── 会话 ─────────────────────────────────────────────────────────────────────

class Conversation(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    title: str
    createdAt: str
    updatedAt: str
    messageCount: int = 0
    lastMessagePreview: str = ""


class ConversationListData(BaseModel):
    list: List[Conversation]
    total: int
    page: int
    pageSize: int


# ─── 步骤卡 ───────────────────────────────────────────────────────────────────

class SubStep(BaseModel):
    subStepId: str
    name: str
    result: str
    completedAt: str
    durationMs: int


class Step(BaseModel):
    stepId: str
    title: str
    subSteps: List[SubStep] = []


# ─── 右侧渲染块 ───────────────────────────────────────────────────────────────

class ChartItem(BaseModel):
    chartId: str
    title: str
    conclusion: str
    echartsOption: dict


class InsightRenderData(BaseModel):
    charts: List[ChartItem]
    markdownReport: str


class ImageRenderData(BaseModel):
    imageId: str
    imageUrl: str
    title: str
    conclusion: str


class InsightRenderBlock(BaseModel):
    renderType: Literal["insight"]
    renderData: InsightRenderData


class ImageRenderBlock(BaseModel):
    renderType: Literal["image"]
    renderData: ImageRenderData


RenderBlock = Union[InsightRenderBlock, ImageRenderBlock]


# ─── 消息 ─────────────────────────────────────────────────────────────────────

class Message(BaseModel):
    id: str
    conversationId: str
    role: Literal["user", "assistant"]
    content: str
    thinkingContent: Optional[str] = None
    thinkingDurationSec: Optional[int] = None
    steps: List[Step] = []
    renderBlocks: List[RenderBlock] = []
    createdAt: str


class MessageListData(BaseModel):
    list: List[Message]


# ─── 请求体 ───────────────────────────────────────────────────────────────────

class CreateConversationRequest(BaseModel):
    title: str = "新对话"


class SendMessageRequest(BaseModel):
    content: str
    deepThinking: bool = False
