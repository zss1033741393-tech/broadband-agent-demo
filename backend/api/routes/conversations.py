"""GET/POST/DELETE /api/conversations"""

from fastapi import APIRouter, HTTPException, Query

from api.models import (
    ApiResponse,
    ConversationListData,
    CreateConversationRequest,
    ok,
    err,
)
from api import repository as repo

router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ApiResponse)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    pageSize: int = Query(default=20, ge=1, le=100),
):
    convs, total = await repo.list_conversations(page=page, page_size=pageSize)
    return ok(ConversationListData(list=convs, total=total, page=page, pageSize=pageSize))


@router.post("", response_model=ApiResponse)
async def create_conversation(body: CreateConversationRequest):
    conv = await repo.create_conversation(title=body.title)
    return ok(conv)


@router.delete("/{conv_id}", response_model=ApiResponse)
async def delete_conversation(conv_id: str):
    deleted = await repo.delete_conversation(conv_id)
    if not deleted:
        return err(1002, "会话不存在")
    return ok(None)
