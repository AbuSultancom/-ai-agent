"""Salla Admin API v2 client (OAuth 2.0 bearer token)."""
from __future__ import annotations
import logging
import requests

logger = logging.getLogger(__name__)


class SallaError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class SallaClient:
    BASE = "https://api.salla.dev/admin/v2"

    def __init__(self, access_token: str):
        self.access_token = access_token
        self._s = requests.Session()
        self._s.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })

    def _req(self, method: str, path: str, **kw) -> dict:
        url = f"{self.BASE}/{path.lstrip('/')}"
        try:
            r = self._s.request(method, url, timeout=30, **kw)
        except requests.RequestException as e:
            raise SallaError(f"Network error: {e}")
        if r.status_code == 429:
            raise SallaError("Salla rate limit exceeded", 429)
        if not r.ok:
            try:
                detail = r.json().get("error", {}).get("message", r.text[:200])
            except Exception:
                detail = r.text[:200]
            raise SallaError(f"Salla API {r.status_code}: {detail}", r.status_code)
        return r.json() if r.content else {}

    # ── Products ──────────────────────────────────────────────────────────────
    def list_products(self, page: int = 1, per_page: int = 50, keyword: str = "") -> dict:
        params: dict = {"page": page, "per_page": min(per_page, 100)}
        if keyword:
            params["keyword"] = keyword
        return self._req("GET", "products", params=params)

    def get_product(self, product_id: int) -> dict:
        return self._req("GET", f"products/{product_id}")

    def create_product(self, name: str, price: float, description: str = "",
                       quantity: int = 0, sku: str = "") -> dict:
        return self._req("POST", "products", json={
            "name": name, "price": price, "description": description,
            "quantity": quantity, "sku": sku,
        })

    def update_product(self, product_id: int, **fields) -> dict:
        return self._req("PUT", f"products/{product_id}", json=fields)

    def delete_product(self, product_id: int) -> dict:
        return self._req("DELETE", f"products/{product_id}")

    # ── Orders ────────────────────────────────────────────────────────────────
    def list_orders(self, page: int = 1, per_page: int = 50, status: str = "") -> dict:
        params: dict = {"page": page, "per_page": min(per_page, 100)}
        if status:
            params["status"] = status
        return self._req("GET", "orders", params=params)

    def get_order(self, order_id: int) -> dict:
        return self._req("GET", f"orders/{order_id}")

    def update_order_status(self, order_id: int, status: str) -> dict:
        return self._req("PUT", f"orders/{order_id}/status", json={"status": status})

    # ── Customers ─────────────────────────────────────────────────────────────
    def list_customers(self, page: int = 1, per_page: int = 50) -> dict:
        return self._req("GET", "customers", params={"page": page, "per_page": per_page})

    def get_customer(self, customer_id: int) -> dict:
        return self._req("GET", f"customers/{customer_id}")

    # ── Categories ────────────────────────────────────────────────────────────
    def list_categories(self) -> dict:
        return self._req("GET", "categories")

    # ── Store info ────────────────────────────────────────────────────────────
    def get_store(self) -> dict:
        return self._req("GET", "store/info")


def get_client() -> SallaClient:
    from core.config import config
    if not config.SALLA_ACCESS_TOKEN:
        raise SallaError("SALLA_ACCESS_TOKEN must be set in .env")
    return SallaClient(config.SALLA_ACCESS_TOKEN)
