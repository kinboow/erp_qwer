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
# PDF 生成核心
# ---------------------------------------------------------------------------
def _build_unshipped_pdf(
    order_info: dict[str, Any],
    items: list[dict[str, Any]],
    page_records: list[dict[str, str]],
) -> bytes:
    all_sizes = list(_FIXED_SIZES)
    blocks = _group_items_to_product_blocks(items)
    block_pages = _paginate_blocks(blocks)
    total_pages = len(block_pages)

    # 确保 page_records 数量匹配
    while len(page_records) < total_pages:
        pid = uuid.uuid4().hex[:16]
        page_records.append({
            "page_index": len(page_records),
            "page_id": pid,
            "barcode_content": f"UNSHIPPED|{pid}",
        })

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
        "title": "韩酷服饰-待发货单",
        "order": order_info,
        "all_sizes": all_sizes,
        "pages": payload_pages,
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
    return proc.stdout


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------
def generate_unshipped_pdf(db: Session, item_ids: list[int], customer_name: str = "") -> dict[str, Any]:
    """
    根据传入的 unshipped report 行 ID 列表，生成待发货单 PDF。
    支持单条或多条（批量打印）。
    """
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

    items = []
    total_order_qty = 0
    total_unshipped_qty = 0
    order_nos = set()

    for r in rows:
        item = dict(r)
        raw = item.pop("unshipped_sizes_json", None) or "[]"
        try:
            item["unshipped_sizes"] = json.loads(raw)
        except Exception:
            item["unshipped_sizes"] = []
        item.pop("order_sizes_json", None)
        items.append(item)
        total_order_qty += int(item.get("order_qty") or 0)
        total_unshipped_qty += int(item.get("unshipped_qty") or 0)
        order_nos.add(item.get("order_no", ""))

    first = items[0]
    order_no_display = first.get("order_no", "")
    if len(order_nos) > 1:
        order_no_display = f"{order_no_display} 等{len(order_nos)}单"

    # 从销售订单主表查询客户详细信息
    order_extra = {}
    primary_order_no = first.get("order_no", "")
    if primary_order_no:
        order_row = db.execute(
            text("""
                SELECT order_no, order_date, customer_name, customer_tel, customer_addr,
                       creator, remark
                FROM erp_sales_orders WHERE order_no = :no
            """),
            {"no": primary_order_no},
        ).mappings().first()
        if order_row:
            order_extra = dict(order_row)

    order_info = {
        "order_no": order_no_display,
        "order_date": str(order_extra.get("order_date") or first.get("order_date") or ""),
        "customer_name": order_extra.get("customer_name") or customer_name or str(first.get("customer_id") or ""),
        "customer_tel": str(order_extra.get("customer_tel") or ""),
        "customer_addr": str(order_extra.get("customer_addr") or ""),
        "creator": str(order_extra.get("creator") or ""),
        "remark": re.sub(r"\[RV[A-Za-z0-9]+\]\s*", "", str(order_extra.get("remark") or "")).strip()[:120],
        "total_order_qty": total_order_qty,
        "total_unshipped_qty": total_unshipped_qty,
    }

    page_records = []
    for i in range(50):  # pre-allocate enough
        pid = uuid.uuid4().hex[:16]
        bc = f"UNSHIPPED|{order_no_display}|{pid}"
        page_records.append({
            "page_index": i,
            "page_id": pid,
            "barcode_content": bc,
        })

    pdf_bytes = _build_unshipped_pdf(order_info, items, page_records)

    # 上传 OSS
    ts = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = re.sub(r'[^\w\-]', '_', order_no_display)
    object_name = f"unshipped/{safe_name}_{ts}.pdf"
    oss_client.upload_file(object_name, pdf_bytes, content_type="application/pdf")

    import time
    proxy_url = f"/api/sales-orders/oss-file/{object_name}?t={int(time.time() * 1000)}"

    return {
        "oss_url": proxy_url,
        "page_count": 1,
        "item_count": len(items),
    }
