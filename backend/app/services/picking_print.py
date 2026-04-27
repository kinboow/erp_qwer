"""
拣货单打印服务 — 生成 PDF（含条形码），上传 OSS，幂等（重复打印返回同一份）
"""

from __future__ import annotations

import io
import json
import logging
import uuid
from datetime import datetime
from typing import Any

import barcode
from barcode.writer import ImageWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Spacer, Paragraph, Image as RLImage,
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.utils.oss_client import oss_client

logger = logging.getLogger(__name__)

PAGE_W, PAGE_H = A4  # 595.27, 841.89 pt

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

    import platform
    import os

    candidates = []
    if platform.system() == "Windows":
        windir = os.environ.get("WINDIR", r"C:\Windows")
        candidates = [
            os.path.join(windir, "Fonts", "msyh.ttc"),     # 微软雅黑
            os.path.join(windir, "Fonts", "simsun.ttc"),    # 宋体
            os.path.join(windir, "Fonts", "simhei.ttf"),    # 黑体
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/System/Library/Fonts/PingFang.ttc",
        ]

    for path in candidates:
        if os.path.isfile(path):
            try:
                pdfmetrics.registerFont(TTFont(font_name, path))
                _FONT_REGISTERED = True
                logger.info("拣货单: 注册字体 %s -> %s", font_name, path)
                return font_name
            except Exception as e:
                logger.warning("拣货单: 注册字体失败 %s: %s", path, e)

    # 回退到 Helvetica（不支持中文但至少不崩溃）
    logger.warning("拣货单: 未找到中文字体，回退 Helvetica")
    return "Helvetica"


# ---------------------------------------------------------------------------
# 条形码生成
# ---------------------------------------------------------------------------
def _generate_barcode_image(content: str, width_mm: float = 50, height_mm: float = 12) -> io.BytesIO:
    """生成 Code128 条形码 PNG 图片，返回 BytesIO"""
    code128 = barcode.get_barcode_class("code128")
    writer = ImageWriter()
    writer.set_options({
        "module_width": 0.25,
        "module_height": height_mm,
        "font_size": 6,
        "text_distance": 2,
        "quiet_zone": 2,
    })
    bc = code128(content, writer=writer)
    buf = io.BytesIO()
    bc.write(buf, options={"write_text": True})
    buf.seek(0)
    return buf


# ---------------------------------------------------------------------------
# PDF 生成核心
# ---------------------------------------------------------------------------
def _build_picking_pdf(
    order: dict[str, Any],
    items: list[dict[str, Any]],
    page_records: list[dict[str, str]],
) -> bytes:
    """
    生成拣货单 PDF。

    page_records: [{"page_index": 0, "page_id": "xxx", "barcode_content": "SO2025...|xxx"}, ...]
    """
    font_name = _register_chinese_font()

    buf = io.BytesIO()

    # 手动逐页绘制（用 canvas 而非 platypus）以精确控制条形码位置
    from reportlab.pdfgen import canvas as pdf_canvas

    c = pdf_canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"拣货单 - {order.get('order_no', '')}")

    # 样式参数
    margin_x = 20 * mm
    margin_top = 25 * mm
    margin_bottom = 25 * mm
    barcode_w = 45 * mm
    barcode_h = 12 * mm

    # ---------------------------------------------------------------
    # 分页：按固定行数分页，每页最多 N 个明细行
    # ---------------------------------------------------------------
    ITEMS_PER_PAGE = 20  # 每页最多放20个明细行
    total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    # 确保 page_records 数量匹配
    assert len(page_records) == total_pages, f"page_records({len(page_records)}) != total_pages({total_pages})"

    for page_idx in range(total_pages):
        if page_idx > 0:
            c.showPage()

        pr = page_records[page_idx]
        bc_content = pr["barcode_content"]

        # -- 条形码：右上角 --
        bc_buf1 = _generate_barcode_image(bc_content, width_mm=50, height_mm=10)
        bc_img1 = RLImage(bc_buf1, width=barcode_w, height=barcode_h)
        bc_img1.drawOn(c, PAGE_W - margin_x - barcode_w, PAGE_H - margin_top + 2 * mm)

        # -- 条形码：左下角 --
        bc_buf2 = _generate_barcode_image(bc_content, width_mm=50, height_mm=10)
        bc_img2 = RLImage(bc_buf2, width=barcode_w, height=barcode_h)
        bc_img2.drawOn(c, margin_x, margin_bottom - barcode_h - 2 * mm)

        # -- 标题 --
        c.setFont(font_name, 16)
        c.drawCentredString(PAGE_W / 2, PAGE_H - margin_top + 5 * mm, "拣 货 单")

        # -- 订单信息头 --
        y = PAGE_H - margin_top - 12 * mm
        c.setFont(font_name, 9)
        info_lines = [
            f"订单号: {order.get('order_no', '')}    日期: {order.get('order_date', '')}    客户: {order.get('customer_name', '')}",
            f"业务员: {order.get('salesperson', '')}    备注: {(order.get('remark') or '')[:60]}    页 {page_idx + 1}/{total_pages}",
        ]
        for line in info_lines:
            c.drawString(margin_x, y, line)
            y -= 5 * mm

        y -= 3 * mm

        # -- 明细表格 --
        page_items = items[page_idx * ITEMS_PER_PAGE: (page_idx + 1) * ITEMS_PER_PAGE]

        # 表头
        header = ["#", "货号", "品名", "颜色", "尺码明细", "小计", "备注"]
        col_widths = [8 * mm, 28 * mm, 22 * mm, 18 * mm, 60 * mm, 14 * mm, 25 * mm]

        table_data = [header]
        for idx, item in enumerate(page_items):
            global_idx = page_idx * ITEMS_PER_PAGE + idx + 1
            sizes = item.get("sizes") or []
            size_str = "  ".join(f"{s.get('size', '')}:{s.get('qty', 0)}" for s in sizes) if sizes else "-"
            table_data.append([
                str(global_idx),
                item.get("product_no", "") or "",
                (item.get("product_name", "") or "")[:8],
                (item.get("color", "") or "")[:6],
                size_str[:50],
                str(int(item.get("total_qty", 0))),
                (item.get("remark", "") or "")[:10],
            ])

        t = Table(table_data, colWidths=col_widths)
        t.setStyle(TableStyle([
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 7.5),
            ("FONTSIZE", (0, 0), (-1, 0), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e8ecf0")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#333333")),
            ("FONTNAME", (0, 0), (-1, 0), font_name),
            ("ALIGN", (0, 0), (-1, 0), "CENTER"),
            ("ALIGN", (0, 1), (0, -1), "CENTER"),
            ("ALIGN", (5, 1), (5, -1), "RIGHT"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cccccc")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
        ]))

        tw, th = t.wrap(0, 0)
        t.drawOn(c, margin_x, y - th)

    c.save()
    return buf.getvalue()


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

    # 3. 计算页数
    items_per_page = 20
    total_pages = max(1, (len(items) + items_per_page - 1) // items_per_page)

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

    proxy_url = f"/api/sales-orders/oss-file/{object_name}"

    return {
        "oss_url": proxy_url,
        "page_count": total_pages,
        "pages": page_records,
    }
