from __future__ import annotations

from pprint import pprint

from fastapi.testclient import TestClient

from app import app


def main() -> None:
    with TestClient(app) as client:
        # --- auth ---
        login = client.post("/api/login")
        print("POST /api/login", login.status_code)
        pprint(login.json())

        account_set = client.get("/api/account-set")
        print("GET /api/account-set", account_set.status_code)
        pprint(account_set.json())

        # --- products ---
        products = client.get("/api/products", params={"rows": 2})
        print("GET /api/products", products.status_code)
        pprint(products.json())

        # --- sales orders list ---
        orders = client.get(
            "/api/sales-orders",
            params={"dates": "2026-04-01", "datee": "2026-04-13", "rows": 2},
        )
        print("GET /api/sales-orders", orders.status_code)
        pprint(orders.json())

        # --- sales order detail ---
        rows = orders.json().get("rows", [])
        if rows:
            dh = rows[0].get("order_no") or rows[0].get("dh")
            detail = client.get(f"/api/sales-orders/{dh}")
            print(f"GET /api/sales-orders/{dh}", detail.status_code)
            pprint(detail.json())

        # --- shipments list ---
        shipments = client.get(
            "/api/sales-shipments",
            params={"dates": "2026-04-01", "datee": "2026-04-13", "rows": 2},
        )
        print("GET /api/sales-shipments", shipments.status_code)
        pprint(shipments.json())

        # --- shipment detail ---
        ship_rows = shipments.json().get("rows", [])
        if ship_rows:
            sdh = ship_rows[0].get("order_no") or ship_rows[0].get("dh")
            ship_detail = client.get(f"/api/sales-shipments/{sdh}")
            print(f"GET /api/sales-shipments/{sdh}", ship_detail.status_code)
            pprint(ship_detail.json())

        # --- reconciliation ---
        recon = client.get(
            "/api/sales-reconciliation",
            params={
                "customer_name": "钟江锋",
                "dates": "2026-04-01",
                "datee": "2026-04-14",
            },
        )
        print("GET /api/sales-reconciliation", recon.status_code)
        pprint(recon.json())

        # --- unshipped report ---
        unshipped = client.get(
            "/api/unshipped-report",
            params={"dates": "2026-04-14", "datee": "2026-04-15", "rows": 2},
        )
        print("GET /api/unshipped-report", unshipped.status_code)
        pprint(unshipped.json())

        # --- inventory ---
        inventory = client.get(
            "/api/inventory",
            params={"rows": 2},
        )
        print("GET /api/inventory", inventory.status_code)
        pprint(inventory.json())


if __name__ == "__main__":
    main()
