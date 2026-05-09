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
import re
import shutil
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import settings
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
_wechat_qr_detector = None
_QR_TEXT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{3,}\|[A-Fa-f0-9]{8,64}$")

# ---------------------------------------------------------------------------
# AI 提示词：解析发货表格图片
# ---------------------------------------------------------------------------
_SHIPPING_TABLE_PARSE_PROMPT = """\
你是一个拣货单/发货单表格识别专家。

## 图片识别注意
如果图片中有纸张背面透过来的文字（颜色较浅、方向相反、镜像或模糊的印刷/手写痕迹），请完全忽略这些背面透字，只识别纸张正面清晰可见的内容。

## 任务
仅识别图片中**表格区域**的内容。表格外的任何内容（标题、二维码、客户信息、备注、页脚、背面透字）一律忽略。

## 表格结构
表格列从左到右依次为：款号、颜色，然后是多个尺码列（如 S、M、L、XL、2XL、3XL、4XL 等）。
每个尺码列可能有两个子列（白色底和灰色底）。**只读取白色底（浅色底）子列中的数字作为数量，灰色底的列完全忽略。**
如果尺码列没有分子列，直接读取该格数字。

## 提取规则
对于表格中每一行数据，提取：
- product_no: 款号/货号（如有多行属于同一款号，每行分别输出）
- color: 颜色名称
- sizes: 仅白色底列的 {尺码: 数量} 键值对

## 跳过规则
- 跳过合计行、汇总行、小计行
- 数量为 0 或空白的尺码不输出
- 整行数量全为 0 的行跳过

## 输出格式（严格 JSON）
{
  "items": [
    {
      "product_no": "A1234",
      "color": "黑色",
      "sizes": {"S": 10, "M": 20, "L": 15}
    }
  ]
}
"""

_SHIPPING_CODE_FALLBACK_PROMPT = """\
你是发货单右上角识别智能体。

任务：识别图片右上角方块码下方印刷的那一行内容。
这行文字通常就是：订单号|纸张ID。

要求：
1. 只关注右上角图像码下方那一行文字
2. 忽略表格、备注、客户信息和其他区域
3. 如果无法确认，返回空字符串，不要猜
4. 严格只返回 JSON

输出格式：
{
  "combined_text": "20260506-033|8d9a3a83cc034f12",
  "order_no": "20260506-033",
  "paper_id": "8d9a3a83cc034f12",
  "confidence": "high|medium|low",
  "reason": "简短说明"
}
"""


# ---------------------------------------------------------------------------
# 码识别 — pyzbar 为主引擎（同时支持 Code128 条形码 + QR 码），微信 WeChatQRCode 兆底（仅QR）
# ---------------------------------------------------------------------------
def _normalize_qr_text(value: str) -> str:
    return str(value or "").replace("\n", "").replace("\r", "").strip()


def _is_valid_qr_text(value: str) -> bool:
    text_val = _normalize_qr_text(value)
    if not text_val:
        return False
    return bool(_QR_TEXT_RE.match(text_val))


