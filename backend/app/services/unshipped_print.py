"""
待发货报表打印服务 — 生成 PDF（含二维码），与拣货单格式一致
"""

from __future__ import annotations

import io
import json
import logging
import os
import re
import subprocess
import uuid
from base64 import b64encode
from datetime import datetime
from typing import Any

import qrcode
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.oss_client import oss_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDL
# ---------------------------------------------------------------------------
_DDL_PRINT_JOBS = """
CREATE TABLE IF NOT EXISTS unshipped_print_jobs (
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
CREATE TABLE IF NOT EXISTS unshipped_print_pages (
    id              BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
    order_no        VARCHAR(100) NOT NULL,
    page_index      INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '从0开始的页码',
    page_id         VARCHAR(64) NOT NULL COMMENT '本页唯一ID',
    barcode_content VARCHAR(300) NOT NULL DEFAULT '' COMMENT '二维码内容 = order_no|page_id',
    status          VARCHAR(20) NOT NULL DEFAULT 'active' COMMENT 'active=有效, voided=已废除',
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uk_page_id (page_id),
    INDEX idx_order_no (order_no)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


_unshipped_print_tables_ensured = False


def ensure_print_tables(db: Session) -> None:
    global _unshipped_print_tables_ensured
    if _unshipped_print_tables_ensured:
        return
    db.execute(text(_DDL_PRINT_JOBS))
    db.execute(text(_DDL_PRINT_PAGES))
    # 兼容已有表：追加 status 列
    try:
        db.execute(text(
            "ALTER TABLE unshipped_print_pages ADD COLUMN status VARCHAR(20) NOT NULL DEFAULT 'active' "
            "COMMENT 'active=有效, voided=已废除' AFTER barcode_content"
        ))
    except Exception:
        pass
    db.commit()
    _unshipped_print_tables_ensured = True

# ---------------------------------------------------------------------------
# 二维码生成
# ---------------------------------------------------------------------------
def _generate_qr_image(content: str, box_size: int = 4, border: int = 1) -> io.BytesIO:
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

_FIXED_SIZES = ["S", "M", "L", "XL", "2XL", "3XL", "4XL"]


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
        sizes = item.get("unshipped_sizes") or []
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
# 分页
# ---------------------------------------------------------------------------
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm

PAGE_W, PAGE_H = landscape(A4)
_MARGIN_TOP = 10 * mm
_MARGIN_BOTTOM = 10 * mm
_TITLE_AREA_H = 24 * mm
_INFO_AREA_H = 26 * mm
_TABLE_HEADER_H = 9 * mm
_ROW_H = 7 * mm
_FOOTER_H = 10 * mm


def _available_rows(page_idx: int) -> int:
    body = PAGE_H - _MARGIN_TOP - _TITLE_AREA_H - _MARGIN_BOTTOM - _FOOTER_H - _TABLE_HEADER_H
    if page_idx == 0:
        body -= _INFO_AREA_H
    return max(int(body / _ROW_H) - 3, 1)


def _paginate_blocks(blocks: list[dict]) -> list[list[dict]]:
    pages: list[list[dict]] = []
    cur_page: list[dict] = []
    page_idx = 0
    cap = _available_rows(page_idx)
    used = 0

    def flush_page() -> None:
        nonlocal cur_page, page_idx, cap, used
        pages.append(cur_page)
        cur_page = []
        page_idx += 1
        cap = _available_rows(page_idx)
        used = 0

    for blk in blocks:
        product_no = blk.get("product_no") or "未知"
        for cr in list(blk.get("color_rows") or []):
            if used >= cap:
                flush_page()
            if cur_page and cur_page[-1].get("product_no") == product_no:
                cur_page[-1]["color_rows"].append(cr)
                cur_page[-1]["n_rows"] += 1
            else:
                cur_page.append({
                    "product_no": product_no,
                    "color_rows": [cr],
                    "n_rows": 1,
                })
            used += 1

    if cur_page:
        pages.append(cur_page)
    return pages if pages else [[]]


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def _query_order_extra(db: Session, order_no: str) -> dict[str, Any]:
    """从 erp_sales_orders 查询订单的客户详细信息"""
    row = db.execute(
        text("""
            SELECT order_no, order_date, customer_name, customer_tel, customer_addr,
                   creator, remark
            FROM erp_sales_orders WHERE order_no = :no
        """),
        {"no": order_no},
    ).mappings().first()
    return dict(row) if row else {}


def generate_unshipped_pdf(db: Session, item_ids: list[int], customer_name: str = "") -> dict[str, Any]:
    """
    根据传入的 unshipped report 行 ID 列表，生成待发货单 PDF。
    批量打印时按订单分组，每个订单独立首页、独立页码。
    """
    ensure_print_tables(db)

    if not item_ids:
        raise ValueError("没有要打印的记录")

    placeholders = ",".join([f":id{i}" for i in range(len(item_ids))])
    params = {f"id{i}": item_ids[i] for i in range(len(item_ids))}

    rows = db.execute(
        text(
            f"SELECT id, erp_row_id, order_no, order_date, customer_id, "
            f"product_no, product_name, color, unit, "
            f"order_qty, shipped_qty, unshipped_qty, unshipped_amount, "
            f"stock_qty, price, remark, "
            f"unshipped_sizes_json, order_sizes_json "
            f"FROM erp_unshipped_report WHERE id IN ({placeholders}) "
            f"ORDER BY order_no, product_no"
        ),
        params,
    ).mappings().all()

    if not rows:
        raise ValueError("记录不存在")

    # 按订单号分组
    from collections import OrderedDict
    order_groups: OrderedDict[str, list] = OrderedDict()
    for r in rows:
        item = dict(r)
        raw = item.pop("unshipped_sizes_json", None) or "[]"
        try:
            item["unshipped_sizes"] = json.loads(raw)
        except Exception:
            item["unshipped_sizes"] = []
        item.pop("order_sizes_json", None)
        ono = item.get("order_no", "")
        order_groups.setdefault(ono, []).append(item)

    # 为每个订单构建独立的 order section
    order_sections = []
    all_page_records = []
    total_item_count = 0
    total_page_count = 0

    for order_no, order_items in order_groups.items():
        order_extra = _query_order_extra(db, order_no)
        first = order_items[0]
        oqty = sum(int(it.get("order_qty") or 0) for it in order_items)
        uqty = sum(int(it.get("unshipped_qty") or 0) for it in order_items)

        order_info = {
            "order_no": order_no,
            "order_date": str(order_extra.get("order_date") or first.get("order_date") or ""),
            "customer_name": order_extra.get("customer_name") or customer_name or str(first.get("customer_id") or ""),
            "customer_tel": str(order_extra.get("customer_tel") or ""),
            "customer_addr": str(order_extra.get("customer_addr") or ""),
            "creator": str(order_extra.get("creator") or ""),
            "remark": re.sub(r"\[RV[A-Za-z0-9]+\]\s*", "", str(order_extra.get("remark") or "")).strip()[:120],
            "total_order_qty": oqty,
            "total_unshipped_qty": uqty,
        }

        blocks = _group_items_to_product_blocks(order_items)
        block_pages = _paginate_blocks(blocks)
        n_pages = len(block_pages)

        # 生成 page_id 并写入 DB
        db.execute(text("UPDATE unshipped_print_pages SET status = 'voided' WHERE order_no = :no AND status = 'active'"), {"no": order_no})
        page_records = []
        for i in range(n_pages):
            page_id = uuid.uuid4().hex[:16]
            bc_content = f"{order_no}|{page_id}"
            page_records.append({
                "page_index": i,
                "page_id": page_id,
                "barcode_content": bc_content,
            })
            db.execute(
                text("""
                    INSERT INTO unshipped_print_pages (order_no, page_index, page_id, barcode_content)
                    VALUES (:no, :idx, :pid, :bc)
                """),
                {"no": order_no, "idx": i, "pid": page_id, "bc": bc_content},
            )

        # 生成 QR 二维码
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

        order_sections.append({
            "order": order_info,
            "pages": payload_pages,
            "page_count": n_pages,
        })

        all_page_records.extend(page_records)
        total_item_count += len(order_items)
        total_page_count += n_pages

        # 更新 print_jobs 记录
        db.execute(
            text("""
                INSERT INTO unshipped_print_jobs (order_no, oss_object_name, oss_url, page_count)
                VALUES (:no, :obj, :url, :cnt)
                ON DUPLICATE KEY UPDATE oss_object_name = VALUES(oss_object_name),
                                        oss_url = VALUES(oss_url),
                                        page_count = VALUES(page_count)
            """),
            {"no": order_no, "obj": f"unshipped/{order_no}.pdf", "url": "", "cnt": n_pages},
        )

    db.commit()
    logger.info("待发货单: 生成 %d 个订单共 %d 页", len(order_sections), total_page_count)

    # 构建 payload 并调用 Node 脚本
    payload = {
        "title": "韩酷服饰-待发货单",
        "all_sizes": list(_FIXED_SIZES),
        "order_sections": order_sections,
    }

    script_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "scripts", "generate-unshipped-pdf.cjs")
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
    pdf_bytes = proc.stdout

    # 上传 OSS
    first_order_no = list(order_groups.keys())[0]
    safe_name = re.sub(r'[^\w\-]', '_', first_order_no)
    ts_str = datetime.now().strftime("%Y%m%d%H%M%S")
    object_name = f"unshipped/{safe_name}_{ts_str}.pdf"
    oss_client.upload_file(object_name, pdf_bytes, content_type="application/pdf")

    import time
    ts = int(time.time() * 1000)
    proxy_url = f"/api/sales-orders/oss-file/{object_name}?t={ts}"

    return {
        "oss_url": proxy_url,
        "page_count": total_page_count,
        "item_count": total_item_count,
        "pages": all_page_records,
    }
