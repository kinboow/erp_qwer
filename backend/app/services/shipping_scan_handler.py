"""
发货群扫码处理器
监听发货群(room_type='shipping')的图片消息 → 二维码识别 → AI解析发货表格 → 下ERP销售发货单 → 通知群推送结果

流程：
1. 收到发货群图片消息
2. CDN 下载图片
3. pyzbar 识别二维码 → 提取 订单号 + 纸张ID
4. 检查纸张ID是否已使用（去重）
5. AI 视觉智能体解析图片中的表格（款号、颜色、尺码数量）
6. 查 ERP 销售订单详情获取关联信息
7. 创建 ERP 销售发货单
8. 向通知群推送发货结果（成功/失败、全部发货/部分未发货）
9. 标记纸张ID为已使用
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.services.ai_order_parser import AIOrderParserError, ai_order_parser
from app.services.downstream_support import ensure_downstream_support_tables
from app.services.wechat_reply import send_room_at

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------
SHIPPING_SCAN_DEDUP_WINDOW = 15  # 同一条消息防重复窗口（秒）
_processed_scans: dict[int, float] = {}  # msg_log_id → monotonic timestamp

# ---------------------------------------------------------------------------
# AI 提示词：解析发货表格图片
# ---------------------------------------------------------------------------
_SHIPPING_TABLE_PARSE_PROMPT = """\
你是一个发货单表格识别专家。请仔细观察图片中的表格，提取以下信息：

对于表格中的每一行，提取：
- product_no: 款号/货号
- color: 颜色
- sizes: 尺码与数量的对应关系，格式为 {"尺码": 数量}

请以 JSON 格式输出，格式如下：
{
  "items": [
    {
      "product_no": "A1234",
      "color": "黑色",
      "sizes": {"S": 10, "M": 20, "L": 15, "XL": 5}
    }
  ]
}