def _dedupe_texts(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        text_val = _normalize_qr_text(v)
        if text_val and text_val not in seen and _is_valid_qr_text(text_val):
            seen.add(text_val)
            result.append(text_val)
    return result


def _dedupe_texts_raw(values: list[str]) -> list[str]:
    """去重但不做格式校验，保留所有非空二维码文本。"""
    seen: set[str] = set()
    result: list[str] = []
    for v in values:
        text_val = _normalize_qr_text(v)
        if text_val and text_val not in seen:
            seen.add(text_val)
            result.append(text_val)
    return result


def _resolve_wechat_qr_model_paths() -> tuple[str, str, str, str] | None:
    """查找微信 QR 模型文件（detect.prototxt / detect.caffemodel / sr.prototxt / sr.caffemodel）。"""
    explicit = (
        (settings.WECHAT_QR_DETECT_PROTO_PATH or "").strip(),
        (settings.WECHAT_QR_DETECT_MODEL_PATH or "").strip(),
        (settings.WECHAT_QR_SUPER_RES_PROTO_PATH or "").strip(),
        (settings.WECHAT_QR_SUPER_RES_MODEL_PATH or "").strip(),
    )
    if all(explicit):
        if all(Path(p).is_file() for p in explicit):
            return explicit
        logger.warning("WeChatQRCode 模型路径已配置，但文件不存在: %s", explicit)

    candidate_dirs = [
        Path(__file__).resolve().parents[2] / "models" / "wechat_qrcode",
        Path(__file__).resolve().parents[2] / "resources" / "wechat_qrcode",
        Path(__file__).resolve().parents[2] / "assets" / "wechat_qrcode",
        Path(__file__).resolve().parents[1] / "models" / "wechat_qrcode",
    ]
    for base_dir in candidate_dirs:
        detect_proto = base_dir / "detect.prototxt"
        detect_model = base_dir / "detect.caffemodel"
        sr_proto = base_dir / "sr.prototxt"
        sr_model = base_dir / "sr.caffemodel"
        if detect_proto.is_file() and detect_model.is_file() and sr_proto.is_file() and sr_model.is_file():
            return (str(detect_proto), str(detect_model), str(sr_proto), str(sr_model))
    return None


def _stage_wechat_qr_model_paths(model_paths: tuple[str, str, str, str]) -> tuple[str, str, str, str]:
    """将模型文件复制到纯 ASCII 临时目录（OpenCV 不支持中文路径）。"""
    names = ("detect.prototxt", "detect.caffemodel", "sr.prototxt", "sr.caffemodel")
    staged_dir = Path(tempfile.gettempdir()) / "erp_wechat_qrcode_models"
    staged_dir.mkdir(parents=True, exist_ok=True)
    staged_paths: list[str] = []
    for src, name in zip(model_paths, names):
        src_path = Path(src)
        dst_path = staged_dir / name
        if (not dst_path.exists()) or src_path.stat().st_mtime > dst_path.stat().st_mtime or src_path.stat().st_size != dst_path.stat().st_size:
            shutil.copyfile(src_path, dst_path)
        staged_paths.append(str(dst_path))
    return tuple(staged_paths)  # type: ignore[return-value]


def _get_wechat_qr_detector():
    """获取 WeChatQRCode 单例检测器（带模型文件自动加载）。"""
    global _wechat_qr_detector
    if _wechat_qr_detector is None:
        import cv2
        model_paths = _resolve_wechat_qr_model_paths()
        if model_paths:
            staged = _stage_wechat_qr_model_paths(model_paths)
            logger.info("WeChatQRCode 加载模型: %s", staged)
            _wechat_qr_detector = cv2.wechat_qrcode_WeChatQRCode(*staged)
        else:
            logger.warning("WeChatQRCode 无模型文件，回退为无参初始化；建议将 detect/sr 模型放到 backend/models/wechat_qrcode")
            _wechat_qr_detector = cv2.wechat_qrcode_WeChatQRCode()
    return _wechat_qr_detector


def _wechat_qr_decode(bgr_img) -> list[str]:
    """微信 QR 检测 + 解码（主引擎），返回经格式校验的文本列表。"""
    detector = _get_wechat_qr_detector()
    decoded_info, _ = detector.detectAndDecode(bgr_img)
    if not decoded_info:
        return []
    return _dedupe_texts([str(s).strip() for s in decoded_info if str(s).strip()])


def _wechat_qr_decode_raw(bgr_img) -> list[str]:
    """微信 QR 检测 + 解码，返回所有原始文本（不做格式校验）。"""
    detector = _get_wechat_qr_detector()
    decoded_info, _ = detector.detectAndDecode(bgr_img)
    if not decoded_info:
        return []
    return _dedupe_texts_raw([str(s).strip() for s in decoded_info if str(s).strip()])


def _pyzbar_decode(img_array) -> list[str]:
    """pyzbar 解码（兜底引擎）。"""
    from pyzbar.pyzbar import decode as pyzbar_decode
    from PIL import Image as PILImage
    pil = PILImage.fromarray(img_array) if not isinstance(img_array, PILImage.Image) else img_array
    results = pyzbar_decode(pil)
    return _dedupe_texts([r.data.decode("utf-8").strip() for r in results if r.data])


def _pyzbar_decode_raw(img_array) -> list[str]:
    """pyzbar 解码，返回所有原始文本（不做格式校验）。"""
    from pyzbar.pyzbar import decode as pyzbar_decode
    from PIL import Image as PILImage
    pil = PILImage.fromarray(img_array) if not isinstance(img_array, PILImage.Image) else img_array
    results = pyzbar_decode(pil)
    return _dedupe_texts_raw([r.data.decode("utf-8").strip() for r in results if r.data])


def decode_qr_from_bytes(image_bytes: bytes) -> list[str]:
    """从图片字节解码条形码/二维码，返回经发货单格式校验的文本列表。

    支持 Code128 条形码（新版打印）和 QR 码（旧版打印）。
    策略（三层，任一层成功即返回）：
    1. 全图 pyzbar（条形码+QR）→ WeChatQRCode（QR兆底）
    2. CLAHE 增强后重试
    3. 四角裁切 + 放大（应对码在图片角落且较小的情况）
    """
    import cv2
    import numpy as np

    started_at = time.perf_counter()
    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    cv_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if cv_img is None:
        logger.warning("码识别: 无法解码图片字节")
        return []
    h, w = cv_img.shape[:2]
    rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
    logger.info("码识别: 图片尺寸 %dx%d (%d bytes)", w, h, len(image_bytes))

    # --- 第1层：全图直接识别 ---
    for engine_name, fn in [
        ("pyzbar", lambda: _pyzbar_decode(rgb)),
        ("wechat_qrcode", lambda: _wechat_qr_decode(cv_img)),
    ]:
        try:
            res = fn()
            if res:
                logger.info("码识别: 全图 %s 识别成功 → %s (%.3fs)", engine_name, res, time.perf_counter() - started_at)
                return res
        except Exception as exc:
            logger.debug("码识别: 全图 %s 异常: %s", engine_name, exc)

    # --- 第2层：CLAHE 增强后重试 ---
    gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(gray)
    clahe_bgr = cv2.cvtColor(clahe, cv2.COLOR_GRAY2BGR)
    for engine_name, fn in [
        ("pyzbar", lambda: _pyzbar_decode(clahe)),
        ("wechat_qrcode", lambda: _wechat_qr_decode(clahe_bgr)),
    ]:
        try:
            res = fn()
            if res:
                logger.info("码识别: CLAHE %s 识别成功 → %s (%.3fs)", engine_name, res, time.perf_counter() - started_at)
                return res
        except Exception as exc:
            logger.debug("码识别: CLAHE %s 异常: %s", engine_name, exc)

    # --- 第3层：四角裁切 + 放大（码在角落且较小时）---
    crop_ratio_w, crop_ratio_h = 0.45, 0.45
    crop_w, crop_h = max(int(w * crop_ratio_w), 200), max(int(h * crop_ratio_h), 200)
    corners = [
        ("右下", max(0, w - crop_w), max(0, h - crop_h), w, h),
        ("右上", max(0, w - crop_w), 0, w, min(h, crop_h)),
        ("左下", 0, max(0, h - crop_h), min(w, crop_w), h),
        ("左上", 0, 0, min(w, crop_w), min(h, crop_h)),
    ]
    for corner_name, x1, y1, x2, y2 in corners:
        crop = cv_img[y1:y2, x1:x2]
        if crop.size == 0:
            continue
        scaled = cv2.resize(crop, (crop.shape[1] * 2, crop.shape[0] * 2), interpolation=cv2.INTER_LANCZOS4)
        crop_rgb = cv2.cvtColor(scaled, cv2.COLOR_BGR2RGB)
        # pyzbar 优先（支持条形码+QR）
        try:
            res = _pyzbar_decode(crop_rgb)
            if res:
                logger.info("码识别: 角落[%s]pyzbar 识别成功 → %s (%.3fs)", corner_name, res, time.perf_counter() - started_at)
                return res
        except Exception as exc:
            logger.debug("码识别: 角落[%s]pyzbar 异常: %s", corner_name, exc)
        # WeChatQRCode 兆底（仅QR）
        try:
            res = _wechat_qr_decode(scaled)
            if res:
                logger.info("码识别: 角落[%s]wechat 识别成功 → %s (%.3fs)", corner_name, res, time.perf_counter() - started_at)
                return res
        except Exception as exc:
            logger.debug("码识别: 角落[%s]wechat 异常: %s", corner_name, exc)
        # CLAHE 增强裁切区域
        crop_gray = cv2.cvtColor(scaled, cv2.COLOR_BGR2GRAY)
        crop_clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(crop_gray)
        try:
            res = _pyzbar_decode(crop_clahe)
            if res:
                logger.info("码识别: 角落[%s]CLAHE+pyzbar 识别成功 → %s (%.3fs)", corner_name, res, time.perf_counter() - started_at)
                return res
        except Exception as exc:
            logger.debug("码识别: 角落[%s]CLAHE+pyzbar 异常: %s", corner_name, exc)

    logger.warning("码识别: 所有引擎均未识别到，耗时 %.3fs", time.perf_counter() - started_at)
    return []


def decode_qr_from_bytes_raw(image_bytes: bytes) -> list[str]:
    """快速全图扫描，返回所有条形码/二维码原始文本（不做发货单格式校验）。"""
    import cv2
    import numpy as np

    arr = np.frombuffer(image_bytes, dtype=np.uint8)
    cv_img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if cv_img is None:
        return []

    # pyzbar 主引擎（同时支持条形码和QR码）
    try:
        rgb = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        res = _pyzbar_decode_raw(rgb)
        if res:
            return res
    except Exception:
        pass

    # 微信 QR 兜底（仅QR码）
    try:
        res = _wechat_qr_decode_raw(cv_img)
        if res:
            return res
    except Exception:
        pass

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
    """检查纸张ID是否已被识别过（非 failed 状态的记录都视为已使用，不允许重复识别）"""
    ensure_downstream_support_tables(db)
    row = db.execute(
        text(
            "SELECT id FROM shipping_scan_records "
            "WHERE paper_id = :pid AND scan_status NOT IN ('failed') "
            "LIMIT 1"
        ),
        {"pid": paper_id},
    ).first()
    return row is not None


def create_scan_record(db: Session, **kwargs) -> int:
    """创建扫码记录，返回记录ID"""
    ensure_downstream_support_tables(db)
    result = db.execute(
        text(
            "INSERT INTO shipping_scan_records "
            "(order_no, paper_id, qr_content, code_source, room_id, room_name, instance_id, sender_id, msg_log_id, scan_status) "
            "VALUES (:order_no, :paper_id, :qr_content, :code_source, :room_id, :room_name, :instance_id, :sender_id, :msg_log_id, :scan_status)"
        ),
        {
            "order_no": kwargs.get("order_no", ""),
            "paper_id": kwargs.get("paper_id", ""),
            "qr_content": kwargs.get("qr_content", ""),
            "code_source": kwargs.get("code_source", ""),
            "room_id": kwargs.get("room_id", ""),
            "room_name": kwargs.get("room_name", ""),
            "instance_id": kwargs.get("instance_id", ""),
            "sender_id": kwargs.get("sender_id", ""),
            "msg_log_id": kwargs.get("msg_log_id"),
            "scan_status": "pending",
        },
    )
    db.commit()
    record_id = result.lastrowid
    _notify_scan_change("scan_created", record_id)
    return record_id


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
        _notify_scan_change("scan_updated", record_id, scan_status=kwargs.get("scan_status"))


def _notify_scan_change(event_type: str, record_id: int, scan_status: str | None = None):
    """通知前端发货扫码记录变动（SSE）"""
    try:
        from app.services.shipping_scan_events import notify_scan_record_change
        notify_scan_record_change(event_type, {"record_id": record_id, "scan_status": scan_status})
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 启动时恢复卡住的扫码记录
# ---------------------------------------------------------------------------
async def recover_stuck_scan_records() -> None:
    """
    启动时恢复卡在 pending/parsing 状态的扫码记录（程序异常退出导致）。
    - 无 ai_parsed_json → 标记 failed，允许 rescan_unrecognized_messages 重新触发。
    - 有 ai_parsed_json → 查 ERP 发货单是否已创建，有则 success，无则 review_pending。
    """
    from datetime import timedelta

    db = SessionLocal()
    try:
        ensure_downstream_support_tables(db)
        from app.services.erp_sync import ensure_tables as ensure_erp_tables
        ensure_erp_tables(db)

        stuck_rows = db.execute(
            text(
                "SELECT id, order_no, paper_id, ai_parsed_json, scan_status, notification_sent "
                "FROM shipping_scan_records "
                "WHERE scan_status IN ('pending', 'parsing') "
                "ORDER BY id ASC"
            )
        ).mappings().all()

        if not stuck_rows:
            logger.info("[启动恢复] 无卡住的发货扫码记录")
            return

        logger.info("[启动恢复] 发现 %d 条卡住的发货扫码记录", len(stuck_rows))

        for row in stuck_rows:
            record_id = row["id"]
            order_no = str(row.get("order_no") or "").strip()
            ai_parsed = str(row.get("ai_parsed_json") or "").strip()

            # --- AI 未完成 → 标记失败（rescan 机制会重新下载图片触发识别）---
            if not ai_parsed or ai_parsed in ("null", "{}", "[]"):
                update_scan_record(
                    db, record_id,
                    scan_status="failed",
                    error_message="程序异常中断，AI识别未完成，请重新扫描",
                )
                logger.info("[启动恢复] record=%d AI未完成 → failed (允许重扫)", record_id)
                continue

            # --- AI 已完成，检查 ERP 是否已有匹配的发货单 ---
            # 1) 先查本地 erp_sales_shipments（remark 包含关联订单号）
            shipment_no = _find_shipment_in_local_db(db, order_no) if order_no else None
            if shipment_no:
                update_scan_record(
                    db, record_id,
                    scan_status="success",
                    shipment_no=shipment_no,
                    error_message="",
                )
                await _notify_recovered_scan_success(
                    db,
                    record_id=record_id,
                    order_no=order_no,
                    shipment_no=shipment_no,
                    ai_parsed=ai_parsed,
                    notification_sent=row.get("notification_sent"),
                )
                logger.info("[启动恢复] record=%d 本地找到发货单 %s → success", record_id, shipment_no)
                continue

            # 2) 本地未找到 → 尝试 ERP API
            if order_no:
                try:
                    shipment_no = await _find_shipment_from_erp_api(order_no)
                except Exception as exc:
                    logger.warning("[启动恢复] record=%d ERP API 查询失败: %s", record_id, exc)
                    shipment_no = None

                if shipment_no:
                    update_scan_record(
                        db, record_id,
                        scan_status="success",
                        shipment_no=shipment_no,
                        error_message="",
                    )
                    await _notify_recovered_scan_success(
                        db,
                        record_id=record_id,
                        order_no=order_no,
                        shipment_no=shipment_no,
                        ai_parsed=ai_parsed,
                        notification_sent=row.get("notification_sent"),
                    )
                    logger.info("[启动恢复] record=%d ERP API 找到发货单 %s → success", record_id, shipment_no)
                    continue

            # 3) 未找到匹配 → 进入人工审核（AI 结果已保存，可在前端查看）
            update_scan_record(
                db, record_id,
                scan_status="review_pending",
                error_message="程序异常中断，AI已识别但发货单创建状态不确定，需人工审核",
            )
            logger.info("[启动恢复] record=%d → review_pending (人工审核)", record_id)

    except Exception as exc:
        logger.exception("[启动恢复] 发货扫码记录恢复异常: %s", exc)
    finally:
        db.close()


async def _notify_recovered_scan_success(
    db: Session,
    record_id: int,
    order_no: str,
    shipment_no: str,
    ai_parsed: str,
    notification_sent: Any = 0,
) -> None:
    if not shipment_no or int(notification_sent or 0) == 1:
        return

    shipping_status = None
    try:
        parsed = json.loads(ai_parsed or "{}")
        parsed_items = (parsed or {}).get("items") or []
        if order_no and parsed_items:
            order_detail = await get_erp_order_detail(order_no)
            shipping_status = calc_shipping_status(order_detail, parsed_items)
    except Exception as exc:
        logger.warning("[启动恢复] record=%d 计算发货状态失败，改为发送简版成功通知: %s", record_id, exc)

    try:
        if shipping_status:
            await send_notification_to_groups(db, order_no, shipment_no, True, shipping_status)
        else:
            from app.services.notify_group import send_to_notification_groups
            await send_to_notification_groups(db, f"📦 订单 {order_no or '-'} 发货成功！\n发货单号：{shipment_no}")
        update_scan_record(db, record_id, notification_sent=1)
    except Exception as exc:
        logger.warning("[启动恢复] record=%d 补发通知群成功消息失败: %s", record_id, exc)


def _find_shipment_in_local_db(db: Session, sales_order_no: str) -> str | None:
    """在本地 erp_sales_shipments 表中查找由发货扫码自动创建的发货单"""
    if not sales_order_no:
        return None
    row = db.execute(
        text(
            "SELECT order_no FROM erp_sales_shipments "
            "WHERE remark LIKE :pattern "
            "ORDER BY id DESC LIMIT 1"
        ),
        {"pattern": f"%发货扫码自动创建 关联订单:{sales_order_no}%"},
    ).mappings().first()
    return row["order_no"] if row else None


async def _find_shipment_from_erp_api(sales_order_no: str) -> str | None:
    """通过 ERP API 查询最近发货单，检查 remark 是否包含指定订单号"""
    from datetime import timedelta
    from app.services.erp_bridge import ERPBridge
    from app.ncloud.services.shipments import list_shipments, get_shipment_detail

    bridge = ERPBridge()
    client = await bridge._ensure_login()

    today = datetime.now()
    dates = (today - timedelta(days=3)).strftime("%Y-%m-%d")
    datee = today.strftime("%Y-%m-%d")

    result = await list_shipments(client, dates=dates, datee=datee, state=None, page=1, rows=200)
    for item in result.rows:
        try:
            detail = await get_shipment_detail(client, item.order_no)
            remark = detail.main.remark or ""
            if f"关联订单:{sales_order_no}" in remark:
                # 顺便同步到本地
                try:
                    from app.services.erp_sync import sync_single_shipment
                    await sync_single_shipment(item.order_no)
                except Exception:
                    pass
                return item.order_no
        except Exception:
            continue
    return None


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
def _extract_cdn_params(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """提取 CDN 下载参数，返回多个候选方案（按图片质量从高到低排序）。

    优先级：原图 c2c file_type=1 → wx_download 最大尺寸 → wx_download 标准。
    """
    message = payload.get("message") if isinstance(payload.get("message"), dict) else {}
    data = message.get("data") if isinstance(message.get("data"), dict) else {}
    cdn = data.get("cdn") if isinstance(data.get("cdn"), dict) else {}
    c2c = data.get("c2c_cdn") if isinstance(data.get("c2c_cdn"), dict) else {}

    auth_key = cdn.get("auth_key") or data.get("auth_key") or ""
    aes_key = cdn.get("aes_key") or c2c.get("aes_key") or data.get("aes_key") or ""

    candidates: list[dict[str, Any]] = []

    # 方案A: c2c_download file_type=1 (原图)
    file_id = c2c.get("file_id") or data.get("file_id") or ""
    if file_id and aes_key:
        c2c_size = c2c.get("file_size") or c2c.get("size") or data.get("size") or 0
        try:
            c2c_size = int(c2c_size)
        except (ValueError, TypeError):
            c2c_size = 0
        candidates.append({"mode": "c2c_download", "file_id": file_id,
                           "aes_key": aes_key, "file_size": c2c_size, "file_type": 1})

    # 方案B: wx_download — 选最大尺寸的 URL
    url_options = []
    for url_key, size_key in [("url", "size"), ("md_url", "md_size"), ("ld_url", "ld_size")]:
        u = cdn.get(url_key) or ""
        s = cdn.get(size_key) or 0
        try:
            s = int(s)
        except (ValueError, TypeError):
            s = 0
        if u and s:
            url_options.append((s, u))
    # data 级别的 url
    data_url = data.get("url") or ""
    data_size = data.get("size") or 0
    try:
        data_size = int(data_size)
    except (ValueError, TypeError):
        data_size = 0
    if data_url and data_size:
        url_options.append((data_size, data_url))

    # 按 size 从大到小排序，取最大的
    url_options.sort(key=lambda x: x[0], reverse=True)
    seen_urls: set[str] = set()
    for size_val, url_val in url_options:
        if url_val in seen_urls:
            continue
        seen_urls.add(url_val)
        if auth_key and aes_key:
            candidates.append({"mode": "wx_download", "url": url_val,
                               "auth_key": auth_key, "aes_key": aes_key, "size": size_val})

    return candidates


async def download_image(db: Session, payload: dict[str, Any], instance_id: str, msg_log_id: int) -> Optional[bytes]:
    """从 OSS 获取图片（若未归档则先从 CDN 下载并归档到 OSS），返回字节。"""
    try:
        from app.services.media_archive import ensure_oss_and_read
        file_bytes = await ensure_oss_and_read(
            db,
            msg_log_id=msg_log_id,
            payload=payload,
            instance_id=instance_id,
            message_type="image",
            file_name="",
        )
        if file_bytes:
            logger.info("[发货扫码] OSS读取成功 msg_log_id=%s size=%d", msg_log_id, len(file_bytes))
        else:
            logger.warning("[发货扫码] OSS读取失败 msg_log_id=%s", msg_log_id)
        return file_bytes
    except Exception as exc:
        logger.warning("[发货扫码] OSS下载异常 msg_log_id=%s: %s", msg_log_id, exc)
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

    # _chat() 内部已完成：API调用 → 提取 content → _extract_json() → 返回 dict
    parsed = await ai_order_parser._chat(vision_model, messages, db=db, caller="shipping_table_parse")

    if not parsed or not isinstance(parsed, dict):
        raise AIOrderParserError("AI视觉模型未返回有效内容")

    return parsed


def _crop_top_right_for_code_text(image_bytes: bytes) -> bytes:
    from PIL import Image

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    w, h = img.size
    crop = img.crop((max(0, int(w * 0.52)), 0, w, max(1, int(h * 0.38))))
    crop = crop.resize((max(crop.size[0] * 2, 1), max(crop.size[1] * 2, 1)))
    buf = io.BytesIO()
    crop.save(buf, format="PNG")
    return buf.getvalue()


async def ai_identify_shipping_code_by_agent(image_bytes: bytes, db: Session) -> dict[str, Any]:
    img_bytes = _crop_top_right_for_code_text(image_bytes)
    img_b64 = base64.b64encode(img_bytes).decode("ascii")
    cfg = ai_order_parser._load_config(db)
    vision_model = cfg.get("vision_model") or cfg.get("model") or "qwen-vl-max"

    image_content: dict[str, Any]
    if ai_order_parser.supports_oss_upload(db):
        try:
            fname = f"shipping_code_agent_{int(time.time())}.png"
            oss_url = await ai_order_parser.upload_file(img_bytes, fname, vision_model, db=db)
            image_content = {"type": "image_url", "image_url": {"url": oss_url}}
        except Exception:
            image_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}
    else:
        image_content = {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}}

    parsed = await ai_order_parser._chat(
        vision_model,
        [
            {"role": "system", "content": _SHIPPING_CODE_FALLBACK_PROMPT},
            {"role": "user", "content": [
                image_content,
                {"type": "text", "text": "请只识别右上角图像码下方那一行印刷文字。"},
            ]},
        ],
        db=db,
        caller="shipping_code_agent",
    )
    if not isinstance(parsed, dict):
        return {}

    combined_text = _normalize_qr_text(str(parsed.get("combined_text") or ""))
    order_no = str(parsed.get("order_no") or "").strip()
    paper_id = str(parsed.get("paper_id") or "").strip()
    if combined_text and (not order_no or not paper_id):
        qr_info = parse_qr_content(combined_text)
        order_no = order_no or qr_info.get("order_no", "")
        paper_id = paper_id or qr_info.get("paper_id", "")
    return {
        "combined_text": combined_text,
        "order_no": order_no,
        "paper_id": paper_id,
        "confidence": str(parsed.get("confidence") or ""),
        "reason": str(parsed.get("reason") or ""),
    }


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
            text("SELECT room_id, room_name FROM downstream_customer_wechat_rooms WHERE room_type = 'notification'")
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


