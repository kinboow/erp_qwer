"""
统一通知群推送服务
向 room_type='notification' 的群发送各类告警/通知消息
"""
import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal

logger = logging.getLogger(__name__)


async def send_to_notification_groups(
    db: Optional[Session],
    message: str,
    *,
    at_list: Optional[list[str]] = None,
) -> int:
    """向所有通知群发送消息，返回成功发送的群数量"""
    from app.services.wechat_reply import send_room_at

    own_db = False
    if db is None:
        db = SessionLocal()
        own_db = True

    sent = 0
    try:
        rows = db.execute(
            text("SELECT room_id FROM downstream_customer_wechat_rooms WHERE room_type = 'notification'")
        ).mappings().all()
        if not rows:
            logger.debug("[通知群] 无通知群，跳过推送")
            return 0
        for row in rows:
            try:
                await send_room_at(db, row["room_id"], message, at_list=at_list)
                sent += 1
            except Exception as exc:
                logger.warning("[通知群] 推送失败 room=%s: %s", row["room_id"], exc)
    except Exception as exc:
        logger.warning("[通知群] 查询通知群失败: %s", exc)
    finally:
        if own_db:
            db.close()
    return sent