注意：
1. 只提取表格中有数据的行，跳过空行和合计行
2. 数量为 0 或空的尺码不要输出
3. 款号和颜色要准确识别，不要遗漏
4. 如果有多个颜色的同款号，每个颜色一行
"""


# ---------------------------------------------------------------------------
# 二维码识别（非AI，使用 pyzbar）
# ---------------------------------------------------------------------------
def decode_qr_from_bytes(image_bytes: bytes) -> list[str]:
    """从图片字节解码所有二维码内容，返回解码文本列表"""
    try:
        from PIL import Image
        from pyzbar.pyzbar import decode as pyzbar_decode
    except ImportError as e:
        logger.error("二维码识别依赖未安装: %s (pip install Pillow pyzbar)", e)
        return []

    try:
        img = Image.open(io.BytesIO(image_bytes))
        results = pyzbar_decode(img)
        decoded = []
        for r in results:
            try:
                text_val = r.data.decode("utf-8").strip()
                if text_val:
                    decoded.append(text_val)
            except Exception:
                pass
        return decoded
    except Exception as exc:
        logger.warning("二维码解码失败: %s", exc)
        return []


def parse_qr_content(qr_text: str) -> dict[str, str]:
    """
    解析二维码内容，提取订单号和纸张ID。
    二维码格式：前半部分是订单号，后半部分是纸张ID。
    尝试多种分隔符：| , ; - _ 空格 等。
    """
    if not qr_text:
        return {}

    # 尝试常见分隔符
    for sep in ["|", ",", ";", "\t", " "]:
        if sep in qr_text:
            parts = [p.strip() for p in qr_text.split(sep, 1) if p.strip()]
            if len(parts) == 2:
                return {"order_no": parts[0], "paper_id": parts[1]}

    # 无分隔符：取前半为订单号，后半为纸张ID
    mid = len(qr_text) // 2
    if mid > 0:
        return {"order_no": qr_text[:mid], "paper_id": qr_text[mid:]}

    return {"order_no": qr_text, "paper_id": qr_text}


# ---------------------------------------------------------------------------
# 纸张ID去重检查
# ---------------------------------------------------------------------------
def is_paper_used(db: Session, paper_id: str) -> bool:
    """检查纸张ID是否已使用"""
    ensure_downstream_support_tables(db)
    row = db.execute(
        text("SELECT id FROM shipping_scan_records WHERE paper_id = :pid LIMIT 1"),
        {"pid": paper_id},
    ).first()
    return row is not None


def create_scan_record(db: Session, **kwargs) -> int:
    """创建扫码记录，返回记录ID"""
    ensure_downstream_support_tables(db)
    result = db.execute(
        text(
            "INSERT INTO shipping_scan_records "
            "(order_no, paper_id, qr_content, room_id, room_name, instance_id, sender_id, msg_log_id, scan_status) "
            "VALUES (:order_no, :paper_id, :qr_content, :room_id, :room_name, :instance_id, :sender_id, :msg_log_id, :scan_status)"
        ),
        {
            "order_no": kwargs.get("order_no", ""),
            "paper_id": kwargs.get("paper_id", ""),
            "qr_content": kwargs.get("qr_content", ""),
            "room_id": kwargs.get("room_id", ""),
            "room_name": kwargs.get("room_name", ""),
            "instance_id": kwargs.get("instance_id", ""),
            "sender_id": kwargs.get("sender_id", ""),
            "msg_log_id": kwargs.get("msg_log_id"),
            "scan_status": "pending",
        },
    )
    db.commit()
    return result.lastrowid


def update_scan_record(db: Session, record_id: int, **kwargs):
    """更新扫码记录"""
    sets = []
    params = {"id": record_id}
    for k, v in kwargs.items():
        sets.append(f"{k} = :{k}")
        params[k] = v
    if sets:
        db.execute(text(f"UPDATE shipping_scan_records SET {', '.join(sets)} WHERE id = :id"), params)
        db.commit()


# ---------------------------------------------------------------------------
# 解析企微运行时配置（复用 at_order_handler 模式）
# ---------------------------------------------------------------------------
def _resolve_wechat_runtime(db: Session, instance_id: str) -> dict[str, Any]:
    if instance_id:
        from app.models import WechatInstance
        inst = db.query(WechatInstance).filter(
            (WechatInstance.wxid == instance_id) | (WechatInstance.id == instance_id)
        ).first()
        if inst:
            return {
                "api_base_url": (inst.api_base_url or "").rstrip("/"),
                "api_key": inst.api_key or "",
                "wxid": inst.wxid or "",
            }
    try:
        row = db.execute(text("SELECT host, port, api_key, selected_wxid FROM wechat_config WHERE id = 1")).mappings().first()
    except Exception:
        row = None
    if row:
        host = (row.get("host") or "").strip()
        port = (row.get("port") or "").strip()
        base = ""
        if host:
            base = host if host.startswith(("http://", "https://")) else f"http://{host}"
            if port and port not in ("80", "443"):
                base = f"{base}:{port}"
        return {
            "api_base_url": base.rstrip("/"),
            "api_key": row.get("api_key") or "",
            "wxid": row.get("selected_wxid") or instance_id,
        }
    return {"api_base_url": "", "api_key": "", "wxid": instance_id}


# ---------------------------------------------------------------------------
# CDN 下载图片
# ---------------------------------------------------------------------------
def _extract_cdn_params(payload: dict[str, Any]) -> dict[str, Any]:
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    cdn = data.get("cdn") if isinstance(data.get("cdn"), dict) else {}
    c2c = data.get("c2c_cdn") if isinstance(data.get("c2c_cdn"), dict) else {}

    url = cdn.get("url") or data.get("url") or ""
    auth_key = cdn.get("auth_key") or data.get("auth_key") or ""
    aes_key = cdn.get("aes_key") or c2c.get("aes_key") or data.get("aes_key") or ""
    size = cdn.get("size") or c2c.get("file_size") or c2c.get("size") or data.get("size") or 0
    try:
        size = int(size)
    except (ValueError, TypeError):
        size = 0

    if url and auth_key and aes_key and size:
        return {"mode": "wx_download", "url": url, "auth_key": auth_key, "aes_key": aes_key, "size": size}

    file_id = c2c.get("file_id") or data.get("file_id") or ""
    if file_id and aes_key:
        return {"mode": "c2c_download", "file_id": file_id, "aes_key": aes_key, "file_size": size, "file_type": 2}

    return {}


async def download_image(db: Session, payload: dict[str, Any], instance_id: str, msg_log_id: int) -> Optional[bytes]:
    """从企微CDN下载图片，返回字节"""
    cdn_params = _extract_cdn_params(payload)
    if not cdn_params:
        logger.debug("[发货扫码] 无CDN参数 msg_log_id=%s", msg_log_id)
        return None

    runtime = _resolve_wechat_runtime(db, instance_id)
    if not runtime.get("api_base_url") or not runtime.get("wxid"):
        logger.warning("[发货扫码] 缺少运行时配置")
        return None

    download_dir = Path(__file__).resolve().parents[2] / "temp" / "shipping_scan"
    download_dir.mkdir(parents=True, exist_ok=True)
    save_path = download_dir / f"scan_{msg_log_id}.png"

    mode = cdn_params.pop("mode")
    api_route = f"cdn/{mode}"
    cdn_params["save_path"] = str(save_path)

    headers: dict[str, str] = {}
    if runtime.get("api_key"):
        headers["X-API-Key"] = runtime["api_key"]

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{runtime['api_base_url']}/api/{runtime['wxid']}/{api_route}",
                json=cdn_params,
                headers=headers,
            )
            resp.raise_for_status()
            resp_data = resp.json()

        if isinstance(resp_data, dict) and resp_data.get("code") not in (0, None):
            logger.warning("[发货扫码] CDN返回错误: %s", resp_data.get("msg"))
            return None

        if not save_path.is_file():
            data_body = resp_data.get("data") if isinstance(resp_data.get("data"), dict) else {}
            for key in ("save_path", "path", "file_path"):
                possible = str(data_body.get(key) or "").strip()
                if possible and Path(possible).is_file():
                    save_path = Path(possible)
                    break

        if not save_path.is_file():
            logger.warning("[发货扫码] 文件未出现 msg_log_id=%s", msg_log_id)
            return None

        return save_path.read_bytes()
    except Exception as exc:
        logger.warning("[发货扫码] 下载失败 msg_log_id=%s: %s", msg_log_id, exc)
        return None


# ---------------------------------------------------------------------------
# AI 视觉解析发货表格
# ---------------------------------------------------------------------------
async def ai_parse_shipping_table(image_bytes: bytes, db: Session) -> dict[str, Any]:
    """调用AI视觉模型解析发货表格图片，返回解析结果"""
    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    cfg = ai_order_parser._load_config(db)
    vision_model = cfg.get("vision_model") or cfg.get("model") or "qwen-vl-max"

    # 构建 vision messages
    image_content: dict[str, Any]
    if ai_order_parser.supports_oss_upload(db):
        try:
            fname = f"shipping_scan_{int(time.time())}.png"
            oss_url = await ai_order_parser.upload_file(image_bytes, fname, vision_model, db=db)
            image_content = {"type": "image_url", "image_url": {"url": oss_url}}
        except Exception:
            image_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
    else:
        image_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}

    messages = [
        {"role": "system", "content": _SHIPPING_TABLE_PARSE_PROMPT},
        {"role": "user", "content": [
            image_content,
            {"type": "text", "text": "请识别这张发货单图片中的表格信息，提取款号、颜色、各尺码对应数量。"},
        ]},
    ]

    result = await ai_order_parser._chat(vision_model, messages, db=db, caller="shipping_table_parse")
    text_content = ""
    choices = result.get("choices") or []
    if choices:
        msg = choices[0].get("message") or {}
        text_content = msg.get("content") or ""
        # 深度思考模型可能包含 reasoning_content
        if not text_content:
            text_content = msg.get("reasoning_content") or ""

    if not text_content:
        raise AIOrderParserError("AI视觉模型未返回有效内容")

    return ai_order_parser._extract_json(text_content)


# ---------------------------------------------------------------------------
# 查询 ERP 销售订单详情
# ---------------------------------------------------------------------------
async def get_erp_order_detail(order_no: str) -> dict[str, Any]:
    """获取ERP销售订单详情"""
    from app.services.erp_bridge import ERPBridge
    bridge = ERPBridge()
    client = await bridge._ensure_login()
    from app.ncloud.services.sales_orders import get_order_detail
    detail = await get_order_detail(client, order_no)
    return detail.model_dump()


# ---------------------------------------------------------------------------
# 创建 ERP 销售发货单
# ---------------------------------------------------------------------------
async def create_erp_shipment(
    order_detail: dict[str, Any],
    parsed_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """根据订单详情和AI解析的发货内容创建销售发货单"""
    from app.ncloud.schemas.shipments import CreateShipmentRequest, CreateShipmentDetailRow
    from app.ncloud.schemas.sales_orders import SizeQty
    from app.ncloud.services.shipments import create_shipment, audit_shipment
    from app.ncloud.schemas.sales_orders import AuditAction
    from app.services.erp_bridge import ERPBridge

    bridge = ERPBridge()
    client = await bridge._ensure_login()

    main = order_detail.get("main") or {}
    order_detail_rows = order_detail.get("detail") or []

    # 构建发货明细行：匹配AI解析的内容与订单行
    shipment_rows = []
    for item in parsed_items:
        product_no = item.get("product_no", "")
        color = item.get("color", "")
        sizes_dict = item.get("sizes") or {}

        # 在订单明细中查找匹配行，获取 erp_item_id（ddid）
        matched_order_row = None
        for orow in order_detail_rows:
            if (orow.get("product_no") or "") == product_no and (orow.get("color") or "") == color:
                matched_order_row = orow
                break
        # 如果精确匹配失败，仅用款号匹配
        if not matched_order_row:
            for orow in order_detail_rows:
                if (orow.get("product_no") or "") == product_no:
                    matched_order_row = orow
                    break

        size_qty_list = [SizeQty(size=str(s), qty=int(q)) for s, q in sizes_dict.items() if int(q or 0) > 0]
        if not size_qty_list:
            continue

        shipment_rows.append(CreateShipmentDetailRow(
            product_no=product_no,
            color=color,
            sizes=size_qty_list,
            order_ref_id=matched_order_row.get("erp_item_id", "") if matched_order_row else "",
            brand=matched_order_row.get("brand", "") if matched_order_row else "",
            unit=matched_order_row.get("unit", "") if matched_order_row else "",
            price=matched_order_row.get("price", 0) if matched_order_row else 0,
            discount=matched_order_row.get("discount", 100) if matched_order_row else 100,
        ))

    if not shipment_rows:
        raise ValueError("AI解析结果与订单明细无匹配项，无法创建发货单")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    req = CreateShipmentRequest(
        customer_id=main.get("customer_id", ""),
        shipment_date=now,
        warehouse=main.get("warehouse") or "成品仓",
        customer_addr=main.get("customer_addr", ""),
        shipping_addr=main.get("shipping_addr", ""),
        shipping_tel=main.get("shipping_tel", ""),
        shipping_method=main.get("shipping_method", ""),
        salesperson=main.get("salesperson", ""),
        contact_person=main.get("contact_person", ""),
        contact_tel=main.get("contact_tel", ""),
        remark=f"发货扫码自动创建 关联订单:{main.get('order_no', '')}",
        detail=shipment_rows,
    )

    result = await create_shipment(client, req)
    shipment_no = result.dh or ""

    # 创建后自动审核
    if shipment_no:
        try:
            await audit_shipment(client, shipment_no, AuditAction.audit)
        except Exception as exc:
            logger.warning("[发货扫码] 发货单 %s 自动审核失败: %s", shipment_no, exc)

    return {"shipment_no": shipment_no, "message": result.message}


# ---------------------------------------------------------------------------
# 计算发货状态（全部发货 / 部分发货）
# ---------------------------------------------------------------------------
def calc_shipping_status(
    order_detail: dict[str, Any],
    parsed_items: list[dict[str, Any]],
) -> dict[str, Any]:
    """比较订单明细与本次发货数量，判断是全部发货还是部分发货"""
    # 订单总数
    order_qty_map: dict[str, int] = {}  # "款号|颜色|尺码" → 数量
    for row in (order_detail.get("detail") or []):
        pno = row.get("product_no", "")
        color = row.get("color", "")
        for sq in (row.get("sizes") or []):
            key = f"{pno}|{color}|{sq.get('size', '')}"
            order_qty_map[key] = order_qty_map.get(key, 0) + int(sq.get("qty", 0))

    # 本次发货数
    shipped_qty_map: dict[str, int] = {}
    for item in parsed_items:
        pno = item.get("product_no", "")
        color = item.get("color", "")
        for size, qty in (item.get("sizes") or {}).items():
            key = f"{pno}|{color}|{size}"
            shipped_qty_map[key] = shipped_qty_map.get(key, 0) + int(qty or 0)

    total_ordered = sum(order_qty_map.values())
    total_shipped = sum(shipped_qty_map.values())

    # 未发货明细
    unshipped = {}
    for key, ordered in order_qty_map.items():
        shipped = shipped_qty_map.get(key, 0)
        if shipped < ordered:
            unshipped[key] = ordered - shipped

    is_full = total_shipped >= total_ordered and not unshipped
    return {
        "is_full": is_full,
        "total_ordered": total_ordered,
        "total_shipped": total_shipped,
        "unshipped": unshipped,
    }


# ---------------------------------------------------------------------------
# 通知群推送
# ---------------------------------------------------------------------------
async def send_notification_to_groups(
    db: Session,
    order_no: str,
    shipment_no: str,
    success: bool,
    shipping_status: dict[str, Any],
    error_msg: str = "",
):
    """向所有通知群推送发货结果"""
    # 查找所有通知群
    try:
        rows = db.execute(
            text("SELECT room_id FROM downstream_customer_wechat_rooms WHERE room_type = 'notification'")
        ).mappings().all()
    except Exception:
        rows = []

    if not rows:
        logger.info("[发货扫码] 无通知群，跳过推送")
        return

    if success:
        status = shipping_status or {}
        if status.get("is_full"):
            msg = f"📦 订单 {order_no} 发货成功！\n发货单号：{shipment_no}\n发货状态：全部发货（共{status.get('total_shipped', 0)}件）"
        else:
            unshipped = status.get("unshipped") or {}
            unshipped_lines = []
            for key, qty in unshipped.items():
                parts = key.split("|")
                if len(parts) == 3:
                    unshipped_lines.append(f"  {parts[0]} {parts[1]} {parts[2]}: 剩余{qty}件")
            unshipped_text = "\n".join(unshipped_lines[:10]) if unshipped_lines else "详见ERP系统"
            msg = (
                f"📦 订单 {order_no} 发货成功！\n"
                f"发货单号：{shipment_no}\n"
                f"发货状态：部分发货（本次{status.get('total_shipped', 0)}件 / 订单共{status.get('total_ordered', 0)}件）\n"
                f"未发货明细：\n{unshipped_text}"
            )
    else:
        msg = f"❌ 订单 {order_no} 发货失败！\n原因：{error_msg or '未知错误'}"

    for row in rows:
        room_id = row["room_id"]
        try:
            await send_room_at(db, room_id, msg)
        except Exception as exc:
            logger.warning("[发货扫码] 通知群推送失败 room=%s: %s", room_id, exc)


# ---------------------------------------------------------------------------
# 判断群是否为发货群
# ---------------------------------------------------------------------------
def resolve_shipping_room(db: Session, room_id: str) -> Optional[dict[str, str]]:
    """检查 room_id 是否为发货群，返回群信息或 None"""
    if not room_id:
        return None
    try:
        row = db.execute(
            text(
                "SELECT room_id, room_name FROM downstream_customer_wechat_rooms "
                "WHERE room_id = :rid AND room_type = 'shipping' LIMIT 1"
            ),
            {"rid": room_id},
        ).mappings().first()
        if row:
            return {"room_id": row["room_id"], "room_name": row["room_name"] or ""}
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# 主入口：处理发货群图片消息
# ---------------------------------------------------------------------------
async def handle_shipping_scan(
    room_id: str,
    sender_id: str,
    msg_log_id: int,
    instance_id: str = "",
    payload: dict[str, Any] | None = None,
) -> None:
    """发货群图片消息 → 二维码识别 → AI解析 → 下发货单 → 通知"""
    if not payload:
        return

    # 防重复
    now = time.monotonic()
    if msg_log_id in _processed_scans:
        if now - _processed_scans[msg_log_id] < SHIPPING_SCAN_DEDUP_WINDOW:
            return
    _processed_scans[msg_log_id] = now
    # 清理过期记录
    cutoff = now - 300
    for k in [k for k, v in _processed_scans.items() if v < cutoff]:
        _processed_scans.pop(k, None)

    record_id = None
    try:
        logger.info("[发货扫码] 收到图片 room=%s sender=%s log_id=%d", room_id, sender_id, msg_log_id)

        # 1. 下载图片
        db = SessionLocal()
        try:
            image_bytes = await download_image(db, payload, instance_id, msg_log_id)
        finally:
            db.close()

        if not image_bytes:
            logger.info("[发货扫码] 图片下载失败，跳过 log_id=%d", msg_log_id)
            return

        # 2. 二维码识别（非AI）
        qr_texts = decode_qr_from_bytes(image_bytes)
        if not qr_texts:
            logger.info("[发货扫码] 未识别到二维码，跳过 log_id=%d", msg_log_id)
            return

        qr_text = qr_texts[0]  # 取第一个二维码
        qr_info = parse_qr_content(qr_text)
        order_no = qr_info.get("order_no", "")
        paper_id = qr_info.get("paper_id", "")

        if not order_no or not paper_id:
            logger.warning("[发货扫码] 二维码内容格式异常: %s", qr_text)
            return

        logger.info("[发货扫码] 二维码识别成功 order=%s paper=%s", order_no, paper_id)

        # 3. 检查纸张ID去重
        db = SessionLocal()
        try:
            if is_paper_used(db, paper_id):
                logger.info("[发货扫码] 纸张ID已使用，跳过 paper=%s", paper_id)
                return

            # 创建扫码记录
            room_info = resolve_shipping_room(db, room_id) or {}
            record_id = create_scan_record(
                db,
                order_no=order_no,
                paper_id=paper_id,
                qr_content=qr_text,
                room_id=room_id,
                room_name=room_info.get("room_name", ""),
                instance_id=instance_id,
                sender_id=sender_id,
                msg_log_id=msg_log_id,
            )
        finally:
            db.close()

        logger.info("[发货扫码] 创建扫码记录 id=%d order=%s paper=%s", record_id, order_no, paper_id)

        # 4. AI 视觉解析发货表格
        db = SessionLocal()
        try:
            update_scan_record(db, record_id, scan_status="parsing")
            parsed = await ai_parse_shipping_table(image_bytes, db)
            parsed_items = parsed.get("items") or []
            update_scan_record(db, record_id, ai_parsed_json=json.dumps(parsed, ensure_ascii=False))
        except Exception as exc:
            update_scan_record(db, record_id, scan_status="failed", error_message=f"AI解析失败: {exc}")
            logger.error("[发货扫码] AI解析失败 record=%d: %s", record_id, exc)
            # 通知群推送失败
            await send_notification_to_groups(db, order_no, "", False, {}, f"AI解析失败: {exc}")
            return
        finally:
            db.close()

        if not parsed_items:
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message="AI未识别到有效发货内容")
                await send_notification_to_groups(db, order_no, "", False, {}, "AI未识别到有效发货内容")
            finally:
                db.close()
            return

        logger.info("[发货扫码] AI解析成功 record=%d items=%d", record_id, len(parsed_items))

        # 5. 获取ERP销售订单详情
        try:
            order_detail = await get_erp_order_detail(order_no)
        except Exception as exc:
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message=f"查询订单失败: {exc}")
                await send_notification_to_groups(db, order_no, "", False, {}, f"查询订单 {order_no} 失败: {exc}")
            finally:
                db.close()
            return

        # 6. 创建销售发货单
        try:
            shipment_result = await create_erp_shipment(order_detail, parsed_items)
            shipment_no = shipment_result.get("shipment_no", "")
        except Exception as exc:
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message=f"创建发货单失败: {exc}")
                await send_notification_to_groups(db, order_no, "", False, {}, f"创建发货单失败: {exc}")
            finally:
                db.close()
            return

        # 7. 计算发货状态
        shipping_status = calc_shipping_status(order_detail, parsed_items)

        # 8. 更新记录 + 通知
        db = SessionLocal()
        try:
            update_scan_record(
                db, record_id,
                scan_status="success",
                shipment_no=shipment_no,
                shipment_result=json.dumps(shipping_status, ensure_ascii=False),
            )
            await send_notification_to_groups(db, order_no, shipment_no, True, shipping_status)
            update_scan_record(db, record_id, notification_sent=1)
        finally:
            db.close()

        logger.info("[发货扫码] 完成 record=%d shipment=%s full=%s",
                     record_id, shipment_no, shipping_status.get("is_full"))

    except Exception as exc:
        logger.exception("[发货扫码] 未知错误 room=%s log_id=%d: %s", room_id, msg_log_id, exc)
        if record_id:
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message=str(exc))
            finally:
                db.close()