def _reviewer_name(user: Any) -> str:
    return (
        getattr(user, "real_name", None)
        or getattr(user, "nickname", None)
        or getattr(user, "username", None)
        or getattr(user, "name", None)
        or ""
    )


async def approve_shipping_scan_record(db: Session, record_id: int, current_user: Any, review_note: str = "") -> dict[str, Any]:
    ensure_downstream_support_tables(db)
    row = db.execute(
        text("SELECT * FROM shipping_scan_records WHERE id = :id LIMIT 1"),
        {"id": record_id},
    ).mappings().first()
    if not row:
        raise ValueError("发货识别记录不存在")
    if row.get("scan_status") != "review_pending":
        raise ValueError("当前记录不是待审核状态")

    order_no = row.get("order_no") or ""
    parsed = json.loads(row.get("ai_parsed_json") or "{}")
    parsed_items = (parsed or {}).get("items") or []
    if not order_no:
        raise ValueError("待审核记录缺少订单号")
    if not parsed_items:
        raise ValueError("待审核记录缺少 AI 解析明细")

    order_detail = await get_erp_order_detail(order_no)
    if order_detail.get("main", {}).get("state") == 2:
        raise ValueError(f"订单 {order_no} 已作废，不能审核下发货单")

    shipment_result = await create_erp_shipment(order_detail, parsed_items)
    shipment_no = shipment_result.get("shipment_no", "")
    if shipment_no:
        try:
            from app.services.erp_sync import sync_single_shipment
            await sync_single_shipment(shipment_no)
        except Exception as exc:
            logger.warning("[发货审核] 即时同步发货单 %s 失败: %s", shipment_no, exc)

    shipping_status = calc_shipping_status(order_detail, parsed_items)
    update_scan_record(
        db,
        record_id,
        scan_status="success",
        shipment_no=shipment_no,
        shipment_result=json.dumps(shipping_status, ensure_ascii=False),
        review_note=(review_note or "").strip(),
        reviewed_by=_reviewer_name(current_user),
        reviewed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        error_message="",
    )
    await send_notification_to_groups(db, order_no, shipment_no, True, shipping_status)
    update_scan_record(db, record_id, notification_sent=1)
    return {
        "record_id": record_id,
        "order_no": order_no,
        "shipment_no": shipment_no,
        "shipping_status": shipping_status,
    }


