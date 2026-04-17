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
    """单个 Skill 脚本执行结果。

    字段契约严格对齐 docs/sse-interface-spec.md §sub_step 与
    api/event_adapter.py 的 sub_step 事件生产：前端流式到达与历史回放
    应当拿到结构一致的 SubStep（仅来源不同）。
    """

    subStepId: str
    name: str
    completedAt: str
    durationMs: int
    # 以下字段按 SSE 规范均为可选，缺失时前端也能正常渲染
    scriptPath: Optional[str] = None
    callArgs: Optional[List[str]] = None
    stdout: Optional[str] = None
    stderr: Optional[str] = None


class Step(BaseModel):
    stepId: str
    title: str
    # 有序渲染块列表（thinking / sub_step / text），历史回放时前端直接使用，
    # 无需从 subSteps 重建，保证与流式展示完全一致。老数据无此字段时默认空列表。
    items: List[Any] = []
    subSteps: List[SubStep] = []
    # SubAgent 本身输出的 assistant content
    textContent: str = ""


# ─── 右侧渲染块 ───────────────────────────────────────────────────────────────

class ChartItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    chartId: str
    title: str
    conclusion: str
    echartsOption: dict
    phaseId: Optional[int] = None
    stepId: Optional[int] = None
    phaseName: Optional[str] = None
    stepName: Optional[str] = None


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


class ExperienceAssuranceRenderData(BaseModel):
    model_config = ConfigDict(extra="allow")

    businessType: str = ""
    applicationType: str = ""
    application: str = ""
    isMock: bool = True
    taskData: dict = {}


class ExperienceAssuranceRenderBlock(BaseModel):
    renderType: Literal["experience_assurance"]
    renderData: ExperienceAssuranceRenderData


RenderBlock = Union[InsightRenderBlock, ImageRenderBlock, ExperienceAssuranceRenderBlock]


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
