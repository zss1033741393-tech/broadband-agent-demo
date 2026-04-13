"""GET/POST/DELETE /api/conversations"""

from fastapi import APIRouter, HTTPException, Query
from loguru import logger

from api.models import (
    ApiResponse,
    ConversationListData,
    CreateConversationRequest,
    ok,
    err,
)
from api import repository as repo

router = APIRouter(prefix="/conversations", tags=["conversations"])

_api_log = logger.bind(channel="api")


@router.get("", response_model=ApiResponse)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
):
    convs, total = await repo.list_conversations(page=page, page_size=pageSize)
    _api_log.info(f"list_conversations page={page} pageSize={pageSize} → total={total}")
    return ok(ConversationListData(list=convs, total=total, page=page, pageSize=pageSize))


@router.post("", response_model=ApiResponse)
async def create_conversation(body: CreateConversationRequest):
    conv = await repo.create_conversation(title=body.title)
    _api_log.info(f"create_conversation → conv_id={conv.id} title={body.title!r}")
    return ok(conv)


@router.patch("/{conv_id}", response_model=ApiResponse)
async def update_conversation(conv_id: str, body: dict):
    title = (body.get("title") or "").strip()
    if not title:
        return err(1003, "标题不能为空")
    updated = await repo.update_conversation_title(conv_id, title)
    if not updated:
        _api_log.warning(f"update_conversation: 会话不存在 conv_id={conv_id}")
        return err(1002, "会话不存在")
    _api_log.info(f"update_conversation conv_id={conv_id} title={title!r}")
    return ok(None)


@router.delete("/{conv_id}", response_model=ApiResponse)
async def delete_conversation(conv_id: str):
    deleted = await repo.delete_conversation(conv_id)
    if not deleted:
        _api_log.warning(f"delete_conversation: 会话不存在 conv_id={conv_id}")
        return err(1002, "会话不存在")
    _api_log.info(f"delete_conversation conv_id={conv_id}")
    return ok(None)