def void_shipping_scan_record(db: Session, record_id: int, current_user: Any, review_note: str = "") -> dict[str, Any]:
    ensure_downstream_support_tables(db)
    row = db.execute(
        text("SELECT id, scan_status, order_no FROM shipping_scan_records WHERE id = :id LIMIT 1"),
        {"id": record_id},
    ).mappings().first()
    if not row:
        raise ValueError("发货识别记录不存在")
    if row.get("scan_status") not in {"review_pending", "pending", "parsing", "failed"}:
        raise ValueError("当前状态不允许作废")
    update_scan_record(
        db,
        record_id,
        scan_status="voided",
        review_note=(review_note or "").strip(),
        reviewed_by=_reviewer_name(current_user),
        reviewed_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )
    return {"record_id": record_id, "order_no": row.get("order_no") or "", "scan_status": "voided"}


# ---------------------------------------------------------------------------
# 判断群是否为发货群
# ---------------------------------------------------------------------------
def resolve_shipping_room(db: Session, room_id: str) -> Optional[dict[str, str]]:
    """检查 room_id 是否为发货群，返回群信息或 None。

    兼容 room_id 有/无 'R:' 前缀的情况（前端存不带前缀，消息日志带前缀）。
    """
    if not room_id:
        return None
    rid_clean = room_id[2:] if room_id.startswith("R:") else room_id
    try:
        row = db.execute(
            text(
                "SELECT room_id, room_name FROM downstream_customer_wechat_rooms "
                "WHERE room_id IN (:rid1, :rid2) AND room_type = 'shipping' LIMIT 1"
            ),
            {"rid1": rid_clean, "rid2": f"R:{rid_clean}"},
        ).mappings().first()
        if row:
            return {"room_id": row["room_id"], "room_name": row["room_name"] or ""}
    except Exception as exc:
        logger.warning("resolve_shipping_room 查询异常: %s", exc)
    return None


