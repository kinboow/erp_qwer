import httpx

from app.config import settings


class ERPBridgeError(Exception):
    pass


class ERPBridge:
    def __init__(self) -> None:
        self.base_url = settings.ERP_BASE_URL.rstrip("/")

    def _ensure_enabled(self):
        if not self.base_url:
            raise ERPBridgeError("未配置 ERP_BASE_URL，请先指向 ncloud2API 服务地址")

    async def _login(self, client: httpx.AsyncClient):
        self._ensure_enabled()
        response = await client.post(f"{self.base_url}/api/login", timeout=30)
        response.raise_for_status()

    async def _request(self, method: str, path: str, *, params=None, json_data=None) -> dict:
        async with httpx.AsyncClient(follow_redirects=True, timeout=60) as client:
            await self._login(client)
            response = await client.request(method, f"{self.base_url}{path}", params=params, json=json_data)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict) and payload.get("detail"):
                raise ERPBridgeError(str(payload.get("detail")))
            return payload

    async def create_sales_order(self, order_data: dict, customer: dict) -> dict:
        customer_id = customer.get("erp_customer_id") or customer.get("id")
        if not customer_id:
            raise ERPBridgeError("所选客户缺少 ERP 客户编号")

        detail_rows = []
        for item in order_data.get("items", []):
            sizes = []
            for size in item.get("sizes") or []:
                size_name = str(size.get("size") or "").strip()
                qty = int(size.get("qty") or 0)
                if size_name and qty:
                    sizes.append({"size": size_name, "qty": qty})
            if not item.get("product_no") or not sizes:
                continue
            detail_rows.append({
                "brand": item.get("brand") or order_data.get("brand") or settings.ERP_DEFAULT_BRAND,
                "product_no": item.get("product_no") or "",
                "color": item.get("color") or "",
                "sizes": sizes,
                "unit": item.get("unit") or "件",
                "price": float(item.get("price") or 0),
                "discount": int(item.get("discount") or 100),
                "packaging": item.get("packaging") or "",
                "customer_product_no": item.get("customer_product_no") or "",
                "grade": item.get("grade") or "",
                "product_spec": item.get("product_spec") or "",
                "semi_product_no": item.get("semi_product_no") or "",
                "linked_order_ref": item.get("linked_order_ref") or "",
                "remark": item.get("remark") or "",
            })

        if not detail_rows:
            raise ERPBridgeError("订单明细为空，无法下单")

        payload = await self._request(
            "POST",
            "/api/sales-orders",
            json_data={
                "customer_id": str(customer_id),
                "order_date": order_data.get("order_date") or "",
                "customer_addr": customer.get("address") or "",
                "customer_tel": customer.get("phone") or "",
                "shipping_addr": customer.get("address") or "",
                "shipping_tel": customer.get("phone") or "",
                "shipping_method": order_data.get("shipping_method") or settings.ERP_DEFAULT_SHIPPING_METHOD,
                "salesperson": order_data.get("salesperson") or settings.ERP_DEFAULT_SALESPERSON,
                "order_ref": order_data.get("order_ref") or "",
                "currency": order_data.get("currency") or settings.ERP_DEFAULT_CURRENCY,
                "brand": order_data.get("brand") or settings.ERP_DEFAULT_BRAND,
                "customer_type": order_data.get("customer_type") or settings.ERP_DEFAULT_CUSTOMER_TYPE,
                "delivery_date": order_data.get("delivery_date") or "",
                "contact_person": customer.get("contact_person") or "",
                "plan": order_data.get("plan") or "否",
                "price_print": int(order_data.get("price_print") or 1),
                "payment_amount": float(order_data.get("payment_amount") or 0),
                "remark": order_data.get("remark") or "",
                "detail": detail_rows,
            },
        )
        order_no = payload.get("dh") or payload.get("order_no") or payload.get("data") or ""
        if order_no:
            await self.audit_sales_order(order_no)
        return {
            "order_no": order_no,
            "message": payload.get("message") or payload.get("Message") or "ERP 下单成功",
        }

    async def audit_sales_order(self, dh: str) -> dict:
        return await self._request("POST", f"/api/sales-orders/{dh}/audit", json_data={"action": "audit"})

    async def query_unshipped(self, customer_erp_id: str, *, dates: str, datee: str, product_nos: list[str] | None = None, brand: str | None = None) -> list[dict]:
        payload = await self._request(
            "GET",
            "/api/unshipped-report",
            params={
                "dates": dates,
                "datee": datee,
                "customer_id": str(customer_erp_id),
                "brand": brand or None,
                "page": 1,
                "rows": 5000,
            },
        )
        rows = payload.get("rows", []) if isinstance(payload, dict) else []
        allowed = {item for item in (product_nos or []) if item}
        result = []
        for row in rows:
            if allowed and row.get("product_no") not in allowed:
                continue
            result.append({
                "id": str(row.get("id") or ""),
                "order_no": row.get("order_no") or "",
                "product_no": row.get("product_no") or "",
                "color": row.get("color") or "",
                "unshipped_qty": row.get("unshipped_qty") or 0,
            })
        return [item for item in result if item["id"]]

    async def cancel_unshipped(self, ids: list[str]) -> dict:
        if not ids:
            return {"message": "没有可取消的未发货订单", "cancelled_ids": []}
        payload = await self._request("POST", "/api/unshipped-report/cancel", json_data={"ids": ids})
        return {
            "message": payload.get("message") or "取消未发货成功",
            "cancelled_ids": ids,
        }
