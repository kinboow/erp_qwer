"""系统消息 API 路由"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.system_messages import (
    get_unread_count,
    list_system_messages,
    mark_all_as_read,
    mark_as_read,
)

router = APIRouter(tags=["系统消息"])


def _ok(data=None, message="success"):
    resp = {"code": 200, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("", summary="获取系统消息列表")
def api_list(
    level: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    is_read: Optional[int] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = list_system_messages(
        db, level=level, source=source, is_read=is_read,
        keyword=keyword, page=page, page_size=page_size,
    )
    return _ok(data=result)


@router.get("/unread-count", summary="获取未读系统消息数量")
def api_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = get_unread_count(db)
    return _ok(data={"count": count})


@router.put("/{message_id}/read", summary="标记单条消息为已读")
def api_mark_read(
    message_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    mark_as_read(db, message_id)
    return _ok(message="已标记为已读")


@router.put("/read-all", summary="全部标记为已读")
def api_mark_all_read(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = mark_all_as_read(db)
    return _ok(message=f"已标记 {count} 条消息为已读")