# ---------------------------------------------------------------------------
# 标记消息已被识别（与客户群逻辑一致）
# ---------------------------------------------------------------------------
def _mark_msg_recognized(msg_log_id: int) -> None:
    """标记消息日志已被 AI 识别处理"""
    if not msg_log_id:
        return
    db = SessionLocal()
    try:
        from app.services.message_logs import mark_ai_recognized
        mark_ai_recognized(db, msg_log_id)
    except Exception as exc:
        logger.warning("标记 ai_recognized 失败 id=%d: %s", msg_log_id, exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# 扫码失败通知（发货群@发送人 + 通知群）
# ---------------------------------------------------------------------------
async def _notify_scan_failure(
    room_id: str, sender_id: str, msg_log_id: int,
    reason: str, instance_id: str = "",
    source: str | int | None = None,
) -> None:
    """扫码失败时：在发货群@发送人提示（引用原图消息） + 通知群推送"""
    db = SessionLocal()
    try:
        # 1) 在发货群@发送人（引用原消息）
        at_list = [sender_id] if sender_id else None
        tip = f"❌ 发货单识别失败\n原因：{reason}\n请重新拍照，确保图片清晰、二维码完整可见"
        try:
            await send_room_at(db, room_id, tip, at_list=at_list, source=source)
        except Exception as exc:
            logger.warning("[发货扫码] 发货群通知失败: %s", exc)

        # 2) 通知群推送
        await send_notification_to_groups(
            db, "", "", False, {},
            f"发货群图片识别失败 (log_id={msg_log_id}): {reason}",
        )
    except Exception as exc:
        logger.warning("[发货扫码] 失败通知异常: %s", exc)
    finally:
        db.close()


async def _notify_scan_success(
    room_id: str,
    source: str | int | None = None,
) -> None:
    db = SessionLocal()
    try:
        await send_room_at(db, room_id, "✅ 发货成功", source=source)
    except Exception as exc:
        logger.warning("[发货扫码] 发货群成功通知失败: %s", exc)
    finally:
        db.close()


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
    # 提取原始消息的 server_id，用于回复时引用该消息
    _msg_data = (payload.get("message") or {}).get("data") or payload.get("data") or {}
    if isinstance(_msg_data, str):
        _msg_data = {}
    source_msg_id = _msg_data.get("server_id") or _msg_data.get("svr_id") or ""

    try:
        logger.info("[发货扫码] 收到图片 room=%s sender=%s log_id=%d", room_id, sender_id, msg_log_id)

        # 1. 下载图片
        db = SessionLocal()
        try:
            image_bytes = await download_image(db, payload, instance_id, msg_log_id)
        finally:
            db.close()

        if not image_bytes:
            logger.info("[发货扫码] 图片下载失败 log_id=%d", msg_log_id)
            await _notify_scan_failure(room_id, sender_id, msg_log_id, "图片下载失败", instance_id, source=source_msg_id)
            # 不标记 ai_recognized，留给补扫重试
            return

        # 2. 识别：GridCode 方块码优先 → 条形码/二维码兜底
        order_no = ""
        paper_id = ""
        qr_text = ""
        code_source = ""
        ai_agent_result: dict[str, Any] | None = None

        # 2a. GridCode 方块码检测（自定义图案，内容直接编码，最鲁棒）
        from app.services.erp_gridcode import decode_gridcode_from_bytes
        import time as _time
        _gc_t0 = _time.perf_counter()
        gridcode_results = decode_gridcode_from_bytes(image_bytes)
        _gc_elapsed = _time.perf_counter() - _gc_t0
        logger.info("[发货扫码] GridCode检测: results=%s 耗时=%.3fs log_id=%d", gridcode_results[:2] if gridcode_results else [], _gc_elapsed, msg_log_id)
        if gridcode_results:
            qr_text = gridcode_results[0]
            qr_info = parse_qr_content(qr_text)
            order_no = qr_info.get("order_no", "")
            paper_id = qr_info.get("paper_id", "")
            if order_no and paper_id:
                code_source = "gridcode"
                logger.info("[发货扫码] GridCode识别成功 order=%s paper=%s", order_no, paper_id)

        if not order_no or not paper_id:
            logger.info("[发货扫码] GridCode未命中，开始调用右上角识别智能体 log_id=%d", msg_log_id)
            db = SessionLocal()
            try:
                ai_agent_result = await ai_identify_shipping_code_by_agent(image_bytes, db)
            except Exception as exc:
                logger.warning("[发货扫码] 右上角识别智能体失败 log_id=%d: %s", msg_log_id, exc)
                ai_agent_result = None
            finally:
                db.close()

            if ai_agent_result:
                logger.info(
                    "[发货扫码] 右上角识别智能体已返回 log_id=%d combined_text=%s confidence=%s",
                    msg_log_id,
                    ai_agent_result.get("combined_text") or "",
                    ai_agent_result.get("confidence") or "",
                )
                order_no = ai_agent_result.get("order_no") or ""
                paper_id = ai_agent_result.get("paper_id") or ""
                qr_text = ai_agent_result.get("combined_text") or qr_text
                if order_no and paper_id:
                    code_source = "ai_agent"
                    logger.info("[发货扫码] 右上角识别智能体成功 order=%s paper=%s confidence=%s", order_no, paper_id, ai_agent_result.get("confidence") or "")
                else:
                    logger.info(
                        "[发货扫码] 右上角识别智能体返回了结果，但未提取到完整订单号/纸张ID log_id=%d order=%s paper=%s",
                        msg_log_id,
                        order_no,
                        paper_id,
                    )
            else:
                logger.info("[发货扫码] 右上角识别智能体返回空结果 log_id=%d", msg_log_id)

        if not order_no or not paper_id:
            logger.info("[发货扫码] 方块码和码下文字均未识别成功 log_id=%d", msg_log_id)
            await _notify_scan_failure(room_id, sender_id, msg_log_id, "识别失败，请拍清晰", instance_id, source=source_msg_id)
            return

        # 3. 检查纸张ID去重
        db = SessionLocal()
        try:
            if is_paper_used(db, paper_id):
                logger.info("[发货扫码] 纸张ID已使用，跳过 paper=%s", paper_id)
                await _notify_scan_failure(
                    room_id, sender_id, msg_log_id,
                    f"此张图片已被识别过，请勿重复识别！(订单:{order_no})",
                    instance_id, source=source_msg_id,
                )
                _mark_msg_recognized(msg_log_id)
                return

            # 创建扫码记录（如有同 paper_id 的 failed 记录则复用，避免列表出现重复）
            room_info = resolve_shipping_room(db, room_id) or {}
            existing_failed = db.execute(
                text(
                    "SELECT id FROM shipping_scan_records "
                    "WHERE paper_id = :pid AND scan_status = 'failed' "
                    "ORDER BY id DESC LIMIT 1"
                ),
                {"pid": paper_id},
            ).first()
            if existing_failed:
                record_id = existing_failed[0]
                update_scan_record(
                    db, record_id,
                    order_no=order_no, qr_content=qr_text, code_source=code_source,
                    room_id=room_id, room_name=room_info.get("room_name", ""),
                    instance_id=instance_id, sender_id=sender_id, msg_log_id=msg_log_id,
                    scan_status="pending", error_message="",
                )
            else:
                record_id = create_scan_record(
                    db,
                    order_no=order_no,
                    paper_id=paper_id,
                    qr_content=qr_text,
                    code_source=code_source,
                    room_id=room_id,
                    room_name=room_info.get("room_name", ""),
                    instance_id=instance_id,
                    sender_id=sender_id,
                    msg_log_id=msg_log_id,
                )
            if ai_agent_result:
                update_scan_record(db, record_id, fallback_ocr_json=json.dumps(ai_agent_result, ensure_ascii=False))
        finally:
            db.close()

        logger.info("[发货扫码] 创建扫码记录 id=%d order=%s paper=%s", record_id, order_no, paper_id)

        # 4. AI 视觉解析发货表格（含熔断检查）
        from app.services.ai_circuit_breaker import is_tripped as _ai_tripped, buffer_message as _ai_buffer, record_success as _ai_ok, record_error as _ai_err
        if _ai_tripped():
            logger.warning("[发货扫码] AI 已熔断，缓冲发货扫码 record=%d order=%s", record_id, order_no)
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message="AI 已暂停（熔断）")
            finally:
                db.close()
            _ai_buffer({
                "room_id": room_id,
                "sender_id": sender_id,
                "sender_name": "",
                "customer_name": "",
                "content_preview": f"[发货扫码] 订单:{order_no} 纸张:{paper_id}",
                "message_type": "shipping_scan",
                "msg_log_id": msg_log_id,
                "record_id": record_id,
                "order_no": order_no,
                "paper_id": paper_id,
            })
            return

        db = SessionLocal()
        try:
            update_scan_record(db, record_id, scan_status="parsing")
            parsed = await ai_parse_shipping_table(image_bytes, db)
            parsed_items = parsed.get("items") or []
            update_scan_record(db, record_id, ai_parsed_json=json.dumps(parsed, ensure_ascii=False))
            _ai_ok()
        except Exception as exc:
            update_scan_record(db, record_id, scan_status="failed", error_message=f"AI解析失败: {exc}")
            logger.error("[发货扫码] AI解析失败 record=%d: %s", record_id, exc)
            await _ai_err(f"shipping_scan: {exc}")
            # 通知群推送失败
            await send_notification_to_groups(db, order_no, "", False, {}, f"AI解析失败: {exc}")
            _mark_msg_recognized(msg_log_id)
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
            _mark_msg_recognized(msg_log_id)
            return

        logger.info("[发货扫码] AI解析成功 record=%d items=%d", record_id, len(parsed_items))

        if code_source in ("ai_text", "ai_agent"):
            db = SessionLocal()
            try:
                update_scan_record(
                    db,
                    record_id,
                    scan_status="review_pending",
                    error_message="图像码未直接识别，已由 AI 读取码下文字，需人工审核后下发货单",
                )
            finally:
                db.close()
            _mark_msg_recognized(msg_log_id)
            logger.info("[发货扫码] 进入人工审核 record=%d order=%s paper=%s", record_id, order_no, paper_id)
            return

        try:
            order_detail = await get_erp_order_detail(order_no)
        except Exception as exc:
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message=f"查询订单失败: {exc}")
                await send_notification_to_groups(db, order_no, "", False, {}, f"查询订单 {order_no} 失败: {exc}")
            finally:
                db.close()
            _mark_msg_recognized(msg_log_id)
            return

        # 5.5 检查订单是否已作废（state=2）
        order_state = order_detail.get("main", {}).get("state")
        if order_state == 2:
            logger.warning("[发货扫码] 订单 %s 已作废(state=2)，@发送人警告", order_no)
            db = SessionLocal()
            try:
                update_scan_record(db, record_id, scan_status="failed", error_message=f"订单 {order_no} 已作废")
                at_list = [sender_id] if sender_id else None
                warn_msg = f"⚠️ 注意！订单 {order_no} 已作废，此单不要发货！！！请核实最新订单号！"
                await send_room_at(db, room_id, warn_msg, at_list=at_list, source=source_msg_id)
                await send_notification_to_groups(db, order_no, "", False, {}, f"⚠️ 已作废订单 {order_no} 的拣货单被扫码识别，已在发货群@发送人警告")
            finally:
                db.close()
            _mark_msg_recognized(msg_log_id)
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
            _mark_msg_recognized(msg_log_id)
            return

        # 6.5 即时同步刚创建的发货单到本地数据库
        if shipment_no:
            try:
                from app.services.erp_sync import sync_single_shipment
                sync_result = await sync_single_shipment(shipment_no)
                logger.info("[发货扫码] 即时同步发货单 %s 结果: %s", shipment_no, sync_result)
            except Exception as exc:
                logger.warning("[发货扫码] 即时同步发货单 %s 失败（不影响主流程）: %s", shipment_no, exc)

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
            await _notify_scan_success(room_id, source=source_msg_id)
            await send_notification_to_groups(db, order_no, shipment_no, True, shipping_status)
            update_scan_record(db, record_id, notification_sent=1)
        finally:
            db.close()

        # 标记消息已识别
        _mark_msg_recognized(msg_log_id)

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
        _mark_msg_recognized(msg_log_id)


