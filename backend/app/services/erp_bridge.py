from __future__ import annotations

import logging
import time
from typing import Any

from app.config import settings
from app.ncloud.client.erp_client import ERPClient
from app.ncloud.schemas.sales_orders import (
    AuditAction,
    CreateOrderDetailRow,
    CreateSalesOrderRequest,
    SizeQty,
)
from app.ncloud.services.sales_orders import audit_order, create_order
from app.ncloud.services.unshipped_report import cancel_or_restore, query_unshipped_report

logger = logging.getLogger(__name__)


class ERPBridgeError(Exception):
    pass


# ---- 模块级 ERPClient 引用，由 main.py startup 注入 ----
_erp_client: ERPClient | None = None


def set_erp_client(client: ERPClient) -> None:
    global _erp_client
    _erp_client = client


class ERPBridge:
    def __init__(self) -> None:
        pass

    def _get_client(self) -> ERPClient:
        if _erp_client is None:
            raise ERPBridgeError("ERP 客户端尚未初始化，请确认系统已完成启动")
        return _erp_client

    async def _ensure_login(self) -> ERPClient:
        client = self._get_client()
        t0 = time.time()
        try:
            await client._auth.login()
        except Exception as exc:
            raise ERPBridgeError(f"ERP 登录失败: {exc}") from exc
        logger.info("[PERF] ERP _ensure_login 耗时 %.2fs", time.time() - t0)
        return client

    async def create_sales_order(self, order_data: dict, customer: dict) -> dict:
        client = await self._ensure_login()

        customer_id = customer.get("erp_customer_id") or customer.get("id")
        if not customer_id:
            raise ERPBridgeError("所选客户缺少 ERP 客户编号")

        detail_rows: list[CreateOrderDetailRow] = []
        for item in order_data.get("items", []):
            sizes: list[SizeQty] = []
            for size in item.get("sizes") or []:
                size_name = str(size.get("size") or "").strip()
                qty = int(size.get("qty") or 0)
                if size_name and qty:
                    sizes.append(SizeQty(size=size_name, qty=qty))
            if not item.get("product_no") or not sizes:
                continue
            detail_rows.append(CreateOrderDetailRow(
                brand=item.get("brand") or order_data.get("brand") or settings.ERP_DEFAULT_BRAND,
                product_no=item.get("product_no") or "",
                color=item.get("color") or "",
                sizes=sizes,
                unit=item.get("unit") or "件",
                price=float(item.get("price") or 0),
                discount=int(item.get("discount") or 100),
                packaging=item.get("packaging") or "",
                customer_product_no=item.get("customer_product_no") or "",
                grade=item.get("grade") or "",
                product_spec=item.get("product_spec") or "",
                semi_product_no=item.get("semi_product_no") or "",
                linked_order_ref=item.get("linked_order_ref") or "",
                remark=item.get("remark") or "",
            ))

        if not detail_rows:
            raise ERPBridgeError("订单明细为空，无法下单")

        req = CreateSalesOrderRequest(
            customer_id=str(customer_id),
            order_date=order_data.get("order_date") or "",
            customer_addr=customer.get("address") or "",
            customer_tel=customer.get("phone") or "",
            shipping_addr=customer.get("address") or "",
            shipping_tel=customer.get("phone") or "",
            shipping_method=order_data.get("shipping_method") or settings.ERP_DEFAULT_SHIPPING_METHOD,
            salesperson=order_data.get("salesperson") or settings.ERP_DEFAULT_SALESPERSON,
            order_ref=order_data.get("order_ref") or "",
            currency=order_data.get("currency") or settings.ERP_DEFAULT_CURRENCY,
            brand=order_data.get("brand") or settings.ERP_DEFAULT_BRAND,
            customer_type=order_data.get("customer_type") or settings.ERP_DEFAULT_CUSTOMER_TYPE,
            delivery_date=order_data.get("delivery_date") or "",
            contact_person=customer.get("contact_person") or "",
            plan=order_data.get("plan") or "否",
            price_print=int(order_data.get("price_print") or 1),
            payment_amount=float(order_data.get("payment_amount") or 0),
            remark=order_data.get("remark") or "",
            detail=detail_rows,
        )

        try:
            t1 = time.time()
            result = await create_order(client, req)
            logger.info("[PERF] ERP create_order 耗时 %.2fs", time.time() - t1)
        except Exception as exc:
            raise ERPBridgeError(f"ERP 创建销售订单失败: {exc}") from exc

        order_no = result.dh or ""
        if order_no:
            t2 = time.time()
            await self.audit_sales_order(order_no)
            logger.info("[PERF] ERP audit_sales_order 耗时 %.2fs", time.time() - t2)
        return {
            "order_no": order_no,
            "message": result.message or "ERP 下单成功",
        }

    async def audit_sales_order(self, dh: str) -> dict:
        client = await self._ensure_login()
        try:
            result = await audit_order(client, dh, AuditAction.audit)
        except Exception as exc:
            raise ERPBridgeError(f"ERP 审核订单失败: {exc}") from exc
        return {"dh": result.dh, "message": result.message}

    async def query_unshipped(self, customer_erp_id: str, *, dates: str, datee: str, product_nos: list[str] | None = None, brand: str | None = None) -> list[dict]:
        client = await self._ensure_login()
        t0 = time.time()
        try:
            report = await query_unshipped_report(
                client,
                dates=dates,
                datee=datee,
                customer_id=customer_erp_id or None,
                brand=brand or None,
                product_no=None,
                page=1,
                rows=5000,
            )
        except Exception as exc:
            raise ERPBridgeError(f"ERP 查询未发货报表失败: {exc}") from exc
        logger.info("[PERF] ERP query_unshipped_report 耗时 %.2fs, 返回 %d 行", time.time() - t0, len(report.rows))

        allowed = {item for item in (product_nos or []) if item}
        result: list[dict[str, Any]] = []
        for row in report.rows:
            if allowed and row.product_no not in allowed:
                continue
            result.append({
                "id": row.id or "",
                "order_no": row.order_no or "",
                "product_no": row.product_no or "",
                "color": row.color or "",
                "unshipped_qty": row.unshipped_qty or 0,
            })
        return [item for item in result if item["id"]]

    async def cancel_unshipped(self, ids: list[str]) -> dict:
        if not ids:
            return {"message": "没有可取消的未发货订单", "cancelled_ids": []}
        client = await self._ensure_login()
        t0 = time.time()
        try:
            result = await cancel_or_restore(client, ids, sfwg=1)
        except Exception as exc:
            raise ERPBridgeError(f"ERP 取消未发货失败: {exc}") from exc
        logger.info("[PERF] ERP cancel_unshipped 耗时 %.2fs, 取消 %d 行", time.time() - t0, len(ids))
        return {
            "message": result.message or "取消未发货成功",
            "cancelled_ids": ids,
        }
