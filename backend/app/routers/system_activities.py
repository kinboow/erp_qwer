"""系统动态 API 路由"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies import get_current_user
from app.models import User
from app.services.system_activities import list_activities

router = APIRouter(tags=["系统动态"])


def _ok(data=None, message="success"):
    resp = {"code": 200, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


@router.get("", summary="获取系统动态列表")
async def api_list(
    type: Optional[str] = Query(None),
    source: Optional[str] = Query(None),
    keyword: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = list_activities(
        db, type=type, source=source,
        keyword=keyword, page=page, page_size=page_size,
    )
    return _ok(data=result)