# ---------------------------------------------------------------------------
# 重试发货扫码（AI 恢复后重新处理之前失败的记录）
# ---------------------------------------------------------------------------
async def retry_shipping_scan_record(record_id: int) -> dict[str, Any]:
    """根据已有的 scan record 重新从 AI 解析开始执行。
    会检查 paper_id 是否已成功识别过，避免重复下单。
    """
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT * FROM shipping_scan_records WHERE id = :id"),
            {"id": record_id},
        ).mappings().first()
    finally:
        db.close()

    if not row:
        return {"ok": False, "error": f"扫码记录 {record_id} 不存在"}

    if row.get("scan_status") == "review_pending":
        return {"ok": False, "error": "该记录为待审核状态，请到发货单审核页面人工确认"}

    order_no = row["order_no"] or ""
    paper_id = row["paper_id"] or ""
    room_id = row["room_id"] or ""
    sender_id = row["sender_id"] or ""
    msg_log_id = row["msg_log_id"] or 0
    instance_id = row["instance_id"] or ""

    # 检查 paper_id 是否已成功
    db = SessionLocal()
    try:
        if is_paper_used(db, paper_id):
            logger.info("[发货重试] paper=%s 已成功识别过，跳过", paper_id)
            return {"ok": False, "error": f"纸张 {paper_id} 已成功识别过，无需重试"}
    finally:
        db.close()

    # 重新下载图片（从 OSS 读取已归档的图片）
    db = SessionLocal()
    try:
        log_row = db.execute(
            text("SELECT oss_key FROM message_logs WHERE id = :id"),
            {"id": msg_log_id},
        ).mappings().first()
    finally:
        db.close()

    image_bytes = None
    oss_key = (log_row or {}).get("oss_key") or ""
    if oss_key:
        try:
            from app.utils.oss_client import oss_client
            image_bytes = oss_client.download_file(oss_key)
        except Exception as exc:
            logger.warning("[发货重试] OSS 下载失败 key=%s: %s", oss_key, exc)

    if not image_bytes:
        return {"ok": False, "error": "无法重新获取图片（OSS 无归档）"}

    # AI 解析
    db = SessionLocal()
    try:
        update_scan_record(db, record_id, scan_status="parsing", error_message="")
        parsed = await ai_parse_shipping_table(image_bytes, db)
        parsed_items = parsed.get("items") or []
        update_scan_record(db, record_id, ai_parsed_json=json.dumps(parsed, ensure_ascii=False))
    except Exception as exc:
        update_scan_record(db, record_id, scan_status="failed", error_message=f"重试AI解析失败: {exc}")
        return {"ok": False, "error": f"AI解析失败: {exc}"}
    finally:
        db.close()

    if not parsed_items:
        db = SessionLocal()
        try:
            update_scan_record(db, record_id, scan_status="failed", error_message="重试: AI未识别到有效发货内容")
        finally:
            db.close()
        return {"ok": False, "error": "AI未识别到有效发货内容"}

    # 获取 ERP 订单详情
    try:
        order_detail = await get_erp_order_detail(order_no)
    except Exception as exc:
        db = SessionLocal()
        try:
            update_scan_record(db, record_id, scan_status="failed", error_message=f"重试: 查询订单失败: {exc}")
        finally:
            db.close()
        return {"ok": False, "error": f"查询订单失败: {exc}"}

    # 检查订单是否已作废
    order_state = order_detail.get("main", {}).get("state")
    if order_state == 2:
        db = SessionLocal()
        try:
            update_scan_record(db, record_id, scan_status="failed", error_message=f"订单 {order_no} 已作废")
        finally:
            db.close()
        return {"ok": False, "error": f"订单 {order_no} 已作废"}

    # 创建发货单
    try:
        shipment_result = await create_erp_shipment(order_detail, parsed_items)
        shipment_no = shipment_result.get("shipment_no", "")
    except Exception as exc:
        db = SessionLocal()
        try:
            update_scan_record(db, record_id, scan_status="failed", error_message=f"重试: 创建发货单失败: {exc}")
        finally:
            db.close()
        return {"ok": False, "error": f"创建发货单失败: {exc}"}

    # 即时同步
    if shipment_no:
        try:
            from app.services.erp_sync import sync_single_shipment
            await sync_single_shipment(shipment_no)
        except Exception:
            pass

    # 计算发货状态
    shipping_status = calc_shipping_status(order_detail, parsed_items)

    # 更新记录 + 通知
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

    _mark_msg_recognized(msg_log_id)
    logger.info("[发货重试] 完成 record=%d shipment=%s", record_id, shipment_no)
    return {"ok": True, "record_id": record_id, "shipment_no": shipment_no, "order_no": order_no}
