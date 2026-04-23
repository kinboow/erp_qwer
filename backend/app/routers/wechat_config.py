from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
from pydantic import BaseModel
from typing import Optional

from app.database import get_db
from app.models import User
from app.dependencies import get_current_user

router = APIRouter(tags=["企微全局配置"])


class WechatConfigDto(BaseModel):
    host: Optional[str] = ""
    port: Optional[str] = ""
    api_key: Optional[str] = ""
    selected_wxid: Optional[str] = ""
    bound_instance_id: Optional[int] = None
    bound_instance_name: Optional[str] = ""
    ws_path: Optional[str] = "/ws/wechat/messages"
    http_path: Optional[str] = "/api/wechat/callback/http"
    callback_timeout: Optional[int] = 5


def json_response(code=200, message="success", data=None):
    resp = {"code": code, "message": message}
    if data is not None:
        resp["data"] = data
    return resp


def ensure_wechat_config_table(db: Session):
    db.execute(text(
        "CREATE TABLE IF NOT EXISTS wechat_config ("
        "id INT UNSIGNED NOT NULL PRIMARY KEY, "
        "host VARCHAR(255) NOT NULL DEFAULT '', "
        "port VARCHAR(50) NOT NULL DEFAULT '', "
        "api_key VARCHAR(255) NOT NULL DEFAULT '', "
        "selected_wxid VARCHAR(100) NOT NULL DEFAULT '', "
        "bound_instance_id INT NULL, "
        "bound_instance_name VARCHAR(255) NOT NULL DEFAULT '', "
        "ws_path VARCHAR(255) NOT NULL DEFAULT '/ws/wechat/messages', "
        "http_path VARCHAR(255) NOT NULL DEFAULT '/api/wechat/callback/http', "
        "callback_timeout INT NOT NULL DEFAULT 5"
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4"
    ))
    db.execute(text(
        "INSERT IGNORE INTO wechat_config ("
        "id, host, port, api_key, selected_wxid, bound_instance_id, bound_instance_name, ws_path, http_path, callback_timeout"
        ") VALUES ("
        "1, '', '', '', '', NULL, '', '/ws/wechat/messages', '/api/wechat/callback/http', 5"
        ")"
    ))
    db.commit()


@router.get("/config", summary="获取企微全局配置")
async def get_wechat_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_wechat_config_table(db)
    row = db.execute(text("SELECT * FROM wechat_config WHERE id = 1")).mappings().first()
    if not row:
        return json_response(data={
            "host": "", "port": "", "api_key": "", "selected_wxid": "",
            "bound_instance_id": None, "bound_instance_name": "",
            "ws_path": "/ws/wechat/messages", "http_path": "/api/wechat/callback/http",
            "callback_timeout": 5
        })
    return json_response(data=dict(row))


@router.put("/config", summary="保存企微全局配置")
async def save_wechat_config(
    payload: WechatConfigDto,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    ensure_wechat_config_table(db)
    db.execute(text(
        "UPDATE wechat_config SET "
        "host = :host, port = :port, api_key = :api_key, "
        "selected_wxid = :selected_wxid, bound_instance_id = :bound_instance_id, "
        "bound_instance_name = :bound_instance_name, "
        "ws_path = :ws_path, http_path = :http_path, callback_timeout = :callback_timeout "
        "WHERE id = 1"
    ), {
        "host": payload.host or "",
        "port": payload.port or "",
        "api_key": payload.api_key or "",
        "selected_wxid": payload.selected_wxid or "",
        "bound_instance_id": payload.bound_instance_id,
        "bound_instance_name": payload.bound_instance_name or "",
        "ws_path": payload.ws_path or "/ws/wechat/messages",
        "http_path": payload.http_path or "/api/wechat/callback/http",
        "callback_timeout": payload.callback_timeout or 5,
    })
    db.commit()
    return json_response(message="配置已保存")
