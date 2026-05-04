"""Zid Merchant API v1 client."""
from __future__ import annotations
import logging
import requests

logger = logging.getLogger(__name__)


class ZidError(Exception):
    def __init__(self, message: str, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class ZidClient:
    BASE = "https://api.zid.sa/v1"

    def __init__(self, access_token: str, store_id: str = ""):
        self.access_token = access_token
        self.store_id = store_id
        self._s = requests.Session()
        self._s.headers.update({
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "X-Manager-Token": access_token,
        })
        if store_id:
            self._s.headers["Store-Id"] = store_id

    def _req(self, method: str, path: str, **kw) -> dict:
        url = f"{self.BASE}/{path.lstrip('/')}"
        try:
            r = self._s.request(method, url, timeout=30, **kw)
        except requests.RequestException as e:
            raise ZidError(f"Network error: {e}")
        if r.status_code == 429:
            raise ZidError("Zid rate limit exceeded", 429)
        if not r.ok:
            try:
                detail = r.json().get("message", r.text[:200])
            except Exception:
                detail = r.text[:200]
            raise ZidError(f"Zid API {r.status_code}: {detail}", r.status_code)
        return r.json() if r.content else {}

    # ── Products ──────────────────────────────────────────────────────────────
    def list_products(self, page: int = 1, per_page: int = 50, search: str = "") -> dict:
        params: dict = {"page": page, "per_page": min(per_page, 100)}
        if search:
            params["search"] = search
        return self._req("GET", "products", params=params)

    def get_product(self, product_id: str) -> dict:
        return self._req("GET", f"products/{product_id}")

    def create_product(self, name: str, price: float, description: str = "",
                       quantity: int = 0, sku: str = "") -> dict:
        return self._req("POST", "products", json={
            "name": {"ar": name, "en": name},
            "price": price,
            "description": {"ar": description, "en": description},
            "quantity": quantity,
            "sku": sku,
        })

    def update_product(self, product_id: str, **fields) -> dict:
        return self._req("PUT", f"products/{product_id}", json=fields)

    def delete_product(self, product_id: str) -> dict:
        return self._req("DELETE", f"products/{product_id}")

    # ── Orders ────────────────────────────────────────────────────────────────
    def list_orders(self, page: int = 1, per_page: int = 50, status: str = "") -> dict:
        params: dict = {"page": page, "per_page": min(per_page, 100)}
        if status:
            params["status"] = status
        return self._req("GET", "managers/orders", params=params)

    def get_order(self, order_id: str) -> dict:
        return self._req("GET", f"managers/orders/{order_id}")

    # ── Customers ─────────────────────────────────────────────────────────────
    def list_customers(self, page: int = 1, per_page: int = 50) -> dict:
        return self._req("GET", "customers", params={"page": page, "per_page": per_page})

    # ── Categories ────────────────────────────────────────────────────────────
    def list_categories(self) -> dict:
        return self._req("GET", "categories")

    # ── Store info ────────────────────────────────────────────────────────────
    def get_store(self) -> dict:
        return self._req("GET", "store")


def get_client() -> ZidClient:
    from core.config import config
    if not config.ZID_ACCESS_TOKEN:
        raise ZidError("ZID_ACCESS_TOKEN must be set in .env")
    return ZidClient(config.ZID_ACCESS_TOKEN, config.ZID_STORE_ID)
