"""
拣货单打印服务 — 生成 PDF（含条形码），上传 OSS，幂等（重复打印返回同一份）
"""

from __future__ import annotations

import io
import json
import logging
import os
import subprocess
import uuid
from base64 import b64encode
from datetime import datetime
from typing import Any

import qrcode
from qrcode.image.pil import PilImage
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.oss_client import oss_client

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = landscape(A4)  # 841.89, 595.27 pt

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_DDL_PRINT_JOBS = """
CREATE TABLE IF NOT EXISTS picking_print_jobs (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no        VARCHAR(100) NOT NULL,
    oss_object_name VARCHAR(500) NOT NULL DEFAULT '',
    oss_url         VARCHAR(1000) NOT NULL DEFAULT '',
    page_count      INT UNSIGNED NOT NULL DEFAULT 0,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_order_no (order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""

_DDL_PRINT_PAGES = """
CREATE TABLE IF NOT EXISTS picking_print_pages (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no        VARCHAR(100) NOT NULL,
    page_index      INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '从0开始的页码',
    page_id         VARCHAR(64) NOT NULL COMMENT '本页唯一ID',
    barcode_content VARCHAR(300) NOT NULL DEFAULT '' COMMENT '条形码内容 = order_no|page_id',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_page_id (page_id),
    INDEX idx_order_no (order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


def ensure_print_tables(db: Session) -> None:
    db.execute(text(_DDL_PRINT_JOBS))
    db.execute(text(_DDL_PRINT_PAGES))
    db.commit()


# ---------------------------------------------------------------------------
# 中文字体注册（尝试多路径）
# ---------------------------------------------------------------------------
_FONT_REGISTERED = False


def _register_chinese_font() -> str:
    """注册中文字体，返回字体名称"""
    global _FONT_REGISTERED
    font_name = "ChineseFont"
    if _FONT_REGISTERED:
        return font_name
    _FONT_REGISTERED = True
    return "Helvetica"


# ---------------------------------------------------------------------------
# 二维码生成
# ---------------------------------------------------------------------------
def _generate_qr_image(content: str, box_size: int = 4, border: int = 1) -> io.BytesIO:
    """生成 QR Code PNG 图片，返回 BytesIO"""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=box_size,
        border=border,
    )
    qr.add_data(content)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf


def _image_buf_to_data_url(buf: io.BytesIO) -> str:
    return f"data:image/png;base64,{b64encode(buf.getvalue()).decode('ascii')}"


# ---------------------------------------------------------------------------
# 尺码排序
# ---------------------------------------------------------------------------
_SIZE_ORDER = [
    "XXS", "XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL",
    "26", "27", "28", "29", "30", "31", "32", "33", "34", "35", "36",
    "37", "38", "39", "40", "41", "42", "43", "44", "45", "46",
    "F", "均码",
]
_SIZE_RANK = {s: i for i, s in enumerate(_SIZE_ORDER)}


def _size_sort_key(size_name: str) -> tuple:
    upper = size_name.strip().upper()
    if upper in _SIZE_RANK:
        return (0, _SIZE_RANK[upper])
    return (1, size_name)


# ---------------------------------------------------------------------------
# 按货号分组
# ---------------------------------------------------------------------------
def _group_items_to_product_blocks(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    from collections import OrderedDict
    grouped: OrderedDict[str, dict] = OrderedDict()
    for item in items:
        pno = item.get("product_no") or "未知"
        if pno not in grouped:
            grouped[pno] = {"product_no": pno, "size_set": set(), "color_rows": []}
        color = item.get("color") or "-"
        sizes = item.get("sizes") or []
        qty_map: dict[str, int] = {}
        subtotal = 0
        for s in sizes:
            sn = s.get("size", "")
            sq = int(s.get("qty", 0))
            if sn:
                qty_map[sn] = qty_map.get(sn, 0) + sq
                grouped[pno]["size_set"].add(sn)
            subtotal += sq
        grouped[pno]["color_rows"].append({"color": color, "qty_map": qty_map, "subtotal": subtotal})

    blocks = []
    for pno, g in grouped.items():
        blocks.append({
            "product_no": pno,
            "color_rows": g["color_rows"],
            "n_rows": len(g["color_rows"]),
        })
    return blocks


# ---------------------------------------------------------------------------
# 页面布局常量
# ---------------------------------------------------------------------------
_MARGIN_TOP = 10 * mm
_MARGIN_BOTTOM = 10 * mm
_MARGIN_X = 10 * mm
_TITLE_AREA_H = 16 * mm          # 标题 + 二维码
_INFO_AREA_H = 26 * mm           # 客户信息（仅首页）
_TABLE_HEADER_H = 8 * mm         # 表头行高
_ROW_H = 6 * mm                  # 数据行高
_FOOTER_H = 10 * mm              # 页脚

_TITLE_FONT_SIZE = 18
_INFO_FONT_SIZE = 9.5
_TABLE_FONT_SIZE = 8.5
_TABLE_HEADER_FONT_SIZE = 10


def _available_rows(page_idx: int) -> int:
    """计算某页能容纳的数据行数（不含表头）"""
    body = PAGE_H - _MARGIN_TOP - _TITLE_AREA_H - _MARGIN_BOTTOM - _FOOTER_H - _TABLE_HEADER_H
    if page_idx == 0:
        body -= _INFO_AREA_H
    return max(int(body / _ROW_H), 1)


def _paginate_blocks(blocks: list[dict]) -> list[list[dict]]:
    """按款号整块分页，不拆分款号"""
    pages: list[list[dict]] = []
    cur_page: list[dict] = []
    cur_rows = 0
    page_idx = 0

    for blk in blocks:
        cap = _available_rows(page_idx)
        needed = blk["n_rows"]
        if cur_page and (cur_rows + needed) > cap:
            pages.append(cur_page)
            cur_page = []
            cur_rows = 0
            page_idx += 1
            cap = _available_rows(page_idx)
        cur_page.append(blk)
        cur_rows += needed

    if cur_page:
        pages.append(cur_page)
    return pages if pages else [[]]


# ---------------------------------------------------------------------------
# 收集所有尺码（全订单统一列）
# ---------------------------------------------------------------------------
def _collect_all_sizes(items: list[dict]) -> list[str]:
    s = set()
    for it in items:
        for sz in (it.get("sizes") or []):
            sn = sz.get("size", "")
            if sn:
                s.add(sn)
    return sorted(s, key=_size_sort_key)


# ---------------------------------------------------------------------------
# PDF 生成核心
# ---------------------------------------------------------------------------
def _build_picking_pdf(
    order: dict[str, Any],
    items: list[dict[str, Any]],
    page_records: list[dict[str, str]],
) -> bytes:
    all_sizes = _collect_all_sizes(items)
    blocks = _group_items_to_product_blocks(items)
    block_pages = _paginate_blocks(blocks)
    total_pages = len(block_pages)

    assert len(page_records) == total_pages, \
        f"page_records({len(page_records)}) != total_pages({total_pages})"
    payload_pages = []
    for page_idx, page_blocks in enumerate(block_pages):
        pr = page_records[page_idx]
        qr_buf = _generate_qr_image(pr["barcode_content"], box_size=4, border=1)
        payload_pages.append({
            "page_index": page_idx,
            "page_id": pr["page_id"],
            "barcode_content": pr["barcode_content"],
            "show_info": page_idx == 0,
            "qr_data_url": _image_buf_to_data_url(qr_buf),
            "blocks": page_blocks,
        })

    payload = {
        "title": "韩酷服饰-拣货单",
        "order": {
            "order_no": order.get("order_no", ""),
            "order_date": order.get("order_date", ""),
            "customer_name": order.get("customer_name", ""),
            "customer_tel": order.get("customer_tel", ""),
            "customer_addr": order.get("customer_addr", ""),
            "creator": order.get("creator", ""),
            "remark": (order.get("remark") or "")[:120],
        },
        "all_sizes": all_sizes,
        "pages": payload_pages,
    }

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "scripts", "generate-picking-pdf.cjs")
    )
    if not os.path.isfile(script_path):
        raise RuntimeError(f"pdfmake 生成脚本不存在: {script_path}")

    proc = subprocess.run(
        ["node", script_path],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", errors="ignore")
        raise RuntimeError(f"pdfmake 生成失败: {err.strip()}")
    return proc.stdout


# ---------------------------------------------------------------------------
# 主入口（幂等）
# ---------------------------------------------------------------------------
def generate_picking_pdf(db: Session, order_no: str) -> dict[str, Any]:
    """
    生成拣货单 PDF。

    幂等逻辑（数据库是唯一真相来源）：
    - page_id 只在首次打印时生成并写入 DB，后续永远复用 DB 中的 page_id
    - 每次调用都会用 DB 中的 page_id 重新生成 PDF 并上传 OSS（覆盖）
    - 即使 OSS 文件被删除，page_id 也不会改变

    返回 {"oss_url": "...", "page_count": N, "pages": [...]}
    """
    ensure_print_tables(db)

    # 1. 读取订单主表
    order_row = db.execute(
        text("""
            SELECT order_no, order_date, customer_name, customer_tel, customer_addr,
                   salesperson, creator, delivery_date, shipping_method,
                   total_qty, total_amount, remark
            FROM erp_sales_orders WHERE order_no = :no
        """),
        {"no": order_no},
    ).mappings().first()
    if not order_row:
        raise ValueError(f"订单不存在: {order_no}")

    order = dict(order_row)

    # 2. 读取明细行
    item_rows = db.execute(
        text("""
            SELECT sort_index, brand, product_no, product_name, color, grade,
                   unit, price, discount, sizes_json, total_qty, remark
            FROM erp_sales_order_items WHERE order_no = :no ORDER BY sort_index
        """),
        {"no": order_no},
    ).mappings().all()

    items = []
    for r in item_rows:
        sizes = []
        try:
            sizes = json.loads(r["sizes_json"] or "[]")
        except Exception:
            pass
        items.append({**dict(r), "sizes": sizes})

    # 3. 按货号分组 → 分页 → 计算真实页数
    blocks = _group_items_to_product_blocks(items)
    block_pages = _paginate_blocks(blocks)
    total_pages = len(block_pages)

    # 4. 从 DB 读取已有 page_id（如果有的话）
    existing_pages = db.execute(
        text("SELECT page_index, page_id, barcode_content FROM picking_print_pages WHERE order_no = :no ORDER BY page_index"),
        {"no": order_no},
    ).mappings().all()

    if existing_pages and len(existing_pages) == total_pages:
        # DB 中有完整的 page_id 映射，直接复用
        page_records = [dict(p) for p in existing_pages]
        logger.info("拣货单: 复用 DB 中的 page_id order=%s pages=%d", order_no, total_pages)
    else:
        # 首次打印或页数变化：生成新的 page_id 并写入 DB
        if existing_pages:
            # 页数变化（明细行增减），清除旧记录重新生成
            db.execute(text("DELETE FROM picking_print_pages WHERE order_no = :no"), {"no": order_no})
            logger.info("拣货单: 页数变化，重新生成 page_id order=%s old=%d new=%d",
                         order_no, len(existing_pages), total_pages)

        page_records = []
        for i in range(total_pages):
            page_id = uuid.uuid4().hex[:16]
            bc_content = f"{order_no}|{page_id}"
            page_records.append({
                "page_index": i,
                "page_id": page_id,
                "barcode_content": bc_content,
            })
            db.execute(
                text("""
                    INSERT INTO picking_print_pages (order_no, page_index, page_id, barcode_content)
                    VALUES (:no, :idx, :pid, :bc)
                """),
                {"no": order_no, "idx": i, "pid": page_id, "bc": bc_content},
            )
        db.commit()
        logger.info("拣货单: 首次生成 page_id order=%s pages=%d", order_no, total_pages)

    # 5. 每次都用 DB 中的 page_id 重新生成 PDF
    pdf_bytes = _build_picking_pdf(order, items, page_records)

    # 6. 上传 OSS（固定文件名，覆盖旧文件）
    object_name = f"picking/{order_no}.pdf"
    oss_client.upload_file(object_name, pdf_bytes, content_type="application/pdf")

    # 7. 更新 print_jobs 记录
    db.execute(
        text("""
            INSERT INTO picking_print_jobs (order_no, oss_object_name, oss_url, page_count)
            VALUES (:no, :obj, :url, :cnt)
            ON DUPLICATE KEY UPDATE oss_object_name = VALUES(oss_object_name),
                                    oss_url = VALUES(oss_url),
                                    page_count = VALUES(page_count)
        """),
        {"no": order_no, "obj": object_name, "url": object_name, "cnt": total_pages},
    )
    db.commit()

    import time
    ts = int(time.time() * 1000)
    proxy_url = f"/api/sales-orders/oss-file/{object_name}?t={ts}"

    return {
        "oss_url": proxy_url,
        "page_count": total_pages,
        "pages": page_records,
    }
